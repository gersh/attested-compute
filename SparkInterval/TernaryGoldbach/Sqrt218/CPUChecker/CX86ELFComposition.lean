/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFDecoder
import SparkInterval.Execution.X86PureEntryABI
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CArchitectureComposition

/-!
# X86 ELF proof-chain handoff for the Sqrt218 pure entry

This module identifies the exact target of the generic static-ELF/x86 proof
chain with the complete successful Sqrt218 source relation. It proves only the
composition. `X86ELFDecoder.decodeSelectedImage` closes the bounded ELF64
header, program-header, `PT_LOAD` byte-slicing, and exact selected
static-symbol resolution layers. `X86PureEntryABI` supplies a symbolic
finite-memory initializer and return observer. Concrete launcher-to-model
refinement, x86 ISA semantics, assembler/linker validation, CompCert, and VST
remain substantive low-level obligations.

No executable or certificate is evaluated here.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CX86ELFComposition

open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance.ArchitectureExecutionAdapter
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchitectureComposition
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPureEntryComposition

/-- The complete five-layer x86 pure-entry refinement chain supplies the
single architecture-to-source obligation used by the Sqrt218 theorem. -/
theorem suppliesSuccessfulPureEntry
    {implementation : NativeImplementation}
    {model : PureEntryModel}
    (binding : ExactArchitectureBinding implementation)
    (machineIdentity :
      binding.machine = model.toArchitectureSemantics)
    (chain :
      PureEntryRefinementChain
        sha256MeasurementScheme model
        (successfulPureEntryChecker
          implementation.identity.neutralContractId)
        (measuredBlob binding.executableBytes)
        implementation.identity.entryPoint) :
    ArchitectureExecutionSuppliesSuccessfulPureEntry implementation := by
  apply
    architectureExecutionSuppliesSuccessfulPureEntry_of_checkerRefinement
      binding
  rw [machineIdentity]
  exact chain.architectureRefinement

/-- Once the exact x86 chain and one exact architecture execution are
available, the package-neutral source claim follows without replay. -/
theorem sourceClaim_of_x86ELFExecution
    {implementation : NativeImplementation}
    {model : PureEntryModel}
    {statement : SparkInterval.Execution.RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (binding : ExactArchitectureBinding implementation)
    (machineIdentity :
      binding.machine = model.toArchitectureSemantics)
    (chain :
      PureEntryRefinementChain
        sha256MeasurementScheme model
        (successfulPureEntryChecker
          implementation.identity.neutralContractId)
        (measuredBlob binding.executableBytes)
        implementation.identity.entryPoint)
    (statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope)
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (architectureExecuted :
      implementation.architectureExecution
        inputBytes receiptBound.rawResultBytes) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  sourceClaim_of_architectureExecution_viaPureEntry
    statementBound receiptBound architectureExecuted
      (suppliesSuccessfulPureEntry binding machineIdentity chain)

end
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CX86ELFComposition
