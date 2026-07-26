/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredZetaHeadCertificate

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredZetaHeadCertificateTest

open SparkInterval.Execution

private def invocation : RegisteredInvocation :=
  .plattHead2e4ProductionV1

private def artifacts : ArtifactHashes := {
  sourceTreeHash := "source"
  hostExecutableHash := "host"
  deviceCubinHash := ""
  kernelManifestHash := "manifest"
}

private def statement : RunStatement := {
  algorithmId := invocation.algorithm.algorithmId
  algorithmHash := invocation.algorithm.algorithmHash
  inputHash := invocation.canonicalInputHash
  parametersHash := invocation.algorithm.canonicalParametersHash
  domainHash := invocation.algorithm.canonicalDomainHash
  result := "true"
  outputHash := "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"
  nonce := "nonce"
  target := .azureSEVSNPCPU
  targetProfileHash := "target-profile"
  trust := .azureSEVSNPConfidentialCompute
  trustProfileHash := "trust-profile"
  artifacts
}

/-- Failure keeps the closed relation satisfiable but proves no source claim. -/
example : RegisteredInvocation.plattHead2e4ProductionV1.Runs "false" := by
  exact ⟨rfl, Or.inl rfl⟩

/- Production selection remains disabled until an exact reviewed deployment
and receipt are installed. -/
example : invocation.statementCheck statement = false := by
  rfl

example :
    invocation.statementCheck
      { statement with target := .nvidiaH100SM90, trust := .nvidiaH100ConfidentialCompute } =
        false := by
  rfl

example :
    RegisteredAlgorithm.plattHead2e4AllQ128RowsDigest =
      "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca" := by
  rfl

example :
    RegisteredAlgorithm.plattHead2e4IncludedQ128RowsCommitment =
      "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7" := by
  rfl

/- Executable diagnostics: the guarded expected message fails if the compiled
pure SHA check returns anything other than `true`. -/
/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.plattHead2e4V1.algorithmHashDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.plattHead2e4V1.metadataHashesDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval invocation.inputHashDiagnosticCheck

#print axioms
  SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence
#print axioms RegisteredInvocation.plattHead2e4ProductionV1_sourceClaim
#print axioms SignedResultCertificate.certifyPlattHead2e4

end SparkInterval.Tests.RegisteredZetaHeadCertificateTest
