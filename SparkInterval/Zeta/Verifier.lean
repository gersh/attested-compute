import SparkInterval.Zeta.CriticalLine
import SparkInterval.Zeta.ChunkCertificate

/-!
# Soundness contract for a finite-height zeta-zero verifier

This file connects three independently checkable layers:

1. a real-valued critical-line function whose zeros agree with
   `riemannZeta (1 / 2 + t * I)`;
2. ordered sign-change brackets for that real function; and
3. a global upper bound on the number of zeta zeros in the closed critical
   rectangle.

When the upper bound equals the number of brackets, all inequalities collapse
to equalities.  The result is the exact finite-height theorem about Mathlib's
`riemannZeta` from `CriticalLine`.

The proof is axiom-free and deliberately names the remaining analytic input.
A production high-bound verifier still has to prove the `ZetaZeroCountUpperBound`
field, for example by a rigorous Turing method or argument-principle checker,
and instantiate `CriticalLineZeroBridge` for its checked Hardy-Z evaluator.
Counts here are counts of distinct zero locations, not analytic multiplicity.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set

/-- The real height interval represented by `criticalRectangle`. -/
def heightDomain (height : ℝ) : Set ℝ :=
  Set.Icc (-height) height

/-- Standard parametrization of the critical line. -/
noncomputable def criticalPoint (t : ℝ) : ℂ :=
  ⟨(1 : ℝ) / 2, t⟩

@[simp] theorem criticalPoint_re (t : ℝ) : (criticalPoint t).re = (1 : ℝ) / 2 :=
  rfl

@[simp] theorem criticalPoint_im (t : ℝ) : (criticalPoint t).im = t :=
  rfl

theorem criticalPoint_injective : Function.Injective criticalPoint := by
  intro left right heq
  exact congrArg Complex.im heq

@[simp] theorem criticalPoint_mem_criticalLine (t : ℝ) :
    criticalPoint t ∈ criticalLine := by
  simp [criticalLine]

@[simp] theorem criticalPoint_mem_criticalRectangle {height t : ℝ} :
    criticalPoint t ∈ criticalRectangle height ↔ t ∈ heightDomain height := by
  simp [heightDomain, mem_criticalRectangle]
  norm_num

/-- Analytic bridge required of the real critical-line evaluator used by the
zero-isolation algorithm.  A Hardy-Z implementation should instantiate this
with its phase/nonvanishing and reality theorems. -/
structure CriticalLineZeroBridge (f : ℝ → ℝ) (height : ℝ) : Prop where
  zero_iff : ∀ {t : ℝ}, t ∈ heightDomain height →
    (f t = 0 ↔ riemannZeta (criticalPoint t) = 0)

namespace CriticalLineZeroBridge

/-- Under the zero-equivalence bridge, the real zero set maps exactly onto the
critical-line zeta zeros in the finite rectangle. -/
theorem image_zerosOn_eq_criticalLineZerosIn
    {f : ℝ → ℝ} {height : ℝ}
    (bridge : CriticalLineZeroBridge f height) :
    criticalPoint '' zerosOn f (heightDomain height) =
      criticalLineZerosIn (criticalRectangle height) := by
  ext z
  constructor
  · rintro ⟨t, ⟨ht, hzero⟩, rfl⟩
    exact ⟨
      ⟨criticalPoint_mem_criticalRectangle.mpr ht,
        (bridge.zero_iff ht).mp hzero⟩,
      criticalPoint_mem_criticalLine t⟩
  · rintro ⟨⟨hzrectangle, hzero⟩, hzline⟩
    have hreal : z.re = (1 : ℝ) / 2 := hzline
    have hpoint : criticalPoint z.im = z := by
      apply Complex.ext
      · simpa using hreal.symm
      · rfl
    have hheight : z.im ∈ heightDomain height := by
      rw [← criticalPoint_mem_criticalRectangle]
      simpa [hpoint] using hzrectangle
    refine ⟨z.im, ⟨hheight, ?_⟩, hpoint⟩
    apply (bridge.zero_iff hheight).mpr
    have hzeta : riemannZeta z = 0 := mem_riemannZetaZeros.mp hzero
    simpa [hpoint] using hzeta

