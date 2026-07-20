import SparkInterval.Zeta.EndpointCertificate
import SparkInterval.Dirichlet.Verifier

/-!
# Formal contract for a Dirichlet Hardy-style evaluator

Platt's GRH computation (arXiv:1305.3087) locates sign changes of the real
completed function

`Λ_χ(t) = ε_χ (q/π)^{it/2} Γ((1/2 + a_χ + it)/2) exp(πt/4) L_χ(1/2 + it)`.

The verification layer needs only the mathematical contract captured here:
a continuous real function that differs from `χ.LFunction (1/2 + i t)` by a
nonvanishing complex factor throughout the checked ordinate interval.  For
`Λ_χ` that factor is `ε_χ (q/π)^{it/2} Γ((1/2 + a_χ + it)/2) exp(πt/4)`,
which never vanishes because `Γ` has no zeros.

The file does not assert that an implementation satisfies the contract;
proving the phase, reality, approximation, and remainder theorems for the
concrete evaluator remains the analytic task, exactly as for the Riemann
Hardy-Z contract in `SparkInterval.Zeta.HardyZContract`.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open DirichletCharacter
open SparkInterval.Zeta (criticalPoint RationalBracketFamily ZeroCertificate)

variable {N : ℕ} [NeZero N]

/-- Minimal mathematical interface of a real completed-L evaluator on one
finite ordinate interval. -/
structure DirichletHardyModel
    (χ : DirichletCharacter ℂ N) (f : ℝ → ℝ) (lo hi : ℝ) where
  phase : ℝ → ℂ
  phase_ne_zero : ∀ {t}, t ∈ ordinateDomain lo hi → phase t ≠ 0
  representation : ∀ {t}, t ∈ ordinateDomain lo hi →
    (f t : ℂ) = phase t * χ.LFunction (criticalPoint t)
  continuous : Continuous f

namespace DirichletHardyModel

/-- A nonvanishing phase factor makes zeros of the real evaluator equivalent
to zeros of the L-function on the critical line. -/
theorem zero_iff
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ}
    (model : DirichletHardyModel χ f lo hi) {t : ℝ}
    (ht : t ∈ ordinateDomain lo hi) :
    f t = 0 ↔ χ.LFunction (criticalPoint t) = 0 := by
  constructor
  · intro hzero
    have hcomplex : (f t : ℂ) = 0 := by simp [hzero]
    rw [model.representation ht] at hcomplex
    exact (mul_eq_zero.mp hcomplex).resolve_left (model.phase_ne_zero ht)
  · intro hzero
    have hcomplex : (f t : ℂ) = 0 := by
      rw [model.representation ht, hzero, mul_zero]
    exact_mod_cast hcomplex

/-- Every proved model supplies the analytic bridge expected by the
finite-strip verifier composition. -/
theorem criticalLineZeroBridge
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ}
    (model : DirichletHardyModel χ f lo hi) :
    LCriticalLineZeroBridge χ f lo hi := {
  zero_iff := fun ht => model.zero_iff ht
}

/-- The model's global continuity discharges every local bracket continuity
premise. -/
theorem continuousOnBrackets
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ} {count : Nat}
    (model : DirichletHardyModel χ f lo hi)
    (certificate : ZeroCertificate f count) :
    certificate.ContinuousOnBrackets := by
  intro _i
  exact model.continuous.continuousOn

/-- End-to-end theorem for the executable endpoint checker.  Once an
evaluator proves the endpoint enclosures and a total-count checker proves
the matching upper bound, the Boolean bracket check feeds directly into the
exact finite-strip GRH conclusion for this character. -/
theorem verifyEndpointFamily
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ} {count : Nat}
    (hχ : χ ≠ 1)
    (model : DirichletHardyModel χ f lo hi)
    (family : RationalBracketFamily count)
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints f)
    (hlower : ∀ i, lo ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ hi)
    (totalUpper : LZeroCountUpperBound χ lo hi count) :
    ∀ z ∈ criticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 := by
  obtain ⟨certificate, hendpoints⟩ :=
    family.exists_zeroCertificate hcheck hencloses
  let evidence : GRHVerifierEvidence χ f lo hi count := {
    nontrivial := hχ
    brackets := certificate
    continuous := model.continuousOnBrackets certificate
    liesIn := by
      intro i x hx
      change (certificate.brackets i).lower ≤ x ∧
        x ≤ (certificate.brackets i).upper at hx
      change lo ≤ x ∧ x ≤ hi
      rw [(hendpoints i).1, (hendpoints i).2] at hx
      exact ⟨(hlower i).trans hx.1, hx.2.trans (hupper i)⟩
    bridge := model.criticalLineZeroBridge
    totalUpper := totalUpper
  }
  exact evidence.all_zeros_on_criticalLine

end DirichletHardyModel

end SparkInterval.Dirichlet
