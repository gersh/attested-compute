/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CStepRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CRosterRefinement

/-!
# Successful C-source power-layout refinement for Sqrt218 V2

This module gives a relational model of the successful path through
`tg_sq218_validate_power_layout_v2`.  It retains both source loops:

* the event loop, including checked power, square-root, bound, and strict
  ordering guards; and
* the per-prime inverse-map loop, including the sequential power-reference
  cursor, every prime/exponent cell, and the terminal maximal-power guard.

The final theorem proves the exact `Operational.V2.powerLayoutCheck` on
`V2Adapter.V2.layout`.  It is symbolic in an arbitrary decoded image and
does not load or replay a production certificate.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPowerLayoutRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPrimitives
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRosterRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

/-! ## Exact adapter views -/

def cEvent (image : ArchiveImage) (index : Nat) : EventRecord :=
  image.events.getD index default

def cPowerRefsAt (image : ArchiveImage) (rowIndex : Nat) : List Nat :=
  let row := cRow image rowIndex
  (image.powerRefs.drop row.powerRefIndex).take row.powerRefCount

def cLastPower (image : ArchiveImage) (rowIndex : Nat) : Nat :=
  let row := cRow image rowIndex
  let references := cPowerRefsAt image rowIndex
  let eventIndex := references.getD (row.powerRefCount - 1) 0
  (cEvent image eventIndex).value

theorem layout_eventCount (image : ArchiveImage) :
    (V2.layout image).eventCount = image.events.length := by
  simp [V2.layout, PowerLayoutCertificate.eventCount]

theorem layout_eventAt (image : ArchiveImage) (index : Nat) :
    (V2.layout image).eventAt index =
      V2.powerEvent (cEvent image index) := by
  unfold PowerLayoutCertificate.eventAt V2.layout cEvent
  change
    (image.events.map V2.powerEvent).getD index
        (V2.powerEvent default) =
      V2.powerEvent (image.events.getD index default)
  rw [List.getD_map]

theorem layout_powerIndicesAt
    (image : ArchiveImage) {rowIndex : Nat}
    (hindex : rowIndex < image.primes.length) :
    (V2.layout image).powerIndicesAt rowIndex =
      cPowerRefsAt image rowIndex := by
  unfold PowerLayoutCertificate.powerIndicesAt V2.layout
  rw [List.getD_eq_getElem _ _ (by simpa using hindex)]
  simp only [List.getElem_map, List.getElem_range]
  rfl

/-! ## Accepted event loop -/

/-- Successful guards for one C event-loop iteration.  `powerRun` is the
literal `tg_pow_u64_checked` source loop and `sqrtOK` is the literal
division-based `tg_floor_sqrt_ok` predicate. -/
structure CPowerEventAccepted
    (image : ArchiveImage) (index previousValue : Nat) : Prop where
  indexLt : index < image.events.length
  primeIndexLt :
    (cEvent image index).primeIndex < image.primes.length
  valueFits :
    (cEvent image index).value < limbBase
  primeFits :
    (cRow image (cEvent image index).primeIndex).prime < limbBase
  exponentFits :
    (cEvent image index).exponent < uint32Base
  floorSqrtFits :
    (cEvent image index).floorSqrt < limbBase
  exponentPositive :
    0 < (cEvent image index).exponent
  valueAtMostBound :
    (cEvent image index).value ≤ image.header.bound
  sqrtOK :
    cFloorSqrtOK
      (cEvent image index).value
      (cEvent image index).floorSqrt
  powerRun :
    cPowChecked
        (cRow image (cEvent image index).primeIndex).prime
        (cEvent image index).exponent =
      some (cEvent image index).value
  ordered :
    index = 0 ∨ previousValue < (cEvent image index).value

structure CPowerEventFacts
    (image : ArchiveImage) (index : Nat) : Prop where
  valueAtMostBound :
    (cEvent image index).value ≤ image.header.bound
  primeIndexLt :
    (cEvent image index).primeIndex < image.primes.length
  exponentPositive :
    0 < (cEvent image index).exponent
  valueEq :
    (cEvent image index).value =
      (cRow image (cEvent image index).primeIndex).prime ^
        (cEvent image index).exponent
  floorSqrtEq :
    (cEvent image index).floorSqrt =
      Nat.sqrt (cEvent image index).value

