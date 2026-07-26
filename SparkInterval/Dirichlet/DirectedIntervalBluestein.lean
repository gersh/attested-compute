/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinCUDADataflow
import SparkInterval.Dirichlet.DirectedIntervalFFT

/-!
# Complete directed-interval Bluestein line

This module composes the abstract directed complex operations, the directed
radix-2 stage invariant, and the exact CUDA-shaped Bluestein dataflow.  One
interval line performs, in order:

* positive pre-chirp multiplication and literal-zero padding;
* the `initializeA` bit-reversal scatter;
* a second bit-reversal scatter for the zero-padded kernel;
* two negative-root forward FFTs;
* pointwise multiplication fused with the inverse bit-reversal scatter;
* one positive-root inverse FFT;
* positive post-chirp multiplication and one normalization by `1 / L`.

Every transcendental or machine-facing fact remains a visible enclosure
premise: source values, input chirps, the zero-padded kernel, negative and
positive twiddles, the output chirp, and the normalization factor.  The main
theorem proves containment first of the exact ungrouped CUDA arithmetic and
then of `cudaBluesteinSourceLineValue`, whose separate exact theorem accounts
for the production shared-memory grouping.

This file proves only mathematical interval containment.  It makes no claim
about MPFR root generation, IEEE or PTX directed rounding, CUDA execution,
flat physical memory, compilation, attestation, or a physical run.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.DirectedIntervalBluestein

open SparkInterval
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution
open SparkInterval.Dirichlet.BluesteinCUDADataflow
open SparkInterval.Dirichlet.DirectedIntervalFFT

/-! ## Explicit table-enclosure premises -/

/-- Every source rectangle encloses the corresponding exact line value. -/
def SourcesContain {order : Nat}
    (sourceBoxes : Fin order → ComplexInterval)
    (source : Fin order → ℂ) : Prop :=
  ∀ input, (sourceBoxes input).Contains (source input)

/-- Every positive input-chirp rectangle encloses its exact half root. -/
def InputChirpsContain {order : Nat}
    (chirpBoxes : Fin order → ComplexInterval) : Prop :=
  ∀ input,
    (chirpBoxes input).Contains
      (BluesteinDFT.halfRoot order ((input.val : Int) ^ 2))

/-- A natural-order kernel table encloses the exact literal-zero-middle
kernel used by the CUDA source. -/
def KernelContains {logLength order : Nat}
    (kernelBoxes : IntervalState logLength) : Prop :=
  StateContains kernelBoxes
    (zeroPaddedKernelState order logLength)

/-- Every positive output-chirp rectangle encloses its exact half root. -/
def OutputChirpsContain {order : Nat}
    (chirpBoxes : Fin order → ComplexInterval) : Prop :=
  ∀ frequency,
    (chirpBoxes frequency).Contains
      (BluesteinDFT.halfRoot order ((frequency.val : Int) ^ 2))

/-- The one normalization rectangle encloses the exact `1 / L` factor. -/
def NormalizationContains {logLength : Nat}
    (normalizationBox : ComplexInterval) : Prop :=
  normalizationBox.Contains (((2 ^ logLength : Nat) : ℂ)⁻¹)

/-! ## Pre-chirp, padding, and source scatters -/

/-- Natural-order interval input after positive pre-chirp multiplication.
Positions beyond `order` are the exact singleton zero rectangle. -/
noncomputable def directedPaddedInputNatural
    (rounding : DirectedRound) (order logLength : Nat)
    (sourceBoxes chirpBoxes : Fin order → ComplexInterval) :
    IntervalState logLength :=
  ⟨fun input =>
    if hinput : input.val < order then
      ComplexInterval.directedMul rounding
        (sourceBoxes ⟨input.val, hinput⟩)
        (chirpBoxes ⟨input.val, hinput⟩)
    else
      ComplexInterval.point 0⟩

