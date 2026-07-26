/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CU128DivRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CRosterRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.V2Adapter
import SparkInterval.TernaryGoldbach.Sqrt218LogSeedClosure

/-!
# Successful C-source logarithm-ladder refinement for Sqrt218 V2

This file models `tg_log_ladder_next` in the source's operation order and
lifts successful seed/recurrence iterations through
`tg_sq218_validate_log_ladder_v2`.

The recurrence uses the exact C word helpers, the exact source two-limb
multiplication, and `CU128DivRefinement.cU128DivU64`.  A successful step is
proved equal to `LogBounds.next`; no transcendental computation occurs in
this module.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CLogLadderRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CU128DivRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRosterRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
open SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate
open TGComputeContracts.Sqrt218

private theorem optionBind_some {α β : Type}
    {first : Option α} {rest : α → Option β} {result : β}
    (hbind : first >>= rest = some result) :
    ∃ value, first = some value ∧ rest value = some result :=
  Option.bind_eq_some_iff.mp hbind

/-- Literal successful/failing arithmetic path of `tg_log_ladder_next`.

Null-pointer guards are ABI preconditions and have no arithmetic payload.
All checked multiplications, additions, both restoring divisions, and the
upper ceiling increment remain in source order.
-/
def cLogLadderNext
    (logScaleWord position : Nat) (bounds : LogBounds) :
    Option LogBounds := do
  if seedAt ≤ position then pure () else none
  let square ← CPrimitives.wordMulChecked position position
  let twiceSquare ← CPrimitives.wordMulChecked 2 square
  let triplePosition ← CPrimitives.wordMulChecked 3 position
  if triplePosition < twiceSquare then pure () else none
  let denominatorBase ← CPrimitives.wordMulChecked 2 square
  let denominator ←
    CPrimitives.wordMulChecked denominatorBase (position - 1)
  let basePolynomial := twiceSquare - triplePosition
  let lowerPolynomial := basePolynomial - 1
  let upperPolynomial ←
    CPrimitives.wordAddChecked basePolynomial 3
  let start : U128 := ⟨0, logScaleWord⟩
  let lowerNumerator ←
    CPrimitives.mulWordChecked start lowerPolynomial
  let lowerDivision ←
    cU128DivU64
      lowerNumerator.hi lowerNumerator.lo denominator
  let nextLower ←
    CPrimitives.wordAddChecked
      bounds.lower lowerDivision.quotient
  let upperNumerator ←
    CPrimitives.mulWordChecked start upperPolynomial
  let upperDivision ←
    cU128DivU64
      upperNumerator.hi upperNumerator.lo denominator
  let upperIncrementSource :=
    if upperDivision.remainder ≠ 0 then
      CPrimitives.wordAddChecked upperDivision.quotient 1
    else
      some upperDivision.quotient
  let upperIncrement ← upperIncrementSource
  let nextUpper ←
    CPrimitives.wordAddChecked bounds.upper upperIncrement
  some ⟨nextLower, nextUpper⟩

/-- Literal zero-based contents of the C array
`tg_sq218_log_seeds[30][2]`. -/
def cLogSeeds : List LogBounds := [
  ⟨0, 0⟩,
  ⟨195103586431999, 195103586572737⟩,
  ⟨309231868028532, 309231868693940⟩,
  ⟨390207172863998, 390207173145474⟩,
  ⟨453016498773239, 453016499054997⟩,
  ⟨504335454460532, 504335455266677⟩,
  ⟨547725013666734, 547725014089229⟩,
  ⟨585310759295998, 585310759718211⟩,
  ⟨618463736514181, 618463736936676⟩,
  ⟨648120085205239, 648120085627734⟩,
  ⟨674947515845858, 674947516268353⟩,
  ⟨699439040892531, 699439041839414⟩,
  ⟨721969060362613, 721969060925845⟩,
  ⟨742828600098734, 742828600661966⟩,
  ⟨762248366993738, 762248367556971⟩,
  ⟨780414345727997, 780414346290948⟩,
  ⟨797478659741748, 797478660304980⟩,
  ⟨813567322946180, 813567323509412⟩,
  ⟨828785892793963, 828785893357196⟩,
  ⟨843223671637238, 843223672200471⟩,
  ⟨856956881960417, 856956882523649⟩,
  ⟨870051102277858, 870051102841090⟩,
  ⟨882563161108618, 882563161679169⟩,
  ⟨894542627324530, 894542628412151⟩,
  ⟨906032997473296, 906032998177266⟩,
  ⟨917072646794612, 917072647498582⟩,
  ⟨927695604734679, 927695605438649⟩,
  ⟨937932186530733, 937932187234703⟩,
  ⟨947809514957280, 947809515661250⟩,
  ⟨957351953425738, 957351954129708⟩
]

