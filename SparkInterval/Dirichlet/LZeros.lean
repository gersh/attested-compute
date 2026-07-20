import Mathlib.NumberTheory.LSeries.Nonvanishing

/-!
# Discreteness of the zeros of nontrivial Dirichlet L-functions

Mathlib proves that the zeros of `riemannZeta` are discrete
(`Mathlib.NumberTheory.LSeries.ZetaZeros`), which the zeta verifier uses to
make every compact-region zero set finite.  This file supplies the analogous
facts for `DirichletCharacter.LFunction` of a nontrivial character, which is
an entire function (`DirichletCharacter.differentiable_LFunction`) that does
not vanish at `s = 2` (`DirichletCharacter.LFunction_ne_zero_of_one_le_re`).

The trivial character is excluded: its L-function has a pole at `s = 1`, and
its critical-strip zeros are governed by `riemannZeta`, which the existing
zeta verifier already covers.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open DirichletCharacter

variable {N : ℕ} [NeZero N]

/-- The zeros of the analytically continued Dirichlet L-function. -/
def LZeros (χ : DirichletCharacter ℂ N) : Set ℂ :=
  χ.LFunction ⁻¹' {0}

theorem mem_LZeros {χ : DirichletCharacter ℂ N} {z : ℂ} :
    z ∈ LZeros χ ↔ χ.LFunction z = 0 :=
  Iff.rfl

/-- A nontrivial Dirichlet L-function is entire, hence analytic everywhere. -/
theorem analyticOnNhd_LFunction {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1) :
    AnalyticOnNhd ℂ χ.LFunction Set.univ :=
  (differentiable_LFunction hχ).differentiableOn.analyticOnNhd isOpen_univ

/-- The complement of the zero set of a nontrivial Dirichlet L-function is
codiscrete: the L-function is entire and does not vanish at `s = 2`. -/
theorem compl_LZeros_mem_codiscrete {χ : DirichletCharacter ℂ N}
    (hχ : χ ≠ 1) : (LZeros χ)ᶜ ∈ Filter.codiscrete ℂ := by
  have hne : χ.LFunction 2 ≠ 0 :=
    LFunction_ne_zero_of_one_le_re χ (Or.inl hχ) (s := 2) (by norm_num)
  simpa [LZeros, Set.preimage_compl] using
    (analyticOnNhd_LFunction hχ).preimage_zero_mem_codiscrete hne

theorem isClosed_LZeros {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1) :
    IsClosed (LZeros χ) := by
  simpa using (mem_codiscrete'.mp (compl_LZeros_mem_codiscrete hχ)).1

theorem isDiscrete_LZeros {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1) :
    IsDiscrete (LZeros χ) := by
  simpa using (mem_codiscrete'.mp (compl_LZeros_mem_codiscrete hχ)).2

/-- Any compact subset of `ℂ` contains only finitely many zeros of a
nontrivial Dirichlet L-function. -/
theorem inter_LZeros_finite {S : Set ℂ} (hS : IsCompact S)
    {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1) :
    (S ∩ LZeros χ).Finite := by
  apply (hS.inter_right (isClosed_LZeros hχ)).finite
  exact (isDiscrete_LZeros hχ).mono Set.inter_subset_right

end SparkInterval.Dirichlet
