/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.Execution.Attestation
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Run
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Wire
import TGComputeContracts.Sqrt218.Sound

/-!
# Canonical artifact binding for the Sqrt218 checker

This file is the data-independent composition point between three ordinary
Lean components:

* the exact canonical archive bytes;
* the SHA-256 name placed in a measured-run trace; and
* successful execution of the typed operational checker.

It contains no production archive and does not evaluate a production replay.
In particular, constructing `CheckedCanonicalArtifact` for the real archive
is a cloud/receipt obligation.  Once such an object is available, every step
from its decoded archive to the paper-shaped source claim is an ordinary Lean
theorem.

`canonicalArchiveSHA256` hashes the exact canonical JSON text.  The wire
decoder proves that this text's UTF-8 bytes are the complete input byte array.
The external importer must still establish that the digest carried by the
signed work trace names those bytes.  SHA-256 collision/second-preimage
resistance and authentic measured execution remain part of the single
disclosed trusted-compute boundary; neither is postulated here.

The normalized trusted-compute receipt V1 does not retain either
`certificate_sha256` or `work_trace_chain_sha256`. Those values occur only
inside the preimage of its opaque wire-statement digest, and the current
Sqrt218 work-trace JSON does not carry `certificate_sha256` as a field.
Consequently there is intentionally no extractor from a V1 receipt to
`CheckedCanonicalArtifact`.

The explicitly versioned `ReceiptArtifactFieldsV2` below specifies the
narrowest additional signed fields needed by a future receipt. Its checker
reconstructs the exact existing Sqrt218 V1 trace chain and canonical trace
artifact. This file does not change the V1 registered invocation, the V1
input hash, or the sole trusted-execution axiom.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational

open SparkInterval.Certificate

/-- SHA-256 name of the exact canonical V1 archive bytes.

Canonical archive JSON is ASCII, so `digestString` hashes precisely the bytes
returned by `canonicalArchiveBytes`. -/
def canonicalArchiveSHA256 (archive : Archive) : String :=
  SHA256.digestString (canonicalArchiveText archive)

/-- Complete formal meaning of a successful, digest-named archive artifact.

The structure deliberately retains `raw` and the decoder equation.  A receipt
cannot gain theorem authority from a digest and a separately chosen typed
archive: both must be joined by the strict canonical decoder. -/
structure CheckedCanonicalArtifact
    (profile : Profile) (certificateSHA256 : String) where
  raw : ByteArray
  archive : Archive
  decoded : decodeCanonicalArchiveBytes raw = .ok archive
  digestBound : canonicalArchiveSHA256 archive = certificateSHA256
  checked : run profile archive = true

namespace CheckedCanonicalArtifact

/-- The retained raw artifact is exactly the canonical encoding of the typed
archive used by the arithmetic checker. -/
theorem exactBytes
    {profile : Profile} {certificateSHA256 : String}
    (artifact : CheckedCanonicalArtifact profile certificateSHA256) :
    canonicalArchiveBytes artifact.archive = artifact.raw :=
  decodeCanonicalArchiveBytes_exact artifact.decoded

/-- The digest-named canonical artifact yields all generic finite certificate
facts.  This theorem typechecks the checker proof but never evaluates the
concrete archive. -/
theorem archiveFacts
    {profile : Profile} {certificateSHA256 : String}
    (artifact : CheckedCanonicalArtifact profile certificateSHA256) :
    ArchiveFacts profile artifact.archive :=
  run_success_sound artifact.checked

/-- Ordinary Lean reduction from a digest-named successful artifact to the
exact source-shaped finite claim. -/
theorem sourceClaim
    {profile : Profile} {certificateSHA256 : String}
    (artifact : CheckedCanonicalArtifact profile certificateSHA256) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  artifact.archiveFacts.certificate.sourceClaim

end CheckedCanonicalArtifact

