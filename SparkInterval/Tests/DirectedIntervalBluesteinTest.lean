/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.DirectedIntervalBluestein

set_option autoImplicit false

namespace SparkInterval.Tests.DirectedIntervalBluesteinTest

open SparkInterval
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution
open SparkInterval.Dirichlet.BluesteinCUDADataflow
open SparkInterval.Dirichlet.DirectedIntervalFFT
open SparkInterval.Dirichlet.DirectedIntervalBluestein

/-- Exact real arithmetic gives a satisfiable instance of every abstract
directed-rounding premise in this module. -/
noncomputable def exactRounding : DirectedRound where
  down := id
  up := id
  down_le := by simp
  le_up := by simp

noncomputable def pointState {logLength : Nat}
    (state : ExactState logLength) : IntervalState logLength :=
  ⟨fun index => ComplexInterval.point (state.value index)⟩

noncomputable def pointTwiddles
    (twiddles : Nat → Nat → ℂ) : Nat → Nat → ComplexInterval :=
  fun stage offset => ComplexInterval.point (twiddles stage offset)

noncomputable def pointSource {order : Nat}
    (source : Fin order → ℂ) : Fin order → ComplexInterval :=
  fun input => ComplexInterval.point (source input)

noncomputable def pointInputChirps (order : Nat) :
    Fin order → ComplexInterval :=
  fun input =>
    ComplexInterval.point
      (SparkInterval.Dirichlet.BluesteinDFT.halfRoot
        order ((input.val : Int) ^ 2))

noncomputable def pointOutputChirps (order : Nat) :
    Fin order → ComplexInterval :=
  pointInputChirps order

theorem pointState_contains {logLength : Nat}
    (state : ExactState logLength) :
    StateContains (pointState state) state := by
  intro index
  exact ComplexInterval.point_contains _

theorem pointTwiddles_contain {logLength : Nat}
    (twiddles : Nat → Nat → ℂ) :
    TwiddlesContain (logLength := logLength)
      (pointTwiddles twiddles) twiddles := by
  intro stage _ offset _
  exact ComplexInterval.point_contains _

theorem pointSource_contains {order : Nat}
    (source : Fin order → ℂ) :
    SourcesContain (pointSource source) source := by
  intro input
  exact ComplexInterval.point_contains _

theorem pointInputChirps_contain (order : Nat) :
    InputChirpsContain (pointInputChirps order) := by
  intro input
  exact ComplexInterval.point_contains _

theorem pointOutputChirps_contain (order : Nat) :
    OutputChirpsContain (pointOutputChirps order) := by
  intro frequency
  exact ComplexInterval.point_contains _

theorem pointNormalization_contains (logLength : Nat) :
    NormalizationContains (logLength := logLength)
      (ComplexInterval.point (((2 ^ logLength : Nat) : ℂ)⁻¹)) :=
  ComplexInterval.point_contains _

/-- The complete premise set is jointly satisfiable at a concrete padded
length-five transform.  This exercises both negative FFTs, the fused scatter,
the positive inverse, and the normalization theorem. -/
example (source : Fin 5 → ℂ) (frequency : Fin 5) :
    (directedBluesteinLineValue exactRounding 5 4
      (pointSource source) (pointInputChirps 5)
      (pointState (zeroPaddedKernelState 5 4))
      (pointTwiddles negativeTwiddle)
      (pointTwiddles positiveTwiddle)
      (pointOutputChirps 5)
      (ComplexInterval.point (((2 ^ 4 : Nat) : ℂ)⁻¹))
      frequency (by omega)).Contains
      (cudaBluesteinSourceLineValue 5 4 source frequency (by omega)) := by
  exact
    directedBluesteinLineValue_contains_cudaSourceLine exactRounding
      frequency (by omega)
      (pointSource_contains source)
      (pointInputChirps_contain 5)
      (pointState_contains _)
      (pointTwiddles_contain negativeTwiddle)
      (pointTwiddles_contain positiveTwiddle)
      (pointOutputChirps_contain 5)
      (pointNormalization_contains 4)

/-- The same non-vacuous instance reaches the direct positive DFT using the
exact no-alias Bluestein theorem. -/
example (source : Fin 5 → ℂ) (frequency : Fin 5) :
    (directedBluesteinLineValue exactRounding 5 4
      (pointSource source) (pointInputChirps 5)
      (pointState (zeroPaddedKernelState 5 4))
      (pointTwiddles negativeTwiddle)
      (pointTwiddles positiveTwiddle)
      (pointOutputChirps 5)
      (ComplexInterval.point (((2 ^ 4 : Nat) : ℂ)⁻¹))
      frequency (by omega)).Contains
      (SparkInterval.Dirichlet.BluesteinDFT.positiveDFT
        5 source frequency) := by
  exact
    directedBluesteinLineValue_contains_positiveDFT exactRounding
      frequency (by omega) (by omega)
      (pointSource_contains source)
      (pointInputChirps_contain 5)
      (pointState_contains _)
      (pointTwiddles_contain negativeTwiddle)
      (pointTwiddles_contain positiveTwiddle)
      (pointOutputChirps_contain 5)
      (pointNormalization_contains 4)

#print axioms directedPaddedInputNatural_contains
#print axioms bitReverseScatterInterval_contains
#print axioms directedNegativeFFTFromBitReversed_contains
#print axioms directedPositiveFFTFromBitReversed_contains
#print axioms directedPointwiseBitReverseCopy_contains
#print axioms directedGatherOutput_contains
#print axioms directedBluesteinLineValue_contains_cudaLine
#print axioms directedBluesteinLineValue_contains_cudaSourceLine
#print axioms directedBluesteinLineValue_contains_positiveDFT

end SparkInterval.Tests.DirectedIntervalBluesteinTest
