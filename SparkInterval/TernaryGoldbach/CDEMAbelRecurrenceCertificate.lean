/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CDEMAbelSource

/-!
# Kernel-checked recurrence bridge for the CDEM Abel scan

`CDEMAbelSource.ScaledOutputClaim` is the final real proposition, but the
external program does not evaluate those real finite sums directly.  It
marks the integer jumps

`delta(n) = sum_(1 <= d <= K, d | n) mu(d)`

and scans the exact floor state

`F(n) = sum_(1 <= d <= K) mu(d) * floor(n / d)`.

This file makes that intermediate boundary explicit.  A compact certificate
checks gap-free chunk coverage, incoming-state continuity, and reduction of
the two integer chunk totals.  `Chunk.LocallyRealizes` is the narrow physical
interface: it starts from the transcript's `before` field, advances by the
closed `floorJump` recurrence, requires the resulting terminal state to be
the transcript's `after` field, and identifies the two retained totals with
folds of consecutive *local* error increments.  It never states a global
`floorState` or source `errorIncrement` equality.

`LocalSourceScaleEvidence` supplies those local witnesses.  Ordinary Lean
then uses `ChainValid`'s initial zero and adjacent state equalities together
with `floorState_jump` to prove every local state equals the closed global
state, and transports the local folds to `Chunk.Realizes`.

The older, broader `SourceScaleEvidence` interface is retained as an off-path
compatibility API.  For a checked certificate the two interfaces are
theorem-equivalent:

* `sourceScaleEvidence_of_local` is the narrow-to-global proof used by the
  new local theorem;
* `localSourceScaleEvidence_of_source` is the explicit compatibility path
  for an existing global witness; and
* `scaledOutputClaim_of_checked_certificate` keeps its old public signature
  and routes through that compatibility path.

The closed registered relation now targets `LocalSourceScaleEvidence`
directly.  Its pre-release definition hash was refreshed, and no accepted
receipt exists under the former meaning.  Endpoints alone still cannot
determine the internally weighted Abel totals, so the local fold equalities
remain the physical evidence boundary.

Ordinary Lean proves all remaining steps:

* the divisor marker is the discrete derivative of `F`;
* `F` is the source table's `floorSum` below the inactive periodizer;
* the integer error is exactly the source `errorSequence`, including
  `errorSequence 0 = 0`;
* sign-directed integer division bounds every signed Abel term;
* the square guards bound every absolute Abel term;
* the checked chunk chain partitions every index in `1 .. 5,000,000,000`
  exactly once; and
* the two checked integer reductions imply `ScaledOutputClaim`.

There is no axiom, `sorry`, `native_decide`, or machine-code refinement
theorem in this module.  The current registered execution exposes
`Nonempty (LocalSourceScaleEvidence certificate)` plus
`certificate.check = true`; it never asserts `ScaledOutputClaim` itself.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate

open Finset
open scoped BigOperators

/- A short local namespace keeps the formulas readable without changing the
source definitions: every entry below is a transparent abbreviation. -/
namespace Source

abbrev prefixUpper : Nat := CDEMAbelSource.prefixUpper
abbrev indexUpper : Nat := CDEMAbelSource.indexUpper
abbrev periodizer : Nat := CDEMAbelSource.periodizer
abbrev weightScale : Nat := CDEMAbelSource.weightScale
abbrev signedTarget : Nat := CDEMAbelSource.signedTarget
abbrev absoluteTarget : Nat := CDEMAbelSource.absoluteTarget
noncomputable abbrev coefficient (d : Nat) : Real :=
  CDEMAbelSource.coefficient d
noncomputable abbrev denominator (d : Nat) : Real :=
  CDEMAbelSource.denominator d
abbrev support : Finset Nat := CDEMAbelSource.support
noncomputable abbrev floorSum (y : Real) : Real :=
  CDEMAbelSource.floorSum y
noncomputable abbrev errorSequence (n : Nat) : Real :=
  CDEMAbelSource.errorSequence n
noncomputable abbrev signedIncrement : Real :=
  CDEMAbelSource.signedIncrement
noncomputable abbrev absoluteIncrement : Real :=
  CDEMAbelSource.absoluteIncrement
abbrev ScaledOutputClaim (signedNumerator absoluteNumerator : Nat) : Prop :=
  CDEMAbelSource.ScaledOutputClaim signedNumerator absoluteNumerator
abbrev SourceClaim : Prop := CDEMAbelSource.SourceClaim

theorem sourceClaim_of_scaledOutput
    (h : ScaledOutputClaim signedTarget absoluteTarget) : SourceClaim :=
  CDEMAbelSource.sourceClaim_of_scaledOutput h

end Source

private theorem weightScale_pos : 0 < Source.weightScale := by
  change 0 < CDEMAbelSource.weightScale
  norm_num [CDEMAbelSource.weightScale]

private theorem weightScale_real_pos :
    (0 : Real) < (Source.weightScale : Real) := by
  exact_mod_cast weightScale_pos

private theorem prefixUpper_lt_periodizer :
    Source.prefixUpper < Source.periodizer := by
  change CDEMAbelSource.prefixUpper < CDEMAbelSource.periodizer
  norm_num [CDEMAbelSource.prefixUpper, CDEMAbelSource.periodizer,
    CDEMAbelSource.indexUpper]

private theorem indexUpper_lt_periodizer :
    Source.indexUpper < Source.periodizer := by
  change CDEMAbelSource.indexUpper < CDEMAbelSource.periodizer
  simp [CDEMAbelSource.periodizer]

/-! ## Closed integer recurrence -/

/-- Exclusive upper endpoint of the source scan. -/
def sourcePast : Nat := Source.indexUpper + 1

/-- Exact integer floor state represented by the C++ recurrence. -/
def floorState (n : Nat) : Int :=
  ∑ d ∈ Finset.Icc 1 Source.prefixUpper,
    ArithmeticFunction.moebius d * (n / d : Nat)

/-- Exact divisor-marker jump used by both reviewed C++ implementations. -/
def floorJump (n : Nat) : Int :=
  ∑ d ∈ Finset.Icc 1 Source.prefixUpper,
    if d ∣ n then ArithmeticFunction.moebius d else 0

/-- Executable form of the source's overridden error sequence. -/
def errorState (n : Nat) : Nat :=
  if n = 0 then 0 else (1 - floorState n).natAbs

