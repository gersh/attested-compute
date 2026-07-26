/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.HardyZContract
import SparkInterval.Zeta.MultiplicityCount
import SparkInterval.Certificate.SHA256

/-!
# Multiplicity-preserving semantics for the Platt zeta head

The CH25 Proposition 7.7 handoff identifies 22,491 checked ordinate cells
with every nontrivial zeta zero of positive ordinate at most 20,000, repeated
according to analytic multiplicity.  This file states that interface for an
arbitrary exact rational cell table and proves it from a smaller checker-
shaped contract:

* a checked ordered family of strict Hardy-Z sign brackets;
* sound endpoint enclosures for a proved `HardyZModel`;
* placement of every bracket inside `(0,20000]`; and
* equality between the analytic multiplicity-slot count and 22,491.

No zero-simplicity hypothesis occurs.  A strict bracket supplies one distinct
critical-line zero.  Since there are as many distinct bracket roots as total
multiplicity slots, finite-cardinality reasoning makes the canonical map onto
all slots, thereby proving both completeness and multiplicity preservation.

The remaining analytic producer obligations are visible in
`CheckedHeadEvidence.endpointEnclosures`, `model`, and `slotCard`.  The first
two connect the directed evaluator to Mathlib's zeta function; `slotCard` is
the Turing/argument-principle conclusion.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

open Complex Set
open SparkInterval.Certificate
open SparkInterval.Zeta

/-- Source height in CH25 Proposition 7.7. -/
def sourceHeight : ℝ := 20_000

/-- Number of positive-ordinate multiplicity slots in the checked head. -/
def sourceCount : Nat := 22_491

/-- The exact nontrivial positive-ordinate zeta band used by the source. -/
def sourceBand : Set ℂ :=
  {s : ℂ | riemannZeta s = 0 ∧ 0 < s.re ∧ s.re < 1 ∧
    0 < s.im ∧ s.im ≤ sourceHeight}

theorem sourceBand_subset_rectangleZeros :
    sourceBand ⊆ zetaZerosIn (criticalRectangle sourceHeight) := by
  intro s hs
  rcases hs with ⟨hzero, hre0, hre1, him0, himUpper⟩
  constructor
  · rw [mem_criticalRectangle]
    exact ⟨hre0.le, hre1.le, by
      have hheight : (0 : ℝ) ≤ sourceHeight := by norm_num [sourceHeight]
      linarith, himUpper⟩
  · exact hzero

/-- The source band is finite because it is contained in a compact zeta-zero
rectangle. -/
theorem sourceBand_finite : sourceBand.Finite :=
  (zetaZerosIn_finite (isCompact_criticalRectangle sourceHeight)).subset
    sourceBand_subset_rectangleZeros

noncomputable instance sourceBandFintype : Fintype sourceBand :=
  Set.Finite.fintype sourceBand_finite

/-- One slot for every copy of every positive-ordinate zero, using Mathlib's
analytic multiplicity without assuming it equals one. -/
abbrev ZeroSlot :=
  Σ rho : sourceBand,
    Fin (analyticOrderAt riemannZeta (rho : ℂ)).toNat

private theorem analyticOrderAt_riemannZeta_ne_top_of_ne_one
    {s : ℂ} (hs : s ≠ 1) :
    analyticOrderAt riemannZeta s ≠ ⊤ := by
  have htwo : (2 : ℂ) ∈ ({1} : Set ℂ)ᶜ := by norm_num
  have hsMem : s ∈ ({1} : Set ℂ)ᶜ := by
    simpa only [Set.mem_compl_iff, Set.mem_singleton_iff] using hs
  have htwoAnalytic : AnalyticAt ℂ riemannZeta 2 :=
    analyticOn_riemannZeta 2 htwo
  have htwoNonzero : riemannZeta (2 : ℂ) ≠ 0 :=
    riemannZeta_ne_zero_of_one_le_re (by norm_num)
  have htwoOrder : analyticOrderAt riemannZeta (2 : ℂ) = 0 :=
    htwoAnalytic.analyticOrderAt_eq_zero.mpr htwoNonzero
  have htwoFinite : analyticOrderAt riemannZeta (2 : ℂ) ≠ ⊤ := by
    rw [htwoOrder]
    exact ENat.zero_ne_top
  exact analyticOn_riemannZeta.analyticOrderAt_ne_top_of_isPreconnected
    (isConnected_compl_singleton_of_one_lt_rank (by simp) (1 : ℂ)).isPreconnected
    htwo hsMem htwoFinite

