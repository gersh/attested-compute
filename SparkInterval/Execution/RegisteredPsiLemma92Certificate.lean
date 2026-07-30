/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredCampaignCertificate
import SparkInterval.TernaryGoldbach.PsiSourceSemantics

/-!
# Registered trusted-compute bridge for CH25 Lemma 9.2

Only a receipt bound to the closed source-scale CPU invocation and the exact
success result `true` exposes the paper-shaped real Chebyshev-psi claim.  The
registered program may honestly return `false`; that output proves nothing.

This campaign is an instantiation of the generic layer in
`SparkInterval.Execution.RegisteredCampaignCertificate`: the check is
`productionCheck` at this invocation and output, and the shared conclusions
come from `certifyRun`.  Only the campaign-specific `sourceClaim` field is
named here.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

def ch25PsiLemma92ProductionInvocation : RegisteredInvocation :=
  .ch25PsiLemma92ProductionV1

def ch25PsiLemma92SuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful source campaign. -/
def ch25PsiLemma92ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.productionCheck ch25PsiLemma92ProductionInvocation
    ch25PsiLemma92SuccessOutput

end SignedResultCertificate

structure CertifiedPsiLemma92
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    ch25PsiLemma92ProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = ch25PsiLemma92SuccessOutput
  statementResult_eq :
    certificate.statement.result = ch25PsiLemma92SuccessOutput
  execution :
    AlgorithmReturned certificate.statement ch25PsiLemma92SuccessOutput
  sourceClaim :
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- End-to-end reduction from one accepted successful source receipt to the
exact normalized real-variable CH25 Lemma 9.2 proposition.  Its only project
axiom is `accepted_run_certificate_sound`; all Q64 and slab arithmetic is an
ordinary Lean theorem. -/
theorem certifyCH25PsiLemma92
    {certificate : SignedResultCertificate}
    (hcheck : certificate.ch25PsiLemma92ProductionCheck = true) :
    CertifiedPsiLemma92 certificate :=
  let run : CertifiedRun certificate ch25PsiLemma92ProductionInvocation
      ch25PsiLemma92SuccessOutput := certifyRun hcheck
  { certified := run.certified
    resultCertificate_eq := run.resultCertificate_eq
    statementResult_eq := run.statementResult_eq
    execution := run.execution
    sourceClaim := run.claim RegisteredInvocation.ch25PsiLemma92ProductionV1_sourceClaim }

end SignedResultCertificate

end SparkInterval.Execution
