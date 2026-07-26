/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFDecoder

/-!
# Tiny kernel-evaluated tests for the bounded ELF64 decoder

These fixtures are below 520 bytes.  They exercise format recognition,
exact `PT_LOAD` slicing, policy-evidence flags, and representative truncation,
overflow, permission, range, symbol-table, and string-table tampering. They
are parser KATs, not a production executable replay.
-/

set_option autoImplicit false
set_option maxRecDepth 10000

namespace SparkInterval.Tests.X86ELFDecoderTest

open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder

private def leBytes (width value : Nat) : List UInt8 :=
  (List.range width).map
    (fun index => UInt8.ofNat ((value / 256 ^ index) % 256))

private def identification : List UInt8 :=
  ([0x7f, 0x45, 0x4c, 0x46, 2, 1, 1, 0, 0,
    0, 0, 0, 0, 0, 0, 0] : List Nat).map UInt8.ofNat

private def header
    (entry programHeaderCount sectionHeaderOffset
      sectionHeaderCount sectionHeaderSize : Nat) : List UInt8 :=
  identification ++
    leBytes 2 2 ++
    leBytes 2 62 ++
    leBytes 4 1 ++
    leBytes 8 entry ++
    leBytes 8 64 ++
    leBytes 8 sectionHeaderOffset ++
    leBytes 4 0 ++
    leBytes 2 64 ++
    leBytes 2 56 ++
    leBytes 2 programHeaderCount ++
    leBytes 2 sectionHeaderSize ++
    leBytes 2 sectionHeaderCount ++
    leBytes 2 0

private def programHeader
    (segmentType flags fileOffset virtualAddress physicalAddress
      fileSize memorySize alignment : Nat) : List UInt8 :=
  leBytes 4 segmentType ++
    leBytes 4 flags ++
    leBytes 8 fileOffset ++
    leBytes 8 virtualAddress ++
    leBytes 8 physicalAddress ++
    leBytes 8 fileSize ++
    leBytes 8 memorySize ++
    leBytes 8 alignment

private def fullSectionHeader
    (sectionType rawFlags virtualAddress fileOffset byteLength
      link info alignment entrySize : Nat) :
    List UInt8 :=
  leBytes 4 0 ++
    leBytes 4 sectionType ++
    leBytes 8 rawFlags ++
    leBytes 8 virtualAddress ++
    leBytes 8 fileOffset ++
    leBytes 8 byteLength ++
    leBytes 4 link ++
    leBytes 4 info ++
    leBytes 8 alignment ++
    leBytes 8 entrySize

private def sectionHeader
    (sectionType fileOffset byteLength alignment entrySize : Nat) :
    List UInt8 :=
  fullSectionHeader sectionType 0 0 fileOffset byteLength
    0 0 alignment entrySize

private def nullSectionHeader : List UInt8 :=
  sectionHeader 0 0 0 0 0

private def minimalELFWithLoad
    (flags fileSize memorySize virtualAddress alignment : Nat) : ByteArray :=
  (header (virtualAddress + 64) 1 0 0 0 ++
    programHeader 1 flags 0 virtualAddress virtualAddress
      fileSize memorySize alignment).toByteArray

private def minimalELF : ByteArray :=
  minimalELFWithLoad 5 120 120 0x400000 0x1000

private def twoProgramHeaderELF (secondType : Nat) : ByteArray :=
  (header 0x400040 2 0 0 0 ++
    programHeader 1 5 0 0x400000 0x400000 176 176 0x1000 ++
    programHeader secondType 4 0 0 0 0 0 1).toByteArray

private def relocationSectionELF : ByteArray :=
  (header 0x400040 1 120 2 64 ++
    programHeader 1 5 0 0x400000 0x400000 248 248 0x1000 ++
    nullSectionHeader ++
    sectionHeader 4 248 0 8 24).toByteArray

private def elf64Symbol
    (nameOffset info visibility sectionIndex value byteLength : Nat) :
    List UInt8 :=
  leBytes 4 nameOffset ++
    leBytes 1 info ++
    leBytes 1 visibility ++
    leBytes 2 sectionIndex ++
    leBytes 8 value ++
    leBytes 8 byteLength

private def nullSymbol : List UInt8 :=
  elf64Symbol 0 0 0 0 0 0

/-- A realistic unrelated local `STT_FILE`/`SHN_ABS` row.  The selected
decoder must retain it without applying selected-function restrictions. -/
private def unrelatedFileSymbol : List UInt8 :=
  elf64Symbol 0 4 0 0xfff1 0 0

