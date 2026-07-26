/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFT

/-!
# Exact Bluestein identity for the all-character transform

The large-conductor Dirichlet pipeline evaluates arbitrary cyclic component
lengths by Bluestein convolution.  This module proves the exact algebraic
identity used by that optimization:

```
exp(2 π i n k / N)
  = exp(π i n² / N)
  * exp(π i k² / N)
  * exp(-π i (n-k)² / N).
```

It then proves that the corresponding chirp/convolution formula equals the
direct positive-sign DFT for every nonzero transform length.  Integer
exponents are used so the negative centered-convolution index is explicit;
there is no hidden natural-number truncation at `n-k`.

The final theorem also identifies this arbitrary-length DFT with the existing
power-of-two direct DFT used by the verified radix-2 certificate layer.

The padding theorem checks the exact `2N-1` no-alias guard, both wrapped
kernel wings, and every zero-padded tail contribution. The companion
`BluesteinFFTConvolution` module proves that the exact staged radix-2 network,
including the signs and literal-zero kernel middle used by CUDA, evaluates
this convolution. Directed interval enclosure of the transcendental tables
and fused operations, CUDA-source refinement, compilation, and physical
execution remain explicit, separate verification edges.
-/

set_option autoImplicit false

open scoped BigOperators

namespace SparkInterval.Dirichlet.BluesteinDFT

/-- Positive-sign complex root with an integer exponent. -/
noncomputable def signedUnitRoot (order : Nat) (exponent : Int) : ℂ :=
  Complex.exp
    ((((2 * Real.pi * (exponent : ℝ)) /
      (order : ℝ) : ℝ) : ℂ) * Complex.I)

/-- Half-angle chirp root.  Squared integer indices are supplied by
`chirpedInput` and `centeredKernel`. -/
noncomputable def halfRoot (order : Nat) (exponent : Int) : ℂ :=
  Complex.exp
    ((((Real.pi * (exponent : ℝ)) /
      (order : ℝ) : ℝ) : ℂ) * Complex.I)

/-- The pointwise Bluestein phase identity.  The nonzero-order guard is kept
explicit even though Lean's total division would also assign a value at
`order = 0`; every live DFT has a positive length. -/
theorem bluestein_kernel_identity
    {order : Nat} (horder : 0 < order) (input frequency : Int) :
    halfRoot order (input ^ 2) *
        halfRoot order (frequency ^ 2) *
        halfRoot order (-((input - frequency) ^ 2)) =
      signedUnitRoot order (input * frequency) := by
  have horder0 : (order : ℝ) ≠ 0 := by
    exact_mod_cast (Nat.ne_of_gt horder)
  rw [halfRoot, halfRoot, halfRoot, signedUnitRoot,
    ← Complex.exp_add, ← Complex.exp_add]
  congr 1
  push_cast
  field_simp [horder0]
  ring

/-- Direct arbitrary-length positive-sign DFT, without normalization. -/
noncomputable def positiveDFT
    (order : Nat) (source : Fin order → ℂ) (frequency : Fin order) : ℂ :=
  ∑ input : Fin order,
    source input *
      signedUnitRoot order ((input.val : Int) * (frequency.val : Int))

/-- A single nonzero entry at `index`.  This is the exact sparse input used
by the maximum-order CUDA basis-vector qualification. -/
def basisVector
    {order : Nat} (index : Fin order) (input : Fin order) : ℂ :=
  if input = index then 1 else 0

/-- The positive DFT of a basis vector is the corresponding row of unit
roots.  In particular, an input supported at index one has output
`exp(2 * pi * i * k / order)` at frequency `k`. -/
theorem positiveDFT_basisVector
    {order : Nat} (index frequency : Fin order) :
    positiveDFT order (basisVector index) frequency =
      signedUnitRoot order
        ((index.val : Int) * (frequency.val : Int)) := by
  unfold positiveDFT basisVector
  rw [Finset.sum_eq_single index]
  · simp
  · intro input _ hne
    simp [hne]
  · simp

