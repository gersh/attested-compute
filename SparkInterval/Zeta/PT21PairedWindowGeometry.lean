/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Rat.Defs
import Mathlib.Tactic

/-!
# Exact multi-window reuse geometry for the PT21 transform

The PT21 source transform produces `131072` samples at spacing `21/512`.
Successive theorem windows are separated by `1008`, which is exactly
`24576 * (21/512)`.  Consequently, when a transform is centred at one source
window, the next window's required sample with offset `j` is the same physical
ordinate as transform offset `j + 24576`.

Both complete required views `[-12870,12870]` fit inside the transform's
`[-65536,65535]` offset range.  Thus one transform may be *tested* as a
producer for two adjacent finite event scans.  This module proves only exact
index/ordinate geometry.  It does not prove that the CUDA transform encloses
Hardy Z, that all shifted disks have useful widths, or that paired execution
is source- or production-ready.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21PairedWindowGeometry

def sourceLower : ℤ := 10_000_000_000
def firstCenterOffset : ℤ := 504
def windowStep : ℤ := 1008
def sampleNumerator : ℤ := 21
def sampleDenominator : ℤ := 512
def sampleShiftPerWindow : ℤ := 24_576

def sourceBlockCount : Nat := 2_966_443_783
def pairedTransformCount : Nat := 1_483_221_891
def finalSingletonBlock : Nat := 2_966_443_782
def fiveWindowGroupCount : Nat := 593_288_756
def fiveWindowTransformCount : Nat := 593_288_757

def requiredLower : ℤ := -12_870
def requiredUpper : ℤ := 12_870
def transformLower : ℤ := -65_536
def transformUpper : ℤ := 65_535
def transformCenterIndex : ℤ := 65_536
def transformSampleCount : ℤ := 131_072

/-- Exact source-window centre, represented over the rationals so sample
coordinates can be compared without rounding. -/
def windowCenter (block : ℤ) : ℚ :=
  sourceLower + firstCenterOffset + windowStep * block

/-- Physical ordinate of one lattice sample relative to a logical window. -/
def sampleOrdinate (block offset : ℤ) : ℚ :=
  windowCenter block +
    offset * sampleNumerator / sampleDenominator

theorem windowStep_eq_sampleShift :
    (windowStep : ℚ) =
      sampleShiftPerWindow * sampleNumerator / sampleDenominator := by
  norm_num [windowStep, sampleShiftPerWindow, sampleNumerator,
    sampleDenominator]

/-- The key reuse identity: the successor window is an exact integral shift
within the first window's transform grid. -/
theorem successor_sample_reindex (block offset : ℤ) :
    sampleOrdinate (block + 1) offset =
      sampleOrdinate block (offset + sampleShiftPerWindow) := by
  rw [sampleOrdinate, sampleOrdinate, windowCenter, windowCenter]
  rw [show ((block + 1 : ℤ) : ℚ) = (block : ℚ) + 1 by norm_num]
  rw [show ((offset + sampleShiftPerWindow : ℤ) : ℚ) =
      (offset : ℚ) + sampleShiftPerWindow by norm_num]
  norm_num [sourceLower, firstCenterOffset, windowStep,
    sampleShiftPerWindow, sampleNumerator, sampleDenominator]
  ring

/-- General exact reindexing for a neighbouring logical block.  The useful
finite range below is `-2 ≤ delta ≤ 2`, but the identity itself is integral
and unbounded. -/
theorem relative_sample_reindex (block offset delta : ℤ) :
    sampleOrdinate (block + delta) offset =
      sampleOrdinate block
        (offset + delta * sampleShiftPerWindow) := by
  rw [sampleOrdinate, sampleOrdinate, windowCenter, windowCenter]
  rw [show ((block + delta : ℤ) : ℚ) =
      (block : ℚ) + delta by norm_num]
  rw [show
      ((offset + delta * sampleShiftPerWindow : ℤ) : ℚ) =
        (offset : ℚ) + delta * sampleShiftPerWindow by norm_num]
  norm_num [sourceLower, firstCenterOffset, windowStep,
    sampleShiftPerWindow, sampleNumerator, sampleDenominator]
  ring

theorem first_required_view_fits
    {offset : ℤ}
    (lower : requiredLower ≤ offset)
    (upper : offset ≤ requiredUpper) :
    transformLower ≤ offset ∧ offset ≤ transformUpper := by
  simp only [requiredLower, requiredUpper, transformLower,
    transformUpper] at lower upper ⊢
  omega

theorem successor_required_view_fits
    {offset : ℤ}
    (lower : requiredLower ≤ offset)
    (upper : offset ≤ requiredUpper) :
    transformLower ≤ offset + sampleShiftPerWindow ∧
      offset + sampleShiftPerWindow ≤ transformUpper := by
  simp only [requiredLower, requiredUpper, sampleShiftPerWindow,
    transformLower, transformUpper] at lower upper ⊢
  omega

/-- Array bounds for the first required view in a zero-based transform. -/
theorem first_required_index_fits
    {offset : ℤ}
    (lower : requiredLower ≤ offset)
    (upper : offset ≤ requiredUpper) :
    0 ≤ transformCenterIndex + offset ∧
      transformCenterIndex + offset < transformSampleCount := by
  simp only [requiredLower, requiredUpper, transformCenterIndex,
    transformSampleCount] at lower upper ⊢
  omega

