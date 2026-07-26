/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedFactorWire

/-!
# Streaming checker for completed Dirichlet-factor artifacts

The legacy `CompletedFactorWire` parser intentionally exposes every parsed
disk and checkpoint record.  That representation is convenient for small
proof fixtures, but a production checkpoint phase can contain 2,351,903
disks.  Materializing a Lean `List` node and a `Disk` structure for every
wire row is unnecessary at the trust boundary.

This module provides a second, source-shaped checker.  It:

* keeps only the three validated headers and two natural-number counters;
* walks gamma and conductor-step disks once;
* walks checkpoint records in lockstep with the exact expected q/sample
  roster;
* checks every binary64 disk with the same exact decoder as the legacy
  checker; and
* retains the same classification, geometry, cross-artifact digest, and
  optional complete-artifact pin checks.

The executable scans are tail recursive.  Their memory use is therefore the
three input `ByteArray`s, the already-required expectation roster, one
linear-size q-freshness hash set (at most 292,500 natural keys), and constant
body-scanner state; no parsed artifact-body list is retained.  The inductive
`CheckpointRowsAt` proposition records the exact wire meaning of an accepted
scan.  It is a theorem-level specification, not a runtime data structure.

No `native_decide`, FFI, `Float`, axiom, source execution, or attestation is
used here.  As in `CompletedFactorWire`, SHA-256 binds bytes but collision
resistance remains a cryptographic assumption outside Lean's arithmetic
proof.
-/

set_option autoImplicit false
set_option maxRecDepth 5000000

namespace SparkInterval.Dirichlet.CompletedFactorStreamingWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CompletedFactorWire

/-! ## Constant-state disk scan -/

/-- Tail-recursive validation of `count` consecutive 24-byte disks. -/
def checkDiskWindow (raw : ByteArray) : Nat → Nat → Bool
  | 0, _ => true
  | count + 1, offset =>
      match parseDiskAt raw offset with
      | none => false
      | some disk =>
          if disk.check then
            checkDiskWindow raw count (offset + diskBytes)
          else
            false

/-- Proposition-level meaning of the constant-state disk scan. -/
inductive DiskWindowAt (raw : ByteArray) : Nat → Nat → Prop
  | nil (offset : Nat) : DiskWindowAt raw 0 offset
  | cons
      {count offset : Nat} {disk : Disk}
      (parse : parseDiskAt raw offset = some disk)
      (valid : disk.IsValid)
      (rest : DiskWindowAt raw count (offset + diskBytes)) :
      DiskWindowAt raw (count + 1) offset

theorem checkDiskWindow_sound
    {raw : ByteArray} {count offset : Nat}
    (hcheck : checkDiskWindow raw count offset = true) :
    DiskWindowAt raw count offset := by
  induction count generalizing offset with
  | zero =>
      exact .nil offset
  | succ count ih =>
      unfold checkDiskWindow at hcheck
      cases hparse : parseDiskAt raw offset with
      | none =>
          simp [hparse] at hcheck
      | some disk =>
          cases hdisk : disk.check with
          | false =>
              simp [hparse, hdisk] at hcheck
          | true =>
              exact .cons hparse
                ((Disk.check_eq_true disk).mp hdisk)
                (ih (by simpa [hparse, hdisk] using hcheck))

theorem DiskWindowAt.row
    {raw : ByteArray} {count offset index : Nat}
    (window : DiskWindowAt raw count offset)
    (hindex : index < count) :
    ∃ disk : Disk,
      parseDiskAt raw (offset + index * diskBytes) = some disk ∧
      disk.IsValid := by
  induction window generalizing index with
  | nil =>
      omega
  | @cons count offset disk hparse hvalid hrest ih =>
      cases index with
      | zero =>
          simpa using ⟨disk, hparse, hvalid⟩
      | succ index =>
          have htail : index < count :=
            Nat.lt_of_succ_lt_succ hindex
          rcases ih htail with ⟨tailDisk, hparseTail, hvalidTail⟩
          refine ⟨tailDisk, ?_, hvalidTail⟩
          simpa [Nat.succ_mul, Nat.add_assoc, Nat.add_comm,
            Nat.add_left_comm] using hparseTail

/-! ## Header-only gamma and step artifacts -/

structure GammaArtifact where
  header : CompletedFactorWire.GammaHeader
  wireSize : Nat
  deriving DecidableEq

def GammaArtifact.IsValid
    (raw : ByteArray) (artifact : GammaArtifact) : Prop :=
  artifact.header.IsValid ∧
    artifact.wireSize = raw.size ∧
    artifact.wireSize =
      gammaHeaderBytes + artifact.header.diskCount * diskBytes ∧
    DiskWindowAt raw artifact.header.diskCount gammaHeaderBytes

structure StepArtifact where
  header : CompletedFactorWire.StepHeader
  wireSize : Nat
  deriving DecidableEq