/-- Input multiplied by the positive half-angle chirp. -/
noncomputable def chirpedInput
    (order : Nat) (source : Fin order → ℂ) (input : Fin order) : ℂ :=
  source input * halfRoot order ((input.val : Int) ^ 2)

/-- Centered negative half-angle chirp used by the convolution. -/
noncomputable def centeredKernel
    (order : Nat) (difference : Int) : ℂ :=
  halfRoot order (-(difference ^ 2))

/-! ## Exact zero-padded circular indexing -/

/-- Circular convolution index `(frequency - input) mod fftLength`. -/
def circularIndex (fftLength frequency input : Nat) : Nat :=
  (frequency + fftLength - input) % fftLength

/-- Interpret the low and high wings of a zero-padded chirp kernel as a
centered integer index. -/
def centeredIndex (order fftLength index : Nat) : Int :=
  if index < order then (index : Int)
  else (index : Int) - (fftLength : Int)

/-- If the convolution length is at least `2 * order - 1`, circular indexing
recovers the exact signed difference and cannot alias the two chirp wings. -/
theorem centeredIndex_circularIndex
    {order fftLength frequency input : Nat}
    (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ fftLength)
    (hfrequency : frequency < order)
    (hinput : input < order) :
    centeredIndex order fftLength
        (circularIndex fftLength frequency input) =
      (frequency : Int) - (input : Int) := by
  have hfftpos : 0 < fftLength := by omega
  by_cases hle : input ≤ frequency
  · have hsum :
        frequency + fftLength - input =
          fftLength + (frequency - input) := by omega
    have hdiffOrder : frequency - input < order := by omega
    have hdiffFft : frequency - input < fftLength := by omega
    have hcircular :
        circularIndex fftLength frequency input =
          frequency - input := by
      calc
        circularIndex fftLength frequency input =
            (frequency - input) % fftLength := by
          simp [circularIndex, hsum]
        _ = frequency - input := Nat.mod_eq_of_lt hdiffFft
    rw [hcircular]
    simp only [centeredIndex, if_pos hdiffOrder]
    rw [Int.ofNat_sub hle]
  · have hlt : frequency < input := by omega
    have hdiffPos : 0 < input - frequency := by omega
    have hdiffOrder : input - frequency < order := by omega
    have hdiffFft : input - frequency < fftLength := by omega
    have hsum :
        frequency + fftLength - input =
          fftLength - (input - frequency) := by omega
    have hwrappedFft :
        fftLength - (input - frequency) < fftLength := by omega
    have hwrappedOrder :
        order ≤ fftLength - (input - frequency) := by omega
    have hcircular :
        circularIndex fftLength frequency input =
          fftLength - (input - frequency) := by
      simp [circularIndex, hsum, Nat.mod_eq_of_lt hwrappedFft]
    rw [hcircular]
    simp only [centeredIndex, if_neg (by omega : ¬
      fftLength - (input - frequency) < order)]
    have hdiffLe : input - frequency ≤ fftLength := by omega
    rw [Int.ofNat_sub hdiffLe, Int.ofNat_sub (Nat.le_of_lt hlt)]
    ring

/-- The two nonzero wings of the padded chirp kernel. -/
noncomputable def wrappedKernel
    (order fftLength index : Nat) : ℂ :=
  centeredKernel order (centeredIndex order fftLength index)

/-- Circular lookup of a padded kernel gives the intended centered chirp. -/
theorem wrappedKernel_circularIndex
    {order fftLength : Nat}
    (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ fftLength)
    (frequency input : Fin order) :
    wrappedKernel order fftLength
        (circularIndex fftLength frequency.val input.val) =
      centeredKernel order
        ((input.val : Int) - (frequency.val : Int)) := by
  rw [wrappedKernel, centeredIndex_circularIndex horder hfft
    frequency.isLt input.isLt]
  unfold centeredKernel
  congr 2
  ring

