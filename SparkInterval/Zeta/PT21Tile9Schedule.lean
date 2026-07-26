/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinCUDADataflow

/-!
# PT21 stages-1..9 tile schedule

These are PT21-specific instantiations of the reusable exact radix-2
shared-prefix theorems.  The 32,768-point row transforms have `logLength = 15`
and the final 65,536-point Hermitian transform has `logLength = 16`; both use
512-value (`tileLog = 9`) tiles.

The statements prove exact positive- and negative-root schedule preservation,
including the ordinary stages after the shared prefix.  They do not prove
binary64/DD enclosure refinement, CUDA execution, or compiler correctness.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21Tile9Schedule

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution
open SparkInterval.Dirichlet.BluesteinCUDADataflow
open SparkInterval.Zeta.WindowedRadix2

/-- The positive-root stages 1..9 of a PT21 32,768-point row transform are
pointwise identical when grouped into 512-value tiles. -/
theorem positive_row_prefix
    (state : ExactState 15)
    (tile : Fin (2 ^ (15 - 9))) (slot : Fin (2 ^ 9)) :
    (runExactStages positiveTwiddle 9 0 state).value
        (tileGlobalIndex (by omega : 9 ≤ 15) tile slot) =
      (initialStagesInTile (by omega : 9 ≤ 15) state tile).value slot :=
  initialStages_grouped_by_tile (by omega) state tile slot

/-- Negative-root counterpart for the PT21 32,768-point row transforms. -/
theorem negative_row_prefix
    (state : ExactState 15)
    (tile : Fin (2 ^ (15 - 9))) (slot : Fin (2 ^ 9)) :
    (runExactStages negativeTwiddle 9 0 state).value
        (tileGlobalIndex (by omega : 9 ≤ 15) tile slot) =
      (negativeInitialStagesInTile (by omega : 9 ≤ 15) state tile).value
        slot :=
  negativeInitialStages_grouped_by_tile (by omega) state tile slot

/-- The positive-root stages 1..9 of the final PT21 65,536-point transform
are pointwise identical when grouped into 512-value tiles. -/
theorem positive_final_prefix
    (state : ExactState 16)
    (tile : Fin (2 ^ (16 - 9))) (slot : Fin (2 ^ 9)) :
    (runExactStages positiveTwiddle 9 0 state).value
        (tileGlobalIndex (by omega : 9 ≤ 16) tile slot) =
      (initialStagesInTile (by omega : 9 ≤ 16) state tile).value slot :=
  initialStages_grouped_by_tile (by omega) state tile slot

/-- Negative-root counterpart for the final PT21 65,536-point transform. -/
theorem negative_final_prefix
    (state : ExactState 16)
    (tile : Fin (2 ^ (16 - 9))) (slot : Fin (2 ^ 9)) :
    (runExactStages negativeTwiddle 9 0 state).value
        (tileGlobalIndex (by omega : 9 ≤ 16) tile slot) =
      (negativeInitialStagesInTile (by omega : 9 ≤ 16) state tile).value
        slot :=
  negativeInitialStages_grouped_by_tile (by omega) state tile slot

/-- Grouped positive stages 1..9 followed by ordinary stages 10..15 preserve
the complete PT21 row-transform schedule. -/
theorem positive_row_full_schedule (state : ExactState 15) :
    positiveSharedLaunch (by omega : 9 ≤ 15) state =
      runExactStages positiveTwiddle 15 0 state :=
  positiveSharedLaunch_eq_full (by omega) state

/-- Grouped negative stages 1..9 followed by ordinary stages 10..15 preserve
the complete PT21 row-transform schedule. -/
theorem negative_row_full_schedule (state : ExactState 15) :
    negativeSharedLaunch (by omega : 9 ≤ 15) state =
      runExactStages negativeTwiddle 15 0 state :=
  negativeSharedLaunch_eq_full (by omega) state

/-- Grouped positive stages 1..9 followed by ordinary stages 10..16 preserve
the complete final PT21 transform schedule. -/
theorem positive_final_full_schedule (state : ExactState 16) :
    positiveSharedLaunch (by omega : 9 ≤ 16) state =
      runExactStages positiveTwiddle 16 0 state :=
  positiveSharedLaunch_eq_full (by omega) state

/-- Grouped negative stages 1..9 followed by ordinary stages 10..16 preserve
the complete final PT21 transform schedule. -/
theorem negative_final_full_schedule (state : ExactState 16) :
    negativeSharedLaunch (by omega : 9 ≤ 16) state =
      runExactStages negativeTwiddle 16 0 state :=
  negativeSharedLaunch_eq_full (by omega) state

end SparkInterval.Zeta.PT21Tile9Schedule
