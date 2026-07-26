/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiEndpointArithmetic

/-!
# Affine incoming-state guards for the CH25 psi campaign

A source shard adds fixed directed Q64 deltas to the state supplied by the
preceding shard.  Consequently, all lower-envelope checks are monotone in the
incoming lower endpoint and all upper-envelope checks are antitone in the
incoming upper endpoint.

These lemmas justify a one-pass shard representation: a worker may retain the
extremal admissible incoming endpoints and their witness rows, while the
ordered campaign checks that the root-derived incoming state lies inside that
interval.  They do not identify native arithmetic with Lean arithmetic and do
not supply source-scale evidence.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.TernaryGoldbach.PsiAffineGuards

open PsiSourceSemantics

def rootScale : Nat := 2 ^ 16
def radiusShift : Nat := 2 ^ 48

private theorem rootScale_pos : 0 < rootScale := by
  simp [rootScale]

private theorem radiusShift_pos : 0 < radiusShift := by
  simp [radiusShift]

private theorem scale_factorization :
    rootScale ^ 2 * radiusShift ^ 2 = scale ^ 2 := by
  simp only [rootScale, radiusShift, scale]
  norm_num [← pow_mul, ← pow_add]

/-- Convert the worker's exact fixed-point `sqrt (2 * right)` floor into the
Q64 radius consumed by `LowerEndpointSafe`. -/
def lowerRadiusQ64 (rootQ16 : Nat) : Nat :=
  rootQ16 * radiusShift

/-- The source endpoint needs a strict lower inequality.  A Q64 inward step is
needed exactly when the Q16 square lands on the boundary. -/
def strictLowerRadiusQ64 (right rootQ16 : Nat) : Nat :=
  if rootQ16 ^ 2 = 2 * right * rootScale ^ 2 then
    lowerRadiusQ64 rootQ16 - 1
  else
    lowerRadiusQ64 rootQ16

/-- Convert the worker's exact fixed-point `sqrt left` floor into its
conservative rational upper-envelope radius. -/
def upperRadiusQ64 (rootQ16 : Nat) : Nat :=
  upperNumerator * rootQ16 * radiusShift / upperDenominator

/-- The Q16 square check used by the worker implies the exact Q64 lower-radius
check used by Lean. -/
theorem lowerRadiusQ64_sq_le
    {right rootQ16 : Nat}
    (hroot : rootQ16 ^ 2 ≤ 2 * right * rootScale ^ 2) :
    lowerRadiusQ64 rootQ16 ^ 2 ≤ 2 * right * scale ^ 2 := by
  calc
    lowerRadiusQ64 rootQ16 ^ 2 =
        rootQ16 ^ 2 * radiusShift ^ 2 := by
          simp only [lowerRadiusQ64]
          ring
    _ ≤ (2 * right * rootScale ^ 2) * radiusShift ^ 2 :=
      Nat.mul_le_mul_right _ hroot
    _ = 2 * right * scale ^ 2 := by
      calc
        (2 * right * rootScale ^ 2) * radiusShift ^ 2 =
            2 * right * (rootScale ^ 2 * radiusShift ^ 2) := by ring
        _ = 2 * right * scale ^ 2 := by rw [scale_factorization]

/-- Strict Q16 inward radii remain strict after conversion to Q64. -/
theorem lowerRadiusQ64_sq_lt
    {right rootQ16 : Nat}
    (hroot : rootQ16 ^ 2 < 2 * right * rootScale ^ 2) :
    lowerRadiusQ64 rootQ16 ^ 2 < 2 * right * scale ^ 2 := by
  calc
    lowerRadiusQ64 rootQ16 ^ 2 =
        rootQ16 ^ 2 * radiusShift ^ 2 := by
          simp only [lowerRadiusQ64]
          ring
    _ < (2 * right * rootScale ^ 2) * radiusShift ^ 2 :=
      Nat.mul_lt_mul_of_pos_right hroot (pow_pos radiusShift_pos 2)
    _ = 2 * right * scale ^ 2 := by
      calc
        (2 * right * rootScale ^ 2) * radiusShift ^ 2 =
            2 * right * (rootScale ^ 2 * radiusShift ^ 2) := by ring
        _ = 2 * right * scale ^ 2 := by rw [scale_factorization]