/-- The exact, unpadded convolution value needed at one DFT frequency. -/
noncomputable def bluesteinConvolutionValue
    (order : Nat) (source : Fin order → ℂ)
    (frequency : Fin order) : ℂ :=
  ∑ input : Fin order,
    chirpedInput order source input *
      centeredKernel order ((input.val : Int) - frequency.val)

/-- The same exact convolution, expressed with the circular indices used by
the padded FFT implementation. -/
noncomputable def wrappedConvolutionValue
    (order fftLength : Nat) (source : Fin order → ℂ)
    (frequency : Fin order) : ℂ :=
  ∑ input : Fin order,
    chirpedInput order source input *
      wrappedKernel order fftLength
        (circularIndex fftLength frequency.val input.val)

theorem wrappedConvolutionValue_eq_bluesteinConvolutionValue
    {order fftLength : Nat}
    (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ fftLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    wrappedConvolutionValue order fftLength source frequency =
      bluesteinConvolutionValue order source frequency := by
  unfold wrappedConvolutionValue bluesteinConvolutionValue
  apply Finset.sum_congr rfl
  intro input _
  rw [wrappedKernel_circularIndex horder hfft frequency input]

/-- Embed the chirped input into a longer FFT vector, filling every trailing
slot with literal zero. -/
noncomputable def paddedChirpedInput
    (order fftLength : Nat) (source : Fin order → ℂ)
    (input : Fin fftLength) : ℂ :=
  if h : input.val < order then
    chirpedInput order source ⟨input.val, h⟩
  else
    0

/-- Literal cyclic convolution of the padded input and wrapped kernel. -/
noncomputable def paddedCyclicConvolutionValue
    (order fftLength : Nat) (source : Fin order → ℂ)
    (frequency : Fin order) : ℂ :=
  ∑ input : Fin fftLength,
    paddedChirpedInput order fftLength source input *
      wrappedKernel order fftLength
        (circularIndex fftLength frequency.val input.val)

/-- The zero tail of the padded input contributes exactly zero. -/
theorem paddedCyclicConvolutionValue_eq_wrappedConvolutionValue
    {order fftLength : Nat}
    (hle : order ≤ fftLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    paddedCyclicConvolutionValue order fftLength source frequency =
      wrappedConvolutionValue order fftLength source frequency := by
  unfold paddedCyclicConvolutionValue wrappedConvolutionValue
  rw [Finset.sum_fin_eq_sum_range, Finset.sum_fin_eq_sum_range]
  rw [← Finset.sum_range_add_sum_Ico _ hle]
  have htail :
      (∑ k ∈ Finset.Ico order fftLength,
        if h : k < fftLength then
          paddedChirpedInput order fftLength source ⟨k, h⟩ *
            wrappedKernel order fftLength
              (circularIndex fftLength frequency.val k)
        else 0) = 0 := by
    apply Finset.sum_eq_zero
    intro input hinput
    have horderInput : order ≤ input := (Finset.mem_Ico.mp hinput).1
    have hinputFft : input < fftLength := (Finset.mem_Ico.mp hinput).2
    simp [hinputFft, paddedChirpedInput, not_lt_of_ge horderInput]
  rw [htail, add_zero]
  apply Finset.sum_congr rfl
  intro input hinput
  have hinputOrder : input < order := Finset.mem_range.mp hinput
  have hinputFft : input < fftLength := lt_of_lt_of_le hinputOrder hle
  simp [hinputOrder, hinputFft, paddedChirpedInput]

/-- A padded cyclic convolution of length at least `2N-1` is exactly the
unpadded Bluestein convolution needed by the DFT. -/
theorem paddedCyclicConvolutionValue_eq_bluesteinConvolutionValue
    {order fftLength : Nat}
    (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ fftLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    paddedCyclicConvolutionValue order fftLength source frequency =
      bluesteinConvolutionValue order source frequency := by
  have hle : order ≤ fftLength := by omega
  rw [paddedCyclicConvolutionValue_eq_wrappedConvolutionValue
    hle source frequency]
  exact wrappedConvolutionValue_eq_bluesteinConvolutionValue
    horder hfft source frequency

/-- Post-chirp applied to one exact convolution value. -/
noncomputable def bluesteinValue
    (order : Nat) (source : Fin order → ℂ)
    (frequency : Fin order) : ℂ :=
  halfRoot order ((frequency.val : Int) ^ 2) *
    bluesteinConvolutionValue order source frequency

/-- Executable-shape specification: post-chirp applied to the literal padded
cyclic convolution. -/
noncomputable def paddedBluesteinValue
    (order fftLength : Nat) (source : Fin order → ℂ)
    (frequency : Fin order) : ℂ :=
  halfRoot order ((frequency.val : Int) ^ 2) *
    paddedCyclicConvolutionValue order fftLength source frequency

/-- Exact arbitrary-length Bluestein evaluation equals the direct
positive-sign DFT. -/
theorem bluesteinValue_eq_positiveDFT
    {order : Nat} (horder : 0 < order)
    (source : Fin order → ℂ) (frequency : Fin order) :
    bluesteinValue order source frequency =
      positiveDFT order source frequency := by
  simp only [bluesteinValue, bluesteinConvolutionValue,
    chirpedInput, centeredKernel, positiveDFT, Finset.mul_sum]
  apply Finset.sum_congr rfl
  intro input _
  rw [← bluestein_kernel_identity horder
    (input.val : Int) (frequency.val : Int)]
  ring

/-- Complete exact Bluestein reduction: zero-pad to any sufficiently long
cyclic convolution, convolve, post-chirp, and obtain the direct DFT. -/
theorem paddedBluesteinValue_eq_positiveDFT
    {order fftLength : Nat}
    (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ fftLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    paddedBluesteinValue order fftLength source frequency =
      positiveDFT order source frequency := by
  rw [paddedBluesteinValue,
    paddedCyclicConvolutionValue_eq_bluesteinConvolutionValue
      horder hfft source frequency]
  exact bluesteinValue_eq_positiveDFT horder source frequency

/-- Integer-exponent roots agree with the existing natural-exponent roots. -/
theorem signedUnitRoot_nat_eq_unitRoot
    (order exponent : Nat) :
    signedUnitRoot order (exponent : Int) =
      FactoredSmallQDFT.unitRoot order exponent := by
  simp [signedUnitRoot, FactoredSmallQDFT.unitRoot]

/-- Source-shaped maximum-order qualification identity: placing one at
input index one produces the ordinary positive unit root at every output
frequency. -/
theorem positiveDFT_basisOne_eq_unitRoot
    {order : Nat} (horder : 1 < order) (frequency : Fin order) :
    positiveDFT order (basisVector ⟨1, horder⟩) frequency =
      FactoredSmallQDFT.unitRoot order frequency.val := by
  rw [positiveDFT_basisVector]
  norm_num
  exact signedUnitRoot_nat_eq_unitRoot order frequency.val

/-- At a power-of-two length, the arbitrary-length direct definition is
literally the same DFT already used by the verified radix-2 network. -/
theorem positiveDFT_two_pow_eq_existing
    {logLength : Nat}
    (source : FactoredSmallQDFT.ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (2 ^ logLength) source.value frequency =
      FactoredSmallQDFT.positiveDFT source frequency := by
  simp only [positiveDFT, FactoredSmallQDFT.positiveDFT]
  apply Finset.sum_congr rfl
  intro input _
  rw [show
    (input.val : Int) * (frequency.val : Int) =
      ((input.val * frequency.val : Nat) : Int) by norm_num]
  rw [signedUnitRoot_nat_eq_unitRoot]

end SparkInterval.Dirichlet.BluesteinDFT