def StepArtifact.IsValid
    (raw : ByteArray) (artifact : StepArtifact) : Prop :=
  artifact.header.IsValid ∧
    artifact.wireSize = raw.size ∧
    artifact.wireSize =
      stepHeaderBytes + artifact.header.qCount * diskBytes ∧
    DiskWindowAt raw artifact.header.qCount stepHeaderBytes

def scanGammaArtifact (raw : ByteArray) : Option GammaArtifact := do
  if gammaHeaderBytes ≤ raw.size then pure () else none
  let header ← parseGammaHeaderOnly raw
  if raw.size = gammaHeaderBytes + header.diskCount * diskBytes then
    pure ()
  else
    none
  if checkDiskWindow raw header.diskCount gammaHeaderBytes then
    pure { header, wireSize := raw.size }
  else
    none

def scanStepArtifact (raw : ByteArray) : Option StepArtifact := do
  if stepHeaderBytes ≤ raw.size then pure () else none
  let header ← parseStepHeaderOnly raw
  if raw.size = stepHeaderBytes + header.qCount * diskBytes then
    pure ()
  else
    none
  if checkDiskWindow raw header.qCount stepHeaderBytes then
    pure { header, wireSize := raw.size }
  else
    none

theorem scanGammaArtifact_sound
    {raw : ByteArray} {artifact : GammaArtifact}
    (hscan : scanGammaArtifact raw = some artifact) :
    artifact.IsValid raw := by
  unfold scanGammaArtifact at hscan
  simp at hscan
  cases hheader : parseGammaHeaderOnly raw with
  | none =>
      simp [hheader] at hscan
  | some header =>
      simp [hheader] at hscan
      rcases hscan with
        ⟨_, hsize, hdisks, hartifact⟩
      subst artifact
      exact
        ⟨parseGammaHeaderOnly_sound hheader, rfl, hsize,
          checkDiskWindow_sound hdisks⟩

theorem scanStepArtifact_sound
    {raw : ByteArray} {artifact : StepArtifact}
    (hscan : scanStepArtifact raw = some artifact) :
    artifact.IsValid raw := by
  unfold scanStepArtifact at hscan
  simp at hscan
  cases hheader : parseStepHeaderOnly raw with
  | none =>
      simp [hheader] at hscan
  | some header =>
      simp [hheader] at hscan
      rcases hscan with
        ⟨_, hsize, hdisks, hartifact⟩
      subst artifact
      exact
        ⟨parseStepHeaderOnly_sound hheader, rfl, hsize,
          checkDiskWindow_sound hdisks⟩

/-! ## Roster-directed checkpoint scan -/

structure CheckpointScanSummary where
  stopOffset : Nat
  checkpointCount : Nat
  deriving Repr, DecidableEq

/-- Exact proposition-level trace of a checkpoint scan.  The head record is
required to encode the head expected `(q,sampleCount)` pair, so this relation
captures ordered roster equality without retaining parsed records. -/
inductive CheckpointRowsAt
    (raw : ByteArray) (phaseSampleCount checkpointSpan : Nat) :
    List QSample → Nat → Nat → CheckpointScanSummary → Prop
  | nil (offset runningCount : Nat) :
      CheckpointRowsAt raw phaseSampleCount checkpointSpan
        [] offset runningCount
        { stopOffset := offset, checkpointCount := runningCount }
  | cons
      {expected : QSample} {rest : List QSample}
      {offset runningCount q sampleCount encodedCheckpointCount reserved : Nat}
      {summary : CheckpointScanSummary}
      (readQ : readU32LE raw offset = some q)
      (readSampleCount :
        readU32LE raw (offset + 4) = some sampleCount)
      (readCheckpointCount :
        readU32LE raw (offset + 8) = some encodedCheckpointCount)
      (readReserved :
        readU32LE raw (offset + 12) = some reserved)
      (qExact : q = expected.q)
      (sampleCountExact : sampleCount = expected.sampleCount)
      (checkpointCountExact :
        encodedCheckpointCount =
          canonicalCheckpointCount sampleCount checkpointSpan)
      (reservedZero : reserved = 0)
      (samplePositive : 0 < sampleCount)
      (sampleBounded : sampleCount ≤ phaseSampleCount)
      (disks :
        DiskWindowAt raw encodedCheckpointCount
          (offset + checkpointRecordHeaderBytes))
      (tail :
        CheckpointRowsAt raw phaseSampleCount checkpointSpan rest
          (offset + checkpointRecordHeaderBytes +
            encodedCheckpointCount * diskBytes)
          (runningCount + encodedCheckpointCount) summary) :
      CheckpointRowsAt raw phaseSampleCount checkpointSpan
        (expected :: rest) offset runningCount summary

