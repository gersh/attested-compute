/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.Execution.X86StaticBinaryCertificate

/-!
# Closed static-CPU executable certificates

This module extracts the data-independent part of the Sqrt218 static-ELF
refinement route for reuse by the fixed ternary-Goldbach CPU campaigns.  It
keeps four boundaries separate:

1. a compact certificate validates the exact retained ELF bytes and their
   reachable block partition;
2. arbitrary formal instruction traces refine the certified block summaries;
3. linked-image behavior refines compiler-target and source behavior; and
4. source behavior refines one fixed `NativeCheckerSemantics`.

No production input, arithmetic trace, or application proposition is a field.
The intermediate behaviors are connected only by universal refinement
theorems, and the final relation is the checker fixed by the caller's theorem
type.

`InstalledCertificate` is deliberately non-vacuous.  It contains an actual
closed `ReviewedArchitectureRun` and a proof that this exact value is the one
installed by `RegisteredArchitectureInvocation.reviewedRun`.  Its
`closedRefinement` theorem never reasons from `reviewedRun = none`.

The current registry has no installed run, so this module creates no
production refinement.  It introduces no axiom and performs no executable or
finite-arithmetic replay.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.StaticCPUExecutableCertificate

open X86ELF

/-- A certified-block transition over the state type of the selected formal
CPU model.

This is the state-polymorphic extraction of
`X86StaticBinaryCertificate.CertifiedBlockStep`, whose original state is the
Sqrt218 pure-entry ABI machine. -/
def CertifiedBlockStep
    {State : Type}
    (certificate : X86StaticBinaryCertificate.Certificate)
    (relation :
      X86StaticBinaryCertificate.BlockCertificate →
        State → State → Prop)
    (before after : State) : Prop :=
  ∃ block ∈ certificate.blocks, relation block before after

/-- Pointwise block refinement lifts to every finite certified-block trace. -/
theorem certifiedBlockTrace_mono
    {State : Type}
    {certificate : X86StaticBinaryCertificate.Certificate}
    {lower higher :
      X86StaticBinaryCertificate.BlockCertificate →
        State → State → Prop}
    (refines :
      ∀ block ∈ certificate.blocks,
        ∀ {before after},
          lower block before after →
            higher block before after)
    {initial final : State}
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

/-- Universal static-ELF and block-summary refinement for one exact
executable and entry point.

The Boolean certificate check proves only byte-level code coverage and
control-flow shape.  `instructionTraceToBlocks` is the first semantic theorem:
it connects every trace of the selected formal CPU model to that checked block
partition.  `blockSummarySound` and `summaryTraceBehavior` then prove the
program behavior without replaying a production execution. -/
structure StaticPureEntryRefinement
    (scheme : MeasurementScheme)
    (model : X86ELF.PureEntryModel)
    (entryPoint : String)
    (decoder : X86StaticBinaryCertificate.InstructionDecoder)
    (executable : MeasuredBlob)
    (certificate : X86StaticBinaryCertificate.Certificate)
    (linkedImageBehavior : X86ELF.IOBehavior) : Type 1 where
  executableExact : executable.Exact scheme
  staticCertificate :
    X86StaticBinaryCertificate.validate
      decoder executable.bytes certificate = true
  instructionBlockStep :
    X86StaticBinaryCertificate.BlockCertificate →
      model.State → model.State → Prop
  summaryBlockStep :
    X86StaticBinaryCertificate.BlockCertificate →
      model.State → model.State → Prop
  instructionTraceToBlocks :
    ∀ {inputBytes : ByteArray}
      {initialState finalState : model.State},
      model.load entryPoint executable.bytes inputBytes initialState →
        Trace model.step initialState finalState →
        Trace
          (CertifiedBlockStep certificate instructionBlockStep)
          initialState finalState
  blockSummarySound :
    ∀ block ∈ certificate.blocks,
      ∀ {before after : model.State},
        instructionBlockStep block before after →
          summaryBlockStep block before after
  summaryTraceBehavior :
    ∀ {inputBytes outputBytes : ByteArray}
      {initialState finalState : model.State},
      model.load entryPoint executable.bytes inputBytes initialState →
        Trace
          (CertifiedBlockStep certificate summaryBlockStep)
          initialState finalState →
        model.returnedWith finalState outputBytes →
        linkedImageBehavior inputBytes outputBytes

namespace StaticPureEntryRefinement

