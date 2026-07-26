/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFPureEntry

/-!
# Bounded ELF64 decoder for the x86 pure-entry boundary

This module is the first concrete byte-level layer underneath
`Architecture.X86ELF.PureEntryModel`.  It parses the complete ELF64 header,
every program header, every `PT_LOAD` file slice, and (when present) every
section header.  All offsets and sizes are converted to unbounded `Nat`
values before bounds checks, so a malformed 64-bit sum cannot be accepted
through machine-word wraparound.

The accepted format is deliberately narrow:

* ELF64, little endian, current ELF version, System V OSABI version zero;
* `ET_EXEC` for `EM_X86_64`;
* ordinary (non-extended) program- and section-header counts;
* 56-byte program headers and, when present, 64-byte section headers;
* bounded file slices for all program headers and non-`SHT_NOBITS` sections;
* range-safe, aligned `PT_LOAD` segments with no unknown permission bits.

`PT_INTERP` and `PT_DYNAMIC` are retained as policy flags.  `SHT_REL`,
`SHT_RELA`, and `SHT_RELR` are conservatively treated as unapplied-relocation
evidence.  This may reject a static executable that merely retained already
applied relocation metadata, but it cannot silently bless relocation
evidence.

When a static symbol table is present, every 24-byte ELF64 row and every
bounded NUL-terminated UTF-8 name is decoded through its exact linked
`SHT_STRTAB`.  The selected `tg_sq218_verify_snapshot_v2` definition must be
unique, `STB_GLOBAL`, `STT_FUNC`, nonempty, defined in an executable section,
and equal to `e_entry`.  Only that exact selected pair is exposed through
`ELF64Image.symbols`.  `decodeSelectedImage` fails closed for stripped
images or a missing selected definition, and its soundness theorem constructs
`ELF64Image.EntryAdmissible`.

