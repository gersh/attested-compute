/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstAffineClusterComposition

/-!
# Source-shaped composition for the CUDA terminal affine scan

The qualification CUDA path divides a leaf into consecutive blocks of 65,536
Möbius input rows.  Every block scans from the zero `{M,Q}` state and retains
its exact delta and four affine extrema.  The device finalizer composes those
summaries in source order.

This file states that algorithm at the row-list level.  In particular:

* a right block is translated by **minus** the affine coordinate of the whole
  left delta;
* candidates are generated with their global source order already installed,
  so composition shifts their values but does not shift their orders;
* all full blocks have 65,536 rows and the optional final block is strictly
  shorter (including the empty exact-multiple case);
* ordered block composition has exactly the same winner, including earliest
  source-order tie breaking, as the ordinary per-row inclusive scan.

The CUDA/CUB refinement to this list theorem remains a separate executable
boundary.  This theorem does not turn a qualification executable into source
evidence or discharge an external analytic atom.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstAffineBlockComposition

open SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter
open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
open SparkInterval.TernaryGoldbach.HurstAffineClusterComposition
open SparkInterval.TernaryGoldbach.MobiusFusedSupport

/-- Exact number of consecutive rows summarized by every non-final CUDA
block. -/
def cudaAffineRowsPerBlock : Nat := 65_536

def cudaAffineThreadsPerBlock : Nat := 256

def cudaAffineRowsPerThread : Nat := 256

theorem cudaAffineTileFactorization :
    cudaAffineRowsPerBlock =
      cudaAffineRowsPerThread * cudaAffineThreadsPerBlock := by
  norm_num [cudaAffineRowsPerBlock, cudaAffineRowsPerThread,
    cudaAffineThreadsPerBlock]

/-- Number of block summaries emitted for a source leaf. -/
def cudaAffineSummaryCount (count : Nat) : Nat :=
  if count = 0 then 0
  else 1 + (count - 1) / cudaAffineRowsPerBlock

def cudaAffineRowBlock (index : Nat) : Nat :=
  index / cudaAffineRowsPerBlock

def cudaAffineRowLocal (index : Nat) : Nat :=
  index % cudaAffineRowsPerBlock

def cudaAffineRowStripe (index : Nat) : Nat :=
  cudaAffineRowLocal index / cudaAffineThreadsPerBlock

def cudaAffineRowThread (index : Nat) : Nat :=
  cudaAffineRowLocal index % cudaAffineThreadsPerBlock

def cudaAffineLaunchRow
    (block stripe thread : Nat) : Nat :=
  block * cudaAffineRowsPerBlock +
    stripe * cudaAffineThreadsPerBlock + thread

/-- The native `block * 65,536 + stripe * 256 + thread` expression
reconstructs every source row exactly. -/
theorem cudaAffineLaunchRow_decode (index : Nat) :
    cudaAffineLaunchRow
      (cudaAffineRowBlock index)
      (cudaAffineRowStripe index)
      (cudaAffineRowThread index) = index := by
  have outer :=
    Nat.div_add_mod index cudaAffineRowsPerBlock
  have inner :=
    Nat.div_add_mod
      (cudaAffineRowLocal index) cudaAffineThreadsPerBlock
  norm_num [cudaAffineLaunchRow, cudaAffineRowBlock,
    cudaAffineRowStripe, cudaAffineRowThread,
    cudaAffineRowLocal, cudaAffineRowsPerBlock,
    cudaAffineThreadsPerBlock] at outer inner ⊢
  omega

/-- Decoded stripe/thread coordinates lie inside the literal 256-by-256
tile. -/
theorem cudaAffineLaunchRow_decode_bounds (index : Nat) :
    cudaAffineRowStripe index < cudaAffineRowsPerThread ∧
    cudaAffineRowThread index < cudaAffineThreadsPerBlock := by
  have localBound :=
    Nat.mod_lt index
      (show 0 < cudaAffineRowsPerBlock by
        norm_num [cudaAffineRowsPerBlock])
  have threadBound :=
    Nat.mod_lt (cudaAffineRowLocal index)
      (show 0 < cudaAffineThreadsPerBlock by
        norm_num [cudaAffineThreadsPerBlock])
  constructor
  · rw [cudaAffineRowStripe,
      Nat.div_lt_iff_lt_mul (by
        norm_num [cudaAffineThreadsPerBlock])]
    norm_num [cudaAffineRowLocal, cudaAffineRowsPerBlock,
      cudaAffineRowsPerThread, cudaAffineThreadsPerBlock] at *
    exact localBound
  · exact threadBound

/-- A live row's decoded block is inside the ceiling-divided launch grid. -/
theorem cudaAffineRowBlock_lt_summaryCount
    {index count : Nat} (live : index < count) :
    cudaAffineRowBlock index < cudaAffineSummaryCount count := by
  have countPositive : count ≠ 0 := by omega
  have indexLe : index ≤ count - 1 := by omega
  have quotientLe :=
    Nat.div_le_div_right
      (c := cudaAffineRowsPerBlock) indexLe
  simp only [cudaAffineRowBlock, cudaAffineSummaryCount,
    countPositive, if_false]
  omega

/-- The public `10^8`-row leaf limit emits at most 1,526 block summaries. -/
theorem cudaAffineSummaryCount_le_1526
    {count : Nat} (countBound : count ≤ 100_000_000) :
    cudaAffineSummaryCount count ≤ 1_526 := by
  cases count with
  | zero =>
      simp [cudaAffineSummaryCount]
  | succ count =>
      have quotientBound :
          count / cudaAffineRowsPerBlock < 1_526 := by
        rw [Nat.div_lt_iff_lt_mul
          (show 0 < cudaAffineRowsPerBlock by
            norm_num [cudaAffineRowsPerBlock])]
        norm_num [cudaAffineRowsPerBlock] at countBound ⊢
        omega
      simp only [cudaAffineSummaryCount, Nat.succ_ne_zero,
        if_false, Nat.succ_sub_one]
      omega

/-- Valid tile coordinates have a unique global source row. -/
theorem cudaAffineLaunchRow_injective
    {firstBlock firstStripe firstThread
      secondBlock secondStripe secondThread : Nat}
    (firstStripeBound :
      firstStripe < cudaAffineRowsPerThread)
    (secondStripeBound :
      secondStripe < cudaAffineRowsPerThread)
    (firstThreadBound :
      firstThread < cudaAffineThreadsPerBlock)
    (secondThreadBound :
      secondThread < cudaAffineThreadsPerBlock)
    (sameRow :
      cudaAffineLaunchRow firstBlock firstStripe firstThread =
        cudaAffineLaunchRow
          secondBlock secondStripe secondThread) :
    firstBlock = secondBlock ∧
      firstStripe = secondStripe ∧
      firstThread = secondThread := by
  norm_num [cudaAffineLaunchRow, cudaAffineRowsPerBlock,
    cudaAffineRowsPerThread, cudaAffineThreadsPerBlock] at *
  omega

/-- Every decoded live row index, and its doubled endpoint source order, fits
`uint32_t` under the public leaf bound. -/
theorem cudaAffineLaunchIndex_and_order_fit_uint32
    {index count endpoint : Nat}
    (live : index < count)
    (countBound : count ≤ 100_000_000)
    (endpointBound : endpoint ≤ 1) :
    cudaAffineLaunchRow
        (cudaAffineRowBlock index)
        (cudaAffineRowStripe index)
        (cudaAffineRowThread index) < 2 ^ 32 ∧
      2 * index + endpoint < 2 ^ 32 := by
  rw [cudaAffineLaunchRow_decode]
  norm_num at countBound ⊢
  omega

/-! ## The 256 carried CUB stripes inside one block -/

/-- Source-level form of the summary kernel's stripe loop.  Each stripe scans
at most `stripeSize` rows from the current running delta, then hands its exact
total to the next stripe. -/
def stripedInputScanFrom (stripeSize : Nat) :
    Nat → PrefixMQ → List PrefixMQ → List PrefixMQ
  | 0, _, _ => []
  | stripes + 1, incoming, rows =>
      let stripe := rows.take stripeSize
      inputScanFrom incoming stripe ++
        stripedInputScanFrom stripeSize stripes
          (incoming + inputTotal stripe)
          (rows.drop stripeSize)

/-- Repeated carried stripe scans are exactly one ordinary scan whenever the
declared stripe capacity covers the rows.  This includes a partial final
stripe and any number of trailing empty stripes. -/
theorem stripedInputScanFrom_eq_inputScanFrom
    (stripeSize stripes : Nat) (incoming : PrefixMQ)
    (rows : List PrefixMQ)
    (capacity : rows.length ≤ stripes * stripeSize) :
    stripedInputScanFrom stripeSize stripes incoming rows =
      inputScanFrom incoming rows := by
  induction stripes generalizing incoming rows with
  | zero =>
      simp only [Nat.zero_mul] at capacity
      have empty : rows = [] := List.eq_nil_of_length_eq_zero
        (Nat.eq_zero_of_le_zero capacity)
      simp [empty, stripedInputScanFrom, inputScanFrom]
  | succ stripes inductionHypothesis =>
      simp only [stripedInputScanFrom]
      rw [inductionHypothesis]
      · rw [← inputScanFrom_append]
        exact congrArg (inputScanFrom incoming)
          (List.take_append_drop stripeSize rows)
      · rw [List.length_drop, Nat.succ_mul] at *
        omega

/-- One CUDA block's 256 carried scans of 256 rows are exactly the ordinary
inclusive scan over its at-most-65,536-row tile.  Only refinement of an actual
CUB `BlockScan` instruction to `inputScanFrom` remains external. -/
theorem cudaBlockStripedScan_eq_inclusiveInputScan
    (rows : List PrefixMQ)
    (tileBound : rows.length ≤ cudaAffineRowsPerBlock) :
    stripedInputScanFrom cudaAffineThreadsPerBlock
        cudaAffineRowsPerThread PrefixMQ.zero rows =
      inclusiveInputScan rows := by
  apply stripedInputScanFrom_eq_inputScanFrom
  simpa [cudaAffineRowsPerBlock, cudaAffineRowsPerThread,
    cudaAffineThreadsPerBlock] using tileBound

/-- The source-shaped CUDA tiling convention.  `fullTiles` contains all full
blocks; `finalTile` is the possibly empty remainder. -/
def CudaTileShape
    (fullTiles : List (List PrefixMQ)) (finalTile : List PrefixMQ) : Prop :=
  (∀ tile ∈ fullTiles, tile.length = cudaAffineRowsPerBlock) ∧
    finalTile.length < cudaAffineRowsPerBlock

/-- A row tile regarded as a zero-proxy worker summary input. -/
def tileWorker (rows : List PrefixMQ) : WorkerChunk :=
  { rows := rows
    proxy := PrefixMQ.zero }

/-- Consecutive full tiles followed by the nonempty partial final tile.  An
empty final tile is omitted, exactly as in the CUDA grid calculation. -/
def cudaTileWorkers
    (fullTiles : List (List PrefixMQ))
    (finalTile : List PrefixMQ) : List WorkerChunk :=
  fullTiles.map tileWorker ++
    if finalTile = [] then [] else [tileWorker finalTile]

/-- The CUDA tile list covers exactly the original consecutive row list,
including both a partial final block and an exact multiple of 65,536. -/
theorem workerRows_cudaTileWorkers
    (fullTiles : List (List PrefixMQ))
    (finalTile : List PrefixMQ) :
    workerRows (cudaTileWorkers fullTiles finalTile) =
      fullTiles.flatten ++ finalTile := by
  simp only [cudaTileWorkers, workerRows, List.map_append,
    List.flatten_append, List.map_map]
  have mappedRows :
      List.map (WorkerChunk.rows ∘ tileWorker) fullTiles =
        fullTiles := by
    simp [Function.comp_def, tileWorker]
  rw [mappedRows]
  split
  · rename_i empty
    simp [empty]
  · simp [tileWorker]