/-- The directed pre-chirp and literal padding enclose the exact padded
Bluestein input. -/
theorem directedPaddedInputNatural_contains
    (rounding : DirectedRound)
    {order logLength : Nat}
    {sourceBoxes chirpBoxes : Fin order → ComplexInterval}
    {source : Fin order → ℂ}
    (hsource : SourcesContain sourceBoxes source)
    (hchirps : InputChirpsContain chirpBoxes) :
    StateContains
      (directedPaddedInputNatural rounding order logLength
        sourceBoxes chirpBoxes)
      (paddedInputState order logLength source) := by
  intro input
  by_cases hinput : input.val < order
  · simpa [directedPaddedInputNatural, paddedInputState,
      BluesteinDFT.paddedChirpedInput, BluesteinDFT.chirpedInput, hinput]
      using
        (ComplexInterval.directedMul_contains rounding
          (hsource ⟨input.val, hinput⟩)
          (hchirps ⟨input.val, hinput⟩))
  · simp [directedPaddedInputNatural, paddedInputState,
      BluesteinDFT.paddedChirpedInput, hinput]

/-- Interval counterpart of the source's unique bit-reversal scatter. -/
noncomputable def bitReverseScatterInterval {logLength : Nat}
    (natural : IntervalState logLength) : IntervalState logLength :=
  ⟨fun address => natural.value (bitReverseIndex address)⟩

/-- The interval scatter preserves pointwise enclosure of the exact source
scatter. -/
theorem bitReverseScatterInterval_contains {logLength : Nat}
    {natural : IntervalState logLength}
    {exact : ExactState logLength}
    (hnatural : StateContains natural exact) :
    StateContains
      (bitReverseScatterInterval natural)
      (bitReverseScatter exact) := by
  intro address
  exact hnatural (bitReverseIndex address)

/-! ## Negative forward and positive inverse transforms -/

/-- Directed negative-root transform entered at bit-reversed addresses. -/
noncomputable def directedNegativeFFTFromBitReversed {logLength : Nat}
    (rounding : DirectedRound)
    (twiddleBoxes : Nat → Nat → ComplexInterval)
    (state : IntervalState logLength) : IntervalState logLength :=
  runDirectedStages rounding twiddleBoxes logLength 0 state

/-- Directed positive-root transform entered at bit-reversed addresses. -/
noncomputable def directedPositiveFFTFromBitReversed {logLength : Nat}
    (rounding : DirectedRound)
    (twiddleBoxes : Nat → Nat → ComplexInterval)
    (state : IntervalState logLength) : IntervalState logLength :=
  runDirectedStages rounding twiddleBoxes logLength 0 state

/-- The complete negative-root stage graph encloses the exact source graph. -/
theorem directedNegativeFFTFromBitReversed_contains {logLength : Nat}
    (rounding : DirectedRound)
    {twiddleBoxes : Nat → Nat → ComplexInterval}
    {state : IntervalState logLength}
    {exact : ExactState logLength}
    (hstate : StateContains state exact)
    (htwiddles : TwiddlesContain (logLength := logLength)
      twiddleBoxes negativeTwiddle) :
    StateContains
      (directedNegativeFFTFromBitReversed rounding twiddleBoxes state)
      (negativeFFTFromBitReversed exact) := by
  simpa [directedNegativeFFTFromBitReversed,
    negativeFFTFromBitReversed] using
    (runDirectedStages_contains (logLength := logLength) rounding
      (twiddleBoxes := twiddleBoxes)
      (twiddles := negativeTwiddle)
      (count := logLength)
      (expectedStage := 0)
      (current := state)
      (exact := exact)
      (by omega) hstate htwiddles)