/-- Every source-band zero has a positive finite analytic multiplicity, so a
canonical slot `0` is available for the bracket root. -/
theorem sourceBand_multiplicity_pos (rho : sourceBand) :
    0 < (analyticOrderAt riemannZeta (rho : ℂ)).toNat := by
  have hzero : riemannZeta (rho : ℂ) = 0 := rho.property.1
  have hneOne : (rho : ℂ) ≠ 1 := by
    intro h
    have him : (rho : ℂ).im = 0 := by simp [h]
    linarith [rho.property.2.2.2.1]
  have hanalytic : AnalyticAt ℂ riemannZeta (rho : ℂ) :=
    analyticOn_riemannZeta _ (by
      simpa only [Set.mem_compl_iff, Set.mem_singleton_iff] using hneOne)
  exact ENat.toNat_pos
    (hanalytic.analyticOrderAt_ne_zero.mpr hzero)
    (analyticOrderAt_riemannZeta_ne_top_of_ne_one hneOne)

/-- One exact rational ordinate cell. -/
structure Cell where
  lower : ℚ
  upper : ℚ
  deriving Repr, DecidableEq, BEq

/-- The fixed table consumed by the source claim. -/
structure CellTable where
  entries : Fin sourceCount → Cell

/-! ## Portable committed Q128 table

The production artifact and the existing `claude_math` certificate store the
ordinate endpoints as natural numerators at scale `2^128`.  Keeping that
format here avoids an informal JSON-to-rational identification at the receipt
boundary.  The reciprocal field is retained because it is part of the
existing committed-row digest, although the analytic enumeration needs only
the two endpoints.
-/

/-- Common exact denominator of every committed Platt-head cell. -/
def q128Scale : Nat := 2 ^ 128

/-- One source artifact row. -/
structure Q128Cell where
  lower : Nat
  upper : Nat
  reciprocalUpper : Nat
  deriving Repr, DecidableEq, BEq

namespace Q128Cell

/-- Interpret a Q128 artifact row as the rational source cell. -/
def toCell (cell : Q128Cell) : Cell :=
  {
    lower := (cell.lower : ℚ) / q128Scale
    upper := (cell.upper : ℚ) / q128Scale
  }

/-- Canonical one-based ASCII row used by the pre-existing CH25 certificate
digest: `index:lower:upper:reciprocalUpper\n`. -/
def canonicalRow (index : Nat) (cell : Q128Cell) : String :=
  toString (index + 1) ++ ":" ++ toString cell.lower ++ ":" ++
    toString cell.upper ++ ":" ++ toString cell.reciprocalUpper ++ "\n"

theorem lower_cast_toCell (cell : Q128Cell) :
    ((cell.toCell.lower : ℚ) : ℝ) = (cell.lower : ℝ) / q128Scale := by
  unfold toCell
  dsimp only
  rw [Rat.cast_div, Rat.cast_natCast, Rat.cast_natCast]

theorem upper_cast_toCell (cell : Q128Cell) :
    ((cell.toCell.upper : ℚ) : ℝ) = (cell.upper : ℝ) / q128Scale := by
  unfold toCell
  dsimp only
  rw [Rat.cast_div, Rat.cast_natCast, Rat.cast_natCast]

