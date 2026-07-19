import SparkInterval.DirectedRounding
import SparkInterval.IntervalOps

/-!
# Outward-rounded binary64 intervals

`FPInterval` has NaN-free extended-binary64 endpoints.  Its finite operations
first interpret both input intervals exactly over `ℝ`, apply the corresponding
exact `RealInterval` operation, and only then round the lower endpoint downward
and the upper endpoint upward.  If an input endpoint is infinite, the operation
returns the conservative whole interval.

The definitions in this file are mathematical specifications, not an
executable use of Lean's runtime `Float`.
-/

set_option autoImplicit false

namespace SparkInterval

/-- A nonempty closed interval with NaN-free extended-binary64 endpoints. -/
structure FPInterval where
  lo : ExtBinary64
  hi : ExtBinary64
  valid : lo.toEReal ≤ hi.toEReal

namespace FPInterval

/-- A real number is contained when its embedding in the extended reals lies
between both endpoints. -/
def ContainsReal (I : FPInterval) (x : ℝ) : Prop :=
  I.lo.toEReal ≤ (x : EReal) ∧ (x : EReal) ≤ I.hi.toEReal

/-- The interval `[-∞, +∞]`. -/
def whole : FPInterval where
  lo := .negInf
  hi := .posInf
  valid := by simp [ExtBinary64.toEReal]

/-- Quantize an exact real interval outward to binary64 endpoints. -/
noncomputable def quantize (I : RealInterval) : FPInterval where
  lo := Binary64Rounding.roundDown I.lo
  hi := Binary64Rounding.roundUp I.hi
  valid := by
    calc
      (Binary64Rounding.roundDown I.lo).toEReal ≤ (I.lo : EReal) :=
        Binary64Rounding.roundDown_le I.lo
      _ ≤ (I.hi : EReal) := EReal.coe_le_coe_iff.mpr I.valid
      _ ≤ (Binary64Rounding.roundUp I.hi).toEReal :=
        Binary64Rounding.le_roundUp I.hi

/-- Recover the exact real interval represented by `I` when both endpoints are
finite.  This is the gate used by every arithmetic operation below. -/
noncomputable def finiteHull? (I : FPInterval) : Option RealInterval :=
  match hlo : I.lo, hhi : I.hi with
  | .finite lo, .finite hi =>
      some {
        lo := lo.1
        hi := hi.1
        valid := by
          have h := I.valid
          rw [hlo, hhi] at h
          exact EReal.coe_le_coe_iff.mp h
      }
  | _, _ => none

/-- An interval excludes zero when it lies strictly on one side of zero in the
extended-real order. -/
def ExcludesZero (I : FPInterval) : Prop :=
  I.hi.toEReal < (0 : EReal) ∨ (0 : EReal) < I.lo.toEReal

/-- Finite-hull extraction preserves zero exclusion. -/
theorem finiteHull_excludesZero {I : FPInterval} {R : RealInterval}
    (hHull : I.finiteHull? = some R) (hzero : I.ExcludesZero) :
    R.ExcludesZero := by
  unfold finiteHull? at hHull
  split at hHull
  next =>
    have hR := Option.some.inj hHull
    subst R
    simp_all [ExcludesZero, RealInterval.ExcludesZero, ExtBinary64.toEReal]
  all_goals simp_all

/-- Apply an exact binary interval operation when all four endpoints are
finite; otherwise return `whole`. -/
noncomputable def liftFinite₂
    (op : RealInterval → RealInterval → RealInterval)
    (X Y : FPInterval) : FPInterval :=
  match X.finiteHull?, Y.finiteHull? with
  | some XR, some YR => quantize (op XR YR)
  | _, _ => whole

/-- Outward-rounded interval addition. -/
noncomputable def add (X Y : FPInterval) : FPInterval :=
  liftFinite₂ RealInterval.add X Y

/-- Outward-rounded interval subtraction. -/
noncomputable def sub (X Y : FPInterval) : FPInterval :=
  liftFinite₂ RealInterval.sub X Y

/-- Outward-rounded interval multiplication. -/
noncomputable def mul (X Y : FPInterval) : FPInterval :=
  liftFinite₂ RealInterval.mul X Y

/-- Outward-rounded interval division.  The supplied evidence excludes zero
from the divisor.  Infinite input endpoints still conservatively produce
`whole`. -/
noncomputable def div (X Y : FPInterval) (hzero : Y.ExcludesZero) : FPInterval :=
  match _hX : X.finiteHull?, hY : Y.finiteHull? with
  | some XR, some YR =>
      quantize (XR.div YR (finiteHull_excludesZero hY hzero))
  | _, _ => whole

end FPInterval

end SparkInterval
