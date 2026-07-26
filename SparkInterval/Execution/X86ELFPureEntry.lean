/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.ArchitectureExecution

/-!
# Static x86-64 ELF pure-entry proof boundary

This module refines the generic architecture boundary into the smallest
honest CPU proof chain proposed for the Sqrt218 fixed-width checker.  It does
not define a toy x86 semantics and it does not identify an application
checker with an instruction step.

The intended authority-bearing artifact is a dedicated static, non-PIE
x86-64 ELF whose selected entry is the flat pure function
`tg_sq218_verify_snapshot_v2`.  An attested launcher supplies disjoint input,
120-byte result, and status buffers.  The modeled entry performs no file I/O,
allocation, or system call.  The current POSIX command-line executable is
therefore *not* an instance of this model: proving that executable requires a
Linux process, libc, allocation, filesystem, and system-call semantics.

The layers kept separate below are:

1. exact ELF64 decoding, static-image policy, symbol selection, SysV-ABI
   initialization, x86-64 instruction stepping, and return observation;
2. the theorem that the exact loaded machine image has the behavior assigned
   to the linked instruction image;
3. assembler/linker validation from that linked-image behavior back to
   CompCert's abstract x86-64 `Asm` behavior;
4. CompCert semantic preservation from target `Asm` behavior back to Clight;
5. the VST/cross-prover theorem connecting Clight behavior to the neutral
   Lean checker relation.

Only their ordinary-Lean composition is proved here.  No inhabitant of any
of the five production obligations is constructed.

Physical CPU conformance is deliberately outside
`ArchitectureRefinesNativeChecker`.  It belongs only to the admission step
that turns reviewed Azure evidence for one exact run into an
`ArchitectureExecution` in one closed model.  Such an admission rule must be
closed over a concrete decoder and x86 semantics; quantifying it over a
caller-selected `PureEntryModel` would be unsound.

This file introduces no axiom and performs no executable or certificate
replay.
-/

set_option autoImplicit false

universe u

namespace SparkInterval.Execution.Architecture.X86ELF

/-- ELF byte order.  The production policy accepts only little endian. -/
inductive Endianness where
  | little
  | big
  deriving DecidableEq, Repr

/-- The relevant ELF object type.  The pure-entry route accepts only a fixed
`ET_EXEC` image, not a relocatable object, shared object, or PIE. -/
inductive ObjectType where
  | relocatable
  | executable
  | shared
  | other
  deriving DecidableEq, Repr

/-- One decoded loadable ELF segment, retaining its exact file bytes. -/
structure LoadSegment where
  fileOffset : Nat
  virtualAddress : UInt64
  fileBytes : ByteArray
  memoryByteLength : Nat
  readable : Bool
  writable : Bool
  executable : Bool

namespace LoadSegment

/-- First virtual address strictly after the segment, represented in `Nat` so
that overflow cannot be hidden by machine-word wraparound. -/
def virtualEnd (segment : LoadSegment) : Nat :=
  segment.virtualAddress.toNat + segment.memoryByteLength

/-- The bytes retained from the ELF file fit in the memory image, and the
virtual range does not cross the 64-bit address-space boundary. -/
def RangeWellFormed (segment : LoadSegment) : Prop :=
  segment.fileBytes.size ≤ segment.memoryByteLength ∧
    segment.virtualEnd ≤ 2 ^ 64

/-- A virtual address belongs to this half-open load range. -/
def ContainsVirtualAddress
    (segment : LoadSegment) (address : UInt64) : Prop :=
  segment.virtualAddress.toNat ≤ address.toNat ∧
    address.toNat < segment.virtualEnd

/-- Two half-open virtual load ranges are disjoint. -/
def MemoryDisjoint (left right : LoadSegment) : Prop :=
  left.virtualEnd ≤ right.virtualAddress.toNat ∨
    right.virtualEnd ≤ left.virtualAddress.toNat

/-- The pure checker image rejects writable executable memory. -/
def PermissionSafe (segment : LoadSegment) : Prop :=
  ¬ (segment.writable = true ∧ segment.executable = true)

end LoadSegment

/-- The information used by the pure-entry loader after exact ELF decoding.

`symbols` is retained because the architecture boundary names the selected
entry.  Production decoding must reject duplicate names used by the selected
entry and must derive all fields from the complete measured ELF bytes. -/
structure ELF64Image where
  endianness : Endianness
  objectType : ObjectType
  machineIsX86_64 : Bool
  entryAddress : UInt64
  segments : List LoadSegment
  symbols : List (String × UInt64)
  hasProgramInterpreter : Bool
  hasDynamicSection : Bool
  hasUnappliedRelocations : Bool

