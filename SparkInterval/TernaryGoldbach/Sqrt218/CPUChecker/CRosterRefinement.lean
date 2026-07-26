/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CModularRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.V2Adapter

/-!
# Successful C-source roster refinement for Sqrt218 V2

This module gives a relational, source-shaped model of the successful path
through `tg_sq218_validate_roster_v2`.  It retains the forward row cursor,
the factor-reference and factor-pair cursors, multiplicity-preserving factor
lists, checked-product bounds, the literal C modular-residue pass, and the
terminal composite run.

The final theorem turns such a successful trace into the exact Boolean
`Operational.V2.primeRosterCheck` consumed by `V2Adapter.V2.roster`.  The
source acceptance relation is deliberately not defined in terms of that
Boolean checker.

Everything is symbolic in an arbitrary decoded `ArchiveImage`; this file
does not load or replay a production archive and makes no compiler, ABI,
executable, ISA, or processor claim.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRosterRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CModularRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

/-! ## Source-shaped slices -/

def cRow (image : ArchiveImage) (index : Nat) : PrimeRecord :=
  image.primes.getD index default

/-- The exact multiplicity-preserving factor-reference slice consumed by the
two C factor loops for one row. -/
def cFactorRefsAt (image : ArchiveImage) (index : Nat) : List Nat :=
  let row := cRow image index
  (image.factorRefs.drop row.factorRefIndex).take row.factorRefCount

/-- The earlier prime values obtained by the C source's second accessor in
the factor-product loop. -/
def cFactorValuesAt (image : ArchiveImage) (index : Nat) : List Nat :=
  (cFactorRefsAt image index).map fun reference =>
    (cRow image reference).prime

/-- The exact factor-pair slice consumed by the C gap loop for one row. -/
def cGapPairsAt (image : ArchiveImage) (index : Nat) :
    List SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.FactorPair :=
  let row := cRow image index
  ((image.factorPairs.drop row.gapPairIndex).take row.gapPairCount).map
    V2.factorPair

/-! ## Elementary adapter equalities -/

theorem roster_count (image : ArchiveImage) :
    (V2.roster image).count = image.primes.length := by
  simp [V2.roster, PrimeRosterCertificate.count]

theorem roster_rowAt
    (image : ArchiveImage) {index : Nat}
    (hindex : index < image.primes.length) :
    (V2.roster image).rowAt index = V2.primeRow image index := by
  simp only [PrimeRosterCertificate.rowAt, V2.roster]
  rw [List.getD_eq_getElem _ _ (by simpa using hindex)]
  simp only [List.getElem_map, List.getElem_range]

theorem roster_primeAt (image : ArchiveImage) (index : Nat) :
    (V2.roster image).primeAt index = (cRow image index).prime := by
  by_cases hindex : index < image.primes.length
  · rw [PrimeRosterCertificate.primeAt, roster_rowAt image hindex]
    rfl
  · have hrows :
        (V2.roster image).rows.length ≤ index := by
      simpa [V2.roster] using (Nat.le_of_not_gt hindex)
    have himage : image.primes.length ≤ index :=
      Nat.le_of_not_gt hindex
    rw [PrimeRosterCertificate.primeAt]
    unfold PrimeRosterCertificate.rowAt cRow
    rw [
      List.getD_eq_default _ _ hrows,
      List.getD_eq_default _ _ himage]
    rfl

theorem roster_previousAt
    (image : ArchiveImage) (index previous : Nat)
    (hprevious :
      previous =
        if index = 0 then 1 else (cRow image (index - 1)).prime) :
    (V2.roster image).previousAt index = previous := by
  rw [PrimeRosterCertificate.previousAt]
  split
  · simp_all
  · rw [roster_primeAt]
    simp_all

