/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Analysis.SpecialFunctions.Trigonometric.Bounds

/-!
# Fixed-point phase error for the windowed zeta campaign

The CUDA phase anchor stores the nearest Q192 turn to
`log (n * sqrt pi) / (2*pi)`, multiplies that integer modulo `2^192` by the
integral window centre, and evaluates directed sine/cosine polynomials.  This
module proves the representation-independent part of that argument: nearest
fixed-point storage contributes at most `pi * height / 2^192` radians, and the
sine and cosine errors are no larger.

The modular limb implementation and the directed polynomial trace still need
their byte-level execution certificate.  No execution or analytic-source
axiom is introduced here.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.FixedPhase

/-- Dividing a nearest scaled-integer enclosure by a positive scale. -/
theorem nearestScaled_error {alpha q scale : ℝ} (hscale : 0 < scale)
    (hnearest : |alpha * scale - q| ≤ 1 / 2) :
    |alpha - q / scale| ≤ 1 / (2 * scale) := by
  have hidentity : alpha - q / scale = (alpha * scale - q) / scale := by
    field_simp
  rw [hidentity, abs_div, abs_of_pos hscale]
  apply (div_le_iff₀ hscale).2
  rw [show 1 / (2 * scale) * scale = 1 / 2 by field_simp]
  exact hnearest

/-- Angular error after multiplying a nearest fixed-point turn by an
integral nonnegative height. -/
theorem angular_error {alpha q scale height : ℝ}
    (hscale : 0 < scale) (hheight : 0 ≤ height)
    (hnearest : |alpha * scale - q| ≤ 1 / 2) :
    |2 * Real.pi * height * alpha -
        2 * Real.pi * height * (q / scale)| ≤
      Real.pi * height / scale := by
  have hcoefficient : 0 ≤ 2 * Real.pi * height := by positivity
  calc
    |2 * Real.pi * height * alpha -
        2 * Real.pi * height * (q / scale)| =
        (2 * Real.pi * height) * |alpha - q / scale| := by
          rw [← mul_sub, abs_mul, abs_of_nonneg hcoefficient]
    _ ≤ (2 * Real.pi * height) * (1 / (2 * scale)) :=
      mul_le_mul_of_nonneg_left (nearestScaled_error hscale hnearest)
        hcoefficient
    _ = Real.pi * height / scale := by field_simp

/-- Sine inherits the fixed-point angular error because real sine is
one-Lipschitz. -/
theorem sin_fixedPoint_error {alpha q scale height : ℝ}
    (hscale : 0 < scale) (hheight : 0 ≤ height)
    (hnearest : |alpha * scale - q| ≤ 1 / 2) :
    |Real.sin (2 * Real.pi * height * alpha) -
        Real.sin (2 * Real.pi * height * (q / scale))| ≤
      Real.pi * height / scale :=
  (Real.abs_sin_sub_sin_le _ _).trans
    (angular_error hscale hheight hnearest)

/-- Cosine inherits the same fixed-point angular error. -/
theorem cos_fixedPoint_error {alpha q scale height : ℝ}
    (hscale : 0 < scale) (hheight : 0 ≤ height)
    (hnearest : |alpha * scale - q| ≤ 1 / 2) :
    |Real.cos (2 * Real.pi * height * alpha) -
        Real.cos (2 * Real.pi * height * (q / scale))| ≤
      Real.pi * height / scale :=
  (Real.abs_cos_sub_cos_le _ _).trans
    (angular_error hscale hheight hnearest)

/-- The exact Q192 scale used by the production kernel. -/
def q192Scale : ℝ := (2 : ℝ) ^ 192

theorem q192Scale_pos : 0 < q192Scale := by
  simp [q192Scale]

end SparkInterval.Zeta.FixedPhase
