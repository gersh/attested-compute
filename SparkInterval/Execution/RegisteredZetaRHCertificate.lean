/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics

/-!
# Registered trusted-compute bridge for Platt--Trudgian finite RH

Only a receipt bound to the closed CPU/SEV-SNP invocation and exact successful
result `true` exposes the source-shaped finite-RH claim. The registered program
may return `false`, which proves nothing. A successful relation retains the
chunked endpoint, Hardy-Z, and global-count evidence required by the ordinary
Lean theorem.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def plattTrudgianFiniteRHProductionInvocation : RegisteredInvocation :=
  .plattTrudgianFiniteRHProductionV1

def plattTrudgianFiniteRHSuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful PT21 campaign. -/
def plattTrudgianFiniteRHProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      plattTrudgianFiniteRHProductionInvocation &&
    certificate.resultCertificate == plattTrudgianFiniteRHSuccessOutput

end SignedResultCertificate

structure CertifiedPlattTrudgianFiniteRH
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    plattTrudgianFiniteRHProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = plattTrudgianFiniteRHSuccessOutput
  statementResult_eq :
    certificate.statement.result = plattTrudgianFiniteRHSuccessOutput
  execution :
    AlgorithmReturned certificate.statement plattTrudgianFiniteRHSuccessOutput
  sourceClaim : ZetaRHSourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- End-to-end conditional reduction from one accepted successful Azure CPU
receipt to the exact PT21 finite-RH source proposition. Its sole project axiom
is `accepted_run_certificate_sound`; the source specialization is an ordinary
Lean theorem. -/
theorem certifyPlattTrudgianFiniteRH
    {certificate : SignedResultCertificate}
    (hcheck : certificate.plattTrudgianFiniteRHProductionCheck = true) :
    CertifiedPlattTrudgianFiniteRH certificate := by
  simp only [plattTrudgianFiniteRHProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = plattTrudgianFiniteRHSuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.plattTrudgianFiniteRHProductionV1_sourceClaim
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