/-- Installing a preceding tile changes an affine value by the negative
coordinate of that tile's delta.  Because the local block was generated with
absolute `sourceOffset` orders, `rowShift = 0`: global source order, and hence
earliest-source tie breaking, is unchanged. -/
theorem rightTile_translation_has_negative_sign_and_global_order
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (base : Nat → Int) (endpoint sourceOffset : Nat)
    (leftDelta : PrefixMQ) (rightRows : List PrefixMQ) :
    (affineCandidatesFrom coordinate base endpoint
        sourceOffset sourceOffset PrefixMQ.zero rightRows).map
        (shiftCandidate (-coordinate leftDelta) 0) =
      affineCandidatesFrom coordinate base endpoint
        sourceOffset sourceOffset leftDelta rightRows := by
  simpa [additive.1] using
    affineCandidatesFrom_translate additive base endpoint
      sourceOffset sourceOffset leftDelta PrefixMQ.zero 0 rightRows

/-- The source-shaped two-tile equation used by the CUDA composer.  The right
summary starts from zero, receives the negative left-delta value translation,
and keeps its already-global candidate orders. -/
theorem adjacentTileCandidates_eq_perRowCandidates
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (base : Nat → Int) (endpoint sourceOffset orderOffset : Nat)
    (leftRows rightRows : List PrefixMQ) :
    affineCandidatesFrom coordinate base endpoint
        sourceOffset orderOffset PrefixMQ.zero leftRows ++
      (affineCandidatesFrom coordinate base endpoint
          (sourceOffset + leftRows.length)
          (orderOffset + leftRows.length)
          PrefixMQ.zero rightRows).map
        (shiftCandidate (-coordinate (inputTotal leftRows)) 0) =
      affineCandidatesFrom coordinate base endpoint
        sourceOffset orderOffset PrefixMQ.zero
        (leftRows ++ rightRows) := by
  rw [affineCandidatesFrom_append]
  congr 1
  simpa [additive.1] using
    affineCandidatesFrom_translate additive base endpoint
      (sourceOffset + leftRows.length)
      (orderOffset + leftRows.length)
      (inputTotal leftRows) PrefixMQ.zero 0 rightRows

/-- Ordered 65,536-row CUDA block composition is exactly the ordinary
per-row inclusive scan and deterministic reduction.  Equality is equality of
the complete `OrderedCandidate`, so the source-order component used to break
equal-value ties is preserved, not merely the extremal value.

`shape` explicitly admits the shorter final tile.  The arithmetic proof is
stronger: it works for any consecutive partition, so the shape hypothesis is
needed only to identify this specialization with the CUDA launch geometry. -/
theorem cudaOrderedTileComposition_eq_perRowInclusiveScan
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat)
    (fullTiles : List (List PrefixMQ))
    (finalTile : List PrefixMQ)
    (_shape : CudaTileShape fullTiles finalTile) :
    let workers := cudaTileWorkers fullTiles finalTile
    composeWorkerMaximum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMaximum
          (rowCandidates
            (fun index pfx => lowerBase index - coordinate pfx)
            lowerEndpoint
            (inclusiveInputScan (fullTiles.flatten ++ finalTile))) ∧
      composeWorkerMinimum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMinimum
          (rowCandidates
            (fun index pfx => upperBase index - coordinate pfx)
            upperEndpoint
            (inclusiveInputScan (fullTiles.flatten ++ finalTile))) := by
  dsimp only
  have composed :=
    nWorkerComposition_eq_inclusiveInputScan additive
      lowerBase upperBase lowerEndpoint upperEndpoint
      (cudaTileWorkers fullTiles finalTile)
  simpa [workerRows_cudaTileWorkers] using composed

/-- The composed terminal delta is also the exact total of every full block
and the partial final block. -/
theorem cudaOrderedTileFinalDelta_eq_perRowTotal
    (fullTiles : List (List PrefixMQ))
    (finalTile : List PrefixMQ) :
    workerFinalState PrefixMQ.zero
        (cudaTileWorkers fullTiles finalTile) =
      inputTotal (fullTiles.flatten ++ finalTile) := by
  rw [workerFinalState_eq_handoff_add_total,
    workerRows_cudaTileWorkers]
  exact PrefixMQ.zero_add _

/-! ## Fixed-width arithmetic used by the CUDA representation -/

/-- Mathematical range represented by a native signed 64-bit candidate
field. -/
def FitsInt64 (value : Int) : Prop :=
  -(2 ^ 63 : Int) ≤ value ∧ value < 2 ^ 63

/-- Every exact tile or cumulative leaf delta fits the native
`int32_t`/`uint32_t` pair when the row stream is valid and has at most
`10^8` rows. -/
theorem cudaTileDelta_fits_int32_uint32
    {rows : List PrefixMQ}
    (valid : PrefixInputRowsValid rows)
    (rowCountBound : rows.length ≤ maximumSegmentRows) :
    PrefixFitsMachineWords (inputTotal rows) := by
  simpa [inputPrefixAt] using
    inputPrefixAt_fits_machine_words
      valid rowCountBound rows.length

/-- The exact Hurst/Mertens candidate operation

`(base - localPrefix.mertens) - precedingDelta.mertens`

fits signed 64 bits.  This is the operation performed when a zero-state tile
candidate is translated by the negative preceding delta. -/
theorem translatedMertensCandidate_fits_int64
    {base : Int} {localRows precedingRows : List PrefixMQ}
    (baseLower : -(sourceLimit : Int) ≤ base)
    (baseUpper : base ≤ sourceLimit)
    (localValid : PrefixInputRowsValid localRows)
    (precedingValid : PrefixInputRowsValid precedingRows)
    (localCount : localRows.length ≤ maximumSegmentRows)
    (precedingCount : precedingRows.length ≤ maximumSegmentRows) :
    FitsInt64
      ((base - (inputTotal localRows).mertens) -
        (inputTotal precedingRows).mertens) := by
  have localFits :=
    cudaTileDelta_fits_int32_uint32 localValid localCount
  have precedingFits :=
    cudaTileDelta_fits_int32_uint32 precedingValid precedingCount
  unfold FitsInt64 PrefixFitsMachineWords at *
  norm_num [sourceLimit, maximumSegmentRows] at *
  omega

/-- The corresponding translated squarefree candidate

`(base - localPrefix.squarefree) - precedingDelta.squarefree`

also fits signed 64 bits.  The retained witness adds the two squarefree
prefixes in `uint32_t`; applying `cudaTileDelta_fits_int32_uint32` to their
concatenation proves that final sum lossless. -/
theorem translatedSquarefreeCandidate_fits_int64
    {base : Int} {localRows precedingRows : List PrefixMQ}
    (baseLower : -(sourceLimit : Int) ≤ base)
    (baseUpper : base ≤ sourceLimit)
    (localValid : PrefixInputRowsValid localRows)
    (precedingValid : PrefixInputRowsValid precedingRows)
    (localCount : localRows.length ≤ maximumSegmentRows)
    (precedingCount : precedingRows.length ≤ maximumSegmentRows) :
    FitsInt64
      ((base - ((inputTotal localRows).squarefree : Int)) -
        ((inputTotal precedingRows).squarefree : Int)) := by
  have localFits :=
    cudaTileDelta_fits_int32_uint32 localValid localCount
  have precedingFits :=
    cudaTileDelta_fits_int32_uint32 precedingValid precedingCount
  let localSquarefree : Int :=
    ((inputTotal localRows).squarefree : Int)
  let precedingSquarefree : Int :=
    ((inputTotal precedingRows).squarefree : Int)
  change FitsInt64
    ((base - localSquarefree) - precedingSquarefree)
  have localNonnegative : (0 : Int) ≤ localSquarefree := by
    simpa [localSquarefree] using
      Int.natCast_nonneg (inputTotal localRows).squarefree
  have precedingNonnegative : (0 : Int) ≤ precedingSquarefree := by
    simpa [precedingSquarefree] using
      Int.natCast_nonneg (inputTotal precedingRows).squarefree
  have localUpper : localSquarefree < (2 ^ 32 : Int) := by
    have castUpper :
        ((inputTotal localRows).squarefree : Int) <
          (2 ^ 32 : Int) := by
      exact_mod_cast localFits.2.2
    simpa [localSquarefree] using castUpper
  have precedingUpper :
      precedingSquarefree < (2 ^ 32 : Int) := by
    have castUpper :
        ((inputTotal precedingRows).squarefree : Int) <
          (2 ^ 32 : Int) := by
      exact_mod_cast precedingFits.2.2
    simpa [precedingSquarefree] using castUpper
  unfold FitsInt64
  norm_num [sourceLimit] at baseLower baseUpper
  norm_num at localUpper precedingUpper ⊢
  omega

/-- Adding the local squarefree witness to the preceding cumulative witness
is still a lossless `uint32_t` value whenever their concatenated leaf has at
most `10^8` valid rows. -/
theorem translatedSquarefreeWitness_fits_uint32
    {precedingRows localRows : List PrefixMQ}
    (valid : PrefixInputRowsValid (precedingRows ++ localRows))
    (rowCountBound :
      (precedingRows ++ localRows).length ≤ maximumSegmentRows) :
    (inputTotal precedingRows).squarefree +
        (inputTotal localRows).squarefree < 2 ^ 32 := by
  have totalFits :=
    cudaTileDelta_fits_int32_uint32 valid rowCountBound
  rw [inputTotal_append] at totalFits
  exact totalFits.2.2

/-! ## The 256-thread ordered summary finalizer

The native finalizer first gives each of 256 threads one consecutive chunk of
summaries, then combines adjacent thread slots at spans
`1, 2, 4, ..., 128`.  The following noncommutative product model makes the
ordering requirement explicit.  It does not assume commutativity. -/

def cudaSummaryThreads : Nat := 256

/-- Native ceiling division used to assign consecutive summaries to each
thread. -/
def cudaSummariesPerThread (summaryCount : Nat) : Nat :=
  if summaryCount = 0 then 0
  else 1 + (summaryCount - 1) / cudaSummaryThreads

def cudaSummaryThreadBegin
    (summaryCount thread : Nat) : Nat :=
  thread * cudaSummariesPerThread summaryCount

def cudaSummaryThreadEnd
    (summaryCount thread : Nat) : Nat :=
  min
    (cudaSummaryThreadBegin summaryCount thread +
      cudaSummariesPerThread summaryCount)
    summaryCount

def cudaSummaryThreadOwns
    (summaryCount thread summaryIndex : Nat) : Prop :=
  cudaSummaryThreadBegin summaryCount thread ≤ summaryIndex ∧
    summaryIndex < cudaSummaryThreadEnd summaryCount thread

/-- The literal summary-count, ceiling-division, thread-begin, and thread-end
arithmetic stays far inside `uint32_t` at the public 100-million-row leaf
cap.  In particular, no thread receives more than six summaries and the
largest unreduced `thread * summariesPerThread` address is below 1,536.

This closes the fixed-width arithmetic side of the native 256-thread summary
coverage argument.  Identifying CUDA registers and instructions with these
natural-number expressions remains part of the compiler/execution boundary. -/
theorem cudaSummaryThread_machine_bounds
    {count thread : Nat}
    (countBound : count ≤ maximumSegmentRows)
    (threadBound : thread < cudaSummaryThreads) :
    cudaAffineSummaryCount count ≤ 1_526 ∧
      cudaSummariesPerThread (cudaAffineSummaryCount count) ≤ 6 ∧
      cudaSummaryThreadBegin
          (cudaAffineSummaryCount count) thread < 1_536 ∧
      cudaSummaryThreadEnd
          (cudaAffineSummaryCount count) thread ≤ 1_526 ∧
      cudaSummaryThreadBegin
          (cudaAffineSummaryCount count) thread < 2 ^ 32 ∧
      cudaSummaryThreadEnd
          (cudaAffineSummaryCount count) thread < 2 ^ 32 := by
  have summaryBound :
      cudaAffineSummaryCount count ≤ 1_526 := by
    apply cudaAffineSummaryCount_le_1526
    simpa [maximumSegmentRows] using countBound
  have perThreadBound :
      cudaSummariesPerThread
          (cudaAffineSummaryCount count) ≤ 6 := by
    cases summaryEquation :
        cudaAffineSummaryCount count with
    | zero =>
        simp [cudaSummariesPerThread]
    | succ summaries =>
        have summariesBound : summaries ≤ 1_525 := by
          omega
        have quotientBound :
            summaries / cudaSummaryThreads < 6 := by
          rw [Nat.div_lt_iff_lt_mul
            (show 0 < cudaSummaryThreads by
              norm_num [cudaSummaryThreads])]
          norm_num [cudaSummaryThreads]
          omega
        simp only [cudaSummariesPerThread, Nat.succ_ne_zero,
          if_false, Nat.succ_sub_one]
        omega
  have beginBound :
      cudaSummaryThreadBegin
          (cudaAffineSummaryCount count) thread < 1_536 := by
    unfold cudaSummaryThreadBegin
    have productBound :=
      Nat.mul_lt_mul_of_lt_of_le
        threadBound perThreadBound (by norm_num : 0 < 6)
    norm_num [cudaSummaryThreads] at productBound
    exact productBound
  have endBound :
      cudaSummaryThreadEnd
          (cudaAffineSummaryCount count) thread ≤ 1_526 := by
    exact (Nat.min_le_right _ _).trans summaryBound
  refine ⟨summaryBound, perThreadBound, beginBound, endBound, ?_, ?_⟩
  · norm_num at beginBound ⊢
    omega
  · norm_num at endBound ⊢
    omega