def cLogSeedAt (position : Nat) : LogBounds :=
  cLogSeeds.getD position ⟨0, 0⟩

theorem cLogSeeds_length :
    cLogSeeds.length = seedAt := by
  rfl

/-- The literal zero-based C table is exactly the one-based analytic seed
function used by the generic ladder. -/
theorem cLogSeedAt_eq_seed
    {position : Nat} (hposition : position < seedAt) :
    cLogSeedAt position = seed (position + 1) := by
  norm_num [seedAt] at hposition
  interval_cases position <;> rfl

/-- The source table branch used before position 30, followed by the exact
source recurrence branch. -/
def cLogLadderStep
    (logScaleWord position : Nat) (bounds : LogBounds) :
    Option LogBounds :=
  if position < seedAt then
    some (cLogSeedAt position)
  else
    cLogLadderNext logScaleWord position bounds

theorem cLogLadderNext_refines
    {position : Nat} {bounds output : LogBounds}
    (hpositionFits : position < limbBase)
    (hlowerFits : bounds.lower < limbBase)
    (hupperFits : bounds.upper < limbBase)
    (hrun :
      cLogLadderNext scale position bounds = some output) :
    output = bounds.next position := by
  unfold cLogLadderNext at hrun
  have hposition : seedAt ≤ position := by
    by_contra hnot
    rw [if_neg hnot] at hrun
    contradiction
  rw [if_pos hposition] at hrun
  rcases optionBind_some hrun with
    ⟨square, hsquare, hrun⟩
  rcases optionBind_some hrun with
    ⟨twiceSquare, htwiceSquare, hrun⟩
  rcases optionBind_some hrun with
    ⟨triplePosition, htriplePosition, hrun⟩
  have horder : triplePosition < twiceSquare := by
    by_contra hnot
    rw [if_neg hnot] at hrun
    contradiction
  rw [if_pos horder] at hrun
  rcases optionBind_some hrun with
    ⟨denominatorBase, hdenominatorBase, hrun⟩
  rcases optionBind_some hrun with
    ⟨denominator, hdenominator, hrun⟩
  let basePolynomial := twiceSquare - triplePosition
  let lowerPolynomial := basePolynomial - 1
  rcases optionBind_some hrun with
    ⟨upperPolynomial, hupperPolynomial, hrun⟩
  let start : U128 := ⟨0, scale⟩
  rcases optionBind_some hrun with
    ⟨lowerNumerator, hlowerNumerator, hrun⟩
  rcases optionBind_some hrun with
    ⟨lowerDivision, hlowerDivision, hrun⟩
  rcases optionBind_some hrun with
    ⟨nextLower, hnextLower, hrun⟩
  rcases optionBind_some hrun with
    ⟨upperNumerator, hupperNumerator, hrun⟩
  rcases optionBind_some hrun with
    ⟨upperDivision, hupperDivision, hrun⟩
  rcases optionBind_some hrun with
    ⟨upperIncrement, hupperIncrement, hrun⟩
  rcases optionBind_some hrun with
    ⟨nextUpper, hnextUpper, hrun⟩
  have houtput :
      LogBounds.mk nextLower nextUpper = output :=
    Option.some.inj hrun
  subst output
  have hsquareSound :=
    CPrimitives.wordMulChecked_sound
      hpositionFits hpositionFits hsquare
  have htwoFits : 2 < limbBase := by norm_num [limbBase]
  have hthreeFits : 3 < limbBase := by norm_num [limbBase]
  have htwiceSquareSound :=
    CPrimitives.wordMulChecked_sound
      htwoFits hsquareSound.1 htwiceSquare
  have htriplePositionSound :=
    CPrimitives.wordMulChecked_sound
      hthreeFits hpositionFits htriplePosition
  have hdenominatorBaseSound :=
    CPrimitives.wordMulChecked_sound
      htwoFits hsquareSound.1 hdenominatorBase
  have hpositionMinusFits : position - 1 < limbBase := by
    omega
  have hdenominatorSound :=
    CPrimitives.wordMulChecked_sound
      hdenominatorBaseSound.1 hpositionMinusFits hdenominator
  have hupperPolynomialSound :=
    CPrimitives.wordAddChecked_sound
      (by
        omega)
      hthreeFits hupperPolynomial
  have hscaleFits : scale < limbBase := by
    norm_num [scale, limbBase]
  have hstartValid : start.Valid := by
    exact ⟨by norm_num [limbBase], hscaleFits⟩
  have hlowerNumeratorSpec :
      U128.mulWordChecked start lowerPolynomial =
        some lowerNumerator :=
    CPrimitives.mulWordChecked_refines
      hstartValid hlowerNumerator
  have hlowerNumeratorValid :=
    (U128.mulWordChecked_sound hlowerNumeratorSpec).2.1
  have hlowerDivisionSound :=
    cU128DivU64_sound
      hlowerNumeratorValid.1 hlowerNumeratorValid.2
      hdenominatorSound.1 hlowerDivision
  have hnextLowerSound :=
    CPrimitives.wordAddChecked_sound
      hlowerFits hlowerDivisionSound.2.2.2.1 hnextLower
  have hupperNumeratorSpec :
      U128.mulWordChecked start upperPolynomial =
        some upperNumerator :=
    CPrimitives.mulWordChecked_refines
      hstartValid hupperNumerator
  have hupperNumeratorValid :=
    (U128.mulWordChecked_sound hupperNumeratorSpec).2.1
  have hupperDivisionSound :=
    cU128DivU64_sound
      hupperNumeratorValid.1 hupperNumeratorValid.2
      hdenominatorSound.1 hupperDivision
  have hupperQuotientEq :
      upperDivision.quotient =
        upperNumerator.toNat / denominator := by
    simpa [U128.toNat] using hupperDivisionSound.2.1
  have hupperRemainderEq :
      upperDivision.remainder =
        upperNumerator.toNat % denominator := by
    simpa [U128.toNat] using hupperDivisionSound.2.2.1
  have hupperIncrementFits :
      upperIncrement < limbBase := by
    by_cases hremainder : upperDivision.remainder ≠ 0
    · rw [if_pos hremainder] at hupperIncrement
      exact
        (CPrimitives.wordAddChecked_sound
          hupperDivisionSound.2.2.2.1
          (by norm_num [limbBase]) hupperIncrement).1
    · rw [if_neg hremainder] at hupperIncrement
      exact Option.some.inj hupperIncrement ▸
        hupperDivisionSound.2.2.2.1
  have hnextUpperSound :=
    CPrimitives.wordAddChecked_sound
      hupperFits hupperIncrementFits hnextUpper
  have hsquareEq : square = position * position :=
    hsquareSound.2
  have htwiceSquareEq :
      twiceSquare = 2 * (position * position) := by
    rw [htwiceSquareSound.2, hsquareEq]
  have htriplePositionEq :
      triplePosition = 3 * position :=
    htriplePositionSound.2
  have hlowerPolynomialEq :
      lowerPolynomial =
        2 * position * position - 3 * position - 1 := by
    change
      twiceSquare - triplePosition - 1 =
        2 * position * position - 3 * position - 1
    rw [htwiceSquareEq, htriplePositionEq]
    ring_nf
  have hupperPolynomialEq :
      upperPolynomial =
        2 * position * position - 3 * position + 3 := by
    rw [hupperPolynomialSound.2]
    rw [htwiceSquareEq, htriplePositionEq]
    ring_nf
  have hdenominatorEq :
      denominator = logIncrementDenominator position := by
    rw [hdenominatorSound.2, hdenominatorBaseSound.2, hsquareEq]
    unfold logIncrementDenominator
    ring
  have hlowerNumeratorValue :
      lowerNumerator.toNat = scale * lowerPolynomial := by
    rw [(U128.mulWordChecked_sound hlowerNumeratorSpec).2.2]
    simp [start, U128.toNat]
  have hupperNumeratorValue :
      upperNumerator.toNat = scale * upperPolynomial := by
    rw [(U128.mulWordChecked_sound hupperNumeratorSpec).2.2]
    simp [start, U128.toNat]
  have hlowerIncrementEq :
      lowerDivision.quotient = logIncrementLower position := by
    rw [hlowerDivisionSound.2.1]
    change lowerNumerator.toNat / denominator =
      logIncrementLower position
    rw [hlowerNumeratorValue, hdenominatorEq,
      hlowerPolynomialEq]
    rfl
  have hupperCeil :
      upperIncrement =
        ceilDiv upperNumerator.toNat denominator := by
    have hceil :=
      CStepRefinement.ceilDiv_eq_quotient
        hupperDivisionSound.1
        (num := upperNumerator.toNat)
    by_cases hremainder : upperDivision.remainder = 0
    · have hsource :
          upperIncrement = upperDivision.quotient := by
        rw [if_neg (by simpa using hremainder)] at hupperIncrement
        exact (Option.some.inj hupperIncrement).symm
      have hmodzero :
          upperNumerator.toNat % denominator = 0 := by
        rw [← hupperRemainderEq]
        exact hremainder
      have hceilEq :
          ceilDiv upperNumerator.toNat denominator =
            upperNumerator.toNat / denominator := by
        rw [hceil, if_pos hmodzero]
      exact
        hsource.trans
          (hupperQuotientEq.trans hceilEq.symm)
    · have hsource :
          upperIncrement = upperDivision.quotient + 1 := by
        rw [if_pos hremainder] at hupperIncrement
        exact
          (CPrimitives.wordAddChecked_sound
            hupperDivisionSound.2.2.2.1
            (by norm_num [limbBase])
            hupperIncrement).2
      have hmodne :
          upperNumerator.toNat % denominator ≠ 0 := by
        intro hzero
        apply hremainder
        rw [hupperRemainderEq]
        exact hzero
      have hceilEq :
          ceilDiv upperNumerator.toNat denominator =
            upperNumerator.toNat / denominator + 1 := by
        rw [hceil, if_neg hmodne]
      exact
        hsource.trans
          ((congrArg (· + 1) hupperQuotientEq).trans
            hceilEq.symm)
  have hupperIncrementEq :
      upperIncrement = logIncrementUpper position := by
    rw [hupperCeil]
    unfold logIncrementUpper ceilDiv
    rw [hupperNumeratorValue, hdenominatorEq,
      hupperPolynomialEq]
  cases bounds with
  | mk lower upper =>
      change
        LogBounds.mk nextLower nextUpper =
          LogBounds.mk
            (lower + logIncrementLower position)
            (upper + logIncrementUpper position)
      rw [hnextLowerSound.2, hlowerIncrementEq,
        hnextUpperSound.2, hupperIncrementEq]

