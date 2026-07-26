/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition

/-!
# Generic registered-campaign certificate layer

Every per-campaign trusted-compute bridge in this directory used to repeat the
same three declarations: a fail-closed application check, a `Certified…`
structure holding the same four shared conclusions, and a soundness theorem
whose proof was a transcription of the same six tactic steps.  Adding a
campaign therefore meant writing a new proof.

This module states that shape once.  A campaign is now *data*: an invocation,
an expected output string, and (optionally) the registered success reduction
that turns the invocation's `Runs` relation into the campaign's source
proposition.  Nothing here weakens any check — `productionCheck` is literally
the conjunction the per-campaign checks already used, and `CertifiedRun`
carries literally the four conclusions the per-campaign structures already
carried.

Three shapes are supported, covering all registered campaigns:

* `productionCheck` / `CertifiedRun` / `certifyRun` — the exact-output shape
  used by twelve campaigns (`"true"`, or an exact decimal payload);
* `certifyDerivedRun` — campaigns whose registered `Runs` relation already
  pins the exact output, so the application check needs no textual
  expectation (the tutorial cubic sum);
* `nonFailureProductionCheck` / `CertifiedNonFailureRun` /
  `certifyNonFailureRun` — campaigns that accept any non-failure output
  satisfying an extra decidable result predicate (fixed-width Sqrt218 V2).

The single project axiom on every path below is the repository's
`accepted_run_certificate_sound` boundary, reached only through
`outcomeCheckForRegisteredInvocation_sound`.  This module adds no axiom, no
`native_decide`, and no `sorry`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

namespace SignedResultCertificate

/-- Generic fail-closed production application check: the closed registered
invocation is bound, the receipt is accepted, the returned bytes and their
digest are bound to the statement, and the returned bytes are exactly
`expected`.

