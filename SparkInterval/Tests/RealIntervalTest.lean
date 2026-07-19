import SparkInterval.IntervalOpsSound

set_option autoImplicit false

namespace SparkInterval.Tests.RealInterval

open SparkInterval
open SparkInterval.RealInterval

private def mixed : RealInterval := ⟨-2, 3, by norm_num⟩
private def positive : RealInterval := ⟨2, 4, by norm_num⟩
private def negative : RealInterval := ⟨-4, -2, by norm_num⟩
private def upperPositive : RealInterval := ⟨4, 5, by norm_num⟩

private theorem positive_excludesZero : positive.ExcludesZero := by
  right
  norm_num [positive]

private theorem negative_excludesZero : negative.ExcludesZero := by
  left
  norm_num [negative]

example : (mixed.add positive).lo = 0 := by
  norm_num [mixed, positive, RealInterval.add]

example : (mixed.sub positive).hi = 1 := by
  norm_num [mixed, positive, RealInterval.sub]

example : (mixed.mul upperPositive).lo = -10 := by
  norm_num [mixed, upperPositive, RealInterval.mul]

example : (mixed.mul upperPositive).hi = 15 := by
  norm_num [mixed, upperPositive, RealInterval.mul]

example : (positive.reciprocal positive_excludesZero).lo = (1 / 4 : ℝ) := by
  rfl

example : (positive.reciprocal positive_excludesZero).hi = (1 / 2 : ℝ) := by
  rfl

example : (negative.reciprocal negative_excludesZero).lo = (-1 / 2 : ℝ) := by
  norm_num [RealInterval.reciprocal, negative]

example : (negative.reciprocal negative_excludesZero).hi = (-1 / 4 : ℝ) := by
  norm_num [RealInterval.reciprocal, negative]

example : (positive.div positive positive_excludesZero).Contains 1 := by
  simpa [positive] using
    div_contains positive.contains_lo positive.contains_lo positive_excludesZero

example : mixed.abs.lo = 0 := by
  norm_num [RealInterval.abs, mixed]

example : mixed.abs.hi = 3 := by
  norm_num [RealInterval.abs, mixed]

example : (mixed.powNat 3).Contains ((-1 : ℝ) ^ 3) := by
  apply powNat_contains
  norm_num [Contains, mixed]

end SparkInterval.Tests.RealInterval
