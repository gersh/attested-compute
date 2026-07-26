/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21EventWire
import SparkInterval.Zeta.PT21NativeBlockWire
import SparkInterval.Zeta.PT21StationaryJunctionWire

/-!
# Finite PT21STJ1-to-PT21BLK1 junction

This module checks the compact boundary exercised by the bounded native
integration test:

* one valid `PT21EVT1` event record;
* one valid `PT21STJ1` stationary-resolution record;
* one valid `PT21BLK1` exact-count transition;
* byte-exact hashes of the required packet, stationary trace, directed-Arb
  Turing inputs, fused source trace, and exact-rational block artifact;
* pinned CUDA/FLINT/Turing/adapter/finalizer identities; and
* the domain-separated predecessor commitment stored in `PT21BLK1`.

The checker preserves stationary multiplicity exactly.  It does not assert
that the finite samples are values of Hardy Z or that the directed-Arb inputs
satisfy the analytic Turing theorem.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21TuringBlockJunction

open SparkInterval.Certificate

abbrev EventRecord := PT21EventWire.EventRecord
abbrev JunctionRecord := PT21StationaryJunctionWire.JunctionRecord
abbrev BlockRecord := PT21NativeBlockWire.BlockRecord

def commitmentDomain : List UInt8 :=
  [115, 112, 97, 114, 107, 105, 110, 116, 101, 114, 118, 97, 108,
    47, 116, 103, 47, 112, 108, 97, 116, 116, 45, 112, 116, 50, 49,
    45, 98, 111, 117, 110, 100, 101, 100, 45, 98, 108, 111, 99, 107,
    45, 99, 104, 97, 105, 110, 45, 99, 111, 109, 109, 105, 116, 109,
    101, 110, 116, 47, 118, 49, 0]

def littleEndianU64 (value : Nat) : List UInt8 :=
  (List.range 8).map fun index =>
    UInt8.ofNat ((value / 256 ^ index) % 256)

structure RetainedPayloads where
  eventRecord : ByteArray
  junctionRecord : ByteArray
  requiredPacket : ByteArray
  stationaryTrace : ByteArray
  turingInputs : ByteArray
  sourceTrace : ByteArray
  blockArtifact : ByteArray
  deriving DecidableEq

/-- Raw SHA-256 bytes for the five payloads entering the composite
predecessor commitment.  They are redundant: `RawDigestsValid` recomputes
each lowercase digest from the retained bytes. -/
structure RawDigests where
  eventRecord : ByteArray
  junctionRecord : ByteArray
  requiredPacket : ByteArray
  stationaryTrace : ByteArray
  turingInputs : ByteArray
  deriving DecidableEq

structure ExecutionIdentities where
  junctionExecutable : ByteArray
  turingExecutable : ByteArray
  flintLibrary : ByteArray
  adapterSources : ByteArray
  finalizerExecutable : ByteArray
  deriving DecidableEq

def byteArrayLowerHex (raw : ByteArray) : String :=
  PT21NativeBlockWire.byteArrayLowerHex raw

def digestNonzero (digest : ByteArray) : Bool :=
  PT21NativeBlockWire.digestNonzero digest

def digestValid (raw digest : ByteArray) : Prop :=
  digest.size = 32 ∧
    digestNonzero digest = true ∧
    byteArrayLowerHex digest = SHA256.digestByteArray raw

instance (raw digest : ByteArray) : Decidable (digestValid raw digest) := by
  unfold digestValid
  infer_instance

def identityValid (digest : ByteArray) : Prop :=
  digest.size = 32 ∧ digestNonzero digest = true

instance (digest : ByteArray) : Decidable (identityValid digest) := by
  unfold identityValid
  infer_instance

def RawDigestsValid (payloads : RetainedPayloads)
    (digests : RawDigests) : Prop :=
  digestValid payloads.eventRecord digests.eventRecord ∧
    digestValid payloads.junctionRecord digests.junctionRecord ∧
    digestValid payloads.requiredPacket digests.requiredPacket ∧
    digestValid payloads.stationaryTrace digests.stationaryTrace ∧
    digestValid payloads.turingInputs digests.turingInputs

instance (payloads : RetainedPayloads) (digests : RawDigests) :
    Decidable (RawDigestsValid payloads digests) := by
  unfold RawDigestsValid
  infer_instance

def IdentitiesValid (identities : ExecutionIdentities) : Prop :=
  identityValid identities.junctionExecutable ∧
    identityValid identities.turingExecutable ∧
    identityValid identities.flintLibrary ∧
    identityValid identities.adapterSources ∧
    identityValid identities.finalizerExecutable

instance (identities : ExecutionIdentities) :
    Decidable (IdentitiesValid identities) := by
  unfold IdentitiesValid
  infer_instance

def expectedCommitment (block : Nat) (digests : RawDigests)
    (identities : ExecutionIdentities) : String :=
  SHA256.digestByteArray <|
    (commitmentDomain ++ littleEndianU64 block ++
      digests.eventRecord.toList ++
      digests.junctionRecord.toList ++
      digests.requiredPacket.toList ++
      digests.stationaryTrace.toList ++
      digests.turingInputs.toList ++
      identities.junctionExecutable.toList ++
      identities.turingExecutable.toList ++
      identities.flintLibrary.toList ++
      identities.adapterSources.toList ++
      identities.finalizerExecutable.toList).toByteArray