theorem CPowerEventAccepted.facts
    {image : ArchiveImage} {index previousValue : Nat}
    (accepted :
      CPowerEventAccepted image index previousValue) :
    CPowerEventFacts image index := by
  have hpower :=
    cPowChecked_value accepted.primeFits accepted.powerRun
  exact {
    valueAtMostBound := accepted.valueAtMostBound
    primeIndexLt := accepted.primeIndexLt
    exponentPositive := accepted.exponentPositive
    valueEq := hpower.2
    floorSqrtEq := cFloorSqrtOK_eq_sqrt accepted.sqrtOK
  }

theorem CPowerEventAccepted.refines_cell
    {image : ArchiveImage} {index previousValue : Nat}
    (accepted :
      CPowerEventAccepted image index previousValue) :
    powerEventCellCheck
        image.header.bound
        (V2.roster image).count
        (V2.roster image).primeAt
        (V2.layout image)
        index =
      true := by
  have facts := accepted.facts
  unfold powerEventCellCheck
  rw [layout_eventAt, roster_count]
  simp only [V2.powerEvent, decide_eq_true_eq]
  rw [roster_primeAt]
  exact
    ⟨facts.valueAtMostBound, facts.primeIndexLt,
      facts.exponentPositive, facts.valueEq, facts.floorSqrtEq⟩

def cPreviousEventValue
    (image : ArchiveImage) (count : Nat) : Nat :=
  if count = 0 then 0 else (cEvent image (count - 1)).value

/-- Successful prefix of the source event loop.  The second index is the
current C local `previous_value`. -/
inductive CPowerEventTrace (image : ArchiveImage) :
    Nat → Nat → Prop
  | nil :
      CPowerEventTrace image 0 0
  | step
      {index previousValue : Nat}
      (priorTrace :
        CPowerEventTrace image index previousValue)
      (accepted :
        CPowerEventAccepted image index previousValue) :
      CPowerEventTrace image
        (index + 1) (cEvent image index).value

theorem CPowerEventTrace.previousValue
    {image : ArchiveImage} {count previousValue : Nat}
    (trace : CPowerEventTrace image count previousValue) :
    previousValue = cPreviousEventValue image count := by
  cases trace with
  | nil =>
      rfl
  | @step index previousValue priorTrace accepted =>
      simp [cPreviousEventValue]

theorem CPowerEventTrace.facts
    {image : ArchiveImage} {count previousValue : Nat}
    (trace : CPowerEventTrace image count previousValue) :
    ∀ index, index < count → CPowerEventFacts image index := by
  induction trace with
  | nil =>
      intro index hindex
      omega
  | @step count previousValue
      priorTrace accepted inductionHypothesis =>
      intro index hindex
      by_cases hbefore : index < count
      · exact inductionHypothesis index hbefore
      · have hequal : index = count := by omega
        subst index
        exact accepted.facts

theorem CPowerEventTrace.cells
    {image : ArchiveImage} {count previousValue : Nat}
    (trace : CPowerEventTrace image count previousValue) :
    ∀ index, index < count →
      powerEventCellCheck
          image.header.bound
          (V2.roster image).count
          (V2.roster image).primeAt
          (V2.layout image)
          index =
        true := by
  induction trace with
  | nil =>
      intro index hindex
      omega
  | @step count previousValue
      priorTrace accepted inductionHypothesis =>
      intro index hindex
      by_cases hbefore : index < count
      · exact inductionHypothesis index hbefore
      · have hequal : index = count := by omega
        subst index
        exact accepted.refines_cell

