/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics

/-!
# Transcript-shaped certificate for the CH25 Lemma A.7 boundary computation

This file is the ordinary-Lean counterpart of the authoritative seven-field
leaf parser in `tg_verifier/analytic.py`.  It deliberately does not evaluate
zeta and does not contain the retained production transcript.

The checker proves, with exact rational arithmetic, that:

* the leaves are canonically grouped into the four rectangle edges;
* each edge is covered by contiguous dyadic subintervals from `0` to `1`;
* every recorded zeta lower bound is strictly positive; and
* every recorded norm-square upper bound is strictly below
  `(349 / 250)^2`.

`AnalyticRealization` is the sole remaining analytic premise.  It says exactly
that a transcript leaf's positive lower bound applies to Mathlib's
`riemannZeta`, and that its norm-square upper bound applies to Mathlib's
`rawG`.  The theorem `sourceClaim_of_checked_certificate` then derives the
source-shaped boundary claim in ordinary Lean.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.A7BoundaryCertificate

open Complex Set
open A7BoundarySourceSemantics

/-- Exact decoded value of a positive-mantissa dyadic wire pair.

The JSON parser first decodes the canonical base64url mantissa to a natural
number.  Thus the seven fields below are the semantic, post-base64 form of one
wire leaf. -/
def dyadicValue (mantissa : ℕ) (exponent : ℤ) : ℚ :=
  match exponent with
  | .ofNat power => (mantissa : ℚ) * (2 : ℚ) ^ power
  | .negSucc power => (mantissa : ℚ) / (2 : ℚ) ^ (power + 1)

/-- One decoded seven-field record from the retained A.7 transcript. -/
structure DyadicLeaf where
  edgeId : ℕ
  depth : ℕ
  index : ℕ
  normSqUpperMantissa : ℕ
  normSqUpperExponent : ℤ
  zetaAbsLowerMantissa : ℕ
  zetaAbsLowerExponent : ℤ
  deriving Repr, DecidableEq, BEq

namespace DyadicLeaf

/-- The normalized dyadic left endpoint `index / 2^depth`. -/
def parameterLower (leaf : DyadicLeaf) : ℚ :=
  (leaf.index : ℚ) / (2 : ℚ) ^ leaf.depth

/-- The normalized dyadic right endpoint `(index + 1) / 2^depth`. -/
def parameterUpper (leaf : DyadicLeaf) : ℚ :=
  (leaf.index + 1 : ℚ) / (2 : ℚ) ^ leaf.depth

def normSqUpper (leaf : DyadicLeaf) : ℚ :=
  dyadicValue leaf.normSqUpperMantissa leaf.normSqUpperExponent

def zetaAbsLower (leaf : DyadicLeaf) : ℚ :=
  dyadicValue leaf.zetaAbsLowerMantissa leaf.zetaAbsLowerExponent

/-- Transparent exact comparison
`normSqUpperMantissa * 2^normSqUpperExponent < (349/250)^2`.

Cross multiplication uses `349^2 = 121801` and `250^2 = 62500`.
No rational comparison is executed by the checker. -/
def dyadicBelowTarget (mantissa : ℕ) : ℤ → Bool
  | .ofNat power =>
      decide (62500 * mantissa * 2 ^ power < 121801)
  | .negSucc power =>
      decide (62500 * mantissa < 121801 * 2 ^ (power + 1))

def normSqBelowTarget (leaf : DyadicLeaf) : Bool :=
  dyadicBelowTarget leaf.normSqUpperMantissa leaf.normSqUpperExponent

/-- Membership in the normalized interval represented by a leaf. -/
def ParameterContains (leaf : DyadicLeaf) (t : ℝ) : Prop :=
  (leaf.parameterLower : ℝ) ≤ t ∧ t ≤ (leaf.parameterUpper : ℝ)

/-- Geometric interpretation of the parser's canonical edge IDs.

The affine parameters are:

* left/right: `t = (im + 4) / 8`;
* bottom/top: `t = (re + 3) / 8`.

Thus `t ∈ [0,1]` is exactly the full corresponding closed edge. -/
def InputContains (leaf : DyadicLeaf) (s : ℂ) : Prop :=
  (leaf.edgeId = 0 ∧ s.re = -3 ∧
      leaf.ParameterContains ((s.im + 4) / 8)) ∨
    (leaf.edgeId = 1 ∧ s.re = 5 ∧
      leaf.ParameterContains ((s.im + 4) / 8)) ∨
    (leaf.edgeId = 2 ∧ s.im = -4 ∧
      leaf.ParameterContains ((s.re + 3) / 8)) ∨
    (leaf.edgeId = 3 ∧ s.im = 4 ∧
      leaf.ParameterContains ((s.re + 3) / 8))