/-- Strict decoding is functional: receipt code cannot pair one raw artifact
with two different typed archives. -/
theorem decodeCanonicalArchiveBytes_archiveUnique
    {raw : ByteArray} {left right : Archive}
    (hleft : decodeCanonicalArchiveBytes raw = .ok left)
    (hright : decodeCanonicalArchiveBytes raw = .ok right) :
    left = right := by
  rw [hleft] at hright
  exact Except.ok.inj hright

/-! ## Existing measured-work-trace V1

These definitions are a direct transcription of
`tools/tg_sqrt218_azure_measured_workload.py`. They are deliberately kept
separate from the receipt extension below: the measured trace stays V1, while
only the normalized signed-receipt binding needs a V2.
-/

/-- Receipt fields already signed independently of the missing Sqrt218
artifact extension. -/
structure ReceiptTraceContext where
  startChallengeSHA256 : String
  inputSHA256 : String
  resultSHA256 : String
  deriving Repr, DecidableEq, BEq

/-- Project the three already-retained signed fields of the normalized receipt
V1 into the Sqrt218 trace context. The future V2 extension need not duplicate
them. -/
def ReceiptTraceContext.ofTrustedComputeEvidence
    (evidence : SparkInterval.Execution.TrustedComputeEvidence) :
    ReceiptTraceContext := {
  startChallengeSHA256 := evidence.startChallengeHash
  inputSHA256 := evidence.claim.inputHash
  resultSHA256 := evidence.claim.outputHash
}

/-- The exact NUL-terminated domain used by `_trace_digest` in the measured
Sqrt218 workload. -/
def measuredTraceDomainV1 : String :=
  "sparkinterval.measured-work-trace.sqrt218-finite.binding.v1" ++
    String.ofList [Char.ofNat 0]

def measuredTraceAlgorithmIdV1 : String :=
  "sparkinterval.ternary-goldbach.sqrt218-finite.v1"

def measuredTraceKindV1 : String :=
  "sparkinterval_challenge_work_trace"

def measuredTraceIterationCountV1 : Nat := 2_000_000

private def traceField (name value : String) : String :=
  name ++ "=" ++ value ++ "\n"

private def isLowerHexDigit (character : Char) : Bool :=
  ('0' ≤ character && character ≤ '9') ||
    ('a' ≤ character && character ≤ 'f')

/-- Syntax check used for every digest in the V2 extension. Cryptographic
meaning is not inferred from syntax. -/
def isCanonicalSHA256Text (value : String) : Bool :=
  value.length == 64 && value.toList.all isLowerHexDigit

/-! ## Signed receipt artifact extension V2 -/

/-- Additional fields that a future normalized receipt must sign directly.

`jobBindingSHA256`, `certificateSHA256`, and
`verificationReportSHA256` are the otherwise-hidden inputs to the existing
trace chain. The two work-trace digests make the trace named by the signed
receipt independently reconstructible.

This is public data, not an authentication capability. A V2 receipt importer
must include these exact fields (or the exact canonical payload below) in the
externally verified signature before constructing theorem-bearing execution
evidence. -/
structure ReceiptArtifactFieldsV2 where
  jobBindingSHA256 : String
  certificateSHA256 : String
  verificationReportSHA256 : String
  workTraceChainSHA256 : String
  workTraceArtifactSHA256 : String
  deriving Repr, DecidableEq, BEq

namespace ReceiptArtifactFieldsV2

/-- Exact preimage of the challenge-dependent chain digest emitted by the
existing measured Sqrt218 workload. -/
def traceChainPayload
    (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) : String :=
  measuredTraceDomainV1 ++
    traceField "challenge_nonce" context.startChallengeSHA256 ++
    traceField "job_binding_sha256" fields.jobBindingSHA256 ++
    traceField "input_sha256" context.inputSHA256 ++
    traceField "result_sha256" context.resultSHA256 ++
    traceField "certificate_sha256" fields.certificateSHA256 ++
    traceField "verification_report_sha256"
      fields.verificationReportSHA256

