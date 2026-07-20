import Mathlib.Analysis.Analytic.Order
import SparkInterval.Zeta.Verifier

/-!
# Multiplicity-aware zeta-zero count certificates

The finite-height verifier counts distinct zero locations with `Set.ncard`, while
an argument-principle or Riemann--von Mangoldt theorem naturally counts zeros
with analytic multiplicity.  This module proves the missing safe direction:

```text
distinct zero count <= analytic multiplicity count <= certified upper bound.
```

Multiplicity is Mathlib's `analyticOrderAt riemannZeta z`, valued in `ℕ∞`.
Keeping the count in `ℕ∞` is important: it does not silently map an infinite
order to zero.  Every zeta zero in the finite rectangle is away from `1`, so
`riemannZeta` is analytic there and its order is nonzero.  Consequently every
distinct zero contributes at least one to the multiplicity sum.

The genuinely analytic step remains explicit as
`ZetaMultiplicityCountUpperBound`.  A future checked Turing-method or
argument-principle implementation must construct that proposition.  The small
Boolean certificate below checks only the arithmetic comparison between the
analytic count claimed by that theorem and the upper bound consumed by the
finite-height verifier.

No simplicity assumption is made, and no execution or attestation axiom is
used in this module.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set
open scoped BigOperators

/-- Analytic multiplicity of a zeta zero.  At nonzeros (and at the exceptional
non-analytic point `1`) this value is not used as a zero multiplicity. -/
noncomputable def zetaZeroMultiplicity (z : ℂ) : ℕ∞ :=
  analyticOrderAt riemannZeta z

/-- Every zeta zero has analytic multiplicity at least one.  In particular, the
junk non-analytic value of `analyticOrderAt` at `1` is irrelevant because
Mathlib proves `riemannZeta 1 != 0`. -/
theorem one_le_zetaZeroMultiplicity {z : ℂ} (hz : z ∈ riemannZetaZeros) :
    (1 : ℕ∞) ≤ zetaZeroMultiplicity z := by
  have hzero : riemannZeta z = 0 := mem_riemannZetaZeros.mp hz
  have hneOne : z ≠ 1 := by
    intro h
    subst z
    exact riemannZeta_one_ne_zero hzero
  have hmem : z ∈ ({1} : Set ℂ)ᶜ := by
    simpa only [Set.mem_compl_iff, Set.mem_singleton_iff] using hneOne
  have hanalytic : AnalyticAt ℂ riemannZeta z :=
    analyticOn_riemannZeta z hmem
  apply Order.one_le_iff_ne_zero.mpr
  exact hanalytic.analyticOrderAt_ne_zero.mpr hzero

/-- The finite set of distinct zeta-zero locations in the closed critical
rectangle.  This is a theorem-level enumeration, not an executable zero finder. -/
noncomputable def zetaZerosFinset (height : ℝ) : Finset ℂ :=
  (zetaZerosIn_finite (isCompact_criticalRectangle height)).toFinset

@[simp] theorem mem_zetaZerosFinset {height : ℝ} {z : ℂ} :
    z ∈ zetaZerosFinset height ↔
      z ∈ zetaZerosIn (criticalRectangle height) := by
  classical
  simp [zetaZerosFinset]

theorem card_zetaZerosFinset (height : ℝ) :
    (zetaZerosFinset height).card =
      (zetaZerosIn (criticalRectangle height)).ncard := by
  classical
  unfold zetaZerosFinset
  exact (Set.ncard_eq_toFinset_card
    (zetaZerosIn (criticalRectangle height))
    (zetaZerosIn_finite (isCompact_criticalRectangle height))).symm

/-- Total analytic multiplicity of all zeta zeros in the closed critical
rectangle.  The finite outer sum is in `ℕ∞`, so a locally identically-zero
function would contribute `⊤` rather than being silently truncated. -/
noncomputable def zetaZeroMultiplicityCount (height : ℝ) : ℕ∞ :=
  ∑ z ∈ zetaZerosFinset height, zetaZeroMultiplicity z

