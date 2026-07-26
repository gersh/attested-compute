import Mathlib.NumberTheory.LegendreSymbol.ZModChar
import Mathlib.NumberTheory.LegendreSymbol.QuadraticChar.Basic
import SparkInterval.Dirichlet.GRHVerification

/-!
# Concrete primitive characters of moduli 3 and 4

Platt's Theorem 7.1 quantifies over every primitive character of every
modulus.  For the limited-test instantiation this file pins down the two
smallest odd-modulus cases completely: the unit groups of `ZMod 3` and
`ZMod 4` are `{1, -1}`, so each modulus has exactly one nontrivial
character, obtained from Mathlib's `quadraticChar (ZMod 3)` and `ZMod.χ₄`
by composing with the integer-to-complex cast.

The classification lemmas turn a per-character finite-strip verification
into the modulus-level `GRHVerifiedForModulus` statement.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open DirichletCharacter

/-- The nontrivial (quadratic, odd) character of modulus 3 valued in `ℂ`. -/
noncomputable def chiThree : DirichletCharacter ℂ 3 :=
  (quadraticChar (ZMod 3)).ringHomComp (Int.castRingHom ℂ)

/-- The nontrivial (quadratic, odd) primitive character of modulus 4 valued
in `ℂ`. -/
noncomputable def chiFour : DirichletCharacter ℂ 4 :=
  ZMod.χ₄.ringHomComp (Int.castRingHom ℂ)

theorem chiThree_neg_one : chiThree (-1 : ZMod 3) = -1 := by
  have h : quadraticChar (ZMod 3) (-1 : ZMod 3) = -1 := by decide
  simp [chiThree, h]

theorem chiFour_neg_one : chiFour (-1 : ZMod 4) = -1 := by
  have h : ZMod.χ₄ (-1 : ZMod 4) = -1 := by decide
  simp [chiFour, h]

theorem chiThree_ne_one : chiThree ≠ 1 := by
  intro h
  have hval : chiThree (-1 : ZMod 3) = 1 := by
    rw [h]
    exact MulChar.one_apply (isUnit_one.neg)
  rw [chiThree_neg_one] at hval
  norm_num at hval

theorem chiFour_ne_one : chiFour ≠ 1 := by
  intro h
  have hval : chiFour (-1 : ZMod 4) = 1 := by
    rw [h]
    exact MulChar.one_apply (isUnit_one.neg)
  rw [chiFour_neg_one] at hval
  norm_num at hval

/-- Every unit of `ZMod 3` is `1` or `-1`. -/
theorem zmod_three_units : ∀ u : (ZMod 3)ˣ, u = 1 ∨ u = -1 := by
  decide +kernel

/-- Every unit of `ZMod 4` is `1` or `-1`. -/
theorem zmod_four_units : ∀ u : (ZMod 4)ˣ, u = 1 ∨ u = -1 := by
  decide +kernel

private theorem char_neg_one_sq {N : ℕ} [NeZero N]
    (χ : DirichletCharacter ℂ N) :
    χ (-1 : ZMod N) * χ (-1 : ZMod N) = 1 := by
  rw [← map_mul, neg_mul_neg, one_mul, map_one]

/-- A character of modulus 3 is trivial or `chiThree`. -/
theorem eq_chiThree_of_ne_one
    {χ : DirichletCharacter ℂ 3} (hχ : χ ≠ 1) : χ = chiThree := by
  rcases mul_self_eq_one_iff.mp (char_neg_one_sq χ) with hone | hneg
  · exfalso
    apply hχ
    apply MulChar.ext
    intro u
    rw [MulChar.one_apply_coe]
    rcases zmod_three_units u with rfl | rfl
    · rw [Units.val_one, map_one]
    · rw [Units.val_neg, Units.val_one]
      exact hone
  · apply MulChar.ext
    intro u
    rcases zmod_three_units u with rfl | rfl
    · rw [Units.val_one, map_one, map_one]
    · rw [Units.val_neg, Units.val_one, hneg, chiThree_neg_one]

/-- A character of modulus 4 is trivial or `chiFour`. -/
theorem eq_chiFour_of_ne_one
    {χ : DirichletCharacter ℂ 4} (hχ : χ ≠ 1) : χ = chiFour := by
  rcases mul_self_eq_one_iff.mp (char_neg_one_sq χ) with hone | hneg
  · exfalso
    apply hχ
    apply MulChar.ext
    intro u
    rw [MulChar.one_apply_coe]
    rcases zmod_four_units u with rfl | rfl
    · rw [Units.val_one, map_one]
    · rw [Units.val_neg, Units.val_one]
      exact hone
  · apply MulChar.ext
    intro u
    rcases zmod_four_units u with rfl | rfl
    · rw [Units.val_one, map_one, map_one]
    · rw [Units.val_neg, Units.val_one, hneg, chiFour_neg_one]

/-- A finite-strip verification of `chiThree` alone settles modulus 3. -/
theorem grhVerifiedForModulus_three {lo hi : ℝ}
    (h : ∀ z ∈ nontrivialCriticalStrip lo hi,
      chiThree.LFunction z = 0 → z.re = (1 : ℝ) / 2) :
    GRHVerifiedForModulus 3 lo hi := by
  intro χ hprim
  have hne : χ ≠ 1 := ne_one_of_isPrimitive (by norm_num) hprim
  rw [eq_chiThree_of_ne_one hne]
  exact h

/-- A finite-strip verification of `chiFour` alone settles modulus 4. -/
theorem grhVerifiedForModulus_four {lo hi : ℝ}
    (h : ∀ z ∈ nontrivialCriticalStrip lo hi,
      chiFour.LFunction z = 0 → z.re = (1 : ℝ) / 2) :
    GRHVerifiedForModulus 4 lo hi := by
  intro χ hprim
  have hne : χ ≠ 1 := ne_one_of_isPrimitive (by norm_num) hprim
  rw [eq_chiFour_of_ne_one hne]
  exact h

end SparkInterval.Dirichlet