theorem CPowerEventTrace.adjacent
    {image : ArchiveImage} {count previousValue : Nat}
    (trace : CPowerEventTrace image count previousValue) :
    ∀ index, index + 1 < count →
      powerEventAdjacentCheck (V2.layout image) index = true := by
  induction trace with
  | nil =>
      intro index hindex
      omega
  | @step count previousValue
      priorTrace accepted inductionHypothesis =>
      intro index hindex
      by_cases hbefore : index + 1 < count
      · exact inductionHypothesis index hbefore
      · have hequal : index + 1 = count := by omega
        have hcountPositive : 0 < count := by omega
        have hnotFirst : count ≠ 0 := Nat.ne_of_gt hcountPositive
        have hordered :
            previousValue < (cEvent image count).value := by
          rcases accepted.ordered with hfirst | hordered
          · exact (hnotFirst hfirst).elim
          · exact hordered
        have hprevious := priorTrace.previousValue
        simp [cPreviousEventValue, hnotFirst] at hprevious
        unfold powerEventAdjacentCheck
        rw [layout_eventAt, layout_eventAt]
        simp only [V2.powerEvent, decide_eq_true_eq]
        have hindexPrevious : index = count - 1 := by omega
        rw [hindexPrevious, ← hprevious]
        simpa [Nat.sub_add_cancel (by omega : 1 ≤ count)] using
          hordered

/-! ## Accepted per-prime inverse-map loop -/

/-- Rejection of `tg_u64_mul_checked` is an actual mathematical overflow,
not wrapped multiplication. -/
theorem cWordMulChecked_none_overflow
    {left right : Nat}
    (_hleft : left < limbBase)
    (_hright : right < limbBase)
    (hrun : cWordMulChecked left right = none) :
    limbBase ≤ left * right := by
  change CPrimitives.wordMulChecked left right = none at hrun
  unfold CPrimitives.wordMulChecked at hrun
  by_cases hoverflow :
      left ≠ 0 ∧ wordMax / left < right
  · rw [if_pos hoverflow] at hrun
    have hleftPositive : 0 < left :=
      Nat.zero_lt_of_ne_zero hoverflow.1
    have hproduct :
        wordMax < right * left :=
      (Nat.div_lt_iff_lt_mul hleftPositive).mp hoverflow.2
    rw [Nat.mul_comm] at hproduct
    dsimp only [limbBase, wordMax] at hproduct ⊢
    omega
  · rw [if_neg hoverflow] at hrun
    contradiction

/-- Successful source conditions for one row of the inverse-map loop.

`references` is the literal per-reference loop.  `nextPowerGuard` preserves
the final C disjunction: multiplication overflow, or a representable next
power strictly beyond the bound.
-/
structure CPowerRowAccepted
    (image : ArchiveImage) (rowIndex nextPowerRef : Nat) : Prop where
  indexLt :
    rowIndex < image.primes.length
  powerCursor :
    (cRow image rowIndex).powerRefIndex = nextPowerRef
  primeFits :
    (cRow image rowIndex).prime < limbBase
  countFits :
    (cRow image rowIndex).powerRefCount < uint32Base
  countPositive :
    0 < (cRow image rowIndex).powerRefCount
  powerEndFits :
    (cRow image rowIndex).powerRefIndex +
        (cRow image rowIndex).powerRefCount <
      limbBase
  powerEndInside :
    (cRow image rowIndex).powerRefIndex +
        (cRow image rowIndex).powerRefCount ≤
      image.powerRefs.length
  references :
    ∀ exponentIndex,
      exponentIndex < (cRow image rowIndex).powerRefCount →
        let eventIndex :=
          (cPowerRefsAt image rowIndex).getD exponentIndex 0
        eventIndex < image.events.length ∧
          (cEvent image eventIndex).primeIndex = rowIndex ∧
          (cEvent image eventIndex).exponent = exponentIndex + 1
  lastPowerFits :
    cLastPower image rowIndex < limbBase
  lastPowerAtMostBound :
    cLastPower image rowIndex ≤ image.header.bound
  nextPowerGuard :
    cWordMulChecked
        (cLastPower image rowIndex)
        (cRow image rowIndex).prime =
      none ∨
      ∃ nextPower,
        cWordMulChecked
            (cLastPower image rowIndex)
            (cRow image rowIndex).prime =
          some nextPower ∧
        image.header.bound < nextPower

