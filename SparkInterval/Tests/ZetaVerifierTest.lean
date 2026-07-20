import SparkInterval.Zeta.Verifier

/-! Type-level regression tests for the finite-height verifier composition. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaVerifier

open SparkInterval.Zeta

example {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (evidence : ZetaVerifierEvidence f height count) :
    (criticalLineZerosIn (criticalRectangle height)).ncard =
      (zetaZerosIn (criticalRectangle height)).ncard :=
  evidence.exact_total_count

example {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (evidence : ZetaVerifierEvidence f height count) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  evidence.all_zeros_on_criticalLine

example {f : ℝ → ℝ} {height : ℝ} {chunkCount : Nat}
    (evidence : ChunkedZetaVerifierEvidence f height chunkCount) :
    (criticalLineZerosIn (criticalRectangle height)).ncard =
      (zetaZerosIn (criticalRectangle height)).ncard :=
  evidence.exact_total_count

example {f : ℝ → ℝ} {height : ℝ} {chunkCount : Nat}
    (evidence : ChunkedZetaVerifierEvidence f height chunkCount) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  evidence.all_zeros_on_criticalLine

end SparkInterval.Tests.ZetaVerifier