/-- Exact parser and arithmetic guards for one decoded leaf.

The final three parameter inequalities are redundant consequences of the
index guard.  Checking them explicitly makes the coverage proof small while
preserving the parser's accepted set. -/
def WellFormed (maxDepth : ℕ) (leaf : DyadicLeaf) : Prop :=
  leaf.edgeId < 4 ∧
    leaf.depth ≤ maxDepth ∧
    leaf.index < 2 ^ leaf.depth ∧
    0 < leaf.normSqUpperMantissa ∧
    Nat.log2 leaf.normSqUpperMantissa < 16384 ∧
    (-16384 : ℤ) ≤ leaf.normSqUpperExponent ∧
    leaf.normSqUpperExponent ≤ 16384 ∧
    0 < leaf.zetaAbsLowerMantissa ∧
    Nat.log2 leaf.zetaAbsLowerMantissa < 16384 ∧
    (-16384 : ℤ) ≤ leaf.zetaAbsLowerExponent ∧
    leaf.zetaAbsLowerExponent ≤ 16384 ∧
    0 < leaf.normSqUpper ∧
    leaf.normSqUpper < sourceTarget ^ 2 ∧
    0 < leaf.zetaAbsLower ∧
    0 ≤ leaf.parameterLower ∧
    leaf.parameterLower < leaf.parameterUpper ∧
    leaf.parameterUpper ≤ 1

/-- Executable form of the exact leaf guard.  It is written as a direct Bool
rather than through an opaque aggregate `Decidable` instance, so tiny kernel
KATs reduce without `native_decide`. -/
def check (maxDepth : ℕ) (leaf : DyadicLeaf) : Bool :=
  Bool.and (decide (leaf.edgeId < 4))
    (Bool.and (decide (leaf.depth ≤ maxDepth))
      (Bool.and (decide (leaf.index < 2 ^ leaf.depth))
        (Bool.and (decide (0 < leaf.normSqUpperMantissa))
          (Bool.and (decide (Nat.log2 leaf.normSqUpperMantissa < 16384))
            (Bool.and (decide ((-16384 : ℤ) ≤ leaf.normSqUpperExponent))
              (Bool.and (decide (leaf.normSqUpperExponent ≤ 16384))
                (Bool.and (decide (0 < leaf.zetaAbsLowerMantissa))
                  (Bool.and
                    (decide (Nat.log2 leaf.zetaAbsLowerMantissa < 16384))
                    (Bool.and
                      (decide ((-16384 : ℤ) ≤ leaf.zetaAbsLowerExponent))
                      (Bool.and
                        (decide (leaf.zetaAbsLowerExponent ≤ 16384))
                        leaf.normSqBelowTarget))))))))))

private theorem dyadicValue_pos {mantissa : ℕ} {exponent : ℤ}
    (hmantissa : 0 < mantissa) :
    0 < dyadicValue mantissa exponent := by
  cases exponent <;> simp only [dyadicValue] <;> positivity

private theorem dyadicBelowTarget_sound
    {mantissa : ℕ} {exponent : ℤ}
    (hcheck : dyadicBelowTarget mantissa exponent = true) :
    dyadicValue mantissa exponent < sourceTarget ^ 2 := by
  cases exponent with
  | ofNat power =>
      simp only [dyadicBelowTarget, decide_eq_true_eq] at hcheck
      have hraw' :
          (62500 : ℚ) * mantissa * 2 ^ power < 121801 := by
        exact_mod_cast hcheck
      rw [dyadicValue]
      norm_num [sourceTarget] at *
      linarith
  | negSucc power =>
      simp only [dyadicBelowTarget, decide_eq_true_eq] at hcheck
      have hraw' :
          (62500 : ℚ) * mantissa < 121801 * 2 ^ (power + 1) := by
        exact_mod_cast hcheck
      rw [dyadicValue]
      have hpow : (0 : ℚ) < (2 : ℚ) ^ (power + 1) := by positivity
      rw [div_lt_iff₀ hpow]
      norm_num [sourceTarget] at *
      nlinarith

