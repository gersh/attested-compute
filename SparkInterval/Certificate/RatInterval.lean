import Mathlib

/-!
# Executable rational intervals

`RatInterval` is the exact interval domain used while checking result
certificates.  Its endpoints are rational numbers, so every operation in this
file is executable and deterministic.  The structure intentionally stores raw
endpoints rather than a proof: malformed certificate intervals can be parsed
and rejected by `isValid`.

The soundness theorems connect these executable computations to containment of
mathematical real numbers.  This file contains no axioms, `sorry`, or unsafe
code.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate

/-- A closed interval represented by two exact rational endpoints.

The endpoints are deliberately raw.  Use `isValid` when accepting untrusted
input, or `IsValid` in proofs.
-/
structure RatInterval where
  lo : ℚ
  hi : ℚ
  deriving DecidableEq, Repr

namespace RatInterval

/-- Propositional well-formedness of a rational interval. -/
def IsValid (I : RatInterval) : Prop := I.lo ≤ I.hi

/-- Executable well-formedness check for an untrusted rational interval. -/
def isValid (I : RatInterval) : Bool := decide (I.lo ≤ I.hi)

/-- Real-number containment denoted by an exact rational interval. -/
def ContainsReal (I : RatInterval) (x : ℝ) : Prop :=
  (I.lo : ℝ) ≤ x ∧ x ≤ (I.hi : ℝ)

/-- The interval lies strictly on one side of zero. -/
def ExcludesZero (I : RatInterval) : Prop :=
  I.hi < 0 ∨ 0 < I.lo

/-- Executable test for an interval lying strictly on one side of zero. -/
def excludesZero (I : RatInterval) : Bool :=
  decide (I.hi < 0 ∨ 0 < I.lo)

/-- A singleton rational interval. -/
def point (x : ℚ) : RatInterval := ⟨x, x⟩

/-- Exact interval negation. -/
def neg (I : RatInterval) : RatInterval := ⟨-I.hi, -I.lo⟩

/-- Exact Minkowski sum. -/
def add (X Y : RatInterval) : RatInterval :=
  ⟨X.lo + Y.lo, X.hi + Y.hi⟩

/-- Exact Minkowski difference. -/
def sub (X Y : RatInterval) : RatInterval :=
  ⟨X.lo - Y.hi, X.hi - Y.lo⟩

/-- The exact rational hull of the four endpoint products. -/
def mul (X Y : RatInterval) : RatInterval :=
  ⟨Min.min (Min.min (X.lo * Y.lo) (X.lo * Y.hi))
      (Min.min (X.hi * Y.lo) (X.hi * Y.hi)),
    Max.max (Max.max (X.lo * Y.lo) (X.lo * Y.hi))
      (Max.max (X.hi * Y.lo) (X.hi * Y.hi))⟩

/-- Reciprocal endpoints.  This helper is used only after proving that the
interval excludes zero. -/
private def reciprocal (I : RatInterval) : RatInterval :=
  ⟨1 / I.hi, 1 / I.lo⟩

/-- Exact interval division.  Division is rejected when the divisor does not
provably exclude zero from its endpoint data. -/
def div? (X Y : RatInterval) : Option RatInterval :=
  if Y.hi < 0 ∨ 0 < Y.lo then some (X.mul Y.reciprocal) else none

/-- The exact interval hull of the absolute-value image. -/
def abs (I : RatInterval) : RatInterval :=
  if I.hi < 0 then
    I.neg
  else if 0 < I.lo then
    I
  else
    ⟨0, Max.max (-I.lo) I.hi⟩

/-- Pointwise minimum of two intervals. -/
def min (X Y : RatInterval) : RatInterval :=
  ⟨Min.min X.lo Y.lo, Min.min X.hi Y.hi⟩

/-- Pointwise maximum of two intervals. -/
def max (X Y : RatInterval) : RatInterval :=
  ⟨Max.max X.lo Y.lo, Max.max X.hi Y.hi⟩

/-- A sound natural power, evaluated by exact interval multiplication. -/
def powNat (I : RatInterval) : Nat → RatInterval
  | 0 => point 1
  | n + 1 => (powNat I n).mul I

