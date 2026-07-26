/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredSqrt218FixedV2Certificate

/-!
# Closed-registry tests for the fixed-width Sqrt218 V2 invocation

These tests exercise only the explicit failure branch and selector structure.
They do not supply, hash, decode, or replay a production certificate.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredSqrt218FixedV2Certificate

open SparkInterval.Execution

private def invocation : RegisteredInvocation :=
  .helfgottSqrt218FixedProductionV2

private def artifacts : ArtifactHashes := {
  sourceTreeHash := "test-source"
  hostExecutableHash := "test-host"
  deviceCubinHash := ""
  kernelManifestHash := "test-manifest"
}

private def statement : RunStatement := {
  algorithmId := invocation.algorithm.algorithmId
  algorithmHash := invocation.algorithm.algorithmHash
  inputHash := invocation.canonicalInputHash
  parametersHash := invocation.algorithm.canonicalParametersHash
  domainHash := invocation.algorithm.canonicalDomainHash
  result := "false"
  outputHash := "test-output"
  nonce := "test-nonce"
  target := .azureSEVSNPCPU
  targetProfileHash := "test-target-profile"
  trust := .azureSEVSNPConfidentialCompute
  trustProfileHash := "test-trust-profile"
  artifacts
}

/- The fixed-V2 execution relation remains satisfiable without asserting a
successful computation. -/
example :
    RegisteredInvocation.helfgottSqrt218FixedProductionV2.Runs "false" :=
  Or.inl rfl

example :
    RegisteredInvocation.helfgottSqrt218FixedProductionV2.ResultAllowed
      "false" :=
  Or.inl rfl

/- No statement can select the invocation while the specialized reviewed pin
is absent. -/
example : invocation.statementCheck statement = false :=
  RegisteredInvocation.helfgottSqrt218FixedProductionV2_unconfigured statement

example :
    reviewedSqrt218FixedV2DeploymentCheck none statement = false := rfl

example :
    reviewedSqrt218FixedV2ReceiptCheck none (.trustedCompute "test") = false :=
  rfl

/- The fixed-V2 registry identity is distinct from the historical V1 route. -/
example :
    RegisteredAlgorithm.helfgottSqrt218FixedV2.algorithmId ≠
      RegisteredAlgorithm.helfgottSqrt218V1.algorithmId := by
  decide

/- The exhaustive registry theorem still permits at most one interpretation
of a statement after adding the distinct fixed-V2 constructor. -/
example {other : RegisteredInvocation} {candidate : RunStatement}
    (hfixed :
      invocation.statementCheck candidate = true)
    (hother : other.statementCheck candidate = true) :
    other = invocation :=
  RegisteredInvocation.statementCheck_unique hother hfixed

/- All protocol preimage literals retain executable stale-edit diagnostics.
The guarded messages make a false result fail the test without adding
`native_decide` to either theorem below. -/
/-- info: true -/
#guard_msgs in
#eval
  RegisteredAlgorithm.helfgottSqrt218FixedV2.algorithmHashDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval
  RegisteredAlgorithm.helfgottSqrt218FixedV2.metadataHashesDiagnosticCheck

#print axioms
  RegisteredInvocation.helfgottSqrt218FixedProductionV2_sourceClaim
#print axioms
  SignedResultCertificate.certifyHelfgottSqrt218FixedV2

end SparkInterval.Tests.RegisteredSqrt218FixedV2Certificate
