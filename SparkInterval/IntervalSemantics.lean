import SparkInterval.ExactSemantics

/-!
# Exact real-interval semantics

The denominator interval must exclude zero before interval division succeeds.
This is intentionally stricter than merely requiring the selected exact
denominator value to be nonzero.
-/

set_option autoImplicit false

namespace SparkInterval

noncomputable section

/-- Pointwise correspondence between exact and interval environments.

Using `Option.Rel` also requires both arrays to agree on which indices exist.
-/
def EnvironmentsCorrespond
    (realEnv : Array ℝ) (intervalEnv : Array RealInterval) : Prop :=
  ∀ i : Nat, Option.Rel (fun x I ↦ I.Contains x) realEnv[i]? intervalEnv[i]?

local instance (I : RealInterval) : Decidable I.ExcludesZero :=
  Classical.propDecidable _

/-- Evaluate an expression using exact real interval operations. -/
def evalInterval : Expr → Array RealInterval → Option RealInterval
  | .const c, _ => some (RealInterval.point c)
  | .var i, env => env[i]?
  | .neg a, env => do
      let X ← evalInterval a env
      pure X.neg
  | .add a b, env => do
      let X ← evalInterval a env
      let Y ← evalInterval b env
      pure (X.add Y)
  | .sub a b, env => do
      let X ← evalInterval a env
      let Y ← evalInterval b env
      pure (X.sub Y)
  | .mul a b, env => do
      let X ← evalInterval a env
      let Y ← evalInterval b env
      pure (X.mul Y)
  | .div a b, env => do
      let X ← evalInterval a env
      let Y ← evalInterval b env
      if hzero : Y.ExcludesZero then some (X.div Y hzero) else none
  | .abs a, env => do
      let X ← evalInterval a env
      pure X.abs
  | .min a b, env => do
      let X ← evalInterval a env
      let Y ← evalInterval b env
      pure (X.min Y)
  | .max a b, env => do
      let X ← evalInterval a env
      let Y ← evalInterval b env
      pure (X.max Y)
  | .powNat a n, env => do
      let X ← evalInterval a env
      pure (X.powNat n)

end

end SparkInterval
