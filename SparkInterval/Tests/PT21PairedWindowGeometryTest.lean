/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21PairedWindowGeometry
import Mathlib.Tactic.NormNum

set_option autoImplicit false

namespace SparkInterval.Tests.PT21PairedWindowGeometryTest

open SparkInterval.Zeta.PT21PairedWindowGeometry

example :
    sampleOrdinate 1 (-12_870) =
      sampleOrdinate 0 (-12_870 + 24_576) := by
  exact successor_sample_reindex 0 (-12_870)

example :
    0 ≤ transformCenterIndex + 12_870 + sampleShiftPerWindow ∧
      transformCenterIndex + 12_870 + sampleShiftPerWindow <
        transformSampleCount := by
  apply successor_required_index_fits
  · norm_num [requiredLower]
  · norm_num [requiredUpper]

example :
    sourceBlockCount = 2 * pairedTransformCount + 1 := by
  exact campaign_pair_accounting.1

example :
    sampleOrdinate (50 + (-2)) 12_870 =
      sampleOrdinate 50 (12_870 + (-2) * 24_576) := by
  exact relative_sample_reindex 50 12_870 (-2)

example :
    transformLower ≤ -12_870 + 2 * sampleShiftPerWindow ∧
      -12_870 + 2 * sampleShiftPerWindow ≤ transformUpper := by
  apply five_window_required_view_fits
  · norm_num [requiredLower]
  · norm_num [requiredUpper]
  · norm_num
  · norm_num

example :
    sourceBlockCount = 5 * fiveWindowGroupCount + 3 := by
  exact campaign_five_window_accounting.1

example :
    ∃! group : Nat,
      group < fiveWindowGroupCount ∧
        5 * group ≤ 1_234_567 ∧ 1_234_567 < 5 * group + 5 := by
  exact (campaign_five_window_unique_partition
    (block := 1_234_567) (by norm_num [sourceBlockCount])).resolve_right
      (by norm_num [fiveWindowGroupCount])

example :
    5 * fiveWindowGroupCount ≤ 2_966_443_782 ∧
      2_966_443_782 < sourceBlockCount := by
  exact (campaign_five_window_unique_partition
    (block := 2_966_443_782) (by norm_num [sourceBlockCount])).resolve_left
      (by
        rintro ⟨group, ⟨groupBound, groupLower, groupUpper⟩, _unique⟩
        norm_num [fiveWindowGroupCount] at groupBound
        omega)

#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.successor_sample_reindex
#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.successor_required_index_fits
#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.campaign_pair_accounting
#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.relative_sample_reindex
#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.five_window_required_view_fits
#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.campaign_five_window_accounting
#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.campaign_five_window_unique_partition
#print axioms
  SparkInterval.Zeta.PT21PairedWindowGeometry.campaign_five_window_center_roster

end SparkInterval.Tests.PT21PairedWindowGeometryTest
