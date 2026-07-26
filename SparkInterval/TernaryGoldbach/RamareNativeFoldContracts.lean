/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Algebra.Order.Floor.Div
import Mathlib.Data.Finset.NatDivisors
import Mathlib.NumberTheory.ArithmeticFunction.Moebius
import Mathlib.NumberTheory.ArithmeticFunction.VonMangoldt
import Mathlib.NumberTheory.Harmonic.EulerMascheroni
import Mathlib.Order.Interval.Finset.Nat
import Mathlib.Tactic

/-!
# Source contracts and finite-fold evidence for the Ramaré native family

This file is a production-data-free copy of the *mathematical shapes* behind
the three live `TGNativeCertificates.Ramare` native leaves in `claude_math`:

* `Finite100M.checkFirstMertens100M = true`;
* `Lemma71.checkLemma71_100M = true`; and
* `MStar140MEngine.checkLimit 140000000 = true`.

The trusted-run boundary must not return any of the claims below.  It may
return only `FiniteFoldEvidence`: signed integer interval states, signed
integer interval increments, exact recurrence equations, local realization
bounds, and integer guard inequalities.  The theorems in this file perform
the ordinary Lean induction from those low-level folds to the source-shaped
real inequalities.

The interval fold is intentionally generic.  A future exact executable
refinement must prove that the measured CPU checker validates every field of
the fold.  No compiler, executable, or receipt theorem is assumed here, and
there is no closed production evaluation or `native_decide`.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.RamareNativeFoldContracts

open ArithmeticFunction Finset
open scoped BigOperators

/-! ## Generic signed fixed-point fold -/

/-- Maximum absolute signed endpoint, expressed as a natural number. -/
def intervalAbsUpper (lo hi : Int) : Nat :=
  max lo.natAbs hi.natAbs

/-- A signed fixed-point interval fold for `steps + 1` values of `signal`.

Index `k` represents `signal (lower + k)`.  The executable evidence contains
the integer interval states and increments.  `deltaBounds` is the local
semantic obligation for one checked transition; it is not an end-to-end
claim about the range. -/
structure ScaledIntervalFold
    (signal : Nat → Real)
    (lower steps scale : Nat) where
  lo : Nat → Int
  hi : Nat → Int
  deltaLo : Nat → Int
  deltaHi : Nat → Int
  scalePos : 0 < scale
  initial :
    (lo 0 : Real) / (scale : Real) ≤ signal lower ∧
      signal lower ≤ (hi 0 : Real) / (scale : Real)
  loStep :
    ∀ k, k < steps → lo (k + 1) = lo k + deltaLo k
  hiStep :
    ∀ k, k < steps → hi (k + 1) = hi k + deltaHi k
  deltaBounds :
    ∀ k, k < steps →
      (deltaLo k : Real) / (scale : Real) ≤
          signal (lower + (k + 1)) - signal (lower + k) ∧
        signal (lower + (k + 1)) - signal (lower + k) ≤
          (deltaHi k : Real) / (scale : Real)

namespace ScaledIntervalFold

/-- Ordinary induction from local signed increments to every prefix state. -/
theorem realizes
    {signal : Nat → Real}
    {lower steps scale : Nat}
    (fold : ScaledIntervalFold signal lower steps scale) :
    ∀ k, k ≤ steps →
      (fold.lo k : Real) / (scale : Real) ≤ signal (lower + k) ∧
        signal (lower + k) ≤
          (fold.hi k : Real) / (scale : Real) := by
  intro k hk
  induction k with
  | zero =>
      simpa using fold.initial
  | succ k ih =>
      have hklt : k < steps := by omega
      have previous := ih (by omega)
      have delta := fold.deltaBounds k hklt
      constructor
      · rw [fold.loStep k hklt]
        push_cast
        calc
          ((fold.lo k : Real) + (fold.deltaLo k : Real)) /
                (scale : Real) =
              (fold.lo k : Real) / (scale : Real) +
                (fold.deltaLo k : Real) / (scale : Real) := by ring
          _ ≤ signal (lower + k) +
                (signal (lower + (k + 1)) - signal (lower + k)) :=
              add_le_add previous.1 delta.1
          _ = signal (lower + (k + 1)) := by ring
      · rw [fold.hiStep k hklt]
        push_cast
        calc
          signal (lower + (k + 1)) =
              signal (lower + k) +
                (signal (lower + (k + 1)) - signal (lower + k)) := by ring
          _ ≤ (fold.hi k : Real) / (scale : Real) +
                (fold.deltaHi k : Real) / (scale : Real) :=
              add_le_add previous.2 delta.2
          _ = ((fold.hi k : Real) + (fold.deltaHi k : Real)) /
                (scale : Real) := by ring

