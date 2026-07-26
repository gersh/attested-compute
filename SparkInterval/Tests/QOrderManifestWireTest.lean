/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.QOrderManifestWire

namespace SparkInterval.Tests.QOrderManifestWireTest

open SparkInterval.Certificate
open SparkInterval.Dirichlet.QOrderManifestWire

set_option maxRecDepth 5000000

private def zeroDigest : List UInt8 := List.replicate 32 0

private def recordBytesFor (q sampleCount : Nat) : List UInt8 :=
  encodeLE 4 q ++ encodeLE 4 sampleCount

private def boundedFixtureRecords : List ScheduleRecord :=
  [{ q := 10_003, sampleCount := 2 },
   { q := 10_001, sampleCount := 1 }]

private def boundedSourceRecords : List ScheduleRecord :=
  sourceProjection boundedFixtureRecords

private def boundedSourceDigest : List UInt8 :=
  [0xfb, 0xff, 0x17, 0x6d, 0x8a, 0x08, 0xb2, 0xe1,
   0xd7, 0x41, 0xae, 0xba, 0xbd, 0x24, 0x20, 0xdd,
   0xc9, 0x7b, 0xbd, 0x9f, 0x26, 0xe5, 0xd5, 0x73,
   0xf2, 0xac, 0xb4, 0x3e, 0xfd, 0x1c, 0xd8, 0xe0]

private def boundedExecutionDigest : List UInt8 :=
  [0xb4, 0x69, 0xeb, 0x2d, 0xfa, 0x33, 0xf1, 0x4f,
   0x08, 0xcf, 0x8b, 0xe3, 0x87, 0x25, 0x9d, 0xdb,
   0x23, 0x24, 0x5e, 0x74, 0xd7, 0xc6, 0x8c, 0x2e,
   0x6f, 0xf0, 0x8b, 0x39, 0x40, 0x1d, 0x99, 0x98]

private def boundedFixture : ByteArray :=
  (magic ++
    encodeLE 4 formatVersion ++
    encodeLE 4 boundedClassificationCode ++
    encodeLE 4 primitiveModulusRosterVersion ++
    encodeLE 4 10_001 ++
    encodeLE 4 10_003 ++
    encodeLE 4 recordBytes ++
    encodeLE 8 2 ++
    encodeLE 8 3 ++
    boundedSourceDigest ++
    boundedExecutionDigest ++
    recordBytesFor 10_003 2 ++
    recordBytesFor 10_001 1).toByteArray

#eval
  if (parseManifest boundedFixture).isSome then
    ()
  else
    panic! "valid bounded TGDQORD1 fixture was rejected"

private def clippedPhase :
    SparkInterval.Dirichlet.CompletedFactorWire.PinnedPhase :=
  {
    firstTIndex := 1
    tIndexStopExclusive := 3
    qCount := 1
    checkpointCount := 1
    tIndexRowCount := 1
  }

#eval
  match parseManifest boundedFixture with
  | none => panic! "valid bounded phase fixture was rejected"
  | some manifest =>
      if manifest.phaseCompletedFactorRoster clippedPhase ==
          ([{ q := 10_003, sampleCount := 1 }] :
            List SparkInterval.Dirichlet.CompletedFactorWire.QSample) then
        ()
      else
        panic! "phase projection did not drop and clip rows exactly"

private def boundedDuplicateFixture : ByteArray :=
  (magic ++
    encodeLE 4 formatVersion ++
    encodeLE 4 boundedClassificationCode ++
    encodeLE 4 primitiveModulusRosterVersion ++
    encodeLE 4 10_001 ++
    encodeLE 4 10_001 ++
    encodeLE 4 recordBytes ++
    encodeLE 8 2 ++
    encodeLE 8 2 ++
    zeroDigest ++
    zeroDigest ++
    recordBytesFor 10_001 1 ++
    recordBytesFor 10_001 1).toByteArray

#eval
  if (parseManifest boundedDuplicateFixture).isNone then
    ()
  else
    panic! "duplicate-q TGDQORD1 fixture was accepted"

private def forgedFullSourceFixture : ByteArray :=
  (magic ++
    encodeLE 4 formatVersion ++
    encodeLE 4 fullSourceClassificationCode ++
    encodeLE 4 primitiveModulusRosterVersion ++
    encodeLE 4 10_001 ++
    encodeLE 4 10_003 ++
    encodeLE 4 recordBytes ++
    encodeLE 8 2 ++
    encodeLE 8 3 ++
    boundedSourceDigest ++
    boundedExecutionDigest ++
    recordBytesFor 10_003 2 ++
    recordBytesFor 10_001 1).toByteArray

#eval
  if (checkFullSourceManifest forgedFullSourceFixture).isNone then
    ()
  else
    panic! "bounded geometry acquired full-source meaning"

example (raw : ByteArray) (manifest : ParsedManifest)
    (h : checkFullSourceManifest raw = some manifest) :
    manifest.sourceRecords = formulaicSourceRoster :=
  checked_full_source_roster h

end SparkInterval.Tests.QOrderManifestWireTest
