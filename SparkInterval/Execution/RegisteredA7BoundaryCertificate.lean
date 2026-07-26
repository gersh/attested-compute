/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence

/-!
# Registered trusted-compute bridge for CH25 Lemma A.7

Only a receipt bound to the closed CPU/SEV-SNP invocation and exact successful
result `true` exposes the source-shaped rectangle-boundary claim. The
registered program may return `false`, which proves nothing. A successful
relation retains one exact checked seven-field transcript and its
`AnalyticRealization`, the explicit FLINT/Arb-to-Mathlib-zeta refinement
obligation.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def ch25A7BoundaryProductionInvocation : RegisteredInvocation :=
  .ch25A7BoundaryProductionV1

def ch25A7BoundarySuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful A.7 replay. -/
def ch25A7BoundaryProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      ch25A7BoundaryProductionInvocation &&
    certificate.resultCertificate == ch25A7BoundarySuccessOutput

end SignedResultCertificate

structure CertifiedCH25A7Boundary
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    ch25A7BoundaryProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = ch25A7BoundarySuccessOutput
  statementResult_eq :
    certificate.statement.result = ch25A7BoundarySuccessOutput
  execution :
    AlgorithmReturned certificate.statement ch25A7BoundarySuccessOutput
  sourceClaim : A7BoundarySourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- End-to-end conditional reduction from one accepted successful Azure CPU
receipt to the literal A.7 boundary proposition. Its sole project axiom is
`accepted_run_certificate_sound`; rational box arithmetic and the final norm
bound are ordinary Lean theorems. -/
theorem certifyCH25A7Boundary
    {certificate : SignedResultCertificate}
    (hcheck : certificate.ch25A7BoundaryProductionCheck = true) :
    CertifiedCH25A7Boundary certificate := by
  simp only [ch25A7BoundaryProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = ch25A7BoundarySuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim
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
