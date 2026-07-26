/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Generated.CDEMAbelProduction
import SparkInterval.TernaryGoldbach.CDEMAbelArtifactProgram

set_option autoImplicit false

namespace SparkInterval.Tests.CDEMAbelArtifactProgram

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.FixedWidthCertificateWire
open SparkInterval.TernaryGoldbach
open SparkInterval.TernaryGoldbach.CDEMAbelArtifactProgram

def sampleCertificate : CDEMAbelRecurrenceCertificate.Certificate where
  signedNumerator := 17
  absoluteNumerator := 29
  chunks := [{
    low := 1
    high := 3
    before := -2
    after := 5
    signedUpper := -7
    absoluteUpper := 11
  }]

/- The campaign encoder and complete-input decoder agree on ordinary data.
This does not run the source-scale recurrence checker. -/
#guard (encode? sampleCertificate).bind decode = some sampleCertificate

#guard decode ByteArray.empty = none

def sampleWithSuffix : Option ByteArray :=
  (encode? sampleCertificate).map fun bytes =>
    (bytes.toList ++ [0]).toByteArray

#guard sampleWithSuffix.bind decode = none

/- Sign byte one with zero magnitude is the forbidden negative-zero
spelling. -/
def negativeZero : ByteArray :=
  ((1 : UInt8) :: List.replicate naturalWidth (0 : UInt8)).toByteArray

#guard readInt negativeZero 0 = none

/- Unknown sign bytes fail closed. -/
def unknownSign : ByteArray :=
  ((2 : UInt8) :: List.replicate naturalWidth (1 : UInt8)).toByteArray

#guard readInt unknownSign 0 = none

/- The existing retained 1,000-row arithmetic transcript fits the exact new
wire format and round-trips.  This serializes roughly 195 KiB; it does not
execute any of the five billion recurrence events. -/
#guard
  (encode? SparkInterval.Generated.CDEMAbelProduction.certificate).bind
    decode =
      some SparkInterval.Generated.CDEMAbelProduction.certificate

/- The source program consumes the full artifact bytes and is bound to the
artifact checker, not to the legacy descriptor checker. -/
example :
    sourceProgramCertificate.program.contractId =
      artifactNativeChecker.checkerId := by
  rfl

example :
    projectedSourceProgramCertificate.downstreamInput =
      CDEMAbelCompactChecker.canonicalInputBytes := by
  rfl

example :
    invocation.terminalTarget = .azureSEVSNPCPU := by
  rfl

#print axioms CDEMAbelClosedReplay.sourceClaim_of_check
#print axioms sourceClaim_of_artifact_acceptance
#print axioms legacy_accepts_of_artifact_acceptance
#print axioms sourceProgramCertificate
#print axioms projectedSourceProgramCertificate
#print axioms sourceClaim_of_opaqueNativeAcceptance

end SparkInterval.Tests.CDEMAbelArtifactProgram
