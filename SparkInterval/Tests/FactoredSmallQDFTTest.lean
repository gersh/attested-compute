/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFTCorrectness

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQDFT

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT

def pointValue (re im : ℚ) : ℂ :=
  ⟨(re : ℝ), (im : ℝ)⟩

def pointDisk (re im : ℚ) : ComplexDisk :=
  ⟨re, im, 0⟩

def exactProduct (left right : ComplexDisk) : ComplexDisk :=
  pointDisk
    (left.re * right.re - left.im * right.im)
    (left.re * right.im + left.im * right.re)

def exactSum (left right : ComplexDisk) : ComplexDisk :=
  pointDisk (left.re + right.re) (left.im + right.im)

/-- The deliberately loose norm witnesses do not affect point-disk output
radii, but all their inequalities are still checked exactly. -/
def exactMul (left right : ComplexDisk) : ComplexDisk.MulCertificate := {
  left := left
  right := right
  output := exactProduct left right
  centerErrorBound := 0
  leftCenterNormBound := 100
  rightCenterNormBound := 100
}

def exactAdd (left right : ComplexDisk) : ComplexDisk.AddCertificate := {
  left := left
  right := right
  output := exactSum left right
  centerErrorBound := 0
}

def mkButterfly (stage group offset : Nat)
    (left right twiddle : ComplexDisk) : ButterflyCertificate :=
  let product := exactMul right twiddle
  {
    stageExponent := stage
    stageLength := width stage
    group := group
    offset := offset
    leftIndex := scheduledLeft stage group offset
    rightIndex := scheduledRight stage group offset
    twiddleTimesRight := product
    addToLeft := exactAdd left product.output
    addNegToRight := exactAdd left (negateDisk product.output)
  }

def one : ComplexDisk := pointDisk 1 0
def imagUnit : ComplexDisk := pointDisk 0 1

def preBitReversed : DiskState 2 :=
  ⟨fun index =>
    match index.val with
    | 0 => pointDisk 1 0
    | 1 => pointDisk 3 0
    | 2 => pointDisk 2 0
    | _ => pointDisk 4 0⟩

def exactPreBitReversed : ExactState 2 :=
  ⟨fun index =>
    match index.val with
    | 0 => pointValue 1 0
    | 1 => pointValue 3 0
    | 2 => pointValue 2 0
    | _ => pointValue 4 0⟩

def twiddleDisks (stage offset : Nat) : ComplexDisk :=
  if stage = 1 ∧ offset = 1 then imagUnit else one

def exactTwiddles (stage offset : Nat) : ℂ :=
  if stage = 1 ∧ offset = 1 then pointValue 0 1 else pointValue 1 0

def stage0Row0 : ButterflyCertificate :=
  mkButterfly 0 0 0 (pointDisk 1 0) (pointDisk 3 0) one

def stage0Row1 : ButterflyCertificate :=
  mkButterfly 0 1 0 (pointDisk 2 0) (pointDisk 4 0) one

def stage0 : StageCertificate 2 :=
  ⟨0, fun group _ => if group = 0 then stage0Row0 else stage0Row1⟩

def stage1Row0 : ButterflyCertificate :=
  mkButterfly 1 0 0 (pointDisk 4 0) (pointDisk 6 0) one

def stage1Row1 : ButterflyCertificate :=
  mkButterfly 1 0 1 (pointDisk (-2) 0) (pointDisk (-2) 0) imagUnit

def stage1 : StageCertificate 2 :=
  ⟨1, fun _ offset => if offset = 0 then stage1Row0 else stage1Row1⟩

def sample : Certificate 2 := {
  input := preBitReversed
  twiddleDisks := twiddleDisks
  stages := [stage0, stage1]
}

theorem pointDisk_contains (re im : ℚ) :
    (pointDisk re im).ContainsComplex (pointValue re im) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (pointDisk re im).center = pointValue re im := by
    apply Complex.ext <;>
      norm_num [pointDisk, pointValue, ComplexDisk.center]
  rw [hcenter]
  simp [pointDisk]

/-- A genuinely two-stage length-four network, not merely a single
butterfly, passes the ordinary kernel-reducible checker. -/
theorem stage0_accepted :
    stage0.Accepted 0 preBitReversed twiddleDisks := by
  refine ⟨rfl, by omega, ?_⟩
  intro index hindex
  have hi : index < 4 := List.mem_range.mp hindex
  interval_cases index <;>
    norm_num [stage0, stage0Row0, stage0Row1, mkButterfly,
      preBitReversed, twiddleDisks, imagUnit, one, exactMul, exactAdd,
      exactProduct, exactSum, pointDisk, StageCertificate.rowAt,
      ButterflyCertificate.WellFormed, groupAt, offsetAt, halfLength, width,
      scheduledLeft, scheduledRight, finIndex,
      ComplexDisk.MulCertificate.check,
      ComplexDisk.MulCertificate.WellFormed,
      ComplexDisk.AddCertificate.check,
      ComplexDisk.AddCertificate.WellFormed,
      ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
      ComplexDisk.centerNormSq, negateDisk]