/-! ## Boolean reflection and basic facts -/

@[simp] theorem isValid_eq_true {I : RatInterval} :
    I.isValid = true ↔ I.IsValid := by
  simp [isValid, IsValid]

@[simp] theorem isValid_eq_false {I : RatInterval} :
    I.isValid = false ↔ ¬ I.IsValid := by
  simp [isValid, IsValid]

@[simp] theorem isValid_iff {I : RatInterval} :
    I.isValid ↔ I.IsValid := by
  simp [isValid, IsValid]

@[simp] theorem excludesZero_eq_true {I : RatInterval} :
    I.excludesZero = true ↔ I.ExcludesZero := by
  simp [excludesZero, ExcludesZero]

@[simp] theorem excludesZero_eq_false {I : RatInterval} :
    I.excludesZero = false ↔ ¬ I.ExcludesZero := by
  simp [excludesZero, ExcludesZero]

@[simp] theorem point_isValid (x : ℚ) : (point x).IsValid := by
  exact le_rfl

@[simp] theorem point_containsReal (x : ℚ) :
    (point x).ContainsReal (x : ℝ) := by
  exact ⟨le_rfl, le_rfl⟩

theorem isValid_of_containsReal {I : RatInterval} {x : ℝ}
    (hx : I.ContainsReal x) : I.IsValid := by
  exact_mod_cast hx.1.trans hx.2

theorem excludesZero_iff_not_contains_zero {I : RatInterval}
    (_hI : I.IsValid) :
    I.ExcludesZero ↔ ¬ (I.lo ≤ 0 ∧ 0 ≤ I.hi) := by
  constructor
  · rintro (hneg | hpos) hzero
    · exact (not_lt_of_ge hzero.2) hneg
    · exact (not_lt_of_ge hzero.1) hpos
  · intro hzero
    by_cases hneg : I.hi < 0
    · exact Or.inl hneg
    · right
      have hhi : 0 ≤ I.hi := le_of_not_gt hneg
      exact lt_of_not_ge fun hlo => hzero ⟨hlo, hhi⟩

