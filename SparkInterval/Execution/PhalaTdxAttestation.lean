/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.P256
import SparkInterval.Certificate.CanonicalHex
import SparkInterval.Execution.RegisteredAlgorithm
import SparkInterval.Execution.TdxQuoteV4

/-!
# Enclave-signed campaign receipts from a Phala/dstack Intel TDX CVM

This module is a **sibling** of the Azure trusted-compute policy, not an
extension of it.  It shares no acceptance function, no attestation
constructor, and no deployment pin with `Execution/TrustedComputePolicy.lean`
or `Execution/ProductionDeploymentPins.lean`.  Nothing here can make an Azure
receipt acceptable, and nothing here is reachable from an Azure campaign.

## What is checked in Lean, and what is not

Intel TDX quotes are ECDSA P-256 structures with a PCK certificate chain, TCB
levels, and a QE identity.  **None of that is verified here.**  Appraising the
quote is the job of `dcap-qvl`, run outside Lean by the operator, exactly as
MAA appraises the Azure attestation outside Lean today.  What Lean checks is:

* the enclave's P-256 signature over the canonical statement, against a
  **source-pinned** enclave public key (`SparkInterval.Certificate.P256`);
* that the signed statement names the exact registered algorithm, input,
  parameters, and domain of a closed `RegisteredInvocation`;
* that the signed result is in that invocation's canonical result language and
  that its SHA-256 is the signed output digest;
* that the signed dstack application identity, app-compose hash, image digest,
  and `dcap-qvl` policy/binary identities are exactly the pinned ones;
* that the retained quote really is a v4 Intel TDX quote, that its
  `mrconfigid` is the dstack encoding of the **pinned** app-compose hash, and
  that its report data is the SHA-256 -- **recomputed here** -- of the
  domain-separated commitment to the pinned public key, this campaign's
  challenge, and this job's binding; and
* that the SHA-256 of those exact quote bytes is the `tdx_quote_sha256` the
  enclave signed, so the signature covers the quote that was parsed.

The `dcap-qvl` appraisal enters only as the SHA-256 of the retained appraisal
output; retaining that file is an evidence-preservation duty, not a Lean
obligation.

What changed when the quote parser landed: `reportDataHash` and `composeHash`
used to be *fields of the receipt* that Lean checked against a computed
commitment and a pin, with no way to tell whether the quote contained them.
`Execution/TdxQuoteV4.lean` now reads both out of the quote bytes themselves,
so "the CPU measured this app-compose document" and "the enclave put this
commitment in the report data" are machine-checked rather than asserted.

## Why this does not reuse `RunStatement`/`certifyRun`

`RunStatement` carries an `ExecutionTarget`/`TrustProfile` pair, and every
registered production invocation's `deploymentCheck` pins that pair to
`azureSEVSNPCPU` / `azureSEVSNPConfidentialCompute`.  A TDX run is neither.
Reusing the Azure path would therefore require either putting a false Azure
target into a TDX statement, or adding TDX constructors to enums that the
Azure acceptance functions match on -- both of which touch Azure code.  This
module instead reuses the part that is genuinely shared and genuinely
statement-free: `RegisteredInvocation.Runs`, together with every existing
registered success reduction (`…_sourceClaim`).  The ergonomics of the generic
`certifyRun` layer are reproduced in
`Execution/PhalaTdxCampaignCertificate.lean`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- Source-pinned identity of one dstack application running in an Intel TDX
confidential VM.