namespace ELF64Image

/-- A symbol/address pair occurs in the decoded symbol table. -/
def SymbolAt (image : ELF64Image) (name : String) (address : UInt64) : Prop :=
  (name, address) ∈ image.symbols

/-- Every symbol name resolves to at most one address. -/
def UniqueSymbolNames (image : ELF64Image) : Prop :=
  ∀ {name : String} {left right : UInt64},
    image.SymbolAt name left →
    image.SymbolAt name right →
    left = right

/-- All retained load segments obey the per-segment range and permission
policy. -/
def SafeLoadSegments (image : ELF64Image) : Prop :=
  ∀ segment ∈ image.segments,
    segment.RangeWellFormed ∧ segment.PermissionSafe

/-- The half-open virtual ranges of distinct load segments do not overlap. -/
def DisjointLoadSegments (image : ELF64Image) : Prop :=
  image.segments.Pairwise LoadSegment.MemoryDisjoint

/-- A selected symbol is exactly the ELF entry point and lies in an
executable load segment. -/
def EntryAdmissible
    (image : ELF64Image) (name : String) (address : UInt64) : Prop :=
  image.SymbolAt name address ∧
    address = image.entryAddress ∧
    ∃ segment ∈ image.segments,
      segment.executable = true ∧
        segment.ContainsVirtualAddress address

/-- Fail-closed image policy for the recommended pure-entry route.

Exact ELF header/program-header parsing and the proof that each retained
`fileBytes` slice is the corresponding slice of the complete measured image
are obligations of the selected concrete decoder.  The separate
`X86ELFDecoder` module now implements that bounded byte layer and exact
selected `SHT_SYMTAB`/`SHT_STRTAB` resolution.  Range, overlap, and permission
discipline are explicit below rather than being left in prose. -/
structure StaticPureEntryAdmissible (image : ELF64Image) : Prop where
  littleEndian : image.endianness = .little
  executable : image.objectType = .executable
  x86_64 : image.machineIsX86_64 = true
  noInterpreter : image.hasProgramInterpreter = false
  noDynamicSection : image.hasDynamicSection = false
  noUnappliedRelocations : image.hasUnappliedRelocations = false
  uniqueSymbolNames : image.UniqueSymbolNames
  nonemptyLoadSegments : image.segments ≠ []
  safeLoadSegments : image.SafeLoadSegments
  disjointLoadSegments : image.DisjointLoadSegments

end ELF64Image

/-- Components of a formal static-ELF/x86-64 pure-entry semantics.

The structure is an interface for implementing the model, not a trusted
choice.  In a production instance:

* `decode` must be a closed exact ELF64 decoder;
* `initializeEntry` must map every loadable segment, establish the SysV AMD64
  entry ABI, place the exact immutable input and disjoint output/status
  buffers in memory, and install a return sentinel;
* `step` must be the formal semantics of every reachable x86-64 instruction,
  not a call to the Sqrt218 checker specification; and
* `returnedWith` must observe normal return to that sentinel and the complete
  result bytes at the ABI output buffer.

The measured launcher-to-initial-state and final-state-to-retained-output
claims are physical admission obligations; they are not consequences of this
interface. -/
structure PureEntryModel where
  semanticsId : Digest
  semanticsIdPresent : semanticsId ≠ ""
  decode : ByteArray → Option ELF64Image
  State : Type u
  initializeEntry :
    ELF64Image → UInt64 → ByteArray → State → Prop
  step : State → State → Prop
  returnedWith : State → ByteArray → Prop

namespace PureEntryModel

/-- Exact static-image load and ABI initialization for a named pure entry. -/
def load (model : PureEntryModel)
    (entryPoint : String)
    (executableBytes inputBytes : ByteArray)
    (state : model.State) : Prop :=
  ∃ image : ELF64Image, ∃ entryAddress : UInt64,
    model.decode executableBytes = some image ∧
      image.StaticPureEntryAdmissible ∧
      image.EntryAdmissible entryPoint entryAddress ∧
      model.initializeEntry image entryAddress inputBytes state

