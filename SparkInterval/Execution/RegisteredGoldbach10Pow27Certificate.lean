/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics

/-!
# Registered trusted-compute bridge for finite Goldbach below `10^27`

This registration is intentionally separate from the historical
Helfgott--Platt source campaign. Only a receipt bound to the closed lowered
Azure CPU finalizer and exact result `true` exposes
`Goldbach10Pow27SourceSemantics.SourceClaim`.

No successful receipt is included here. The physical finalizer must replay and
bind the exact 65,536-leaf H100 aggregate and exact 7,106-range n=45 ladder
aggregate before returning `true`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def goldbach10Pow27ProductionInvocation : RegisteredInvocation :=
  .goldbach10Pow27ProductionV1

def goldbach10Pow27SuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful lowered finalizer. -/
def goldbach10Pow27ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      goldbach10Pow27ProductionInvocation &&
    certificate.resultCertificate == goldbach10Pow27SuccessOutput

end SignedResultCertificate

structure CertifiedGoldbach10Pow27
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    goldbach10Pow27ProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = goldbach10Pow27SuccessOutput
  statementResult_eq :
    certificate.statement.result = goldbach10Pow27SuccessOutput
  execution :
    AlgorithmReturned certificate.statement goldbach10Pow27SuccessOutput
  sourceClaim : Goldbach10Pow27SourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- Conditional end-to-end reduction from one accepted successful Azure CPU
finalizer receipt to the exact finite claim through `10^27`. Its sole project
axiom is `accepted_run_certificate_sound`; the binary-plus-ladder implication
is ordinary Lean. -/
theorem certifyGoldbach10Pow27
    {certificate : SignedResultCertificate}
    (hcheck : certificate.goldbach10Pow27ProductionCheck = true) :
    CertifiedGoldbach10Pow27 certificate := by
  simp only [goldbach10Pow27ProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = goldbach10Pow27SuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.goldbach10Pow27ProductionV1_sourceClaim
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
