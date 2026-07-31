/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.ArithmeticFunction.Moebius
import SparkInterval.Basic
import SparkInterval.TernaryGoldbach.HurstAffineCertificate
import TGComputeContracts.HurstV2

/-!
# Source semantics for the shared Hurst finite campaign

This module fixes the mathematical meaning of the four coordinates emitted by
the source-scale Hurst worker.  It deliberately uses exact `Int`, `Nat`, and
`Rat` arithmetic.  The predicates below mirror the worker's arbitrary-
precision fallback decisions; the cheaper integer-square-root filters in the
C++ implementation are optimizations and are not part of the theorem
statement.

The public `checked_*_real` theorems then derive the four ordinary real
step-function inequalities used by the source atoms.  In particular, the
squarefree proof checks both the value at each strict threshold and the right
limit of every slab; the V2 worker and receipt schema use that same inclusive
threshold policy.  Mathlib's proved 20-decimal bounds for `Real.pi` close the
directed density enclosure, so this real projection has no extra analytic
axiom.

`checked_full_source_claims_of_local` is the production ordinary-Lean half of
the trusted-compute bridge.  A closed registered invocation must still supply
`LocalSourceScaleEvidence certificate`: primitive Möbius/Q96 row deltas,
local integer guard decisions, literal full-range geometry, and a zero root.
Lean derives the unique global prefixes only along that checked replay.  The
older `SourceScaleEvidence SourceRowPredicate certificate` theorems remain as
an off-path compatibility API.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstSourceSemantics

open Finset
open SparkInterval.TernaryGoldbach.HurstAffineCertificate

/-- Exact Mertens prefix through the inclusive natural endpoint `n`. -/
def mertensPrefix (n : Nat) : Int :=
  ∑ k ∈ Finset.Icc 1 n, ArithmeticFunction.moebius k

/-- Exact count of squarefree positive integers through `n`. -/
def squarefreePrefix (n : Nat) : Nat :=
  ((Finset.Icc 1 n).filter fun k => ArithmeticFunction.moebius k ≠ 0).card

/-- Exact little-Mertens prefix through `n`. -/
def littleMertensPrefix (n : Nat) : Rat :=
  ∑ k ∈ Finset.Icc 1 n,
    (ArithmeticFunction.moebius k : Rat) / (k : Rat)

def littleScale : Nat := 2 ^ 96

def sourceLimit : Nat := 10_000_000_000_000_000
def little211Limit : Nat := 1_000_000_000_000

/-- **Exclusive** upper endpoint of Platt's stronger little-Mertens range.

The closed form is false at this endpoint: at `n = 7 727 068 587` the sum is
`5.6880854031502278e-06` against the majorant `5.6880397241931255e-06`.  A
sweep of `3 ≤ n ≤ 7 727 068 587` finds that one violation and no other; on
`[3, 7 727 068 586]` the minimum relative margin is `1.47e-05`.  Helfgott's
`Σ_{n<x}` statement is exactly this half-open `Σ_{n≤x}` one, so narrowing is a
summation-convention transport rather than a weakening. -/
def littleStrongerLimit : Nat := 7_727_068_587

/-- The machine coordinates realize every source prefix that the worker
actually tracks.

Mertens and squarefree coordinates remain active through the full campaign.
The C++ worker deliberately freezes both little-Mertens Q96 coordinates after
`10^12`, once neither little-Mertens claim consumes them.  Their directed
prefix realization is therefore required exactly on that active range, not
spuriously through `10^16`. -/
def PrefixRealization (n : Nat) (state : State) : Prop :=
  state.mertens = mertensPrefix n ∧
  state.squarefree = (squarefreePrefix n : Int) ∧
  (n ≤ little211Limit →
    (state.littleLowerQ96 : Rat) / littleScale ≤ littleMertensPrefix n ∧
    littleMertensPrefix n ≤ (state.littleUpperQ96 : Rat) / littleScale)

/-- Primitive replay meaning of one worker row.

The exact Möbius and squarefree increments are source-local.  While the Q96
coordinates are active, their increments are directed rational enclosures of
the one term `mu(n)/n`; after the active range the worker emits zero in both
coordinates. -/
def SourceRowDelta (n : Nat) (delta : State) : Prop :=
  delta.mertens = ArithmeticFunction.moebius n ∧
  delta.squarefree =
      (if ArithmeticFunction.moebius n = 0 then 0 else 1) ∧
  if n ≤ little211Limit then
    (delta.littleLowerQ96 : Rat) / littleScale ≤
        (ArithmeticFunction.moebius n : Rat) / n ∧
      (ArithmeticFunction.moebius n : Rat) / n ≤
        (delta.littleUpperQ96 : Rat) / littleScale
  else
    delta.littleLowerQ96 = 0 ∧ delta.littleUpperQ96 = 0

/-- Exact fallback decision for Hurst's `0.571 * sqrt n` bound. -/
def HurstSafeAt (n : Nat) (state : State) : Prop :=
  1_000_000 * state.mertens.natAbs ^ 2 ≤ 571 ^ 2 * n

def densityScale : Nat := 1_000_000_000_000_000_000
def densityLower : Nat := 607_927_101_854_026_628
def densityUpper : Nat := 607_927_101_854_026_629

/-- Exact arbitrary-precision fallback for one signed squarefree-deviation
side.  `deviation <= 0` is immediately safe, matching the worker. -/
def SquarefreeDeviationSafe
    (deviation : Int) (y boundNumerator boundDenominator : Nat) : Prop :=
  deviation ≤ 0 ∨
    (deviation.natAbs * boundDenominator) ^ 2 ≤
      (boundNumerator * densityScale) ^ 2 * y

/-- Both sides of the rational enclosure of `6/pi^2` are safe at one real
step-function endpoint. -/
def SquarefreeSafeAt
    (y : Nat) (squarefreeCount : Int)
    (boundNumerator boundDenominator : Nat) : Prop :=
  let scaledCount : Int := densityScale * squarefreeCount
  let upperDeviation : Int := scaledCount - densityLower * y
  let lowerDeviation : Int := densityUpper * y - scaledCount
  SquarefreeDeviationSafe upperDeviation y boundNumerator boundDenominator ∧
    SquarefreeDeviationSafe lowerDeviation y boundNumerator boundDenominator

/-- Exact Q96 fallback used for either little-Mertens bound. -/
def LittleEndpointSafe (rightEndpoint : Nat) (stronger : Bool)
    (value : Int) : Prop :=
  if stronger then
    4 * rightEndpoint * value.natAbs ^ 2 ≤ littleScale ^ 2
  else
    rightEndpoint * value.natAbs ^ 2 ≤ 2 * littleScale ^ 2

def LittleIntervalSafe (rightEndpoint : Nat) (stronger : Bool)
    (state : State) : Prop :=
  LittleEndpointSafe rightEndpoint stronger state.littleLowerQ96 ∧
    LittleEndpointSafe rightEndpoint stronger state.littleUpperQ96

/-- Exact source decisions made after processing row `n`.  For squarefree
counts, V2 retains both the value at `n`, inclusively from each strict-real
threshold, and the left limit at `n+1`.  The inclusive value check is needed
for points strictly between a threshold and its successor.  For
little-Mertens, the right endpoint is `n+1`.

Equation (2.11) keeps its closed terminal endpoint at `little211Limit`.  The
stronger range does **not**: its upper endpoint is exclusive, because the
closed statement is false there (see `littleStrongerLimit`).  A row at
`n = littleStrongerLimit - 1` still guards the right endpoint `n + 1 =
littleStrongerLimit`, which is what covers the real slab `[n, n+1)` where the
`1/(2√x)` majorant is smallest; what is dropped is only the demand that the
*prefix at* `littleStrongerLimit` satisfy the bound, which is exactly the
false case. -/
def SourceRowSafe (n : Nat) (state : State) : Prop :=
  (33 ≤ n → HurstSafeAt n state) ∧
  (9_243 ≤ n → SquarefreeSafeAt n state.squarefree 151 2_000) ∧
  (9_243 ≤ n → n < sourceLimit →
    SquarefreeSafeAt (n + 1) state.squarefree 151 2_000) ∧
  (438_429 ≤ n → SquarefreeSafeAt n state.squarefree 57 2_000) ∧
  (438_429 ≤ n → n < sourceLimit →
    SquarefreeSafeAt (n + 1) state.squarefree 57 2_000) ∧
  (n ≤ little211Limit →
    LittleIntervalSafe (if n < little211Limit then n + 1 else n) false state) ∧
  (3 ≤ n → n < littleStrongerLimit →
    LittleIntervalSafe (n + 1) true state)

/-- Concrete row predicate to be fixed in the registered Hurst invocation. -/
def SourceRowPredicate (n : Nat) (state : State) : Prop :=
  PrefixRealization n state ∧ SourceRowSafe n state

/-- Production evidence fixes primitive Möbius/Q96 row deltas and the local
integer guard decisions.  It does not assume a global prefix realization. -/
abbrev LocalSourceScaleEvidence (certificate : Certificate) :=
  ReplaySourceScaleEvidence SourceRowDelta SourceRowSafe certificate