`attestationAuthority` is the single field that decides whether a receipt
signed by this key may be treated as evidence of a hardware-isolated
execution.  It is `false` for local stand-in keys, which is what keeps a dry
run from ever reaching a production campaign theorem. -/
structure PhalaTdxEnclavePin where
  /-- Human-readable identifier of this pin, for review and audit. -/
  pinId : String
  /-- dstack application id, 40 lowercase hexadecimal digits. -/
  appId : String
  /-- SHA-256 of the dstack `app-compose.json` measured into the CVM. -/
  composeHash : Digest
  /-- OCI image digest of the campaign image, as `sha256:<64 hex>`. -/
  imageDigest : String
  /-- SEC1 uncompressed P-256 public key derived by dstack for this app,
  130 lowercase hexadecimal digits.  The empty string means *not yet pinned*,
  which makes every signature check fail closed. -/
  enclavePublicKeyHex : String
  /-- SHA-256 of the reviewed `dcap-qvl` appraisal policy. -/
  quoteAppraisalPolicyHash : Digest
  /-- SHA-256 of the reviewed `dcap-qvl` binary that appraised the quote. -/
  quoteAppraisalArtifactHash : Digest
  /-- Whether a signature by this key is accepted as evidence that the run
  happened inside an Intel TDX enclave.  Never set this for a key that was
  generated anywhere other than inside the enclave by dstack. -/
  attestationAuthority : Bool
  deriving Repr, DecidableEq, BEq

/-- Closed set of reviewed enclave identities.

This is an inductive, not a caller-populated structure, for exactly the reason
`RegisteredInvocation` is: the trust axiom below must not be applicable to a
pin that a theorem author invented. -/
inductive PhalaTdxEnclave where
  /-- The production CH25 Lemma A.7 campaign application, as a *slot*: its
  public key is empty, so every check against it fails closed.

  The first real run was performed on 2026-07-27 and its reviewed key is
  pinned at `ch25A7BoundaryPhalaProd5V1` below, deliberately as a new
  identity rather than by filling this one in.  Keeping this slot empty keeps
  `ch25A7BoundaryProductionV1_publicKey_unpinned` and
  `ch25A7BoundaryPhalaTdxCheck_eq_false` true as stated, so a real deployment
  was added without weakening any existing guard.  A pin here would name a
  *different* deployment and would be a separate review event. -/
  | ch25A7BoundaryProductionV1
  /-- A local stand-in used by `SparkInterval/Tests/PhalaTdxDryRunTest.lean`.
  It carries **no** attestation authority: no receipt signed by this key can
  discharge the trust axiom, whatever else it satisfies. -/
  | ch25A7BoundaryLocalDryRunV1
  /-- **The one deployment this project attests.**  The dstack application
  that ran the CH25 Lemma A.7 boundary campaign inside an Intel TDX
  confidential VM on Phala Cloud prod5 (CVM `a7-e2e`) on 2026-07-27, whose
  retained evidence is committed at `tests/data/phala_tdx_prod5/`.  Its pin
  literals are machine-derived; see `Execution/PhalaTdxProd5Evidence.lean`,
  which proves by `decide` that the case below is exactly what
  `tools/tg_phala_tdx_pin_from_evidence.py` derives from that evidence. -/
  | ch25A7BoundaryPhalaProd5V1
  /-- The prod5 pin with one hexadecimal digit of the enclave public key
  changed.  It exists for exactly one purpose: so that
  `SparkInterval/Tests/PhalaTdxProd5RunTest.lean` can state, as a Lean
  theorem, that `phalaTdxOutcomeCheck` *rejects* a receipt whose pinned key is
  off by one character.  It carries no attestation authority and must never be
  given any. -/
  | ch25A7BoundaryPhalaProd5TamperedKeyV1
  deriving Repr, DecidableEq, BEq

namespace PhalaTdxEnclave

/-- The reviewed pin data for each closed enclave identity.

