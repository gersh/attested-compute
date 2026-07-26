/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDisk
import Mathlib.Analysis.SpecialFunctions.Complex.CircleAddChar

/-!
# Typed certificates for the small-conductor positive-sign radix-2 DFT

The small-`q` CUDA path first bit-reverses each line and then performs the
usual decimation-in-time butterflies

```
v := right * exp(+2*pi*i*j/stageLength)
left  := left + v
right := left - v.
```

This module checks exactly that arithmetic after binary64 words have been
decoded to rational disks.  A butterfly record is tied to its stage, group,
offset, left index, right index, source disks, and stage twiddle.  Stage rows
are addressed by `(group, offset)`, so exchanging two otherwise valid rows is
rejected.  The subtraction path is represented by exact disk negation followed
by the already proved disk-addition checker, exactly as the CUDA `diskSub`
helper negates both centre coordinates before calling `diskAdd`.

The main theorem is a finite staged invariant: an accepted `logLength`-stage
certificate encloses the exact positive-sign radix-2 transform of a
bit-reversed input.  The initial bit-reversal containment and transcendental
twiddle containment are explicit premises.  The companion module
`FactoredSmallQDFTCorrectness` proves the generic permutation/algebra identity
between this staged transform and the direct DFT formula, and supplies the
unconditional direct-DFT application theorem.

This is a typed arithmetic certificate layer.  In particular, `rows` and the
twiddle bank below are total Lean functions used as finite-query tables: the
checker queries exactly the indices in `List.range (2^logLength)` and ignores
all other function values.  They are not a proposed finite wire encoding.
Replacing them by a canonical finite-list parser is a separate refinement
edge.  This file makes no claim about such parsing, a CUDA trace, MPFR/Arb
root production, or physical execution.
-/

set_option autoImplicit false

open scoped BigOperators

namespace SparkInterval.Dirichlet.FactoredSmallQDFT

open SparkInterval.Certified

/-! ## Exact negation and one CUDA-shaped butterfly -/

/-- Exact disk operation used before checking `left - product` as an addition. -/
def negateDisk (disk : ComplexDisk) : ComplexDisk :=
  ⟨-disk.re, -disk.im, disk.radius⟩

@[simp] theorem negateDisk_center (disk : ComplexDisk) :
    (negateDisk disk).center = -disk.center := by
  apply Complex.ext <;>
    simp [negateDisk, ComplexDisk.center]

/-- Exact centre negation preserves a Euclidean disk enclosure. -/
theorem negateDisk_contains {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (negateDisk disk).ContainsComplex (-value) := by
  rw [ComplexDisk.ContainsComplex, negateDisk_center]
  rw [show -value - -disk.center = -(value - disk.center) by ring,
    norm_neg]
  exact hcontains

/-- Arithmetic and schedule metadata for one radix-2 butterfly. -/
structure ButterflyCertificate where
  stageExponent : Nat
  stageLength : Nat
  group : Nat
  offset : Nat
  leftIndex : Nat
  rightIndex : Nat
  twiddleTimesRight : ComplexDisk.MulCertificate
  addToLeft : ComplexDisk.AddCertificate
  addNegToRight : ComplexDisk.AddCertificate
  deriving Repr, DecidableEq, BEq

def halfLength (stageExponent : Nat) : Nat := 2 ^ stageExponent

def width (stageExponent : Nat) : Nat := 2 * halfLength stageExponent

def scheduledLeft (stageExponent group offset : Nat) : Nat :=
  group * width stageExponent + offset

def scheduledRight (stageExponent group offset : Nat) : Nat :=
  scheduledLeft stageExponent group offset + halfLength stageExponent

/-- Use a total lookup internally.  Accepted rows separately prove that the
unreduced scheduled indices are below the source-owned transform length. -/
def finIndex (logLength index : Nat) : Fin (2 ^ logLength) :=
  ⟨index % (2 ^ logLength), Nat.mod_lt _ (Nat.pow_pos (by omega))⟩

/-- A line of rational disks of source-owned power-of-two length. -/
structure DiskState (logLength : Nat) where
  value : Fin (2 ^ logLength) → ComplexDisk

/-- The corresponding exact complex-valued line. -/
structure ExactState (logLength : Nat) where
  value : Fin (2 ^ logLength) → ℂ

def StateContains {logLength : Nat}
    (disks : DiskState logLength) (exact : ExactState logLength) : Prop :=
  ∀ index, (disks.value index).ContainsComplex (exact.value index)

namespace ButterflyCertificate

/-- All arithmetic links and all schedule links for one row.  Multiplication
order matches CUDA: `diskMul(values[right], roots[rootOffset + j])`. -/
def WellFormed {logLength : Nat} (certificate : ButterflyCertificate)
    (expectedStage expectedGroup expectedOffset : Nat)
    (current : DiskState logLength)
    (twiddleDisks : Nat → Nat → ComplexDisk) : Prop :=
  let expectedLeft :=
    scheduledLeft expectedStage expectedGroup expectedOffset
  let expectedRight :=
    scheduledRight expectedStage expectedGroup expectedOffset
  certificate.stageExponent = expectedStage ∧
  certificate.stageLength = width expectedStage ∧
  certificate.group = expectedGroup ∧
  certificate.offset = expectedOffset ∧
  certificate.leftIndex = expectedLeft ∧
  certificate.rightIndex = expectedRight ∧
  expectedRight < 2 ^ logLength ∧
  certificate.twiddleTimesRight.check = true ∧
  certificate.twiddleTimesRight.left =
    current.value (finIndex logLength expectedRight) ∧
  certificate.twiddleTimesRight.right =
    twiddleDisks expectedStage expectedOffset ∧
  certificate.addToLeft.check = true ∧
  certificate.addToLeft.left =
    current.value (finIndex logLength expectedLeft) ∧
  certificate.addToLeft.right = certificate.twiddleTimesRight.output ∧
  certificate.addNegToRight.check = true ∧
  certificate.addNegToRight.left =
    current.value (finIndex logLength expectedLeft) ∧
  certificate.addNegToRight.right =
    negateDisk certificate.twiddleTimesRight.output

instance instDecidableWellFormed {logLength : Nat}
    (certificate : ButterflyCertificate)
    (expectedStage expectedGroup expectedOffset : Nat)
    (current : DiskState logLength)
    (twiddleDisks : Nat → Nat → ComplexDisk) :
    Decidable (certificate.WellFormed expectedStage expectedGroup
      expectedOffset current twiddleDisks) := by
  unfold WellFormed
  infer_instance

def check {logLength : Nat} (certificate : ButterflyCertificate)
    (expectedStage expectedGroup expectedOffset : Nat)
    (current : DiskState logLength)
    (twiddleDisks : Nat → Nat → ComplexDisk) : Bool :=
  decide (certificate.WellFormed expectedStage expectedGroup
    expectedOffset current twiddleDisks)

theorem check_sound {logLength : Nat} {certificate : ButterflyCertificate}
    {expectedStage expectedGroup expectedOffset : Nat}
    {current : DiskState logLength}
    {twiddleDisks : Nat → Nat → ComplexDisk}
    (hcheck : certificate.check expectedStage expectedGroup expectedOffset
      current twiddleDisks = true) :
    certificate.WellFormed expectedStage expectedGroup expectedOffset
      current twiddleDisks :=
  of_decide_eq_true hcheck

/-- Exact positive-sign butterfly values. -/
def exactLeft (left right twiddle : ℂ) : ℂ :=
  left + right * twiddle

def exactRight (left right twiddle : ℂ) : ℂ :=
  left - right * twiddle

/-- One accepted CUDA-shaped butterfly encloses both exact outputs. -/
theorem outputs_contain {logLength : Nat}
    {certificate : ButterflyCertificate}
    {expectedStage expectedGroup expectedOffset : Nat}
    {current : DiskState logLength}
    {twiddleDisks : Nat → Nat → ComplexDisk}
    {left right twiddle : ℂ}
    (hvalid : certificate.WellFormed expectedStage expectedGroup
      expectedOffset current twiddleDisks)
    (hleft : (current.value (finIndex logLength
      (scheduledLeft expectedStage expectedGroup expectedOffset))).ContainsComplex
        left)
    (hright : (current.value (finIndex logLength
      (scheduledRight expectedStage expectedGroup expectedOffset))).ContainsComplex
        right)
    (htwiddle : (twiddleDisks expectedStage expectedOffset).ContainsComplex
      twiddle) :
    certificate.addToLeft.output.ContainsComplex
        (exactLeft left right twiddle) ∧
      certificate.addNegToRight.output.ContainsComplex
        (exactRight left right twiddle) := by
  dsimp only [WellFormed] at hvalid
  rcases hvalid with
    ⟨_, _, _, _, _, _, _, hmulCheck, hmulLeft, hmulRight,
      haddCheck, haddLeft, haddRight, hsubCheck, hsubLeft, hsubRight⟩
  have hmulLeftContains :
      certificate.twiddleTimesRight.left.ContainsComplex right := by
    rw [hmulLeft]
    exact hright
  have hmulRightContains :
      certificate.twiddleTimesRight.right.ContainsComplex twiddle := by
    rw [hmulRight]
    exact htwiddle
  have hproduct : certificate.twiddleTimesRight.output.ContainsComplex
      (right * twiddle) :=
    ComplexDisk.MulCertificate.output_contains_mul
      hmulCheck hmulLeftContains hmulRightContains
  have haddLeftContains :
      certificate.addToLeft.left.ContainsComplex left := by
    rw [haddLeft]
    exact hleft
  have haddRightContains :
      certificate.addToLeft.right.ContainsComplex (right * twiddle) := by
    rw [haddRight]
    exact hproduct
  have hsubLeftContains :
      certificate.addNegToRight.left.ContainsComplex left := by
    rw [hsubLeft]
    exact hleft
  have hsubRightContains :
      certificate.addNegToRight.right.ContainsComplex (-(right * twiddle)) := by
    rw [hsubRight]
    exact negateDisk_contains hproduct
  constructor
  · simpa [exactLeft] using
      (ComplexDisk.AddCertificate.output_contains_add
        haddCheck haddLeftContains haddRightContains)
  · simpa [exactRight, sub_eq_add_neg] using
      (ComplexDisk.AddCertificate.output_contains_add
        hsubCheck hsubLeftContains hsubRightContains)

end ButterflyCertificate

/-! ## One complete stage -/

def groupAt (stageExponent index : Nat) : Nat :=
  index / width stageExponent

def offsetAt (stageExponent index : Nat) : Nat :=
  index % halfLength stageExponent

def isLeftOutput (stageExponent index : Nat) : Bool :=
  decide (index % width stageExponent < halfLength stageExponent)

/-- A stage is a typed table keyed by the exact CUDA `(group, j)` coordinates.
There is no producer-provided row order to trust.  It is intentionally a
finite-query semantic model rather than a raw-wire representation: `check`
queries the table only through the finite natural output range. -/
structure StageCertificate (logLength : Nat) where
  stageExponent : Nat
  rows : Nat → Nat → ButterflyCertificate

namespace StageCertificate

def rowAt {logLength : Nat} (certificate : StageCertificate logLength)
    (expectedStage index : Nat) : ButterflyCertificate :=
  certificate.rows (groupAt expectedStage index)
    (offsetAt expectedStage index)

/-- Output line in natural index order.  Both members of a pair select the
same checked row, then select its plus or minus output. -/
def output {logLength : Nat} (certificate : StageCertificate logLength)
    (expectedStage : Nat) : DiskState logLength :=
  ⟨fun index =>
    let row := certificate.rowAt expectedStage index.val
    if isLeftOutput expectedStage index.val then
      row.addToLeft.output
    else
      row.addNegToRight.output⟩

/-- Source-owned stage number plus a complete check at every natural output
index.  The two output indices of a butterfly deliberately check the same row. -/
def Accepted {logLength : Nat} (certificate : StageCertificate logLength)
    (expectedStage : Nat) (current : DiskState logLength)
    (twiddleDisks : Nat → Nat → ComplexDisk) : Prop :=
  certificate.stageExponent = expectedStage ∧
  expectedStage < logLength ∧
  ∀ index ∈ List.range (2 ^ logLength),
    (certificate.rowAt expectedStage index).WellFormed expectedStage
      (groupAt expectedStage index) (offsetAt expectedStage index)
      current twiddleDisks

instance instDecidableAccepted {logLength : Nat}
    (certificate : StageCertificate logLength) (expectedStage : Nat)
    (current : DiskState logLength)
    (twiddleDisks : Nat → Nat → ComplexDisk) :
    Decidable (certificate.Accepted expectedStage current twiddleDisks) := by
  unfold Accepted
  infer_instance

def check {logLength : Nat} (certificate : StageCertificate logLength)
    (expectedStage : Nat) (current : DiskState logLength)
    (twiddleDisks : Nat → Nat → ComplexDisk) : Bool :=
  decide (certificate.Accepted expectedStage current twiddleDisks)

theorem check_sound {logLength : Nat}
    {certificate : StageCertificate logLength} {expectedStage : Nat}
    {current : DiskState logLength}
    {twiddleDisks : Nat → Nat → ComplexDisk}
    (hcheck : certificate.check expectedStage current twiddleDisks = true) :
    certificate.Accepted expectedStage current twiddleDisks :=
  of_decide_eq_true hcheck

end StageCertificate

/-- Exact source-level semantics of one DIT stage. -/
def exactStage {logLength : Nat} (expectedStage : Nat)
    (twiddles : Nat → Nat → ℂ) (current : ExactState logLength) :
    ExactState logLength :=
  ⟨fun index =>
    let group := groupAt expectedStage index.val
    let offset := offsetAt expectedStage index.val
    let left := current.value (finIndex logLength
      (scheduledLeft expectedStage group offset))
    let right := current.value (finIndex logLength
      (scheduledRight expectedStage group offset))
    if isLeftOutput expectedStage index.val then
      ButterflyCertificate.exactLeft left right
        (twiddles expectedStage offset)
    else
      ButterflyCertificate.exactRight left right
        (twiddles expectedStage offset)⟩

def TwiddlesContain {logLength : Nat}
    (twiddleDisks : Nat → Nat → ComplexDisk)
    (twiddles : Nat → Nat → ℂ) : Prop :=
  ∀ stage, stage < logLength →
    ∀ offset, offset < halfLength stage →
      (twiddleDisks stage offset).ContainsComplex (twiddles stage offset)

/-- The checked output of one full stage preserves pointwise containment. -/
theorem StageCertificate.output_contains_exactStage {logLength : Nat}
    {certificate : StageCertificate logLength} {expectedStage : Nat}
    {current : DiskState logLength} {exact : ExactState logLength}
    {twiddleDisks : Nat → Nat → ComplexDisk}
    {twiddles : Nat → Nat → ℂ}
    (hcheck : certificate.check expectedStage current twiddleDisks = true)
    (hcurrent : StateContains current exact)
    (htwiddles : TwiddlesContain (logLength := logLength)
      twiddleDisks twiddles) :
    StateContains (certificate.output expectedStage)
      (exactStage expectedStage twiddles exact) := by
  have haccepted := certificate.check_sound hcheck
  intro index
  have hrow := haccepted.2.2 index.val
    (List.mem_range.mpr index.isLt)
  have hoffset : offsetAt expectedStage index.val <
      halfLength expectedStage := by
    exact Nat.mod_lt _ (Nat.pow_pos (by omega))
  have houtputs := ButterflyCertificate.outputs_contain hrow
    (hcurrent (finIndex logLength (scheduledLeft expectedStage
      (groupAt expectedStage index.val) (offsetAt expectedStage index.val))))
    (hcurrent (finIndex logLength (scheduledRight expectedStage
      (groupAt expectedStage index.val) (offsetAt expectedStage index.val))))
    (htwiddles expectedStage haccepted.2.1
      (offsetAt expectedStage index.val) hoffset)
  by_cases hside : isLeftOutput expectedStage index.val = true
  · simpa [StageCertificate.output, exactStage, hside] using houtputs.1
  · have hfalse : isLeftOutput expectedStage index.val = false :=
      Bool.eq_false_of_not_eq_true hside
    simpa [StageCertificate.output, exactStage, hfalse] using houtputs.2

/-! ## Complete finite stage trace -/

def LinkedStages {logLength : Nat}
    (twiddleDisks : Nat → Nat → ComplexDisk) :
    Nat → DiskState logLength → List (StageCertificate logLength) → Prop
  | _, _, [] => True
  | expectedStage, current, stage :: rest =>
      stage.Accepted expectedStage current twiddleDisks ∧
      LinkedStages twiddleDisks (expectedStage + 1)
        (stage.output expectedStage) rest

def checkLinkedStages {logLength : Nat}
    (twiddleDisks : Nat → Nat → ComplexDisk) :
    Nat → DiskState logLength → List (StageCertificate logLength) → Bool
  | _, _, [] => true
  | expectedStage, current, stage :: rest =>
      stage.check expectedStage current twiddleDisks &&
      checkLinkedStages twiddleDisks (expectedStage + 1)
        (stage.output expectedStage) rest

theorem checkLinkedStages_sound {logLength : Nat}
    {twiddleDisks : Nat → Nat → ComplexDisk}
    {expectedStage : Nat} {current : DiskState logLength}
    {stages : List (StageCertificate logLength)}
    (hcheck : checkLinkedStages twiddleDisks expectedStage current stages = true) :
    LinkedStages twiddleDisks expectedStage current stages := by
  induction stages generalizing expectedStage current with
  | nil => simp [LinkedStages]
  | cons stage rest ih =>
      simp only [checkLinkedStages, Bool.and_eq_true] at hcheck
      exact ⟨StageCertificate.check_sound hcheck.1, ih hcheck.2⟩

def runStages {logLength : Nat} :
    Nat → DiskState logLength → List (StageCertificate logLength) →
      DiskState logLength
  | _, current, [] => current
  | expectedStage, _, stage :: rest =>
      runStages (expectedStage + 1) (stage.output expectedStage) rest

/-- Pure mathematical iteration of the same positive-sign stage equations. -/
def runExactStages {logLength : Nat}
    (twiddles : Nat → Nat → ℂ) :
    Nat → Nat → ExactState logLength → ExactState logLength
  | 0, _, current => current
  | count + 1, expectedStage, current =>
      runExactStages twiddles count (expectedStage + 1)
        (exactStage expectedStage twiddles current)

/-- Staged invariant for any accepted suffix of the butterfly network. -/
theorem runStages_contains {logLength : Nat}
    {twiddleDisks : Nat → Nat → ComplexDisk}
    {twiddles : Nat → Nat → ℂ}
    {expectedStage : Nat} {current : DiskState logLength}
    {exact : ExactState logLength}
    {stages : List (StageCertificate logLength)}
    (hlinked : LinkedStages twiddleDisks expectedStage current stages)
    (hcurrent : StateContains current exact)
    (htwiddles : TwiddlesContain (logLength := logLength)
      twiddleDisks twiddles) :
    StateContains (runStages expectedStage current stages)
      (runExactStages twiddles stages.length expectedStage exact) := by
  induction stages generalizing expectedStage current exact with
  | nil => simpa [runStages, runExactStages] using hcurrent
  | cons stage rest ih =>
      rcases hlinked with ⟨hstage, hrest⟩
      have hstageCheck :
          stage.check expectedStage current twiddleDisks = true := by
        exact decide_eq_true hstage
      have hnext := stage.output_contains_exactStage
        hstageCheck hcurrent htwiddles
      have hfinal := ih hrest hnext
      simpa [runStages, runExactStages] using hfinal

/-! ## Source-level bit reversal and positive DFT -/

/-- Reverse exactly `bits` low-order bits. -/
def reverseBits : Nat → Nat → Nat
  | 0, _ => 0
  | bits + 1, index =>
      (index % 2) * 2 ^ bits + reverseBits bits (index / 2)

/-- Reversing the low `bits` bits always produces an actual `bits`-bit
index.  Thus the `finIndex` in `bitReversed` does not hide a wraparound. -/
theorem reverseBits_lt_two_pow (bits index : Nat) :
    reverseBits bits index < 2 ^ bits := by
  induction bits generalizing index with
  | zero => simp [reverseBits]
  | succ bits ih =>
      rw [reverseBits, pow_succ]
      have htail := ih (index / 2)
      have hbit : index % 2 < 2 := Nat.mod_lt _ (by omega)
      have hcases : index % 2 = 0 ∨ index % 2 = 1 := by omega
      rcases hcases with hzero | hone
      · simp [hzero]
        omega
      · simp [hone]
        omega

def bitReversed {logLength : Nat} (source : ExactState logLength) :
    ExactState logLength :=
  ⟨fun index => source.value
    (finIndex logLength (reverseBits logLength index.val))⟩

/-- Positive root used by CUDA stage `stageExponent`. -/
noncomputable def unitRoot (order exponent : Nat) : ℂ :=
  Complex.exp
    ((((2 * Real.pi * (exponent : ℝ)) /
      (order : ℝ) : ℝ) : ℂ) * Complex.I)

theorem unitRoot_zero (order : Nat) : unitRoot order 0 = 1 := by
  simp [unitRoot]

theorem unitRoot_add (order a b : Nat) :
    unitRoot order (a + b) = unitRoot order a * unitRoot order b := by
  rw [unitRoot, unitRoot, unitRoot, ← Complex.exp_add]
  congr 1
  push_cast
  field_simp

theorem unitRoot_mul_right (order a b : Nat) :
    unitRoot order (a * b) = unitRoot order a ^ b := by
  unfold unitRoot
  rw [← Complex.exp_nat_mul]
  congr 1
  push_cast
  field_simp

theorem unitRoot_double (order a : Nat) :
    unitRoot (2 * order) (2 * a) = unitRoot order a := by
  rw [unitRoot, unitRoot]
  congr 1
  push_cast
  field_simp

theorem unitRoot_order {order : Nat} (horder : 0 < order) :
    unitRoot order order = 1 := by
  have horder0 : (order : ℝ) ≠ 0 := by positivity
  have hreal : (2 * Real.pi * (order : ℝ)) / order =
      2 * Real.pi := by field_simp
  have harg :
      (((2 * Real.pi * (order : ℝ)) / order : ℝ) : ℂ) * Complex.I =
        2 * (Real.pi : ℂ) * Complex.I := by
    rw [hreal]
    push_cast
    rfl
  rw [unitRoot, harg]
  exact Complex.exp_two_pi_mul_I

theorem unitRoot_half {order : Nat} (horder : 0 < order) :
    unitRoot (2 * order) order = -1 := by
  have horder0 : (order : ℝ) ≠ 0 := by positivity
  have hreal : (2 * Real.pi * (order : ℝ)) /
      ((2 * order : Nat) : ℝ) = Real.pi := by
    push_cast
    field_simp
  have harg :
      (((2 * Real.pi * (order : ℝ)) /
        ((2 * order : Nat) : ℝ) : ℝ) : ℂ) * Complex.I =
          (Real.pi : ℂ) * Complex.I := by
    rw [hreal]
  rw [unitRoot, harg]
  exact Complex.exp_pi_mul_I

theorem unitRoot_even (half row frequency : Nat) :
    unitRoot (2 * half) ((2 * row) * frequency) =
      unitRoot half (row * frequency) := by
  rw [show (2 * row) * frequency = 2 * (row * frequency) by ring]
  exact unitRoot_double half (row * frequency)

theorem unitRoot_odd (half row frequency : Nat) :
    unitRoot (2 * half) ((2 * row + 1) * frequency) =
      unitRoot half (row * frequency) * unitRoot (2 * half) frequency := by
  rw [show (2 * row + 1) * frequency =
      2 * (row * frequency) + frequency by ring,
    unitRoot_add, unitRoot_double]

theorem unitRoot_even_shift {half : Nat} (hhalf : 0 < half)
    (row frequency : Nat) :
    unitRoot (2 * half) ((2 * row) * (frequency + half)) =
      unitRoot half (row * frequency) := by
  have hperiod : unitRoot (2 * half) ((2 * half) * row) = 1 := by
    rw [unitRoot_mul_right, unitRoot_order (by omega)]
    simp
  rw [show (2 * row) * (frequency + half) =
      2 * (row * frequency) + (2 * half) * row by ring,
    unitRoot_add, unitRoot_double, hperiod, mul_one]

theorem unitRoot_odd_shift {half : Nat} (hhalf : 0 < half)
    (row frequency : Nat) :
    unitRoot (2 * half) ((2 * row + 1) * (frequency + half)) =
      -(unitRoot half (row * frequency) *
        unitRoot (2 * half) frequency) := by
  have hnegative :
      unitRoot (2 * half) (half * (2 * row + 1)) = -1 := by
    rw [unitRoot_mul_right, unitRoot_half hhalf,
      Odd.neg_one_pow (odd_two_mul_add_one row)]
  rw [show (2 * row + 1) * (frequency + half) =
      (2 * row + 1) * frequency + half * (2 * row + 1) by ring,
    unitRoot_add, unitRoot_odd, hnegative]
  ring

/-- Pair the even and odd summands of a range of twice the length. -/
theorem sum_range_twice {R : Type*} [AddCommMonoid R]
    (f : Nat → R) (length : Nat) :
    ∑ index ∈ Finset.range (2 * length), f index =
      ∑ index ∈ Finset.range length,
        (f (2 * index) + f (2 * index + 1)) := by
  induction length with
  | zero => simp
  | succ length ih =>
      rw [Nat.mul_succ, Finset.sum_range_succ, Finset.sum_range_succ,
        Finset.sum_range_succ, ih]
      simp [add_assoc]

/-- Positive root used by CUDA stage `stageExponent`. -/
noncomputable def positiveTwiddle (stageExponent offset : Nat) : ℂ :=
  unitRoot (width stageExponent) offset

/-- Source-level positive-sign radix-2 algorithm, including the initial
bit-reversal permutation and with no normalization. -/
noncomputable def positiveRadix2Transform {logLength : Nat}
    (source : ExactState logLength) : ExactState logLength :=
  runExactStages positiveTwiddle logLength 0 (bitReversed source)

/-- Direct positive-sign DFT formula, with no normalization. -/
noncomputable def positiveDFT {logLength : Nat}
    (source : ExactState logLength) (frequency : Fin (2 ^ logLength)) : ℂ :=
  ∑ input : Fin (2 ^ logLength), source.value input *
    unitRoot (2 ^ logLength) (input.val * frequency.val)

/-- Pointwise statement of the generic radix-2 permutation/algebra identity.
It is proved for every source in `FactoredSmallQDFTCorrectness`. -/
def Radix2CorrectFor {logLength : Nat}
    (source : ExactState logLength) : Prop :=
  ∀ frequency,
    (positiveRadix2Transform source).value frequency =
      positiveDFT source frequency

/-- Complete typed certificate for one transform line. -/
structure Certificate (logLength : Nat) where
  input : DiskState logLength
  /-- Typed finite-query table.  Only stages and offsets demanded by the
  checked network are semantically relevant; a future raw parser should use
  canonical finite arrays and prove that decoding realizes these lookups. -/
  twiddleDisks : Nat → Nat → ComplexDisk
  stages : List (StageCertificate logLength)

namespace Certificate

def output {logLength : Nat} (certificate : Certificate logLength) :
    DiskState logLength :=
  runStages 0 certificate.input certificate.stages

def check {logLength : Nat} (certificate : Certificate logLength) : Bool :=
  decide (certificate.stages.length = logLength) &&
    checkLinkedStages certificate.twiddleDisks 0 certificate.input
      certificate.stages

theorem checker_sound {logLength : Nat}
    {certificate : Certificate logLength}
    (hcheck : certificate.check = true) :
    certificate.stages.length = logLength ∧
      LinkedStages certificate.twiddleDisks 0 certificate.input
        certificate.stages := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, checkLinkedStages_sound hcheck.2⟩

/-- Application theorem for an arbitrary exact twiddle family. -/
theorem output_contains_transform {logLength : Nat}
    {certificate : Certificate logLength}
    {initial : ExactState logLength}
    {twiddles : Nat → Nat → ℂ}
    (hcheck : certificate.check = true)
    (hinput : StateContains certificate.input initial)
    (htwiddles : TwiddlesContain (logLength := logLength)
      certificate.twiddleDisks twiddles) :
    StateContains certificate.output
      (runExactStages twiddles logLength 0 initial) := by
  rcases checker_sound hcheck with ⟨hlength, hlinked⟩
  have hrun := runStages_contains hlinked hinput htwiddles
  simpa [output, hlength] using hrun

/-- Clean positive-sign transform tie-in.  The bit-reversal permutation and
every transcendental root enclosure remain visible hypotheses. -/
theorem output_contains_positiveRadix2 {logLength : Nat}
    {certificate : Certificate logLength}
    {source : ExactState logLength}
    (hcheck : certificate.check = true)
    (hbitReverse : StateContains certificate.input (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      certificate.twiddleDisks positiveTwiddle) :
    StateContains certificate.output (positiveRadix2Transform source) := by
  simpa [positiveRadix2Transform] using
    (output_contains_transform hcheck hbitReverse hroots)

/-- Compositional direct-DFT corollary parameterized by the pure radix-2
identity.  `FactoredSmallQDFTCorrectness` proves that identity generically and
offers a premise-free wrapper. -/
theorem output_contains_positiveDFT {logLength : Nat}
    {certificate : Certificate logLength}
    {source : ExactState logLength}
    (hcheck : certificate.check = true)
    (hbitReverse : StateContains certificate.input (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      certificate.twiddleDisks positiveTwiddle)
    (hRadix2 : Radix2CorrectFor source) :
    ∀ frequency,
      (certificate.output.value frequency).ContainsComplex
        (positiveDFT source frequency) := by
  have htransform := output_contains_positiveRadix2
    hcheck hbitReverse hroots
  intro frequency
  rw [← hRadix2 frequency]
  exact htransform frequency

end Certificate

end SparkInterval.Dirichlet.FactoredSmallQDFT