theorem roster_factorValuesAt
    (image : ArchiveImage) (index : Nat) :
    (V2.roster image).factorValuesAt index =
      cFactorValuesAt image index := by
  unfold PrimeRosterCertificate.factorValuesAt cFactorValuesAt
  rw [show
    (V2.roster image).rowAt index =
      V2.primeRow image index by
        by_cases hindex : index < image.primes.length
        · exact roster_rowAt image hindex
        · have hrows :
              (V2.roster image).rows.length ≤ index := by
            simpa [V2.roster] using (Nat.le_of_not_gt hindex)
          have himage : image.primes.length ≤ index :=
            Nat.le_of_not_gt hindex
          unfold PrimeRosterCertificate.rowAt
          rw [List.getD_eq_default _ _ hrows]
          unfold V2.primeRow V2.factorRefsAt V2.gapPairsAt
          rw [List.getD_eq_default _ _ himage]
          rfl]
  simp only [V2.primeRow, V2.factorRefsAt, cFactorRefsAt, cRow]
  apply List.map_congr_left
  intro reference _hreference
  exact roster_primeAt image reference

theorem roster_gapPairsAt
    (image : ArchiveImage) {index : Nat}
    (hindex : index < image.primes.length) :
    ((V2.roster image).rowAt index).gapPairs =
      cGapPairsAt image index := by
  rw [roster_rowAt image hindex]
  rfl

/-! ## Exact source gap pass -/

/-- Successful iterations of `tg_validate_gap_pair`, starting at the supplied
natural value.  Each edge retains the decoded-word bounds, the successful
checked multiplication, and the exact expected consecutive value. -/
inductive CGapRun :
    Nat →
      List
        SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.FactorPair →
      Prop
  | nil (value : Nat) :
      CGapRun value []
  | cons
      {value : Nat}
      {pair :
        SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.FactorPair}
      {rest :
        List
          SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.FactorPair}
      (valueFits : value < limbBase)
      (leftFits : pair.left < limbBase)
      (rightFits : pair.right < limbBase)
      (leftNontrivial : 1 < pair.left)
      (rightNontrivial : 1 < pair.right)
      (productFits : pair.left * pair.right < limbBase)
      (product : pair.left * pair.right = value)
      (tail : CGapRun (value + 1) rest) :
      CGapRun value (pair :: rest)

/-- The literal successful C factor-pair pass is the V2 Boolean consecutive
factor run. -/
theorem CGapRun.refines_factorRunCheck
    {value : Nat}
    {pairs :
      List SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.FactorPair}
    (run : CGapRun value pairs) :
    factorRunCheck value pairs = true := by
  induction run with
  | nil value =>
      rfl
  | @cons value pair rest
      _valueFits _leftFits _rightFits leftNontrivial rightNontrivial
      _productFits product tail inductionHypothesis =>
      simp only [factorRunCheck, Bool.and_eq_true,
        factorPairCheck, decide_eq_true_eq]
      exact
        ⟨⟨leftNontrivial, rightNontrivial, product.symm⟩,
          inductionHypothesis⟩

/-! ## One accepted source row -/

/-- Successful source conditions for one iteration of the outer roster loop.

