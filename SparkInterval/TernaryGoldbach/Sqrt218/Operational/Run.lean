/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.Certified.Exp
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Archive
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Scan
import TGComputeContracts.Sqrt218.Kernel

/-!
# Data-independent operational checker for a typed Sqrt218 archive

This module checks a typed archive and proves that success yields the generic
`TGComputeContracts.Sqrt218.CertificateFacts`.  It contains no production
rows and does not evaluate the production computation.

The prime roster and prime-power layout are checked through bounded,
architecture-neutral predicates.  The fixed-point event loop is literally
the reusable `runFixedEvents` kernel.  Real logarithm containment is not
assumed from an attestation: every integer endpoint is separately checked by
the proved rational `SparkInterval.Certified.logCheck` checker.

Two deliberately uncomposed refinements remain:

1. the proved strict decoder in the sibling `Wire` module has not yet been
   bound to the receipt's artifact digest and registered V1 success relation;
2. a measured native executable/compiler/ISA execution to `run`.

Neither gap is represented by an axiom or an inhabitant in this module.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational

namespace Contract

open TGComputeContracts.Sqrt218

end Contract

/-! ## Total accessors into the typed arrays -/

namespace Archive

def primeCount (archive : Archive) : Nat :=
  archive.primes.length

def primeAt (archive : Archive) (index : Nat) : Nat :=
  (archive.primes.getD index default).prime

def logLowerAt (archive : Archive) (index : Nat) : Nat :=
  (archive.primes.getD index default).logLower

def logUpperAt (archive : Archive) (index : Nat) : Nat :=
  (archive.primes.getD index default).logUpper

def eventCount (archive : Archive) : Nat :=
  archive.events.length

def eventAt (archive : Archive) (index : Nat) :
    TGComputeContracts.Sqrt218.PowerEvent :=
  let event := archive.events.getD index default
  {
    value := event.power
    primeIndex := event.primeIndex
    exponent := event.exponent
    floorSqrt := Nat.sqrt event.power
  }

def powerCountAt (archive : Archive) (primeIndex : Nat) : Nat :=
  (archive.eventIndicesForPrime primeIndex).length

def canonicalIndexAt
    (archive : Archive) (primeIndex exponentIndex : Nat) : Nat :=
  (archive.eventIndicesForPrime primeIndex).getD exponentIndex 0

def claimedExit (archive : Archive) :
    TGComputeContracts.Sqrt218.FixedState := {
  weightedUpper := archive.summary.finalWeightedUpper
  psiLower := archive.summary.finalPsiLower
}

end Archive

/-! ## A reusable bounded Boolean loop -/

def checkRange (start count : Nat) (cell : Nat → Bool) : Bool :=
  (List.range count).all fun offset => cell (start + offset)

theorem checkRange_sound
    {start count : Nat} {cell : Nat → Bool}
    (hcheck : checkRange start count cell = true) :
    ∀ index, start ≤ index → index < start + count →
      cell index = true := by
  intro index hlower hupper
  unfold checkRange at hcheck
  rw [List.all_eq_true] at hcheck
  have hoffset : index - start ∈ List.range count := by
    simp only [List.mem_range]
    omega
  have hcell := hcheck (index - start) hoffset
  rw [Nat.add_sub_of_le hlower] at hcell
  exact hcell

private theorem strict_of_adjacent
    {count : Nat} {value : Nat → Nat}
    (hadjacent :
      ∀ index, index + 1 < count →
        value index < value (index + 1)) :
    ∀ left right, left < count → right < count → left < right →
      value left < value right := by
  intro left right hleft hright hlr
  induction right with
  | zero => omega
  | succ right inductionHypothesis =>
      by_cases heq : left = right
      · subst left
        exact hadjacent right hright
      · exact
          (inductionHypothesis (by omega) (by omega)).trans
            (hadjacent right hright)

/-! ## Complete prime roster -/

def primeCellCheck (archive : Archive) (index : Nat) : Bool :=
  decide (
    (archive.primeAt index).Prime ∧
      archive.primeAt index ≤ archive.bound)