/-- Embed the strongest existing Sqrt218 exact-decoder/static-block
certificate into the state-polymorphic interface.

This adapter is definition-only: it does not weaken or replay any of the
original universal instruction/block/summary obligations. -/
def ofExactDecoderRefinement
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : X86PureEntryABI.LauncherConfig}
    {x86Step :
      X86PureEntryABI.MachineState →
        X86PureEntryABI.MachineState → Prop}
    {decoder : X86StaticBinaryCertificate.InstructionDecoder}
    {executable : MeasuredBlob}
    {certificate : X86StaticBinaryCertificate.Certificate}
    {linkedImageBehavior : X86ELF.IOBehavior}
    (refinement :
      X86StaticBinaryCertificate.ExactPureEntryRefinement
        registeredSHA256MeasurementScheme
        semanticsId semanticsIdPresent config x86Step decoder
        executable certificate linkedImageBehavior) :
    StaticPureEntryRefinement registeredSHA256MeasurementScheme
      (X86ELFExactPureEntry.exactDecoderModel
        semanticsId semanticsIdPresent config x86Step)
      X86ELF.ELF64Decoder.selectedEntrySymbol decoder
      executable certificate linkedImageBehavior where
  executableExact := refinement.executableExact
  staticCertificate := refinement.staticCertificate
  instructionBlockStep := refinement.instructionBlockStep
  summaryBlockStep := refinement.summaryBlockStep
  instructionTraceToBlocks := by
    intro inputBytes initialState finalState loaded traced
    exact refinement.instructionTraceToBlocks loaded traced
  blockSummarySound := refinement.blockSummarySound
  summaryTraceBehavior := by
    intro inputBytes outputBytes initialState finalState loaded traced returned
    exact refinement.summaryTraceBehavior loaded traced returned

/-- The checked block decomposition and its universal semantic proofs supply
the existing static-ELF/ISA behavior boundary. -/
theorem elfISARefinesLinkedBehavior
    {scheme : MeasurementScheme}
    {model : X86ELF.PureEntryModel}
    {entryPoint : String}
    {decoder : X86StaticBinaryCertificate.InstructionDecoder}
    {executable : MeasuredBlob}
    {certificate : X86StaticBinaryCertificate.Certificate}
    {linkedImageBehavior : X86ELF.IOBehavior}
    (refinement :
      StaticPureEntryRefinement scheme model entryPoint decoder
        executable certificate linkedImageBehavior) :
    X86ELF.ELFISARefinesLinkedBehavior
      scheme model executable entryPoint linkedImageBehavior := by
  refine {
    executableExact := refinement.executableExact
    refines := ?_
  }
  intro inputBytes outputBytes initialState finalState
    loaded instructionTrace returned
  have blockTrace :=
    refinement.instructionTraceToBlocks loaded instructionTrace
  have summaryTrace :=
    certifiedBlockTrace_mono refinement.blockSummarySound blockTrace
  exact refinement.summaryTraceBehavior loaded summaryTrace returned

/-- The exact ELF bytes really passed the compact static-binary validator. -/
theorem checkedStaticBinary
    {scheme : MeasurementScheme}
    {model : X86ELF.PureEntryModel}
    {entryPoint : String}
    {decoder : X86StaticBinaryCertificate.InstructionDecoder}
    {executable : MeasuredBlob}
    {certificate : X86StaticBinaryCertificate.Certificate}
    {linkedImageBehavior : X86ELF.IOBehavior}
    (refinement :
      StaticPureEntryRefinement scheme model entryPoint decoder
        executable certificate linkedImageBehavior) :
    X86StaticBinaryCertificate.Checked
      decoder executable.bytes certificate :=
  X86StaticBinaryCertificate.checked_of_validate
    refinement.staticCertificate

end StaticPureEntryRefinement

/-- Complete data-independent static-CPU certificate for one concrete closed
registry value and one concrete checker.

