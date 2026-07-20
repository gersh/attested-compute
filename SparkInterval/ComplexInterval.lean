import SparkInterval.IntervalOpsSound

/-!
# Closed complex rectangles

This file lifts the exact real-interval foundation to rectangular enclosures
of complex numbers.  The real and imaginary components are enclosed
independently, and every operation is assembled from already-proved
`RealInterval` operations.

Only polynomial operations are provided here.  In particular, this module
does not assume or postulate sound complex division or transcendental
functions.
-/

set_option autoImplicit false

namespace SparkInterval

/-- A closed rectangle in `ℂ`, represented by intervals for its two coordinates. -/
structure ComplexInterval where
  re : RealInterval
  im : RealInterval

namespace ComplexInterval

/-- `R.Contains z` means that both coordinates of `z` lie in `R`. -/
def Contains (R : ComplexInterval) (z : ℂ) : Prop :=
  R.re.Contains z.re ∧ R.im.Contains z.im

/-- The singleton rectangle containing one exact complex number. -/
def point (z : ℂ) : ComplexInterval where
  re := RealInterval.point z.re
  im := RealInterval.point z.im

/-- Coordinate-wise image of a rectangle under complex negation. -/
def neg (R : ComplexInterval) : ComplexInterval where
  re := R.re.neg
  im := R.im.neg

/-- Coordinate-wise Minkowski sum of two complex rectangles. -/
def add (X Y : ComplexInterval) : ComplexInterval where
  re := X.re.add Y.re
  im := X.im.add Y.im

/-- Coordinate-wise Minkowski difference of two complex rectangles. -/
def sub (X Y : ComplexInterval) : ComplexInterval where
  re := X.re.sub Y.re
  im := X.im.sub Y.im

/--
Rectangular enclosure of a complex product, using
`(x * y).re = x.re * y.re - x.im * y.im` and
`(x * y).im = x.re * y.im + x.im * y.re`.
-/
def mul (X Y : ComplexInterval) : ComplexInterval where
  re := (X.re.mul Y.re).sub (X.im.mul Y.im)
  im := (X.re.mul Y.im).add (X.im.mul Y.re)

/-- A named single-step squaring schedule. -/
def square (R : ComplexInterval) : ComplexInterval :=
  R.mul R

/-- A sound natural power schedule, evaluated by repeated rectangle multiplication. -/
def powNat (R : ComplexInterval) : Nat → ComplexInterval
  | 0 => point 1
  | n + 1 => (powNat R n).mul R

@[simp] theorem point_contains (z : ℂ) : (point z).Contains z := by
  exact ⟨RealInterval.point_contains z.re, RealInterval.point_contains z.im⟩

theorem neg_contains {R : ComplexInterval} {z : ℂ} (hz : R.Contains z) :
    R.neg.Contains (-z) := by
  exact ⟨RealInterval.neg_contains hz.1, RealInterval.neg_contains hz.2⟩

theorem add_contains {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.add Y).Contains (x + y) := by
  exact ⟨RealInterval.add_contains hx.1 hy.1,
    RealInterval.add_contains hx.2 hy.2⟩

theorem sub_contains {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.sub Y).Contains (x - y) := by
  exact ⟨RealInterval.sub_contains hx.1 hy.1,
    RealInterval.sub_contains hx.2 hy.2⟩

theorem mul_contains {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.mul Y).Contains (x * y) := by
  constructor
  · exact RealInterval.sub_contains
      (RealInterval.mul_contains hx.1 hy.1)
      (RealInterval.mul_contains hx.2 hy.2)
  · exact RealInterval.add_contains
      (RealInterval.mul_contains hx.1 hy.2)
      (RealInterval.mul_contains hx.2 hy.1)

theorem square_contains {R : ComplexInterval} {z : ℂ} (hz : R.Contains z) :
    R.square.Contains (z ^ 2) := by
  simpa [square, pow_two] using mul_contains hz hz

theorem powNat_contains {R : ComplexInterval} {z : ℂ} (hz : R.Contains z) :
    ∀ n : Nat, (R.powNat n).Contains (z ^ n)
  | 0 => by simp [powNat]
  | n + 1 => by
      simpa [powNat, pow_succ] using mul_contains (powNat_contains hz n) hz

end ComplexInterval

end SparkInterval
