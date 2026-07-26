/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredHurstSharedCertificate

/-!
# Closed shared-Hurst invocation tests

These tests exercise identity binding and the non-explosive failure path.  They
do not fabricate a successful full-source witness or trusted Azure evidence.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredHurstSharedCertificate

open SparkInterval.Certificate
open SparkInterval.Execution
open SparkInterval.TernaryGoldbach

private def invocation : RegisteredInvocation :=
  .hurstSharedFourResidualProductionV2

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
  outputHash :=
    "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"
  nonce := "nonce"
  target := .azureSEVSNPCPU
  targetProfileHash := "target-profile"
  trust := .azureSEVSNPConfidentialCompute
  trustProfileHash := "trust-profile"
  artifacts
}

/- Production selection remains disabled until an exact reviewed deployment
and receipt are installed. -/
example : invocation.statementCheck statement = false := by
  rfl

example :
    invocation.statementCheck
      { statement with target := .dgxSparkSM121, trust := .localUnattested } =
        false := by
  rfl

/- Executable stale-edit diagnostic.  The expected message fails closed if
the compiled pure SHA result is not `true`, without making compiler evaluation
a proof rule. -/
/-- info: true -/
#guard_msgs in
#eval invocation.sourceBindingDiagnosticCheck

/-- The registered relation is satisfiable without asserting any residual: a
measured campaign is permitted to report failure. -/
example : invocation.Runs "false" := by
  exact ⟨rfl, Or.inl rfl⟩

/-- A successful result exposes only the replay-shaped local evidence, not
the old global row-predicate premise. -/
example {output : String}
    (run : invocation.Runs output) (houtput : output = "true") :
    ∃ certificate : HurstAffineCertificate.Certificate,
      Nonempty (HurstSourceSemantics.LocalSourceScaleEvidence certificate) ∧
        certificate.check = true := by
  rcases run.2 with hfailure | hsuccess
  · rw [houtput] at hfailure
    contradiction
  · exact hsuccess.2

#print axioms RegisteredInvocation.hurstSharedFourResidualProductionV2_sourceClaims
#print axioms RegisteredInvocation.hurstSharedFourResidualProductionV2_realClaims
#print axioms RegisteredInvocation.hurstSharedFourResidualProductionV2_sharedRealClaims
#print axioms SignedResultCertificate.certifyHurstSharedFourResidual

end SparkInterval.Tests.RegisteredHurstSharedCertificate