def primeAdjacentCheck (archive : Archive) (index : Nat) : Bool :=
  decide (archive.primeAt index < archive.primeAt (index + 1))

def primeCoverCellCheck (archive : Archive) (value : Nat) : Bool :=
  decide (
    value.Prime →
      ∃ index : Fin archive.primeCount,
        archive.primeAt index = value)

/-- A direct bounded specification of the independent sieve comparison.

This high-level Boolean is intentionally not evaluated for production during
an ordinary build.  A future native refinement may implement it with the
linear Eratosthenes representation used by the Python verifier. -/
def primeRosterCheck (archive : Archive) : Bool :=
  decide (0 < archive.primeCount) &&
    (checkRange 0 archive.primeCount (primeCellCheck archive) &&
      (checkRange 0 (archive.primeCount - 1)
          (primeAdjacentCheck archive) &&
        checkRange 0 (archive.bound + 1)
          (primeCoverCellCheck archive)))

theorem primeRosterCheck_sound {archive : Archive}
    (hcheck : primeRosterCheck archive = true) :
    TGComputeContracts.Sqrt218.PrimeRosterFacts
      archive.bound archive.primeCount archive.primeAt := by
  simp only [primeRosterCheck, Bool.and_eq_true,
    decide_eq_true_eq] at hcheck
  have hcells :
      ∀ index, index < archive.primeCount →
        primeCellCheck archive index = true := by
    intro index hindex
    exact checkRange_sound hcheck.2.1 index (by omega) (by simpa using hindex)
  have hadjacent :
      ∀ index, index + 1 < archive.primeCount →
        archive.primeAt index < archive.primeAt (index + 1) := by
    intro index hindex
    have hcell :=
      checkRange_sound hcheck.2.2.1 index (by omega) (by omega)
    simpa [primeAdjacentCheck, decide_eq_true_eq] using hcell
  refine {
    count_pos := hcheck.1
    prime := ?_
    value_le := ?_
    strictMono := strict_of_adjacent hadjacent
    cover := ?_
  }
  · intro index hindex
    have hcell := hcells index hindex
    simp only [primeCellCheck, decide_eq_true_eq] at hcell
    exact hcell.1
  · intro index hindex
    have hcell := hcells index hindex
    simp only [primeCellCheck, decide_eq_true_eq] at hcell
    exact hcell.2
  · intro value hprime hbound
    have hcell :=
      checkRange_sound hcheck.2.2.2 value (by omega) (by omega)
    simp only [primeCoverCellCheck, decide_eq_true_eq] at hcell
    obtain ⟨index, hvalue⟩ := hcell hprime
    exact ⟨index, index.isLt, hvalue⟩

/-! ## Exact Lucas/Pratt row validation

The semantic roster proof above uses Lean's proved primality predicate.  These
additional checks mirror the independently replayed wire protocol, so changing
an otherwise-unused witness or factorization still makes the operational run
fail closed.
-/

def modularPower (base exponent modulus : Nat) : Nat :=
  if hzero : exponent = 0 then
    1 % modulus
  else
    let half := modularPower base (exponent / 2) modulus
    let square := (half * half) % modulus
    if exponent % 2 = 0 then
      square
    else
      (square * (base % modulus)) % modulus
termination_by exponent
decreasing_by
  exact Nat.div_lt_self (Nat.pos_of_ne_zero hzero) (by omega)

def prattRowCheck (archive : Archive) (index : Nat) : Bool :=
  let row := archive.primes.getD index default
  if row.prime = 2 then
    decide (row.witness = 0 ∧ row.factors = [])
  else
    decide (
      row.factors ≠ [] ∧
        row.factors.Pairwise (· ≤ ·) ∧
        row.factors.prod = row.prime - 1 ∧
        (row.factors.all fun factor =>
          decide (factor.Prime ∧ factor < row.prime)) = true ∧
        2 ≤ row.witness ∧
        row.witness < row.prime ∧
        modularPower row.witness (row.prime - 1) row.prime = 1 ∧
        (row.factors.all fun factor =>
          decide (
            modularPower row.witness
              ((row.prime - 1) / factor) row.prime ≠ 1)) = true)

