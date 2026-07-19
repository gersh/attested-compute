import SparkInterval.Basic

/-!
# IEEE-754 binary64 encodings

This file models the representation layer of IEEE-754 binary64.  It does not
use Lean's runtime `Float`: an encoding is exactly a 64-bit word, and finite
values are decoded as signed integer multiples of an integral power of two.

The representation intentionally keeps the original word.  In particular,
positive and negative zero are distinct encodings even though both decode to
the mathematical real number zero.
-/

set_option autoImplicit false

namespace SparkInterval

/-- The complete set of binary64 bit patterns. -/
abbrev Binary64Bits := BitVec 64

/-- The mutually exclusive IEEE-754 classes, with the sign made explicit for
all classes except NaN.  (The sign bit of a NaN remains available from its
encoding but has no numerical meaning.) -/
inductive Binary64Class where
  | positiveZero
  | negativeZero
  | positiveSubnormal
  | negativeSubnormal
  | positiveNormal
  | negativeNormal
  | positiveInfinity
  | negativeInfinity
  | nan
  deriving DecidableEq, Repr

namespace Binary64Bits

/-- `2^52`, one greater than the largest fraction field. -/
def fractionModulus : Nat := 4503599627370496

/-- `2^11`, one greater than the largest exponent field. -/
def exponentModulus : Nat := 2048

/-- The all-ones exponent field. -/
def exponentAllOnes : Nat := 2047

/-- `2^63`, the place value of the sign bit. -/
def signThreshold : Nat := 9223372036854775808

/-- The stored 52-bit fraction field. -/
def fractionBits (x : Binary64Bits) : Nat :=
  x.toNat % fractionModulus

/-- The stored 11-bit biased exponent field. -/
def exponentBits (x : Binary64Bits) : Nat :=
  (x.toNat / fractionModulus) % exponentModulus

/-- The high bit of an encoding. `true` denotes a negative encoding. -/
def signBit (x : Binary64Bits) : Bool :=
  decide (signThreshold ≤ x.toNat)

theorem fractionModulus_eq : fractionModulus = 2 ^ 52 := by
  norm_num [fractionModulus]

theorem exponentModulus_eq : exponentModulus = 2 ^ 11 := by
  norm_num [exponentModulus]

theorem signThreshold_eq : signThreshold = 2 ^ 63 := by
  norm_num [signThreshold]

theorem fractionBits_lt (x : Binary64Bits) : x.fractionBits < fractionModulus := by
  exact Nat.mod_lt _ (by norm_num [fractionModulus])

theorem exponentBits_lt (x : Binary64Bits) : x.exponentBits < exponentModulus := by
  exact Nat.mod_lt _ (by norm_num [exponentModulus])

/-- The exact IEEE-754 classification of a 64-bit word. -/
def classify (x : Binary64Bits) : Binary64Class :=
  if x.exponentBits = 0 then
    if x.fractionBits = 0 then
      if x.signBit then .negativeZero else .positiveZero
    else if x.signBit then .negativeSubnormal else .positiveSubnormal
  else if x.exponentBits = exponentAllOnes then
    if x.fractionBits = 0 then
      if x.signBit then .negativeInfinity else .positiveInfinity
    else .nan
  else if x.signBit then .negativeNormal else .positiveNormal

/-- A finite encoding has neither an all-ones exponent nor any special-value
interpretation.  The strict inequality form is useful to later rounding
proofs. -/
def IsFinite (x : Binary64Bits) : Prop :=
  x.exponentBits < exponentAllOnes

instance instDecidableIsFinite (x : Binary64Bits) : Decidable x.IsFinite := by
  unfold IsFinite
  infer_instance

/-- Boolean reflection of `IsFinite`. -/
def isFinite (x : Binary64Bits) : Bool :=
  decide x.IsFinite

def IsZero (x : Binary64Bits) : Prop :=
  x.exponentBits = 0 ∧ x.fractionBits = 0

def IsSubnormal (x : Binary64Bits) : Prop :=
  x.exponentBits = 0 ∧ x.fractionBits ≠ 0

