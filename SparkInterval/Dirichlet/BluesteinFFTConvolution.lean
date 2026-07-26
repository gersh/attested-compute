/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinDFT
import SparkInterval.Zeta.WindowedRadix2
import Mathlib.Analysis.Fourier.ZMod

/-!
# Exact FFT convolution for the Bluestein path

This module closes the exact algebraic edge between the padded Bluestein
convolution in `BluesteinDFT` and the already verified radix-2 transform.
The sign convention is explicit:

* both forward transforms are unnormalized positive-sign DFTs;
* the inverse is a negative-sign DFT followed by multiplication by `1 / L`;
* circular convolution uses `(output + L - input) % L`;
* `L = 2 ^ logLength`, so it is always nonzero.

The proof first transports the repository's `Fin L` transform to Mathlib's
Fourier equivalence on `ZMod L`.  This supplies exact normalized inversion.
The positive-sign convolution theorem is proved directly by translating the
inner sum by one group element.  It is then transported back to `Fin L`, with
a separate theorem identifying `Nat` circular indexing with subtraction in
`ZMod L`.

Finally, the abstract transforms are replaced by
`FactoredSmallQDFT.positiveRadix2Transform` and its
conjugate-positive-conjugate negative-sign counterpart.  The first complete
theorem uses the mathematically equivalent convention

```
positive FFTs -> pointwise product -> normalized negative FFT -> post-chirp
```

The last theorem mirrors this result and proves the convention used by the
CUDA source:

```
negative FFTs -> pointwise product -> normalized positive FFT -> post-chirp
```

Both compute the direct arbitrary-length positive DFT whenever
`2 * order - 1 <= 2 ^ logLength`; neither swaps a sign without an explicit
theorem.

This theorem does not claim that transcendental interval tables contain these
exact roots, or that a CUDA trace refines the exact radix-2 state.  Those
remain distinct certificate and binary-refinement edges.
-/

set_option autoImplicit false

open scoped BigOperators

namespace SparkInterval.Dirichlet.BluesteinFFTConvolution

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Zeta.WindowedRadix2

/-! ## `Fin` / `ZMod` and root-convention bridges -/

theorem finEquiv_val {n : Nat} [NeZero n] (index : Fin n) :
    (ZMod.finEquiv n index).val = index.val := by
  cases n with
  | zero => exact (NeZero.ne 0 rfl).elim
  | succ n => rfl

theorem finEquiv_eq_natCast {n : Nat} [NeZero n] (index : Fin n) :
    ZMod.finEquiv n index = (index.val : ZMod n) := by
  apply ZMod.val_injective
  rw [finEquiv_val]
  simp [ZMod.val_natCast, Nat.mod_eq_of_lt index.isLt]

/-- The positive root used by the radix-2 implementation is Mathlib's
standard additive character. -/
theorem unitRoot_eq_stdAddChar {n : Nat} [NeZero n] (exponent : Nat) :
    unitRoot n exponent = ZMod.stdAddChar (exponent : ZMod n) := by
  rw [show (exponent : ZMod n) =
    ((exponent : Int) : ZMod n) by norm_num]
  rw [ZMod.stdAddChar_coe]
  simp only [unitRoot]
  congr 1
  push_cast
  field_simp

/-- A radix-2 exact state, reindexed by the additive group `ZMod L`. -/
noncomputable def toZModState {logLength : Nat}
    (source : ExactState logLength) : ZMod (2 ^ logLength) → ℂ :=
  fun index =>
    source.value ((ZMod.finEquiv (2 ^ logLength)).symm index)

/-- Unnormalized positive-sign DFT on `ZMod n`. -/
noncomputable def zPositive {n : Nat} [NeZero n]
    (source : ZMod n → ℂ) (frequency : ZMod n) : ℂ :=
  ∑ input : ZMod n,
    ZMod.stdAddChar (input * frequency) * source input

