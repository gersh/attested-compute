import SparkInterval.Certificate.RatInterval

/-!
# Outward dyadic rounding for certified evaluation pipelines

Exact rational interval arithmetic is sound but repeated multiplication
grows numerators and denominators without bound.  Certified evaluators
therefore outward-round intermediate intervals to dyadic endpoints with a
caller-chosen precision.  Rounding only ever widens an interval, so every
containment theorem survives.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-- Round a rational down to a dyadic with denominator `2 ^ prec`. -/
def roundDown (prec : ℕ) (q : ℚ) : ℚ :=
  (⌊q * 2 ^ prec⌋ : ℚ) / 2 ^ prec

/-- Round a rational up to a dyadic with denominator `2 ^ prec`. -/
def roundUp (prec : ℕ) (q : ℚ) : ℚ :=
  (⌈q * 2 ^ prec⌉ : ℚ) / 2 ^ prec

theorem roundDown_le (prec : ℕ) (q : ℚ) : roundDown prec q ≤ q := by
  rw [roundDown, div_le_iff₀ (by positivity)]
  exact Int.floor_le _

theorem le_roundUp (prec : ℕ) (q : ℚ) : q ≤ roundUp prec q := by
  rw [roundUp, le_div_iff₀ (by positivity)]
  exact Int.le_ceil _

theorem roundDown_le_roundUp (prec : ℕ) (q : ℚ) :
    roundDown prec q ≤ roundUp prec q :=
  (roundDown_le prec q).trans (le_roundUp prec q)

/-- Outward-round both endpoints, preserving real containment. -/
def roundOut (prec : ℕ) (I : RatInterval) : RatInterval :=
  { lo := roundDown prec I.lo, hi := roundUp prec I.hi }

theorem roundOut_containsReal {prec : ℕ} {I : RatInterval} {x : ℝ}
    (h : I.ContainsReal x) : (roundOut prec I).ContainsReal x := by
  constructor
  · calc ((roundOut prec I).lo : ℝ) ≤ (I.lo : ℝ) := by
          exact_mod_cast roundDown_le prec I.lo
      _ ≤ x := h.1
  · calc x ≤ (I.hi : ℝ) := h.2
      _ ≤ ((roundOut prec I).hi : ℝ) := by
          exact_mod_cast le_roundUp prec I.hi

theorem roundOut_isValid {prec : ℕ} {I : RatInterval} (h : I.IsValid) :
    (roundOut prec I).IsValid :=
  ((roundDown_le prec I.lo).trans h).trans (le_roundUp prec I.hi)

/-- Widen an interval symmetrically by a nonnegative rational slack. -/
def widen (e : ℚ) (I : RatInterval) : RatInterval :=
  { lo := I.lo - e, hi := I.hi + e }

theorem widen_containsReal {e : ℚ} (he : 0 ≤ e) {I : RatInterval} {x : ℝ}
    (h : I.ContainsReal x) : (widen e I).ContainsReal x := by
  have he' : (0 : ℝ) ≤ (e : ℝ) := by exact_mod_cast he
  constructor
  · have : ((I.lo - e : ℚ) : ℝ) = (I.lo : ℝ) - (e : ℝ) := by push_cast; ring
    rw [widen, this]
    linarith [h.1]
  · have : ((I.hi + e : ℚ) : ℝ) = (I.hi : ℝ) + (e : ℝ) := by push_cast; ring
    rw [widen, this]
    linarith [h.2]

/-- Containment of a real value known only through bounds by two rationals. -/
theorem containsReal_of_le_of_le {lo hi : ℚ} {x : ℝ}
    (hlo : (lo : ℝ) ≤ x) (hhi : x ≤ (hi : ℝ)) :
    (RatInterval.mk lo hi).ContainsReal x :=
  ⟨hlo, hhi⟩

end SparkInterval.Certified