private theorem normSqBelowTarget_sound {leaf : DyadicLeaf}
    (hcheck : leaf.normSqBelowTarget = true) :
    leaf.normSqUpper < sourceTarget ^ 2 := by
  exact dyadicBelowTarget_sound hcheck

private theorem parameter_guards_of_index_lt {leaf : DyadicLeaf}
    (hindex : leaf.index < 2 ^ leaf.depth) :
    0 ≤ leaf.parameterLower ∧
      leaf.parameterLower < leaf.parameterUpper ∧
      leaf.parameterUpper ≤ 1 := by
  have hpow : (0 : ℚ) < (2 : ℚ) ^ leaf.depth := by positivity
  have hsucc : leaf.index + 1 ≤ 2 ^ leaf.depth :=
    Nat.succ_le_iff.mpr hindex
  constructor
  · unfold parameterLower
    positivity
  constructor
  · unfold parameterLower parameterUpper
    apply (div_lt_div_iff_of_pos_right hpow).2
    exact_mod_cast Nat.lt_succ_self leaf.index
  · unfold parameterUpper
    apply (div_le_one hpow).2
    exact_mod_cast hsucc

/-- Soundness of the transparent leaf checker. -/
theorem check_sound {maxDepth : ℕ} {leaf : DyadicLeaf}
    (hcheck : leaf.check maxDepth = true) :
    leaf.WellFormed maxDepth := by
  unfold check at hcheck
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hedgeCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hdepthCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hindexCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hnormMantissaCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hnormBitsCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hnormExponentLowerCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hnormExponentUpperCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hzetaMantissaCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hzetaBitsCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hzetaExponentLowerCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with
    ⟨hzetaExponentUpperCheck, hnormBound⟩
  have hedge : leaf.edgeId < 4 := of_decide_eq_true hedgeCheck
  have hdepth : leaf.depth ≤ maxDepth := of_decide_eq_true hdepthCheck
  have hindex : leaf.index < 2 ^ leaf.depth :=
    of_decide_eq_true hindexCheck
  have hnormMantissa : 0 < leaf.normSqUpperMantissa :=
    of_decide_eq_true hnormMantissaCheck
  have hnormBits : Nat.log2 leaf.normSqUpperMantissa < 16384 :=
    of_decide_eq_true hnormBitsCheck
  have hnormExponentLower : (-16384 : ℤ) ≤ leaf.normSqUpperExponent :=
    of_decide_eq_true hnormExponentLowerCheck
  have hnormExponentUpper : leaf.normSqUpperExponent ≤ 16384 :=
    of_decide_eq_true hnormExponentUpperCheck
  have hzetaMantissa : 0 < leaf.zetaAbsLowerMantissa :=
    of_decide_eq_true hzetaMantissaCheck
  have hzetaBits : Nat.log2 leaf.zetaAbsLowerMantissa < 16384 :=
    of_decide_eq_true hzetaBitsCheck
  have hzetaExponentLower : (-16384 : ℤ) ≤ leaf.zetaAbsLowerExponent :=
    of_decide_eq_true hzetaExponentLowerCheck
  have hzetaExponentUpper : leaf.zetaAbsLowerExponent ≤ 16384 :=
    of_decide_eq_true hzetaExponentUpperCheck
  have hnormPositive :
      0 < leaf.normSqUpper :=
    dyadicValue_pos hnormMantissa
  have hzetaPositive :
      0 < leaf.zetaAbsLower :=
    dyadicValue_pos hzetaMantissa
  obtain ⟨hparameterLower, hparameterStrict, hparameterUpper⟩ :=
    parameter_guards_of_index_lt hindex
  exact
    ⟨hedge, hdepth, hindex, hnormMantissa, hnormBits,
      hnormExponentLower, hnormExponentUpper, hzetaMantissa, hzetaBits,
      hzetaExponentLower, hzetaExponentUpper, hnormPositive,
      normSqBelowTarget_sound hnormBound, hzetaPositive,
      hparameterLower, hparameterStrict, hparameterUpper⟩

/-- Named projection used to keep the large wire-size guards out of arithmetic
tactic contexts. -/
theorem normSqUpper_lt_targetSq {maxDepth : ℕ} {leaf : DyadicLeaf}
    (hwell : leaf.WellFormed maxDepth) :
    leaf.normSqUpper < sourceTarget ^ 2 := by
  rcases hwell with
    ⟨_, _, _, _, _, _, _, _, _, _, _, _, hstrict, _, _, _, _⟩
  exact hstrict