/-- The number of distinct zero locations is bounded by the total analytic
multiplicity, without assuming that any zero is simple. -/
theorem coe_ncard_le_zetaZeroMultiplicityCount (height : ℝ) :
    ((zetaZerosIn (criticalRectangle height)).ncard : ℕ∞) ≤
      zetaZeroMultiplicityCount height := by
  classical
  rw [← card_zetaZerosFinset height, zetaZeroMultiplicityCount]
  calc
    ((zetaZerosFinset height).card : ℕ∞) =
        ∑ _z ∈ zetaZerosFinset height, (1 : ℕ∞) := by simp
    _ ≤ ∑ z ∈ zetaZerosFinset height, zetaZeroMultiplicity z := by
      apply Finset.sum_le_sum
      intro z hz
      exact one_le_zetaZeroMultiplicity (mem_zetaZerosFinset.mp hz).2

/-- The explicit analytic oracle boundary.  A rigorous Turing-method,
Riemann--von Mangoldt, or argument-principle proof should construct this value
from its own checked interval evidence and boundary conventions. -/
structure ZetaMultiplicityCountUpperBound (height : ℝ) (bound : Nat) : Prop where
  count_le : zetaZeroMultiplicityCount height ≤ (bound : ℕ∞)

namespace ZetaMultiplicityCountUpperBound

/-- A multiplicity-count upper bound is automatically an upper bound on the
number of distinct zeta-zero locations. -/
theorem distinctCount_le {height : ℝ} {bound : Nat}
    (upper : ZetaMultiplicityCountUpperBound height bound) :
    (zetaZerosIn (criticalRectangle height)).ncard ≤ bound := by
  have hcast :
      ((zetaZerosIn (criticalRectangle height)).ncard : ℕ∞) ≤
        (bound : ℕ∞) :=
    (coe_ncard_le_zetaZeroMultiplicityCount height).trans upper.count_le
  exact ENat.coe_le_coe.mp hcast

/-- Handoff to the existing finite-height verifier's distinct-count contract. -/
theorem toZetaZeroCountUpperBound {height : ℝ} {bound : Nat}
    (upper : ZetaMultiplicityCountUpperBound height bound) :
    ZetaZeroCountUpperBound height bound := {
  count_le := upper.distinctCount_le
}

end ZetaMultiplicityCountUpperBound

/-! ## Small checked arithmetic wrapper -/

/-- Untrusted numeric output of an analytic zero-count checker.  The first
number is the multiplicity-count upper bound justified by the analytic proof;
the second is the (usually bracket-derived) bound requested by the verifier. -/
structure ZetaMultiplicityCountCertificate where
  claimedMultiplicityCount : Nat
  upperBound : Nat
  deriving DecidableEq, Repr

namespace ZetaMultiplicityCountCertificate

/-- Exact arithmetic proposition reflected by `check`. -/
def IsValid (certificate : ZetaMultiplicityCountCertificate) : Prop :=
  certificate.claimedMultiplicityCount ≤ certificate.upperBound

instance (certificate : ZetaMultiplicityCountCertificate) :
    Decidable certificate.IsValid := by
  unfold IsValid
  infer_instance

/-- Executable arithmetic check.  This does not pretend to check the analytic
Turing/argument-principle proof represented by `ZetaMultiplicityCountUpperBound`. -/
def check (certificate : ZetaMultiplicityCountCertificate) : Bool :=
  decide certificate.IsValid

@[simp] theorem check_eq_true {certificate : ZetaMultiplicityCountCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check]

@[simp] theorem check_eq_false {certificate : ZetaMultiplicityCountCertificate} :
    certificate.check = false ↔ ¬certificate.IsValid := by
  simp [check]

/-- Sound checked handoff.  The Boolean check supplies only the final natural
inequality; `analyticUpper` is the deliberately explicit analytic premise. -/
theorem check_sound {height : ℝ}
    (certificate : ZetaMultiplicityCountCertificate)
    (hcheck : certificate.check = true)
    (analyticUpper : ZetaMultiplicityCountUpperBound height
      certificate.claimedMultiplicityCount) :
    ZetaZeroCountUpperBound height certificate.upperBound := by
  have hvalid : certificate.IsValid := certificate.check_eq_true.mp hcheck
  have hcast : (certificate.claimedMultiplicityCount : ℕ∞) ≤
      (certificate.upperBound : ℕ∞) := ENat.coe_le_coe.mpr hvalid
  exact (ZetaMultiplicityCountUpperBound.mk
    (analyticUpper.count_le.trans hcast)).toZetaZeroCountUpperBound

end ZetaMultiplicityCountCertificate

end SparkInterval.Zeta
