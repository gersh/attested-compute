/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction

/-!
# Exact distributed composition of Hurst affine summaries

The H100 campaign splits the terminal Möbius range into consecutive workers.
Each worker computes its row delta and its local affine guard extrema from a
scan which starts at zero.  A worker receipt may additionally record an
arbitrary proxy incoming state.  Conceptually evaluating candidates at that
proxy and then normalizing by the same proxy gives exactly the zero-based
local candidates; no assertion that the proxy satisfies the guard is needed.

The reducer performs two different operations which must not be conflated:

* it exclusively scans worker deltas from the real CPU handoff to obtain the
  real incoming state checked against each local guard;
* it subtracts only the cumulative worker delta from each local extremum to
  express that extremum as a guard on the original CPU handoff.

This file proves, for an arbitrary number of workers, that reducing those
translated local extrema is exactly the same as one sequential scan and
candidate reduction over the concatenated input rows.  Candidate source
orders are translated at the same time, so equal extrema retain the earliest
source endpoint.  The theorem has no proxy-guard hypothesis.

The result is an architecture-independent list theorem.  Parsing the Python
worker bundles, identifying their fields with these structures, and refining
the compiled CUB/CUDA execution to the list scan remain explicit external
boundaries.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstAffineClusterComposition

open SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter
open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction

/-! ## Exact affine candidate streams -/

/-- A coordinate used by an affine guard.  The two production instances are
Mertens and the integer coercion of the squarefree count. -/
def CoordinateAdditive (coordinate : PrefixMQ → Int) : Prop :=
  coordinate PrefixMQ.zero = 0 ∧
    ∀ left right,
      coordinate (left + right) =
        coordinate left + coordinate right

/-- Mertens is an additive affine coordinate. -/
theorem mertensCoordinate_additive :
    CoordinateAdditive PrefixMQ.mertens := by
  constructor
  · rfl
  · intro left right
    rfl

/-- Squarefree count, coerced to `Int`, is an additive affine coordinate. -/
theorem squarefreeCoordinate_additive :
    CoordinateAdditive (fun state => (state.squarefree : Int)) := by
  constructor
  · rfl
  · intro left right
    simp

/-- Shift one exact candidate by a common affine value and a whole-row source
offset.  Production uses `valueShift = -coordinate cumulativeDelta`. -/
def shiftCandidate
    (valueShift : Int) (rowShift : Nat)
    (candidate : OrderedCandidate) : OrderedCandidate :=
  { value := candidate.value + valueShift
    order := candidate.order + 2 * rowShift }

@[simp] theorem shiftCandidate_value
    (valueShift : Int) (rowShift : Nat)
    (candidate : OrderedCandidate) :
    (shiftCandidate valueShift rowShift candidate).value =
      candidate.value + valueShift := rfl

@[simp] theorem shiftCandidate_order
    (valueShift : Int) (rowShift : Nat)
    (candidate : OrderedCandidate) :
    (shiftCandidate valueShift rowShift candidate).order =
      candidate.order + 2 * rowShift := rfl

/-- One exact endpoint-candidate stream.  `sourceOffset` selects the
source-dependent analytic bound, while `orderOffset` is the row offset in the
complete GPU range.  Keeping these offsets separate models a worker's local
order zero without losing its absolute source formula. -/
def affineCandidatesFrom
    (coordinate : PrefixMQ → Int) (base : Nat → Int)
    (endpoint sourceOffset orderOffset : Nat) :
    PrefixMQ → List PrefixMQ → List OrderedCandidate
  | _, [] => []
  | incoming, row :: rest =>
      let next := incoming + row
      { value := base sourceOffset - coordinate next
        order := 2 * orderOffset + endpoint } ::
      affineCandidatesFrom coordinate base endpoint
        (sourceOffset + 1) (orderOffset + 1) next rest

@[simp] theorem affineCandidatesFrom_length
    (coordinate : PrefixMQ → Int) (base : Nat → Int)
    (endpoint sourceOffset orderOffset : Nat)
    (incoming : PrefixMQ) (rows : List PrefixMQ) :
    (affineCandidatesFrom coordinate base endpoint
      sourceOffset orderOffset incoming rows).length = rows.length := by
  induction rows generalizing sourceOffset orderOffset incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp [affineCandidatesFrom, inductionHypothesis]

