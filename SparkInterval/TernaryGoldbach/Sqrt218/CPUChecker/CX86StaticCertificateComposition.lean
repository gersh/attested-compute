/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86StaticBinaryCertificate
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CX86ELFComposition

/-!
# Exact static-binary certificate composition for Sqrt218

The older `CX86ELFComposition.suppliesSuccessfulPureEntry` theorem accepts an
arbitrary `PureEntryModel`.  This module gives the narrower recommended
entry: the machine is definitionally
`X86ELFExactPureEntry.exactDecoderModel`, so the exact selected-entry ELF
decoder and concrete pure-entry ABI initializer/observer cannot be replaced
by a caller.

The x86 transition relation remains an explicit parameter.  Its universal
proof is the `ExactPureEntryRefinement.instructionTraceToBlocks` field; this
module does not define or assume an x86 semantics.

No executable, input archive, or instruction trace is evaluated here.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CX86StaticCertificateComposition

open SparkInterval.Execution
open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder
open SparkInterval.Execution.Architecture.X86ELFExactPureEntry
open SparkInterval.Execution.Architecture.X86PureEntryABI
open
  SparkInterval.Execution.Architecture.X86StaticBinaryCertificate
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance.ArchitectureExecutionAdapter
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchitectureComposition
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPureEntryComposition

/-- The exact-decoder/ABI static certificate plus the remaining ordinary
assembler/linker, CompCert, and VST refinements supplies the one architecture
obligation used by the Sqrt218 theorem.

All parameters are data-independent.  In particular, `x86Step` is formal ISA
semantics and the three behavior refinements are universal theorems; none is
a fact imported from the production receipt. -/
theorem suppliesSuccessfulPureEntry
    {implementation : NativeImplementation}
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {x86Step : MachineState → MachineState → Prop}
    {decoder : InstructionDecoder}
    {certificate : Certificate}
    {linkedImageBehavior compCertAsmBehavior clightBehavior : IOBehavior}
    (binding : ExactArchitectureBinding implementation)
    (machineIdentity :
      binding.machine =
        (exactDecoderModel semanticsId semanticsIdPresent
          config x86Step).toArchitectureSemantics)
    (entryPointIdentity :
      implementation.identity.entryPoint = selectedEntrySymbol)
    (staticRefinement :
      ExactPureEntryRefinement sha256MeasurementScheme
        semanticsId semanticsIdPresent config x86Step decoder
        (measuredBlob binding.executableBytes)
        certificate linkedImageBehavior)
    (assemblerLinker :
      BehaviorRefines linkedImageBehavior compCertAsmBehavior)
    (compCert :
      BehaviorRefines compCertAsmBehavior clightBehavior)
    (vstAndNeutralContract :
      BehaviorRefines clightBehavior
        (successfulPureEntryChecker
          implementation.identity.neutralContractId).accepts) :
    ArchitectureExecutionSuppliesSuccessfulPureEntry implementation := by
  let chain :
      PureEntryRefinementChain sha256MeasurementScheme
        (exactDecoderModel semanticsId semanticsIdPresent config x86Step)
        (successfulPureEntryChecker
          implementation.identity.neutralContractId)
        (measuredBlob binding.executableBytes)
        selectedEntrySymbol :=
    {
      linkedImageBehavior
      compCertAsmBehavior
      clightBehavior
      elfAndISA :=
        staticRefinement.elfISARefinesLinkedBehavior
      assemblerLinker
      compCert
      vstAndNeutralContract
    }
  apply
    CX86ELFComposition.suppliesSuccessfulPureEntry
      binding machineIdentity
  simpa [entryPointIdentity] using chain

end
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CX86StaticCertificateComposition
