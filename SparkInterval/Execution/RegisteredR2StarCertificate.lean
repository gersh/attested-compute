/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.R2StarSourceSemantics

/-!
# Registered trusted-compute bridge for Ramaré--Zúñiga Lemma 6.2

Only a receipt bound to the closed source-scale H100 invocation and the exact
success result `true` exposes the paper-shaped `R₂*` claim.  The registered
program may return `false`, which proves nothing.  The success relation keeps
the recurrence-to-Mathlib coefficient realization explicit in
`SourceScaleEvidence`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def ramareZunigaLemma62ProductionInvocation : RegisteredInvocation :=
  .ramareZunigaLemma62ProductionV1

def ramareZunigaLemma62SuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful source campaign. -/
def ramareZunigaLemma62ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      ramareZunigaLemma62ProductionInvocation &&
    certificate.resultCertificate == ramareZunigaLemma62SuccessOutput

end SignedResultCertificate

structure CertifiedRamareZunigaLemma62
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    ramareZunigaLemma62ProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = ramareZunigaLemma62SuccessOutput
  statementResult_eq :
    certificate.statement.result = ramareZunigaLemma62SuccessOutput
  execution :
    AlgorithmReturned certificate.statement ramareZunigaLemma62SuccessOutput
  sourceClaim : R2StarSourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- End-to-end reduction from one accepted successful H100 receipt to the
literal real-variable Lemma 6.2 proposition.  Its only project axiom is
`accepted_run_certificate_sound`; interval composition, endpoint arithmetic,
and the real-floor reduction are ordinary Lean theorems. -/
theorem certifyRamareZunigaLemma62
    {certificate : SignedResultCertificate}
    (hcheck : certificate.ramareZunigaLemma62ProductionCheck = true) :
    CertifiedRamareZunigaLemma62 certificate := by
  simp only [ramareZunigaLemma62ProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = ramareZunigaLemma62SuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.ramareZunigaLemma62ProductionV1_sourceClaim
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