/-- Named positive-zeta projection from the exact leaf guard. -/
theorem zetaAbsLower_pos {maxDepth : ℕ} {leaf : DyadicLeaf}
    (hwell : leaf.WellFormed maxDepth) :
    0 < leaf.zetaAbsLower := by
  rcases hwell with
    ⟨_, _, _, _, _, _, _, _, _, _, _, _, _, hpositive, _, _, _⟩
  exact hpositive

end DyadicLeaf

/-- The finite decoded core of the A.7 transcript.  Static JSON metadata and
diagnostic summary fields are identity/provenance data, not mathematical
inputs to this exact checker. -/
structure Certificate where
  maxDepth : ℕ
  leaves : List DyadicLeaf
  deriving Repr, DecidableEq, BEq

namespace Certificate

/-- Leaves bearing one edge ID, in their original transcript order. -/
def edgeLeaves (certificate : Certificate) (edgeId : ℕ) : List DyadicLeaf :=
  certificate.leaves.filter fun leaf => leaf.edgeId == edgeId

/-- A nonempty serial cover beginning at `cursor` and ending exactly at `1`.

This recursive proposition is deliberately shaped like the parser's cursor
loop.  A singleton must end at `1`; a non-final leaf must end strictly before
`1`, and the next leaf begins at that exact rational endpoint. -/
def ContiguousFrom (maxDepth edgeId : ℕ) :
    ℚ → List DyadicLeaf → Prop
  | _, [] => False
  | cursor, [leaf] =>
      leaf.WellFormed maxDepth ∧
        leaf.edgeId = edgeId ∧
        leaf.parameterLower = cursor ∧
        leaf.parameterUpper = 1
  | cursor, leaf :: next :: rest =>
      leaf.WellFormed maxDepth ∧
        leaf.edgeId = edgeId ∧
        leaf.parameterLower = cursor ∧
        leaf.parameterUpper < 1 ∧
        ContiguousFrom maxDepth edgeId leaf.parameterUpper (next :: rest)

/-- Exact equality between a cursor `cursorNumerator / 2^cursorDepth`
and a leaf's lower endpoint, checked by natural-number cross multiplication. -/
def cursorMatches
    (cursorNumerator cursorDepth : ℕ) (leaf : DyadicLeaf) : Bool :=
  decide
    (cursorNumerator * 2 ^ leaf.depth =
      leaf.index * 2 ^ cursorDepth)

/-- Executable cursor replay for one filtered edge list.

All endpoint comparisons are raw natural-number power-of-two comparisons.
There is no executable rational comparison in this loop. -/
def contiguousCheck (maxDepth edgeId : ℕ) :
    ℕ → ℕ → List DyadicLeaf → Bool
  | _, _, [] => false
  | cursorNumerator, cursorDepth, [leaf] =>
      Bool.and (leaf.check maxDepth)
        (Bool.and (decide (leaf.edgeId = edgeId))
          (Bool.and (cursorMatches cursorNumerator cursorDepth leaf)
            (decide (leaf.index + 1 = 2 ^ leaf.depth))))
  | cursorNumerator, cursorDepth, leaf :: next :: rest =>
      Bool.and (leaf.check maxDepth)
        (Bool.and (decide (leaf.edgeId = edgeId))
          (Bool.and (cursorMatches cursorNumerator cursorDepth leaf)
            (Bool.and (decide (leaf.index + 1 < 2 ^ leaf.depth))
              (contiguousCheck maxDepth edgeId (leaf.index + 1) leaf.depth
                (next :: rest)))))

private theorem parameterLower_eq_cursor_of_match
    {cursorNumerator cursorDepth : ℕ} {leaf : DyadicLeaf}
    (hmatch :
      cursorNumerator * 2 ^ leaf.depth =
        leaf.index * 2 ^ cursorDepth) :
    leaf.parameterLower =
      (cursorNumerator : ℚ) / (2 : ℚ) ^ cursorDepth := by
  unfold DyadicLeaf.parameterLower
  apply (div_eq_div_iff (by positivity) (by positivity)).2
  exact_mod_cast hmatch.symm

private theorem parameterUpper_eq_one_of_raw
    {leaf : DyadicLeaf} (hfinal : leaf.index + 1 = 2 ^ leaf.depth) :
    leaf.parameterUpper = 1 := by
  unfold DyadicLeaf.parameterUpper
  apply (div_eq_one_iff_eq (by positivity)).2
  exact_mod_cast hfinal

