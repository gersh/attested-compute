/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedRootTable
import SparkInterval.Dirichlet.DirectedIntervalBluestein

/-!
# Certified roots as directed-Bluestein input boxes

`CertifiedRootTable.rootRectFast?` returns exact rational rectangles, whereas
the directed FFT and Bluestein theorems consume `ComplexInterval` rectangles
over `ℝ`.  This file is the small, explicit bridge between those two layers.

A production binary64 box is accepted only when it contains both rational
coordinate intervals returned by the fully checked root generator.  The
resulting theorem supplies the exact root-containment premise needed by the
directed arithmetic proof.  No MPFR, CUDA, compiler, or execution fact is
introduced here.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedBluesteinRootBridge

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinCUDADataflow
open SparkInterval.Dirichlet.DirectedIntervalFFT
open SparkInterval.Dirichlet.DirectedIntervalBluestein

/-- A real-endpoint production box contains an exact rational rectangle.
The comparisons are directly executable once the production endpoints have
been decoded to exact rationals or dyadics. -/
def EnclosesRect (box : ComplexInterval) (rect : ComplexRect) : Prop :=
  box.re.lo ≤ (rect.re.lo : ℝ) ∧
  (rect.re.hi : ℝ) ≤ box.re.hi ∧
  box.im.lo ≤ (rect.im.lo : ℝ) ∧
  (rect.im.hi : ℝ) ≤ box.im.hi

/-- Containment is transitive across the rational-to-real rectangle bridge. -/
theorem contains_of_enclosesRect
    {box : ComplexInterval} {rect : ComplexRect} {z : ℂ}
    (houter : EnclosesRect box rect)
    (hinner : rect.ContainsComplex z) :
    box.Contains z := by
  exact
    ⟨⟨houter.1.trans hinner.1.1,
        hinner.1.2.trans houter.2.1⟩,
      ⟨houter.2.2.1.trans hinner.2.1,
        hinner.2.2.trans houter.2.2.2⟩⟩

/-- A production box carries a fast checked root certificate when it encloses
the exact rational output of a successful `rootRectFast?` evaluation. -/
def FastRootCertificate
    (workPrecision outputPrecision order exponent : Nat)
    (box : ComplexInterval) : Prop :=
  ∃ rect : ComplexRect,
    CertifiedRootTable.rootRectFast?
        workPrecision outputPrecision order exponent = some rect ∧
      EnclosesRect box rect

/-- The endpoint comparison plus a successful checked rational evaluation
proves containment of the exact positive root. -/
theorem fastRootCertificate_contains
    {workPrecision outputPrecision order exponent : Nat}
    {box : ComplexInterval}
    (hcertificate :
      FastRootCertificate workPrecision outputPrecision
        order exponent box) :
    box.Contains (unitRoot order exponent) := by
  rcases hcertificate with ⟨rect, hroot, houter⟩
  exact contains_of_enclosesRect houter
    (CertifiedRootTable.rootRectFast?_containsComplex hroot)

/-! ## Positive and negative radix-2 twiddles -/

/-- Checked root certificates for every stage coordinate queried by a
`logLength`-stage transform. -/
def PositiveTwiddleCertificates
    (workPrecision outputPrecision logLength : Nat)
    (boxes : Nat → Nat → ComplexInterval) : Prop :=
  ∀ stage, stage < logLength →
    ∀ offset, offset < halfLength stage →
      FastRootCertificate workPrecision outputPrecision
        (width stage) offset (boxes stage offset)

/-- The finite family of successful root checks supplies the complete
positive-twiddle premise used by the directed FFT. -/
theorem positiveTwiddlesContain_of_certificates
    {workPrecision outputPrecision logLength : Nat}
    {boxes : Nat → Nat → ComplexInterval}
    (hcertificates :
      PositiveTwiddleCertificates workPrecision outputPrecision
        logLength boxes) :
    TwiddlesContain (logLength := logLength) boxes positiveTwiddle := by
  intro stage hstage offset hoffset
  simpa [positiveTwiddle] using
    fastRootCertificate_contains
      (hcertificates stage hstage offset hoffset)

/-- Reflect a complex rectangle across the real axis. -/
def conjugateBox (box : ComplexInterval) : ComplexInterval where
  re := box.re
  im := box.im.neg

/-- Rectangle reflection contains complex conjugation exactly. -/
theorem conjugateBox_contains
    {box : ComplexInterval} {z : ℂ}
    (hcontains : box.Contains z) :
    (conjugateBox box).Contains (starRingEnd ℂ z) := by
  constructor
  · simpa [conjugateBox] using hcontains.1
  · change
      -box.im.hi ≤ -z.im ∧ -z.im ≤ -box.im.lo
    exact ⟨neg_le_neg hcontains.2.2, neg_le_neg hcontains.2.1⟩

