import SparkInterval.IntervalOps

/-!
# Soundness of exact real interval operations

Every theorem in this file states that applying the corresponding real
operation to contained values produces a value contained in the result.
-/

set_option autoImplicit false

namespace SparkInterval

private theorem fourProducts_lower
    {a b c d x y : ℝ}
    (hax : a ≤ x) (hxb : x ≤ b) (hcy : c ≤ y) (hyd : y ≤ d) :
    min (min (a * c) (a * d)) (min (b * c) (b * d)) ≤ x * y := by
  by_cases hy : 0 ≤ y
  · by_cases ha : 0 ≤ a
    · calc
        min (min (a * c) (a * d)) (min (b * c) (b * d)) ≤ a * c :=
          (min_le_left _ _).trans (min_le_left _ _)
        _ ≤ a * y := mul_le_mul_of_nonneg_left hcy ha
        _ ≤ x * y := mul_le_mul_of_nonneg_right hax hy
    · have ha' : a ≤ 0 := le_of_not_ge ha
      calc
        min (min (a * c) (a * d)) (min (b * c) (b * d)) ≤ a * d :=
          (min_le_left _ _).trans (min_le_right _ _)
        _ ≤ a * y := mul_le_mul_of_nonpos_left hyd ha'
        _ ≤ x * y := mul_le_mul_of_nonneg_right hax hy
  · have hy' : y ≤ 0 := le_of_not_ge hy
    by_cases hb : 0 ≤ b
    · calc
        min (min (a * c) (a * d)) (min (b * c) (b * d)) ≤ b * c :=
          (min_le_right _ _).trans (min_le_left _ _)
        _ ≤ b * y := mul_le_mul_of_nonneg_left hcy hb
        _ ≤ x * y := mul_le_mul_of_nonpos_right hxb hy'
    · have hb' : b ≤ 0 := le_of_not_ge hb
      calc
        min (min (a * c) (a * d)) (min (b * c) (b * d)) ≤ b * d :=
          (min_le_right _ _).trans (min_le_right _ _)
        _ ≤ b * y := mul_le_mul_of_nonpos_left hyd hb'
        _ ≤ x * y := mul_le_mul_of_nonpos_right hxb hy'

private theorem fourProducts_upper
    {a b c d x y : ℝ}
    (hax : a ≤ x) (hxb : x ≤ b) (hcy : c ≤ y) (hyd : y ≤ d) :
    x * y ≤ max (max (a * c) (a * d)) (max (b * c) (b * d)) := by
  by_cases hy : 0 ≤ y
  · by_cases hb : 0 ≤ b
    · calc
        x * y ≤ b * y := mul_le_mul_of_nonneg_right hxb hy
        _ ≤ b * d := mul_le_mul_of_nonneg_left hyd hb
        _ ≤ max (max (a * c) (a * d)) (max (b * c) (b * d)) :=
          (le_max_right _ _).trans (le_max_right _ _)
    · have hb' : b ≤ 0 := le_of_not_ge hb
      calc
        x * y ≤ b * y := mul_le_mul_of_nonneg_right hxb hy
        _ ≤ b * c := mul_le_mul_of_nonpos_left hcy hb'
        _ ≤ max (max (a * c) (a * d)) (max (b * c) (b * d)) :=
          (le_max_left _ _).trans (le_max_right _ _)
  · have hy' : y ≤ 0 := le_of_not_ge hy
    by_cases ha : 0 ≤ a
    · calc
        x * y ≤ a * y := mul_le_mul_of_nonpos_right hax hy'
        _ ≤ a * d := mul_le_mul_of_nonneg_left hyd ha
        _ ≤ max (max (a * c) (a * d)) (max (b * c) (b * d)) :=
          (le_max_right _ _).trans (le_max_left _ _)
    · have ha' : a ≤ 0 := le_of_not_ge ha
      calc
        x * y ≤ a * y := mul_le_mul_of_nonpos_right hax hy'
        _ ≤ a * c := mul_le_mul_of_nonpos_left hcy ha'
        _ ≤ max (max (a * c) (a * d)) (max (b * c) (b * d)) :=
          (le_max_left _ _).trans (le_max_left _ _)

