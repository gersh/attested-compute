/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Analysis.Complex.Basic
import SparkInterval.Certificate.Binary64

/-!
# Exact certificates for complex-disk arithmetic

The production GPU kernels represent a complex enclosure by a binary64 centre
and a nonnegative binary64 radius.  After the three words have been decoded,
they are exact rationals.  This module gives that decoded data an independent
Lean meaning and checks the inequalities used by the GPU's disk
multiplication formula using rational arithmetic only.

The checker deliberately says nothing about CUDA, PTX, SASS, a parser, or a
particular run.  Those are separate artifact/refinement edges.  Its soundness
theorem is the reusable arithmetic link: any producer may propose a
`MulCertificate`, but a successful Boolean check proves that its output disk
contains the product of every pair of values contained by its input disks.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-- A complex disk with exactly rational centre and radius.  Binary64 values
are rationals after decoding, so this is also the mathematical wire model. -/
structure ComplexDisk where
  re : ℚ
  im : ℚ
  radius : ℚ
  deriving Repr, DecidableEq, BEq

namespace ComplexDisk

def center (disk : ComplexDisk) : ℂ :=
  ⟨(disk.re : ℝ), (disk.im : ℝ)⟩

/-- Euclidean closed-disk semantics. -/
def ContainsComplex (disk : ComplexDisk) (value : ℂ) : Prop :=
  ‖value - disk.center‖ ≤ (disk.radius : ℝ)

/-- Squared Euclidean norm of the rational centre. -/
def centerNormSq (disk : ComplexDisk) : ℚ :=
  disk.re ^ 2 + disk.im ^ 2

/-- Exact squared distance between `output.center` and the product of the two
input centres. -/
def productCenterErrorSq
    (left right output : ComplexDisk) : ℚ :=
  (left.re * right.re - left.im * right.im - output.re) ^ 2 +
  (left.re * right.im + left.im * right.re - output.im) ^ 2

/-- Exact squared distance between `output.center` and the sum of two input
centres. -/
def sumCenterErrorSq (left right output : ComplexDisk) : ℚ :=
  (left.re + right.re - output.re) ^ 2 +
  (left.im + right.im - output.im) ^ 2

/-- The `ℓ¹` norm of a disk centre.  The CUDA FFT may use this inexpensive
upper bound in place of a square root when constructing a Euclidean-disk
certificate. -/
def centerL1Bound (disk : ComplexDisk) : ℚ :=
  |disk.re| + |disk.im|

/-- The `ℓ¹` norm of the exact centre error in a disk multiplication. -/
def productCenterErrorL1Bound
    (left right output : ComplexDisk) : ℚ :=
  |left.re * right.re - left.im * right.im - output.re| +
  |left.re * right.im + left.im * right.re - output.im|

/-- The `ℓ¹` norm of the exact centre error in a disk addition. -/
def sumCenterErrorL1Bound (left right output : ComplexDisk) : ℚ :=
  |left.re + right.re - output.re| +
  |left.im + right.im - output.im|

private theorem sq_norm_le_l1_sq (x y : ℚ) :
    x ^ 2 + y ^ 2 ≤ (|x| + |y|) ^ 2 := by
  rw [add_sq, sq_abs, sq_abs]
  nlinarith [mul_nonneg (abs_nonneg x) (abs_nonneg y)]

/-- An `ℓ¹` centre bound is a valid squared Euclidean-norm witness. -/
theorem centerNormSq_le_centerL1Bound_sq (disk : ComplexDisk) :
    disk.centerNormSq ≤ disk.centerL1Bound ^ 2 := by
  exact sq_norm_le_l1_sq disk.re disk.im

/-- An `ℓ¹` multiplication-error bound satisfies the squared inequality
required by `MulCertificate.WellFormed`. -/
theorem productCenterErrorSq_le_productCenterErrorL1Bound_sq
    (left right output : ComplexDisk) :
    productCenterErrorSq left right output ≤
      productCenterErrorL1Bound left right output ^ 2 := by
  exact sq_norm_le_l1_sq
    (left.re * right.re - left.im * right.im - output.re)
    (left.re * right.im + left.im * right.re - output.im)