The two reference lists retain multiplicity.  `factorProductsFit` records
every successful intermediate `tg_u64_mul_checked`, while `cResidues` is the
literal all-multiplicities `tg_pow_mod` decision.  `gapRun` is the exact
consecutive loop beginning at `previous + 1`.
-/
structure CRowAccepted
    (image : ArchiveImage)
    (index previous nextFactor nextGap : Nat) : Prop where
  indexLt : index < image.primes.length
  factorCursor :
    (cRow image index).factorRefIndex = nextFactor
  gapCursor :
    (cRow image index).gapPairIndex = nextGap
  primeFits :
    (cRow image index).prime < limbBase
  primeOrder :
    previous < (cRow image index).prime
  primeBound :
    (cRow image index).prime ≤ image.header.bound
  logOrder :
    (cRow image index).logLower ≤ (cRow image index).logUpper
  factorEndFits :
    (cRow image index).factorRefIndex +
        (cRow image index).factorRefCount <
      limbBase
  factorEndInside :
    (cRow image index).factorRefIndex +
        (cRow image index).factorRefCount ≤
      image.factorRefs.length
  gapEndFits :
    (cRow image index).gapPairIndex +
        (cRow image index).gapPairCount <
      limbBase
  gapEndInside :
    (cRow image index).gapPairIndex +
        (cRow image index).gapPairCount ≤
      image.factorPairs.length
  gapCount :
    (cRow image index).gapPairCount =
      (cRow image index).prime - previous - 1
  referencesEarlier :
    ∀ reference ∈ cFactorRefsAt image index, reference < index
  factorProductsFit :
    ∀ prefixCount, prefixCount ≤ (cFactorValuesAt image index).length →
      ((cFactorValuesAt image index).take prefixCount).prod < limbBase
  factorProduct :
    (cFactorValuesAt image index).prod =
      (cRow image index).prime - 1
  twoRow :
    (cRow image index).prime = 2 →
      index = 0 ∧
        (cRow image index).witness = 0 ∧
        (cRow image index).factorRefCount = 0
  nonTwoRow :
    (cRow image index).prime ≠ 2 →
      (cRow image index).factorRefCount ≠ 0 ∧
        2 ≤ (cRow image index).witness ∧
        (cRow image index).witness < (cRow image index).prime ∧
        cLucasResidueCheck
            (cRow image index).prime
            (cRow image index).witness
            (cFactorValuesAt image index) =
          true
  gapRun :
    CGapRun (previous + 1) (cGapPairsAt image index)

theorem CRowAccepted.factorRefsLength
    {image : ArchiveImage}
    {index previous nextFactor nextGap : Nat}
    (accepted :
      CRowAccepted image index previous nextFactor nextGap) :
    (cFactorRefsAt image index).length =
      (cRow image index).factorRefCount := by
  have hend := accepted.factorEndInside
  simp only [cFactorRefsAt, List.length_take, List.length_drop]
  omega

theorem CRowAccepted.gapPairsLength
    {image : ArchiveImage}
    {index previous nextFactor nextGap : Nat}
    (accepted :
      CRowAccepted image index previous nextFactor nextGap) :
    (cGapPairsAt image index).length =
      (cRow image index).gapPairCount := by
  have hend := accepted.gapEndInside
  simp only [cGapPairsAt, List.length_map, List.length_take,
    List.length_drop]
  omega

theorem CRowAccepted.factorRefs
    {image : ArchiveImage}
    {index previous nextFactor nextGap : Nat}
    (accepted :
      CRowAccepted image index previous nextFactor nextGap) :
    ((V2.roster image).rowAt index).factorRefs =
      cFactorRefsAt image index := by
  rw [roster_rowAt image accepted.indexLt]
  rfl

theorem CRowAccepted.primeGapCheck
    {image : ArchiveImage}
    {index previous nextFactor nextGap : Nat}
    (accepted :
      CRowAccepted image index previous nextFactor nextGap)
    (hprevious :
      (V2.roster image).previousAt index = previous) :
    primeGapCheck (V2.roster image) index = true := by
  change
    factorGapCheck
        ((V2.roster image).previousAt index)
        ((V2.roster image).primeAt index)
        ((V2.roster image).rowAt index).gapPairs =
      true
  rw [hprevious, roster_primeAt,
    roster_gapPairsAt image accepted.indexLt]
  simp only [factorGapCheck, Bool.and_eq_true, decide_eq_true_eq]
  constructor
  · rw [accepted.gapPairsLength, accepted.gapCount]
    have horder := accepted.primeOrder
    omega
  · exact accepted.gapRun.refines_factorRunCheck

