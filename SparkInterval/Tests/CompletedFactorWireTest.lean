/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedFactorWire
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Cross-language tests for completed-factor artifacts

The three fixtures are the exact output of
`write_synthetic_unit_artifacts(q=7, first_t_index=0, sample_count=8,
checkpoint_span=4)`.  The tests cover exact field projection, full-source
classification separation, disk finiteness, canonical checkpoint counts,
cross-artifact links, complete artifact pins, and a repaired-link
substitution attack.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.Tests.CompletedFactorWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CompletedFactorWire
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

private def decodeFixture (hex : String) : ByteArray :=
  (decodeLowerHex hex).getD ByteArray.empty

private def truncatedGammaRaw : ByteArray :=
  decodeFixture
    "5447444347414d310100000000000000180000000000000000000000000000000800000000000000400000000000000005000000000000001000000000000000d4a337caef7722d145367ba2f8370353c33f1fd6c2d164e3bc71af9374731972781293f8d433537a7d3b9bc10ef7c9f757c4fab984cd46e98fde5dfcdd2c8d84000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000"

private def gammaHeaderRaw : ByteArray :=
  decodeFixture
    "5447444347414d310100000000000000180000000000000000000000000000000800000000000000400000000000000005000000000000001000000000000000d4a337caef7722d145367ba2f8370353c33f1fd6c2d164e3bc71af9374731972781293f8d433537a7d3b9bc10ef7c9f757c4fab984cd46e98fde5dfcdd2c8d84"

private def unitDiskRaw : ByteArray :=
  decodeFixture "000000000000f03f00000000000000000000000000000000"

private def gammaRaw : ByteArray :=
  (gammaHeaderRaw.toList ++
    (List.replicate 16 unitDiskRaw.toList).flatten).toByteArray

private def stepRaw : ByteArray :=
  decodeFixture
    "5447444353545031010000000000000018000000000000000200000001000000070000000000000007000000000000001cfabff28e4788390030eddd710ec196f96ce7f238232080522f0d1e6a70024e1cfabff28e4788390030eddd710ec196f96ce7f238232080522f0d1e6a70024ed4a337caef7722d145367ba2f8370353c33f1fd6c2d164e3bc71af9374731972000000000000f03f00000000000000000000000000000000"

private def checkpointRaw : ByteArray :=
  decodeFixture
    "54474443435042310100000000000000180000001000000000000000000000000000000000000000080000000000000040000000000000000500000004000000010000000000000002000000000000001cfabff28e4788390030eddd710ec196f96ce7f238232080522f0d1e6a70024e0a83c9690a5a77305e81de924c59477259b66a76132f62c233a9f4824c1837cc91f8514f0d9a162f4411b6654f8ddfa1330503c7bc00a91637685640aee57a7ef02aac16f12e4229606199f77c527e28cb1e506cebab3436ae347f2779dde35407000000080000000200000000000000000000000000f03f00000000000000000000000000000000000000000000f03f00000000000000000000000000000000"

private def scheduleDigest : ByteArray :=
  decodeFixture
    "1cfabff28e4788390030eddd710ec196f96ce7f238232080522f0d1e6a70024e"

private def phaseScheduleDigest : ByteArray :=
  decodeFixture
    "0a83c9690a5a77305e81de924c59477259b66a76132f62c233a9f4824c1837cc"

private def producerDigest : ByteArray :=
  decodeFixture
    "781293f8d433537a7d3b9bc10ef7c9f757c4fab984cd46e98fde5dfcdd2c8d84"

private def expected : BoundedExpectations := {
  phaseIndex := 0
  firstTIndex := 0
  tIndexStopExclusive := 8
  checkpointSpan := 4
  roster := [⟨7, 8⟩]
  scheduleManifestSHA256 := scheduleDigest
  executionOrderSHA256 := scheduleDigest
  phaseScheduleSHA256 := phaseScheduleDigest
  producerIdentitySHA256 := producerDigest
}

private def pins : ArtifactPins := {
  gammaArtifactSHA256 :=
    "91f8514f0d9a162f4411b6654f8ddfa1330503c7bc00a91637685640aee57a7e"
  stepArtifactSHA256 :=
    "f02aac16f12e4229606199f77c527e28cb1e506cebab3436ae347f2779dde354"
  checkpointArtifactSHA256 :=
    "0092419861bd5d1f6de8dc3d8befaa5c2875d1b4462ce12499da8a237e74ecf0"
}

private def phase0 : PinnedPhase :=
  ⟨0, 768, 292_500, 292_500, 224_640_000⟩

/-- Source-shaped metadata with a deliberately tiny, wrong ordered roster.
It is useful for proving the full-source checker does not promote a bounded
fixture merely because its digest fields are caller-supplied. -/
private def invalidFullSourceExpected : FullSourceExpectations := {
  phaseIndex := 0
  phase := phase0
  roster := [⟨7, 8⟩]
  scheduleManifestSHA256 := pinnedSourceScheduleManifestSHA256
  executionOrderSHA256 := pinnedSourceExecutionOrderSHA256
  phaseScheduleSHA256 :=
    (pinnedPhaseScheduleSHA256? 0).getD ByteArray.empty
  producerIdentitySHA256 := producerDigest
}