/-- An `ℓ¹` addition-error bound satisfies the squared inequality required by
`AddCertificate.WellFormed`. -/
theorem sumCenterErrorSq_le_sumCenterErrorL1Bound_sq
    (left right output : ComplexDisk) :
    sumCenterErrorSq left right output ≤
      sumCenterErrorL1Bound left right output ^ 2 := by
  exact sq_norm_le_l1_sq
    (left.re + right.re - output.re)
    (left.im + right.im - output.im)

@[simp] theorem center_re (disk : ComplexDisk) : disk.center.re = disk.re := rfl
@[simp] theorem center_im (disk : ComplexDisk) : disk.center.im = disk.im := rfl

theorem center_norm_sq (disk : ComplexDisk) :
    ‖disk.center‖ ^ 2 = (disk.centerNormSq : ℝ) := by
  rw [Complex.sq_norm, Complex.normSq_apply]
  norm_num [center, centerNormSq]
  ring

theorem product_center_error_norm_sq (left right output : ComplexDisk) :
    ‖left.center * right.center - output.center‖ ^ 2 =
      (productCenterErrorSq left right output : ℝ) := by
  rw [Complex.sq_norm, Complex.normSq_apply]
  norm_num [center, productCenterErrorSq, Complex.mul_re, Complex.mul_im,
    Complex.sub_re, Complex.sub_im]
  ring

theorem sum_center_error_norm_sq (left right output : ComplexDisk) :
    ‖left.center + right.center - output.center‖ ^ 2 =
      (sumCenterErrorSq left right output : ℝ) := by
  rw [Complex.sq_norm, Complex.normSq_apply]
  norm_num [center, sumCenterErrorSq, Complex.add_re, Complex.add_im,
    Complex.sub_re, Complex.sub_im]
  ring

private theorem norm_le_of_sq_le_sq {z : ℂ} {bound : ℝ}
    (hbound : 0 ≤ bound) (hsq : ‖z‖ ^ 2 ≤ bound ^ 2) :
    ‖z‖ ≤ bound := by
  nlinarith [norm_nonneg z]

/-! ## Addition witnesses -/

/-- Exact postcondition witness for the disk-addition error formula. -/
structure AddCertificate where
  left : ComplexDisk
  right : ComplexDisk
  output : ComplexDisk
  centerErrorBound : ℚ
  deriving Repr, DecidableEq, BEq

namespace AddCertificate

def WellFormed (certificate : AddCertificate) : Prop :=
  0 ≤ certificate.left.radius ∧
  0 ≤ certificate.right.radius ∧
  0 ≤ certificate.output.radius ∧
  0 ≤ certificate.centerErrorBound ∧
  ComplexDisk.sumCenterErrorSq certificate.left certificate.right
      certificate.output ≤ certificate.centerErrorBound ^ 2 ∧
  certificate.centerErrorBound + certificate.left.radius +
      certificate.right.radius ≤ certificate.output.radius

instance instDecidableWellFormed (certificate : AddCertificate) :
    Decidable certificate.WellFormed := by
  unfold WellFormed
  infer_instance

def check (certificate : AddCertificate) : Bool :=
  decide certificate.WellFormed

theorem check_sound {certificate : AddCertificate}
    (hcheck : certificate.check = true) : certificate.WellFormed :=
  of_decide_eq_true hcheck

