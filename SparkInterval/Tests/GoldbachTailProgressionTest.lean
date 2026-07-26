/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachTailProgression

namespace SparkInterval.Tests.GoldbachTailProgressionTest

open TernaryGoldbach.GoldbachTailProgression
open TernaryGoldbach.GoldbachWordOwnerSieve

example : 84 &&& 1 = 0 ↔ Even 84 :=
  bitmaskOne_eq_zero_iff_even 84

example : ¬ (85 &&& 1 = 0) := by
  rw [bitmaskOne_eq_zero_iff_even]
  norm_num

/-- The source branches choose `113²` as the first term when the window
starts below the square. -/
example : firstCofactor 12_001 113 = 113 := by
  norm_num [firstCofactor, oddAdjustedCofactor, ceilingCofactor]

/-- Above the square, the ceiling and odd adjustment choose the first odd
multiple in the window. -/
example : firstComposite 20_000 113 = 20_001 := by
  norm_num [firstComposite, firstCofactor, oddAdjustedCofactor,
    ceilingCofactor, Nat.even_iff]

/-- A later odd composite is present in the sequential tail progression. -/
example : ∃ index, tailComposite 20_000 113 index = 21_357 := by
  exact tailComposite_complete
    (qLow := 20_000) (prime := 113) (candidate := 21_357)
    (by norm_num) (by norm_num [Odd]) (by norm_num [Odd])
    (by norm_num) (by norm_num) (by norm_num)

/-- The same composite is present in one exact warp lane and round. -/
example :
    ∃ lane : Fin 32, ∃ round,
      warpComposite (firstComposite 20_000 113) (2 * 113)
        lane round = 21_357 := by
  exact warpTail_complete
    (qLow := 20_000) (prime := 113) (candidate := 21_357)
    (by norm_num) (by norm_num [Odd]) (by norm_num [Odd])
    (by norm_num) (by norm_num) (by norm_num)

/-- Every generated term is in the mathematical clear set. -/
example :
    ClearedBy [3, 5, 7, 113] (tailComposite 20_000 113 5) := by
  exact tailComposite_clearedBy [3, 5, 7, 113] 20_000 113 5
    (by norm_num) (by norm_num [Odd]) (by norm_num)

/-- The literal bounded start model accepts the exact pair retained by the
optimized CUDA source. -/
example :
    cudaTailStart? 20_000 22_000 113 =
      some (firstComposite 20_000 113, firstCofactor 20_000 113) := by
  exact
    (cudaTailStart_eq_some_of_bounded_candidate
      (qLow := 20_000) (qHigh := 22_000)
      (prime := 113) (candidate := 21_357)
      (by norm_num) (by norm_num [Odd]) (by norm_num [Odd])
      (by norm_num) (by norm_num) (by norm_num) (by norm_num)
      (by norm_num)).1

/-- The literal lower-prime guard rejects a non-kernel prime. -/
example : cudaTailStart? 3 101 1 = none := by
  norm_num [cudaTailStart?]

/-- The source square guard rejects a prime whose square is above the
inclusive window. -/
example : cudaTailStart? 101 119 11 = none := by
  norm_num [cudaTailStart?]

/-- When the first ceiling multiple is even but its odd successor would leave
the window, the nested subtraction guard rejects before adding the prime. -/
example : cudaTailStart? 23 25 3 = none := by
  norm_num [cudaTailStart?, ceilingCofactor, Nat.even_iff]

/-- The bounded one-thread theorem also proves that the exact packed bit
targeted for the candidate is live. -/
example :
    cudaTailStart? 20_001 22_001 113 =
        some (firstComposite 20_001 113, firstCofactor 20_001 113) ∧
      ∃ index,
        tailComposite 20_001 113 index = 21_357 ∧
          TailLoopReaches 20_001 22_001 113 index ∧
          21_357 =
            20_001 + 2 * oddBitIndex 20_001 21_357 ∧
          oddBitIndex 20_001 21_357 <
            oddWindowCount 20_001 22_001 := by
  exact boundedTail_complete
    (qLow := 20_001) (qHigh := 22_001)
    (prime := 113) (candidate := 21_357)
    (by norm_num) (by norm_num [Odd]) (by norm_num [Odd])
    (by norm_num [Odd]) (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num)

/-- The bounded one-warp theorem reaches the same live bit through the source
32-lane schedule. -/
example :
    cudaTailStart? 20_001 22_001 113 =
        some (firstComposite 20_001 113, firstCofactor 20_001 113) ∧
      ∃ lane : Fin 32, ∃ round,
        warpComposite (firstComposite 20_001 113) (2 * 113)
            lane round = 21_357 ∧
          WarpLoopReaches 22_001
            (firstComposite 20_001 113) (2 * 113) lane round ∧
          21_357 =
            20_001 + 2 * oddBitIndex 20_001 21_357 ∧
          oddBitIndex 20_001 21_357 <
            oddWindowCount 20_001 22_001 := by
  exact boundedWarpTail_complete
    (qLow := 20_001) (qHigh := 22_001)
    (prime := 113) (candidate := 21_357)
    (by norm_num) (by norm_num [Odd]) (by norm_num [Odd])
    (by norm_num [Odd]) (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num)

end SparkInterval.Tests.GoldbachTailProgressionTest