private theorem inward_one_sq_lt
    {radius bound : Nat} (hradius : 0 < radius)
    (hequality : radius ^ 2 = bound) :
    (radius - 1) ^ 2 < bound := by
  calc
    (radius - 1) ^ 2 < radius ^ 2 :=
      Nat.pow_lt_pow_left
        (Nat.sub_lt hradius (by norm_num)) (by norm_num)
    _ = bound := hequality

/-- The worker's equality-triggered one-unit correction supplies the strict
Q64 radius needed at the closed source endpoint. -/
theorem strictLowerRadiusQ64_sq_lt
    {right rootQ16 : Nat} (hright : 0 < right)
    (hroot : rootQ16 ^ 2 ≤ 2 * right * rootScale ^ 2) :
    strictLowerRadiusQ64 right rootQ16 ^ 2 <
      2 * right * scale ^ 2 := by
  by_cases hequality : rootQ16 ^ 2 = 2 * right * rootScale ^ 2
  · simp only [strictLowerRadiusQ64, hequality, ↓reduceIte]
    have hrootPositive : 0 < rootQ16 := by
      by_contra hnot
      have hzero : rootQ16 = 0 := Nat.eq_zero_of_not_pos hnot
      have hrightside : 0 < 2 * right * rootScale ^ 2 :=
        Nat.mul_pos (Nat.mul_pos (by norm_num) hright)
          (pow_pos rootScale_pos 2)
      simp only [hzero, zero_pow (by norm_num : 2 ≠ 0)] at hequality
      omega
    have hradiusPositive : 0 < lowerRadiusQ64 rootQ16 :=
      Nat.mul_pos hrootPositive radiusShift_pos
    apply inward_one_sq_lt hradiusPositive
    calc
      lowerRadiusQ64 rootQ16 ^ 2 =
          rootQ16 ^ 2 * radiusShift ^ 2 := by
            simp only [lowerRadiusQ64]
            ring
      _ = (2 * right * rootScale ^ 2) * radiusShift ^ 2 := by
        rw [hequality]
      _ = 2 * right * scale ^ 2 := by
        calc
          (2 * right * rootScale ^ 2) * radiusShift ^ 2 =
              2 * right * (rootScale ^ 2 * radiusShift ^ 2) := by ring
          _ = 2 * right * scale ^ 2 := by rw [scale_factorization]
  · simp only [strictLowerRadiusQ64, hequality, ↓reduceIte]
    exact lowerRadiusQ64_sq_lt (lt_of_le_of_ne hroot hequality)

/-- The truncated rational Q16 radius used for the upper envelope is
conservative at Q64 precision. -/
theorem upperRadiusQ64_sq_le
    {left rootQ16 : Nat}
    (hroot : rootQ16 ^ 2 ≤ left * rootScale ^ 2) :
    upperRadiusQ64 rootQ16 ^ 2 * upperDenominator ^ 2 ≤
      upperNumerator ^ 2 * left * scale ^ 2 := by
  let numeratorQ64 := upperNumerator * rootQ16 * radiusShift
  have hdivision :
      upperRadiusQ64 rootQ16 * upperDenominator ≤ numeratorQ64 := by
    simpa only [upperRadiusQ64, numeratorQ64] using
      Nat.div_mul_le_self numeratorQ64 upperDenominator
  calc
    upperRadiusQ64 rootQ16 ^ 2 * upperDenominator ^ 2 =
        (upperRadiusQ64 rootQ16 * upperDenominator) ^ 2 := by ring
    _ ≤ numeratorQ64 ^ 2 := Nat.pow_le_pow_left hdivision 2
    _ = upperNumerator ^ 2 * rootQ16 ^ 2 * radiusShift ^ 2 := by
      simp only [numeratorQ64]
      ring
    _ ≤ upperNumerator ^ 2 * (left * rootScale ^ 2) *
        radiusShift ^ 2 :=
      Nat.mul_le_mul_right _ (Nat.mul_le_mul_left _ hroot)
    _ = upperNumerator ^ 2 * left * scale ^ 2 := by
      calc
        upperNumerator ^ 2 * (left * rootScale ^ 2) * radiusShift ^ 2 =
            upperNumerator ^ 2 * left *
              (rootScale ^ 2 * radiusShift ^ 2) := by ring
        _ = upperNumerator ^ 2 * left * scale ^ 2 := by
          rw [scale_factorization]

