import SparkInterval.Dirichlet.SmallModuli

/-! Type-level regression tests for the finite-strip GRH target theorems. -/

set_option autoImplicit false

namespace SparkInterval.Tests.DirichletVerifier

open SparkInterval.Dirichlet
open DirichletCharacter

example (lo hi : ℝ) : IsCompact (criticalStripEnvelope lo hi) :=
  isCompact_criticalStripEnvelope lo hi

/-- Regression for the former false closed-strip target: an even primitive
character's boundary zero at `s = 0` is not a nontrivial zero. -/
example (lo hi : ℝ) : (0 : ℂ) ∉ nontrivialCriticalStrip lo hi := by
  simp

example {lo hi : ℝ} (hlo : lo ≤ 0) (hhi : 0 ≤ hi) :
    (0 : ℂ) ∈ criticalStripEnvelope lo hi := by
  simp [hlo, hhi]

example {N : ℕ} [NeZero N] {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1)
    {lo hi : ℝ} :
    (LZerosIn χ (nontrivialCriticalStrip lo hi)).Finite :=
  LZerosIn_nontrivialCriticalStrip_finite hχ lo hi

example {N : ℕ} [NeZero N] {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1)
    {lo hi : ℝ}
    (hcount :
      (criticalLineLZerosIn χ (nontrivialCriticalStrip lo hi)).ncard =
        (LZerosIn χ (nontrivialCriticalStrip lo hi)).ncard) :
    ∀ z ∈ nontrivialCriticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  all_zeros_in_nontrivialStrip_on_criticalLine hχ hcount

example {N : ℕ} [NeZero N] {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ}
    {lo hi : ℝ} {count : Nat}
    (evidence : GRHVerifierEvidence χ f lo hi count) :
    ∀ z ∈ nontrivialCriticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  evidence.all_zeros_on_criticalLine

example : chiFour ≠ 1 := chiFour_ne_one

example {χ : DirichletCharacter ℂ 4} (hχ : χ.IsPrimitive) : χ = chiFour :=
  eq_chiFour_of_ne_one (ne_one_of_isPrimitive (by norm_num) hχ)

end SparkInterval.Tests.DirichletVerifier
