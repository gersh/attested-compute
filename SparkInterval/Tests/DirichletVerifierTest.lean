import SparkInterval.Dirichlet.SmallModuli

/-! Type-level regression tests for the finite-strip GRH target theorems. -/

set_option autoImplicit false

namespace SparkInterval.Tests.DirichletVerifier

open SparkInterval.Dirichlet
open DirichletCharacter

example (lo hi : ℝ) : IsCompact (criticalStrip lo hi) :=
  isCompact_criticalStrip lo hi

example {N : ℕ} [NeZero N] {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1)
    {lo hi : ℝ} :
    (LZerosIn χ (criticalStrip lo hi)).Finite :=
  LZerosIn_finite hχ (isCompact_criticalStrip lo hi)

example {N : ℕ} [NeZero N] {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1)
    {lo hi : ℝ}
    (hcount :
      (criticalLineLZerosIn χ (criticalStrip lo hi)).ncard =
        (LZerosIn χ (criticalStrip lo hi)).ncard) :
    ∀ z ∈ criticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  all_zeros_in_strip_on_criticalLine hχ hcount

example {N : ℕ} [NeZero N] {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ}
    {lo hi : ℝ} {count : Nat}
    (evidence : GRHVerifierEvidence χ f lo hi count) :
    ∀ z ∈ criticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  evidence.all_zeros_on_criticalLine

example : chiFour ≠ 1 := chiFour_ne_one

example {χ : DirichletCharacter ℂ 4} (hχ : χ.IsPrimitive) : χ = chiFour :=
  eq_chiFour_of_ne_one (ne_one_of_isPrimitive (by norm_num) hχ)

end SparkInterval.Tests.DirichletVerifier