/-- The critical launch crossover is literal arithmetic: 255 and 256
summaries give each active thread one item, while 257 gives two-item chunks.
-/
theorem summaryThreadCrossover_255_256_257 :
    cudaSummariesPerThread 255 = 1 ∧
    cudaSummariesPerThread 256 = 1 ∧
    cudaSummariesPerThread 257 = 2 := by
  norm_num [cudaSummariesPerThread, cudaSummaryThreads]

/-- At the 257-summary crossover, thread 128 owns exactly the partial final
chunk containing global summary 256, and thread 129 is already empty. -/
theorem summaryCount257_partialFinalThread :
    cudaSummaryThreadOwns 257 128 256 ∧
    ¬cudaSummaryThreadOwns 257 128 255 ∧
    ¬cudaSummaryThreadOwns 257 129 256 := by
  norm_num [cudaSummaryThreadOwns, cudaSummaryThreadBegin,
    cudaSummaryThreadEnd, cudaSummariesPerThread,
    cudaSummaryThreads]

/-- One abstract span-doubling round combines adjacent entries in their
existing left-to-right order. -/
def adjacentOrderedProducts {α : Type} [Mul α] : List α → List α
  | [] => []
  | [item] => [item]
  | left :: right :: rest =>
      (left * right) :: adjacentOrderedProducts rest

/-- An adjacent round preserves the ordered product for any associative
operation with identity.  No commutativity assumption appears. -/
theorem prod_adjacentOrderedProducts
    {α : Type} [Monoid α] (items : List α) :
    (adjacentOrderedProducts items).prod = items.prod := by
  induction items using List.twoStepInduction with
  | nil => rfl
  | singleton item => simp [adjacentOrderedProducts]
  | cons_cons left right rest inductionHypothesis =>
      simp only [adjacentOrderedProducts, List.prod_cons,
        inductionHypothesis]
      exact mul_assoc _ _ _

/-- Repeated adjacent span-doubling rounds.  The CUDA implementation performs
eight rounds for its 256 shared-memory thread slots. -/
def orderedTreeRounds {α : Type} [Mul α] :
    Nat → List α → List α
  | 0, items => items
  | rounds + 1, items =>
      orderedTreeRounds rounds (adjacentOrderedProducts items)

theorem prod_orderedTreeRounds
    {α : Type} [Monoid α] (rounds : Nat) (items : List α) :
    (orderedTreeRounds rounds items).prod = items.prod := by
  induction rounds generalizing items with
  | zero => rfl
  | succ rounds inductionHypothesis =>
      rw [orderedTreeRounds, inductionHypothesis,
        prod_adjacentOrderedProducts]

/-- Consume `threads` consecutive `take size`/`drop size` slices.  This is the
list-level form of native thread `t` starting at `t * size`.  Empty trailing
thread slots remain explicit empty chunks and hence contribute the identity.
-/
def consecutiveThreadChunks {α : Type} (size : Nat) :
    Nat → List α → List (List α)
  | 0, _ => []
  | threads + 1, items =>
      items.take size ::
        consecutiveThreadChunks size threads (items.drop size)

@[simp] theorem consecutiveThreadChunks_length
    {α : Type} (size threads : Nat) (items : List α) :
    (consecutiveThreadChunks size threads items).length = threads := by
  induction threads generalizing items with
  | zero => rfl
  | succ threads inductionHypothesis =>
      simp [consecutiveThreadChunks, inductionHypothesis]

/-- Thread `t` receives literally the slice beginning at `t * size`. -/
theorem consecutiveThreadChunks_getElem
    {α : Type} (size threads : Nat) (items : List α)
    (thread : Nat) (inRange : thread < threads) :
    (consecutiveThreadChunks size threads items)[thread]'(by
      simpa using inRange) =
      (items.drop (thread * size)).take size := by
  induction threads generalizing items thread with
  | zero => simp at inRange
  | succ threads inductionHypothesis =>
      cases thread with
      | zero =>
          simp [consecutiveThreadChunks]
      | succ thread =>
          simp only [Nat.succ_lt_succ_iff] at inRange
          simp only [consecutiveThreadChunks,
            List.getElem_cons_succ]
          rw [inductionHypothesis (items.drop size)
            thread inRange]
          rw [List.drop_drop]
          congr 2
          simp [Nat.succ_mul, Nat.add_comm]

/-- A fixed number of consecutive take/drop chunks covers the input whenever
its aggregate capacity is sufficient. -/
theorem flatten_consecutiveThreadChunks
    {α : Type} (size threads : Nat) (items : List α)
    (capacity : items.length ≤ threads * size) :
    (consecutiveThreadChunks size threads items).flatten = items := by
  induction threads generalizing items with
  | zero =>
      simp only [Nat.zero_mul] at capacity
      have empty : items = [] := List.eq_nil_of_length_eq_zero
        (Nat.eq_zero_of_le_zero capacity)
      simp [empty, consecutiveThreadChunks]
  | succ threads inductionHypothesis =>
      simp only [consecutiveThreadChunks, List.flatten_cons]
      rw [inductionHypothesis]
      · exact List.take_append_drop size items
      · rw [List.length_drop, Nat.succ_mul] at *
        omega

/-- Ceiling assignment to 256 threads always has enough aggregate slots. -/
theorem summaryCount_le_threadCapacity (summaryCount : Nat) :
    summaryCount ≤
      cudaSummaryThreads *
        cudaSummariesPerThread summaryCount := by
  cases summaryCount with
  | zero =>
      simp [cudaSummariesPerThread]
  | succ count =>
      have division :=
        Nat.div_add_mod count cudaSummaryThreads
      have remainder :=
        Nat.mod_lt count
          (show 0 < cudaSummaryThreads by
            norm_num [cudaSummaryThreads])
      simp only [cudaSummariesPerThread, Nat.succ_ne_zero,
        if_false, Nat.succ_sub_one]
      norm_num [cudaSummaryThreads] at division remainder ⊢
      omega

/-- The actual 256 source-index chunks extracted by the CUDA begin/end
formula, padded by empty chunks after the source summaries are exhausted. -/
def cudaExtractedThreadChunks {α : Type}
    (summaries : List α) : List (List α) :=
  consecutiveThreadChunks
    (cudaSummariesPerThread summaries.length)
    cudaSummaryThreads summaries

/-- The 256 extracted take/drop slices cover every summary exactly once and
in source order. -/
theorem cudaExtractedThreadChunks_cover
    {α : Type} (summaries : List α) :
    (cudaExtractedThreadChunks summaries).flatten = summaries := by
  apply flatten_consecutiveThreadChunks
  simpa [Nat.mul_comm] using
    summaryCount_le_threadCapacity summaries.length

/-- Conditional algebraic form, useful for auditing any independently
defined chunk extraction. -/
theorem conditionalThreadChunksAndTree_refine_orderedFold
    {α : Type} [Monoid α]
    (summaries : List α) (threadChunks : List (List α))
    (cover : threadChunks.flatten = summaries) :
    (orderedTreeRounds 8
      (threadChunks.map List.prod)).prod = summaries.prod := by
  rw [prod_orderedTreeRounds, ← List.prod_flatten, cover]

/-- The concrete 256-thread extraction followed by the eight native adjacent
tree rounds equals the original noncommutative ordered fold.  This discharges
the source-level chunk-coverage premise; identifying compiled CUDA indexes
and instructions with these definitions remains the executable refinement
boundary tested by the native KAT. -/
theorem cudaExtractedChunksAndTree_refine_orderedFold
    {α : Type} [Monoid α] (summaries : List α) :
    (orderedTreeRounds 8
      ((cudaExtractedThreadChunks summaries).map List.prod)).prod =
        summaries.prod := by
  exact conditionalThreadChunksAndTree_refine_orderedFold
    summaries (cudaExtractedThreadChunks summaries)
    (cudaExtractedThreadChunks_cover summaries)

/-! ## Concrete affine `{M,Q}` block summaries

The preceding tree theorem deliberately works for an arbitrary monoid.  This
section supplies the concrete, noncommutative monoid used by
`TgMobiusAffineMqBlockSummary`.

Unlike `OrderedCandidate`, the native candidate carries an additional
squarefree-prefix witness.  The witness is retained with the winning
candidate but is deliberately absent from the comparison key: extrema compare
the exact value first and the global source order second.  Consequently two
candidates with equal value and order but different witnesses retain the
left-hand candidate, just as the ordered native fold does.
-/

/-- Source semantics of `TgMobiusAffineMqBoundCandidate`.  A native empty
sentinel is represented by `none` in the summary below, so every value of this
structure denotes a real candidate. -/
structure CudaAffineMqBoundCandidate where
  value : Int
  localSquarefree : Nat
  order : Nat
  deriving Repr, DecidableEq

@[ext] theorem CudaAffineMqBoundCandidate.ext
    {left right : CudaAffineMqBoundCandidate}
    (value : left.value = right.value)
    (localSquarefree :
      left.localSquarefree = right.localSquarefree)
    (order : left.order = right.order) :
    left = right := by
  rcases left with ⟨leftValue, leftSquarefree, leftOrder⟩
  rcases right with ⟨rightValue, rightSquarefree, rightOrder⟩
  simp_all

/-- Erase the retained squarefree witness when forming the deterministic
extremum key. -/
def CudaAffineMqBoundCandidate.ordered
    (candidate : CudaAffineMqBoundCandidate) : OrderedCandidate :=
  { value := candidate.value
    order := candidate.order }

/-- Maximum/earliest key used by `hurst_lower` and `squarefree_lower`. -/
def cudaAffineMaximumKey
    (candidate : CudaAffineMqBoundCandidate) : Int ×ₗ Nat :=
  lowerKey candidate.ordered

/-- Minimum/earliest key used by `hurst_upper` and `squarefree_upper`. -/
def cudaAffineMinimumKey
    (candidate : CudaAffineMqBoundCandidate) : Int ×ₗ Nat :=
  upperKey candidate.ordered

/-- Left-biased minimum by a linearly ordered key.  Left bias matters only
when the compared keys are identical; it models the native source-ordered
fold even though the retained witness is not part of the key. -/
def chooseByKey {α κ : Type} [LinearOrder κ]
    (key : α → κ) (left right : α) : α :=
  if key left ≤ key right then left else right

theorem chooseByKey_assoc {α κ : Type} [LinearOrder κ]
    (key : α → κ) (first second third : α) :
    chooseByKey key (chooseByKey key first second) third =
      chooseByKey key first (chooseByKey key second third) := by
  unfold chooseByKey
  by_cases firstSecond : key first ≤ key second
  · by_cases secondThird : key second ≤ key third
    · have firstThird : key first ≤ key third :=
        firstSecond.trans secondThird
      simp [firstSecond, secondThird, firstThird]
    · simp [firstSecond, secondThird]
  · by_cases secondThird : key second ≤ key third
    · simp [firstSecond, secondThird]
    · have thirdFirst : key third < key first :=
        (lt_of_not_ge secondThird).trans
          (lt_of_not_ge firstSecond)
      have firstThird : ¬key first ≤ key third :=
        not_le.mpr thirdFirst
      simp [firstSecond, secondThird, firstThird]