/-- The recursive affine stream is exactly candidate generation over the
existing exact `inputScanFrom` specification. -/
theorem affineCandidatesFrom_eq_scan_mapIdx
    (coordinate : PrefixMQ → Int) (base : Nat → Int)
    (endpoint sourceOffset orderOffset : Nat)
    (incoming : PrefixMQ) (rows : List PrefixMQ) :
    affineCandidatesFrom coordinate base endpoint
        sourceOffset orderOffset incoming rows =
      (inputScanFrom incoming rows).mapIdx fun index pfx =>
        { value :=
            base (sourceOffset + index) - coordinate pfx
          order := 2 * (orderOffset + index) + endpoint } := by
  induction rows generalizing sourceOffset orderOffset incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp only [affineCandidatesFrom, inputScanFrom, List.mapIdx_cons]
      congr 1
      simpa only [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm] using
        inductionHypothesis
          (sourceOffset + 1) (orderOffset + 1) (incoming + row)

/-- At source/order zero, the distributed capstone's right side is literally
the existing `rowCandidates` API applied to `inclusiveInputScan`. -/
theorem affineCandidatesFrom_zero_eq_rowCandidates
    (coordinate : PrefixMQ → Int) (base : Nat → Int)
    (endpoint : Nat) (rows : List PrefixMQ) :
    affineCandidatesFrom coordinate base endpoint
        0 0 PrefixMQ.zero rows =
      rowCandidates
        (fun index pfx => base index - coordinate pfx)
        endpoint (inclusiveInputScan rows) := by
  rw [affineCandidatesFrom_eq_scan_mapIdx]
  simp [rowCandidates, inclusiveInputScan]

/-- Affine candidates split exactly at a consecutive row boundary. -/
theorem affineCandidatesFrom_append
    (coordinate : PrefixMQ → Int) (base : Nat → Int)
    (endpoint sourceOffset orderOffset : Nat)
    (incoming : PrefixMQ) (left right : List PrefixMQ) :
    affineCandidatesFrom coordinate base endpoint
        sourceOffset orderOffset incoming (left ++ right) =
      affineCandidatesFrom coordinate base endpoint
          sourceOffset orderOffset incoming left ++
      affineCandidatesFrom coordinate base endpoint
          (sourceOffset + left.length)
          (orderOffset + left.length)
          (incoming + inputTotal left) right := by
  induction left generalizing sourceOffset orderOffset incoming with
  | nil =>
      simp [affineCandidatesFrom, inputTotal]
  | cons row rest inductionHypothesis =>
      simp only [List.cons_append, affineCandidatesFrom,
        List.length_cons, inputTotal]
      congr 1
      simpa only [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm,
        PrefixMQ.add_assoc] using
        inductionHypothesis
          (sourceOffset + 1) (orderOffset + 1) (incoming + row)

/-- Adding a state before every local prefix subtracts that state's
coordinate from every affine candidate and adds the worker's row offset to
every source order. -/
theorem affineCandidatesFrom_translate
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (base : Nat → Int) (endpoint sourceOffset orderOffset : Nat)
    (stateShift incoming : PrefixMQ) (rowShift : Nat)
    (rows : List PrefixMQ) :
    (affineCandidatesFrom coordinate base endpoint
        sourceOffset orderOffset incoming rows).map
        (shiftCandidate (-coordinate stateShift) rowShift) =
      affineCandidatesFrom coordinate base endpoint
        sourceOffset (rowShift + orderOffset)
        (stateShift + incoming) rows := by
  induction rows generalizing sourceOffset orderOffset incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp only [affineCandidatesFrom, List.map_cons]
      congr 1
      · simp only [shiftCandidate, OrderedCandidate.mk.injEq]
        constructor
        · rw [additive.2 incoming row,
            additive.2 (stateShift + incoming) row,
            additive.2 stateShift incoming]
          omega
        · omega
      · simpa only [PrefixMQ.add_assoc, Nat.add_assoc] using
          inductionHypothesis
            (sourceOffset + 1) (orderOffset + 1) (incoming + row)

/-- Evaluating a worker at an arbitrary proxy and then adding the proxy
coordinate back gives the canonical zero-based local candidate stream. -/
theorem affineCandidatesFrom_normalize_proxy
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (base : Nat → Int) (endpoint sourceOffset orderOffset : Nat)
    (proxy incoming : PrefixMQ) (rows : List PrefixMQ) :
    (affineCandidatesFrom coordinate base endpoint
        sourceOffset orderOffset (proxy + incoming) rows).map
        (shiftCandidate (coordinate proxy) 0) =
      affineCandidatesFrom coordinate base endpoint
        sourceOffset orderOffset incoming rows := by
  induction rows generalizing sourceOffset orderOffset incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp only [affineCandidatesFrom, List.map_cons]
      congr 1
      · simp only [shiftCandidate, OrderedCandidate.mk.injEq]
        constructor
        · rw [additive.2 (proxy + incoming) row,
            additive.2 proxy incoming,
            additive.2 incoming row]
          omega
        · omega
      · simpa only [PrefixMQ.add_assoc] using
          inductionHypothesis
            (sourceOffset + 1) (orderOffset + 1) (incoming + row)