end Q128Cell

/-- A literal source-count table suitable for generation into a receipt
theorem module. -/
structure Q128CellTable where
  entries : Fin sourceCount → Q128Cell

namespace Q128CellTable

/-- Rational table consumed by the analytic source theorem. -/
def toCellTable (table : Q128CellTable) : CellTable where
  entries i := (table.entries i).toCell

/-- Complete canonical row preimage.  This is intentionally computed from the
literal table rather than accepted as a caller-supplied digest. -/
def canonicalPayload (table : Q128CellTable) : String :=
  String.join (List.ofFn (fun i ↦ (table.entries i).canonicalRow i.val))

/-- Kernel implementation of the exact table commitment carried by the
external artifacts and the trusted-compute receipt. -/
def commitment (table : Q128CellTable) : String :=
  SHA256.digestString table.canonicalPayload

end Q128CellTable

/-- Exact source-shaped multiplicity-preserving enumeration for a cell table. -/
def SourceClaim (table : CellTable) : Prop :=
  ∃ e : Fin sourceCount ≃ ZeroSlot,
    ∀ i,
      ((table.entries i).lower : ℝ) ≤ ((e i).1 : ℂ).im ∧
        ((e i).1 : ℂ).im ≤ ((table.entries i).upper : ℝ)

/-- Source claim specialized to a literal Q128 artifact table. -/
def Q128SourceClaim (table : Q128CellTable) : Prop :=
  SourceClaim table.toCellTable

/-- Checker-shaped evidence for the source claim.  The rational family is
ordinary untrusted data; `familyCheck` proves all local signs and ordering by
exact reduction.  The remaining fields are the explicit analytic refinement
obligations. -/
structure CheckedHeadEvidence (table : CellTable) where
  f : ℝ → ℝ
  model : HardyZModel f sourceHeight
  family : RationalBracketFamily sourceCount
  familyCheck : family.check = true
  endpointEnclosures : ∀ i, (family.entries i).EnclosesEndpoints f
  endpointsMatch : ∀ i,
    (family.entries i).lower = (table.entries i).lower ∧
      (family.entries i).upper = (table.entries i).upper
  positiveRange : ∀ i,
    0 < ((family.entries i).lower : ℝ) ∧
      ((family.entries i).upper : ℝ) ≤ sourceHeight
  /-- Turing/argument-principle conclusion, stated as total analytic slots. -/
  slotCard : Fintype.card ZeroSlot = sourceCount

/-- Receipt-facing evidence for one literal table.  The equality makes the
commitment a checked consequence of the rows and prevents a materializer from
substituting an unrelated digest string. -/
structure CheckedQ128HeadEvidence (table : Q128CellTable)
    (expectedCommitment : String) where
  commitment_eq : table.commitment = expectedCommitment
  checkedHead : CheckedHeadEvidence table.toCellTable

