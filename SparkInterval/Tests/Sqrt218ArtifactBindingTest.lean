/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.ArtifactBinding

/-!
# Small known-answer tests for the Sqrt218 receipt artifact binding

The vector below was computed independently with Python's `hashlib` and the
existing measured-workload `_trace_digest`/canonical-JSON formulas. It hashes
only a few hundred bytes. No certificate archive is loaded and no arithmetic
replay is run.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.Sqrt218ArtifactBinding

open SparkInterval.TernaryGoldbach.Sqrt218Operational

def context : ReceiptTraceContext := {
  startChallengeSHA256 :=
    "1111111111111111111111111111111111111111111111111111111111111111"
  inputSHA256 :=
    "3333333333333333333333333333333333333333333333333333333333333333"
  resultSHA256 :=
    "4444444444444444444444444444444444444444444444444444444444444444"
}

def fields : ReceiptArtifactFieldsV2 := {
  jobBindingSHA256 :=
    "2222222222222222222222222222222222222222222222222222222222222222"
  certificateSHA256 :=
    "5555555555555555555555555555555555555555555555555555555555555555"
  verificationReportSHA256 :=
    "6666666666666666666666666666666666666666666666666666666666666666"
  workTraceChainSHA256 :=
    "2148d52d62a1e5cf8da3465ef696b6cc7f83320f62d5d5ef6c4e3977d6f84cb9"
  workTraceArtifactSHA256 :=
    "eab920afbb09069f847af27f8d7067c681a6d27dc2e924b4b7c20e3c1a784cbe"
}

#guard fields.expectedWorkTraceChainSHA256 context ==
  "2148d52d62a1e5cf8da3465ef696b6cc7f83320f62d5d5ef6c4e3977d6f84cb9"

#guard fields.expectedWorkTraceArtifactSHA256 context ==
  "eab920afbb09069f847af27f8d7067c681a6d27dc2e924b4b7c20e3c1a784cbe"

#guard fields.signedExtensionSHA256 ==
  "b335198fd008cdd8ad40edb584d4c879cfb79d7d45a74599997789cb66f9eba3"

#guard fields.check context

def tamperedCertificate : ReceiptArtifactFieldsV2 := {
  fields with
  certificateSHA256 :=
    "7777777777777777777777777777777777777777777777777777777777777777"
}

def tamperedTraceArtifact : ReceiptArtifactFieldsV2 := {
  fields with
  workTraceArtifactSHA256 :=
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}

def tamperedTraceChain : ReceiptArtifactFieldsV2 := {
  fields with
  workTraceChainSHA256 :=
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}

def uppercaseCertificate : ReceiptArtifactFieldsV2 := {
  fields with
  certificateSHA256 :=
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
}

#guard !tamperedCertificate.check context
#guard !tamperedTraceArtifact.check context
#guard !tamperedTraceChain.check context
#guard !uppercaseCertificate.check context

#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.ReceiptArtifactFieldsV2.traceBound_of_check
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.CheckedReceiptArtifactV2.exactBytes
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.CheckedReceiptArtifactV2.archive_eq_of_raw_eq
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.CheckedReceiptArtifactV2.sourceClaim

end SparkInterval.Tests.Sqrt218ArtifactBinding