/-- The generic architecture semantics induced by a static x86-64 pure-entry
model.  The Azure CPU target is fixed here; a caller cannot retarget this
construction to a GPU or local-development profile. -/
def toArchitectureSemantics
    (model : PureEntryModel) : ArchitectureSemantics where
  semanticsId := model.semanticsId
  target := .azureSEVSNPCPU
  State := model.State
  load := model.load
  step := model.step
  haltedWith := model.returnedWith

end PureEntryModel

/-- An input/output behavior relation at one proof layer. -/
abbrev IOBehavior := ByteArray → ByteArray → Prop

/-- Semantic refinement in the safety direction needed here: every behavior
of the lower-level implementation is permitted by the higher-level model. -/
def BehaviorRefines (lower higher : IOBehavior) : Prop :=
  ∀ {inputBytes outputBytes : ByteArray},
    lower inputBytes outputBytes →
      higher inputBytes outputBytes

namespace BehaviorRefines

/-- Behavior refinement is transitive. -/
theorem trans
    {first second third : IOBehavior}
    (firstToSecond : BehaviorRefines first second)
    (secondToThird : BehaviorRefines second third) :
    BehaviorRefines first third := by
  intro inputBytes outputBytes firstBehavior
  exact secondToThird (firstToSecond firstBehavior)

end BehaviorRefines

/-- Exact ELF load plus x86-64 ISA execution refines the behavior assigned to
the linked instruction image.

This is the first genuinely machine-level production theorem.  Its proof must
unpack exact ELF decoding and loading, then symbolically reason about the
reachable instruction trace and SysV ABI.  It must not be proved by defining
`linkedBehavior` to mean that the application checker accepts. -/
structure ELFISARefinesLinkedBehavior
    (scheme : MeasurementScheme)
    (model : PureEntryModel)
    (executable : MeasuredBlob)
    (entryPoint : String)
    (linkedBehavior : IOBehavior) : Prop where
  executableExact : executable.Exact scheme
  refines :
    ∀ {inputBytes outputBytes : ByteArray}
      {initialState finalState : model.State},
      model.load entryPoint executable.bytes inputBytes initialState →
      Trace model.step initialState finalState →
      model.returnedWith finalState outputBytes →
      linkedBehavior inputBytes outputBytes

/-- The complete proof chain from a linked x86-64 instruction image back to
the architecture-neutral native checker.

Each field is intentionally one direction of one named boundary.  In
particular, a CompCert theorem does not discharge `assemblerLinker`, and an
attestation receipt discharges none of these fields. -/
structure PureEntryRefinementChain
    (scheme : MeasurementScheme)
    (model : PureEntryModel)
    (checker : NativeCheckerSemantics)
    (executable : MeasuredBlob)
    (entryPoint : String) where
  linkedImageBehavior : IOBehavior
  compCertAsmBehavior : IOBehavior
  clightBehavior : IOBehavior
  elfAndISA :
    ELFISARefinesLinkedBehavior
      scheme model executable entryPoint linkedImageBehavior
  assemblerLinker :
    BehaviorRefines linkedImageBehavior compCertAsmBehavior
  compCert :
    BehaviorRefines compCertAsmBehavior clightBehavior
  vstAndNeutralContract :
    BehaviorRefines clightBehavior checker.accepts

namespace PureEntryRefinementChain

/-- The layered pure-entry proof chain constructs the generic executable
refinement theorem required by the architecture boundary.

This theorem is data-independent: it reasons about an arbitrary input/output
pair and never evaluates a production certificate or architecture trace. -/
theorem architectureRefinement
    {scheme : MeasurementScheme}
    {model : PureEntryModel}
    {checker : NativeCheckerSemantics}
    {executable : MeasuredBlob}
    {entryPoint : String}
    (chain :
      PureEntryRefinementChain
        scheme model checker executable entryPoint) :
    ArchitectureRefinesNativeChecker
      scheme model.toArchitectureSemantics checker executable entryPoint := by
  refine {
    executableExact := chain.elfAndISA.executableExact
    refines := ?_
  }
  intro run executableBound entryPointBound execution
  rcases execution with
    ⟨_exactMeasurements, _semanticsBound, _targetBound,
      initialState, finalState, loaded, traced, halted⟩
  subst executableBound
  subst entryPointBound
  have linked :
      chain.linkedImageBehavior
        run.input.bytes run.output.bytes :=
    chain.elfAndISA.refines loaded traced halted
  exact chain.vstAndNeutralContract
    (chain.compCert (chain.assemblerLinker linked))

end PureEntryRefinementChain

end SparkInterval.Execution.Architecture.X86ELF