/-- Optional deterministic reduction.  `none` is the exact semantic
replacement for the native maximum/minimum sentinels. -/
def mergeOptionalByKey {α κ : Type} [LinearOrder κ]
    (key : α → κ) : Option α → Option α → Option α
  | none, right => right
  | left, none => left
  | some left, some right => some (chooseByKey key left right)

theorem mergeOptionalByKey_assoc
    {α κ : Type} [LinearOrder κ]
    (key : α → κ) (first second third : Option α) :
    mergeOptionalByKey key
        (mergeOptionalByKey key first second) third =
      mergeOptionalByKey key first
        (mergeOptionalByKey key second third) := by
  cases first <;> cases second <;> cases third <;>
    simp [mergeOptionalByKey, chooseByKey_assoc]

def mergeCudaAffineMaximum :
    Option CudaAffineMqBoundCandidate →
      Option CudaAffineMqBoundCandidate →
        Option CudaAffineMqBoundCandidate :=
  mergeOptionalByKey cudaAffineMaximumKey

def mergeCudaAffineMinimum :
    Option CudaAffineMqBoundCandidate →
      Option CudaAffineMqBoundCandidate →
        Option CudaAffineMqBoundCandidate :=
  mergeOptionalByKey cudaAffineMinimumKey

theorem mergeCudaAffineMaximum_assoc
    (first second third : Option CudaAffineMqBoundCandidate) :
    mergeCudaAffineMaximum
        (mergeCudaAffineMaximum first second) third =
      mergeCudaAffineMaximum first
        (mergeCudaAffineMaximum second third) := by
  exact mergeOptionalByKey_assoc cudaAffineMaximumKey
    first second third

theorem mergeCudaAffineMinimum_assoc
    (first second third : Option CudaAffineMqBoundCandidate) :
    mergeCudaAffineMinimum
        (mergeCudaAffineMinimum first second) third =
      mergeCudaAffineMinimum first
        (mergeCudaAffineMinimum second third) := by
  exact mergeOptionalByKey_assoc cudaAffineMinimumKey
    first second third

/-- Common candidate translation.  `valueShift` affects comparison;
`squarefreeShift` affects only the retained prefix witness; global source
order is unchanged. -/
def translateCudaAffineCandidate
    (valueShift : Int) (squarefreeShift : Nat)
    (candidate : CudaAffineMqBoundCandidate) :
    CudaAffineMqBoundCandidate :=
  { value := candidate.value + valueShift
    localSquarefree :=
      candidate.localSquarefree + squarefreeShift
    order := candidate.order }

/-- Prefixing a zero-based tile by `delta` subtracts its Mertens coordinate
from a Hurst candidate.  The Hurst candidate's unused squarefree field stays
unchanged. -/
def translateCudaHurstCandidate
    (delta : PrefixMQ) (candidate : CudaAffineMqBoundCandidate) :
    CudaAffineMqBoundCandidate :=
  translateCudaAffineCandidate (-delta.mertens) 0 candidate

/-- Prefixing a zero-based tile by `delta` subtracts its squarefree
coordinate from the value and adds that coordinate to the retained
squarefree-prefix witness. -/
def translateCudaSquarefreeCandidate
    (delta : PrefixMQ) (candidate : CudaAffineMqBoundCandidate) :
    CudaAffineMqBoundCandidate :=
  translateCudaAffineCandidate
    (-((delta.squarefree : Nat) : Int)) delta.squarefree candidate

@[simp] theorem translateCudaAffineCandidate_order
    (valueShift : Int) (squarefreeShift : Nat)
    (candidate : CudaAffineMqBoundCandidate) :
    (translateCudaAffineCandidate valueShift squarefreeShift
      candidate).order = candidate.order := rfl

@[simp] theorem translateCudaHurstCandidate_zero
    (candidate : CudaAffineMqBoundCandidate) :
    translateCudaHurstCandidate PrefixMQ.zero candidate =
      candidate := by
  rcases candidate with ⟨value, localSquarefree, order⟩
  simp [translateCudaHurstCandidate,
    translateCudaAffineCandidate]

@[simp] theorem translateCudaSquarefreeCandidate_zero
    (candidate : CudaAffineMqBoundCandidate) :
    translateCudaSquarefreeCandidate PrefixMQ.zero candidate =
      candidate := by
  rcases candidate with ⟨value, localSquarefree, order⟩
  simp [translateCudaSquarefreeCandidate,
    translateCudaAffineCandidate]

theorem translateCudaHurstCandidate_add
    (left right : PrefixMQ)
    (candidate : CudaAffineMqBoundCandidate) :
    translateCudaHurstCandidate (left + right) candidate =
      translateCudaHurstCandidate left
        (translateCudaHurstCandidate right candidate) := by
  rcases left with ⟨leftMertens, leftSquarefree⟩
  rcases right with ⟨rightMertens, rightSquarefree⟩
  rcases candidate with ⟨value, localSquarefree, order⟩
  simp only [translateCudaHurstCandidate,
    translateCudaAffineCandidate, PrefixMQ.add_mertens,
    CudaAffineMqBoundCandidate.mk.injEq]
  constructor
  · ring
  constructor <;> simp

theorem translateCudaSquarefreeCandidate_add
    (left right : PrefixMQ)
    (candidate : CudaAffineMqBoundCandidate) :
    translateCudaSquarefreeCandidate (left + right) candidate =
      translateCudaSquarefreeCandidate left
        (translateCudaSquarefreeCandidate right candidate) := by
  rcases left with ⟨leftMertens, leftSquarefree⟩
  rcases right with ⟨rightMertens, rightSquarefree⟩
  rcases candidate with ⟨value, localSquarefree, order⟩
  simp only [translateCudaSquarefreeCandidate,
    translateCudaAffineCandidate, PrefixMQ.add_squarefree,
    CudaAffineMqBoundCandidate.mk.injEq]
  constructor
  · push_cast
    ring
  constructor
  · omega
  · trivial

theorem cudaAffineMaximumKey_translate_le_iff
    (valueShift : Int) (squarefreeShift : Nat)
    (left right : CudaAffineMqBoundCandidate) :
    cudaAffineMaximumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift left) ≤
        cudaAffineMaximumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift right) ↔
      cudaAffineMaximumKey left ≤ cudaAffineMaximumKey right := by
  simpa [cudaAffineMaximumKey,
    CudaAffineMqBoundCandidate.ordered,
    translateCudaAffineCandidate, shiftCandidate] using
      lowerKey_shift_le_iff valueShift 0
        left.ordered right.ordered

theorem cudaAffineMinimumKey_translate_le_iff
    (valueShift : Int) (squarefreeShift : Nat)
    (left right : CudaAffineMqBoundCandidate) :
    cudaAffineMinimumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift left) ≤
        cudaAffineMinimumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift right) ↔
      cudaAffineMinimumKey left ≤ cudaAffineMinimumKey right := by
  simpa [cudaAffineMinimumKey,
    CudaAffineMqBoundCandidate.ordered,
    translateCudaAffineCandidate, shiftCandidate] using
      upperKey_shift_le_iff valueShift 0
        left.ordered right.ordered

theorem translateCudaAffineCandidate_chooseMaximum
    (valueShift : Int) (squarefreeShift : Nat)
    (left right : CudaAffineMqBoundCandidate) :
    translateCudaAffineCandidate valueShift squarefreeShift
        (chooseByKey cudaAffineMaximumKey left right) =
      chooseByKey cudaAffineMaximumKey
        (translateCudaAffineCandidate valueShift squarefreeShift left)
        (translateCudaAffineCandidate valueShift squarefreeShift right) := by
  unfold chooseByKey
  by_cases comparison :
      cudaAffineMaximumKey left ≤ cudaAffineMaximumKey right
  · have shifted :=
      (cudaAffineMaximumKey_translate_le_iff
        valueShift squarefreeShift left right).mpr comparison
    simp [comparison, shifted]
  · have shifted :
      ¬cudaAffineMaximumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift left) ≤
        cudaAffineMaximumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift right) := by
      simpa [cudaAffineMaximumKey_translate_le_iff] using comparison
    simp [comparison, shifted]

theorem translateCudaAffineCandidate_chooseMinimum
    (valueShift : Int) (squarefreeShift : Nat)
    (left right : CudaAffineMqBoundCandidate) :
    translateCudaAffineCandidate valueShift squarefreeShift
        (chooseByKey cudaAffineMinimumKey left right) =
      chooseByKey cudaAffineMinimumKey
        (translateCudaAffineCandidate valueShift squarefreeShift left)
        (translateCudaAffineCandidate valueShift squarefreeShift right) := by
  unfold chooseByKey
  by_cases comparison :
      cudaAffineMinimumKey left ≤ cudaAffineMinimumKey right
  · have shifted :=
      (cudaAffineMinimumKey_translate_le_iff
        valueShift squarefreeShift left right).mpr comparison
    simp [comparison, shifted]
  · have shifted :
      ¬cudaAffineMinimumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift left) ≤
        cudaAffineMinimumKey
          (translateCudaAffineCandidate valueShift
            squarefreeShift right) := by
      simpa [cudaAffineMinimumKey_translate_le_iff] using comparison
    simp [comparison, shifted]

theorem Option.map_translate_mergeCudaAffineMaximum
    (valueShift : Int) (squarefreeShift : Nat)
    (left right : Option CudaAffineMqBoundCandidate) :
    Option.map
        (translateCudaAffineCandidate valueShift squarefreeShift)
        (mergeCudaAffineMaximum left right) =
      mergeCudaAffineMaximum
        (left.map
          (translateCudaAffineCandidate valueShift squarefreeShift))
        (right.map
          (translateCudaAffineCandidate valueShift squarefreeShift)) := by
  cases left <;> cases right <;>
    simp [mergeCudaAffineMaximum, mergeOptionalByKey,
      translateCudaAffineCandidate_chooseMaximum]

theorem Option.map_translate_mergeCudaAffineMinimum
    (valueShift : Int) (squarefreeShift : Nat)
    (left right : Option CudaAffineMqBoundCandidate) :
    Option.map
        (translateCudaAffineCandidate valueShift squarefreeShift)
        (mergeCudaAffineMinimum left right) =
      mergeCudaAffineMinimum
        (left.map
          (translateCudaAffineCandidate valueShift squarefreeShift))
        (right.map
          (translateCudaAffineCandidate valueShift squarefreeShift)) := by
  cases left <;> cases right <;>
    simp [mergeCudaAffineMinimum, mergeOptionalByKey,
      translateCudaAffineCandidate_chooseMinimum]

def translateCudaHurstOption
    (delta : PrefixMQ) :
    Option CudaAffineMqBoundCandidate →
      Option CudaAffineMqBoundCandidate :=
  Option.map (translateCudaHurstCandidate delta)

def translateCudaSquarefreeOption
    (delta : PrefixMQ) :
    Option CudaAffineMqBoundCandidate →
      Option CudaAffineMqBoundCandidate :=
  Option.map (translateCudaSquarefreeCandidate delta)

@[simp] theorem translateCudaHurstOption_zero
    (candidate : Option CudaAffineMqBoundCandidate) :
    translateCudaHurstOption PrefixMQ.zero candidate =
      candidate := by
  cases candidate <;> simp [translateCudaHurstOption]

@[simp] theorem translateCudaSquarefreeOption_zero
    (candidate : Option CudaAffineMqBoundCandidate) :
    translateCudaSquarefreeOption PrefixMQ.zero candidate =
      candidate := by
  cases candidate <;> simp [translateCudaSquarefreeOption]

theorem translateCudaHurstOption_add
    (left right : PrefixMQ)
    (candidate : Option CudaAffineMqBoundCandidate) :
    translateCudaHurstOption (left + right) candidate =
      translateCudaHurstOption left
        (translateCudaHurstOption right candidate) := by
  cases candidate <;>
    simp [translateCudaHurstOption,
      translateCudaHurstCandidate_add]

theorem translateCudaSquarefreeOption_add
    (left right : PrefixMQ)
    (candidate : Option CudaAffineMqBoundCandidate) :
    translateCudaSquarefreeOption (left + right) candidate =
      translateCudaSquarefreeOption left
        (translateCudaSquarefreeOption right candidate) := by
  cases candidate <;>
    simp [translateCudaSquarefreeOption,
      translateCudaSquarefreeCandidate_add]