/-- The exact production-shaped local candidate stream. -/
def localCandidates
    (coordinate : PrefixMQ → Int) (base : Nat → Int)
    (endpoint sourceOffset : Nat) (rows : List PrefixMQ) :
    List OrderedCandidate :=
  affineCandidatesFrom coordinate base endpoint
    sourceOffset 0 PrefixMQ.zero rows

/-- Candidate stream obtained by evaluating at, and then explicitly
normalizing away, an arbitrary worker proxy. -/
def proxyNormalizedCandidates
    (coordinate : PrefixMQ → Int) (base : Nat → Int)
    (endpoint sourceOffset : Nat) (proxy : PrefixMQ)
    (rows : List PrefixMQ) : List OrderedCandidate :=
  (affineCandidatesFrom coordinate base endpoint
      sourceOffset 0 proxy rows).map
    (shiftCandidate (coordinate proxy) 0)

/-- Proxy normalization is exact and has no guard-admissibility premise. -/
theorem proxyNormalizedCandidates_eq_local
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (base : Nat → Int) (endpoint sourceOffset : Nat)
    (proxy : PrefixMQ) (rows : List PrefixMQ) :
    proxyNormalizedCandidates coordinate base endpoint
        sourceOffset proxy rows =
      localCandidates coordinate base endpoint sourceOffset rows := by
  unfold proxyNormalizedCandidates localCandidates
  simpa [additive.1] using
    affineCandidatesFrom_normalize_proxy additive base endpoint
      sourceOffset 0 proxy PrefixMQ.zero rows

/-! ## Reduction algebra used by worker summaries -/

/-- Combine optional partial reductions. -/
def mergeReduced
    (key : OrderedCandidate → Int ×ₗ Nat) :
    Option OrderedCandidate → Option OrderedCandidate →
      Option OrderedCandidate
  | none, right => right
  | left, none => left
  | some left, some right => some (combineByKey key left right)

private theorem foldByKey_combine_of_assoc
    (key : OrderedCandidate → Int ×ₗ Nat)
    (associative :
      ∀ first second third,
        combineByKey key (combineByKey key first second) third =
          combineByKey key first (combineByKey key second third))
    (first second : OrderedCandidate)
    (candidates : List OrderedCandidate) :
    foldByKey key (combineByKey key first second) candidates =
      combineByKey key first (foldByKey key second candidates) := by
  induction candidates generalizing second with
  | nil => rfl
  | cons candidate rest inductionHypothesis =>
      change
        foldByKey key
            (combineByKey key
              (combineByKey key first second) candidate) rest =
          combineByKey key first
            (foldByKey key
              (combineByKey key second candidate) rest)
      rw [associative]
      exact inductionHypothesis (combineByKey key second candidate)

private theorem reduceByKey_append_of_assoc
    (key : OrderedCandidate → Int ×ₗ Nat)
    (associative :
      ∀ first second third,
        combineByKey key (combineByKey key first second) third =
          combineByKey key first (combineByKey key second third))
    (left right : List OrderedCandidate) :
    reduceByKey key (left ++ right) =
      mergeReduced key (reduceByKey key left) (reduceByKey key right) := by
  cases left with
  | nil => rfl
  | cons first rest =>
      cases right with
      | nil => simp [reduceByKey, mergeReduced]
      | cons second tail =>
          simp only [List.cons_append, reduceByKey, Option.some.injEq,
            mergeReduced]
          rw [foldByKey_append]
          change
            foldByKey key
                (combineByKey key
                  (foldByKey key first rest) second) tail =
              combineByKey key (foldByKey key first rest)
                (foldByKey key second tail)
          exact foldByKey_combine_of_assoc key associative
            (foldByKey key first rest) second tail

/-- Reducing consecutive maximum streams may be done worker by worker. -/
theorem reduceMaximum_append
    (left right : List OrderedCandidate) :
    reduceMaximum (left ++ right) =
      mergeReduced lowerKey
        (reduceMaximum left) (reduceMaximum right) := by
  exact reduceByKey_append_of_assoc lowerKey
    combineMaximum_assoc left right

/-- Reducing consecutive minimum streams may be done worker by worker. -/
theorem reduceMinimum_append
    (left right : List OrderedCandidate) :
    reduceMinimum (left ++ right) =
      mergeReduced upperKey
        (reduceMinimum left) (reduceMinimum right) := by
  exact reduceByKey_append_of_assoc upperKey
    combineMinimum_assoc left right