def IsNormal (x : Binary64Bits) : Prop :=
  0 < x.exponentBits ∧ x.exponentBits < exponentAllOnes

def IsInfinite (x : Binary64Bits) : Prop :=
  x.exponentBits = exponentAllOnes ∧ x.fractionBits = 0

def IsNaN (x : Binary64Bits) : Prop :=
  x.exponentBits = exponentAllOnes ∧ x.fractionBits ≠ 0

instance instDecidableIsZero (x : Binary64Bits) : Decidable x.IsZero := by
  unfold IsZero
  infer_instance

instance instDecidableIsSubnormal (x : Binary64Bits) : Decidable x.IsSubnormal := by
  unfold IsSubnormal
  infer_instance

instance instDecidableIsNormal (x : Binary64Bits) : Decidable x.IsNormal := by
  unfold IsNormal
  infer_instance

instance instDecidableIsInfinite (x : Binary64Bits) : Decidable x.IsInfinite := by
  unfold IsInfinite
  infer_instance

instance instDecidableIsNaN (x : Binary64Bits) : Decidable x.IsNaN := by
  unfold IsNaN
  infer_instance

theorem isFinite_eq_true_iff (x : Binary64Bits) :
    x.isFinite = true ↔ x.IsFinite := by
  simp [isFinite]

theorem finite_exponent_le (x : Binary64Bits) (h : x.IsFinite) :
    x.exponentBits ≤ 2046 := by
  exact Nat.le_pred_of_lt h

theorem special_exponent_eq (x : Binary64Bits) (h : ¬x.IsFinite) :
    x.exponentBits = exponentAllOnes := by
  have hlt := x.exponentBits_lt
  simp only [IsFinite, not_lt] at h
  norm_num [exponentModulus, exponentAllOnes] at hlt h ⊢
  omega

theorem finite_iff_zero_subnormal_or_normal (x : Binary64Bits) :
    x.IsFinite ↔ x.IsZero ∨ x.IsSubnormal ∨ x.IsNormal := by
  constructor
  · intro h
    by_cases he : x.exponentBits = 0
    · by_cases hf : x.fractionBits = 0
      · exact Or.inl ⟨he, hf⟩
      · exact Or.inr (Or.inl ⟨he, hf⟩)
    · exact Or.inr (Or.inr ⟨Nat.pos_of_ne_zero he, h⟩)
  · rintro (h | h | h)
    · norm_num [IsFinite, IsZero, exponentAllOnes, h.1]
    · norm_num [IsFinite, IsSubnormal, exponentAllOnes, h.1]
    · exact h.2

theorem not_finite_iff_infinite_or_nan (x : Binary64Bits) :
    ¬x.IsFinite ↔ x.IsInfinite ∨ x.IsNaN := by
  constructor
  · intro h
    have he := special_exponent_eq x h
    by_cases hf : x.fractionBits = 0
    · exact Or.inl ⟨he, hf⟩
    · exact Or.inr ⟨he, hf⟩
  · rintro (h | h)
    · simp [IsFinite, h.1]
    · simp [IsFinite, h.1]

theorem zero_iff_classify_zero (x : Binary64Bits) :
    x.IsZero ↔ x.classify = .positiveZero ∨ x.classify = .negativeZero := by
  simp only [IsZero, classify]
  aesop

theorem infinite_iff_classify_infinity (x : Binary64Bits) :
    x.IsInfinite ↔
      x.classify = .positiveInfinity ∨ x.classify = .negativeInfinity := by
  simp only [IsInfinite, classify, exponentAllOnes]
  aesop

theorem nan_iff_classify_nan (x : Binary64Bits) :
    x.IsNaN ↔ x.classify = .nan := by
  simp only [IsNaN, classify, exponentAllOnes]
  aesop

end Binary64Bits

/-- A binary64 word accompanied by proof that it encodes a finite value.
Keeping `bits` here preserves signed zero and allows later proofs to refer back
to the exact input or output word. -/
structure Binary64Finite where
  bits : Binary64Bits
  finite : bits.IsFinite
  deriving DecidableEq

namespace Binary64Finite

instance : Coe Binary64Finite Binary64Bits := ⟨Binary64Finite.bits⟩

/-- Equivalence with the subtype presentation.  This exposes the finite
enumeration to rounding definitions without changing the bit-preserving public
structure. -/
def equivSubtype : Binary64Finite ≃ {bits : Binary64Bits // bits.IsFinite} where
  toFun x := ⟨x.bits, x.finite⟩
  invFun x := ⟨x.1, x.2⟩
  left_inv _ := rfl
  right_inv _ := rfl

/- Finiteness is proof-only.  We intentionally do not install a `Fintype`
instance: reducing its `univ` would try to materialize nearly `2^64` words
during code generation. -/
instance : Finite Binary64Finite :=
  Finite.of_injective Binary64Finite.bits (by
    rintro ⟨x, hx⟩ ⟨y, hy⟩ h
    cases h
    rfl)

/-- All finite binary64 *encodings*.  The two signed-zero encodings are both
members even though their real interpretations coincide. -/
noncomputable def allFinite : Finset Binary64Finite :=
  Set.finite_univ.toFinset

@[simp] theorem mem_allFinite (x : Binary64Finite) : x ∈ allFinite := by
  simp [allFinite]

theorem exists_mem_allFinite_bits_iff (bits : Binary64Bits) :
    (∃ x ∈ allFinite, x.bits = bits) ↔ bits.IsFinite := by
  constructor
  · rintro ⟨x, _, rfl⟩
    exact x.finite
  · intro h
    exact ⟨⟨bits, h⟩, mem_allFinite _, rfl⟩

/-- The positive-zero encoding. -/
def positiveZero : Binary64Finite :=
  ⟨BitVec.ofNat 64 0x0000000000000000, by native_decide⟩

/-- The negative-zero encoding. -/
def negativeZero : Binary64Finite :=
  ⟨BitVec.ofNat 64 0x8000000000000000, by native_decide⟩

/-- The least positive subnormal encoding. -/
def leastPositiveSubnormal : Binary64Finite :=
  ⟨BitVec.ofNat 64 0x0000000000000001, by native_decide⟩

/-- The greatest positive finite encoding. -/
def greatestPositiveFinite : Binary64Finite :=
  ⟨BitVec.ofNat 64 0x7fefffffffffffff, by native_decide⟩

/-- The sign bit; `true` denotes a negative encoding. -/
def sign (x : Binary64Finite) : Bool :=
  x.bits.signBit

/-- The integral significand used by the exact dyadic interpretation.  Normal
values have their implicit leading bit restored. -/
def significand (x : Binary64Finite) : Nat :=
  if x.bits.exponentBits = 0 then
    x.bits.fractionBits
  else
    Binary64Bits.fractionModulus + x.bits.fractionBits

/-- The power of two paired with `significand`.  Thus a subnormal is
`fraction * 2^-1074`, while a normal with stored exponent `e` is
`(2^52 + fraction) * 2^(e-1075)`. -/
def exponent (x : Binary64Finite) : Int :=
  if x.bits.exponentBits = 0 then
    -1074
  else
    (x.bits.exponentBits : Int) - 1075

/-- The unsigned exact dyadic value. -/
noncomputable def magnitude (x : Binary64Finite) : ℝ :=
  (x.significand : ℝ) * (2 : ℝ) ^ x.exponent

/-- Exact real interpretation of a finite binary64 encoding. -/
noncomputable def toReal (x : Binary64Finite) : ℝ :=
  if x.sign then -x.magnitude else x.magnitude

/-- Canonical constraints satisfied by the integer/dyadic representation used
by `toReal`.  Zero has the chosen exponent `-1074`; nonzero subnormals use the
same exponent; normals have a 53-bit significand and exponent in the full
binary64 range. -/
def Canonical (_sign : Bool) (significand : Nat) (exponent : Int) : Prop :=
  (significand = 0 ∧ exponent = -1074) ∨
  (0 < significand ∧
    significand < Binary64Bits.fractionModulus ∧ exponent = -1074) ∨
  (Binary64Bits.fractionModulus ≤ significand ∧
    significand < 2 * Binary64Bits.fractionModulus ∧
    (-1074 : Int) ≤ exponent ∧ exponent ≤ 971)

theorem canonical (x : Binary64Finite) :
    Canonical x.sign x.significand x.exponent := by
  by_cases he : x.bits.exponentBits = 0
  · by_cases hf : x.bits.fractionBits = 0
    · left
      simp [significand, exponent, he, hf]
    · right; left
      simp only [significand, he, if_pos]
      refine ⟨Nat.pos_of_ne_zero hf, x.bits.fractionBits_lt, ?_⟩
      simp [exponent, he]
  · right; right
    have hfrac := x.bits.fractionBits_lt
    have hfinite := x.finite
    have hexpPos : 0 < x.bits.exponentBits := Nat.pos_of_ne_zero he
    have hexpLe : x.bits.exponentBits ≤ 2046 :=
      Binary64Bits.finite_exponent_le x.bits hfinite
    simp only [significand, exponent, he, if_false]
    constructor
    · omega
    constructor
    · omega
    constructor <;> norm_num <;> omega

theorem significand_lt_two_mul_modulus (x : Binary64Finite) :
    x.significand < 2 * Binary64Bits.fractionModulus := by
  rcases x.canonical with h | h | h
  · simp [h.1, Binary64Bits.fractionModulus]
  · omega
  · exact h.2.1

theorem exponent_bounds (x : Binary64Finite) :
    (-1074 : Int) ≤ x.exponent ∧ x.exponent ≤ 971 := by
  rcases x.canonical with h | h | h
  · omega
  · omega
  · exact h.2.2

theorem toReal_of_sign_false (x : Binary64Finite) (h : x.sign = false) :
    x.toReal = x.magnitude := by
  simp [toReal, h]

theorem toReal_of_sign_true (x : Binary64Finite) (h : x.sign = true) :
    x.toReal = -x.magnitude := by
  simp [toReal, h]

theorem magnitude_nonneg (x : Binary64Finite) : 0 ≤ x.magnitude := by
  exact mul_nonneg (Nat.cast_nonneg x.significand) (zpow_nonneg (by norm_num) _)

theorem toReal_nonneg_of_sign_false (x : Binary64Finite) (h : x.sign = false) :
    0 ≤ x.toReal := by
  rw [x.toReal_of_sign_false h]
  exact x.magnitude_nonneg

theorem toReal_nonpos_of_sign_true (x : Binary64Finite) (h : x.sign = true) :
    x.toReal ≤ 0 := by
  rw [x.toReal_of_sign_true h]
  exact neg_nonpos.mpr x.magnitude_nonneg

theorem toReal_eq_zero_iff (x : Binary64Finite) :
    x.toReal = 0 ↔ x.bits.IsZero := by
  have hpow : (2 : ℝ) ^ x.exponent ≠ 0 := zpow_ne_zero _ (by norm_num)
  have hmagnitude : x.magnitude = 0 ↔ x.bits.IsZero := by
    simp only [magnitude, mul_eq_zero, hpow, or_false, Nat.cast_eq_zero,
      significand, Binary64Bits.IsZero]
    by_cases he : x.bits.exponentBits = 0
    · simp [he]
    · simp [he, Binary64Bits.fractionModulus]
  unfold toReal
  split <;> simp [hmagnitude]

@[simp] theorem positiveZero_sign : positiveZero.sign = false := by
  native_decide

@[simp] theorem negativeZero_sign : negativeZero.sign = true := by
  native_decide

theorem positiveZero_bits_ne_negativeZero_bits :
    positiveZero.bits ≠ negativeZero.bits := by
  native_decide

@[simp] theorem positiveZero_toReal : positiveZero.toReal = 0 := by
  rw [toReal_eq_zero_iff]
  native_decide

@[simp] theorem negativeZero_toReal : negativeZero.toReal = 0 := by
  rw [toReal_eq_zero_iff]
  native_decide

@[simp] theorem leastPositiveSubnormal_significand :
    leastPositiveSubnormal.significand = 1 := by
  native_decide

@[simp] theorem leastPositiveSubnormal_exponent :
    leastPositiveSubnormal.exponent = -1074 := by
  native_decide

@[simp] theorem greatestPositiveFinite_significand :
    greatestPositiveFinite.significand = 9007199254740991 := by
  native_decide

@[simp] theorem greatestPositiveFinite_exponent :
    greatestPositiveFinite.exponent = 971 := by
  native_decide

@[simp] theorem greatestPositiveFinite_sign :
    greatestPositiveFinite.sign = false := by
  native_decide

theorem abs_toReal_eq_magnitude (x : Binary64Finite) :
    |x.toReal| = x.magnitude := by
  unfold toReal
  split <;> simp [abs_of_nonneg x.magnitude_nonneg]

theorem magnitude_le_greatestPositiveFinite (x : Binary64Finite) :
    x.magnitude ≤ greatestPositiveFinite.magnitude := by
  have hsigNat : x.significand ≤ 9007199254740991 := by
    have hlt := x.significand_lt_two_mul_modulus
    norm_num [Binary64Bits.fractionModulus] at hlt ⊢
    omega
  have hsig : (x.significand : ℝ) ≤ (9007199254740991 : ℝ) := by
    exact_mod_cast hsigNat
  have hpow : (2 : ℝ) ^ x.exponent ≤ (2 : ℝ) ^ (971 : Int) := by
    exact zpow_le_zpow_right₀ (by norm_num) x.exponent_bounds.2
  rw [magnitude, magnitude, greatestPositiveFinite_significand,
    greatestPositiveFinite_exponent]
  calc
    (x.significand : ℝ) * (2 : ℝ) ^ x.exponent ≤
        (9007199254740991 : ℝ) * (2 : ℝ) ^ x.exponent :=
      mul_le_mul_of_nonneg_right hsig (zpow_nonneg (by norm_num) _)
    _ ≤ (9007199254740991 : ℝ) * (2 : ℝ) ^ (971 : Int) :=
      mul_le_mul_of_nonneg_left hpow (by norm_num)

theorem toReal_le_greatestPositiveFinite (x : Binary64Finite) :
    x.toReal ≤ greatestPositiveFinite.toReal := by
  calc
    x.toReal ≤ |x.toReal| := le_abs_self _
    _ = x.magnitude := x.abs_toReal_eq_magnitude
    _ ≤ greatestPositiveFinite.magnitude := x.magnitude_le_greatestPositiveFinite
    _ = greatestPositiveFinite.toReal := by
      rw [toReal_of_sign_false greatestPositiveFinite
        greatestPositiveFinite_sign]

theorem neg_greatestPositiveFinite_le_toReal (x : Binary64Finite) :
    -greatestPositiveFinite.toReal ≤ x.toReal := by
  have h := x.toReal_le_greatestPositiveFinite
  have habs : |x.toReal| ≤ greatestPositiveFinite.toReal := by
    rw [x.abs_toReal_eq_magnitude,
      greatestPositiveFinite.toReal_of_sign_false greatestPositiveFinite_sign]
    exact x.magnitude_le_greatestPositiveFinite
  exact neg_le_of_abs_le habs

end Binary64Finite

namespace Binary64Bits

/-- Decode a word exactly when it is finite.  Infinity and NaN produce
`none`; no arbitrary real value is assigned to them. -/
noncomputable def decodeFinite? (x : Binary64Bits) : Option ℝ :=
  if h : x.IsFinite then
    some (Binary64Finite.toReal ⟨x, h⟩)
  else
    none

theorem decodeFinite?_eq_none_iff (x : Binary64Bits) :
    x.decodeFinite? = none ↔ ¬x.IsFinite := by
  simp [decodeFinite?]

theorem decodeFinite?_eq_some (x : Binary64Finite) :
    x.bits.decodeFinite? = some x.toReal := by
  simp only [decodeFinite?, x.finite, ↓reduceDIte]

end Binary64Bits

end SparkInterval
