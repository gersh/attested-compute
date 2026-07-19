import SparkInterval.Certificate.Binary64

/-!
# Certificate expression semantics

`CertExpr` mirrors the complete canonical reference expression language.  Its
executable evaluator works over exact rational intervals.  The independent
`Realizes` relation describes arbitrary real selections from input and
constant intervals.  `eval_sound` proves that rational evaluation encloses
every such real result.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate

/-- The full expression syntax accepted by mathematical result certificates. -/
inductive CertExpr where
  | const (value : RawInterval)
  | var (index : Nat)
  | neg (arg : CertExpr)
  | add (left right : CertExpr)
  | sub (left right : CertExpr)
  | mul (left right : CertExpr)
  | div (left right : CertExpr)
  | abs (arg : CertExpr)
  | min (left right : CertExpr)
  | max (left right : CertExpr)
  | powNat (arg : CertExpr) (exponent : Nat)
  deriving BEq, DecidableEq, Repr

namespace CertExpr

/-- A conservative, saturating estimate of exact-rational growth and
evaluation work. Binary operations add the costs of their operands; a natural
power accounts for the repeated multiplicative expansion. The result is
capped at `limit + 1`, so hostile nested powers cannot themselves create a
large cost numeral. -/
def arithmeticCostUpTo (limit : Nat) : CertExpr → Nat
  | .const _ | .var _ => 1
  | .neg arg | .abs arg =>
      Nat.min (limit + 1) (arg.arithmeticCostUpTo limit + 1)
  | .add left right | .sub left right | .mul left right |
      .div left right | .min left right | .max left right =>
      Nat.min (limit + 1)
        (left.arithmeticCostUpTo limit + right.arithmeticCostUpTo limit + 1)
  | .powNat arg exponent =>
      Nat.min (limit + 1)
        (arg.arithmeticCostUpTo limit * Nat.max exponent 1 + 1)

/-- Evaluate a certificate expression by exact rational interval arithmetic.

Malformed constants, missing variables, and division by an interval that does
not exclude zero all fail closed.
-/
def eval : CertExpr → Array RatInterval → Option RatInterval
  | .const value, _ => value.decodeFinite
  | .var index, env => env[index]?
  | .neg arg, env => do
      let value ← arg.eval env
      pure value.neg
  | .add left right, env => do
      let leftValue ← left.eval env
      let rightValue ← right.eval env
      pure (leftValue.add rightValue)
  | .sub left right, env => do
      let leftValue ← left.eval env
      let rightValue ← right.eval env
      pure (leftValue.sub rightValue)
  | .mul left right, env => do
      let leftValue ← left.eval env
      let rightValue ← right.eval env
      pure (leftValue.mul rightValue)
  | .div left right, env => do
      let leftValue ← left.eval env
      let rightValue ← right.eval env
      leftValue.div? rightValue
  | .abs arg, env => do
      let value ← arg.eval env
      pure value.abs
  | .min left right, env => do
      let leftValue ← left.eval env
      let rightValue ← right.eval env
      pure (leftValue.min rightValue)
  | .max left right, env => do
      let leftValue ← left.eval env
      let rightValue ← right.eval env
      pure (leftValue.max rightValue)
  | .powNat arg exponent, env => do
      let value ← arg.eval env
      pure (value.powNat exponent)

/-- Pointwise correspondence between selected real inputs and rational input
intervals.  `Option.Rel` also requires both arrays to have the same observable
index domain. -/
def EnvironmentsCorrespond
    (realEnv : Array ℝ) (intervalEnv : Array RatInterval) : Prop :=
  ∀ index : Nat,
    Option.Rel (fun value interval ↦ interval.ContainsReal value)
      realEnv[index]? intervalEnv[index]?

/-- Mathematical real-selection semantics for interval expressions.

Constants on the wire are intervals rather than scalar literals.  The
relation therefore permits any real member of a decoded constant interval.
Division realizes only nonzero selected denominators, matching partial exact
real evaluation.
-/
inductive Realizes (env : Array ℝ) : CertExpr → ℝ → Prop
  | const {raw : RawInterval} {interval : RatInterval} {value : ℝ}
      (decoded : raw.decodeFinite = some interval)
      (contains : interval.ContainsReal value) :
      Realizes env (.const raw) value
  | var {index : Nat} {value : ℝ}
      (get : env[index]? = some value) :
      Realizes env (.var index) value
  | neg {arg : CertExpr} {value : ℝ}
      (argRealizes : Realizes env arg value) :
      Realizes env (.neg arg) (-value)
  | add {left right : CertExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes env left leftValue)
      (rightRealizes : Realizes env right rightValue) :
      Realizes env (.add left right) (leftValue + rightValue)
  | sub {left right : CertExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes env left leftValue)
      (rightRealizes : Realizes env right rightValue) :
      Realizes env (.sub left right) (leftValue - rightValue)
  | mul {left right : CertExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes env left leftValue)
      (rightRealizes : Realizes env right rightValue) :
      Realizes env (.mul left right) (leftValue * rightValue)
  | div {left right : CertExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes env left leftValue)
      (rightRealizes : Realizes env right rightValue)
      (denominatorNonzero : rightValue ≠ 0) :
      Realizes env (.div left right) (leftValue / rightValue)
  | abs {arg : CertExpr} {value : ℝ}
      (argRealizes : Realizes env arg value) :
      Realizes env (.abs arg) |value|
  | min {left right : CertExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes env left leftValue)
      (rightRealizes : Realizes env right rightValue) :
      Realizes env (.min left right) (Min.min leftValue rightValue)
  | max {left right : CertExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes env left leftValue)
      (rightRealizes : Realizes env right rightValue) :
      Realizes env (.max left right) (Max.max leftValue rightValue)
  | powNat {arg : CertExpr} {value : ℝ} {exponent : Nat}
      (argRealizes : Realizes env arg value) :
      Realizes env (.powNat arg exponent) (value ^ exponent)

