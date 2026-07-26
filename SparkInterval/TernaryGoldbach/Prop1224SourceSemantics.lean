/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Source semantics for Helfgott Proposition 12.2.4's finite computation

This module restates the exact finite-computation atom used by the
ternary-Goldbach development.  It keeps all source reals intact: `G_q`, the
infinite-prime definition of `c_E`, `f₁(q)`, the exact `c(c₊)` expression,
and the two strict/non-strict window conditions.

The compact certificate checker proves only that independent source-rank
shards cover `[0, 3389047618)` without gaps.  The physical edge remains the
explicit `ExternalShardRealization.mpfrGmpRows` field.  That field says the
MPFR transcendental intervals, exact GMP `G_q` accumulation, factorization,
and every conservative integer-window decision realize the literal Lean row
claim.  A receipt hash or a reported minimum margin does not construct it.

Ordinary Lean proves that the closed rank scheduler enumerates every `q` in
the source's disjoint range and that checked shard evidence implies the exact
source-shaped proposition.  No axiom or successful run is declared here.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.Prop1224SourceSemantics

open Finset
open scoped BigOperators

/-! ## Literal source definitions -/

noncomputable def ramareGTerm (r : Nat) : Real :=
  ((ArithmeticFunction.moebius r : Int) : Real) ^ 2 /
    (Nat.totient r : Real)

noncomputable def ramareG (q : Nat) (R : Real) : Real :=
  ∑ r ∈ (Finset.Icc 1 ⌊R⌋₊).filter (fun r => r.Coprime q),
    ramareGTerm r

noncomputable def ramareCE : Real :=
  Real.eulerMascheroniConstant +
    ∑' p : Nat.Primes,
      Real.log ((p : Nat) : Real) /
        (((p : Nat) : Real) * (((p : Nat) : Real) - 1))

noncomputable def ramareF1 (d : Nat) : Real :=
  ∏ p ∈ d.primeFactors,
    ((1 + (p : Real) ^ (-(2 : Real) / 3)) *
      (1 + ((p : Real) ^ ((1 : Real) / 3) +
          (p : Real) ^ ((2 : Real) / 3)) /
        ((p : Real) * ((p : Real) - 1)))⁻¹)

noncomputable def ramareLogSum (q : Nat) : Real :=
  ∑ p ∈ q.primeFactors, Real.log p / p

def ramareOmegaStar : Real := 0.627312

def ramareBetaStar : Real := 0.023111

noncomputable def ramareCDelta : Real := 1.36 - ramareCE

noncomputable def ramareKappaStar (q : Nat) : Real :=
  (1 - ramareOmegaStar) * (Real.log q - ramareLogSum q) +
    ramareCDelta

noncomputable def ramareC2Star : Real :=
  Real.exp ((1.4709 - ramareCE) +
    ramareOmegaStar * (ramareCE - 1.312) - ramareCDelta)

noncomputable def ramareTau : Real :=
  0.4 * Real.exp (-Real.eulerMascheroniConstant)

noncomputable def ramareCSigmaStar : Real :=
  Real.exp (Real.exp (-Real.eulerMascheroniConstant) *
    ((1.36 : Real) - (1.36 : Real) ^ 2 / 5.248 - 1.172))

noncomputable def ramareVarpiZero (q : Nat) : Real :=
  if 1 + Real.log q < ramareCSigmaStar * (q : Real) ^ ramareTau then
    (ramareCSigmaStar * (q : Real) ^ ramareTau -
        Real.log q *
          (ramareCSigmaStar * (q : Real) ^ ramareTau - Real.log q) ^
            (-ramareTau / (1 - ramareTau))) ^
      (1 / (1 - ramareTau))
  else 0

noncomputable def ramareVarpiStar (q : Nat) : Real :=
  max (ramareVarpiZero q)
    (max (ramareCSigmaStar * ((10 : Real) ^ 5) ^ ramareTau - Real.log q)
      ((10 : Real) ^ 5 /
        (ramareC2Star * q) ^ (1 / (1 - ramareOmegaStar))))

def RamareProp1224CiteRange (q : Nat) : Prop :=
  (q : Real) < 3300000000 ∨
    (210 ∣ q ∧ (q : Real) < 22000000000)

noncomputable def ramareErr (q : Nat) (R : Real) : Real :=
  ramareG q R -
    (Nat.totient q : Real) / q *
      (Real.log R + ramareCE + ramareLogSum q)