`machineIdentity` prevents substitution of a convenient application-level
semantics: the pure-entry model must be definitionally identified with the
exact formal machine stored in the reviewed closed registry entry.
`sourceToChecker` ends at the fixed checker relation; there is no theorem or
arbitrary proposition field carrying the mathematical claim. -/
structure Certificate
    (invocation : RegisteredArchitectureInvocation)
    (reviewed : ReviewedArchitectureRun invocation)
    (checker : NativeCheckerSemantics) : Type 1 where
  cpuTarget :
    invocation.terminalTarget = .azureSEVSNPCPU
  model : X86ELF.PureEntryModel
  machineIdentity :
    reviewed.machine = model.toArchitectureSemantics
  decoder : X86StaticBinaryCertificate.InstructionDecoder
  staticBinary : X86StaticBinaryCertificate.Certificate
  linkedImageBehavior : X86ELF.IOBehavior
  compilerTargetBehavior : X86ELF.IOBehavior
  sourceBehavior : X86ELF.IOBehavior
  pureEntry :
    StaticPureEntryRefinement registeredSHA256MeasurementScheme
      model reviewed.compactPins.entryPoint decoder
      reviewed.executableArtifact staticBinary linkedImageBehavior
  assemblerLinker :
    X86ELF.BehaviorRefines
      linkedImageBehavior compilerTargetBehavior
  compiler :
    X86ELF.BehaviorRefines
      compilerTargetBehavior sourceBehavior
  sourceToChecker :
    X86ELF.BehaviorRefines sourceBehavior checker.accepts

namespace Certificate

/-- A closed static-CPU certificate constructs the exact generic
architecture-to-checker theorem for its reviewed registry value.

This composition is universal in input/output bytes and formal traces.  It
does not execute the binary or the finite arithmetic algorithm. -/
theorem architectureRefinement
    {invocation : RegisteredArchitectureInvocation}
    {reviewed : ReviewedArchitectureRun invocation}
    {checker : NativeCheckerSemantics}
    (certificate : Certificate invocation reviewed checker) :
    ArchitectureRefinesNativeChecker
      registeredSHA256MeasurementScheme reviewed.machine checker
      reviewed.executableArtifact reviewed.compactPins.entryPoint := by
  let chain :
      X86ELF.PureEntryRefinementChain
        registeredSHA256MeasurementScheme certificate.model checker
        reviewed.executableArtifact reviewed.compactPins.entryPoint :=
    {
      linkedImageBehavior := certificate.linkedImageBehavior
      compCertAsmBehavior := certificate.compilerTargetBehavior
      clightBehavior := certificate.sourceBehavior
      elfAndISA :=
        certificate.pureEntry.elfISARefinesLinkedBehavior
      assemblerLinker := certificate.assemblerLinker
      compCert := certificate.compiler
      vstAndNeutralContract := certificate.sourceToChecker
    }
  rw [certificate.machineIdentity]
  exact chain.architectureRefinement

end Certificate

/-- A static-CPU certificate for the actual value installed in one closed
registry branch.

The `installed` field is what prevents the closed theorem below from being a
vacuous proof based on the current `none` branch. -/
structure InstalledCertificate
    (invocation : RegisteredArchitectureInvocation)
    (checker : NativeCheckerSemantics) : Type 1 where
  reviewed : ReviewedArchitectureRun invocation
  installed : invocation.reviewedRun = some reviewed
  certificate : Certificate invocation reviewed checker

namespace InstalledCertificate

/-- An installed certificate always exhibits a genuinely installed reviewed
run. -/
theorem installedRunExists
    {invocation : RegisteredArchitectureInvocation}
    {checker : NativeCheckerSemantics}
    (certificate : InstalledCertificate invocation checker) :
    ∃ reviewed : ReviewedArchitectureRun invocation,
      invocation.reviewedRun = some reviewed :=
  ⟨certificate.reviewed, certificate.installed⟩

/-- One installed static-CPU certificate supplies the universal closed
refinement shape used by the external-atom registered capstone.

Any queried value must equal the actually installed reviewed value.  The proof
uses equality of two `some` values and never uses an absent registry branch. -/
theorem closedRefinement
    {invocation : RegisteredArchitectureInvocation}
    {checker : NativeCheckerSemantics}
    (certificate : InstalledCertificate invocation checker) :
    ∀ reviewed : ReviewedArchitectureRun invocation,
      invocation.reviewedRun = some reviewed →
        ArchitectureRefinesNativeChecker
          registeredSHA256MeasurementScheme reviewed.machine checker
          reviewed.executableArtifact reviewed.compactPins.entryPoint := by
  intro reviewed selected
  have equalSome :
      some reviewed = some certificate.reviewed :=
    selected.symm.trans certificate.installed
  have equalReviewed : reviewed = certificate.reviewed :=
    Option.some.inj equalSome
  subst reviewed
  exact certificate.certificate.architectureRefinement

end InstalledCertificate

end SparkInterval.Execution.Architecture.StaticCPUExecutableCertificate
