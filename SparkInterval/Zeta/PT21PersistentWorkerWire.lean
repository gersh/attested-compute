/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21EventWire
import SparkInterval.Zeta.PT21StationaryJunctionWire

/-!
# Finite framing for the bounded persistent PT21 worker

The persistent CUDA/FLINT and Arb processes use small binary envelopes to
avoid per-block process startup and hexadecimal JSON transport.  This module
gives those envelopes total parsers and connects an accepted junction response
to the existing `PT21EVT1` and `PT21STJ1` checkers.

No analytic fact is added here.  In particular, the stationary-trace and
Turing JSON payloads remain opaque finite bytes at this transport layer.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21PersistentWorkerWire

abbrev EventRecord := PT21EventWire.EventRecord
abbrev JunctionRecord := PT21StationaryJunctionWire.JunctionRecord

def formatVersion : Nat := 1
def sourceBlockCount : Nat := PT21EventWire.sourceBlockCount
def junctionRequestBytes : Nat := 24
def junctionResponseHeaderBytes : Nat := 40
def eventRecordBytes : Nat := PT21EventWire.eventRecordBytes
def junctionRecordBytes : Nat := PT21StationaryJunctionWire.recordBytes
def maximumStationaryTraceBytes : Nat := 16 * 1024 * 1024
def turingRequestBytes : Nat := 56
def turingResponseHeaderBytes : Nat := 16
def maximumTuringArtifactBytes : Nat := 256 * 1024

def junctionRequestMagic : List UInt8 :=
  [0x50, 0x54, 0x32, 0x31, 0x4a, 0x52, 0x51, 0x31]

def junctionResponseMagic : List UInt8 :=
  [0x50, 0x54, 0x32, 0x31, 0x4a, 0x52, 0x53, 0x31]

def turingRequestMagic : List UInt8 :=
  [0x50, 0x54, 0x32, 0x31, 0x54, 0x52, 0x51, 0x31]

def turingResponseMagic : List UInt8 :=
  [0x50, 0x54, 0x32, 0x31, 0x54, 0x52, 0x53, 0x31]

def readU32LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  PT21EventWire.readU32LE raw offset

def readU64LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  PT21EventWire.readU64LE raw offset

structure JunctionRequest where
  block : Nat
  deriving DecidableEq

def parseJunctionRequest (raw : ByteArray) : Option JunctionRequest := do
  if raw.size = junctionRequestBytes then pure () else none
  if raw.extract 0 8 = junctionRequestMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedBytes ← readU32LE raw 12
  if encodedBytes = junctionRequestBytes then pure () else none
  let block ← readU64LE raw 16
  if block < sourceBlockCount then pure { block } else none

structure TuringRequest where
  block : Nat
  requiredPacketSHA256 : ByteArray
  deriving DecidableEq

def parseTuringRequest (raw : ByteArray) : Option TuringRequest := do
  if raw.size = turingRequestBytes then pure () else none
  if raw.extract 0 8 = turingRequestMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedBytes ← readU32LE raw 12
  if encodedBytes = turingRequestBytes then pure () else none
  let block ← readU64LE raw 16
  if block < sourceBlockCount then pure () else none
  pure {
    block
    requiredPacketSHA256 := raw.extract 24 56
  }

structure JunctionResponse where
  block : Nat
  eventRecord : ByteArray
  junctionRecord : ByteArray
  stationaryTrace : ByteArray
  deriving DecidableEq

def parseJunctionResponse (raw : ByteArray) : Option JunctionResponse := do
  if junctionResponseHeaderBytes ≤ raw.size then pure () else none
  if raw.extract 0 8 = junctionResponseMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedBytes ← readU32LE raw 12
  if encodedBytes = raw.size then pure () else none
  let block ← readU64LE raw 16
  if block < sourceBlockCount then pure () else none
  let eventBytes ← readU32LE raw 24
  if eventBytes = eventRecordBytes then pure () else none
  let junctionBytes ← readU32LE raw 28
  if junctionBytes = junctionRecordBytes then pure () else none
  let traceBytes ← readU32LE raw 32
  if 0 < traceBytes ∧ traceBytes ≤ maximumStationaryTraceBytes then
    pure ()
  else
    none
  let failureFlags ← readU32LE raw 36
  if failureFlags = 0 then pure () else none
  let eventEnd := junctionResponseHeaderBytes + eventBytes
  let junctionEnd := eventEnd + junctionBytes
  let traceEnd := junctionEnd + traceBytes
  if traceEnd = raw.size then pure () else none
  pure {
    block
    eventRecord := raw.extract junctionResponseHeaderBytes eventEnd
    junctionRecord := raw.extract eventEnd junctionEnd
    stationaryTrace := raw.extract junctionEnd traceEnd
  }