/-- Tail-recursive scan of checkpoint records against an exact runtime
roster.  The accumulator is the total number of checkpoint disks seen. -/
def scanCheckpointRows
    (raw : ByteArray) (phaseSampleCount checkpointSpan : Nat) :
    List QSample → Nat → Nat → Option CheckpointScanSummary
  | [], offset, runningCount =>
      some { stopOffset := offset, checkpointCount := runningCount }
  | expected :: rest, offset, runningCount =>
      match readU32LE raw offset with
      | none => none
      | some q =>
          match readU32LE raw (offset + 4) with
          | none => none
          | some sampleCount =>
              match readU32LE raw (offset + 8) with
              | none => none
              | some encodedCheckpointCount =>
                  match readU32LE raw (offset + 12) with
                  | none => none
                  | some reserved =>
                      if _ :
                          q = expected.q ∧
                            sampleCount = expected.sampleCount ∧
                            encodedCheckpointCount =
                              canonicalCheckpointCount sampleCount
                                checkpointSpan ∧
                            reserved = 0 ∧
                            0 < sampleCount ∧
                            sampleCount ≤ phaseSampleCount then
                        if checkDiskWindow raw encodedCheckpointCount
                            (offset + checkpointRecordHeaderBytes) then
                          scanCheckpointRows raw phaseSampleCount
                            checkpointSpan rest
                            (offset + checkpointRecordHeaderBytes +
                              encodedCheckpointCount * diskBytes)
                            (runningCount + encodedCheckpointCount)
                        else
                          none
                      else
                        none

theorem scanCheckpointRows_sound
    {raw : ByteArray} {phaseSampleCount checkpointSpan : Nat}
    {roster : List QSample} {offset runningCount : Nat}
    {summary : CheckpointScanSummary}
    (hscan :
      scanCheckpointRows raw phaseSampleCount checkpointSpan roster
        offset runningCount = some summary) :
    CheckpointRowsAt raw phaseSampleCount checkpointSpan roster
      offset runningCount summary := by
  induction roster generalizing offset runningCount with
  | nil =>
      have hsummary :
          summary =
            { stopOffset := offset, checkpointCount := runningCount } := by
        simpa [scanCheckpointRows] using hscan.symm
      subst summary
      exact .nil offset runningCount
  | cons expected rest ih =>
      unfold scanCheckpointRows at hscan
      cases hq : readU32LE raw offset with
      | none =>
          simp [hq] at hscan
      | some q =>
          simp only [hq] at hscan
          cases hsamples : readU32LE raw (offset + 4) with
          | none =>
              simp [hsamples] at hscan
          | some sampleCount =>
              simp only [hsamples] at hscan
              cases hcount :
                  readU32LE raw (offset + 8) with
              | none =>
                  simp [hcount] at hscan
              | some encodedCheckpointCount =>
                  simp only [hcount] at hscan
                  cases hreserved :
                      readU32LE raw (offset + 12) with
                  | none =>
                      simp [hreserved] at hscan
                  | some reserved =>
                      simp only [hreserved] at hscan
                      simp at hscan
                      apply CheckpointRowsAt.cons
                        hq hsamples hcount hreserved
                        hscan.1.1 hscan.1.2.1
                        hscan.1.2.2.1 hscan.1.2.2.2.1
                        hscan.1.2.2.2.2.1
                        hscan.1.2.2.2.2.2
                        (checkDiskWindow_sound hscan.2.1)
                      exact ih hscan.2.2

structure CheckpointArtifact where
  header : CompletedFactorWire.CheckpointHeader
  wireSize : Nat
  stopOffset : Nat
  scannedCheckpointCount : Nat
  deriving DecidableEq

def CheckpointArtifact.IsValid
    (expected : FullSourceExpectations)
    (raw : ByteArray) (artifact : CheckpointArtifact) : Prop :=
  artifact.header.IsValid ∧
    artifact.wireSize = raw.size ∧
    artifact.stopOffset = raw.size ∧
    artifact.scannedCheckpointCount =
      artifact.header.checkpointCount ∧
    CheckpointRowsAt raw
      (artifact.header.tIndexStopExclusive -
        artifact.header.firstTIndex)
      artifact.header.checkpointSpan expected.roster
      checkpointHeaderBytes 0
      {
        stopOffset := artifact.stopOffset
        checkpointCount := artifact.scannedCheckpointCount
      } ∧
    artifact.wireSize =
      checkpointHeaderBytes +
        artifact.header.qCount * checkpointRecordHeaderBytes +
        artifact.header.checkpointCount * diskBytes

def scanCheckpointArtifact
    (expected : FullSourceExpectations)
    (raw : ByteArray) : Option CheckpointArtifact := do
  if checkpointHeaderBytes ≤ raw.size then pure () else none
  let header ← parseCheckpointHeaderOnly raw
  if expected.roster.length = header.qCount then pure () else none
  let summary ←
    scanCheckpointRows raw
      (header.tIndexStopExclusive - header.firstTIndex)
      header.checkpointSpan expected.roster checkpointHeaderBytes 0
  if summary.stopOffset = raw.size ∧
      summary.checkpointCount = header.checkpointCount ∧
      raw.size =
        checkpointHeaderBytes +
          header.qCount * checkpointRecordHeaderBytes +
          header.checkpointCount * diskBytes then
    pure {
      header
      wireSize := raw.size
      stopOffset := summary.stopOffset
      scannedCheckpointCount := summary.checkpointCount
    }
  else
    none

