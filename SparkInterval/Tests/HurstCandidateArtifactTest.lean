/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.TernaryGoldbach.HurstCandidateArtifact

set_option autoImplicit false

namespace SparkInterval.Tests.HurstCandidateArtifact

open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.TernaryGoldbach
open SparkInterval.TernaryGoldbach.HurstCandidateArtifact

def zeroGuard : HurstAffineCertificate.Guard where
  lower := .zero
  upper := .zero

def sampleCertificate : HurstAffineCertificate.Certificate where
  sourceLower := 1
  sourceUpper := HurstAffineCertificate.sourceUpperExclusive
  rootState := .zero
  finalState := .zero
  blocks := [{
    lower := 1
    upper := HurstAffineCertificate.sourceUpperExclusive
    delta := .zero
    guard := zeroGuard
  }]

#guard (encode? sampleCertificate).bind decode = some sampleCertificate

def signedDelta : HurstAffineCertificate.State where
  mertens := -1
  squarefree := 2
  littleLowerQ96 := -3
  littleUpperQ96 := 4

def signedSampleCertificate : HurstAffineCertificate.Certificate where
  sourceLower := 1
  sourceUpper := HurstAffineCertificate.sourceUpperExclusive
  rootState := .zero
  finalState := signedDelta
  blocks := [{
    lower := 1
    upper := HurstAffineCertificate.sourceUpperExclusive
    delta := signedDelta
    guard := zeroGuard
  }]

#guard (encode? signedSampleCertificate).bind decode =
  some signedSampleCertificate

/- Cross-language known answer shared with
`tests/test_candidate_artifact_wires.py`; negative coordinates exercise the
canonical sign/magnitude spelling. -/
#guard
  (encode? signedSampleCertificate).map
    SparkInterval.Certificate.SHA256.digestByteArray =
      some
        "23b334b8eb33b33618417781a11fea97d2bb4cf8678517d5bc7218aa0b2f4b37"

def hasMissingRealizationCode : Outcome → Bool
  | .rejected code => code == missingRealizationCode
  | .returned _ => false

/- Even a valid full-range affine chain fails closed at the absent primitive
row replay boundary. -/
#guard
  (encode? sampleCertificate).map
    (hasMissingRealizationCode ∘ runCandidate) = some true

def withSuffix : Option ByteArray :=
  (encode? sampleCertificate).map fun bytes =>
    (bytes.toList ++ [0]).toByteArray

#guard withSuffix.bind decode = none

example :
    failClosedCertificate.program.run
      HurstCompactChecker.canonicalInputBytes =
        .rejected
          SparkInterval.Execution.Architecture.CanonicalInstalledArtifactProgram.artifactAbsentCode :=
  failClosed_rejects_canonical

example : invocation.terminalTarget = .azureSEVSNPCPU := by
  rfl

end SparkInterval.Tests.HurstCandidateArtifact