private def selectedFunctionSymbol
    (value : Nat) : List UInt8 :=
  elf64Symbol 1 0x12 0 1 value 16

private def selectedSymbolELF
    (duplicate : Bool) (selectedValue : Nat) : ByteArray :=
  let textOffset := 376
  let textSize := 16
  let symbolOffset := textOffset + textSize
  let symbolBytes :=
    nullSymbol ++ unrelatedFileSymbol ++
      selectedFunctionSymbol selectedValue ++
      (if duplicate then selectedFunctionSymbol selectedValue else [])
  let stringBytes :=
    [UInt8.ofNat 0] ++ selectedEntrySymbol.toUTF8.toList ++
      [UInt8.ofNat 0]
  let stringOffset := symbolOffset + symbolBytes.length
  let totalSize := stringOffset + stringBytes.length
  (header (0x400000 + textOffset) 1 120 4 64 ++
    programHeader 1 5 0 0x400000 0x400000
      totalSize totalSize 0x1000 ++
    nullSectionHeader ++
    fullSectionHeader 1 6 (0x400000 + textOffset)
      textOffset textSize 0 0 16 0 ++
    fullSectionHeader 2 0 0 symbolOffset symbolBytes.length
      3 2 8 24 ++
    fullSectionHeader 3 0 0 stringOffset stringBytes.length
      0 0 1 0 ++
    List.replicate textSize (UInt8.ofNat 0) ++
    symbolBytes ++ stringBytes).toByteArray

private def selectedSymbolImage : ByteArray :=
  selectedSymbolELF false (0x400000 + 376)

private def duplicateSelectedSymbolImage : ByteArray :=
  selectedSymbolELF true (0x400000 + 376)

#guard minimalELF.size == 120

#guard
  match decode minimalELF with
  | .ok decoded =>
      match decoded.image.segments with
      | [segment] =>
          decoded.image.entryAddress == UInt64.ofNat 0x400040 &&
            decoded.programHeaders.length == 1 &&
            segment.fileBytes == minimalELF &&
            segment.readable &&
            !segment.writable &&
            segment.executable &&
            !decoded.image.hasProgramInterpreter &&
            !decoded.image.hasDynamicSection &&
            !decoded.image.hasUnappliedRelocations &&
            decide
              (decoded.entrySymbolStatus =
                .unresolvedNoSymbolTable)
      | _ => false
  | .error _ => false

#guard
  match decode (minimalELF.set! 0 0) with
  | .error error => decide (error = .badMagic)
  | .ok _ => false

#guard
  match decode (minimalELF.extract 0 63) with
  | .error error => decide (error = .truncatedHeader)
  | .ok _ => false

#guard
  match decode (minimalELF.set! 4 1) with
  | .error error => decide (error = .wrongClass)
  | .ok _ => false

#guard
  match decode (minimalELF.set! 7 3) with
  | .error error => decide (error = .wrongOSABI)
  | .ok _ => false

#guard
  match decode (minimalELF.set! 8 1) with
  | .error error => decide (error = .badABIVersion)
  | .ok _ => false

/- `p_filesz = 121` crosses the 120-byte fixture boundary. -/
#guard
  match decode (minimalELF.set! 96 121) with
  | .error error =>
      decide (error = .invalidProgramFileRange 0)
  | .ok _ => false

/- Reducing `p_memsz` below the retained 120 file bytes is rejected. -/
#guard
  match decode (minimalELF.set! 104 119) with
  | .error error =>
      decide (error = .loadFileLargerThanMemory 0)
  | .ok _ => false

/- A writable+executable `PT_LOAD` never reaches the policy layer. -/
#guard
  match decode (minimalELF.set! 68 7) with
  | .error error =>
      decide (error = .invalidLoadPermissions 0)
  | .ok _ => false

/- Moving the load start to the last address makes its 120-byte memory range
cross the 64-bit address-space boundary. -/
private def overflowingLoadELF : ByteArray :=
  minimalELFWithLoad 5 120 120 (2 ^ 64 - 1) 1

#guard
  match decode overflowingLoadELF with
  | .error error =>
      decide (error = .loadAddressOverflow 0)
  | .ok _ => false

#guard
  match decode (twoProgramHeaderELF 3) with
  | .ok decoded =>
      decoded.image.hasProgramInterpreter &&
        !decoded.image.hasDynamicSection
  | .error _ => false

#guard
  match decode (twoProgramHeaderELF 2) with
  | .ok decoded =>
      !decoded.image.hasProgramInterpreter &&
        decoded.image.hasDynamicSection
  | .error _ => false