Installing the production public key is a trust-boundary review event with
exactly the weight of editing the Azure receipt registry: it is the moment the
project starts trusting a particular Phala deployment. -/
def pin : PhalaTdxEnclave → PhalaTdxEnclavePin
  | .ch25A7BoundaryProductionV1 =>
      { pinId := "sparkinterval.phala-tdx.ch25-a7-boundary.production.v1"
        appId := ""
        composeHash := ""
        imageDigest := ""
        enclavePublicKeyHex := ""
        quoteAppraisalPolicyHash := ""
        quoteAppraisalArtifactHash := ""
        attestationAuthority := true }
  | .ch25A7BoundaryLocalDryRunV1 =>
      -- Every literal below is a documented local-dry-run sentinel produced
      -- by `tests/data/phala_tdx_dry_run/`.  The signing key is committed in
      -- that directory in the clear: it is a stand-in, not a secret, and
      -- `attestationAuthority := false` is what stops it mattering.
      { pinId := "sparkinterval.phala-tdx.ch25-a7-boundary.local-dry-run.v1"
        appId := "327d84eaf0cfb23bfc4260453516a9afc0287705"
        composeHash :=
          "44c2baa7f7fbf92c08d9800071ec0d3d21404c07af1db8254ebd77c717b8e35c"
        imageDigest :=
          "sha256:43233eef77b7ad2463aa6b352a7459ffd42b0d1f8b9373858889d8f1bc0c073c"
        enclavePublicKeyHex :=
          "04f13d15d34f4c77b7482a2deab601e317c284631899a83b15985d5f9c831bc6" ++
          "be15fade17cf66c016ec35c28adf8c79bb5320400c88f6c979e00ebc85ee13f902"
        quoteAppraisalPolicyHash :=
          "62e29a716d65e330fcce6a137c1eed7e6db903740f490ccd2697c8b668710808"
        quoteAppraisalArtifactHash :=
          "4f5ef2ba3f386e03f21f750f76057f807cf20376d727f4013b052f5c0ab3c171"
        attestationAuthority := false }
  | .ch25A7BoundaryPhalaProd5V1 =>
      -- PHALA PROD5, CVM `a7-e2e`, Intel TDX, 2026-07-27T21:48:16Z.
      --
      -- `attestationAuthority := true` here is the project's trust-boundary
      -- statement that this P-256 key was derived by dstack inside that trust
      -- domain and never left it.  It is scoped to this one deployment: this
      -- app id, this app-compose hash, this image digest, and the reviewed
      -- `dcap-qvl` policy and binary that appraised that run's quote.  It says
      -- nothing about any other run, image, or platform.
      --
      -- Every literal is machine-derived from `tests/data/phala_tdx_prod5/`
      -- by `tools/tg_phala_tdx_pin_from_evidence.py`, and
      -- `Execution/PhalaTdxProd5Evidence.lean` proves by `decide` that this
      -- case equals the generated record.  A mistyped digit is a build
      -- failure, not a silently trusted stranger.
      { pinId := "sparkinterval.phala-tdx.ch25-a7-boundary.phala-prod5.v1"
        appId := "8428181231415b81042d93de854c0d82b1dab95b"
        composeHash :=
          "fe27ae910ef7f6760e08eb650e832b076693654deff83418a2a8ea9c9e06cdfd"
        imageDigest :=
          "sha256:4e6029a39771bd18f9e0b9bc64017393700ce47c17a678dd93cbf0ddc17c774f"
        enclavePublicKeyHex :=
          "04102c134190b19efac1e997ff9ab48d517506e14127660704853f2eaa5ae147" ++
          "1f97e2a83645f0f31c14efa912801318e063533b03022a7bf91c08201a84f0222d"
        quoteAppraisalPolicyHash :=
          "9de162db5c359ebc75264d90dd243ea443a2f0d765cb469c31fb57fc21f1a501"
        quoteAppraisalArtifactHash :=
          "cf7f9aaad376230844aad27bb2615377e9c622f334904c1aa35f9f74a78b9ef8"
        attestationAuthority := true }
  | .ch25A7BoundaryPhalaProd5TamperedKeyV1 =>
      -- The prod5 pin with the final hexadecimal digit of the public key
      -- changed from `d` to `0`.  A negative-test fixture, and nothing else:
      -- `attestationAuthority := false` is what keeps it inert.
      { pinId := "sparkinterval.phala-tdx.ch25-a7-boundary.prod5-negative-test.v1"
        appId := "8428181231415b81042d93de854c0d82b1dab95b"
        composeHash :=
          "fe27ae910ef7f6760e08eb650e832b076693654deff83418a2a8ea9c9e06cdfd"
        imageDigest :=
          "sha256:4e6029a39771bd18f9e0b9bc64017393700ce47c17a678dd93cbf0ddc17c774f"
        enclavePublicKeyHex :=
          "04102c134190b19efac1e997ff9ab48d517506e14127660704853f2eaa5ae147" ++
          "1f97e2a83645f0f31c14efa912801318e063533b03022a7bf91c08201a84f02220"
        quoteAppraisalPolicyHash :=
          "9de162db5c359ebc75264d90dd243ea443a2f0d765cb469c31fb57fc21f1a501"
        quoteAppraisalArtifactHash :=
          "cf7f9aaad376230844aad27bb2615377e9c622f334904c1aa35f9f74a78b9ef8"
        attestationAuthority := false }