/-- The complete positive-root stage graph encloses the exact source graph. -/
theorem directedPositiveFFTFromBitReversed_contains {logLength : Nat}
    (rounding : DirectedRound)
    {twiddleBoxes : Nat → Nat → ComplexInterval}
    {state : IntervalState logLength}
    {exact : ExactState logLength}
    (hstate : StateContains state exact)
    (htwiddles : TwiddlesContain (logLength := logLength)
      twiddleBoxes positiveTwiddle) :
    StateContains
      (directedPositiveFFTFromBitReversed rounding twiddleBoxes state)
      (positiveFFTFromBitReversed exact) := by
  simpa [directedPositiveFFTFromBitReversed,
    positiveFFTFromBitReversed] using
    (runDirectedStages_contains (logLength := logLength) rounding
      (twiddleBoxes := twiddleBoxes)
      (twiddles := positiveTwiddle)
      (count := logLength)
      (expectedStage := 0)
      (current := state)
      (exact := exact)
      (by omega) hstate htwiddles)

/-! ## Fused pointwise multiplication and inverse scatter -/

/-- Directed interval counterpart of `pointwiseBitReverseCopy`: multiply at
the natural frequency and store at the inverse FFT's bit-reversed address. -/
noncomputable def directedPointwiseBitReverseCopy {logLength : Nat}
    (rounding : DirectedRound)
    (values multiplier : IntervalState logLength) :
    IntervalState logLength :=
  bitReverseScatterInterval
    ⟨fun frequency =>
      ComplexInterval.directedMul rounding
        (values.value frequency) (multiplier.value frequency)⟩

/-- The fused directed pointwise/scatter operation encloses the exact fused
source operation. -/
theorem directedPointwiseBitReverseCopy_contains {logLength : Nat}
    (rounding : DirectedRound)
    {values multiplier : IntervalState logLength}
    {exactValues exactMultiplier : ExactState logLength}
    (hvalues : StateContains values exactValues)
    (hmultiplier : StateContains multiplier exactMultiplier) :
    StateContains
      (directedPointwiseBitReverseCopy rounding values multiplier)
      (pointwiseBitReverseCopy exactValues exactMultiplier) := by
  intro address
  exact
    ComplexInterval.directedMul_contains rounding
      (hvalues (bitReverseIndex address))
      (hmultiplier (bitReverseIndex address))

/-! ## Post-chirp and the single normalization -/

/-- Directed gather arithmetic: positive post-chirp followed by exactly one
multiplication by an interval enclosing `1 / L`. -/
noncomputable def directedGatherOutput
    {order logLength : Nat}
    (rounding : DirectedRound)
    (workspace : IntervalState logLength)
    (postChirpBox normalizationBox : ComplexInterval)
    (frequency : Fin order)
    (hle : order ≤ 2 ^ logLength) : ComplexInterval :=
  ComplexInterval.directedMul rounding
    (ComplexInterval.directedMul rounding
      (workspace.value (paddedFrequency hle frequency))
      postChirpBox)
    normalizationBox

/-- The abstract gather encloses the exact source-order post-chirp and
normalization. -/
theorem directedGatherOutput_contains
    {order logLength : Nat}
    (rounding : DirectedRound)
    {workspace : IntervalState logLength}
    {exactWorkspace : ExactState logLength}
    {postChirpBox normalizationBox : ComplexInterval}
    (frequency : Fin order)
    (hle : order ≤ 2 ^ logLength)
    (hworkspace : StateContains workspace exactWorkspace)
    (hpost :
      postChirpBox.Contains
        (BluesteinDFT.halfRoot order ((frequency.val : Int) ^ 2)))
    (hnormalization : NormalizationContains
      (logLength := logLength) normalizationBox) :
    (directedGatherOutput rounding workspace postChirpBox
      normalizationBox frequency hle).Contains
      (gatherOutputValue order logLength exactWorkspace frequency hle) := by
  have hproduct :
      (ComplexInterval.directedMul rounding
        (workspace.value (paddedFrequency hle frequency))
        postChirpBox).Contains
        (exactWorkspace.value (paddedFrequency hle frequency) *
          BluesteinDFT.halfRoot order ((frequency.val : Int) ^ 2)) :=
    ComplexInterval.directedMul_contains rounding
      (hworkspace (paddedFrequency hle frequency)) hpost
  have hscaled :=
    ComplexInterval.directedMul_contains rounding
      hproduct hnormalization
  simpa [directedGatherOutput, gatherOutputValue, div_eq_mul_inv] using
    hscaled

