import SparkInterval.Expr

/-!
# Exact real semantics

Division by zero and out-of-range variables fail with `none`.
-/

set_option autoImplicit false

namespace SparkInterval

noncomputable section

local instance : DecidableEq ℝ := Classical.decEq ℝ

/-- Evaluate an expression over exact mathematical real numbers. -/
def evalReal : Expr → Array ℝ → Option ℝ
  | .const c, _ => some c
  | .var i, env => env[i]?
  | .neg a, env => do
      let x ← evalReal a env
      pure (-x)
  | .add a b, env => do
      let x ← evalReal a env
      let y ← evalReal b env
      pure (x + y)
  | .sub a b, env => do
      let x ← evalReal a env
      let y ← evalReal b env
      pure (x - y)
  | .mul a b, env => do
      let x ← evalReal a env
      let y ← evalReal b env
      pure (x * y)
  | .div a b, env => do
      let x ← evalReal a env
      let y ← evalReal b env
      if y = 0 then none else some (x / y)
  | .abs a, env => do
      let x ← evalReal a env
      pure |x|
  | .min a b, env => do
      let x ← evalReal a env
      let y ← evalReal b env
      pure (min x y)
  | .max a b, env => do
      let x ← evalReal a env
      let y ← evalReal b env
      pure (max x y)
  | .powNat a n, env => do
      let x ← evalReal a env
      pure (x ^ n)

end

end SparkInterval
