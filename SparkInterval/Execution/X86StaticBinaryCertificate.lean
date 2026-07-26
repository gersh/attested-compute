/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFExactPureEntry

/-!
# Compact static x86 binary-certificate boundary

This module factors the first, machine-level field of
`X86ELF.PureEntryRefinementChain` into:

1. a finite, executable checker for an exact selected-entry ELF, its decoded
   instructions, and its closed direct-control-flow graph;
2. a universal proof that x86 instruction traces decompose into certified
   block steps;
3. a proof for each certified block summary; and
4. a universal proof that summary traces have the linked-image behavior.

The static checker visits only the supplied ELF and certificate.  It never
opens a Sqrt218 input archive and never follows a runtime instruction trace.
The semantic fields quantify over arbitrary traces, so their proof terms may
be checked once and reused for every cloud input.

This is a proof boundary, not an x86 implementation.  `InstructionDecoder`
must eventually be instantiated by a closed, proved x86 decoder, and
`instructionTraceToBlocks` remains the substantive ISA proof.  The final
composition fixes `X86ELFDecoder.decodeSelectedImage` and the concrete
`X86PureEntryABI` initializer/observer through `exactDecoderModel`; only the
future x86 transition relation remains an explicit parameter.

No certificate accepted here authorizes a physical run.  Receipt appraisal,
launcher refinement, physical CPU conformance, CompCert preservation, and
assembler/linker validation remain separate obligations.
-/

set_option autoImplicit false

universe u

namespace SparkInterval.Execution.Architecture.X86StaticBinaryCertificate

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder
open SparkInterval.Execution.Architecture.X86ELFExactPureEntry
open SparkInterval.Execution.Architecture.X86PureEntryABI

/-- Statically visible control flow for the deliberately narrow first
validator.  Indirect jumps and returns are not guessed: returns have no
static target, while an output containing any other indirect transfer must be
rejected by the future concrete decoder or represented by an extended
certificate format. -/
inductive StaticControlFlow where
  | fallthrough
  | jump (target : Nat)
  | branch (taken fallthrough : Nat)
  | call (callee continuation : Nat)
  | returns
  deriving DecidableEq, Repr

namespace StaticControlFlow

/-- Direct addresses which must be block entries in the same certificate. -/
def directTargets : StaticControlFlow → List Nat
  | .fallthrough => []
  | .jump target => [target]
  | .branch taken notTaken => [taken, notTaken]
  | .call callee continuation => [callee, continuation]
  | .returns => []

/-- Only a non-control instruction may occur before the last row of a basic
block. -/
def terminatesBlock : StaticControlFlow → Bool
  | .fallthrough => false
  | _ => true

end StaticControlFlow

/-- Exact output expected from the future closed x86 instruction decoder.

`encoding` is retained rather than only a mnemonic.  Static validation below
also proves it is the exact slice of the ELF-loaded bytes at `address`.
`formId` is a human-auditable opcode/form identifier; its interpretation and
the correctness of `flow` remain obligations of the concrete decoder proof. -/
structure DecodedInstruction where
  address : Nat
  encoding : ByteArray
  formId : String
  flow : StaticControlFlow
  deriving DecidableEq

namespace DecodedInstruction

def endAddress (instruction : DecodedInstruction) : Nat :=
  instruction.address + instruction.encoding.size

/-- The instruction has at least one byte and cannot cross the x86-64 address
space boundary. -/
def RangeWellFormed (instruction : DecodedInstruction) : Prop :=
  0 < instruction.encoding.size ∧
    instruction.endAddress ≤ X86PureEntryABI.addressSpaceSize

end DecodedInstruction

/-- Identity and pure decoding function for one reviewed x86 decoder.

The function receives both the complete ELF and its exact decoded image.  A
future soundness theorem must show that it fetches from the loaded bytes and
implements the selected formal ISA decoder.  Merely constructing this
structure grants no such theorem. -/
structure InstructionDecoder where
  decoderId : Digest
  decoderIdPresent : decoderId ≠ ""
  decodeAt :
    ByteArray → ELF64Image → Nat → Option DecodedInstruction

/-- One basic-block certificate.  The final instruction fixes the listed
successors through `StaticControlFlow.directTargets`; intermediate rows must
be ordinary fallthrough instructions. -/
structure BlockCertificate where
  startAddress : Nat
  instructions : List DecodedInstruction
  successors : List Nat
  summaryId : Digest
  deriving DecidableEq

namespace BlockCertificate

def instructionAddresses (block : BlockCertificate) : List Nat :=
  block.instructions.map (·.address)

end BlockCertificate