/-- Finiteness of compact-region zeta zeros transfers back to the real
critical-line zero set through the injective parametrization. -/
theorem zerosOn_finite {f : ℝ → ℝ} {height : ℝ}
    (bridge : CriticalLineZeroBridge f height) :
    (zerosOn f (heightDomain height)).Finite := by
  apply Set.Finite.of_finite_image
  · rw [bridge.image_zerosOn_eq_criticalLineZerosIn]
    exact (zetaZerosIn_finite (isCompact_criticalRectangle height)).subset
      (criticalLineZerosIn_subset (criticalRectangle height))
  · exact criticalPoint_injective.injOn

/-- The bridge preserves the number of distinct zero locations. -/
theorem criticalLineZerosIn_ncard_eq_zerosOn_ncard
    {f : ℝ → ℝ} {height : ℝ}
    (bridge : CriticalLineZeroBridge f height) :
    (criticalLineZerosIn (criticalRectangle height)).ncard =
      (zerosOn f (heightDomain height)).ncard := by
  rw [← bridge.image_zerosOn_eq_criticalLineZerosIn]
  exact Set.ncard_image_of_injective _ criticalPoint_injective

end CriticalLineZeroBridge

/-- The global counting result required from a Turing-method or
argument-principle certificate.  Compactness already proves finiteness; this
structure records only the application-specific numerical upper bound. -/
structure ZetaZeroCountUpperBound (height : ℝ) (bound : Nat) : Prop where
  count_le :
    (zetaZerosIn (criticalRectangle height)).ncard ≤ bound

namespace CriticalLineZeroBridge

/-- A global zeta-zero upper bound is also an upper bound for the real
critical-line zeros, because those zeros inject into the compact zeta-zero
set. -/
theorem zeroCountUpperBound
    {f : ℝ → ℝ} {height : ℝ} {bound : Nat}
    (bridge : CriticalLineZeroBridge f height)
    (upper : ZetaZeroCountUpperBound height bound) :
    ZeroCountUpperBound f (heightDomain height) bound := by
  refine {
    finite := bridge.zerosOn_finite
    count_le := ?_
  }
  calc
    (zerosOn f (heightDomain height)).ncard =
        (criticalLineZerosIn (criticalRectangle height)).ncard :=
      bridge.criticalLineZerosIn_ncard_eq_zerosOn_ncard.symm
    _ ≤ (zetaZerosIn (criticalRectangle height)).ncard :=
      Set.ncard_le_ncard
        (criticalLineZerosIn_subset (criticalRectangle height))
        (zetaZerosIn_finite (isCompact_criticalRectangle height))
    _ ≤ bound := upper.count_le

end CriticalLineZeroBridge

/-- All mathematical evidence consumed by the final finite-height verifier.
The large bracket family may later be supplied chunk-by-chunk; this structure
states its logical content independently of storage format. -/
structure ZetaVerifierEvidence (f : ℝ → ℝ) (height : ℝ) (count : Nat) where
  brackets : ZeroCertificate f count
  continuous : brackets.ContinuousOnBrackets
  liesIn : brackets.LiesIn (heightDomain height)
  bridge : CriticalLineZeroBridge f height
  totalUpper : ZetaZeroCountUpperBound height count

namespace ZetaVerifierEvidence

