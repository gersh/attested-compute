import SparkInterval.IntervalOpsSound

/-! A small theorem-level example using the axiom-free real interval core. -/

namespace SparkInterval.Examples

def X : RealInterval where
  lo := 1
  hi := 2
  valid := by norm_num

def Y : RealInterval where
  lo := 3
  hi := 5
  valid := by norm_num

example : X.Contains (3 / 2 : ℝ) := by
  constructor <;> norm_num [X]

example : Y.Contains (4 : ℝ) := by
  constructor <;> norm_num [Y]

example : (X.mul Y).Contains ((3 / 2 : ℝ) * 4) := by
  apply RealInterval.mul_contains
  · constructor <;> norm_num [X]
  · constructor <;> norm_num [Y]

end SparkInterval.Examples