/-- Chain digest expected from the V1 Sqrt218 workload. -/
def expectedWorkTraceChainSHA256
    (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) : String :=
  SHA256.digestString (fields.traceChainPayload context)

/-- Exact compact sorted-key JSON bytes emitted as the existing work-trace
artifact. Every interpolated value is required to be lowercase SHA-256 by
`check`. -/
def canonicalWorkTraceText
    (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) : String :=
  "{\"algorithm_id\":\"" ++ measuredTraceAlgorithmIdV1 ++
  "\",\"challenge_nonce\":\"" ++ context.startChallengeSHA256 ++
  "\",\"input_sha256\":\"" ++ context.inputSHA256 ++
  "\",\"iteration_count\":" ++ toString measuredTraceIterationCountV1 ++
  ",\"job_binding_sha256\":\"" ++ fields.jobBindingSHA256 ++
  "\",\"kind\":\"" ++ measuredTraceKindV1 ++
  "\",\"result_sha256\":\"" ++ context.resultSHA256 ++
  "\",\"schema_version\":1,\"trace_sha256\":\"" ++
    fields.workTraceChainSHA256 ++ "\"}"

/-- Artifact digest expected for the canonical V1 trace JSON. -/
def expectedWorkTraceArtifactSHA256
    (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) : String :=
  SHA256.digestString (fields.canonicalWorkTraceText context)

/-- Human-readable proposition enforced by the receipt-extension checker. -/
def TraceBound
    (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) : Prop :=
  fields.workTraceChainSHA256 =
      fields.expectedWorkTraceChainSHA256 context ∧
    fields.workTraceArtifactSHA256 =
      fields.expectedWorkTraceArtifactSHA256 context

instance (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) :
    Decidable (fields.TraceBound context) := by
  unfold TraceBound
  infer_instance

/-- Every digest carried by the context and V2 extension has canonical
lowercase SHA-256 syntax. -/
def allDigestsCanonical
    (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) : Bool :=
  isCanonicalSHA256Text context.startChallengeSHA256 &&
    isCanonicalSHA256Text context.inputSHA256 &&
    isCanonicalSHA256Text context.resultSHA256 &&
    isCanonicalSHA256Text fields.jobBindingSHA256 &&
    isCanonicalSHA256Text fields.certificateSHA256 &&
    isCanonicalSHA256Text fields.verificationReportSHA256 &&
    isCanonicalSHA256Text fields.workTraceChainSHA256 &&
    isCanonicalSHA256Text fields.workTraceArtifactSHA256

/--
Small, data-independent validation of the exact trace/digest equations.
It never reads or replays the production archive.
-/
def check
    (fields : ReceiptArtifactFieldsV2)
    (context : ReceiptTraceContext) : Bool :=
  fields.allDigestsCanonical context &&
    decide (fields.TraceBound context)

theorem traceBound_of_check
    {fields : ReceiptArtifactFieldsV2}
    {context : ReceiptTraceContext}
    (hcheck : fields.check context = true) :
    fields.TraceBound context := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact hcheck.2

/-- Exact domain-separated payload that a future V2 receipt signature must
commit. Signing only the final digest of this payload is equivalent at the
disclosed cryptographic boundary, but a source importer must not omit or
reinterpret any field. -/
def canonicalSignedExtensionPayload
    (fields : ReceiptArtifactFieldsV2) : String :=
  "sparkinterval.trusted-compute.sqrt218-artifact-binding.v2\n" ++
    traceField "job_binding_sha256" fields.jobBindingSHA256 ++
    traceField "certificate_sha256" fields.certificateSHA256 ++
    traceField "verification_report_sha256"
      fields.verificationReportSHA256 ++
    traceField "work_trace_chain_sha256" fields.workTraceChainSHA256 ++
    traceField "work_trace_artifact_sha256"
      fields.workTraceArtifactSHA256

