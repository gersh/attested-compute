import SparkInterval.FloatFormat

/-!
# Mathematical directed rounding for binary64

The definitions in this file are deliberately non-executable specifications.
They enumerate the finite set of exact real values decoded by
`Binary64Finite` and select mathematical extrema.  A later executable
integer/dyadic implementation can be proved to refine this specification;
Lean's native `Float` is not part of the definition.

Finite *encodings* retain their sign bit, so positive and negative zero remain
distinct in `Binary64Finite`.  Rounding a mathematical real uses
`Binary64Value`, the image quotient by `toReal`; this necessarily identifies
the two zero encodings because `ℝ` itself has only one zero.  Operation-level
bit semantics must impose IEEE's signed-zero rule separately.
-/

set_option autoImplicit false

namespace SparkInterval

/-- The finite set of numeric values represented by finite binary64 words.
Unlike `Binary64Finite.allFinite`, this image contains zero only once. -/
noncomputable def binary64RepresentableValues : Finset ℝ :=
  (Set.finite_range Binary64Finite.toReal).toFinset

/-- Exact numeric representability by at least one finite binary64 encoding. -/
def IsBinary64Representable (x : ℝ) : Prop :=
  x ∈ binary64RepresentableValues

theorem mem_binary64RepresentableValues_iff {x : ℝ} :
    x ∈ binary64RepresentableValues ↔
      ∃ b : Binary64Finite, b.toReal = x := by
  simp [binary64RepresentableValues]

theorem isBinary64Representable_iff {x : ℝ} :
    IsBinary64Representable x ↔ ∃ b : Binary64Finite, b.toReal = x :=
  mem_binary64RepresentableValues_iff

theorem binary64Finite_mem_representableValues (b : Binary64Finite) :
    b.toReal ∈ binary64RepresentableValues := by
  exact mem_binary64RepresentableValues_iff.mpr ⟨b, rfl⟩