private def pinnedPhases : List PinnedPhase :=
  (List.range 10).filterMap pinnedPhase?

#guard pinnedPhases.length = 10
#guard (pinnedPhases.map PinnedPhase.qCount).sum = 2_013_932
#guard
  (pinnedPhases.map PinnedPhase.checkpointCount).sum = 2_351_903
#guard
  (pinnedPhases.map PinnedPhase.tIndexRowCount).sum = 3_637_613_167
#guard
  pinnedPhases.map PinnedPhase.firstTIndex =
    [0, 768, 1_600, 2_368, 3_200, 4_032, 5_568, 9_600, 49_088, 88_512]
#guard
  pinnedPhases.map PinnedPhase.tIndexStopExclusive =
    [768, 1_600, 2_368, 3_200, 4_032, 5_568, 9_600, 49_088, 88_512,
      sourceTIndexStop]
#guard decodeClassification 2 = none
#guard pinnedPhase? 0 = some phase0
#guard
  SparkInterval.Dirichlet.CompletedFactorWire.byteArrayLowerHex
      pinnedSourceScheduleManifestSHA256 =
    "a5ae1af2e4a9e944ccef559e169a13cd74f21c220ed882950ecd4491cbf13e93"
#guard
  SparkInterval.Dirichlet.CompletedFactorWire.byteArrayLowerHex
      pinnedSourceExecutionOrderSHA256 =
    "34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd"
#guard !decide invalidFullSourceExpected.IsValid

#guard gammaRaw.size = 512
#guard stepRaw.size = 168
#guard checkpointRaw.size = 272
#guard
  SHA256.digestString factorConvention =
    SparkInterval.Dirichlet.CompletedFactorWire.byteArrayLowerHex
      factorConventionSHA256
#guard truncatedGammaRaw.size = 488
#guard (parseGammaArtifact truncatedGammaRaw).isNone

#guard (parseGammaArtifact gammaRaw).isSome
#guard (parseStepArtifact stepRaw).isSome
#guard (parseCheckpointArtifact checkpointRaw).isSome

#guard
  (parseGammaArtifact gammaRaw).map
    (fun artifact => artifact.header.classification) =
      some .bounded
#guard
  (parseGammaArtifact gammaRaw).map
    (fun artifact => artifact.header.diskCount) = some 16
#guard
  (parseStepArtifact stepRaw).map
    (fun artifact => artifact.header.qStart) = some 7
#guard
  (parseCheckpointArtifact checkpointRaw).map
    (fun artifact => artifact.header.phaseIndex) = some 0
#guard
  (parseCheckpointArtifact checkpointRaw).map
    (fun artifact => recordRoster artifact.records) =
      some [⟨7, 8⟩]

#guard canonicalCheckpointCount 8 4 = 2
#guard expectedCheckpointTotal expected = 2
#guard checkBoundedBundle expected gammaRaw stepRaw checkpointRaw
#guard
  checkPinnedBoundedBundle expected pins gammaRaw stepRaw checkpointRaw
#guard
  !checkFullSourceBundle invalidFullSourceExpected gammaRaw stepRaw
    checkpointRaw
#guard
  !checkPinnedFullSourceBundle invalidFullSourceExpected pins gammaRaw stepRaw
    checkpointRaw

/-- The classification byte cannot be promoted to full source while retaining
the bounded eight-sample geometry. -/
private def falselyPromotedGamma : ByteArray :=
  gammaRaw.set! 12 1

#guard (parseGammaArtifact falselyPromotedGamma).isNone
#guard
  !checkBoundedBundle expected falselyPromotedGamma stepRaw checkpointRaw

private def falselyPromotedStep : ByteArray :=
  stepRaw.set! 12 1

private def falselyPromotedCheckpoint : ByteArray :=
  checkpointRaw.set! 12 1

#guard (parseStepArtifact falselyPromotedStep).isNone
#guard (parseCheckpointArtifact falselyPromotedCheckpoint).isNone

/-- A nonfinite radius word in the step row fails at the exact disk decoder. -/
private def nonfiniteStep : ByteArray :=
  (stepRaw.set! 166 0xf0).set! 167 0x7f

#guard (parseStepArtifact nonfiniteStep).isNone

/-- The record count must be the canonical ceiling of samples/span. -/
private def shortCheckpointRoster : ByteArray :=
  checkpointRaw.set! 216 1

#guard (parseCheckpointArtifact shortCheckpointRoster).isNone

/-- Schedule fields are checked across both the expectation and the two
linked artifacts. -/
private def substitutedStepSchedule : ByteArray :=
  stepRaw.set! 48 0

#guard
  !checkBoundedBundle expected gammaRaw substitutedStepSchedule checkpointRaw

private def substitutedCheckpointRoster : ByteArray :=
  checkpointRaw.set! 208 8

