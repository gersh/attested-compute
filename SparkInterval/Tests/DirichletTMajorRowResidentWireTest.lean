/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.TMajorRowResidentWire
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Cross-language checks for the row-resident Dirichlet wire

The block and seed headers below were emitted by the Python `TGDLTMB1` builder
used by `test_tg_dirichlet_tmajor_cuda_block.py`.  The summary is encoded by
Lean in the same compact sorted-key spelling written by the C++ runner.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.Tests.DirichletTMajorRowResidentWire

open SparkInterval.Dirichlet.TMajorRowResidentWire
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

private def decodeFixture (hex : String) : ByteArray :=
  (decodeLowerHex hex).getD ByteArray.empty

private def pythonBlockHeader : ByteArray :=
  decodeFixture
    "5447444c544d4231020000000000000002000000020000001127000013270000040000000100000000000000000000000200000000000000000010000000000040001000000000007800000000000000da0ae1efdc62bbb27647f2d09845926788e29cc38876b26cab17e8b6cb268f9fd3affb94990febf6cb21aed82fdecb14d834b3f9b92c7b4e7f192bcfbec932703c2b8250e68dd540185d3ecd27a26ce872e73da5a18697918859ce3b6851f38f6556a2008397b0026e1207538763aa2ffde839187ba1518c292609ee047b5edcbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb1d45c90c368cea26ba050fb0911f4c58c94472720b53d88725fdc6728e1b9e7d"

#guard pythonBlockHeader.size = blockHeaderBytes
#guard (parseBlockHeader pythonBlockHeader).isSome
#guard (parseBlockHeader pythonBlockHeader).map BlockHeader.rowCount = some 2
#guard
  (parseBlockHeader pythonBlockHeader).map BlockHeader.targetCount = some 2
#guard (parseBlockHeader pythonBlockHeader).map BlockHeader.qStart = some 10_001
#guard (parseBlockHeader pythonBlockHeader).map BlockHeader.qStop = some 10_003
#guard (parseBlockHeader pythonBlockHeader).map BlockHeader.sidecarMode = some 1
#guard hasPrimitiveCharacterModulus 10_001
#guard !hasPrimitiveCharacterModulus 10_002
#guard hasPrimitiveCharacterModulus 10_003
#guard expectedTargetQs 10_001 10_003 0 2 = [10_001, 10_003]
#guard (parseBlockHeader (pythonBlockHeader.set! 8 1)).isNone

private def pythonRowHeader : ByteArray :=
  decodeFixture
    "5447444c544d5231020000000000000000000000000000000000100000000000b310fc4717e5c65be001eb6bf00a3345e28d657425f90a57ff50a8e6d8dc8b3f"

#guard (parseRowHeaderAt pythonRowHeader 0 0).isSome
#guard (parseRowHeaderAt pythonRowHeader 0 1).isNone
#guard (parseRowHeaderAt (pythonRowHeader.set! 12 1) 0 0).isNone

private def pythonTargetHeader : ByteArray :=
  decodeFixture
    "5447444c544d51310200000011270000020000000200000000000000000000004026000000000000000000000000000040000000000000000500000000000000804c0000000000004000000000000000100000000000000034595d3373da0b8c659728e7201f47137be52fb59a8c7baef778c44a63329cf0"

private def parsedPythonTarget : Option TargetHeader := do
  let block ← parseBlockHeader pythonBlockHeader
  parseTargetHeaderAt pythonTargetHeader 0 block 10_001

#guard parsedPythonTarget.isSome
#guard parsedPythonTarget.map TargetHeader.componentCount = some 2
#guard parsedPythonTarget.map TargetHeader.batchCount = some 2
#guard parsedPythonTarget.map TargetHeader.groupOrder = some 9_792
#guard parsedPythonTarget.map TargetHeader.valueCount = some 19_584

private def pythonTargetFactors : ByteArray :=
  decodeFixture
    "1865192d9e7a843f1965192d9e7a843f000000000000008000000000000000806dc621d0dccd7e3f6ec621d0dccd7e3fe98cc91261fe7abfe88cc91261fe7abf"

private def pythonTargetTails : ByteArray :=
  decodeFixture "4e4fffbec7a87332a77d989560137c32"

#guard
  match parsedPythonTarget with
  | none => false
  | some target =>
      digestMatches
        (targetSidecarBytes target pythonTargetFactors pythonTargetTails)
        target.sidecarSHA256

private def syntheticTGDAFFI1 : ByteArray :=
  (allCharsInputMagic ++
    encodeLE 4 formatVersion ++
    encodeLE 4 10_001 ++
    encodeLE 4 2 ++
    encodeLE 4 2 ++
    encodeLE 8 9_792 ++
    encodeLE 8 0 ++
    encodeLE 8 sourceTDenominator ++
    encodeLE 8 sourceTStepNumerator ++
    encodeLE 8 19_584 ++
    encodeLE 8 0 ++
    List.replicate (19_584 * complexIntervalBytes) (0 : UInt8)).toByteArray

#guard
  match parsedPythonTarget with
  | none => false
  | some target => (parseOutputFrameAt syntheticTGDAFFI1 0 target).isSome

