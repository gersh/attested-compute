import SparkInterval.Dirichlet.CriticalLine
import SparkInterval.Zeta.Verifier

/-!
# Soundness contract for a finite-strip GRH verifier

Dirichlet analogue of `SparkInterval.Zeta.Verifier`.  Three independently
checkable layers combine:

1. a real-valued critical-line evaluator whose zeros agree with
   `χ.LFunction (1/2 + t*I)` on the checked ordinate interval;
2. ordered sign-change brackets for that real function; and
3. a global upper bound on the number of L-function zeros in the closed
   rectangle `[0,1] x [lo,hi]`.

When the upper bound equals the number of brackets, all inequalities
collapse and every zero in the rectangle lies on the critical line.  The
proof is axiom-free; a production verifier still has to prove the
`LZeroCountUpperBound` field (Turing method or argument principle) and the
`LCriticalLineZeroBridge` for its checked evaluator.  Counts are counts of
distinct zero locations, not analytic multiplicity.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open Set DirichletCharacter
open SparkInterval.Zeta (criticalPoint criticalPoint_injective)

variable {N : ℕ} [NeZero N]

/-- The real ordinate interval represented by `criticalStrip`. -/
def ordinateDomain (lo hi : ℝ) : Set ℝ :=
  Set.Icc lo hi

@[simp] theorem criticalPoint_mem_criticalStrip {lo hi t : ℝ} :
    criticalPoint t ∈ criticalStrip lo hi ↔ t ∈ ordinateDomain lo hi := by
  simp [ordinateDomain, mem_criticalStrip, SparkInterval.Zeta.criticalPoint]
  norm_num

theorem criticalPoint_mem_criticalLine (t : ℝ) :
    criticalPoint t ∈ Zeta.criticalLine :=
  SparkInterval.Zeta.criticalPoint_mem_criticalLine t

/-- Analytic bridge required of the real critical-line evaluator: its zeros
on the checked ordinate interval agree exactly with the L-function zeros on
the critical line. -/
structure LCriticalLineZeroBridge
    (χ : DirichletCharacter ℂ N) (f : ℝ → ℝ) (lo hi : ℝ) : Prop where
  zero_iff : ∀ {t : ℝ}, t ∈ ordinateDomain lo hi →
    (f t = 0 ↔ χ.LFunction (criticalPoint t) = 0)

namespace LCriticalLineZeroBridge

/-- Under the zero-equivalence bridge, the real zero set maps exactly onto
the critical-line L-function zeros in the rectangle. -/
theorem image_zerosOn_eq_criticalLineLZerosIn
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ}
    (bridge : LCriticalLineZeroBridge χ f lo hi) :
    criticalPoint '' Zeta.zerosOn f (ordinateDomain lo hi) =
      criticalLineLZerosIn χ (criticalStrip lo hi) := by
  ext z
  constructor
  · rintro ⟨t, ⟨ht, hzero⟩, rfl⟩
    exact ⟨
      ⟨criticalPoint_mem_criticalStrip.mpr ht,
        (bridge.zero_iff ht).mp hzero⟩,
      criticalPoint_mem_criticalLine t⟩
  · rintro ⟨⟨hzstrip, hzero⟩, hzline⟩
    have hreal : z.re = (1 : ℝ) / 2 := hzline
    have hpoint : criticalPoint z.im = z := by
      apply Complex.ext
      · simpa using hreal.symm
      · rfl
    have hordinate : z.im ∈ ordinateDomain lo hi := by
      rw [← criticalPoint_mem_criticalStrip]
      simpa [hpoint] using hzstrip
    refine ⟨z.im, ⟨hordinate, ?_⟩, hpoint⟩
    apply (bridge.zero_iff hordinate).mpr
    have hLzero : χ.LFunction z = 0 := mem_LZeros.mp hzero
    simpa [hpoint] using hLzero

/-- Finiteness of compact-region L-function zeros transfers back to the real
critical-line zero set through the injective parametrization. -/
theorem zerosOn_finite
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ}
    (hχ : χ ≠ 1) (bridge : LCriticalLineZeroBridge χ f lo hi) :
    (Zeta.zerosOn f (ordinateDomain lo hi)).Finite := by
  apply Set.Finite.of_finite_image
  · rw [bridge.image_zerosOn_eq_criticalLineLZerosIn]
    exact (LZerosIn_finite hχ (isCompact_criticalStrip lo hi)).subset
      (criticalLineLZerosIn_subset χ (criticalStrip lo hi))
  · exact criticalPoint_injective.injOn