theorem CRowAccepted.primeRowCheck
    {image : ArchiveImage}
    {index previous nextFactor nextGap : Nat}
    (accepted :
      CRowAccepted image index previous nextFactor nextGap)
    (hpreviousPositive : 0 < previous) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.primeRowCheck
        (V2.roster image) index =
      true := by
  unfold
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.primeRowCheck
  rw [roster_rowAt image accepted.indexLt]
  change
    (if (cRow image index).prime = 2 then
      decide (
        index = 0 ∧
          (cRow image index).witness = 0 ∧
          V2.factorRefsAt image index = [])
    else
      decide (
        V2.factorRefsAt image index ≠ [] ∧
          (∀ reference ∈ V2.factorRefsAt image index,
            reference < index) ∧
          ((V2.roster image).factorValuesAt index).prod =
            (cRow image index).prime - 1 ∧
          2 ≤ (cRow image index).witness ∧
          (cRow image index).witness <
            (cRow image index).prime) &&
        lucasResidueCheck
          (cRow image index).prime
          (cRow image index).witness
          ((V2.roster image).factorValuesAt index).dedup) =
      true
  by_cases htwo : (cRow image index).prime = 2
  · rw [if_pos htwo]
    simp only [decide_eq_true_eq]
    have hsource := accepted.twoRow htwo
    refine ⟨hsource.1, hsource.2.1, ?_⟩
    unfold V2.factorRefsAt
    change
      (image.factorRefs.drop (cRow image index).factorRefIndex).take
          (cRow image index).factorRefCount =
        []
    rw [hsource.2.2]
    rfl
  · rw [if_neg htwo]
    simp only [Bool.and_eq_true, decide_eq_true_eq]
    have hsource := accepted.nonTwoRow htwo
    have hp : 1 < (cRow image index).prime := by
      have hone : 1 ≤ previous := hpreviousPositive
      exact hone.trans_lt accepted.primeOrder
    have hrefs :
        V2.factorRefsAt image index =
          cFactorRefsAt image index := by
      rfl
    have hvalues :
        (V2.roster image).factorValuesAt index =
          cFactorValuesAt image index :=
      roster_factorValuesAt image index
    constructor
    · refine ⟨?_, ?_, ?_, hsource.2.1, hsource.2.2.1⟩
      · rw [hrefs]
        intro hempty
        have hlength := accepted.factorRefsLength
        rw [hempty, List.length_nil] at hlength
        exact hsource.1 hlength.symm
      · rw [hrefs]
        exact accepted.referencesEarlier
      · rw [hvalues]
        exact accepted.factorProduct
    · rw [hvalues,
        ← cLucasResidueCheck_eq_dedup
          (cFactorValuesAt image index) hp]
      exact hsource.2.2.2

theorem CRowAccepted.rowCheck
    {image : ArchiveImage}
    {index previous nextFactor nextGap : Nat}
    (accepted :
      CRowAccepted image index previous nextFactor nextGap)
    (hprevious :
      (V2.roster image).previousAt index = previous)
    (hpreviousPositive : 0 < previous) :
    rowCheck (V2.roster image) index = true := by
  unfold SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.rowCheck
  simp only [Bool.and_eq_true]
  exact
    ⟨accepted.primeRowCheck hpreviousPositive,
      accepted.primeGapCheck hprevious⟩

/-! ## Forward outer-loop trace -/

/-- Successful iterations of the source's outer `for (row_index = 0; ...)`
loop.  The state indices are, in order, the next row, next factor reference,
next factor pair, and previous prime. -/
inductive CRosterTrace (image : ArchiveImage) :
    Nat → Nat → Nat → Nat → Prop
  | nil :
      CRosterTrace image 0 0 0 1
  | step
      {index nextFactor nextGap previous : Nat}
      (priorTrace :
        CRosterTrace image index nextFactor nextGap previous)
      (accepted :
        CRowAccepted image index previous nextFactor nextGap) :
      CRosterTrace image
        (index + 1)
        (nextFactor + (cRow image index).factorRefCount)
        (nextGap + (cRow image index).gapPairCount)
        (cRow image index).prime

def cPreviousAt (image : ArchiveImage) (count : Nat) : Nat :=
  if count = 0 then 1 else (cRow image (count - 1)).prime

def cUsedFactorCount (image : ArchiveImage) (count : Nat) : Nat :=
  ((image.primes.map PrimeRecord.factorRefCount).take count).sum

