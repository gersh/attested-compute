/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredCDEMAbelCertificate

/-!
# Focused tests for the registered CDEM Abel bridge

No test fabricates trusted Azure evidence.  The examples exercise the closed
identity, production result encoding, exact source-proposition projection,
and the end-to-end theorem interface used once a real receipt is admitted.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredCDEMAbelCertificate

open SparkInterval.Certificate
open SparkInterval.Execution
open SparkInterval.TernaryGoldbach

private def invocation : RegisteredInvocation :=
  .cdemTableAbelProductionV2

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
  result := cdemTableAbelProductionOutput
  outputHash :=
    "84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c"
  nonce := "nonce"
  target := .azureSEVSNPCPU
  targetProfileHash := "target-profile"
  trust := .azureSEVSNPConfidentialCompute
  trustProfileHash := "trust-profile"
  artifacts
}

/-- Production remains fail-closed until reviewed deployment and receipt pins
are installed. -/
example : invocation.statementCheck statement = false := by
  rfl

/-- The result-language guard is independent of the currently absent
production deployment pin. -/
example :
    invocation.resultCheck { statement with result := "error" } = false := by
  rfl

/-- A CDEM receipt cannot be relabeled as an unattested local execution. -/
example :
    invocation.statementCheck
      { statement with target := .dgxSparkSM121, trust := .localUnattested } =
        false := by
  rfl

/- Executable stale-edit diagnostic, kept separate from the mathematical
certificate theorem. -/
/-- info: true -/
#guard_msgs in
#eval invocation.sourceBindingDiagnosticCheck

/-- The compact production bytes are exactly the injective pairing of the two
numerators printed by the reviewed producer. -/
example :
    cdemTableAbelProductionOutput =
      "2372685835387717172679029560108650251645442524" := by
  norm_num [cdemTableAbelProductionOutput,
    RegisteredAlgorithm.cdemTableAbelProductionOutput,
    CDEMAbelSource.signedTarget, CDEMAbelSource.absoluteTarget, Nat.pair]
  decide

/-- The bridge concludes the exact source claim, not the downstream coarse
`U <= 7/20000`, `V <= 48712` consumer bounds. -/
example {output : String}
    (run : RegisteredInvocation.cdemTableAbelProductionV2.Runs output)
    (houtput : output = cdemTableAbelProductionOutput) :
    CDEMAbelSource.SourceClaim := by
  exact RegisteredInvocation.cdemTableAbelProductionV2_sourceClaim
    run houtput

/-- A non-failure output cannot bypass the checked recurrence certificate or
its local recurrence/fold premise. -/
example {output : String}
    (run : RegisteredInvocation.cdemTableAbelProductionV2.Runs output)
    (hsuccess : output ≠ "false") :
    SparkInterval.Generated.CDEMAbelProduction.certificate.check = true ∧
      Nonempty
        (CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence
          SparkInterval.Generated.CDEMAbelProduction.certificate) ∧
      CDEMAbelSource.ScaledOutputClaim
        SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
        SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator := by
  rcases
      RegisteredInvocation.cdemTableAbelProductionV2_result run hsuccess with
    ⟨_hencoded, hrecurrenceCheck,
      hlocalSourceScaleEvidence, hscaled⟩
  exact ⟨hrecurrenceCheck, hlocalSourceScaleEvidence, hscaled⟩

/-- Reusable end-to-end interface for a future source-admitted Azure receipt. -/
example (certificate : SignedResultCertificate)
    (hcheck : certificate.cdemTableAbelProductionCheck = true) :
    certificate.resultCertificate = cdemTableAbelProductionOutput ∧
      certificate.statement.result = cdemTableAbelProductionOutput ∧
      CDEMAbelSource.ScaledOutputClaim
        CDEMAbelSource.signedTarget CDEMAbelSource.absoluteTarget ∧
      SparkInterval.Generated.CDEMAbelProduction.certificate.check = true ∧
      Nonempty
        (CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence
          SparkInterval.Generated.CDEMAbelProduction.certificate) ∧
      CDEMAbelSource.SourceClaim := by
  have certified := certificate.certifyCDEMTableAbel hcheck
  exact ⟨certified.resultCertificate_eq, certified.statementResult_eq,
    certified.scaledNumerators, certified.recurrenceCheck,
    certified.localSourceScaleEvidence, certified.sourceClaim⟩

#print axioms CDEMAbelSource.sourceClaim_of_scaledOutput
#print axioms RegisteredInvocation.cdemTableAbelProductionV2_result
#print axioms RegisteredInvocation.cdemTableAbelProductionV2_sourceClaim
#print axioms SignedResultCertificate.certifyCDEMTableAbel

end SparkInterval.Tests.RegisteredCDEMAbelCertificate