This is the shared body of every per-campaign `…ProductionCheck`. -/
def productionCheck (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (expected : String) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation invocation &&
    certificate.resultCertificate == expected

/-- Generic fail-closed check for campaigns that accept any non-failure
output passing an extra decidable result predicate. -/
def nonFailureProductionCheck (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (accepted : String → Bool) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation invocation &&
    (certificate.resultCertificate != "false" &&
      accepted certificate.resultCertificate)

end SignedResultCertificate

/-- The four conclusions shared by every exact-output registered campaign.

Stated once here instead of once per campaign. -/
structure CertifiedRun (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (expected : String) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation invocation
  resultCertificate_eq : certificate.resultCertificate = expected
  statementResult_eq : certificate.statement.result = expected
  execution : AlgorithmReturned certificate.statement expected

/-- The shared conclusions for a non-failure campaign.  The exact returned
bytes are not pinned to a literal, so the equalities are stated against
`certificate.resultCertificate` itself. -/
structure CertifiedNonFailureRun (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (accepted : String → Bool) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation invocation
  nonFailure : certificate.resultCertificate ≠ "false"
  acceptedResult : accepted certificate.resultCertificate = true
  execution : AlgorithmReturned certificate.statement certificate.resultCertificate

/-- A complete new campaign in one declaration: the four shared conclusions
plus the campaign's own source proposition.  A campaign that needs nothing
beyond a single source claim can be introduced as an `abbrev` of this and
never has to state a structure or write a proof. -/
structure CertifiedSourceRun (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) (expected : String)
    (claim : Prop) : Prop extends CertifiedRun certificate invocation expected where
  sourceClaim : claim

namespace SignedResultCertificate

/-- The generic soundness theorem, proved once.

An accepted receipt bound to the closed invocation whose returned bytes are
exactly `expected` yields the registered `Runs` relation at `expected`, the
exact result/statement equalities, and the fixed formal execution relation.

Its only project axiom is `accepted_run_certificate_sound`. -/
theorem certifyRun {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation} {expected : String}
    (hcheck : certificate.productionCheck invocation expected = true) :
    CertifiedRun certificate invocation expected := by
  simp only [productionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput : certificate.resultCertificate = expected := by
    simpa using hcheck.2
  have hexecution := certified.outcome.execution
  rw [houtput] at hexecution
  exact {
    certified := certified
    resultCertificate_eq := houtput
    statementResult_eq := certified.outcome.binding.1.trans houtput
    execution := hexecution
  }

/-- The same four conclusions for a campaign whose registered `Runs` relation
already determines the exact output, so the application check carries no
textual expectation.

Its only project axiom is `accepted_run_certificate_sound`. -/
theorem certifyDerivedRun {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation} {expected : String}
    (outputOf : ∀ {output : String}, invocation.Runs output → output = expected)
    (hcheck :
      certificate.outcomeCheckForRegisteredInvocation invocation = true) :
    CertifiedRun certificate invocation expected := by
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck
  have houtput : certificate.resultCertificate = expected := outputOf certified.run
  have hexecution := certified.outcome.execution
  rw [houtput] at hexecution
  exact {
    certified := certified
    resultCertificate_eq := houtput
    statementResult_eq := certified.outcome.binding.1.trans houtput
    execution := hexecution
  }

/-- The generic non-failure soundness theorem, proved once.

Its only project axiom is `accepted_run_certificate_sound`. -/
theorem certifyNonFailureRun {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation} {accepted : String → Bool}
    (hcheck :
      certificate.nonFailureProductionCheck invocation accepted = true) :
    CertifiedNonFailureRun certificate invocation accepted := by
  simp only [nonFailureProductionCheck, Bool.and_eq_true] at hcheck
  exact {
    certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
    nonFailure := by simpa using hcheck.2.1
    acceptedResult := hcheck.2.2
    execution := (outcomeCheckForRegisteredInvocation_sound hcheck.1).outcome.execution
  }

/-- Declarative source campaign: supply the registered success reduction and
the checked receipt, and get the complete campaign conclusion.  No proof
obligation is created at the campaign site. -/
theorem certifySourceRun {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation} {expected : String} {claim : Prop}
    (reduce : ∀ {output : String}, invocation.Runs output → output = expected → claim)
    (hcheck : certificate.productionCheck invocation expected = true) :
    CertifiedSourceRun certificate invocation expected claim :=
  let run := certifyRun hcheck
  { run with sourceClaim := reduce run.certified.run run.resultCertificate_eq }

end SignedResultCertificate

namespace CertifiedRun

variable {certificate : SignedResultCertificate}
  {invocation : RegisteredInvocation} {expected : String}

/-- Apply any registered success reduction whose conclusion does not mention
the returned output.  This is the single line every source-claim campaign
needs.

A reduction whose conclusion *does* mention the output (the CDEM numerator
encoding, the fixed-V2 success relation) is applied directly to
`run.certified.run` instead; no combinator can carry the motive for it
without higher-order unification guesswork. -/
theorem claim (run : CertifiedRun certificate invocation expected) {P : Prop}
    (reduce : ∀ {output : String}, invocation.Runs output → output = expected → P) :
    P :=
  reduce run.certified.run run.resultCertificate_eq

/-- A campaign whose expected output is not the failure token proves that the
receipt is not a failure receipt. -/
theorem nonFailure (run : CertifiedRun certificate invocation expected)
    (hexpected : expected ≠ "false") :
    certificate.resultCertificate ≠ "false" := fun hfailure =>
  hexpected (run.resultCertificate_eq.symm.trans hfailure)

end CertifiedRun

namespace CertifiedNonFailureRun

variable {certificate : SignedResultCertificate}
  {invocation : RegisteredInvocation} {accepted : String → Bool}

/-- Apply any registered success reduction stated against non-failure. -/
theorem claim (run : CertifiedNonFailureRun certificate invocation accepted)
    {P : Prop}
    (reduce : ∀ {output : String}, invocation.Runs output → output ≠ "false" → P) :
    P :=
  reduce run.certified.run run.nonFailure

end CertifiedNonFailureRun

/-- The success token used by every boolean-result campaign is not the failure
token.  Supplied here so no campaign has to restate it. -/
theorem success_ne_failure : ("true" : String) ≠ "false" := by decide

end SparkInterval.Execution