/-! ## Local replay to global prefix semantics -/

theorem mertensPrefix_succ (n : Nat) :
    mertensPrefix (n + 1) =
      mertensPrefix n + ArithmeticFunction.moebius (n + 1) := by
  unfold mertensPrefix
  rw [show Finset.Icc 1 (n + 1) =
      insert (n + 1) (Finset.Icc 1 n) by
        ext k
        simp only [Finset.mem_Icc, Finset.mem_insert]
        omega,
    Finset.sum_insert]
  · ring
  · simp

theorem squarefreePrefix_succ (n : Nat) :
    squarefreePrefix (n + 1) =
      squarefreePrefix n +
        (if ArithmeticFunction.moebius (n + 1) = 0 then 0 else 1) := by
  unfold squarefreePrefix
  rw [show Finset.Icc 1 (n + 1) =
      insert (n + 1) (Finset.Icc 1 n) by
        ext k
        simp only [Finset.mem_Icc, Finset.mem_insert]
        omega]
  rw [Finset.filter_insert]
  by_cases hmu : ArithmeticFunction.moebius (n + 1) = 0
  · simp [hmu]
  · simp [hmu]

theorem squarefreePrefix_int_succ (n : Nat) :
    (squarefreePrefix (n + 1) : Int) =
      (squarefreePrefix n : Int) +
        (if ArithmeticFunction.moebius (n + 1) = 0 then 0 else 1) := by
  exact_mod_cast squarefreePrefix_succ n

theorem littleMertensPrefix_succ (n : Nat) :
    littleMertensPrefix (n + 1) =
      littleMertensPrefix n +
        (ArithmeticFunction.moebius (n + 1) : Rat) /
          ((n + 1 : Nat) : Rat) := by
  unfold littleMertensPrefix
  rw [show Finset.Icc 1 (n + 1) =
      insert (n + 1) (Finset.Icc 1 n) by
        ext k
        simp only [Finset.mem_Icc, Finset.mem_insert]
        omega,
    Finset.sum_insert]
  · ring
  · simp

@[simp] theorem prefixRealization_zero :
    PrefixRealization 0 State.zero := by
  simp [PrefixRealization, State.zero, mertensPrefix, squarefreePrefix,
    littleMertensPrefix, little211Limit]

/-- One valid primitive replay row advances a realized prefix by one source
index.  Directed Q96 enclosures compose additively while that coordinate is
active. -/
theorem prefixRealization_add_sourceRowDelta
    (n : Nat) {state delta : State}
    (hrealizes : PrefixRealization n state)
    (hdelta : SourceRowDelta (n + 1) delta) :
    PrefixRealization (n + 1) (state + delta) := by
  rcases hrealizes with ⟨hmertens, hsquarefree, hlittle⟩
  rcases hdelta with ⟨hdeltaMertens, hdeltaSquarefree, hdeltaLittle⟩
  refine ⟨?_, ?_, ?_⟩
  · rw [State.add_mertens, hmertens, hdeltaMertens]
    exact (mertensPrefix_succ n).symm
  · rw [State.add_squarefree, hsquarefree, hdeltaSquarefree]
    exact (squarefreePrefix_int_succ n).symm
  · intro hactive
    have hpreviousActive : n ≤ little211Limit := by omega
    have hprevious := hlittle hpreviousActive
    simp only [if_pos hactive] at hdeltaLittle
    have hlowerAdd :
        (((state + delta).littleLowerQ96 : Int) : Rat) / littleScale =
          (state.littleLowerQ96 : Rat) / littleScale +
            (delta.littleLowerQ96 : Rat) / littleScale := by
      simp only [State.add_littleLowerQ96, Int.cast_add]
      ring
    have hupperAdd :
        (((state + delta).littleUpperQ96 : Int) : Rat) / littleScale =
          (state.littleUpperQ96 : Rat) / littleScale +
            (delta.littleUpperQ96 : Rat) / littleScale := by
      simp only [State.add_littleUpperQ96, Int.cast_add]
      ring
    rw [hlowerAdd, hupperAdd, littleMertensPrefix_succ]
    exact ⟨add_le_add hprevious.1 hdeltaLittle.1,
      add_le_add hprevious.2 hdeltaLittle.2⟩

/-- Within one replayed block, primitive row deltas identify the actual local
prefix with the global source prefix. -/
private theorem ReplayBlockRealization.prefixRealizes
    {block : Block} {incoming : State}
    (evidence :
      ReplayBlockRealization SourceRowDelta SourceRowSafe block)
    (hlower : 0 < block.lower)
    (hincoming :
      PrefixRealization (block.lower - 1) incoming) :
    ∀ n, block.lower ≤ n → n < block.upper →
      PrefixRealization n
        (incoming + evidence.prefixBefore (n + 1)) := by
  intro n hnLower hnUpper
  induction n, hnLower using Nat.le_induction with
  | base =>
      have hpredSucc : block.lower - 1 + 1 = block.lower := by
        omega
      rw [evidence.prefixStep block.lower (by rfl) hnUpper,
        evidence.prefixAtLower, State.zero_add]
      have hdelta :=
        evidence.rowDeltaValid block.lower (by rfl) hnUpper
      have hstep :=
        prefixRealization_add_sourceRowDelta
          (block.lower - 1) hincoming (by
            simpa [hpredSucc] using hdelta)
      simpa [hpredSucc] using hstep
  | succ n hnLowerN inductionHypothesis =>
      have hnUpper' : n < block.upper := by omega
      have hnSuccUpper : n + 1 < block.upper := by omega
      rw [evidence.prefixStep (n + 1) (by omega) hnSuccUpper,
        ← State.add_assoc]
      exact prefixRealization_add_sourceRowDelta n
        (inductionHypothesis hnUpper')
        (evidence.rowDeltaValid (n + 1) (by omega) hnSuccUpper)

/-- Checked block chaining transports replay-local evidence to the combined
global-prefix and local-safety predicate at every actual source row. -/
private theorem chain_replay_source_rows
    {sourceUpper nextLower : Nat} {incoming : State}
    {blocks : List Block}
    (hchain : ChainValid sourceUpper nextLower incoming blocks)
    (hphysical : ∀ block, block ∈ blocks →
      ReplayBlockRealization SourceRowDelta SourceRowSafe block)
    (hnextLower : 0 < nextLower)
    (hincoming :
      PrefixRealization (nextLower - 1) incoming) :
    ∀ n, nextLower ≤ n → n < sourceUpper →
      ∃ state : State, SourceRowPredicate n state := by
  induction blocks generalizing nextLower incoming with
  | nil =>
      intro n hnLower hnUpper
      simp only [ChainValid] at hchain
      omega
  | cons block rest inductionHypothesis =>
      rw [ChainValid] at hchain
      rcases hchain with ⟨hlower, hwell, hguard, hrest⟩
      intro n hnLower hnUpper
      let evidence := hphysical block (by simp)
      have hblockLower : 0 < block.lower := by omega
      have hblockNonempty : block.lower < block.upper := hwell.1
      have hincomingBlock :
          PrefixRealization (block.lower - 1) incoming := by
        simpa [hlower] using hincoming
      by_cases hnBlock : n < block.upper
      · have hnBlockLower : block.lower ≤ n := by
          simpa [hlower] using hnLower
        have hrealizes :=
          ReplayBlockRealization.prefixRealizes
            evidence hblockLower hincomingBlock
            n hnBlockLower hnBlock
        have hsafe :=
          evidence.rowSafe incoming hguard n hnBlockLower hnBlock
        exact ⟨incoming + evidence.prefixBefore (n + 1),
          hrealizes, hsafe⟩
      · have hlastLower : block.lower ≤ block.upper - 1 := by
          omega
        have hlastUpper : block.upper - 1 < block.upper := by
          omega
        have hlast :=
          ReplayBlockRealization.prefixRealizes
            evidence hblockLower hincomingBlock
            (block.upper - 1) hlastLower hlastUpper
        have houtgoing :
            PrefixRealization (block.upper - 1)
              (block.advance incoming) := by
          unfold Block.advance
          rw [← evidence.totalDelta]
          simpa [show block.upper - 1 + 1 = block.upper by omega]
            using hlast
        apply inductionHypothesis hrest
        · intro tailBlock hmem
          exact hphysical tailBlock (by simp [hmem])
        · omega
        · exact houtgoing
        · omega
        · exact hnUpper

/-- A checked full-range local replay yields the same exact source-row
conclusion without assuming `PrefixRealization` at the physical edge. -/
theorem checked_full_source_claims_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate) :
    ∀ n, 1 ≤ n → n ≤ sourceLimit →
      ∃ state : State, SourceRowPredicate n state := by
  have hvalid := Certificate.checker_sound hcheck
  have hroot :
      PrefixRealization (certificate.sourceLower - 1)
        certificate.rootState := by
    rw [evidence.fullRange.1, evidence.rootZero]
    exact prefixRealization_zero
  have hrows :=
    chain_replay_source_rows hvalid.2.1 evidence.physical
      (by rw [evidence.fullRange.1]; norm_num) hroot
  intro n hnLower hnUpper
  apply hrows n
  · simpa [evidence.fullRange.1] using hnLower
  · rw [evidence.fullRange.2]
    simpa [sourceUpperExclusive, sourceLimit] using
      (Nat.lt_succ_iff.mpr hnUpper)

