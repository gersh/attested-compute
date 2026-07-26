/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256

/-!
# Finite wire checker for the PT21 event-to-stationary junction

`PT21STJ1` is the fixed 400-byte link between an accepted `PT21EVT1`
scanner record and the bounded FLINT Gaussian--sinc stationary resolver.  It
binds the event root, exact candidate/input/refinement digests, finite output,
and resolver/FLINT identities.

This checker establishes only finite wire relationships.  In particular,
`semanticRealizationFlags` must be zero: no Hardy-Z endpoint, FLINT-to-Mathlib,
or analytic Turing realization can be encoded in this record.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21StationaryJunctionWire

open SparkInterval.Certificate

def formatVersion : Nat := 1
def recordBytes : Nat := 400
def recordDigestOffset : Nat := 368
def sourceBlockCount : Nat := 2_966_443_783
def maximumCandidates : Nat := 10_000
def sourcePrecisionBits : Nat := 128
def flintRelease : Nat := 30_600

def recordMagic : List UInt8 :=
  [0x50, 0x54, 0x32, 0x31, 0x53, 0x54, 0x4a, 0x31]

def recordDomain : List UInt8 :=
  [115, 112, 97, 114, 107, 105, 110, 116, 101, 114, 118, 97, 108,
    47, 116, 103, 47, 112, 108, 97, 116, 116, 45, 112, 116, 50, 49,
    45, 115, 116, 97, 116, 105, 111, 110, 97, 114, 121, 45, 106,
    117, 110, 99, 116, 105, 111, 110, 45, 114, 101, 99, 111, 114,
    100, 47, 118, 49, 0]

