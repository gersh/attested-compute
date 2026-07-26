/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.ProjectedCertificateProgram
import SparkInterval.Execution.ParsedCertificateProgram

set_option autoImplicit false

namespace SparkInterval.Tests.ProjectedCertificateProgram

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.Execution.Architecture.ProjectedCertificateProgram

def sourceChecker : NativeCheckerSemantics where
  checkerId := "projected-program-test-source"
  accepts := fun input output =>
    input = "artifact".toUTF8 ∧ output = "ok".toUTF8

def downstreamChecker : NativeCheckerSemantics where
  checkerId := "projected-program-test-downstream"
  accepts := fun input output =>
    input = "descriptor".toUTF8 ∧ output = "ok".toUTF8

def decode (bytes : ByteArray) : Option Unit :=
  if bytes = "artifact".toUTF8 then some () else none

def sourceCertificate :
    DeterministicFinalizerIR.Certificate sourceChecker :=
  ParsedCertificateProgram.certificate
    sourceChecker decode (fun _ => true) "ok".toUTF8 (by
      intro input _ decoded _checked
      by_cases exactInput : input = "artifact".toUTF8
      · exact ⟨exactInput, rfl⟩
      · have decodedInput : input = "artifact".toUTF8 := by
          simpa [decode] using decoded
        exact (exactInput decodedInput).elim)

def projected :
    ProjectedCertificateProgram.Certificate
      sourceChecker downstreamChecker where
  sourceProgram := sourceCertificate
  downstreamInput := "descriptor".toUTF8
  downstreamResult := "ok".toUTF8
  project := by
    intro _input _output _accepted
    exact ⟨rfl, rfl⟩

example :
    downstreamChecker.accepts
      projected.downstreamInput projected.downstreamResult := by
  apply projected.downstream_of_returned
    (artifactBytes := "artifact".toUTF8)
    (outputBytes := "ok".toUTF8)
  rfl

#print axioms
  ProjectedCertificateProgram.Certificate.downstream_of_returned
#print axioms
  ProjectedCertificateProgram.Certificate.downstream_of_opaqueNativeAcceptance

end SparkInterval.Tests.ProjectedCertificateProgram