/-- The bridge preserves the number of distinct zero locations. -/
theorem criticalLineLZerosIn_ncard_eq_zerosOn_ncard
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ}
    (bridge : LCriticalLineZeroBridge χ f lo hi) :
    (criticalLineLZerosIn χ (criticalStrip lo hi)).ncard =
      (Zeta.zerosOn f (ordinateDomain lo hi)).ncard := by
  rw [← bridge.image_zerosOn_eq_criticalLineLZerosIn]
  exact Set.ncard_image_of_injective _ criticalPoint_injective

end LCriticalLineZeroBridge

/-- The global counting result required from a Turing-method or
argument-principle certificate for one character and one rectangle. -/
structure LZeroCountUpperBound
    (χ : DirichletCharacter ℂ N) (lo hi : ℝ) (bound : Nat) : Prop where
  count_le :
    (LZerosIn χ (criticalStrip lo hi)).ncard ≤ bound

namespace LCriticalLineZeroBridge

/-- A global L-zero upper bound is also an upper bound for the real
critical-line zeros. -/
theorem zeroCountUpperBound
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ} {bound : Nat}
    (hχ : χ ≠ 1)
    (bridge : LCriticalLineZeroBridge χ f lo hi)
    (upper : LZeroCountUpperBound χ lo hi bound) :
    Zeta.ZeroCountUpperBound f (ordinateDomain lo hi) bound := by
  refine {
    finite := bridge.zerosOn_finite hχ
    count_le := ?_
  }
  calc
    (Zeta.zerosOn f (ordinateDomain lo hi)).ncard =
        (criticalLineLZerosIn χ (criticalStrip lo hi)).ncard :=
      bridge.criticalLineLZerosIn_ncard_eq_zerosOn_ncard.symm
    _ ≤ (LZerosIn χ (criticalStrip lo hi)).ncard :=
      Set.ncard_le_ncard
        (criticalLineLZerosIn_subset χ (criticalStrip lo hi))
        (LZerosIn_finite hχ (isCompact_criticalStrip lo hi))
    _ ≤ bound := upper.count_le

end LCriticalLineZeroBridge

/-- All mathematical evidence consumed by the finite-strip GRH verifier for
one nontrivial character. -/
structure GRHVerifierEvidence
    (χ : DirichletCharacter ℂ N) (f : ℝ → ℝ) (lo hi : ℝ) (count : Nat) where
  nontrivial : χ ≠ 1
  brackets : Zeta.ZeroCertificate f count
  continuous : brackets.ContinuousOnBrackets
  liesIn : brackets.LiesIn (ordinateDomain lo hi)
  bridge : LCriticalLineZeroBridge χ f lo hi
  totalUpper : LZeroCountUpperBound χ lo hi count

namespace GRHVerifierEvidence

/-- The checked brackets account for exactly all distinct critical-line
zeros in the rectangle. -/
theorem exact_criticalLine_count
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ} {count : Nat}
    (evidence : GRHVerifierEvidence χ f lo hi count) :
    (criticalLineLZerosIn χ (criticalStrip lo hi)).ncard = count := by
  have complete := evidence.brackets.complete_of_count_upperBound
    evidence.continuous evidence.liesIn
    (evidence.bridge.zeroCountUpperBound evidence.nontrivial
      evidence.totalUpper)
  calc
    (criticalLineLZerosIn χ (criticalStrip lo hi)).ncard =
        (Zeta.zerosOn f (ordinateDomain lo hi)).ncard :=
      evidence.bridge.criticalLineLZerosIn_ncard_eq_zerosOn_ncard
    _ = count := complete.exactCount

/-- The bracket count and global upper bound force equality between the
number of critical-line zeros and all L-function zeros in the rectangle. -/
theorem exact_total_count
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ} {count : Nat}
    (evidence : GRHVerifierEvidence χ f lo hi count) :
    (criticalLineLZerosIn χ (criticalStrip lo hi)).ncard =
      (LZerosIn χ (criticalStrip lo hi)).ncard := by
  apply Nat.le_antisymm
  · exact Set.ncard_le_ncard
      (criticalLineLZerosIn_subset χ (criticalStrip lo hi))
      (LZerosIn_finite evidence.nontrivial (isCompact_criticalStrip lo hi))
  · rw [evidence.exact_criticalLine_count]
    exact evidence.totalUpper.count_le

/-- Final finite-strip GRH theorem for one nontrivial character. -/
theorem all_zeros_on_criticalLine
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ} {count : Nat}
    (evidence : GRHVerifierEvidence χ f lo hi count) :
    ∀ z ∈ criticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  all_zeros_in_strip_on_criticalLine evidence.nontrivial
    evidence.exact_total_count

end GRHVerifierEvidence

end SparkInterval.Dirichlet
