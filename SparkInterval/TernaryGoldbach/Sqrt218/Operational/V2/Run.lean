/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.LogRows
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.PowerLayout
import TGComputeContracts.Sqrt218.Sound

/-!
# Efficient V2 Sqrt218 checker

This is the architecture-neutral semantics intended for the fixed-width
confidential-CPU checker.  It composes four certificate-driven passes:

1. Lucas/Pratt rows and explicit composite gaps;
2. sorted prime-power events with a linear-size inverse map;
3. one directed integer logarithm ladder; and
4. one checked fixed-point event fold followed by the Abel anchor.

The source module contains no production archive.  Typechecking
`run_success_sound` proves the algorithm for arbitrary input; it does not
evaluate the cutoff-2,000,000 instance.  The concrete `run = true` execution
belongs in the measured cloud job.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

open TGComputeContracts.Sqrt218

/-- Exact protocol discriminator for the fixed-width V2 checker input. -/
def certificateKind : String :=
  "sparkinterval.sqrt218-fixed-certificate.v2"

/-- Typed, architecture-independent view of the V2 binary certificate. -/
structure Archive where
  kind : String
  schemaVersion : Nat
  bound : Nat
  logSeedAt : Nat
  logScale : Nat
  reciprocalScale : Nat
  roster : PrimeRosterCertificate
  layout : PowerLayoutCertificate
  logs : LogRows.Certificate
  claimedExit : FixedState
  deriving Repr, DecidableEq, Inhabited

namespace Archive

def primeCount (archive : Archive) : Nat :=
  archive.roster.count

def primeAt (archive : Archive) : Nat → Nat :=
  archive.roster.primeAt

def eventCount (archive : Archive) : Nat :=
  archive.layout.eventCount

def eventAt (archive : Archive) :
    Nat → TGComputeContracts.Sqrt218.PowerEvent :=
  archive.layout.eventAt

def logLowerAt (archive : Archive) : Nat → Nat :=
  archive.logs.logLowerAt

def logUpperAt (archive : Archive) : Nat → Nat :=
  archive.logs.logUpperAt

end Archive

/-- Fixed, human-readable V2 header contract at an explicitly supplied
bound.  This parameterized form exists for bounded format/kernel tests; the
production entry point below fixes it to `sourceCutoff`. -/
def headerCheckAt (expectedBound : Nat) (archive : Archive) : Bool :=
  decide (
    archive.kind = certificateKind ∧
      archive.schemaVersion = 2 ∧
      archive.bound = expectedBound ∧
      archive.logSeedAt =
        SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate.seedAt ∧
      archive.logScale = scale ∧
      archive.reciprocalScale = reciprocalScale)

/-- Production V2 header contract. -/
def headerCheck (archive : Archive) : Bool :=
  headerCheckAt sourceCutoff archive

/-- The single event fold used by the V2 mathematical checker. -/
def fixedRunCheck (archive : Archive) : Bool :=
  decide (
    runFixedEvents archive.eventCount archive.eventAt
      archive.logLowerAt archive.logUpperAt
      0 archive.eventCount FixedState.zero =
        some archive.claimedExit)

/-- Exact endpoint Abel guard. -/
def anchorCheck (archive : Archive) : Bool :=
  anchorOK archive.bound archive.claimedExit.weightedUpper
    archive.claimedExit.psiLower

/-- Complete V2 Boolean semantics at an explicitly supplied bound.

All passes are data-independent definitions.  Do not reduce this function on
the production archive during an ordinary local build.  `runAt` is exposed so
that genuinely small complete archives can exercise the same composition
without weakening any checker pass. -/
def runAt (expectedBound : Nat) (archive : Archive) : Bool :=
  headerCheckAt expectedBound archive &&
    (primeRosterCheck archive.bound archive.roster &&
      (powerLayoutCheck archive.bound archive.primeCount archive.primeAt
          archive.layout &&
        (LogRows.check archive.primeCount archive.primeAt archive.logs &&
          (fixedRunCheck archive && anchorCheck archive))))

/-- Production V2 Boolean semantics, fixed to the paper cutoff. -/
def run (archive : Archive) : Bool :=
  runAt sourceCutoff archive

/-- Ordinary, data-independent soundness of the efficient V2 checker. -/
theorem run_success_sound {archive : Archive}
    (hcheck : run archive = true) :
    CertificateFacts
      (primeCount := archive.primeCount)
      (primeAt := archive.primeAt)
      (eventCount := archive.eventCount)
      (eventAt := archive.eventAt)
      (logLowerAt := archive.logLowerAt)
      (logUpperAt := archive.logUpperAt)
      (exit := archive.claimedExit) := by
  simp only [run, runAt, Bool.and_eq_true] at hcheck
  have hheader := hcheck.1
  simp only [headerCheckAt, decide_eq_true_eq] at hheader
  have hrosterRaw :=
    primeRosterCheck_sound hcheck.2.1
  have hroster :
      PrimeRosterFacts sourceCutoff archive.primeCount archive.primeAt := by
    simpa [Archive.primeCount, Archive.primeAt, hheader.2.2.1] using
      hrosterRaw
  have hlayoutRaw :=
    powerLayoutCheck_sound hrosterRaw hcheck.2.2.1
  have hlayout :
    PrimePowerEnumerationFacts sourceCutoff
        archive.primeCount archive.primeAt
        archive.eventCount archive.eventAt := by
    simpa [Archive.primeCount, Archive.primeAt,
      Archive.eventCount, Archive.eventAt, hheader.2.2.1] using hlayoutRaw
  have hlogs :=
    LogRows.check_sound hrosterRaw hcheck.2.2.2.1
  have hrun := hcheck.2.2.2.2.1
  simp only [fixedRunCheck, decide_eq_true_eq] at hrun
  have hanchor := hcheck.2.2.2.2.2
  exact {
    roster := hroster
    layout := hlayout
    logs := hlogs
    run := hrun
    anchor := by
      simpa [anchorCheck, hheader.2.2.1] using hanchor
  }

/-- The efficient V2 checker implies the exact finite source claim with no
execution or citation axiom. -/
theorem sourceClaim_of_run {archive : Archive}
    (hcheck : run archive = true) :
    SourceClaim :=
  (run_success_sound hcheck).sourceClaim

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