/-! ## Successful source iterations -/

theorem cLogLadderStep_refines
    {logScaleWord position : Nat} {bounds output : LogBounds}
    (hscale : logScaleWord = scale)
    (hpositionFits : position < limbBase)
    (hlowerFits : bounds.lower < limbBase)
    (hupperFits : bounds.upper < limbBase)
    (hrun :
      cLogLadderStep logScaleWord position bounds = some output) :
    output =
      SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.next
        position bounds := by
  subst logScaleWord
  by_cases hseed : position < seedAt
  · simp only [cLogLadderStep, hseed, if_true] at hrun
    have houtput := Option.some.inj hrun
    simp only [
      SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.next,
      hseed, if_true]
    exact houtput.symm.trans (cLogSeedAt_eq_seed hseed)
  · simp only [cLogLadderStep, hseed, if_false] at hrun
    simp only [
      SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.next,
      hseed, if_false]
    exact
      cLogLadderNext_refines
        hpositionFits hlowerFits hupperFits hrun

/-- Successful iterations of the C `while (position < row.prime)` loop.

The count is explicit, every live word is retained below `2^64`, and every
edge records the exact successful source operation.  In particular, the
relation does not define acceptance by appealing to the Lean ladder. -/
inductive CLogAdvanceTrace (logScaleWord : Nat) :
    Nat → Nat → LogBounds → LogBounds → Prop
  | nil (position : Nat) (bounds : LogBounds) :
      CLogAdvanceTrace logScaleWord 0 position bounds bounds
  | step
      {count position : Nat}
      {bounds nextBounds finalBounds : LogBounds}
      (positionFits : position < limbBase)
      (lowerFits : bounds.lower < limbBase)
      (upperFits : bounds.upper < limbBase)
      (sourceStep :
        cLogLadderStep logScaleWord position bounds =
          some nextBounds)
      (tail :
        CLogAdvanceTrace logScaleWord count (position + 1)
          nextBounds finalBounds) :
      CLogAdvanceTrace logScaleWord (count + 1) position
        bounds finalBounds