/-- The `ch25A7BoundaryProductionV1` slot carries no key, so every check
against *that identity* fails closed.  It was left that way when the Phala
prod5 deployment was pinned (as `ch25A7BoundaryPhalaProd5V1`), so this
guarantee, and everything stated in terms of it, is unchanged. -/
theorem ch25A7BoundaryProductionV1_publicKey_unpinned :
    PhalaTdxEnclave.ch25A7BoundaryProductionV1.pin.enclavePublicKeyHex = "" :=
  rfl

/-- The local dry-run identity can never satisfy the trust axiom's authority
premise.  This is the containment that lets a dry run exercise every other
check with a stand-in key. -/
theorem ch25A7BoundaryLocalDryRunV1_no_authority :
    PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1.pin.attestationAuthority
      = false :=
  rfl

end PhalaTdxEnclave

/-- The signed campaign statement produced by the enclave.

Every field is a string.  `signatureHex` is the only field not covered by the
signature; the canonical payload below commits to all the others. -/
structure PhalaTdxReceipt where
  algorithmId : String
  algorithmHash : Digest
  inputHash : Digest
  parametersHash : Digest
  domainHash : Digest
  /-- Exact returned bytes of the campaign. -/
  result : String
  outputHash : Digest
  challengeNonce : Digest
  jobBindingHash : Digest
  appId : String
  composeHash : Digest
  imageDigest : String
  /-- SHA-256 of the retained Intel TDX quote. -/
  quoteHash : Digest
  /-- **The retained quote itself**, packed big-endian.

  This is what makes `reportDataHash` and `composeHash` checkable rather than
  asserted.  `phalaTdxQuoteCheck` parses it with
  `Execution/TdxQuoteV4.lean` and requires its SHA-256 to be `quoteHash`, so
  the enclave's signature -- which covers `quoteHash` -- covers these exact
  bytes.  It is deliberately *not* a separate signed field: nothing new is
  trusted, an existing signed commitment is merely opened. -/
  quote : SHA256.PackedBytes
  /-- SHA-256 of the retained `dcap-qvl` appraisal output. -/
  quoteAppraisalHash : Digest
  quoteAppraisalPolicyHash : Digest
  quoteAppraisalArtifactHash : Digest
  /-- SHA-256 the enclave placed in the quote's report data. -/
  reportDataHash : Digest
  issuedAt : String
  /-- `r || s`, 128 lowercase hexadecimal digits. -/
  signatureHex : String
  deriving Repr, DecidableEq, BEq

/-- Commit a variable-length value before it enters the line format, so no
field value can be shifted into another field's position. -/
private def phalaTdxCommittedField (name value : String) : String :=
  name ++ "=" ++ SHA256.digestString value ++ "\n"

/-- Bytes whose SHA-256 the enclave places in the TDX quote's report data.