#guard (parseCheckpointArtifact substitutedCheckpointRoster).isSome
#guard
  !checkBoundedBundle expected gammaRaw stepRaw substitutedCheckpointRoster

private def substitutedPhaseSchedule : ByteArray :=
  checkpointRaw.set! 112 0

#guard (parseCheckpointArtifact substitutedPhaseSchedule).isSome
#guard
  !checkBoundedBundle expected gammaRaw stepRaw substitutedPhaseSchedule

private def zeroFirstGammaCenter : ByteArray :=
  (gammaRaw.set! 134 0).set! 135 0

private def replaceDigestAt
    (raw : ByteArray) (offset : Nat) (digest : ByteArray) : ByteArray :=
  (raw.extract 0 offset).toList ++ digest.toList ++
    (raw.extract (offset + 32) raw.size).toList |>.toByteArray

private def repairedCheckpoint : ByteArray :=
  replaceDigestAt checkpointRaw 144
    (decodeFixture (SHA256.digestByteArray zeroFirstGammaCenter))

/- Internal links can be repaired after a semantic disk substitution.  This
is why the public boundary includes immutable complete-artifact pins. -/
#guard
  SHA256.digestByteArray zeroFirstGammaCenter ≠
    pins.gammaArtifactSHA256
#guard
  checkBoundedBundle expected zeroFirstGammaCenter stepRaw repairedCheckpoint
#guard
  !checkPinnedBoundedBundle expected pins zeroFirstGammaCenter stepRaw
    repairedCheckpoint
#guard
  !checkPinnedFullSourceBundle invalidFullSourceExpected pins
    zeroFirstGammaCenter stepRaw repairedCheckpoint

#guard
  (parseGammaArtifact
    (gammaRaw.extract 0 (gammaRaw.size - 1))).isNone
#guard
  (parseCheckpointArtifact
    (checkpointRaw.toList ++ [0]).toByteArray).isNone

example {raw : ByteArray} {offset : Nat} {disk : Disk}
    (hparse : parseDiskAt raw offset = some disk) :
    readU64LE raw offset = some disk.realBits ∧
      readU64LE raw (offset + 8) = some disk.imaginaryBits ∧
      readU64LE raw (offset + 16) = some disk.radiusBits :=
  parseDiskAt_sound hparse

example {raw : ByteArray} {offset : Nat} {disk : Disk}
    (hparse : parseDiskAt raw offset = some disk)
    (hcheck : disk.check = true) :
    ∃ value : SparkInterval.Certified.ComplexDisk,
      disk.decode = some value ∧ 0 ≤ value.radius := by
  exact checkedDiskAt_sound hparse hcheck

example
    (hcheck :
      checkBoundedBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      ∀ record ∈ bundle.checkpoint.records,
        record.encodedCheckpointCount =
          canonicalCheckpointCount record.sampleCount
            bundle.checkpoint.header.checkpointSpan ∧
        record.checkpoints.length = record.encodedCheckpointCount :=
  checkBoundedBundle_checkpointCounts hcheck

example
    {sourceExpected : FullSourceExpectations} {sourcePins : ArtifactPins}
    {sourceGamma sourceStep sourceCheckpoint : ByteArray}
    (hchanged :
      SHA256.digestByteArray sourceGamma ≠
        sourcePins.gammaArtifactSHA256) :
    checkPinnedFullSourceBundle sourceExpected sourcePins sourceGamma
      sourceStep sourceCheckpoint = false :=
  checkPinnedFullSourceBundle_rejectsGammaSubstitution hchanged

example : distinctNats [10_003, 10_001, 10_005] := by
  apply (distinctNats_iff_nodup _).2
  decide

example : ¬ distinctNats [10_003, 10_001, 10_003] := by
  intro hdistinct
  have hnodup :=
    (distinctNats_iff_nodup [10_003, 10_001, 10_003]).1 hdistinct
  simp at hnodup

#print axioms decodeClassification_code
#print axioms distinctNats_iff_nodup
#print axioms Disk.check_sound
#print axioms parseDiskAt_sound
#print axioms checkedDiskAt_sound
#print axioms parseGammaArtifact_sound
#print axioms parseStepArtifact_sound
#print axioms parseCheckpointArtifact_sound
#print axioms checkBoundedBundle_sound
#print axioms checkBoundedBundle_fields
#print axioms checkBoundedBundle_checkpointCounts
#print axioms checkBoundedBundle_diskRows
#print axioms checkPinnedBoundedBundle_sound
#print axioms checkPinnedBoundedBundle_digests
#print axioms checkFullSourceBundle_sound
#print axioms checkFullSourceBundle_fields
#print axioms checkFullSourceBundle_exactRoster
#print axioms checkFullSourceBundle_checkpointCounts
#print axioms checkFullSourceBundle_diskRows
#print axioms checkPinnedFullSourceBundle_sound
#print axioms checkPinnedFullSourceBundle_digests
#print axioms checkPinnedFullSourceBundle_rejectsGammaSubstitution

end SparkInterval.Tests.CompletedFactorWire