theorem lowerKey_shift_le_iff
    (valueShift : Int) (rowShift : Nat)
    (left right : OrderedCandidate) :
    lowerKey (shiftCandidate valueShift rowShift left) ≤
        lowerKey (shiftCandidate valueShift rowShift right) ↔
      lowerKey left ≤ lowerKey right := by
  rw [lowerKey_le_iff, lowerKey_le_iff]
  simp only [shiftCandidate_value, shiftCandidate_order]
  constructor <;> rintro ⟨value, tie⟩
  · constructor
    · omega
    · intro equality
      have shifted := tie (by omega)
      omega
  · constructor
    · omega
    · intro equality
      have shifted :=
        tie (by omega)
      omega

theorem upperKey_shift_le_iff
    (valueShift : Int) (rowShift : Nat)
    (left right : OrderedCandidate) :
    upperKey (shiftCandidate valueShift rowShift left) ≤
        upperKey (shiftCandidate valueShift rowShift right) ↔
      upperKey left ≤ upperKey right := by
  rw [upperKey_le_iff, upperKey_le_iff]
  simp only [shiftCandidate_value, shiftCandidate_order]
  constructor <;> rintro ⟨value, tie⟩
  · constructor
    · omega
    · intro equality
      have shifted := tie (by omega)
      omega
  · constructor
    · omega
    · intro equality
      have shifted :=
        tie (by omega)
      omega

private theorem shiftCandidate_combineMaximum
    (valueShift : Int) (rowShift : Nat)
    (left right : OrderedCandidate) :
    shiftCandidate valueShift rowShift
        (combineByKey lowerKey left right) =
      combineByKey lowerKey
        (shiftCandidate valueShift rowShift left)
        (shiftCandidate valueShift rowShift right) := by
  unfold combineByKey
  by_cases comparison : lowerKey left ≤ lowerKey right
  · have shiftedComparison :=
      (lowerKey_shift_le_iff valueShift rowShift left right).mpr
        comparison
    simp [comparison, shiftedComparison]
  · have shiftedComparison :
        ¬ lowerKey (shiftCandidate valueShift rowShift left) ≤
          lowerKey (shiftCandidate valueShift rowShift right) := by
      simpa [lowerKey_shift_le_iff] using comparison
    simp [comparison, shiftedComparison]

private theorem shiftCandidate_combineMinimum
    (valueShift : Int) (rowShift : Nat)
    (left right : OrderedCandidate) :
    shiftCandidate valueShift rowShift
        (combineByKey upperKey left right) =
      combineByKey upperKey
        (shiftCandidate valueShift rowShift left)
        (shiftCandidate valueShift rowShift right) := by
  unfold combineByKey
  by_cases comparison : upperKey left ≤ upperKey right
  · have shiftedComparison :=
      (upperKey_shift_le_iff valueShift rowShift left right).mpr
        comparison
    simp [comparison, shiftedComparison]
  · have shiftedComparison :
        ¬ upperKey (shiftCandidate valueShift rowShift left) ≤
          upperKey (shiftCandidate valueShift rowShift right) := by
      simpa [upperKey_shift_le_iff] using comparison
    simp [comparison, shiftedComparison]

private theorem shiftCandidate_foldMaximum
    (valueShift : Int) (rowShift : Nat)
    (initial : OrderedCandidate) (candidates : List OrderedCandidate) :
    shiftCandidate valueShift rowShift
        (foldByKey lowerKey initial candidates) =
      foldByKey lowerKey
        (shiftCandidate valueShift rowShift initial)
        (candidates.map (shiftCandidate valueShift rowShift)) := by
  induction candidates generalizing initial with
  | nil => rfl
  | cons candidate rest inductionHypothesis =>
      calc
        shiftCandidate valueShift rowShift
            (foldByKey lowerKey
              (combineByKey lowerKey initial candidate) rest) =
            foldByKey lowerKey
              (shiftCandidate valueShift rowShift
                (combineByKey lowerKey initial candidate))
              (rest.map (shiftCandidate valueShift rowShift)) :=
          inductionHypothesis
            (combineByKey lowerKey initial candidate)
        _ =
            foldByKey lowerKey
              (combineByKey lowerKey
                (shiftCandidate valueShift rowShift initial)
                (shiftCandidate valueShift rowShift candidate))
              (rest.map (shiftCandidate valueShift rowShift)) := by
          rw [shiftCandidate_combineMaximum]