private theorem parameterUpper_lt_one_of_raw
    {leaf : DyadicLeaf} (hnonfinal : leaf.index + 1 < 2 ^ leaf.depth) :
    leaf.parameterUpper < 1 := by
  unfold DyadicLeaf.parameterUpper
  apply (div_lt_one (by positivity)).2
  exact_mod_cast hnonfinal

/-- Soundness of the raw natural-number cursor replay. -/
theorem contiguousCheck_sound
    {maxDepth edgeId cursorNumerator cursorDepth : ℕ}
    {leaves : List DyadicLeaf}
    (hcheck :
      contiguousCheck maxDepth edgeId cursorNumerator cursorDepth leaves =
        true) :
    ContiguousFrom maxDepth edgeId
      ((cursorNumerator : ℚ) / (2 : ℚ) ^ cursorDepth) leaves := by
  induction leaves generalizing cursorNumerator cursorDepth with
  | nil =>
      simp [contiguousCheck] at hcheck
  | cons leaf tail ih =>
      cases tail with
      | nil =>
          unfold contiguousCheck at hcheck
          rcases Bool.and_eq_true_iff.mp hcheck with ⟨hleaf, hcheck⟩
          rcases Bool.and_eq_true_iff.mp hcheck with ⟨hedgeCheck, hcheck⟩
          rcases Bool.and_eq_true_iff.mp hcheck with
            ⟨hmatchCheck, hfinalCheck⟩
          have hedge : leaf.edgeId = edgeId :=
            of_decide_eq_true hedgeCheck
          have hmatch :
              cursorNumerator * 2 ^ leaf.depth =
                leaf.index * 2 ^ cursorDepth := by
            exact of_decide_eq_true hmatchCheck
          have hfinal : leaf.index + 1 = 2 ^ leaf.depth :=
            of_decide_eq_true hfinalCheck
          exact
            ⟨DyadicLeaf.check_sound hleaf, hedge,
              parameterLower_eq_cursor_of_match hmatch,
              parameterUpper_eq_one_of_raw hfinal⟩
      | cons next rest =>
          unfold contiguousCheck at hcheck
          rcases Bool.and_eq_true_iff.mp hcheck with ⟨hleaf, hcheck⟩
          rcases Bool.and_eq_true_iff.mp hcheck with ⟨hedgeCheck, hcheck⟩
          rcases Bool.and_eq_true_iff.mp hcheck with ⟨hmatchCheck, hcheck⟩
          rcases Bool.and_eq_true_iff.mp hcheck with
            ⟨hnonfinalCheck, hrest⟩
          have hedge : leaf.edgeId = edgeId :=
            of_decide_eq_true hedgeCheck
          have hmatch :
              cursorNumerator * 2 ^ leaf.depth =
                leaf.index * 2 ^ cursorDepth := by
            exact of_decide_eq_true hmatchCheck
          have hnonfinal : leaf.index + 1 < 2 ^ leaf.depth :=
            of_decide_eq_true hnonfinalCheck
          refine
            ⟨DyadicLeaf.check_sound hleaf, hedge,
              parameterLower_eq_cursor_of_match hmatch,
              parameterUpper_lt_one_of_raw hnonfinal, ?_⟩
          simpa [DyadicLeaf.parameterUpper] using
            ih hrest

/-- Exact full normalized cover for one canonical edge. -/
def EdgeCover (certificate : Certificate) (edgeId : ℕ) : Prop :=
  ContiguousFrom certificate.maxDepth edgeId 0
    (certificate.edgeLeaves edgeId)

/-- Executable exact cursor check for one edge. -/
def edgeCoverCheck (certificate : Certificate) (edgeId : ℕ) : Bool :=
  contiguousCheck certificate.maxDepth edgeId 0 0
    (certificate.edgeLeaves edgeId)

theorem edgeCoverCheck_sound
    {certificate : Certificate} {edgeId : ℕ} :
    certificate.edgeCoverCheck edgeId = true →
      certificate.EdgeCover edgeId := by
  intro hcheck
  have hsound := contiguousCheck_sound hcheck
  simpa [EdgeCover] using hsound

/-- Parser-shaped acceptance proposition. -/
def Accepted (certificate : Certificate) : Prop :=
  certificate.maxDepth ≤ 64 ∧
    4 ≤ certificate.leaves.length ∧
    certificate.leaves.length ≤ 2000000 ∧
    certificate.leaves =
      certificate.edgeLeaves 0 ++ certificate.edgeLeaves 1 ++
        certificate.edgeLeaves 2 ++ certificate.edgeLeaves 3 ∧
    certificate.EdgeCover 0 ∧
    certificate.EdgeCover 1 ∧
    certificate.EdgeCover 2 ∧
    certificate.EdgeCover 3