/-- The source error rule evaluated at an explicitly supplied floor state.
This lets a chunk compute its errors before that state has been identified
with the global `floorState`. -/
def errorAtState (n : Nat) (state : Int) : Nat :=
  if n = 0 then 0 else (1 - state).natAbs

/-- Signed error increment at one positive source index. -/
def errorIncrement (n : Nat) : Int :=
  (errorState n : Int) - (errorState (n - 1) : Int)

@[simp] theorem errorAtState_floorState (n : Nat) :
    errorAtState n (floorState n) = errorState n := by
  rfl

/-- A floor quotient increases exactly at a multiple of its denominator. -/
theorem natCast_div_sub_pred (n denominator : Nat) (hn : 0 < n) :
    ((n / denominator : Nat) : Int) -
        (((n - 1) / denominator : Nat) : Int) =
      if denominator ∣ n then 1 else 0 := by
  have hstep := Nat.succ_div (a := n - 1) (b := denominator)
  have hnstep : n - 1 + 1 = n := by omega
  rw [hnstep] at hstep
  rw [hstep]
  by_cases hdiv : denominator ∣ n <;> simp [hdiv]

/-- The source-shaped floor state has exactly the divisor-marker recurrence
implemented by the producer and independent chunk replayer. -/
theorem floorState_jump (n : Nat) (hn : 0 < n) :
    floorState n - floorState (n - 1) = floorJump n := by
  rw [floorState, floorState, floorJump, ← Finset.sum_sub_distrib]
  apply Finset.sum_congr rfl
  intro d _hd
  calc
    ArithmeticFunction.moebius d * (n / d : Nat) -
          ArithmeticFunction.moebius d * ((n - 1) / d : Nat) =
        ArithmeticFunction.moebius d *
          (((n / d : Nat) : Int) -
            (((n - 1) / d : Nat) : Int)) := by ring
    _ = ArithmeticFunction.moebius d *
          (if d ∣ n then 1 else 0) := by
      rw [natCast_div_sub_pred n d hn]
    _ = if d ∣ n then ArithmeticFunction.moebius d else 0 := by
      split <;> simp

@[simp] theorem floorState_zero : floorState 0 = 0 := by
  simp [floorState]

/-! ## Directed integer weights -/

/-- Integer ceiling division, matching the two reviewed C++ sources. -/
def ceilDiv (a b : Nat) : Nat := a ⌈/⌉ b

/-- One sign-directed fixed-point contribution to the signed Abel sum. -/
def signedTermUpper (n : Nat) (increment : Int) : Int :=
  if 0 < increment then increment * (ceilDiv Source.weightScale n : Nat)
  else if increment < 0 then
    increment * (Source.weightScale / n : Nat)
  else 0

/-- One externally retained reciprocal-square-root weight is admissible
exactly when its integer square proves the required directed inequality. -/
def SqrtWeightValid (n q : Nat) : Prop :=
  Source.weightScale * Source.weightScale ≤ q * q * n

/-- A valid reciprocal-square-root guard cannot occur at index zero. -/
theorem index_pos_of_sqrtWeightValid {n q : Nat}
    (hvalid : SqrtWeightValid n q) : 0 < n := by
  by_contra hn
  have hnZero : n = 0 := Nat.eq_zero_of_not_pos hn
  subst n
  norm_num [SqrtWeightValid, CDEMAbelSource.weightScale] at hvalid

/-- One fixed-point contribution to the absolute Abel sum. -/
def absoluteTermUpper (q : Nat) (increment : Int) : Nat :=
  increment.natAbs * q

theorem le_ceilDiv_mul (a b : Nat) (hb : 0 < b) :
    a ≤ ceilDiv a b * b := by
  have h := le_smul_ceilDiv (α := Nat) (β := Nat) hb (b := a)
  simpa [ceilDiv, Nat.mul_comm] using h

/-- Positive increments use `ceil(scale/n)`. -/
theorem positiveWeight_sound (n : Nat) (hn : 0 < n) :
    1 / (n : Real) ≤
      (ceilDiv Source.weightScale n : Nat) /
        (Source.weightScale : Real) := by
  have hscale :
      (0 : Real) < (Source.weightScale : Real) :=
    weightScale_real_pos
  have hnReal : (0 : Real) < (n : Real) := by exact_mod_cast hn
  rw [div_le_div_iff₀ hnReal hscale]
  exact_mod_cast le_ceilDiv_mul Source.weightScale n hn

/-- Negative increments use `floor(scale/n)`; multiplication by a
nonpositive increment reverses the weight inequality. -/
theorem negativeWeight_sound (n : Nat) (hn : 0 < n)
    {increment : Real} (hinc : increment ≤ 0) :
    increment / (n : Real) ≤
      increment * ((Source.weightScale / n : Nat) : Real) /
        (Source.weightScale : Real) := by
  have hfloor :
      (((Source.weightScale / n : Nat) : Real) /
          (Source.weightScale : Real)) ≤ 1 / (n : Real) := by
    rw [div_le_div_iff₀ weightScale_real_pos
      (by exact_mod_cast hn : (0 : Real) < (n : Real))]
    exact_mod_cast Nat.div_mul_le_self Source.weightScale n
  have hmul := mul_le_mul_of_nonpos_left hfloor hinc
  calc
    increment / (n : Real) =
        increment * (1 / (n : Real)) := by ring
    _ ≤ increment *
        (((Source.weightScale / n : Nat) : Real) /
          (Source.weightScale : Real)) := hmul
    _ = increment * ((Source.weightScale / n : Nat) : Real) /
        (Source.weightScale : Real) := by ring

/-- One signed recurrence term is bounded by its exact directed integer
contribution. -/
theorem signedTermUpper_sound (n : Nat) (increment : Int) (hn : 0 < n) :
    (increment : Real) / (n : Real) ≤
      (signedTermUpper n increment : Real) /
        (Source.weightScale : Real) := by
  unfold signedTermUpper
  by_cases hp : 0 < increment
  · rw [if_pos hp]
    have hweight := positiveWeight_sound n hn
    have hinc : (0 : Real) ≤ increment := by exact_mod_cast hp.le
    calc
      (increment : Real) / (n : Real) =
          (increment : Real) * (1 / (n : Real)) := by ring
      _ ≤ (increment : Real) *
          ((ceilDiv Source.weightScale n : Nat) /
            (Source.weightScale : Real)) :=
        mul_le_mul_of_nonneg_left hweight hinc
      _ = ((increment * (ceilDiv Source.weightScale n : Nat) : Int) :
          Real) / (Source.weightScale : Real) := by
        push_cast
        ring
  · rw [if_neg hp]
    by_cases hninc : increment < 0
    · rw [if_pos hninc]
      simpa only [Int.cast_natCast, Int.cast_mul] using
        (negativeWeight_sound n hn
          (increment := (increment : Real))
          (by exact_mod_cast hninc.le))
    · rw [if_neg hninc]
      have hz : increment = 0 := by omega
      simp [hz]

