import SparkInterval.Certified.Rounding

/-!
# Complex rectangles over exact rational intervals

Axis-aligned rectangles with `RatInterval` sides, together with containment
of exact complex values.  These are the certified-evaluation counterpart of
the binary64 rectangles used by the GPU kernels: addition, subtraction,
multiplication, rational scaling, outward rounding, and norm-based
widening all preserve containment.

The norm-widening lemma `ComplexRect.widen_contains_of_norm_le` is the
bridge that consumes analytic remainder bounds: if a rectangle contains a
computable main term and `‖target - main‖ ≤ e`, the rectangle widened by
`e` contains the target.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-- An axis-aligned complex rectangle with exact rational corners. -/
structure ComplexRect where
  re : RatInterval
  im : RatInterval
  deriving Repr

namespace ComplexRect

/-- The rectangle contains an exact complex number. -/
def ContainsComplex (R : ComplexRect) (z : ℂ) : Prop :=
  R.re.ContainsReal z.re ∧ R.im.ContainsReal z.im

def IsValid (R : ComplexRect) : Prop :=
  R.re.IsValid ∧ R.im.IsValid

def point (x y : ℚ) : ComplexRect :=
  ⟨RatInterval.point x, RatInterval.point y⟩

def add (Z W : ComplexRect) : ComplexRect :=
  ⟨Z.re.add W.re, Z.im.add W.im⟩

def sub (Z W : ComplexRect) : ComplexRect :=
  ⟨Z.re.sub W.re, Z.im.sub W.im⟩

def neg (Z : ComplexRect) : ComplexRect :=
  ⟨Z.re.neg, Z.im.neg⟩

/-- `(a+bi)(c+di) = (ac - bd) + (ad + bc)i` with interval sides. -/
def mul (Z W : ComplexRect) : ComplexRect :=
  ⟨(Z.re.mul W.re).sub (Z.im.mul W.im),
   (Z.re.mul W.im).add (Z.im.mul W.re)⟩

/-- Scale both sides by a real interval factor. -/
def scale (r : RatInterval) (Z : ComplexRect) : ComplexRect :=
  ⟨r.mul Z.re, r.mul Z.im⟩

def roundOutRect (prec : ℕ) (Z : ComplexRect) : ComplexRect :=
  ⟨roundOut prec Z.re, roundOut prec Z.im⟩

def widenRect (e : ℚ) (Z : ComplexRect) : ComplexRect :=
  ⟨widen e Z.re, widen e Z.im⟩

theorem point_containsComplex (x y : ℚ) :
    (point x y).ContainsComplex ⟨(x : ℝ), (y : ℝ)⟩ :=
  ⟨RatInterval.point_containsReal x, RatInterval.point_containsReal y⟩

theorem add_containsComplex {Z W : ComplexRect} {z w : ℂ}
    (hz : Z.ContainsComplex z) (hw : W.ContainsComplex w) :
    (Z.add W).ContainsComplex (z + w) :=
  ⟨RatInterval.add_containsReal hz.1 hw.1,
   RatInterval.add_containsReal hz.2 hw.2⟩

theorem sub_containsComplex {Z W : ComplexRect} {z w : ℂ}
    (hz : Z.ContainsComplex z) (hw : W.ContainsComplex w) :
    (Z.sub W).ContainsComplex (z - w) :=
  ⟨RatInterval.sub_containsReal hz.1 hw.1,
   RatInterval.sub_containsReal hz.2 hw.2⟩

theorem neg_containsComplex {Z : ComplexRect} {z : ℂ}
    (hz : Z.ContainsComplex z) :
    Z.neg.ContainsComplex (-z) :=
  ⟨RatInterval.neg_containsReal hz.1, RatInterval.neg_containsReal hz.2⟩