/-- Versioned static certificate.  Version one deliberately supports only
the direct-control forms above. -/
structure Certificate where
  formatVersion : Nat
  decoderId : Digest
  selectedSymbol : String
  entryAddress : Nat
  blocks : List BlockCertificate
  deriving DecidableEq

namespace Certificate

def blockStarts (certificate : Certificate) : List Nat :=
  certificate.blocks.map (·.startAddress)

def instructionAddresses (certificate : Certificate) : List Nat :=
  certificate.blocks.flatMap BlockCertificate.instructionAddresses

end Certificate

/-- An instruction's exact bytes occur in one executable loaded segment.

This predicate binds the certificate to `loadSegmentBytes`: retained ELF file
bytes followed by the ELF-required zero fill.  It is stronger than merely
checking that the address lies inside an executable range. -/
def LoadedExecutableBytes
    (image : ELF64Image) (instruction : DecodedInstruction) : Prop :=
  ∃ segment ∈ image.segments,
    segment.executable = true ∧
      segment.virtualAddress.toNat ≤ instruction.address ∧
      instruction.endAddress ≤ segment.virtualEnd ∧
      instruction.encoding =
        (loadSegmentBytes segment).extract
          (instruction.address - segment.virtualAddress.toNat)
          (instruction.endAddress - segment.virtualAddress.toNat)

private instance instDecidableLoadedExecutableBytes
    (image : ELF64Image) (instruction : DecodedInstruction) :
    Decidable (LoadedExecutableBytes image instruction) := by
  unfold LoadedExecutableBytes
  infer_instance

/-- One claimed row agrees with the closed decoder and exact loaded bytes. -/
def RowValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (expectedAddress : Nat)
    (instruction : DecodedInstruction) : Prop :=
  instruction.address = expectedAddress ∧
    instruction.RangeWellFormed ∧
    decoder.decodeAt executableBytes image expectedAddress =
      some instruction ∧
    LoadedExecutableBytes image instruction

private instance instDecidableRowValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (expectedAddress : Nat)
    (instruction : DecodedInstruction) :
    Decidable
      (RowValid decoder executableBytes image expectedAddress instruction) := by
  unfold RowValid DecodedInstruction.RangeWellFormed
    DecodedInstruction.endAddress
  infer_instance

/-- Boolean checker for one exact instruction row. -/
def rowCheck
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (expectedAddress : Nat)
    (instruction : DecodedInstruction) : Bool :=
  decide
    (RowValid decoder executableBytes image expectedAddress instruction)

/-- Executable checker for exact contiguous instruction rows.

The singleton case is the final instruction.  Its statically decoded flow
must terminate the block and must reproduce the certificate's successor
list. -/
def rowsCheck
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (expectedAddress : Nat) (successors : List Nat) :
    List DecodedInstruction → Bool
  | [] => false
  | [instruction] =>
      rowCheck decoder executableBytes image expectedAddress instruction &&
        decide
          (instruction.flow.terminatesBlock = true ∧
            instruction.flow.directTargets = successors)
  | instruction :: next :: rest =>
      rowCheck decoder executableBytes image expectedAddress instruction &&
        decide (instruction.flow = .fallthrough) &&
        rowsCheck decoder executableBytes image
          instruction.endAddress successors (next :: rest)

/-- Propositional meaning exposed by successful row checking. -/
def RowsValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (expectedAddress : Nat) (successors : List Nat)
    (instructions : List DecodedInstruction) : Prop :=
  rowsCheck decoder executableBytes image expectedAddress
    successors instructions = true

private instance instDecidableRowsValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (expectedAddress : Nat) (successors : List Nat)
    (instructions : List DecodedInstruction) :
    Decidable
      (RowsValid decoder executableBytes image expectedAddress
        successors instructions) := by
  unfold RowsValid
  infer_instance

/-- A block's rows are exact, contiguous, and terminate in its declared
direct successors. -/
def BlockValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (block : BlockCertificate) : Prop :=
  RowsValid decoder executableBytes image block.startAddress
    block.successors block.instructions

private instance instDecidableBlockValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (block : BlockCertificate) :
    Decidable (BlockValid decoder executableBytes image block) := by
  unfold BlockValid
  infer_instance

/-- Complete structural meaning of certificate acceptance.