/-- A successful source while-trace is exactly the pure Lean ladder fold. -/
theorem CLogAdvanceTrace.refines_advance
    {logScaleWord count position : Nat}
    {bounds finalBounds : LogBounds}
    (trace :
      CLogAdvanceTrace logScaleWord count position bounds finalBounds)
    (hscale : logScaleWord = scale) :
    finalBounds =
      SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.advance
        count position bounds := by
  induction trace with
  | nil position bounds =>
      rfl
  | @step count position bounds nextBounds finalBounds
      positionFits lowerFits upperFits sourceStep tail
      inductionHypothesis =>
      have hnext :=
        cLogLadderStep_refines hscale positionFits lowerFits upperFits
          sourceStep
      rw [
        SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.advance]
      rw [← hnext]
      exact inductionHypothesis

def cLogBounds (row : PrimeRecord) : LogBounds :=
  ⟨row.logLower, row.logUpper⟩

/-- Successful source-shaped iterations of the outer logarithm-row loop.

`primeBound` is retained even though the generic V2 log checker only needs
strict row order: it is an explicit rejection guard in the C source. -/
inductive CLogRowsTrace
    (logScaleWord bound : Nat) :
    LogRows.LadderState → List PrimeRecord → Prop
  | nil (state : LogRows.LadderState) :
      CLogRowsTrace logScaleWord bound state []
  | step
      {state : LogRows.LadderState}
      {row : PrimeRecord} {rest : List PrimeRecord}
      {finalBounds : LogBounds}
      (primeFits : row.prime < limbBase)
      (primeOrder : state.position < row.prime)
      (primeBound : row.prime ≤ bound)
      (advance :
        CLogAdvanceTrace logScaleWord
          (row.prime - state.position)
          state.position state.bounds finalBounds)
      (rowBounds : cLogBounds row = finalBounds)
      (tail :
        CLogRowsTrace logScaleWord bound
          ⟨row.prime, finalBounds⟩ rest) :
      CLogRowsTrace logScaleWord bound state (row :: rest)

