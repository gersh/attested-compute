/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedFactorStreamingWire
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Bounded tests for the completed-factor streaming checker

These are the same exact Python-writer fixtures used by the materializing
checker tests.  They exercise positive header/body scans plus fail-closed
disk, roster, count, truncation, and trailing-byte controls.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.Tests.CompletedFactorStreamingWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CompletedFactorWire
open SparkInterval.Dirichlet.CompletedFactorStreamingWire
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

private def decodeFixture (hex : String) : ByteArray :=
  (decodeLowerHex hex).getD ByteArray.empty

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

private def boundedExpected : FullSourceExpectations := {
  phaseIndex := 0
  phase := ⟨0, 768, 292_500, 292_500, 224_640_000⟩
  roster := [⟨7, 8⟩]
  scheduleManifestSHA256 := pinnedSourceScheduleManifestSHA256
  executionOrderSHA256 := pinnedSourceExecutionOrderSHA256
  phaseScheduleSHA256 :=
    (pinnedPhaseScheduleSHA256? 0).getD ByteArray.empty
  producerIdentitySHA256 :=
    decodeFixture
      "781293f8d433537a7d3b9bc10ef7c9f757c4fab984cd46e98fde5dfcdd2c8d84"
}

#guard (scanGammaArtifact gammaRaw).isSome
#guard (scanStepArtifact stepRaw).isSome
#guard (scanCheckpointArtifact boundedExpected checkpointRaw).isSome
#guard
  checkRosterFresh [⟨10_003, 8⟩, ⟨10_001, 8⟩, ⟨10_005, 8⟩]
    (Std.HashSet.emptyWithCapacity 3)
#guard
  !checkRosterFresh [⟨10_003, 8⟩, ⟨10_001, 8⟩, ⟨10_003, 7⟩]
    (Std.HashSet.emptyWithCapacity 3)

private def tinyPhase : PinnedPhase :=
  ⟨0, 8, 2, 2, 16⟩

#guard
  scanRosterTotals tinyPhase [⟨10_001, 8⟩, ⟨10_003, 8⟩] 0 0 0 =
    some ⟨2, 16, 2⟩
#guard
  (scanRosterTotals tinyPhase [⟨9_999, 8⟩] 0 0 0).isNone
#guard
  (scanRosterTotals tinyPhase [⟨10_001, 0⟩] 0 0 0).isNone

#guard
  (scanCheckpointArtifact boundedExpected checkpointRaw).map
      (fun artifact =>
        (artifact.stopOffset, artifact.scannedCheckpointCount)) =
    some (checkpointRaw.size, 2)

private def wrongRosterExpected : FullSourceExpectations := {
  boundedExpected with roster := [⟨11, 8⟩]
}

#guard
  (scanCheckpointArtifact wrongRosterExpected checkpointRaw).isNone

/-- A nonfinite step radius fails during the constant-state disk walk. -/
private def nonfiniteStep : ByteArray :=
  (stepRaw.set! 166 0xf0).set! 167 0x7f

#guard (scanStepArtifact nonfiniteStep).isNone

/-- A changed encoded checkpoint count is rejected before its disk window can
shift the following record boundary. -/
private def wrongCheckpointCount : ByteArray :=
  checkpointRaw.set! 216 1

#guard
  (scanCheckpointArtifact boundedExpected wrongCheckpointCount).isNone

#guard
  (scanGammaArtifact (gammaRaw.extract 0 (gammaRaw.size - 1))).isNone

#guard
  (scanCheckpointArtifact boundedExpected
    (checkpointRaw.toList ++ [0]).toByteArray).isNone

/- Full-source acceptance is classification-sensitive even though the
individual scanners intentionally support bounded fixtures. -/
#guard
  !SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkFullSourceBundle
    boundedExpected gammaRaw stepRaw checkpointRaw

example {raw : ByteArray} {count offset : Nat}
    (hcheck : checkDiskWindow raw count offset = true) :
    DiskWindowAt raw count offset :=
  checkDiskWindow_sound hcheck

example {raw : ByteArray} {count offset index : Nat}
    (window : DiskWindowAt raw count offset)
    (hindex : index < count) :
    ∃ disk : Disk,
      parseDiskAt raw (offset + index * diskBytes) = some disk ∧
      disk.IsValid :=
  window.row hindex

#print axioms checkDiskWindow_sound
#print axioms DiskWindowAt.row
#print axioms scanCheckpointRows_sound
#print axioms checkRosterFresh_sound
#print axioms scanRosterTotals_sound
#print axioms fullSourceExpectations_valid_of_streaming_scans
#print axioms scanGammaArtifact_sound
#print axioms scanStepArtifact_sound
#print axioms scanCheckpointArtifact_sound
#print axioms
  SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkFullSourceBundle_sound
#print axioms
  SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkFullSourceBundle_exactRoster
#print axioms
  SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkFullSourceBundle_diskRows
#print axioms
  SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkPinnedFullSourceBundle_sound

end SparkInterval.Tests.CompletedFactorStreamingWire