Besides exact row decoding, this requires unique block and instruction
addresses, a certified selected entry, and closure of every direct CFG edge.
Returns deliberately contribute no direct edge. -/
def StructurallyValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (certificate : Certificate) : Prop :=
  certificate.formatVersion = 1 ∧
    certificate.decoderId = decoder.decoderId ∧
    certificate.selectedSymbol = selectedEntrySymbol ∧
    certificate.entryAddress = image.entryAddress.toNat ∧
    certificate.blocks ≠ [] ∧
    certificate.blockStarts.Nodup ∧
    certificate.instructionAddresses.Nodup ∧
    certificate.entryAddress ∈ certificate.blockStarts ∧
    (∀ block ∈ certificate.blocks,
      BlockValid decoder executableBytes image block) ∧
    (∀ block ∈ certificate.blocks,
      ∀ target ∈ block.successors,
        target ∈ certificate.blockStarts)

private instance instDecidableStructurallyValid
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (image : ELF64Image)
    (certificate : Certificate) :
    Decidable
      (StructurallyValid decoder executableBytes image certificate) := by
  unfold StructurallyValid
  infer_instance

namespace StructurallyValid

theorem selectedSymbol
    {decoder : InstructionDecoder}
    {executableBytes : ByteArray} {image : ELF64Image}
    {certificate : Certificate}
    (valid :
      StructurallyValid decoder executableBytes image certificate) :
    certificate.selectedSymbol = selectedEntrySymbol :=
  valid.2.2.1

theorem entryAddress
    {decoder : InstructionDecoder}
    {executableBytes : ByteArray} {image : ELF64Image}
    {certificate : Certificate}
    (valid :
      StructurallyValid decoder executableBytes image certificate) :
    certificate.entryAddress = image.entryAddress.toNat :=
  valid.2.2.2.1

end StructurallyValid

/-- Executable static validation.  Runtime is bounded by the exact ELF and
certificate sizes, independent of every Sqrt218 input archive and of the
number of instructions executed by a cloud run. -/
def validate
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (certificate : Certificate) : Bool :=
  match decodeSelectedImage executableBytes with
  | none => false
  | some image =>
      decide
        (StructurallyValid decoder executableBytes image certificate)

/-- Kernel-facing proposition produced by successful finite validation. -/
def Checked
    (decoder : InstructionDecoder)
    (executableBytes : ByteArray) (certificate : Certificate) : Prop :=
  ∃ image : ELF64Image,
    decodeSelectedImage executableBytes = some image ∧
      StructurallyValid decoder executableBytes image certificate

theorem checked_of_validate
    {decoder : InstructionDecoder}
    {executableBytes : ByteArray} {certificate : Certificate}
    (accepted : validate decoder executableBytes certificate = true) :
    Checked decoder executableBytes certificate := by
  unfold validate at accepted
  cases decoded : decodeSelectedImage executableBytes with
  | none =>
      simp [decoded] at accepted
  | some image =>
      have accepted' :
          decide
              (StructurallyValid decoder executableBytes image certificate) =
            true := by
        simpa only [decoded] using accepted
      exact
        ⟨image, decoded, of_decide_eq_true accepted'⟩

/-- Validation also pins the selected symbol and entry address through the
existing exact ELF decoder. -/
theorem checked_selectedEntry
    {decoder : InstructionDecoder}
    {executableBytes : ByteArray} {certificate : Certificate}
    (checked : Checked decoder executableBytes certificate) :
    ∃ image : ELF64Image,
      decodeSelectedImage executableBytes = some image ∧
        image.EntryAdmissible selectedEntrySymbol image.entryAddress ∧
        certificate.selectedSymbol = selectedEntrySymbol ∧
        certificate.entryAddress = image.entryAddress.toNat := by
  rcases checked with ⟨image, decoded, structural⟩
  exact
    ⟨image, decoded,
      decodeSelectedImage_entryAdmissible decoded,
      structural.selectedSymbol,
      structural.entryAddress⟩

/-- Lift a block-indexed relation only over blocks actually retained in this
certificate. -/
def CertifiedBlockStep
    (certificate : Certificate)
    (relation :
      BlockCertificate → MachineState → MachineState → Prop)
    (before after : MachineState) : Prop :=
  ∃ block ∈ certificate.blocks, relation block before after

/-- A pointwise refinement of certified block relations lifts to every
finite block trace. -/
theorem trace_mono
    {certificate : Certificate}
    {lower higher :
      BlockCertificate → MachineState → MachineState → Prop}
    (refines :
      ∀ block ∈ certificate.blocks,
        ∀ {before after},
          lower block before after →
            higher block before after)
    {initial final : MachineState}
    (trace :
      Trace (CertifiedBlockStep certificate lower) initial final) :
    Trace (CertifiedBlockStep certificate higher) initial final := by
  induction trace with
  | refl =>
      exact .refl _
  | tail prior lastStep inductionHypothesis =>
      rcases lastStep with ⟨block, member, blockStep⟩
      exact
        .tail inductionHypothesis
          ⟨block, member, refines block member blockStep⟩