/-- Exact per-`q` computation claim after the source's analytic reductions. -/
def SourceRowClaim (q : Nat) : Prop :=
  ∀ k : Nat, 1 ≤ k →
    ramareVarpiStar q ≤ (k : Real) →
    (k : Real) ^ ((1 : Real) / 3) * ramareKappaStar q <
      (q : Real) / (Nat.totient q : Real) *
        (7.284 * (1 + ramareBetaStar)) * ramareF1 q →
    ramareErr q (k : Real) +
        ramareOmegaStar *
          (7.284 * (20000 * (k : Real)) ^ (-(1 : Real) / 3) *
            ramareF1 q) ≤
      (Nat.totient q : Real) / q * ramareKappaStar q

/-- Literal source-shaped trusted proposition. -/
def SourceClaim : Prop :=
  ∀ q k : Nat, 1 ≤ q → 1 ≤ k →
    RamareProp1224CiteRange q →
    ramareVarpiStar q ≤ (k : Real) →
    (k : Real) ^ ((1 : Real) / 3) * ramareKappaStar q <
      (q : Real) / (Nat.totient q : Real) *
        (7.284 * (1 + ramareBetaStar)) * ramareF1 q →
    ramareErr q (k : Real) +
        ramareOmegaStar *
          (7.284 * (20000 * (k : Real)) ^ (-(1 : Real) / 3) *
            ramareF1 q) ≤
      (Nat.totient q : Real) / q * ramareKappaStar q

/-! ## Closed source-rank scheduler -/

def denseRankEnd : Nat := 3_299_999_999
def firstExtensionQ : Nat := 3_300_000_060
def extensionDivisor : Nat := 210
def sourceRankCount : Nat := 3_389_047_618

/-- Exact `q` assigned to a nonterminal source rank. -/
def qAtRank (rank : Nat) : Nat :=
  if rank < denseRankEnd then rank + 1
  else firstExtensionQ + (rank - denseRankEnd) * extensionDivisor

/-- Every positive `q` in the paper's computation range has a source rank.
This closes the finite scheduler arithmetic independently of MPFR/GMP. -/
theorem citeRange_has_rank {q : Nat} (hq : 1 ≤ q)
    (hrange : RamareProp1224CiteRange q) :
    ∃ rank, rank < sourceRankCount ∧ qAtRank rank = q := by
  rcases hrange with hdense | hextension
  · have hqUpper : q < 3_300_000_000 := by exact_mod_cast hdense
    refine ⟨q - 1, ?_, ?_⟩
    · simp only [sourceRankCount]
      omega
    · have hrank : q - 1 < denseRankEnd := by
        simp only [denseRankEnd]
        omega
      simp [qAtRank, hrank]
      omega
  · rcases hextension with ⟨hdivides, hupperReal⟩
    have hqUpper : q < 22_000_000_000 := by exact_mod_cast hupperReal
    by_cases hqDense : q < 3_300_000_000
    · refine ⟨q - 1, ?_, ?_⟩
      · simp only [sourceRankCount]
        omega
      · have hrank : q - 1 < denseRankEnd := by
          simp only [denseRankEnd]
          omega
        simp [qAtRank, hrank]
        omega
    · rcases hdivides with ⟨m, rfl⟩
      let rank := denseRankEnd + (m - 15_714_286)
      have hmLower : 15_714_286 ≤ m := by omega
      have hmUpper : m ≤ 104_761_904 := by omega
      refine ⟨rank, ?_, ?_⟩
      · dsimp [rank, denseRankEnd, sourceRankCount]
        omega
      · simp [qAtRank, rank, denseRankEnd,
          firstExtensionQ, extensionDivisor]
        omega

/-! ## Compact coverage certificate and explicit physical edge -/

structure Shard where
  lower : Nat
  upper : Nat
  deriving Repr, DecidableEq

namespace Shard

def WellFormed (shard : Shard) : Prop := shard.lower < shard.upper

instance instDecidableWellFormed (shard : Shard) :
    Decidable shard.WellFormed := by
  unfold WellFormed
  infer_instance

end Shard

def ChainValid (sourceUpper : Nat) : Nat → List Shard → Prop
  | nextLower, [] => nextLower = sourceUpper
  | nextLower, shard :: rest =>
      shard.lower = nextLower ∧ shard.WellFormed ∧
        ChainValid sourceUpper shard.upper rest

