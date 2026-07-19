import SparkInterval.RealInterval

/-!
# Exact operations on real intervals

These operations use exact real arithmetic.  Multiplication uses the four
corners of the input rectangle, and reciprocal is available only with evidence
that the input interval excludes zero.
-/

set_option autoImplicit false

namespace SparkInterval.RealInterval

/-- Exact interval negation. -/
def neg (I : RealInterval) : RealInterval where
  lo := -I.hi
  hi := -I.lo
  valid := neg_le_neg I.valid

/-- Exact Minkowski sum of two real intervals. -/
def add (X Y : RealInterval) : RealInterval where
  lo := X.lo + Y.lo
  hi := X.hi + Y.hi
  valid := add_le_add X.valid Y.valid

/-- Exact Minkowski difference of two real intervals. -/
def sub (X Y : RealInterval) : RealInterval where
  lo := X.lo - Y.hi
  hi := X.hi - Y.lo
  valid := sub_le_sub X.valid Y.valid

/-- The tight real interval hull of all products of members of `X` and `Y`. -/
def mul (X Y : RealInterval) : RealInterval where
  lo := min (min (X.lo * Y.lo) (X.lo * Y.hi))
    (min (X.hi * Y.lo) (X.hi * Y.hi))
  hi := max (max (X.lo * Y.lo) (X.lo * Y.hi))
    (max (X.hi * Y.lo) (X.hi * Y.hi))
  valid := by
    calc
      min (min (X.lo * Y.lo) (X.lo * Y.hi))
          (min (X.hi * Y.lo) (X.hi * Y.hi))
          ≤ X.lo * Y.lo := (min_le_left _ _).trans (min_le_left _ _)
      _ ≤ max (max (X.lo * Y.lo) (X.lo * Y.hi))
          (max (X.hi * Y.lo) (X.hi * Y.hi)) :=
        (le_max_left _ _).trans (le_max_left _ _)

/-- The reciprocal image of an interval known to exclude zero. -/
noncomputable def reciprocal (I : RealInterval) (hzero : I.ExcludesZero) : RealInterval where
  lo := 1 / I.hi
  hi := 1 / I.lo
  valid := by
    rcases hzero with hneg | hpos
    · have hlo : I.lo < 0 := I.valid.trans_lt hneg
      exact (one_div_le_one_div_of_neg hneg hlo).2 I.valid
    · have hhi : 0 < I.hi := hpos.trans_le I.valid
      exact (one_div_le_one_div hhi hpos).2 I.valid

/-- Exact interval division, defined as multiplication by a reciprocal interval. -/
noncomputable def div (X Y : RealInterval) (hzero : Y.ExcludesZero) : RealInterval :=
  X.mul (Y.reciprocal hzero)

/-- The tight interval hull of the absolute-value image of `I`. -/
noncomputable def abs (I : RealInterval) : RealInterval :=
  if hneg : I.hi < 0 then
    I.neg
  else if _hpos : 0 < I.lo then
    I
  else
    {
      lo := 0
      hi := max (-I.lo) I.hi
      valid := (le_of_not_gt hneg).trans (le_max_right _ _)
    }

/-- Pointwise minimum of two real intervals. -/
def min (X Y : RealInterval) : RealInterval where
  lo := Min.min X.lo Y.lo
  hi := Min.min X.hi Y.hi
  valid := min_le_min X.valid Y.valid

/-- Pointwise maximum of two real intervals. -/
def max (X Y : RealInterval) : RealInterval where
  lo := Max.max X.lo Y.lo
  hi := Max.max X.hi Y.hi
  valid := max_le_max X.valid Y.valid

/-- A sound natural power, computed by repeated exact interval multiplication. -/
def powNat (I : RealInterval) : Nat → RealInterval
  | 0 => point 1
  | n + 1 => (powNat I n).mul I

end SparkInterval.RealInterval