theorem scanCheckpointArtifact_sound
    {expected : FullSourceExpectations} {raw : ByteArray}
    {artifact : CheckpointArtifact}
    (hscan :
      scanCheckpointArtifact expected raw = some artifact) :
    artifact.IsValid expected raw := by
  unfold scanCheckpointArtifact at hscan
  simp at hscan
  cases hheader : parseCheckpointHeaderOnly raw with
  | none =>
      simp [hheader] at hscan
  | some header =>
      simp [hheader] at hscan
      cases hrows :
          scanCheckpointRows raw
            (header.tIndexStopExclusive - header.firstTIndex)
            header.checkpointSpan expected.roster
            checkpointHeaderBytes 0 with
      | none =>
          simp [hrows] at hscan
      | some summary =>
          simp [hrows] at hscan
          rcases hscan with
            ⟨_, _, hsummary, hartifact⟩
          subst artifact
          exact
            ⟨parseCheckpointHeaderOnly_sound hheader, rfl,
              hsummary.1, hsummary.2.1,
              by
                simpa using
                  (scanCheckpointRows_sound hrows),
              hsummary.2.2⟩

/-! ## Exact full-source bindings -/

/-! ### Linear expected-roster validation

`CompletedFactorWire.FullSourceExpectations.IsValid` is intentionally phrased
with a proposition-level distinctness condition.  Its generic decision
procedure sorts a copied q projection.  The streaming checker instead uses a
hash set with capacity reserved once.  The theorem below connects successful
execution back to ordinary `List.Nodup`, and hence to the existing
source-shaped expectation proposition.
-/

def checkRosterFresh : List QSample → Std.HashSet Nat → Bool
  | [], _ => true
  | row :: rest, seen =>
      if seen.contains row.q then
        false
      else
        checkRosterFresh rest (seen.insert row.q)

theorem checkRosterFresh_sound
    {roster : List QSample} {seen : Std.HashSet Nat}
    (hcheck : checkRosterFresh roster seen = true) :
    (roster.map QSample.q).Nodup ∧
      ∀ row ∈ roster, row.q ∉ seen := by
  induction roster generalizing seen with
  | nil =>
      simp
  | cons row rest ih =>
      unfold checkRosterFresh at hcheck
      cases hcontains : seen.contains row.q with
      | true =>
          simp [hcontains] at hcheck
      | false =>
          have htail :
              checkRosterFresh rest (seen.insert row.q) = true := by
            simpa [hcontains] using hcheck
          rcases ih htail with ⟨hnodup, hfresh⟩
          have hheadFresh : row.q ∉ seen :=
            (Std.HashSet.contains_eq_false_iff_not_mem.mp hcontains)
          have hheadNotIn : row.q ∉ rest.map QSample.q := by
            intro hmember
            rcases List.mem_map.mp hmember with
              ⟨tailRow, htailRow, hq⟩
            have htailFresh :
                tailRow.q ∉ seen.insert row.q :=
              hfresh tailRow htailRow
            apply htailFresh
            rw [Std.HashSet.mem_insert]
            left
            simp [hq]
          refine
            ⟨List.nodup_cons.mpr ⟨hheadNotIn, hnodup⟩, ?_⟩
          intro candidate hcandidate
          simp only [List.mem_cons] at hcandidate
          rcases hcandidate with hcandidate | hcandidate
          · cases hcandidate
            exact hheadFresh
          · have hfreshInserted :
                candidate.q ∉ seen.insert row.q :=
              hfresh candidate hcandidate
            intro hseen
            apply hfreshInserted
            rw [Std.HashSet.mem_insert]
            exact Or.inr hseen

/-- Constant-size source metadata, excluding the large roster traversal. -/
def ExpectationsFixedMetadataValid
    (expected : FullSourceExpectations) : Prop :=
  pinnedPhase? expected.phaseIndex = some expected.phase ∧
    pinnedPhaseScheduleSHA256? expected.phaseIndex =
      some expected.phaseScheduleSHA256 ∧
    expected.scheduleManifestSHA256 =
      pinnedSourceScheduleManifestSHA256 ∧
    expected.executionOrderSHA256 =
      pinnedSourceExecutionOrderSHA256 ∧
    digestSized expected.producerIdentitySHA256

instance (expected : FullSourceExpectations) :
    Decidable (ExpectationsFixedMetadataValid expected) := by
  unfold ExpectationsFixedMetadataValid
  infer_instance

def rosterSampleTotal (roster : List QSample) : Nat :=
  (roster.map QSample.sampleCount).sum

def rosterCheckpointTotal (roster : List QSample) : Nat :=
  (roster.map fun row =>
    canonicalCheckpointCount row.sampleCount defaultCheckpointSpan).sum

structure ExpectedRosterSummary where
  rowCount : Nat
  sampleTotal : Nat
  checkpointTotal : Nat
  deriving Repr, DecidableEq

/-- Tail-recursive geometry and aggregate pass.  In particular this avoids
the stack-unsafe `List.sum` used by a generic decision procedure on a
292,500-row source expectation. -/
def scanRosterTotals (phase : PinnedPhase) :
    List QSample → Nat → Nat → Nat → Option ExpectedRosterSummary
  | [], rowCount, sampleTotal, checkpointTotal =>
      some { rowCount, sampleTotal, checkpointTotal }
  | row :: rest, rowCount, sampleTotal, checkpointTotal =>
      if _ :
          sourceQStart ≤ row.q ∧ row.q ≤ sourceQStop ∧
            0 < row.sampleCount ∧
            row.sampleCount ≤
              phase.tIndexStopExclusive - phase.firstTIndex then
        scanRosterTotals phase rest
          (rowCount + 1)
          (sampleTotal + row.sampleCount)
          (checkpointTotal +
            canonicalCheckpointCount row.sampleCount defaultCheckpointSpan)
      else
        none

theorem scanRosterTotals_sound
    {phase : PinnedPhase} {roster : List QSample}
    {rowCount sampleTotal checkpointTotal : Nat}
    {summary : ExpectedRosterSummary}
    (hscan :
      scanRosterTotals phase roster rowCount sampleTotal checkpointTotal =
        some summary) :
    summary.rowCount = rowCount + roster.length ∧
      summary.sampleTotal = sampleTotal + rosterSampleTotal roster ∧
      summary.checkpointTotal =
        checkpointTotal + rosterCheckpointTotal roster ∧
      ∀ row ∈ roster,
        sourceQStart ≤ row.q ∧ row.q ≤ sourceQStop ∧
          0 < row.sampleCount ∧
          row.sampleCount ≤
            phase.tIndexStopExclusive - phase.firstTIndex := by
  induction roster generalizing rowCount sampleTotal checkpointTotal with
  | nil =>
      simp [scanRosterTotals] at hscan
      subst summary
      simp [rosterSampleTotal, rosterCheckpointTotal]
  | cons row rest ih =>
      unfold scanRosterTotals at hscan
      split at hscan
      · rename_i hgeometry
        rcases ih hscan with
          ⟨hrows, hsamples, hcheckpoints, hrest⟩
        refine ⟨?_, ?_, ?_, ?_⟩
        · simp only [List.length_cons]
          omega
        · unfold rosterSampleTotal at hsamples ⊢
          simp only [List.map_cons, List.sum_cons]
          omega
        · unfold rosterCheckpointTotal at hcheckpoints ⊢
          simp only [List.map_cons, List.sum_cons]
          omega
        · intro candidate hcandidate
          simp only [List.mem_cons] at hcandidate
          rcases hcandidate with hcandidate | hcandidate
          · cases hcandidate
            exact hgeometry
          · exact hrest candidate hcandidate
      · simp at hscan

def ExpectedRosterSummary.MatchesPhase
    (summary : ExpectedRosterSummary) (phase : PinnedPhase) : Prop :=
  summary.rowCount = phase.qCount ∧
    summary.sampleTotal = phase.tIndexRowCount ∧
    summary.checkpointTotal = phase.checkpointCount

instance (summary : ExpectedRosterSummary) (phase : PinnedPhase) :
    Decidable (summary.MatchesPhase phase) := by
  unfold ExpectedRosterSummary.MatchesPhase
  infer_instance

theorem fullSourceExpectations_valid_of_streaming_scans
    {expected : FullSourceExpectations}
    {summary : ExpectedRosterSummary}
    (hfixed : ExpectationsFixedMetadataValid expected)
    (hfresh :
      checkRosterFresh expected.roster
        (Std.HashSet.emptyWithCapacity expected.roster.length) = true)
    (htotals :
      scanRosterTotals expected.phase expected.roster 0 0 0 =
        some summary)
    (hmatches : summary.MatchesPhase expected.phase) :
    expected.IsValid := by
  have hnodup := (checkRosterFresh_sound hfresh).1
  rcases scanRosterTotals_sound htotals with
    ⟨hrows, hsamples, hcheckpoints, hgeometry⟩
  rcases hmatches with ⟨hmatchesRows, hmatchesSamples,
    hmatchesCheckpoints⟩
  refine
    ⟨hfixed.1, hfixed.2.1, hfixed.2.2.1, hfixed.2.2.2.1,
      hfixed.2.2.2.2, ?_, ?_, hgeometry, ?_, ?_⟩
  · omega
  · exact (distinctNats_iff_nodup _).mpr hnodup
  · unfold fullSourceSampleTotal
    change rosterSampleTotal expected.roster =
      expected.phase.tIndexRowCount
    omega
  · unfold fullSourceCheckpointTotal
    change rosterCheckpointTotal expected.roster =
      expected.phase.checkpointCount
    omega

structure Bundle where
  gamma : GammaArtifact
  step : StepArtifact
  checkpoint : CheckpointArtifact
  deriving DecidableEq

