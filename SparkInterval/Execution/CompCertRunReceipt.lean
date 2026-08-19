/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.P256
import SparkInterval.Execution.CompCertRunLedger

/-!
# Checking an enclave-signed CompCert run receipt

`tg_verifier/compcert_run_receipt.py` produces receipts of kind
`sparkinterval.compcert-run-receipt.v1`: thirteen named fields, a P-256
signature over their canonical digest, and the enclave public key that signed.
This module is the Lean side of that format.

## ⚠ This module admits nothing

It contains **no axiom and no `opaque`**, and that is the design, not an
omission.

Everything here is decidable: whether a receipt's canonical digest recomputes,
whether its signature verifies under the named key, whether the key is one a
reviewed pin names, and whether the fields describe the artifact a
`CompCertRunSpec` identifies. All of that is arithmetic on strings.

What none of it establishes is that **a machine really executed anything** —
no signature can, since a signature proves only that a key was used. That
empirical step already has a home:
`leancompcert/LeanCompCert/Attest/Admission.lean` states it as
`opaque MachineExecuted` inside a `RunAdmission` hypothesis, with a join to
`Computation.Returns`. A consumer combines a `CertifiedCompCertReceipt` from
here with a `RunAdmission` from there.

Adding a fresh `opaque`+axiom pair here would be a **third** notion of "a run
happened" in a codebase that already has two (`PhalaTdxAttestedEmission` and
`MachineExecuted`), one of them entirely unused downstream. So this module
stops at the checkable part.

## Why not `phalaTdxOutcomeCheck`

That checker is keyed on `PhalaTdxEnclave` and `RegisteredInvocation`, both
closed inductives — registering one CompCert run there means editing two
enumerations and about twenty match arms. The pins here are a **list with a
lookup**, the shape `TrustedComputeRegistry.importedTrustedComputeRuns`
already uses on the Azure side: reviewed as data, generated rather than
hand-edited, and not extensible by a caller at proof time. Adding an enclave
is a generator run, not an inductive edit.

Keeping the pin *list* closed still matters. `attestationAuthority` is the
assertion that a key was produced inside a TDX enclave by dstack; if any
caller could conjure a pin with it set, every check below would be
bypassable. A caller may supply a receipt; only the reviewed table supplies
authority.

## Cost

`digestString` over the canonical payload is the expensive part: thirteen
committed fields is roughly a kilobyte, and a 1,024-byte `digestString`
measures at 92 s / 22 GB in the kernel (`docs/COMPCERT_ARTIFACT_UNDER_TDX.md`).
The P-256 verification is cheap by comparison, 3.9 s / 1.1 GB
(`SparkInterval/Certificate/P256.lean`). Check one receipt per module.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- One enclave-signed receipt, exactly the wire format the producer emits. -/
structure CompCertRunReceipt where
  /-- `compcert-run-v1:<programName>`. -/
  algorithmId : String
  /-- SHA-256 of the spec's `canonicalDefinition`. -/
  algorithmHash : String
  /-- SHA-256 of the emitted C's digest — which artifact ran. -/
  inputHash : String
  /-- SHA-256 of the artifact's transcript. -/
  result : String
  /-- SHA-256 of `result`. -/
  outputHash : String
  /-- `"1"` exactly when the enclave's comparison against the pinned
  expectation passed. -/
  matchedPinnedExpectation : String
  appId : String
  composeHash : String
  /-- SHA-256 of the app-compose document the enclave read inside the TD. -/
  appComposeSha256 : String
  /-- SHA-256 of the `docker_compose_file` that document carries. -/
  dockerComposeFileSha256 : String
  tdxQuoteSha256 : String
  reportDataSha256 : String
  issuedAt : String
  /-- SEC1 uncompressed P-256 public key, 130 lowercase hex characters. -/
  enclavePublicKey : String
  /-- The canonical payload digest the signature is over. -/
  receiptSha256 : String
  /-- P-256 signature, 128 lowercase hex characters. -/
  signature : String
  deriving Repr, DecidableEq, BEq

/-- A reviewed enclave identity.

