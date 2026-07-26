/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedFactorWire

/-!
# Exact wire model for the Dirichlet q-order manifest

`TGDQORD1` is the single schedule object shared by the large-q producer,
resident FFT pipeline, completed-factor service, and source reducer.  This
module gives that binary file a total, architecture-independent Lean parser.

The parser checks:

* every fixed-width header field and the exact file size;
* the source range, nonempty primitive-modulus domain, and sample bounds;
* exact header row totals;
* absence of duplicate moduli using an `O(n log n)` sorted projection;
* both record-stream SHA-256 fields; and
* for a production file, the complete source geometry, formulaic sample
  count of every modulus, and all three published digest pins.

The production manifest's complete-file digest is the commitment to the
canonical component-signature execution permutation.  The sorted projection
separately proves that its records are exactly the formulaic primitive-modulus
source roster.  `checkScheduledFullSourceBundle` projects this same checked
manifest onto a selected resident phase and passes that exact ordered roster
to the completed-factor checker.  Thus no second, metadata-only q/sample
roster is introduced at that handoff.

No FFI, `Float`, `native_decide`, or external process occurs here.  As with
every digest-bound artifact interface, this module computes SHA-256 exactly
but does not prove cryptographic collision resistance.  It proves wire and
roster identity, not Arb containment, CUDA refinement, zero isolation,
Turing completeness, attestation, or Platt's analytic theorem.
-/

set_option autoImplicit false
set_option maxRecDepth 5000000

namespace SparkInterval.Dirichlet.QOrderManifestWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CompletedFactorWire

/-! ## Format and source constants -/

def magic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x51, 0x4f, 0x52, 0x44, 0x31]

def formatVersion : Nat := 1
def boundedClassificationCode : Nat := 0
def fullSourceClassificationCode : Nat := 1
def primitiveModulusRosterVersion : Nat := 2
def headerBytes : Nat := 112
def recordBytes : Nat := 8
def maximumRecordCount : Nat := 292_500

def sourceQStart : Nat := 10_001
def sourceQStop : Nat := 400_000
def sourceQCount : Nat := 292_500
def sourceTRowCount : Nat := 3_637_613_167

def sourceRosterDomain : String := "TGDQ_SOURCE_ROSTER_V1"
def executionOrderDomain : String := "TGDQ_EXECUTION_ORDER_V1"

def pinnedSourceRosterSHA256 : String :=
  "d80a78ee36a82e2dab0d783b2c2407eff425a5978edb46585fba09d1ca7d5a2c"

def pinnedExecutionOrderSHA256 : String :=
  "34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd"

def pinnedManifestSHA256 : String :=
  "a5ae1af2e4a9e944ccef559e169a13cd74f21c220ed882950ecd4491cbf13e93"

inductive Classification where
  | bounded
  | fullSource
  deriving Repr, DecidableEq, BEq

def decodeClassification : Nat → Option Classification
  | 0 => some .bounded
  | 1 => some .fullSource
  | _ => none

/-! ## Exact little-endian primitives -/

def checkedSlice? (raw : ByteArray) (offset count : Nat) : Option ByteArray :=
  if offset + count ≤ raw.size then
    some (raw.extract offset (offset + count))
  else
    none

