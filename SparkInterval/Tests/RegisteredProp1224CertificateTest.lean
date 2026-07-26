/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredProp1224Certificate

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredProp1224CertificateTest

open SparkInterval.Execution

private def invocation : RegisteredInvocation :=
  .helfgottProp1224ProductionV1

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
example : RegisteredInvocation.helfgottProp1224ProductionV1.Runs "false" := by
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

/- Executable diagnostics; these do not introduce compiled evaluation as a
proof rule. -/
/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.helfgottProp1224MpfrV1.algorithmHashDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.helfgottProp1224MpfrV1.metadataHashesDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval invocation.inputHashDiagnosticCheck

#print axioms
  SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.sourceClaim_of_checked_certificate
#print axioms RegisteredInvocation.helfgottProp1224ProductionV1_sourceClaim
#print axioms SignedResultCertificate.certifyHelfgottProp1224

end SparkInterval.Tests.RegisteredProp1224CertificateTest