def readLE (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat :=
  if offset + width ≤ raw.size then
    some ((List.range width).foldl
      (fun value index =>
        value + (raw.get! (offset + index)).toNat * 256 ^ index) 0)
  else
    none

def readU32LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE 4 raw offset

def readU64LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE 8 raw offset

def readDigest (raw : ByteArray) (offset : Nat) : Option ByteArray :=
  if offset + 32 ≤ raw.size then
    some (raw.extract offset (offset + 32))
  else
    none

structure JunctionRecord where
  block : Nat
  failureFlags : Nat
  candidateCount : Nat
  resolutionCount : Nat
  ambiguousInputCount : Nat
  refinementCount : Nat
  resolvedMultiplicitySlots : Nat
  precisionBits : Nat
  maximumDepth : Nat
  replayExtraPrecisionBits : Nat
  flintReleaseRaw : Nat
  semanticRealizationFlags : Nat
  resolverReplayAccepted : Nat
  higherPrecisionContainmentComplete : Nat
  eventRecordSHA256 : ByteArray
  eventArtifactSHA256 : ByteArray
  candidateListSHA256 : ByteArray
  resolverInputSHA256 : ByteArray
  refinementTraceSHA256 : ByteArray
  resolutionSHA256 : ByteArray
  stationaryTraceSHA256 : ByteArray
  resolverSHA256 : ByteArray
  flintSHA256 : ByteArray
  recordSHA256 : ByteArray
  deriving DecidableEq

private def parseSized (raw : ByteArray) : Option JunctionRecord := do
  if raw.extract 0 8 = recordMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedBytes ← readU32LE raw 12
  if encodedBytes = recordBytes then pure () else none
  let block ← readU64LE raw 16
  let failureFlags ← readU64LE raw 24
  let candidateCount ← readU32LE raw 32
  let resolutionCount ← readU32LE raw 36
  let ambiguousInputCount ← readU32LE raw 40
  let refinementCount ← readU32LE raw 44
  let resolvedMultiplicitySlots ← readU32LE raw 48
  let precisionBits ← readU32LE raw 52
  let maximumDepth ← readU32LE raw 56
  let replayExtraPrecisionBits ← readU32LE raw 60
  let flintReleaseRaw ← readU32LE raw 64
  let semanticRealizationFlags ← readU32LE raw 68
  let resolverReplayAccepted ← readU32LE raw 72
  let higherPrecisionContainmentComplete ← readU32LE raw 76
  let eventRecordSHA256 ← readDigest raw 80
  let eventArtifactSHA256 ← readDigest raw 112
  let candidateListSHA256 ← readDigest raw 144
  let resolverInputSHA256 ← readDigest raw 176
  let refinementTraceSHA256 ← readDigest raw 208
  let resolutionSHA256 ← readDigest raw 240
  let stationaryTraceSHA256 ← readDigest raw 272
  let resolverSHA256 ← readDigest raw 304
  let flintSHA256 ← readDigest raw 336
  let recordSHA256 ← readDigest raw recordDigestOffset
  pure {
    block
    failureFlags
    candidateCount
    resolutionCount
    ambiguousInputCount
    refinementCount
    resolvedMultiplicitySlots
    precisionBits
    maximumDepth
    replayExtraPrecisionBits
    flintReleaseRaw
    semanticRealizationFlags
    resolverReplayAccepted
    higherPrecisionContainmentComplete
    eventRecordSHA256
    eventArtifactSHA256
    candidateListSHA256
    resolverInputSHA256
    refinementTraceSHA256
    resolutionSHA256
    stationaryTraceSHA256
    resolverSHA256
    flintSHA256
    recordSHA256
  }

/-- Total decoder for exactly one 400-byte `PT21STJ1` record. -/
def parse (raw : ByteArray) : Option JunctionRecord :=
  if raw.size = recordBytes then parseSized raw else none

def zeroDigest : ByteArray :=
  (List.replicate 32 (0 : UInt8)).toByteArray

def digestNonzero (digest : ByteArray) : Bool :=
  digest != zeroDigest

private def lowerHexDigit (value : Nat) : Char :=
  "0123456789abcdef".toList.getD value '0'

private def byteLowerHex (value : UInt8) : List Char :=
  [lowerHexDigit (value.toNat / 16), lowerHexDigit (value.toNat % 16)]

def byteArrayLowerHex (raw : ByteArray) : String :=
  String.ofList (raw.toList.flatMap byteLowerHex)

def expectedRecordSHA256 (raw : ByteArray) : String :=
  SHA256.digestByteArray
    (recordDomain ++ (raw.extract 0 recordDigestOffset).toList).toByteArray

namespace JunctionRecord

/-- Exact finite meaning of an accepted stationary-junction wire. -/
def IsValid (raw : ByteArray) (record : JunctionRecord) : Prop :=
  record.block < sourceBlockCount ∧
    record.failureFlags = 0 ∧
    record.candidateCount ≤ maximumCandidates ∧
    record.resolutionCount = record.candidateCount ∧
    record.ambiguousInputCount = record.refinementCount ∧
    record.ambiguousInputCount = 0 ∧
    record.refinementCount = 0 ∧
    record.resolvedMultiplicitySlots = 2 * record.candidateCount ∧
    record.precisionBits = sourcePrecisionBits ∧
    0 < record.maximumDepth ∧
    record.maximumDepth ≤ 96 ∧
    32 ≤ record.replayExtraPrecisionBits ∧
    record.replayExtraPrecisionBits ≤ 512 ∧
    record.flintReleaseRaw = flintRelease ∧
    record.semanticRealizationFlags = 0 ∧
    record.resolverReplayAccepted = 1 ∧
    record.higherPrecisionContainmentComplete = 1 ∧
    digestNonzero record.eventRecordSHA256 = true ∧
    digestNonzero record.eventArtifactSHA256 = true ∧
    digestNonzero record.candidateListSHA256 = true ∧
    digestNonzero record.resolverInputSHA256 = true ∧
    digestNonzero record.refinementTraceSHA256 = true ∧
    digestNonzero record.resolutionSHA256 = true ∧
    digestNonzero record.stationaryTraceSHA256 = true ∧
    digestNonzero record.resolverSHA256 = true ∧
    digestNonzero record.flintSHA256 = true ∧
    byteArrayLowerHex record.recordSHA256 = expectedRecordSHA256 raw

instance (raw : ByteArray) (record : JunctionRecord) :
    Decidable (record.IsValid raw) := by
  unfold IsValid
  infer_instance

def check (raw : ByteArray) (record : JunctionRecord) : Bool :=
  decide (record.IsValid raw)

@[simp] theorem check_eq_true (raw : ByteArray) (record : JunctionRecord) :
    record.check raw = true ↔ record.IsValid raw := by
  simp [check]

/-- The finite junction preserves the source's conservative multiplicity-two
accounting instead of silently treating a stationary candidate as one zero. -/
theorem resolvedMultiplicitySlots_eq
    {raw : ByteArray} {record : JunctionRecord}
    (hvalid : record.IsValid raw) :
    record.resolvedMultiplicitySlots = 2 * record.candidateCount :=
  hvalid.2.2.2.2.2.2.2.1

/-- Derived pending-work count.  It is not trusted as a second independent
field: accepted records make it zero by exact count equality. -/
def unresolvedStationaryCount (record : JunctionRecord) : Nat :=
  record.candidateCount - record.resolutionCount

theorem resolutionCount_eq_candidateCount
    {raw : ByteArray} {record : JunctionRecord}
    (hvalid : record.IsValid raw) :
    record.resolutionCount = record.candidateCount :=
  hvalid.2.2.2.1

theorem unresolvedStationaryCount_eq_zero
    {raw : ByteArray} {record : JunctionRecord}
    (hvalid : record.IsValid raw) :
    record.unresolvedStationaryCount = 0 := by
  unfold unresolvedStationaryCount
  rw [resolutionCount_eq_candidateCount hvalid]
  simp

end JunctionRecord

def ValidatedBytes (raw : ByteArray) : Prop :=
  ∃ record : JunctionRecord, parse raw = some record ∧ record.IsValid raw

def checkBytes (raw : ByteArray) : Bool :=
  match parse raw with
  | none => false
  | some record => record.check raw

theorem checkBytes_sound {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    ValidatedBytes raw := by
  unfold checkBytes at hcheck
  cases hparse : parse raw with
  | none =>
      simp [hparse] at hcheck
  | some record =>
      exact ⟨record, hparse,
        (JunctionRecord.check_eq_true raw record).mp (by
          simpa [hparse] using hcheck)⟩

theorem checkBytes_size {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    raw.size = recordBytes := by
  rcases checkBytes_sound hcheck with ⟨record, hparse, _⟩
  by_cases hsize : raw.size = recordBytes
  · exact hsize
  · simp [parse, hsize] at hparse

#print axioms JunctionRecord.resolvedMultiplicitySlots_eq
#print axioms JunctionRecord.unresolvedStationaryCount_eq_zero
#print axioms checkBytes_sound
#print axioms checkBytes_size

end SparkInterval.Zeta.PT21StationaryJunctionWire
