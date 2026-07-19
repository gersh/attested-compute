import SparkInterval.FPInterval
import SparkInterval.IntervalOpsSound

/-!
# Soundness of outward-rounded binary64 intervals

The mathematical binary64 quantizer encloses every member of the exact real
interval that it is given.  The four arithmetic operations inherit their
soundness from the exact `RealInterval` operations.  Operations involving an
infinite input endpoint deliberately return `FPInterval.whole`, which is a
sound conservative result.
-/

set_option autoImplicit false

namespace SparkInterval
namespace FPInterval

/-- Every real number belongs to the conservative whole interval. -/
@[simp] theorem whole_contains (x : ℝ) : whole.ContainsReal x := by
  simp [whole, ContainsReal, ExtBinary64.toEReal]

/-- Outward quantization contains every real contained in its exact input. -/
theorem quantize_contains {I : RealInterval} {x : ℝ}
    (hx : I.Contains x) : (quantize I).ContainsReal x := by
  constructor
  · exact (Binary64Rounding.roundDown_le I.lo).trans
      (EReal.coe_le_coe_iff.mpr hx.1)
  · exact (EReal.coe_le_coe_iff.mpr hx.2).trans
      (Binary64Rounding.le_roundUp I.hi)

/-- If finite endpoint extraction succeeds, containment by the floating-point
interval gives containment by the exact real hull that was extracted. -/
theorem finiteHull_contains_of_containsReal {I : FPInterval}
    {R : RealInterval} {x : ℝ} (hHull : I.finiteHull? = some R)
    (hx : I.ContainsReal x) : R.Contains x := by
  unfold finiteHull? at hHull
  split at hHull
  next =>
    have hR := Option.some.inj hHull
    subst R
    simp_all [ContainsReal, RealInterval.Contains, ExtBinary64.toEReal]
  all_goals simp_all

/-- The generic finite binary-operation lift is sound whenever its exact real
operation is sound. -/
theorem liftFinite₂_contains
    {f : ℝ → ℝ → ℝ}
    (op : RealInterval → RealInterval → RealInterval)
    (hop : ∀ (XR YR : RealInterval) {x y : ℝ},
      XR.Contains x → YR.Contains y → (op XR YR).Contains (f x y))
    {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (liftFinite₂ op X Y).ContainsReal (f x y) := by
  generalize hX : X.finiteHull? = oX
  generalize hY : Y.finiteHull? = oY
  cases oX with
  | none =>
      simp [liftFinite₂, hX, hY]
  | some XR =>
      cases oY with
      | none =>
          simp [liftFinite₂, hX, hY]
      | some YR =>
          simpa [liftFinite₂, hX, hY] using quantize_contains
            (hop XR YR
              (finiteHull_contains_of_containsReal hX hx)
              (finiteHull_contains_of_containsReal hY hy))

/-- Outward-rounded addition contains the exact sum. -/
theorem add_contains {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.add Y).ContainsReal (x + y) := by
  exact liftFinite₂_contains RealInterval.add
    (fun _ _ _ _ => RealInterval.add_contains) hx hy

/-- Outward-rounded subtraction contains the exact difference. -/
theorem sub_contains {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.sub Y).ContainsReal (x - y) := by
  exact liftFinite₂_contains RealInterval.sub
    (fun _ _ _ _ => RealInterval.sub_contains) hx hy

/-- Outward-rounded multiplication contains the exact product. -/
theorem mul_contains {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.mul Y).ContainsReal (x * y) := by
  exact liftFinite₂_contains RealInterval.mul
    (fun _ _ _ _ => RealInterval.mul_contains) hx hy

/-- Outward-rounded division contains the exact quotient whenever the divisor
interval excludes zero. -/
theorem div_contains {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y)
    (hzero : Y.ExcludesZero) :
    (X.div Y hzero).ContainsReal (x / y) := by
  unfold div
  split
  next XR YR hX hY =>
    exact quantize_contains (RealInterval.div_contains
      (finiteHull_contains_of_containsReal hX hx)
      (finiteHull_contains_of_containsReal hY hy)
      (finiteHull_excludesZero hY hzero))
  all_goals exact whole_contains (x / y)

end FPInterval
end SparkInterval
