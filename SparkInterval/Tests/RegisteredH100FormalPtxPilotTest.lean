/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredH100FormalPtxPilot

/-!
# Closed H100 formal-PTX pilot registry tests

These checks exercise the stable mathematical invocation only.  They do not
fabricate Azure/NVIDIA evidence or add a registry receipt.  A generated
production consumer must still cross the repository's single trusted-run
axiom after an exact source-admitted receipt is present.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredH100FormalPtxPilot

open SparkInterval.Certificate
open SparkInterval.Execution

private def invocation : RegisteredInvocation :=
  .h100FormalPtxConstantOneV1

private def artifacts : ArtifactHashes := {
  sourceTreeHash := "source"
  hostExecutableHash := "host"
  deviceCubinHash := "cubin"
  kernelManifestHash := "manifest"
}

private def statement : RunStatement := {
  algorithmId := invocation.algorithm.algorithmId
  algorithmHash := invocation.algorithm.algorithmHash
  inputHash := invocation.canonicalInputHash
  parametersHash := invocation.algorithm.canonicalParametersHash
  domainHash := invocation.algorithm.canonicalDomainHash
  result := RegisteredAlgorithm.h100FormalPtxConstantOneOutput
  outputHash :=
    "205f8f99959515c5308e00f7ddc1578ea5e93e1079eadf998c1137c646e9e621"
  nonce := "nonce"
  target := .nvidiaH100SM90
  targetProfileHash := "target-profile"
  trust := .nvidiaH100ConfidentialCompute
  trustProfileHash := "trust-profile"
  artifacts
}

example : invocation.statementCheck statement = true := by
  rfl

/-- A matching pilot identity cannot attach its semantics to arbitrary bytes. -/
example :
    invocation.statementCheck { statement with result := "error" } = false := by
  apply
    RegisteredInvocation.statementCheck_eq_false_of_resultCheck_eq_false
  rfl

/-- The closed H100 computation cannot be relabeled as a local DGX run. -/
example :
    invocation.statementCheck
      { statement with target := .dgxSparkSM121, trust := .localUnattested } =
        false := by
  rfl

/-- The registered relation fixes the complete compact result bytes. -/
private theorem exactRun :
    RegisteredInvocation.h100FormalPtxConstantOneV1.Runs
      RegisteredAlgorithm.h100FormalPtxConstantOneOutput := by
  exact ⟨rfl, rfl⟩

example :
    RegisteredAlgorithm.h100FormalPtxConstantOneOutput =
        RegisteredAlgorithm.h100FormalPtxConstantOneOutput ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) :=
  RegisteredInvocation.h100FormalPtxConstantOneV1_result exactRun

/-- The reusable end-to-end theorem exposes all application facts from one
closed-invocation outcome check.  This theorem does not fabricate such a
check; production consumers obtain it only from a source-admitted receipt. -/
example (certificate : SignedResultCertificate)
    (hcheck : certificate.outcomeCheckForRegisteredInvocation
      h100FormalPtxConstantOneInvocation = true) :
    certificate.resultCertificate =
        RegisteredAlgorithm.h100FormalPtxConstantOneOutput ∧
      certificate.statement.result =
        RegisteredAlgorithm.h100FormalPtxConstantOneOutput ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) ∧
      RegisteredAlgorithm.h100FormalPtxConstantOnePTX =
        SparkInterval.PTX.renderUncheckedFor .sm90
          (SparkInterval.PTX.buildModule h100FormalPtxConstantOneBatch) := by
  have certified := certificate.certifyH100FormalPtxConstantOne hcheck
  exact ⟨certified.resultCertificate_eq, certified.statementResult_eq,
    certified.lowerEndpoint, certified.formalProgramIdentity⟩

#print axioms RegisteredAlgorithm.h100FormalPtxConstantOne_decodes
#print axioms h100FormalPtxConstantOnePTX_eq_formalEmitter
#print axioms RegisteredInvocation.h100FormalPtxConstantOneV1_result
#print axioms SignedResultCertificate.certifyH100FormalPtxConstantOne

end SparkInterval.Tests.RegisteredH100FormalPtxPilot