theorem translateCudaHurstOption_mergeMaximum
    (delta : PrefixMQ)
    (left right : Option CudaAffineMqBoundCandidate) :
    translateCudaHurstOption delta
        (mergeCudaAffineMaximum left right) =
      mergeCudaAffineMaximum
        (translateCudaHurstOption delta left)
        (translateCudaHurstOption delta right) := by
  exact Option.map_translate_mergeCudaAffineMaximum
    (-delta.mertens) 0 left right

theorem translateCudaHurstOption_mergeMinimum
    (delta : PrefixMQ)
    (left right : Option CudaAffineMqBoundCandidate) :
    translateCudaHurstOption delta
        (mergeCudaAffineMinimum left right) =
      mergeCudaAffineMinimum
        (translateCudaHurstOption delta left)
        (translateCudaHurstOption delta right) := by
  exact Option.map_translate_mergeCudaAffineMinimum
    (-delta.mertens) 0 left right

theorem translateCudaSquarefreeOption_mergeMaximum
    (delta : PrefixMQ)
    (left right : Option CudaAffineMqBoundCandidate) :
    translateCudaSquarefreeOption delta
        (mergeCudaAffineMaximum left right) =
      mergeCudaAffineMaximum
        (translateCudaSquarefreeOption delta left)
        (translateCudaSquarefreeOption delta right) := by
  exact Option.map_translate_mergeCudaAffineMaximum
    (-((delta.squarefree : Nat) : Int)) delta.squarefree left right

theorem translateCudaSquarefreeOption_mergeMinimum
    (delta : PrefixMQ)
    (left right : Option CudaAffineMqBoundCandidate) :
    translateCudaSquarefreeOption delta
        (mergeCudaAffineMinimum left right) =
      mergeCudaAffineMinimum
        (translateCudaSquarefreeOption delta left)
        (translateCudaSquarefreeOption delta right) := by
  exact Option.map_translate_mergeCudaAffineMinimum
    (-((delta.squarefree : Nat) : Int)) delta.squarefree left right

/-- Exact source semantics of `TgMobiusAffineMqBlockSummary`: one tile delta
and four optional real candidates corresponding, in C layout order, to
`hurst_lower`, `hurst_upper`, `squarefree_lower`, and `squarefree_upper`. -/
structure CudaAffineMqBlockSummary where
  delta : PrefixMQ
  hurstLower : Option CudaAffineMqBoundCandidate
  hurstUpper : Option CudaAffineMqBoundCandidate
  squarefreeLower : Option CudaAffineMqBoundCandidate
  squarefreeUpper : Option CudaAffineMqBoundCandidate
  deriving Repr, DecidableEq

@[ext] theorem CudaAffineMqBlockSummary.ext
    {left right : CudaAffineMqBlockSummary}
    (delta : left.delta = right.delta)
    (hurstLower : left.hurstLower = right.hurstLower)
    (hurstUpper : left.hurstUpper = right.hurstUpper)
    (squarefreeLower :
      left.squarefreeLower = right.squarefreeLower)
    (squarefreeUpper :
      left.squarefreeUpper = right.squarefreeUpper) :
    left = right := by
  rcases left with
    ⟨leftDelta, leftHurstLower, leftHurstUpper,
      leftSquarefreeLower, leftSquarefreeUpper⟩
  rcases right with
    ⟨rightDelta, rightHurstLower, rightHurstUpper,
      rightSquarefreeLower, rightSquarefreeUpper⟩
  simp_all

/-- Semantic empty summary used for inactive finalizer threads. -/
def emptyCudaAffineMqBlockSummary : CudaAffineMqBlockSummary :=
  { delta := PrefixMQ.zero
    hurstLower := none
    hurstUpper := none
    squarefreeLower := none
    squarefreeUpper := none }

/-- Ordered composition of consecutive CUDA summaries.  The right Hurst
values receive `-left.delta.mertens`; right squarefree values receive
`-left.delta.squarefree`, while their retained witnesses receive
`+left.delta.squarefree`.  Candidate order is already global and is not
translated. -/
def composeCudaAffineMqBlockSummary
    (left right : CudaAffineMqBlockSummary) :
    CudaAffineMqBlockSummary :=
  { delta := left.delta + right.delta
    hurstLower :=
      mergeCudaAffineMaximum left.hurstLower
        (translateCudaHurstOption left.delta right.hurstLower)
    hurstUpper :=
      mergeCudaAffineMinimum left.hurstUpper
        (translateCudaHurstOption left.delta right.hurstUpper)
    squarefreeLower :=
      mergeCudaAffineMaximum left.squarefreeLower
        (translateCudaSquarefreeOption
          left.delta right.squarefreeLower)
    squarefreeUpper :=
      mergeCudaAffineMinimum left.squarefreeUpper
        (translateCudaSquarefreeOption
          left.delta right.squarefreeUpper) }

theorem empty_composeCudaAffineMqBlockSummary
    (summary : CudaAffineMqBlockSummary) :
    composeCudaAffineMqBlockSummary
        emptyCudaAffineMqBlockSummary summary = summary := by
  rcases summary with
    ⟨delta, hurstLower, hurstUpper,
      squarefreeLower, squarefreeUpper⟩
  simp [composeCudaAffineMqBlockSummary,
    emptyCudaAffineMqBlockSummary, mergeCudaAffineMaximum,
    mergeCudaAffineMinimum, mergeOptionalByKey]

theorem composeCudaAffineMqBlockSummary_empty
    (summary : CudaAffineMqBlockSummary) :
    composeCudaAffineMqBlockSummary summary
        emptyCudaAffineMqBlockSummary = summary := by
  rcases summary with
    ⟨delta, hurstLower, hurstUpper,
      squarefreeLower, squarefreeUpper⟩
  cases hurstLower <;> cases hurstUpper <;>
    cases squarefreeLower <;> cases squarefreeUpper <;>
  simp [composeCudaAffineMqBlockSummary,
    emptyCudaAffineMqBlockSummary, mergeCudaAffineMaximum,
    mergeCudaAffineMinimum, mergeOptionalByKey,
    translateCudaHurstOption, translateCudaSquarefreeOption]

/-- Associativity of the exact ordered native summary operation.  This proof
uses both translation signs and the squarefree-witness addition; it is not a
generic assertion that an unspecified CUDA reduction happens to be a
monoid. -/
theorem composeCudaAffineMqBlockSummary_assoc
    (first second third : CudaAffineMqBlockSummary) :
    composeCudaAffineMqBlockSummary
        (composeCudaAffineMqBlockSummary first second) third =
      composeCudaAffineMqBlockSummary first
        (composeCudaAffineMqBlockSummary second third) := by
  apply CudaAffineMqBlockSummary.ext
  · exact PrefixMQ.add_assoc first.delta second.delta third.delta
  · simp only [composeCudaAffineMqBlockSummary]
    rw [translateCudaHurstOption_mergeMaximum,
      ← translateCudaHurstOption_add,
      mergeCudaAffineMaximum_assoc]
  · simp only [composeCudaAffineMqBlockSummary]
    rw [translateCudaHurstOption_mergeMinimum,
      ← translateCudaHurstOption_add,
      mergeCudaAffineMinimum_assoc]
  · simp only [composeCudaAffineMqBlockSummary]
    rw [translateCudaSquarefreeOption_mergeMaximum,
      ← translateCudaSquarefreeOption_add,
      mergeCudaAffineMaximum_assoc]
  · simp only [composeCudaAffineMqBlockSummary]
    rw [translateCudaSquarefreeOption_mergeMinimum,
      ← translateCudaSquarefreeOption_add,
      mergeCudaAffineMinimum_assoc]

instance : One CudaAffineMqBlockSummary :=
  ⟨emptyCudaAffineMqBlockSummary⟩

instance : Mul CudaAffineMqBlockSummary :=
  ⟨composeCudaAffineMqBlockSummary⟩

instance : Monoid CudaAffineMqBlockSummary where
  one_mul := empty_composeCudaAffineMqBlockSummary
  mul_one := composeCudaAffineMqBlockSummary_empty
  mul_assoc := composeCudaAffineMqBlockSummary_assoc

/-- Instantiation of the proven 256-thread consecutive-chunk extraction and
eight adjacent tree rounds for the concrete CUDA affine summary.  The result
is the same ordered fold of exact summary semantics.

Refining compiled CUB scans, native sentinel encoding, fixed-width
instructions, and the CUDA load/store execution to these source values
remains an explicit external executable-refinement obligation. -/
theorem cudaAffineMqSummaryTree_refines_orderedFold
    (summaries : List CudaAffineMqBlockSummary) :
    (orderedTreeRounds 8
      ((cudaExtractedThreadChunks summaries).map List.prod)).prod =
        summaries.prod := by
  exact cudaExtractedChunksAndTree_refine_orderedFold summaries

/-! ## Concrete summaries extracted from exact per-row candidates

The native block kernel permits a row to emit zero, one, or several endpoint
candidates in each of the four streams.  `CudaAffineMqRowBound` records the
source-only part of one such candidate: its bound before subtracting the
running coordinate and whether it is the integer (`0`) or right-limit (`1`)
endpoint.  A row-bound schedule can therefore express the Hurst `n ≥ 33`
filter, both squarefree endpoints, the squarefree threshold, and omission of
the terminal right endpoint without building those analytic formulas into
the composition theorem.
-/

structure CudaAffineMqRowBound where
  base : Int
  endpoint : Nat
  deriving Repr, DecidableEq

/-- Four source-indexed endpoint schedules, in native summary field order. -/
structure CudaAffineMqRowBounds where
  hurstLower : Nat → List CudaAffineMqRowBound
  hurstUpper : Nat → List CudaAffineMqRowBound
  squarefreeLower : Nat → List CudaAffineMqRowBound
  squarefreeUpper : Nat → List CudaAffineMqRowBound

/-- Hurst candidates emitted at one row after its inclusive local prefix has
been formed.  Their squarefree witness field is the native literal zero. -/
def cudaHurstRowCandidates
    (bounds : List CudaAffineMqRowBound)
    (orderOffset : Nat) (pfx : PrefixMQ) :
    List CudaAffineMqBoundCandidate :=
  bounds.map fun bound =>
    { value := bound.base - pfx.mertens
      localSquarefree := 0
      order := 2 * orderOffset + bound.endpoint }

/-- Squarefree candidates emitted at one row.  The exact inclusive
squarefree prefix is retained as the candidate witness. -/
def cudaSquarefreeRowCandidates
    (bounds : List CudaAffineMqRowBound)
    (orderOffset : Nat) (pfx : PrefixMQ) :
    List CudaAffineMqBoundCandidate :=
  bounds.map fun bound =>
    { value := bound.base - (pfx.squarefree : Int)
      localSquarefree := pfx.squarefree
      order := 2 * orderOffset + bound.endpoint }

/-- Exact Hurst candidate stream over consecutive input rows.  Source and
order offsets remain separate, matching the earlier affine scan model. -/
def cudaHurstCandidatesFrom
    (bounds : Nat → List CudaAffineMqRowBound) :
    Nat → Nat → PrefixMQ → List PrefixMQ →
      List CudaAffineMqBoundCandidate
  | _, _, _, [] => []
  | sourceOffset, orderOffset, incoming, row :: rest =>
      let next := incoming + row
      cudaHurstRowCandidates (bounds sourceOffset)
          orderOffset next ++
        cudaHurstCandidatesFrom bounds
          (sourceOffset + 1) (orderOffset + 1) next rest

/-- Exact squarefree candidate stream over consecutive input rows. -/
def cudaSquarefreeCandidatesFrom
    (bounds : Nat → List CudaAffineMqRowBound) :
    Nat → Nat → PrefixMQ → List PrefixMQ →
      List CudaAffineMqBoundCandidate
  | _, _, _, [] => []
  | sourceOffset, orderOffset, incoming, row :: rest =>
      let next := incoming + row
      cudaSquarefreeRowCandidates (bounds sourceOffset)
          orderOffset next ++
        cudaSquarefreeCandidatesFrom bounds
          (sourceOffset + 1) (orderOffset + 1) next rest