theorem stage1_accepted :
    stage1.Accepted 1 (stage0.output 0) twiddleDisks := by
  refine ⟨rfl, by omega, ?_⟩
  intro index hindex
  have hi : index < 4 := List.mem_range.mp hindex
  interval_cases index <;>
    norm_num [stage1, stage1Row0, stage1Row1, stage0, stage0Row0,
      stage0Row1, mkButterfly, preBitReversed, twiddleDisks, imagUnit, one,
      exactMul, exactAdd, exactProduct, exactSum, pointDisk,
      StageCertificate.rowAt, StageCertificate.output, isLeftOutput,
      ButterflyCertificate.WellFormed, groupAt, offsetAt, halfLength, width,
      scheduledLeft, scheduledRight, finIndex,
      ComplexDisk.MulCertificate.check,
      ComplexDisk.MulCertificate.WellFormed,
      ComplexDisk.AddCertificate.check,
      ComplexDisk.AddCertificate.WellFormed,
      ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
      ComplexDisk.centerNormSq, negateDisk]

theorem length_four_check : sample.check = true := by
  have hstage0 :
      stage0.check 0 preBitReversed twiddleDisks = true :=
    decide_eq_true stage0_accepted
  have hstage1 :
      stage1.check 1 (stage0.output 0) twiddleDisks = true :=
    decide_eq_true stage1_accepted
  simp [sample, Certificate.check, checkLinkedStages, hstage0, hstage1]

theorem initial_contains :
    StateContains preBitReversed exactPreBitReversed := by
  intro index
  fin_cases index <;>
    exact pointDisk_contains _ _

theorem twiddles_contain :
    TwiddlesContain (logLength := 2) twiddleDisks exactTwiddles := by
  intro stage hstage offset hoffset
  interval_cases stage
  · have hoffset' : offset = 0 := by
      norm_num [halfLength] at hoffset
      omega
    subst offset
    simpa [twiddleDisks, exactTwiddles, imagUnit, one] using
      pointDisk_contains 1 0
  · norm_num [halfLength] at hoffset
    interval_cases offset
    · simpa [twiddleDisks, exactTwiddles, imagUnit, one] using
        pointDisk_contains 1 0
    · simpa [twiddleDisks, exactTwiddles, imagUnit, one] using
        pointDisk_contains 0 1

/-- The accepted two-stage trace encloses the exact radix-2 calculation. -/
theorem length_four_transform :
    StateContains sample.output
      (runExactStages exactTwiddles 2 0 exactPreBitReversed) :=
  Certificate.output_contains_transform
    length_four_check initial_contains twiddles_contain

/-- The FFT/direct-DFT identity is now generic Lean mathematics, rather than a
per-certificate assumption. -/
theorem length_four_radix2_correct :
    Radix2CorrectFor exactPreBitReversed :=
  radix2CorrectFor exactPreBitReversed

/-- The result is the positive-sign transform of `[1,2,3,4]`:
`[10, -2-2i, -2, -2+2i]`. -/
theorem length_four_expected_values :
    ∀ index,
      (sample.output.value index).ContainsComplex
        (match index.val with
        | 0 => pointValue 10 0
        | 1 => pointValue (-2) (-2)
        | 2 => pointValue (-2) 0
        | _ => pointValue (-2) 2) := by
  intro index
  have h := length_four_transform index
  fin_cases index <;>
    convert h using 1 <;>
      apply Complex.ext <;>
      norm_num [runExactStages, exactStage, exactPreBitReversed,
        exactTwiddles, ButterflyCertificate.exactLeft,
        ButterflyCertificate.exactRight, groupAt, offsetAt, isLeftOutput,
        halfLength, width, scheduledLeft, scheduledRight, finIndex,
        pointValue, Complex.mul_re, Complex.mul_im]

/-! Tamper cases: each changes an independently valid-looking arithmetic row
but violates a source-owned schedule or state link. -/

def reorderedStage0 : StageCertificate 2 :=
  ⟨0, fun group _ => if group = 0 then stage0Row1 else stage0Row0⟩

def reordered : Certificate 2 :=
  { sample with stages := [reorderedStage0, stage1] }

