/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256

/-!
# Exact parser for the nonterminal PT21 fused event record

`PT21EVT1` is the 192-byte output of the source DD transform followed by the
three-stream CUDA event scanner.  It records direct-event counts and weights,
the exact number of stationary candidates still awaiting Gaussian--sinc
resolution, and a Merkle commitment to the required disks and compact event
arrays.

This checker intentionally cannot accept a record as `PT21BLK1`: no lower or
upper Turing count exists in this format, and every stationary candidate is
still unresolved.  The event-artifact digest is an opaque finite commitment
until a separately proved physical/source realization binds it to Hardy Z.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21EventWire

open SparkInterval.Certificate

def formatVersion : Nat := 1
def eventRecordBytes : Nat := 192
def recordDigestOffset : Nat := 160
def sourceBlockCount : Nat := 2_966_443_783
def requiredSampleCount : Nat := 25_741

def recordMagic : List UInt8 :=
  [0x50, 0x54, 0x32, 0x31, 0x45, 0x56, 0x54, 0x31]

def recordDomain : List UInt8 :=
  [115, 112, 97, 114, 107, 105, 110, 116, 101, 114, 118, 97, 108,
    47, 116, 103, 47, 112, 108, 97, 116, 116, 45, 112, 116, 50,
    49, 45, 101, 118, 101, 110, 116, 45, 114, 101, 99, 111, 114,
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

def readI64LE (raw : ByteArray) (offset : Nat) : Option Int := do
  let value ← readU64LE raw offset
  if value < 2 ^ 63 then
    pure (Int.ofNat value)
  else
    pure (Int.ofNat value - Int.ofNat (2 ^ 64))

def readDigest (raw : ByteArray) (offset : Nat) : Option ByteArray :=
  if offset + 32 ≤ raw.size then
    some (raw.extract offset (offset + 32))
  else
    none

structure EventRecord where
  block : Nat
  failureFlags : Nat
  certifiedSampleCount : Nat
  digestValid : Nat
  leftDirectCount : Nat
  mainDirectCount : Nat
  rightDirectCount : Nat
  leftStationaryCount : Nat
  mainStationaryCount : Nat
  rightStationaryCount : Nat
  leftDirectSlots : Nat
  mainDirectSlots : Nat
  rightDirectSlots : Nat
  unresolvedStationaryCount : Nat
  leftNleftUnits : Int
  mainNleftUnits : Int
  rightNleftUnits : Int
  leftNrightUnits : Int
  mainNrightUnits : Int
  rightNrightUnits : Int
  eventArtifactSHA256 : ByteArray
  recordSHA256 : ByteArray
  deriving DecidableEq

private def parseSized (raw : ByteArray) : Option EventRecord := do
  if raw.extract 0 8 = recordMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedBytes ← readU32LE raw 12
  if encodedBytes = eventRecordBytes then pure () else none
  let block ← readU64LE raw 16
  let failureFlags ← readU32LE raw 24
  let certifiedSampleCount ← readU32LE raw 28
  let digestValid ← readU32LE raw 32
  let reserved ← readU32LE raw 36
  if reserved = 0 then pure () else none
  let leftDirectCount ← readU32LE raw 40
  let mainDirectCount ← readU32LE raw 44
  let rightDirectCount ← readU32LE raw 48
  let leftStationaryCount ← readU32LE raw 52
  let mainStationaryCount ← readU32LE raw 56
  let rightStationaryCount ← readU32LE raw 60
  let leftDirectSlots ← readU32LE raw 64
  let mainDirectSlots ← readU32LE raw 68
  let rightDirectSlots ← readU32LE raw 72
  let unresolvedStationaryCount ← readU32LE raw 76
  let leftNleftUnits ← readI64LE raw 80
  let mainNleftUnits ← readI64LE raw 88
  let rightNleftUnits ← readI64LE raw 96
  let leftNrightUnits ← readI64LE raw 104
  let mainNrightUnits ← readI64LE raw 112
  let rightNrightUnits ← readI64LE raw 120
  let eventArtifactSHA256 ← readDigest raw 128
  let recordSHA256 ← readDigest raw recordDigestOffset
  pure {
    block
    failureFlags
    certifiedSampleCount
    digestValid
    leftDirectCount
    mainDirectCount
    rightDirectCount
    leftStationaryCount
    mainStationaryCount
    rightStationaryCount
    leftDirectSlots
    mainDirectSlots
    rightDirectSlots
    unresolvedStationaryCount
    leftNleftUnits
    mainNleftUnits
    rightNleftUnits
    leftNrightUnits
    mainNrightUnits
    rightNrightUnits
    eventArtifactSHA256
    recordSHA256
  }

/-- Total decoder for exactly one `PT21EVT1` record. -/
def parse (raw : ByteArray) : Option EventRecord :=
  if raw.size = eventRecordBytes then parseSized raw else none

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

def weightInBounds (count edgeCount : Nat) (left right : Int) : Prop :=
  let maximum : Int := Int.ofNat (count * (edgeCount - 1))
  (-maximum ≤ left ∧ left ≤ 0 ∧ 0 ≤ right ∧ right ≤ maximum)

namespace EventRecord

/-- Exact finite meaning of an accepted nonterminal event record. -/
def IsValid (raw : ByteArray) (record : EventRecord) : Prop :=
  record.block < sourceBlockCount ∧
    record.failureFlags = 0 ∧
    record.certifiedSampleCount = requiredSampleCount ∧
    record.digestValid = 1 ∧
    record.leftDirectCount ≤ 512 ∧
    record.mainDirectCount ≤ 24_576 ∧
    record.rightDirectCount ≤ 512 ∧
    record.leftStationaryCount ≤ 510 ∧
    record.mainStationaryCount ≤ 24_574 ∧
    record.rightStationaryCount ≤ 510 ∧
    record.leftDirectSlots = record.leftDirectCount ∧
    record.mainDirectSlots = record.mainDirectCount ∧
    record.rightDirectSlots = record.rightDirectCount ∧
    record.unresolvedStationaryCount =
      record.leftStationaryCount +
        record.mainStationaryCount + record.rightStationaryCount ∧
    weightInBounds record.leftDirectCount 512
      record.leftNleftUnits record.leftNrightUnits ∧
    weightInBounds record.mainDirectCount 24_576
      record.mainNleftUnits record.mainNrightUnits ∧
    weightInBounds record.rightDirectCount 512
      record.rightNleftUnits record.rightNrightUnits ∧
    digestNonzero record.eventArtifactSHA256 = true ∧
    byteArrayLowerHex record.recordSHA256 = expectedRecordSHA256 raw

instance (raw : ByteArray) (record : EventRecord) :
    Decidable (record.IsValid raw) := by
  unfold IsValid weightInBounds
  infer_instance

def check (raw : ByteArray) (record : EventRecord) : Bool :=
  decide (record.IsValid raw)

@[simp] theorem check_eq_true (raw : ByteArray) (record : EventRecord) :
    record.check raw = true ↔ record.IsValid raw := by
  simp [check]

/-- An accepted wire carries the exact pending-work count expected by the
Gaussian--sinc stationary resolver; it does not claim those candidates are
already zero slots. -/
theorem unresolved_eq_candidate_sum {raw : ByteArray} {record : EventRecord}
    (hvalid : record.IsValid raw) :
    record.unresolvedStationaryCount =
      record.leftStationaryCount +
        record.mainStationaryCount + record.rightStationaryCount :=
  hvalid.2.2.2.2.2.2.2.2.2.2.2.2.2.1

end EventRecord

def ValidatedBytes (raw : ByteArray) : Prop :=
  ∃ record : EventRecord, parse raw = some record ∧ record.IsValid raw

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
        (EventRecord.check_eq_true raw record).mp (by
          simpa [hparse] using hcheck)⟩

theorem checkBytes_size {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    raw.size = eventRecordBytes := by
  rcases checkBytes_sound hcheck with ⟨record, hparse, _⟩
  by_cases hsize : raw.size = eventRecordBytes
  · exact hsize
  · simp [parse, hsize] at hparse

end SparkInterval.Zeta.PT21EventWire
