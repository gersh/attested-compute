/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.P256
import SparkInterval.Certificate.CanonicalHex
import SparkInterval.Execution.RegisteredAlgorithm

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
  and `dcap-qvl` policy/binary identities are exactly the pinned ones; and
* that the SHA-256 the enclave placed in the TDX quote's report data is the
  domain-separated commitment to the pinned public key and this campaign's
  challenge, so the quote and the signature cannot come from two unrelated
  parties.

The `dcap-qvl` appraisal enters only as the SHA-256 of the retained appraisal
output; retaining that file is an evidence-preservation duty, not a Lean
obligation.

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
  /-- The production CH25 Lemma A.7 campaign application.  Its public key is
  deliberately unfilled until a first real run has been performed and the
  dstack-derived key has been reviewed and pinned by a source change. -/
  | ch25A7BoundaryProductionV1
  /-- A local stand-in used by `SparkInterval/Tests/PhalaTdxDryRunTest.lean`.
  It carries **no** attestation authority: no receipt signed by this key can
  discharge the trust axiom, whatever else it satisfies. -/
  | ch25A7BoundaryLocalDryRunV1
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
      { pinId := "sparkinterval.phala-tdx.ch25-a7-boundary.local-dry-run.v1"
        appId := "00112233445566778899aabbccddeeff00112233"
        composeHash :=
          "6a0aa5bcbf5cbe2b1e0f6ab52e6a4b32aef6ab97b1c0f5f6d3a2f4c76a6bd0be"
        imageDigest :=
          "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        enclavePublicKeyHex := ""
        quoteAppraisalPolicyHash :=
          "0000000000000000000000000000000000000000000000000000000000000000"
        quoteAppraisalArtifactHash :=
          "0000000000000000000000000000000000000000000000000000000000000000"
        attestationAuthority := false }

/-- No production pin is installed, so every production signature check fails
closed.  Supplying the reviewed dstack-derived key is the single source edit
that enables the first real run. -/
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
  /-- SHA-256 of the retained Intel TDX quote.  Lean does not parse it. -/
  quoteHash : Digest
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

/-- The complete fail-closed acceptance check for one enclave-signed run. -/
def phalaTdxOutcomeCheck (enclave : PhalaTdxEnclave)
    (invocation : RegisteredInvocation) (receipt : PhalaTdxReceipt) : Bool :=
  phalaTdxPinCheck enclave receipt &&
    phalaTdxInvocationCheck invocation receipt &&
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

end SparkInterval.Execution