namespace RealInterval

theorem neg_contains {I : RealInterval} {x : ℝ} (hx : I.Contains x) :
    I.neg.Contains (-x) := by
  exact ⟨neg_le_neg hx.2, neg_le_neg hx.1⟩

theorem add_contains {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.add Y).Contains (x + y) := by
  exact ⟨add_le_add hx.1 hy.1, add_le_add hx.2 hy.2⟩

theorem sub_contains {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.sub Y).Contains (x - y) := by
  exact ⟨sub_le_sub hx.1 hy.2, sub_le_sub hx.2 hy.1⟩

theorem mul_contains {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.mul Y).Contains (x * y) := by
  exact ⟨fourProducts_lower hx.1 hx.2 hy.1 hy.2,
    fourProducts_upper hx.1 hx.2 hy.1 hy.2⟩

theorem reciprocal_contains {I : RealInterval} {x : ℝ}
    (hx : I.Contains x) (hzero : I.ExcludesZero) :
    (I.reciprocal hzero).Contains (1 / x) := by
  rcases hzero with hneg | hpos
  · have hxneg : x < 0 := hx.2.trans_lt hneg
    have hloneg : I.lo < 0 := I.valid.trans_lt hneg
    exact ⟨(one_div_le_one_div_of_neg hneg hxneg).2 hx.2,
      (one_div_le_one_div_of_neg hxneg hloneg).2 hx.1⟩
  · have hxpos : 0 < x := hpos.trans_le hx.1
    have hhipos : 0 < I.hi := hpos.trans_le I.valid
    exact ⟨(one_div_le_one_div hhipos hxpos).2 hx.2,
      (one_div_le_one_div hxpos hpos).2 hx.1⟩

theorem div_contains {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) (hzero : Y.ExcludesZero) :
    (X.div Y hzero).Contains (x / y) := by
  simpa [div, div_eq_mul_inv, one_div] using
    mul_contains hx (reciprocal_contains hy hzero)

theorem abs_contains {I : RealInterval} {x : ℝ} (hx : I.Contains x) :
    I.abs.Contains |x| := by
  rw [abs]
  split_ifs with hneg hpos
  · have hxneg : x < 0 := hx.2.trans_lt hneg
    simpa [abs_of_neg hxneg] using neg_contains hx
  · have hxpos : 0 < x := hpos.trans_le hx.1
    simpa [abs_of_pos hxpos] using hx
  · have hlo : I.lo ≤ 0 := le_of_not_gt hpos
    constructor
    · exact abs_nonneg x
    · change |x| ≤ Max.max (-I.lo) I.hi
      apply abs_le.2
      constructor
      · have hleft : -I.lo ≤ Max.max (-I.lo) I.hi := le_max_left _ _
        have hbound : -Max.max (-I.lo) I.hi ≤ I.lo := by
          simpa only [neg_neg] using neg_le_neg hleft
        exact hbound.trans hx.1
      · exact hx.2.trans (le_max_right _ _)

theorem min_contains {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.min Y).Contains (Min.min x y) := by
  exact ⟨min_le_min hx.1 hy.1, min_le_min hx.2 hy.2⟩

theorem max_contains {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.max Y).Contains (Max.max x y) := by
  exact ⟨max_le_max hx.1 hy.1, max_le_max hx.2 hy.2⟩

theorem powNat_contains {I : RealInterval} {x : ℝ} (hx : I.Contains x) :
    ∀ n : Nat, (I.powNat n).Contains (x ^ n)
  | 0 => by simp [powNat]
  | n + 1 => by
      simpa [powNat, pow_succ] using mul_contains (powNat_contains hx n) hx

end RealInterval

end SparkInterval