private def pythonBlockFooter : ByteArray :=
  decodeFixture
    "5447444c544d463102000000000000000200000000000000020000000000000004000000000000008866000000000000a000000000000000000000000000000087a8678faf295b18236803a2e73f317d660fe7b2b4cec822b0080258931b9c8e7939f5c429a0448aab62ae346b401d02cde45236abf61195181a5aca9ba72f348be25a57e38b63ab7675fe768ab49494b85bf68c448f7a1ad521bff4e004841c"

#guard (parseBlockFooterAt pythonBlockFooter 0).isSome

private def pythonSeedHeader : ByteArray :=
  decodeFixture
    "54474452435653310100000004000000801a060030000000010000000000000059c30000000000000500000000000000400000000000000059c3000000000000c000000000010000001000000000000000000000000000000000000000000000"

#guard pythonSeedHeader.size = seedHeaderBytes
#guard (parseSeedHeader pythonSeedHeader).isSome
#guard (parseSeedHeader pythonSeedHeader).map SeedHeader.xStart = some 1
#guard (parseSeedHeader pythonSeedHeader).map SeedHeader.xStop = some 50_009
#guard
  (parseSeedHeader pythonSeedHeader).map SeedHeader.chunkRecords = some 4_096

private def pythonOneRecordSeedArtifact : ByteArray :=
  decodeFixture
    "54474452435653310100000004000000801a06003000000001000000000000000100000000000000050000000000000040000000000000000100000000000000c00000000001000001000000000000000000000000000000000000000000000054474452435643310100000000000000010000000000000001000000000000001b2fb138f9f7655c3c325be8a5c18cc0784f5445e06a65737b5a653e09e24aa5000000000000f03f000000000000f03f000000000000f03f000000000000f03f0000000000000000000000000000000054474452435646310100000000000000010000000000000001000000000000000f6828b5c435acec3a828a8fd5a14b0cacbc7df208c9dbd6ee24a056488fe428f141667e66ff5c330ebe9342c4c75219a5bf758d545fc1b05a4a00372fc4bb72"

#guard pythonOneRecordSeedArtifact.size = 304
#guard (parseSeedArtifact pythonOneRecordSeedArtifact).isSome
#guard (parseSeedArtifact (pythonOneRecordSeedArtifact.set! 180 1)).isNone
#guard
  (parseSeedArtifact
    (pythonOneRecordSeedArtifact.toList ++ [0]).toByteArray).isNone

private def sampleSummary : ExecutionSummary := {
  allCharacterFFTExecuted := false
  completedLZeroStateValidated := false
  elapsedKernelNanoseconds := 123_456
  externalAtomDischarged := false
  inputArtifactSHA256 := String.ofList (List.replicate 64 'a')
  laneIndex := 0
  outputStreamSHA256 := String.ofList (List.replicate 64 'b')
  recoverySeedArtifactSHA256 := String.ofList (List.replicate 64 'c')
  rowBindingsSHA256 := String.ofList (List.replicate 64 'd')
  rowCount := 2
  rowPayloadH2DBytes := 2 * rowPayloadBytes
  sidecarSourceSHA256 := String.ofList (List.replicate 64 'e')
  sourceContractSHA256 := String.ofList (List.replicate 64 '1')
  sourceScaleRun := false
  spoolReceiptSHA256 := String.ofList (List.replicate 64 '2')
  targetCount := 2
  trustedExecutionAttested := false
  valueCount := 26_248
  zeroCompletenessClaimed := false
}

private def sampleSummaryBytes : ByteArray :=
  canonicalSummaryBytes sampleSummary

#guard parseExecutionSummary sampleSummaryBytes = some sampleSummary
#guard
  parseExecutionSummary
    (sampleSummaryBytes.toList ++ [0]).toByteArray = none
#guard
  parseExecutionSummary (sampleSummaryBytes.set! 0 0) = none

private def claimedCompletionSummary : ExecutionSummary :=
  { sampleSummary with externalAtomDischarged := true }

#guard
  parseExecutionSummary
    (canonicalSummaryBytes claimedCompletionSummary) = none

#guard binary64Finite 0x3ff0000000000000
#guard !binary64Finite 0x7ff0000000000000
#guard binary64LE 0xbff0000000000000 0
#guard binary64LE 0x8000000000000000 0
#guard binary64LE 0 0x8000000000000000
#guard binary64Nonnegative 0x8000000000000000

#guard maximumTIndex 10_001 = 127_987
#guard maximumTIndex 10_002 = 127_974
#guard canonicalComponentCount 10_001 = 2
#guard canonicalComponentCount 10_002 = 2
#guard Nat.totient 10_001 = 9_792
#guard Nat.totient 10_002 = 3_332

example {raw : ByteArray} {header : BlockHeader}
    (hparse : parseBlockHeader raw = some header) :
    raw.size = blockHeaderBytes :=
  parseBlockHeader_size hparse

example {raw : ByteArray} {summary : ExecutionSummary}
    (hparse : parseExecutionSummary raw = some summary) :
    canonicalSummaryBytes summary = raw :=
  parseExecutionSummary_canonical hparse

end SparkInterval.Tests.DirichletTMajorRowResidentWire