private theorem shiftCandidate_foldMinimum
    (valueShift : Int) (rowShift : Nat)
    (initial : OrderedCandidate) (candidates : List OrderedCandidate) :
    shiftCandidate valueShift rowShift
        (foldByKey upperKey initial candidates) =
      foldByKey upperKey
        (shiftCandidate valueShift rowShift initial)
        (candidates.map (shiftCandidate valueShift rowShift)) := by
  induction candidates generalizing initial with
  | nil => rfl
  | cons candidate rest inductionHypothesis =>
      calc
        shiftCandidate valueShift rowShift
            (foldByKey upperKey
              (combineByKey upperKey initial candidate) rest) =
            foldByKey upperKey
              (shiftCandidate valueShift rowShift
                (combineByKey upperKey initial candidate))
              (rest.map (shiftCandidate valueShift rowShift)) :=
          inductionHypothesis
            (combineByKey upperKey initial candidate)
        _ =
            foldByKey upperKey
              (combineByKey upperKey
                (shiftCandidate valueShift rowShift initial)
                (shiftCandidate valueShift rowShift candidate))
              (rest.map (shiftCandidate valueShift rowShift)) := by
          rw [shiftCandidate_combineMinimum]

/-- Translating a complete local maximum stream is equivalent to translating
only its deterministic winner. -/
theorem reduceMaximum_map_shift
    (valueShift : Int) (rowShift : Nat)
    (candidates : List OrderedCandidate) :
    reduceMaximum
        (candidates.map (shiftCandidate valueShift rowShift)) =
      (reduceMaximum candidates).map
        (shiftCandidate valueShift rowShift) := by
  cases candidates with
  | nil => rfl
  | cons first rest =>
      simp only [List.map_cons, reduceMaximum, reduceByKey,
        Option.map_some, Option.some.injEq]
      exact (shiftCandidate_foldMaximum
        valueShift rowShift first rest).symm

/-- Translating a complete local minimum stream is equivalent to translating
only its deterministic winner. -/
theorem reduceMinimum_map_shift
    (valueShift : Int) (rowShift : Nat)
    (candidates : List OrderedCandidate) :
    reduceMinimum
        (candidates.map (shiftCandidate valueShift rowShift)) =
      (reduceMinimum candidates).map
        (shiftCandidate valueShift rowShift) := by
  cases candidates with
  | nil => rfl
  | cons first rest =>
      simp only [List.map_cons, reduceMinimum, reduceByKey,
        Option.map_some, Option.some.injEq]
      exact (shiftCandidate_foldMinimum
        valueShift rowShift first rest).symm

/-! ## Worker summaries and the real exclusive scan -/

/-- One consecutive worker's exact rows and its independently chosen proxy
incoming state.  Contiguity is represented by list order: concatenating
`rows` is the complete source range. -/
structure WorkerChunk where
  rows : List PrefixMQ
  proxy : PrefixMQ
  deriving Repr, DecidableEq

/-- Exact row stream covered by a list of consecutive workers. -/
def workerRows (workers : List WorkerChunk) : List PrefixMQ :=
  (workers.map WorkerChunk.rows).flatten

/-- The arithmetic portion of one worker terminal.  Lower guard candidates
are reduced by the maximum key and upper guard candidates by the minimum key.
Both are explicitly normalized away from the recorded proxy. -/
structure WorkerSummary where
  proxy : PrefixMQ
  delta : PrefixMQ
  lowerGuard : Option OrderedCandidate
  upperGuard : Option OrderedCandidate
  deriving DecidableEq

/-- Pure worker summary for one affine coordinate. -/
def workerSummary
    (coordinate : PrefixMQ → Int)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint sourceOffset : Nat)
    (worker : WorkerChunk) : WorkerSummary :=
  { proxy := worker.proxy
    delta := inputTotal worker.rows
    lowerGuard :=
      reduceMaximum
        (proxyNormalizedCandidates coordinate lowerBase
          lowerEndpoint sourceOffset worker.proxy worker.rows)
    upperGuard :=
      reduceMinimum
        (proxyNormalizedCandidates coordinate upperBase
          upperEndpoint sourceOffset worker.proxy worker.rows) }

@[simp] theorem workerSummary_delta
    (coordinate : PrefixMQ → Int)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint sourceOffset : Nat)
    (worker : WorkerChunk) :
    (workerSummary coordinate lowerBase upperBase
      lowerEndpoint upperEndpoint sourceOffset worker).delta =
        inputTotal worker.rows := rfl

theorem workerSummary_lower_eq_local
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint sourceOffset : Nat)
    (worker : WorkerChunk) :
    (workerSummary coordinate lowerBase upperBase
        lowerEndpoint upperEndpoint sourceOffset worker).lowerGuard =
      reduceMaximum
        (localCandidates coordinate lowerBase
          lowerEndpoint sourceOffset worker.rows) := by
  simp only [workerSummary]
  rw [proxyNormalizedCandidates_eq_local additive]