This is what ties the quote to the signing key.  Without it, a genuine quote
from one enclave and a genuine signature from an unrelated key would both
verify while proving nothing jointly. -/
def phalaTdxReportDataPreimage
    (enclavePublicKeyHex challengeNonce jobBindingHash : String) : String :=
  "sparkinterval.phala-tdx-report-data.v1\n" ++
  phalaTdxCommittedField "enclave_public_key" enclavePublicKeyHex ++
  phalaTdxCommittedField "challenge_nonce" challengeNonce ++
  phalaTdxCommittedField "job_binding_sha256" jobBindingHash

/-- Exact bytes signed by the enclave.  Mirrored by
`tg_verifier/phala_tdx_receipt.py`; the two are kept in step by
`tests/test_phala_tdx_first_run.py`. -/
def PhalaTdxReceipt.canonicalSignedPayload (receipt : PhalaTdxReceipt) :
    String :=
  "sparkinterval.phala-tdx-attested-run.v1\n" ++
  phalaTdxCommittedField "algorithm_id" receipt.algorithmId ++
  phalaTdxCommittedField "algorithm_hash" receipt.algorithmHash ++
  phalaTdxCommittedField "input_hash" receipt.inputHash ++
  phalaTdxCommittedField "parameters_hash" receipt.parametersHash ++
  phalaTdxCommittedField "domain_hash" receipt.domainHash ++
  phalaTdxCommittedField "result" receipt.result ++
  phalaTdxCommittedField "output_hash" receipt.outputHash ++
  phalaTdxCommittedField "challenge_nonce" receipt.challengeNonce ++
  phalaTdxCommittedField "job_binding_sha256" receipt.jobBindingHash ++
  phalaTdxCommittedField "app_id" receipt.appId ++
  phalaTdxCommittedField "compose_hash" receipt.composeHash ++
  phalaTdxCommittedField "image_digest" receipt.imageDigest ++
  phalaTdxCommittedField "tdx_quote_sha256" receipt.quoteHash ++
  phalaTdxCommittedField "dcap_qvl_output_sha256" receipt.quoteAppraisalHash ++
  phalaTdxCommittedField "dcap_qvl_policy_sha256"
    receipt.quoteAppraisalPolicyHash ++
  phalaTdxCommittedField "dcap_qvl_artifact_sha256"
    receipt.quoteAppraisalArtifactHash ++
  phalaTdxCommittedField "report_data_sha256" receipt.reportDataHash ++
  phalaTdxCommittedField "issued_at" receipt.issuedAt

/-- SHA-256 of the canonical signed payload; this is the digest signed. -/
def PhalaTdxReceipt.statementDigest (receipt : PhalaTdxReceipt) : Digest :=
  SHA256.digestString receipt.canonicalSignedPayload

/-- Verify the enclave's P-256 signature against the source-pinned key.

This is the only cryptography Lean performs on this path. -/
def phalaTdxSignatureCheck
    (enclave : PhalaTdxEnclave) (receipt : PhalaTdxReceipt) : Bool :=
  P256.verifyDigestHex enclave.pin.enclavePublicKeyHex
    receipt.statementDigest receipt.signatureHex

/-- Every deployment coordinate the receipt asserts is exactly the reviewed
pin, the digests are canonical, and the quote's report data commits to the
pinned key and this campaign's challenge. -/
def phalaTdxPinCheck
    (enclave : PhalaTdxEnclave) (receipt : PhalaTdxReceipt) : Bool :=
  let expected := enclave.pin
  expected.appId == receipt.appId &&
  expected.composeHash == receipt.composeHash &&
  expected.imageDigest == receipt.imageDigest &&
  expected.quoteAppraisalPolicyHash == receipt.quoteAppraisalPolicyHash &&
  expected.quoteAppraisalArtifactHash == receipt.quoteAppraisalArtifactHash &&
  Certificate.isCanonicalLowerHexOfLength 40 receipt.appId &&
  Certificate.isCanonicalLowerHexOfLength 64 receipt.composeHash &&
  Certificate.isCanonicalLowerHexOfLength 64 receipt.challengeNonce &&
  Certificate.isCanonicalLowerHexOfLength 64 receipt.jobBindingHash &&
  Certificate.isCanonicalLowerHexOfLength 64 receipt.quoteHash &&
  Certificate.isCanonicalLowerHexOfLength 64 receipt.quoteAppraisalHash &&
  Certificate.isCanonicalLowerHexOfLength 64
    receipt.quoteAppraisalPolicyHash &&
  Certificate.isCanonicalLowerHexOfLength 64
    receipt.quoteAppraisalArtifactHash &&
  Certificate.isCanonicalLowerHexOfLength 64 receipt.reportDataHash &&
  Certificate.isCanonicalLowerHexOfLength 128 receipt.signatureHex &&
  Certificate.isCanonicalLowerHexOfLength 130 expected.enclavePublicKeyHex &&
  receipt.reportDataHash ==
    SHA256.digestString
      (phalaTdxReportDataPreimage expected.enclavePublicKeyHex
        receipt.challengeNonce receipt.jobBindingHash)

/-- The signed statement names the exact closed registered invocation, and its
result is bound to the signed output digest and to that invocation's canonical
result language. -/
def phalaTdxInvocationCheck
    (invocation : RegisteredInvocation) (receipt : PhalaTdxReceipt) : Bool :=
  receipt.algorithmId == invocation.algorithm.algorithmId &&
  receipt.algorithmHash == invocation.algorithm.algorithmHash &&
  receipt.inputHash == invocation.canonicalInputHash &&
  receipt.parametersHash == invocation.algorithm.canonicalParametersHash &&
  receipt.domainHash == invocation.algorithm.canonicalDomainHash &&
  invocation.sourceBindingDiagnosticCheck &&
  receipt.outputHash == SHA256.digestString receipt.result &&
  decide (invocation.ResultAllowed receipt.result)

/-- **The quote binding.**  Everything the retained TDX quote must itself
say, read out of its bytes.

Four conditions, none of which was checkable before the quote was parsed:

1. the bytes are a v4 quote from an Intel TDX platform and are long enough to
   contain a TD report body;
2. the quote's `mrconfigid` is `01 ‖ composeHash ‖ 0…0` for the **pinned**
   app-compose hash -- that is, the CPU measured the reviewed configuration;
3. the quote's report data is exactly the SHA-256, *recomputed here from the
   pinned public key and this run's challenge and job binding*, with the
   upper 32 bytes zero; and
4. the SHA-256 of these exact quote bytes is the `tdx_quote_sha256` the
   enclave signed.

Condition 3 is the one that closes the statement-to-quote chain: the digest
is computed, never read from the receipt.  Condition 4 is what stops a
genuine receipt from being paired with somebody else's genuine quote.

None of this appraises the quote's Intel signature, PCK chain, TCB level, or
QE identity.  That remains `dcap-qvl`'s job, outside Lean. -/
def phalaTdxQuoteCheck
    (enclave : PhalaTdxEnclave) (receipt : PhalaTdxReceipt) : Bool :=
  TdxQuoteV4.wellFormed receipt.quote &&
    TdxQuoteV4.quoteBindsCompose receipt.quote enclave.pin.composeHash &&
      TdxQuoteV4.quoteBindsStatement receipt.quote
        (SHA256.digestString
          (phalaTdxReportDataPreimage enclave.pin.enclavePublicKeyHex
            receipt.challengeNonce receipt.jobBindingHash)) &&
        receipt.quote.digest == receipt.quoteHash

/-- The complete fail-closed acceptance check for one enclave-signed run. -/
def phalaTdxOutcomeCheck (enclave : PhalaTdxEnclave)
    (invocation : RegisteredInvocation) (receipt : PhalaTdxReceipt) : Bool :=
  phalaTdxPinCheck enclave receipt &&
    phalaTdxInvocationCheck invocation receipt &&
      phalaTdxQuoteCheck enclave receipt &&
        phalaTdxSignatureCheck enclave receipt

/-- An unpinned enclave public key makes acceptance impossible, whatever the
rest of the receipt says.  This is what "fail closed until credentials exist"
means concretely. -/
theorem phalaTdxOutcomeCheck_eq_false_of_unpinned_key
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (hunpinned :
      Certificate.isCanonicalLowerHexOfLength 130
        enclave.pin.enclavePublicKeyHex = false) :
    phalaTdxOutcomeCheck enclave invocation receipt = false := by
  simp [phalaTdxOutcomeCheck, phalaTdxPinCheck, hunpinned]

/-- The production identity is unreachable today. -/
theorem phalaTdxOutcomeCheck_ch25A7BoundaryProductionV1_eq_false
    (invocation : RegisteredInvocation) (receipt : PhalaTdxReceipt) :
    phalaTdxOutcomeCheck .ch25A7BoundaryProductionV1 invocation receipt
      = false :=
  phalaTdxOutcomeCheck_eq_false_of_unpinned_key (by decide)

/-! ## The quote must be a quote, and must be *this* quote

A checker that accepted everything would satisfy every positive statement in
this module.  These are the refusals. -/

/-- A quote too short to contain a TD report body forces rejection.  This is
the case a stand-in file, a truncated download, or an empty field falls
into. -/
theorem phalaTdxOutcomeCheck_eq_false_of_truncated_quote
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (hshort : receipt.quote.byteCount < TdxQuoteV4.minimumByteCount) :
    phalaTdxOutcomeCheck enclave invocation receipt = false := by
  simp [phalaTdxOutcomeCheck, phalaTdxQuoteCheck,
    TdxQuoteV4.wellFormed_eq_false_of_short hshort]

/-- A quote whose measured configuration is not the pinned app-compose
document forces rejection, however well-formed the rest of the receipt is.
This is the guard that a different measured code base cannot borrow this
deployment's identity. -/
theorem phalaTdxOutcomeCheck_eq_false_of_wrong_mrConfigId
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (hmismatch :
      TdxQuoteV4.mrConfigIdHex receipt.quote ≠
        TdxQuoteV4.expectedMrConfigIdHex enclave.pin.composeHash) :
    phalaTdxOutcomeCheck enclave invocation receipt = false := by
  simp [phalaTdxOutcomeCheck, phalaTdxQuoteCheck,
    TdxQuoteV4.quoteBindsCompose_eq_false_of_mismatch hmismatch]

/-- A quote whose report data is not the recomputed commitment forces
rejection.  The digest on the right is computed from the pinned key and this
run's challenge and job binding; nothing the receipt says about it is
consulted. -/
theorem phalaTdxOutcomeCheck_eq_false_of_wrong_reportData
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (hmismatch :
      TdxQuoteV4.reportDataStatementHex receipt.quote ≠
        SHA256.digestString
          (phalaTdxReportDataPreimage enclave.pin.enclavePublicKeyHex
            receipt.challengeNonce receipt.jobBindingHash)) :
    phalaTdxOutcomeCheck enclave invocation receipt = false := by
  simp [phalaTdxOutcomeCheck, phalaTdxQuoteCheck,
    TdxQuoteV4.quoteBindsStatement_eq_false_of_mismatch hmismatch]

/-- A quote whose own SHA-256 is not the signed `tdx_quote_sha256` forces
rejection.  Without this a genuine receipt could be presented alongside an
unrelated genuine quote. -/
theorem phalaTdxOutcomeCheck_eq_false_of_unbound_quote
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (hmismatch : receipt.quote.digest ≠ receipt.quoteHash) :
    phalaTdxOutcomeCheck enclave invocation receipt = false := by
  simp [phalaTdxOutcomeCheck, phalaTdxQuoteCheck, hmismatch]

end SparkInterval.Execution