/-- The checked brackets account for exactly all distinct critical-line zeros
in the finite rectangle. -/
theorem exact_criticalLine_count
    {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (evidence : ZetaVerifierEvidence f height count) :
    (criticalLineZerosIn (criticalRectangle height)).ncard = count := by
  have complete := evidence.brackets.complete_of_count_upperBound
    evidence.continuous evidence.liesIn
    (evidence.bridge.zeroCountUpperBound evidence.totalUpper)
  calc
    (criticalLineZerosIn (criticalRectangle height)).ncard =
        (zerosOn f (heightDomain height)).ncard :=
      evidence.bridge.criticalLineZerosIn_ncard_eq_zerosOn_ncard
    _ = count := complete.exactCount

/-- The bracket count and global upper bound force equality between the number
of critical-line zeros and all zeta zeros in the rectangle. -/
theorem exact_total_count
    {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (evidence : ZetaVerifierEvidence f height count) :
    (criticalLineZerosIn (criticalRectangle height)).ncard =
      (zetaZerosIn (criticalRectangle height)).ncard := by
  apply Nat.le_antisymm
  · exact Set.ncard_le_ncard
      (criticalLineZerosIn_subset (criticalRectangle height))
      (zetaZerosIn_finite (isCompact_criticalRectangle height))
  · rw [evidence.exact_criticalLine_count]
    exact evidence.totalUpper.count_le

/-- Final finite-height zeta-zero theorem.  Once the analytic bridge and count
upper bound are proved for the executable checker, no further zeta-specific
assumption is used downstream. -/
theorem all_zeros_on_criticalLine
    {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (evidence : ZetaVerifierEvidence f height count) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  all_zeros_to_height_on_criticalLine evidence.exact_total_count

end ZetaVerifierEvidence

/-! ## Chunked high-bound handoff -/

/-- The high-bound form of `ZetaVerifierEvidence`.  Its logical root count is
the sum of independently sized chunks, avoiding a monolithic `Fin count`
index in the producer and permitting a future streaming checker to discharge
the local fields one chunk at a time. -/
structure ChunkedZetaVerifierEvidence
    (f : ℝ → ℝ) (height : ℝ) (chunkCount : Nat) where
  chunks : ChunkCertificate f chunkCount
  continuous : chunks.ContinuousOnChunks
  liesIn : chunks.LiesIn (heightDomain height)
  bridge : CriticalLineZeroBridge f height
  totalUpper : ZetaZeroCountUpperBound height chunks.totalCount

namespace ChunkedZetaVerifierEvidence

/-- The sum of all chunk-local bracket counts is exactly the number of
distinct critical-line zeros in the finite rectangle. -/
theorem exact_criticalLine_count
    {f : ℝ → ℝ} {height : ℝ} {chunkCount : Nat}
    (evidence : ChunkedZetaVerifierEvidence f height chunkCount) :
    (criticalLineZerosIn (criticalRectangle height)).ncard =
      evidence.chunks.totalCount := by
  have complete := evidence.chunks.complete_of_count_upperBound
    evidence.continuous evidence.liesIn
    (evidence.bridge.zeroCountUpperBound evidence.totalUpper)
  calc
    (criticalLineZerosIn (criticalRectangle height)).ncard =
        (zerosOn f (heightDomain height)).ncard :=
      evidence.bridge.criticalLineZerosIn_ncard_eq_zerosOn_ncard
    _ = evidence.chunks.totalCount := complete.exactCount

/-- The additive chunk lower bound and global upper bound force exact equality
with the total compact-region zeta-zero count. -/
theorem exact_total_count
    {f : ℝ → ℝ} {height : ℝ} {chunkCount : Nat}
    (evidence : ChunkedZetaVerifierEvidence f height chunkCount) :
    (criticalLineZerosIn (criticalRectangle height)).ncard =
      (zetaZerosIn (criticalRectangle height)).ncard := by
  apply Nat.le_antisymm
  · exact Set.ncard_le_ncard
      (criticalLineZerosIn_subset (criticalRectangle height))
      (zetaZerosIn_finite (isCompact_criticalRectangle height))
  · rw [evidence.exact_criticalLine_count]
    exact evidence.totalUpper.count_le

/-- Final theorem exposed by the chunked high-bound architecture. -/
theorem all_zeros_on_criticalLine
    {f : ℝ → ℝ} {height : ℝ} {chunkCount : Nat}
    (evidence : ChunkedZetaVerifierEvidence f height chunkCount) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  all_zeros_to_height_on_criticalLine evidence.exact_total_count

end ChunkedZetaVerifierEvidence

end SparkInterval.Zeta