/-- Executable exact checker.  It uses ordinary `decide`, not
`native_decide`. -/
def check (certificate : Certificate) : Bool :=
  Bool.and (decide (certificate.maxDepth ≤ 64))
    (Bool.and (decide (4 ≤ certificate.leaves.length))
      (Bool.and (decide (certificate.leaves.length ≤ 2000000))
        (Bool.and (decide (certificate.leaves =
          certificate.edgeLeaves 0 ++ certificate.edgeLeaves 1 ++
            certificate.edgeLeaves 2 ++ certificate.edgeLeaves 3))
          (Bool.and (certificate.edgeCoverCheck 0)
            (Bool.and (certificate.edgeCoverCheck 1)
              (Bool.and (certificate.edgeCoverCheck 2)
                (certificate.edgeCoverCheck 3)))))))

theorem accepted_of_check_eq_true {certificate : Certificate}
    (hcheck : certificate.check = true) : certificate.Accepted := by
  unfold check at hcheck
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hdepthCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hlengthLowerCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hlengthUpperCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hcanonicalCheck, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hedge0, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hedge1, hcheck⟩
  rcases Bool.and_eq_true_iff.mp hcheck with ⟨hedge2, hedge3⟩
  have hdepth : certificate.maxDepth ≤ 64 :=
    of_decide_eq_true hdepthCheck
  have hlengthLower : 4 ≤ certificate.leaves.length :=
    of_decide_eq_true hlengthLowerCheck
  have hlengthUpper : certificate.leaves.length ≤ 2000000 :=
    of_decide_eq_true hlengthUpperCheck
  have hcanonical :
      certificate.leaves =
        certificate.edgeLeaves 0 ++ certificate.edgeLeaves 1 ++
          certificate.edgeLeaves 2 ++ certificate.edgeLeaves 3 :=
    of_decide_eq_true hcanonicalCheck
  exact
    ⟨hdepth, hlengthLower, hlengthUpper, hcanonical,
      edgeCoverCheck_sound hedge0, edgeCoverCheck_sound hedge1,
      edgeCoverCheck_sound hedge2, edgeCoverCheck_sound hedge3⟩

private theorem contiguousFrom_covers
    {maxDepth edgeId : ℕ} {cursor : ℚ} {leaves : List DyadicLeaf}
    (hcover : ContiguousFrom maxDepth edgeId cursor leaves)
    (t : ℝ) (hcursor : (cursor : ℝ) ≤ t) (htop : t ≤ 1) :
    ∃ leaf, leaf ∈ leaves ∧
      leaf.WellFormed maxDepth ∧ leaf.edgeId = edgeId ∧
      leaf.ParameterContains t := by
  induction leaves generalizing cursor with
  | nil =>
      simp [ContiguousFrom] at hcover
  | cons leaf tail ih =>
      cases tail with
      | nil =>
          rcases hcover with ⟨hwell, hedge, hlower, hupper⟩
          refine ⟨leaf, by simp, hwell, hedge, ?_, ?_⟩
          · rw [hlower]
            exact hcursor
          · rw [hupper]
            simpa using htop
      | cons next rest =>
          rcases hcover with
            ⟨hwell, hedge, hlower, hupper, hrest⟩
          by_cases hhere : t ≤ (leaf.parameterUpper : ℝ)
          · refine ⟨leaf, by simp, hwell, hedge, ?_, hhere⟩
            rw [hlower]
            exact hcursor
          · obtain ⟨found, hmem, hfoundWell, hfoundEdge, hfoundContains⟩ :=
              ih hrest (le_of_lt (lt_of_not_ge hhere))
            exact ⟨found, by simp [hmem], hfoundWell, hfoundEdge,
              hfoundContains⟩

