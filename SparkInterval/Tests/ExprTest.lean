import SparkInterval.EvalSound

set_option autoImplicit false

namespace SparkInterval.Tests.Expr

open SparkInterval

noncomputable section

private def realEnv : Array ℝ := #[2, -3]

private def intervalEnv : Array RealInterval :=
  #[⟨1, 3, by norm_num⟩, ⟨-4, -2, by norm_num⟩]

private theorem environmentsCorrespond :
    EnvironmentsCorrespond realEnv intervalEnv := by
  intro i
  rcases i with _ | i
  · norm_num [realEnv, intervalEnv, RealInterval.Contains]
  · rcases i with _ | i
    · norm_num [realEnv, intervalEnv, RealInterval.Contains]
    · simp [realEnv, intervalEnv]

private def quotientExpr : Expr :=
  .div (.add (.var 0) (.const 1)) (.var 1)

example : evalReal quotientExpr realEnv = some (-1) := by
  norm_num [quotientExpr, evalReal, realEnv]

example : ∃ result, evalInterval quotientExpr intervalEnv = some result := by
  norm_num [quotientExpr, evalInterval, intervalEnv, RealInterval.ExcludesZero]

example {result : RealInterval}
    (hint : evalInterval quotientExpr intervalEnv = some result) :
    result.Contains (-1) := by
  exact evalInterval_sound (expr := quotientExpr) environmentsCorrespond
    (by norm_num [quotientExpr, evalReal, realEnv]) hint

private def crossingZeroEnv : Array RealInterval :=
  #[⟨1, 3, by norm_num⟩, ⟨-1, 1, by norm_num⟩]

example : evalInterval quotientExpr crossingZeroEnv = none := by
  norm_num [quotientExpr, evalInterval, crossingZeroEnv, RealInterval.ExcludesZero]

private def compositeExpr : Expr :=
  .max (.abs (.var 1)) (.powNat (.sub (.var 0) (.const 1)) 2)

example : evalReal compositeExpr realEnv = some 3 := by
  norm_num [compositeExpr, evalReal, realEnv]

end

end SparkInterval.Tests.Expr
