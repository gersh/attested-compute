import SparkInterval.FPIntervalSound

/-! Compile-time regression tests for outward-rounded interval arithmetic. -/

set_option autoImplicit false

namespace SparkInterval.Tests.FPInterval

open SparkInterval

private def exactUnit : RealInterval := ⟨1, 1, le_rfl⟩

example : (FPInterval.quantize exactUnit).ContainsReal 1 := by
  exact FPInterval.quantize_contains (RealInterval.point_contains 1)

example (x : ℝ) : FPInterval.whole.ContainsReal x :=
  FPInterval.whole_contains x

example (X : FPInterval) : FPInterval.whole.add X = FPInterval.whole := by
  rfl

example (X : FPInterval) : FPInterval.whole.sub X = FPInterval.whole := by
  rfl

example (X : FPInterval) : FPInterval.whole.mul X = FPInterval.whole := by
  rfl

example {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.add Y).ContainsReal (x + y) :=
  FPInterval.add_contains hx hy

example {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.sub Y).ContainsReal (x - y) :=
  FPInterval.sub_contains hx hy

example {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.mul Y).ContainsReal (x * y) :=
  FPInterval.mul_contains hx hy

example {X Y : FPInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y)
    (hzero : Y.ExcludesZero) :
    (X.div Y hzero).ContainsReal (x / y) :=
  FPInterval.div_contains hx hy hzero

example (Y : FPInterval) (hzero : Y.ExcludesZero) :
    (FPInterval.whole.div Y hzero) = FPInterval.whole := by
  rfl

#print axioms SparkInterval.FPInterval.quantize_contains
#print axioms SparkInterval.FPInterval.add_contains
#print axioms SparkInterval.FPInterval.sub_contains
#print axioms SparkInterval.FPInterval.mul_contains
#print axioms SparkInterval.FPInterval.div_contains

end SparkInterval.Tests.FPInterval
