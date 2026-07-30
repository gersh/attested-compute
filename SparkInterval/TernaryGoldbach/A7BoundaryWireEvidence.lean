/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence
import SparkInterval.TernaryGoldbach.A7BoundaryWire

/-!
# Reference semantics of the A.7 boundary checker, and its proved consequences

`A7BoundaryWire.checkBytes` is a **total** `ByteArray → Bool`.  This module
gives it the role it should have had all along: it is the *reference
semantics* of the external A.7 boundary checker.  Everything the external
program is allowed to be believed about is spelled out here as a function of
the exact bytes it consumes and the exact bytes it emits.

## The model

`modelOutput : ByteArray → String` is the complete input/output behaviour of
the reference checker: it consumes one `TGA7WIR1` artifact and emits either
the four bytes `true` or the five bytes `false`.  It is total, it is
`decide`-checkable, it uses no `native_decide`, and it is the same source text
that `sparkinterval-check-a7-wire` compiles.

## What is proved here, with no axioms at all

* `successEvidence_of_modelOutput`: if the model emits `true` on some bytes,
  and the analytic realization premise holds for the certificate those bytes
  decode to, then `A7BoundarySuccessEvidence.SuccessEvidence` holds.
* `sourceClaim_of_modelOutput`: hence `A7BoundarySourceSemantics.SourceClaim`,
  through the already-proved `sourceClaim_of_successEvidence`.

The combinatorial half of `SuccessEvidence` -- the existence of a transcript
passing `Certificate.check` -- is therefore a **theorem about bytes**, not
something a receipt has to assert.

## What is *not* proved here, and cannot be

`SuccessEvidence` also contains `Nonempty (AnalyticRealization certificate)`:
the statement that each recorded FLINT/Arb box really encloses Mathlib's
`riemannZeta` and `rawG` on the corresponding segment.  No decision procedure
over bytes can imply that, because the bytes do not mention `riemannZeta`.  It
is therefore carried explicitly as `RetainedAnalyticRealization`, a named
hypothesis -- never an axiom -- so that every theorem which needs it says so
in its own statement.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.A7BoundaryWireEvidence

open A7BoundaryCertificate
open A7BoundaryWire

/-! ## The reference semantics -/

/-- Emitted bytes of the reference A.7 boundary checker on artifact bytes
`raw`.

This is the complete externally visible behaviour of the checker: consume one
`TGA7WIR1` artifact, emit `true` or `false`.  `checkRetainedBytes` additionally
pins the retained source transcript, canonical leaf array, record payload, and
whole-wire SHA-256 identities, so `modelOutput raw = "true"` is only reachable
for the one reviewed artifact. -/
def modelOutput (raw : ByteArray) : String :=
  if checkRetainedBytes raw then "true" else "false"

/-- The model emits only the two canonical verdicts. -/
theorem modelOutput_mem (raw : ByteArray) :
    modelOutput raw = "true" ∨ modelOutput raw = "false" := by
  unfold modelOutput
  split
  · exact Or.inl rfl
  · exact Or.inr rfl

/-- Emitting `true` is exactly acceptance by the total finite checker. -/
theorem modelOutput_eq_true_iff (raw : ByteArray) :
    modelOutput raw = "true" ↔ checkRetainedBytes raw = true := by
  unfold modelOutput
  constructor
  · intro hmodel
    by_cases hcheck : checkRetainedBytes raw = true
    · exact hcheck
    · rw [Bool.not_eq_true] at hcheck
      rw [hcheck] at hmodel
      simp at hmodel
  · intro hcheck
    rw [hcheck]
    rfl

/-! ## The one analytic premise -/

/-- **The FLINT/Arb-to-Mathlib realization premise, for the pinned artifact
only.**

`RetainedPins` fixes the SHA-256 of the whole wire, so the quantifier ranges
over (at most) the single reviewed byte string and the single certificate it
decodes to.  Widening this to arbitrary bytes would be a much stronger and
false claim.

This is a `def`, used as an explicit hypothesis.  It is deliberately not an
axiom: it is the mathematical content that the external FLINT/Arb replay is
evidence for, and it must remain visible in the statement of every theorem
that consumes it. -/
def RetainedAnalyticRealization : Prop :=
  ∀ (raw : ByteArray) (artifact : Artifact),
    parse raw = some artifact →
      RetainedPins raw artifact →
        Nonempty (AnalyticRealization artifact.certificate)

/-! ## Proved consequences -/

/-- Accepted retained bytes plus the analytic premise give the exact success
evidence the registered A.7 relation asks for.

Axioms: the base trio only. -/
theorem successEvidence_of_checkRetainedBytes {raw : ByteArray}
    (hcheck : checkRetainedBytes raw = true)
    (realization : RetainedAnalyticRealization) :
    A7BoundarySuccessEvidence.SuccessEvidence := by
  obtain ⟨artifact, hparse, haccepted, hpins⟩ := checkRetainedBytes_sound hcheck
  exact ⟨artifact.certificate, haccepted.2.2, realization raw artifact hparse hpins⟩

/-- The requested chain, stated over the emitted bytes: reference model emits
`true` implies the registered success evidence.

Axioms: the base trio only. -/
theorem successEvidence_of_modelOutput {raw : ByteArray}
    (hmodel : modelOutput raw = "true")
    (realization : RetainedAnalyticRealization) :
    A7BoundarySuccessEvidence.SuccessEvidence :=
  successEvidence_of_checkRetainedBytes
    ((modelOutput_eq_true_iff raw).mp hmodel) realization

/-- End of the chain: reference model emits `true` implies the literal CH25
Lemma A.7 source claim.

Axioms: the base trio only. -/
theorem sourceClaim_of_modelOutput {raw : ByteArray}
    (hmodel : modelOutput raw = "true")
    (realization : RetainedAnalyticRealization) :
    A7BoundarySourceSemantics.SourceClaim :=
  A7BoundarySuccessEvidence.sourceClaim_of_successEvidence
    (successEvidence_of_modelOutput hmodel realization)

/-- The finite half alone, with no analytic premise: accepted retained bytes
decode to a certificate that really is `Certificate.Accepted`.

This is the part a byte-level checker can honestly establish. -/
theorem accepted_of_checkRetainedBytes {raw : ByteArray}
    (hcheck : checkRetainedBytes raw = true) :
    ∃ artifact : Artifact,
      parse raw = some artifact ∧
        RetainedPins raw artifact ∧
        artifact.certificate.Accepted := by
  obtain ⟨artifact, hparse, haccepted, hpins⟩ := checkRetainedBytes_sound hcheck
  exact
    ⟨artifact, hparse, hpins,
      Certificate.accepted_of_check_eq_true haccepted.2.2⟩

end SparkInterval.TernaryGoldbach.A7BoundaryWireEvidence
