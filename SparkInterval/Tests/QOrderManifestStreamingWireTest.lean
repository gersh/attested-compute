/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.QOrderManifestStreamingWire

/-!
# Tests for the production-scale q-order checker

The small checks below exercise the same tail-recursive geometry, hash-set,
coverage, and source-byte code used on the production manifest.  The
production file itself remains an external input and is benchmarked with
`lean --run`; it is not checked into the repository.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.QOrderManifestStreamingWireTest

open SparkInterval.Dirichlet.QOrderManifestWire
open SparkInterval.Dirichlet.QOrderManifestStreamingWire

private def sourceRow (q : Nat) : ScheduleRecord :=
  { q, sampleCount := sourceSampleCount q }

private def threeSourceRows : List ScheduleRecord :=
  [sourceRow 10_001, sourceRow 10_003, sourceRow 10_004]

#guard
  scanRecordGeometry threeSourceRows 0 0 =
    some {
      rowCount := 3
      sampleTotal :=
        sourceSampleCount 10_001 +
          sourceSampleCount 10_003 +
          sourceSampleCount 10_004
    }

#guard
  (scanRecordGeometry
    [{ q := 10_001, sampleCount := sourceSampleCount 10_001 - 1 }]
    0 0).isNone

#guard
  (collectFresh threeSourceRows
    (Std.HashSet.emptyWithCapacity 3)).isSome

#guard
  (collectFresh [sourceRow 10_001, sourceRow 10_003, sourceRow 10_001]
    (Std.HashSet.emptyWithCapacity 3)).isNone

private def threeSourceSet : Std.HashSet Nat :=
  (Std.HashSet.emptyWithCapacity 3)
    |>.insert 10_001
    |>.insert 10_003
    |>.insert 10_004

#guard checkCoverageWindow threeSourceSet 10_001 4

private def missingSourceSet : Std.HashSet Nat :=
  (Std.HashSet.emptyWithCapacity 2)
    |>.insert 10_001
    |>.insert 10_004

/- Counts alone would not notice this omitted primitive modulus. -/
#guard !checkCoverageWindow missingSourceSet 10_001 4

private def extraNonprimitiveSet : Std.HashSet Nat :=
  threeSourceSet.insert 10_002

#guard !checkCoverageWindow extraNonprimitiveSet 10_001 4

private def expectedSmallBody : ByteArray :=
  pushScheduleRecord
    (pushScheduleRecord
      (pushScheduleRecord ByteArray.empty (sourceRow 10_001))
      (sourceRow 10_003))
    (sourceRow 10_004)

#guard
  buildFormulaicSourceBodyAux 10_001 4 ByteArray.empty =
    expectedSmallBody

example
    {raw : ByteArray} {manifest : StreamingManifest}
    (hcheck :
      SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkFullSourceManifest
        raw = some manifest) :
    manifest.IsValid raw :=
  checkFullSourceManifest_sound hcheck

/- The validity proposition retains the exact raw-header binding rather than
only the source-shaped values copied from that header. -/
example
    {raw : ByteArray} {manifest : StreamingManifest}
    (hcheck :
      SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkFullSourceManifest
        raw = some manifest) :
    parseHeaderOnly raw = some manifest.header :=
  (checkFullSourceManifest_sound hcheck).2.1

example
    {raw : ByteArray} {manifest : StreamingManifest}
    {phaseIndex : Nat} {producerIdentitySHA256 : ByteArray}
    {expected :
      SparkInterval.Dirichlet.CompletedFactorWire.FullSourceExpectations}
    (hcheck :
      SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkFullSourceManifest
        raw = some manifest)
    (hexpected :
      fullSourceExpectations? manifest phaseIndex producerIdentitySHA256 =
        some expected) :
    ∃ phase :
        SparkInterval.Dirichlet.CompletedFactorWire.PinnedPhase,
      SparkInterval.Dirichlet.CompletedFactorWire.pinnedPhase? phaseIndex =
          some phase ∧
        expected.roster =
          manifest.phaseCompletedFactorRoster phase :=
  checked_full_source_exact_phase_roster hcheck hexpected

#print axioms scanRecordGeometry_sound
#print axioms collectFresh_sound
#print axioms checkCoverageWindow_sound
#print axioms checkExactSourceCoverage_sound
#print axioms pushScheduleRecord_toList
#print axioms buildFormulaicSourceBodyAux_toList
#print axioms formulaicSourceSHA256_eq_spec
#print axioms executionOrderSHA256_eq_spec
#print axioms
  SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkFullSourceManifest_sound
#print axioms checked_formulaic_record_iff
#print axioms
  SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkScheduledFullSourceBundle_sound
#print axioms checked_full_source_exact_phase_roster
#print axioms
  SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkScheduledFullSourceBundle_exactRoster

end SparkInterval.Tests.QOrderManifestStreamingWireTest
