import SparkInterval.Basic

/-!
# Closed real intervals

This file defines nonempty, closed intervals over the mathematical real numbers
and their containment relation.  No executable floating-point operation occurs
in these definitions.
-/

set_option autoImplicit false

namespace SparkInterval

/-- A nonempty closed interval with real endpoints. -/
structure RealInterval where
  lo : ℝ
  hi : ℝ
  valid : lo ≤ hi

namespace RealInterval

/-- `I.Contains x` means that `x` lies between both closed endpoints of `I`. -/
def Contains (I : RealInterval) (x : ℝ) : Prop :=
  I.lo ≤ x ∧ x ≤ I.hi

/-- The singleton interval containing an exact real constant. -/
def point (x : ℝ) : RealInterval :=
  ⟨x, x, le_rfl⟩

@[simp] theorem point_lo (x : ℝ) : (point x).lo = x := rfl

@[simp] theorem point_hi (x : ℝ) : (point x).hi = x := rfl

@[simp] theorem point_contains_iff {x y : ℝ} : (point x).Contains y ↔ y = x := by
  constructor
  · intro h
    exact le_antisymm h.2 h.1
  · rintro rfl
    exact ⟨le_rfl, le_rfl⟩

@[simp] theorem point_contains (x : ℝ) : (point x).Contains x := by
  simp

theorem contains_lo (I : RealInterval) : I.Contains I.lo :=
  ⟨le_rfl, I.valid⟩

theorem contains_hi (I : RealInterval) : I.Contains I.hi :=
  ⟨I.valid, le_rfl⟩

theorem contains_iff_mem_Icc {I : RealInterval} {x : ℝ} :
    I.Contains x ↔ x ∈ Set.Icc I.lo I.hi :=
  Iff.rfl

/-- An interval excludes zero exactly when it lies strictly on one side of it. -/
def ExcludesZero (I : RealInterval) : Prop :=
  I.hi < 0 ∨ 0 < I.lo

theorem excludesZero_of_contains {I : RealInterval} {x : ℝ}
    (hI : I.ExcludesZero) (hx : I.Contains x) : x ≠ 0 := by
  rcases hI with hneg | hpos
  · exact ne_of_lt (hx.2.trans_lt hneg)
  · exact ne_of_gt (hpos.trans_le hx.1)

end RealInterval

end SparkInterval
