import SparkInterval.FloatFormat

set_option autoImplicit false

namespace SparkInterval.Tests.FloatFormat

open SparkInterval

private abbrev bits (n : Nat) : Binary64Bits := BitVec.ofNat 64 n

private def positiveZero : Binary64Bits := bits 0x0000000000000000
private def negativeZero : Binary64Bits := bits 0x8000000000000000
private def leastSubnormal : Binary64Bits := bits 0x0000000000000001
private def greatestSubnormal : Binary64Bits := bits 0x000fffffffffffff
private def leastNormal : Binary64Bits := bits 0x0010000000000000
private def one : Binary64Bits := bits 0x3ff0000000000000
private def negativeOne : Binary64Bits := bits 0xbff0000000000000
private def greatestFinite : Binary64Bits := bits 0x7fefffffffffffff
private def positiveInfinity : Binary64Bits := bits 0x7ff0000000000000
private def negativeInfinity : Binary64Bits := bits 0xfff0000000000000
private def quietNaN : Binary64Bits := bits 0x7ff8000000000000

example : positiveZero.classify = .positiveZero := by native_decide
example : negativeZero.classify = .negativeZero := by native_decide
example : leastSubnormal.classify = .positiveSubnormal := by native_decide
example : greatestSubnormal.classify = .positiveSubnormal := by native_decide
example : leastNormal.classify = .positiveNormal := by native_decide
example : one.classify = .positiveNormal := by native_decide
example : negativeOne.classify = .negativeNormal := by native_decide
example : greatestFinite.classify = .positiveNormal := by native_decide
example : positiveInfinity.classify = .positiveInfinity := by native_decide
example : negativeInfinity.classify = .negativeInfinity := by native_decide
example : quietNaN.classify = .nan := by native_decide

example : positiveZero ≠ negativeZero := by native_decide
example : positiveZero.IsFinite := by native_decide
example : greatestFinite.IsFinite := by native_decide
example : ¬positiveInfinity.IsFinite := by native_decide
example : ¬negativeInfinity.IsFinite := by native_decide
example : ¬quietNaN.IsFinite := by native_decide

private def positiveZeroFinite : Binary64Finite :=
  ⟨positiveZero, by native_decide⟩

private def negativeZeroFinite : Binary64Finite :=
  ⟨negativeZero, by native_decide⟩

private def leastSubnormalFinite : Binary64Finite :=
  ⟨leastSubnormal, by native_decide⟩

private def leastNormalFinite : Binary64Finite :=
  ⟨leastNormal, by native_decide⟩

private def oneFinite : Binary64Finite :=
  ⟨one, by native_decide⟩

private def negativeOneFinite : Binary64Finite :=
  ⟨negativeOne, by native_decide⟩

example : positiveZeroFinite.sign = false := by native_decide
example : negativeZeroFinite.sign = true := by native_decide

example : positiveZeroFinite.toReal = 0 := by
  rw [Binary64Finite.toReal_eq_zero_iff]
  native_decide

example : negativeZeroFinite.toReal = 0 := by
  rw [Binary64Finite.toReal_eq_zero_iff]
  native_decide

example : leastSubnormalFinite.significand = 1 := by native_decide
example : leastSubnormalFinite.exponent = -1074 := by native_decide
example : leastSubnormalFinite.toReal = (2 : ℝ) ^ (-1074 : Int) := by
  norm_num [Binary64Finite.toReal, Binary64Finite.magnitude,
    Binary64Finite.sign, Binary64Finite.significand, Binary64Finite.exponent,
    leastSubnormalFinite, leastSubnormal, bits, Binary64Bits.signBit,
    Binary64Bits.exponentBits, Binary64Bits.fractionBits,
    Binary64Bits.signThreshold, Binary64Bits.fractionModulus,
    Binary64Bits.exponentModulus]

example : leastNormalFinite.significand = Binary64Bits.fractionModulus := by
  native_decide

example : leastNormalFinite.exponent = -1074 := by native_decide

example : oneFinite.significand = Binary64Bits.fractionModulus := by native_decide
example : oneFinite.exponent = -52 := by native_decide
example : oneFinite.toReal = 1 := by
  norm_num [Binary64Finite.toReal, Binary64Finite.magnitude,
    Binary64Finite.sign, Binary64Finite.significand, Binary64Finite.exponent,
    oneFinite, one, bits, Binary64Bits.signBit, Binary64Bits.exponentBits,
    Binary64Bits.fractionBits, Binary64Bits.signThreshold,
    Binary64Bits.fractionModulus, Binary64Bits.exponentModulus, zpow_neg]

example : negativeOneFinite.toReal = -1 := by
  norm_num [Binary64Finite.toReal, Binary64Finite.magnitude,
    Binary64Finite.sign, Binary64Finite.significand, Binary64Finite.exponent,
    negativeOneFinite, negativeOne, bits, Binary64Bits.signBit,
    Binary64Bits.exponentBits, Binary64Bits.fractionBits,
    Binary64Bits.signThreshold, Binary64Bits.fractionModulus,
    Binary64Bits.exponentModulus, zpow_neg]

end SparkInterval.Tests.FloatFormat