theorem CLogRowsTrace.refines_checkRows
    {logScaleWord bound : Nat}
    {state : LogRows.LadderState} {rows : List PrimeRecord}
    (trace :
      CLogRowsTrace logScaleWord bound state rows)
    (hscale : logScaleWord = scale) :
    LogRows.checkRows state (rows.map V2.logRow) = true := by
  induction trace with
  | nil state =>
      rfl
  | @step state row rest finalBounds
      primeFits primeOrder primeBound advance rowBounds tail
      inductionHypothesis =>
      have hadvance := advance.refines_advance hscale
      have hstate :
          LogRows.advanceTo state row.prime =
            ⟨row.prime, finalBounds⟩ := by
        cases state with
        | mk position bounds =>
            simp only [LogRows.advanceTo,
              SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.advanceTo]
            rw [← hadvance]
      change
        (if state.position < row.prime then
          decide
              (cLogBounds row =
                (LogRows.advanceTo state row.prime).bounds) &&
            LogRows.checkRows
              (LogRows.advanceTo state row.prime)
              (rest.map V2.logRow)
        else false) =
          true
      rw [if_pos primeOrder]
      simp only [Bool.and_eq_true, decide_eq_true_eq]
      constructor
      · rw [hstate]
        exact rowBounds
      · rw [hstate]
        exact inductionHypothesis

