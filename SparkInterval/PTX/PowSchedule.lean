import Mathlib.Algebra.Group.Defs
import Mathlib.Algebra.Group.Nat.Defs
import Mathlib.Data.Nat.BinaryRec

/-!
# Binary exponentiation schedule

The existing version-1 generated kernel evaluates `powNat` by `n` repeated
multiplications.  This file proves a logarithmic binary schedule without yet
changing that versioned result semantics.  A later version-2 compiler can fold
these steps exclusively through the already proved interval multiplication
lowering, adding no PTX opcode or vendor-semantic assumption.

Because outward-rounded interval multiplication is not bitwise associative,
switching schedules may change result endpoints even though both enclose the
same exact power.  Keeping the schedule separate prevents an accidental change
to the v1 wire algorithm.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- One multiplication in left-to-right binary exponentiation. -/
inductive PowStep where
  | square
  | mulBase
  deriving BEq, DecidableEq, Repr

namespace PowStep

/-- Effect of one schedule step on the exponent represented by the current
accumulator. -/
def advanceExponent : PowStep → Nat → Nat
  | .square, exponent => exponent + exponent
  | .mulBase, exponent => exponent + 1

end PowStep

/-- Steps contributed by one non-leading binary digit. -/
def powBitSuffix (bit : Bool) : List PowStep :=
  [.square] ++ if bit then [.mulBase] else []

/-- Left-to-right binary exponentiation starting from exponent zero. -/
def powSchedule : Nat → List PowStep :=
  Nat.binaryRecFromOne [] [.mulBase]
    (fun bit _ _ previous => previous ++ powBitSuffix bit)

@[simp] theorem powSchedule_zero : powSchedule 0 = [] := by
  simp [powSchedule]

@[simp] theorem powSchedule_one : powSchedule 1 = [.mulBase] := by
  simp [powSchedule]

theorem powSchedule_bit (bit : Bool) (n : Nat) (hn : n ≠ 0) :
    powSchedule (Nat.bit bit n) = powSchedule n ++ powBitSuffix bit := by
  unfold powSchedule
  rw [Nat.binaryRecFromOne_eq bit n hn]

/-- Execute an exponent schedule symbolically. -/
def runPowExponents : List PowStep → Nat → Nat
  | [], exponent => exponent
  | step :: rest, exponent =>
      runPowExponents rest (step.advanceExponent exponent)

@[simp] theorem runPowExponents_append (left right : List PowStep)
    (exponent : Nat) :
    runPowExponents (left ++ right) exponent =
      runPowExponents right (runPowExponents left exponent) := by
  induction left generalizing exponent with
  | nil => rfl
  | cons step rest induction =>
      simp only [List.cons_append, runPowExponents]
      exact induction (step.advanceExponent exponent)

/-- The schedule represents exactly the requested natural exponent. -/
theorem powSchedule_denotes (n : Nat) :
    runPowExponents (powSchedule n) 0 = n := by
  induction n using Nat.binaryRecFromOne with
  | zero => rfl
  | one => simp [runPowExponents, PowStep.advanceExponent]
  | bit bit n hn induction =>
      rw [powSchedule_bit bit n hn, runPowExponents_append, induction]
      cases bit <;>
        simp [powBitSuffix, runPowExponents, PowStep.advanceExponent, Nat.bit, Nat.two_mul]

/-- Number of interval multiplications required by the binary schedule. -/
def powMulCount (n : Nat) : Nat :=
  (powSchedule n).length

@[simp] theorem powMulCount_zero : powMulCount 0 = 0 := by
  simp [powMulCount]

@[simp] theorem powMulCount_one : powMulCount 1 = 1 := by
  simp [powMulCount]

theorem powMulCount_bit (bit : Bool) (n : Nat) (hn : n ≠ 0) :
    powMulCount (Nat.bit bit n) =
      powMulCount n + if bit then 2 else 1 := by
  rw [powMulCount, powSchedule_bit bit n hn, List.length_append]
  cases bit <;> simp [powMulCount, powBitSuffix]

/-- Execute a schedule in an arbitrary multiplicative type. -/
def runPowValues {α : Type*} [Mul α] (base : α) : List PowStep → α → α
  | [], current => current
  | .square :: rest, current => runPowValues base rest (current * current)
  | .mulBase :: rest, current => runPowValues base rest (current * base)

theorem runPowValues_eq_pow {α : Type*} [Monoid α] (base : α)
    (steps : List PowStep) (exponent : Nat) :
    runPowValues base steps (base ^ exponent) =
      base ^ runPowExponents steps exponent := by
  induction steps generalizing exponent with
  | nil => rfl
  | cons step rest induction =>
      cases step with
      | square =>
          simp only [runPowValues, runPowExponents, PowStep.advanceExponent]
          rw [← pow_add]
          exact induction (exponent + exponent)
      | mulBase =>
          simp only [runPowValues, runPowExponents, PowStep.advanceExponent]
          rw [← pow_succ]
          exact induction (exponent + 1)

/-- Algebraic correctness of the executable binary schedule. -/
theorem runPowSchedule_eq_pow {α : Type*} [Monoid α] (base : α) (n : Nat) :
    runPowValues base (powSchedule n) 1 = base ^ n := by
  have hrun := runPowValues_eq_pow base (powSchedule n) 0
  simpa [powSchedule_denotes] using hrun

end SparkInterval.PTX
