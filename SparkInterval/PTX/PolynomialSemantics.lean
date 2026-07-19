import SparkInterval.PTX.Semantics

/-!
# Whole-expression semantics for the generated polynomial kernel

This module composes the proved directed add/subtract/multiply fragments into
the complete expression language accepted by the Phase 5 PTX generator.  It
also models the generator's shared nonfinite path: an infinite operand to a
later arithmetic operation widens the row to `[-∞,+∞]` with status 2.

The theorem in this file is deliberately about the documented PTX arithmetic
model.  Relating an offline `ptxas` cubin and a physical GPU execution to this
model remains an explicit backend/hardware assumption.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

open SparkInterval

/-- Status values produced by the restricted generated kernel. -/
inductive KernelStatus where
  | ok
  | nonfiniteIntermediate
  deriving BEq, DecidableEq, Repr

/-- Mathematical observation of one generated-kernel row. -/
structure KernelResult where
  interval : F64Interval
  status : KernelStatus

namespace F64Interval

/-- The conservative result written by the shared nonfinite branch. -/
def whole : F64Interval := { lo := .negInf, hi := .posInf }

/-- Numeric sign negation, including reversal of interval endpoints. -/
noncomputable def negate (interval : F64Interval) : F64Interval :=
  { lo := interval.hi.negate, hi := interval.lo.negate }

/-- Extract finite endpoint values. -/
noncomputable def finiteBounds? (interval : F64Interval) : Option (ℝ × ℝ) :=
  match interval.lo, interval.hi with
  | .finite lo, .finite hi => some (lo, hi)
  | _, _ => none

@[simp] theorem whole_containsReal (value : ℝ) : whole.ContainsReal value := by
  simp [whole, ContainsReal, F64Value.toEReal]

theorem negate_containsReal {interval : F64Interval} {value : ℝ}
    (hvalue : interval.ContainsReal value) :
    interval.negate.ContainsReal (-value) := by
  constructor
  · simpa [negate, ContainsReal] using EReal.neg_le_neg_iff.mpr hvalue.2
  · simpa [negate, ContainsReal] using EReal.neg_le_neg_iff.mpr hvalue.1

end F64Interval

namespace KernelResult

def whole : KernelResult := {
  interval := F64Interval.whole
  status := .nonfiniteIntermediate
}

noncomputable def negate (result : KernelResult) : KernelResult :=
  match result.status with
  | .ok => { interval := result.interval.negate, status := .ok }
  | .nonfiniteIntermediate => whole

end KernelResult

/-- Decode a constant interval exactly as the generated `mov.b64` pair. -/
noncomputable def IntervalBits.decodeF64Interval? (value : IntervalBits) :
    Option F64Interval := do
  let lo ← decodeF64Bits value.lo.value
  let hi ← decodeF64Bits value.hi.value
  pure { lo, hi }

/-- Raw-endpoint form of the arithmetic fragment result.  It is defined
without an interval-validity proof so the executable model can first inspect
the operands.  Soundness constructs valid `RealInterval`s from the selected
values in the theorem below. -/
noncomputable def roundedBinaryInterval (op : F64BinaryOp)
    (leftLo leftHi rightLo rightHi : ℝ) : F64Interval :=
  match op with
  | .add => {
      lo := F64Value.ofExt <| Binary64Rounding.roundDown (leftLo + rightLo)
      hi := F64Value.ofExt <| Binary64Rounding.roundUp (leftHi + rightHi)
    }
  | .sub => {
      lo := F64Value.ofExt <| Binary64Rounding.roundDown (leftLo - rightHi)
      hi := F64Value.ofExt <| Binary64Rounding.roundUp (leftHi - rightLo)
    }
  | .mul =>
      let d00 := F64Value.ofExt <| Binary64Rounding.roundDown (leftLo * rightLo)
      let d01 := F64Value.ofExt <| Binary64Rounding.roundDown (leftLo * rightHi)
      let d10 := F64Value.ofExt <| Binary64Rounding.roundDown (leftHi * rightLo)
      let d11 := F64Value.ofExt <| Binary64Rounding.roundDown (leftHi * rightHi)
      let u00 := F64Value.ofExt <| Binary64Rounding.roundUp (leftLo * rightLo)
      let u01 := F64Value.ofExt <| Binary64Rounding.roundUp (leftLo * rightHi)
      let u10 := F64Value.ofExt <| Binary64Rounding.roundUp (leftHi * rightLo)
      let u11 := F64Value.ofExt <| Binary64Rounding.roundUp (leftHi * rightHi)
      {
        lo := F64Value.minimum (F64Value.minimum d00 d01)
          (F64Value.minimum d10 d11)
        hi := F64Value.maximum (F64Value.maximum u00 u01)
          (F64Value.maximum u10 u11)
      }