private theorem rowSafeWitness_exists_source_row
    {incoming : State} {blocks : List Block} {n : Nat}
    (hwitness : RowSafeWitnessFrom SourceRowPredicate incoming blocks n) :
    ∃ state : State, SourceRowPredicate n state := by
  induction blocks generalizing incoming with
  | nil => simp [RowSafeWitnessFrom] at hwitness
  | cons block rest inductionHypothesis =>
      rw [RowSafeWitnessFrom] at hwitness
      rcases hwitness with hhead | htail
      · rcases hhead with ⟨evidence, _, _, hsafe⟩
        exact ⟨incoming + evidence.prefixBefore (n + 1), hsafe⟩
      · exact inductionHypothesis htail

/-- Kernel-checked source conclusion for the one shared physical campaign.
Every natural endpoint through `10^16` has an exact prefix realization and all
four applicable exact fallback decisions. -/
theorem checked_full_source_claims
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate) :
    ∀ n, 1 ≤ n → n ≤ sourceLimit →
      ∃ state : State, SourceRowPredicate n state := by
  intro n hnLower hnUpper
  apply rowSafeWitness_exists_source_row
  apply checked_full_source_rows_sound hcheck evidence n hnLower
  simpa [sourceLimit] using hnUpper

/-- Mertens projection of the shared source campaign. -/
theorem checked_hurst_endpoint
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (n : Nat) (hnLower : 33 ≤ n) (hnUpper : n ≤ sourceLimit) :
    ∃ state : State, PrefixRealization n state ∧ HurstSafeAt n state := by
  rcases checked_full_source_claims hcheck evidence n (by omega) hnUpper with
    ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.1 hnLower⟩

/-- Replay-shaped counterpart of `checked_hurst_endpoint`. -/
theorem checked_hurst_endpoint_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (n : Nat) (hnLower : 33 ≤ n) (hnUpper : n ≤ sourceLimit) :
    ∃ state : State, PrefixRealization n state ∧ HurstSafeAt n state := by
  rcases checked_full_source_claims_of_local
      hcheck evidence n (by omega) hnUpper with
    ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.1 hnLower⟩

/-- The exact integer fallback implies the familiar real square-root form.
This theorem is independent of the external execution boundary. -/
theorem abs_mertensPrefix_le_of_realizes_hurst
    {n : Nat} {state : State}
    (hrealizes : PrefixRealization n state)
    (hsafe : HurstSafeAt n state) :
    |(mertensPrefix n : Real)| ≤
      ((571 : Real) / 1_000) * Real.sqrt n := by
  have hsafeReal :
      (1_000_000 : Real) * (state.mertens.natAbs : Real) ^ 2 ≤
        (571 : Real) ^ 2 * n := by
    exact_mod_cast hsafe
  have habsCast : |(state.mertens : Real)| = state.mertens.natAbs := by
    simp [Int.cast_abs]
  have hn : (0 : Real) ≤ n := by positivity
  have hsqrtSq : (Real.sqrt n) ^ 2 = (n : Real) := Real.sq_sqrt hn
  have hsqrtNonneg : (0 : Real) ≤ Real.sqrt n := Real.sqrt_nonneg n
  have habsNonneg : (0 : Real) ≤ |(state.mertens : Real)| := abs_nonneg _
  rw [← hrealizes.1]
  rw [← habsCast] at hsafeReal
  nlinarith

/-- Both strict-real squarefree stages are present in the same row predicate.
The conclusion retains both the value at `n` and the left-limit check at
`n+1`. -/
theorem checked_squarefree_endpoints
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (n : Nat) (hnLower : 438_429 ≤ n) (hnUpper : n < sourceLimit) :
    ∃ state : State,
      PrefixRealization n state ∧
      SquarefreeSafeAt n state.squarefree 151 2_000 ∧
      SquarefreeSafeAt (n + 1) state.squarefree 151 2_000 ∧
      SquarefreeSafeAt n state.squarefree 57 2_000 ∧
      SquarefreeSafeAt (n + 1) state.squarefree 57 2_000 := by
  rcases checked_full_source_claims hcheck evidence n (by omega)
      (Nat.le_of_lt hnUpper) with ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.2.1 (by omega),
    hsafe.2.2.1 (by omega) hnUpper,
    hsafe.2.2.2.1 hnLower,
    hsafe.2.2.2.2.1 (by omega) hnUpper⟩

/-- Replay-shaped counterpart of `checked_squarefree_endpoints`. -/
theorem checked_squarefree_endpoints_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (n : Nat) (hnLower : 438_429 ≤ n) (hnUpper : n < sourceLimit) :
    ∃ state : State,
      PrefixRealization n state ∧
      SquarefreeSafeAt n state.squarefree 151 2_000 ∧
      SquarefreeSafeAt (n + 1) state.squarefree 151 2_000 ∧
      SquarefreeSafeAt n state.squarefree 57 2_000 ∧
      SquarefreeSafeAt (n + 1) state.squarefree 57 2_000 := by
  rcases checked_full_source_claims_of_local hcheck evidence n (by omega)
      (Nat.le_of_lt hnUpper) with ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.2.1 (by omega),
    hsafe.2.2.1 (by omega) hnUpper,
    hsafe.2.2.2.1 hnLower,
    hsafe.2.2.2.2.1 (by omega) hnUpper⟩

/-- Little-Mertens `2.11` projection, including the right endpoint used for
the real step-function slab. -/
theorem checked_little211_endpoint
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (n : Nat) (hnLower : 1 ≤ n) (hnUpper : n ≤ little211Limit) :
    ∃ state : State,
      PrefixRealization n state ∧
      LittleIntervalSafe
        (if n < little211Limit then n + 1 else n) false state := by
  rcases checked_full_source_claims hcheck evidence n hnLower
      (hnUpper.trans (by norm_num [little211Limit, sourceLimit])) with
    ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.2.2.2.2.2.1 hnUpper⟩

/-- Replay-shaped counterpart of `checked_little211_endpoint`. -/
theorem checked_little211_endpoint_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (n : Nat) (hnLower : 1 ≤ n) (hnUpper : n ≤ little211Limit) :
    ∃ state : State,
      PrefixRealization n state ∧
      LittleIntervalSafe
        (if n < little211Limit then n + 1 else n) false state := by
  rcases checked_full_source_claims_of_local hcheck evidence n hnLower
      (hnUpper.trans (by norm_num [little211Limit, sourceLimit])) with
    ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.2.2.2.2.2.1 hnUpper⟩

/-- Stronger little-Mertens projection. -/
theorem checked_little_stronger_endpoint
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (n : Nat) (hnLower : 3 ≤ n) (hnUpper : n < littleStrongerLimit) :
    ∃ state : State,
      PrefixRealization n state ∧
      LittleIntervalSafe (n + 1) true state := by
  rcases checked_full_source_claims hcheck evidence n (by omega)
      (hnUpper.le.trans (by norm_num [littleStrongerLimit, sourceLimit])) with
    ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.2.2.2.2.2.2 hnLower hnUpper⟩

/-- Replay-shaped counterpart of `checked_little_stronger_endpoint`. -/
theorem checked_little_stronger_endpoint_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (n : Nat) (hnLower : 3 ≤ n) (hnUpper : n < littleStrongerLimit) :
    ∃ state : State,
      PrefixRealization n state ∧
      LittleIntervalSafe (n + 1) true state := by
  rcases checked_full_source_claims_of_local hcheck evidence n (by omega)
      (hnUpper.le.trans (by norm_num [littleStrongerLimit, sourceLimit])) with
    ⟨state, hrealizes, hsafe⟩
  exact ⟨state, hrealizes, hsafe.2.2.2.2.2.2 hnLower hnUpper⟩

/-! ## Real step-function projections -/

/-- Real Mertens step function represented by the source campaign.  This is
definitionally the usual sum through `⌊x⌋₊`, but is kept local so the
accelerator package does not depend on `claude_math`. -/
noncomputable def mertensStep (x : Real) : Real :=
  (mertensPrefix ⌊x⌋₊ : Real)

/-- Real little-Mertens step function represented by the source campaign. -/
noncomputable def littleMertensStep (x : Real) : Real :=
  (littleMertensPrefix ⌊x⌋₊ : Real)

/-- Real squarefree-counting step function represented by the source
campaign. -/
noncomputable def squarefreeStep (x : Real) : Real :=
  (squarefreePrefix ⌊x⌋₊ : Real)

/-! ### Definition-identification normal forms

These three lemmas expose the precise finite-sum syntax used by the downstream
source package.  Consequently its adapter does not need an analytic argument:
after unfolding the consumer definition, these are direct rewrite lemmas. -/