theorem workerSummary_upper_eq_local
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint sourceOffset : Nat)
    (worker : WorkerChunk) :
    (workerSummary coordinate lowerBase upperBase
        lowerEndpoint upperEndpoint sourceOffset worker).upperGuard =
      reduceMinimum
        (localCandidates coordinate upperBase
          upperEndpoint sourceOffset worker.rows) := by
  simp only [workerSummary]
  rw [proxyNormalizedCandidates_eq_local additive]

/-- All arithmetic fields of a worker summary are independent of the proxy.
The proxy remains in the receipt for auditability, but is not used as a
sequential state or as a proof premise. -/
theorem workerSummary_arithmetic_independent_of_proxy
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint sourceOffset : Nat)
    (rows : List PrefixMQ) (firstProxy secondProxy : PrefixMQ) :
    let first :=
      workerSummary coordinate lowerBase upperBase
        lowerEndpoint upperEndpoint sourceOffset
        ⟨rows, firstProxy⟩
    let second :=
      workerSummary coordinate lowerBase upperBase
        lowerEndpoint upperEndpoint sourceOffset
        ⟨rows, secondProxy⟩
    first.delta = second.delta ∧
      first.lowerGuard = second.lowerGuard ∧
      first.upperGuard = second.upperGuard := by
  dsimp
  constructor
  · rfl
  constructor
  · rw [workerSummary_lower_eq_local additive,
      workerSummary_lower_eq_local additive]
  · rw [workerSummary_upper_eq_local additive,
      workerSummary_upper_eq_local additive]

/-- Exact exclusive scan of worker deltas, starting at the real CPU handoff.
The proxy field is deliberately ignored. -/
def workerIncomingStates :
    PrefixMQ → List WorkerChunk → List PrefixMQ
  | _, [] => []
  | incoming, worker :: rest =>
      incoming ::
        workerIncomingStates
          (incoming + inputTotal worker.rows) rest

/-- State after every consecutive worker delta has been applied. -/
def workerFinalState :
    PrefixMQ → List WorkerChunk → PrefixMQ
  | incoming, [] => incoming
  | incoming, worker :: rest =>
      workerFinalState
        (incoming + inputTotal worker.rows) rest

@[simp] theorem workerIncomingStates_length
    (incoming : PrefixMQ) (workers : List WorkerChunk) :
    (workerIncomingStates incoming workers).length =
      workers.length := by
  induction workers generalizing incoming with
  | nil => rfl
  | cons worker rest inductionHypothesis =>
      simp [workerIncomingStates, inductionHypothesis]

/-- Every emitted worker input is the CPU handoff plus the total of exactly
the preceding worker rows. -/
theorem workerIncomingStates_getElem
    (handoff : PrefixMQ) (workers : List WorkerChunk)
    (index : Nat) (inRange : index < workers.length) :
    (workerIncomingStates handoff workers)[index]'(by simpa using inRange) =
      handoff +
        inputTotal (workerRows (workers.take index)) := by
  induction workers generalizing handoff index with
  | nil => simp at inRange
  | cons worker rest inductionHypothesis =>
      cases index with
      | zero =>
          simp [workerIncomingStates, workerRows, inputTotal]
      | succ index =>
          simp only [List.length_cons, Nat.succ_lt_succ_iff] at inRange
          simp only [workerIncomingStates, List.getElem_cons_succ]
          rw [inductionHypothesis
            (handoff + inputTotal worker.rows) index inRange]
          simp only [List.take_succ_cons, workerRows, List.map_cons,
            List.flatten_cons, inputTotal_append]
          exact PrefixMQ.add_assoc _ _ _

/-- Distributed exclusive scans concatenate exactly; the right batch starts
at the final state of the left batch. -/
theorem workerIncomingStates_append
    (incoming : PrefixMQ)
    (left right : List WorkerChunk) :
    workerIncomingStates incoming (left ++ right) =
      workerIncomingStates incoming left ++
        workerIncomingStates
          (workerFinalState incoming left) right := by
  induction left generalizing incoming with
  | nil => rfl
  | cons worker rest inductionHypothesis =>
      simp only [List.cons_append, workerIncomingStates,
        workerFinalState, List.cons.injEq, true_and]
      exact inductionHypothesis
        (incoming + inputTotal worker.rows)

/-- The terminal exclusive-scan state is the CPU handoff plus the exact total
of the single concatenated row stream. -/
theorem workerFinalState_eq_handoff_add_total
    (handoff : PrefixMQ) (workers : List WorkerChunk) :
    workerFinalState handoff workers =
      handoff + inputTotal (workerRows workers) := by
  induction workers generalizing handoff with
  | nil =>
      simp [workerFinalState, workerRows, inputTotal]
  | cons worker rest inductionHypothesis =>
      simp only [workerFinalState, workerRows, List.map_cons,
        List.flatten_cons, inputTotal_append]
      rw [inductionHypothesis]
      exact PrefixMQ.add_assoc _ _ _