theorem cudaHurstCandidatesFrom_append
    (bounds : Nat → List CudaAffineMqRowBound)
    (sourceOffset orderOffset : Nat)
    (incoming : PrefixMQ) (left right : List PrefixMQ) :
    cudaHurstCandidatesFrom bounds sourceOffset orderOffset
        incoming (left ++ right) =
      cudaHurstCandidatesFrom bounds sourceOffset orderOffset
          incoming left ++
        cudaHurstCandidatesFrom bounds
          (sourceOffset + left.length)
          (orderOffset + left.length)
          (incoming + inputTotal left) right := by
  induction left generalizing sourceOffset orderOffset incoming with
  | nil =>
      simp [cudaHurstCandidatesFrom, inputTotal]
  | cons row rest inductionHypothesis =>
      simp only [List.cons_append, cudaHurstCandidatesFrom,
        List.length_cons, inputTotal, List.append_assoc]
      congr 1
      simpa only [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm,
        PrefixMQ.add_assoc] using
        inductionHypothesis
          (sourceOffset + 1) (orderOffset + 1) (incoming + row)

theorem cudaSquarefreeCandidatesFrom_append
    (bounds : Nat → List CudaAffineMqRowBound)
    (sourceOffset orderOffset : Nat)
    (incoming : PrefixMQ) (left right : List PrefixMQ) :
    cudaSquarefreeCandidatesFrom bounds sourceOffset orderOffset
        incoming (left ++ right) =
      cudaSquarefreeCandidatesFrom bounds sourceOffset orderOffset
          incoming left ++
        cudaSquarefreeCandidatesFrom bounds
          (sourceOffset + left.length)
          (orderOffset + left.length)
          (incoming + inputTotal left) right := by
  induction left generalizing sourceOffset orderOffset incoming with
  | nil =>
      simp [cudaSquarefreeCandidatesFrom, inputTotal]
  | cons row rest inductionHypothesis =>
      simp only [List.cons_append, cudaSquarefreeCandidatesFrom,
        List.length_cons, inputTotal, List.append_assoc]
      congr 1
      simpa only [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm,
        PrefixMQ.add_assoc] using
        inductionHypothesis
          (sourceOffset + 1) (orderOffset + 1) (incoming + row)

theorem cudaHurstRowCandidates_translate
    (bounds : List CudaAffineMqRowBound)
    (orderOffset : Nat) (stateShift pfx : PrefixMQ) :
    (cudaHurstRowCandidates bounds orderOffset pfx).map
        (translateCudaHurstCandidate stateShift) =
      cudaHurstRowCandidates bounds orderOffset
        (stateShift + pfx) := by
  simp only [cudaHurstRowCandidates, List.map_map]
  apply List.map_congr_left
  intro bound _member
  apply CudaAffineMqBoundCandidate.ext
  · simp [translateCudaHurstCandidate,
      translateCudaAffineCandidate]
    ring
  · simp [translateCudaHurstCandidate,
      translateCudaAffineCandidate]
  · simp [translateCudaHurstCandidate,
      translateCudaAffineCandidate]

theorem cudaSquarefreeRowCandidates_translate
    (bounds : List CudaAffineMqRowBound)
    (orderOffset : Nat) (stateShift pfx : PrefixMQ) :
    (cudaSquarefreeRowCandidates bounds orderOffset pfx).map
        (translateCudaSquarefreeCandidate stateShift) =
      cudaSquarefreeRowCandidates bounds orderOffset
        (stateShift + pfx) := by
  simp only [cudaSquarefreeRowCandidates, List.map_map]
  apply List.map_congr_left
  intro bound _member
  apply CudaAffineMqBoundCandidate.ext
  · simp [translateCudaSquarefreeCandidate,
      translateCudaAffineCandidate, Nat.add_comm]
    ring
  · simp [translateCudaSquarefreeCandidate,
      translateCudaAffineCandidate, Nat.add_comm]
  · simp [translateCudaSquarefreeCandidate,
      translateCudaAffineCandidate]

/-- Installing an incoming Mertens state translates the entire zero-based
Hurst stream by exactly its negative Mertens coordinate, with no order
translation. -/
theorem cudaHurstCandidatesFrom_translate
    (bounds : Nat → List CudaAffineMqRowBound)
    (sourceOffset orderOffset : Nat)
    (stateShift incoming : PrefixMQ) (rows : List PrefixMQ) :
    (cudaHurstCandidatesFrom bounds sourceOffset orderOffset
        incoming rows).map
        (translateCudaHurstCandidate stateShift) =
      cudaHurstCandidatesFrom bounds sourceOffset orderOffset
        (stateShift + incoming) rows := by
  induction rows generalizing sourceOffset orderOffset incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp only [cudaHurstCandidatesFrom, List.map_append]
      rw [cudaHurstRowCandidates_translate,
        inductionHypothesis]
      simp only [PrefixMQ.add_assoc]

/-- Installing an incoming squarefree state both subtracts its coordinate
from every value and adds it to every retained prefix witness. -/
theorem cudaSquarefreeCandidatesFrom_translate
    (bounds : Nat → List CudaAffineMqRowBound)
    (sourceOffset orderOffset : Nat)
    (stateShift incoming : PrefixMQ) (rows : List PrefixMQ) :
    (cudaSquarefreeCandidatesFrom bounds sourceOffset orderOffset
        incoming rows).map
        (translateCudaSquarefreeCandidate stateShift) =
      cudaSquarefreeCandidatesFrom bounds sourceOffset orderOffset
        (stateShift + incoming) rows := by
  induction rows generalizing sourceOffset orderOffset incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp only [cudaSquarefreeCandidatesFrom, List.map_append]
      rw [cudaSquarefreeRowCandidates_translate,
        inductionHypothesis]
      simp only [PrefixMQ.add_assoc]

/-- Exact optional maximum of a source-ordered candidate stream. -/
def reduceCudaAffineMaximum :
    List CudaAffineMqBoundCandidate →
      Option CudaAffineMqBoundCandidate
  | [] => none
  | candidate :: rest =>
      mergeCudaAffineMaximum (some candidate)
        (reduceCudaAffineMaximum rest)

/-- Exact optional minimum of a source-ordered candidate stream. -/
def reduceCudaAffineMinimum :
    List CudaAffineMqBoundCandidate →
      Option CudaAffineMqBoundCandidate
  | [] => none
  | candidate :: rest =>
      mergeCudaAffineMinimum (some candidate)
        (reduceCudaAffineMinimum rest)

