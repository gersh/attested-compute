/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredCampaignCertificate
import SparkInterval.Execution.RegisteredA7BoundaryCertificate
import SparkInterval.Execution.RegisteredCDEMAbelCertificate
import SparkInterval.Execution.RegisteredSqrt218FixedV2Certificate

/-!
# Tests for the generic registered-campaign certificate layer

Three things are checked here.

1. **No check was weakened.**  Every per-campaign `…ProductionCheck` is
   definitionally the generic `productionCheck` at that campaign's invocation
   and output (`rfl`), and the generic check is evaluated on crafted bad
   certificates — wrong invocation, wrong output, `"false"` output — where it
   must return `false`.
2. **The generic layer adds no axiom.**  `#print axioms` for `certifyRun`,
   `certifyDerivedRun`, `certifyNonFailureRun`, and `certifySourceRun`.
3. **New-campaign ergonomics.**  A complete throwaway example campaign is
   declared at the bottom of this file with no tactic proof at all.  It is an
   example only: it is not exported, not registered in the campaign matrix,
   and creates no production claim.

No receipt is installed and no campaign is executed by this module.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredCampaignCertificate

open SparkInterval.Execution
open SparkInterval.Execution.SignedResultCertificate

/-! ## The per-campaign checks are the generic check, unchanged -/

example (certificate : SignedResultCertificate) :
    certificate.ch25A7BoundaryProductionCheck =
      certificate.productionCheck ch25A7BoundaryProductionInvocation
        ch25A7BoundarySuccessOutput := rfl

example (certificate : SignedResultCertificate) :
    certificate.cdemTableAbelProductionCheck =
      certificate.productionCheck cdemTableAbelProductionInvocation
        cdemTableAbelProductionOutput := rfl

example (certificate : SignedResultCertificate) :
    certificate.helfgottSqrt218FixedV2ProductionCheck =
      certificate.nonFailureProductionCheck
        helfgottSqrt218FixedV2ProductionInvocation
        RegisteredInvocation.sqrt218FixedV2AcceptedResultCheck := rfl

/-! ## Crafted bad certificates are rejected

The generic check is a conjunction, so it is `false` as soon as any conjunct
is.  These are proved by `Bool` reasoning on the shape, not by evaluating a
receipt: no receipt exists. -/

/-- Wrong returned output ⇒ the generic check is `false`, whatever the
receipt says. -/
theorem productionCheck_eq_false_of_output_ne
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (expected : String)
    (hne : certificate.resultCertificate ≠ expected) :
    certificate.productionCheck invocation expected = false := by
  simp [productionCheck, hne]

/-- A failure receipt (`"false"`) can never satisfy a success campaign. -/
theorem productionCheck_eq_false_of_failure_output
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (expected : String)
    (hfailure : certificate.resultCertificate = "false")
    (hexpected : expected ≠ "false") :
    certificate.productionCheck invocation expected = false :=
  productionCheck_eq_false_of_output_ne certificate invocation expected
    (fun h => hexpected (h.symm.trans hfailure))

/-- A receipt not bound to the campaign's closed invocation is rejected even
when the returned bytes are exactly right. -/
theorem productionCheck_eq_false_of_unbound_invocation
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (expected : String)
    (hunbound :
      certificate.outcomeCheckForRegisteredInvocation invocation = false) :
    certificate.productionCheck invocation expected = false := by
  simp [productionCheck, hunbound]

/-- The non-failure check likewise rejects a `"false"` result. -/
theorem nonFailureProductionCheck_eq_false_of_failure_output
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (accepted : String → Bool)
    (hfailure : certificate.resultCertificate = "false") :
    certificate.nonFailureProductionCheck invocation accepted = false := by
  simp [nonFailureProductionCheck, hfailure]

/-- The non-failure check rejects a non-failure result that fails the
campaign's extra accepted-result predicate. -/
theorem nonFailureProductionCheck_eq_false_of_unaccepted
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (accepted : String → Bool)
    (hrejected : accepted certificate.resultCertificate = false) :
    certificate.nonFailureProductionCheck invocation accepted = false := by
  simp [nonFailureProductionCheck, hrejected]

/-! ## The generic layer adds no axiom -/

#print axioms SignedResultCertificate.certifyRun
#print axioms SignedResultCertificate.certifyDerivedRun
#print axioms SignedResultCertificate.certifyNonFailureRun
#print axioms SignedResultCertificate.certifySourceRun

/-! ## Example: a complete new campaign, declared rather than proved

This is an EXAMPLE ONLY.  It reuses an existing closed invocation purely so
the example elaborates; it registers nothing, is not in the campaign matrix,
and asserts no production claim.  What it demonstrates is the cost of adding
a campaign on top of the generic layer: three `def`/`abbrev` lines of data
and one `:=` line with no tactic block. -/

namespace ExampleCampaign

/-- Data (1/3): which closed registered invocation. -/
def exampleInvocation : RegisteredInvocation := .ch25A7BoundaryProductionV1

/-- Data (2/3): which exact returned bytes count as success. -/
def exampleSuccessOutput : String := "true"

/-- Data (3/3): what the campaign concludes, and the complete conclusion
type -- no structure declaration is needed. -/
abbrev CertifiedExample (certificate : SignedResultCertificate) : Prop :=
  CertifiedSourceRun certificate exampleInvocation exampleSuccessOutput
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim

/-- The campaign's fail-closed application check.  (A real campaign puts this
in `SparkInterval.Execution.SignedResultCertificate` so it is reachable by dot
notation; the example keeps it local so it exports nothing.) -/
def exampleProductionCheck (certificate : SignedResultCertificate) : Bool :=
  certificate.productionCheck exampleInvocation exampleSuccessOutput

/-- The campaign's end-to-end theorem.  No tactic proof: the reduction is
supplied as data and everything else is the generic `certifySourceRun`. -/
theorem certifyExample {certificate : SignedResultCertificate}
    (hcheck : exampleProductionCheck certificate = true) :
    CertifiedExample certificate :=
  certifySourceRun RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim
    hcheck

-- The example campaign crosses exactly the same single project axiom as
-- every real campaign.
#print axioms certifyExample

end ExampleCampaign

end SparkInterval.Tests.RegisteredCampaignCertificate