Not caller-constructible in practice: `compcertEnclavePins` below is the only
table consulted, and `attestationAuthority` is meaningful only there. -/
structure CompCertEnclavePin where
  /-- Human-readable identifier, for review. -/
  pinId : String
  appId : String
  composeHash : String
  /-- The key dstack derived for this app, 130 lowercase hex.  The empty
  string means *not yet pinned*, which makes every signature check fail
  closed. -/
  enclavePublicKey : String
  /-- Whether a signature by this key counts as evidence that the run happened
  inside an Intel TDX enclave.  Never set for a key generated anywhere else. -/
  attestationAuthority : Bool
  deriving Repr, DecidableEq, BEq

/-- Reviewed enclave pins.

Empty until a run's identity has been reviewed and added, which makes every
check below fail closed — the same "no credentials yet" stance
`PhalaTdxEnclave.ch25A7BoundaryProductionV1` takes with an empty key. -/
def compcertEnclavePins : List CompCertEnclavePin := []

/-- Lookup by app id.  Duplicate app ids are rejected by the generator before
this source is emitted. -/
def lookupCompCertEnclavePin (appId : String) : Option CompCertEnclavePin :=
  compcertEnclavePins.find? (fun pin => pin.appId == appId)

namespace CompCertRunReceipt

/-- One line of the canonical payload: the field name and the SHA-256 of its
value.  Committing rather than inlining is what stops a value containing a
newline from being read as a following field. -/
private def committedField (name value : String) : String :=
  name ++ "=" ++ SHA256.digestString value ++ "\n"

/-- The exact string the enclave signed.  Field order is part of the preimage;
adding a field is a new receipt kind, never an edit here. -/
def canonicalPayload (r : CompCertRunReceipt) : String :=
  "sparkinterval.compcert-run-receipt.v1\n" ++
  committedField "algorithm_id" r.algorithmId ++
  committedField "algorithm_hash" r.algorithmHash ++
  committedField "input_hash" r.inputHash ++
  committedField "result" r.result ++
  committedField "output_hash" r.outputHash ++
  committedField "matched_pinned_expectation" r.matchedPinnedExpectation ++
  committedField "app_id" r.appId ++
  committedField "compose_hash" r.composeHash ++
  committedField "app_compose_sha256" r.appComposeSha256 ++
  committedField "docker_compose_file_sha256" r.dockerComposeFileSha256 ++
  committedField "tdx_quote_sha256" r.tdxQuoteSha256 ++
  committedField "report_data_sha256" r.reportDataSha256 ++
  committedField "issued_at" r.issuedAt

/-- The digest recomputes from the fields.  Without this the signature would
be over whatever `receiptSha256` claims rather than over the receipt. -/
def digestCheck (r : CompCertRunReceipt) : Bool :=
  SHA256.digestString r.canonicalPayload == r.receiptSha256

/-- The signature verifies under the key the receipt names. -/
def signatureCheck (r : CompCertRunReceipt) : Bool :=
  P256.verifyDigestHex r.enclavePublicKey r.receiptSha256 r.signature

/-- The receipt describes the artifact this spec identifies.

`algorithmHash` is the load-bearing one: it is the SHA-256 of the spec's
generated `canonicalDefinition`, which names the emitted C's digest, the
toolchain and the accepted value.  A receipt for another artifact cannot
satisfy it. -/
def specCheck (r : CompCertRunReceipt) (spec : CompCertRunSpec) : Bool :=
  r.algorithmId == spec.algorithmId &&
    r.algorithmHash == spec.algorithmHash &&
    r.matchedPinnedExpectation == "1"

/-- The receipt was signed by the pinned key of the pinned deployment. -/
def pinCheck (r : CompCertRunReceipt) (pin : CompCertEnclavePin) : Bool :=
  pin.attestationAuthority &&
    pin.enclavePublicKey.length == 130 &&
    r.enclavePublicKey == pin.enclavePublicKey &&
    r.appId == pin.appId &&
    r.composeHash == pin.composeHash

end CompCertRunReceipt

/-- Fail-closed check for one signed CompCert run receipt. -/
def compcertRunReceiptCheck (r : CompCertRunReceipt) (pin : CompCertEnclavePin)
    (spec : CompCertRunSpec) : Bool :=
  spec.specWellFormed && r.pinCheck pin && r.specCheck spec &&
    r.digestCheck && r.signatureCheck