/-! ## Complete line -/

/-- The complete directed-interval line in the CUDA source's operation
order.  The kernel input is natural order; both source scatters are part of
this definition. -/
noncomputable def directedBluesteinLineValue
    (rounding : DirectedRound)
    (order logLength : Nat)
    (sourceBoxes inputChirpBoxes : Fin order → ComplexInterval)
    (kernelBoxes : IntervalState logLength)
    (negativeTwiddleBoxes positiveTwiddleBoxes :
      Nat → Nat → ComplexInterval)
    (outputChirpBoxes : Fin order → ComplexInterval)
    (normalizationBox : ComplexInterval)
    (frequency : Fin order)
    (hle : order ≤ 2 ^ logLength) : ComplexInterval :=
  let initializedNatural :=
    directedPaddedInputNatural rounding order logLength
      sourceBoxes inputChirpBoxes
  let initialized := bitReverseScatterInterval initializedNatural
  let kernel := bitReverseScatterInterval kernelBoxes
  let transformedInput :=
    directedNegativeFFTFromBitReversed rounding
      negativeTwiddleBoxes initialized
  let transformedKernel :=
    directedNegativeFFTFromBitReversed rounding
      negativeTwiddleBoxes kernel
  let fused :=
    directedPointwiseBitReverseCopy rounding
      transformedInput transformedKernel
  let inverse :=
    directedPositiveFFTFromBitReversed rounding
      positiveTwiddleBoxes fused
  directedGatherOutput rounding inverse
    (outputChirpBoxes frequency) normalizationBox frequency hle