/-- Cross-record and digest relationships after all three individual wires
have passed their own total checkers. -/
def LinkedRecordsValid (payloads : RetainedPayloads)
    (digests : RawDigests) (identities : ExecutionIdentities)
    (event : EventRecord) (junction : JunctionRecord)
    (block : BlockRecord) : Prop :=
  RawDigestsValid payloads digests ∧
    IdentitiesValid identities ∧
    event.block = junction.block ∧
    junction.block = block.block ∧
    junction.eventRecordSHA256 = event.recordSHA256 ∧
    junction.eventArtifactSHA256 = event.eventArtifactSHA256 ∧
    junction.resolutionCount = block.stationaryResolutionCount ∧
    junction.stationaryTraceSHA256 = block.stationaryTraceSHA256 ∧
    junction.stationaryTraceSHA256 = digests.stationaryTrace ∧
    junction.resolverSHA256 = identities.junctionExecutable ∧
    junction.flintSHA256 = identities.flintLibrary ∧
    junction.resolvedMultiplicitySlots =
      2 * block.stationaryResolutionCount ∧
    block.requiredPacketSHA256 = digests.requiredPacket ∧
    byteArrayLowerHex block.sourceTraceSHA256 =
      SHA256.digestByteArray payloads.sourceTrace ∧
    byteArrayLowerHex block.blockArtifactSHA256 =
      SHA256.digestByteArray payloads.blockArtifact ∧
    byteArrayLowerHex block.producerCommitmentSHA256 =
      expectedCommitment block.block digests identities

instance (payloads : RetainedPayloads) (digests : RawDigests)
    (identities : ExecutionIdentities) (event : EventRecord)
    (junction : JunctionRecord) (block : BlockRecord) :
    Decidable
      (LinkedRecordsValid payloads digests identities event junction block) := by
  unfold LinkedRecordsValid
  infer_instance

def linkCheck (payloads : RetainedPayloads) (digests : RawDigests)
    (identities : ExecutionIdentities) (event : EventRecord)
    (junction : JunctionRecord) (block : BlockRecord) : Bool :=
  decide
    (LinkedRecordsValid payloads digests identities event junction block)

@[simp] theorem linkCheck_eq_true
    (payloads : RetainedPayloads) (digests : RawDigests)
    (identities : ExecutionIdentities) (event : EventRecord)
    (junction : JunctionRecord) (block : BlockRecord) :
    linkCheck payloads digests identities event junction block = true ↔
      LinkedRecordsValid payloads digests identities event junction block := by
  simp [linkCheck]

/-- One total Boolean covering all three parsers, all finite wire validators,
and the complete predecessor/digest linkage. -/
def check (payloads : RetainedPayloads) (digests : RawDigests)
    (identities : ExecutionIdentities) (blockRaw : ByteArray) : Bool :=
  match PT21EventWire.parse payloads.eventRecord,
      PT21StationaryJunctionWire.parse payloads.junctionRecord,
      PT21NativeBlockWire.parse blockRaw with
  | some event, some junction, some block =>
      event.check payloads.eventRecord &&
        junction.check payloads.junctionRecord &&
        block.check blockRaw &&
        linkCheck payloads digests identities event junction block
  | _, _, _ => false

def ValidatedBytes (payloads : RetainedPayloads) (digests : RawDigests)
    (identities : ExecutionIdentities) (blockRaw : ByteArray) : Prop :=
  ∃ event junction block,
    PT21EventWire.parse payloads.eventRecord = some event ∧
      PT21StationaryJunctionWire.parse payloads.junctionRecord =
        some junction ∧
      PT21NativeBlockWire.parse blockRaw = some block ∧
      event.IsValid payloads.eventRecord ∧
      junction.IsValid payloads.junctionRecord ∧
      block.IsValid blockRaw ∧
      LinkedRecordsValid payloads digests identities event junction block

theorem check_sound {payloads : RetainedPayloads} {digests : RawDigests}
    {identities : ExecutionIdentities} {blockRaw : ByteArray}
    (hcheck : check payloads digests identities blockRaw = true) :
    ValidatedBytes payloads digests identities blockRaw := by
  unfold check at hcheck
  cases hevent : PT21EventWire.parse payloads.eventRecord with
  | none => simp [hevent] at hcheck
  | some event =>
      cases hjunction :
          PT21StationaryJunctionWire.parse payloads.junctionRecord with
      | none => simp [hevent, hjunction] at hcheck
      | some junction =>
          cases hblock : PT21NativeBlockWire.parse blockRaw with
          | none => simp [hevent, hjunction, hblock] at hcheck
          | some block =>
              simp only [hevent, hjunction, hblock, Bool.and_eq_true] at hcheck
              exact ⟨event, junction, block, hevent, hjunction, hblock,
                (PT21EventWire.EventRecord.check_eq_true
                  payloads.eventRecord event).mp hcheck.1.1.1,
                (PT21StationaryJunctionWire.JunctionRecord.check_eq_true
                  payloads.junctionRecord junction).mp hcheck.1.1.2,
                (PT21NativeBlockWire.BlockRecord.check_eq_true
                  blockRaw block).mp hcheck.1.2,
                (linkCheck_eq_true payloads digests identities
                  event junction block).mp hcheck.2⟩

/-- The joined wire cannot collapse a resolved stationary candidate to one
slot.  The exact factor of two is visible at the final native boundary. -/
theorem preserves_stationary_multiplicity
    {payloads : RetainedPayloads} {digests : RawDigests}
    {identities : ExecutionIdentities} {event : EventRecord}
    {junction : JunctionRecord} {block : BlockRecord}
    (hvalid :
      LinkedRecordsValid payloads digests identities event junction block) :
    junction.resolvedMultiplicitySlots =
      2 * block.stationaryResolutionCount :=
  hvalid.2.2.2.2.2.2.2.2.2.2.2.1

#print axioms check_sound
#print axioms preserves_stationary_multiplicity

end SparkInterval.Zeta.PT21TuringBlockJunction