def prattTableCheck (archive : Archive) : Bool :=
  checkRange 0 archive.primeCount (prattRowCheck archive)

/-! ## Complete prime-power layout -/

def eventCellCheck (archive : Archive) (index : Nat) : Bool :=
  let event := archive.eventAt index
  decide (
    event.value ≤ archive.bound ∧
      event.primeIndex < archive.primeCount ∧
      0 < event.exponent ∧
      event.value =
        archive.primeAt event.primeIndex ^ event.exponent ∧
      event.floorSqrt = Nat.sqrt event.value)

def eventAdjacentCheck (archive : Archive) (index : Nat) : Bool :=
  decide (
    (archive.eventAt index).value <
      (archive.eventAt (index + 1)).value)

def powerCountCellCheck (archive : Archive) (primeIndex : Nat) : Bool :=
  let count := archive.powerCountAt primeIndex
  let prime := archive.primeAt primeIndex
  decide (
    0 < count ∧
      prime ^ count ≤ archive.bound ∧
      archive.bound < prime ^ (count + 1))

def canonicalCellCheck
    (archive : Archive) (primeIndex exponentIndex : Nat) : Bool :=
  let eventIndex := archive.canonicalIndexAt primeIndex exponentIndex
  let event := archive.eventAt eventIndex
  decide (
    eventIndex < archive.eventCount ∧
      event.primeIndex = primeIndex ∧
      event.exponent = exponentIndex + 1)

def canonicalPrimeCheck (archive : Archive) (primeIndex : Nat) : Bool :=
  checkRange 0 (archive.powerCountAt primeIndex)
    (canonicalCellCheck archive primeIndex)

def primePowerLayoutCheck (archive : Archive) : Bool :=
  checkRange 0 archive.eventCount (eventCellCheck archive) &&
    (checkRange 0 (archive.eventCount - 1)
        (eventAdjacentCheck archive) &&
      (checkRange 0 archive.primeCount (powerCountCellCheck archive) &&
        checkRange 0 archive.primeCount (canonicalPrimeCheck archive)))

theorem primePowerLayoutCheck_sound {archive : Archive}
    (hroster :
      TGComputeContracts.Sqrt218.PrimeRosterFacts
        archive.bound archive.primeCount archive.primeAt)
    (hcheck : primePowerLayoutCheck archive = true) :
    TGComputeContracts.Sqrt218.PrimePowerEnumerationFacts
      archive.bound archive.primeCount archive.primeAt
      archive.eventCount archive.eventAt := by
  simp only [primePowerLayoutCheck, Bool.and_eq_true] at hcheck
  have hevent :
      ∀ index, index < archive.eventCount →
        TGComputeContracts.Sqrt218.PowerEventFacts
          archive.bound archive.primeCount archive.primeAt
          (archive.eventAt index) := by
    intro index hindex
    have hcell :=
      checkRange_sound hcheck.1 index (by omega) (by simpa using hindex)
    simp only [eventCellCheck, decide_eq_true_eq] at hcell
    exact {
      value_le := hcell.1
      primeIndex_lt := hcell.2.1
      exponent_pos := hcell.2.2.1
      value_eq := hcell.2.2.2.1
      floorSqrt_eq := hcell.2.2.2.2
    }
  have horder :
      ∀ index, index + 1 < archive.eventCount →
        (archive.eventAt index).value <
          (archive.eventAt (index + 1)).value := by
    intro index hindex
    have hcell :=
      checkRange_sound hcheck.2.1 index (by omega) (by omega)
    simpa [eventAdjacentCheck, decide_eq_true_eq] using hcell
  have hcount :
      ∀ primeIndex, primeIndex < archive.primeCount →
        0 < archive.powerCountAt primeIndex ∧
        archive.primeAt primeIndex ^
            archive.powerCountAt primeIndex ≤ archive.bound ∧
        archive.bound <
          archive.primeAt primeIndex ^
            (archive.powerCountAt primeIndex + 1) := by
    intro primeIndex hindex
    have hcell :=
      checkRange_sound hcheck.2.2.1 primeIndex
        (by omega) (by simpa using hindex)
    simpa [powerCountCellCheck, decide_eq_true_eq] using hcell
  have hcoverage :
      ∀ primeIndex, primeIndex < archive.primeCount →
        ∀ exponentIndex,
          exponentIndex < archive.powerCountAt primeIndex →
          archive.canonicalIndexAt primeIndex exponentIndex <
              archive.eventCount ∧
            (archive.eventAt
                (archive.canonicalIndexAt
                  primeIndex exponentIndex)).primeIndex = primeIndex ∧
            (archive.eventAt
                (archive.canonicalIndexAt
                  primeIndex exponentIndex)).exponent =
              exponentIndex + 1 := by
    intro primeIndex hprimeIndex exponentIndex hexponentIndex
    have hprime :=
      checkRange_sound hcheck.2.2.2 primeIndex
        (by omega) (by simpa using hprimeIndex)
    have hcell :=
      checkRange_sound hprime exponentIndex
        (by omega) (by simpa using hexponentIndex)
    simpa [canonicalCellCheck, decide_eq_true_eq] using hcell
  exact
    TGComputeContracts.Sqrt218.primePowerEnumerationFacts_of_canonical
      hroster hevent horder hcount hcoverage