/-- Full arithmetic containment theorem before using any Bluestein algebra:
the directed line encloses the exact ungrouped CUDA-shaped line value. -/
theorem directedBluesteinLineValue_contains_cudaLine
    (rounding : DirectedRound)
    {order logLength : Nat}
    {sourceBoxes inputChirpBoxes : Fin order → ComplexInterval}
    {kernelBoxes : IntervalState logLength}
    {negativeTwiddleBoxes positiveTwiddleBoxes :
      Nat → Nat → ComplexInterval}
    {outputChirpBoxes : Fin order → ComplexInterval}
    {normalizationBox : ComplexInterval}
    {source : Fin order → ℂ}
    (frequency : Fin order)
    (hle : order ≤ 2 ^ logLength)
    (hsource : SourcesContain sourceBoxes source)
    (hinputChirps : InputChirpsContain inputChirpBoxes)
    (hkernel : KernelContains (order := order) kernelBoxes)
    (hnegativeTwiddles :
      TwiddlesContain (logLength := logLength)
        negativeTwiddleBoxes negativeTwiddle)
    (hpositiveTwiddles :
      TwiddlesContain (logLength := logLength)
        positiveTwiddleBoxes positiveTwiddle)
    (houtputChirps : OutputChirpsContain outputChirpBoxes)
    (hnormalization :
      NormalizationContains (logLength := logLength) normalizationBox) :
    (directedBluesteinLineValue rounding order logLength
      sourceBoxes inputChirpBoxes kernelBoxes
      negativeTwiddleBoxes positiveTwiddleBoxes
      outputChirpBoxes normalizationBox frequency hle).Contains
      (cudaBluesteinLineValue order logLength source frequency hle) := by
  have hinitialNatural :
      StateContains
        (directedPaddedInputNatural rounding order logLength
          sourceBoxes inputChirpBoxes)
        (paddedInputState order logLength source) :=
    directedPaddedInputNatural_contains rounding hsource hinputChirps
  have hinitial :
      StateContains
        (bitReverseScatterInterval
          (directedPaddedInputNatural rounding order logLength
            sourceBoxes inputChirpBoxes))
        (initializeAWorkspace order logLength source) := by
    simpa [initializeAWorkspace, initializeANatural] using
      bitReverseScatterInterval_contains hinitialNatural
  have hkernelScatter :
      StateContains
        (bitReverseScatterInterval kernelBoxes)
        (bitReverseCopy
          (zeroPaddedKernelState order logLength)) := by
    simpa [bitReverseCopy] using
      bitReverseScatterInterval_contains hkernel
  have htransformedInput :
      StateContains
        (directedNegativeFFTFromBitReversed rounding
          negativeTwiddleBoxes
          (bitReverseScatterInterval
            (directedPaddedInputNatural rounding order logLength
              sourceBoxes inputChirpBoxes)))
        (negativeFFTFromBitReversed
          (initializeAWorkspace order logLength source)) :=
    directedNegativeFFTFromBitReversed_contains rounding
      hinitial hnegativeTwiddles
  have htransformedKernel :
      StateContains
        (directedNegativeFFTFromBitReversed rounding
          negativeTwiddleBoxes
          (bitReverseScatterInterval kernelBoxes))
        (negativeFFTFromBitReversed
          (bitReverseCopy
            (zeroPaddedKernelState order logLength))) :=
    directedNegativeFFTFromBitReversed_contains rounding
      hkernelScatter hnegativeTwiddles
  have hfused :
      StateContains
        (directedPointwiseBitReverseCopy rounding
          (directedNegativeFFTFromBitReversed rounding
            negativeTwiddleBoxes
            (bitReverseScatterInterval
              (directedPaddedInputNatural rounding order logLength
                sourceBoxes inputChirpBoxes)))
          (directedNegativeFFTFromBitReversed rounding
            negativeTwiddleBoxes
            (bitReverseScatterInterval kernelBoxes)))
        (pointwiseBitReverseCopy
          (negativeFFTFromBitReversed
            (initializeAWorkspace order logLength source))
          (negativeFFTFromBitReversed
            (bitReverseCopy
              (zeroPaddedKernelState order logLength)))) :=
    directedPointwiseBitReverseCopy_contains rounding
      htransformedInput htransformedKernel
  have hinverse :
      StateContains
        (directedPositiveFFTFromBitReversed rounding
          positiveTwiddleBoxes
          (directedPointwiseBitReverseCopy rounding
            (directedNegativeFFTFromBitReversed rounding
              negativeTwiddleBoxes
              (bitReverseScatterInterval
                (directedPaddedInputNatural rounding order logLength
                  sourceBoxes inputChirpBoxes)))
            (directedNegativeFFTFromBitReversed rounding
              negativeTwiddleBoxes
              (bitReverseScatterInterval kernelBoxes))))
        (positiveFFTFromBitReversed
          (pointwiseBitReverseCopy
            (negativeFFTFromBitReversed
              (initializeAWorkspace order logLength source))
            (negativeFFTFromBitReversed
              (bitReverseCopy
                (zeroPaddedKernelState order logLength))))) :=
    directedPositiveFFTFromBitReversed_contains rounding
      hfused hpositiveTwiddles
  have hgather :=
    directedGatherOutput_contains rounding frequency hle hinverse
      (houtputChirps frequency) hnormalization
  simpa [directedBluesteinLineValue, cudaBluesteinLineValue] using
    hgather