/-- A checked output disk contains the exact sum of any values in the two
input disks. This is an arithmetic postcondition theorem, not a statement
about a physical instruction trace. -/
theorem output_contains_add {certificate : AddCertificate} {x y : ℂ}
    (hcheck : certificate.check = true)
    (hx : certificate.left.ContainsComplex x)
    (hy : certificate.right.ContainsComplex y) :
    certificate.output.ContainsComplex (x + y) := by
  rcases check_sound hcheck with ⟨hrx, hry, _, he, hcenterSq, hradius⟩
  have hcenterSq' :
      ‖certificate.left.center + certificate.right.center -
          certificate.output.center‖ ^ 2 ≤
        (certificate.centerErrorBound : ℝ) ^ 2 := by
    rw [ComplexDisk.sum_center_error_norm_sq]
    exact_mod_cast hcenterSq
  have hcenter :
      ‖certificate.left.center + certificate.right.center -
          certificate.output.center‖ ≤
        (certificate.centerErrorBound : ℝ) :=
    norm_le_of_sq_le_sq (by exact_mod_cast he) hcenterSq'
  have hx' : ‖x - certificate.left.center‖ ≤
      (certificate.left.radius : ℝ) := hx
  have hy' : ‖y - certificate.right.center‖ ≤
      (certificate.right.radius : ℝ) := hy
  have hdecomp :
      x + y - certificate.output.center =
        (certificate.left.center + certificate.right.center -
          certificate.output.center) +
        (x - certificate.left.center) +
        (y - certificate.right.center) := by
    ring
  rw [ContainsComplex, hdecomp]
  calc
    ‖(certificate.left.center + certificate.right.center -
          certificate.output.center) +
        (x - certificate.left.center) +
        (y - certificate.right.center)‖
        ≤ ‖certificate.left.center + certificate.right.center -
              certificate.output.center‖ +
            ‖x - certificate.left.center‖ +
            ‖y - certificate.right.center‖ := by
          calc
            _ ≤ ‖(certificate.left.center + certificate.right.center -
                    certificate.output.center) +
                  (x - certificate.left.center)‖ +
                ‖y - certificate.right.center‖ := norm_add_le _ _
            _ ≤ (‖certificate.left.center + certificate.right.center -
                    certificate.output.center‖ +
                  ‖x - certificate.left.center‖) +
                ‖y - certificate.right.center‖ := by
                  gcongr
                  exact norm_add_le _ _
    _ ≤ (certificate.centerErrorBound : ℝ) +
          certificate.left.radius + certificate.right.radius := by linarith
    _ ≤ (certificate.output.radius : ℝ) := by exact_mod_cast hradius

end AddCertificate

/-- Rational witnesses for every upper bound used by directed disk
multiplication.  The three auxiliary bounds need not be tight. -/
structure MulCertificate where
  left : ComplexDisk
  right : ComplexDisk
  output : ComplexDisk
  centerErrorBound : ℚ
  leftCenterNormBound : ℚ
  rightCenterNormBound : ℚ
  deriving Repr, DecidableEq, BEq

namespace MulCertificate

/-- Exact, executable arithmetic obligations.  Squared inequalities avoid
putting square roots or floating-point evaluation in Lean's checker. -/
def WellFormed (certificate : MulCertificate) : Prop :=
  0 ≤ certificate.left.radius ∧
  0 ≤ certificate.right.radius ∧
  0 ≤ certificate.output.radius ∧
  0 ≤ certificate.centerErrorBound ∧
  0 ≤ certificate.leftCenterNormBound ∧
  0 ≤ certificate.rightCenterNormBound ∧
  ComplexDisk.productCenterErrorSq certificate.left certificate.right
      certificate.output ≤ certificate.centerErrorBound ^ 2 ∧
  certificate.left.centerNormSq ≤ certificate.leftCenterNormBound ^ 2 ∧
  certificate.right.centerNormSq ≤ certificate.rightCenterNormBound ^ 2 ∧
  certificate.centerErrorBound +
      certificate.leftCenterNormBound * certificate.right.radius +
      certificate.rightCenterNormBound * certificate.left.radius +
      certificate.left.radius * certificate.right.radius ≤
    certificate.output.radius

instance instDecidableWellFormed (certificate : MulCertificate) :
    Decidable certificate.WellFormed := by
  unfold WellFormed
  infer_instance

/-- Kernel-reducible checker for one disk-multiplication witness. -/
def check (certificate : MulCertificate) : Bool :=
  decide certificate.WellFormed