def cUsedGapCount (image : ArchiveImage) (count : Nat) : Nat :=
  ((image.primes.map PrimeRecord.gapPairCount).take count).sum

theorem CRosterTrace.previousAt
    {image : ArchiveImage}
    {count nextFactor nextGap previous : Nat}
    (trace :
      CRosterTrace image count nextFactor nextGap previous) :
    previous = cPreviousAt image count := by
  cases trace with
  | nil =>
      rfl
  | @step index nextFactor nextGap previous priorTrace accepted =>
      simp [cPreviousAt]

theorem CRosterTrace.previousPositive
    {image : ArchiveImage}
    {count nextFactor nextGap previous : Nat}
    (trace :
      CRosterTrace image count nextFactor nextGap previous) :
    0 < previous := by
  induction trace with
  | nil =>
      omega
  | @step index nextFactor nextGap previous
      priorTrace accepted inductionHypothesis =>
      exact inductionHypothesis.trans accepted.primeOrder

theorem CRosterTrace.factorCursor
    {image : ArchiveImage}
    {count nextFactor nextGap previous : Nat}
    (trace :
      CRosterTrace image count nextFactor nextGap previous) :
    nextFactor = cUsedFactorCount image count := by
  induction trace with
  | nil =>
      rfl
  | @step index nextFactor nextGap previous
      priorTrace accepted inductionHypothesis =>
      rw [inductionHypothesis]
      change
        ((image.primes.map PrimeRecord.factorRefCount).take index).sum +
            (cRow image index).factorRefCount =
          ((image.primes.map PrimeRecord.factorRefCount).take
            (index + 1)).sum
      rw [List.sum_take_succ
        (image.primes.map PrimeRecord.factorRefCount) index
        (by simpa using accepted.indexLt)]
      congr 1
      rw [List.getElem_map]
      exact
        congrArg PrimeRecord.factorRefCount
          (List.getD_eq_getElem
            image.primes default accepted.indexLt)

theorem CRosterTrace.gapCursor
    {image : ArchiveImage}
    {count nextFactor nextGap previous : Nat}
    (trace :
      CRosterTrace image count nextFactor nextGap previous) :
    nextGap = cUsedGapCount image count := by
  induction trace with
  | nil =>
      rfl
  | @step index nextFactor nextGap previous
      priorTrace accepted inductionHypothesis =>
      rw [inductionHypothesis]
      change
        ((image.primes.map PrimeRecord.gapPairCount).take index).sum +
            (cRow image index).gapPairCount =
          ((image.primes.map PrimeRecord.gapPairCount).take
            (index + 1)).sum
      rw [List.sum_take_succ
        (image.primes.map PrimeRecord.gapPairCount) index
        (by simpa using accepted.indexLt)]
      congr 1
      rw [List.getElem_map]
      exact
        congrArg PrimeRecord.gapPairCount
          (List.getD_eq_getElem
            image.primes default accepted.indexLt)

/-- Every row reached by a successful source trace passes the exact V2 row
Boolean.  The induction simultaneously supplies the positive `previous`
invariant needed to exclude degenerate modulus one. -/
theorem CRosterTrace.rows
    {image : ArchiveImage}
    {count nextFactor nextGap previous : Nat}
    (trace :
      CRosterTrace image count nextFactor nextGap previous) :
    ∀ index, index < count →
      rowCheck (V2.roster image) index = true := by
  induction trace with
  | nil =>
      intro index hindex
      omega
  | @step count nextFactor nextGap previous
      priorTrace accepted inductionHypothesis =>
      intro index hindex
      by_cases hbefore : index < count
      · exact inductionHypothesis index hbefore
      · have hequal : index = count := by omega
        subst index
        apply accepted.rowCheck
        · exact
            roster_previousAt image count previous
              priorTrace.previousAt
        · exact priorTrace.previousPositive

/-! ## Complete successful source call -/

/-- The successful terminal state of `tg_sq218_validate_roster_v2`.

The header/count equalities come from the already checked V2 view.  The
terminal fields are the literal final guards followed by the source `while`
loop over all remaining factor-pair records.
-/
structure CRosterAccepted
    (image : ArchiveImage)
    (nextFactor nextGap previous : Nat) : Prop where
  header : headerCheck image = true
  primeCountPositive : 0 < image.header.primeCount
  trace :
    CRosterTrace image image.header.primeCount
      nextFactor nextGap previous
  previousAtMostBound :
    previous ≤ image.header.bound
  factorCursorComplete :
    image.header.factorRefCount = nextFactor
  nextGapAtMostCount :
    nextGap ≤ image.header.factorPairCount
  remainingGapCount :
    image.header.factorPairCount - nextGap =
      image.header.bound - previous
  terminalRun :
    CGapRun
      (previous + 1)
      ((image.factorPairs.drop nextGap).map V2.factorPair)

theorem CRosterAccepted.fullTrace
    {image : ArchiveImage}
    {nextFactor nextGap previous : Nat}
    (accepted :
      CRosterAccepted image nextFactor nextGap previous) :
    CRosterTrace image image.primes.length
      nextFactor nextGap previous := by
  have hheader := headerCheck_sound accepted.header
  simpa only [hheader.primeCount] using accepted.trace

theorem CRosterAccepted.tailCheck
    {image : ArchiveImage}
    {nextFactor nextGap previous : Nat}
    (accepted :
      CRosterAccepted image nextFactor nextGap previous) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.tailCheck
        image.header.bound (V2.roster image) =
      true := by
  have hheader := headerCheck_sound accepted.header
  have htrace := accepted.fullTrace
  have hcountPositive : 0 < image.primes.length := by
    rw [← hheader.primeCount]
    exact accepted.primeCountPositive
  have hprevious :
      (V2.roster image).primeAt
          ((V2.roster image).count - 1) =
        previous := by
    rw [roster_count, roster_primeAt]
    have htracePrevious := htrace.previousAt
    simp [cPreviousAt, Nat.ne_of_gt hcountPositive] at htracePrevious
    exact htracePrevious.symm
  have hnextGap :
      nextGap = V2.usedGapPairCount image := by
    rw [htrace.gapCursor, cUsedGapCount, V2.usedGapPairCount]
    rw [List.take_of_length_le (by simp)]
  have htail :
      (V2.roster image).tailPairs =
        (image.factorPairs.drop nextGap).map V2.factorPair := by
    simp only [V2.roster]
    rw [hnextGap]
  unfold SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.tailCheck
  simp only [Bool.and_eq_true, decide_eq_true_eq]
  constructor
  · simpa [roster_count] using hcountPositive
  · rw [hprevious, htail]
    simp only [factorGapCheck, Bool.and_eq_true, decide_eq_true_eq]
    constructor
    · have hpairs := hheader.factorPairCount
      have hremaining := accepted.remainingGapCount
      have hpreviousBound := accepted.previousAtMostBound
      have hgapBound := accepted.nextGapAtMostCount
      simp only [List.length_map, List.length_drop]
      omega
    · exact accepted.terminalRun.refines_factorRunCheck

/-- A complete successful C-shaped roster call is exactly the generic V2
prime-roster Boolean used by the Sqrt218 capstone. -/
theorem CRosterAccepted.refines_primeRosterCheck
    {image : ArchiveImage}
    {nextFactor nextGap previous : Nat}
    (accepted :
      CRosterAccepted image nextFactor nextGap previous) :
    primeRosterCheck image.header.bound (V2.roster image) = true := by
  have htrace := accepted.fullTrace
  unfold primeRosterCheck
  simp only [Bool.and_eq_true]
  constructor
  · unfold checkRange
    simp only [List.all_eq_true, List.mem_range, Nat.zero_add]
    intro index hindex
    rw [roster_count] at hindex
    exact htrace.rows index hindex
  · exact accepted.tailCheck

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRosterRefinement
