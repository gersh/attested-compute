import SparkInterval.Certified.Complex

/-!
# Certified rational enclosures of `Real.arctan`

This file provides an executable, fully proved rational-interval enclosure
of the real arctangent.  The core evaluator sums the alternating Maclaurin
series `arctan x = ∑ (-1)^k x^(2k+1) / (2k+1)` with exact rational
arithmetic on a reduced argument `|x| ≤ 1/2`, then widens the partial sum
by a proven tail bound: on that range the tail is geometrically dominated
with ratio `1/4`, so the truncation error after `N` terms is at most
`|x|^(2N+1) * 4/3`.  General arguments are reduced without square roots:

* `x < 0` uses oddness, `arctan (-x) = -arctan x`;
* `1/2 < x < 2` uses `arctan x = π/4 + arctan ((x - 1) / (x + 1))`,
  derived here from `Real.arctan_add` and `Real.arctan_one`;
* `2 ≤ x` uses `arctan x = π/2 - arctan (1/x)`
  (`Real.arctan_inv_of_pos`).

The constant `π` enters through the exact decimal bounds
`Real.pi_gt_d20` / `Real.pi_lt_d20`.  Interval arguments are handled by
endpoint evaluation and monotonicity of `arctan`.  This file contains no
axioms, `sorry`, or `native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-! ## Alternating-series partial sum and tail bound -/

/-- Maclaurin partial sum of `arctan` truncated after `terms` terms,
evaluated with exact rational arithmetic. -/
def atanPartialSum (terms : ℕ) (q : ℚ) : ℚ :=
  ∑ k ∈ Finset.range terms, (-1 : ℚ) ^ k * q ^ (2 * k + 1) / ((2 * k + 1 : ℕ) : ℚ)

/-- Rational tail bound for the truncated `arctan` series, sound whenever
`|q| ≤ 1/2`: the omitted tail is geometrically dominated with ratio `1/4`. -/
def atanErr (terms : ℕ) (q : ℚ) : ℚ :=
  |q| ^ (2 * terms + 1) * (4 / 3)

theorem atanPartialSum_cast (terms : ℕ) (q : ℚ) :
    ((atanPartialSum terms q : ℚ) : ℝ) =
      ∑ k ∈ Finset.range terms,
        (-1 : ℝ) ^ k * (q : ℝ) ^ (2 * k + 1) / ((2 * k + 1 : ℕ) : ℝ) := by
  unfold atanPartialSum
  push_cast
  rfl

theorem atanErr_cast (terms : ℕ) (q : ℚ) :
    ((atanErr terms q : ℚ) : ℝ) = |(q : ℝ)| ^ (2 * terms + 1) * (4 / 3) := by
  unfold atanErr
  push_cast
  rfl

/-- Tail bound for the alternating `arctan` series: on `|x| ≤ 1/2` the
truncation error after `N` terms is at most `|x|^(2N+1) * 4/3`. -/
theorem abs_arctan_sub_partialSum {x : ℝ} (hx : |x| ≤ 1 / 2) (N : ℕ) :
    |Real.arctan x - ∑ k ∈ Finset.range N,
        (-1 : ℝ) ^ k * x ^ (2 * k + 1) / ((2 * k + 1 : ℕ) : ℝ)|
      ≤ |x| ^ (2 * N + 1) * (4 / 3) := by
  have hnorm : ‖x‖ < 1 := by
    rw [Real.norm_eq_abs]
    linarith
  have hsum := Real.hasSum_arctan hnorm
  have htail : HasSum
      (fun n : ℕ => (-1 : ℝ) ^ (n + N) * x ^ (2 * (n + N) + 1)
        / ((2 * (n + N) + 1 : ℕ) : ℝ))
      (Real.arctan x - ∑ k ∈ Finset.range N,
        (-1 : ℝ) ^ k * x ^ (2 * k + 1) / ((2 * k + 1 : ℕ) : ℝ)) :=
    (hasSum_nat_add_iff' N).mpr hsum
  have habs : ∀ n : ℕ,
      |(-1 : ℝ) ^ (n + N) * x ^ (2 * (n + N) + 1)
          / ((2 * (n + N) + 1 : ℕ) : ℝ)|
        ≤ |x| ^ (2 * N + 1) * (1 / 4 : ℝ) ^ n := by
    intro n
    have hden : (1 : ℝ) ≤ ((2 * (n + N) + 1 : ℕ) : ℝ) :=
      Nat.one_le_cast.mpr (by omega)
    have h1 : |(-1 : ℝ) ^ (n + N) * x ^ (2 * (n + N) + 1)
        / ((2 * (n + N) + 1 : ℕ) : ℝ)|
        = |x| ^ (2 * (n + N) + 1) / ((2 * (n + N) + 1 : ℕ) : ℝ) := by
      rw [abs_div, abs_mul, abs_pow, abs_pow, abs_neg, abs_one, one_pow,
        one_mul, Nat.abs_cast]
    have h2 : |x| ^ (2 * (n + N) + 1) / ((2 * (n + N) + 1 : ℕ) : ℝ)
        ≤ |x| ^ (2 * (n + N) + 1) :=
      div_le_self (pow_nonneg (abs_nonneg x) _) hden
    have h3 : |x| ^ (2 * (n + N) + 1) = |x| ^ (2 * N + 1) * (x ^ 2) ^ n := by
      rw [← sq_abs x]
      ring
    have hx2 : x ^ 2 ≤ (1 / 4 : ℝ) := by
      nlinarith [sq_abs x, abs_nonneg x]
    have h4 : (x ^ 2) ^ n ≤ (1 / 4 : ℝ) ^ n :=
      pow_le_pow_left₀ (sq_nonneg x) hx2 n
    calc |(-1 : ℝ) ^ (n + N) * x ^ (2 * (n + N) + 1)
        / ((2 * (n + N) + 1 : ℕ) : ℝ)|
        = |x| ^ (2 * (n + N) + 1) / ((2 * (n + N) + 1 : ℕ) : ℝ) := h1
      _ ≤ |x| ^ (2 * (n + N) + 1) := h2
      _ = |x| ^ (2 * N + 1) * (x ^ 2) ^ n := h3
      _ ≤ |x| ^ (2 * N + 1) * (1 / 4 : ℝ) ^ n :=
        mul_le_mul_of_nonneg_left h4 (pow_nonneg (abs_nonneg x) _)
  have hgeom : HasSum (fun n : ℕ => (1 / 4 : ℝ) ^ n) ((1 - (1 / 4 : ℝ))⁻¹) :=
    hasSum_geometric_of_lt_one (by norm_num) (by norm_num)
  have h43 : ((1 - (1 / 4 : ℝ))⁻¹ : ℝ) = 4 / 3 := by norm_num
  rw [h43] at hgeom
  have hgeomc : HasSum (fun n : ℕ => |x| ^ (2 * N + 1) * (1 / 4 : ℝ) ^ n)
      (|x| ^ (2 * N + 1) * (4 / 3)) := hgeom.mul_left _
  have hgeomneg : HasSum
      (fun n : ℕ => -(|x| ^ (2 * N + 1) * (1 / 4 : ℝ) ^ n))
      (-(|x| ^ (2 * N + 1) * (4 / 3))) := hgeomc.neg
  have hup : ∀ n : ℕ,
      (-1 : ℝ) ^ (n + N) * x ^ (2 * (n + N) + 1) / ((2 * (n + N) + 1 : ℕ) : ℝ)
        ≤ |x| ^ (2 * N + 1) * (1 / 4 : ℝ) ^ n :=
    fun n => (le_abs_self _).trans (habs n)
  have hlow : ∀ n : ℕ,
      -(|x| ^ (2 * N + 1) * (1 / 4 : ℝ) ^ n)
        ≤ (-1 : ℝ) ^ (n + N) * x ^ (2 * (n + N) + 1)
          / ((2 * (n + N) + 1 : ℕ) : ℝ) :=
    fun n => (neg_le_neg (habs n)).trans (neg_abs_le _)
  rw [abs_le]
  exact ⟨hasSum_le hlow hgeomneg htail, hasSum_le hup htail hgeomc⟩

/-! ## Core enclosure on the reduced range -/

/-- Interval enclosure of `arctan q`, sound for `|q| ≤ 1/2`. -/
def atanSmall (terms : ℕ) (q : ℚ) : RatInterval :=
  widen (atanErr terms q) (RatInterval.point (atanPartialSum terms q))

theorem atanSmall_containsReal {terms : ℕ} {q : ℚ} (hq : |q| ≤ 1 / 2) :
    (atanSmall terms q).ContainsReal (Real.arctan (q : ℝ)) := by
  have hqR : |(q : ℝ)| ≤ 1 / 2 := by
    have h2 : ((1 / 2 : ℚ) : ℝ) = 1 / 2 := by norm_num
    rw [← Rat.cast_abs, ← h2]
    exact Rat.cast_le.mpr hq
  unfold atanSmall
  apply widen_contains_of_abs_le
    (RatInterval.point_containsReal (atanPartialSum terms q))
  rw [atanErr_cast, atanPartialSum_cast]
  exact abs_arctan_sub_partialSum hqR terms

/-! ## π enclosure and argument reduction -/

/-- Exact rational enclosure of `π` with twenty decimal digits, backed by
`Real.pi_gt_d20` and `Real.pi_lt_d20`. -/
def piInterval : RatInterval :=
  ⟨3.14159265358979323846, 3.14159265358979323847⟩

theorem piInterval_containsReal : piInterval.ContainsReal Real.pi := by
  constructor
  · show ((3.14159265358979323846 : ℚ) : ℝ) ≤ Real.pi
    have h : ((3.14159265358979323846 : ℚ) : ℝ)
        = (3.14159265358979323846 : ℝ) := by norm_num
    rw [h]
    exact Real.pi_gt_d20.le
  · show Real.pi ≤ ((3.14159265358979323847 : ℚ) : ℝ)
    have h : ((3.14159265358979323847 : ℚ) : ℝ)
        = (3.14159265358979323847 : ℝ) := by norm_num
    rw [h]
    exact Real.pi_lt_d20.le

/-- Enclosure of `arctan q` for `0 ≤ q`, with square-root-free argument
reduction into the series range `|·| ≤ 1/2`. -/
def atanPos (terms : ℕ) (q : ℚ) : RatInterval :=
  if q ≤ 1 / 2 then
    atanSmall terms q
  else if q < 2 then
    ((RatInterval.point (1 / 4)).mul piInterval).add
      (atanSmall terms ((q - 1) / (q + 1)))
  else
    ((RatInterval.point (1 / 2)).mul piInterval).sub
      (atanSmall terms (1 / q))

theorem atanPos_containsReal (terms : ℕ) {q : ℚ} (hq : 0 ≤ q) :
    (atanPos terms q).ContainsReal (Real.arctan (q : ℝ)) := by
  unfold atanPos
  split_ifs with h1 h2
  · exact atanSmall_containsReal (by rwa [abs_of_nonneg hq])
  · -- Band `1/2 < q < 2`: shift by `π/4`.
    have h1' : (1 / 2 : ℚ) < q := not_le.mp h1
    have hq0 : (0 : ℚ) < q := lt_trans (by norm_num) h1'
    have hq1 : (0 : ℚ) < q + 1 := by linarith
    have hu_abs : |(q - 1) / (q + 1)| ≤ 1 / 2 := by
      rw [abs_le]
      constructor
      · rw [le_div_iff₀ hq1]
        linarith
      · rw [div_le_iff₀ hq1]
        linarith
    have hsmall := atanSmall_containsReal (terms := terms) hu_abs
    have hquarter : ((RatInterval.point (1 / 4)).mul piInterval).ContainsReal
        (((1 / 4 : ℚ) : ℝ) * Real.pi) :=
      RatInterval.mul_containsReal (RatInterval.point_containsReal _)
        piInterval_containsReal
    have hcont := RatInterval.add_containsReal hquarter hsmall
    have hxpos : (0 : ℝ) < (q : ℝ) := by exact_mod_cast hq0
    have hq1R : (0 : ℝ) < (q : ℝ) + 1 := by linarith
    have hkey : ((1 / 4 : ℚ) : ℝ) * Real.pi
        + Real.arctan (((q - 1) / (q + 1) : ℚ) : ℝ) = Real.arctan (q : ℝ) := by
      have hcastu : (((q - 1) / (q + 1) : ℚ) : ℝ)
          = ((q : ℝ) - 1) / ((q : ℝ) + 1) := by
        push_cast
        ring
      have hlt : ((q : ℝ) - 1) / ((q : ℝ) + 1) * 1 < 1 := by
        rw [mul_one, div_lt_one hq1R]
        linarith
      have hadd := Real.arctan_add hlt
      rw [Real.arctan_one] at hadd
      have e1 : ((q : ℝ) - 1) / ((q : ℝ) + 1) + 1
          = 2 * (q : ℝ) / ((q : ℝ) + 1) := by
        rw [eq_div_iff hq1R.ne', add_mul, div_mul_cancel₀ _ hq1R.ne']
        ring
      have e2 : 1 - ((q : ℝ) - 1) / ((q : ℝ) + 1) = 2 / ((q : ℝ) + 1) := by
        rw [eq_div_iff hq1R.ne', sub_mul, div_mul_cancel₀ _ hq1R.ne']
        ring
      have hratio : (((q : ℝ) - 1) / ((q : ℝ) + 1) + 1)
          / (1 - ((q : ℝ) - 1) / ((q : ℝ) + 1) * 1) = (q : ℝ) := by
        rw [mul_one, e1, e2,
          div_eq_iff (div_pos (by norm_num : (0 : ℝ) < 2) hq1R).ne']
        ring
      rw [hratio] at hadd
      have hc4 : ((1 / 4 : ℚ) : ℝ) = 1 / 4 := by norm_num
      rw [hcastu, hc4]
      linarith [hadd]
    rwa [hkey] at hcont
  · -- Tail `2 ≤ q`: reflect through `π/2`.
    have h2' : (2 : ℚ) ≤ q := not_lt.mp h2
    have hq0 : (0 : ℚ) < q := by linarith
    have hu_abs : |1 / q| ≤ 1 / 2 := by
      have hpos : (0 : ℚ) < 1 / q := by positivity
      rw [abs_of_pos hpos, div_le_iff₀ hq0]
      linarith
    have hsmall := atanSmall_containsReal (terms := terms) hu_abs
    have hhalf : ((RatInterval.point (1 / 2)).mul piInterval).ContainsReal
        (((1 / 2 : ℚ) : ℝ) * Real.pi) :=
      RatInterval.mul_containsReal (RatInterval.point_containsReal _)
        piInterval_containsReal
    have hcont := RatInterval.sub_containsReal hhalf hsmall
    have hkey : ((1 / 2 : ℚ) : ℝ) * Real.pi
        - Real.arctan ((1 / q : ℚ) : ℝ) = Real.arctan (q : ℝ) := by
      have hxpos : (0 : ℝ) < (q : ℝ) := by exact_mod_cast hq0
      have hinv := Real.arctan_inv_of_pos hxpos
      have hcastu : ((1 / q : ℚ) : ℝ) = ((q : ℝ))⁻¹ := by
        push_cast
        ring
      have hc2 : ((1 / 2 : ℚ) : ℝ) = 1 / 2 := by norm_num
      rw [hcastu, hinv, hc2]
      ring
    rwa [hkey] at hcont

/-! ## Public API -/

/-- Executable rational-interval enclosure of `arctan x`.

`terms` controls the series truncation.  The reduction used here is
square-root free and needs no iterated halving, so `halvings` is absorbed
as additional series terms; passing a larger `halvings` still tightens the
enclosure monotonically.  The result is always `some` (the `Option` exists
only to match the certified-evaluator calling convention). -/
def atanQ (terms halvings : ℕ) (x : ℚ) : Option RatInterval :=
  if x < 0 then some ((atanPos (terms + halvings) (-x)).neg)
  else some (atanPos (terms + halvings) x)

theorem atanQ_containsReal {terms halvings : ℕ} {x : ℚ} {I : RatInterval}
    (h : atanQ terms halvings x = some I) :
    I.ContainsReal (Real.arctan (x : ℝ)) := by
  unfold atanQ at h
  split_ifs at h with hneg
  · have hI : (atanPos (terms + halvings) (-x)).neg = I := Option.some.inj h
    subst hI
    have hcont := atanPos_containsReal (terms + halvings)
      (neg_nonneg.mpr hneg.le)
    have hres := RatInterval.neg_containsReal hcont
    have hcast : -Real.arctan ((-x : ℚ) : ℝ) = Real.arctan (x : ℝ) := by
      push_cast
      rw [Real.arctan_neg]
      ring
    rwa [hcast] at hres
  · have hI : atanPos (terms + halvings) x = I := Option.some.inj h
    subst hI
    exact atanPos_containsReal (terms + halvings) (not_lt.mp hneg)

/-- Interval-argument enclosure of `arctan`, by endpoint evaluation and
monotonicity of `arctan`. -/
def atanInterval (terms halvings : ℕ) (J : RatInterval) : Option RatInterval :=
  (atanQ terms halvings J.lo).bind fun A =>
    (atanQ terms halvings J.hi).map fun B => (⟨A.lo, B.hi⟩ : RatInterval)

theorem atanInterval_containsReal {terms halvings : ℕ} {J I : RatInterval}
    (h : atanInterval terms halvings J = some I) {x : ℝ}
    (hx : J.ContainsReal x) :
    I.ContainsReal (Real.arctan x) := by
  unfold atanInterval at h
  cases hA : atanQ terms halvings J.lo with
  | none =>
      rw [hA] at h
      have h' : (none : Option RatInterval) = some I := h
      injection h'
  | some A =>
      rw [hA] at h
      cases hB : atanQ terms halvings J.hi with
      | none =>
          rw [hB] at h
          have h' : (none : Option RatInterval) = some I := h
          injection h'
      | some B =>
          rw [hB] at h
          have hI : (⟨A.lo, B.hi⟩ : RatInterval) = I :=
            Option.some.inj
              (show some (⟨A.lo, B.hi⟩ : RatInterval) = some I from h)
          subst hI
          have hA' := atanQ_containsReal hA
          have hB' := atanQ_containsReal hB
          exact ⟨le_trans hA'.1 (Real.arctan_mono hx.1),
            le_trans (Real.arctan_mono hx.2) hB'.2⟩

/-! ## Executable smoke checks

`#guard` evaluates at elaboration time and fails the build on `false`;
it produces no proof obligations and no axioms. -/

#guard (atanQ 8 0 (1 / 3)).isSome
#guard (atanQ 8 0 (7 / 10)).isSome
#guard (atanQ 8 0 (-3)).isSome
#guard
  match atanQ 16 0 (1 / 2) with
  | some I => decide (I.lo ≤ I.hi ∧ I.hi - I.lo ≤ 1 / 100000000)
  | none => false
#guard
  match atanInterval 12 0 ⟨-3, 5⟩ with
  | some I => decide (I.lo ≤ I.hi)
  | none => false

end SparkInterval.Certified
