import SparkInterval.PTX.PowSchedule

/-! Regression tests for the version-2 binary power schedule foundation. -/

set_option autoImplicit false

namespace SparkInterval.Tests.PTXPowSchedule

open SparkInterval.PTX

example : powMulCount 0 = 0 := by decide
example : powMulCount 1 = 1 := by decide
example : powMulCount 2 = 2 := by decide
example : powMulCount 3 = 3 := by decide
example : powMulCount 4 = 3 := by decide
example : powMulCount 8 = 4 := by decide
example : powMulCount 16 = 5 := by decide
example : powMulCount 32 = 6 := by decide
example : powMulCount 63 = 11 := by decide
example : powMulCount 64 = 7 := by decide

example : runPowValues (2 : Nat) (powSchedule 64) 1 = 2 ^ 64 :=
  runPowSchedule_eq_pow 2 64

end SparkInterval.Tests.PTXPowSchedule
