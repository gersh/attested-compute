/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredPsiLemma92Certificate

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredPsiLemma92CertificateTest

open SparkInterval.Execution

private def invocation : RegisteredInvocation := .ch25PsiLemma92ProductionV1

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

/-- The canonical failure result keeps the closed relation satisfiable but
cannot satisfy the application success check. -/
example : RegisteredInvocation.ch25PsiLemma92ProductionV1.Runs "false" := by
  exact ⟨rfl, Or.inl rfl⟩

/- Production selection remains disabled until an exact reviewed deployment
and receipt are installed. -/
example : invocation.statementCheck statement = false := by rfl

/- Executable diagnostics, guarded without adding `native_decide` to any
theorem. -/
/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.ch25PsiLemma92V1.algorithmHashDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.ch25PsiLemma92V1.metadataHashesDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval invocation.inputHashDiagnosticCheck

example :
    invocation.statementCheck
      { statement with target := .dgxSparkSM121, trust := .localUnattested } =
        false := by rfl

#print axioms RegisteredInvocation.ch25PsiLemma92ProductionV1_sourceClaim
#print axioms SignedResultCertificate.certifyCH25PsiLemma92
#print axioms SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.canonicalState_prefixRealization
#print axioms SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_canonical_evidence
#print axioms SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_gap_evidence

end SparkInterval.Tests.RegisteredPsiLemma92CertificateTest
