/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.Verifier
import SparkInterval.Dirichlet.FactoredSmallQSourceRealization

/-!
# Closing per-character counts from one aggregate Turing equality

This file isolates the elementary arithmetic step used by a source-scale
Dirichlet campaign.  For every character, the zero-isolation checker must
prove that its certified strict-sign-bracket count is a lower bound for the
multiplicity-counted zero count supplied by the analytic Turing theorem.  If
the two totals over the same finite character roster are equal, every
pointwise inequality is an equality.

The result permits a streamed campaign to retain one exact aggregate count
per modulus instead of an expected count for every character.  It does **not**
provide either analytic premise: the production bridge must still prove the
per-character lower bounds, the exact Turing total, that a
multiplicity-counted Turing upper bound is also a safe upper bound on distinct
zero locations, and that both sides use the identical complete roster.

The endpoint theorem below uses `RationalBracketFamily`, hence only strict
sign changes.  It does not silently add stationary-zero events.  If equality
with a multiplicity count holds, it may in particular force simplicity in the
checked region; no simplicity hypothesis is used.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.Dirichlet

open scoped BigOperators

namespace FactoredSmallQSourceRealization.PrimitiveRosterRealization

variable {N : Nat} [NeZero N] {ids : List Nat}

/-- The existing source-roster realization is an actual equivalence between
listed opaque identifiers and mathematical primitive characters. -/
def characterEquiv
    (realization :
      FactoredSmallQSourceRealization.PrimitiveRosterRealization N ids) :
    {id : Nat // id ∈ ids} ≃
      {chi : DirichletCharacter Complex N // chi.IsPrimitive} :=
  Equiv.ofBijective
    (fun id =>
      ⟨realization.characterOf id,
        realization.primitive_of_mem id id.property⟩)
    (by
      constructor
      · intro left right heq
        apply Subtype.ext
        have hcharacters :
            realization.characterOf left =
              realization.characterOf right :=
          congrArg Subtype.val heq
        rcases realization.complete_unique
            (realization.characterOf left)
            (realization.primitive_of_mem left left.property) with
          ⟨chosen, _hchosen, unique⟩
        have hleft :
            left.val = chosen :=
          unique left.val ⟨left.property, rfl⟩
        have hright :
            right.val = chosen :=
          unique right.val ⟨right.property, hcharacters.symm⟩
        exact hleft.trans hright.symm
      · intro chi
        rcases realization.complete_unique chi.val chi.property with
          ⟨id, hid, _unique⟩
        refine ⟨⟨id, hid.1⟩, ?_⟩
        exact Subtype.ext hid.2)

/-- Canonical list position is therefore a duplicate-free, complete primitive
character roster.  This is the equivalence expected by the aggregate Turing
assembly theorem; no digest is promoted to roster completeness. -/
def indexEquiv
    (realization :
      FactoredSmallQSourceRealization.PrimitiveRosterRealization N ids) :
    Fin ids.length ≃
      {chi : DirichletCharacter Complex N // chi.IsPrimitive} :=
  (realization.nodup.getEquiv ids).trans realization.characterEquiv

end FactoredSmallQSourceRealization.PrimitiveRosterRealization

/-- The two auditable premises needed to recover every individual count from
one aggregate equality over a finite roster. -/
structure AggregateTuringCountEvidence (ι : Type*) [Fintype ι] where
  /-- Number of independently certified zero slots checked for a roster
  member.  In the endpoint-family theorem below these are precisely disjoint
  strict-sign-change brackets, hence distinct critical-line zero locations. -/
  bracketCount : ι → Nat
  /-- Exact multiplicity-counted zero count assigned by the analytic Turing
  theorem to the same roster member. -/
  turingCount : ι → Nat
  /-- The independently certified slots give a lower bound for the analytic
  multiplicity count.  This direction never assumes that the isolated zeros
  are simple. -/
  bracketCount_le_turingCount :
    ∀ i, bracketCount i ≤ turingCount i
  /-- The checked and analytic counts agree after summing over exactly the
  same finite roster. -/
  aggregateCount_eq :
    (∑ i, bracketCount i) = ∑ i, turingCount i

namespace AggregateTuringCountEvidence

/-- Nonnegative pointwise deficits with zero aggregate deficit all vanish. -/
theorem count_eq
    {ι : Type*} [Fintype ι]
    (evidence : AggregateTuringCountEvidence ι) (i : ι) :
    evidence.bracketCount i = evidence.turingCount i := by
  exact
    ((Finset.sum_eq_sum_iff_of_le
        (fun j _ => evidence.bracketCount_le_turingCount j)).mp
      evidence.aggregateCount_eq) i (Finset.mem_univ i)

/-- The aggregate certificate recovers exact counts for the whole roster. -/
theorem all_counts_eq
    {ι : Type*} [Fintype ι]
    (evidence : AggregateTuringCountEvidence ι) :
    evidence.bracketCount = evidence.turingCount := by
  funext i
  exact evidence.count_eq i

/-- Once aggregate equality recovers the individual count, a multiplicity-safe
analytic Turing upper bound stated at `turingCount` is exactly the upper bound
required by the ordinary finite-strip verifier at `bracketCount`.

This theorem deliberately receives `LZeroCountUpperBound` as a premise.  The
aggregate arithmetic neither proves the Turing theorem nor identifies its
analytic zero-count convention.  A source theorem that counts analytic
multiplicity must first prove the safe inequality from distinct locations to
that multiplicity count; this file does not identify the two notions by
definition. -/
theorem zeroCountUpperBound_at_bracketCount
    {N : Nat} [NeZero N] {ι : Type*} [Fintype ι]
    {lo hi : Real}
    (evidence : AggregateTuringCountEvidence ι)
    (chi : ι → DirichletCharacter Complex N)
    (turingUpper :
      ∀ i, LZeroCountUpperBound (chi i) lo hi (evidence.turingCount i)) :
    ∀ i, LZeroCountUpperBound (chi i) lo hi (evidence.bracketCount i) := by
  intro i
  rw [evidence.count_eq i]
  exact turingUpper i

end AggregateTuringCountEvidence

/-- Per-index verification over a bijective primitive-character roster is
exactly verification of every primitive character of the modulus.  Using an
equivalence here prevents both omissions and duplicate roster rows. -/
theorem grhVerifiedForModulus_of_completeRoster
    {N : Nat} [NeZero N] {ι : Type*} {lo hi : Real}
    (roster :
      ι ≃ {chi : DirichletCharacter Complex N // chi.IsPrimitive})
    (verified :
      ∀ i, ∀ z ∈ nontrivialCriticalStrip lo hi,
        (roster i).1.LFunction z = 0 → z.re = (1 : Real) / 2) :
    GRHVerifiedForModulus N lo hi := by
  intro chi primitive z hz hzero
  let i := roster.symm ⟨chi, primitive⟩
  have hroster : roster i = ⟨chi, primitive⟩ := by
    dsimp [i]
    exact roster.apply_symm_apply ⟨chi, primitive⟩
  have hvalue : (roster i).1 = chi :=
    congrArg Subtype.val hroster
  apply verified i z hz
  simpa only [hvalue] using hzero

/-- End-to-end axiom-free assembly for one modulus with `N ≥ 2`.

The finite strict-sign endpoint families, their exact enclosures, the complete
primitive roster, the Hardy-model theorem, and the multiplicity-safe analytic
Turing upper bounds all remain explicit premises.  The only compression is
numerical: equality of the aggregate counts recovers the individual count
needed by `DirichletHardyModel.verifyEndpointFamily`.

The hypothesis `2 ≤ N` is deliberate.  It supplies nontriviality of primitive
characters and keeps the source's `q = 1` Riemann-zeta computation outside this
Dirichlet assembly theorem. -/
theorem grhVerifiedForModulus_of_aggregateTuringEndpointFamilies
    {N : Nat} [NeZero N] (hN : 2 ≤ N)
    {ι : Type*} [Fintype ι] {lo hi : Real}
    (roster :
      ι ≃ {chi : DirichletCharacter Complex N // chi.IsPrimitive})
    (f : ι → Real → Real)
    (counts : AggregateTuringCountEvidence ι)
    (models :
      ∀ i, DirichletHardyModel (roster i).1 (f i) lo hi)
    (families :
      ∀ i, SparkInterval.Zeta.RationalBracketFamily
        (counts.bracketCount i))
    (checks : ∀ i, (families i).check = true)
    (encloses :
      ∀ i j, ((families i).entries j).EnclosesEndpoints (f i))
    (lowerEndpoints :
      ∀ i j, lo ≤ (((families i).entries j).lower : Real))
    (upperEndpoints :
      ∀ i j, (((families i).entries j).upper : Real) ≤ hi)
    (turingUpper :
      ∀ i, LZeroCountUpperBound (roster i).1 lo hi
        (counts.turingCount i)) :
    GRHVerifiedForModulus N lo hi := by
  apply grhVerifiedForModulus_of_completeRoster roster
  intro i
  exact
    (models i).verifyEndpointFamily
      (ne_one_of_isPrimitive hN (roster i).2)
      (families i) (checks i) (encloses i)
      (lowerEndpoints i) (upperEndpoints i)
      (counts.zeroCountUpperBound_at_bracketCount
        (fun j => (roster j).1) turingUpper i)

/-- Source-roster specialization of the aggregate assembly theorem.

Using `PrimitiveRosterRealization.indexEquiv` here makes the finite index
domain definitionally the positions of the source-owned noduplicated list and
proves, rather than assumes from a digest, that it contains every primitive
character exactly once.  As above, `q = 1` is deliberately excluded by
`2 ≤ N` and must be supplied by the separate zeta campaign. -/
theorem grhVerifiedForModulus_of_sourceRoster_aggregateTuringEndpointFamilies
    {N : Nat} [NeZero N] (hN : 2 ≤ N)
    {ids : List Nat} {lo hi : Real}
    (realization :
      FactoredSmallQSourceRealization.PrimitiveRosterRealization N ids)
    (f : Fin ids.length → Real → Real)
    (counts : AggregateTuringCountEvidence (Fin ids.length))
    (models :
      ∀ i, DirichletHardyModel (realization.indexEquiv i).1 (f i) lo hi)
    (families :
      ∀ i, SparkInterval.Zeta.RationalBracketFamily
        (counts.bracketCount i))
    (checks : ∀ i, (families i).check = true)
    (encloses :
      ∀ i j, ((families i).entries j).EnclosesEndpoints (f i))
    (lowerEndpoints :
      ∀ i j, lo ≤ (((families i).entries j).lower : Real))
    (upperEndpoints :
      ∀ i j, (((families i).entries j).upper : Real) ≤ hi)
    (turingUpper :
      ∀ i, LZeroCountUpperBound (realization.indexEquiv i).1 lo hi
        (counts.turingCount i)) :
    GRHVerifiedForModulus N lo hi :=
  grhVerifiedForModulus_of_aggregateTuringEndpointFamilies hN
    realization.indexEquiv f counts models families checks encloses
    lowerEndpoints upperEndpoints turingUpper

end SparkInterval.Dirichlet
