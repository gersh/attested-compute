import SparkInterval.DirectedRounding

/-! Compile-time regression tests for the mathematical binary64 rounding model. -/

set_option autoImplicit false

namespace SparkInterval.Tests.Rounding

open SparkInterval
open SparkInterval.Binary64Rounding

example (x : ℝ) : (roundDown x).toEReal ≤ (x : EReal) :=
  roundDown_le x

example (x : ℝ) : (x : EReal) ≤ (roundUp x).toEReal :=
  le_roundUp x

example (x : ℝ) (y : Binary64Finite) (h : y.toReal ≤ x) :
    (y.toReal : EReal) ≤ (roundDown x).toEReal :=
  roundDown_greatest y h

example (x : ℝ) (y : Binary64Finite) (h : x ≤ y.toReal) :
    (roundUp x).toEReal ≤ (y.toReal : EReal) :=
  roundUp_least y h

example (x : Binary64Value) :
    (predecessor x).toEReal < (x.1 : EReal) :=
  predecessor_lt x

example (x : Binary64Value) :
    (x.1 : EReal) < (successor x).toEReal :=
  lt_successor x

example (x : Binary64Value) (y : Binary64Finite) (h : y.toReal < x.1) :
    (y.toReal : EReal) ≤ (predecessor x).toEReal :=
  le_predecessor_of_lt x y h

example (x : Binary64Value) (y : Binary64Finite) (h : x.1 < y.toReal) :
    (successor x).toEReal ≤ (y.toReal : EReal) :=
  successor_le_of_lt x y h

example (y : Binary64Finite) :
    roundDown y.toReal = .finite y.asValue :=
  roundDown_exact y.asValue

example (y : Binary64Finite) :
    roundUp y.toReal = .finite y.asValue :=
  roundUp_exact y.asValue

example :
    Binary64Finite.positiveZero.bits ≠ Binary64Finite.negativeZero.bits :=
  Binary64Finite.positiveZero_bits_ne_negativeZero_bits

example :
    Binary64Finite.positiveZero.asValue = Binary64Finite.negativeZero.asValue :=
  Binary64Finite.signedZeros_asValue_eq

example :
    roundDown Binary64Finite.positiveZero.toReal =
      .finite Binary64Finite.negativeZero.asValue :=
  roundDown_signed_zero

example :
    roundUp Binary64Finite.negativeZero.toReal =
      .finite Binary64Finite.positiveZero.asValue :=
  roundUp_signed_zero

example :
    maxFiniteReal = Binary64Finite.greatestPositiveFinite.toReal :=
  maxFiniteReal_eq_greatestPositiveFinite

example :
    minFiniteReal = -Binary64Finite.greatestPositiveFinite.toReal :=
  minFiniteReal_eq_neg_greatestPositiveFinite

example : roundDown (maxFiniteReal + 1) = .finite maxFinite := by
  apply roundDown_of_maxFinite_le
  linarith

example : roundUp (maxFiniteReal + 1) = .posInf := by
  apply roundUp_eq_posInf_of_maxFinite_lt
  linarith

example : roundDown (minFiniteReal - 1) = .negInf := by
  apply roundDown_eq_negInf_of_lt_minFinite
  linarith

example : roundUp (minFiniteReal - 1) = .finite minFinite := by
  apply roundUp_of_le_minFinite
  linarith

example (x : ℝ) (y : Binary64Finite) :
    |x - (nearestFinite x).1| ≤ |x - y.toReal| :=
  nearestFinite_isNearest x y

/-- Regression for the ties-to-even preference branch: whenever a nearest
candidate has an even significand witness, the selected result does too. -/
example {x : ℝ} (h : (evenNearestCandidates x).Nonempty) :
    HasEvenSignificand (nearestFinite x).1 :=
  nearestFinite_hasEvenSignificand h

example (y : Binary64Finite) : nearestFinite y.toReal = y.asValue :=
  nearestFinite_exact y.asValue

example :
    roundNearestEven nearestEvenOverflowThreshold = .posInf :=
  roundNearestEven_eq_posInf le_rfl

example :
    roundNearestEven (-nearestEvenOverflowThreshold) = .negInf :=
  roundNearestEven_eq_negInf le_rfl

example (y : Binary64Finite) :
    roundNearestEven y.toReal = .finite y.asValue :=
  roundNearestEven_exact y.asValue

example :
    roundNearestEven Binary64Finite.positiveZero.toReal =
      .finite Binary64Finite.negativeZero.asValue :=
  roundNearestEven_signed_zero

end SparkInterval.Tests.Rounding