end ScaledIntervalFold

/-- A single signed fixed-point interval cell.  It is used for the isolated
first-Mertens anchor at `10^8`; the three range computations use full folds.
-/
structure ScaledIntervalCell
    (value : Real)
    (scale : Nat) where
  lo : Int
  hi : Int
  scalePos : 0 < scale
  bounds :
    (lo : Real) / (scale : Real) ≤ value ∧
      value ≤ (hi : Real) / (scale : Real)

/-- Turn an integer endpoint guard into an absolute real bound. -/
theorem abs_le_of_scaled_interval
    {lo hi : Int}
    {x : Real}
    {scale num denom : Nat}
    (scalePos : 0 < scale)
    (denomPos : 0 < denom)
    (lower : (lo : Real) / (scale : Real) ≤ x)
    (upper : x ≤ (hi : Real) / (scale : Real))
    (guard : denom * intervalAbsUpper lo hi ≤ num * scale) :
    |x| ≤ (num : Real) / (denom : Real) := by
  have scaleRealPos : (0 : Real) < (scale : Real) := by
    exact_mod_cast scalePos
  have denomRealPos : (0 : Real) < (denom : Real) := by
    exact_mod_cast denomPos
  have loMax : lo.natAbs ≤ intervalAbsUpper lo hi :=
    le_max_left _ _
  have hiMax : hi.natAbs ≤ intervalAbsUpper lo hi :=
    le_max_right _ _
  have guardReal :
      (denom : Real) * (intervalAbsUpper lo hi : Real) ≤
        (num : Real) * (scale : Real) := by
    exact_mod_cast guard
  have loAbs :
      |(lo : Real)| ≤
        (num : Real) * (scale : Real) / (denom : Real) := by
    rw [← Int.cast_abs, ← Nat.cast_natAbs]
    have castLo :
        (lo.natAbs : Real) ≤ (intervalAbsUpper lo hi : Real) := by
      exact_mod_cast loMax
    rw [le_div_iff₀ denomRealPos]
    nlinarith
  have hiAbs :
      |(hi : Real)| ≤
        (num : Real) * (scale : Real) / (denom : Real) := by
    rw [← Int.cast_abs, ← Nat.cast_natAbs]
    have castHi :
        (hi.natAbs : Real) ≤ (intervalAbsUpper lo hi : Real) := by
      exact_mod_cast hiMax
    rw [le_div_iff₀ denomRealPos]
    nlinarith
  rw [abs_le]
  constructor
  · have loNegative := neg_le_of_abs_le loAbs
    calc
      -((num : Real) / (denom : Real)) =
          (-(num : Real) * (scale : Real) / (denom : Real)) /
            (scale : Real) := by field_simp
      _ ≤ (lo : Real) / (scale : Real) := by
        rw [div_le_div_iff_of_pos_right scaleRealPos]
        have normalize :
            (-(num : Real) * (scale : Real) / (denom : Real)) =
              -((num : Real) * (scale : Real) / (denom : Real)) := by
          ring
        rw [normalize]
        exact loNegative
      _ ≤ x := lower
  · have hiPositive := le_of_abs_le hiAbs
    calc
      x ≤ (hi : Real) / (scale : Real) := upper
      _ ≤ ((num : Real) * (scale : Real) / (denom : Real)) /
          (scale : Real) := by
        rw [div_le_div_iff_of_pos_right scaleRealPos]
        exact hiPositive
      _ = (num : Real) / (denom : Real) := by field_simp

/-! ## Exact source-shaped quantities -/

/-- `∑_{1<n≤N} Λ(n)/n`, matching the package-local source copy. -/
def mangoldtDivSum (N : Nat) : Real :=
  ∑ n ∈ Finset.Ioc 1 N,
    ArithmeticFunction.vonMangoldt n / (n : Real)

