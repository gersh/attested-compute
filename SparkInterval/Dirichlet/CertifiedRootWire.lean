/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.Binary64
import SparkInterval.Dirichlet.CertifiedBluesteinRootBridge

/-!
# Total raw-binary64 checker for certified DFT roots

This module turns the rational root proof into a small certificate checker.
Each production complex rectangle is supplied as four raw binary64 words.
The checker:

1. decodes both coordinate intervals to exact rationals, rejecting NaNs,
   infinities, out-of-range words, and reversed endpoints;
2. runs the fully checked rational root generator; and
3. checks four rational endpoint inequalities.

A successful `Bool` proves that the decoded production rectangle contains the
exact DFT root.  The checker does not call `Float`, MPFR, native code, CUDA, or
an external oracle.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedRootWire

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.CertifiedBluesteinRootBridge

/-- Four raw binary64 endpoints in the production complex-rectangle layout. -/
structure RawComplexBox where
  re : RawInterval
  im : RawInterval
  deriving BEq, DecidableEq, Repr

namespace RawComplexBox

/-- Decode a production rectangle to exact rational coordinates. -/
def decodeFinite (raw : RawComplexBox) : Option ComplexRect := do
  let re ← raw.re.decodeFinite
  let im ← raw.im.decodeFinite
  pure { re, im }

theorem decodeFinite_isValid
    {raw : RawComplexBox} {rect : ComplexRect}
    (hdecode : raw.decodeFinite = some rect) :
    rect.IsValid := by
  unfold decodeFinite at hdecode
  cases hre : raw.re.decodeFinite with
  | none => simp [hre] at hdecode
  | some re =>
      cases him : raw.im.decodeFinite with
      | none => simp [hre, him] at hdecode
      | some im =>
          simp [hre, him] at hdecode
          subst rect
          exact
            ⟨RawInterval.decodeFinite_isValid hre,
              RawInterval.decodeFinite_isValid him⟩

end RawComplexBox

/-- Exact rational endpoint comparison used by the executable checker. -/
def RationallyEncloses (outer inner : ComplexRect) : Prop :=
  outer.re.lo ≤ inner.re.lo ∧
  inner.re.hi ≤ outer.re.hi ∧
  outer.im.lo ≤ inner.im.lo ∧
  inner.im.hi ≤ outer.im.hi

instance (outer inner : ComplexRect) :
    Decidable (RationallyEncloses outer inner) := by
  unfold RationallyEncloses
  infer_instance

/-- Total checker for one raw production root box. -/
def check
    (workPrecision outputPrecision order exponent : Nat)
    (raw : RawComplexBox) : Bool :=
  match raw.decodeFinite,
      CertifiedRootTable.rootRectFast?
        workPrecision outputPrecision order exponent with
  | some outer, some inner => decide (RationallyEncloses outer inner)
  | _, _ => false

/-- Successful checking exposes the decoded and exact rational rectangles and
the four endpoint inequalities between them. -/
theorem check_eq_true
    {workPrecision outputPrecision order exponent : Nat}
    {raw : RawComplexBox}
    (hcheck :
      check workPrecision outputPrecision order exponent raw = true) :
    ∃ outer inner : ComplexRect,
      raw.decodeFinite = some outer ∧
      CertifiedRootTable.rootRectFast?
          workPrecision outputPrecision order exponent = some inner ∧
      RationallyEncloses outer inner := by
  unfold check at hcheck
  cases houter : raw.decodeFinite with
  | none => simp [houter] at hcheck
  | some outer =>
      cases hinner :
          CertifiedRootTable.rootRectFast?
            workPrecision outputPrecision order exponent with
      | none => simp [houter, hinner] at hcheck
      | some inner =>
          simp only [houter, hinner, decide_eq_true_eq] at hcheck
          exact ⟨outer, inner, rfl, rfl, hcheck⟩

/-- A valid rational rectangle interpreted as a mathematical real rectangle. -/
noncomputable def toComplexInterval
    (rect : ComplexRect) (hvalid : rect.IsValid) : ComplexInterval where
  re :=
    { lo := (rect.re.lo : ℝ)
      hi := (rect.re.hi : ℝ)
      valid := Rat.cast_le.mpr hvalid.1 }
  im :=
    { lo := (rect.im.lo : ℝ)
      hi := (rect.im.hi : ℝ)
      valid := Rat.cast_le.mpr hvalid.2 }

theorem rationallyEncloses_to_enclosesRect
    {outer inner : ComplexRect}
    (hvalid : outer.IsValid)
    (hencloses : RationallyEncloses outer inner) :
    EnclosesRect (toComplexInterval outer hvalid) inner := by
  exact
    ⟨Rat.cast_le.mpr hencloses.1,
      Rat.cast_le.mpr hencloses.2.1,
      Rat.cast_le.mpr hencloses.2.2.1,
      Rat.cast_le.mpr hencloses.2.2.2⟩

/-- Main wire theorem: a successful raw-word check produces a valid decoded
box carrying the exact `FastRootCertificate` consumed by the Bluestein root
bridge. -/
theorem check_sound
    {workPrecision outputPrecision order exponent : Nat}
    {raw : RawComplexBox}
    (hcheck :
      check workPrecision outputPrecision order exponent raw = true) :
    ∃ (outer : ComplexRect) (hvalid : outer.IsValid),
      raw.decodeFinite = some outer ∧
      FastRootCertificate workPrecision outputPrecision order exponent
        (toComplexInterval outer hvalid) := by
  rcases check_eq_true hcheck with
    ⟨outer, inner, houter, hinner, hencloses⟩
  let hvalid := RawComplexBox.decodeFinite_isValid houter
  refine ⟨outer, hvalid, houter, ?_⟩
  exact
    ⟨inner, hinner,
      rationallyEncloses_to_enclosesRect hvalid hencloses⟩

/-- Human-facing consequence: the valid decoded binary64 rectangle exposed
by a successful check contains the exact positive root. -/
theorem checked_box_contains
    {workPrecision outputPrecision order exponent : Nat}
    {raw : RawComplexBox}
    (hcheck :
      check workPrecision outputPrecision order exponent raw = true) :
    ∃ (outer : ComplexRect) (hvalid : outer.IsValid),
      raw.decodeFinite = some outer ∧
      (toComplexInterval outer hvalid).Contains
        (unitRoot order exponent) := by
  rcases check_sound hcheck with
    ⟨outer, hvalid, hdecode, hcertificate⟩
  exact
    ⟨outer, hvalid, hdecode,
      fastRootCertificate_contains hcertificate⟩

end SparkInterval.Dirichlet.CertifiedRootWire