No executable is run, and this module uses no axiom, `sorry`, or
`native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.X86ELF

namespace ELF64Decoder

private def elfClass64 : Nat := 2
private def elfDataLittleEndian : Nat := 1
private def elfCurrentVersion : Nat := 1
private def etExecutable : Nat := 2
private def emX86_64 : Nat := 62
private def elf64HeaderSize : Nat := 64
private def elf64ProgramHeaderSize : Nat := 56
private def elf64SectionHeaderSize : Nat := 64
private def pnExtended : Nat := 0xffff
private def shnExtended : Nat := 0xffff
private def addressSpaceSize : Nat := 2 ^ 64

private def ptLoad : Nat := 1
private def ptDynamic : Nat := 2
private def ptInterp : Nat := 3

private def shtSymtab : Nat := 2
private def shtStrtab : Nat := 3
private def shtRela : Nat := 4
private def shtNoBits : Nat := 8
private def shtRel : Nat := 9
private def shtRelr : Nat := 19

/-- The one symbol selected by the Sqrt218 pure-entry architecture model. -/
def selectedEntrySymbol : String :=
  "tg_sq218_verify_snapshot_v2"

/-- Reasons the strict decoder rejects an image.  Constructors carrying an
index identify the malformed program or section header without retaining a
large trace. -/
inductive DecodeError where
  | truncatedHeader
  | badMagic
  | wrongClass
  | wrongEndianness
  | badIdentificationVersion
  | wrongOSABI
  | badABIVersion
  | badIdentificationPadding
  | notExecutable
  | wrongMachine
  | badELFVersion
  | unsupportedProcessorFlags
  | badELFHeaderSize
  | missingProgramHeaders
  | unsupportedExtendedProgramHeaderCount
  | badProgramHeaderSize
  | badProgramHeaderTable
  | unsupportedExtendedSectionHeaderCount
  | unsupportedExtendedSectionNameIndex
  | badSectionHeaderLayout
  | badSectionHeaderTable
  | truncatedProgramHeader (index : Nat)
  | invalidProgramFileRange (index : Nat)
  | invalidLoadPermissions (index : Nat)
  | loadFileLargerThanMemory (index : Nat)
  | emptyLoadMemoryRange (index : Nat)
  | loadAddressOverflow (index : Nat)
  | invalidLoadAlignment (index : Nat)
  | loadPolicyInvariantFailure
  | overlappingLoadSegments
  | entryNotInExecutableLoad
  | truncatedSectionHeader (index : Nat)
  | invalidSectionFileRange (index : Nat)
  | invalidSectionAlignment (index : Nat)
  | invalidRelocationEntrySize (index : Nat)
  | invalidSymbolTableEntrySize (sectionIndex : Nat)
  | invalidSymbolTableLink (sectionIndex : Nat)
  | invalidStringTable (sectionIndex : Nat)
  | truncatedSymbol
      (sectionIndex symbolIndex : Nat)
  | invalidSymbolNameOffset
      (sectionIndex symbolIndex : Nat)
  | unterminatedSymbolName
      (sectionIndex symbolIndex : Nat)
  | invalidSymbolNameUTF8
      (sectionIndex symbolIndex : Nat)
  | invalidNullSymbol (sectionIndex : Nat)
  | invalidSymbolBinding
      (sectionIndex symbolIndex : Nat)
  | invalidSymbolVisibility
      (sectionIndex symbolIndex : Nat)
  | invalidSymbolSectionIndex
      (sectionIndex symbolIndex : Nat)
  | invalidSelectedSymbolBinding
      (sectionIndex symbolIndex : Nat)
  | invalidSelectedSymbolType
      (sectionIndex symbolIndex : Nat)
  | undefinedSelectedSymbol
      (sectionIndex symbolIndex : Nat)
  | zeroSizedSelectedSymbol
      (sectionIndex symbolIndex : Nat)
  | selectedSymbolOutsideExecutableSection
      (sectionIndex symbolIndex : Nat)
  | selectedSymbolEntryMismatch
      (sectionIndex symbolIndex : Nat)
  | duplicateSelectedSymbolDefinitions
  | noLoadSegments
  deriving DecidableEq, Repr

/-- An exact bounded byte slice.  The subtraction-form check avoids even a
temporary unchecked `offset + length` test. -/
def checkedSlice?
    (bytes : ByteArray) (offset length : Nat) : Option ByteArray :=
  if offset ≤ bytes.size ∧ length ≤ bytes.size - offset then
    some (bytes.extract offset (offset + length))
  else
    none

/-- Successful slicing exposes both bounds and the exact retained slice. -/
theorem checkedSlice?_eq_some
    {bytes : ByteArray} {offset length : Nat} {slice : ByteArray}
    (h : checkedSlice? bytes offset length = some slice) :
    offset ≤ bytes.size ∧
      offset + length ≤ bytes.size ∧
      slice = bytes.extract offset (offset + length) ∧
      slice.size = length := by
  unfold checkedSlice? at h
  split at h
  · rename_i hbounds
    simp only [Option.some.injEq] at h
    subst slice
    refine ⟨hbounds.1, ?_, rfl, ?_⟩
    · omega
    · rw [ByteArray.size_extract]
      omega
  · simp at h

/-- Little-endian natural-number decoding over an exactly bounded slice. -/
def readNatLE?
    (bytes : ByteArray) (offset width : Nat) : Option Nat := do
  let slice ← checkedSlice? bytes offset width
  return (List.range width).foldl
    (fun value index =>
      value + (slice.get! index).toNat * 256 ^ index)
    0

/-- A successful little-endian read cannot have crossed the input boundary. -/
theorem readNatLE?_bounds
    {bytes : ByteArray} {offset width value : Nat}
    (h : readNatLE? bytes offset width = some value) :
    offset ≤ bytes.size ∧ offset + width ≤ bytes.size := by
  unfold readNatLE? at h
  cases hs : checkedSlice? bytes offset width with
  | none =>
      simp [hs] at h
  | some slice =>
      have hslice := checkedSlice?_eq_some hs
      exact ⟨hslice.1, hslice.2.1⟩

private def require
    (condition : Bool) (error : DecodeError) : Except DecodeError Unit :=
  if condition then .ok () else .error error

private def read
    (bytes : ByteArray) (offset width : Nat)
    (error : DecodeError) : Except DecodeError Nat :=
  match readNatLE? bytes offset width with
  | some value => .ok value
  | none => .error error

private def exactBytes
    (bytes : ByteArray) (offset : Nat) (expected : List Nat)
    (error : DecodeError) : Except DecodeError Unit := do
  let actual ←
    match checkedSlice? bytes offset expected.length with
    | some value => .ok value
    | none => .error error
  require
    (actual == (expected.map UInt8.ofNat).toByteArray)
    error

private def validAlignment (alignment : Nat) : Bool :=
  alignment == 0 ||
    alignment == 1 ||
    decide (Nat.isPowerOfTwo alignment)

/-- One completely decoded ELF64 program header.  The exact file payload is
retained for every header, not only `PT_LOAD`, and `rawFlags` preserves all
32 flag bits. -/
structure ProgramHeader where
  index : Nat
  segmentType : Nat
  rawFlags : Nat
  fileOffset : Nat
  virtualAddress : Nat
  physicalAddress : Nat
  fileByteLength : Nat
  memoryByteLength : Nat
  alignment : Nat
  fileBytes : ByteArray
  deriving DecidableEq

namespace ProgramHeader

def isLoad (header : ProgramHeader) : Bool :=
  header.segmentType == ptLoad

def isInterpreter (header : ProgramHeader) : Bool :=
  header.segmentType == ptInterp

def isDynamic (header : ProgramHeader) : Bool :=
  header.segmentType == ptDynamic

def toLoadSegment? (header : ProgramHeader) : Option LoadSegment :=
  if header.isLoad then
    some {
      fileOffset := header.fileOffset
      virtualAddress := UInt64.ofNat header.virtualAddress
      fileBytes := header.fileBytes
      memoryByteLength := header.memoryByteLength
      readable := header.rawFlags.testBit 2
      writable := header.rawFlags.testBit 1
      executable := header.rawFlags.testBit 0
    }
  else
    none

end ProgramHeader

/-- One decoded section header.  `fileBytes = none` occurs exactly for
`SHT_NOBITS`; all other sections retain their exact bounded file slice. -/
structure SectionHeader where
  index : Nat
  nameOffset : Nat
  sectionType : Nat
  rawFlags : Nat
  virtualAddress : Nat
  fileOffset : Nat
  byteLength : Nat
  link : Nat
  info : Nat
  alignment : Nat
  entrySize : Nat
  fileBytes : Option ByteArray
  deriving DecidableEq

namespace SectionHeader

def isRelocationEvidence (header : SectionHeader) : Bool :=
  header.sectionType == shtRel ||
    header.sectionType == shtRela ||
    header.sectionType == shtRelr

def isStaticSymbolTable (header : SectionHeader) : Bool :=
  header.sectionType == shtSymtab

def isStringTable (header : SectionHeader) : Bool :=
  header.sectionType == shtStrtab

/-- The mandatory all-zero section-header-table sentinel. -/
def isNullSentinel (header : SectionHeader) : Bool :=
  header.nameOffset == 0 &&
    header.sectionType == 0 &&
    header.rawFlags == 0 &&
    header.virtualAddress == 0 &&
    header.fileOffset == 0 &&
    header.byteLength == 0 &&
    header.link == 0 &&
    header.info == 0 &&
    header.alignment == 0 &&
    header.entrySize == 0

end SectionHeader

/-- One exact 24-byte ELF64 symbol-table row and its bounded UTF-8 name. -/
structure Symbol where
  tableSectionIndex : Nat
  symbolIndex : Nat
  nameOffset : Nat
  nameBytes : ByteArray
  name : String
  binding : Nat
  symbolType : Nat
  visibility : Nat
  sectionIndex : Nat
  value : Nat
  byteLength : Nat
  deriving DecidableEq

namespace Symbol

def isNullSentinel (symbol : Symbol) : Bool :=
  symbol.nameOffset == 0 &&
    symbol.nameBytes.isEmpty &&
    symbol.name.isEmpty &&
    symbol.binding == 0 &&
    symbol.symbolType == 0 &&
    symbol.visibility == 0 &&
    symbol.sectionIndex == 0 &&
    symbol.value == 0 &&
    symbol.byteLength == 0

def hasSelectedName (symbol : Symbol) : Bool :=
  symbol.name == selectedEntrySymbol

end Symbol

private structure SelectedSymbolAtEntry
    (entryAddress : Nat) : Type where
  symbol : Symbol
  value_eq : symbol.value = entryAddress

/-- Exact selected-entry resolution status.  A present static symbol table
that contains no selected definition is distinguished from a stripped image. -/
inductive EntrySymbolStatus where
  | unresolvedNoSymbolTable
  | unresolvedSelectedNotFound
  | resolvedSelected (address : UInt64)
  deriving DecidableEq, Repr

/-- Conservative result of scanning section headers for relocation metadata. -/
inductive RelocationEvidence where
  | sectionTableAbsent
  | noneFound
  | relocationSectionPresent
  deriving DecidableEq, Repr

/-- Complete output of the bounded decoder.  Proof fields expose the
restricted header/load policy and the exact selected-symbol binding without
unfolding the parser. -/
structure DecodedELF64 where
  image : ELF64Image
  programHeaders : List ProgramHeader
  sectionHeaders : List SectionHeader
  staticSymbols : List Symbol
  entrySymbolStatus : EntrySymbolStatus
  relocationEvidence : RelocationEvidence
  littleEndian : image.endianness = .little
  executable : image.objectType = .executable
  x86_64 : image.machineIsX86_64 = true
  uniqueSymbolNames : image.UniqueSymbolNames
  selectedSymbolsOnly :
    ∀ {name : String} {address : UInt64},
      image.SymbolAt name address →
        name = selectedEntrySymbol
  resolvedSelectedSymbol :
    ∀ {address : UInt64},
      entrySymbolStatus = .resolvedSelected address →
        image.SymbolAt selectedEntrySymbol address
  resolvedSelectedAtEntry :
    ∀ {address : UInt64},
      entrySymbolStatus = .resolvedSelected address →
        address = image.entryAddress
  nonemptyLoadSegments : image.segments ≠ []
  safeLoadSegments : image.SafeLoadSegments
  disjointLoadSegments : image.DisjointLoadSegments
  entryInExecutableLoad :
    ∃ segment ∈ image.segments,
      segment.executable = true ∧
        segment.ContainsVirtualAddress image.entryAddress
  loadSegmentsExact :
    image.segments = programHeaders.filterMap ProgramHeader.toLoadSegment?
  interpreterFlagExact :
    image.hasProgramInterpreter =
      programHeaders.any ProgramHeader.isInterpreter
  dynamicFlagExact :
    image.hasDynamicSection =
      programHeaders.any ProgramHeader.isDynamic
  relocationFlagExact :
    image.hasUnappliedRelocations =
      sectionHeaders.any SectionHeader.isRelocationEvidence

private def parseProgramHeader
    (bytes : ByteArray) (tableOffset index : Nat) :
    Except DecodeError ProgramHeader := do
  let base := tableOffset + index * elf64ProgramHeaderSize
  let truncated := DecodeError.truncatedProgramHeader index
  let segmentType ← read bytes base 4 truncated
  let rawFlags ← read bytes (base + 4) 4 truncated
  let fileOffset ← read bytes (base + 8) 8 truncated
  let virtualAddress ← read bytes (base + 16) 8 truncated
  let physicalAddress ← read bytes (base + 24) 8 truncated
  let fileByteLength ← read bytes (base + 32) 8 truncated
  let memoryByteLength ← read bytes (base + 40) 8 truncated
  let alignment ← read bytes (base + 48) 8 truncated
  let fileBytes ←
    match checkedSlice? bytes fileOffset fileByteLength with
    | some payload => .ok payload
    | none => .error (.invalidProgramFileRange index)
  if segmentType == ptLoad then
    require (rawFlags < 8) (.invalidLoadPermissions index)
    require
      (!(rawFlags.testBit 1 && rawFlags.testBit 0))
      (.invalidLoadPermissions index)
    require
      (fileByteLength ≤ memoryByteLength)
      (.loadFileLargerThanMemory index)
    require (memoryByteLength > 0) (.emptyLoadMemoryRange index)
    require
      (memoryByteLength ≤ addressSpaceSize - virtualAddress)
      (.loadAddressOverflow index)
    require (validAlignment alignment) (.invalidLoadAlignment index)
    if alignment > 1 then
      require
        (fileOffset % alignment == virtualAddress % alignment)
        (.invalidLoadAlignment index)
    else
      pure ()
  else
    pure ()
  return {
    index
    segmentType
    rawFlags
    fileOffset
    virtualAddress
    physicalAddress
    fileByteLength
    memoryByteLength
    alignment
    fileBytes
  }

private def parseProgramHeaders
    (bytes : ByteArray) (tableOffset : Nat) :
    List Nat → Except DecodeError (List ProgramHeader)
  | [] => .ok []
  | index :: rest => do
      let header ← parseProgramHeader bytes tableOffset index
      let headers ← parseProgramHeaders bytes tableOffset rest
      return header :: headers

private def expectedRelocationEntrySize? (sectionType : Nat) : Option Nat :=
  if sectionType == shtRela then some 24
  else if sectionType == shtRel then some 16
  else if sectionType == shtRelr then some 8
  else none

private def parseSectionHeader
    (bytes : ByteArray) (tableOffset index : Nat) :
    Except DecodeError SectionHeader := do
  let base := tableOffset + index * elf64SectionHeaderSize
  let truncated := DecodeError.truncatedSectionHeader index
  let nameOffset ← read bytes base 4 truncated
  let sectionType ← read bytes (base + 4) 4 truncated
  let rawFlags ← read bytes (base + 8) 8 truncated
  let virtualAddress ← read bytes (base + 16) 8 truncated
  let fileOffset ← read bytes (base + 24) 8 truncated
  let byteLength ← read bytes (base + 32) 8 truncated
  let link ← read bytes (base + 40) 4 truncated
  let info ← read bytes (base + 44) 4 truncated
  let alignment ← read bytes (base + 48) 8 truncated
  let entrySize ← read bytes (base + 56) 8 truncated
  require
    (validAlignment alignment)
    (.invalidSectionAlignment index)
  let fileBytes ←
    if sectionType == shtNoBits then
      require
        (fileOffset ≤ bytes.size)
        (.invalidSectionFileRange index)
      pure none
    else
      match checkedSlice? bytes fileOffset byteLength with
      | some payload => pure (some payload)
      | none => .error (.invalidSectionFileRange index)
  match expectedRelocationEntrySize? sectionType with
  | none => pure ()
  | some expected =>
      require
        (entrySize == expected && byteLength % expected == 0)
        (.invalidRelocationEntrySize index)
  return {
    index
    nameOffset
    sectionType
    rawFlags
    virtualAddress
    fileOffset
    byteLength
    link
    info
    alignment
    entrySize
    fileBytes
  }

private def parseSectionHeaders
    (bytes : ByteArray) (tableOffset : Nat) :
    List Nat → Except DecodeError (List SectionHeader)
  | [] => .ok []
  | index :: rest => do
      let header ← parseSectionHeader bytes tableOffset index
      let headers ← parseSectionHeaders bytes tableOffset rest
      return header :: headers

private def sectionAt?
    (sections : List SectionHeader) (index : Nat) :
    Option SectionHeader :=
  (sections.drop index).head?

private def decodeSymbolName
    (stringBytes : ByteArray)
    (tableSectionIndex symbolIndex nameOffset : Nat) :
    Except DecodeError (ByteArray × String) := do
  require
    (nameOffset < stringBytes.size)
    (.invalidSymbolNameOffset tableSectionIndex symbolIndex)
  let terminator ←
    match stringBytes.findIdx? (fun byte => byte == 0) nameOffset with
    | some index => pure index
    | none =>
        throw
          (.unterminatedSymbolName tableSectionIndex symbolIndex)
  let nameBytes := stringBytes.extract nameOffset terminator
  let name ←
    match String.fromUTF8? nameBytes with
    | some value => pure value
    | none =>
        throw
          (.invalidSymbolNameUTF8 tableSectionIndex symbolIndex)
  return (nameBytes, name)

private def parseSymbol
    (sections : List SectionHeader)
    (table : SectionHeader)
    (tableBytes stringBytes : ByteArray)
    (index : Nat) : Except DecodeError Symbol := do
  let truncated := DecodeError.truncatedSymbol table.index index
  let base := index * 24
  let nameOffset ← read tableBytes base 4 truncated
  let info ← read tableBytes (base + 4) 1 truncated
  let visibility ← read tableBytes (base + 5) 1 truncated
  let sectionIndex ← read tableBytes (base + 6) 2 truncated
  let value ← read tableBytes (base + 8) 8 truncated
  let byteLength ← read tableBytes (base + 16) 8 truncated
  let binding := info / 16
  let symbolType := info % 16
  require
    (visibility < 4)
    (.invalidSymbolVisibility table.index index)
  require
    ((index < table.info && binding == 0) ||
      (index ≥ table.info && binding != 0))
    (.invalidSymbolBinding table.index index)
  let (nameBytes, name) ←
    decodeSymbolName stringBytes table.index index nameOffset
  let symbol : Symbol := {
    tableSectionIndex := table.index
    symbolIndex := index
    nameOffset
    nameBytes
    name
    binding
    symbolType
    visibility
    sectionIndex
    value
    byteLength
  }
  if symbol.hasSelectedName then
    require
      (binding == 1)
      (.invalidSelectedSymbolBinding table.index index)
    require
      (symbolType == 2)
      (.invalidSelectedSymbolType table.index index)
    require
      (sectionIndex > 0)
      (.undefinedSelectedSymbol table.index index)
    require
      (byteLength > 0)
      (.zeroSizedSelectedSymbol table.index index)
    let selectedSection ←
      match sectionAt? sections sectionIndex with
      | some linkedSection => pure linkedSection
      | none =>
          throw
            (.invalidSymbolSectionIndex table.index index)
    require
      (selectedSection.rawFlags.testBit 2 &&
        selectedSection.virtualAddress ≤ value &&
        selectedSection.byteLength ≤
          addressSpaceSize - selectedSection.virtualAddress &&
        byteLength ≤ addressSpaceSize - value &&
        byteLength ≤
          selectedSection.virtualAddress +
              selectedSection.byteLength - value)
      (.selectedSymbolOutsideExecutableSection table.index index)
  else
    pure ()
  return symbol

private def parseSymbols
    (sections : List SectionHeader)
    (table : SectionHeader)
    (tableBytes stringBytes : ByteArray) :
    List Nat → Except DecodeError (List Symbol)
  | [] => .ok []
  | index :: rest => do
      let symbol ←
        parseSymbol sections table tableBytes stringBytes index
      let symbols ←
        parseSymbols sections table tableBytes stringBytes rest
      return symbol :: symbols

private def parseStaticSymbolTable
    (sections : List SectionHeader) (table : SectionHeader) :
    Except DecodeError (List Symbol) := do
  let tableBytes ←
    match table.fileBytes with
    | some bytes => pure bytes
    | none => throw (.invalidSymbolTableEntrySize table.index)
  require
    (table.entrySize == 24 &&
      table.byteLength ≥ 24 &&
      table.byteLength % 24 == 0 &&
      tableBytes.size == table.byteLength)
    (.invalidSymbolTableEntrySize table.index)
  let symbolCount := table.byteLength / 24
  require
    (table.info > 0 && table.info ≤ symbolCount)
    (.invalidSymbolBinding table.index 0)
  let stringTable ←
    match sectionAt? sections table.link with
    | some linkedSection => pure linkedSection
    | none => throw (.invalidSymbolTableLink table.index)
  require
    (stringTable.isStringTable &&
      stringTable.entrySize == 0)
    (.invalidSymbolTableLink table.index)
  let stringBytes ←
    match stringTable.fileBytes with
    | some bytes => pure bytes
    | none => throw (.invalidStringTable stringTable.index)
  require
    (stringBytes.size == stringTable.byteLength &&
      stringBytes.size > 0 &&
      stringBytes.get! 0 == 0 &&
      stringBytes.get! (stringBytes.size - 1) == 0)
    (.invalidStringTable stringTable.index)
  let symbols ←
    parseSymbols sections table tableBytes stringBytes
      (List.range symbolCount)
  match symbols with
  | [] => throw (.invalidNullSymbol table.index)
  | first :: _ =>
      require first.isNullSentinel (.invalidNullSymbol table.index)
  return symbols

private def parseStaticSymbolTables
    (sections : List SectionHeader) :
    List SectionHeader → Except DecodeError (List Symbol)
  | [] => .ok []
  | table :: rest => do
      let current ←
        if table.isStaticSymbolTable then
          parseStaticSymbolTable sections table
        else
          pure []
      let remaining ← parseStaticSymbolTables sections rest
      return current ++ remaining

private instance instDecidableRangeWellFormed
    (segment : LoadSegment) : Decidable segment.RangeWellFormed := by
  unfold LoadSegment.RangeWellFormed
  infer_instance

private instance instDecidablePermissionSafe
    (segment : LoadSegment) : Decidable segment.PermissionSafe := by
  unfold LoadSegment.PermissionSafe
  infer_instance

private instance instDecidableMemoryDisjoint
    (left right : LoadSegment) :
    Decidable (LoadSegment.MemoryDisjoint left right) := by
  unfold LoadSegment.MemoryDisjoint
  infer_instance

private def loadSegmentSafeCheck (segment : LoadSegment) : Bool :=
  decide (segment.RangeWellFormed ∧ segment.PermissionSafe)

private theorem loadSegmentSafeCheck_sound
    {segment : LoadSegment}
    (h : loadSegmentSafeCheck segment = true) :
    segment.RangeWellFormed ∧ segment.PermissionSafe := by
  exact of_decide_eq_true h

private structure LoadPolicyCertificate
    (segments : List LoadSegment) : Type where
  nonempty : segments ≠ []
  safe :
    ∀ segment ∈ segments,
      segment.RangeWellFormed ∧ segment.PermissionSafe
  disjoint : segments.Pairwise LoadSegment.MemoryDisjoint

private def certifyLoadPolicy
    (segments : List LoadSegment) :
    Except DecodeError (LoadPolicyCertificate segments) :=
  if hempty : segments = [] then
    .error .noLoadSegments
  else if hsafe : segments.all loadSegmentSafeCheck = true then
    if hdisjoint :
        segments.Pairwise LoadSegment.MemoryDisjoint then
      .ok {
        nonempty := hempty
        safe := by
          intro segment hmember
          exact loadSegmentSafeCheck_sound
            ((List.all_eq_true.mp hsafe) segment hmember)
        disjoint := hdisjoint
      }
    else
      .error .overlappingLoadSegments
  else
    .error .loadPolicyInvariantFailure

private instance instDecidableContainsVirtualAddress
    (segment : LoadSegment) (address : UInt64) :
    Decidable (segment.ContainsVirtualAddress address) := by
  unfold LoadSegment.ContainsVirtualAddress
  infer_instance

private def entryLoadCheck
    (address : UInt64) (segment : LoadSegment) : Bool :=
  segment.executable &&
    decide (segment.ContainsVirtualAddress address)

private theorem entryLoadCheck_sound
    {address : UInt64} {segment : LoadSegment}
    (h : entryLoadCheck address segment = true) :
    segment.executable = true ∧
      segment.ContainsVirtualAddress address := by
  simp only [entryLoadCheck, Bool.and_eq_true] at h
  exact ⟨h.1, of_decide_eq_true h.2⟩

private structure EntryLoadCertificate
    (segments : List LoadSegment) (address : UInt64) : Type where
  executableLoad :
    ∃ segment ∈ segments,
      segment.executable = true ∧
        segment.ContainsVirtualAddress address

private def certifyEntryLoad
    (segments : List LoadSegment) (address : UInt64) :
    Except DecodeError (EntryLoadCertificate segments address) :=
  if hcontains : segments.any (entryLoadCheck address) = true then
    .ok {
      executableLoad := by
        rcases List.any_eq_true.mp hcontains with
          ⟨segment, hmember, hcheck⟩
        exact
          ⟨segment, hmember, entryLoadCheck_sound hcheck⟩
    }
  else
    .error .entryNotInExecutableLoad

/-- Parse one complete image using the deliberately narrow static-x86 policy.

The result is structural evidence only and never authorizes the binary.  It
does, when exact static symbol/string tables permit, resolve the single
selected pure-entry symbol. -/
def decode (bytes : ByteArray) : Except DecodeError DecodedELF64 := do
  require (bytes.size ≥ elf64HeaderSize) .truncatedHeader
  exactBytes bytes 0 [0x7f, 0x45, 0x4c, 0x46] .badMagic
  let elfClass ← read bytes 4 1 .truncatedHeader
  require (elfClass == elfClass64) .wrongClass
  let byteOrder ← read bytes 5 1 .truncatedHeader
  require (byteOrder == elfDataLittleEndian) .wrongEndianness
  let identificationVersion ← read bytes 6 1 .truncatedHeader
  require
    (identificationVersion == elfCurrentVersion)
    .badIdentificationVersion
  let osABI ← read bytes 7 1 .truncatedHeader
  require (osABI == 0) .wrongOSABI
  let abiVersion ← read bytes 8 1 .truncatedHeader
  require (abiVersion == 0) .badABIVersion
  exactBytes bytes 9 [0, 0, 0, 0, 0, 0, 0] .badIdentificationPadding

  let objectType ← read bytes 16 2 .truncatedHeader
  require (objectType == etExecutable) .notExecutable
  let machine ← read bytes 18 2 .truncatedHeader
  require (machine == emX86_64) .wrongMachine
  let version ← read bytes 20 4 .truncatedHeader
  require (version == elfCurrentVersion) .badELFVersion
  let entryAddress ← read bytes 24 8 .truncatedHeader
  let programHeaderOffset ← read bytes 32 8 .truncatedHeader
  let sectionHeaderOffset ← read bytes 40 8 .truncatedHeader
  let processorFlags ← read bytes 48 4 .truncatedHeader
  require (processorFlags == 0) .unsupportedProcessorFlags
  let headerSize ← read bytes 52 2 .truncatedHeader
  require (headerSize == elf64HeaderSize) .badELFHeaderSize
  let programHeaderSize ← read bytes 54 2 .truncatedHeader
  let programHeaderCount ← read bytes 56 2 .truncatedHeader
  let sectionHeaderSize ← read bytes 58 2 .truncatedHeader
  let sectionHeaderCount ← read bytes 60 2 .truncatedHeader
  let sectionNameIndex ← read bytes 62 2 .truncatedHeader

  require (programHeaderCount > 0) .missingProgramHeaders
  require
    (programHeaderCount != pnExtended)
    .unsupportedExtendedProgramHeaderCount
  require
    (programHeaderSize == elf64ProgramHeaderSize)
    .badProgramHeaderSize
  require
    (programHeaderOffset ≥ elf64HeaderSize)
    .badProgramHeaderTable
  match
      checkedSlice? bytes programHeaderOffset
        (programHeaderCount * elf64ProgramHeaderSize) with
  | none => throw .badProgramHeaderTable
  | some _ => pure ()

  if sectionHeaderCount == 0 then
    require
      (sectionHeaderOffset == 0 &&
        (sectionHeaderSize == 0 ||
          sectionHeaderSize == elf64SectionHeaderSize) &&
        sectionNameIndex == 0)
      .badSectionHeaderLayout
  else
    require
      (sectionHeaderCount != shnExtended)
      .unsupportedExtendedSectionHeaderCount
    require
      (sectionNameIndex != shnExtended)
      .unsupportedExtendedSectionNameIndex
    require
      (sectionNameIndex == 0 || sectionNameIndex < sectionHeaderCount)
      .badSectionHeaderLayout
    require
      (sectionHeaderSize == elf64SectionHeaderSize &&
        sectionHeaderOffset ≥ elf64HeaderSize)
      .badSectionHeaderLayout
    match
        checkedSlice? bytes sectionHeaderOffset
          (sectionHeaderCount * elf64SectionHeaderSize) with
    | none => throw .badSectionHeaderTable
    | some _ => pure ()

  let programHeaders ←
    parseProgramHeaders bytes programHeaderOffset
      (List.range programHeaderCount)
  let loadSegments :=
    programHeaders.filterMap ProgramHeader.toLoadSegment?
  let loadPolicy ← certifyLoadPolicy loadSegments
  let entryAddressWord := UInt64.ofNat entryAddress
  let entryLoad ←
    certifyEntryLoad loadSegments entryAddressWord
  let sectionHeaders ←
    if sectionHeaderCount == 0 then
      pure []
    else
      parseSectionHeaders bytes sectionHeaderOffset
        (List.range sectionHeaderCount)
  if sectionHeaderCount > 0 then
    match sectionHeaders with
    | [] => throw .badSectionHeaderLayout
    | first :: _ =>
        require first.isNullSentinel .badSectionHeaderLayout
  else
    pure ()
  let hasInterpreter :=
    programHeaders.any ProgramHeader.isInterpreter
  let hasDynamic :=
    programHeaders.any ProgramHeader.isDynamic
  let hasRelocations :=
    sectionHeaders.any SectionHeader.isRelocationEvidence
  let hasStaticSymbolTable :=
    sectionHeaders.any SectionHeader.isStaticSymbolTable
  let staticSymbols ←
    parseStaticSymbolTables sectionHeaders sectionHeaders
  let selectedSymbols :=
    staticSymbols.filter Symbol.hasSelectedName
  let selectedEntry ←
    (match selectedSymbols with
      | [] => pure none
      | [symbol] =>
          if hvalue : symbol.value = entryAddress then
            pure
              (some {
                symbol
                value_eq := hvalue
              })
          else
            throw
              (.selectedSymbolEntryMismatch
                symbol.tableSectionIndex symbol.symbolIndex)
      | _ => throw .duplicateSelectedSymbolDefinitions :
        Except DecodeError
          (Option (SelectedSymbolAtEntry entryAddress)))
  let entrySymbolStatus :=
    match selectedEntry with
    | some selected =>
        EntrySymbolStatus.resolvedSelected
          (UInt64.ofNat selected.symbol.value)
    | none =>
        if hasStaticSymbolTable then
          EntrySymbolStatus.unresolvedSelectedNotFound
        else
          EntrySymbolStatus.unresolvedNoSymbolTable
  let imageSymbols :=
    match selectedEntry with
    | some selected =>
        [(selectedEntrySymbol,
          UInt64.ofNat selected.symbol.value)]
    | none => []
  let relocationEvidence :=
    if sectionHeaderCount == 0 then
      RelocationEvidence.sectionTableAbsent
    else if hasRelocations then
      RelocationEvidence.relocationSectionPresent
    else
      RelocationEvidence.noneFound
  let image : ELF64Image := {
    endianness := .little
    objectType := .executable
    machineIsX86_64 := true
    entryAddress := entryAddressWord
    segments := loadSegments
    symbols := imageSymbols
    hasProgramInterpreter := hasInterpreter
    hasDynamicSection := hasDynamic
    hasUnappliedRelocations := hasRelocations
  }
  return {
    image
    programHeaders
    sectionHeaders
    staticSymbols
    entrySymbolStatus
    relocationEvidence
    littleEndian := rfl
    executable := rfl
    x86_64 := rfl
    uniqueSymbolNames := by
      cases hselected : selectedEntry with
      | none =>
          simp [ELF64Image.UniqueSymbolNames,
            ELF64Image.SymbolAt, image, imageSymbols, hselected]
      | some selected =>
          intro name left right hleft hright
          simp [ELF64Image.SymbolAt, image,
            imageSymbols, hselected] at hleft hright
          exact hleft.2.trans hright.2.symm
    selectedSymbolsOnly := by
      intro name address hsymbol
      cases hselected : selectedEntry with
      | none =>
          simp [ELF64Image.SymbolAt, image,
            imageSymbols, hselected] at hsymbol
      | some selected =>
          have hpair :
              name = selectedEntrySymbol ∧
                address =
                  UInt64.ofNat selected.symbol.value := by
            simpa [ELF64Image.SymbolAt, image,
              imageSymbols, hselected] using hsymbol
          exact hpair.1
    resolvedSelectedSymbol := by
      intro address hstatus
      cases hselected : selectedEntry with
      | none =>
          cases hstatic : hasStaticSymbolTable <;>
            simp [entrySymbolStatus, hselected, hstatic] at hstatus
      | some selected =>
          simp [entrySymbolStatus, hselected] at hstatus
          subst address
          simp [ELF64Image.SymbolAt, image,
            imageSymbols, hselected]
    resolvedSelectedAtEntry := by
      intro address hstatus
      cases hselected : selectedEntry with
      | none =>
          cases hstatic : hasStaticSymbolTable <;>
            simp [entrySymbolStatus, hselected, hstatic] at hstatus
      | some selected =>
          simp [entrySymbolStatus, hselected] at hstatus
          subst address
          simp [image, entryAddressWord, selected.value_eq]
    nonemptyLoadSegments := loadPolicy.nonempty
    safeLoadSegments := loadPolicy.safe
    disjointLoadSegments := loadPolicy.disjoint
    entryInExecutableLoad := entryLoad.executableLoad
    loadSegmentsExact := rfl
    interpreterFlagExact := rfl
    dynamicFlagExact := rfl
    relocationFlagExact := rfl
  }

/-- Structural image decoding.  A stripped image may succeed here with an
empty symbol list; use `decodeSelectedImage` for the fail-closed named-entry
interface expected by the pure-entry loader. -/
def decodeImage (bytes : ByteArray) : Option ELF64Image :=
  match decode bytes with
  | .ok decoded => some decoded.image
  | .error _ => none

/-- Every returned image has the exact restricted ELF header policy. -/
theorem decodeImage_headerPolicy
    {bytes : ByteArray} {image : ELF64Image}
    (h : decodeImage bytes = some image) :
    image.endianness = .little ∧
      image.objectType = .executable ∧
        image.machineIsX86_64 = true := by
  cases hdecode : decode bytes with
  | error error =>
      simp [decodeImage, hdecode] at h
  | ok decoded =>
      have himage : decoded.image = image := by
        simpa [decodeImage, hdecode] using h
      subst image
      exact
        ⟨decoded.littleEndian, decoded.executable,
          decoded.x86_64⟩

/-- Every successful image has at least one load segment, and its complete
decoded load list already satisfies the range, W^X, and pairwise-disjoint
parts of the static-image policy. -/
theorem decodeImage_loadPolicy
    {bytes : ByteArray} {image : ELF64Image}
    (h : decodeImage bytes = some image) :
    image.segments ≠ [] ∧
      image.SafeLoadSegments ∧
      image.DisjointLoadSegments := by
  cases hdecode : decode bytes with
  | error error =>
      simp [decodeImage, hdecode] at h
  | ok decoded =>
      have himage : decoded.image = image := by
        simpa [decodeImage, hdecode] using h
      subst image
      exact
        ⟨decoded.nonemptyLoadSegments,
          decoded.safeLoadSegments,
          decoded.disjointLoadSegments⟩

namespace DecodedELF64

/-- Exact selected-symbol resolution plus equality with `e_entry` constructs
the existing named-entry policy proposition. -/
theorem entryAdmissible_of_resolvedSelectedAndEntry
    (decoded : DecodedELF64)
    {address : UInt64}
    (hresolved :
      decoded.entrySymbolStatus = .resolvedSelected address)
    (hentry : address = decoded.image.entryAddress) :
    decoded.image.EntryAdmissible
      selectedEntrySymbol decoded.image.entryAddress := by
  refine ⟨?_, rfl, decoded.entryInExecutableLoad⟩
  have hsymbol := decoded.resolvedSelectedSymbol hresolved
  simpa [hentry] using hsymbol

/-- The strict decoder records the selected value-to-`e_entry` check, so a
resolved status is already sufficient for named-entry admissibility. -/
theorem resolvedSelected_entryAdmissible
    (decoded : DecodedELF64)
    {address : UInt64}
    (hresolved :
      decoded.entrySymbolStatus = .resolvedSelected address) :
    decoded.image.EntryAdmissible
      selectedEntrySymbol decoded.image.entryAddress :=
  decoded.entryAdmissible_of_resolvedSelectedAndEntry
    hresolved (decoded.resolvedSelectedAtEntry hresolved)

end DecodedELF64

/-- Fail-closed decoder for the exact selected pure entry.  Stripped images,
images lacking the selected definition, and selected-value/`e_entry`
mismatches all return `none`. -/
def decodeSelectedImage (bytes : ByteArray) : Option ELF64Image :=
  match decode bytes with
  | .error _ => none
  | .ok decoded =>
      match decoded.entrySymbolStatus with
      | .resolvedSelected _ => some decoded.image
      | .unresolvedNoSymbolTable => none
      | .unresolvedSelectedNotFound => none

/-- Every image returned by the selected-entry decoder satisfies the exact
named-entry policy at its ELF header entry address. -/
theorem decodeSelectedImage_entryAdmissible
    {bytes : ByteArray} {image : ELF64Image}
    (hdecode : decodeSelectedImage bytes = some image) :
    image.EntryAdmissible selectedEntrySymbol image.entryAddress := by
  unfold decodeSelectedImage at hdecode
  cases hdetailed : decode bytes with
  | error error =>
      simp [hdetailed] at hdecode
  | ok decoded =>
      cases hstatus : decoded.entrySymbolStatus with
      | unresolvedNoSymbolTable =>
          simp [hdetailed, hstatus] at hdecode
      | unresolvedSelectedNotFound =>
          simp [hdetailed, hstatus] at hdecode
      | resolvedSelected address =>
          have himage : decoded.image = image := by
            simpa [hdetailed, hstatus] using hdecode
          subst image
          exact
            decoded.resolvedSelected_entryAdmissible hstatus

end ELF64Decoder

end SparkInterval.Execution.Architecture.X86ELF
