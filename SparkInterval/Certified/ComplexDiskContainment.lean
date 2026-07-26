/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDisk

/-!
# Exact containment certificates for rational complex disks

The PT21 whole-transform qualification compares two emitted disks with the
exact dyadic obligation

```
radius(inner) ≤ radius(outer)
```

and

```
|center(inner) - center(outer)|²
  ≤ (radius(outer) - radius(inner))².
```

This module proves that those arithmetic inequalities really imply set
containment.  The checker operates on exact rationals and therefore applies
directly after finite binary64 or double-double words have been decoded.

It does not claim that a CUDA instruction trace produced either disk, that a
particular transform is mathematically valid, or that a physical run checked
every output.  Those are separate refinement and artifact boundaries.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

namespace ComplexDisk

/-- Exact squared distance between two rational disk centres. -/
def centerDistanceSq (inner outer : ComplexDisk) : ℚ :=
  (inner.re - outer.re) ^ 2 + (inner.im - outer.im) ^ 2

theorem center_distance_norm_sq (inner outer : ComplexDisk) :
    ‖inner.center - outer.center‖ ^ 2 =
      (centerDistanceSq inner outer : ℝ) := by
  rw [Complex.sq_norm, Complex.normSq_apply]
  norm_num [center, centerDistanceSq, Complex.sub_re, Complex.sub_im]
  ring

private theorem norm_le_of_sq_le_sq {z : ℂ} {bound : ℝ}
    (hbound : 0 ≤ bound) (hsq : ‖z‖ ^ 2 ≤ bound ^ 2) :
    ‖z‖ ≤ bound := by
  nlinarith [norm_nonneg z]

/-! ## Exact containment checker -/

/-- A proposed proof that every value in `inner` is also in `outer`. -/
structure ContainmentCertificate where
  inner : ComplexDisk
  outer : ComplexDisk
  deriving Repr, DecidableEq, BEq

namespace ContainmentCertificate

/-- The exact squared-distance criterion used by the PT21 qualification
runner.  Explicit nonnegativity makes the disk semantics non-vacuous and
allows the squared inequality to be unsquared soundly. -/
def WellFormed (certificate : ContainmentCertificate) : Prop :=
  0 ≤ certificate.inner.radius ∧
  0 ≤ certificate.outer.radius ∧
  0 ≤ certificate.outer.radius - certificate.inner.radius ∧
  ComplexDisk.centerDistanceSq certificate.inner certificate.outer ≤
    (certificate.outer.radius - certificate.inner.radius) ^ 2

instance instDecidableWellFormed
    (certificate : ContainmentCertificate) :
    Decidable certificate.WellFormed := by
  unfold WellFormed
  infer_instance

/-- Kernel-reducible exact-rational containment checker. -/
def check (certificate : ContainmentCertificate) : Bool :=
  decide certificate.WellFormed

theorem check_sound {certificate : ContainmentCertificate}
    (hcheck : certificate.check = true) :
    certificate.WellFormed :=
  of_decide_eq_true hcheck

/-- The squared arithmetic criterion implies actual closed-disk
containment. -/
theorem outer_contains_of_inner_contains
    {certificate : ContainmentCertificate} {value : ℂ}
    (hcheck : certificate.check = true)
    (hvalue : certificate.inner.ContainsComplex value) :
    certificate.outer.ContainsComplex value := by
  rcases check_sound hcheck with
    ⟨hinnerRadius, houterRadius, hradiusDifference, hdistanceSq⟩
  have hdistanceSqReal :
      ‖certificate.inner.center - certificate.outer.center‖ ^ 2 ≤
        ((certificate.outer.radius -
          certificate.inner.radius : ℚ) : ℝ) ^ 2 := by
    rw [ComplexDisk.center_distance_norm_sq]
    exact_mod_cast hdistanceSq
  have hdistance :
      ‖certificate.inner.center - certificate.outer.center‖ ≤
        ((certificate.outer.radius -
          certificate.inner.radius : ℚ) : ℝ) :=
    norm_le_of_sq_le_sq (by exact_mod_cast hradiusDifference)
      hdistanceSqReal
  have hdecomposition :
      value - certificate.outer.center =
        (value - certificate.inner.center) +
          (certificate.inner.center - certificate.outer.center) := by
    ring
  rw [ContainsComplex, hdecomposition]
  calc
    ‖(value - certificate.inner.center) +
        (certificate.inner.center - certificate.outer.center)‖
        ≤ ‖value - certificate.inner.center‖ +
          ‖certificate.inner.center - certificate.outer.center‖ :=
      norm_add_le _ _
    _ ≤ (certificate.inner.radius : ℝ) +
          ((certificate.outer.radius -
            certificate.inner.radius : ℚ) : ℝ) :=
      add_le_add hvalue hdistance
    _ = (certificate.outer.radius : ℝ) := by
      norm_num

end ContainmentCertificate

end ComplexDisk

end SparkInterval.Certified
