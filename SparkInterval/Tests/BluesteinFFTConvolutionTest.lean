/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinFFTConvolution

set_option autoImplicit false

namespace SparkInterval.Tests.BluesteinFFTConvolutionTest

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution

/-- Bounded symbolic inversion test at transform length eight. -/
example (source : ExactState 3) (frequency : Fin 8) :
    normalizedNegativeDFT (positiveTransform source) frequency =
      source.value frequency :=
  normalizedNegativeDFT_positiveTransform source frequency

/-- The same bounded inversion test through the exact staged networks. -/
example (source : ExactState 3) (frequency : Fin 8) :
    normalizedNegativeRadix2
        (positiveRadix2Transform source) frequency =
      source.value frequency :=
  normalizedNegativeRadix2_positiveRadix2 source frequency

/-- Bounded inversion test in the CUDA source's mirrored sign convention. -/
example (source : ExactState 3) (frequency : Fin 8) :
    normalizedPositiveRadix2
        (negativeRadix2Transform source) frequency =
      source.value frequency :=
  normalizedPositiveRadix2_negativeRadix2 source frequency

/-- Bounded symbolic convolution theorem at transform length eight. -/
example (left right : ExactState 3) (frequency : Fin 8) :
    positiveDFT (cyclicConvolution left right) frequency =
      positiveDFT left frequency * positiveDFT right frequency :=
  positiveDFT_cyclicConvolution left right frequency

/-- The source-level radix-2 network computes the same length-eight cyclic
convolution. -/
example (left right : ExactState 3) (output : Fin 8) :
    normalizedNegativeRadix2
        (pointwiseProduct
          (positiveRadix2Transform left)
          (positiveRadix2Transform right))
        output =
      (cyclicConvolution left right).value output :=
  normalizedNegativeRadix2_pointwise_positiveRadix2
    left right output

/-- The length-five CUDA kernel has a literal-zero middle in its
length-sixteen allocation. -/
example :
    (zeroPaddedKernelState 5 4).value
        (⟨5, by omega⟩ : Fin 16) = 0 := by
  rfl

/-- A length-five Bluestein transform fits without aliasing in a
length-sixteen radix-2 convolution. -/
example (source : Fin 5 → ℂ) (frequency : Fin 5) :
    SparkInterval.Dirichlet.BluesteinDFT.halfRoot
          5 ((frequency.val : Int) ^ 2) *
        normalizedNegativeRadix2
          (pointwiseProduct
            (positiveRadix2Transform
              (paddedInputState 5 4 source))
            (positiveRadix2Transform
              (paddedKernelState 5 4)))
          (paddedFrequency (by omega : 5 ≤ 2 ^ 4) frequency) =
      SparkInterval.Dirichlet.BluesteinDFT.positiveDFT
        5 source frequency :=
  fft_pointwise_ifft_bluestein_eq_positiveDFT
    (by omega) (by omega) source frequency

/-- The same bounded Bluestein theorem with the signs used by the optimized
CUDA source: negative forward transforms and a normalized positive inverse. -/
example (source : Fin 5 → ℂ) (frequency : Fin 5) :
    SparkInterval.Dirichlet.BluesteinDFT.halfRoot
          5 ((frequency.val : Int) ^ 2) *
        normalizedPositiveRadix2
          (pointwiseProduct
            (negativeRadix2Transform
              (paddedInputState 5 4 source))
            (negativeRadix2Transform
              (zeroPaddedKernelState 5 4)))
          (paddedFrequency (by omega : 5 ≤ 2 ^ 4) frequency) =
      SparkInterval.Dirichlet.BluesteinDFT.positiveDFT
        5 source frequency :=
  cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT
    (by omega) (by omega) source frequency

#print axioms normalized_dft_zPositive
#print axioms normalizedNegativeDFT_positiveTransform
#print axioms normalizedNegativeRadix2_positiveRadix2
#print axioms normalizedPositiveRadix2_negativeRadix2
#print axioms positiveDFT_cyclicConvolution
#print axioms normalizedNegativeRadix2_pointwise_positiveRadix2
#print axioms fft_pointwise_ifft_bluestein_eq_positiveDFT
#print axioms cyclicConvolution_zeroPaddedKernel
#print axioms cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT

end SparkInterval.Tests.BluesteinFFTConvolutionTest
