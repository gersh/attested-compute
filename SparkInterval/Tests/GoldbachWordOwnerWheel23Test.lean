/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWordOwnerWheel23

namespace SparkInterval.Tests.GoldbachWordOwnerWheel23Test

open TernaryGoldbach.GoldbachWordOwnerWheel23

private def bitOne : Fin 64 :=
  ⟨1, by norm_num⟩

private def bitFour : Fin 64 :=
  ⟨4, by norm_num⟩

private def bitTwelve : Fin 64 :=
  ⟨12, by norm_num⟩

private def bitFourteen : Fin 64 :=
  ⟨14, by norm_num⟩

example :
    wheelModulus = 3 * 5 * 7 * 11 * 13 * 17 * 19 * 23 := by
  norm_num [wheelModulus]

example :
    cudaPhase 101 2 63 = 241 := by
  norm_num [cudaPhase, cudaHalf, wheelModulus, Nat.shiftRight_eq_div_pow]

example :
    cudaPhase 101 2 63 =
      (wordCandidate 101 2 63 >>> 1) % wheelModulus := by
  exact cudaPhase_addresses_wordCandidate
    101 2 63 (by norm_num) (by norm_num)

example :
    duplicatedWheelTableBit (wheelModulus - 2 + 3) =
      wheelTableBit 1 := by
  rw [duplicatedWheelTableBit_eq_mod
    (wheelModulus - 2) 3]
  · norm_num [wheelModulus]
  · norm_num [wheelModulus]
  · norm_num

example :
    23 ∣ tableOddValue (cudaPhase 1 0 11) ↔
      23 ∣ wordCandidate 1 0 11 := by
  exact tableOddValue_cudaPhase_dvd_iff_wordCandidate
    (by norm_num [wheelPrimes])
    1 0 11 (by norm_num) (by norm_num)

/-- The raw table would clear 3, but explicit restoration retains it. -/
example :
    restoredWheelInitializer 1 0 bitOne = true := by
  rw [restoredWheelInitializer_eq_squareGuard 1 0 (by norm_num)]
  norm_num [squareGuardWheelInitializer, applySquareGuardClears,
    clearedByBool, wheelPrimes, wordCandidate, allOnesWord, bitOne]

/-- Nine is legitimately cleared by the square-guarded prime 3. -/
example :
    restoredWheelInitializer 1 0 bitFour = false := by
  rw [restoredWheelInitializer_eq_squareGuard 1 0 (by norm_num)]
  norm_num [squareGuardWheelInitializer, applySquareGuardClears,
    clearedByBool, wheelPrimes, wordCandidate, allOnesWord, bitFour]

/-- Twenty-five is legitimately cleared exactly when the 5-square guard
becomes live. -/
example :
    restoredWheelInitializer 1 0 bitTwelve = false := by
  rw [restoredWheelInitializer_eq_squareGuard 1 0 (by norm_num)]
  norm_num [squareGuardWheelInitializer, applySquareGuardClears,
    clearedByBool, wheelPrimes, wordCandidate, allOnesWord, bitTwelve]

/-- Twenty-nine survives the through-23 initializer. -/
example :
    restoredWheelInitializer 1 0 bitFourteen = true := by
  rw [restoredWheelInitializer_eq_squareGuard 1 0 (by norm_num)]
  norm_num [squareGuardWheelInitializer, applySquareGuardClears,
    clearedByBool, wheelPrimes, wordCandidate, allOnesWord, bitFourteen]

example :
    applySquareGuardClears
        (restoredWheelInitializer 101 7)
        101 7 [29, 31] =
      applySquareGuardClears allOnesWord 101 7
        (wheelPrimes ++ [29, 31]) := by
  exact restoredWheel_then_remaining_eq_original
    101 7 (by norm_num) [29, 31]

end SparkInterval.Tests.GoldbachWordOwnerWheel23Test
