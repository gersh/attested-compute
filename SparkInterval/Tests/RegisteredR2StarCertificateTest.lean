/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredR2StarCertificate

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredR2StarCertificateTest

open SparkInterval.Execution

private def invocation : RegisteredInvocation :=
  .ramareZunigaLemma62ProductionV1

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
  result := "true"
  outputHash := "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"
  nonce := "nonce"
  target := .nvidiaH100SM90
  targetProfileHash := "target-profile"
  trust := .nvidiaH100ConfidentialCompute
  trustProfileHash := "trust-profile"
  artifacts
}

/-- Failure keeps the closed relation satisfiable but proves no source claim. -/
example : RegisteredInvocation.ramareZunigaLemma62ProductionV1.Runs "false" := by
  exact ⟨rfl, Or.inl rfl⟩

/- Production selection remains disabled until an exact reviewed deployment
and receipt are installed. -/
example : invocation.statementCheck statement = false := by rfl

example :
    invocation.statementCheck
      { statement with target := .azureSEVSNPCPU, trust := .azureSEVSNPConfidentialCompute } =
        false := by
  rfl

/- Executable diagnostics; expected messages make a false result fail without
putting `native_decide` in a theorem. -/
/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.ramareZunigaLemma62V1.algorithmHashDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.ramareZunigaLemma62V1.metadataHashesDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval invocation.inputHashDiagnosticCheck

#print axioms
  SparkInterval.TernaryGoldbach.R2StarSourceSemantics.sourceClaim_of_checked_certificate
#print axioms RegisteredInvocation.ramareZunigaLemma62ProductionV1_sourceClaim
#print axioms SignedResultCertificate.certifyRamareZunigaLemma62

end SparkInterval.Tests.RegisteredR2StarCertificateTest
