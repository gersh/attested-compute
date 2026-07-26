/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PendingExternalArtifactPrograms

set_option autoImplicit false

namespace SparkInterval.Tests.PendingExternalArtifactPrograms

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.TransitiveChildManifest
open
  SparkInterval.TernaryGoldbach.PendingExternalArtifactPrograms

private def digest (value : UInt8) : Digest32 where
  bytes := (List.replicate 32 value).toByteArray

private def oneChildManifest : Manifest where
  schemaVersion := schemaVersion
  campaignTag := 1
  sourceLower := 1
  sourceUpper := 21_000_000_001
  rootDigest := digest 1
  children := [{
    ordinal := 0
    lower := 1
    upper := 21_000_000_001
    backend := .azureNCCadsH100v5
    receiptDigest := digest 2
    artifactDigest := digest 3
    resultDigest := digest 4
    predecessorDigest := digest 1
  }]

example :
    r2StarSpec.expectedBackends =
      [.azureNCCadsH100v5] := by
  rfl

example :
    historicalGoldbachSpec.expectedBackends.length = 8_512 := by
  exact historicalGoldbach_expectedBackendCount

example :
    plattDirichletSpec.expectedBackends =
      [.azureSEVSNPCPU, .azureSEVSNPCPU] := by
  rfl

example :
    decode ByteArray.empty = none := by
  rfl

example :
    r2StarManifestCheck oneChildManifest = true := by
  rfl

example :
    r2StarFailClosed.program.run
      SparkInterval.TernaryGoldbach.R2StarCompactChecker.canonicalInputBytes =
        .rejected
          CanonicalInstalledArtifactProgram.artifactAbsentCode :=
  r2Star_rejects_canonical

example :
    plattDirichletFailClosed.program.run
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalInputBytes =
        .rejected
          CanonicalInstalledArtifactProgram.artifactAbsentCode :=
  plattDirichlet_rejects_canonical

#print axioms r2Star_rejects_canonical
#print axioms historicalGoldbach_rejects_canonical
#print axioms plattDirichlet_rejects_canonical

end SparkInterval.Tests.PendingExternalArtifactPrograms