/-- Raising a directed lower endpoint cannot invalidate a lower-envelope
guard. -/
theorem lowerEndpointSafe_mono
    {right lower lower' : Nat} {strict : Bool}
    (hlower : lower ≤ lower')
    (hsafe : LowerEndpointSafe right strict lower) :
    LowerEndpointSafe right strict lower' := by
  have hdifference :
      lowerDifference right lower' ≤ lowerDifference right lower := by
    simp only [lowerDifference]
    omega
  simp only [LowerEndpointSafe] at hsafe ⊢
  by_cases hnonpos : lowerDifference right lower' ≤ 0
  · exact Or.inl hnonpos
  · have hpositive' : 0 < lowerDifference right lower' :=
      lt_of_not_ge hnonpos
    have hpositive : 0 < lowerDifference right lower :=
      lt_of_lt_of_le hpositive' hdifference
    have habs :
        (lowerDifference right lower').natAbs ≤
          (lowerDifference right lower).natAbs := by
      have habsInt :
          ((lowerDifference right lower').natAbs : Int) ≤
            (lowerDifference right lower).natAbs := by
        rw [Int.natAbs_of_nonneg hpositive'.le,
          Int.natAbs_of_nonneg hpositive.le]
        exact hdifference
      exact_mod_cast habsInt
    right
    cases strict with
    | false =>
        simp only [Bool.false_eq_true, ↓reduceIte] at hsafe ⊢
        exact (Nat.pow_le_pow_left habs 2).trans
          (hsafe.resolve_left (not_le_of_gt hpositive))
    | true =>
        simp only [↓reduceIte] at hsafe ⊢
        exact lt_of_le_of_lt (Nat.pow_le_pow_left habs 2)
          (hsafe.resolve_left (not_le_of_gt hpositive))

/-- Lowering a directed upper endpoint cannot invalidate an upper-envelope
guard. -/
theorem upperEndpointSafe_anti
    {left upper' upper : Nat}
    (hupper : upper' ≤ upper)
    (hsafe : UpperEndpointSafe left upper) :
    UpperEndpointSafe left upper' := by
  have hdifference :
      upperDifference left upper' ≤ upperDifference left upper := by
    simp only [upperDifference]
    omega
  simp only [UpperEndpointSafe] at hsafe ⊢
  by_cases hnonpos : upperDifference left upper' ≤ 0
  · exact Or.inl hnonpos
  · have hpositive' : 0 < upperDifference left upper' :=
      lt_of_not_ge hnonpos
    have hpositive : 0 < upperDifference left upper :=
      lt_of_lt_of_le hpositive' hdifference
    have habs :
        (upperDifference left upper').natAbs ≤
          (upperDifference left upper).natAbs := by
      have habsInt :
          ((upperDifference left upper').natAbs : Int) ≤
            (upperDifference left upper).natAbs := by
        rw [Int.natAbs_of_nonneg hpositive'.le,
          Int.natAbs_of_nonneg hpositive.le]
        exact hdifference
      exact_mod_cast habsInt
    right
    exact
      (Nat.mul_le_mul_right (upperDenominator ^ 2)
        (Nat.pow_le_pow_left habs 2)).trans
        (hsafe.resolve_left (not_le_of_gt hpositive))

/-- A conservative Q64 radius suffices for a non-strict lower guard.  This is
the arithmetic interface used by the one-pass worker after it has certified a
fixed-point square-root radius. -/
theorem lowerEndpointSafe_of_radius
    {right lowerQ64 radiusQ64 : Nat}
    (henclosed : right * scale ≤ lowerQ64 + radiusQ64)
    (hradius : radiusQ64 ^ 2 ≤ 2 * right * scale ^ 2) :
    LowerEndpointSafe right false lowerQ64 := by
  simp only [LowerEndpointSafe, Bool.false_eq_true, ↓reduceIte]
  by_cases hnonpos : lowerDifference right lowerQ64 ≤ 0
  · exact Or.inl hnonpos
  · right
    have hpositive : 0 < lowerDifference right lowerQ64 :=
      lt_of_not_ge hnonpos
    have henclosedInt :
        (right : Int) * scale ≤ lowerQ64 + radiusQ64 := by
      exact_mod_cast henclosed
    have hdifferenceInt :
        lowerDifference right lowerQ64 ≤ (radiusQ64 : Int) := by
      simp only [lowerDifference]
      omega
    have habs :
        (lowerDifference right lowerQ64).natAbs ≤ radiusQ64 := by
      have habsInt :
          ((lowerDifference right lowerQ64).natAbs : Int) ≤ radiusQ64 := by
        rw [Int.natAbs_of_nonneg hpositive.le]
        exact hdifferenceInt
      exact_mod_cast habsInt
    exact (Nat.pow_le_pow_left habs 2).trans hradius

/-- The strict version of `lowerEndpointSafe_of_radius`; the worker uses a
one-unit inward correction when its fixed-point square-root radius lands
exactly on the squared boundary. -/
theorem lowerEndpointSafe_strict_of_radius
    {right lowerQ64 radiusQ64 : Nat}
    (henclosed : right * scale ≤ lowerQ64 + radiusQ64)
    (hradius : radiusQ64 ^ 2 < 2 * right * scale ^ 2) :
    LowerEndpointSafe right true lowerQ64 := by
  simp only [LowerEndpointSafe, ↓reduceIte]
  by_cases hnonpos : lowerDifference right lowerQ64 ≤ 0
  · exact Or.inl hnonpos
  · right
    have hpositive : 0 < lowerDifference right lowerQ64 :=
      lt_of_not_ge hnonpos
    have henclosedInt :
        (right : Int) * scale ≤ lowerQ64 + radiusQ64 := by
      exact_mod_cast henclosed
    have hdifferenceInt :
        lowerDifference right lowerQ64 ≤ (radiusQ64 : Int) := by
      simp only [lowerDifference]
      omega
    have habs :
        (lowerDifference right lowerQ64).natAbs ≤ radiusQ64 := by
      have habsInt :
          ((lowerDifference right lowerQ64).natAbs : Int) ≤ radiusQ64 := by
        rw [Int.natAbs_of_nonneg hpositive.le]
        exact hdifferenceInt
      exact_mod_cast habsInt
    exact lt_of_le_of_lt (Nat.pow_le_pow_left habs 2) hradius

/-- A conservative rational Q64 radius suffices for an upper guard. -/
theorem upperEndpointSafe_of_radius
    {left upperQ64 radiusQ64 : Nat}
    (henclosed : upperQ64 ≤ left * scale + radiusQ64)
    (hradius :
      radiusQ64 ^ 2 * upperDenominator ^ 2 ≤
        upperNumerator ^ 2 * left * scale ^ 2) :
    UpperEndpointSafe left upperQ64 := by
  simp only [UpperEndpointSafe]
  by_cases hnonpos : upperDifference left upperQ64 ≤ 0
  · exact Or.inl hnonpos
  · right
    have hpositive : 0 < upperDifference left upperQ64 :=
      lt_of_not_ge hnonpos
    have henclosedInt :
        (upperQ64 : Int) ≤ (left : Int) * scale + radiusQ64 := by
      exact_mod_cast henclosed
    have hdifferenceInt :
        upperDifference left upperQ64 ≤ (radiusQ64 : Int) := by
      simp only [upperDifference]
      omega
    have habs :
        (upperDifference left upperQ64).natAbs ≤ radiusQ64 := by
      have habsInt :
          ((upperDifference left upperQ64).natAbs : Int) ≤ radiusQ64 := by
        rw [Int.natAbs_of_nonneg hpositive.le]
        exact hdifferenceInt
      exact_mod_cast habsInt
    exact
      (Nat.mul_le_mul_right (upperDenominator ^ 2)
        (Nat.pow_le_pow_left habs 2)).trans hradius

/-- Direct checker theorem for an ordinary one-pass lower witness. -/
theorem lowerEndpointSafe_of_q16_root
    {right lowerQ64 rootQ16 : Nat}
    (henclosed :
      right * scale ≤ lowerQ64 + lowerRadiusQ64 rootQ16)
    (hroot : rootQ16 ^ 2 ≤ 2 * right * rootScale ^ 2) :
    LowerEndpointSafe right false lowerQ64 :=
  lowerEndpointSafe_of_radius henclosed
    (lowerRadiusQ64_sq_le hroot)

/-- Direct checker theorem for the corrected strict terminal witness. -/
theorem lowerEndpointSafe_strict_of_q16_root
    {right lowerQ64 rootQ16 : Nat} (hright : 0 < right)
    (henclosed :
      right * scale ≤ lowerQ64 + strictLowerRadiusQ64 right rootQ16)
    (hroot : rootQ16 ^ 2 ≤ 2 * right * rootScale ^ 2) :
    LowerEndpointSafe right true lowerQ64 :=
  lowerEndpointSafe_strict_of_radius henclosed
    (strictLowerRadiusQ64_sq_lt hright hroot)

/-- Direct checker theorem for an ordinary one-pass upper witness. -/
theorem upperEndpointSafe_of_q16_root
    {left upperQ64 rootQ16 : Nat}
    (henclosed :
      upperQ64 ≤ left * scale + upperRadiusQ64 rootQ16)
    (hroot : rootQ16 ^ 2 ≤ left * rootScale ^ 2) :
    UpperEndpointSafe left upperQ64 :=
  upperEndpointSafe_of_radius henclosed
    (upperRadiusQ64_sq_le hroot)

/-- One lower check after the shard has accumulated `deltaQ64`. -/
structure LowerGuard where
  right : Nat
  strict : Bool
  deltaQ64 : Nat
  deriving Repr, DecidableEq

/-- One upper check after the shard has accumulated `deltaQ64`. -/
structure UpperGuard where
  left : Nat
  deltaQ64 : Nat
  deriving Repr, DecidableEq

def LowerGuard.SafeAt (guard : LowerGuard) (incomingLowerQ64 : Nat) : Prop :=
  LowerEndpointSafe guard.right guard.strict
    (incomingLowerQ64 + guard.deltaQ64)

def UpperGuard.SafeAt (guard : UpperGuard) (incomingUpperQ64 : Nat) : Prop :=
  UpperEndpointSafe guard.left (incomingUpperQ64 + guard.deltaQ64)

/-- A lower endpoint row together with the conservative Q64 radius used by
the native affine fold.  This is mathematical data only: executable
refinement must still show that a worker emitted the corresponding list. -/
structure LowerRadiusGuard extends LowerGuard where
  radiusQ64 : Nat
  deriving Repr, DecidableEq

/-- The least incoming lower endpoint accepted by this row.  The two
truncated subtractions are exactly the native worker's
`max (0, right * scale - radius - delta)` calculation. -/
def LowerRadiusGuard.requirement (guard : LowerRadiusGuard) : Nat :=
  guard.right * scale - guard.radiusQ64 - guard.deltaQ64

def LowerRadiusGuard.RadiusSafe (guard : LowerRadiusGuard) : Prop :=
  if guard.strict then
    guard.radiusQ64 ^ 2 < 2 * guard.right * scale ^ 2
  else
    guard.radiusQ64 ^ 2 ≤ 2 * guard.right * scale ^ 2

def LowerRadiusGuard.SafeAt
    (guard : LowerRadiusGuard) (incomingLowerQ64 : Nat) : Prop :=
  LowerEndpointSafe guard.right guard.strict
    (incomingLowerQ64 + guard.deltaQ64)

/-- An upper endpoint row together with the conservative Q64 radius used by
the native affine fold. -/
structure UpperRadiusGuard extends UpperGuard where
  radiusQ64 : Nat
  deriving Repr, DecidableEq

/-- The greatest incoming upper endpoint accepted by this row.  Native code
must separately establish `BoundaryDefined`, just as the C++ implementation
fails closed if the accumulated delta exceeds this boundary. -/
def UpperRadiusGuard.allowance (guard : UpperRadiusGuard) : Nat :=
  guard.left * scale + guard.radiusQ64 - guard.deltaQ64

def UpperRadiusGuard.BoundaryDefined (guard : UpperRadiusGuard) : Prop :=
  guard.deltaQ64 ≤ guard.left * scale + guard.radiusQ64

def UpperRadiusGuard.RadiusSafe (guard : UpperRadiusGuard) : Prop :=
  guard.radiusQ64 ^ 2 * upperDenominator ^ 2 ≤
    upperNumerator ^ 2 * guard.left * scale ^ 2

def UpperRadiusGuard.SafeAt
    (guard : UpperRadiusGuard) (incomingUpperQ64 : Nat) : Prop :=
  UpperEndpointSafe guard.left
    (incomingUpperQ64 + guard.deltaQ64)

/-- Exact max fold used to summarize every lower-row requirement. -/
def minimumIncoming : List LowerRadiusGuard → Nat
  | [] => 0
  | guard :: guards => max guard.requirement (minimumIncoming guards)

/-- Exact min fold used to summarize every upper-row allowance.  The initial
cap is explicit so an executable implementation can use its fixed-width
maximum while the theorem remains independent of a machine word size. -/
def maximumIncoming (initial : Nat) : List UpperRadiusGuard → Nat
  | [] => initial
  | guard :: guards => min guard.allowance (maximumIncoming initial guards)

/-- Every member's lower requirement is bounded by the max fold. -/
theorem LowerRadiusGuard.requirement_le_minimumIncoming
    {guard : LowerRadiusGuard} {guards : List LowerRadiusGuard}
    (hmember : guard ∈ guards) :
    guard.requirement ≤ minimumIncoming guards := by
  induction guards with
  | nil => simp at hmember
  | cons head tail ih =>
      simp only [List.mem_cons] at hmember
      simp only [minimumIncoming]
      rcases hmember with rfl | htail
      · exact Nat.le_max_left _ _
      · exact (ih htail).trans (Nat.le_max_right _ _)

/-- The min fold is no larger than every member's upper allowance. -/
theorem UpperRadiusGuard.maximumIncoming_le_allowance
    (initial : Nat) {guard : UpperRadiusGuard}
    {guards : List UpperRadiusGuard} (hmember : guard ∈ guards) :
    maximumIncoming initial guards ≤ guard.allowance := by
  induction guards with
  | nil => simp at hmember
  | cons head tail ih =>
      simp only [List.mem_cons] at hmember
      simp only [maximumIncoming]
      rcases hmember with rfl | htail
      · exact Nat.min_le_left _ _
      · exact (Nat.min_le_right _ _).trans (ih htail)

/-- A row's folded lower requirement and radius certificate imply its exact
endpoint predicate at the supplied incoming state. -/
theorem LowerRadiusGuard.safeAt_of_requirement
    (guard : LowerRadiusGuard) {incomingLowerQ64 : Nat}
    (hrequirement : guard.requirement ≤ incomingLowerQ64)
    (hradius : guard.RadiusSafe) :
    guard.SafeAt incomingLowerQ64 := by
  have henclosed :
      guard.right * scale ≤
        incomingLowerQ64 + guard.deltaQ64 + guard.radiusQ64 := by
    simp only [LowerRadiusGuard.requirement] at hrequirement
    omega
  cases hstrict : guard.strict with
  | false =>
      simp only [LowerRadiusGuard.SafeAt, hstrict]
      apply lowerEndpointSafe_of_radius
      · omega
      · simpa only [LowerRadiusGuard.RadiusSafe, hstrict, Bool.false_eq_true,
          ↓reduceIte] using hradius
  | true =>
      simp only [LowerRadiusGuard.SafeAt, hstrict]
      apply lowerEndpointSafe_strict_of_radius
      · omega
      · simpa only [LowerRadiusGuard.RadiusSafe, hstrict, ↓reduceIte] using
          hradius

/-- A row's folded upper allowance and radius certificate imply its exact
endpoint predicate at the supplied incoming state. -/
theorem UpperRadiusGuard.safeAt_of_allowance
    (guard : UpperRadiusGuard) {incomingUpperQ64 : Nat}
    (hincoming : incomingUpperQ64 ≤ guard.allowance)
    (hboundary : guard.BoundaryDefined)
    (hradius : guard.RadiusSafe) :
    guard.SafeAt incomingUpperQ64 := by
  apply upperEndpointSafe_of_radius (radiusQ64 := guard.radiusQ64)
  · simp only [UpperRadiusGuard.allowance] at hincoming
    simp only [UpperRadiusGuard.BoundaryDefined] at hboundary
    omega
  · exact hradius

/-- The worker's max fold proves all lower endpoint guards at once. -/
theorem all_lower_safe_of_minimumIncoming
    (guards : List LowerRadiusGuard) {incomingLowerQ64 : Nat}
    (hincoming : minimumIncoming guards ≤ incomingLowerQ64)
    (hradius : ∀ guard ∈ guards, guard.RadiusSafe) :
    ∀ guard ∈ guards, guard.SafeAt incomingLowerQ64 := by
  intro guard hmember
  apply guard.safeAt_of_requirement
  · exact (guard.requirement_le_minimumIncoming hmember).trans hincoming
  · exact hradius guard hmember

/-- The worker's min fold proves all upper endpoint guards at once. -/
theorem all_upper_safe_of_maximumIncoming
    (initial : Nat) (guards : List UpperRadiusGuard)
    {incomingUpperQ64 : Nat}
    (hincoming : incomingUpperQ64 ≤ maximumIncoming initial guards)
    (hboundary : ∀ guard ∈ guards, guard.BoundaryDefined)
    (hradius : ∀ guard ∈ guards, guard.RadiusSafe) :
    ∀ guard ∈ guards, guard.SafeAt incomingUpperQ64 := by
  intro guard hmember
  apply guard.safeAt_of_allowance
  · exact hincoming.trans
      (guard.maximumIncoming_le_allowance initial hmember)
  · exact hboundary guard hmember
  · exact hradius guard hmember

/-- The exact max/min folds emitted by the one-pass worker imply every
endpoint predicate in the shard.  This is the architecture-independent
correctness theorem for the affine reduction; identifying a native event
stream and its fixed-width folds with these lists remains an executable
refinement obligation. -/
theorem all_radius_safe_of_folds
    (initialUpperQ64 : Nat)
    (lowerGuards : List LowerRadiusGuard)
    (upperGuards : List UpperRadiusGuard)
    {incomingLowerQ64 incomingUpperQ64 : Nat}
    (hlower :
      minimumIncoming lowerGuards ≤ incomingLowerQ64)
    (hupper :
      incomingUpperQ64 ≤ maximumIncoming initialUpperQ64 upperGuards)
    (hlowerRadius :
      ∀ guard ∈ lowerGuards, guard.RadiusSafe)
    (hupperBoundary :
      ∀ guard ∈ upperGuards, guard.BoundaryDefined)
    (hupperRadius :
      ∀ guard ∈ upperGuards, guard.RadiusSafe) :
    (∀ guard ∈ lowerGuards, guard.SafeAt incomingLowerQ64) ∧
      ∀ guard ∈ upperGuards, guard.SafeAt incomingUpperQ64 := by
  exact
    ⟨all_lower_safe_of_minimumIncoming lowerGuards hlower hlowerRadius,
      all_upper_safe_of_maximumIncoming initialUpperQ64 upperGuards hupper
        hupperBoundary hupperRadius⟩

/-- The compact affine summary stores the worst admissible incoming
endpoints. -/
structure AdmissibleIncoming where
  minimumLowerQ64 : Nat
  maximumUpperQ64 : Nat
  deriving Repr, DecidableEq

def AdmissibleIncoming.Contains
    (bounds : AdmissibleIncoming)
    (incomingLowerQ64 incomingUpperQ64 : Nat) : Prop :=
  bounds.minimumLowerQ64 ≤ incomingLowerQ64 ∧
    incomingUpperQ64 ≤ bounds.maximumUpperQ64

/-- A lower guard proved at the stored minimum remains true at every admitted
incoming lower endpoint. -/
theorem LowerGuard.safeAt_of_minimum
    (guard : LowerGuard) (bounds : AdmissibleIncoming)
    {incomingLowerQ64 incomingUpperQ64 : Nat}
    (hcontains : bounds.Contains incomingLowerQ64 incomingUpperQ64)
    (hsafe : guard.SafeAt bounds.minimumLowerQ64) :
    guard.SafeAt incomingLowerQ64 := by
  apply lowerEndpointSafe_mono
    (Nat.add_le_add_right hcontains.1 guard.deltaQ64)
  exact hsafe

/-- An upper guard proved at the stored maximum remains true at every admitted
incoming upper endpoint. -/
theorem UpperGuard.safeAt_of_maximum
    (guard : UpperGuard) (bounds : AdmissibleIncoming)
    {incomingLowerQ64 incomingUpperQ64 : Nat}
    (hcontains : bounds.Contains incomingLowerQ64 incomingUpperQ64)
    (hsafe : guard.SafeAt bounds.maximumUpperQ64) :
    guard.SafeAt incomingUpperQ64 := by
  apply upperEndpointSafe_anti
    (Nat.add_le_add_right hcontains.2 guard.deltaQ64)
  exact hsafe

/-- Checking every retained guard at the two extremal incoming endpoints is
sufficient for any root-derived state inside the advertised interval. -/
theorem all_safe_of_extrema
    (lowerGuards : List LowerGuard) (upperGuards : List UpperGuard)
    (bounds : AdmissibleIncoming)
    {incomingLowerQ64 incomingUpperQ64 : Nat}
    (hcontains : bounds.Contains incomingLowerQ64 incomingUpperQ64)
    (hlower :
      ∀ guard ∈ lowerGuards, guard.SafeAt bounds.minimumLowerQ64)
    (hupper :
      ∀ guard ∈ upperGuards, guard.SafeAt bounds.maximumUpperQ64) :
    (∀ guard ∈ lowerGuards, guard.SafeAt incomingLowerQ64) ∧
      ∀ guard ∈ upperGuards, guard.SafeAt incomingUpperQ64 := by
  constructor
  · intro guard hguard
    exact guard.safeAt_of_minimum bounds hcontains (hlower guard hguard)
  · intro guard hguard
    exact guard.safeAt_of_maximum bounds hcontains (hupper guard hguard)

end SparkInterval.TernaryGoldbach.PsiAffineGuards