/-- `ψ(N)` in the same finite-set convention. -/
def psiSum (N : Nat) : Real :=
  ∑ n ∈ Finset.Ioc 1 N, ArithmeticFunction.vonMangoldt n

/-- Natural-endpoint first-Mertens remainder. -/
def firstMertensRemainderNat (N : Nat) : Real :=
  mangoldtDivSum N - Real.log N + Real.eulerMascheroniConstant

/-- Natural-endpoint corrected remainder. -/
def correctedRemainderNat (N : Nat) : Real :=
  firstMertensRemainderNat N - (psiSum N - N) / N

/-- Source-shaped real first-Mertens remainder with the exact floor
convention used by the live consumer. -/
def firstMertensRemainder (x : Real) : Real :=
  mangoldtDivSum ⌊x⌋₊ - Real.log x + Real.eulerMascheroniConstant

/-- Source-shaped real Chebyshev remainder. -/
def chebyshevRemainder (x : Real) : Real :=
  psiSum ⌊x⌋₊ - x

/-- Cancellation-friendly corrected real remainder. -/
def correctedRemainder (x : Real) : Real :=
  firstMertensRemainder x - chebyshevRemainder x / x

/-- Möbius log-square source coefficient from the Ramaré--Zúñiga table. -/
def r2BaseCoeff (n : Nat) : Real :=
  ∑ d ∈ n.divisors,
    (ArithmeticFunction.moebius d : Real) * (Real.log d) ^ 2

/-- Corrected source coefficient. -/
def r2CoeffValue (n : Nat) : Real :=
  r2BaseCoeff n + 2 * Real.eulerMascheroniConstant

/-- Summatory corrected coefficient. -/
def r2StarValue (N : Nat) : Real :=
  ∑ n ∈ Finset.Icc 1 N, r2CoeffValue n

/-- Log-weighted absolute coefficient sum. -/
def weightedValue (N : Nat) : Real :=
  ∑ n ∈ Finset.Icc 1 N, |r2CoeffValue n| / (n : Real)

/-- Quantity bounded in each of the four Lemma 7.1 rows. -/
def lemma71Quantity (N : Nat) : Real :=
  weightedValue N + |r2StarValue N| / (N : Real)

/-- Exact little-Mertens sum used by the `m★` sweep. -/
def littleMertens (U : Nat) : Real :=
  ∑ n ∈ Finset.Icc 1 U,
    (ArithmeticFunction.moebius n : Real) / (n : Real)

/-- Natural-endpoint Ramaré `m★`. -/
def ramareMStar (N : Nat) : Real :=
  ∑ w ∈ Finset.Icc 1 (Nat.sqrt N),
    |littleMertens (N / w ^ 2)| / (w : Real) ^ 2

/-- Product checked by the `140,000,000` production fold. -/
def mStarProduct (N : Nat) : Real :=
  ramareMStar N * Real.log ((N : Real) + 1)

/-! ## The three source claims -/

def Finite100MSourceClaim : Prop :=
  (∀ y : Real, 144913 ≤ y → y ≤ 100000000 →
    |correctedRemainder y| ≤ 5 / 1000) ∧
  |firstMertensRemainder 100000000| ≤ 4 / 10000

def Lemma71SourceClaim : Prop :=
  lemma71Quantity 462848 ≤ (374 / 10000 : Real) * 4345 ∧
  lemma71Quantity 1000000 ≤ (422 / 10000 : Real) * 4345 ∧
  lemma71Quantity 10000000 ≤ (579 / 10000 : Real) * 4345 ∧
  lemma71Quantity 100000000 ≤ (762 / 10000 : Real) * 4345

def MStar140MSourceClaim : Prop :=
  ∀ N : Nat, 2 ≤ N → N ≤ 140000000 →
    mStarProduct N ≤ 4 / 5

/-- One source-shaped bundle, with one field per live native leaf. -/
structure SourceClaims : Prop where
  finite100M : Finite100MSourceClaim
  lemma71 : Lemma71SourceClaim
  mStar140M : MStar140MSourceClaim

/-! ## Closed fold dimensions and low-level evidence -/