theorem div?_eq_none_iff {X Y : RatInterval} (hY : Y.IsValid) :
    X.div? Y = none ↔ Y.lo ≤ 0 ∧ 0 ≤ Y.hi := by
  by_cases hzero : Y.ExcludesZero
  · have hnot := (excludesZero_iff_not_contains_zero hY).mp hzero
    have hzero' : Y.hi < 0 ∨ 0 < Y.lo := hzero
    simp [div?, hzero', hnot]
  · have hcontains : Y.lo ≤ 0 ∧ 0 ≤ Y.hi := by
      by_contra hnot
      exact hzero ((excludesZero_iff_not_contains_zero hY).mpr hnot)
    have hzero' : ¬ (Y.hi < 0 ∨ 0 < Y.lo) := hzero
    simp [div?, hzero', hcontains]

/-! ## Preservation of validity -/

theorem neg_isValid {I : RatInterval} (hI : I.IsValid) : I.neg.IsValid := by
  exact neg_le_neg hI

theorem add_isValid {X Y : RatInterval} (hX : X.IsValid) (hY : Y.IsValid) :
    (X.add Y).IsValid := by
  exact add_le_add hX hY

theorem sub_isValid {X Y : RatInterval} (hX : X.IsValid) (hY : Y.IsValid) :
    (X.sub Y).IsValid := by
  exact sub_le_sub hX hY

theorem mul_isValid (X Y : RatInterval) : (X.mul Y).IsValid := by
  calc
    Min.min (Min.min (X.lo * Y.lo) (X.lo * Y.hi))
        (Min.min (X.hi * Y.lo) (X.hi * Y.hi))
        ≤ X.lo * Y.lo := (min_le_left _ _).trans (min_le_left _ _)
    _ ≤ Max.max (Max.max (X.lo * Y.lo) (X.lo * Y.hi))
        (Max.max (X.hi * Y.lo) (X.hi * Y.hi)) :=
      (le_max_left _ _).trans (le_max_left _ _)

private theorem reciprocal_isValid {I : RatInterval}
    (hI : I.IsValid) (hzero : I.ExcludesZero) : I.reciprocal.IsValid := by
  rcases hzero with hneg | hpos
  · have hlo : I.lo < 0 := hI.trans_lt hneg
    exact (one_div_le_one_div_of_neg hneg hlo).2 hI
  · have hhi : 0 < I.hi := hpos.trans_le hI
    exact (one_div_le_one_div hhi hpos).2 hI

theorem div?_isValid {X Y R : RatInterval}
    (hresult : X.div? Y = some R) :
    R.IsValid := by
  by_cases hzero : Y.ExcludesZero
  · have hzero' : Y.hi < 0 ∨ 0 < Y.lo := hzero
    rw [div?, if_pos hzero'] at hresult
    injection hresult with hresult
    subst R
    exact mul_isValid X Y.reciprocal
  · have hzero' : ¬ (Y.hi < 0 ∨ 0 < Y.lo) := hzero
    simp [div?, hzero'] at hresult

theorem abs_isValid {I : RatInterval} (hI : I.IsValid) : I.abs.IsValid := by
  rw [abs]
  split_ifs with hneg hpos
  · exact neg_isValid hI
  · exact hI
  · exact (le_of_not_gt hneg).trans (le_max_right _ _)

theorem min_isValid {X Y : RatInterval} (hX : X.IsValid) (hY : Y.IsValid) :
    (X.min Y).IsValid := by
  exact min_le_min hX hY

theorem max_isValid {X Y : RatInterval} (hX : X.IsValid) (hY : Y.IsValid) :
    (X.max Y).IsValid := by
  exact max_le_max hX hY

theorem powNat_isValid {I : RatInterval} (_hI : I.IsValid) :
    ∀ n : Nat, (I.powNat n).IsValid
  | 0 => point_isValid 1
  | n + 1 => mul_isValid (I.powNat n) I

/-! ## Real-containment soundness -/

private theorem fourProducts_lower
    {a b c d x y : ℝ}
    (hax : a ≤ x) (hxb : x ≤ b) (hcy : c ≤ y) (hyd : y ≤ d) :
    Min.min (Min.min (a * c) (a * d)) (Min.min (b * c) (b * d)) ≤ x * y := by
  by_cases hy : 0 ≤ y
  · by_cases ha : 0 ≤ a
    · calc
        Min.min (Min.min (a * c) (a * d)) (Min.min (b * c) (b * d)) ≤ a * c :=
          (min_le_left _ _).trans (min_le_left _ _)
        _ ≤ a * y := mul_le_mul_of_nonneg_left hcy ha
        _ ≤ x * y := mul_le_mul_of_nonneg_right hax hy
    · have ha' : a ≤ 0 := le_of_not_ge ha
      calc
        Min.min (Min.min (a * c) (a * d)) (Min.min (b * c) (b * d)) ≤ a * d :=
          (min_le_left _ _).trans (min_le_right _ _)
        _ ≤ a * y := mul_le_mul_of_nonpos_left hyd ha'
        _ ≤ x * y := mul_le_mul_of_nonneg_right hax hy
  · have hy' : y ≤ 0 := le_of_not_ge hy
    by_cases hb : 0 ≤ b
    · calc
        Min.min (Min.min (a * c) (a * d)) (Min.min (b * c) (b * d)) ≤ b * c :=
          (min_le_right _ _).trans (min_le_left _ _)
        _ ≤ b * y := mul_le_mul_of_nonneg_left hcy hb
        _ ≤ x * y := mul_le_mul_of_nonpos_right hxb hy'
    · have hb' : b ≤ 0 := le_of_not_ge hb
      calc
        Min.min (Min.min (a * c) (a * d)) (Min.min (b * c) (b * d)) ≤ b * d :=
          (min_le_right _ _).trans (min_le_right _ _)
        _ ≤ b * y := mul_le_mul_of_nonpos_left hyd hb'
        _ ≤ x * y := mul_le_mul_of_nonpos_right hxb hy'

private theorem fourProducts_upper
    {a b c d x y : ℝ}
    (hax : a ≤ x) (hxb : x ≤ b) (hcy : c ≤ y) (hyd : y ≤ d) :
    x * y ≤ Max.max (Max.max (a * c) (a * d)) (Max.max (b * c) (b * d)) := by
  by_cases hy : 0 ≤ y
  · by_cases hb : 0 ≤ b
    · calc
        x * y ≤ b * y := mul_le_mul_of_nonneg_right hxb hy
        _ ≤ b * d := mul_le_mul_of_nonneg_left hyd hb
        _ ≤ Max.max (Max.max (a * c) (a * d)) (Max.max (b * c) (b * d)) :=
          (le_max_right _ _).trans (le_max_right _ _)
    · have hb' : b ≤ 0 := le_of_not_ge hb
      calc
        x * y ≤ b * y := mul_le_mul_of_nonneg_right hxb hy
        _ ≤ b * c := mul_le_mul_of_nonpos_left hcy hb'
        _ ≤ Max.max (Max.max (a * c) (a * d)) (Max.max (b * c) (b * d)) :=
          (le_max_left _ _).trans (le_max_right _ _)
  · have hy' : y ≤ 0 := le_of_not_ge hy
    by_cases ha : 0 ≤ a
    · calc
        x * y ≤ a * y := mul_le_mul_of_nonpos_right hax hy'
        _ ≤ a * d := mul_le_mul_of_nonneg_left hyd ha
        _ ≤ Max.max (Max.max (a * c) (a * d)) (Max.max (b * c) (b * d)) :=
          (le_max_right _ _).trans (le_max_left _ _)
    · have ha' : a ≤ 0 := le_of_not_ge ha
      calc
        x * y ≤ a * y := mul_le_mul_of_nonpos_right hax hy'
        _ ≤ a * c := mul_le_mul_of_nonpos_left hcy ha'
        _ ≤ Max.max (Max.max (a * c) (a * d)) (Max.max (b * c) (b * d)) :=
          (le_max_left _ _).trans (le_max_left _ _)

theorem neg_containsReal {I : RatInterval} {x : ℝ} (hx : I.ContainsReal x) :
    I.neg.ContainsReal (-x) := by
  simpa only [ContainsReal, neg, Rat.cast_neg] using
    And.intro (neg_le_neg hx.2) (neg_le_neg hx.1)

theorem add_containsReal {X Y : RatInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.add Y).ContainsReal (x + y) := by
  simpa only [ContainsReal, add, Rat.cast_add] using
    And.intro (add_le_add hx.1 hy.1) (add_le_add hx.2 hy.2)

theorem sub_containsReal {X Y : RatInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.sub Y).ContainsReal (x - y) := by
  simpa only [ContainsReal, sub, Rat.cast_sub] using
    And.intro (sub_le_sub hx.1 hy.2) (sub_le_sub hx.2 hy.1)

theorem mul_containsReal {X Y : RatInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.mul Y).ContainsReal (x * y) := by
  constructor
  · simpa only [mul, ContainsReal, Rat.cast_mul, Rat.cast_min] using
      fourProducts_lower hx.1 hx.2 hy.1 hy.2
  · simpa only [mul, ContainsReal, Rat.cast_mul, Rat.cast_max] using
      fourProducts_upper hx.1 hx.2 hy.1 hy.2

private theorem reciprocal_containsReal {I : RatInterval} {x : ℝ}
    (hx : I.ContainsReal x) (hzero : I.ExcludesZero) :
    I.reciprocal.ContainsReal (1 / x) := by
  rcases hzero with hneg | hpos
  · have hnegR : (I.hi : ℝ) < 0 := by exact_mod_cast hneg
    have hxneg : x < 0 := hx.2.trans_lt hnegR
    have hloR : (I.lo : ℝ) < 0 := hx.1.trans_lt hxneg
    constructor
    · simpa only [reciprocal, ContainsReal, Rat.cast_div, Rat.cast_one] using
        (one_div_le_one_div_of_neg hnegR hxneg).2 hx.2
    · simpa only [reciprocal, ContainsReal, Rat.cast_div, Rat.cast_one] using
        (one_div_le_one_div_of_neg hxneg hloR).2 hx.1
  · have hposR : 0 < (I.lo : ℝ) := by exact_mod_cast hpos
    have hxpos : 0 < x := hposR.trans_le hx.1
    have hhiR : 0 < (I.hi : ℝ) := hxpos.trans_le hx.2
    constructor
    · simpa only [reciprocal, ContainsReal, Rat.cast_div, Rat.cast_one] using
        (one_div_le_one_div hhiR hxpos).2 hx.2
    · simpa only [reciprocal, ContainsReal, Rat.cast_div, Rat.cast_one] using
        (one_div_le_one_div hxpos hposR).2 hx.1

theorem div?_containsReal {X Y R : RatInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y)
    (hresult : X.div? Y = some R) : R.ContainsReal (x / y) := by
  by_cases hzero : Y.ExcludesZero
  · have hzero' : Y.hi < 0 ∨ 0 < Y.lo := hzero
    rw [div?, if_pos hzero'] at hresult
    injection hresult with hresult
    subst R
    simpa only [div_eq_mul_inv, one_div, one_mul] using
      mul_containsReal hx (reciprocal_containsReal hy hzero)
  · have hzero' : ¬ (Y.hi < 0 ∨ 0 < Y.lo) := hzero
    simp [div?, hzero'] at hresult

theorem abs_containsReal {I : RatInterval} {x : ℝ} (hx : I.ContainsReal x) :
    I.abs.ContainsReal |x| := by
  rw [abs]
  split_ifs with hneg hpos
  · have hnegR : (I.hi : ℝ) < 0 := by exact_mod_cast hneg
    have hxneg : x < 0 := hx.2.trans_lt hnegR
    simpa [abs_of_neg hxneg] using neg_containsReal hx
  · have hposR : 0 < (I.lo : ℝ) := by exact_mod_cast hpos
    have hxpos : 0 < x := hposR.trans_le hx.1
    simpa [abs_of_pos hxpos] using hx
  · constructor
    · simpa only [Rat.cast_zero] using abs_nonneg x
    · change |x| ≤ ((Max.max (-I.lo) I.hi : ℚ) : ℝ)
      rw [Rat.cast_max, Rat.cast_neg]
      apply abs_le.2
      constructor
      · have hleft : -(I.lo : ℝ) ≤ Max.max (-(I.lo : ℝ)) (I.hi : ℝ) :=
          le_max_left _ _
        have hbound : -Max.max (-(I.lo : ℝ)) (I.hi : ℝ) ≤ (I.lo : ℝ) := by
          simpa only [neg_neg] using neg_le_neg hleft
        exact hbound.trans hx.1
      · exact hx.2.trans (le_max_right _ _)

theorem min_containsReal {X Y : RatInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.min Y).ContainsReal (Min.min x y) := by
  constructor
  · simpa only [min, ContainsReal, Rat.cast_min] using min_le_min hx.1 hy.1
  · simpa only [min, ContainsReal, Rat.cast_min] using min_le_min hx.2 hy.2

theorem max_containsReal {X Y : RatInterval} {x y : ℝ}
    (hx : X.ContainsReal x) (hy : Y.ContainsReal y) :
    (X.max Y).ContainsReal (Max.max x y) := by
  constructor
  · simpa only [max, ContainsReal, Rat.cast_max] using max_le_max hx.1 hy.1
  · simpa only [max, ContainsReal, Rat.cast_max] using max_le_max hx.2 hy.2

theorem powNat_containsReal {I : RatInterval} {x : ℝ}
    (hx : I.ContainsReal x) : ∀ n : Nat, (I.powNat n).ContainsReal (x ^ n)
  | 0 => by simp [powNat, ContainsReal, point]
  | n + 1 => by
      simpa [powNat, pow_succ] using
        mul_containsReal (powNat_containsReal hx n) hx

end RatInterval

end SparkInterval.Certificate