theorem CPowerRowAccepted.powerRefsLength
    {image : ArchiveImage} {rowIndex nextPowerRef : Nat}
    (accepted :
      CPowerRowAccepted image rowIndex nextPowerRef) :
    (cPowerRefsAt image rowIndex).length =
      (cRow image rowIndex).powerRefCount := by
  have hend := accepted.powerEndInside
  simp only [cPowerRefsAt, List.length_take, List.length_drop]
  omega

theorem CPowerRowAccepted.targetPowerIndices
    {image : ArchiveImage} {rowIndex nextPowerRef : Nat}
    (accepted :
      CPowerRowAccepted image rowIndex nextPowerRef) :
    (V2.layout image).powerIndicesAt rowIndex =
      cPowerRefsAt image rowIndex :=
  layout_powerIndicesAt image accepted.indexLt

theorem CPowerRowAccepted.targetPowerCount
    {image : ArchiveImage} {rowIndex nextPowerRef : Nat}
    (accepted :
      CPowerRowAccepted image rowIndex nextPowerRef) :
    (V2.layout image).powerCountAt rowIndex =
      (cRow image rowIndex).powerRefCount := by
  unfold PowerLayoutCertificate.powerCountAt
  rw [accepted.targetPowerIndices, accepted.powerRefsLength]

theorem CPowerRowAccepted.targetCanonicalIndex
    {image : ArchiveImage} {rowIndex nextPowerRef exponentIndex : Nat}
    (accepted :
      CPowerRowAccepted image rowIndex nextPowerRef) :
    (V2.layout image).canonicalIndexAt rowIndex exponentIndex =
      (cPowerRefsAt image rowIndex).getD exponentIndex 0 := by
  unfold PowerLayoutCertificate.canonicalIndexAt
  rw [accepted.targetPowerIndices]

theorem CPowerRowAccepted.lastPower_eq_primePow
    {image : ArchiveImage} {rowIndex nextPowerRef : Nat}
    (accepted :
      CPowerRowAccepted image rowIndex nextPowerRef)
    {previousValue : Nat}
    (events :
      CPowerEventTrace image image.events.length previousValue) :
    cLastPower image rowIndex =
      (cRow image rowIndex).prime ^
        (cRow image rowIndex).powerRefCount := by
  let count := (cRow image rowIndex).powerRefCount
  let exponentIndex := count - 1
  let eventIndex :=
    (cPowerRefsAt image rowIndex).getD exponentIndex 0
  have hcountPositive : 0 < count := by
    simpa only [count] using accepted.countPositive
  have hexponentIndex : exponentIndex < count := by
    dsimp only [exponentIndex]
    omega
  have hreference :=
    accepted.references exponentIndex (by
      simpa only [count] using hexponentIndex)
  have heventFacts :=
    events.facts eventIndex (by
      simpa only [eventIndex] using hreference.1)
  change
    (cEvent image eventIndex).value =
      (cRow image rowIndex).prime ^ count
  rw [heventFacts.valueEq, hreference.2.1, hreference.2.2]
  simp only [exponentIndex]
  rw [Nat.sub_add_cancel (by omega : 1 ≤ count)]

theorem CPowerRowAccepted.refines_index_cell
    {image : ArchiveImage} {rowIndex nextPowerRef exponentIndex : Nat}
    (accepted :
      CPowerRowAccepted image rowIndex nextPowerRef)
    (hindex :
      exponentIndex < (cRow image rowIndex).powerRefCount) :
    powerIndexCellCheck
        (V2.layout image) rowIndex exponentIndex =
      true := by
  have hreference := accepted.references exponentIndex hindex
  let reference :=
    (cPowerRefsAt image rowIndex).getD exponentIndex 0
  unfold powerIndexCellCheck
  rw [accepted.targetCanonicalIndex]
  change
    decide (
      reference < (V2.layout image).eventCount ∧
        ((V2.layout image).eventAt reference).primeIndex =
          rowIndex ∧
        ((V2.layout image).eventAt reference).exponent =
          exponentIndex + 1) =
      true
  rw [layout_eventAt, layout_eventCount]
  simp only [V2.powerEvent, decide_eq_true_eq]
  simpa only [reference] using hreference