theorem mul_containsComplex {Z W : ComplexRect} {z w : ℂ}
    (hz : Z.ContainsComplex z) (hw : W.ContainsComplex w) :
    (Z.mul W).ContainsComplex (z * w) := by
  constructor
  · have : (z * w).re = z.re * w.re - z.im * w.im := Complex.mul_re z w
    rw [mul, this]
    exact RatInterval.sub_containsReal
      (RatInterval.mul_containsReal hz.1 hw.1)
      (RatInterval.mul_containsReal hz.2 hw.2)
  · have : (z * w).im = z.re * w.im + z.im * w.re := Complex.mul_im z w
    rw [mul, this]
    exact RatInterval.add_containsReal
      (RatInterval.mul_containsReal hz.1 hw.2)
      (RatInterval.mul_containsReal hz.2 hw.1)

/-- Containment under scaling by a real interval factor, where the scalar
multiplies the complex value through the real embedding. -/
theorem scale_containsComplex {r : RatInterval} {Z : ComplexRect}
    {c : ℝ} {z : ℂ}
    (hc : r.ContainsReal c) (hz : Z.ContainsComplex z) :
    (scale r Z).ContainsComplex ((c : ℂ) * z) := by
  constructor
  · have : ((c : ℂ) * z).re = c * z.re := by
      simp [Complex.mul_re]
    rw [scale, this]
    exact RatInterval.mul_containsReal hc hz.1
  · have : ((c : ℂ) * z).im = c * z.im := by
      simp [Complex.mul_im]
    rw [scale, this]
    exact RatInterval.mul_containsReal hc hz.2

theorem roundOutRect_containsComplex {prec : ℕ} {Z : ComplexRect} {z : ℂ}
    (hz : Z.ContainsComplex z) :
    (roundOutRect prec Z).ContainsComplex z :=
  ⟨roundOut_containsReal hz.1, roundOut_containsReal hz.2⟩

theorem widenRect_containsComplex {e : ℚ} (he : 0 ≤ e)
    {Z : ComplexRect} {z : ℂ} (hz : Z.ContainsComplex z) :
    (widenRect e Z).ContainsComplex z :=
  ⟨widen_containsReal he hz.1, widen_containsReal he hz.2⟩

/-- Interval widening absorbs a bounded real perturbation of an enclosed
midpoint value. -/
theorem _root_.SparkInterval.Certified.widen_contains_of_abs_le
    {e : ℚ} {I : RatInterval} {m x : ℝ}
    (hm : I.ContainsReal m) (habs : |x - m| ≤ (e : ℝ)) :
    (widen e I).ContainsReal x := by
  have h1 := abs_le.mp habs
  constructor
  · show ((I.lo - e : ℚ) : ℝ) ≤ x
    push_cast
    linarith [hm.1]
  · show x ≤ ((I.hi + e : ℚ) : ℝ)
    push_cast
    linarith [hm.2]

/-- Norm-based widening: a rectangle around a computable main value,
widened by a remainder radius, contains the analytic target.  This is how
Euler-Maclaurin and Stirling remainder premises enter the pipeline. -/
theorem widen_contains_of_norm_le {e : ℚ} {Z : ComplexRect} {main w : ℂ}
    (hmain : Z.ContainsComplex main) (hnorm : ‖w - main‖ ≤ (e : ℝ)) :
    (widenRect e Z).ContainsComplex w := by
  have hre : |w.re - main.re| ≤ (e : ℝ) := by
    calc |w.re - main.re| = |(w - main).re| := by simp [Complex.sub_re]
      _ ≤ ‖w - main‖ := Complex.abs_re_le_norm _
      _ ≤ (e : ℝ) := hnorm
  have him : |w.im - main.im| ≤ (e : ℝ) := by
    calc |w.im - main.im| = |(w - main).im| := by simp [Complex.sub_im]
      _ ≤ ‖w - main‖ := Complex.abs_im_le_norm _
      _ ≤ (e : ℝ) := hnorm
  exact ⟨widen_contains_of_abs_le hmain.1 hre,
         widen_contains_of_abs_le hmain.2 him⟩

end ComplexRect

end SparkInterval.Certified