#guard relocationSectionELF.size == 248

#guard
  match decode relocationSectionELF with
  | .ok decoded =>
      decoded.image.hasUnappliedRelocations &&
        decide
          (decoded.relocationEvidence =
            .relocationSectionPresent) &&
        decoded.sectionHeaders.length == 2
  | .error _ => false

/- Tampering with the mandatory section-zero sentinel is fail-closed. -/
#guard
  match decode (relocationSectionELF.set! 124 1) with
  | .error error => decide (error = .badSectionHeaderLayout)
  | .ok _ => false

#guard selectedSymbolImage.size < 520

#guard
  match decode selectedSymbolImage with
  | .ok decoded =>
      decoded.staticSymbols.length == 3 &&
        decide
          (decoded.entrySymbolStatus =
            .resolvedSelected (UInt64.ofNat 0x400178)) &&
        decoded.image.symbols ==
          [(selectedEntrySymbol, UInt64.ofNat 0x400178)]
  | .error _ => false

#guard
  match decodeSelectedImage selectedSymbolImage with
  | some image =>
      image.symbols ==
        [(selectedEntrySymbol, UInt64.ofNat 0x400178)]
  | none => false

/- A stripped structural ELF remains decodable for inspection, but the
named-entry interface fails closed. -/
#guard
  match decodeSelectedImage minimalELF with
  | none => true
  | some _ => false

private def rejectedAs
    (bytes : ByteArray) (expected : DecodeError) : Bool :=
  match decode bytes with
  | .error actual => decide (actual = expected)
  | .ok _ => false

/- `sh_link` must select the exact `SHT_STRTAB`, not `.text`. -/
#guard
  rejectedAs (selectedSymbolImage.set! 288 1)
    (.invalidSymbolTableLink 2)

/- An ELF64 `SHT_SYMTAB` row is exactly 24 bytes. -/
#guard
  rejectedAs (selectedSymbolImage.set! 304 23)
    (.invalidSymbolTableEntrySize 2)

/- The selected row's `st_name` must lie inside its linked string table. -/
#guard
  rejectedAs (selectedSymbolImage.set! 440 0xff)
    (.invalidSymbolNameOffset 2 2)

/- The linked string table must retain its final NUL byte. -/
#guard
  rejectedAs
    (selectedSymbolImage.set!
      (selectedSymbolImage.size - 1) 1)
    (.invalidStringTable 3)

/- Every retained symbol name must be valid UTF-8. -/
#guard
  rejectedAs (selectedSymbolImage.set! 465 0xff)
    (.invalidSymbolNameUTF8 2 2)

/- Weak binding does not satisfy the exact selected `STB_GLOBAL` rule. -/
#guard
  rejectedAs (selectedSymbolImage.set! 444 0x22)
    (.invalidSelectedSymbolBinding 2 2)

/- `STT_OBJECT` does not satisfy the exact selected `STT_FUNC` rule. -/
#guard
  rejectedAs (selectedSymbolImage.set! 444 0x11)
    (.invalidSelectedSymbolType 2 2)

#guard
  rejectedAs (selectedSymbolImage.set! 446 0)
    (.undefinedSelectedSymbol 2 2)

#guard
  rejectedAs (selectedSymbolImage.set! 456 0)
    (.zeroSizedSelectedSymbol 2 2)

/- The selected definition's ordinary section must be executable. -/
#guard
  rejectedAs (selectedSymbolImage.set! 192 2)
    (.selectedSymbolOutsideExecutableSection 2 2)

#guard
  rejectedAs
    (selectedSymbolImage.set! 24 0x79)
    (.selectedSymbolEntryMismatch 2 2)

#guard
  rejectedAs duplicateSelectedSymbolImage
    .duplicateSelectedSymbolDefinitions

/- A well-formed table with a different name remains structurally visible,
but it cannot instantiate the selected-entry loader. -/
private def missingSelectedNameImage : ByteArray :=
  selectedSymbolImage.set! 465 (UInt8.ofNat 0x78)

#guard
  match decode missingSelectedNameImage with
  | .ok decoded =>
      decide
        (decoded.entrySymbolStatus =
          .unresolvedSelectedNotFound)
  | .error _ => false

#guard
  match decodeSelectedImage missingSelectedNameImage with
  | none => true
  | some _ => false

example :
    checkedSlice? minimalELF 64 56 =
      some (minimalELF.extract 64 120) := by
  rfl

example :
    readNatLE? minimalELF 24 8 = some 0x400040 := by
  rfl

end SparkInterval.Tests.X86ELFDecoderTest
