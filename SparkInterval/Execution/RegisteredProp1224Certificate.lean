/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.Prop1224SourceSemantics

/-!
# Registered trusted-compute bridge for Helfgott Proposition 12.2.4

Only a receipt bound to the closed CPU/SEV-SNP invocation and the exact
success result `true` exposes the source-shaped finite-computation claim.  The
registered program may return `false`, which proves nothing.  A successful
relation retains the external MPFR/GMP-to-exact-real realization explicitly
in `SourceScaleEvidence`; neither a shard hash nor a reported margin creates
that evidence.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def helfgottProp1224ProductionInvocation : RegisteredInvocation :=
  .helfgottProp1224ProductionV1

def helfgottProp1224SuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful source campaign. -/
def helfgottProp1224ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      helfgottProp1224ProductionInvocation &&
    certificate.resultCertificate == helfgottProp1224SuccessOutput

end SignedResultCertificate

structure CertifiedHelfgottProp1224
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    helfgottProp1224ProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = helfgottProp1224SuccessOutput
  statementResult_eq :
    certificate.statement.result = helfgottProp1224SuccessOutput
  execution :
    AlgorithmReturned certificate.statement helfgottProp1224SuccessOutput
  sourceClaim : Prop1224SourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- End-to-end conditional reduction from one accepted successful Azure CPU
receipt to the literal finite-computation proposition.  Its sole project
axiom is `accepted_run_certificate_sound`; scheduler coverage and the
source-shaped reduction are ordinary Lean theorems. -/
theorem certifyHelfgottProp1224
    {certificate : SignedResultCertificate}
    (hcheck : certificate.helfgottProp1224ProductionCheck = true) :
    CertifiedHelfgottProp1224 certificate := by
  simp only [helfgottProp1224ProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = helfgottProp1224SuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.helfgottProp1224ProductionV1_sourceClaim
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
