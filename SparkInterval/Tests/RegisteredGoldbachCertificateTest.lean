/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredGoldbachCertificate

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredGoldbachCertificateTest

open SparkInterval.Execution

private def invocation : RegisteredInvocation :=
  .helfgottPlattGoldbachProductionV1

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

example : RegisteredInvocation.helfgottPlattGoldbachProductionV1.Runs "false" := by
  exact ⟨rfl, Or.inl rfl⟩

example : helfgottPlattGoldbachTerminalArtifactPins = none := by
  rfl

example : invocation.statementCheck statement = false := by
  exact
    RegisteredInvocation.helfgottPlattGoldbachProductionV1_unconfigured
      rfl statement

example {candidate : RunStatement} {expected : ArtifactHashes}
    (hpins : helfgottPlattGoldbachTerminalArtifactPins = some expected)
    (halgorithm :
      candidate.algorithmId =
        RegisteredAlgorithm.helfgottPlattGoldbachV1.algorithmId)
    (hinput :
      candidate.inputHash =
        RegisteredInvocation.helfgottPlattGoldbachProductionV1.canonicalInputHash)
    (hhost :
      candidate.artifacts.hostExecutableHash =
        expected.hostExecutableHash)
    (hdevice :
      candidate.artifacts.deviceCubinHash = expected.deviceCubinHash)
    (hsource :
      candidate.artifacts.sourceTreeHash = expected.sourceTreeHash)
    (hchildren :
      candidate.artifacts.kernelManifestHash ≠
        expected.kernelManifestHash) :
    invocation.statementCheck candidate ≠ true := by
  exact
    RegisteredInvocation.helfgottPlattGoldbachProductionV1_rejects_childIdentityCommitmentSubstitution
      hpins halgorithm hinput hhost hdevice hsource hchildren

/- Executable diagnostics: keep compiler evaluation visibly separate from
the proof-producing certificate theorem below. -/
/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.helfgottPlattGoldbachV1.algorithmHashDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.helfgottPlattGoldbachV1.metadataHashesDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval invocation.inputHashDiagnosticCheck

#print axioms
  SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.sourceClaim_of_checked_evidence
#print axioms RegisteredInvocation.helfgottPlattGoldbachProductionV1_sourceClaim
#print axioms SignedResultCertificate.certifyHelfgottPlattGoldbach

end SparkInterval.Tests.RegisteredGoldbachCertificateTest
