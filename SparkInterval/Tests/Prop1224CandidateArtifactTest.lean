/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.TernaryGoldbach.Prop1224CandidateArtifact

set_option autoImplicit false

namespace SparkInterval.Tests.Prop1224CandidateArtifact

open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.TernaryGoldbach
open SparkInterval.TernaryGoldbach.Prop1224CandidateArtifact

def sampleCertificate : Prop1224SourceSemantics.Certificate where
  sourceLower := 0
  sourceUpper := Prop1224SourceSemantics.sourceRankCount
  shards := [{
    lower := 0
    upper := Prop1224SourceSemantics.sourceRankCount
  }]

#guard (encode? sampleCertificate).bind decode = some sampleCertificate

/- Cross-language known answer shared with
`tests/test_candidate_artifact_wires.py`. -/
#guard
  (encode? sampleCertificate).map
    SparkInterval.Certificate.SHA256.digestByteArray =
      some
        "9507c40bd8e61773be8a5e0ce88daece4b560a67fce8502070d1e7f2ba30b064"

def hasMissingRealizationCode : Outcome → Bool
  | .rejected code => code == missingRealizationCode
  | .returned _ => false

/- Even a complete valid rank chain fails closed at the absent MPFR/GMP row
realization boundary. -/
#guard
  (encode? sampleCertificate).map
    (hasMissingRealizationCode ∘ runCandidate) = some true

def withSuffix : Option ByteArray :=
  (encode? sampleCertificate).map fun bytes =>
    (bytes.toList ++ [0]).toByteArray

#guard withSuffix.bind decode = none

example :
    failClosedCertificate.program.run
      Prop1224CompactChecker.canonicalInputBytes =
        .rejected
          SparkInterval.Execution.Architecture.CanonicalInstalledArtifactProgram.artifactAbsentCode :=
  failClosed_rejects_canonical

example :
    invocation.terminalTarget = .azureSEVSNPCPU := by
  rfl

end SparkInterval.Tests.Prop1224CandidateArtifact