/-- An integer square guard is sufficient for a directed real
reciprocal-square-root weight. -/
theorem reciprocalSqrt_le_scaledWeight
    (n q : Nat) (hn : 0 < n) (hvalid : SqrtWeightValid n q) :
    1 / Real.sqrt (n : Real) ≤
      (q : Real) / (Source.weightScale : Real) := by
  have hscale :
      (0 : Real) < (Source.weightScale : Real) :=
    weightScale_real_pos
  have hnReal : (0 : Real) < (n : Real) := by exact_mod_cast hn
  have hsqrt : 0 < Real.sqrt (n : Real) := Real.sqrt_pos.2 hnReal
  have hreal :
      (Source.weightScale : Real) * (Source.weightScale : Real) ≤
        (q : Real) * (q : Real) * (n : Real) := by
    exact_mod_cast hvalid
  have hsquares :
      (Source.weightScale : Real) ^ 2 ≤
        ((q : Real) * Real.sqrt (n : Real)) ^ 2 := by
    rw [pow_two, pow_two]
    calc
      (Source.weightScale : Real) * (Source.weightScale : Real) ≤
          (q : Real) * (q : Real) * (n : Real) := hreal
      _ = (q : Real) * (q : Real) *
          (Real.sqrt (n : Real) * Real.sqrt (n : Real)) := by
        rw [Real.mul_self_sqrt hnReal.le]
      _ = ((q : Real) * Real.sqrt (n : Real)) *
          ((q : Real) * Real.sqrt (n : Real)) := by ring
  have hlinear :
      (Source.weightScale : Real) ≤
        (q : Real) * Real.sqrt (n : Real) :=
    (sq_le_sq₀ hscale.le (mul_nonneg (by positivity) hsqrt.le)).mp hsquares
  rw [div_le_div_iff₀ hsqrt hscale]
  simpa using hlinear

/-- One absolute recurrence term is bounded by its square-guarded integer
contribution. -/
theorem absoluteTermUpper_sound
    (n q : Nat) (increment : Int) (hn : 0 < n)
    (hvalid : SqrtWeightValid n q) :
    |(increment : Real)| / Real.sqrt (n : Real) ≤
      (absoluteTermUpper q increment : Nat) /
        (Source.weightScale : Real) := by
  have hweight := reciprocalSqrt_le_scaledWeight n q hn hvalid
  have hinc : (0 : Real) ≤ increment.natAbs := by positivity
  calc
    |(increment : Real)| / Real.sqrt (n : Real) =
        (increment.natAbs : Real) *
          (1 / Real.sqrt (n : Real)) := by
      rw [← Int.cast_abs, Nat.cast_natAbs]
      ring
    _ ≤ (increment.natAbs : Real) *
        ((q : Real) / (Source.weightScale : Real)) :=
      mul_le_mul_of_nonneg_left hweight hinc
    _ = (absoluteTermUpper q increment : Nat) /
        (Source.weightScale : Real) := by
      unfold absoluteTermUpper
      push_cast
      ring

/-! ## Compact chunk certificate -/

/-- One inclusive source chunk retained by the production transcript.
`variation` is deliberately absent because no source theorem consumes it. -/
structure Chunk where
  low : Nat
  high : Nat
  before : Int
  after : Int
  signedUpper : Int
  absoluteUpper : Nat
  deriving Repr, DecidableEq

namespace Chunk

def WellFormed (chunk : Chunk) : Prop :=
  chunk.low ≤ chunk.high ∧ chunk.high < sourcePast

instance instDecidableWellFormed (chunk : Chunk) :
    Decidable chunk.WellFormed := by
  unfold WellFormed
  infer_instance

/-- Number of recurrence events in the inclusive chunk interval. -/
def eventCount (chunk : Chunk) : Nat :=
  chunk.high + 1 - chunk.low

/-- Local recurrence state after `offset` events.  Offset zero is exactly the
retained incoming state; successor offsets apply the closed divisor marker at
`chunk.low + offset`. -/
def localFloorState (chunk : Chunk) : Nat → Int
  | 0 => chunk.before
  | offset + 1 =>
      localFloorState chunk offset + floorJump (chunk.low + offset)

/-- Local error increment at source index `n`.  Membership in the chunk
interval is imposed by `LocallyRealizes`; the definition itself stays total
and executable. -/
def localErrorIncrement (chunk : Chunk) (n : Nat) : Int :=
  (errorAtState n
      (chunk.localFloorState (n - chunk.low + 1)) : Int) -
    (errorAtState (n - 1)
      (chunk.localFloorState (n - chunk.low)) : Int)

/-- Minimal physical meaning of one replayed chunk.

Only local recurrence states occur here.  In particular, this proposition
does not mention `floorState` or `errorIncrement`.  The endpoint equality and
the two local folds are exactly the evidence that a bounded replay can emit;
global source semantics are derived later from the checked chain. -/
def LocallyRealizes (chunk : Chunk) : Prop :=
  chunk.after = chunk.localFloorState chunk.eventCount ∧
  ∃ sqrtWeight : Nat → Nat,
    (∀ n, n ∈ Finset.Ico chunk.low (chunk.high + 1) →
      SqrtWeightValid n (sqrtWeight n)) ∧
    chunk.signedUpper =
      ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        signedTermUpper n (chunk.localErrorIncrement n) ∧
    chunk.absoluteUpper =
      ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        absoluteTermUpper (sqrtWeight n) (chunk.localErrorIncrement n)

/-- Exact mathematical meaning of one externally replayed chunk.