/-- The local Mertens step is the usual `Iic ⌊x⌋₊` real Möbius sum,
including the vanishing term at zero. -/
theorem mertensStep_eq_sourceSum (x : Real) :
    mertensStep x =
      ∑ n ∈ Finset.Iic ⌊x⌋₊, (ArithmeticFunction.moebius n : Real) := by
  unfold mertensStep mertensPrefix
  rw [Int.cast_sum]
  rw [show Finset.Iic ⌊x⌋₊ = insert 0 (Finset.Icc 1 ⌊x⌋₊) by
        ext n
        simp only [Finset.mem_Iic, Finset.mem_insert, Finset.mem_Icc]
        omega,
      Finset.sum_insert (by simp)]
  simp

/-- The local directed-rational prefix casts to the exact real sum used by
the little-Mertens source declarations. -/
theorem littleMertensStep_eq_sourceSum (x : Real) :
    littleMertensStep x =
      ∑ n ∈ Finset.Icc 1 ⌊x⌋₊,
        ((ArithmeticFunction.moebius n : Int) : Real) / (n : Real) := by
  unfold littleMertensStep littleMertensPrefix
  push_cast
  rfl

/-- The local squarefree cardinal is the exact absolute-Möbius range sum
used by the consumer's `squarefreeCount`. -/
theorem squarefreeStep_eq_sourceSum (x : Real) :
    squarefreeStep x =
      ∑ n ∈ Finset.range (⌊x⌋₊ + 1),
        |(ArithmeticFunction.moebius n : Real)| := by
  unfold squarefreeStep squarefreePrefix
  have hmu0 : ArithmeticFunction.moebius 0 = 0 := by
    simp [ArithmeticFunction.moebius]
  rw [Finset.card_eq_sum_ones]
  push_cast
  rw [show Finset.range (⌊x⌋₊ + 1) =
      insert 0 (Finset.Icc 1 ⌊x⌋₊) by
        ext n
        simp only [Finset.mem_range, Finset.mem_insert, Finset.mem_Icc]
        omega,
      Finset.sum_insert (by simp)]
  simp only [hmu0, Int.cast_zero, abs_zero, zero_add]
  rw [Finset.sum_filter]
  apply Finset.sum_congr rfl
  intro n hn
  rcases ArithmeticFunction.moebius_eq_or n with h0 | h1 | hn1
  · simp [h0]
  · simp [h1]
  · simp [hn1]

private theorem floor_upper {x : Real} {limit : Nat}
    (hx0 : 0 ≤ x) (hx : x ≤ limit) : ⌊x⌋₊ ≤ limit := by
  exact_mod_cast (Nat.floor_le hx0).trans hx

private theorem slab_right {x : Real} {limit : Nat}
    (hx0 : 0 ≤ x) (hx : x ≤ limit) :
    x ≤ ((if ⌊x⌋₊ < limit then ⌊x⌋₊ + 1 else ⌊x⌋₊ : Nat) : Real) := by
  by_cases hfloor : ⌊x⌋₊ < limit
  · simp [hfloor]
    exact (Nat.lt_floor_add_one x).le
  · have heq : ⌊x⌋₊ = limit :=
      Nat.le_antisymm (floor_upper hx0 hx) (Nat.le_of_not_gt hfloor)
    simp [heq]
    exact hx

private theorem littleEndpointFalseReal
    {rightEndpoint : Nat} {value : Int} {x : Real}
    (hsafe : LittleEndpointSafe rightEndpoint false value)
    (hx : 0 < x) (hxr : x ≤ rightEndpoint) :
    |(value : Real) / littleScale| ≤ Real.sqrt (2 / x) := by
  simp [LittleEndpointSafe] at hsafe
  have hsafeReal :
      (rightEndpoint : Real) * (value.natAbs : Real) ^ 2 ≤
        2 * (littleScale : Real) ^ 2 := by
    exact_mod_cast hsafe
  have hscale : (0 : Real) < littleScale := by norm_num [littleScale]
  have hscaleSq : (0 : Real) < (littleScale : Real) ^ 2 :=
    sq_pos_of_pos hscale
  have habs : |(value : Real) / littleScale| =
      (value.natAbs : Real) / littleScale := by
    rw [abs_div, ← Int.cast_abs, Nat.cast_natAbs]
    simp [abs_of_pos hscale]
  rw [habs]
  apply (Real.le_sqrt (by positivity) (by positivity)).2
  have hxmul :
      x * ((value.natAbs : Real) / littleScale) ^ 2 ≤
        (rightEndpoint : Real) *
          ((value.natAbs : Real) / littleScale) ^ 2 :=
    mul_le_mul_of_nonneg_right hxr (sq_nonneg _)
  have hrscaled :
      (rightEndpoint : Real) *
          ((value.natAbs : Real) / littleScale) ^ 2 ≤ 2 := by
    rw [div_pow]
    calc
      (rightEndpoint : Real) *
            ((value.natAbs : Real) ^ 2 / (littleScale : Real) ^ 2) =
          ((rightEndpoint : Real) * (value.natAbs : Real) ^ 2) /
            (littleScale : Real) ^ 2 := by ring
      _ ≤ 2 := (div_le_iff₀ hscaleSq).2 hsafeReal
  rw [div_pow]
  apply (le_div_iff₀ hx).2
  calc
    (value.natAbs : Real) ^ 2 / (littleScale : Real) ^ 2 * x =
        x * ((value.natAbs : Real) / littleScale) ^ 2 := by
          rw [div_pow]
          ring
    _ ≤ (rightEndpoint : Real) *
        ((value.natAbs : Real) / littleScale) ^ 2 := hxmul
    _ ≤ 2 := hrscaled

private theorem littleEndpointTrueReal
    {rightEndpoint : Nat} {value : Int} {x : Real}
    (hsafe : LittleEndpointSafe rightEndpoint true value)
    (hx : 0 < x) (hxr : x ≤ rightEndpoint) :
    |(value : Real) / littleScale| ≤ 1 / (2 * Real.sqrt x) := by
  simp [LittleEndpointSafe] at hsafe
  have hsafeReal :
      4 * (rightEndpoint : Real) * (value.natAbs : Real) ^ 2 ≤
        (littleScale : Real) ^ 2 := by
    exact_mod_cast hsafe
  have hscale : (0 : Real) < littleScale := by norm_num [littleScale]
  have hscaleSq : (0 : Real) < (littleScale : Real) ^ 2 :=
    sq_pos_of_pos hscale
  have habs : |(value : Real) / littleScale| =
      (value.natAbs : Real) / littleScale := by
    rw [abs_div, ← Int.cast_abs, Nat.cast_natAbs]
    simp [abs_of_pos hscale]
  rw [habs]
  have hxmul :
      4 * x * ((value.natAbs : Real) / littleScale) ^ 2 ≤
        4 * (rightEndpoint : Real) *
          ((value.natAbs : Real) / littleScale) ^ 2 := by
    exact mul_le_mul_of_nonneg_right
      (mul_le_mul_of_nonneg_left hxr (by norm_num)) (sq_nonneg _)
  have hrscaled :
      4 * (rightEndpoint : Real) *
          ((value.natAbs : Real) / littleScale) ^ 2 ≤ 1 := by
    rw [div_pow]
    calc
      4 * (rightEndpoint : Real) *
            ((value.natAbs : Real) ^ 2 / (littleScale : Real) ^ 2) =
          (4 * (rightEndpoint : Real) * (value.natAbs : Real) ^ 2) /
            (littleScale : Real) ^ 2 := by ring
      _ ≤ 1 := (div_le_iff₀ hscaleSq).2 (by simpa using hsafeReal)
  have hxscaled :
      4 * x * ((value.natAbs : Real) / littleScale) ^ 2 ≤ 1 :=
    hxmul.trans hrscaled
  have hsqrt : (Real.sqrt x) ^ 2 = x := Real.sq_sqrt hx.le
  have hnonneg :
      0 ≤ ((value.natAbs : Real) / littleScale) *
        (2 * Real.sqrt x) := by positivity
  apply (le_div_iff₀ (by positivity : (0 : Real) < 2 * Real.sqrt x)).2
  apply (sq_le_sq₀ hnonneg (by norm_num)).mp
  nlinarith [hxscaled]

private theorem littleFalseRealOfRealizes
    {n rightEndpoint : Nat} {state : State} {x : Real}
    (hrealizes : PrefixRealization n state)
    (hnActive : n ≤ little211Limit)
    (hsafe : LittleIntervalSafe rightEndpoint false state)
    (hx : 0 < x) (hxr : x ≤ rightEndpoint) :
    |(littleMertensPrefix n : Real)| ≤ Real.sqrt (2 / x) := by
  have hbounds := hrealizes.2.2 hnActive
  have hlRat := hbounds.1
  have huRat := hbounds.2
  have hl : (state.littleLowerQ96 : Real) / littleScale ≤
      (littleMertensPrefix n : Real) := by
    exact_mod_cast hlRat
  have hu : (littleMertensPrefix n : Real) ≤
      (state.littleUpperQ96 : Real) / littleScale := by
    exact_mod_cast huRat
  have hle := littleEndpointFalseReal hsafe.1 hx hxr
  have hue := littleEndpointFalseReal hsafe.2 hx hxr
  exact abs_le.mpr ⟨(abs_le.mp hle).1.trans hl,
    hu.trans (abs_le.mp hue).2⟩

private theorem littleTrueRealOfRealizes
    {n rightEndpoint : Nat} {state : State} {x : Real}
    (hrealizes : PrefixRealization n state)
    (hnActive : n ≤ little211Limit)
    (hsafe : LittleIntervalSafe rightEndpoint true state)
    (hx : 0 < x) (hxr : x ≤ rightEndpoint) :
    |(littleMertensPrefix n : Real)| ≤ 1 / (2 * Real.sqrt x) := by
  have hbounds := hrealizes.2.2 hnActive
  have hlRat := hbounds.1
  have huRat := hbounds.2
  have hl : (state.littleLowerQ96 : Real) / littleScale ≤
      (littleMertensPrefix n : Real) := by
    exact_mod_cast hlRat
  have hu : (littleMertensPrefix n : Real) ≤
      (state.littleUpperQ96 : Real) / littleScale := by
    exact_mod_cast huRat
  have hle := littleEndpointTrueReal hsafe.1 hx hxr
  have hue := littleEndpointTrueReal hsafe.2 hx hxr
  exact abs_le.mpr ⟨(abs_le.mp hle).1.trans hl,
    hu.trans (abs_le.mp hue).2⟩

/-- Full real-variable Hurst projection.  This matches the source shape
`|M(x)| ≤ 0.571√x` on `33 ≤ x ≤ 10^16`; the only package-local
difference is the name `mertensStep`. -/
theorem checked_hurst_real
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (x : Real) (hxLower : 33 ≤ x) (hxUpper : x ≤ sourceLimit) :
    |mertensStep x| ≤ ((571 : Real) / 1_000) * Real.sqrt x := by
  have hx0 : 0 ≤ x := by linarith
  let n := ⌊x⌋₊
  have hnLower : 33 ≤ n := Nat.le_floor hxLower
  have hnUpper : n ≤ sourceLimit := floor_upper hx0 hxUpper
  rcases checked_hurst_endpoint hcheck evidence n hnLower hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hnat := abs_mertensPrefix_le_of_realizes_hurst hrealizes hsafe
  have hfloor : (n : Real) ≤ x := Nat.floor_le hx0
  calc
    |mertensStep x| = |(mertensPrefix n : Real)| := by rfl
    _ ≤ ((571 : Real) / 1_000) * Real.sqrt n := hnat
    _ ≤ ((571 : Real) / 1_000) * Real.sqrt x := by gcongr

/-- Local-replay production path for the real Hurst projection. -/
theorem checked_hurst_real_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (x : Real) (hxLower : 33 ≤ x) (hxUpper : x ≤ sourceLimit) :
    |mertensStep x| ≤ ((571 : Real) / 1_000) * Real.sqrt x := by
  have hx0 : 0 ≤ x := by linarith
  let n := ⌊x⌋₊
  have hnLower : 33 ≤ n := Nat.le_floor hxLower
  have hnUpper : n ≤ sourceLimit := floor_upper hx0 hxUpper
  rcases checked_hurst_endpoint_of_local
      hcheck evidence n hnLower hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hnat := abs_mertensPrefix_le_of_realizes_hurst hrealizes hsafe
  have hfloor : (n : Real) ≤ x := Nat.floor_le hx0
  calc
    |mertensStep x| = |(mertensPrefix n : Real)| := by rfl
    _ ≤ ((571 : Real) / 1_000) * Real.sqrt n := hnat
    _ ≤ ((571 : Real) / 1_000) * Real.sqrt x := by gcongr

/-- Platt/Lambov equation (2.11) projected from both directed Q96
coordinates on every real slab through `10^12`. -/
theorem checked_little211_real
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (x : Real) (hxLower : 1 ≤ x) (hxUpper : x ≤ little211Limit) :
    |littleMertensStep x| ≤ Real.sqrt (2 / x) := by
  have hx : 0 < x := lt_of_lt_of_le (by norm_num) hxLower
  let n := ⌊x⌋₊
  have hnLower : 1 ≤ n := Nat.le_floor
    (show ((1 : Nat) : Real) ≤ x by simpa using hxLower)
  have hnUpper : n ≤ little211Limit := floor_upper hx.le hxUpper
  rcases checked_little211_endpoint hcheck evidence n hnLower hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hxr :
      x ≤ ((if n < little211Limit then n + 1 else n : Nat) : Real) := by
    exact slab_right hx.le hxUpper
  exact littleFalseRealOfRealizes hrealizes hnUpper hsafe hx hxr

/-- Local-replay production path for the `2.11` little-Mertens bound. -/
theorem checked_little211_real_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (x : Real) (hxLower : 1 ≤ x) (hxUpper : x ≤ little211Limit) :
    |littleMertensStep x| ≤ Real.sqrt (2 / x) := by
  have hx : 0 < x := lt_of_lt_of_le (by norm_num) hxLower
  let n := ⌊x⌋₊
  have hnLower : 1 ≤ n := Nat.le_floor
    (show ((1 : Nat) : Real) ≤ x by simpa using hxLower)
  have hnUpper : n ≤ little211Limit := floor_upper hx.le hxUpper
  rcases checked_little211_endpoint_of_local
      hcheck evidence n hnLower hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hxr :
      x ≤ ((if n < little211Limit then n + 1 else n : Nat) : Real) := by
    exact slab_right hx.le hxUpper
  exact littleFalseRealOfRealizes hrealizes hnUpper hsafe hx hxr

/-- Platt's stronger `1/(2√x)` computation projected from both directed
Q96 coordinates on every real slab strictly below `7,727,068,587`.

The upper endpoint is **exclusive**; the closed statement is false there.  See
`littleStrongerLimit`. -/
theorem checked_little_stronger_real
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (x : Real) (hxLower : 3 ≤ x) (hxUpper : x < littleStrongerLimit) :
    |littleMertensStep x| ≤ 1 / (2 * Real.sqrt x) := by
  have hx : 0 < x := lt_of_lt_of_le (by norm_num) hxLower
  let n := ⌊x⌋₊
  have hnLower : 3 ≤ n := Nat.le_floor
    (show ((3 : Nat) : Real) ≤ x by simpa using hxLower)
  have hnUpper : n < littleStrongerLimit :=
    (Nat.floor_lt hx.le).mpr (by exact_mod_cast hxUpper)
  rcases checked_little_stronger_endpoint hcheck evidence n hnLower hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hxr : x ≤ ((n + 1 : Nat) : Real) := by
    push_cast
    exact (Nat.lt_floor_add_one x).le
  exact littleTrueRealOfRealizes hrealizes
    (hnUpper.le.trans (by norm_num [littleStrongerLimit, little211Limit]))
    hsafe hx hxr

/-- Local-replay production path for the stronger little-Mertens bound. -/
theorem checked_little_stronger_real_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (x : Real) (hxLower : 3 ≤ x) (hxUpper : x < littleStrongerLimit) :
    |littleMertensStep x| ≤ 1 / (2 * Real.sqrt x) := by
  have hx : 0 < x := lt_of_lt_of_le (by norm_num) hxLower
  let n := ⌊x⌋₊
  have hnLower : 3 ≤ n := Nat.le_floor
    (show ((3 : Nat) : Real) ≤ x by simpa using hxLower)
  have hnUpper : n < littleStrongerLimit :=
    (Nat.floor_lt hx.le).mpr (by exact_mod_cast hxUpper)
  rcases checked_little_stronger_endpoint_of_local
      hcheck evidence n hnLower hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hxr : x ≤ ((n + 1 : Nat) : Real) := by
    push_cast
    exact (Nat.lt_floor_add_one x).le
  exact littleTrueRealOfRealizes hrealizes
    (hnUpper.le.trans (by norm_num [littleStrongerLimit, little211Limit]))
    hsafe hx hxr

/-! ## Squarefree rational-density projection -/

/-- A real density constant lies in the worker's directed rational
enclosure.  The application theorem below takes this proposition explicitly
for `6 / π²`; proving that analytic constant enclosure belongs in the consumer
package, not in the finite-computation bridge. -/
def DensityEnclosure (c : Real) : Prop :=
  (densityLower : Real) / densityScale ≤ c ∧
    c ≤ (densityUpper : Real) / densityScale

/-- The worker's 18-decimal directed density enclosure really contains
`6/π²`.  This is ordinary kernel-checked arithmetic from Mathlib's proved
20-decimal bounds on `π`; it is not external execution evidence. -/
theorem densityEnclosure_six_div_pi_sq :
    DensityEnclosure (6 / Real.pi ^ 2) := by
  have hp : (0 : Real) < Real.pi := Real.pi_pos
  constructor
  · apply (le_div_iff₀ (sq_pos_of_pos hp)).2
    have hpi := Real.pi_lt_d20
    norm_num [densityLower, densityScale] at hpi ⊢
    nlinarith [sq_nonneg
      (Real.pi -
        (314159265358979323847 : Real) / 100000000000000000000)]
  · apply (div_le_iff₀ (sq_pos_of_pos hp)).2
    have hpi := Real.pi_gt_d20
    norm_num [densityUpper, densityScale] at hpi ⊢
    nlinarith [sq_nonneg
      (Real.pi -
        (314159265358979323846 : Real) / 100000000000000000000)]

private theorem squarefreeDeviationReal
    {deviation : Int} {y numerator denominator : Nat}
    (hsafe : SquarefreeDeviationSafe deviation y numerator denominator)
    (hden : 0 < denominator) :
    (deviation : Real) / densityScale ≤
      (numerator : Real) / denominator * Real.sqrt y := by
  have hscale : (0 : Real) < densityScale := by norm_num [densityScale]
  have hdenReal : (0 : Real) < denominator := by exact_mod_cast hden
  by_cases hnonpos : deviation ≤ 0
  · have hdev : (deviation : Real) ≤ 0 := by exact_mod_cast hnonpos
    have hright :
        (0 : Real) ≤
          (numerator : Real) / denominator * Real.sqrt y := by positivity
    exact (div_nonpos_of_nonpos_of_nonneg hdev hscale.le).trans hright
  · have hdev : 0 < deviation := lt_of_not_ge hnonpos
    have hsquare := hsafe.resolve_left hnonpos
    have hdevReal : (0 : Real) < deviation := by exact_mod_cast hdev
    have habsCast : |(deviation : Real)| = deviation.natAbs := by
      simp [Int.cast_abs]
    have hdevNat : (deviation.natAbs : Real) = (deviation : Real) := by
      rw [← habsCast, abs_of_pos hdevReal]
    have hsquareReal :
        (((deviation.natAbs * denominator : Nat) : Real)) ^ 2 ≤
          (((numerator * densityScale : Nat) : Real)) ^ 2 * (y : Real) := by
      exact_mod_cast hsquare
    push_cast at hsquareReal
    rw [hdevNat] at hsquareReal
    have hsqrtSq : (Real.sqrt (y : Real)) ^ 2 = (y : Real) :=
      Real.sq_sqrt (by positivity)
    have hleft : 0 ≤ (deviation : Real) * denominator := by positivity
    have hright :
        0 ≤ (numerator : Real) * densityScale * Real.sqrt y := by
      positivity
    have hprod :
        (deviation : Real) * denominator ≤
          (numerator : Real) * densityScale * Real.sqrt y := by
      apply (sq_le_sq₀ hleft hright).mp
      nlinarith [hsquareReal]
    apply (div_le_iff₀ hscale).2
    rw [show
      (numerator : Real) / denominator * Real.sqrt y * densityScale =
        ((numerator : Real) * densityScale * Real.sqrt y) / denominator by
          field_simp]
    exact (le_div_iff₀ hdenReal).2 (by simpa [mul_comm] using hprod)

/-- If the normalized lower deviation is positive, its ratio to `√x` is
monotone on a slab.  This is the nontrivial reason why the worker's right-limit
check at `n+1` controls every lower side between `n` and `n+1`. -/
private theorem affineLowerSlab
    {q upper c b x right : Real}
    (hq : 0 ≤ q) (hupper : 0 ≤ upper) (hb : 0 ≤ b)
    (hx : 0 < x) (hxr : x ≤ right)
    (hcUpper : c ≤ upper)
    (hright : upper * right - q ≤ b * Real.sqrt right) :
    c * x - q ≤ b * Real.sqrt x := by
  by_cases htarget : c * x - q ≤ 0
  · exact htarget.trans (by positivity)
  have htargetPos : 0 < c * x - q := lt_of_not_ge htarget
  have hdx : 0 < upper * x - q := by
    have : c * x ≤ upper * x :=
      mul_le_mul_of_nonneg_right hcUpper hx.le
    linarith
  have hrightPos : 0 < right := hx.trans_le hxr
  have hrightDeviation : 0 ≤ upper * right - q := by
    have hux : upper * x ≤ upper * right :=
      mul_le_mul_of_nonneg_left hxr hupper
    linarith
  have hqUx : q ≤ upper * x := by linarith
  have hUx : 0 ≤ upper * x := mul_nonneg hupper hx.le
  have hqSq : q ^ 2 ≤ (upper * x) ^ 2 :=
    (sq_le_sq₀ hq hUx).2 hqUx
  have hUxSq : (upper * x) ^ 2 ≤ upper ^ 2 * right * x := by
    have hmul := mul_le_mul_of_nonneg_right hxr
      (mul_nonneg (sq_nonneg upper) hx.le)
    nlinarith
  have hterm : q ^ 2 ≤ upper ^ 2 * right * x := hqSq.trans hUxSq
  have hcross :
      right * (upper * x - q) ^ 2 ≤
        x * (upper * right - q) ^ 2 := by
    have hfactor :
        0 ≤ (right - x) * (upper ^ 2 * right * x - q ^ 2) :=
      mul_nonneg (sub_nonneg.mpr hxr) (sub_nonneg.mpr hterm)
    nlinarith
  have hrightSq :
      (upper * right - q) ^ 2 ≤ (b * Real.sqrt right) ^ 2 :=
    (sq_le_sq₀ hrightDeviation (by positivity)).2 hright
  have hcombined :
      right * (upper * x - q) ^ 2 ≤ right * (b ^ 2 * x) := by
    calc
      right * (upper * x - q) ^ 2
          ≤ x * (upper * right - q) ^ 2 := hcross
      _ ≤ x * (b * Real.sqrt right) ^ 2 :=
        mul_le_mul_of_nonneg_left hrightSq hx.le
      _ = right * (b ^ 2 * x) := by
        calc
          x * (b * Real.sqrt right) ^ 2 =
              x * b ^ 2 * (Real.sqrt right) ^ 2 := by ring
          _ = x * b ^ 2 * right := by
            rw [Real.sq_sqrt hrightPos.le]
          _ = right * (b ^ 2 * x) := by ring
  have hdxSq : (upper * x - q) ^ 2 ≤ b ^ 2 * x := by
    nlinarith
  have hdxBound : upper * x - q ≤ b * Real.sqrt x := by
    apply (sq_le_sq₀ hdx.le (by positivity)).mp
    calc
      (upper * x - q) ^ 2 ≤ b ^ 2 * x := hdxSq
      _ = (b * Real.sqrt x) ^ 2 := by
        rw [show
          (b * Real.sqrt x) ^ 2 = b ^ 2 * (Real.sqrt x) ^ 2 by ring,
          Real.sq_sqrt hx.le]
  have hcx : c * x ≤ upper * x :=
    mul_le_mul_of_nonneg_right hcUpper hx.le
  linarith

private theorem squarefreeRealSlabOfRealizes
    {n numerator denominator : Nat} {state : State} {x c : Real}
    (hrealizes : PrefixRealization n state)
    (hleftSafe : SquarefreeSafeAt n state.squarefree numerator denominator)
    (hrightSafe :
      SquarefreeSafeAt (n + 1) state.squarefree numerator denominator)
    (hdensity : DensityEnclosure c)
    (hden : 0 < denominator) (hn : 1 ≤ n)
    (hnx : (n : Real) ≤ x) (hxr : x ≤ (n + 1 : Nat)) :
    |(squarefreePrefix n : Real) - c * x| ≤
      (numerator : Real) / denominator * Real.sqrt x := by
  change
    SquarefreeDeviationSafe
        ((densityScale : Int) * state.squarefree -
          (densityLower : Int) * n)
        n numerator denominator ∧
      SquarefreeDeviationSafe
        ((densityUpper : Int) * n -
          (densityScale : Int) * state.squarefree)
        n numerator denominator at hleftSafe
  change
    SquarefreeDeviationSafe
        ((densityScale : Int) * state.squarefree -
          (densityLower : Int) * (n + 1))
        (n + 1) numerator denominator ∧
      SquarefreeDeviationSafe
        ((densityUpper : Int) * (n + 1) -
          (densityScale : Int) * state.squarefree)
        (n + 1) numerator denominator at hrightSafe
  have hqstate : (state.squarefree : Real) = squarefreePrefix n := by
    exact_mod_cast hrealizes.2.1
  have hscaleNe : (densityScale : Real) ≠ 0 := by
    norm_num [densityScale]
  have hx : 0 < x := by
    have : (0 : Real) < n := by exact_mod_cast (Nat.zero_lt_of_lt hn)
    linarith
  have hleftDev := squarefreeDeviationReal hleftSafe.1 hden
  have hrightDev := squarefreeDeviationReal hrightSafe.2 hden
  have hleft :
      (squarefreePrefix n : Real) -
          ((densityLower : Real) / densityScale) * n ≤
        (numerator : Real) / denominator * Real.sqrt n := by
    calc
      (squarefreePrefix n : Real) -
          ((densityLower : Real) / densityScale) * n =
          ((densityScale : Real) * squarefreePrefix n -
            (densityLower : Real) * n) / densityScale := by
              field_simp [hscaleNe]
      _ = (((densityScale : Int) * state.squarefree -
          (densityLower : Int) * n : Int) : Real) / densityScale := by
            push_cast
            rw [hqstate]
      _ ≤ (numerator : Real) / denominator * Real.sqrt n := hleftDev
  have hright :
      ((densityUpper : Real) / densityScale) * (n + 1 : Nat) -
          (squarefreePrefix n : Real) ≤
        (numerator : Real) / denominator * Real.sqrt (n + 1 : Nat) := by
    calc
      ((densityUpper : Real) / densityScale) * (n + 1 : Nat) -
          (squarefreePrefix n : Real) =
          ((densityUpper : Real) * (n + 1 : Nat) -
            densityScale * squarefreePrefix n) / densityScale := by
              field_simp [hscaleNe]
      _ = (((densityUpper : Int) * (n + 1) -
          (densityScale : Int) * state.squarefree : Int) : Real) /
          densityScale := by
            push_cast
            rw [hqstate]
      _ ≤ (numerator : Real) / denominator * Real.sqrt (n + 1 : Nat) :=
        hrightDev
  have hlowerNonneg :
      (0 : Real) ≤ (densityLower : Real) / densityScale := by positivity
  have hlowerProduct :
      ((densityLower : Real) / densityScale) * n ≤ c * x := by
    calc
      ((densityLower : Real) / densityScale) * n
          ≤ ((densityLower : Real) / densityScale) * x :=
        mul_le_mul_of_nonneg_left hnx hlowerNonneg
      _ ≤ c * x := mul_le_mul_of_nonneg_right hdensity.1 hx.le
  have hb : 0 ≤ (numerator : Real) / denominator := by positivity
  have hupperBound :
      (squarefreePrefix n : Real) - c * x ≤
        (numerator : Real) / denominator * Real.sqrt x := by
    calc
      (squarefreePrefix n : Real) - c * x ≤
          (squarefreePrefix n : Real) -
            ((densityLower : Real) / densityScale) * n :=
        sub_le_sub_left hlowerProduct _
      _ ≤ (numerator : Real) / denominator * Real.sqrt n := hleft
      _ ≤ (numerator : Real) / denominator * Real.sqrt x := by
        exact mul_le_mul_of_nonneg_left (Real.sqrt_le_sqrt hnx) hb
  have hlowerBound :
      c * x - (squarefreePrefix n : Real) ≤
        (numerator : Real) / denominator * Real.sqrt x := by
    apply affineLowerSlab
      (q := (squarefreePrefix n : Real))
      (upper := (densityUpper : Real) / densityScale)
      (c := c) (b := (numerator : Real) / denominator)
      (x := x) (right := (n + 1 : Nat))
    · positivity
    · positivity
    · exact hb
    · exact hx
    · exact hxr
    · exact hdensity.2
    · exact hright
  exact abs_le.mpr ⟨by linarith, hupperBound⟩

private theorem squarefreeRealEndpointOfRealizes
    {n numerator denominator : Nat} {state : State} {c : Real}
    (hrealizes : PrefixRealization n state)
    (hsafe : SquarefreeSafeAt n state.squarefree numerator denominator)
    (hdensity : DensityEnclosure c)
    (hden : 0 < denominator) :
    |(squarefreePrefix n : Real) - c * n| ≤
      (numerator : Real) / denominator * Real.sqrt n := by
  change
    SquarefreeDeviationSafe
        ((densityScale : Int) * state.squarefree -
          (densityLower : Int) * n)
        n numerator denominator ∧
      SquarefreeDeviationSafe
        ((densityUpper : Int) * n -
          (densityScale : Int) * state.squarefree)
        n numerator denominator at hsafe
  have hqstate : (state.squarefree : Real) = squarefreePrefix n := by
    exact_mod_cast hrealizes.2.1
  have hscaleNe : (densityScale : Real) ≠ 0 := by
    norm_num [densityScale]
  have hleftDev := squarefreeDeviationReal hsafe.1 hden
  have hrightDev := squarefreeDeviationReal hsafe.2 hden
  have hleft :
      (squarefreePrefix n : Real) -
          ((densityLower : Real) / densityScale) * n ≤
        (numerator : Real) / denominator * Real.sqrt n := by
    calc
      (squarefreePrefix n : Real) -
          ((densityLower : Real) / densityScale) * n =
          ((densityScale : Real) * squarefreePrefix n -
            (densityLower : Real) * n) / densityScale := by
              field_simp [hscaleNe]
      _ = (((densityScale : Int) * state.squarefree -
          (densityLower : Int) * n : Int) : Real) / densityScale := by
            push_cast
            rw [hqstate]
      _ ≤ _ := hleftDev
  have hright :
      ((densityUpper : Real) / densityScale) * n -
          (squarefreePrefix n : Real) ≤
        (numerator : Real) / denominator * Real.sqrt n := by
    calc
      ((densityUpper : Real) / densityScale) * n -
          (squarefreePrefix n : Real) =
          ((densityUpper : Real) * n -
            densityScale * squarefreePrefix n) / densityScale := by
              field_simp [hscaleNe]
      _ = (((densityUpper : Int) * n -
          (densityScale : Int) * state.squarefree : Int) : Real) /
          densityScale := by
            push_cast
            rw [hqstate]
      _ ≤ _ := hrightDev
  have hn : (0 : Real) ≤ n := by positivity
  have hcnLower :
      ((densityLower : Real) / densityScale) * n ≤ c * n :=
    mul_le_mul_of_nonneg_right hdensity.1 hn
  have hcnUpper :
      c * n ≤ ((densityUpper : Real) / densityScale) * n :=
    mul_le_mul_of_nonneg_right hdensity.2 hn
  exact abs_le.mpr ⟨by linarith, by linarith⟩

/-- First strict-real CDEM squarefree head through `10^16`. -/
theorem checked_squarefree_b1_real
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (x : Real) (hxLower : (9_243 : Real) < x)
    (hxUpper : x ≤ sourceLimit) :
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (151 / 2_000 : Real) * Real.sqrt x := by
  have hx : 0 < x := by linarith
  let n := ⌊x⌋₊
  have hnLower : 9_243 ≤ n := Nat.le_floor hxLower.le
  have hnOne : 1 ≤ n := by omega
  have hnUpper : n ≤ sourceLimit := floor_upper hx.le hxUpper
  rcases checked_full_source_claims hcheck evidence n (by omega) hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hleft := hsafe.2.1 hnLower
  by_cases hnTerminal : n = sourceLimit
  · have hxEq : x = (n : Real) := by
      have hnCast : (n : Real) ≤ x := Nat.floor_le hx.le
      have : x ≤ (n : Real) := by simpa [hnTerminal] using hxUpper
      linarith
    rw [squarefreeStep, show ⌊x⌋₊ = n by rfl, hxEq]
    exact squarefreeRealEndpointOfRealizes hrealizes hleft
      densityEnclosure_six_div_pi_sq
      (by norm_num)
  · have hnLt : n < sourceLimit := lt_of_le_of_ne hnUpper hnTerminal
    have hright := hsafe.2.2.1 hnLower hnLt
    apply squarefreeRealSlabOfRealizes hrealizes hleft hright
      densityEnclosure_six_div_pi_sq
      (by norm_num) hnOne
    · exact Nat.floor_le hx.le
    · simpa [n, Nat.cast_add, Nat.cast_one] using
        (Nat.lt_floor_add_one x).le

/-- Local-replay production path for the first squarefree stage. -/
theorem checked_squarefree_b1_real_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (x : Real) (hxLower : (9_243 : Real) < x)
    (hxUpper : x ≤ sourceLimit) :
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (151 / 2_000 : Real) * Real.sqrt x := by
  have hx : 0 < x := by linarith
  let n := ⌊x⌋₊
  have hnLower : 9_243 ≤ n := Nat.le_floor hxLower.le
  have hnOne : 1 ≤ n := by omega
  have hnUpper : n ≤ sourceLimit := floor_upper hx.le hxUpper
  rcases checked_full_source_claims_of_local
      hcheck evidence n (by omega) hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hleft := hsafe.2.1 hnLower
  by_cases hnTerminal : n = sourceLimit
  · have hxEq : x = (n : Real) := by
      have hnCast : (n : Real) ≤ x := Nat.floor_le hx.le
      have : x ≤ (n : Real) := by simpa [hnTerminal] using hxUpper
      linarith
    rw [squarefreeStep, show ⌊x⌋₊ = n by rfl, hxEq]
    exact squarefreeRealEndpointOfRealizes hrealizes hleft
      densityEnclosure_six_div_pi_sq
      (by norm_num)
  · have hnLt : n < sourceLimit := lt_of_le_of_ne hnUpper hnTerminal
    have hright := hsafe.2.2.1 hnLower hnLt
    apply squarefreeRealSlabOfRealizes hrealizes hleft hright
      densityEnclosure_six_div_pi_sq
      (by norm_num) hnOne
    · exact Nat.floor_le hx.le
    · simpa [n, Nat.cast_add, Nat.cast_one] using
        (Nat.lt_floor_add_one x).le

/-- Second strict-real CDEM squarefree head through `10^16`, with the sharper
constant `57/2000`. -/
theorem checked_squarefree_b2_real
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate)
    (x : Real) (hxLower : (438_429 : Real) < x)
    (hxUpper : x ≤ sourceLimit) :
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (57 / 2_000 : Real) * Real.sqrt x := by
  have hx : 0 < x := by linarith
  let n := ⌊x⌋₊
  have hnLower : 438_429 ≤ n := Nat.le_floor hxLower.le
  have hnOne : 1 ≤ n := by omega
  have hnUpper : n ≤ sourceLimit := floor_upper hx.le hxUpper
  rcases checked_full_source_claims hcheck evidence n (by omega) hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hleft := hsafe.2.2.2.1 hnLower
  by_cases hnTerminal : n = sourceLimit
  · have hxEq : x = (n : Real) := by
      have hnCast : (n : Real) ≤ x := Nat.floor_le hx.le
      have : x ≤ (n : Real) := by simpa [hnTerminal] using hxUpper
      linarith
    rw [squarefreeStep, show ⌊x⌋₊ = n by rfl, hxEq]
    exact squarefreeRealEndpointOfRealizes hrealizes hleft
      densityEnclosure_six_div_pi_sq
      (by norm_num)
  · have hnLt : n < sourceLimit := lt_of_le_of_ne hnUpper hnTerminal
    have hright := hsafe.2.2.2.2.1 hnLower hnLt
    apply squarefreeRealSlabOfRealizes hrealizes hleft hright
      densityEnclosure_six_div_pi_sq
      (by norm_num) hnOne
    · exact Nat.floor_le hx.le
    · simpa [n, Nat.cast_add, Nat.cast_one] using
        (Nat.lt_floor_add_one x).le

/-- Local-replay production path for the sharper squarefree stage. -/
theorem checked_squarefree_b2_real_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (x : Real) (hxLower : (438_429 : Real) < x)
    (hxUpper : x ≤ sourceLimit) :
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (57 / 2_000 : Real) * Real.sqrt x := by
  have hx : 0 < x := by linarith
  let n := ⌊x⌋₊
  have hnLower : 438_429 ≤ n := Nat.le_floor hxLower.le
  have hnOne : 1 ≤ n := by omega
  have hnUpper : n ≤ sourceLimit := floor_upper hx.le hxUpper
  rcases checked_full_source_claims_of_local
      hcheck evidence n (by omega) hnUpper with
    ⟨state, hrealizes, hsafe⟩
  have hleft := hsafe.2.2.2.1 hnLower
  by_cases hnTerminal : n = sourceLimit
  · have hxEq : x = (n : Real) := by
      have hnCast : (n : Real) ≤ x := Nat.floor_le hx.le
      have : x ≤ (n : Real) := by simpa [hnTerminal] using hxUpper
      linarith
    rw [squarefreeStep, show ⌊x⌋₊ = n by rfl, hxEq]
    exact squarefreeRealEndpointOfRealizes hrealizes hleft
      densityEnclosure_six_div_pi_sq
      (by norm_num)
  · have hnLt : n < sourceLimit := lt_of_le_of_ne hnUpper hnTerminal
    have hright := hsafe.2.2.2.2.1 hnLower hnLt
    apply squarefreeRealSlabOfRealizes hrealizes hleft hright
      densityEnclosure_six_div_pi_sq
      (by norm_num) hnOne
    · exact Nat.floor_le hx.le
    · simpa [n, Nat.cast_add, Nat.cast_one] using
        (Nat.lt_floor_add_one x).le

/-- The complete ordinary-real conclusion of one successful shared Hurst
campaign.  This is the package-local capstone for the four named source atoms
(the squarefree atom contains two constants). -/
structure RealSourceClaims : Prop where
  hurst : ∀ x : Real, 33 ≤ x → x ≤ sourceLimit →
    |mertensStep x| ≤ ((571 : Real) / 1_000) * Real.sqrt x
  squarefreeB1 : ∀ x : Real, (9_243 : Real) < x → x ≤ sourceLimit →
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (151 / 2_000 : Real) * Real.sqrt x
  squarefreeB2 : ∀ x : Real, (438_429 : Real) < x → x ≤ sourceLimit →
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (57 / 2_000 : Real) * Real.sqrt x
  little211 : ∀ x : Real, 1 ≤ x → x ≤ little211Limit →
    |littleMertensStep x| ≤ Real.sqrt (2 / x)
  littleStronger : ∀ x : Real, 3 ≤ x → x < littleStrongerLimit →
    |littleMertensStep x| ≤ 1 / (2 * Real.sqrt x)

/-- A checked full-range exact certificate supplies the complete real-source
capstone without any additional analytic premise. -/
theorem checked_real_source_claims
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate) :
    RealSourceClaims := {
  hurst := checked_hurst_real hcheck evidence
  squarefreeB1 := checked_squarefree_b1_real hcheck evidence
  squarefreeB2 := checked_squarefree_b2_real hcheck evidence
  little211 := checked_little211_real hcheck evidence
  littleStronger := checked_little_stronger_real hcheck evidence
}

/-- The production-shaped local replay supplies the same real-source
capstone, with global prefix semantics derived in ordinary Lean. -/
theorem checked_real_source_claims_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate) :
    RealSourceClaims := {
  hurst := checked_hurst_real_of_local hcheck evidence
  squarefreeB1 := checked_squarefree_b1_real_of_local hcheck evidence
  squarefreeB2 := checked_squarefree_b2_real_of_local hcheck evidence
  little211 := checked_little211_real_of_local hcheck evidence
  littleStronger := checked_little_stronger_real_of_local hcheck evidence
}

/-- Source-package projection used by downstream theorem consumers.

This theorem is ordinary Lean glue: it rewrites the package-local prefix
functions to the shared exact finite sums.  It does not use the execution
axiom.  A registered successful receipt reaches it only through the existing
`accepted_run_certificate_sound` boundary. -/
theorem checked_shared_real_source_claims
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence SourceRowPredicate certificate) :
    TGComputeContracts.HurstV2.RealSourceClaims := by
  refine {
    hurst := ?_
    squarefreeB1 := ?_
    squarefreeB2 := ?_
    little211 := ?_
    littleStronger := ?_
  }
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ sourceLimit := by
      simpa [TGComputeContracts.HurstV2.sourceLimit, sourceLimit] using hxUpper
    have h := checked_hurst_real hcheck evidence x hxLower hxUpper'
    rw [mertensStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.mertensStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ sourceLimit := by
      simpa [TGComputeContracts.HurstV2.sourceLimit, sourceLimit] using hxUpper
    have h := checked_squarefree_b1_real hcheck evidence x hxLower hxUpper'
    rw [squarefreeStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.squarefreeStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ sourceLimit := by
      simpa [TGComputeContracts.HurstV2.sourceLimit, sourceLimit] using hxUpper
    have h := checked_squarefree_b2_real hcheck evidence x hxLower hxUpper'
    rw [squarefreeStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.squarefreeStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ little211Limit := by
      simpa [TGComputeContracts.HurstV2.little211Limit, little211Limit] using hxUpper
    have h := checked_little211_real hcheck evidence x hxLower hxUpper'
    rw [littleMertensStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.littleMertensStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x < littleStrongerLimit := by
      simpa [TGComputeContracts.HurstV2.littleStrongerLimit,
        littleStrongerLimit] using hxUpper
    have h := checked_little_stronger_real hcheck evidence x hxLower hxUpper'
    rw [littleMertensStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.littleMertensStep] using h

/-- Shared source-package projection from the narrow production evidence. -/
theorem checked_shared_real_source_claims_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate) :
    TGComputeContracts.HurstV2.RealSourceClaims := by
  refine {
    hurst := ?_
    squarefreeB1 := ?_
    squarefreeB2 := ?_
    little211 := ?_
    littleStronger := ?_
  }
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ sourceLimit := by
      simpa [TGComputeContracts.HurstV2.sourceLimit, sourceLimit] using hxUpper
    have h := checked_hurst_real_of_local hcheck evidence x hxLower hxUpper'
    rw [mertensStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.mertensStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ sourceLimit := by
      simpa [TGComputeContracts.HurstV2.sourceLimit, sourceLimit] using hxUpper
    have h :=
      checked_squarefree_b1_real_of_local hcheck evidence x hxLower hxUpper'
    rw [squarefreeStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.squarefreeStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ sourceLimit := by
      simpa [TGComputeContracts.HurstV2.sourceLimit, sourceLimit] using hxUpper
    have h :=
      checked_squarefree_b2_real_of_local hcheck evidence x hxLower hxUpper'
    rw [squarefreeStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.squarefreeStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x ≤ little211Limit := by
      simpa [TGComputeContracts.HurstV2.little211Limit, little211Limit] using hxUpper
    have h :=
      checked_little211_real_of_local hcheck evidence x hxLower hxUpper'
    rw [littleMertensStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.littleMertensStep] using h
  · intro x hxLower hxUpper
    have hxUpper' : x < littleStrongerLimit := by
      simpa [TGComputeContracts.HurstV2.littleStrongerLimit,
        littleStrongerLimit] using hxUpper
    have h :=
      checked_little_stronger_real_of_local
        hcheck evidence x hxLower hxUpper'
    rw [littleMertensStep_eq_sourceSum] at h
    simpa [TGComputeContracts.HurstV2.littleMertensStep] using h

end SparkInterval.TernaryGoldbach.HurstSourceSemantics
