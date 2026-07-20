import SparkInterval.Zeta.EndpointCertificate
import SparkInterval.Zeta.Verifier

/-!
# Formal contract for a Hardy-Z evaluator

The production evaluator may use Riemann-Siegel, an amortized transform, or a
different certified formula.  The zero-verification layer needs only the
mathematical contract captured here: a continuous real function differs from
`riemannZeta (1/2 + i t)` by a nonzero complex factor throughout the checked
height interval.

`HardyZModel.criticalLineZeroBridge` proves that this representation supplies
the exact zero-equivalence consumed by `ZetaVerifierEvidence`.  The file does
not assert that an implementation satisfies the contract; proving the phase,
reality, approximation, and remainder theorems remains the analytic task.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

/-- Minimal mathematical interface of a real Hardy-Z-style evaluator on one
finite height interval. -/
structure HardyZModel (f : ℝ → ℝ) (height : ℝ) where
  phase : ℝ → ℂ
  phase_ne_zero : ∀ {t}, t ∈ heightDomain height → phase t ≠ 0
  representation : ∀ {t}, t ∈ heightDomain height →
    (f t : ℂ) = phase t * riemannZeta (criticalPoint t)
  continuous : Continuous f

namespace HardyZModel

/-- A nonvanishing Hardy factor makes zeros of the real evaluator equivalent
to zeros of zeta on the critical line. -/
theorem zero_iff {f : ℝ → ℝ} {height : ℝ}
    (model : HardyZModel f height) {t : ℝ}
    (ht : t ∈ heightDomain height) :
    f t = 0 ↔ riemannZeta (criticalPoint t) = 0 := by
  constructor
  · intro hzero
    have hcomplex : (f t : ℂ) = 0 := by simp [hzero]
    rw [model.representation ht] at hcomplex
    exact (mul_eq_zero.mp hcomplex).resolve_left (model.phase_ne_zero ht)
  · intro hzero
    have hcomplex : (f t : ℂ) = 0 := by
      rw [model.representation ht, hzero, mul_zero]
    exact_mod_cast hcomplex

/-- Every proved Hardy-Z model supplies the analytic bridge expected by the
finite-height verifier composition. -/
theorem criticalLineZeroBridge {f : ℝ → ℝ} {height : ℝ}
    (model : HardyZModel f height) : CriticalLineZeroBridge f height := {
  zero_iff := fun ht => model.zero_iff ht
}

/-- The model's global continuity discharges every local bracket continuity
premise in the monolithic certificate. -/
theorem continuousOnBrackets {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (model : HardyZModel f height)
    (certificate : ZeroCertificate f count) :
    certificate.ContinuousOnBrackets := by
  intro _i
  exact model.continuous.continuousOn

/-- The same continuity handoff for independently produced chunks. -/
theorem continuousOnChunks {f : ℝ → ℝ} {height : ℝ} {chunkCount : Nat}
    (model : HardyZModel f height)
    (certificate : ChunkCertificate f chunkCount) :
    certificate.ContinuousOnChunks := by
  intro _chunk _index
  exact model.continuous.continuousOn

/-- End-to-end theorem for the current executable endpoint checker.  Once an
evaluator proves the endpoint enclosures and a total-count checker proves the
matching upper bound, the Boolean bracket check feeds directly into the exact
finite-height zeta conclusion. -/
theorem verifyEndpointFamily
    {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (model : HardyZModel f height)
    (family : RationalBracketFamily count)
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints f)
    (hlower : ∀ i, -height ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 := by
  obtain ⟨certificate, hendpoints⟩ :=
    family.exists_zeroCertificate hcheck hencloses
  let evidence : ZetaVerifierEvidence f height count := {
    brackets := certificate
    continuous := model.continuousOnBrackets certificate
    liesIn := by
      intro i x hx
      change (certificate.brackets i).lower ≤ x ∧
        x ≤ (certificate.brackets i).upper at hx
      change -height ≤ x ∧ x ≤ height
      rw [(hendpoints i).1, (hendpoints i).2] at hx
      exact ⟨(hlower i).trans hx.1, hx.2.trans (hupper i)⟩
    bridge := model.criticalLineZeroBridge
    totalUpper := totalUpper
  }
  exact evidence.all_zeros_on_criticalLine

end HardyZModel

end SparkInterval.Zeta
