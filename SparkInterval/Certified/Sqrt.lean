import SparkInterval.Certified.Rounding

/-!
# Certified rational enclosure of the real square root

`sqrtInterval prec x` computes an executable rational interval that provably
contains `Real.sqrt x`.  The input is scaled by `4 ^ prec`, the floor of the
scaled value is bracketed by `Nat.sqrt`, and the two candidate roots are
divided by `2 ^ prec`, producing an enclosure of width `1 / 2 ^ prec` for
positive inputs.

Nonpositive inputs yield the degenerate interval `[0, 0]`, matching the
convention `Real.sqrt x = 0` for `x ≤ 0`.  This file contains no axioms,
`sorry`, or `native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-- Executable rational enclosure of `Real.sqrt x` with width `1 / 2 ^ prec`
on positive inputs.  Nonpositive inputs collapse to `[0, 0]`. -/
def sqrtInterval (prec : ℕ) (x : ℚ) : RatInterval :=
  if x ≤ 0 then ⟨0, 0⟩
  else
    ⟨(Nat.sqrt (⌊x * 4 ^ prec⌋).toNat : ℚ) / 2 ^ prec,
      ((Nat.sqrt (⌊x * 4 ^ prec⌋).toNat + 1 : ℕ) : ℚ) / 2 ^ prec⟩

/-- Degenerate soundness: for nonpositive `x` both `Real.sqrt x` and the
computed interval collapse to zero. -/
theorem sqrtInterval_containsReal_of_nonpos (prec : ℕ) {x : ℚ} (hx : x ≤ 0) :
    (sqrtInterval prec x).ContainsReal (Real.sqrt (x : ℝ)) := by
  have hx' : (x : ℝ) ≤ 0 := by exact_mod_cast hx
  rw [sqrtInterval, if_pos hx, Real.sqrt_eq_zero_of_nonpos hx']
  exact containsReal_of_le_of_le (by norm_num) (by norm_num)

/-- Soundness: the computed interval encloses the real square root. -/
theorem sqrtInterval_containsReal (prec : ℕ) {x : ℚ} (hx : 0 ≤ x) :
    (sqrtInterval prec x).ContainsReal (Real.sqrt (x : ℝ)) := by
  rcases hx.eq_or_lt with h0 | hxpos
  · exact sqrtInterval_containsReal_of_nonpos prec h0.symm.le
  · rw [sqrtInterval, if_neg (not_le.mpr hxpos)]
    set N : ℕ := (⌊x * 4 ^ prec⌋).toNat with hN
    set r : ℕ := Nat.sqrt N with hr
    have hpow4 : (0 : ℚ) < 4 ^ prec := by positivity
    have hfloor_nonneg : (0 : ℤ) ≤ ⌊x * 4 ^ prec⌋ :=
      Int.floor_nonneg.mpr (mul_nonneg hxpos.le hpow4.le)
    have hNZ : (N : ℤ) = ⌊x * 4 ^ prec⌋ := by
      rw [hN]; exact Int.toNat_of_nonneg hfloor_nonneg
    have hNeq : (N : ℚ) = ((⌊x * 4 ^ prec⌋ : ℤ) : ℚ) := by exact_mod_cast hNZ
    -- `N ≤ x * 4 ^ prec < N + 1`, the floor bracketing of the scaled input.
    have hN_le : (N : ℚ) ≤ x * 4 ^ prec := by
      rw [hNeq]; exact Int.floor_le _
    have hN_lt : x * 4 ^ prec < (N : ℚ) + 1 := by
      rw [hNeq]; exact Int.lt_floor_add_one _
    -- `r ^ 2 ≤ N` and `N + 1 ≤ (r + 1) ^ 2`, the `Nat.sqrt` bracketing.
    have hr_sq : (r : ℚ) ^ 2 ≤ (N : ℚ) := by
      rw [hr]; exact_mod_cast Nat.sqrt_le' N
    have hr_succ : (N : ℚ) + 1 ≤ ((r : ℚ) + 1) ^ 2 := by
      rw [hr]; exact_mod_cast Nat.succ_le_succ_sqrt' N
    have hpow : ((2 : ℚ) ^ prec) ^ 2 = 4 ^ prec := by
      rw [← pow_mul, mul_comm, pow_mul]; norm_num
    have hlo_sq : ((r : ℚ) / 2 ^ prec) ^ 2 ≤ x := by
      rw [div_pow, hpow, div_le_iff₀ hpow4]
      exact hr_sq.trans hN_le
    -- The upper endpoint must cover `sqrt` of everything below `(N + 1) / 4 ^ prec`.
    have hhi_sq : x ≤ (((r + 1 : ℕ) : ℚ) / 2 ^ prec) ^ 2 := by
      rw [div_pow, hpow, le_div_iff₀ hpow4]
      calc x * 4 ^ prec ≤ (N : ℚ) + 1 := hN_lt.le
        _ ≤ ((r : ℚ) + 1) ^ 2 := hr_succ
        _ = ((r + 1 : ℕ) : ℚ) ^ 2 := by push_cast; ring
    refine containsReal_of_le_of_le ?_ ?_
    · exact Real.le_sqrt_of_sq_le (by exact_mod_cast hlo_sq)
    · rw [Real.sqrt_le_iff]
      refine ⟨?_, by exact_mod_cast hhi_sq⟩
      have h0 : (0 : ℚ) ≤ ((r + 1 : ℕ) : ℚ) / 2 ^ prec := by positivity
      exact_mod_cast h0

/-- The computed enclosure is well formed for every rational input. -/
theorem sqrtInterval_isValid (prec : ℕ) (x : ℚ) :
    (sqrtInterval prec x).IsValid := by
  by_cases hle : x ≤ 0
  · rw [sqrtInterval, if_pos hle]
    exact le_rfl
  · exact RatInterval.isValid_of_containsReal
      (sqrtInterval_containsReal prec (not_le.mp hle).le)

/-- The lower endpoint is a ratio of naturals, hence nonnegative. -/
theorem sqrtInterval_nonneg (prec : ℕ) (x : ℚ) :
    0 ≤ (sqrtInterval prec x).lo := by
  by_cases hle : x ≤ 0
  · rw [sqrtInterval, if_pos hle]
  · rw [sqrtInterval, if_neg hle]
    show (0 : ℚ) ≤ (Nat.sqrt (⌊x * 4 ^ prec⌋).toNat : ℚ) / 2 ^ prec
    positivity

-- Sanity check: `sqrtInterval 3 2` is `[11/8, 12/8]`, the dyadic bracketing of
-- `√2 ≈ 1.414`.  `Nat.sqrt` is well-founded recursion, so `decide` cannot
-- kernel-reduce it; the root is certified through `Nat.eq_sqrt'` instead.
example : (sqrtInterval 3 (2 : ℚ)).lo = 11 / 8 ∧ (sqrtInterval 3 (2 : ℚ)).hi = 12 / 8 := by
  have hsqrt : Nat.sqrt 128 = 11 := (Nat.eq_sqrt'.mpr (by norm_num)).symm
  rw [sqrtInterval, if_neg (by norm_num)]
  norm_num [show ((128 : ℤ)).toNat = 128 from rfl, hsqrt]

end SparkInterval.Certified
