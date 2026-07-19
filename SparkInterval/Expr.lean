import SparkInterval.IntervalOpsSound

/-!
# Interval expression language

Constants in the Phase 1 language are exact mathematical real values.  The
interval semantics encloses each one by a singleton.  A later floating-point
phase can replace that singleton construction with verified directed rounding
without changing the recursive proof pattern.
-/

set_option autoImplicit false

namespace SparkInterval

/-- A small, first-order expression language suitable for one GPU thread. -/
inductive Expr where
  | const : ℝ → Expr
  | var : Nat → Expr
  | neg : Expr → Expr
  | add : Expr → Expr → Expr
  | sub : Expr → Expr → Expr
  | mul : Expr → Expr → Expr
  | div : Expr → Expr → Expr
  | abs : Expr → Expr
  | min : Expr → Expr → Expr
  | max : Expr → Expr → Expr
  | powNat : Expr → Nat → Expr

end SparkInterval