The premise contains no real Abel sum.  It binds the transcript's incoming
and outgoing states to the closed Möbius floor state, binds the signed total
to the closed sign-directed integer fold, and binds the absolute total to
integer weights carrying explicit square guards. -/
def Realizes (chunk : Chunk) : Prop :=
  chunk.before = floorState (chunk.low - 1) ∧
  chunk.after = floorState chunk.high ∧
  ∃ sqrtWeight : Nat → Nat,
    (∀ n, n ∈ Finset.Ico chunk.low (chunk.high + 1) →
      SqrtWeightValid n (sqrtWeight n)) ∧
    chunk.signedUpper =
      ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        signedTermUpper n (errorIncrement n) ∧
    chunk.absoluteUpper =
      ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        absoluteTermUpper (sqrtWeight n) (errorIncrement n)

end Chunk

/-- Gap-free half-open chunk topology with exact incoming-state continuity. -/
def ChainValid : Nat → Int → List Chunk → Prop
  | nextLow, _nextBefore, [] => nextLow = sourcePast
  | nextLow, nextBefore, chunk :: rest =>
      chunk.low = nextLow ∧
      chunk.WellFormed ∧
      chunk.before = nextBefore ∧
      ChainValid (chunk.high + 1) chunk.after rest

instance instDecidableChainValid
    (nextLow : Nat) (nextBefore : Int) (chunks : List Chunk) :
    Decidable (ChainValid nextLow nextBefore chunks) := by
  induction chunks generalizing nextLow nextBefore with
  | nil =>
      simp only [ChainValid]
      infer_instance
  | cons chunk rest inductionHypothesis =>
      simp only [ChainValid]
      letI := inductionHypothesis (chunk.high + 1) chunk.after
      infer_instance

structure Certificate where
  signedNumerator : Nat
  absoluteNumerator : Nat
  chunks : List Chunk
  deriving Repr, DecidableEq

namespace Certificate

def signedTotal (certificate : Certificate) : Int :=
  (certificate.chunks.map Chunk.signedUpper).sum

def absoluteTotal (certificate : Certificate) : Nat :=
  (certificate.chunks.map Chunk.absoluteUpper).sum

/-- The kernel-checkable part of the transcript: exact coverage, state
continuity, and conservative reduction to the returned numerator pair. -/
def ArithmeticValid (certificate : Certificate) : Prop :=
  ChainValid 1 0 certificate.chunks ∧
  certificate.signedTotal ≤ (certificate.signedNumerator : Int) ∧
  certificate.absoluteTotal ≤ certificate.absoluteNumerator

instance instDecidableArithmeticValid (certificate : Certificate) :
    Decidable certificate.ArithmeticValid := by
  unfold ArithmeticValid signedTotal absoluteTotal
  infer_instance

def check (certificate : Certificate) : Bool :=
  decide certificate.ArithmeticValid

theorem check_sound {certificate : Certificate}
    (hcheck : certificate.check = true) :
    certificate.ArithmeticValid := by
  exact of_decide_eq_true hcheck

end Certificate

/-- Established global physical interface retained for off-path
compatibility.

`physical` attests the closed per-chunk folds directly.  New materializers
should instead construct `LocalSourceScaleEvidence`; for a checked chain,
ordinary Lean converts between the interfaces in both directions. -/
structure SourceScaleEvidence (certificate : Certificate) : Prop where
  physical :
    ∀ chunk, chunk ∈ certificate.chunks → chunk.Realizes

/-- Narrow source-scale evidence emitted by a local recurrence replay.

Unlike `SourceScaleEvidence`, this structure does not assume that a chunk
already agrees with the global source state.  That fact is recovered from the
checked gap-free chain. -/
structure LocalSourceScaleEvidence (certificate : Certificate) : Prop where
  localPhysical :
    ∀ chunk, chunk ∈ certificate.chunks → chunk.LocallyRealizes

/-! ## Local recurrence transport -/

/-- Advancing the local recurrence from a globally identified incoming state
reconstructs the closed global floor state at every offset. -/
theorem Chunk.localFloorState_eq_floorState
    (chunk : Chunk)
    (hlow : 0 < chunk.low)
    (hbefore : chunk.before = floorState (chunk.low - 1))
    (offset : Nat) :
    chunk.localFloorState offset =
      floorState (chunk.low + offset - 1) := by
  induction offset with
  | zero =>
      simpa [Chunk.localFloorState] using hbefore
  | succ offset inductionHypothesis =>
      simp only [Chunk.localFloorState]
      rw [inductionHypothesis]
      rw [show chunk.low + (offset + 1) - 1 =
        chunk.low + offset by omega]
      have hjump :=
        floorState_jump (chunk.low + offset) (by omega)
      omega

/-- On a chunk interval, a local error increment becomes the closed source
increment once the incoming state is globally identified. -/
theorem Chunk.localErrorIncrement_eq_errorIncrement
    (chunk : Chunk)
    (hlow : 0 < chunk.low)
    (hbefore : chunk.before = floorState (chunk.low - 1))
    {n : Nat}
    (hn : n ∈ Finset.Ico chunk.low (chunk.high + 1)) :
    chunk.localErrorIncrement n = errorIncrement n := by
  have hnLow : chunk.low ≤ n := (Finset.mem_Ico.mp hn).1
  have hcurrentIndex :
      chunk.low + (n - chunk.low + 1) - 1 = n := by
    omega
  have hpreviousIndex :
      chunk.low + (n - chunk.low) - 1 = n - 1 := by
    omega
  have hcurrentState :=
    chunk.localFloorState_eq_floorState hlow hbefore
      (n - chunk.low + 1)
  have hpreviousState :=
    chunk.localFloorState_eq_floorState hlow hbefore
      (n - chunk.low)
  unfold Chunk.localErrorIncrement
  rw [hcurrentState, hpreviousState, hcurrentIndex, hpreviousIndex]
  simp only [errorAtState_floorState, errorIncrement]