/-- Execute one guarded arithmetic node. -/
noncomputable def guardedBinary (op : F64BinaryOp)
    (left right : KernelResult) : KernelResult :=
  match left.status, right.status with
  | .ok, .ok =>
      match left.interval.finiteBounds?, right.interval.finiteBounds? with
      | some (leftLo, leftHi), some (rightLo, rightHi) => {
          interval := roundedBinaryInterval op leftLo leftHi rightLo rightHi
          status := .ok
        }
      | _, _ => .whole
  | _, _ => .whole

private theorem roundedBinaryInterval_contains
    (op : F64BinaryOp) {leftLo leftHi rightLo rightHi leftValue rightValue : ℝ}
    (hleft : leftLo ≤ leftValue ∧ leftValue ≤ leftHi)
    (hright : rightLo ≤ rightValue ∧ rightValue ≤ rightHi) :
    (roundedBinaryInterval op leftLo leftHi rightLo rightHi).ContainsReal
      (exactBinary op leftValue rightValue) := by
  let left : RealInterval := ⟨leftLo, leftHi, hleft.1.trans hleft.2⟩
  let right : RealInterval := ⟨rightLo, rightHi, hright.1.trans hright.2⟩
  cases op with
  | add =>
      simpa [roundedBinaryInterval, exactBinary, addFragmentResult, left, right]
        using addFragmentResult_contains (left := left) (right := right) hleft hright
  | sub =>
      simpa [roundedBinaryInterval, exactBinary, subFragmentResult, left, right]
        using subFragmentResult_contains (left := left) (right := right) hleft hright
  | mul =>
      simpa [roundedBinaryInterval, exactBinary, mulFragmentResult, left, right]
        using mulFragmentResult_contains (left := left) (right := right) hleft hright

/-- A guarded generated arithmetic node contains the corresponding exact real
operation, whether it computes normally or takes the conservative whole path. -/
theorem guardedBinary_contains (op : F64BinaryOp)
    {left right : KernelResult} {leftValue rightValue : ℝ}
    (hleft : left.interval.ContainsReal leftValue)
    (hright : right.interval.ContainsReal rightValue) :
    (guardedBinary op left right).interval.ContainsReal
      (exactBinary op leftValue rightValue) := by
  cases hls : left.status <;> cases hrs : right.status <;>
    simp only [guardedBinary, hls, hrs]
  · cases hlo : left.interval.lo with
    | negInf => simp [F64Interval.finiteBounds?, hlo, KernelResult.whole]
    | posInf => simp [F64Interval.finiteBounds?, hlo, KernelResult.whole]
    | finite leftLo =>
        cases hhi : left.interval.hi with
        | negInf => simp [F64Interval.finiteBounds?, hlo, hhi, KernelResult.whole]
        | posInf => simp [F64Interval.finiteBounds?, hlo, hhi, KernelResult.whole]
        | finite leftHi =>
            cases rlo : right.interval.lo with
            | negInf =>
                simp [F64Interval.finiteBounds?, hlo, hhi, rlo, KernelResult.whole]
            | posInf =>
                simp [F64Interval.finiteBounds?, hlo, hhi, rlo, KernelResult.whole]
            | finite rightLo =>
                cases rhi : right.interval.hi with
                | negInf =>
                    simp [F64Interval.finiteBounds?, hlo, hhi, rlo, rhi,
                      KernelResult.whole]
                | posInf =>
                    simp [F64Interval.finiteBounds?, hlo, hhi, rlo, rhi,
                      KernelResult.whole]
                | finite rightHi =>
                    have hleft' : leftLo ≤ leftValue ∧ leftValue ≤ leftHi := by
                      simpa [F64Interval.ContainsReal, hlo, hhi, F64Value.toEReal]
                        using hleft
                    have hright' : rightLo ≤ rightValue ∧ rightValue ≤ rightHi := by
                      simpa [F64Interval.ContainsReal, rlo, rhi, F64Value.toEReal]
                        using hright
                    simpa [F64Interval.finiteBounds?, hlo, hhi, rlo, rhi] using
                      roundedBinaryInterval_contains op hleft' hright'
  · simp [KernelResult.whole]
  · simp [KernelResult.whole]
  · simp [KernelResult.whole]