def cLogInitial : LogRows.LadderState :=
  ⟨1, cLogSeedAt 0⟩

theorem cLogInitial_eq_initial :
    cLogInitial = LogRows.initial := by
  rfl

/-- The successful terminal state of
`tg_sq218_validate_log_ladder_v2`.

The header pass ties the C loop count and log scale to the decoded V2 image;
the trace retains the source's row-bound rejection guard and exact checked
arithmetic path. -/
structure CLogLadderAccepted (image : ArchiveImage) : Prop where
  header : headerCheck image = true
  trace :
    CLogRowsTrace image.header.logScale image.header.bound
      cLogInitial image.primes

theorem logs_count (image : ArchiveImage) :
    (V2.logs image).count = image.primes.length := by
  simp [V2.logs, LogRows.Certificate.count]

theorem logs_primeAt
    (image : ArchiveImage) (index : Nat) :
    ((V2.logs image).rowAt index).prime =
      (V2.roster image).primeAt index := by
  by_cases hindex : index < image.primes.length
  · unfold LogRows.Certificate.rowAt V2.logs
    rw [List.getD_eq_getElem _ _ (by simpa using hindex)]
    simp only [List.getElem_map, V2.logRow]
    have hcRow :
        cRow image index = image.primes[index] :=
      List.getD_eq_getElem image.primes default hindex
    rw [← hcRow]
    exact (roster_primeAt image index).symm
  · have hlogs :
        (V2.logs image).rows.length ≤ index := by
      simpa [V2.logs] using (Nat.le_of_not_gt hindex)
    have himage : image.primes.length ≤ index :=
      Nat.le_of_not_gt hindex
    rw [LogRows.Certificate.rowAt,
      List.getD_eq_default _ _ hlogs]
    rw [roster_primeAt]
    unfold cRow
    rw [List.getD_eq_default _ _ himage]
    rfl

/-! The fixed seed-table theorem is established below.  It is deliberately
separate from the production trace: only thirty closed rational checks are
involved, never the archive-sized ladder. -/

/-- A complete successful C-shaped log-ladder call discharges the exact V2
log Boolean consumed by the capstone. -/
theorem CLogLadderAccepted.refines_logRowsCheck
    {image : ArchiveImage}
    (accepted : CLogLadderAccepted image) :
    LogRows.check
        (V2.roster image).count
        (V2.roster image).primeAt
        (V2.logs image) =
      true := by
  have hheader := accepted.header
  simp only [headerCheck, decide_eq_true_eq] at hheader
  have hscale :
      image.header.logScale = scale := by
    simpa [logScale, scale] using hheader.2.2.2.2.2.1
  have hrows :
      LogRows.checkRows LogRows.initial (V2.logs image).rows = true := by
    rw [← cLogInitial_eq_initial]
    exact accepted.trace.refines_checkRows hscale
  unfold LogRows.check
  simp only [seedTableCheck_closed, true_and, Bool.and_eq_true,
    decide_eq_true_eq]
  refine ⟨?_, ?_, hrows⟩
  · rw [logs_count, roster_count]
  · unfold checkRange
    simp only [List.all_eq_true, List.mem_range, Nat.zero_add]
    intro index hindex
    simp only [LogRows.alignmentCellCheck, decide_eq_true_eq]
    exact logs_primeAt image index

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CLogLadderRefinement

end
