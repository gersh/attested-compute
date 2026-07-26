/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.ArithmeticFunction.VonMangoldt
import Mathlib.NumberTheory.Harmonic.EulerMascheroni

/-!
# Source semantics for the Ramaré--Zúñiga Lemma 6.2 campaign

This file fixes the exact mathematical meaning of the streamed `R2Star`
campaign.  The source coefficient and summatory function are copied literally
from the ternary-Goldbach development: the unmarked product of arithmetic
functions is Dirichlet convolution and the last term is `2γ`.

The small certificate checker proves only gap-free chunk and state chaining.
`SourceScaleEvidence` is the explicit physical boundary.  In particular, its
`coefficientRealizes` field says that every machine interval increment encloses
the actual Mathlib von-Mangoldt coefficient.  The CUDA factor-support
recurrence does not obtain that fact merely by producing a hash or a numerical
summary.

Given that explicit realization evidence, ordinary Lean proves:

* directed prefix intervals enclose the exact finite sum;
* the worker's squared integer guard implies the endpoint real inequality; and
* all integer endpoints imply the paper-shaped statement for every real
  `X ∈ [3, 21·10^9]`, including the natural-floor slab reduction.

No axiom is declared in this file and no source-scale run is claimed.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.R2StarSourceSemantics

open Finset
open scoped BigOperators ArithmeticFunction ArithmeticFunction.zeta

/-- Literal upper endpoint in Ramaré--Zúñiga Alterman, Lemma 6.2. -/
def sourceLimit : Nat := 21_000_000_000

/-- Fixed-point scale used by the production CUDA campaign. -/
def scale : Nat := 2 ^ 32

def boundNumerator : Nat := 193
def boundDenominator : Nat := 100

/-- The source coefficient `(Lambda * Lambda)(n) - Lambda(n) log n + 2 gamma`.
The first multiplication is Dirichlet convolution. -/
noncomputable def r2Coeff (n : Nat) : Real :=
  (ArithmeticFunction.vonMangoldt * ArithmeticFunction.vonMangoldt) n -
    ArithmeticFunction.vonMangoldt n * Real.log n +
      2 * Real.eulerMascheroniConstant

/-- The corrected source summatory remainder `R₂*(N)`. -/
noncomputable def r2Star (N : Nat) : Real :=
  ∑ n ∈ Finset.Icc 1 N, r2Coeff n

/-- The exact real-variable proposition cited as Ramaré--Zúñiga Alterman,
Lemma 6.2. -/
def SourceClaim : Prop :=
  ∀ X : Real, 3 ≤ X → X ≤ sourceLimit →
    |r2Star ⌊X⌋₊| ≤
      ((boundNumerator : Real) / boundDenominator) *
        Real.sqrt X * Real.log X

/-! ## Small arithmetic certificate -/

/-- Directed Q32 enclosure state after an inclusive source row. -/
structure State where
  lowerQ32 : Int
  upperQ32 : Int
  deriving Repr, DecidableEq

namespace State

def zero : State := ⟨0, 0⟩

def add (left right : State) : State :=
  ⟨left.lowerQ32 + right.lowerQ32,
    left.upperQ32 + right.upperQ32⟩

instance : Add State := ⟨add⟩

@[simp] theorem add_lowerQ32 (left right : State) :
    (left + right).lowerQ32 = left.lowerQ32 + right.lowerQ32 := rfl

@[simp] theorem add_upperQ32 (left right : State) :
    (left + right).upperQ32 = left.upperQ32 + right.upperQ32 := rfl

/-- A Q32 state encloses one exact real value. -/
def Realizes (state : State) (value : Real) : Prop :=
  (state.lowerQ32 : Real) / scale ≤ value ∧
    value ≤ (state.upperQ32 : Real) / scale

theorem zero_realizes : zero.Realizes 0 := by
  norm_num [zero, Realizes, scale]

theorem add_realizes {left right : State} {x y : Real}
    (hleft : left.Realizes x) (hright : right.Realizes y) :
    (left + right).Realizes (x + y) := by
  have hscale : (0 : Real) < scale := by norm_num [scale]
  constructor <;> simp only [Realizes] at hleft hright ⊢ <;>
    simp only [add_lowerQ32, add_upperQ32, Int.cast_add] <;>
    rw [add_div] <;> linarith

/-- Absolute integer radius used by the exact squared envelope. -/
def magnitude (state : State) : Nat :=
  max state.lowerQ32.natAbs state.upperQ32.natAbs

private theorem lower_neg_magnitude (state : State) :
    -((state.magnitude : Nat) : Int) ≤ state.lowerQ32 := by
  apply neg_le_of_abs_le
  rw [← Int.natCast_natAbs]
  exact Nat.cast_le.2 (Nat.le_max_left _ _)

private theorem upper_le_magnitude (state : State) :
    state.upperQ32 ≤ (state.magnitude : Nat) := by
  exact Int.le_natAbs.trans
    (Nat.cast_le.2 (Nat.le_max_right _ _))

/-- Every value in the directed interval is bounded by its integer radius. -/
theorem abs_le_magnitude_div {state : State} {value : Real}
    (hrealizes : state.Realizes value) :
    |value| ≤ (state.magnitude : Real) / scale := by
  have hscale : (0 : Real) < scale := by norm_num [scale]
  have hlower : (-((state.magnitude : Nat) : Int) : Real) ≤
      (state.lowerQ32 : Real) := by
    exact_mod_cast lower_neg_magnitude state
  have hupper : (state.upperQ32 : Real) ≤ state.magnitude := by
    exact_mod_cast upper_le_magnitude state
  rw [abs_le]
  constructor
  · exact le_trans (by
      rw [← neg_div]
      exact div_le_div_of_nonneg_right hlower hscale.le) hrealizes.1
  · exact hrealizes.2.trans
      (div_le_div_of_nonneg_right hupper hscale.le)

end State

/-- One half-open streamed chunk.  Hashes and timing metadata are kept in the
signed external receipt; this kernel object retains only the arithmetic state
and coverage fields used by the theorem reduction. -/
structure Chunk where
  lower : Nat
  upper : Nat
  incoming : State
  outgoing : State
  minimumSquaredSlack : Nat
  minimumSlackIndex : Nat
  deriving Repr, DecidableEq

namespace Chunk

def WellFormed (chunk : Chunk) : Prop :=
  1 ≤ chunk.lower ∧
  chunk.lower < chunk.upper ∧
  chunk.incoming.lowerQ32 ≤ chunk.incoming.upperQ32 ∧
  chunk.outgoing.lowerQ32 ≤ chunk.outgoing.upperQ32 ∧
  max 3 chunk.lower ≤ chunk.minimumSlackIndex ∧
  chunk.minimumSlackIndex < chunk.upper

instance instDecidableWellFormed (chunk : Chunk) :
    Decidable chunk.WellFormed := by
  unfold WellFormed
  infer_instance

end Chunk

/-- Exact range and boundary-state semantics of an ordered chunk list. -/
def ChainValid (sourceUpper : Nat) : Nat → State → List Chunk → Prop
  | nextLower, _, [] => nextLower = sourceUpper
  | nextLower, incoming, chunk :: rest =>
      chunk.lower = nextLower ∧
      chunk.incoming = incoming ∧
      chunk.WellFormed ∧
      ChainValid sourceUpper chunk.upper chunk.outgoing rest

structure Certificate where
  sourceLower : Nat
  sourceUpper : Nat
  rootState : State
  finalState : State
  chunks : List Chunk
  deriving Repr, DecidableEq

namespace Certificate

def ArithmeticValid (certificate : Certificate) : Prop :=
  certificate.sourceLower < certificate.sourceUpper ∧
  ChainValid certificate.sourceUpper certificate.sourceLower
    certificate.rootState certificate.chunks ∧
  certificate.chunks.getLast?.map Chunk.outgoing =
    some certificate.finalState

private def chainCheck (sourceUpper : Nat) :
    Nat → State → List Chunk → Bool
  | nextLower, _, [] => decide (nextLower = sourceUpper)
  | nextLower, incoming, chunk :: rest =>
      decide (chunk.lower = nextLower ∧ chunk.incoming = incoming ∧
        chunk.WellFormed) &&
      chainCheck sourceUpper chunk.upper chunk.outgoing rest

private theorem chainCheck_sound
    {sourceUpper nextLower : Nat} {incoming : State} {chunks : List Chunk}
    (hcheck : chainCheck sourceUpper nextLower incoming chunks = true) :
    ChainValid sourceUpper nextLower incoming chunks := by
  induction chunks generalizing nextLower incoming with
  | nil => simpa [chainCheck, ChainValid] using hcheck
  | cons chunk rest inductionHypothesis =>
      simp only [chainCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
      rw [ChainValid]
      exact ⟨hcheck.1.1, hcheck.1.2.1, hcheck.1.2.2,
        inductionHypothesis hcheck.2⟩

/-- Kernel-reducible checker for the compact chunk chain. -/
def check (certificate : Certificate) : Bool :=
  decide (certificate.sourceLower < certificate.sourceUpper) &&
    (chainCheck certificate.sourceUpper certificate.sourceLower
      certificate.rootState certificate.chunks &&
    decide (certificate.chunks.getLast?.map Chunk.outgoing =
      some certificate.finalState))

theorem checker_sound {certificate : Certificate}
    (hcheck : certificate.check = true) : certificate.ArithmeticValid := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, chainCheck_sound hcheck.2.1, hcheck.2.2⟩

def FullSourceRange (certificate : Certificate) : Prop :=
  certificate.sourceLower = 1 ∧
    certificate.sourceUpper = sourceLimit + 1

end Certificate

/-! ## Exact physical/source realization boundary -/

/-- The worker's exact squared endpoint guard.  Both prefix and logarithm are
Q32 integers, so the common scale cancels before squaring. -/
def EndpointSafe (n : Nat) (state : State) (logLowerQ32 : Nat) : Prop :=
  (boundDenominator * state.magnitude) ^ 2 ≤
    boundNumerator ^ 2 * n * logLowerQ32 ^ 2

/-- Row-level meaning of one physical chunk.

`coefficientRealizes` is the presently unclosed refinement obligation between
the segmented factor-support recurrence and Mathlib's von-Mangoldt
convolution.  It is intentionally visible here instead of being inferred from
the chunk hash or the minimum-slack summary. -/
structure ExternalChunkRealization (chunk : Chunk) where
  stateAt : Nat → State
  deltaAt : Nat → State
  logLowerQ32 : Nat → Nat
  stateAtIncoming : stateAt (chunk.lower - 1) = chunk.incoming
  stateStep : ∀ n, chunk.lower ≤ n → n < chunk.upper →
    stateAt n = stateAt (n - 1) + deltaAt n
  stateAtOutgoing : stateAt (chunk.upper - 1) = chunk.outgoing
  coefficientRealizes : ∀ n, chunk.lower ≤ n → n < chunk.upper →
    (deltaAt n).Realizes (r2Coeff n)
  logLowerRealizes : ∀ n, chunk.lower ≤ n → n < chunk.upper →
    ((logLowerQ32 n : Nat) : Real) / scale ≤ Real.log n
  endpointSafe : ∀ n, chunk.lower ≤ n → n < chunk.upper → 3 ≤ n →
    EndpointSafe n (stateAt n) (logLowerQ32 n)

/-- The retained source-scale campaign must supply a realization for every
chunk in the checked arithmetic certificate. -/
structure SourceScaleEvidence (certificate : Certificate) where
  fullRange : certificate.FullSourceRange
  rootState : certificate.rootState = State.zero
  physical : ∀ chunk, chunk ∈ certificate.chunks →
    ExternalChunkRealization chunk

/-! ## Prefix and endpoint soundness -/

@[simp] theorem r2Star_zero : r2Star 0 = 0 := by
  simp [r2Star]

theorem r2Star_succ (n : Nat) :
    r2Star (n + 1) = r2Star n + r2Coeff (n + 1) := by
  unfold r2Star
  rw [show Finset.Icc 1 (n + 1) = insert (n + 1) (Finset.Icc 1 n) by
      ext k
      simp only [Finset.mem_Icc, Finset.mem_insert]
      omega,
    Finset.sum_insert]
  · ring
  · simp

private theorem ExternalChunkRealization.state_realizes
    {chunk : Chunk} (evidence : ExternalChunkRealization chunk)
    (hwell : chunk.WellFormed)
    (hincoming : chunk.incoming.Realizes (r2Star (chunk.lower - 1))) :
    ∀ n, chunk.lower ≤ n → n < chunk.upper →
      (evidence.stateAt n).Realizes (r2Star n) := by
  intro n hnLower hnUpper
  induction n, hnLower using Nat.le_induction with
  | base =>
      have hlowerOne : 1 ≤ chunk.lower := hwell.1
      have hlowerPos : 0 < chunk.lower := by omega
      have hpredSucc : chunk.lower - 1 + 1 = chunk.lower := by omega
      rw [evidence.stateStep chunk.lower (by rfl) hnUpper,
        evidence.stateAtIncoming]
      have hadd := State.add_realizes hincoming
        (evidence.coefficientRealizes chunk.lower (by rfl) hnUpper)
      have hstar :
          r2Star chunk.lower =
            r2Star (chunk.lower - 1) + r2Coeff chunk.lower := by
        calc
          r2Star chunk.lower = r2Star (chunk.lower - 1 + 1) := by rw [hpredSucc]
          _ = r2Star (chunk.lower - 1) +
              r2Coeff (chunk.lower - 1 + 1) := r2Star_succ _
          _ = r2Star (chunk.lower - 1) + r2Coeff chunk.lower := by rw [hpredSucc]
      rw [hstar]
      exact hadd
  | succ n hnLowerN inductionHypothesis =>
      have hnUpper' : n < chunk.upper := by omega
      have hnSuccUpper : n + 1 < chunk.upper := by omega
      rw [evidence.stateStep (n + 1) (by omega) hnSuccUpper,
        show n + 1 - 1 = n by omega, r2Star_succ]
      exact State.add_realizes (inductionHypothesis hnUpper')
        (evidence.coefficientRealizes (n + 1) (by omega) hnSuccUpper)

private theorem endpoint_of_realizes_safe
    {n logLowerQ32 : Nat} {state : State}
    (hn : 3 ≤ n)
    (hrealizes : state.Realizes (r2Star n))
    (hlog : (logLowerQ32 : Real) / scale ≤ Real.log n)
    (hsafe : EndpointSafe n state logLowerQ32) :
    |r2Star n| ≤
      ((boundNumerator : Real) / boundDenominator) *
        Real.sqrt n * Real.log n := by
  let magnitude : Real := state.magnitude
  let logarithm : Real := logLowerQ32
  have hscale : (0 : Real) < scale := by norm_num [scale]
  have hn0 : (0 : Real) ≤ n := by positivity
  have hsqrt0 : (0 : Real) ≤ Real.sqrt n := Real.sqrt_nonneg _
  have hsqrtSq : (Real.sqrt (n : Real)) ^ 2 = n := Real.sq_sqrt hn0
  have hmag0 : 0 ≤ magnitude := by positivity
  have hlogarithm0 : 0 ≤ logarithm := by positivity
  have hsafeReal :
      ((boundDenominator : Real) * magnitude) ^ 2 ≤
        ((boundNumerator : Real) * Real.sqrt n * logarithm) ^ 2 := by
    have hcast :
        (((boundDenominator * state.magnitude) ^ 2 : Nat) : Real) ≤
          ((boundNumerator ^ 2 * n * logLowerQ32 ^ 2 : Nat) : Real) := by
      exact_mod_cast hsafe
    push_cast at hcast
    calc
      ((boundDenominator : Real) * magnitude) ^ 2 ≤
          (boundNumerator : Real) ^ 2 * n * logarithm ^ 2 := by
        simpa [magnitude, logarithm] using hcast
      _ = ((boundNumerator : Real) * Real.sqrt n * logarithm) ^ 2 := by
        rw [mul_pow, mul_pow, hsqrtSq]
  have hlinear :
      (boundDenominator : Real) * magnitude ≤
        (boundNumerator : Real) * Real.sqrt n * logarithm :=
    (sq_le_sq₀ (by positivity) (by positivity)).mp hsafeReal
  have hmagnitude :
      |r2Star n| ≤ magnitude / scale := by
    simpa [magnitude] using State.abs_le_magnitude_div hrealizes
  have hfixed :
      magnitude / scale ≤
        ((boundNumerator : Real) / boundDenominator) *
          Real.sqrt n * (logarithm / scale) := by
    have hden : (0 : Real) < boundDenominator := by norm_num [boundDenominator]
    have hquotient :
        magnitude ≤
          ((boundNumerator : Real) * Real.sqrt n * logarithm) /
            boundDenominator := by
      apply (le_div_iff₀ hden).2
      simpa [mul_comm] using hlinear
    calc
      magnitude / scale ≤
          (((boundNumerator : Real) * Real.sqrt n * logarithm) /
            boundDenominator) / scale :=
        div_le_div_of_nonneg_right hquotient hscale.le
      _ = ((boundNumerator : Real) / boundDenominator) *
          Real.sqrt n * (logarithm / scale) := by
        field_simp
  have hlog0 : 0 ≤ Real.log (n : Real) :=
    Real.log_nonneg (by exact_mod_cast (show 1 ≤ n by omega))
  calc
    |r2Star n| ≤ magnitude / scale := hmagnitude
    _ ≤ ((boundNumerator : Real) / boundDenominator) *
        Real.sqrt n * (logarithm / scale) := hfixed
    _ ≤ ((boundNumerator : Real) / boundDenominator) *
        Real.sqrt n * Real.log n := by
      exact mul_le_mul_of_nonneg_left hlog (by positivity)

private theorem chain_endpoint
    {sourceUpper nextLower : Nat} {incoming : State} {chunks : List Chunk}
    (hchain : ChainValid sourceUpper nextLower incoming chunks)
    (hphysical : ∀ chunk, chunk ∈ chunks → ExternalChunkRealization chunk)
    (hincoming : incoming.Realizes (r2Star (nextLower - 1))) :
    ∀ n, nextLower ≤ n → n < sourceUpper → 3 ≤ n →
      |r2Star n| ≤
        ((boundNumerator : Real) / boundDenominator) *
          Real.sqrt n * Real.log n := by
  induction chunks generalizing nextLower incoming with
  | nil =>
      intro n hnLower hnUpper _
      simp only [ChainValid] at hchain
      omega
  | cons chunk rest inductionHypothesis =>
      rw [ChainValid] at hchain
      rcases hchain with ⟨hlower, hin, hwell, hrest⟩
      intro n hnLower hnUpper hnThree
      let evidence := hphysical chunk (by simp)
      by_cases hnChunk : n < chunk.upper
      · have hchunkLower : chunk.lower ≤ n := by simpa [hlower] using hnLower
        have hincoming' :
            chunk.incoming.Realizes (r2Star (chunk.lower - 1)) := by
          simpa [hlower, hin] using hincoming
        have hrealizes := evidence.state_realizes hwell hincoming'
          n hchunkLower hnChunk
        exact endpoint_of_realizes_safe hnThree hrealizes
          (evidence.logLowerRealizes n hchunkLower hnChunk)
          (evidence.endpointSafe n hchunkLower hnChunk hnThree)
      · have hchunkLt : chunk.lower < chunk.upper := hwell.2.1
        have hupperPos : 0 < chunk.upper := by omega
        have hlastLower : chunk.lower ≤ chunk.upper - 1 := by omega
        have hlastUpper : chunk.upper - 1 < chunk.upper := by omega
        have hincoming' :
            chunk.incoming.Realizes (r2Star (chunk.lower - 1)) := by
          simpa [hlower, hin] using hincoming
        have houtgoing :
            chunk.outgoing.Realizes (r2Star (chunk.upper - 1)) := by
          rw [← evidence.stateAtOutgoing]
          exact evidence.state_realizes hwell hincoming'
            (chunk.upper - 1) hlastLower hlastUpper
        exact inductionHypothesis hrest
          (fun tailChunk hmem => hphysical tailChunk (by simp [hmem]))
          houtgoing n (by omega) hnUpper hnThree

/-- A checked gap-free source certificate plus explicit recurrence realization
proves every natural endpoint used by Lemma 6.2. -/
theorem checked_integer_endpoints
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) :
    ∀ n, 3 ≤ n → n ≤ sourceLimit →
      |r2Star n| ≤
        ((boundNumerator : Real) / boundDenominator) *
          Real.sqrt n * Real.log n := by
  have hvalid := Certificate.checker_sound hcheck
  intro n hnLower hnUpper
  apply chain_endpoint hvalid.2.1 evidence.physical ?_ n ?_ ?_ hnLower
  · rw [evidence.rootState, evidence.fullRange.1]
    simpa using State.zero_realizes
  · simpa [evidence.fullRange.1] using (show 1 ≤ n by omega)
  · rw [evidence.fullRange.2]
    omega

private theorem floor_upper {X : Real} {limit : Nat}
    (hX0 : 0 ≤ X) (hX : X ≤ limit) : ⌊X⌋₊ ≤ limit := by
  exact_mod_cast (Nat.floor_le hX0).trans hX

/-- The complete ordinary Lean reduction from source-scale streamed evidence
to the source-shaped real proposition. -/
theorem sourceClaim_of_checked_certificate
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) : SourceClaim := by
  intro X hXLower hXUpper
  let n := ⌊X⌋₊
  have hX0 : 0 ≤ X := by linarith
  have hnLower : 3 ≤ n := Nat.le_floor
    (show ((3 : Nat) : Real) ≤ X by simpa using hXLower)
  have hnUpper : n ≤ sourceLimit := floor_upper hX0 hXUpper
  have hnX : (n : Real) ≤ X := Nat.floor_le hX0
  have hendpoint := checked_integer_endpoints hcheck evidence n hnLower hnUpper
  have hsqrt : Real.sqrt n ≤ Real.sqrt X := Real.sqrt_le_sqrt hnX
  have hnPos : (0 : Real) < n := by positivity
  have hlog : Real.log n ≤ Real.log X := Real.log_le_log hnPos hnX
  have hlogn0 : (0 : Real) ≤ Real.log n :=
    Real.log_nonneg (by exact_mod_cast (show 1 ≤ n by omega))
  have hlogX0 : (0 : Real) ≤ Real.log X := hlogn0.trans hlog
  calc
    |r2Star ⌊X⌋₊| = |r2Star n| := rfl
    _ ≤ ((boundNumerator : Real) / boundDenominator) *
        Real.sqrt n * Real.log n := hendpoint
    _ ≤ ((boundNumerator : Real) / boundDenominator) *
        Real.sqrt X * Real.log X := by
      apply mul_le_mul
      · exact mul_le_mul_of_nonneg_left hsqrt (by positivity)
      · exact hlog
      · positivity
      · positivity

end SparkInterval.TernaryGoldbach.R2StarSourceSemantics