/-- Production-layout capstone: the same directed line encloses the exact
`min(L, 1024)` shared-prefix source value. -/
theorem directedBluesteinLineValue_contains_cudaSourceLine
    (rounding : DirectedRound)
    {order logLength : Nat}
    {sourceBoxes inputChirpBoxes : Fin order → ComplexInterval}
    {kernelBoxes : IntervalState logLength}
    {negativeTwiddleBoxes positiveTwiddleBoxes :
      Nat → Nat → ComplexInterval}
    {outputChirpBoxes : Fin order → ComplexInterval}
    {normalizationBox : ComplexInterval}
    {source : Fin order → ℂ}
    (frequency : Fin order)
    (hle : order ≤ 2 ^ logLength)
    (hsource : SourcesContain sourceBoxes source)
    (hinputChirps : InputChirpsContain inputChirpBoxes)
    (hkernel : KernelContains (order := order) kernelBoxes)
    (hnegativeTwiddles :
      TwiddlesContain (logLength := logLength)
        negativeTwiddleBoxes negativeTwiddle)
    (hpositiveTwiddles :
      TwiddlesContain (logLength := logLength)
        positiveTwiddleBoxes positiveTwiddle)
    (houtputChirps : OutputChirpsContain outputChirpBoxes)
    (hnormalization :
      NormalizationContains (logLength := logLength) normalizationBox) :
    (directedBluesteinLineValue rounding order logLength
      sourceBoxes inputChirpBoxes kernelBoxes
      negativeTwiddleBoxes positiveTwiddleBoxes
      outputChirpBoxes normalizationBox frequency hle).Contains
      (cudaBluesteinSourceLineValue
        order logLength source frequency hle) := by
  have hline :=
    directedBluesteinLineValue_contains_cudaLine rounding
      frequency hle hsource hinputChirps hkernel
      hnegativeTwiddles hpositiveTwiddles houtputChirps
      hnormalization
  simpa [cudaBluesteinSourceLineValue,
    cudaBluesteinSharedLineValue_eq_ungrouped] using hline

/-- Direct-DFT capstone.  The only additional hypotheses are the true
nonzero-order and `2 * order - 1 ≤ L` no-alias guards required by the exact
Bluestein identity. -/
theorem directedBluesteinLineValue_contains_positiveDFT
    (rounding : DirectedRound)
    {order logLength : Nat}
    {sourceBoxes inputChirpBoxes : Fin order → ComplexInterval}
    {kernelBoxes : IntervalState logLength}
    {negativeTwiddleBoxes positiveTwiddleBoxes :
      Nat → Nat → ComplexInterval}
    {outputChirpBoxes : Fin order → ComplexInterval}
    {normalizationBox : ComplexInterval}
    {source : Fin order → ℂ}
    (frequency : Fin order)
    (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (hsource : SourcesContain sourceBoxes source)
    (hinputChirps : InputChirpsContain inputChirpBoxes)
    (hkernel : KernelContains (order := order) kernelBoxes)
    (hnegativeTwiddles :
      TwiddlesContain (logLength := logLength)
        negativeTwiddleBoxes negativeTwiddle)
    (hpositiveTwiddles :
      TwiddlesContain (logLength := logLength)
        positiveTwiddleBoxes positiveTwiddle)
    (houtputChirps : OutputChirpsContain outputChirpBoxes)
    (hnormalization :
      NormalizationContains (logLength := logLength) normalizationBox) :
    (directedBluesteinLineValue rounding order logLength
      sourceBoxes inputChirpBoxes kernelBoxes
      negativeTwiddleBoxes positiveTwiddleBoxes
      outputChirpBoxes normalizationBox frequency
      (by omega : order ≤ 2 ^ logLength)).Contains
      (BluesteinDFT.positiveDFT order source frequency) := by
  rw [← cudaBluesteinSourceLineValue_eq_positiveDFT
    horder hfft source frequency]
  exact
    directedBluesteinLineValue_contains_cudaSourceLine rounding
      frequency (by omega) hsource hinputChirps hkernel
      hnegativeTwiddles hpositiveTwiddles houtputChirps
      hnormalization

end SparkInterval.Dirichlet.DirectedIntervalBluestein