theorem positiveDFT_eq_zPositive {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT source frequency =
      zPositive (toZModState source)
        (ZMod.finEquiv (2 ^ logLength) frequency) := by
  unfold positiveDFT zPositive toZModState
  rw [Fintype.sum_equiv
    (ZMod.finEquiv (2 ^ logLength)).toEquiv _ _]
  intro input
  rw [unitRoot_eq_stdAddChar]
  have hcharacter :
      ZMod.stdAddChar
          ((input.val * frequency.val : Nat) :
            ZMod (2 ^ logLength)) =
        ZMod.stdAddChar
          (ZMod.finEquiv (2 ^ logLength) input *
            ZMod.finEquiv (2 ^ logLength) frequency) := by
    congr 1
    rw [Nat.cast_mul, ← finEquiv_eq_natCast input,
      ← finEquiv_eq_natCast frequency]
  rw [hcharacter]
  simp
  ring

theorem conj_unitRoot_eq_stdAddChar_neg {n : Nat} [NeZero n]
    (exponent : Nat) :
    starRingEnd ℂ (unitRoot n exponent) =
      ZMod.stdAddChar (-(exponent : ZMod n)) := by
  rw [unitRoot_eq_stdAddChar]
  rw [AddChar.map_neg_eq_inv]
  rw [ZMod.stdAddChar_apply]
  exact
    (Circle.coe_inv_eq_conj
      (ZMod.toCircle (exponent : ZMod n))).symm

/-- The direct negative-sign DFT used by the windowed code is Mathlib's
`ZMod.dft`, after reindexing by `finEquiv`. -/
theorem negativeDFT_eq_dft {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    negativeDFT source frequency =
      ZMod.dft (toZModState source)
        (ZMod.finEquiv (2 ^ logLength) frequency) := by
  unfold negativeDFT toZModState
  rw [ZMod.dft_apply]
  simp only [smul_eq_mul]
  rw [Fintype.sum_equiv
    (ZMod.finEquiv (2 ^ logLength)).toEquiv _ _]
  intro input
  rw [conj_unitRoot_eq_stdAddChar_neg]
  have hcharacter :
      ZMod.stdAddChar
          (-((input.val * frequency.val : Nat) :
            ZMod (2 ^ logLength))) =
        ZMod.stdAddChar
          (-(ZMod.finEquiv (2 ^ logLength) input *
            ZMod.finEquiv (2 ^ logLength) frequency)) := by
    congr 1
    rw [Nat.cast_mul, ← finEquiv_eq_natCast input,
      ← finEquiv_eq_natCast frequency]
  rw [hcharacter]
  simp
  ring

/-! ## Exact inversion and convolution on `ZMod` -/

/-- The unnormalized positive transform is `n` times Mathlib's inverse
negative transform. -/
theorem zPositive_eq_scale_invDFT {n : Nat} [NeZero n]
    (source : ZMod n → ℂ) :
    zPositive source = (n : ℂ) • ZMod.dft.symm source := by
  funext frequency
  rw [Pi.smul_apply, ZMod.invDFT_apply]
  simp only [smul_eq_mul, zPositive]
  have hn : (n : ℂ) ≠ 0 := by
    exact_mod_cast (NeZero.ne n)
  field_simp

/-- Normalized negative-sign inversion of the positive-sign DFT. -/
theorem normalized_dft_zPositive {n : Nat} [NeZero n]
    (source : ZMod n → ℂ) (output : ZMod n) :
    (n : ℂ)⁻¹ * ZMod.dft (zPositive source) output =
      source output := by
  rw [zPositive_eq_scale_invDFT]
  rw [map_smul]
  simp only [Pi.smul_apply, LinearEquiv.apply_symm_apply, smul_eq_mul]
  have hn : (n : ℂ) ≠ 0 := by
    exact_mod_cast (NeZero.ne n)
  field_simp

/-- Literal cyclic convolution on the finite additive group. -/
noncomputable def zCyclicConvolution {n : Nat} [NeZero n]
    (left right : ZMod n → ℂ) (output : ZMod n) : ℂ :=
  ∑ input : ZMod n, left input * right (output - input)

/-- A positive-sign DFT takes cyclic convolution to pointwise
multiplication. -/
theorem zPositive_cyclicConvolution {n : Nat} [NeZero n]
    (left right : ZMod n → ℂ) (frequency : ZMod n) :
    zPositive (zCyclicConvolution left right) frequency =
      zPositive left frequency * zPositive right frequency := by
  unfold zPositive zCyclicConvolution
  have hleft :
      (∑ output : ZMod n,
        ZMod.stdAddChar (output * frequency) *
          ∑ input : ZMod n, left input * right (output - input)) =
      ∑ output : ZMod n, ∑ input : ZMod n,
        ZMod.stdAddChar (output * frequency) *
          (left input * right (output - input)) := by
    apply Finset.sum_congr rfl
    intro output _
    rw [Finset.mul_sum]
  rw [hleft]
  rw [Finset.sum_comm]
  rw [Finset.sum_mul]
  apply Finset.sum_congr rfl
  intro input _
  rw [Finset.mul_sum]
  rw [← Fintype.sum_equiv (Equiv.addRight input)
    (fun delta : ZMod n =>
      ZMod.stdAddChar ((delta + input) * frequency) *
        (left input * right ((delta + input) - input)))
    (fun output : ZMod n =>
      ZMod.stdAddChar (output * frequency) *
        (left input * right (output - input))) (fun _ => rfl)]
  simp only [add_sub_cancel_right]
  simp_rw [add_mul, AddChar.map_add_eq_mul]
  apply Finset.sum_congr rfl
  intro delta _
  rw [mul_comm delta frequency, mul_comm input frequency]
  ring

noncomputable def zPointwiseProduct {n : Nat}
    (left right : ZMod n → ℂ) : ZMod n → ℂ :=
  fun frequency => left frequency * right frequency

/-- The full transform-domain convolution identity on `ZMod`: two positive
DFTs, pointwise multiplication, then a normalized negative DFT. -/
theorem normalized_dft_pointwise_positive {n : Nat} [NeZero n]
    (left right : ZMod n → ℂ) (output : ZMod n) :
    (n : ℂ)⁻¹ *
        ZMod.dft
          (zPointwiseProduct (zPositive left) (zPositive right))
          output =
      zCyclicConvolution left right output := by
  have hproduct :
      zPointwiseProduct (zPositive left) (zPositive right) =
        zPositive (zCyclicConvolution left right) := by
    funext frequency
    exact
      (zPositive_cyclicConvolution left right frequency).symm
  rw [hproduct]
  exact
    normalized_dft_zPositive (zCyclicConvolution left right) output

/-! ## Power-of-two states and explicit circular indexing -/

noncomputable def positiveTransform {logLength : Nat}
    (source : ExactState logLength) : ExactState logLength :=
  ⟨positiveDFT source⟩

noncomputable def normalizedNegativeDFT {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) : ℂ :=
  ((2 ^ logLength : Nat) : ℂ)⁻¹ * negativeDFT source frequency

theorem toZModState_positiveTransform {logLength : Nat}
    (source : ExactState logLength) :
    toZModState (positiveTransform source) =
      zPositive (toZModState source) := by
  funext frequency
  change
    positiveDFT source
        ((ZMod.finEquiv (2 ^ logLength)).symm frequency) =
      zPositive (toZModState source) frequency
  rw [positiveDFT_eq_zPositive]
  simp

/-- Normalized negative inversion, in the exact `Fin (2^m)` representation
used by the radix-2 implementation. -/
theorem normalizedNegativeDFT_positiveTransform {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    normalizedNegativeDFT (positiveTransform source) frequency =
      source.value frequency := by
  unfold normalizedNegativeDFT
  rw [negativeDFT_eq_dft, toZModState_positiveTransform]
  rw [normalized_dft_zPositive]
  unfold toZModState
  simp

/-- `Fin` circular indexing represents subtraction in `ZMod`; the proof
retains the `Nat` subtraction guard explicitly. -/
theorem finEquiv_finIndex_circularIndex {logLength : Nat}
    (frequency input : Fin (2 ^ logLength)) :
    ZMod.finEquiv (2 ^ logLength)
        (finIndex logLength
          (BluesteinDFT.circularIndex (2 ^ logLength)
            frequency.val input.val)) =
      ZMod.finEquiv (2 ^ logLength) frequency -
        ZMod.finEquiv (2 ^ logLength) input := by
  rw [finEquiv_eq_natCast, finEquiv_eq_natCast,
    finEquiv_eq_natCast]
  simp only [finIndex]
  rw [BluesteinDFT.circularIndex]
  have hinput :
      input.val ≤ frequency.val + 2 ^ logLength := by
    have := input.isLt
    omega
  rw [ZMod.natCast_mod, ZMod.natCast_mod, Nat.cast_sub hinput]
  have hlength :
      ((2 ^ logLength : Nat) : ZMod (2 ^ logLength)) = 0 :=
    ZMod.natCast_self (2 ^ logLength)
  push_cast
  have hpow :
      (2 : ZMod (2 ^ logLength)) ^ logLength = 0 := by
    simpa only [Nat.cast_pow, Nat.cast_ofNat] using hlength
  rw [hpow]
  simp

theorem finIndex_circularIndex_eq_finEquiv_symm_sub
    {logLength : Nat}
    (frequency input : Fin (2 ^ logLength)) :
    finIndex logLength
        (BluesteinDFT.circularIndex (2 ^ logLength)
          frequency.val input.val) =
      (ZMod.finEquiv (2 ^ logLength)).symm
        (ZMod.finEquiv (2 ^ logLength) frequency -
          ZMod.finEquiv (2 ^ logLength) input) := by
  apply (ZMod.finEquiv (2 ^ logLength)).injective
  rw [finEquiv_finIndex_circularIndex]
  simp

/-- Literal power-of-two cyclic convolution in the exact radix-2 state
representation. -/
noncomputable def cyclicConvolution {logLength : Nat}
    (left right : ExactState logLength) : ExactState logLength :=
  ⟨fun output =>
    ∑ input : Fin (2 ^ logLength),
      left.value input *
        right.value
          (finIndex logLength
            (BluesteinDFT.circularIndex (2 ^ logLength)
              output.val input.val))⟩

theorem toZModState_cyclicConvolution {logLength : Nat}
    (left right : ExactState logLength) :
    toZModState (cyclicConvolution left right) =
      zCyclicConvolution (toZModState left) (toZModState right) := by
  funext output
  change
    (∑ input : Fin (2 ^ logLength),
      left.value input *
        right.value
          (finIndex logLength
            (BluesteinDFT.circularIndex (2 ^ logLength)
              ((ZMod.finEquiv
                (2 ^ logLength)).symm output).val input.val))) = _
  unfold zCyclicConvolution
  rw [Fintype.sum_equiv
    (ZMod.finEquiv (2 ^ logLength)).toEquiv _ _]
  intro input
  unfold toZModState
  rw [finIndex_circularIndex_eq_finEquiv_symm_sub]
  simp

/-- Positive-DFT convolution theorem in the repository's exact power-of-two
state representation. -/
theorem positiveDFT_cyclicConvolution {logLength : Nat}
    (left right : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (cyclicConvolution left right) frequency =
      positiveDFT left frequency * positiveDFT right frequency := by
  rw [positiveDFT_eq_zPositive, toZModState_cyclicConvolution,
    zPositive_cyclicConvolution]
  rw [positiveDFT_eq_zPositive, positiveDFT_eq_zPositive]

noncomputable def pointwiseProduct {logLength : Nat}
    (left right : ExactState logLength) : ExactState logLength :=
  ⟨fun frequency => left.value frequency * right.value frequency⟩

theorem pointwise_positiveTransform_eq_positive_cyclicConvolution
    {logLength : Nat} (left right : ExactState logLength) :
    pointwiseProduct (positiveTransform left) (positiveTransform right) =
      positiveTransform (cyclicConvolution left right) := by
  apply congrArg ExactState.mk
  funext frequency
  exact (positiveDFT_cyclicConvolution left right frequency).symm

theorem normalizedNegativeDFT_pointwise_positive
    {logLength : Nat} (left right : ExactState logLength)
    (output : Fin (2 ^ logLength)) :
    normalizedNegativeDFT
        (pointwiseProduct
          (positiveTransform left) (positiveTransform right))
        output =
      (cyclicConvolution left right).value output := by
  rw [pointwise_positiveTransform_eq_positive_cyclicConvolution]
  exact
    normalizedNegativeDFT_positiveTransform
      (cyclicConvolution left right) output

/-! ## Replacement by the proved radix-2 network -/

theorem positiveRadix2Transform_eq_positiveTransform
    {logLength : Nat} (source : ExactState logLength) :
    positiveRadix2Transform source = positiveTransform source := by
  apply congrArg ExactState.mk
  funext frequency
  exact
    SparkInterval.Dirichlet.FactoredSmallQDFT.radix2CorrectFor
      source frequency

/-- Source-level negative-sign FFT: conjugate the input, run the proved
positive radix-2 transform, and conjugate the output. -/
noncomputable def negativeRadix2Transform {logLength : Nat}
    (source : ExactState logLength) : ExactState logLength :=
  conjugateExactState
    (positiveRadix2Transform (conjugateExactState source))

theorem negativeRadix2Transform_eq_negativeDFT {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    (negativeRadix2Transform source).value frequency =
      negativeDFT source frequency := by
  unfold negativeRadix2Transform conjugateExactState
  change
    starRingEnd ℂ
        ((positiveRadix2Transform
          (conjugateExactState source)).value frequency) = _
  rw [SparkInterval.Dirichlet.FactoredSmallQDFT.radix2CorrectFor]
  exact
    (negativeDFT_eq_conjugate_positiveDFT source frequency).symm

/-- Normalized source-level inverse radix-2 transform. -/
noncomputable def normalizedNegativeRadix2 {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) : ℂ :=
  ((2 ^ logLength : Nat) : ℂ)⁻¹ *
    (negativeRadix2Transform source).value frequency

theorem normalizedNegativeRadix2_eq_normalizedNegativeDFT
    {logLength : Nat} (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    normalizedNegativeRadix2 source frequency =
      normalizedNegativeDFT source frequency := by
  unfold normalizedNegativeRadix2 normalizedNegativeDFT
  rw [negativeRadix2Transform_eq_negativeDFT]

/-- The proved positive radix-2 network followed by the normalized proved
negative network is exactly the identity. -/
theorem normalizedNegativeRadix2_positiveRadix2
    {logLength : Nat} (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    normalizedNegativeRadix2
        (positiveRadix2Transform source) frequency =
      source.value frequency := by
  rw [positiveRadix2Transform_eq_positiveTransform,
    normalizedNegativeRadix2_eq_normalizedNegativeDFT]
  exact normalizedNegativeDFT_positiveTransform source frequency

/-- Exact forward-radix-2, pointwise-product, inverse-radix-2 convolution
theorem. -/
theorem normalizedNegativeRadix2_pointwise_positiveRadix2
    {logLength : Nat} (left right : ExactState logLength)
    (output : Fin (2 ^ logLength)) :
    normalizedNegativeRadix2
        (pointwiseProduct
          (positiveRadix2Transform left)
          (positiveRadix2Transform right))
        output =
      (cyclicConvolution left right).value output := by
  rw [positiveRadix2Transform_eq_positiveTransform,
    positiveRadix2Transform_eq_positiveTransform,
    normalizedNegativeRadix2_eq_normalizedNegativeDFT]
  exact normalizedNegativeDFT_pointwise_positive left right output

/-! ## The complete exact Bluestein transform shape -/

noncomputable def paddedInputState (order logLength : Nat)
    (source : Fin order → ℂ) : ExactState logLength :=
  ⟨fun input =>
    BluesteinDFT.paddedChirpedInput
      order (2 ^ logLength) source input⟩

noncomputable def paddedKernelState
    (order logLength : Nat) : ExactState logLength :=
  ⟨fun input =>
    BluesteinDFT.wrappedKernel order (2 ^ logLength) input.val⟩

def paddedFrequency {order logLength : Nat}
    (hle : order ≤ 2 ^ logLength) (frequency : Fin order) :
    Fin (2 ^ logLength) :=
  ⟨frequency.val, lt_of_lt_of_le frequency.isLt hle⟩

@[simp] theorem paddedFrequency_val {order logLength : Nat}
    (hle : order ≤ 2 ^ logLength) (frequency : Fin order) :
    (paddedFrequency hle frequency).val = frequency.val :=
  rfl

theorem finIndex_circularIndex_val
    {logLength frequency input : Nat} :
    (finIndex logLength
      (BluesteinDFT.circularIndex
        (2 ^ logLength) frequency input)).val =
      BluesteinDFT.circularIndex
        (2 ^ logLength) frequency input := by
  simp only [finIndex]
  have hlength : 0 < 2 ^ logLength :=
    Nat.pow_pos (by omega)
  have hcircular :
      BluesteinDFT.circularIndex
          (2 ^ logLength) frequency input <
        2 ^ logLength :=
    Nat.mod_lt _ hlength
  exact Nat.mod_eq_of_lt hcircular

theorem cyclicConvolution_padded_states {order logLength : Nat}
    (hle : order ≤ 2 ^ logLength) (source : Fin order → ℂ)
    (frequency : Fin order) :
    (cyclicConvolution
      (paddedInputState order logLength source)
      (paddedKernelState order logLength)).value
        (paddedFrequency hle frequency) =
      BluesteinDFT.paddedCyclicConvolutionValue
        order (2 ^ logLength) source frequency := by
  unfold cyclicConvolution paddedInputState paddedKernelState
  change
    (∑ input : Fin (2 ^ logLength),
      BluesteinDFT.paddedChirpedInput
          order (2 ^ logLength) source input *
        BluesteinDFT.wrappedKernel order (2 ^ logLength)
          (finIndex logLength
            (BluesteinDFT.circularIndex
              (2 ^ logLength) frequency.val input.val)).val) = _
  unfold BluesteinDFT.paddedCyclicConvolutionValue
  apply Finset.sum_congr rfl
  intro input _
  rw [finIndex_circularIndex_val]

/-- The exact radix-2 FFT shape computes the literal padded cyclic
convolution used by `BluesteinDFT`. -/
theorem fft_pointwise_ifft_eq_paddedCyclicConvolutionValue
    {order logLength : Nat} (hle : order ≤ 2 ^ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    normalizedNegativeRadix2
        (pointwiseProduct
          (positiveRadix2Transform
            (paddedInputState order logLength source))
          (positiveRadix2Transform
            (paddedKernelState order logLength)))
        (paddedFrequency hle frequency) =
      BluesteinDFT.paddedCyclicConvolutionValue
        order (2 ^ logLength) source frequency := by
  rw [normalizedNegativeRadix2_pointwise_positiveRadix2]
  exact cyclicConvolution_padded_states hle source frequency

/-- Complete exact arbitrary-length Bluestein theorem: forward FFTs,
pointwise product, normalized inverse FFT, and post-chirp equal the direct
positive-sign DFT. -/
theorem fft_pointwise_ifft_bluestein_eq_positiveDFT
    {order logLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    BluesteinDFT.halfRoot order ((frequency.val : Int) ^ 2) *
        normalizedNegativeRadix2
          (pointwiseProduct
            (positiveRadix2Transform
              (paddedInputState order logLength source))
            (positiveRadix2Transform
              (paddedKernelState order logLength)))
          (paddedFrequency
            (by omega : order ≤ 2 ^ logLength) frequency) =
      BluesteinDFT.positiveDFT order source frequency := by
  rw [fft_pointwise_ifft_eq_paddedCyclicConvolutionValue]
  change
    BluesteinDFT.paddedBluesteinValue
      order (2 ^ logLength) source frequency = _
  exact
    BluesteinDFT.paddedBluesteinValue_eq_positiveDFT
      horder hfft source frequency

/-! ## CUDA's mirrored forward/inverse sign convention

The optimized all-character CUDA source calls its negative-root transform
the forward FFT and its positive-root transform the inverse FFT.  The next
theorems mirror the preceding development so the final statement follows
that implementation convention exactly.
-/

/-- Mathlib's negative DFT is the positive transform evaluated at the
negated frequency. -/
theorem dft_eq_zPositive_neg {n : Nat} [NeZero n]
    (source : ZMod n → ℂ) (frequency : ZMod n) :
    ZMod.dft source frequency = zPositive source (-frequency) := by
  rw [ZMod.dft_apply]
  unfold zPositive
  simp only [smul_eq_mul]
  apply Finset.sum_congr rfl
  intro input _
  congr 2
  ring

/-- Negative-sign DFT convolution theorem. -/
theorem dft_cyclicConvolution {n : Nat} [NeZero n]
    (left right : ZMod n → ℂ) (frequency : ZMod n) :
    ZMod.dft (zCyclicConvolution left right) frequency =
      ZMod.dft left frequency * ZMod.dft right frequency := by
  rw [dft_eq_zPositive_neg, zPositive_cyclicConvolution]
  rw [← dft_eq_zPositive_neg, ← dft_eq_zPositive_neg]

/-- Normalized positive-sign inversion of Mathlib's negative DFT. -/
theorem normalized_zPositive_dft {n : Nat} [NeZero n]
    (source : ZMod n → ℂ) (output : ZMod n) :
    (n : ℂ)⁻¹ * zPositive (ZMod.dft source) output =
      source output := by
  calc
    (n : ℂ)⁻¹ * zPositive (ZMod.dft source) output =
        ZMod.dft.symm (ZMod.dft source) output := by
      rw [ZMod.invDFT_apply]
      simp only [zPositive, smul_eq_mul]
    _ = source output := by simp

theorem normalized_zPositive_pointwise_dft
    {n : Nat} [NeZero n] (left right : ZMod n → ℂ)
    (output : ZMod n) :
    (n : ℂ)⁻¹ *
        zPositive
          (zPointwiseProduct
            (ZMod.dft left) (ZMod.dft right))
          output =
      zCyclicConvolution left right output := by
  have hproduct :
      zPointwiseProduct (ZMod.dft left) (ZMod.dft right) =
        ZMod.dft (zCyclicConvolution left right) := by
    funext frequency
    exact (dft_cyclicConvolution left right frequency).symm
  rw [hproduct]
  exact
    normalized_zPositive_dft
      (zCyclicConvolution left right) output

noncomputable def negativeTransform {logLength : Nat}
    (source : ExactState logLength) : ExactState logLength :=
  ⟨negativeDFT source⟩

noncomputable def normalizedPositiveDFT {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) : ℂ :=
  ((2 ^ logLength : Nat) : ℂ)⁻¹ * positiveDFT source frequency

theorem toZModState_negativeTransform {logLength : Nat}
    (source : ExactState logLength) :
    toZModState (negativeTransform source) =
      ZMod.dft (toZModState source) := by
  funext frequency
  change
    negativeDFT source
        ((ZMod.finEquiv (2 ^ logLength)).symm frequency) =
      ZMod.dft (toZModState source) frequency
  rw [negativeDFT_eq_dft]
  simp

/-- Normalized positive inversion in the exact `Fin (2^m)`
representation. -/
theorem normalizedPositiveDFT_negativeTransform {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    normalizedPositiveDFT (negativeTransform source) frequency =
      source.value frequency := by
  unfold normalizedPositiveDFT
  rw [positiveDFT_eq_zPositive, toZModState_negativeTransform]
  rw [normalized_zPositive_dft]
  unfold toZModState
  simp

theorem negativeDFT_cyclicConvolution {logLength : Nat}
    (left right : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    negativeDFT (cyclicConvolution left right) frequency =
      negativeDFT left frequency * negativeDFT right frequency := by
  rw [negativeDFT_eq_dft, toZModState_cyclicConvolution,
    dft_cyclicConvolution]
  rw [negativeDFT_eq_dft, negativeDFT_eq_dft]

theorem pointwise_negativeTransform_eq_negative_cyclicConvolution
    {logLength : Nat} (left right : ExactState logLength) :
    pointwiseProduct (negativeTransform left) (negativeTransform right) =
      negativeTransform (cyclicConvolution left right) := by
  apply congrArg ExactState.mk
  funext frequency
  exact (negativeDFT_cyclicConvolution left right frequency).symm

theorem normalizedPositiveDFT_pointwise_negative
    {logLength : Nat} (left right : ExactState logLength)
    (output : Fin (2 ^ logLength)) :
    normalizedPositiveDFT
        (pointwiseProduct
          (negativeTransform left) (negativeTransform right))
        output =
      (cyclicConvolution left right).value output := by
  rw [pointwise_negativeTransform_eq_negative_cyclicConvolution]
  exact
    normalizedPositiveDFT_negativeTransform
      (cyclicConvolution left right) output

theorem negativeRadix2Transform_eq_negativeTransform
    {logLength : Nat} (source : ExactState logLength) :
    negativeRadix2Transform source = negativeTransform source := by
  apply congrArg ExactState.mk
  funext frequency
  exact negativeRadix2Transform_eq_negativeDFT source frequency

/-- Positive-root radix-2 network followed by the CUDA inverse normalization. -/
noncomputable def normalizedPositiveRadix2 {logLength : Nat}
    (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) : ℂ :=
  ((2 ^ logLength : Nat) : ℂ)⁻¹ *
    (positiveRadix2Transform source).value frequency

theorem normalizedPositiveRadix2_eq_normalizedPositiveDFT
    {logLength : Nat} (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    normalizedPositiveRadix2 source frequency =
      normalizedPositiveDFT source frequency := by
  unfold normalizedPositiveRadix2 normalizedPositiveDFT
  rw [SparkInterval.Dirichlet.FactoredSmallQDFT.radix2CorrectFor]

/-- Exact inversion in the sign convention used by the CUDA source. -/
theorem normalizedPositiveRadix2_negativeRadix2
    {logLength : Nat} (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    normalizedPositiveRadix2
        (negativeRadix2Transform source) frequency =
      source.value frequency := by
  rw [negativeRadix2Transform_eq_negativeTransform,
    normalizedPositiveRadix2_eq_normalizedPositiveDFT]
  exact normalizedPositiveDFT_negativeTransform source frequency

/-- Exact FFT convolution in the CUDA source's sign convention. -/
theorem normalizedPositiveRadix2_pointwise_negativeRadix2
    {logLength : Nat} (left right : ExactState logLength)
    (output : Fin (2 ^ logLength)) :
    normalizedPositiveRadix2
        (pointwiseProduct
          (negativeRadix2Transform left)
          (negativeRadix2Transform right))
        output =
      (cyclicConvolution left right).value output := by
  rw [negativeRadix2Transform_eq_negativeTransform,
    negativeRadix2Transform_eq_negativeTransform,
    normalizedPositiveRadix2_eq_normalizedPositiveDFT]
  exact normalizedPositiveDFT_pointwise_negative left right output

/-- Every circular kernel index used by a low Bluestein output lies in one
of the two populated kernel wings. -/
theorem circularIndex_mem_kernel_wings
    {order fftLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ fftLength)
    (frequency input : Fin order) :
    BluesteinDFT.circularIndex
          fftLength frequency.val input.val < order ∨
      fftLength -
          BluesteinDFT.circularIndex
            fftLength frequency.val input.val < order := by
  have hfftpos : 0 < fftLength := by omega
  by_cases hle : input.val ≤ frequency.val
  · left
    have hsum :
        frequency.val + fftLength - input.val =
          fftLength + (frequency.val - input.val) := by
      omega
    have hdiffOrder :
        frequency.val - input.val < order := by
      omega
    have hdiffFft :
        frequency.val - input.val < fftLength := by
      omega
    calc
      BluesteinDFT.circularIndex
          fftLength frequency.val input.val =
          (frequency.val - input.val) % fftLength := by
        simp [BluesteinDFT.circularIndex, hsum]
      _ = frequency.val - input.val :=
        Nat.mod_eq_of_lt hdiffFft
      _ < order := hdiffOrder
  · right
    have hlt : frequency.val < input.val := by omega
    have hdiffOrder :
        input.val - frequency.val < order := by
      omega
    have hdiffFft :
        input.val - frequency.val < fftLength := by
      omega
    have hsum :
        frequency.val + fftLength - input.val =
          fftLength - (input.val - frequency.val) := by
      omega
    have hwrappedFft :
        fftLength - (input.val - frequency.val) < fftLength := by
      omega
    have hcircular :
        BluesteinDFT.circularIndex
            fftLength frequency.val input.val =
          fftLength - (input.val - frequency.val) := by
      simp [BluesteinDFT.circularIndex, hsum,
        Nat.mod_eq_of_lt hwrappedFft]
    rw [hcircular]
    omega

/-- The CUDA host's kernel allocation: the low and high chirp wings are
populated and the unused middle is literal zero. -/
noncomputable def zeroPaddedKernelState
    (order logLength : Nat) : ExactState logLength :=
  ⟨fun index =>
    if index.val < order ∨
        2 ^ logLength - index.val < order then
      BluesteinDFT.wrappedKernel
        order (2 ^ logLength) index.val
    else
      0⟩

theorem zeroPaddedKernelState_circularIndex
    {order logLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (frequency input : Fin order) :
    (zeroPaddedKernelState order logLength).value
        (finIndex logLength
          (BluesteinDFT.circularIndex
            (2 ^ logLength) frequency.val input.val)) =
      BluesteinDFT.wrappedKernel order (2 ^ logLength)
        (BluesteinDFT.circularIndex
          (2 ^ logLength) frequency.val input.val) := by
  unfold zeroPaddedKernelState
  change
    (if
        (finIndex logLength
          (BluesteinDFT.circularIndex
            (2 ^ logLength) frequency.val input.val)).val < order ∨
        2 ^ logLength -
          (finIndex logLength
            (BluesteinDFT.circularIndex
              (2 ^ logLength) frequency.val input.val)).val < order
      then
        BluesteinDFT.wrappedKernel order (2 ^ logLength)
          (finIndex logLength
            (BluesteinDFT.circularIndex
              (2 ^ logLength) frequency.val input.val)).val
      else 0) = _
  rw [show
    (finIndex logLength
      (BluesteinDFT.circularIndex
        (2 ^ logLength) frequency.val input.val)).val =
      BluesteinDFT.circularIndex
        (2 ^ logLength) frequency.val input.val by
    exact finIndex_circularIndex_val]
  simp [circularIndex_mem_kernel_wings
    horder hfft frequency input]

/-- Replacing the arbitrary unused middle of `wrappedKernel` by the CUDA
host's literal-zero middle leaves every requested low output unchanged. -/
theorem cyclicConvolution_zeroPaddedKernel
    {order logLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    (cyclicConvolution
      (paddedInputState order logLength source)
      (zeroPaddedKernelState order logLength)).value
        (paddedFrequency
          (by omega : order ≤ 2 ^ logLength) frequency) =
      BluesteinDFT.paddedCyclicConvolutionValue
        order (2 ^ logLength) source frequency := by
  unfold cyclicConvolution paddedInputState
  change
    (∑ input : Fin (2 ^ logLength),
      BluesteinDFT.paddedChirpedInput
          order (2 ^ logLength) source input *
        (zeroPaddedKernelState order logLength).value
          (finIndex logLength
            (BluesteinDFT.circularIndex
              (2 ^ logLength) frequency.val input.val))) = _
  unfold BluesteinDFT.paddedCyclicConvolutionValue
  apply Finset.sum_congr rfl
  intro input _
  by_cases hinput : input.val < order
  · rw [zeroPaddedKernelState_circularIndex horder hfft
      ⟨frequency.val, frequency.isLt⟩
      ⟨input.val, hinput⟩]
  · simp [BluesteinDFT.paddedChirpedInput, hinput]

/-- The CUDA-sign FFT shape computes the literal padded cyclic convolution. -/
theorem cuda_fft_pointwise_ifft_eq_paddedCyclicConvolutionValue
    {order logLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    normalizedPositiveRadix2
        (pointwiseProduct
          (negativeRadix2Transform
            (paddedInputState order logLength source))
          (negativeRadix2Transform
            (zeroPaddedKernelState order logLength)))
        (paddedFrequency
          (by omega : order ≤ 2 ^ logLength) frequency) =
      BluesteinDFT.paddedCyclicConvolutionValue
        order (2 ^ logLength) source frequency := by
  rw [normalizedPositiveRadix2_pointwise_negativeRadix2]
  exact
    cyclicConvolution_zeroPaddedKernel
      horder hfft source frequency

/-- Complete exact Bluestein theorem in the CUDA source's actual sign and
normalization convention. -/
theorem cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT
    {order logLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    BluesteinDFT.halfRoot order ((frequency.val : Int) ^ 2) *
        normalizedPositiveRadix2
          (pointwiseProduct
            (negativeRadix2Transform
              (paddedInputState order logLength source))
            (negativeRadix2Transform
              (zeroPaddedKernelState order logLength)))
          (paddedFrequency
            (by omega : order ≤ 2 ^ logLength) frequency) =
      BluesteinDFT.positiveDFT order source frequency := by
  rw [cuda_fft_pointwise_ifft_eq_paddedCyclicConvolutionValue
    horder hfft]
  change
    BluesteinDFT.paddedBluesteinValue
      order (2 ^ logLength) source frequency = _
  exact
    BluesteinDFT.paddedBluesteinValue_eq_positiveDFT
      horder hfft source frequency

end SparkInterval.Dirichlet.BluesteinFFTConvolution
