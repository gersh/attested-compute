/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredGoldbach10Pow27Certificate

namespace SparkInterval.Tests.RegisteredGoldbach10Pow27CertificateTest

open SparkInterval.Execution

example {certificate : SignedResultCertificate}
    (hcheck : certificate.goldbach10Pow27ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics.SourceClaim :=
  (certificate.certifyGoldbach10Pow27 hcheck).sourceClaim

/- The pure SHA diagnostics are executable checks.  Their preimages are
cross-checked by `tests.test_trusted_compute_registry`; keeping the literal
selectors as kernel-reduced equalities here avoids importing an evaluator
trust axiom merely to prove a diagnostic computation. -/
example :
    RegisteredAlgorithm.goldbach10Pow27V1.algorithmHash =
      "23ade6c8a6069feec88b20c24ad118a2ed8b93f16d673f20591caa7cbdf167c9" := by
  rfl

example :
    RegisteredAlgorithm.goldbach10Pow27V1.canonicalParametersHash =
      "ee334b42905942c4d3232007e2a67c27fee4e89a8143bbf6adb0d1957b0b8cb9" := by
  rfl

example :
    RegisteredAlgorithm.goldbach10Pow27V1.canonicalDomainHash =
      "4a01f0bc8f042f6605fc42fca28c73416a694e7541759abb5e7fec04720f9fa7" := by
  rfl

example :
    RegisteredInvocation.goldbach10Pow27ProductionV1.canonicalInputHash =
      "5e34a58a14883600c91b891a78749cdcff1210ce48f64e41f7bf965f2331ad27" := by
  rfl

/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.goldbach10Pow27V1.algorithmHashDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval RegisteredAlgorithm.goldbach10Pow27V1.metadataHashesDiagnosticCheck

/-- info: true -/
#guard_msgs in
#eval RegisteredInvocation.goldbach10Pow27ProductionV1.inputHashDiagnosticCheck

example :
    goldbach10Pow27TerminalArtifactPins = none := by
  rfl

example (statement : RunStatement) :
    RegisteredInvocation.goldbach10Pow27ProductionV1.statementCheck
      statement = false := by
  exact
    RegisteredInvocation.goldbach10Pow27ProductionV1_unconfigured
      rfl statement

example {statement : RunStatement} {expected : ArtifactHashes}
    (hpins : goldbach10Pow27TerminalArtifactPins = some expected)
    (halgorithm :
      statement.algorithmId =
        RegisteredAlgorithm.goldbach10Pow27V1.algorithmId)
    (hinput :
      statement.inputHash =
        RegisteredInvocation.goldbach10Pow27ProductionV1.canonicalInputHash)
    (hhost :
      statement.artifacts.hostExecutableHash =
        expected.hostExecutableHash)
    (hdevice :
      statement.artifacts.deviceCubinHash = expected.deviceCubinHash)
    (hsource :
      statement.artifacts.sourceTreeHash = expected.sourceTreeHash)
    (hchildren :
      statement.artifacts.kernelManifestHash ≠
        expected.kernelManifestHash) :
    RegisteredInvocation.goldbach10Pow27ProductionV1.statementCheck
      statement ≠ true := by
  exact
    RegisteredInvocation.goldbach10Pow27ProductionV1_rejects_childIdentityCommitmentSubstitution
      hpins halgorithm hinput hhost hdevice hsource hchildren

#print axioms SignedResultCertificate.certifyGoldbach10Pow27

end SparkInterval.Tests.RegisteredGoldbach10Pow27CertificateTest
