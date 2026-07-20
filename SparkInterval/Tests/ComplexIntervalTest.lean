import SparkInterval.ComplexInterval

set_option autoImplicit false

namespace SparkInterval.Tests.ComplexInterval

open SparkInterval
open SparkInterval.ComplexInterval

private def left : SparkInterval.ComplexInterval where
  re := ⟨1, 2, by norm_num⟩
  im := ⟨3, 4, by norm_num⟩

private def right : SparkInterval.ComplexInterval where
  re := ⟨5, 6, by norm_num⟩
  im := ⟨7, 8, by norm_num⟩

private def x : ℂ := ⟨2, 3⟩
private def y : ℂ := ⟨5, 7⟩

example : left.Contains x := by
  norm_num [left, x, Contains, RealInterval.Contains]

example : right.Contains y := by
  norm_num [right, y, Contains, RealInterval.Contains]

example : (left.mul right).re.lo = -27 := by
  norm_num [left, right, ComplexInterval.mul, RealInterval.mul, RealInterval.sub]

example : (left.mul right).re.hi = -9 := by
  norm_num [left, right, ComplexInterval.mul, RealInterval.mul, RealInterval.sub]

example : (left.mul right).im.lo = 22 := by
  norm_num [left, right, ComplexInterval.mul, RealInterval.mul, RealInterval.add]

example : (left.mul right).im.hi = 40 := by
  norm_num [left, right, ComplexInterval.mul, RealInterval.mul, RealInterval.add]

example : (left.mul right).Contains (x * y) := by
  apply mul_contains
  · norm_num [left, x, Contains, RealInterval.Contains]
  · norm_num [right, y, Contains, RealInterval.Contains]

example (z : ℂ) : (point z).square.Contains (z ^ 2) := by
  exact square_contains (point_contains z)

example : left.powNat 5 |>.Contains (x ^ 5) := by
  apply powNat_contains
  norm_num [left, x, Contains, RealInterval.Contains]

end SparkInterval.Tests.ComplexInterval
