/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.IntervalOpsSound

/-!
# Sign-quadrant real interval multiplication

The large-q Dirichlet CUDA path avoids evaluating all four endpoint products
when one or both input intervals have a known sign.  This module specifies
that conditional endpoint selection over exact real numbers and proves that
it is exactly the ordinary four-corner interval product.

This is the algebraic justification for the optimization.  It does not claim
that CUDA comparisons or directed binary64 instructions refine the tests and
products below; those compiler/ISA obligations remain separate.
-/

set_option autoImplicit false

namespace SparkInterval.RealInterval

/-- Lower endpoint selected by the production sign-quadrant decision tree. -/
noncomputable def signQuadrantMulLo (X Y : RealInterval) : ℝ :=
  if 0 ≤ X.lo then
    if 0 ≤ Y.lo then
      X.lo * Y.lo
    else if Y.hi ≤ 0 then
      X.hi * Y.lo
    else
      X.hi * Y.lo
  else if X.hi ≤ 0 then
    if 0 ≤ Y.lo then
      X.lo * Y.hi
    else if Y.hi ≤ 0 then
      X.hi * Y.hi
    else
      X.lo * Y.hi
  else if 0 ≤ Y.lo then
    X.lo * Y.hi
  else if Y.hi ≤ 0 then
    X.hi * Y.lo
  else
    Min.min (X.lo * Y.hi) (X.hi * Y.lo)

/-- Upper endpoint selected by the production sign-quadrant decision tree. -/
noncomputable def signQuadrantMulHi (X Y : RealInterval) : ℝ :=
  if 0 ≤ X.lo then
    if 0 ≤ Y.lo then
      X.hi * Y.hi
    else if Y.hi ≤ 0 then
      X.lo * Y.hi
    else
      X.hi * Y.hi
  else if X.hi ≤ 0 then
    if 0 ≤ Y.lo then
      X.hi * Y.lo
    else if Y.hi ≤ 0 then
      X.lo * Y.lo
    else
      X.lo * Y.lo
  else if 0 ≤ Y.lo then
    X.hi * Y.hi
  else if Y.hi ≤ 0 then
    X.lo * Y.lo
  else
    Max.max (X.lo * Y.lo) (X.hi * Y.hi)

theorem signQuadrantMulLo_eq_mul_lo (X Y : RealInterval) :
    signQuadrantMulLo X Y = (X.mul Y).lo := by
  unfold signQuadrantMulLo RealInterval.mul
  simp only [min_def]
  split_ifs <;>
    simp_all only [not_le] <;>
    nlinarith [X.valid, Y.valid]

theorem signQuadrantMulHi_eq_mul_hi (X Y : RealInterval) :
    signQuadrantMulHi X Y = (X.mul Y).hi := by
  unfold signQuadrantMulHi RealInterval.mul
  simp only [max_def]
  split_ifs <;>
    simp_all only [not_le] <;>
    nlinarith [X.valid, Y.valid]

/-- Exact interval returned by the optimized endpoint decision tree. -/
noncomputable def signQuadrantMul (X Y : RealInterval) : RealInterval where
  lo := signQuadrantMulLo X Y
  hi := signQuadrantMulHi X Y
  valid := by
    rw [signQuadrantMulLo_eq_mul_lo, signQuadrantMulHi_eq_mul_hi]
    exact (X.mul Y).valid

/-- The optimized decision tree is extensionally the tight four-corner
interval product. -/
theorem signQuadrantMul_eq_mul (X Y : RealInterval) :
    signQuadrantMul X Y = X.mul Y := by
  cases X with
  | mk xlo xhi hx =>
      cases Y with
      | mk ylo yhi hy =>
          simp only [signQuadrantMul]
          congr
          · exact
              signQuadrantMulLo_eq_mul_lo
                ⟨xlo, xhi, hx⟩ ⟨ylo, yhi, hy⟩
          · exact
              signQuadrantMulHi_eq_mul_hi
                ⟨xlo, xhi, hx⟩ ⟨ylo, yhi, hy⟩