/-- Array bounds for the shifted successor view in the same transform. -/
theorem successor_required_index_fits
    {offset : ℤ}
    (lower : requiredLower ≤ offset)
    (upper : offset ≤ requiredUpper) :
    0 ≤ transformCenterIndex + offset + sampleShiftPerWindow ∧
      transformCenterIndex + offset + sampleShiftPerWindow <
        transformSampleCount := by
  simp only [requiredLower, requiredUpper, transformCenterIndex,
    sampleShiftPerWindow, transformSampleCount] at lower upper ⊢
  omega

/-- A transform centred at the middle logical block has room for the complete
required views of that block and its two predecessors and successors.  Width
certification is a separate runtime gate. -/
theorem five_window_required_view_fits
    {offset delta : ℤ}
    (offsetLower : requiredLower ≤ offset)
    (offsetUpper : offset ≤ requiredUpper)
    (deltaLower : -2 ≤ delta)
    (deltaUpper : delta ≤ 2) :
    transformLower ≤ offset + delta * sampleShiftPerWindow ∧
      offset + delta * sampleShiftPerWindow ≤ transformUpper := by
  simp only [requiredLower, requiredUpper, sampleShiftPerWindow,
    transformLower, transformUpper] at offsetLower offsetUpper ⊢
  omega

theorem five_window_required_index_fits
    {offset delta : ℤ}
    (offsetLower : requiredLower ≤ offset)
    (offsetUpper : offset ≤ requiredUpper)
    (deltaLower : -2 ≤ delta)
    (deltaUpper : delta ≤ 2) :
    0 ≤ transformCenterIndex + offset +
        delta * sampleShiftPerWindow ∧
      transformCenterIndex + offset + delta * sampleShiftPerWindow <
        transformSampleCount := by
  simp only [requiredLower, requiredUpper, transformCenterIndex,
    sampleShiftPerWindow, transformSampleCount] at offsetLower offsetUpper ⊢
  omega

/-- The full campaign has an odd number of blocks: all but the final block can
be assigned to exact adjacent pairs. -/
theorem campaign_pair_accounting :
    sourceBlockCount = 2 * pairedTransformCount + 1 ∧
      finalSingletonBlock + 1 = sourceBlockCount := by
  norm_num [sourceBlockCount, pairedTransformCount, finalSingletonBlock]

/-- Pure geometry permits `floor(blocks/5)` centred five-window groups and a
final centred three-window group.  Whether the outer shifted disks remain
strictly signed must be measured and checked; this is not a readiness claim. -/
theorem campaign_five_window_accounting :
    sourceBlockCount = 5 * fiveWindowGroupCount + 3 ∧
      fiveWindowTransformCount = fiveWindowGroupCount + 1 := by
  norm_num [sourceBlockCount, fiveWindowGroupCount,
    fiveWindowTransformCount]

/-- Every campaign block belongs either to one unique complete five-block
group `[5*k, 5*k+5)`, or to the single residual interval
`[5*fiveWindowGroupCount, sourceBlockCount)`.  The latter has exactly three
blocks by `campaign_five_window_accounting`.  This is the missing
gap-free/non-overlap statement behind the transform-count arithmetic. -/
theorem campaign_five_window_unique_partition
    {block : Nat}
    (inCampaign : block < sourceBlockCount) :
    (∃! group : Nat,
      group < fiveWindowGroupCount ∧
        5 * group ≤ block ∧ block < 5 * group + 5) ∨
      (5 * fiveWindowGroupCount ≤ block ∧
        block < sourceBlockCount) := by
  by_cases inFullGroups : block < 5 * fiveWindowGroupCount
  · left
    have fivePositive : 0 < (5 : Nat) := by norm_num
    have remainderSmall := Nat.mod_lt block fivePositive
    have divisionIdentity := Nat.div_add_mod block 5
    refine ⟨block / 5, ?_, ?_⟩
    · constructor
      · omega
      constructor <;> omega
    · intro candidate candidateOwns
      omega
  · right
    exact ⟨Nat.le_of_not_gt inFullGroups, inCampaign⟩

/-- The centres selected by the unique partition are `5*k+2` for complete
groups and `5*fiveWindowGroupCount+1` for the final three blocks. -/
theorem campaign_five_window_center_roster :
    (∀ group < fiveWindowGroupCount,
      5 * group ≤ 5 * group + 2 ∧
        5 * group + 2 < 5 * group + 5) ∧
      (5 * fiveWindowGroupCount ≤
          5 * fiveWindowGroupCount + 1 ∧
        5 * fiveWindowGroupCount + 1 < sourceBlockCount) := by
  constructor
  · intro group _groupInRange
    omega
  · norm_num [sourceBlockCount, fiveWindowGroupCount]

#print axioms windowStep_eq_sampleShift
#print axioms successor_sample_reindex
#print axioms relative_sample_reindex
#print axioms first_required_view_fits
#print axioms successor_required_view_fits
#print axioms first_required_index_fits
#print axioms successor_required_index_fits
#print axioms five_window_required_view_fits
#print axioms five_window_required_index_fits
#print axioms campaign_pair_accounting
#print axioms campaign_five_window_accounting
#print axioms campaign_five_window_unique_partition
#print axioms campaign_five_window_center_roster

end SparkInterval.Zeta.PT21PairedWindowGeometry