def firstMertensScale : Nat := 281474976710656
def lemma71Scale : Nat := 4294967296
def mStarProductScale : Nat :=
  281474976710656 * 281474976710656

def firstLower : Nat := 144913
def firstSteps : Nat := 100000000 - firstLower
def lemmaLower : Nat := 1
def lemmaSteps : Nat := 100000000 - lemmaLower
def mStarLower : Nat := 2
def mStarSteps : Nat := 140000000 - mStarLower

/-- Low-level output of the shared first-Mertens fixed-point fold.

The guard fields are integer comparisons over signed interval endpoints.
They do not state either real source claim. -/
structure Finite100MFoldEvidence where
  corrected :
    ScaledIntervalFold
      correctedRemainderNat firstLower firstSteps firstMertensScale
  correctedGuard :
    ∀ k, k ≤ firstSteps →
      1000 * intervalAbsUpper (corrected.lo k) (corrected.hi k) ≤
        4 * firstMertensScale
  psi :
    ScaledIntervalFold psiSum firstLower firstSteps firstMertensScale
  psiUpperGuard :
    ∀ k, k ≤ firstSteps →
      psi.hi k ≤
        Int.ofNat
          (2 * (firstLower + k) * firstMertensScale)
  anchor :
    ScaledIntervalCell
      (firstMertensRemainderNat 100000000) firstMertensScale
  anchorGuard :
    10000 * intervalAbsUpper anchor.lo anchor.hi ≤
      4 * firstMertensScale

/-- Low-level signed interval fold and four integer row guards. -/
structure Lemma71FoldEvidence where
  fold :
    ScaledIntervalFold
      lemma71Quantity lemmaLower lemmaSteps lemma71Scale
  row462848 :
    10000 *
        intervalAbsUpper
          (fold.lo (462848 - lemmaLower))
          (fold.hi (462848 - lemmaLower)) ≤
      (374 * 4345) * lemma71Scale
  row1000000 :
    10000 *
        intervalAbsUpper
          (fold.lo (1000000 - lemmaLower))
          (fold.hi (1000000 - lemmaLower)) ≤
      (422 * 4345) * lemma71Scale
  row10000000 :
    10000 *
        intervalAbsUpper
          (fold.lo (10000000 - lemmaLower))
          (fold.hi (10000000 - lemmaLower)) ≤
      (579 * 4345) * lemma71Scale
  row100000000 :
    10000 *
        intervalAbsUpper
          (fold.lo (100000000 - lemmaLower))
          (fold.hi (100000000 - lemmaLower)) ≤
      (762 * 4345) * lemma71Scale

/-- Low-level signed interval fold and exact integer product guards for every
point of the `m★` production range. -/
structure MStar140MFoldEvidence where
  fold :
    ScaledIntervalFold
      mStarProduct mStarLower mStarSteps mStarProductScale
  productGuard :
    ∀ k, k ≤ mStarSteps →
      5 * intervalAbsUpper (fold.lo k) (fold.hi k) ≤
        4 * mStarProductScale

/-- The only mathematical evidence that the compact native checker may
accept.  This has no `SourceClaims` field and no final real inequality field.
-/
structure FiniteFoldEvidence where
  finite100M : Finite100MFoldEvidence
  lemma71 : Lemma71FoldEvidence
  mStar140M : MStar140MFoldEvidence

/-! ## Source theorem for the first-Mertens fold -/

@[simp] theorem firstMertensRemainder_nat (N : Nat) :
    firstMertensRemainder (N : Real) = firstMertensRemainderNat N := by
  simp [firstMertensRemainder, firstMertensRemainderNat]

@[simp] theorem correctedRemainder_nat {N : Nat} (_positive : 0 < N) :
    correctedRemainder (N : Real) = correctedRemainderNat N := by
  simp [correctedRemainder, correctedRemainderNat, chebyshevRemainder,
    firstMertensRemainder, firstMertensRemainderNat]

theorem psiSum_nonneg (N : Nat) : 0 ≤ psiSum N := by
  unfold psiSum
  exact Finset.sum_nonneg
    (fun n _ => ArithmeticFunction.vonMangoldt_nonneg)