/-- Consequently it contains every exact product of contained inputs. -/
theorem signQuadrantMul_contains {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (signQuadrantMul X Y).Contains (x * y) := by
  rw [signQuadrantMul_eq_mul]
  exact mul_contains hx hy

/-! ## Per-product directed rounding

CUDA rounds each selected endpoint product immediately rather than first
constructing an exact-real hull.  The following model abstracts the two
directed operations only by their defining inequalities. -/

noncomputable def directedSignQuadrantMulLo
    (roundDown : ℝ → ℝ) (X Y : RealInterval) : ℝ :=
  if 0 ≤ X.lo then
    if 0 ≤ Y.lo then
      roundDown (X.lo * Y.lo)
    else if Y.hi ≤ 0 then
      roundDown (X.hi * Y.lo)
    else
      roundDown (X.hi * Y.lo)
  else if X.hi ≤ 0 then
    if 0 ≤ Y.lo then
      roundDown (X.lo * Y.hi)
    else if Y.hi ≤ 0 then
      roundDown (X.hi * Y.hi)
    else
      roundDown (X.lo * Y.hi)
  else if 0 ≤ Y.lo then
    roundDown (X.lo * Y.hi)
  else if Y.hi ≤ 0 then
    roundDown (X.hi * Y.lo)
  else
    Min.min
      (roundDown (X.lo * Y.hi))
      (roundDown (X.hi * Y.lo))

noncomputable def directedSignQuadrantMulHi
    (roundUp : ℝ → ℝ) (X Y : RealInterval) : ℝ :=
  if 0 ≤ X.lo then
    if 0 ≤ Y.lo then
      roundUp (X.hi * Y.hi)
    else if Y.hi ≤ 0 then
      roundUp (X.lo * Y.hi)
    else
      roundUp (X.hi * Y.hi)
  else if X.hi ≤ 0 then
    if 0 ≤ Y.lo then
      roundUp (X.hi * Y.lo)
    else if Y.hi ≤ 0 then
      roundUp (X.lo * Y.lo)
    else
      roundUp (X.lo * Y.lo)
  else if 0 ≤ Y.lo then
    roundUp (X.hi * Y.hi)
  else if Y.hi ≤ 0 then
    roundUp (X.lo * Y.lo)
  else
    Max.max
      (roundUp (X.lo * Y.lo))
      (roundUp (X.hi * Y.hi))

theorem directedSignQuadrantMulLo_le
    (roundDown : ℝ → ℝ) (hround : ∀ value, roundDown value ≤ value)
    (X Y : RealInterval) :
    directedSignQuadrantMulLo roundDown X Y ≤
      signQuadrantMulLo X Y := by
  unfold directedSignQuadrantMulLo signQuadrantMulLo
  split_ifs <;>
    first
    | exact hround _
    | exact min_le_min (hround _) (hround _)

theorem le_directedSignQuadrantMulHi
    (roundUp : ℝ → ℝ) (hround : ∀ value, value ≤ roundUp value)
    (X Y : RealInterval) :
    signQuadrantMulHi X Y ≤
      directedSignQuadrantMulHi roundUp X Y := by
  unfold directedSignQuadrantMulHi signQuadrantMulHi
  split_ifs <;>
    first
    | exact hround _
    | exact max_le_max (hround _) (hround _)

/-- The production-shaped endpoint selection with an abstract directed
rounding operation at every selected product. -/
noncomputable def directedSignQuadrantMul
    (roundDown roundUp : ℝ → ℝ)
    (hdown : ∀ value, roundDown value ≤ value)
    (hup : ∀ value, value ≤ roundUp value)
    (X Y : RealInterval) : RealInterval where
  lo := directedSignQuadrantMulLo roundDown X Y
  hi := directedSignQuadrantMulHi roundUp X Y
  valid := by
    calc
      directedSignQuadrantMulLo roundDown X Y ≤
          signQuadrantMulLo X Y :=
        directedSignQuadrantMulLo_le roundDown hdown X Y
      _ = (X.mul Y).lo := signQuadrantMulLo_eq_mul_lo X Y
      _ ≤ (X.mul Y).hi := (X.mul Y).valid
      _ = signQuadrantMulHi X Y :=
        (signQuadrantMulHi_eq_mul_hi X Y).symm
      _ ≤ directedSignQuadrantMulHi roundUp X Y :=
        le_directedSignQuadrantMulHi roundUp hup X Y

/-- Per-product directed rounding preserves enclosure in every sign case. -/
theorem directedSignQuadrantMul_contains
    (roundDown roundUp : ℝ → ℝ)
    (hdown : ∀ value, roundDown value ≤ value)
    (hup : ∀ value, value ≤ roundUp value)
    {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (directedSignQuadrantMul roundDown roundUp hdown hup X Y).Contains
      (x * y) := by
  have hproduct := mul_contains hx hy
  constructor
  · exact
      (directedSignQuadrantMulLo_le roundDown hdown X Y).trans
        ((signQuadrantMulLo_eq_mul_lo X Y).symm ▸ hproduct.1)
  · exact
      ((signQuadrantMulHi_eq_mul_hi X Y).symm ▸ hproduct.2).trans
        (le_directedSignQuadrantMulHi roundUp hup X Y)

end SparkInterval.RealInterval