/-- Translating a worker's zero-based stream by the exact cumulative delta
produces precisely the corresponding segment of the one global stream. -/
theorem localCandidates_translate_to_global
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (base : Nat → Int) (endpoint sourceOffset rowOffset : Nat)
    (cumulative : PrefixMQ) (rows : List PrefixMQ) :
    (localCandidates coordinate base endpoint sourceOffset rows).map
        (shiftCandidate (-coordinate cumulative) rowOffset) =
      affineCandidatesFrom coordinate base endpoint
        sourceOffset rowOffset cumulative rows := by
  unfold localCandidates
  simpa [additive.1] using
    affineCandidatesFrom_translate additive base endpoint
      sourceOffset 0 cumulative PrefixMQ.zero rowOffset rows

/-- A translated local lower/upper pair contains the original CPU handoff
exactly when the unshifted pair contains that worker's real incoming state.
The worker proxy is absent from both sides. -/
theorem translatedGuard_contains_handoff_iff
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (handoff cumulative : PrefixMQ) (rowOffset : Nat)
    (lower upper : OrderedCandidate) :
    let translatedLower :=
      shiftCandidate (-coordinate cumulative) rowOffset lower
    let translatedUpper :=
      shiftCandidate (-coordinate cumulative) rowOffset upper
    translatedLower.value ≤ coordinate handoff ∧
        coordinate handoff ≤ translatedUpper.value ↔
      lower.value ≤ coordinate (handoff + cumulative) ∧
        coordinate (handoff + cumulative) ≤ upper.value := by
  dsimp only [shiftCandidate]
  rw [additive.2]
  omega

/-! ## Ordered n-worker composition -/

/-- Compose worker lower extrema in source order.  `cumulative` is the exact
exclusive scan from zero; the corresponding real incoming state is
`handoff + cumulative`. -/
def composeWorkerMaximum
    (coordinate : PrefixMQ → Int)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat) :
    Nat → PrefixMQ → List WorkerChunk → Option OrderedCandidate
  | _, _, [] => none
  | sourceOffset, cumulative, worker :: rest =>
      let summary :=
        workerSummary coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint sourceOffset worker
      let translated :=
        summary.lowerGuard.map
          (shiftCandidate (-coordinate cumulative) sourceOffset)
      mergeReduced lowerKey translated
        (composeWorkerMaximum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint
          (sourceOffset + worker.rows.length)
          (cumulative + summary.delta) rest)

/-- Compose worker upper extrema in source order. -/
def composeWorkerMinimum
    (coordinate : PrefixMQ → Int)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat) :
    Nat → PrefixMQ → List WorkerChunk → Option OrderedCandidate
  | _, _, [] => none
  | sourceOffset, cumulative, worker :: rest =>
      let summary :=
        workerSummary coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint sourceOffset worker
      let translated :=
        summary.upperGuard.map
          (shiftCandidate (-coordinate cumulative) sourceOffset)
      mergeReduced upperKey translated
        (composeWorkerMinimum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint
          (sourceOffset + worker.rows.length)
          (cumulative + summary.delta) rest)

private theorem composeWorkerMaximum_eq_singleFrom
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint sourceOffset : Nat)
    (cumulative : PrefixMQ) (workers : List WorkerChunk) :
    composeWorkerMaximum coordinate lowerBase upperBase
        lowerEndpoint upperEndpoint sourceOffset cumulative workers =
      reduceMaximum
        (affineCandidatesFrom coordinate lowerBase lowerEndpoint
          sourceOffset sourceOffset cumulative (workerRows workers)) := by
  induction workers generalizing sourceOffset cumulative with
  | nil =>
      rfl
  | cons worker rest inductionHypothesis =>
      simp only [composeWorkerMaximum, workerRows, List.map_cons,
        List.flatten_cons]
      rw [workerSummary_lower_eq_local additive]
      rw [← reduceMaximum_map_shift
        (-coordinate cumulative) sourceOffset]
      rw [localCandidates_translate_to_global additive]
      rw [workerSummary_delta]
      rw [inductionHypothesis
        (sourceOffset + worker.rows.length)
        (cumulative + inputTotal worker.rows)]
      rw [← reduceMaximum_append]
      rw [← affineCandidatesFrom_append]
      rfl