/-- Proof-carrying semantic layer for one exact ELF and static certificate.

The model is definitionally the exact selected-entry decoder plus concrete
pure-entry ABI.  `x86Step` is intentionally still explicit: constructing
`instructionTraceToBlocks` requires the future closed x86 decoder and ISA
semantics, not certificate metadata.

`instructionTraceToBlocks` is a universal theorem over arbitrary input bytes
and arbitrary formal traces.  It is not a retained production trace.
`blockSummarySound` discharges each finite code block once, while
`summaryTraceBehavior` proves loops and calls through source-shaped
invariants without unrolling a production execution. -/
structure ExactPureEntryRefinement
    (scheme : MeasurementScheme)
    (semanticsId : Digest) (semanticsIdPresent : semanticsId ≠ "")
    (config : LauncherConfig)
    (x86Step : MachineState → MachineState → Prop)
    (decoder : InstructionDecoder)
    (executable : MeasuredBlob)
    (certificate : Certificate)
    (linkedBehavior : IOBehavior) : Type where
  executableExact : executable.Exact scheme
  staticCertificate :
    validate decoder executable.bytes certificate = true
  instructionBlockStep :
    BlockCertificate → MachineState → MachineState → Prop
  summaryBlockStep :
    BlockCertificate → MachineState → MachineState → Prop
  instructionTraceToBlocks :
    ∀ {inputBytes : ByteArray}
      {initialState finalState : MachineState},
      (exactDecoderModel semanticsId semanticsIdPresent config x86Step).load
          selectedEntrySymbol executable.bytes inputBytes initialState →
        Trace
            (exactDecoderModel semanticsId semanticsIdPresent config x86Step).step
            initialState finalState →
        Trace
          (CertifiedBlockStep certificate instructionBlockStep)
          initialState finalState
  blockSummarySound :
    ∀ block ∈ certificate.blocks,
      ∀ {before after : MachineState},
        instructionBlockStep block before after →
          summaryBlockStep block before after
  summaryTraceBehavior :
    ∀ {inputBytes outputBytes : ByteArray}
      {initialState finalState : MachineState},
      (exactDecoderModel semanticsId semanticsIdPresent config x86Step).load
          selectedEntrySymbol executable.bytes inputBytes initialState →
        Trace
            (CertifiedBlockStep certificate summaryBlockStep)
            initialState finalState →
        (exactDecoderModel semanticsId semanticsIdPresent config x86Step).returnedWith
            finalState outputBytes →
        linkedBehavior inputBytes outputBytes

namespace ExactPureEntryRefinement

/-- The compact static certificate and its universal block proofs discharge
the existing machine-level `ELFISARefinesLinkedBehavior` field.

The proof does not evaluate `validate`; acceptance is retained as a small
proof field, normally established once for the pinned ELF/certificate.  No
production input or runtime trace is present in the result. -/
theorem elfISARefinesLinkedBehavior
    {scheme : MeasurementScheme}
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {x86Step : MachineState → MachineState → Prop}
    {decoder : InstructionDecoder}
    {executable : MeasuredBlob}
    {certificate : Certificate}
    {linkedBehavior : IOBehavior}
    (refinement :
      ExactPureEntryRefinement scheme semanticsId semanticsIdPresent
        config x86Step decoder executable certificate linkedBehavior) :
    ELFISARefinesLinkedBehavior scheme
      (exactDecoderModel semanticsId semanticsIdPresent config x86Step)
      executable selectedEntrySymbol linkedBehavior := by
  refine {
    executableExact := refinement.executableExact
    refines := ?_
  }
  intro inputBytes outputBytes initialState finalState
    loaded instructionTrace returned
  have blockTrace :=
    refinement.instructionTraceToBlocks loaded instructionTrace
  have summaryTrace :=
    trace_mono refinement.blockSummarySound blockTrace
  exact
    refinement.summaryTraceBehavior loaded summaryTrace returned

/-- Projection retained for audit tooling: a semantic refinement cannot omit
successful static validation of the exact executable bytes. -/
theorem checkedStaticBinary
    {scheme : MeasurementScheme}
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {x86Step : MachineState → MachineState → Prop}
    {decoder : InstructionDecoder}
    {executable : MeasuredBlob}
    {certificate : Certificate}
    {linkedBehavior : IOBehavior}
    (refinement :
      ExactPureEntryRefinement scheme semanticsId semanticsIdPresent
        config x86Step decoder executable certificate linkedBehavior) :
    Checked decoder executable.bytes certificate :=
  checked_of_validate refinement.staticCertificate

end ExactPureEntryRefinement

end SparkInterval.Execution.Architecture.X86StaticBinaryCertificate