/-- One local replay witness transports to the older global witness once its
incoming state is known. -/
theorem Chunk.realizes_of_locallyRealizes
    {chunk : Chunk}
    (hlow : 0 < chunk.low)
    (hwell : chunk.WellFormed)
    (hbefore : chunk.before = floorState (chunk.low - 1))
    (hlocal : chunk.LocallyRealizes) :
    chunk.Realizes := by
  rcases hlocal with
    ⟨hafterLocal, sqrtWeight, hweights, hsignedLocal, habsoluteLocal⟩
  have hlowHigh : chunk.low ≤ chunk.high := hwell.1
  have hendpoint :
      chunk.low + chunk.eventCount - 1 = chunk.high := by
    unfold Chunk.eventCount
    omega
  have hstateHigh :=
    chunk.localFloorState_eq_floorState hlow hbefore chunk.eventCount
  have hafterGlobal : chunk.after = floorState chunk.high := by
    calc
      chunk.after = chunk.localFloorState chunk.eventCount := hafterLocal
      _ = floorState (chunk.low + chunk.eventCount - 1) := hstateHigh
      _ = floorState chunk.high := by rw [hendpoint]
  refine ⟨hbefore, hafterGlobal, sqrtWeight, hweights, ?_, ?_⟩
  · calc
      chunk.signedUpper =
          ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            signedTermUpper n (chunk.localErrorIncrement n) :=
        hsignedLocal
      _ = ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            signedTermUpper n (errorIncrement n) := by
        apply Finset.sum_congr rfl
        intro n hn
        rw [chunk.localErrorIncrement_eq_errorIncrement hlow hbefore hn]
  · calc
      chunk.absoluteUpper =
          ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            absoluteTermUpper (sqrtWeight n)
              (chunk.localErrorIncrement n) :=
        habsoluteLocal
      _ = ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            absoluteTermUpper (sqrtWeight n) (errorIncrement n) := by
        apply Finset.sum_congr rfl
        intro n hn
        rw [chunk.localErrorIncrement_eq_errorIncrement hlow hbefore hn]

/-- Explicit compatibility in the other direction: an old global chunk
witness determines the new local witness by the same recurrence theorem. -/
theorem Chunk.locallyRealizes_of_realizes
    {chunk : Chunk}
    (hlow : 0 < chunk.low)
    (hwell : chunk.WellFormed)
    (hrealizes : chunk.Realizes) :
    chunk.LocallyRealizes := by
  rcases hrealizes with
    ⟨hbefore, hafterGlobal, sqrtWeight, hweights, hsignedGlobal,
      habsoluteGlobal⟩
  have hlowHigh : chunk.low ≤ chunk.high := hwell.1
  have hendpoint :
      chunk.low + chunk.eventCount - 1 = chunk.high := by
    unfold Chunk.eventCount
    omega
  have hstateHigh :=
    chunk.localFloorState_eq_floorState hlow hbefore chunk.eventCount
  have hafterLocal :
      chunk.after = chunk.localFloorState chunk.eventCount := by
    calc
      chunk.after = floorState chunk.high := hafterGlobal
      _ = floorState (chunk.low + chunk.eventCount - 1) := by
        rw [hendpoint]
      _ = chunk.localFloorState chunk.eventCount := hstateHigh.symm
  refine ⟨hafterLocal, sqrtWeight, hweights, ?_, ?_⟩
  · calc
      chunk.signedUpper =
          ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            signedTermUpper n (errorIncrement n) :=
        hsignedGlobal
      _ = ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            signedTermUpper n (chunk.localErrorIncrement n) := by
        apply Finset.sum_congr rfl
        intro n hn
        rw [chunk.localErrorIncrement_eq_errorIncrement hlow hbefore hn]
  · calc
      chunk.absoluteUpper =
          ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            absoluteTermUpper (sqrtWeight n) (errorIncrement n) :=
        habsoluteGlobal
      _ = ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            absoluteTermUpper (sqrtWeight n)
              (chunk.localErrorIncrement n) := by
        apply Finset.sum_congr rfl
        intro n hn
        rw [chunk.localErrorIncrement_eq_errorIncrement hlow hbefore hn]

/-- Gap-free chaining transports every local chunk witness to the old global
source witness.  The induction's state invariant is precisely the global
meaning of the next chunk's `before` field. -/
theorem chain_realizes_of_local
    {nextLow : Nat} {nextBefore : Int} {chunks : List Chunk}
    (hchain : ChainValid nextLow nextBefore chunks)
    (hnextLow : 0 < nextLow)
    (hnextBefore :
      nextBefore = floorState (nextLow - 1))
    (hlocal :
      ∀ chunk, chunk ∈ chunks → chunk.LocallyRealizes) :
    ∀ chunk, chunk ∈ chunks → chunk.Realizes := by
  induction chunks generalizing nextLow nextBefore with
  | nil =>
      intro chunk hmem
      simp at hmem
  | cons chunk rest inductionHypothesis =>
      simp only [ChainValid] at hchain
      rcases hchain with
        ⟨hlow, hwell, hbeforeLink, hrest⟩
      have hchunkLow : 0 < chunk.low := by
        omega
      have hchunkBefore :
          chunk.before = floorState (chunk.low - 1) := by
        calc
          chunk.before = nextBefore := hbeforeLink
          _ = floorState (nextLow - 1) := hnextBefore
          _ = floorState (chunk.low - 1) := by rw [hlow]
      have hheadLocal : chunk.LocallyRealizes :=
        hlocal chunk (by simp)
      have hheadRealizes : chunk.Realizes :=
        chunk.realizes_of_locallyRealizes
          hchunkLow hwell hchunkBefore hheadLocal
      have hheadAfter :
          chunk.after = floorState chunk.high :=
        hheadRealizes.2.1
      have hrestBefore :
          chunk.after = floorState (chunk.high + 1 - 1) := by
        simpa using hheadAfter
      have hrestLocal :
          ∀ tailChunk, tailChunk ∈ rest →
            tailChunk.LocallyRealizes := by
        intro tailChunk hmem
        exact hlocal tailChunk (by simp [hmem])
      have htail :=
        inductionHypothesis
          (nextLow := chunk.high + 1)
          (nextBefore := chunk.after)
          hrest (by omega) hrestBefore hrestLocal
      intro candidate hmem
      rcases List.mem_cons.mp hmem with hhead | htailMem
      · simpa [hhead] using hheadRealizes
      · exact htail candidate htailMem

