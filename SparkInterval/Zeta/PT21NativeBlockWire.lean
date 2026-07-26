/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256

/-!
# Exact parser for one PT21 native-finalizer block record

The optimized Platt--Trudgian finalizer exchanges one fixed-width
`PT21BLK1` record per source window.  This module gives that 320-byte record
an ordinary Lean parser and one total Boolean finite checker.

The field offsets and checks mirror
`tg_verifier.platt_pt21_native_finalizer.parse_block_record`:

* little-endian `u32` and `u64` fields;
* the exact magic, version, width, and source block geometry;
* telescoping lower/main/upper counts;
* zero finite-failure counters;
* one sparse refinement for every initially ambiguous disk;
* count/digest consistency for stationary and sparse fallbacks;
* unique placement and count linkage for the source-height block; and
* the domain-separated SHA-256 of all first 288 bytes.

Successful checking proves only these finite wire relationships.  In
particular, a block record does not prove that an interval encloses Hardy Z,
that a sign event realizes a zero, or that a Turing count has its analytic
meaning.  Those remain the explicit source-realization boundary.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21NativeBlockWire

open SparkInterval.Certificate

def formatVersion : Nat := 1
def blockRecordBytes : Nat := 320
def blockDigestOffset : Nat := 288
def sourceBlockCount : Nat := 2_966_443_783
def sourceHeightBlock : Nat := 2_966_443_782
def noCount : Nat := 2 ^ 64 - 1

def blockMagic : List UInt8 :=
  [0x50, 0x54, 0x32, 0x31, 0x42, 0x4c, 0x4b, 0x31]

def blockRecordDomain : List UInt8 :=
  [115, 112, 97, 114, 107, 105, 110, 116, 101, 114, 118, 97, 108,
    47, 116, 103, 47, 112, 108, 97, 116, 116, 45, 112, 116, 50, 49,
    45, 110, 97, 116, 105, 118, 101, 45, 98, 108, 111, 99, 107, 45,
    114, 101, 99, 111, 114, 100, 47, 118, 49, 0]

/-- Read one bounded unsigned little-endian field. -/
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

structure BlockRecord where
  block : Nat
  lowerCount : Nat
  upperCount : Nat
  mainSlots : Nat
  stationaryResolutionCount : Nat
  sparseRefinementCount : Nat
  initialAmbiguousCount : Nat
  invalidDiskCount : Nat
  unresolvedDiskCount : Nat
  unresolvedStationaryCount : Nat
  turingFailureCount : Nat
  replayFailureCount : Nat
  sourceHeightCountRaw : Nat
  requiredPacketSHA256 : ByteArray
  sourceTraceSHA256 : ByteArray
  blockArtifactSHA256 : ByteArray
  stationaryTraceSHA256 : ByteArray
  sparseRefinementSHA256 : ByteArray
  producerCommitmentSHA256 : ByteArray
  sourceHeightSlotsFromLower : Nat
  recordSHA256 : ByteArray
  deriving DecidableEq

/-- Field decoder used only after the exact outer width has been checked. -/
private def parseSized (raw : ByteArray) : Option BlockRecord := do
  if raw.extract 0 8 = blockMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedBytes ← readU32LE raw 12
  if encodedBytes = blockRecordBytes then pure () else none
  let block ← readU64LE raw 16
  let lowerCount ← readU64LE raw 24
  let upperCount ← readU64LE raw 32
  let mainSlots ← readU64LE raw 40
  let stationaryResolutionCount ← readU32LE raw 48
  let sparseRefinementCount ← readU32LE raw 52
  let initialAmbiguousCount ← readU32LE raw 56
  let invalidDiskCount ← readU32LE raw 60
  let unresolvedDiskCount ← readU32LE raw 64
  let unresolvedStationaryCount ← readU32LE raw 68
  let turingFailureCount ← readU32LE raw 72
  let replayFailureCount ← readU32LE raw 76
  let sourceHeightCountRaw ← readU64LE raw 80
  let requiredPacketSHA256 ← readDigest raw 88
  let sourceTraceSHA256 ← readDigest raw 120
  let blockArtifactSHA256 ← readDigest raw 152
  let stationaryTraceSHA256 ← readDigest raw 184
  let sparseRefinementSHA256 ← readDigest raw 216
  let producerCommitmentSHA256 ← readDigest raw 248
  let sourceHeightSlotsFromLower ← readU64LE raw 280
  let recordSHA256 ← readDigest raw blockDigestOffset
  pure {
    block
    lowerCount
    upperCount
    mainSlots
    stationaryResolutionCount
    sparseRefinementCount
    initialAmbiguousCount
    invalidDiskCount
    unresolvedDiskCount
    unresolvedStationaryCount
    turingFailureCount
    replayFailureCount
    sourceHeightCountRaw
    requiredPacketSHA256
    sourceTraceSHA256
    blockArtifactSHA256
    stationaryTraceSHA256
    sparseRefinementSHA256
    producerCommitmentSHA256
    sourceHeightSlotsFromLower
    recordSHA256
  }