/-- Repeated multiplication used by the generated natural-power expansion. -/
noncomputable def powLoop : Nat → KernelResult → KernelResult → KernelResult
  | 0, _, accumulator => accumulator
  | exponent + 1, base, accumulator =>
      powLoop exponent base (guardedBinary .mul accumulator base)

private theorem powLoop_contains (exponent : Nat)
    {base accumulator : KernelResult} {baseValue accumulatorValue : ℝ}
    (hbase : base.interval.ContainsReal baseValue)
    (haccumulator : accumulator.interval.ContainsReal accumulatorValue) :
    (powLoop exponent base accumulator).interval.ContainsReal
      (accumulatorValue * baseValue ^ exponent) := by
  induction exponent generalizing accumulator accumulatorValue with
  | zero => simpa [powLoop]
  | succ exponent induction =>
      have hstep := guardedBinary_contains .mul haccumulator hbase
      have hrest := induction hstep
      simpa [powLoop, pow_succ, exactBinary, mul_assoc, mul_comm, mul_left_comm]
        using hrest

/-- Complete documented arithmetic/control model for one generated expression
row.  Loads supply the already-decoded interval environment. -/
noncomputable def PolynomialExpr.evalKernel
    (environment : Array F64Interval) : PolynomialExpr → Option KernelResult
  | .const value => do
      let interval ← value.decodeF64Interval?
      pure { interval, status := .ok }
  | .var index => do
      let interval ← environment[index]?
      pure { interval, status := .ok }
  | .neg argument => do
      let result ← argument.evalKernel environment
      pure result.negate
  | .add left right => do
      let leftResult ← left.evalKernel environment
      match leftResult.status with
      | .nonfiniteIntermediate => pure .whole
      | .ok => do
          let rightResult ← right.evalKernel environment
          pure (guardedBinary .add leftResult rightResult)
  | .sub left right => do
      let leftResult ← left.evalKernel environment
      match leftResult.status with
      | .nonfiniteIntermediate => pure .whole
      | .ok => do
          let rightResult ← right.evalKernel environment
          pure (guardedBinary .sub leftResult rightResult)
  | .mul left right => do
      let leftResult ← left.evalKernel environment
      match leftResult.status with
      | .nonfiniteIntermediate => pure .whole
      | .ok => do
          let rightResult ← right.evalKernel environment
          pure (guardedBinary .mul leftResult rightResult)
  | .powNat argument exponent => do
      let base ← argument.evalKernel environment
      match base.status with
      | .nonfiniteIntermediate => pure .whole
      | .ok =>
          let one : KernelResult := {
            interval := { lo := .finite 1, hi := .finite 1 }
            status := .ok
          }
          pure (powLoop exponent base one)