/-- A checked chain also transports every old global witness to the new local
interface.  This is the off-path compatibility direction for callers of the
former public API. -/
theorem chain_local_of_realizes
    {nextLow : Nat} {nextBefore : Int} {chunks : List Chunk}
    (hchain : ChainValid nextLow nextBefore chunks)
    (hnextLow : 0 < nextLow)
    (hphysical :
      ∀ chunk, chunk ∈ chunks → chunk.Realizes) :
    ∀ chunk, chunk ∈ chunks → chunk.LocallyRealizes := by
  induction chunks generalizing nextLow nextBefore with
  | nil =>
      intro chunk hmem
      simp at hmem
  | cons chunk rest inductionHypothesis =>
      simp only [ChainValid] at hchain
      rcases hchain with
        ⟨hlow, hwell, _hbeforeLink, hrest⟩
      have hchunkLow : 0 < chunk.low := by
        omega
      have hheadRealizes : chunk.Realizes :=
        hphysical chunk (by simp)
      have hheadLocal : chunk.LocallyRealizes :=
        chunk.locallyRealizes_of_realizes
          hchunkLow hwell hheadRealizes
      have hrestPhysical :
          ∀ tailChunk, tailChunk ∈ rest → tailChunk.Realizes := by
        intro tailChunk hmem
        exact hphysical tailChunk (by simp [hmem])
      have htail :=
        inductionHypothesis
          (nextLow := chunk.high + 1)
          (nextBefore := chunk.after)
          hrest (by omega) hrestPhysical
      intro candidate hmem
      rcases List.mem_cons.mp hmem with hhead | htailMem
      · simpa [hhead] using hheadLocal
      · exact htail candidate htailMem

/-- The new narrow physical interface implies the established global
interface entirely in ordinary Lean. -/
theorem sourceScaleEvidence_of_local
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate) :
    SourceScaleEvidence certificate := by
  have hvalid := Certificate.check_sound hcheck
  refine ⟨?_⟩
  exact chain_realizes_of_local hvalid.1 (by norm_num) (by simp)
    evidence.localPhysical

/-- Existing global evidence can be viewed through the new local interface. -/
theorem localSourceScaleEvidence_of_source
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) :
    LocalSourceScaleEvidence certificate := by
  have hvalid := Certificate.check_sound hcheck
  refine ⟨?_⟩
  exact chain_local_of_realizes hvalid.1 (by norm_num)
    evidence.physical

/-! ## Identification with the source definitions -/

/-- Below `N+1`, the periodizing coefficient is inactive and the source
`floorSum` is exactly the cast of the closed integer floor state. -/
theorem floorSum_eq_floorState_cast
    (n : Nat) (hn : n ≤ Source.indexUpper) :
    CDEMAbelSource.floorSum n = (floorState n : Real) := by
  have hdisjoint :
      Disjoint (Finset.Icc 1 CDEMAbelSource.prefixUpper)
        {CDEMAbelSource.periodizer} := by
    refine Finset.disjoint_left.2 ?_
    intro d hd hperiodizer
    have hdUpper := (Finset.mem_Icc.mp hd).2
    have heq : d = CDEMAbelSource.periodizer :=
      Finset.mem_singleton.mp hperiodizer
    subst d
    exact (Nat.not_le_of_gt prefixUpper_lt_periodizer) hdUpper
  have hprefix :
      (∑ d ∈ Finset.Icc 1 CDEMAbelSource.prefixUpper,
        CDEMAbelSource.coefficient d *
          (⌊(n : Real) / CDEMAbelSource.denominator d⌋₊ : Real)) =
        (floorState n : Real) := by
    rw [floorState, Int.cast_sum]
    apply Finset.sum_congr rfl
    intro d hd
    have hdUpper := (Finset.mem_Icc.mp hd).2
    have hdne : d ≠ CDEMAbelSource.periodizer := by
      intro heq
      subst d
      exact (Nat.not_le_of_gt prefixUpper_lt_periodizer) hdUpper
    rw [CDEMAbelSource.coefficient, if_neg hdne,
      CDEMAbelSource.denominator, Nat.floor_div_natCast]
    simp only [Nat.floor_natCast, Int.cast_mul, Int.cast_natCast]
  have hnPeriodizer : n < CDEMAbelSource.periodizer := by
    exact lt_of_le_of_lt hn indexUpper_lt_periodizer
  have hperiodizerFloor :
      ⌊(n : Real) /
          CDEMAbelSource.denominator CDEMAbelSource.periodizer⌋₊ = 0 := by
    rw [CDEMAbelSource.denominator, Nat.floor_div_natCast,
      Nat.floor_natCast]
    exact Nat.div_eq_of_lt hnPeriodizer
  simp only [CDEMAbelSource.floorSum, CDEMAbelSource.support]
  rw [Finset.sum_union hdisjoint, Finset.sum_singleton, hprefix,
    hperiodizerFloor]
  simp

/-- The integer error recurrence is literally the source error sequence,
including its explicit value at zero. -/
theorem errorSequence_eq_errorState
    (n : Nat) (hn : n ≤ Source.indexUpper) :
    CDEMAbelSource.errorSequence n = (errorState n : Real) := by
  by_cases hnZero : n = 0
  · subst n
    simp [CDEMAbelSource.errorSequence, errorState]
  · simp only [CDEMAbelSource.errorSequence, errorState, if_neg hnZero]
    rw [floorSum_eq_floorState_cast n hn]
    rw [show (1 : Real) - (floorState n : Real) =
        ((1 - floorState n : Int) : Real) by
      push_cast
      ring]
    simpa only [Nat.cast_natAbs, Int.cast_abs]

noncomputable def signedRecurrenceSum : Real :=
  ∑ n ∈ Finset.Ico 1 sourcePast,
    (errorIncrement n : Real) / (n : Real)

noncomputable def absoluteRecurrenceSum : Real :=
  ∑ n ∈ Finset.Ico 1 sourcePast,
    |(errorIncrement n : Real)| / Real.sqrt (n : Real)

theorem signedIncrement_eq_recurrenceSum :
    CDEMAbelSource.signedIncrement = signedRecurrenceSum := by
  unfold CDEMAbelSource.signedIncrement signedRecurrenceSum
  rw [show Finset.Icc 1 CDEMAbelSource.indexUpper =
      Finset.Ico 1 sourcePast by
    rw [sourcePast, Finset.Ico_add_one_right_eq_Icc]]
  apply Finset.sum_congr rfl
  intro n hn
  have hnUpper : n ≤ Source.indexUpper := by
    have := (Finset.mem_Ico.mp hn).2
    simp only [sourcePast] at this
    omega
  rw [errorSequence_eq_errorState n hnUpper,
    errorSequence_eq_errorState (n - 1) (by omega)]
  simp only [errorIncrement, Int.cast_sub, Int.cast_natCast]