/-! ## Independent rational realization of the directed log rows -/

def logTerms : Nat := 40
def logRangeBits : Nat := 4
def logPrecision : Nat := 128

def primeLogCellCheck (archive : Archive) (index : Nat) : Bool :=
  SparkInterval.Certified.logCheck logTerms logRangeBits logPrecision
    (archive.primeAt index : Rat)
    ((archive.logLowerAt index : Rat) /
      TGComputeContracts.Sqrt218.scale)
    ((archive.logUpperAt index : Rat) /
      TGComputeContracts.Sqrt218.scale)

def primeLogTableCheck (archive : Archive) : Bool :=
  checkRange 0 archive.primeCount (primeLogCellCheck archive)

theorem primeLogTableCheck_sound {archive : Archive}
    (hroster :
      TGComputeContracts.Sqrt218.PrimeRosterFacts
        archive.bound archive.primeCount archive.primeAt)
    (hcheck : primeLogTableCheck archive = true) :
    TGComputeContracts.Sqrt218.PrimeLogFacts archive.primeCount
      archive.primeAt archive.logLowerAt archive.logUpperAt := by
  have hcell :
      ∀ index, index < archive.primeCount →
        primeLogCellCheck archive index = true := by
    intro index hindex
    exact
      checkRange_sound hcheck index (by omega) (by simpa using hindex)
  have hscale :
      (0 : Real) < TGComputeContracts.Sqrt218.scale := by
    exact_mod_cast TGComputeContracts.Sqrt218.scale_pos
  refine {
    lower := ?_
    upper := ?_
  }
  · intro index hindex
    have hp := hroster.prime index hindex
    have hcontains :=
      SparkInterval.Certified.logCheck_sound
        (terms := logTerms) (k := logRangeBits) (prec := logPrecision)
        (x := (archive.primeAt index : Rat))
        (lo := (archive.logLowerAt index : Rat) /
          TGComputeContracts.Sqrt218.scale)
        (hi := (archive.logUpperAt index : Rat) /
          TGComputeContracts.Sqrt218.scale)
        (by norm_num [logTerms])
        (by exact_mod_cast hp.pos)
        (hcell index hindex)
    have hlower :
        (archive.logLowerAt index : Real) /
            TGComputeContracts.Sqrt218.scale ≤
          Real.log (archive.primeAt index) := by
      simpa [Rat.cast_div] using hcontains.1
    calc
      (archive.logLowerAt index : Real) =
          TGComputeContracts.Sqrt218.scale *
            ((archive.logLowerAt index : Real) /
              TGComputeContracts.Sqrt218.scale) := by
            field_simp
      _ ≤ TGComputeContracts.Sqrt218.scale *
          Real.log (archive.primeAt index) :=
        mul_le_mul_of_nonneg_left hlower hscale.le
  · intro index hindex
    have hp := hroster.prime index hindex
    have hcontains :=
      SparkInterval.Certified.logCheck_sound
        (terms := logTerms) (k := logRangeBits) (prec := logPrecision)
        (x := (archive.primeAt index : Rat))
        (lo := (archive.logLowerAt index : Rat) /
          TGComputeContracts.Sqrt218.scale)
        (hi := (archive.logUpperAt index : Rat) /
          TGComputeContracts.Sqrt218.scale)
        (by norm_num [logTerms])
        (by exact_mod_cast hp.pos)
        (hcell index hindex)
    have hupper :
        Real.log (archive.primeAt index) ≤
          (archive.logUpperAt index : Real) /
            TGComputeContracts.Sqrt218.scale := by
      simpa [Rat.cast_div] using hcontains.2
    calc
      TGComputeContracts.Sqrt218.scale *
          Real.log (archive.primeAt index) ≤
        TGComputeContracts.Sqrt218.scale *
          ((archive.logUpperAt index : Real) /
            TGComputeContracts.Sqrt218.scale) :=
        mul_le_mul_of_nonneg_left hupper hscale.le
      _ = (archive.logUpperAt index : Real) := by
        field_simp