/-- A finite binary64 *numeric value*.  Bit-distinct encodings with the same
exact real interpretation (precisely the two signed zeros) inhabit the same
subtype value. -/
abbrev Binary64Value := {x : ℝ // x ∈ binary64RepresentableValues}

/-- Forget the encoding while retaining proof of exact binary64
representability. -/
noncomputable def Binary64Finite.asValue (b : Binary64Finite) : Binary64Value :=
  ⟨b.toReal, binary64Finite_mem_representableValues b⟩

theorem Binary64Finite.signedZeros_asValue_eq :
    positiveZero.asValue = negativeZero.asValue := by
  apply Subtype.ext
  change positiveZero.toReal = negativeZero.toReal
  simp

theorem binary64RepresentableValues_nonempty :
    binary64RepresentableValues.Nonempty :=
  ⟨0, mem_binary64RepresentableValues_iff.mpr
    ⟨Binary64Finite.positiveZero, by simp⟩⟩

/-- Numeric binary64 endpoints, including the two infinities but excluding
NaN. -/
inductive ExtBinary64 where
  | negInf
  | finite (value : Binary64Value)
  | posInf

namespace ExtBinary64

/-- Exact interpretation in the extended real line. -/
noncomputable def toEReal : ExtBinary64 → EReal
  | .negInf => ⊥
  | .finite value => (value.1 : EReal)
  | .posInf => ⊤

end ExtBinary64

namespace Binary64Rounding

/-- All finite binary64 values no greater than `x`. -/
noncomputable def lowerCandidates (x : ℝ) : Finset ℝ :=
  binary64RepresentableValues.filter fun y => y ≤ x

/-- All finite binary64 values no less than `x`. -/
noncomputable def upperCandidates (x : ℝ) : Finset ℝ :=
  binary64RepresentableValues.filter fun y => x ≤ y

/-- Finite binary64 values strictly below a representable value. -/
noncomputable def strictLowerCandidates (x : Binary64Value) : Finset ℝ :=
  binary64RepresentableValues.filter fun y => y < x.1

/-- Finite binary64 values strictly above a representable value. -/
noncomputable def strictUpperCandidates (x : Binary64Value) : Finset ℝ :=
  binary64RepresentableValues.filter fun y => x.1 < y

/-- The immediately preceding numeric binary64 value, or negative infinity at
the lower finite boundary.  Signed zero is a single numeric value here; bit
level signed-zero behavior remains an operation-specific refinement. -/
noncomputable def predecessor (x : Binary64Value) : ExtBinary64 :=
  if h : (strictLowerCandidates x).Nonempty then
    .finite ⟨(strictLowerCandidates x).max' h,
      (Finset.mem_filter.mp (Finset.max'_mem _ h)).1⟩
  else
    .negInf

/-- The immediately following numeric binary64 value, or positive infinity at
the upper finite boundary. -/
noncomputable def successor (x : Binary64Value) : ExtBinary64 :=
  if h : (strictUpperCandidates x).Nonempty then
    .finite ⟨(strictUpperCandidates x).min' h,
      (Finset.mem_filter.mp (Finset.min'_mem _ h)).1⟩
  else
    .posInf

theorem predecessor_lt (x : Binary64Value) :
    (predecessor x).toEReal < (x.1 : EReal) := by
  classical
  rw [predecessor]
  split
  next h =>
    exact EReal.coe_lt_coe_iff.mpr
      (Finset.mem_filter.mp (Finset.max'_mem (strictLowerCandidates x) h)).2
  next => simp [ExtBinary64.toEReal]

theorem lt_successor (x : Binary64Value) :
    (x.1 : EReal) < (successor x).toEReal := by
  classical
  rw [successor]
  split
  next h =>
    exact EReal.coe_lt_coe_iff.mpr
      (Finset.mem_filter.mp (Finset.min'_mem (strictUpperCandidates x) h)).2
  next => simp [ExtBinary64.toEReal]

/-- No representable value lies strictly between `predecessor x` and `x`. -/
theorem le_predecessor_of_lt (x : Binary64Value) (y : Binary64Finite)
    (hy : y.toReal < x.1) :
    (y.toReal : EReal) ≤ (predecessor x).toEReal := by
  classical
  have hymem : y.toReal ∈ strictLowerCandidates x :=
    Finset.mem_filter.mpr
      ⟨binary64Finite_mem_representableValues y, hy⟩
  have hne : (strictLowerCandidates x).Nonempty := ⟨y.toReal, hymem⟩
  rw [predecessor]
  simp only [dif_pos hne, ExtBinary64.toEReal]
  exact EReal.coe_le_coe_iff.mpr (Finset.le_max' _ _ hymem)

/-- No representable value lies strictly between `x` and `successor x`. -/
theorem successor_le_of_lt (x : Binary64Value) (y : Binary64Finite)
    (hy : x.1 < y.toReal) :
    (successor x).toEReal ≤ (y.toReal : EReal) := by
  classical
  have hymem : y.toReal ∈ strictUpperCandidates x :=
    Finset.mem_filter.mpr
      ⟨binary64Finite_mem_representableValues y, hy⟩
  have hne : (strictUpperCandidates x).Nonempty := ⟨y.toReal, hymem⟩
  rw [successor]
  simp only [dif_pos hne, ExtBinary64.toEReal]
  exact EReal.coe_le_coe_iff.mpr (Finset.min'_le _ _ hymem)

/-- Round toward negative infinity. -/
noncomputable def roundDown (x : ℝ) : ExtBinary64 :=
  if h : (lowerCandidates x).Nonempty then
    .finite ⟨(lowerCandidates x).max' h,
      (Finset.mem_filter.mp (Finset.max'_mem _ h)).1⟩
  else
    .negInf

/-- Round toward positive infinity. -/
noncomputable def roundUp (x : ℝ) : ExtBinary64 :=
  if h : (upperCandidates x).Nonempty then
    .finite ⟨(upperCandidates x).min' h,
      (Finset.mem_filter.mp (Finset.min'_mem _ h)).1⟩
  else
    .posInf

theorem roundDown_le (x : ℝ) :
    (roundDown x).toEReal ≤ (x : EReal) := by
  classical
  rw [roundDown]
  split
  next h =>
    exact EReal.coe_le_coe_iff.mpr
      (Finset.mem_filter.mp (Finset.max'_mem (lowerCandidates x) h)).2
  next => simp [ExtBinary64.toEReal]

theorem le_roundUp (x : ℝ) :
    (x : EReal) ≤ (roundUp x).toEReal := by
  classical
  rw [roundUp]
  split
  next h =>
    exact EReal.coe_le_coe_iff.mpr
      (Finset.mem_filter.mp (Finset.min'_mem (upperCandidates x) h)).2
  next => simp [ExtBinary64.toEReal]

/-- `roundDown x` is at least every finite representable value below `x`. -/
theorem roundDown_greatest (y : Binary64Finite) {x : ℝ}
    (hy : y.toReal ≤ x) :
    (y.toReal : EReal) ≤ (roundDown x).toEReal := by
  classical
  have hymem : y.toReal ∈ lowerCandidates x := by
    exact Finset.mem_filter.mpr
      ⟨binary64Finite_mem_representableValues y, hy⟩
  have hne : (lowerCandidates x).Nonempty := ⟨y.toReal, hymem⟩
  rw [roundDown]
  simp only [dif_pos hne, ExtBinary64.toEReal]
  exact EReal.coe_le_coe_iff.mpr (Finset.le_max' _ _ hymem)

/-- `roundUp x` is at most every finite representable value above `x`. -/
theorem roundUp_least (y : Binary64Finite) {x : ℝ}
    (hy : x ≤ y.toReal) :
    (roundUp x).toEReal ≤ (y.toReal : EReal) := by
  classical
  have hymem : y.toReal ∈ upperCandidates x := by
    exact Finset.mem_filter.mpr
      ⟨binary64Finite_mem_representableValues y, hy⟩
  have hne : (upperCandidates x).Nonempty := ⟨y.toReal, hymem⟩
  rw [roundUp]
  simp only [dif_pos hne, ExtBinary64.toEReal]
  exact EReal.coe_le_coe_iff.mpr (Finset.min'_le _ _ hymem)

/-- The least finite binary64 real value, defined extensionally. -/
noncomputable def minFiniteReal : ℝ :=
  binary64RepresentableValues.min' binary64RepresentableValues_nonempty

/-- The greatest finite binary64 real value, defined extensionally. -/
noncomputable def maxFiniteReal : ℝ :=
  binary64RepresentableValues.max' binary64RepresentableValues_nonempty

noncomputable def minFinite : Binary64Value :=
  ⟨minFiniteReal, Finset.min'_mem _ _⟩

noncomputable def maxFinite : Binary64Value :=
  ⟨maxFiniteReal, Finset.max'_mem _ _⟩

theorem minFinite_le (y : Binary64Value) : minFiniteReal ≤ y.1 := by
  exact Finset.min'_le _ _ y.2

theorem le_maxFinite (y : Binary64Value) : y.1 ≤ maxFiniteReal := by
  exact Finset.le_max' _ _ y.2

theorem maxFiniteReal_eq_greatestPositiveFinite :
    maxFiniteReal = Binary64Finite.greatestPositiveFinite.toReal := by
  apply le_antisymm
  · have hmem : maxFiniteReal ∈ binary64RepresentableValues :=
      Finset.max'_mem _ _
    rcases mem_binary64RepresentableValues_iff.mp hmem with ⟨b, hb⟩
    rw [← hb]
    exact Binary64Finite.toReal_le_greatestPositiveFinite b
  · exact Finset.le_max' _ _
      (binary64Finite_mem_representableValues
        Binary64Finite.greatestPositiveFinite)

theorem minFiniteReal_eq_neg_greatestPositiveFinite :
    minFiniteReal = -Binary64Finite.greatestPositiveFinite.toReal := by
  apply le_antisymm
  · let negGreatest : Binary64Finite :=
      ⟨BitVec.ofNat 64 0xffefffffffffffff, by native_decide⟩
    have hneg : negGreatest.toReal =
        -Binary64Finite.greatestPositiveFinite.toReal := by
      -- The two encodings have identical magnitude fields and opposite signs.
      norm_num [negGreatest, Binary64Finite.greatestPositiveFinite,
        Binary64Finite.toReal, Binary64Finite.magnitude,
        Binary64Finite.sign, Binary64Finite.significand, Binary64Finite.exponent,
        Binary64Bits.signBit, Binary64Bits.signThreshold,
        Binary64Bits.exponentBits, Binary64Bits.exponentModulus,
        Binary64Bits.fractionBits, Binary64Bits.fractionModulus]
    rw [← hneg]
    exact Finset.min'_le _ _
      (binary64Finite_mem_representableValues negGreatest)
  · have hmem : minFiniteReal ∈ binary64RepresentableValues :=
      Finset.min'_mem _ _
    rcases mem_binary64RepresentableValues_iff.mp hmem with ⟨b, hb⟩
    rw [← hb]
    exact Binary64Finite.neg_greatestPositiveFinite_le_toReal b

theorem lowerCandidates_eq_all {x : ℝ} (h : maxFiniteReal ≤ x) :
    lowerCandidates x = binary64RepresentableValues := by
  classical
  ext y
  simp only [lowerCandidates, Finset.mem_filter]
  constructor
  · exact And.left
  · intro hy
    exact ⟨hy, (Finset.le_max' _ _ hy).trans h⟩

theorem upperCandidates_eq_all {x : ℝ} (h : x ≤ minFiniteReal) :
    upperCandidates x = binary64RepresentableValues := by
  classical
  ext y
  simp only [upperCandidates, Finset.mem_filter]
  constructor
  · exact And.left
  · intro hy
    exact ⟨hy, h.trans (Finset.min'_le _ _ hy)⟩

theorem roundDown_of_maxFinite_le {x : ℝ} (h : maxFiniteReal ≤ x) :
    roundDown x = .finite maxFinite := by
  classical
  simp [roundDown, lowerCandidates_eq_all h,
    binary64RepresentableValues_nonempty, maxFinite, maxFiniteReal]

theorem roundUp_of_le_minFinite {x : ℝ} (h : x ≤ minFiniteReal) :
    roundUp x = .finite minFinite := by
  classical
  simp [roundUp, upperCandidates_eq_all h,
    binary64RepresentableValues_nonempty, minFinite, minFiniteReal]

theorem lowerCandidates_empty_of_lt_minFinite {x : ℝ}
    (h : x < minFiniteReal) : lowerCandidates x = ∅ := by
  classical
  apply Finset.eq_empty_iff_forall_notMem.mpr
  intro y hy
  have hyr := (Finset.mem_filter.mp hy).1
  have hyx := (Finset.mem_filter.mp hy).2
  exact (not_le_of_gt h) ((Finset.min'_le _ _ hyr).trans hyx)

theorem upperCandidates_empty_of_maxFinite_lt {x : ℝ}
    (h : maxFiniteReal < x) : upperCandidates x = ∅ := by
  classical
  apply Finset.eq_empty_iff_forall_notMem.mpr
  intro y hy
  have hyr := (Finset.mem_filter.mp hy).1
  have hxy := (Finset.mem_filter.mp hy).2
  exact (not_le_of_gt h) (hxy.trans (Finset.le_max' _ _ hyr))

theorem roundDown_eq_negInf_of_lt_minFinite {x : ℝ}
    (h : x < minFiniteReal) : roundDown x = .negInf := by
  classical
  simp [roundDown, lowerCandidates_empty_of_lt_minFinite h]

theorem roundUp_eq_posInf_of_maxFinite_lt {x : ℝ}
    (h : maxFiniteReal < x) : roundUp x = .posInf := by
  classical
  simp [roundUp, upperCandidates_empty_of_maxFinite_lt h]

theorem roundDown_exact (y : Binary64Value) :
    roundDown y.1 = .finite y := by
  classical
  have hymem : y.1 ∈ lowerCandidates y.1 :=
    Finset.mem_filter.mpr ⟨y.2, le_rfl⟩
  have hne : (lowerCandidates y.1).Nonempty := ⟨y.1, hymem⟩
  rw [roundDown]
  simp only [dif_pos hne]
  congr 2
  apply le_antisymm
  · exact (Finset.mem_filter.mp (Finset.max'_mem _ hne)).2
  · exact Finset.le_max' _ _ hymem

theorem roundUp_exact (y : Binary64Value) :
    roundUp y.1 = .finite y := by
  classical
  have hymem : y.1 ∈ upperCandidates y.1 :=
    Finset.mem_filter.mpr ⟨y.2, le_rfl⟩
  have hne : (upperCandidates y.1).Nonempty := ⟨y.1, hymem⟩
  rw [roundUp]
  simp only [dif_pos hne]
  congr 2
  apply le_antisymm
  · exact Finset.min'_le _ _ hymem
  · exact (Finset.mem_filter.mp (Finset.min'_mem _ hne)).2

theorem roundDown_signed_zero :
    roundDown Binary64Finite.positiveZero.toReal =
      .finite Binary64Finite.negativeZero.asValue := by
  calc
    roundDown Binary64Finite.positiveZero.toReal =
        .finite Binary64Finite.positiveZero.asValue :=
      roundDown_exact Binary64Finite.positiveZero.asValue
    _ = .finite Binary64Finite.negativeZero.asValue :=
      congrArg ExtBinary64.finite Binary64Finite.signedZeros_asValue_eq

theorem roundUp_signed_zero :
    roundUp Binary64Finite.negativeZero.toReal =
      .finite Binary64Finite.positiveZero.asValue := by
  calc
    roundUp Binary64Finite.negativeZero.toReal =
        .finite Binary64Finite.negativeZero.asValue :=
      roundUp_exact Binary64Finite.negativeZero.asValue
    _ = .finite Binary64Finite.positiveZero.asValue :=
      congrArg ExtBinary64.finite Binary64Finite.signedZeros_asValue_eq.symm

/-! ## Candidate specification for round to nearest, ties to even

The selector below is definitionally nearest and prefers an even-significand
nearest candidate.  A complete IEEE characterization still requires the
separate adjacency/parity theorem that every genuine binary64 midpoint has
such an even candidate.  Directed interval arithmetic does not depend on this
unfinished nearest-even lemma.
-/

/-- Distances from `x` to all finite binary64 numeric values. -/
noncomputable def finiteDistances (x : ℝ) : Finset ℝ :=
  binary64RepresentableValues.image fun y => |x - y|

theorem finiteDistances_nonempty (x : ℝ) : (finiteDistances x).Nonempty := by
  exact binary64RepresentableValues_nonempty.image fun y => |x - y|

/-- The distance from `x` to its nearest finite binary64 value. -/
noncomputable def nearestDistance (x : ℝ) : ℝ :=
  (finiteDistances x).min' (finiteDistances_nonempty x)

theorem nearestDistance_nonneg (x : ℝ) : 0 ≤ nearestDistance x := by
  have hmem := Finset.min'_mem (finiteDistances x) (finiteDistances_nonempty x)
  rcases Finset.mem_image.mp hmem with ⟨y, _, hy⟩
  unfold nearestDistance
  rw [← hy]
  exact abs_nonneg _

theorem nearestDistance_le (x : ℝ) {y : ℝ}
    (hy : y ∈ binary64RepresentableValues) :
    nearestDistance x ≤ |x - y| := by
  exact Finset.min'_le _ _ (Finset.mem_image.mpr ⟨y, hy, rfl⟩)

/-- All finite numeric values at minimum distance from `x`. -/
noncomputable def nearestCandidates (x : ℝ) : Finset ℝ :=
  binary64RepresentableValues.filter fun y =>
    |x - y| = nearestDistance x

theorem nearestCandidates_nonempty (x : ℝ) :
    (nearestCandidates x).Nonempty := by
  have hmem := Finset.min'_mem (finiteDistances x) (finiteDistances_nonempty x)
  rcases Finset.mem_image.mp hmem with ⟨y, hy, hdist⟩
  exact ⟨y, Finset.mem_filter.mpr ⟨hy, hdist⟩⟩

/-- A numeric value has even significand when at least one finite encoding of
that value does.  The existential formulation is important at zero, where two
different bit patterns decode to the same numeric value. -/
def HasEvenSignificand (y : ℝ) : Prop :=
  ∃ b : Binary64Finite, b.toReal = y ∧ Even b.significand

/-- The nearest candidates carrying an even-significand encoding. -/
noncomputable def evenNearestCandidates (x : ℝ) : Finset ℝ :=
  by
    classical
    exact (nearestCandidates x).filter HasEvenSignificand

/-- Select a nearest finite value, preferring an even-significand witness
whenever one exists.  The fallback chooses an unspecified nearest value, not
the lower endpoint of a tie.  It covers the ordinary unique-nearest case;
proving that every binary64 midpoint has an even candidate will later show
that it is never used to resolve a genuine two-way tie. -/
noncomputable def nearestFinite (x : ℝ) : Binary64Value :=
  by
    classical
    exact if h : (evenNearestCandidates x).Nonempty then
      ⟨h.choose,
        (Finset.mem_filter.mp
          (Finset.mem_filter.mp h.choose_spec).1).1⟩
    else
      let hnear := nearestCandidates_nonempty x
      ⟨hnear.choose, (Finset.mem_filter.mp hnear.choose_spec).1⟩

theorem nearestFinite_mem_nearestCandidates (x : ℝ) :
    (nearestFinite x).1 ∈ nearestCandidates x := by
  classical
  rw [nearestFinite]
  split
  next h => exact (Finset.mem_filter.mp h.choose_spec).1
  next => exact (nearestCandidates_nonempty x).choose_spec

theorem nearestFinite_distance (x : ℝ) :
    |x - (nearestFinite x).1| = nearestDistance x := by
  exact (Finset.mem_filter.mp (nearestFinite_mem_nearestCandidates x)).2

/-- The selected finite result is no farther from `x` than any finite
binary64 encoding. -/
theorem nearestFinite_isNearest (x : ℝ) (y : Binary64Finite) :
    |x - (nearestFinite x).1| ≤ |x - y.toReal| := by
  rw [nearestFinite_distance]
  exact nearestDistance_le x (binary64Finite_mem_representableValues y)

/-- If an even-significand nearest candidate exists, the selector chooses
one.  This is the tie-preference clause of round-to-nearest-even. -/
theorem nearestFinite_hasEvenSignificand {x : ℝ}
    (h : (evenNearestCandidates x).Nonempty) :
    HasEvenSignificand (nearestFinite x).1 := by
  classical
  rw [nearestFinite, dif_pos h]
  exact (Finset.mem_filter.mp h.choose_spec).2

theorem nearestDistance_eq_zero (y : Binary64Value) :
    nearestDistance y.1 = 0 := by
  apply le_antisymm
  · simpa using nearestDistance_le y.1 y.2
  · exact nearestDistance_nonneg y.1

theorem nearestCandidates_exact (y : Binary64Value) :
    nearestCandidates y.1 = {y.1} := by
  classical
  ext z
  constructor
  · intro hz
    have hdist := (Finset.mem_filter.mp hz).2
    rw [nearestDistance_eq_zero y] at hdist
    have : y.1 - z = 0 := abs_eq_zero.mp hdist
    simp only [sub_eq_zero] at this
    simp [this]
  · intro hz
    have hzy : z = y.1 := by simpa using hz
    subst z
    exact Finset.mem_filter.mpr
      ⟨y.2, by simp [nearestDistance_eq_zero y]⟩

theorem nearestFinite_exact (y : Binary64Value) : nearestFinite y.1 = y := by
  apply Subtype.ext
  have hmem := nearestFinite_mem_nearestCandidates y.1
  rw [nearestCandidates_exact y] at hmem
  simpa using hmem

/-- Half of the spacing beyond the greatest finite binade.  At this exact
threshold IEEE roundTiesToEven selects the hypothetical even value `2^1024`,
which is encoded as infinity; below it, the greatest finite value is nearer. -/
noncomputable def nearestEvenOverflowThreshold : ℝ :=
  Binary64Finite.greatestPositiveFinite.toReal + (2 : ℝ) ^ 970

theorem greatestPositiveFinite_toReal_pos :
    0 < Binary64Finite.greatestPositiveFinite.toReal := by
  rw [Binary64Finite.toReal_of_sign_false _
    Binary64Finite.greatestPositiveFinite_sign]
  simp only [Binary64Finite.magnitude,
    Binary64Finite.greatestPositiveFinite_significand,
    Binary64Finite.greatestPositiveFinite_exponent]
  positivity

theorem nearestEvenOverflowThreshold_pos : 0 < nearestEvenOverflowThreshold := by
  unfold nearestEvenOverflowThreshold
  exact add_pos greatestPositiveFinite_toReal_pos (by positivity)

/-- Value-level candidate for round-to-nearest, ties-to-even.

Inside the overflow thresholds, `nearestFinite` minimizes exact real distance
and prefers an even-significand witness.  At either threshold and beyond, the
result is the corresponding infinity, matching IEEE overflow under
roundTiesToEven.  Its unconditional midpoint-parity characterization remains
an explicit later proof obligation. -/
noncomputable def roundNearestEven (x : ℝ) : ExtBinary64 :=
  if nearestEvenOverflowThreshold ≤ x then
    .posInf
  else if x ≤ -nearestEvenOverflowThreshold then
    .negInf
  else
    .finite (nearestFinite x)

theorem roundNearestEven_eq_posInf {x : ℝ}
    (h : nearestEvenOverflowThreshold ≤ x) :
    roundNearestEven x = .posInf := by
  simp [roundNearestEven, h]

theorem roundNearestEven_eq_negInf {x : ℝ}
    (h : x ≤ -nearestEvenOverflowThreshold) :
    roundNearestEven x = .negInf := by
  have hnot : ¬nearestEvenOverflowThreshold ≤ x := by
    have hsep : -nearestEvenOverflowThreshold < nearestEvenOverflowThreshold :=
      neg_lt_self nearestEvenOverflowThreshold_pos
    exact not_le.mpr (h.trans_lt hsep)
  simp [roundNearestEven, h, hnot]

theorem roundNearestEven_of_between {x : ℝ}
    (hlo : -nearestEvenOverflowThreshold < x)
    (hhi : x < nearestEvenOverflowThreshold) :
    roundNearestEven x = .finite (nearestFinite x) := by
  simp [roundNearestEven, not_le.mpr hhi, not_le.mpr hlo]

theorem roundNearestEven_exact (y : Binary64Value) :
    roundNearestEven y.1 = .finite y := by
  have hymax := le_maxFinite y
  have hymin := minFinite_le y
  rw [maxFiniteReal_eq_greatestPositiveFinite] at hymax
  rw [minFiniteReal_eq_neg_greatestPositiveFinite] at hymin
  have hhalf : 0 < (2 : ℝ) ^ 970 := by positivity
  have hhi : y.1 < nearestEvenOverflowThreshold := by
    rw [nearestEvenOverflowThreshold]
    exact hymax.trans_lt (lt_add_of_pos_right _ hhalf)
  have hlo : -nearestEvenOverflowThreshold < y.1 := by
    rw [nearestEvenOverflowThreshold]
    calc
      -(Binary64Finite.greatestPositiveFinite.toReal + (2 : ℝ) ^ 970) <
          -Binary64Finite.greatestPositiveFinite.toReal :=
        neg_lt_neg (lt_add_of_pos_right _ hhalf)
      _ ≤ y.1 := hymin
  rw [roundNearestEven_of_between hlo hhi, nearestFinite_exact]

theorem roundNearestEven_signed_zero :
    roundNearestEven Binary64Finite.positiveZero.toReal =
      .finite Binary64Finite.negativeZero.asValue := by
  calc
    roundNearestEven Binary64Finite.positiveZero.toReal =
        .finite Binary64Finite.positiveZero.asValue :=
      roundNearestEven_exact Binary64Finite.positiveZero.asValue
    _ = .finite Binary64Finite.negativeZero.asValue :=
      congrArg ExtBinary64.finite Binary64Finite.signedZeros_asValue_eq

end Binary64Rounding

end SparkInterval