private theorem optionMap_eq_some
    {alpha beta : Type} {input : Option alpha} {f : alpha → beta} {result : beta}
    (h : (do let value ← input; pure (f value)) = some result) :
    ∃ value, input = some value ∧ f value = result := by
  cases input with
  | none => simp at h
  | some value =>
      refine ⟨value, rfl, ?_⟩
      simpa using h

private theorem optionMap₂_eq_some
    {alpha beta gamma : Type}
    {left : Option alpha} {right : Option beta}
    {f : alpha → beta → gamma} {result : gamma}
    (h : (do
      let leftValue ← left
      let rightValue ← right
      pure (f leftValue rightValue)) = some result) :
    ∃ leftValue rightValue,
      left = some leftValue ∧ right = some rightValue ∧
        f leftValue rightValue = result := by
  cases left with
  | none => simp at h
  | some leftValue =>
      cases right with
      | none => simp at h
      | some rightValue =>
          refine ⟨leftValue, rightValue, rfl, rfl, ?_⟩
          simpa using h

private theorem optionBind₂_eq_some
    {alpha beta gamma : Type}
    {left : Option alpha} {right : Option beta}
    {f : alpha → beta → Option gamma} {result : gamma}
    (h : (do
      let leftValue ← left
      let rightValue ← right
      f leftValue rightValue) = some result) :
    ∃ leftValue rightValue,
      left = some leftValue ∧ right = some rightValue ∧
        f leftValue rightValue = some result := by
  cases left with
  | none => simp at h
  | some leftValue =>
      cases right with
      | none => simp at h
      | some rightValue =>
          exact ⟨leftValue, rightValue, rfl, rfl, h⟩

/-- Exact rational interval evaluation encloses every arbitrary real selection
described by `Realizes`. -/
theorem eval_sound
    {expr : CertExpr}
    {realEnv : Array ℝ}
    {intervalEnv : Array RatInterval}
    {value : ℝ}
    {result : RatInterval}
    (henv : EnvironmentsCorrespond realEnv intervalEnv)
    (hreal : Realizes realEnv expr value)
    (heval : expr.eval intervalEnv = some result) :
    result.ContainsReal value := by
  induction hreal generalizing intervalEnv result with
  | const decoded contains =>
      simp only [eval] at heval
      rw [decoded] at heval
      simp only [Option.some.injEq] at heval
      subst result
      exact contains
  | @var index value get =>
      have correspondence := henv index
      change intervalEnv[index]? = some result at heval
      rw [get, heval] at correspondence
      simpa using correspondence
  | neg argRealizes ih =>
      rcases optionMap_eq_some heval with ⟨argResult, harg, rfl⟩
      exact RatInterval.neg_containsReal (ih henv harg)
  | add leftRealizes rightRealizes leftIH rightIH =>
      rcases optionMap₂_eq_some heval with
        ⟨leftResult, rightResult, hleft, hright, rfl⟩
      exact RatInterval.add_containsReal
        (leftIH henv hleft) (rightIH henv hright)
  | sub leftRealizes rightRealizes leftIH rightIH =>
      rcases optionMap₂_eq_some heval with
        ⟨leftResult, rightResult, hleft, hright, rfl⟩
      exact RatInterval.sub_containsReal
        (leftIH henv hleft) (rightIH henv hright)
  | mul leftRealizes rightRealizes leftIH rightIH =>
      rcases optionMap₂_eq_some heval with
        ⟨leftResult, rightResult, hleft, hright, rfl⟩
      exact RatInterval.mul_containsReal
        (leftIH henv hleft) (rightIH henv hright)
  | div leftRealizes rightRealizes denominatorNonzero leftIH rightIH =>
      rcases optionBind₂_eq_some heval with
        ⟨leftResult, rightResult, hleft, hright, hdiv⟩
      exact RatInterval.div?_containsReal
        (leftIH henv hleft) (rightIH henv hright) hdiv
  | abs argRealizes ih =>
      rcases optionMap_eq_some heval with ⟨argResult, harg, rfl⟩
      exact RatInterval.abs_containsReal (ih henv harg)
  | min leftRealizes rightRealizes leftIH rightIH =>
      rcases optionMap₂_eq_some heval with
        ⟨leftResult, rightResult, hleft, hright, rfl⟩
      exact RatInterval.min_containsReal
        (leftIH henv hleft) (rightIH henv hright)
  | max leftRealizes rightRealizes leftIH rightIH =>
      rcases optionMap₂_eq_some heval with
        ⟨leftResult, rightResult, hleft, hright, rfl⟩
      exact RatInterval.max_containsReal
        (leftIH henv hleft) (rightIH henv hright)
  | powNat argRealizes ih =>
      rcases optionMap_eq_some heval with ⟨argResult, harg, rfl⟩
      exact RatInterval.powNat_containsReal (ih henv harg) _

end CertExpr

end SparkInterval.Certificate