/-! ## Closed operational success and its ordinary soundness theorem -/

def headerCheck (profile : Profile) (archive : Archive) : Bool :=
  decide (
    archive.kind = certificateKind ∧
      archive.schemaVersion = 1 ∧
      profile.bound = TGComputeContracts.Sqrt218.sourceCutoff ∧
      archive.bound = profile.bound ∧
      archive.logSeedAt = profile.logSeedAt ∧
      archive.logScale = profile.logScale ∧
      archive.reciprocalScale = profile.reciprocalScale ∧
      profile.logScale = TGComputeContracts.Sqrt218.scale ∧
      profile.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale ∧
      (profile.expectedSummary = none ∨
        profile.expectedSummary = some archive.summary))

def summaryShapeCheck (profile : Profile) (archive : Archive) : Bool :=
  decide (
    archive.summary.primeCount = archive.primeCount ∧
      archive.summary.primePowerEventCount = archive.eventCount ∧
      archive.summary.properPrimePowerEventCount =
        archive.eventCount - archive.primeCount ∧
      archive.summary.reusedPrimeCount =
        (archive.primes.filter
          (fun row =>
            decide (row.prime ≤ min archive.bound profile.reusedPrimeBound))).length ∧
      archive.summary.tailPrimeCount =
        (archive.primes.filter
          (fun row =>
            decide (
              profile.reusedPrimeBound < row.prime ∧
                row.prime ≤ archive.bound))).length ∧
      archive.summary.prattDigest =
        SparkInterval.Certificate.SHA256.digestString
          archive.prattTranscript ∧
      archive.summary.layoutDigest =
        SparkInterval.Certificate.SHA256.digestString
          archive.layoutTranscript)

/-- Exact architecture-neutral acceptance check.

The result is a Boolean; it cannot carry a caller-selected proposition. -/
def run (profile : Profile) (archive : Archive) : Bool :=
  headerCheck profile archive &&
    (primeRosterCheck archive &&
      (prattTableCheck archive &&
        (primePowerLayoutCheck archive &&
          (primeLogTableCheck archive &&
            (decide (
              TGComputeContracts.Sqrt218.runFixedEvents archive.eventCount
                archive.eventAt archive.logLowerAt archive.logUpperAt
                0 archive.eventCount
                TGComputeContracts.Sqrt218.FixedState.zero =
                  some archive.claimedExit) &&
              (TGComputeContracts.Sqrt218.anchorOK archive.bound
                  archive.claimedExit.weightedUpper
                  archive.claimedExit.psiLower &&
                (StreamingScan.scanCheck profile archive &&
                  summaryShapeCheck profile archive)))))))

/-- Facts exposed by a successful decoded-archive replay.