def readLE (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat := do
  let bytes ← checkedSlice? raw offset width
  pure <| (List.range width).foldl
    (fun value index =>
      value + (bytes.get! index).toNat * 256 ^ index) 0

def readU32LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE 4 raw offset

def readU64LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE 8 raw offset

def readDigest (raw : ByteArray) (offset : Nat) : Option ByteArray :=
  checkedSlice? raw offset 32

def encodeLE (width value : Nat) : List UInt8 :=
  (List.range width).map fun index =>
    UInt8.ofNat ((value / 256 ^ index) % 256)

private def lowerHexDigit (value : Nat) : Char :=
  "0123456789abcdef".toList.getD value '0'

private def byteLowerHex (value : UInt8) : List Char :=
  [lowerHexDigit (value.toNat / 16), lowerHexDigit (value.toNat % 16)]

def byteArrayLowerHex (raw : ByteArray) : String :=
  String.ofList (raw.toList.flatMap byteLowerHex)

/-! ## Formulaic source roster -/

/-- For source-range `q`, primitive characters exist iff `q ≢ 2 (mod 4)`.
The exceptional small moduli do not enter this campaign. -/
def hasPrimitiveCharacterModulus (q : Nat) : Bool :=
  3 ≤ q && q ≤ sourceQStop && q % 4 != 2

/-- Platt's source height, before cancelling the rational numerator and
denominator.  Keeping it in this form makes the integer floor transparent. -/
def sourceHeightNumerator (q : Nat) : Nat :=
  max 100_000_000
    (200 * q + if q % 2 = 0 then 75_000_000 else 37_500_000)

/-- Number of ordinates `t = 5j/64` retained for modulus `q`, including
`j = 0`.  The denominator is nonzero in every accepted record because
`q ≥ 3`; the guard remains explicit in `ScheduleRecord.SourceValid`. -/
def sourceSampleCount (q : Nat) : Nat :=
  (sourceHeightNumerator q * 64) / (q * 5) + 1

structure ScheduleRecord where
  q : Nat
  sampleCount : Nat
  deriving Repr, DecidableEq, BEq

def ScheduleRecord.wireBytes (record : ScheduleRecord) : List UInt8 :=
  encodeLE 4 record.q ++ encodeLE 4 record.sampleCount

def ScheduleRecord.SourceValid (record : ScheduleRecord) : Prop :=
  3 ≤ record.q ∧
    record.q ≤ sourceQStop ∧
    record.q % 4 ≠ 2 ∧
    0 < record.sampleCount ∧
    record.sampleCount ≤ sourceSampleCount record.q

instance (record : ScheduleRecord) : Decidable record.SourceValid := by
  unfold ScheduleRecord.SourceValid
  infer_instance

def recordQLE (left right : ScheduleRecord) : Bool :=
  decide (left.q ≤ right.q)

def sourceProjection (records : List ScheduleRecord) : List ScheduleRecord :=
  records.mergeSort recordQLE

def sourceProjectionStrict (records : List ScheduleRecord) : Prop :=
  (sourceProjection records).IsChain fun left right => left.q < right.q

instance (records : List ScheduleRecord) :
    Decidable (sourceProjectionStrict records) := by
  unfold sourceProjectionStrict
  infer_instance

def formulaicSourceRoster : List ScheduleRecord :=
  (List.range (sourceQStop - sourceQStart + 1)).filterMap fun offset =>
    let q := sourceQStart + offset
    if hasPrimitiveCharacterModulus q then
      some { q, sampleCount := sourceSampleCount q }
    else
      none

def recordStreamBytes
    (domain : String) (records : List ScheduleRecord) : ByteArray :=
  (domain.toUTF8.toList ++ records.flatMap ScheduleRecord.wireBytes).toByteArray

def recordStreamSHA256
    (domain : String) (records : List ScheduleRecord) : String :=
  SHA256.digestByteArray (recordStreamBytes domain records)

/-! ## Total parser -/

structure Header where
  magicBytes : ByteArray
  version : Nat
  classification : Classification
  rosterVersion : Nat
  qStart : Nat
  qStop : Nat
  encodedRecordBytes : Nat
  qCount : Nat
  tRowCount : Nat
  sourceRosterSHA256 : ByteArray
  executionOrderSHA256 : ByteArray
  deriving DecidableEq

def Header.StructurallyValid (header : Header) : Prop :=
  header.magicBytes.toList = magic ∧
    header.version = formatVersion ∧
    header.rosterVersion = primitiveModulusRosterVersion ∧
    header.encodedRecordBytes = recordBytes ∧
    0 < header.qCount ∧
    header.qCount ≤ maximumRecordCount ∧
    sourceQStart ≤ header.qStart ∧
    header.qStart ≤ header.qStop ∧
    header.qStop ≤ sourceQStop ∧
    header.sourceRosterSHA256.size = 32 ∧
    header.executionOrderSHA256.size = 32

instance (header : Header) : Decidable header.StructurallyValid := by
  unfold Header.StructurallyValid
  infer_instance

private def parseHeader (raw : ByteArray) : Option Header := do
  let magicBytes ← checkedSlice? raw 0 8
  let version ← readU32LE raw 8
  let classificationCode ← readU32LE raw 12
  let classification ← decodeClassification classificationCode
  let rosterVersion ← readU32LE raw 16
  let qStart ← readU32LE raw 20
  let qStop ← readU32LE raw 24
  let encodedRecordBytes ← readU32LE raw 28
  let qCount ← readU64LE raw 32
  let tRowCount ← readU64LE raw 40
  let sourceRosterSHA256 ← readDigest raw 48
  let executionOrderSHA256 ← readDigest raw 80
  let header : Header := {
    magicBytes
    version
    classification
    rosterVersion
    qStart
    qStop
    encodedRecordBytes
    qCount
    tRowCount
    sourceRosterSHA256
    executionOrderSHA256
  }
  if _ : header.StructurallyValid then some header else none

private def parseRecordsAux
    (raw : ByteArray) : Nat → Nat → List ScheduleRecord →
      Option (List ScheduleRecord)
  | 0, _, reversed => some reversed.reverse
  | remaining + 1, offset, reversed => do
      let q ← readU32LE raw offset
      let sampleCount ← readU32LE raw (offset + 4)
      let record : ScheduleRecord := { q, sampleCount }
      parseRecordsAux raw remaining (offset + recordBytes) (record :: reversed)

def parseRecords
    (raw : ByteArray) (count offset : Nat) :
    Option (List ScheduleRecord) :=
  parseRecordsAux raw count offset []

structure ParsedManifest where
  header : Header
  records : List ScheduleRecord
  sourceRecords : List ScheduleRecord
  wireSize : Nat
  deriving DecidableEq

def ParsedManifest.IsValid
    (raw : ByteArray) (manifest : ParsedManifest) : Prop :=
  manifest.header.StructurallyValid ∧
    manifest.records.length = manifest.header.qCount ∧
    manifest.sourceRecords = sourceProjection manifest.records ∧
    (∀ record ∈ manifest.records, record.SourceValid) ∧
    (manifest.sourceRecords.IsChain fun left right => left.q < right.q) ∧
    manifest.sourceRecords.head?.map ScheduleRecord.q =
      some manifest.header.qStart ∧
    manifest.sourceRecords.getLast?.map ScheduleRecord.q =
      some manifest.header.qStop ∧
    (manifest.records.map ScheduleRecord.sampleCount).sum =
      manifest.header.tRowCount ∧
    byteArrayLowerHex manifest.header.sourceRosterSHA256 =
      recordStreamSHA256 sourceRosterDomain
        manifest.sourceRecords ∧
    byteArrayLowerHex manifest.header.executionOrderSHA256 =
      recordStreamSHA256 executionOrderDomain manifest.records ∧
    manifest.wireSize = raw.size ∧
    manifest.wireSize =
      headerBytes + manifest.header.qCount * recordBytes

instance (raw : ByteArray) (manifest : ParsedManifest) :
    Decidable (manifest.IsValid raw) := by
  unfold ParsedManifest.IsValid
  infer_instance

private def parseCandidate (raw : ByteArray) : Option ParsedManifest := do
  if headerBytes ≤ raw.size then pure () else none
  let header ← parseHeader raw
  if raw.size = headerBytes + header.qCount * recordBytes then pure () else none
  let records ← parseRecords raw header.qCount headerBytes
  let sourceRecords := sourceProjection records
  pure { header, records, sourceRecords, wireSize := raw.size }

/-- Parse and validate an arbitrary bounded or full-source `TGDQORD1` file. -/
def parseManifest (raw : ByteArray) : Option ParsedManifest :=
  match parseCandidate raw with
  | none => none
  | some manifest =>
      if _ : manifest.IsValid raw then some manifest else none

theorem parseManifest_sound
    {raw : ByteArray} {manifest : ParsedManifest}
    (hparse : parseManifest raw = some manifest) :
    manifest.IsValid raw := by
  unfold parseManifest at hparse
  cases hcandidate : parseCandidate raw with
  | none => simp [hcandidate] at hparse
  | some candidate =>
      simp only [hcandidate] at hparse
      split at hparse
      · rename_i hvalid
        cases hparse
        exact hvalid
      · simp at hparse

/-! ## Production identity and consumer projection -/

def ParsedManifest.FullSourceValid
    (raw : ByteArray) (manifest : ParsedManifest) : Prop :=
  manifest.IsValid raw ∧
    manifest.header.classification = .fullSource ∧
    manifest.header.qStart = sourceQStart ∧
    manifest.header.qStop = sourceQStop ∧
    manifest.header.qCount = sourceQCount ∧
    manifest.header.tRowCount = sourceTRowCount ∧
    manifest.sourceRecords = formulaicSourceRoster ∧
    byteArrayLowerHex manifest.header.sourceRosterSHA256 =
      pinnedSourceRosterSHA256 ∧
    byteArrayLowerHex manifest.header.executionOrderSHA256 =
      pinnedExecutionOrderSHA256 ∧
    SHA256.digestByteArray raw = pinnedManifestSHA256

instance (raw : ByteArray) (manifest : ParsedManifest) :
    Decidable (manifest.FullSourceValid raw) := by
  unfold ParsedManifest.FullSourceValid
  infer_instance

/-- Fail-closed production checker.  A bounded file cannot pass this API. -/
def checkFullSourceManifest (raw : ByteArray) : Option ParsedManifest :=
  match parseManifest raw with
  | none => none
  | some manifest =>
      if _ : manifest.FullSourceValid raw then some manifest else none

theorem checkFullSourceManifest_sound
    {raw : ByteArray} {manifest : ParsedManifest}
    (hcheck : checkFullSourceManifest raw = some manifest) :
    manifest.FullSourceValid raw := by
  unfold checkFullSourceManifest at hcheck
  cases hparse : parseManifest raw with
  | none => simp [hparse] at hcheck
  | some parsed =>
      simp only [hparse] at hcheck
      split at hcheck
      · rename_i hvalid
        cases hcheck
        exact hvalid
      · simp at hcheck

def ScheduleRecord.fullScheduleSample
    (record : ScheduleRecord) : CompletedFactorWire.QSample :=
  { q := record.q, sampleCount := record.sampleCount }

/-- The complete execution-order `(q,total sample count)` schedule. -/
def ParsedManifest.fullScheduleRoster
    (manifest : ParsedManifest) : List CompletedFactorWire.QSample :=
  manifest.records.map ScheduleRecord.fullScheduleSample

/-- Exact active sample count of one source record inside a resident phase. -/
def phaseSampleCount
    (phase : CompletedFactorWire.PinnedPhase)
    (record : ScheduleRecord) : Nat :=
  min record.sampleCount phase.tIndexStopExclusive - phase.firstTIndex

/-- Project the canonical execution order onto one phase, dropping inactive
moduli and clipping its terminal rows exactly as the source scheduler does. -/
def ParsedManifest.phaseCompletedFactorRoster
    (manifest : ParsedManifest)
    (phase : CompletedFactorWire.PinnedPhase) :
    List CompletedFactorWire.QSample :=
  manifest.records.filterMap fun record =>
    if phase.firstTIndex < record.sampleCount then
      some {
        q := record.q
        sampleCount := phaseSampleCount phase record
      }
    else
      none

/-- Construct a factor-bundle expectation only from the already parsed
canonical schedule and the shared pinned phase catalog. -/
def fullSourceExpectations?
    (manifest : ParsedManifest) (phaseIndex : Nat)
    (producerIdentitySHA256 : ByteArray) :
    Option CompletedFactorWire.FullSourceExpectations := do
  let phase ← CompletedFactorWire.pinnedPhase? phaseIndex
  let phaseScheduleSHA256 ←
    CompletedFactorWire.pinnedPhaseScheduleSHA256? phaseIndex
  pure {
    phaseIndex
    phase
    roster := manifest.phaseCompletedFactorRoster phase
    scheduleManifestSHA256 :=
      CompletedFactorWire.pinnedSourceScheduleManifestSHA256
    executionOrderSHA256 :=
      CompletedFactorWire.pinnedSourceExecutionOrderSHA256
    phaseScheduleSHA256
    producerIdentitySHA256
  }

/-- End-to-end wire check for one completed-factor phase.  The schedule is
checked first; its exact ordered phase projection is then the expectation
consumed by the gamma/step/checkpoint bundle checker. -/
def checkScheduledFullSourceBundle
    (scheduleRaw : ByteArray) (phaseIndex : Nat)
    (producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray) :
    Bool :=
  match checkFullSourceManifest scheduleRaw with
  | none => false
  | some manifest =>
      match fullSourceExpectations? manifest phaseIndex
          producerIdentitySHA256 with
      | none => false
      | some expected =>
          CompletedFactorWire.checkFullSourceBundle expected
            gammaRaw stepRaw checkpointRaw

def ValidatedScheduledFullSourceBundle
    (scheduleRaw : ByteArray) (phaseIndex : Nat)
    (producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray) :
    Prop :=
  ∃ manifest : ParsedManifest,
    ∃ expected : CompletedFactorWire.FullSourceExpectations,
      checkFullSourceManifest scheduleRaw = some manifest ∧
      fullSourceExpectations? manifest phaseIndex
        producerIdentitySHA256 = some expected ∧
      CompletedFactorWire.ValidatedFullSourceBundle expected
        gammaRaw stepRaw checkpointRaw

theorem checkScheduledFullSourceBundle_sound
    {scheduleRaw : ByteArray} {phaseIndex : Nat}
    {producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkScheduledFullSourceBundle scheduleRaw phaseIndex
        producerIdentitySHA256 gammaRaw stepRaw checkpointRaw = true) :
    ValidatedScheduledFullSourceBundle scheduleRaw phaseIndex
      producerIdentitySHA256 gammaRaw stepRaw checkpointRaw := by
  unfold checkScheduledFullSourceBundle at hcheck
  cases hschedule : checkFullSourceManifest scheduleRaw with
  | none => simp [hschedule] at hcheck
  | some manifest =>
      cases hexpected :
          fullSourceExpectations? manifest phaseIndex
            producerIdentitySHA256 with
      | none => simp [hschedule, hexpected] at hcheck
      | some expected =>
          refine ⟨manifest, expected, hschedule, hexpected, ?_⟩
          have hfactor :
              CompletedFactorWire.checkFullSourceBundle expected
                gammaRaw stepRaw checkpointRaw = true := by
            simpa [hschedule, hexpected] using hcheck
          exact CompletedFactorWire.checkFullSourceBundle_sound hfactor

theorem checkScheduledFullSourceBundle_exactRoster
    {scheduleRaw : ByteArray} {phaseIndex : Nat}
    {producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkScheduledFullSourceBundle scheduleRaw phaseIndex
        producerIdentitySHA256 gammaRaw stepRaw checkpointRaw = true) :
    ∃ manifest : ParsedManifest,
      ∃ phase : CompletedFactorWire.PinnedPhase,
        checkFullSourceManifest scheduleRaw = some manifest ∧
        CompletedFactorWire.pinnedPhase? phaseIndex = some phase ∧
        ∃ bundle : CompletedFactorWire.Bundle,
          CompletedFactorWire.parseCheckpointArtifact checkpointRaw =
            some bundle.checkpoint ∧
          CompletedFactorWire.recordRoster bundle.checkpoint.records =
            manifest.phaseCompletedFactorRoster phase := by
  rcases checkScheduledFullSourceBundle_sound hcheck with
    ⟨manifest, expected, hschedule, hexpected, hbundle⟩
  unfold fullSourceExpectations? at hexpected
  cases hphase : CompletedFactorWire.pinnedPhase? phaseIndex with
  | none => simp [hphase] at hexpected
  | some phase =>
      cases hdigest :
          CompletedFactorWire.pinnedPhaseScheduleSHA256? phaseIndex with
      | none => simp [hphase, hdigest] at hexpected
      | some phaseDigest =>
          simp [hphase, hdigest] at hexpected
          cases hexpected
          rcases hbundle with
            ⟨bundle, _, _, hcheckpoint, hvalid⟩
          have hmatches :
              bundle.CheckpointMatchesFullSource {
                phaseIndex
                phase
                roster := manifest.phaseCompletedFactorRoster phase
                scheduleManifestSHA256 :=
                  CompletedFactorWire.pinnedSourceScheduleManifestSHA256
                executionOrderSHA256 :=
                  CompletedFactorWire.pinnedSourceExecutionOrderSHA256
                phaseScheduleSHA256 := phaseDigest
                producerIdentitySHA256
              } :=
            hvalid.2.2.2.2.2.2.1
          have hroster :
              CompletedFactorWire.recordRoster bundle.checkpoint.records =
                manifest.phaseCompletedFactorRoster phase :=
            hmatches.2.2.2.2.2.2.2.2.2
          exact
            ⟨manifest, phase, hschedule, rfl, bundle, hcheckpoint, hroster⟩

theorem checked_full_source_roster
    {raw : ByteArray} {manifest : ParsedManifest}
    (hcheck : checkFullSourceManifest raw = some manifest) :
    manifest.sourceRecords = formulaicSourceRoster := by
  exact (checkFullSourceManifest_sound hcheck).2.2.2.2.2.2.1

theorem checked_full_source_not_bounded
    {raw : ByteArray} {manifest : ParsedManifest}
    (hcheck : checkFullSourceManifest raw = some manifest) :
    manifest.header.classification ≠ .bounded := by
  have hclass :=
    (checkFullSourceManifest_sound hcheck).2.1
  simp [hclass]

end SparkInterval.Dirichlet.QOrderManifestWire
