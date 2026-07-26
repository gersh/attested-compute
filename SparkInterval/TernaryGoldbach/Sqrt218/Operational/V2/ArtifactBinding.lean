/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.Execution.Statement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.V2Adapter
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Wire
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultSemantics

/-!
# Receipt binding for the fixed-width Sqrt218 V2 checker

`ResultWire` supplies the cycle-free parser for the complete 120-byte native
result and its exact ASCII envelope.  This module joins that result to:

* the complete binary certificate bytes named by `RunStatement.inputHash`;
* the input snapshot length and digest embedded by the native wrapper;
* the generic receipt's UTF-8 output digest; and
* the strict fixed-width certificate decoder and proved V2 checker.

Nothing here evaluates the production certificate.  `CheckedArtifacts`
requires `completeCheck = true` as data and only composes the existing
data-independent soundness theorem.  Physical execution remains at the sole
project-wide `accepted_run_certificate_sound` boundary and closed registered
invocation; this module introduces no trust declaration.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ArtifactBinding

open SparkInterval.Certificate
open SparkInterval.Execution
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

/-- Exact artifacts recovered from a generic signed trusted-compute claim.

The input SHA equality uses the complete retained binary certificate; the
embedded SHA equality then proves that the wrapper result names those same
bytes.  No SHA injectivity principle is needed because `certificateBytes`
itself is retained and fed to the strict certificate decoder below. -/
structure ReceiptBoundArtifacts (statement : RunStatement) where
  certificateBytes : ByteArray
  nativeResultBytes : ByteArray
  nativeResult : NativeResultRecord
  decodedResult :
    decodeResultEnvelope statement.result =
      .ok (nativeResultBytes, nativeResult)
  accepted : acceptedResultCheck nativeResult = true
  signedInputDigest :
    SHA256.digestByteArray certificateBytes = statement.inputHash
  wrapperInputLength :
    nativeResult.inputByteLength = certificateBytes.size
  wrapperInputDigest :
    nativeResult.inputSHA256 = statement.inputHash
  signedOutputDigest :
    SHA256.digestString statement.result = statement.outputHash

namespace ReceiptBoundArtifacts

/-- Two bindings for the same receipt text recover the same complete native
record bytes and typed fields. -/
theorem result_eq
    {statement : RunStatement}
    (left right : ReceiptBoundArtifacts statement) :
    left.nativeResultBytes = right.nativeResultBytes ∧
      left.nativeResult = right.nativeResult :=
  decodeResultEnvelope_unique left.decodedResult right.decodedResult

end ReceiptBoundArtifacts

/-- Complete ordinary-Lean handoff from exact receipt-bound bytes to the V2
checker.  Constructing this for production is a cloud certificate/registry
obligation; importing this definition performs no replay. -/
structure CheckedArtifacts (statement : RunStatement)
    extends ReceiptBoundArtifacts statement where
  image : ArchiveImage
  decodedCertificate :
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire.decodeCanonicalArchiveBytes
      certificateBytes = .ok image
  complete :
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter.completeCheck
      image nativeResult.arithmeticResult = true

namespace CheckedArtifacts

/-- The exact retained certificate bytes re-encode from their decoded image. -/
theorem exactCertificateBytes
    {statement : RunStatement}
    (artifacts : CheckedArtifacts statement) :
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire.encodeCanonicalArchiveBytes
        artifacts.image =
      some artifacts.certificateBytes :=
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire.decodeCanonicalArchiveBytes_exact
    artifacts.decodedCertificate

/-- Every step after the exact artifact/checker junction is an ordinary,
data-independent Lean theorem. -/
theorem sourceClaim
    {statement : RunStatement}
    (artifacts : CheckedArtifacts statement) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter.sourceClaim_of_completeCheck
    artifacts.complete

end CheckedArtifacts

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ArtifactBinding