theorem check_sound {certificate : MulCertificate}
    (hcheck : certificate.check = true) : certificate.WellFormed :=
  of_decide_eq_true hcheck

/-- Golden arithmetic theorem for the exact witness checker.  This is the
same semantic error decomposition used by the CUDA `diskMul` helper: centre rounding error,
`|center(left)| * radius(right)`, `|center(right)| * radius(left)`, and the
radius product are accumulated into the result radius.  It does not assert
that a physical CUDA instruction trace computed the supplied witness. -/
theorem output_contains_mul
    {certificate : MulCertificate} {x y : ℂ}
    (hcheck : certificate.check = true)
    (hx : certificate.left.ContainsComplex x)
    (hy : certificate.right.ContainsComplex y) :
    certificate.output.ContainsComplex (x * y) := by
  have h := check_sound hcheck
  rcases h with
    ⟨hrx, hry, hro, he, hnx, hny, hcenterSq, hleftSq, hrightSq, hradius⟩
  have hcenterSq' :
      ‖certificate.left.center * certificate.right.center -
          certificate.output.center‖ ^ 2 ≤
        (certificate.centerErrorBound : ℝ) ^ 2 := by
    rw [ComplexDisk.product_center_error_norm_sq]
    exact_mod_cast hcenterSq
  have hleftSq' :
      ‖certificate.left.center‖ ^ 2 ≤
        (certificate.leftCenterNormBound : ℝ) ^ 2 := by
    rw [ComplexDisk.center_norm_sq]
    exact_mod_cast hleftSq
  have hrightSq' :
      ‖certificate.right.center‖ ^ 2 ≤
        (certificate.rightCenterNormBound : ℝ) ^ 2 := by
    rw [ComplexDisk.center_norm_sq]
    exact_mod_cast hrightSq
  have hcenter :
      ‖certificate.left.center * certificate.right.center -
          certificate.output.center‖ ≤
        (certificate.centerErrorBound : ℝ) :=
    norm_le_of_sq_le_sq (by exact_mod_cast he) hcenterSq'
  have hleft : ‖certificate.left.center‖ ≤
      (certificate.leftCenterNormBound : ℝ) :=
    norm_le_of_sq_le_sq (by exact_mod_cast hnx) hleftSq'
  have hright : ‖certificate.right.center‖ ≤
      (certificate.rightCenterNormBound : ℝ) :=
    norm_le_of_sq_le_sq (by exact_mod_cast hny) hrightSq'
  have hrx' : 0 ≤ (certificate.left.radius : ℝ) := by exact_mod_cast hrx
  have hry' : 0 ≤ (certificate.right.radius : ℝ) := by exact_mod_cast hry
  have hx' : ‖x - certificate.left.center‖ ≤
      (certificate.left.radius : ℝ) := hx
  have hy' : ‖y - certificate.right.center‖ ≤
      (certificate.right.radius : ℝ) := hy
  have hleftError :
      ‖certificate.left.center‖ * ‖y - certificate.right.center‖ ≤
        (certificate.leftCenterNormBound : ℝ) *
          certificate.right.radius :=
    mul_le_mul hleft hy' (norm_nonneg _) (by exact_mod_cast hnx)
  have hrightError :
      ‖x - certificate.left.center‖ * ‖certificate.right.center‖ ≤
        (certificate.left.radius : ℝ) *
          certificate.rightCenterNormBound :=
    mul_le_mul hx' hright (norm_nonneg _) hrx'
  have hradiusError :
      ‖x - certificate.left.center‖ * ‖y - certificate.right.center‖ ≤
        (certificate.left.radius : ℝ) * certificate.right.radius :=
    mul_le_mul hx' hy' (norm_nonneg _) hrx'
  have hdecomp :
      x * y - certificate.output.center =
        (certificate.left.center * certificate.right.center -
            certificate.output.center) +
        certificate.left.center * (y - certificate.right.center) +
        (x - certificate.left.center) * certificate.right.center +
        (x - certificate.left.center) * (y - certificate.right.center) := by
    ring
  rw [ContainsComplex, hdecomp]
  calc
    ‖(certificate.left.center * certificate.right.center -
          certificate.output.center) +
        certificate.left.center * (y - certificate.right.center) +
        (x - certificate.left.center) * certificate.right.center +
        (x - certificate.left.center) * (y - certificate.right.center)‖
        ≤ ‖certificate.left.center * certificate.right.center -
              certificate.output.center‖ +
            ‖certificate.left.center * (y - certificate.right.center)‖ +
            ‖(x - certificate.left.center) * certificate.right.center‖ +
            ‖(x - certificate.left.center) *
              (y - certificate.right.center)‖ := by
          calc
            _ ≤ ‖(certificate.left.center * certificate.right.center -
                    certificate.output.center) +
                  certificate.left.center * (y - certificate.right.center) +
                  (x - certificate.left.center) *
                    certificate.right.center‖ +
                ‖(x - certificate.left.center) *
                  (y - certificate.right.center)‖ := norm_add_le _ _
            _ ≤ (‖certificate.left.center * certificate.right.center -
                    certificate.output.center‖ +
                  ‖certificate.left.center *
                    (y - certificate.right.center)‖ +
                  ‖(x - certificate.left.center) *
                    certificate.right.center‖) +
                ‖(x - certificate.left.center) *
                  (y - certificate.right.center)‖ := by
                    gcongr
                    calc
                      _ ≤ ‖(certificate.left.center * certificate.right.center -
                              certificate.output.center) +
                            certificate.left.center *
                              (y - certificate.right.center)‖ +
                          ‖(x - certificate.left.center) *
                            certificate.right.center‖ := norm_add_le _ _
                      _ ≤ (‖certificate.left.center * certificate.right.center -
                              certificate.output.center‖ +
                            ‖certificate.left.center *
                              (y - certificate.right.center)‖) +
                          ‖(x - certificate.left.center) *
                            certificate.right.center‖ := by
                              gcongr
                              exact norm_add_le _ _
            _ = _ := by ring
    _ = ‖certificate.left.center * certificate.right.center -
              certificate.output.center‖ +
            ‖certificate.left.center‖ *
              ‖y - certificate.right.center‖ +
            ‖x - certificate.left.center‖ *
              ‖certificate.right.center‖ +
            ‖x - certificate.left.center‖ *
              ‖y - certificate.right.center‖ := by
          simp only [Complex.norm_mul]
    _ ≤ (certificate.centerErrorBound : ℝ) +
            certificate.leftCenterNormBound * certificate.right.radius +
            certificate.rightCenterNormBound * certificate.left.radius +
            certificate.left.radius * certificate.right.radius := by
          nlinarith
    _ ≤ (certificate.output.radius : ℝ) := by exact_mod_cast hradius

end MulCertificate

/-! ## Exact binary64 wire decoding -/

/-- The three raw binary64 words used by the C++/CUDA wire format. -/
structure Raw where
  reBits : Nat
  imBits : Nat
  radiusBits : Nat
  deriving Repr, DecidableEq, BEq

namespace Raw

/-- Decode every finite binary64 word to its exact rational value.  Positivity
of the radius is intentionally checked by the arithmetic certificate rather
than hidden in this parser. -/
def decode (raw : Raw) : Option ComplexDisk := do
  let re ← Binary64.decodeFinite raw.reBits
  let im ← Binary64.decodeFinite raw.imBits
  let radius ← Binary64.decodeFinite raw.radiusBits
  pure ⟨re, im, radius⟩

end Raw

/-- Wire-level form of one disk-addition witness. -/
structure RawAddCertificate where
  left : Raw
  right : Raw
  output : Raw
  centerErrorBoundBits : Nat
  deriving Repr, DecidableEq, BEq

namespace RawAddCertificate

def decode (raw : RawAddCertificate) : Option AddCertificate := do
  let left ← raw.left.decode
  let right ← raw.right.decode
  let output ← raw.output.decode
  let centerErrorBound ← Binary64.decodeFinite raw.centerErrorBoundBits
  pure { left, right, output, centerErrorBound }

def check (raw : RawAddCertificate) : Bool :=
  match raw.decode with
  | none => false
  | some certificate => certificate.check

def Validated (raw : RawAddCertificate) : Prop :=
  ∃ certificate : AddCertificate,
    raw.decode = some certificate ∧ certificate.WellFormed

theorem check_sound {raw : RawAddCertificate} (hcheck : raw.check = true) :
    raw.Validated := by
  unfold check at hcheck
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some certificate =>
      exact ⟨certificate, hdecode, AddCertificate.check_sound (by
        simpa [hdecode] using hcheck)⟩

theorem output_contains_add {raw : RawAddCertificate}
    {certificate : AddCertificate}
    (hcheck : raw.check = true)
    (hdecode : raw.decode = some certificate)
    {x y : ℂ}
    (hx : certificate.left.ContainsComplex x)
    (hy : certificate.right.ContainsComplex y) :
    certificate.output.ContainsComplex (x + y) := by
  have htyped : certificate.check = true := by
    unfold check at hcheck
    simpa [hdecode] using hcheck
  exact AddCertificate.output_contains_add htyped hx hy

end RawAddCertificate

/-- Wire-level form of a multiplication witness.  Auxiliary norm/error bounds
are binary64 words as well, so successful decoding leaves no floating value
with an approximate or host-language meaning. -/
structure RawMulCertificate where
  left : Raw
  right : Raw
  output : Raw
  centerErrorBoundBits : Nat
  leftCenterNormBoundBits : Nat
  rightCenterNormBoundBits : Nat
  deriving Repr, DecidableEq, BEq

namespace RawMulCertificate

def decode (raw : RawMulCertificate) : Option MulCertificate := do
  let left ← raw.left.decode
  let right ← raw.right.decode
  let output ← raw.output.decode
  let centerErrorBound ← Binary64.decodeFinite raw.centerErrorBoundBits
  let leftCenterNormBound ←
    Binary64.decodeFinite raw.leftCenterNormBoundBits
  let rightCenterNormBound ←
    Binary64.decodeFinite raw.rightCenterNormBoundBits
  pure {
    left := left
    right := right
    output := output
    centerErrorBound := centerErrorBound
    leftCenterNormBound := leftCenterNormBound
    rightCenterNormBound := rightCenterNormBound
  }

/-- One fail-closed Boolean check covers exact decoding and all rational
arithmetic inequalities. -/
def check (raw : RawMulCertificate) : Bool :=
  match raw.decode with
  | none => false
  | some certificate => certificate.check

/-- Typed result recovered from an accepted wire witness. -/
def Validated (raw : RawMulCertificate) : Prop :=
  ∃ certificate : MulCertificate,
    raw.decode = some certificate ∧ certificate.WellFormed

theorem check_sound {raw : RawMulCertificate} (hcheck : raw.check = true) :
    raw.Validated := by
  unfold check at hcheck
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some certificate =>
      exact ⟨certificate, hdecode, MulCertificate.check_sound (by
        simpa [hdecode] using hcheck)⟩

/-- Application theorem for exact wire words.  Once the decoded input disks
are known to contain `x` and `y`, the decoded output encloses `x*y`. -/
theorem output_contains_mul {raw : RawMulCertificate}
    {certificate : MulCertificate}
    (hcheck : raw.check = true)
    (hdecode : raw.decode = some certificate)
    {x y : ℂ}
    (hx : certificate.left.ContainsComplex x)
    (hy : certificate.right.ContainsComplex y) :
    certificate.output.ContainsComplex (x * y) := by
  have htyped : certificate.check = true := by
    unfold check at hcheck
    simpa [hdecode] using hcheck
  exact MulCertificate.output_contains_mul
    (certificate := certificate) htyped hx hy

end RawMulCertificate

end ComplexDisk

end SparkInterval.Certified
