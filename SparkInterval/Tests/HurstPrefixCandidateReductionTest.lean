/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction

namespace SparkInterval.Tests.HurstPrefixCandidateReductionTest

open SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter
open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction

/-- Raw native bytes for Möbius values `[1, -1, 0, 1]`. -/
def sampleRows : List UInt8 := [1, 255, 0, 1]

#guard MobiusRowsValid sampleRows
#guard !(MobiusRowsValid ([2] : List UInt8))

/-- Production-shaped unscanned pairs corresponding to `sampleRows`. -/
def sampleInputRows : List PrefixMQ :=
  [ { mertens := 1, squarefree := 1 }
  , { mertens := -1, squarefree := 1 }
  , { mertens := 0, squarefree := 0 }
  , { mertens := 1, squarefree := 1 } ]

#guard PrefixInputRowsValid sampleInputRows
#guard !(PrefixInputRowsValid
  ([{ mertens := 0, squarefree := 1 }] : List PrefixMQ))

example :
    inclusiveInputScan sampleInputRows =
      [ { mertens := 1, squarefree := 1 }
      , { mertens := 0, squarefree := 2 }
      , { mertens := 0, squarefree := 2 }
      , { mertens := 1, squarefree := 3 } ] := by
  decide

example :
    inclusiveScan sampleRows =
      [ { mertens := 1, squarefree := 1 }
      , { mertens := 0, squarefree := 2 }
      , { mertens := 0, squarefree := 2 }
      , { mertens := 1, squarefree := 3 } ] := by
  decide

/-- The raw-byte qualification path initializes exactly the production
direct-row input. -/
example : sampleRows.map rowDelta = sampleInputRows := by
  decide

example :
    inclusiveInputScan (sampleRows.map rowDelta) =
      inclusiveScan sampleRows :=
  inclusiveInputScan_map_rowDelta sampleRows

example :
    inputScanFrom PrefixMQ.zero
        (sampleInputRows.take 2 ++ sampleInputRows.drop 2) =
      inputScanFrom PrefixMQ.zero (sampleInputRows.take 2) ++
        inputScanFrom
          (PrefixMQ.zero + inputTotal (sampleInputRows.take 2))
          (sampleInputRows.drop 2) :=
  inputScanFrom_append PrefixMQ.zero
    (sampleInputRows.take 2) (sampleInputRows.drop 2)

example :
    localMertens sampleRows 4 = 1 ∧
      localSquarefree sampleRows 4 = 3 := by
  decide

def prefixMertens (_index : Nat) (pfx : PrefixMQ) : Int :=
  pfx.mertens

def sampleCandidates : List OrderedCandidate :=
  rowCandidates prefixMertens 0 (inclusiveScan sampleRows)

def sampleInputCandidates : List OrderedCandidate :=
  rowCandidates prefixMertens 0 (inclusiveInputScan sampleInputRows)

def samplePairedCandidates : List OrderedCandidate :=
  pairedEndpointCandidates prefixMertens prefixMertens
    (fun index => index != 3)
    (inclusiveInputScan sampleInputRows)

example : sampleInputCandidates = sampleCandidates := by
  decide

example :
    samplePairedCandidates =
      [ { value := 1, order := 0 }
      , { value := 0, order := 2 }
      , { value := 0, order := 4 }
      , { value := 1, order := 6 }
      , { value := 1, order := 1 }
      , { value := 0, order := 3 }
      , { value := 0, order := 5 } ] := by
  decide

/- The terminal right-limit order seven is absent. -/
#guard !(samplePairedCandidates.any (fun candidate =>
  candidate.order == 7))

example :
    sampleCandidates =
      [ { value := 1, order := 0 }
      , { value := 0, order := 2 }
      , { value := 0, order := 4 }
      , { value := 1, order := 6 } ] := by
  decide

/-- Equal maxima at orders zero and six select order zero. -/
example :
    reduceMaximum sampleCandidates =
      some { value := 1, order := 0 } := by
  decide

/-- Equal minima at orders two and four select order two. -/
example :
    reduceMinimum sampleCandidates =
      some { value := 0, order := 2 } := by
  decide

example :
    reduceMaximum samplePairedCandidates =
      some { value := 1, order := 0 } := by
  decide

example :
    let best : OrderedCandidate := { value := 1, order := 0 }
    best ∈ samplePairedCandidates ∧
      best.order < 2 ^ 32 ∧
      ∀ candidate ∈ samplePairedCandidates,
        candidate.value ≤ best.value ∧
          (candidate.value = best.value →
            best.order ≤ candidate.order) := by
  apply reducePairedEndpointMaximum_sound
    (prefixes := inclusiveInputScan sampleInputRows)
    (integerValue := prefixMertens)
    (rightValue := prefixMertens)
    (includeRight := fun index => index != 3)
  · norm_num [
      SparkInterval.TernaryGoldbach.MobiusFusedSupport.maximumSegmentRows,
      sampleInputRows]
  · decide