theorem CPowerRowAccepted.refines_row
    {image : ArchiveImage} {rowIndex nextPowerRef : Nat}
    (accepted :
      CPowerRowAccepted image rowIndex nextPowerRef)
    {previousValue : Nat}
    (events :
      CPowerEventTrace image image.events.length previousValue)
    (hboundFits : image.header.bound < limbBase) :
    powerIndexRowCheck
        image.header.bound
        (V2.roster image).primeAt
        (V2.layout image)
        rowIndex =
      true := by
  have hlast := accepted.lastPower_eq_primePow events
  have hcount := accepted.targetPowerCount
  unfold powerIndexRowCheck
  rw [hcount, roster_primeAt]
  simp only [Bool.and_eq_true, decide_eq_true_eq]
  constructor
  · refine
      ⟨accepted.countPositive,
        ?_, ?_⟩
    · rw [← hlast]
      exact accepted.lastPowerAtMostBound
    · have hproduct :
          cLastPower image rowIndex *
              (cRow image rowIndex).prime =
            (cRow image rowIndex).prime ^
              ((cRow image rowIndex).powerRefCount + 1) := by
        rw [hlast, pow_succ]
      rcases accepted.nextPowerGuard with
        hoverflow | ⟨nextPower, hnext, hbeyond⟩
      · have hoverflowBound :=
          cWordMulChecked_none_overflow
            accepted.lastPowerFits accepted.primeFits hoverflow
        rw [← hproduct]
        exact hboundFits.trans_le hoverflowBound
      · have hnextSound :=
          cWordMulChecked_sound
            accepted.lastPowerFits accepted.primeFits hnext
        rw [← hproduct, ← hnextSound.2]
        exact hbeyond
  · unfold checkRange
    simp only [List.all_eq_true, List.mem_range, Nat.zero_add]
    intro exponentIndex hindex
    exact accepted.refines_index_cell hindex

/-! ## Forward row trace -/

inductive CPowerRowTrace (image : ArchiveImage) :
    Nat → Nat → Prop
  | nil :
      CPowerRowTrace image 0 0
  | step
      {rowIndex nextPowerRef : Nat}
      (priorTrace :
        CPowerRowTrace image rowIndex nextPowerRef)
      (accepted :
        CPowerRowAccepted image rowIndex nextPowerRef) :
      CPowerRowTrace image
        (rowIndex + 1)
        (nextPowerRef + (cRow image rowIndex).powerRefCount)

def cUsedPowerRefCount
    (image : ArchiveImage) (rowCount : Nat) : Nat :=
  ((image.primes.map PrimeRecord.powerRefCount).take rowCount).sum

theorem CPowerRowTrace.powerCursor
    {image : ArchiveImage} {rowCount nextPowerRef : Nat}
    (trace : CPowerRowTrace image rowCount nextPowerRef) :
    nextPowerRef = cUsedPowerRefCount image rowCount := by
  induction trace with
  | nil =>
      rfl
  | @step rowIndex nextPowerRef
      priorTrace accepted inductionHypothesis =>
      rw [inductionHypothesis]
      change
        ((image.primes.map PrimeRecord.powerRefCount).take
              rowIndex).sum +
            (cRow image rowIndex).powerRefCount =
          ((image.primes.map PrimeRecord.powerRefCount).take
              (rowIndex + 1)).sum
      rw [List.sum_take_succ
        (image.primes.map PrimeRecord.powerRefCount) rowIndex
        (by simpa using accepted.indexLt)]
      congr 1
      rw [List.getElem_map]
      exact
        congrArg PrimeRecord.powerRefCount
          (List.getD_eq_getElem
            image.primes default accepted.indexLt)

theorem CPowerRowTrace.rows
    {image : ArchiveImage} {rowCount nextPowerRef : Nat}
    (trace : CPowerRowTrace image rowCount nextPowerRef)
    {previousValue : Nat}
    (events :
      CPowerEventTrace image image.events.length previousValue)
    (hboundFits : image.header.bound < limbBase) :
    ∀ rowIndex, rowIndex < rowCount →
      powerIndexRowCheck
          image.header.bound
          (V2.roster image).primeAt
          (V2.layout image)
          rowIndex =
        true := by
  induction trace with
  | nil =>
      intro rowIndex hindex
      omega
  | @step rowCount nextPowerRef
      priorTrace accepted inductionHypothesis =>
      intro rowIndex hindex
      by_cases hbefore : rowIndex < rowCount
      · exact inductionHypothesis rowIndex hbefore
      · have hequal : rowIndex = rowCount := by omega
        subst rowIndex
        exact accepted.refines_row events hboundFits