theorem reordered_rows_fail_closed : reordered.check = false := by
  have hnot : ¬ reorderedStage0.Accepted 0 preBitReversed twiddleDisks := by
    intro haccepted
    have hrow := haccepted.2.2 0 (by simp)
    norm_num [reorderedStage0, stage0Row1, mkButterfly,
      StageCertificate.rowAt, ButterflyCertificate.WellFormed,
      groupAt, offsetAt, halfLength, width, scheduledLeft, scheduledRight]
      at hrow
  have hbad :
      reorderedStage0.check 0 preBitReversed twiddleDisks = false := by
    exact decide_eq_false hnot
  simp [reordered, sample, Certificate.check, checkLinkedStages, hbad]

def wrongTwiddleRow : ButterflyCertificate :=
  mkButterfly 1 0 1 (pointDisk (-2) 0) (pointDisk (-2) 0) one

def wrongTwiddleStage : StageCertificate 2 :=
  ⟨1, fun _ offset => if offset = 0 then stage1Row0 else wrongTwiddleRow⟩

def wrongTwiddle : Certificate 2 :=
  { sample with stages := [stage0, wrongTwiddleStage] }

theorem wrong_twiddle_fails_closed : wrongTwiddle.check = false := by
  have hnot : ¬ wrongTwiddleStage.Accepted 1
      (stage0.output 0) twiddleDisks := by
    intro haccepted
    have hrow := haccepted.2.2 1 (by simp)
    norm_num [wrongTwiddleStage, wrongTwiddleRow, stage1Row0, mkButterfly,
      twiddleDisks, imagUnit, one, pointDisk, exactMul, exactProduct,
      StageCertificate.rowAt, ButterflyCertificate.WellFormed,
      groupAt, offsetAt, halfLength, width, scheduledLeft, scheduledRight]
      at hrow
  have hbad : wrongTwiddleStage.check 1
      (stage0.output 0) twiddleDisks = false := by
    exact decide_eq_false hnot
  have hstage0 :
      stage0.check 0 preBitReversed twiddleDisks = true :=
    decide_eq_true stage0_accepted
  simp [wrongTwiddle, sample, Certificate.check, checkLinkedStages,
    hstage0, hbad]

def badSubtractionRow : ButterflyCertificate :=
  { stage1Row1 with
    addNegToRight := exactAdd (pointDisk (-2) 0) (pointDisk 0 (-2)) }

def badSubtractionStage : StageCertificate 2 :=
  ⟨1, fun _ offset => if offset = 0 then stage1Row0 else badSubtractionRow⟩

def badSubtraction : Certificate 2 :=
  { sample with stages := [stage0, badSubtractionStage] }

theorem bad_subtraction_link_fails_closed : badSubtraction.check = false := by
  have hnot : ¬ badSubtractionStage.Accepted 1
      (stage0.output 0) twiddleDisks := by
    intro haccepted
    have hrow := haccepted.2.2 1 (by simp)
    norm_num [badSubtractionStage, badSubtractionRow, stage1Row0,
      stage1Row1, mkButterfly, imagUnit, pointDisk, exactMul, exactAdd,
      exactProduct, exactSum, negateDisk, StageCertificate.rowAt,
      ButterflyCertificate.WellFormed, groupAt, offsetAt, halfLength,
      width, scheduledLeft, scheduledRight] at hrow
  have hbad : badSubtractionStage.check 1
      (stage0.output 0) twiddleDisks = false := by
    exact decide_eq_false hnot
  have hstage0 :
      stage0.check 0 preBitReversed twiddleDisks = true :=
    decide_eq_true stage0_accepted
  simp [badSubtraction, sample, Certificate.check, checkLinkedStages,
    hstage0, hbad]

#print axioms negateDisk_contains
#print axioms ButterflyCertificate.check_sound
#print axioms ButterflyCertificate.outputs_contain
#print axioms StageCertificate.check_sound
#print axioms StageCertificate.output_contains_exactStage
#print axioms checkLinkedStages_sound
#print axioms runStages_contains
#print axioms reverseBits_lt_two_pow
#print axioms unitRoot_add
#print axioms unitRoot_even_shift
#print axioms exactStage_blockTransform
#print axioms reverseBits_involutive
#print axioms radix2CorrectFor
#print axioms Certificate.checker_sound
#print axioms Certificate.output_contains_transform
#print axioms Certificate.output_contains_positiveRadix2
#print axioms Certificate.output_contains_positiveDFT
#print axioms Certificate.output_contains_positiveDFT_unconditional
#print axioms length_four_check
#print axioms length_four_transform
#print axioms length_four_radix2_correct
#print axioms length_four_expected_values
#print axioms reordered_rows_fail_closed
#print axioms wrong_twiddle_fails_closed
#print axioms bad_subtraction_link_fails_closed

end SparkInterval.Tests.FactoredSmallQDFT
