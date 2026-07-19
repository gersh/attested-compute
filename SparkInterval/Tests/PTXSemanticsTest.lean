import SparkInterval.PTX.Semantics

/-! Compile-time regression tests for the Phase 6 arithmetic semantics. -/

set_option autoImplicit false

namespace SparkInterval.Tests.PTXSemantics

open SparkInterval
open SparkInterval.PTX

private def left : RealInterval := ⟨-2, 3, by norm_num⟩
private def right : RealInterval := ⟨4, 5, by norm_num⟩

example : left.Contains 1 := by norm_num [left, RealInterval.Contains]
example : right.Contains 4 := by norm_num [right, RealInterval.Contains]

example : (addFragmentResult left right).ContainsReal (1 + 4) := by
  exact addFragmentResult_contains
    (by norm_num [left, RealInterval.Contains])
    (by norm_num [right, RealInterval.Contains])

example : (subFragmentResult left right).ContainsReal (1 - 4) := by
  exact subFragmentResult_contains
    (by norm_num [left, RealInterval.Contains])
    (by norm_num [right, RealInterval.Contains])

example : (mulFragmentResult left right).ContainsReal (1 * 4) := by
  exact mulFragmentResult_contains
    (by norm_num [left, RealInterval.Contains])
    (by norm_num [right, RealInterval.Contains])

example : ∃ result,
    (do
      let registers ← executeF64Fragment
        (addArithmeticFragment canonicalAddSubResult canonicalLeft canonicalRight)
        (canonicalInputRegisters left right)
      observeInterval registers canonicalAddSubResult) = some result ∧
    result.ContainsReal (1 + 4) := by
  exact executeCanonicalAdd_contains
    (by norm_num [left, RealInterval.Contains])
    (by norm_num [right, RealInterval.Contains])

example : ∃ result,
    (do
      let registers ← executeF64Fragment
        (subArithmeticFragment canonicalAddSubResult canonicalLeft canonicalRight)
        (canonicalInputRegisters left right)
      observeInterval registers canonicalAddSubResult) = some result ∧
    result.ContainsReal (1 - 4) := by
  exact executeCanonicalSub_contains
    (by norm_num [left, RealInterval.Contains])
    (by norm_num [right, RealInterval.Contains])

example : ∃ result,
    (do
      let registers ← executeF64Fragment
        (mulArithmeticFragment canonicalMulResult canonicalLeft canonicalRight
          canonicalMulTemporaries)
        (canonicalInputRegisters left right)
      observeInterval registers canonicalMulResult) = some result ∧
    result.ContainsReal (1 * 4) := by
  exact executeCanonicalMul_contains
    (by norm_num [left, RealInterval.Contains])
    (by norm_num [right, RealInterval.Contains])

example (value : F64Value) :
    value.negate.toEReal = -value.toEReal :=
  F64Value.negate_toEReal value

example (raw : Nat)
    (hfinite : Binary64Bits.IsFinite (BitVec.ofNat 64 raw)) :
    decodeF64Bits raw = some (.finite
      (Binary64Finite.toReal ⟨BitVec.ofNat 64 raw, hfinite⟩)) :=
  decodeF64Bits_of_finite raw hfinite

example (raw : Nat)
    (hinfinite : Binary64Bits.IsInfinite (BitVec.ofNat 64 raw)) :
    decodeF64Bits raw =
      if Binary64Bits.signBit (BitVec.ofNat 64 raw) then
        some .negInf
      else
        some .posInf :=
  decodeF64Bits_of_infinite raw hinfinite

example (raw : Nat)
    (hnan : Binary64Bits.IsNaN (BitVec.ofNat 64 raw)) :
    decodeF64Bits raw = none :=
  decodeF64Bits_of_nan raw hnan

example (left right : F64Value) :
    (F64Value.minimum left right).toEReal =
      min left.toEReal right.toEReal :=
  F64Value.minimum_toEReal left right

example (left right : F64Value) :
    (F64Value.maximum left right).toEReal =
      max left.toEReal right.toEReal :=
  F64Value.maximum_toEReal left right

example (op : F64BinaryOp) (x y : ℝ) :
    ∃ result,
      directedBinary op .down (.finite x) (.finite y) = some result ∧
      result.toEReal ≤ (exactBinary op x y : EReal) :=
  directedBinary_down_le op x y

example (op : F64BinaryOp) (x y : ℝ) :
    ∃ result,
      directedBinary op .up (.finite x) (.finite y) = some result ∧
      (exactBinary op x y : EReal) ≤ result.toEReal :=
  le_directedBinary_up op x y

example (registers : F64RegisterFile) :
    executeF64Instruction (.branch ⟨0⟩) registers = none := rfl

#print axioms SparkInterval.PTX.directedBinary_down_le
#print axioms SparkInterval.PTX.le_directedBinary_up
#print axioms SparkInterval.PTX.executeCanonicalAdd_contains
#print axioms SparkInterval.PTX.executeCanonicalSub_contains
#print axioms SparkInterval.PTX.executeCanonicalMul_contains

end SparkInterval.Tests.PTXSemantics
