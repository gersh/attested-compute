/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing

set_option autoImplicit false

namespace SparkInterval.Tests.GoldbachWarpLaunchIndexingTest

open SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing

/-- Ten logical primes require 320 threads and therefore two source blocks. -/
example : sourceLaunchBlocks 10 = 2 ∧ launchBlocks 10 = 2 := by
  norm_num [sourceLaunchBlocks, launchBlocks, launchThreadCount,
    threadsPerBlock, warpWidth]

/-- The last lane of prime nine is global thread 319, owned by thread 63 in
the rounded second block. -/
example :
    ownerCoordinate 9 (31 : Fin 32) =
      { block := 1, thread := 63 } := by
  norm_num [ownerCoordinate, primeLaneGlobalIndex,
    threadsPerBlock, warpWidth]

example :
    (ownerCoordinate 9 (31 : Fin 32)).warpIndex = 9 ∧
      (ownerCoordinate 9 (31 : Fin 32)).lane = 31 := by
  exact ⟨ownerCoordinate_warpIndex 9 (31 : Fin 32),
    ownerCoordinate_lane 9 (31 : Fin 32)⟩

/-- The literal source bit-mask lane agrees with the arithmetic lane. -/
example :
    (ownerCoordinate 9 (31 : Fin 32)).sourceLane = 31 := by
  rw [sourceLane_eq_lane]
  exact ownerCoordinate_lane 9 (31 : Fin 32)

/-- The final partial block still supplies exactly one active owner. -/
example :
    ∃! coordinate, OwnsPrimeLane 10 9 (31 : Fin 32) coordinate :=
  existsUnique_ownerCoordinate (by norm_num)

/-- The same rounded-block owner statement uses source `threadIdx.x & 31`
directly. -/
example :
    ∃! coordinate, SourceOwnsPrimeLane 10 9 (31 : Fin 32) coordinate :=
  existsUnique_sourceOwnerCoordinate (by norm_num)

/-- The first lane in the next logical warp is decoded without overlap. -/
example :
    ∃! coordinate, OwnsPrimeLane 10 9 (0 : Fin 32) coordinate :=
  existsUnique_ownerCoordinate (by norm_num)

/-- A production-bounded launch fits every modeled 32- and 64-bit field. -/
example :
    launchThreadCount maximumWarpPrimeCount < 2 ^ 32 ∧
      launchThreadCount maximumWarpPrimeCount +
          (threadsPerBlock - 1) < 2 ^ 32 ∧
      launchBlocks maximumWarpPrimeCount < 2 ^ 32 ∧
      ∀ coordinate : ThreadCoordinate,
        coordinate.block < launchBlocks maximumWarpPrimeCount →
        coordinate.thread < threadsPerBlock →
          coordinate.block * threadsPerBlock < 2 ^ 32 ∧
          coordinate.globalIndex < 2 ^ 32 ∧
          coordinate.globalIndex < 2 ^ 64 :=
  productionLaunch_widthSafe (by rfl)

/-- The concrete rounded-block boundary owner inherits those width bounds. -/
example :
    primeLaneGlobalIndex 9 (31 : Fin 32) < 2 ^ 32 ∧
      (ownerCoordinate 9 (31 : Fin 32)).block * threadsPerBlock < 2 ^ 32 ∧
      (ownerCoordinate 9 (31 : Fin 32)).globalIndex < 2 ^ 32 ∧
      (ownerCoordinate 9 (31 : Fin 32)).globalIndex < 2 ^ 64 :=
  productionOwner_widthSafe (primeCount := 10)
    (by norm_num [maximumWarpPrimeCount]) (by norm_num)

#print axioms
  SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.sourceLaunchBlocks_eq_launchBlocks
#print axioms
  SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.bitmask31_eq_mod32
#print axioms
  SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.warp_lane_decode
#print axioms
  SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.existsUnique_ownerCoordinate
#print axioms
  SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.existsUnique_sourceOwnerCoordinate
#print axioms
  SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.productionLaunch_widthSafe
#print axioms
  SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.productionOwner_widthSafe

end SparkInterval.Tests.GoldbachWarpLaunchIndexingTest