/-- Exact-real selection semantics for the interval-valued polynomial source. -/
inductive PolynomialExpr.Realizes (environment : Array ℝ) :
    PolynomialExpr → ℝ → Prop
  | const {raw : IntervalBits} {interval : F64Interval} {value : ℝ}
      (decoded : raw.decodeF64Interval? = some interval)
      (contains : interval.ContainsReal value) :
      Realizes environment (.const raw) value
  | var {index : Nat} {value : ℝ}
      (get : environment[index]? = some value) :
      Realizes environment (.var index) value
  | neg {argument : PolynomialExpr} {value : ℝ}
      (argumentRealizes : Realizes environment argument value) :
      Realizes environment (.neg argument) (-value)
  | add {left right : PolynomialExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes environment left leftValue)
      (rightRealizes : Realizes environment right rightValue) :
      Realizes environment (.add left right) (leftValue + rightValue)
  | sub {left right : PolynomialExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes environment left leftValue)
      (rightRealizes : Realizes environment right rightValue) :
      Realizes environment (.sub left right) (leftValue - rightValue)
  | mul {left right : PolynomialExpr} {leftValue rightValue : ℝ}
      (leftRealizes : Realizes environment left leftValue)
      (rightRealizes : Realizes environment right rightValue) :
      Realizes environment (.mul left right) (leftValue * rightValue)
  | powNat {argument : PolynomialExpr} {value : ℝ} {exponent : Nat}
      (argumentRealizes : Realizes environment argument value) :
      Realizes environment (.powNat argument exponent) (value ^ exponent)

/-- Selected exact inputs and decoded interval inputs have the same index
domain, with each exact value contained in its corresponding interval. -/
def PolynomialEnvironmentsCorrespond
    (realEnvironment : Array ℝ) (intervalEnvironment : Array F64Interval) : Prop :=
  ∀ index : Nat,
    Option.Rel (fun value interval => interval.ContainsReal value)
      realEnvironment[index]? intervalEnvironment[index]?

/-- **Whole-expression bounded-arithmetic theorem.**