def Bundle.GammaMatchesFullSource
    (expected : FullSourceExpectations) (bundle : Bundle) : Prop :=
  bundle.gamma.header.classification = .fullSource ∧
    bundle.gamma.header.firstTIndex = 0 ∧
    bundle.gamma.header.tIndexStopExclusive = sourceTIndexStop ∧
    bundle.gamma.header.diskCount = 2 * sourceTIndexStop ∧
    bundle.gamma.header.producerIdentitySHA256 =
      expected.producerIdentitySHA256

def Bundle.StepMatchesFullSource
    (expected : FullSourceExpectations) (bundle : Bundle) : Prop :=
  bundle.step.header.classification = .fullSource ∧
    bundle.step.header.qCount = sourceQCount ∧
    bundle.step.header.qStart = sourceQStart ∧
    bundle.step.header.qStop = sourceQStop ∧
    bundle.step.header.scheduleManifestSHA256 =
      expected.scheduleManifestSHA256 ∧
    bundle.step.header.executionOrderSHA256 =
      expected.executionOrderSHA256

def Bundle.CheckpointMatchesFullSource
    (expected : FullSourceExpectations) (bundle : Bundle) : Prop :=
  bundle.checkpoint.header.classification = .fullSource ∧
    bundle.checkpoint.header.phaseIndex = expected.phaseIndex ∧
    bundle.checkpoint.header.firstTIndex = expected.phase.firstTIndex ∧
    bundle.checkpoint.header.tIndexStopExclusive =
      expected.phase.tIndexStopExclusive ∧
    bundle.checkpoint.header.checkpointSpan = defaultCheckpointSpan ∧
    bundle.checkpoint.header.qCount = expected.phase.qCount ∧
    bundle.checkpoint.header.checkpointCount =
      expected.phase.checkpointCount ∧
    bundle.checkpoint.header.scheduleManifestSHA256 =
      expected.scheduleManifestSHA256 ∧
    bundle.checkpoint.header.phaseScheduleSHA256 =
      expected.phaseScheduleSHA256

def Bundle.CrossArtifactBindings
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw : ByteArray) (bundle : Bundle) : Prop :=
  bundle.gamma.header.factorConventionSHA256 =
      SparkInterval.Dirichlet.CompletedFactorWire.factorConventionSHA256 ∧
    bundle.step.header.factorConventionSHA256 =
      SparkInterval.Dirichlet.CompletedFactorWire.factorConventionSHA256 ∧
    bundle.checkpoint.header.scheduleManifestSHA256 =
      bundle.step.header.scheduleManifestSHA256 ∧
    artifactDigestMatches gammaRaw
      bundle.checkpoint.header.gammaArtifactSHA256 ∧
    artifactDigestMatches stepRaw
      bundle.checkpoint.header.stepArtifactSHA256 ∧
    bundle.gamma.header.producerIdentitySHA256 =
      expected.producerIdentitySHA256

def Bundle.FullSourceBindings
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw : ByteArray) (bundle : Bundle) : Prop :=
  expected.IsValid ∧
    bundle.GammaMatchesFullSource expected ∧
    bundle.StepMatchesFullSource expected ∧
    bundle.CheckpointMatchesFullSource expected ∧
    bundle.CrossArtifactBindings expected gammaRaw stepRaw

def Bundle.ArtifactBindings
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw : ByteArray) (bundle : Bundle) : Prop :=
  bundle.GammaMatchesFullSource expected ∧
    bundle.StepMatchesFullSource expected ∧
    bundle.CheckpointMatchesFullSource expected ∧
    bundle.CrossArtifactBindings expected gammaRaw stepRaw

instance (expected : FullSourceExpectations)
    (gammaRaw stepRaw : ByteArray) (bundle : Bundle) :
    Decidable (bundle.ArtifactBindings expected gammaRaw stepRaw) := by
  unfold Bundle.ArtifactBindings Bundle.GammaMatchesFullSource
    Bundle.StepMatchesFullSource Bundle.CheckpointMatchesFullSource
    Bundle.CrossArtifactBindings
  infer_instance

def Bundle.IsFullSourceValid
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray)
    (bundle : Bundle) : Prop :=
  expected.IsValid ∧
    bundle.gamma.IsValid gammaRaw ∧
    bundle.step.IsValid stepRaw ∧
    bundle.checkpoint.IsValid expected checkpointRaw ∧
    bundle.GammaMatchesFullSource expected ∧
    bundle.StepMatchesFullSource expected ∧
    bundle.CheckpointMatchesFullSource expected ∧
    bundle.CrossArtifactBindings expected gammaRaw stepRaw

/-- Streaming full-source checker.  The return value retains no body rows. -/
def checkFullSourceBundle
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Bool :=
  if _ : ExpectationsFixedMetadataValid expected then
    if checkRosterFresh expected.roster
        (Std.HashSet.emptyWithCapacity expected.roster.length) then
      match scanRosterTotals expected.phase expected.roster 0 0 0 with
      | none => false
      | some summary =>
          if _ : summary.MatchesPhase expected.phase then
            match scanGammaArtifact gammaRaw with
            | none => false
            | some gamma =>
                match scanStepArtifact stepRaw with
                | none => false
                | some step =>
                    match scanCheckpointArtifact expected checkpointRaw with
                    | none => false
                    | some checkpoint =>
                        decide
                          (({ gamma, step, checkpoint } :
                              Bundle).ArtifactBindings
                            expected gammaRaw stepRaw)
          else
            false
    else
      false
  else
    false

