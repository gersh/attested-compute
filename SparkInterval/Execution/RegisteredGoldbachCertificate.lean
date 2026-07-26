/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.GoldbachSourceSemantics

/-!
# Registered trusted-compute bridge for finite Helfgott--Platt Goldbach

Only a receipt bound to the closed Azure CPU finalizer and exact successful
result `true` exposes the source-shaped finite three-prime claim. The finalizer
identity pins the H100 binary and CPU prime-ladder campaign and artifact
formats. A successful relation retains the exact `CheckedSourceEvidence`;
`false` proves nothing.

No successful receipt is included here. In particular, the present formal
relation does not independently expose the transitive attestation chain from
the final CPU receipt to both branch receipts; that remains an explicit
deployment/materializer obligation while the Azure semantic binding is off.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def helfgottPlattGoldbachProductionInvocation : RegisteredInvocation :=
  .helfgottPlattGoldbachProductionV1

def helfgottPlattGoldbachSuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful CPU finalizer. -/
def helfgottPlattGoldbachProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      helfgottPlattGoldbachProductionInvocation &&
    certificate.resultCertificate == helfgottPlattGoldbachSuccessOutput

end SignedResultCertificate

structure CertifiedHelfgottPlattGoldbach
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    helfgottPlattGoldbachProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = helfgottPlattGoldbachSuccessOutput
  statementResult_eq :
    certificate.statement.result = helfgottPlattGoldbachSuccessOutput
  execution :
    AlgorithmReturned certificate.statement helfgottPlattGoldbachSuccessOutput
  sourceClaim : GoldbachSourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- End-to-end conditional reduction from one accepted successful Azure CPU
finalizer receipt to the exact finite Helfgott--Platt source proposition. Its
sole project axiom is `accepted_run_certificate_sound`; the binary-plus-ladder
reduction is ordinary Lean. -/
theorem certifyHelfgottPlattGoldbach
    {certificate : SignedResultCertificate}
    (hcheck : certificate.helfgottPlattGoldbachProductionCheck = true) :
    CertifiedHelfgottPlattGoldbach certificate := by
  simp only [helfgottPlattGoldbachProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = helfgottPlattGoldbachSuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.helfgottPlattGoldbachProductionV1_sourceClaim
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