Every result produced by the complete generated polynomial arithmetic model
contains every exact real value represented by the source expression and its
input intervals.  This composes constants, loads, negation, directed
add/subtract/multiply, repeated powers, and the shared conservative widening
path. -/
theorem PolynomialExpr.evalKernel_sound
    {realEnvironment : Array ℝ} {intervalEnvironment : Array F64Interval}
    (henvironments : PolynomialEnvironmentsCorrespond
      realEnvironment intervalEnvironment)
    {expression : PolynomialExpr} {value : ℝ} {result : KernelResult}
    (hrealizes : expression.Realizes realEnvironment value)
    (heval : expression.evalKernel intervalEnvironment = some result) :
    result.interval.ContainsReal value := by
  induction expression generalizing value result with
  | const raw =>
      cases hrealizes with
      | const decoded contains =>
          simp [PolynomialExpr.evalKernel, decoded] at heval
          subst result
          exact contains
  | var index =>
      cases hrealizes with
      | var get =>
          have hcorrespond := henvironments index
          rw [get] at hcorrespond
          cases hinterval : intervalEnvironment[index]? with
          | none => simp [hinterval] at hcorrespond
          | some interval =>
              have hcontains : interval.ContainsReal value := by
                simpa [hinterval] using hcorrespond
              simp [PolynomialExpr.evalKernel, hinterval] at heval
              subst result
              exact hcontains
  | neg argument induction =>
      cases hrealizes with
      | neg argumentRealizes =>
          cases hargument : argument.evalKernel intervalEnvironment with
          | none => simp [PolynomialExpr.evalKernel, hargument] at heval
          | some argumentResult =>
              have hcontains := induction argumentRealizes hargument
              cases hstatus : argumentResult.status with
              | ok =>
                  have hneg := F64Interval.negate_containsReal hcontains
                  simp [PolynomialExpr.evalKernel, hargument, KernelResult.negate,
                    hstatus] at heval
                  subst result
                  exact hneg
              | nonfiniteIntermediate =>
                  simp [PolynomialExpr.evalKernel, hargument, KernelResult.negate,
                    hstatus] at heval
                  subst result
                  exact F64Interval.whole_containsReal _
  | add left right leftInduction rightInduction =>
      cases hrealizes with
      | add leftRealizes rightRealizes =>
          cases hleft : left.evalKernel intervalEnvironment with
          | none => simp [PolynomialExpr.evalKernel, hleft] at heval
          | some leftResult =>
              have hleftContains := leftInduction leftRealizes hleft
              cases hstatus : leftResult.status with
              | nonfiniteIntermediate =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus] at heval
                  subst result
                  exact F64Interval.whole_containsReal _
              | ok =>
                  cases hright : right.evalKernel intervalEnvironment with
                  | none =>
                      simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                  | some rightResult =>
                      have hrightContains := rightInduction rightRealizes hright
                      have hbounded := guardedBinary_contains .add
                        hleftContains hrightContains
                      simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                      subst result
                      simpa [exactBinary] using hbounded
  | sub left right leftInduction rightInduction =>
      cases hrealizes with
      | sub leftRealizes rightRealizes =>
          cases hleft : left.evalKernel intervalEnvironment with
          | none => simp [PolynomialExpr.evalKernel, hleft] at heval
          | some leftResult =>
              have hleftContains := leftInduction leftRealizes hleft
              cases hstatus : leftResult.status with
              | nonfiniteIntermediate =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus] at heval
                  subst result
                  exact F64Interval.whole_containsReal _
              | ok =>
                  cases hright : right.evalKernel intervalEnvironment with
                  | none =>
                      simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                  | some rightResult =>
                      have hrightContains := rightInduction rightRealizes hright
                      have hbounded := guardedBinary_contains .sub
                        hleftContains hrightContains
                      simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                      subst result
                      simpa [exactBinary] using hbounded
  | mul left right leftInduction rightInduction =>
      cases hrealizes with
      | mul leftRealizes rightRealizes =>
          cases hleft : left.evalKernel intervalEnvironment with
          | none => simp [PolynomialExpr.evalKernel, hleft] at heval
          | some leftResult =>
              have hleftContains := leftInduction leftRealizes hleft
              cases hstatus : leftResult.status with
              | nonfiniteIntermediate =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus] at heval
                  subst result
                  exact F64Interval.whole_containsReal _
              | ok =>
                  cases hright : right.evalKernel intervalEnvironment with
                  | none =>
                      simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                  | some rightResult =>
                      have hrightContains := rightInduction rightRealizes hright
                      have hbounded := guardedBinary_contains .mul
                        hleftContains hrightContains
                      simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                      subst result
                      simpa [exactBinary] using hbounded
  | powNat argument exponent induction =>
      cases hrealizes with
      | powNat argumentRealizes =>
          cases hargument : argument.evalKernel intervalEnvironment with
          | none => simp [PolynomialExpr.evalKernel, hargument] at heval
          | some base =>
              have hbase := induction argumentRealizes hargument
              cases hstatus : base.status with
              | nonfiniteIntermediate =>
                  simp [PolynomialExpr.evalKernel, hargument, hstatus] at heval
                  subst result
                  exact F64Interval.whole_containsReal _
              | ok =>
                  let one : KernelResult := {
                    interval := { lo := .finite 1, hi := .finite 1 }
                    status := .ok
                  }
                  have hone : one.interval.ContainsReal 1 := by
                    simp [one, F64Interval.ContainsReal, F64Value.toEReal]
                  have hpower := powLoop_contains exponent
                    (base := base) (accumulator := one) hbase hone
                  simp [PolynomialExpr.evalKernel, hargument, hstatus] at heval
                  subst result
                  simpa [one] using hpower

end SparkInterval.PTX