theorem reduceCudaAffineMaximum_append
    (left right : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMaximum (left ++ right) =
      mergeCudaAffineMaximum
        (reduceCudaAffineMaximum left)
        (reduceCudaAffineMaximum right) := by
  induction left with
  | nil =>
      simp [reduceCudaAffineMaximum, mergeCudaAffineMaximum,
        mergeOptionalByKey]
  | cons candidate rest inductionHypothesis =>
      simp only [List.cons_append, reduceCudaAffineMaximum,
        inductionHypothesis]
      exact (mergeCudaAffineMaximum_assoc
        (some candidate) (reduceCudaAffineMaximum rest)
        (reduceCudaAffineMaximum right)).symm

theorem reduceCudaAffineMinimum_append
    (left right : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMinimum (left ++ right) =
      mergeCudaAffineMinimum
        (reduceCudaAffineMinimum left)
        (reduceCudaAffineMinimum right) := by
  induction left with
  | nil =>
      simp [reduceCudaAffineMinimum, mergeCudaAffineMinimum,
        mergeOptionalByKey]
  | cons candidate rest inductionHypothesis =>
      simp only [List.cons_append, reduceCudaAffineMinimum,
        inductionHypothesis]
      exact (mergeCudaAffineMinimum_assoc
        (some candidate) (reduceCudaAffineMinimum rest)
        (reduceCudaAffineMinimum right)).symm

theorem reduceCudaAffineMaximum_map_translate
    (valueShift : Int) (squarefreeShift : Nat)
    (candidates : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMaximum
        (candidates.map
          (translateCudaAffineCandidate valueShift squarefreeShift)) =
      (reduceCudaAffineMaximum candidates).map
        (translateCudaAffineCandidate valueShift squarefreeShift) := by
  induction candidates with
  | nil => rfl
  | cons candidate rest inductionHypothesis =>
      simp only [List.map_cons, reduceCudaAffineMaximum,
        inductionHypothesis]
      exact
        (Option.map_translate_mergeCudaAffineMaximum
          valueShift squarefreeShift
          (some candidate) (reduceCudaAffineMaximum rest)).symm

theorem reduceCudaAffineMinimum_map_translate
    (valueShift : Int) (squarefreeShift : Nat)
    (candidates : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMinimum
        (candidates.map
          (translateCudaAffineCandidate valueShift squarefreeShift)) =
      (reduceCudaAffineMinimum candidates).map
        (translateCudaAffineCandidate valueShift squarefreeShift) := by
  induction candidates with
  | nil => rfl
  | cons candidate rest inductionHypothesis =>
      simp only [List.map_cons, reduceCudaAffineMinimum,
        inductionHypothesis]
      exact
        (Option.map_translate_mergeCudaAffineMinimum
          valueShift squarefreeShift
          (some candidate) (reduceCudaAffineMinimum rest)).symm

theorem reduceCudaAffineMaximum_map_translateHurst
    (delta : PrefixMQ)
    (candidates : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMaximum
        (candidates.map (translateCudaHurstCandidate delta)) =
      translateCudaHurstOption delta
        (reduceCudaAffineMaximum candidates) := by
  change
    reduceCudaAffineMaximum
        (candidates.map
          (translateCudaAffineCandidate (-delta.mertens) 0)) =
      (reduceCudaAffineMaximum candidates).map
        (translateCudaAffineCandidate (-delta.mertens) 0)
  exact reduceCudaAffineMaximum_map_translate
    (-delta.mertens) 0 candidates

theorem reduceCudaAffineMinimum_map_translateHurst
    (delta : PrefixMQ)
    (candidates : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMinimum
        (candidates.map (translateCudaHurstCandidate delta)) =
      translateCudaHurstOption delta
        (reduceCudaAffineMinimum candidates) := by
  change
    reduceCudaAffineMinimum
        (candidates.map
          (translateCudaAffineCandidate (-delta.mertens) 0)) =
      (reduceCudaAffineMinimum candidates).map
        (translateCudaAffineCandidate (-delta.mertens) 0)
  exact reduceCudaAffineMinimum_map_translate
    (-delta.mertens) 0 candidates

theorem reduceCudaAffineMaximum_map_translateSquarefree
    (delta : PrefixMQ)
    (candidates : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMaximum
        (candidates.map
          (translateCudaSquarefreeCandidate delta)) =
      translateCudaSquarefreeOption delta
        (reduceCudaAffineMaximum candidates) := by
  change
    reduceCudaAffineMaximum
        (candidates.map
          (translateCudaAffineCandidate
            (-((delta.squarefree : Nat) : Int))
            delta.squarefree)) =
      (reduceCudaAffineMaximum candidates).map
        (translateCudaAffineCandidate
          (-((delta.squarefree : Nat) : Int))
          delta.squarefree)
  exact reduceCudaAffineMaximum_map_translate
    (-((delta.squarefree : Nat) : Int))
    delta.squarefree candidates

theorem reduceCudaAffineMinimum_map_translateSquarefree
    (delta : PrefixMQ)
    (candidates : List CudaAffineMqBoundCandidate) :
    reduceCudaAffineMinimum
        (candidates.map
          (translateCudaSquarefreeCandidate delta)) =
      translateCudaSquarefreeOption delta
        (reduceCudaAffineMinimum candidates) := by
  change
    reduceCudaAffineMinimum
        (candidates.map
          (translateCudaAffineCandidate
            (-((delta.squarefree : Nat) : Int))
            delta.squarefree)) =
      (reduceCudaAffineMinimum candidates).map
        (translateCudaAffineCandidate
          (-((delta.squarefree : Nat) : Int))
          delta.squarefree)
  exact reduceCudaAffineMinimum_map_translate
    (-((delta.squarefree : Nat) : Int))
    delta.squarefree candidates

/-- One exact zero-incoming tile summary extracted from every per-row
candidate in all four native streams. -/
def cudaAffineMqSummaryOfRows
    (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat)
    (rows : List PrefixMQ) : CudaAffineMqBlockSummary :=
  { delta := inputTotal rows
    hurstLower :=
      reduceCudaAffineMaximum
        (cudaHurstCandidatesFrom bounds.hurstLower
          sourceOffset orderOffset PrefixMQ.zero rows)
    hurstUpper :=
      reduceCudaAffineMinimum
        (cudaHurstCandidatesFrom bounds.hurstUpper
          sourceOffset orderOffset PrefixMQ.zero rows)
    squarefreeLower :=
      reduceCudaAffineMaximum
        (cudaSquarefreeCandidatesFrom bounds.squarefreeLower
          sourceOffset orderOffset PrefixMQ.zero rows)
    squarefreeUpper :=
      reduceCudaAffineMinimum
        (cudaSquarefreeCandidatesFrom bounds.squarefreeUpper
          sourceOffset orderOffset PrefixMQ.zero rows) }

@[simp] theorem cudaAffineMqSummaryOfRows_nil
    (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat) :
    cudaAffineMqSummaryOfRows bounds sourceOffset orderOffset [] =
      emptyCudaAffineMqBlockSummary := by
  rfl

/-- The concrete summary of concatenated consecutive rows is exactly the
ordered native composition of their two zero-based summaries.  This is the
theorem-level bridge from per-row affine candidates to the concrete summary
monoid. -/
theorem cudaAffineMqSummaryOfRows_append
    (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat)
    (left right : List PrefixMQ) :
    cudaAffineMqSummaryOfRows bounds sourceOffset orderOffset
        (left ++ right) =
      composeCudaAffineMqBlockSummary
        (cudaAffineMqSummaryOfRows bounds
          sourceOffset orderOffset left)
        (cudaAffineMqSummaryOfRows bounds
          (sourceOffset + left.length)
          (orderOffset + left.length) right) := by
  apply CudaAffineMqBlockSummary.ext
  · exact inputTotal_append left right
  · simp only [cudaAffineMqSummaryOfRows,
      composeCudaAffineMqBlockSummary]
    rw [cudaHurstCandidatesFrom_append,
      reduceCudaAffineMaximum_append]
    congr 1
    let rightCandidates :=
      cudaHurstCandidatesFrom bounds.hurstLower
        (sourceOffset + left.length)
        (orderOffset + left.length) PrefixMQ.zero right
    have translated :=
      cudaHurstCandidatesFrom_translate bounds.hurstLower
        (sourceOffset + left.length)
        (orderOffset + left.length)
        (inputTotal left) PrefixMQ.zero right
    calc
      reduceCudaAffineMaximum
          (cudaHurstCandidatesFrom bounds.hurstLower
            (sourceOffset + left.length)
            (orderOffset + left.length)
            (PrefixMQ.zero + inputTotal left) right) =
          reduceCudaAffineMaximum
            (rightCandidates.map
              (translateCudaHurstCandidate (inputTotal left))) := by
            congr 1
            simpa [rightCandidates] using translated.symm
      _ = translateCudaHurstOption (inputTotal left)
            (reduceCudaAffineMaximum rightCandidates) :=
          reduceCudaAffineMaximum_map_translateHurst
            (inputTotal left) rightCandidates
  · simp only [cudaAffineMqSummaryOfRows,
      composeCudaAffineMqBlockSummary]
    rw [cudaHurstCandidatesFrom_append,
      reduceCudaAffineMinimum_append]
    congr 1
    let rightCandidates :=
      cudaHurstCandidatesFrom bounds.hurstUpper
        (sourceOffset + left.length)
        (orderOffset + left.length) PrefixMQ.zero right
    have translated :=
      cudaHurstCandidatesFrom_translate bounds.hurstUpper
        (sourceOffset + left.length)
        (orderOffset + left.length)
        (inputTotal left) PrefixMQ.zero right
    calc
      reduceCudaAffineMinimum
          (cudaHurstCandidatesFrom bounds.hurstUpper
            (sourceOffset + left.length)
            (orderOffset + left.length)
            (PrefixMQ.zero + inputTotal left) right) =
          reduceCudaAffineMinimum
            (rightCandidates.map
              (translateCudaHurstCandidate (inputTotal left))) := by
            congr 1
            simpa [rightCandidates] using translated.symm
      _ = translateCudaHurstOption (inputTotal left)
            (reduceCudaAffineMinimum rightCandidates) :=
          reduceCudaAffineMinimum_map_translateHurst
            (inputTotal left) rightCandidates
  · simp only [cudaAffineMqSummaryOfRows,
      composeCudaAffineMqBlockSummary]
    rw [cudaSquarefreeCandidatesFrom_append,
      reduceCudaAffineMaximum_append]
    congr 1
    let rightCandidates :=
      cudaSquarefreeCandidatesFrom bounds.squarefreeLower
        (sourceOffset + left.length)
        (orderOffset + left.length) PrefixMQ.zero right
    have translated :=
      cudaSquarefreeCandidatesFrom_translate bounds.squarefreeLower
        (sourceOffset + left.length)
        (orderOffset + left.length)
        (inputTotal left) PrefixMQ.zero right
    calc
      reduceCudaAffineMaximum
          (cudaSquarefreeCandidatesFrom bounds.squarefreeLower
            (sourceOffset + left.length)
            (orderOffset + left.length)
            (PrefixMQ.zero + inputTotal left) right) =
          reduceCudaAffineMaximum
            (rightCandidates.map
              (translateCudaSquarefreeCandidate
                (inputTotal left))) := by
            congr 1
            simpa [rightCandidates] using translated.symm
      _ = translateCudaSquarefreeOption (inputTotal left)
            (reduceCudaAffineMaximum rightCandidates) :=
          reduceCudaAffineMaximum_map_translateSquarefree
            (inputTotal left) rightCandidates
  · simp only [cudaAffineMqSummaryOfRows,
      composeCudaAffineMqBlockSummary]
    rw [cudaSquarefreeCandidatesFrom_append,
      reduceCudaAffineMinimum_append]
    congr 1
    let rightCandidates :=
      cudaSquarefreeCandidatesFrom bounds.squarefreeUpper
        (sourceOffset + left.length)
        (orderOffset + left.length) PrefixMQ.zero right
    have translated :=
      cudaSquarefreeCandidatesFrom_translate bounds.squarefreeUpper
        (sourceOffset + left.length)
        (orderOffset + left.length)
        (inputTotal left) PrefixMQ.zero right
    calc
      reduceCudaAffineMinimum
          (cudaSquarefreeCandidatesFrom bounds.squarefreeUpper
            (sourceOffset + left.length)
            (orderOffset + left.length)
            (PrefixMQ.zero + inputTotal left) right) =
          reduceCudaAffineMinimum
            (rightCandidates.map
              (translateCudaSquarefreeCandidate
                (inputTotal left))) := by
            congr 1
            simpa [rightCandidates] using translated.symm
      _ = translateCudaSquarefreeOption (inputTotal left)
            (reduceCudaAffineMinimum rightCandidates) :=
          reduceCudaAffineMinimum_map_translateSquarefree
            (inputTotal left) rightCandidates

/-- Summarize consecutive tiles while advancing both global source and
source-order offsets by every preceding tile length. -/
def cudaAffineMqSummariesOfTiles
    (bounds : CudaAffineMqRowBounds) :
    Nat → Nat → List (List PrefixMQ) →
      List CudaAffineMqBlockSummary
  | _, _, [] => []
  | sourceOffset, orderOffset, tile :: rest =>
      cudaAffineMqSummaryOfRows bounds
          sourceOffset orderOffset tile ::
        cudaAffineMqSummariesOfTiles bounds
          (sourceOffset + tile.length)
          (orderOffset + tile.length) rest

/-- Ordered multiplication of consecutive tile summaries is the single
summary extracted from their flattened per-row stream. -/
theorem prod_cudaAffineMqSummariesOfTiles
    (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat)
    (tiles : List (List PrefixMQ)) :
    (cudaAffineMqSummariesOfTiles bounds
      sourceOffset orderOffset tiles).prod =
        cudaAffineMqSummaryOfRows bounds
          sourceOffset orderOffset tiles.flatten := by
  induction tiles generalizing sourceOffset orderOffset with
  | nil =>
      rfl
  | cons tile rest inductionHypothesis =>
      simp only [cudaAffineMqSummariesOfTiles, List.prod_cons,
        List.flatten_cons, inductionHypothesis]
      exact (cudaAffineMqSummaryOfRows_append bounds
        sourceOffset orderOffset tile rest.flatten).symm

/-- The source-level 256-thread extraction/tree and the ordinary ordered fold
both equal the exact four-field per-row summary of the flattened consecutive
tiles.  Refining compiled CUB scans and the CUDA kernel to
`cudaAffineMqSummaryOfRows` remains external. -/
theorem cudaAffineMqTileSummaryTree_eq_perRowSummary
    (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat)
    (tiles : List (List PrefixMQ)) :
    (orderedTreeRounds 8
      ((cudaExtractedThreadChunks
        (cudaAffineMqSummariesOfTiles bounds
          sourceOffset orderOffset tiles)).map List.prod)).prod =
      cudaAffineMqSummaryOfRows bounds
        sourceOffset orderOffset tiles.flatten := by
  rw [cudaAffineMqSummaryTree_refines_orderedFold,
    prod_cudaAffineMqSummariesOfTiles]

/-! ## Projection to the prior per-row/worker extrema model -/

/-- One endpoint per row, used to identify the concrete Hurst fields with the
earlier `affineCandidatesFrom` definition. -/
def singletonCudaAffineMqRowBounds
    (base : Nat → Int) (endpoint sourceIndex : Nat) :
    List CudaAffineMqRowBound :=
  [{ base := base sourceIndex, endpoint := endpoint }]

/-- A four-field schedule with only the two Hurst streams populated. -/
def cudaHurstOnlyRowBounds
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat) :
    CudaAffineMqRowBounds :=
  { hurstLower :=
      singletonCudaAffineMqRowBounds lowerBase lowerEndpoint
    hurstUpper :=
      singletonCudaAffineMqRowBounds upperBase upperEndpoint
    squarefreeLower := fun _ => []
    squarefreeUpper := fun _ => [] }

/-- Erasing the unused squarefree witness from the concrete singleton Hurst
stream yields the earlier affine per-row stream literally. -/
theorem map_ordered_cudaHurstCandidatesFrom_singleton
    (base : Nat → Int) (endpoint sourceOffset orderOffset : Nat)
    (incoming : PrefixMQ) (rows : List PrefixMQ) :
    (cudaHurstCandidatesFrom
      (singletonCudaAffineMqRowBounds base endpoint)
      sourceOffset orderOffset incoming rows).map
        CudaAffineMqBoundCandidate.ordered =
      affineCandidatesFrom PrefixMQ.mertens base endpoint
        sourceOffset orderOffset incoming rows := by
  induction rows generalizing sourceOffset orderOffset incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp only [cudaHurstCandidatesFrom,
        singletonCudaAffineMqRowBounds,
        cudaHurstRowCandidates, List.map_cons, List.map_nil,
        List.singleton_append,
        affineCandidatesFrom,
        CudaAffineMqBoundCandidate.ordered]
      congr 1
      simpa only [Nat.add_assoc] using
        inductionHypothesis
          (sourceOffset + 1) (orderOffset + 1)
          (incoming + row)

theorem ordered_chooseCudaAffineMaximum
    (left right : CudaAffineMqBoundCandidate) :
    (chooseByKey cudaAffineMaximumKey left right).ordered =
      combineByKey lowerKey left.ordered right.ordered := by
  by_cases comparison :
      lowerKey left.ordered ≤ lowerKey right.ordered
  · simp [chooseByKey, combineByKey, cudaAffineMaximumKey,
      comparison]
  · simp [chooseByKey, combineByKey, cudaAffineMaximumKey,
      comparison]

theorem ordered_chooseCudaAffineMinimum
    (left right : CudaAffineMqBoundCandidate) :
    (chooseByKey cudaAffineMinimumKey left right).ordered =
      combineByKey upperKey left.ordered right.ordered := by
  by_cases comparison :
      upperKey left.ordered ≤ upperKey right.ordered
  · simp [chooseByKey, combineByKey, cudaAffineMinimumKey,
      comparison]
  · simp [chooseByKey, combineByKey, cudaAffineMinimumKey,
      comparison]

theorem Option.map_ordered_mergeCudaAffineMaximum
    (left right : Option CudaAffineMqBoundCandidate) :
    (mergeCudaAffineMaximum left right).map
        CudaAffineMqBoundCandidate.ordered =
      mergeReduced lowerKey
        (left.map CudaAffineMqBoundCandidate.ordered)
        (right.map CudaAffineMqBoundCandidate.ordered) := by
  cases left <;> cases right <;>
    simp [mergeCudaAffineMaximum, mergeOptionalByKey,
      mergeReduced, ordered_chooseCudaAffineMaximum]

theorem Option.map_ordered_mergeCudaAffineMinimum
    (left right : Option CudaAffineMqBoundCandidate) :
    (mergeCudaAffineMinimum left right).map
        CudaAffineMqBoundCandidate.ordered =
      mergeReduced upperKey
        (left.map CudaAffineMqBoundCandidate.ordered)
        (right.map CudaAffineMqBoundCandidate.ordered) := by
  cases left <;> cases right <;>
    simp [mergeCudaAffineMinimum, mergeOptionalByKey,
      mergeReduced, ordered_chooseCudaAffineMinimum]

/-- Concrete maximum reduction, after witness erasure, is the prior
deterministic maximum reduction on exactly the same ordered stream. -/
theorem Option.map_ordered_reduceCudaAffineMaximum
    (candidates : List CudaAffineMqBoundCandidate) :
    (reduceCudaAffineMaximum candidates).map
        CudaAffineMqBoundCandidate.ordered =
      reduceMaximum
        (candidates.map CudaAffineMqBoundCandidate.ordered) := by
  induction candidates with
  | nil => rfl
  | cons candidate rest inductionHypothesis =>
      simp only [reduceCudaAffineMaximum, List.map_cons]
      rw [Option.map_ordered_mergeCudaAffineMaximum,
        inductionHypothesis]
      have appended :=
        reduceMaximum_append
          [candidate.ordered]
          (rest.map CudaAffineMqBoundCandidate.ordered)
      simpa [reduceMaximum, reduceByKey, foldByKey] using
        appended.symm

/-- Concrete minimum reduction has the analogous exact projection. -/
theorem Option.map_ordered_reduceCudaAffineMinimum
    (candidates : List CudaAffineMqBoundCandidate) :
    (reduceCudaAffineMinimum candidates).map
        CudaAffineMqBoundCandidate.ordered =
      reduceMinimum
        (candidates.map CudaAffineMqBoundCandidate.ordered) := by
  induction candidates with
  | nil => rfl
  | cons candidate rest inductionHypothesis =>
      simp only [reduceCudaAffineMinimum, List.map_cons]
      rw [Option.map_ordered_mergeCudaAffineMinimum,
        inductionHypothesis]
      have appended :=
        reduceMinimum_append
          [candidate.ordered]
          (rest.map CudaAffineMqBoundCandidate.ordered)
      simpa [reduceMinimum, reduceByKey, foldByKey] using
        appended.symm

/-- The two concrete Hurst fields of `summaryOfRows`, after witness erasure,
are exactly the earlier per-row inclusive-scan extrema. -/
theorem cudaHurstSummaryOfRows_projects_to_perRowExtrema
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat)
    (rows : List PrefixMQ) :
    let summary :=
      cudaAffineMqSummaryOfRows
        (cudaHurstOnlyRowBounds lowerBase upperBase
          lowerEndpoint upperEndpoint) 0 0 rows
    summary.hurstLower.map
          CudaAffineMqBoundCandidate.ordered =
        reduceMaximum
          (rowCandidates
            (fun index pfx =>
              lowerBase index - pfx.mertens)
            lowerEndpoint (inclusiveInputScan rows)) ∧
      summary.hurstUpper.map
          CudaAffineMqBoundCandidate.ordered =
        reduceMinimum
          (rowCandidates
            (fun index pfx =>
              upperBase index - pfx.mertens)
            upperEndpoint (inclusiveInputScan rows)) := by
  dsimp only
  constructor
  · simp only [cudaAffineMqSummaryOfRows,
      cudaHurstOnlyRowBounds]
    rw [Option.map_ordered_reduceCudaAffineMaximum,
      map_ordered_cudaHurstCandidatesFrom_singleton,
      affineCandidatesFrom_zero_eq_rowCandidates]
  · simp only [cudaAffineMqSummaryOfRows,
      cudaHurstOnlyRowBounds]
    rw [Option.map_ordered_reduceCudaAffineMinimum,
      map_ordered_cudaHurstCandidatesFrom_singleton,
      affineCandidatesFrom_zero_eq_rowCandidates]

/-- Named source result of the 256-thread consecutive-chunk/tree model. -/
def cudaAffineMqTileTreeResult
    (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat)
    (tiles : List (List PrefixMQ)) :
    CudaAffineMqBlockSummary :=
  (orderedTreeRounds 8
    ((cudaExtractedThreadChunks
      (cudaAffineMqSummariesOfTiles bounds
        sourceOffset orderOffset tiles)).map List.prod)).prod

theorem cudaAffineMqTileTreeResult_eq_perRowSummary
    (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat)
    (tiles : List (List PrefixMQ)) :
    cudaAffineMqTileTreeResult bounds sourceOffset orderOffset tiles =
      cudaAffineMqSummaryOfRows bounds
        sourceOffset orderOffset tiles.flatten := by
  exact cudaAffineMqTileSummaryTree_eq_perRowSummary
    bounds sourceOffset orderOffset tiles

/-- Final theorem-level connection to the earlier `WorkerChunk` model.  For
the same CUDA full-tile/partial-final-tile partition, the concrete
four-field tree's projected Hurst extrema equal the earlier worker
composition extrema, which in turn were proved equal to the ordinary
per-row inclusive scan.

This identifies all source-level list arithmetic.  Extraction of the rows
and bounds by compiled CUDA/CUB remains the explicit external refinement
boundary. -/
theorem cudaHurstTileTree_projects_to_workerComposition
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat)
    (fullTiles : List (List PrefixMQ))
    (finalTile : List PrefixMQ)
    (shape : CudaTileShape fullTiles finalTile) :
    let workers := cudaTileWorkers fullTiles finalTile
    let tiles := workers.map WorkerChunk.rows
    let bounds :=
      cudaHurstOnlyRowBounds lowerBase upperBase
        lowerEndpoint upperEndpoint
    let aggregate :=
      cudaAffineMqTileTreeResult bounds 0 0 tiles
    aggregate.hurstLower.map
          CudaAffineMqBoundCandidate.ordered =
        composeWorkerMaximum PrefixMQ.mertens
          lowerBase upperBase lowerEndpoint upperEndpoint
          0 PrefixMQ.zero workers ∧
      aggregate.hurstUpper.map
          CudaAffineMqBoundCandidate.ordered =
        composeWorkerMinimum PrefixMQ.mertens
          lowerBase upperBase lowerEndpoint upperEndpoint
          0 PrefixMQ.zero workers := by
  dsimp only
  let workers := cudaTileWorkers fullTiles finalTile
  let tiles := workers.map WorkerChunk.rows
  let bounds :=
    cudaHurstOnlyRowBounds lowerBase upperBase
      lowerEndpoint upperEndpoint
  have tree :=
    cudaAffineMqTileTreeResult_eq_perRowSummary bounds 0 0 tiles
  have projected :=
    cudaHurstSummaryOfRows_projects_to_perRowExtrema
      lowerBase upperBase lowerEndpoint upperEndpoint tiles.flatten
  have workersRows :
      tiles.flatten = fullTiles.flatten ++ finalTile := by
    simpa [tiles, workers, workerRows] using
      workerRows_cudaTileWorkers fullTiles finalTile
  have prior :=
    cudaOrderedTileComposition_eq_perRowInclusiveScan
      mertensCoordinate_additive
      lowerBase upperBase lowerEndpoint upperEndpoint
      fullTiles finalTile shape
  constructor
  · rw [tree]
    calc
      (cudaAffineMqSummaryOfRows bounds 0 0
          tiles.flatten).hurstLower.map
            CudaAffineMqBoundCandidate.ordered =
          reduceMaximum
            (rowCandidates
              (fun index pfx =>
                lowerBase index - pfx.mertens)
              lowerEndpoint
              (inclusiveInputScan tiles.flatten)) :=
        projected.1
      _ = reduceMaximum
            (rowCandidates
              (fun index pfx =>
                lowerBase index - pfx.mertens)
              lowerEndpoint
              (inclusiveInputScan
                (fullTiles.flatten ++ finalTile))) := by
          rw [workersRows]
      _ = composeWorkerMaximum PrefixMQ.mertens
            lowerBase upperBase lowerEndpoint upperEndpoint
            0 PrefixMQ.zero
            (cudaTileWorkers fullTiles finalTile) :=
          prior.1.symm
  · rw [tree]
    calc
      (cudaAffineMqSummaryOfRows bounds 0 0
          tiles.flatten).hurstUpper.map
            CudaAffineMqBoundCandidate.ordered =
          reduceMinimum
            (rowCandidates
              (fun index pfx =>
                upperBase index - pfx.mertens)
              upperEndpoint
              (inclusiveInputScan tiles.flatten)) :=
        projected.2
      _ = reduceMinimum
            (rowCandidates
              (fun index pfx =>
                upperBase index - pfx.mertens)
              upperEndpoint
              (inclusiveInputScan
                (fullTiles.flatten ++ finalTile))) := by
          rw [workersRows]
      _ = composeWorkerMinimum PrefixMQ.mertens
            lowerBase upperBase lowerEndpoint upperEndpoint
            0 PrefixMQ.zero
            (cudaTileWorkers fullTiles finalTile) :=
          prior.2.symm

/-! ## Compact receipt guards implied by valid Möbius rows -/

/-- Exact source-row invariants checked again by the host receipt:
squarefree count cannot exceed the row count, Mertens lies between its
negative and positive, and `M + Q` is even. -/
theorem validPrefixRows_imply_terminalMqGuards
    {rows : List PrefixMQ} (valid : PrefixInputRowsValid rows) :
    (inputTotal rows).squarefree ≤ rows.length ∧
      -((inputTotal rows).squarefree : Int) ≤
        (inputTotal rows).mertens ∧
      (inputTotal rows).mertens ≤
        ((inputTotal rows).squarefree : Int) ∧
      ((inputTotal rows).mertens +
        ((inputTotal rows).squarefree : Int)) % 2 = 0 := by
  induction rows with
  | nil =>
      simp [inputTotal]
  | cons row rest inductionHypothesis =>
      have rowValid : PrefixInputRowValid row :=
        valid row (by simp)
      have restValid : PrefixInputRowsValid rest := by
        intro other member
        exact valid other (by simp [member])
      have tail := inductionHypothesis restValid
      rcases row with ⟨mertens, squarefree⟩
      unfold PrefixInputRowValid at rowValid
      change
        (-1 : Int) ≤ mertens ∧
          mertens ≤ 1 ∧
          squarefree =
            if mertens = 0 then 0 else 1 at rowValid
      by_cases zero : mertens = 0
      · have squarefreeZero : squarefree = 0 := by
          simpa [zero] using rowValid.2.2
        subst mertens
        subst squarefree
        simp only [inputTotal, PrefixMQ.add_mertens,
          PrefixMQ.add_squarefree, List.length_cons,
          Nat.cast_add, Nat.cast_zero]
        omega
      · have squarefreeOne : squarefree = 1 := by
          simpa [zero] using rowValid.2.2
        have sign : mertens = -1 ∨ mertens = 1 := by
          omega
        rcases sign with negative | positive
        · subst mertens
          subst squarefree
          simp only [inputTotal, PrefixMQ.add_mertens,
            PrefixMQ.add_squarefree, List.length_cons,
            Nat.cast_add, Nat.cast_one]
          omega
        · subst mertens
          subst squarefree
          simp only [inputTotal, PrefixMQ.add_mertens,
            PrefixMQ.add_squarefree, List.length_cons,
            Nat.cast_add, Nat.cast_one]
          omega

end SparkInterval.TernaryGoldbach.HurstAffineBlockComposition
