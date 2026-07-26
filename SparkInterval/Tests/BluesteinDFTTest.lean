/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinDFT

namespace SparkInterval.Tests.BluesteinDFTTest

open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.BluesteinDFT

example (source : Fin 7 → ℂ) (frequency : Fin 7) :
    bluesteinValue 7 source frequency =
      positiveDFT 7 source frequency :=
  bluesteinValue_eq_positiveDFT (by omega) source frequency

example (source : Fin 7 → ℂ) (frequency : Fin 7) :
    paddedBluesteinValue 7 16 source frequency =
      positiveDFT 7 source frequency :=
  paddedBluesteinValue_eq_positiveDFT (by omega) (by omega)
    source frequency

example :
    halfRoot 7 ((3 : Int) ^ 2) *
        halfRoot 7 ((5 : Int) ^ 2) *
        halfRoot 7 (-(((3 : Int) - 5) ^ 2)) =
      signedUnitRoot 7 ((3 : Int) * 5) :=
  bluestein_kernel_identity (by omega) 3 5

example (frequency : Fin 7) :
    positiveDFT 7 (basisVector (1 : Fin 7)) frequency =
      signedUnitRoot 7 (frequency.val : Int) := by
  rw [positiveDFT_basisVector]
  simp

example (frequency : Fin 7) :
    positiveDFT 7 (basisVector (1 : Fin 7)) frequency =
      FactoredSmallQDFT.unitRoot 7 frequency.val :=
  positiveDFT_basisOne_eq_unitRoot (by omega) frequency

#print axioms bluestein_kernel_identity
#print axioms positiveDFT_basisVector
#print axioms positiveDFT_basisOne_eq_unitRoot
#print axioms centeredIndex_circularIndex
#print axioms paddedCyclicConvolutionValue_eq_bluesteinConvolutionValue
#print axioms bluesteinValue_eq_positiveDFT
#print axioms paddedBluesteinValue_eq_positiveDFT
#print axioms positiveDFT_two_pow_eq_existing

end SparkInterval.Tests.BluesteinDFTTest