theorem correctedRemainder_sub_floor {x : Real} (hx : 1 ≤ x) :
    let N := ⌊x⌋₊
    correctedRemainder x - correctedRemainderNat N =
      (Real.log N - Real.log x) +
        psiSum N * (1 / (N : Real) - 1 / x) := by
  let N := ⌊x⌋₊
  have hN : 1 ≤ N := by
    exact (Nat.le_floor_iff' Nat.one_ne_zero).2 (by simpa using hx)
  have hxpos : 0 < x := lt_of_lt_of_le zero_lt_one hx
  have hNR : (0 : Real) < (N : Real) := by
    exact_mod_cast (by omega : 0 < N)
  simp only [correctedRemainder, correctedRemainderNat,
    firstMertensRemainder, firstMertensRemainderNat, chebyshevRemainder]
  change
    (mangoldtDivSum N - Real.log x + Real.eulerMascheroniConstant -
      (psiSum N - x) / x) -
        (mangoldtDivSum N - Real.log N + Real.eulerMascheroniConstant -
          (psiSum N - N) / N) =
      (Real.log N - Real.log x) +
        psiSum N * (1 / (N : Real) - 1 / x)
  field_simp [hxpos.ne', hNR.ne']
  ring

theorem correctedRemainder_floor_drift
    {x : Real}
    {N : Nat}
    (hN : 3000 ≤ N)
    (hNx : (N : Real) ≤ x)
    (hxN : x < (N + 1 : Nat))
    (hpsi : psiSum N ≤ 2 * N) :
    |correctedRemainder x - correctedRemainderNat N| ≤ 1 / 1000 := by
  have hNpos : 0 < N := by omega
  have hNR : (0 : Real) < (N : Real) := by
    exact_mod_cast hNpos
  have hxpos : 0 < x := hNR.trans_le hNx
  have hfloor : ⌊x⌋₊ = N := by
    exact (Nat.floor_eq_iff (by positivity)).2
      ⟨hNx, by simpa [Nat.cast_add, Nat.cast_one] using hxN⟩
  have formula := correctedRemainder_sub_floor (x := x) (by
    have oneLeN : (1 : Real) ≤ (N : Real) := by
      exact_mod_cast (by omega : 1 ≤ N)
    exact oneLeN.trans hNx)
  simp only [hfloor] at formula
  rw [formula]
  have logMono : Real.log N ≤ Real.log x :=
    Real.log_le_log hNR hNx
  have ratioPos : 0 < x / (N : Real) := div_pos hxpos hNR
  have logRatio := Real.log_le_sub_one_of_pos ratioPos
  have logSplit :
      Real.log (x / (N : Real)) =
        Real.log x - Real.log N :=
    Real.log_div hxpos.ne' hNR.ne'
  rw [logSplit] at logRatio
  have xGap : x - (N : Real) ≤ 1 := by
    simpa [Nat.cast_add, Nat.cast_one] using
      (show x - (N : Real) ≤ 1 by
        have gap := hxN.le
        push_cast at gap
        linarith)
  have logGap : Real.log x - Real.log N ≤ 1 / (N : Real) := by
    have rewriteRatio :
        x / (N : Real) - 1 =
          (x - (N : Real)) / (N : Real) := by
      field_simp
    rw [rewriteRatio] at logRatio
    exact logRatio.trans (div_le_div_of_nonneg_right xGap hNR.le)
  have firstTerm :
      |Real.log N - Real.log x| ≤ 1 / (N : Real) := by
    rw [abs_of_nonpos (sub_nonpos.mpr logMono), neg_sub]
    exact logGap
  have inverseNonneg :
      0 ≤ 1 / (N : Real) - 1 / x := by
    exact sub_nonneg.mpr (one_div_le_one_div_of_le hNR hNx)
  have inverseEq :
      1 / (N : Real) - 1 / x =
        (x - (N : Real)) / ((N : Real) * x) := by
    field_simp [hNR.ne', hxpos.ne']
  have oneLeRatio : (1 : Real) ≤ x / (N : Real) := by
    rw [le_div_iff₀ hNR]
    simpa using hNx
  have inverseBound :
      1 / (N : Real) - 1 / x ≤
        1 / ((N : Real) * (N : Real)) := by
    rw [inverseEq, div_le_iff₀ (mul_pos hNR hxpos)]
    have gapRatio :
        x - (N : Real) ≤ x / (N : Real) :=
      xGap.trans oneLeRatio
    calc
      x - (N : Real) ≤ x / (N : Real) := gapRatio
      _ = 1 / ((N : Real) * (N : Real)) *
          ((N : Real) * x) := by field_simp
  have psiNonneg : 0 ≤ psiSum N := psiSum_nonneg N
  have secondTerm :
      |psiSum N * (1 / (N : Real) - 1 / x)| ≤
        2 / (N : Real) := by
    rw [abs_of_nonneg (mul_nonneg psiNonneg inverseNonneg)]
    calc
      psiSum N * (1 / (N : Real) - 1 / x) ≤
          (2 * (N : Real)) *
            (1 / ((N : Real) * (N : Real))) :=
        mul_le_mul hpsi inverseBound inverseNonneg (by positivity)
      _ = 2 / (N : Real) := by field_simp
  calc
    |(Real.log N - Real.log x) +
        psiSum N * (1 / (N : Real) - 1 / x)| ≤
        |Real.log N - Real.log x| +
          |psiSum N * (1 / (N : Real) - 1 / x)| :=
      abs_add_le _ _
    _ ≤ 1 / (N : Real) + 2 / (N : Real) :=
      add_le_add firstTerm secondTerm
    _ ≤ 1 / 1000 := by
      rw [show 1 / (N : Real) + 2 / (N : Real) =
        3 / (N : Real) by ring]
      rw [div_le_div_iff₀ hNR
        (by norm_num : (0 : Real) < 1000)]
      norm_num
      exact_mod_cast hN

theorem finite100MSourceClaim_of_evidence
    (evidence : Finite100MFoldEvidence) :
    Finite100MSourceClaim := by
  constructor
  · intro y hyLower hyUpper
    let N := ⌊y⌋₊
    have yNonneg : 0 ≤ y := by linarith
    have nLower : firstLower ≤ N := by
      exact (Nat.le_floor_iff' (by
        norm_num [firstLower] : firstLower ≠ 0)).2
        (by simpa [firstLower] using hyLower)
    have nUpper : N ≤ 100000000 :=
      Nat.floor_le_of_le hyUpper
    let k := N - firstLower
    have kBound : k ≤ firstSteps := by
      simp only [k, firstSteps, firstLower]
      omega
    have index : firstLower + k = N := by
      simp only [k]
      omega
    have correctedBounds :=
      evidence.corrected.realizes k kBound
    rw [index] at correctedBounds
    have correctedDiscrete :
        |correctedRemainderNat N| ≤ 4 / 1000 := by
      exact abs_le_of_scaled_interval
        evidence.corrected.scalePos (by norm_num)
        correctedBounds.1 correctedBounds.2
        (evidence.correctedGuard k kBound)
    have psiBounds := evidence.psi.realizes k kBound
    rw [index] at psiBounds
    have psiGuard := evidence.psiUpperGuard k kBound
    rw [index] at psiGuard
    have scaleRealPos :
        (0 : Real) < (firstMertensScale : Real) := by
      exact_mod_cast evidence.psi.scalePos
    have psiUpperReal :
        (evidence.psi.hi k : Real) ≤
          ((2 * N * firstMertensScale : Nat) : Real) := by
      exact_mod_cast psiGuard
    have psiBound : psiSum N ≤ 2 * (N : Real) := by
      calc
        psiSum N ≤
            (evidence.psi.hi k : Real) /
              (firstMertensScale : Real) :=
          psiBounds.2
        _ ≤ ((2 * N * firstMertensScale : Nat) : Real) /
              (firstMertensScale : Real) :=
          div_le_div_of_nonneg_right psiUpperReal scaleRealPos.le
        _ = 2 * (N : Real) := by
          push_cast
          field_simp
    have nToY : (N : Real) ≤ y := Nat.floor_le yNonneg
    have yToNext : y < (N + 1 : Nat) := by
      simpa [N, Nat.cast_add, Nat.cast_one] using
        Nat.lt_floor_add_one y
    have drift :=
      correctedRemainder_floor_drift
        (x := y) (N := N)
        (by simp [firstLower] at nLower; omega)
        nToY yToNext psiBound
    calc
      |correctedRemainder y| =
          |correctedRemainderNat N +
            (correctedRemainder y - correctedRemainderNat N)| := by
        ring_nf
      _ ≤ |correctedRemainderNat N| +
          |correctedRemainder y - correctedRemainderNat N| :=
        abs_add_le _ _
      _ ≤ 4 / 1000 + 1 / 1000 :=
        add_le_add correctedDiscrete drift
      _ = 5 / 1000 := by norm_num
  · change
      |firstMertensRemainder ((100000000 : Nat) : Real)| ≤
        4 / 10000
    rw [firstMertensRemainder_nat]
    exact abs_le_of_scaled_interval
      evidence.anchor.scalePos (by norm_num)
      evidence.anchor.bounds.1 evidence.anchor.bounds.2
      evidence.anchorGuard

/-! ## Source theorems for the row and m-star folds -/

private theorem lemma71_row_of_evidence
    (evidence : Lemma71FoldEvidence)
    (K numerator : Nat)
    (hKLower : lemmaLower ≤ K)
    (hKUpper : K ≤ 100000000)
    (guard :
      10000 *
          intervalAbsUpper
            (evidence.fold.lo (K - lemmaLower))
            (evidence.fold.hi (K - lemmaLower)) ≤
        (numerator * 4345) * lemma71Scale) :
    lemma71Quantity K ≤
      (numerator / 10000 : Real) * 4345 := by
  let k := K - lemmaLower
  have kBound : k ≤ lemmaSteps := by
    simp only [k, lemmaSteps, lemmaLower]
    omega
  have index : lemmaLower + k = K := by
    simp only [k]
    omega
  have bounds := evidence.fold.realizes k kBound
  rw [index] at bounds
  have absolute :
      |lemma71Quantity K| ≤
        ((numerator * 4345 : Nat) : Real) / 10000 :=
    abs_le_of_scaled_interval
      evidence.fold.scalePos (by norm_num)
      bounds.1 bounds.2 guard
  calc
    lemma71Quantity K ≤ |lemma71Quantity K| := le_abs_self _
    _ ≤ ((numerator * 4345 : Nat) : Real) / 10000 := absolute
    _ = (numerator / 10000 : Real) * 4345 := by
      push_cast
      ring

theorem lemma71SourceClaim_of_evidence
    (evidence : Lemma71FoldEvidence) :
    Lemma71SourceClaim := by
  exact
    ⟨lemma71_row_of_evidence evidence 462848 374
        (by norm_num [lemmaLower]) (by norm_num) evidence.row462848,
      lemma71_row_of_evidence evidence 1000000 422
        (by norm_num [lemmaLower]) (by norm_num) evidence.row1000000,
      lemma71_row_of_evidence evidence 10000000 579
        (by norm_num [lemmaLower]) (by norm_num) evidence.row10000000,
      lemma71_row_of_evidence evidence 100000000 762
        (by norm_num [lemmaLower]) (by norm_num) evidence.row100000000⟩

theorem mStar140MSourceClaim_of_evidence
    (evidence : MStar140MFoldEvidence) :
    MStar140MSourceClaim := by
  intro N nLower nUpper
  let k := N - mStarLower
  have kBound : k ≤ mStarSteps := by
    simp only [k, mStarSteps, mStarLower]
    omega
  have index : mStarLower + k = N := by
    simp only [k, mStarLower]
    omega
  have bounds := evidence.fold.realizes k kBound
  rw [index] at bounds
  have absolute :
      |mStarProduct N| ≤ (4 : Real) / 5 :=
    abs_le_of_scaled_interval
      evidence.fold.scalePos (by norm_num)
      bounds.1 bounds.2
      (evidence.productGuard k kBound)
  exact (le_abs_self (mStarProduct N)).trans absolute

/-- Ordinary acceptance-evidence-to-all-three-claims theorem. -/
theorem sourceClaims_of_finiteFoldEvidence
    (evidence : FiniteFoldEvidence) :
    SourceClaims where
  finite100M :=
    finite100MSourceClaim_of_evidence evidence.finite100M
  lemma71 :=
    lemma71SourceClaim_of_evidence evidence.lemma71
  mStar140M :=
    mStar140MSourceClaim_of_evidence evidence.mStar140M

end SparkInterval.TernaryGoldbach.RamareNativeFoldContracts

end