/-- Soundness of one exact edge-cover check. -/
theorem edgeCover_covers
    {certificate : Certificate} {edgeId : ℕ}
    (hcover : certificate.EdgeCover edgeId)
    (t : ℝ) (hlower : 0 ≤ t) (hupper : t ≤ 1) :
    ∃ leaf, leaf ∈ certificate.leaves ∧
      leaf.WellFormed certificate.maxDepth ∧
      leaf.edgeId = edgeId ∧ leaf.ParameterContains t := by
  obtain ⟨leaf, hmem, hwell, hedge, hcontains⟩ :=
    contiguousFrom_covers hcover t (by simpa using hlower) hupper
  have hmem' : leaf ∈ certificate.leaves ∧ leaf.edgeId = edgeId := by
    simpa [edgeLeaves] using hmem
  exact ⟨leaf, hmem'.1, hwell, hedge, hcontains⟩

private theorem frontier_cases {s : ℂ}
    (hs : s ∈ frontier sourceRectangle) :
    (s.re = -3 ∧ -4 ≤ s.im ∧ s.im ≤ 4) ∨
    (s.re = 5 ∧ -4 ≤ s.im ∧ s.im ≤ 4) ∨
    (s.im = -4 ∧ -3 ≤ s.re ∧ s.re ≤ 5) ∨
    (s.im = 4 ∧ -3 ≤ s.re ∧ s.re ≤ 5) := by
  rw [sourceRectangle, frontier_reProdIm, closure_Ioo (by norm_num),
    frontier_Ioo (by norm_num), closure_Ioo (by norm_num),
    frontier_Ioo (by norm_num)] at hs
  rcases hs with hhorizontal | hvertical
  · rcases hhorizontal with ⟨hre, him⟩
    change -3 ≤ s.re ∧ s.re ≤ 5 at hre
    rcases him with him | him
    · exact Or.inr (Or.inr (Or.inl ⟨him, hre.1, hre.2⟩))
    · exact Or.inr (Or.inr (Or.inr ⟨him, hre.1, hre.2⟩))
  · rcases hvertical with ⟨hre, him⟩
    change -4 ≤ s.im ∧ s.im ≤ 4 at him
    rcases hre with hre | hre
    · exact Or.inl ⟨hre, him.1, him.2⟩
    · exact Or.inr (Or.inl ⟨hre, him.1, him.2⟩)

/-- A checked finite transcript covers every point on the exact source
rectangle frontier. -/
theorem covers_frontier
    {certificate : Certificate} (haccepted : certificate.Accepted)
    (s : ℂ) (hs : s ∈ frontier sourceRectangle) :
    ∃ leaf, leaf ∈ certificate.leaves ∧
      leaf.WellFormed certificate.maxDepth ∧ leaf.InputContains s := by
  rcases haccepted with
    ⟨_, _, _, _, hleft, hright, hbottom, htop⟩
  rcases frontier_cases hs with h | h | h | h
  · obtain ⟨leaf, hmem, hwell, hedge, hparameter⟩ :=
      edgeCover_covers hleft ((s.im + 4) / 8) (by linarith) (by linarith)
    exact ⟨leaf, hmem, hwell, Or.inl ⟨hedge, h.1, hparameter⟩⟩
  · obtain ⟨leaf, hmem, hwell, hedge, hparameter⟩ :=
      edgeCover_covers hright ((s.im + 4) / 8) (by linarith) (by linarith)
    exact ⟨leaf, hmem, hwell,
      Or.inr (Or.inl ⟨hedge, h.1, hparameter⟩)⟩
  · obtain ⟨leaf, hmem, hwell, hedge, hparameter⟩ :=
      edgeCover_covers hbottom ((s.re + 3) / 8) (by linarith) (by linarith)
    exact ⟨leaf, hmem, hwell,
      Or.inr (Or.inr (Or.inl ⟨hedge, h.1, hparameter⟩))⟩
  · obtain ⟨leaf, hmem, hwell, hedge, hparameter⟩ :=
      edgeCover_covers htop ((s.re + 3) / 8) (by linarith) (by linarith)
    exact ⟨leaf, hmem, hwell,
      Or.inr (Or.inr (Or.inr ⟨hedge, h.1, hparameter⟩))⟩

end Certificate

namespace DyadicLeaf

/-- Boundary geometry keeps the explicit `s - 1` denominator away from zero. -/
theorem sub_one_ne_zero_of_inputContains {leaf : DyadicLeaf} {s : ℂ}
    (hcontains : leaf.InputContains s) : s - 1 ≠ 0 := by
  intro hzero
  rcases hcontains with h | h | h | h
  · have hre := congrArg Complex.re hzero
    norm_num [h.2.1] at hre
  · have hre := congrArg Complex.re hzero
    norm_num [h.2.1] at hre
  · have him := congrArg Complex.im hzero
    norm_num [h.2.1] at him
  · have him := congrArg Complex.im hzero
    norm_num [h.2.1] at him