structure Certificate where
  sourceLower : Nat
  sourceUpper : Nat
  shards : List Shard
  deriving Repr, DecidableEq

namespace Certificate

def ArithmeticValid (certificate : Certificate) : Prop :=
  certificate.sourceLower < certificate.sourceUpper ∧
    ChainValid certificate.sourceUpper certificate.sourceLower
      certificate.shards

private def chainCheck (sourceUpper : Nat) : Nat → List Shard → Bool
  | nextLower, [] => decide (nextLower = sourceUpper)
  | nextLower, shard :: rest =>
      decide (shard.lower = nextLower ∧ shard.WellFormed) &&
        chainCheck sourceUpper shard.upper rest

private theorem chainCheck_sound
    {sourceUpper nextLower : Nat} {shards : List Shard}
    (hcheck : chainCheck sourceUpper nextLower shards = true) :
    ChainValid sourceUpper nextLower shards := by
  induction shards generalizing nextLower with
  | nil => simpa [chainCheck, ChainValid] using hcheck
  | cons shard rest inductionHypothesis =>
      simp only [chainCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
      rw [ChainValid]
      exact ⟨hcheck.1.1, hcheck.1.2, inductionHypothesis hcheck.2⟩

def check (certificate : Certificate) : Bool :=
  decide (certificate.sourceLower < certificate.sourceUpper) &&
    chainCheck certificate.sourceUpper certificate.sourceLower
      certificate.shards

theorem checker_sound {certificate : Certificate}
    (hcheck : certificate.check = true) : certificate.ArithmeticValid := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, chainCheck_sound hcheck.2⟩

def FullSourceRange (certificate : Certificate) : Prop :=
  certificate.sourceLower = 0 ∧
    certificate.sourceUpper = sourceRankCount

end Certificate

/-- Physical/source meaning of one independent MPFR/GMP shard.

This is the intentionally explicit unproved refinement boundary.  For every
rank it includes exact factorization/totient realization, outward MPFR
realization of `log`, `exp`, and real powers (including the exact `c_E` and
Euler-gamma constants), exact GMP directed realization of `G_q(k)`, and all
integer-window endpoint decisions, summarized by the resulting literal
`SourceRowClaim`. -/
structure ExternalShardRealization (shard : Shard) where
  mpfrGmpRows : ∀ rank, shard.lower ≤ rank → rank < shard.upper →
    SourceRowClaim (qAtRank rank)

structure SourceScaleEvidence (certificate : Certificate) where
  fullRange : certificate.FullSourceRange
  physical : ∀ shard, shard ∈ certificate.shards →
    ExternalShardRealization shard

private theorem chain_row
    {sourceUpper nextLower : Nat} {shards : List Shard}
    (hchain : ChainValid sourceUpper nextLower shards)
    (hphysical : ∀ shard, shard ∈ shards → ExternalShardRealization shard)
    : ∀ rank, nextLower ≤ rank → rank < sourceUpper →
      SourceRowClaim (qAtRank rank) := by
  induction shards generalizing nextLower with
  | nil =>
      intro rank hlower hupper
      simp only [ChainValid] at hchain
      omega
  | cons shard rest inductionHypothesis =>
      rw [ChainValid] at hchain
      rcases hchain with ⟨hshardLower, hwell, hrest⟩
      intro rank hlower hupper
      by_cases hinShard : rank < shard.upper
      · exact (hphysical shard (by simp)).mpfrGmpRows rank
          (by simpa [hshardLower] using hlower) hinShard
      · exact inductionHypothesis hrest
          (fun tail hmem => hphysical tail (by simp [hmem]))
          rank (by omega) hupper

/-- A checked full-rank certificate and explicit MPFR/GMP realization imply
the exact source-shaped finite-computation atom. -/
theorem sourceClaim_of_checked_certificate
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) : SourceClaim := by
  intro q k hq hk hrange hvarpi hlambda
  obtain ⟨rank, hrankUpper, hrankQ⟩ := citeRange_has_rank hq hrange
  have hvalid := Certificate.checker_sound hcheck
  have hrow : SourceRowClaim (qAtRank rank) :=
    chain_row hvalid.2 evidence.physical rank
      (by simp [evidence.fullRange.1])
      (by simpa [evidence.fullRange.2] using hrankUpper)
  rw [hrankQ] at hrow
  exact hrow k hk hvarpi hlambda

end SparkInterval.TernaryGoldbach.Prop1224SourceSemantics