structure TuringResponse where
  artifact : ByteArray
  deriving DecidableEq

def parseTuringResponse (raw : ByteArray) : Option TuringResponse := do
  if turingResponseHeaderBytes < raw.size then pure () else none
  if raw.extract 0 8 = turingResponseMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedBytes ← readU32LE raw 12
  if encodedBytes = raw.size then pure () else none
  if raw.size ≤ turingResponseHeaderBytes + maximumTuringArtifactBytes then
    pure {
      artifact := raw.extract turingResponseHeaderBytes raw.size
    }
  else
    none

def linkedRecords (response : JunctionResponse) (event : EventRecord)
    (junction : JunctionRecord) : Prop :=
  event.block = response.block ∧
    junction.block = response.block ∧
    junction.eventRecordSHA256 = event.recordSHA256

instance (response : JunctionResponse) (event : EventRecord)
    (junction : JunctionRecord) :
    Decidable (linkedRecords response event junction) := by
  unfold linkedRecords
  infer_instance

/-- The transport checker delegates the two record bodies to their existing
total finite checkers and checks the block/hash linkage exposed by the
envelope. -/
def checkJunctionResponse (raw : ByteArray) : Bool :=
  match parseJunctionResponse raw with
  | none => false
  | some response =>
      match PT21EventWire.parse response.eventRecord,
          PT21StationaryJunctionWire.parse response.junctionRecord with
      | some event, some junction =>
          event.check response.eventRecord &&
            junction.check response.junctionRecord &&
            decide (linkedRecords response event junction)
      | _, _ => false

def ValidatedJunctionResponse (raw : ByteArray) : Prop :=
  ∃ response event junction,
    parseJunctionResponse raw = some response ∧
      PT21EventWire.parse response.eventRecord = some event ∧
      PT21StationaryJunctionWire.parse response.junctionRecord =
        some junction ∧
      event.IsValid response.eventRecord ∧
      junction.IsValid response.junctionRecord ∧
      linkedRecords response event junction

theorem checkJunctionResponse_sound {raw : ByteArray}
    (hcheck : checkJunctionResponse raw = true) :
    ValidatedJunctionResponse raw := by
  unfold checkJunctionResponse at hcheck
  cases hresponse : parseJunctionResponse raw with
  | none => simp [hresponse] at hcheck
  | some response =>
      cases hevent : PT21EventWire.parse response.eventRecord with
      | none => simp [hresponse, hevent] at hcheck
      | some event =>
          cases hjunction :
              PT21StationaryJunctionWire.parse response.junctionRecord with
          | none => simp [hresponse, hevent, hjunction] at hcheck
          | some junction =>
              simp only [hresponse, hevent, hjunction, Bool.and_eq_true]
                at hcheck
              exact ⟨response, event, junction, hresponse, hevent, hjunction,
                (PT21EventWire.EventRecord.check_eq_true
                  response.eventRecord event).mp hcheck.1.1,
                (PT21StationaryJunctionWire.JunctionRecord.check_eq_true
                  response.junctionRecord junction).mp hcheck.1.2,
                of_decide_eq_true hcheck.2⟩

theorem acceptedJunctionResponse_preserves_block
    {raw : ByteArray} {response : JunctionResponse}
    {event : EventRecord} {junction : JunctionRecord}
    (hparse : parseJunctionResponse raw = some response)
    (hevent : PT21EventWire.parse response.eventRecord = some event)
    (hjunction :
      PT21StationaryJunctionWire.parse response.junctionRecord =
        some junction)
    (hcheck : checkJunctionResponse raw = true) :
    event.block = response.block ∧ junction.block = response.block := by
  rcases checkJunctionResponse_sound hcheck with
    ⟨checkedResponse, checkedEvent, checkedJunction,
      hresponse', hevent', hjunction', _, _, hlinked⟩
  rw [hparse] at hresponse'
  cases hresponse'
  rw [hevent] at hevent'
  cases hevent'
  rw [hjunction] at hjunction'
  cases hjunction'
  exact ⟨hlinked.1, hlinked.2.1⟩

#print axioms checkJunctionResponse_sound
#print axioms acceptedJunctionResponse_preserves_block

end SparkInterval.Zeta.PT21PersistentWorkerWire