/-! ## Complete successful source call -/

/-- Complete successful state of
`tg_sq218_validate_power_layout_v2`.

The two data fields of the C function are parameters of the proposition so
the structure remains `Prop`-valued: `nextPowerRef` is the terminal inverse
map cursor and `previousValue` is the terminal event-order cursor.
-/
structure CPowerLayoutAccepted
    (image : ArchiveImage)
    (nextPowerRef previousValue : Nat) : Prop where
  header :
    headerCheck image = true
  boundFits :
    image.header.bound < limbBase
  events :
    CPowerEventTrace image image.header.eventCount previousValue
  rows :
    CPowerRowTrace image image.header.primeCount nextPowerRef
  powerCursorComplete :
    nextPowerRef = image.header.powerRefCount

theorem CPowerLayoutAccepted.fullEvents
    {image : ArchiveImage} {nextPowerRef previousValue : Nat}
    (accepted :
      CPowerLayoutAccepted image nextPowerRef previousValue) :
    CPowerEventTrace image image.events.length previousValue := by
  have hheader := headerCheck_sound accepted.header
  simpa only [hheader.eventCount] using accepted.events

theorem CPowerLayoutAccepted.fullRows
    {image : ArchiveImage} {nextPowerRef previousValue : Nat}
    (accepted :
      CPowerLayoutAccepted image nextPowerRef previousValue) :
    CPowerRowTrace image image.primes.length nextPowerRef := by
  have hheader := headerCheck_sound accepted.header
  simpa only [hheader.primeCount] using accepted.rows

/-- The source cursor consumes every physical power-reference word.  This is
stronger than the V2 Boolean needs, but records the terminal C guard exactly
for human and compiler-refinement audits. -/
theorem CPowerLayoutAccepted.consumesAllPowerRefs
    {image : ArchiveImage} {nextPowerRef previousValue : Nat}
    (accepted :
      CPowerLayoutAccepted image nextPowerRef previousValue) :
    cUsedPowerRefCount image image.primes.length =
      image.powerRefs.length := by
  have hheader := headerCheck_sound accepted.header
  have hcursor := accepted.fullRows.powerCursor
  rw [← hcursor, accepted.powerCursorComplete,
    hheader.powerRefCount]

/-- The complete successful C-shaped call is exactly the linear-size V2
power-layout Boolean used by the Sqrt218 capstone. -/
theorem CPowerLayoutAccepted.refines_powerLayoutCheck
    {image : ArchiveImage} {nextPowerRef previousValue : Nat}
    (accepted :
      CPowerLayoutAccepted image nextPowerRef previousValue) :
    powerLayoutCheck
        image.header.bound
        (V2.roster image).count
        (V2.roster image).primeAt
        (V2.layout image) =
      true := by
  have hevents := accepted.fullEvents
  have hrows := accepted.fullRows
  unfold powerLayoutCheck
  simp only [Bool.and_eq_true, decide_eq_true_eq]
  constructor
  · simp [V2.layout, roster_count]
  · constructor
    · unfold checkRange
      simp only [List.all_eq_true, List.mem_range, Nat.zero_add]
      intro eventIndex hindex
      rw [layout_eventCount] at hindex
      exact hevents.cells eventIndex hindex
    · constructor
      · unfold checkRange
        simp only [List.all_eq_true, List.mem_range, Nat.zero_add]
        intro eventIndex hindex
        rw [layout_eventCount] at hindex
        apply hevents.adjacent eventIndex
        omega
      · unfold checkRange
        simp only [List.all_eq_true, List.mem_range, Nat.zero_add]
        intro rowIndex hindex
        rw [roster_count] at hindex
        exact hrows.rows hevents accepted.boundFits rowIndex hindex

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPowerLayoutRefinement
