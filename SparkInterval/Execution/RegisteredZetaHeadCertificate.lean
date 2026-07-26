/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

/-!
# Registered trusted-compute bridge for the Platt zero head through 20,000

Only a receipt bound to the closed CPU/SEV-SNP invocation and exact successful
result `true` exposes a literal 22,491-row Q128 table.  Its checked evidence
computes the exact reviewed table commitment and proves the multiplicity-
preserving source claim without assuming zero simplicity.  The registered
program may return `false`, which proves nothing.

No production receipt or generated literal table is admitted here.  The
semantic binding remains disabled until a retained run supplies the table and
the FLINT Hardy-Z/count realization fields are independently reviewed.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def plattHead2e4ProductionInvocation : RegisteredInvocation :=
  .plattHead2e4ProductionV1

def plattHead2e4SuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful Platt-head replay. -/
def plattHead2e4ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      plattHead2e4ProductionInvocation &&
    certificate.resultCertificate == plattHead2e4SuccessOutput

end SignedResultCertificate

structure CertifiedPlattHead2e4
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    plattHead2e4ProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = plattHead2e4SuccessOutput
  statementResult_eq :
    certificate.statement.result = plattHead2e4SuccessOutput
  execution :
    AlgorithmReturned certificate.statement plattHead2e4SuccessOutput
  sourceClaim :
    SparkInterval.Generated.PlattHeadQ128.table.commitment =
        RegisteredAlgorithm.plattHead2e4IncludedQ128RowsCommitment ∧
      ZetaHeadSourceSemantics.Q128SourceClaim
        SparkInterval.Generated.PlattHeadQ128.table

namespace SignedResultCertificate

/-- End-to-end conditional reduction from one accepted successful Azure CPU
receipt to a literal, commitment-checked Q128 Platt-head source claim.  Its
sole project axiom is `accepted_run_certificate_sound`; all table conversion
and multiplicity-preserving enumeration reasoning is ordinary Lean. -/
theorem certifyPlattHead2e4
    {certificate : SignedResultCertificate}
    (hcheck : certificate.plattHead2e4ProductionCheck = true) :
    CertifiedPlattHead2e4 certificate := by
  simp only [plattHead2e4ProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = plattHead2e4SuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.plattHead2e4ProductionV1_sourceClaim
      certified.run houtput
  have hexecution := certified.outcome.execution
  rw [houtput] at hexecution
  exact {
    certified := certified
    resultCertificate_eq := houtput
    statementResult_eq := certified.outcome.binding.1.trans houtput
    execution := hexecution
    sourceClaim := hsource
  }

end SignedResultCertificate

end SparkInterval.Execution