private theorem composeWorkerMinimum_eq_singleFrom
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint sourceOffset : Nat)
    (cumulative : PrefixMQ) (workers : List WorkerChunk) :
    composeWorkerMinimum coordinate lowerBase upperBase
        lowerEndpoint upperEndpoint sourceOffset cumulative workers =
      reduceMinimum
        (affineCandidatesFrom coordinate upperBase upperEndpoint
          sourceOffset sourceOffset cumulative (workerRows workers)) := by
  induction workers generalizing sourceOffset cumulative with
  | nil =>
      rfl
  | cons worker rest inductionHypothesis =>
      simp only [composeWorkerMinimum, workerRows, List.map_cons,
        List.flatten_cons]
      rw [workerSummary_upper_eq_local additive]
      rw [← reduceMinimum_map_shift
        (-coordinate cumulative) sourceOffset]
      rw [localCandidates_translate_to_global additive]
      rw [workerSummary_delta]
      rw [inductionHypothesis
        (sourceOffset + worker.rows.length)
        (cumulative + inputTotal worker.rows)]
      rw [← reduceMinimum_append]
      rw [← affineCandidatesFrom_append]
      rfl

/-- Generic distributed-composition theorem.  It applies to any number of
consecutive workers, including the production count eight.  The right side
is one exact zero-based scan and deterministic reduction of all concatenated
rows.  No proxy guard is assumed. -/
theorem nWorkerComposition_eq_single
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat)
    (workers : List WorkerChunk) :
    composeWorkerMaximum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMaximum
          (affineCandidatesFrom coordinate lowerBase lowerEndpoint
            0 0 PrefixMQ.zero (workerRows workers)) ∧
      composeWorkerMinimum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMinimum
          (affineCandidatesFrom coordinate upperBase upperEndpoint
            0 0 PrefixMQ.zero (workerRows workers)) := by
  constructor
  · exact composeWorkerMaximum_eq_singleFrom additive
      lowerBase upperBase lowerEndpoint upperEndpoint
      0 PrefixMQ.zero workers
  · exact composeWorkerMinimum_eq_singleFrom additive
      lowerBase upperBase lowerEndpoint upperEndpoint
      0 PrefixMQ.zero workers

/-- The same capstone stated directly with the already audited
`inclusiveInputScan` and `rowCandidates` definitions. -/
theorem nWorkerComposition_eq_inclusiveInputScan
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat)
    (workers : List WorkerChunk) :
    composeWorkerMaximum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMaximum
          (rowCandidates
            (fun index pfx =>
              lowerBase index - coordinate pfx)
            lowerEndpoint
            (inclusiveInputScan (workerRows workers))) ∧
      composeWorkerMinimum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMinimum
          (rowCandidates
            (fun index pfx =>
              upperBase index - coordinate pfx)
            upperEndpoint
            (inclusiveInputScan (workerRows workers))) := by
  have composed :=
    nWorkerComposition_eq_single additive lowerBase upperBase
      lowerEndpoint upperEndpoint workers
  constructor
  · calc
      composeWorkerMaximum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
          reduceMaximum
            (affineCandidatesFrom coordinate lowerBase lowerEndpoint
              0 0 PrefixMQ.zero (workerRows workers)) := composed.1
      _ = reduceMaximum
          (rowCandidates
            (fun index pfx =>
              lowerBase index - coordinate pfx)
            lowerEndpoint
            (inclusiveInputScan (workerRows workers))) := by
        rw [affineCandidatesFrom_zero_eq_rowCandidates]
  · calc
      composeWorkerMinimum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
          reduceMinimum
            (affineCandidatesFrom coordinate upperBase upperEndpoint
              0 0 PrefixMQ.zero (workerRows workers)) := composed.2
      _ = reduceMinimum
          (rowCandidates
            (fun index pfx =>
              upperBase index - coordinate pfx)
            upperEndpoint
            (inclusiveInputScan (workerRows workers))) := by
        rw [affineCandidatesFrom_zero_eq_rowCandidates]

/-- Production-shaped specialization: eight workers have exactly the same
winner and earliest source-order tie as the single concatenated reduction. -/
theorem eightWorkerComposition_eq_single
    {coordinate : PrefixMQ → Int}
    (additive : CoordinateAdditive coordinate)
    (lowerBase upperBase : Nat → Int)
    (lowerEndpoint upperEndpoint : Nat)
    (workers : List WorkerChunk)
    (_eightWorkers : workers.length = 8) :
    composeWorkerMaximum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMaximum
          (affineCandidatesFrom coordinate lowerBase lowerEndpoint
            0 0 PrefixMQ.zero (workerRows workers)) ∧
      composeWorkerMinimum coordinate lowerBase upperBase
          lowerEndpoint upperEndpoint 0 PrefixMQ.zero workers =
        reduceMinimum
          (affineCandidatesFrom coordinate upperBase upperEndpoint
            0 0 PrefixMQ.zero (workerRows workers)) :=
  nWorkerComposition_eq_single additive lowerBase upperBase
    lowerEndpoint upperEndpoint workers

end SparkInterval.TernaryGoldbach.HurstAffineClusterComposition
