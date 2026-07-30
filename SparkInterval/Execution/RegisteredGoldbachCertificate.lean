/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredCampaignCertificate
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

This campaign is an instantiation of the generic layer in
`SparkInterval.Execution.RegisteredCampaignCertificate`: the check is
`productionCheck` at this invocation and output, and the shared conclusions
come from `certifyRun`.  Only the campaign-specific `sourceClaim` field is
named here.
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
  certificate.productionCheck helfgottPlattGoldbachProductionInvocation
    helfgottPlattGoldbachSuccessOutput

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
    CertifiedHelfgottPlattGoldbach certificate :=
  let run : CertifiedRun certificate helfgottPlattGoldbachProductionInvocation
      helfgottPlattGoldbachSuccessOutput := certifyRun hcheck
  { certified := run.certified
    resultCertificate_eq := run.resultCertificate_eq
    statementResult_eq := run.statementResult_eq
    execution := run.execution
    sourceClaim := run.claim RegisteredInvocation.helfgottPlattGoldbachProductionV1_sourceClaim }

end SignedResultCertificate

end SparkInterval.Execution