/-- A checked Hardy-Z bracket family plus the exact multiplicity count gives
the multiplicity-preserving source enumeration. -/
theorem sourceClaim_of_checked_head_evidence
    {table : CellTable} (evidence : CheckedHeadEvidence table) :
    SourceClaim table := by
  obtain ⟨certificate, hcertificateEndpoints⟩ :=
    evidence.family.exists_zeroCertificate evidence.familyCheck
      evidence.endpointEnclosures
  have hselection : Nonempty certificate.RootSelection :=
    certificate.exists_rootSelection
      (evidence.model.continuousOnBrackets certificate)
  let selection := Classical.choice hselection
  let root : Fin sourceCount → sourceBand := fun i =>
    ⟨criticalPoint (selection.point i), by
      have hcarrier := selection.mem_carrier i
      change (certificate.brackets i).lower ≤ selection.point i ∧
        selection.point i ≤ (certificate.brackets i).upper at hcarrier
      have hendpoints := evidence.endpointsMatch i
      have hrange := evidence.positiveRange i
      have htPos : 0 < selection.point i := by
        have hlower : ((evidence.family.entries i).lower : ℝ) ≤
            selection.point i := by
          rw [← hcertificateEndpoints i |>.1]
          exact hcarrier.1
        exact hrange.1.trans_le hlower
      have htUpper : selection.point i ≤ sourceHeight := by
        have hu : selection.point i ≤
            ((evidence.family.entries i).upper : ℝ) := by
          rw [← hcertificateEndpoints i |>.2]
          exact hcarrier.2
        exact hu.trans hrange.2
      have htDomain : selection.point i ∈ heightDomain sourceHeight := by
        change -sourceHeight ≤ selection.point i ∧
          selection.point i ≤ sourceHeight
        have hheight : (0 : ℝ) ≤ sourceHeight := by norm_num [sourceHeight]
        exact ⟨by linarith, htUpper⟩
      have hzeta : riemannZeta (criticalPoint (selection.point i)) = 0 :=
        (evidence.model.zero_iff htDomain).mp (selection.is_zero i)
      exact ⟨hzeta, by norm_num [criticalPoint], by norm_num [criticalPoint],
        by simpa [criticalPoint] using htPos,
        by simpa [criticalPoint] using htUpper⟩⟩
  have root_injective : Function.Injective root := by
    intro i j hij
    apply selection.injective
    have him := congrArg (fun z : ℂ ↦ z.im)
      (congrArg Subtype.val hij)
    simpa [root, criticalPoint] using him
  let toSlot : Fin sourceCount → ZeroSlot := fun i =>
    ⟨root i, ⟨0, sourceBand_multiplicity_pos (root i)⟩⟩
  have toSlot_injective : Function.Injective toSlot := by
    intro i j hij
    apply root_injective
    exact congrArg (fun slot : ZeroSlot ↦ slot.1) hij
  have hcard :
      Fintype.card (Fin sourceCount) = Fintype.card ZeroSlot := by
    rw [Fintype.card_fin, evidence.slotCard]
  have toSlot_surjective : Function.Surjective toSlot :=
    ((Fintype.bijective_iff_injective_and_card toSlot).2
      ⟨toSlot_injective, hcard⟩).2
  let e : Fin sourceCount ≃ ZeroSlot :=
    Equiv.ofBijective toSlot ⟨toSlot_injective, toSlot_surjective⟩
  refine ⟨e, ?_⟩
  intro i
  have hcarrier := selection.mem_carrier i
  change (certificate.brackets i).lower ≤ selection.point i ∧
    selection.point i ≤ (certificate.brackets i).upper at hcarrier
  have hendpoints := evidence.endpointsMatch i
  have hlower : ((table.entries i).lower : ℝ) ≤ selection.point i := by
    calc
      ((table.entries i).lower : ℝ) =
          ((evidence.family.entries i).lower : ℝ) := by rw [hendpoints.1]
      _ = (certificate.brackets i).lower := by
        rw [hcertificateEndpoints i |>.1]
      _ ≤ selection.point i := hcarrier.1
  have hupper : selection.point i ≤ ((table.entries i).upper : ℝ) := by
    calc
      selection.point i ≤ (certificate.brackets i).upper := hcarrier.2
      _ = ((evidence.family.entries i).upper : ℝ) := by
        rw [hcertificateEndpoints i |>.2]
      _ = ((table.entries i).upper : ℝ) := by rw [hendpoints.2]
  simpa [e, toSlot, root, criticalPoint] using And.intro hlower hupper

/-- A checked receipt-facing Q128 table yields its exact source claim. -/
theorem q128SourceClaim_of_checked_evidence
    {table : Q128CellTable} {expectedCommitment : String}
    (evidence : CheckedQ128HeadEvidence table expectedCommitment) :
    Q128SourceClaim table :=
  sourceClaim_of_checked_head_evidence evidence.checkedHead

end SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

end
