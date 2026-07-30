/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredCampaignCertificate
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Run
import SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics
import TGComputeContracts.Sqrt218.Sound

/-!
# Registered trusted-compute bridge for Helfgott (2.18)

Only a receipt bound to the closed Azure CPU/SEV-SNP invocation and the exact
success result `true` exposes the finite head-and-anchor source claim.  The
registered `Runs` relation now requires an existential typed archive for which
the exact production-profile `Sqrt218Operational.run` equation is true.
Ordinary Lean then applies `run_success_sound` and the package-neutral
`CertificateFacts.sourceClaim`; neither theorem evaluates a production
archive.

The sole run axiom still supplies the link from accepted measured bytes and
execution to that existential typed operational success.  The data-independent
`Sqrt218Operational.decodeCanonicalArchiveBytes` now proves strict canonical
V1 JSON decoding, including `kind`, exact fields, and exact EOF, but it is not
yet composed with the receipt artifact digest or this registered success
relation.  There is likewise no native compiler/ISA refinement, and
attestation alone does not establish either connection.  Those gaps remain
inside the disclosed execution boundary; adding the decoder did not narrow the
sole axiom.  The mathematical archive-to-source reduction is no longer
asserted there.  In particular, the receipt edge exposes only full
`Sqrt218Operational.run` success, never the weaker streaming-scan facts alone.

The production deployment pin remains `none` until a real run, hardware
evidence, artifacts, and receipt have been reviewed.  Consequently this module
creates no successful certificate by itself and never runs the production
scan during an ordinary Lean build.

The sole execution trust used by the conditional theorem below is the
project-wide `accepted_run_certificate_sound` axiom reached through
`outcomeCheckForRegisteredInvocation_sound`.

This campaign is an instantiation of the generic layer in
`SparkInterval.Execution.RegisteredCampaignCertificate`: the check is
`productionCheck` at this invocation and output, and the shared conclusions
come from `certifyRun`.  Only the campaign-specific `sourceClaim` field is
named here.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def helfgottSqrt218ProductionInvocation : RegisteredInvocation :=
  .helfgottSqrt218ProductionV1

def helfgottSqrt218SuccessOutput : String := "true"

namespace RegisteredInvocation

/-- A successful typed operational replay yields exactly the two finite source
inequalities.  This reduction is data-independent and axiom-free. -/
theorem helfgottSqrt218ProductionV1_sourceClaim
    {output : String}
    (run : RegisteredInvocation.helfgottSqrt218ProductionV1.Runs output)
    (houtput : output = helfgottSqrt218SuccessOutput) :
    Sqrt218SourceSemantics.SourceClaim := by
  obtain ⟨archive, harchive⟩ :=
    helfgottSqrt218ProductionV1_operationalSuccess run houtput
  exact
    (Sqrt218Operational.run_success_sound harchive).certificate.sourceClaim

end RegisteredInvocation

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful Sqrt218 replay. -/
def helfgottSqrt218ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.productionCheck helfgottSqrt218ProductionInvocation
    helfgottSqrt218SuccessOutput

end SignedResultCertificate

/-- The full result exposed by one successfully checked production receipt. -/
structure CertifiedHelfgottSqrt218
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    helfgottSqrt218ProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = helfgottSqrt218SuccessOutput
  statementResult_eq :
    certificate.statement.result = helfgottSqrt218SuccessOutput
  execution :
    AlgorithmReturned certificate.statement helfgottSqrt218SuccessOutput
  sourceClaim : Sqrt218SourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- Conditional reduction from one accepted successful measured replay to the
exact finite proposition consumed downstream.  With the production deployment
pin disabled, no certificate can satisfy the premise. -/
theorem certifyHelfgottSqrt218
    {certificate : SignedResultCertificate}
    (hcheck : certificate.helfgottSqrt218ProductionCheck = true) :
    CertifiedHelfgottSqrt218 certificate :=
  let run : CertifiedRun certificate helfgottSqrt218ProductionInvocation
      helfgottSqrt218SuccessOutput := certifyRun hcheck
  { certified := run.certified
    resultCertificate_eq := run.resultCertificate_eq
    statementResult_eq := run.statementResult_eq
    execution := run.execution
    sourceClaim := run.claim RegisteredInvocation.helfgottSqrt218ProductionV1_sourceClaim }

end SignedResultCertificate

end SparkInterval.Execution