def ValidatedFullSourceBundle
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    scanGammaArtifact gammaRaw = some bundle.gamma ∧
    scanStepArtifact stepRaw = some bundle.step ∧
    scanCheckpointArtifact expected checkpointRaw =
      some bundle.checkpoint ∧
    bundle.IsFullSourceValid expected gammaRaw stepRaw checkpointRaw

theorem checkFullSourceBundle_sound
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ValidatedFullSourceBundle expected gammaRaw stepRaw checkpointRaw := by
  unfold checkFullSourceBundle at hcheck
  split at hcheck
  · rename_i hmetadata
    split at hcheck
    · rename_i hfreshCheck
      cases htotals :
          scanRosterTotals expected.phase expected.roster 0 0 0 with
      | none =>
          simp [htotals] at hcheck
      | some summary =>
          simp [htotals] at hcheck
          rcases hcheck with ⟨hmatches, hcheck⟩
          cases hgamma : scanGammaArtifact gammaRaw with
          | none =>
              simp [hgamma] at hcheck
          | some gamma =>
            cases hstep : scanStepArtifact stepRaw with
            | none =>
                simp [hgamma, hstep] at hcheck
            | some step =>
              cases hcheckpoint :
                  scanCheckpointArtifact expected checkpointRaw with
              | none =>
                  simp [hgamma, hstep, hcheckpoint] at hcheck
              | some checkpoint =>
                  have hartifactBindings :
                      ({ gamma, step, checkpoint } :
                        Bundle).ArtifactBindings expected gammaRaw stepRaw := by
                    simpa [hgamma, hstep, hcheckpoint] using hcheck
                  have hexpected : expected.IsValid :=
                    fullSourceExpectations_valid_of_streaming_scans
                      hmetadata hfreshCheck htotals hmatches
                  have hbindings :
                      ({ gamma, step, checkpoint } :
                        Bundle).FullSourceBindings
                          expected gammaRaw stepRaw :=
                    ⟨hexpected, hartifactBindings⟩
                  exact
                    ⟨{ gamma, step, checkpoint },
                      hgamma, hstep, hcheckpoint,
                      hbindings.1,
                      scanGammaArtifact_sound hgamma,
                      scanStepArtifact_sound hstep,
                      scanCheckpointArtifact_sound hcheckpoint,
                      hbindings.2.1,
                      hbindings.2.2.1,
                      hbindings.2.2.2.1,
                      hbindings.2.2.2.2⟩
    · simp at hcheck
  · simp at hcheck

/-- Accepted checkpoint bytes encode exactly the expected ordered roster;
there is no aggregate-only or set-only handoff. -/
theorem checkFullSourceBundle_exactRoster
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      scanCheckpointArtifact expected checkpointRaw =
        some bundle.checkpoint ∧
      expected.IsValid ∧
      CheckpointRowsAt checkpointRaw
        (bundle.checkpoint.header.tIndexStopExclusive -
          bundle.checkpoint.header.firstTIndex)
        bundle.checkpoint.header.checkpointSpan expected.roster
        checkpointHeaderBytes 0
        {
          stopOffset := bundle.checkpoint.stopOffset
          checkpointCount := bundle.checkpoint.scannedCheckpointCount
        } := by
  rcases checkFullSourceBundle_sound hcheck with
    ⟨bundle, _, _, hcheckpoint, hvalid⟩
  exact
    ⟨bundle, hcheckpoint, hvalid.1, hvalid.2.2.2.1.2.2.2.2.1⟩

/-- Every accepted gamma, step, and checkpoint disk is finite with a
nonnegative exact rational radius. -/
theorem checkFullSourceBundle_diskRows
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      DiskWindowAt gammaRaw bundle.gamma.header.diskCount
        gammaHeaderBytes ∧
      DiskWindowAt stepRaw bundle.step.header.qCount
        stepHeaderBytes ∧
      CheckpointRowsAt checkpointRaw
        (bundle.checkpoint.header.tIndexStopExclusive -
          bundle.checkpoint.header.firstTIndex)
        bundle.checkpoint.header.checkpointSpan expected.roster
        checkpointHeaderBytes 0
        {
          stopOffset := bundle.checkpoint.stopOffset
          checkpointCount := bundle.checkpoint.scannedCheckpointCount
        } := by
  rcases checkFullSourceBundle_sound hcheck with
    ⟨bundle, _, _, _, hvalid⟩
  exact
    ⟨bundle, hvalid.2.1.2.2.2,
      hvalid.2.2.1.2.2.2,
      hvalid.2.2.2.1.2.2.2.2.1⟩