/-- Conjugating the checked positive table supplies the complete
negative-twiddle premise used by both forward transforms. -/
theorem negativeTwiddlesContain_of_positive_certificates
    {workPrecision outputPrecision logLength : Nat}
    {positiveBoxes : Nat → Nat → ComplexInterval}
    (hcertificates :
      PositiveTwiddleCertificates workPrecision outputPrecision
        logLength positiveBoxes) :
    TwiddlesContain (logLength := logLength)
      (fun stage offset => conjugateBox (positiveBoxes stage offset))
      negativeTwiddle := by
  intro stage hstage offset hoffset
  exact conjugateBox_contains
    (positiveTwiddlesContain_of_certificates hcertificates
      stage hstage offset hoffset)

/-! ## Positive half-angle chirps -/

/-- A natural-exponent half-angle chirp is a positive root of twice the
order.  The positive-order guard is explicit because this is the live
Bluestein regime. -/
theorem halfRoot_nat_eq_unitRoot
    {order : Nat} (horder : 0 < order) (exponent : Nat) :
    BluesteinDFT.halfRoot order (exponent : Int) =
      unitRoot (2 * order) exponent := by
  unfold BluesteinDFT.halfRoot unitRoot
  congr 1
  push_cast
  have horderReal : (order : ℝ) ≠ 0 := by positivity
  field_simp [horderReal]

/-- Checked certificates for every positive half-angle chirp queried by a
length-`order` input or output table. -/
def PositiveChirpCertificates
    (workPrecision outputPrecision order : Nat)
    (boxes : Fin order → ComplexInterval) : Prop :=
  ∀ index,
    FastRootCertificate workPrecision outputPrecision
      (2 * order) (index.val ^ 2) (boxes index)

/-- Checked doubled-order roots supply the input-chirp premise. -/
theorem inputChirpsContain_of_certificates
    {workPrecision outputPrecision order : Nat}
    (horder : 0 < order)
    {boxes : Fin order → ComplexInterval}
    (hcertificates :
      PositiveChirpCertificates workPrecision outputPrecision order boxes) :
    InputChirpsContain boxes := by
  intro index
  have hroot :=
    fastRootCertificate_contains (hcertificates index)
  rw [← halfRoot_nat_eq_unitRoot horder (index.val ^ 2)] at hroot
  norm_num at hroot ⊢
  exact hroot

/-- The same checked table supplies the output-chirp premise. -/
theorem outputChirpsContain_of_certificates
    {workPrecision outputPrecision order : Nat}
    (horder : 0 < order)
    {boxes : Fin order → ComplexInterval}
    (hcertificates :
      PositiveChirpCertificates workPrecision outputPrecision order boxes) :
    OutputChirpsContain boxes := by
  intro index
  exact inputChirpsContain_of_certificates horder hcertificates index

/-! ## Negative chirps and the literal-zero padded kernel -/

/-- Complex conjugation changes the sign of a half-angle chirp exponent. -/
theorem conjugate_halfRoot (order : Nat) (exponent : Int) :
    starRingEnd ℂ (BluesteinDFT.halfRoot order exponent) =
      BluesteinDFT.halfRoot order (-exponent) := by
  unfold BluesteinDFT.halfRoot
  rw [← Complex.exp_conj]
  congr 1
  push_cast
  simp
  ring

/-- Reflecting a certified positive chirp box encloses the corresponding
negative chirp used by the Bluestein kernel. -/
theorem conjugateBox_contains_negative_chirp
    {workPrecision outputPrecision order exponent : Nat}
    (horder : 0 < order)
    {box : ComplexInterval}
    (hcertificate :
      FastRootCertificate workPrecision outputPrecision
        (2 * order) (exponent ^ 2) box) :
    (conjugateBox box).Contains
      (BluesteinDFT.halfRoot order (-((exponent : Int) ^ 2))) := by
  have hpositive :=
    fastRootCertificate_contains hcertificate
  rw [← halfRoot_nat_eq_unitRoot horder (exponent ^ 2)] at hpositive
  have hnegative := conjugateBox_contains hpositive
  rw [conjugate_halfRoot] at hnegative
  norm_num at hnegative ⊢
  exact hnegative

/-- Natural-order kernel boxes built from one positive chirp table.  The two
populated wings are reflected; the unused middle is the exact singleton zero
rectangle. -/
noncomputable def kernelBoxesFromPositiveChirps
    {order logLength : Nat}
    (positiveBoxes : Fin order → ComplexInterval) :
    IntervalState logLength :=
  ⟨fun index =>
    if hlow : index.val < order then
      conjugateBox (positiveBoxes ⟨index.val, hlow⟩)
    else if hhigh : 2 ^ logLength - index.val < order then
      conjugateBox
        (positiveBoxes ⟨2 ^ logLength - index.val, hhigh⟩)
    else
      ComplexInterval.point 0⟩

theorem centeredIndex_eq_neg_distance
    {order fftLength index : Nat}
    (hindex : index < fftLength)
    (hnotlow : ¬index < order) :
    BluesteinDFT.centeredIndex order fftLength index =
      -((fftLength - index : Nat) : Int) := by
  simp only [BluesteinDFT.centeredIndex, if_neg hnotlow]
  rw [Int.ofNat_sub (Nat.le_of_lt hindex)]
  ring