def signedExtensionSHA256
    (fields : ReceiptArtifactFieldsV2) : String :=
  SHA256.digestString fields.canonicalSignedExtensionPayload

end ReceiptArtifactFieldsV2

/-! ## Receipt-bound archive -/

/-- Complete ordinary-Lean handoff for a future V2 receipt extension.

The authenticated importer remains responsible for supplying the exact raw
artifact whose digest equals the signed `certificateSHA256`. The strict
decoder then fixes the unique typed archive for those bytes, and `checked`
requires that exact archive to be the input to `Operational.run`.

The structure does not assert that a signature or hardware quote is valid.
That physical/cryptographic premise must remain at the single external-run
trust boundary. -/
structure CheckedReceiptArtifactV2
    (profile : Profile)
    (context : ReceiptTraceContext)
    (fields : ReceiptArtifactFieldsV2) where
  traceChecked : fields.check context = true
  raw : ByteArray
  archive : Archive
  decoded : decodeCanonicalArchiveBytes raw = .ok archive
  certificateDigestBound :
    canonicalArchiveSHA256 archive = fields.certificateSHA256
  checked : run profile archive = true

namespace CheckedReceiptArtifactV2

/-- Forget only the V2 trace metadata while retaining the exact
digest/decoder/checker junction. -/
def toCheckedCanonicalArtifact
    {profile : Profile}
    {context : ReceiptTraceContext}
    {fields : ReceiptArtifactFieldsV2}
    (artifact : CheckedReceiptArtifactV2 profile context fields) :
    CheckedCanonicalArtifact profile fields.certificateSHA256 := {
  raw := artifact.raw
  archive := artifact.archive
  decoded := artifact.decoded
  digestBound := artifact.certificateDigestBound
  checked := artifact.checked
}

theorem exactBytes
    {profile : Profile}
    {context : ReceiptTraceContext}
    {fields : ReceiptArtifactFieldsV2}
    (artifact : CheckedReceiptArtifactV2 profile context fields) :
    canonicalArchiveBytes artifact.archive = artifact.raw :=
  artifact.toCheckedCanonicalArtifact.exactBytes

theorem traceBound
    {profile : Profile}
    {context : ReceiptTraceContext}
    {fields : ReceiptArtifactFieldsV2}
    (artifact : CheckedReceiptArtifactV2 profile context fields) :
    fields.TraceBound context :=
  ReceiptArtifactFieldsV2.traceBound_of_check artifact.traceChecked

theorem archiveFacts
    {profile : Profile}
    {context : ReceiptTraceContext}
    {fields : ReceiptArtifactFieldsV2}
    (artifact : CheckedReceiptArtifactV2 profile context fields) :
    ArchiveFacts profile artifact.archive :=
  artifact.toCheckedCanonicalArtifact.archiveFacts

/-- Every post-authentication step from the signed digest/trace binding and
exact artifact bytes to the paper-shaped claim is an ordinary Lean theorem. -/
theorem sourceClaim
    {profile : Profile}
    {context : ReceiptTraceContext}
    {fields : ReceiptArtifactFieldsV2}
    (artifact : CheckedReceiptArtifactV2 profile context fields) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  artifact.toCheckedCanonicalArtifact.sourceClaim

/-- Decoder uniqueness is byte-level, not a claim that SHA-256 is injective.
Two handoffs retaining the same raw artifact cannot select different typed
archives. -/
theorem archive_eq_of_raw_eq
    {profile : Profile}
    {context : ReceiptTraceContext}
    {fields : ReceiptArtifactFieldsV2}
    (left right : CheckedReceiptArtifactV2 profile context fields)
    (hraw : left.raw = right.raw) :
    left.archive = right.archive := by
  apply decodeCanonicalArchiveBytes_archiveUnique left.decoded
  simpa [hraw] using right.decoded

end CheckedReceiptArtifactV2

end SparkInterval.TernaryGoldbach.Sqrt218Operational