/-! ## Complete-artifact pins -/

def Bundle.MatchesPins
    (gammaRaw stepRaw checkpointRaw : ByteArray)
    (pins : ArtifactPins) (_bundle : Bundle) : Prop :=
  pins.IsValid ∧
    SHA256.digestByteArray gammaRaw = pins.gammaArtifactSHA256 ∧
    SHA256.digestByteArray stepRaw = pins.stepArtifactSHA256 ∧
    SHA256.digestByteArray checkpointRaw =
      pins.checkpointArtifactSHA256

instance (gammaRaw stepRaw checkpointRaw : ByteArray)
    (pins : ArtifactPins) (bundle : Bundle) :
    Decidable
      (bundle.MatchesPins gammaRaw stepRaw checkpointRaw pins) := by
  unfold Bundle.MatchesPins
  infer_instance

def checkPinnedFullSourceBundle
    (expected : FullSourceExpectations) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Bool :=
  if _ : ExpectationsFixedMetadataValid expected then
    if checkRosterFresh expected.roster
        (Std.HashSet.emptyWithCapacity expected.roster.length) then
      match scanRosterTotals expected.phase expected.roster 0 0 0 with
      | none => false
      | some summary =>
          if _ : summary.MatchesPhase expected.phase then
            match scanGammaArtifact gammaRaw with
            | none => false
            | some gamma =>
                match scanStepArtifact stepRaw with
                | none => false
                | some step =>
                    match scanCheckpointArtifact expected checkpointRaw with
                    | none => false
                    | some checkpoint =>
                        decide
                          (({ gamma, step, checkpoint } :
                              Bundle).ArtifactBindings
                                expected gammaRaw stepRaw ∧
                            ({ gamma, step, checkpoint } :
                              Bundle).MatchesPins
                                gammaRaw stepRaw checkpointRaw pins)
          else
            false
    else
      false
  else
    false

def ValidatedPinnedFullSourceBundle
    (expected : FullSourceExpectations) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    scanGammaArtifact gammaRaw = some bundle.gamma ∧
    scanStepArtifact stepRaw = some bundle.step ∧
    scanCheckpointArtifact expected checkpointRaw =
      some bundle.checkpoint ∧
    bundle.IsFullSourceValid expected gammaRaw stepRaw checkpointRaw ∧
    bundle.MatchesPins gammaRaw stepRaw checkpointRaw pins

theorem checkPinnedFullSourceBundle_sound
    {expected : FullSourceExpectations} {pins : ArtifactPins}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkPinnedFullSourceBundle expected pins gammaRaw stepRaw
        checkpointRaw = true) :
    ValidatedPinnedFullSourceBundle expected pins gammaRaw stepRaw
      checkpointRaw := by
  unfold checkPinnedFullSourceBundle at hcheck
  split at hcheck
  · rename_i hmetadata
    split at hcheck
    · rename_i hfreshCheck
      cases htotals :
          scanRosterTotals expected.phase expected.roster 0 0 0 with
      | none =>
          simp [htotals] at hcheck
      | some summary =>
          simp [htotals] at hcheck
          rcases hcheck with ⟨hmatches, hcheck⟩
          cases hgamma : scanGammaArtifact gammaRaw with
          | none =>
              simp [hgamma] at hcheck
          | some gamma =>
            cases hstep : scanStepArtifact stepRaw with
            | none =>
                simp [hgamma, hstep] at hcheck
            | some step =>
              cases hcheckpoint :
                  scanCheckpointArtifact expected checkpointRaw with
              | none =>
                  simp [hgamma, hstep, hcheckpoint] at hcheck
              | some checkpoint =>
                  have haccepted :
                      ({ gamma, step, checkpoint } :
                          Bundle).ArtifactBindings expected gammaRaw stepRaw ∧
                        ({ gamma, step, checkpoint } : Bundle).MatchesPins
                          gammaRaw stepRaw checkpointRaw pins := by
                    simpa [hgamma, hstep, hcheckpoint] using hcheck
                  have hexpected : expected.IsValid :=
                    fullSourceExpectations_valid_of_streaming_scans
                      hmetadata hfreshCheck htotals hmatches
                  have hbindings :
                      ({ gamma, step, checkpoint } :
                        Bundle).FullSourceBindings
                          expected gammaRaw stepRaw :=
                    ⟨hexpected, haccepted.1⟩
                  exact
                    ⟨{ gamma, step, checkpoint },
                      hgamma, hstep, hcheckpoint,
                      ⟨hbindings.1,
                        scanGammaArtifact_sound hgamma,
                        scanStepArtifact_sound hstep,
                        scanCheckpointArtifact_sound hcheckpoint,
                        hbindings.2.1,
                        hbindings.2.2.1,
                        hbindings.2.2.2.1,
                        hbindings.2.2.2.2⟩,
                      haccepted.2⟩
    · simp at hcheck
  · simp at hcheck

end SparkInterval.Dirichlet.CompletedFactorStreamingWire