/-- Total decoder for exactly one 320-byte `PT21BLK1` record. -/
def parse (raw : ByteArray) : Option BlockRecord :=
  if raw.size = blockRecordBytes then
    parseSized raw
  else
    none

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

/-- Domain-separated digest of the finite record prefix. -/
def expectedRecordSHA256 (raw : ByteArray) : String :=
  SHA256.digestByteArray
    (blockRecordDomain ++ (raw.extract 0 blockDigestOffset).toList).toByteArray

namespace BlockRecord

/-- Exact finite meaning of an accepted decoded record. -/
def IsValid (raw : ByteArray) (record : BlockRecord) : Prop :=
  record.block < sourceBlockCount ∧
    0 < record.lowerCount ∧
    0 < record.upperCount ∧
    record.lowerCount + record.mainSlots = record.upperCount ∧
    record.invalidDiskCount = 0 ∧
    record.unresolvedDiskCount = 0 ∧
    record.unresolvedStationaryCount = 0 ∧
    record.turingFailureCount = 0 ∧
    record.replayFailureCount = 0 ∧
    record.initialAmbiguousCount = record.sparseRefinementCount ∧
    digestNonzero record.requiredPacketSHA256 = true ∧
    digestNonzero record.sourceTraceSHA256 = true ∧
    digestNonzero record.blockArtifactSHA256 = true ∧
    digestNonzero record.producerCommitmentSHA256 = true ∧
    ((record.stationaryResolutionCount = 0) ↔
      record.stationaryTraceSHA256 = zeroDigest) ∧
    ((record.sparseRefinementCount = 0) ↔
      record.sparseRefinementSHA256 = zeroDigest) ∧
    ((record.block = sourceHeightBlock) ↔
      record.sourceHeightCountRaw ≠ noCount) ∧
    (if record.sourceHeightCountRaw = noCount then
      record.sourceHeightSlotsFromLower = 0
    else
      record.sourceHeightSlotsFromLower ≤ record.mainSlots ∧
        record.lowerCount + record.sourceHeightSlotsFromLower =
          record.sourceHeightCountRaw) ∧
    byteArrayLowerHex record.recordSHA256 = expectedRecordSHA256 raw

instance (raw : ByteArray) (record : BlockRecord) :
    Decidable (record.IsValid raw) := by
  unfold IsValid
  infer_instance

/-- One total Boolean over the complete decoded finite record. -/
def check (raw : ByteArray) (record : BlockRecord) : Bool :=
  decide (record.IsValid raw)

@[simp] theorem check_eq_true (raw : ByteArray) (record : BlockRecord) :
    record.check raw = true ↔ record.IsValid raw := by
  simp [check]

end BlockRecord

/-- Complete byte-level finite acceptance proposition. -/
def ValidatedBytes (raw : ByteArray) : Prop :=
  ∃ record : BlockRecord,
    parse raw = some record ∧ record.IsValid raw

/-- Single fail-closed parser/checker for a complete native block record. -/
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
        (BlockRecord.check_eq_true raw record).mp (by
          simpa [hparse] using hcheck)⟩

theorem checkBytes_parse {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    ∃ record, parse raw = some record := by
  rcases checkBytes_sound hcheck with ⟨record, hparse, _⟩
  exact ⟨record, hparse⟩

theorem checkBytes_size {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    raw.size = blockRecordBytes := by
  rcases checkBytes_parse hcheck with ⟨record, hparse⟩
  by_cases hsize : raw.size = blockRecordBytes
  · exact hsize
  · simp [parse, hsize] at hparse

end SparkInterval.Zeta.PT21NativeBlockWire