This structure contains the generic checker contract, not a source theorem and
not a caller-provided `Prop`. -/
structure ArchiveFacts (profile : Profile) (archive : Archive) : Prop where
  header :
    archive.kind = certificateKind ∧
      archive.schemaVersion = 1 ∧
      profile.bound = TGComputeContracts.Sqrt218.sourceCutoff ∧
      archive.bound = profile.bound ∧
      archive.logSeedAt = profile.logSeedAt ∧
      archive.logScale = profile.logScale ∧
      archive.reciprocalScale = profile.reciprocalScale ∧
      profile.logScale = TGComputeContracts.Sqrt218.scale ∧
      profile.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale ∧
      (profile.expectedSummary = none ∨
        profile.expectedSummary = some archive.summary)
  certificate :
    TGComputeContracts.Sqrt218.CertificateFacts
      (primeCount := archive.primeCount)
      (primeAt := archive.primeAt)
      (eventCount := archive.eventCount)
      (eventAt := archive.eventAt)
      (logLowerAt := archive.logLowerAt)
      (logUpperAt := archive.logUpperAt)
      (exit := archive.claimedExit)
  prattRows : prattTableCheck archive = true
  streaming : StreamingScan.ScanFacts profile archive
  summaryShape :
    archive.summary.primeCount = archive.primeCount ∧
      archive.summary.primePowerEventCount = archive.eventCount ∧
      archive.summary.properPrimePowerEventCount =
        archive.eventCount - archive.primeCount ∧
      archive.summary.reusedPrimeCount =
        (archive.primes.filter
          (fun row =>
            decide (row.prime ≤ min archive.bound profile.reusedPrimeBound))).length ∧
      archive.summary.tailPrimeCount =
        (archive.primes.filter
          (fun row =>
            decide (
              profile.reusedPrimeBound < row.prime ∧
                row.prime ≤ archive.bound))).length ∧
      archive.summary.prattDigest =
        SparkInterval.Certificate.SHA256.digestString
          archive.prattTranscript ∧
      archive.summary.layoutDigest =
        SparkInterval.Certificate.SHA256.digestString
          archive.layoutTranscript

/-- Ordinary, data-independent soundness of the operational checker. -/
theorem run_success_sound {profile : Profile} {archive : Archive}
    (hcheck : run profile archive = true) :
    ArchiveFacts profile archive := by
  simp only [run, Bool.and_eq_true] at hcheck
  have hheader := hcheck.1
  simp only [headerCheck, decide_eq_true_eq] at hheader
  have hprofileBound :
      profile.bound = TGComputeContracts.Sqrt218.sourceCutoff :=
    hheader.2.2.1
  have harchiveBound : archive.bound = profile.bound :=
    hheader.2.2.2.1
  have hroster := primeRosterCheck_sound hcheck.2.1
  have hpratt := hcheck.2.2.1
  have hlayout :=
    primePowerLayoutCheck_sound hroster hcheck.2.2.2.1
  have hlogs :=
    primeLogTableCheck_sound hroster hcheck.2.2.2.2.1
  have hrun := hcheck.2.2.2.2.2.1
  simp only [decide_eq_true_eq] at hrun
  have hanchor := hcheck.2.2.2.2.2.2.1
  have hstreaming :=
    StreamingScan.scanCheck_sound hcheck.2.2.2.2.2.2.2.1
  have hsummary := hcheck.2.2.2.2.2.2.2.2
  simp only [summaryShapeCheck, decide_eq_true_eq] at hsummary
  refine {
    header := hheader
    certificate := {
      roster := ?_
      layout := ?_
      logs := hlogs
      run := hrun
      anchor := ?_
    }
    prattRows := hpratt
    streaming := hstreaming
    summaryShape := hsummary
  }
  · simpa [hprofileBound, harchiveBound] using hroster
  · simpa [hprofileBound, harchiveBound] using hlayout
  · simpa [hprofileBound, harchiveBound] using hanchor

end SparkInterval.TernaryGoldbach.Sqrt218Operational