/-- A checked positive chirp table supplies every nonzero kernel entry and
the literal zero middle supplies itself. -/
theorem kernelContains_of_positive_chirp_certificates
    {workPrecision outputPrecision order logLength : Nat}
    (horder : 0 < order)
    {positiveBoxes : Fin order → ComplexInterval}
    (hcertificates :
      PositiveChirpCertificates workPrecision outputPrecision
        order positiveBoxes) :
    KernelContains (order := order)
      (kernelBoxesFromPositiveChirps
        (logLength := logLength) positiveBoxes) := by
  intro index
  by_cases hlow : index.val < order
  · have hnegative :=
      conjugateBox_contains_negative_chirp horder
        (hcertificates ⟨index.val, hlow⟩)
    simpa [kernelBoxesFromPositiveChirps,
      BluesteinFFTConvolution.zeroPaddedKernelState,
      BluesteinDFT.wrappedKernel, BluesteinDFT.centeredKernel,
      BluesteinDFT.centeredIndex, hlow] using hnegative
  · by_cases hhigh : 2 ^ logLength - index.val < order
    · have hnegative :=
        conjugateBox_contains_negative_chirp horder
          (hcertificates
            ⟨2 ^ logLength - index.val, hhigh⟩)
      have hcentered :
          BluesteinDFT.centeredIndex
              order (2 ^ logLength) index.val =
            -((2 ^ logLength - index.val : Nat) : Int) :=
        centeredIndex_eq_neg_distance index.isLt hlow
      have hkernel :
          BluesteinDFT.wrappedKernel
              order (2 ^ logLength) index.val =
            BluesteinDFT.halfRoot order
              (-((2 ^ logLength - index.val : Nat) : Int) ^ 2) := by
        rw [BluesteinDFT.wrappedKernel,
          BluesteinDFT.centeredKernel, hcentered]
        congr 2
        ring
      simpa [kernelBoxesFromPositiveChirps,
        BluesteinFFTConvolution.zeroPaddedKernelState,
        hlow, hhigh, hkernel] using hnegative
    · simp [kernelBoxesFromPositiveChirps,
        BluesteinFFTConvolution.zeroPaddedKernelState, hlow, hhigh]

/-! ## Certified-root directed-Bluestein capstone -/

/-- The power-of-two normalization represented as an exact singleton box. -/
noncomputable def exactNormalizationBox (logLength : Nat) : ComplexInterval :=
  ComplexInterval.point (((2 ^ logLength : Nat) : ℂ)⁻¹)

theorem exactNormalizationBox_contains (logLength : Nat) :
    NormalizationContains
      (logLength := logLength) (exactNormalizationBox logLength) :=
  ComplexInterval.point_contains _

/-- End-to-end mathematical composition for one transform coefficient.

The only numerical premises are successful fast rational root certificates
whose rectangles fit inside the supplied chirp and positive-twiddle boxes.
The negative twiddles and kernel are derived by exact conjugation, padding is
literal zero, and normalization is the exact singleton `1 / 2^logLength`.
What remains beyond this theorem is implementation refinement of the supplied
boxes and directed operations, plus physical execution. -/
theorem certifiedRoots_directedBluestein_contains_positiveDFT
    (rounding : DirectedRound)
    {workPrecision outputPrecision order logLength : Nat}
    {sourceBoxes chirpBoxes : Fin order → ComplexInterval}
    {positiveTwiddleBoxes : Nat → Nat → ComplexInterval}
    {source : Fin order → ℂ}
    (frequency : Fin order)
    (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (hsource : SourcesContain sourceBoxes source)
    (hchirps :
      PositiveChirpCertificates workPrecision outputPrecision
        order chirpBoxes)
    (htwiddles :
      PositiveTwiddleCertificates workPrecision outputPrecision
        logLength positiveTwiddleBoxes) :
    (directedBluesteinLineValue rounding order logLength
      sourceBoxes chirpBoxes
      (kernelBoxesFromPositiveChirps
        (logLength := logLength) chirpBoxes)
      (fun stage offset =>
        conjugateBox (positiveTwiddleBoxes stage offset))
      positiveTwiddleBoxes
      chirpBoxes
      (exactNormalizationBox logLength)
      frequency
      (by omega : order ≤ 2 ^ logLength)).Contains
      (BluesteinDFT.positiveDFT order source frequency) := by
  exact
    directedBluesteinLineValue_contains_positiveDFT rounding
      frequency horder hfft hsource
      (inputChirpsContain_of_certificates horder hchirps)
      (kernelContains_of_positive_chirp_certificates horder hchirps)
      (negativeTwiddlesContain_of_positive_certificates htwiddles)
      (positiveTwiddlesContain_of_certificates htwiddles)
      (outputChirpsContain_of_certificates horder hchirps)
      (exactNormalizationBox_contains logLength)

end SparkInterval.Dirichlet.CertifiedBluesteinRootBridge