/-- Regrouping a candidate stream across a synthetic worker boundary leaves
the same sequential fold. -/
example :
    foldByKey lowerKey
        { value := 1, order := 0 }
        (sampleCandidates.take 1 ++ sampleCandidates.drop 1) =
      foldByKey lowerKey
        (foldByKey lowerKey
          { value := 1, order := 0 }
          (sampleCandidates.take 1))
        (sampleCandidates.drop 1) := by
  exact foldByKey_append lowerKey
    { value := 1, order := 0 }
    (sampleCandidates.take 1)
    (sampleCandidates.drop 1)

example :
    PrefixFitsMachineWords (prefixAt sampleRows 4) :=
  prefixAt_fits_machine_words
    (rows := sampleRows)
    (by simp [sampleRows, MobiusRowsValid, MobiusByteValid])
    (by norm_num [sampleRows,
      SparkInterval.TernaryGoldbach.MobiusFusedSupport.maximumSegmentRows])
    4

example :
    PrefixFitsMachineWords (inputPrefixAt sampleInputRows 4) :=
  inputPrefixAt_fits_machine_words
    (rows := sampleInputRows)
    (by simp [sampleInputRows, PrefixInputRowsValid,
      PrefixInputRowValid])
    (by norm_num [sampleInputRows,
      SparkInterval.TernaryGoldbach.MobiusFusedSupport.maximumSegmentRows])
    4

example :
    (∀ best,
      reduceMaximum
          (rowCandidates prefixMertens 0
            (inclusiveScan sampleRows)) = some best →
        best ∈ rowCandidates prefixMertens 0
            (inclusiveScan sampleRows) ∧
        best.order < 2 ^ 32 ∧
        ∀ candidate ∈ rowCandidates prefixMertens 0
            (inclusiveScan sampleRows),
          candidate.value ≤ best.value ∧
            (candidate.value = best.value →
              best.order ≤ candidate.order)) := by
  have sound :=
    scanAndCandidateReduction_sound
      (rows := sampleRows)
      (by simp [sampleRows, MobiusRowsValid, MobiusByteValid])
      (by norm_num [sampleRows,
        SparkInterval.TernaryGoldbach.MobiusFusedSupport.maximumSegmentRows])
      prefixMertens prefixMertens
      (lowerEndpoint := 0) (upperEndpoint := 0)
      (by omega) (by omega)
  exact sound.2.1

example :
    (∀ best,
      reduceMaximum
          (rowCandidates prefixMertens 0
            (inclusiveInputScan sampleInputRows)) = some best →
        best ∈ rowCandidates prefixMertens 0
            (inclusiveInputScan sampleInputRows) ∧
        best.order < 2 ^ 32 ∧
        ∀ candidate ∈ rowCandidates prefixMertens 0
            (inclusiveInputScan sampleInputRows),
          candidate.value ≤ best.value ∧
            (candidate.value = best.value →
              best.order ≤ candidate.order)) := by
  have sound :=
    inputScanAndCandidateReduction_sound
      (rows := sampleInputRows)
      (by simp [sampleInputRows, PrefixInputRowsValid,
        PrefixInputRowValid])
      (by norm_num [sampleInputRows,
        SparkInterval.TernaryGoldbach.MobiusFusedSupport.maximumSegmentRows])
      prefixMertens prefixMertens
      (lowerEndpoint := 0) (upperEndpoint := 0)
      (by omega) (by omega)
  exact sound.2.1

example :
    ∃ lowerBest upperBest,
      reduceMaximum sampleInputCandidates = some lowerBest ∧
      reduceMinimum sampleInputCandidates = some upperBest := by
  exact inputScanReducers_return_winners
    (rows := sampleInputRows) (by decide)
    prefixMertens prefixMertens 0 0

#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inclusiveInputScan_getElem
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputScanFrom_append
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputPrefixAt_fits_machine_words
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputScanAndCandidateReduction_sound
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inclusiveInputScan_map_rowDelta
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inclusiveScan_getElem
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.prefixAt_fits_machine_words
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.reduceMaximum_sound
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.reduceMinimum_sound
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.combineMaximum_assoc
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.combineMinimum_assoc
#print axioms
  SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.scanAndCandidateReduction_sound

end SparkInterval.Tests.HurstPrefixCandidateReductionTest