theorem absoluteIncrement_eq_recurrenceSum :
    CDEMAbelSource.absoluteIncrement = absoluteRecurrenceSum := by
  unfold CDEMAbelSource.absoluteIncrement absoluteRecurrenceSum
  rw [show Finset.Icc 1 CDEMAbelSource.indexUpper =
      Finset.Ico 1 sourcePast by
    rw [sourcePast, Finset.Ico_add_one_right_eq_Icc]]
  apply Finset.sum_congr rfl
  intro n hn
  have hnUpper : n ≤ Source.indexUpper := by
    have := (Finset.mem_Ico.mp hn).2
    simp only [sourcePast] at this
    omega
  rw [errorSequence_eq_errorState n hnUpper,
    errorSequence_eq_errorState (n - 1) (by omega)]
  simp only [errorIncrement, Int.cast_sub, Int.cast_natCast]

/-! ## Gap-free composition and final projection -/

def sumOverChunks {M : Type*} [AddCommMonoid M]
    (f : Nat → M) (chunks : List Chunk) : M :=
  (chunks.map fun chunk =>
    ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1), f n).sum

/-- A checked chunk chain partitions its half-open source interval exactly. -/
theorem chain_sum {M : Type*} [AddCommMonoid M]
    (f : Nat → M) {nextLow : Nat} {nextBefore : Int}
    {chunks : List Chunk}
    (hchain : ChainValid nextLow nextBefore chunks) :
    (∑ n ∈ Finset.Ico nextLow sourcePast, f n) =
      sumOverChunks f chunks := by
  induction chunks generalizing nextLow nextBefore with
  | nil =>
      simp only [ChainValid] at hchain
      subst nextLow
      simp [sumOverChunks]
  | cons chunk rest inductionHypothesis =>
      simp only [ChainValid] at hchain
      rcases hchain with
        ⟨hlow, hwell, hbefore, hrest⟩
      have hnextHigh :
          nextLow ≤ chunk.high + 1 := by
        calc
          nextLow = chunk.low := hlow.symm
          _ ≤ chunk.high := hwell.1
          _ ≤ chunk.high + 1 := Nat.le_succ chunk.high
      have hpast : chunk.high + 1 ≤ sourcePast := by
        exact Nat.succ_le_iff.mpr hwell.2
      rw [← Finset.sum_Ico_consecutive f hnextHigh hpast]
      rw [inductionHypothesis
        (nextLow := chunk.high + 1)
        (nextBefore := chunk.after) hrest]
      simp [sumOverChunks, hlow]

private theorem realized_chunk_signed_sound
    {chunk : Chunk} (hrealizes : chunk.Realizes) :
    (∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        (errorIncrement n : Real) / (n : Real)) ≤
      (chunk.signedUpper : Real) / (Source.weightScale : Real) := by
  rcases hrealizes with
    ⟨_hbefore, _hafter, sqrtWeight, hweights, hsigned, _habsolute⟩
  calc
    (∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        (errorIncrement n : Real) / (n : Real)) ≤
        ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
          (signedTermUpper n (errorIncrement n) : Real) /
            (Source.weightScale : Real) := by
      apply Finset.sum_le_sum
      intro n hn
      exact signedTermUpper_sound n (errorIncrement n)
        (index_pos_of_sqrtWeightValid (hweights n hn))
    _ = ((∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
          signedTermUpper n (errorIncrement n) : Int) : Real) /
        (Source.weightScale : Real) := by
      simp only [Int.cast_sum]
      rw [Finset.sum_div]
    _ = (chunk.signedUpper : Real) /
        (Source.weightScale : Real) := by rw [← hsigned]

private theorem realized_chunk_absolute_sound
    {chunk : Chunk} (hrealizes : chunk.Realizes) :
    (∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        |(errorIncrement n : Real)| / Real.sqrt (n : Real)) ≤
      (chunk.absoluteUpper : Real) / (Source.weightScale : Real) := by
  rcases hrealizes with
    ⟨_hbefore, _hafter, sqrtWeight, hweights, _hsigned, habsolute⟩
  calc
    (∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
        |(errorIncrement n : Real)| / Real.sqrt (n : Real)) ≤
        ∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
          (absoluteTermUpper (sqrtWeight n) (errorIncrement n) : Real) /
            (Source.weightScale : Real) := by
      apply Finset.sum_le_sum
      intro n hn
      exact absoluteTermUpper_sound n (sqrtWeight n) (errorIncrement n)
        (index_pos_of_sqrtWeightValid (hweights n hn))
        (hweights n hn)
    _ = ((∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
          absoluteTermUpper (sqrtWeight n) (errorIncrement n) : Nat) :
            Real) / (Source.weightScale : Real) := by
      simp only [Nat.cast_sum]
      rw [Finset.sum_div]
    _ = (chunk.absoluteUpper : Real) /
        (Source.weightScale : Real) := by rw [← habsolute]

private theorem chunks_signed_sound
    (chunks : List Chunk)
    (hphysical : ∀ chunk, chunk ∈ chunks → chunk.Realizes) :
    sumOverChunks
        (fun n => (errorIncrement n : Real) / (n : Real)) chunks ≤
      (((chunks.map Chunk.signedUpper).sum : Int) : Real) /
        (Source.weightScale : Real) := by
  induction chunks with
  | nil => simp [sumOverChunks]
  | cons chunk rest inductionHypothesis =>
      have hhead : chunk.Realizes :=
        hphysical chunk (by simp)
      have htail :
          ∀ tailChunk, tailChunk ∈ rest → tailChunk.Realizes := by
        intro tailChunk hmem
        exact hphysical tailChunk (by simp [hmem])
      have hheadSound := realized_chunk_signed_sound hhead
      have htailSound := inductionHypothesis htail
      rw [sumOverChunks, List.map_cons, List.sum_cons]
      change
        (∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            (errorIncrement n : Real) / (n : Real)) +
            sumOverChunks
              (fun n => (errorIncrement n : Real) / (n : Real)) rest ≤
          ((chunk.signedUpper +
            (rest.map Chunk.signedUpper).sum : Int) : Real) /
            (Source.weightScale : Real)
      calc
        _ ≤ (chunk.signedUpper : Real) / (Source.weightScale : Real) +
            (((rest.map Chunk.signedUpper).sum : Int) : Real) /
              (Source.weightScale : Real) :=
          add_le_add hheadSound htailSound
        _ = _ := by
          push_cast
          ring

private theorem chunks_absolute_sound
    (chunks : List Chunk)
    (hphysical : ∀ chunk, chunk ∈ chunks → chunk.Realizes) :
    sumOverChunks
        (fun n =>
          |(errorIncrement n : Real)| / Real.sqrt (n : Real)) chunks ≤
      (((chunks.map Chunk.absoluteUpper).sum : Nat) : Real) /
        (Source.weightScale : Real) := by
  induction chunks with
  | nil => simp [sumOverChunks]
  | cons chunk rest inductionHypothesis =>
      have hhead : chunk.Realizes :=
        hphysical chunk (by simp)
      have htail :
          ∀ tailChunk, tailChunk ∈ rest → tailChunk.Realizes := by
        intro tailChunk hmem
        exact hphysical tailChunk (by simp [hmem])
      have hheadSound := realized_chunk_absolute_sound hhead
      have htailSound := inductionHypothesis htail
      rw [sumOverChunks, List.map_cons, List.sum_cons]
      change
        (∑ n ∈ Finset.Ico chunk.low (chunk.high + 1),
            |(errorIncrement n : Real)| / Real.sqrt (n : Real)) +
            sumOverChunks
              (fun n =>
                |(errorIncrement n : Real)| /
                  Real.sqrt (n : Real)) rest ≤
          ((chunk.absoluteUpper +
            (rest.map Chunk.absoluteUpper).sum : Nat) : Real) /
            (Source.weightScale : Real)
      calc
        _ ≤ (chunk.absoluteUpper : Real) /
              (Source.weightScale : Real) +
            (((rest.map Chunk.absoluteUpper).sum : Nat) : Real) /
              (Source.weightScale : Real) :=
          add_le_add hheadSound htailSound
        _ = _ := by
          push_cast
          ring

/-- Shared projection after every chunk has been identified with the closed
global recurrence.  Public entry points below expose both the new local
interface and the old compatibility interface. -/
private theorem scaledOutputClaim_of_checked_global_core
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) :
    Source.ScaledOutputClaim certificate.signedNumerator
      certificate.absoluteNumerator := by
  have hvalid := Certificate.check_sound hcheck
  have hsignedChunks :=
    chunks_signed_sound certificate.chunks evidence.physical
  have habsoluteChunks :=
    chunks_absolute_sound certificate.chunks evidence.physical
  have hsignedPartition :=
    chain_sum
      (fun n => (errorIncrement n : Real) / (n : Real))
      hvalid.1
  have habsolutePartition :=
    chain_sum
      (fun n =>
        |(errorIncrement n : Real)| / Real.sqrt (n : Real))
      hvalid.1
  have hsignedTarget :
      (((certificate.chunks.map Chunk.signedUpper).sum : Int) : Real) /
          (Source.weightScale : Real) ≤
        (certificate.signedNumerator : Real) /
          (Source.weightScale : Real) := by
    have htotal :
        (certificate.chunks.map Chunk.signedUpper).sum ≤
          (certificate.signedNumerator : Int) := by
      simpa [Certificate.signedTotal] using hvalid.2.1
    apply div_le_div_of_nonneg_right
    · exact_mod_cast htotal
    · positivity
  have habsoluteTarget :
      (((certificate.chunks.map Chunk.absoluteUpper).sum : Nat) : Real) /
          (Source.weightScale : Real) ≤
        (certificate.absoluteNumerator : Real) /
          (Source.weightScale : Real) := by
    have htotal :
        (certificate.chunks.map Chunk.absoluteUpper).sum ≤
          certificate.absoluteNumerator := by
      simpa [Certificate.absoluteTotal] using hvalid.2.2
    apply div_le_div_of_nonneg_right
    · exact_mod_cast htotal
    · positivity
  have hsigned :
      CDEMAbelSource.signedIncrement ≤
        (certificate.signedNumerator : Real) /
          (Source.weightScale : Real) := by
    rw [signedIncrement_eq_recurrenceSum]
    rw [signedRecurrenceSum, hsignedPartition]
    exact hsignedChunks.trans hsignedTarget
  have habsolute :
      CDEMAbelSource.absoluteIncrement ≤
        (certificate.absoluteNumerator : Real) /
          (Source.weightScale : Real) := by
    rw [absoluteIncrement_eq_recurrenceSum]
    rw [absoluteRecurrenceSum, habsolutePartition]
    exact habsoluteChunks.trans habsoluteTarget
  constructor
  · have hmul := (le_div_iff₀
      weightScale_real_pos).1 hsigned
    simpa [mul_comm] using hmul
  · have hmul := (le_div_iff₀
      weightScale_real_pos).1 habsolute
    simpa [mul_comm] using hmul

/-- Main narrow source-realization theorem.  Its physical premise contains
only local recurrence states, local folds, and square guards.  The checked
chain and `floorState_jump` derive all global source equalities. -/
theorem scaledOutputClaim_of_checked_local_certificate
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate) :
    Source.ScaledOutputClaim certificate.signedNumerator
      certificate.absoluteNumerator :=
  scaledOutputClaim_of_checked_global_core hcheck
    (sourceScaleEvidence_of_local hcheck evidence)

/-- Compatibility theorem retaining the former public API.

For a checked certificate, an old global witness first converts to the local
interface, so this path exercises the same recurrence transport as the new
entry point. -/
theorem scaledOutputClaim_of_checked_certificate
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) :
    Source.ScaledOutputClaim certificate.signedNumerator
      certificate.absoluteNumerator :=
  scaledOutputClaim_of_checked_local_certificate hcheck
    (localSourceScaleEvidence_of_source hcheck evidence)

/-- Production specialization for a locally materialized certificate. -/
theorem sourceClaim_of_checked_local_production_certificate
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate)
    (hsigned :
      certificate.signedNumerator = Source.signedTarget)
    (habsolute :
      certificate.absoluteNumerator = Source.absoluteTarget) :
    Source.SourceClaim := by
  have hscaled :=
    scaledOutputClaim_of_checked_local_certificate hcheck evidence
  rw [hsigned, habsolute] at hscaled
  exact Source.sourceClaim_of_scaledOutput hscaled

/-- Production specialization: a checked recurrence certificate carrying the
two fixed transcript numerators yields the exact source proposition.  This
keeps the former global-evidence signature as a compatibility API. -/
theorem sourceClaim_of_checked_production_certificate
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate)
    (hsigned :
      certificate.signedNumerator = Source.signedTarget)
    (habsolute :
      certificate.absoluteNumerator = Source.absoluteTarget) :
    Source.SourceClaim := by
  have hscaled :=
    scaledOutputClaim_of_checked_certificate hcheck evidence
  rw [hsigned, habsolute] at hscaled
  exact Source.sourceClaim_of_scaledOutput hscaled

end SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate
