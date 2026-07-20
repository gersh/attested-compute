import SparkInterval.Zeta.SymmetricCount

/-! Regression tests for positive-ordinate/symmetric multiplicity bookkeeping. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaSymmetricCount

open SparkInterval.Zeta

example (height : ℝ) :
    zetaZeroMultiplicityCount height =
      positiveZetaZeroMultiplicityCount height +
        negativeZetaZeroMultiplicityCount height +
          realAxisZetaZeroMultiplicityCount height :=
  zetaZeroMultiplicityCount_partition height

example (symmetry : ZetaConjugationMultiplicitySymmetry) (height : ℝ) :
    negativeZetaZeroMultiplicityCount height =
      positiveZetaZeroMultiplicityCount height :=
  symmetry.negative_eq_positive height

example {height : ℝ}
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    zetaZeroMultiplicityCount height =
      2 * positiveZetaZeroMultiplicityCount height :=
  zetaZeroMultiplicityCount_eq_two_mul_positive symmetry noRealAxis

example {height : ℝ} {bound : Nat}
    (positiveUpper : PositiveZetaMultiplicityCountUpperBound height bound)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    ZetaMultiplicityCountUpperBound height (2 * bound) :=
  positiveUpper.toZetaMultiplicityCountUpperBound symmetry noRealAxis

example {height : ℝ} {bound : Nat}
    (positiveUpper : PositiveZetaMultiplicityCountUpperBound height bound)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    ZetaZeroCountUpperBound height (2 * bound) :=
  positiveUpper.toZetaZeroCountUpperBound symmetry noRealAxis

end SparkInterval.Tests.ZetaSymmetricCount