/-- Boundary geometry keeps the explicit `s + 2` denominator away from zero. -/
theorem add_two_ne_zero_of_inputContains {leaf : DyadicLeaf} {s : ℂ}
    (hcontains : leaf.InputContains s) : s + 2 ≠ 0 := by
  intro hzero
  rcases hcontains with h | h | h | h
  · have hre := congrArg Complex.re hzero
    norm_num [h.2.1] at hre
  · have hre := congrArg Complex.re hzero
    norm_num [h.2.1] at hre
  · have him := congrArg Complex.im hzero
    norm_num [h.2.1] at him
  · have him := congrArg Complex.im hzero
    norm_num [h.2.1] at him

end DyadicLeaf

/-- The explicit FLINT/Arb-to-Mathlib realization boundary.

This is intentionally a parameter, not an axiom.  It records both analytic
facts that the seven-field transcript itself cannot establish:

* the positive stored zeta lower bound applies to Mathlib's zeta value; and
* the stored norm-square upper bound applies to Mathlib's `rawG`.

The latter premise receives all three nonzero denominator guards explicitly.
-/
structure AnalyticRealization (certificate : Certificate) : Prop where
  zetaAbsLower :
    ∀ leaf, leaf ∈ certificate.leaves →
      leaf.WellFormed certificate.maxDepth →
      ∀ s, leaf.InputContains s →
        (leaf.zetaAbsLower : ℝ) ≤ ‖riemannZeta s‖
  rawGNormSqUpper :
    ∀ leaf, leaf ∈ certificate.leaves →
      leaf.WellFormed certificate.maxDepth →
      ∀ s, leaf.InputContains s →
        riemannZeta s ≠ 0 → s - 1 ≠ 0 → s + 2 ≠ 0 →
        ‖rawG s‖ ^ 2 ≤ (leaf.normSqUpper : ℝ)

namespace AnalyticRealization

/-- A positive transcript lower bound plus analytic realization proves that
the zeta denominator is nonzero. -/
theorem zeta_ne_zero
    {certificate : Certificate} (realization : AnalyticRealization certificate)
    {leaf : DyadicLeaf} (hmem : leaf ∈ certificate.leaves)
    (hwell : leaf.WellFormed certificate.maxDepth)
    {s : ℂ} (hcontains : leaf.InputContains s) :
    riemannZeta s ≠ 0 := by
  have hlower := realization.zetaAbsLower leaf hmem hwell s hcontains
  have hpositiveRat := DyadicLeaf.zetaAbsLower_pos hwell
  clear hwell
  have hpositive : (0 : ℝ) < (leaf.zetaAbsLower : ℝ) := by
    exact_mod_cast hpositiveRat
  intro hzero
  rw [hzero, norm_zero] at hlower
  linarith

end AnalyticRealization

/-- A checked seven-field transcript and its explicit analytic realization
prove the literal CH25 A.7 source claim. -/
theorem sourceClaim_of_checked_certificate
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (realization : AnalyticRealization certificate) :
    SourceClaim := by
  have haccepted := Certificate.accepted_of_check_eq_true hcheck
  intro s hs
  obtain ⟨leaf, hmem, hwell, hcontains⟩ :=
    Certificate.covers_frontier haccepted s hs
  have hzeta := realization.zeta_ne_zero hmem hwell hcontains
  have hsub := leaf.sub_one_ne_zero_of_inputContains hcontains
  have hadd := leaf.add_two_ne_zero_of_inputContains hcontains
  have hsq :=
    realization.rawGNormSqUpper leaf hmem hwell s hcontains hzeta hsub hadd
  have hstrictRat := DyadicLeaf.normSqUpper_lt_targetSq hwell
  clear hwell
  have hstrict :
      (leaf.normSqUpper : ℝ) < (sourceTarget : ℝ) ^ 2 := by
    exact_mod_cast hstrictRat
  have htarget : (0 : ℝ) < (sourceTarget : ℝ) := by
    norm_num [sourceTarget]
  clear hcheck haccepted realization hmem hcontains hzeta hsub hadd
    hstrictRat
  have hnorm : ‖rawG s‖ ≤ (sourceTarget : ℝ) := by
    nlinarith [norm_nonneg (rawG s)]
  simpa [sourceTarget] using hnorm

end SparkInterval.TernaryGoldbach.A7BoundaryCertificate
