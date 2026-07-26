/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.Dirichlet.PlattTheorem71Contract

/-!
# Registered trusted-compute bridge for Platt's Dirichlet Theorem 7.1

Only a receipt bound to the closed CPU/SEV-SNP finalizer and exact successful
result `true` exposes the source-shaped two-branch theorem. The registered
program may return `false`, which proves nothing. A successful relation keeps
the complete universal even- and odd-conductor source evidence explicit.

No production source-evidence artifact or successful campaign receipt is
admitted here. The Azure semantic binding remains disabled until the full
physical campaign and its source realization have been independently reviewed.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

def plattDirichletTheorem71ProductionInvocation : RegisteredInvocation :=
  .plattDirichletTheorem71ProductionV1

def plattDirichletTheorem71SuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful Dirichlet
Theorem 7.1 finalizer. -/
def plattDirichletTheorem71ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      plattDirichletTheorem71ProductionInvocation &&
    certificate.resultCertificate == plattDirichletTheorem71SuccessOutput

end SignedResultCertificate

structure CertifiedPlattDirichletTheorem71
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    plattDirichletTheorem71ProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = plattDirichletTheorem71SuccessOutput
  statementResult_eq :
    certificate.statement.result = plattDirichletTheorem71SuccessOutput
  execution :
    AlgorithmReturned certificate.statement plattDirichletTheorem71SuccessOutput
  sourceClaim : SparkInterval.Dirichlet.PlattTheorem71DirichletVerification

namespace SignedResultCertificate

/-- End-to-end conditional reduction from one accepted successful Azure CPU
finalizer receipt to the exact two-branch Platt Theorem 7.1 source proposition.
Its sole project axiom is `accepted_run_certificate_sound`; the source
specialization is an ordinary Lean theorem. -/
theorem certifyPlattDirichletTheorem71
    {certificate : SignedResultCertificate}
    (hcheck : certificate.plattDirichletTheorem71ProductionCheck = true) :
    CertifiedPlattDirichletTheorem71 certificate := by
  simp only [plattDirichletTheorem71ProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = plattDirichletTheorem71SuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.plattDirichletTheorem71ProductionV1_sourceClaim
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