/-- What an accepted receipt establishes — all of it decidable, none of it
about whether a machine ran.

`signatureBinds` is the substantive one: a P-256 signature by the reviewed
enclave key stands over a payload that names this artifact and this result. -/
structure CertifiedCompCertReceipt (r : CompCertRunReceipt)
    (pin : CompCertEnclavePin) (spec : CompCertRunSpec) : Prop where
  /-- The pinned deployment is one whose signatures count. -/
  authority : pin.attestationAuthority = true
  /-- The receipt names the pinned key, app and compose. -/
  pinned : r.pinCheck pin = true
  /-- The receipt describes this artifact, and the enclave's own comparison
  against the pinned expectation passed. -/
  describes : r.specCheck spec = true
  /-- Its digest recomputes from its fields. -/
  digest : SHA256.digestString r.canonicalPayload = r.receiptSha256
  /-- And that digest carries a valid signature under the pinned key. -/
  signatureBinds :
    P256.verifyDigestHex r.enclavePublicKey r.receiptSha256 r.signature = true

/-- Soundness of the fail-closed check.  **Axiom-free** — base trio only.

Turning this into a statement about a `Computation` needs the empirical
premise, which lives in `LeanCompCert.Attest.Admission` and is deliberately
not restated here. -/
theorem certifyCompCertReceipt {r : CompCertRunReceipt}
    {pin : CompCertEnclavePin} {spec : CompCertRunSpec}
    (hcheck : compcertRunReceiptCheck r pin spec = true) :
    CertifiedCompCertReceipt r pin spec := by
  -- `&&` associates left, so this is `((((A && B) && C) && D) && E)`.  The
  -- conjuncts are extracted with `tauto` rather than by projection index:
  -- guessing the nesting is how the two previous versions of this proof broke,
  -- and `beq_iff_eq` is deliberately NOT in the simp set here, because turning
  -- a component into a String equation makes `obtain` attempt dependent
  -- elimination and fail.
  simp only [compcertRunReceiptCheck, Bool.and_eq_true] at hcheck
  obtain ⟨⟨⟨⟨_hwf, hpin⟩, hspec⟩, hdig⟩, hsig⟩ := hcheck
  have hauth : pin.attestationAuthority = true := by
    simp only [CompCertRunReceipt.pinCheck, Bool.and_eq_true] at hpin
    tauto
  exact {
    authority := hauth
    pinned := hpin
    describes := hspec
    digest := by simpa [CompCertRunReceipt.digestCheck] using hdig
    signatureBinds := by simpa [CompCertRunReceipt.signatureCheck] using hsig }

/-- An empty pin table refuses every receipt.  This is what "fail closed until
an identity has been reviewed" means, and it is proved rather than asserted. -/
theorem compcertRunReceiptCheck_eq_false_of_unpinned
    (r : CompCertRunReceipt) (spec : CompCertRunSpec)
    (pin : CompCertEnclavePin) (hpin : pin.attestationAuthority = false) :
    compcertRunReceiptCheck r pin spec = false := by
  simp [compcertRunReceiptCheck, CompCertRunReceipt.pinCheck, hpin]

/-- A key of the wrong length is refused whatever else holds: a pin whose key
has not been filled in cannot accept anything. -/
theorem compcertRunReceiptCheck_eq_false_of_short_key
    (r : CompCertRunReceipt) (spec : CompCertRunSpec)
    (pin : CompCertEnclavePin) (hkey : pin.enclavePublicKey.length ≠ 130) :
    compcertRunReceiptCheck r pin spec = false := by
  simp [compcertRunReceiptCheck, CompCertRunReceipt.pinCheck, hkey]

/-- A receipt whose enclave did **not** match its pinned expectation is
refused, however well signed it is. -/
theorem compcertRunReceiptCheck_eq_false_of_mismatch
    (r : CompCertRunReceipt) (spec : CompCertRunSpec)
    (pin : CompCertEnclavePin) (hm : r.matchedPinnedExpectation ≠ "1") :
    compcertRunReceiptCheck r pin spec = false := by
  simp [compcertRunReceiptCheck, CompCertRunReceipt.specCheck, hm]

end SparkInterval.Execution
