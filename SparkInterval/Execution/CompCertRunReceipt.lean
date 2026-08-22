/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.P256
import SparkInterval.Execution.CompCertRunLedger

/-!
# Checking an enclave-signed CompCert run receipt

**The end-to-end picture is `docs/ATTESTED_COMPCERT_RUNS.md`** — what is
proved, what is computed, the one thing that is admitted, and why the axiom
that consumes this module lives in the consumer rather than here.

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

A closed table, and the only source of attestation authority: the check looks
a pin up here by the receipt's own `appId` and never accepts one from a
caller.  Adding an entry is therefore a reviewable change to this file, not
something a proof can do to itself. -/
def compcertEnclavePins : List CompCertEnclavePin :=
  -- ⚠ `attestationAuthority := true` IS THE TRUST DECISION on every line
  -- below: a person asserting each key was derived inside an enclave.
  -- Evidence: `audits/compcert/rh_phala_<batch>/retained-evidence/` in
  -- the consuming repository, each re-verifying offline against the
  -- pinned Intel SGX Root CA.  904 checks, 0 failures, 73 receipts.
  --
  -- Five deployments rather than one because `docker_compose_file` is
  -- capped at 200 KB; the artifacts do not fit in a single compose, and
  -- each deployment is therefore a separate app id and a separate
  -- reviewed identity.
  [
  { -- Intel TDX, 2026-08-22, batch `pilots`: 2 attested CompCert run(s).
      pinId := "rh-x86-pilots-2026-08-22"
      appId := "a5363d2d478318f2c404f3ef7737b50c47039ee4"
      composeHash :=
        "9824273a2b4dc57a5acfb747a83348f070729651bda915eb34778c03ce719cb0"
      enclavePublicKey :=
        "04cd270c646b426e02d3cb8b831d506e663f5ceca7aa2a7852cc4adbb3f5202c2584" ++
        "463a6f8a2e310d28ddddaf1dd574336548f2ec2c8059f034345478842b6db7"
      attestationAuthority := true },
  { -- Intel TDX, 2026-08-22, batch `b1`: 12 attested CompCert run(s).
      pinId := "rh-x86-b1-2026-08-22"
      appId := "a27953320f86dc25aa05e0ce897f179fa75f5d8e"
      composeHash :=
        "dded0eb20bd56250f46e92365d2b5967cc744731332c58976b5a1815cdf20e5a"
      enclavePublicKey :=
        "04e885f5b124e5522ec3f2ad1393f58124515a0cfce17887f8622d5f072288756216" ++
        "29c909af28f5704de6f316d6d97ffe1b538db787f3faa7c94ebd31770c2cdb"
      attestationAuthority := true },
  { -- Intel TDX, 2026-08-22, batch `b2`: 26 attested CompCert run(s).
      pinId := "rh-x86-b2-2026-08-22"
      appId := "2ecf40ab8795d721f2e29e64ca43c5f0370a1ab7"
      composeHash :=
        "fe17da0094b39fe01b4b03a788bba702720cf586e2567a93e729f2fe6e181402"
      enclavePublicKey :=
        "040350ac37718e3400ed8737be6a64f4acba593ac465935f75f02ccc5aa946f06f7a" ++
        "15c32898fc7fcd487159b90cd7403532e596bed8319c647ab2767c23c72ee9"
      attestationAuthority := true },
  { -- Intel TDX, 2026-08-22, batch `b3a`: 21 attested CompCert run(s).
      pinId := "rh-x86-b3a-2026-08-22"
      appId := "eaac63decf756154d5bb1a53701073ca4bcce26d"
      composeHash :=
        "fabb6e8c94286b5bdcd6df6d3c563fbb43ed2956a41c56132ecfd190b05d0acd"
      enclavePublicKey :=
        "04e33d49ed8f6f3ca717f98af02a6c065da90832c40878d63a8fca6ec601bda9e6a8" ++
        "9eea93854ffdc7ff35ef3a26df9f4a6667fd4fdf03895bb04dd48bb675cf7d"
      attestationAuthority := true },
  { -- Intel TDX, 2026-08-22, batch `b3b`: 12 attested CompCert run(s).
      pinId := "rh-x86-b3b-2026-08-22"
      appId := "38ecb64588f6e81681cd9eddc00195947ded5cd7"
      composeHash :=
        "b880bc9d0e25afeb62185f1fb59dd113fe8a2bd3ea0d1429a39d63502672e97d"
      enclavePublicKey :=
        "04c1794247852c52e7537b877e368a26267cc9b346bdf3a5f3224d610ae5ed77e555" ++
        "5bdd5fbd9431c36019091acd506ae0bd92df9ffc7537982e2c2e0b33669144"
      attestationAuthority := true } ]

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

/-- Fail-closed check for one signed CompCert run receipt.

**The pin is looked up, never supplied.**  An earlier version took it as a
parameter, which meant the caller supplied the trust anchor: forge a pin
carrying your own public key and `attestationAuthority := true`, sign anything
with the matching private key, and the check passed with no enclave involved.
That was demonstrated, not theorised.  Keying the lookup on the receipt's own
`appId` against the closed reviewed table is what makes the signature mean
something: a key that is not in this source file cannot be made to count, and
adding one is visible in a diff. -/
def compcertRunReceiptCheck (r : CompCertRunReceipt)
    (spec : CompCertRunSpec) : Bool :=
  match lookupCompCertEnclavePin r.appId with
  | none => false
  | some pin =>
      spec.specWellFormed && r.pinCheck pin && r.specCheck spec &&
        r.digestCheck && r.signatureCheck

/-- What an accepted receipt establishes.

`reviewedPin` is the load-bearing field and the reason this structure does not
take a pin as a parameter: the pin must come from `compcertEnclavePins`, so a
caller cannot conjure the authority that makes a signature count. -/
structure CertifiedCompCertReceipt (r : CompCertRunReceipt)
    (spec : CompCertRunSpec) : Prop where
  /-- Some pin in the **reviewed table** matches this receipt, carries
  attestation authority, and is the key the receipt names. -/
  reviewedPin : ∃ pin, lookupCompCertEnclavePin r.appId = some pin ∧
    pin.attestationAuthority = true ∧ r.pinCheck pin = true
  /-- The receipt describes this artifact, and the enclave's own comparison
  against the pinned expectation passed. -/
  describes : r.specCheck spec = true
  /-- Its digest recomputes from its fields. -/
  digest : SHA256.digestString r.canonicalPayload = r.receiptSha256
  /-- And that digest carries a valid signature under the key it names. -/
  signatureBinds :
    P256.verifyDigestHex r.enclavePublicKey r.receiptSha256 r.signature = true

set_option maxHeartbeats 1000000 in
/-- Soundness of the fail-closed check.  **Axiom-free** — base trio only.

The heartbeat allowance is for elaboration only: the pin table is a list, so
matching a receipt against it costs string comparisons that the default budget
does not cover once the table is non-empty. -/
theorem certifyCompCertReceipt {r : CompCertRunReceipt} {spec : CompCertRunSpec}
    (hcheck : compcertRunReceiptCheck r spec = true) :
    CertifiedCompCertReceipt r spec := by
  unfold compcertRunReceiptCheck at hcheck
  cases hlookup : lookupCompCertEnclavePin r.appId with
  | none => rw [hlookup] at hcheck; exact absurd hcheck (by simp)
  | some pin =>
      rw [hlookup] at hcheck
      -- Projections, not `obtain` and not `tauto`.  `obtain` makes `cases`
      -- attempt dependent elimination on the P-256 term; `tauto` exhausts its
      -- heartbeats once the pin table is non-empty.  `&&` associates left, so
      -- five conjuncts are `((((A ∧ B) ∧ C) ∧ D) ∧ E)`.
      simp only [Bool.and_eq_true] at hcheck
      have hpin : r.pinCheck pin = true := hcheck.1.1.1.2
      have hspec : r.specCheck spec = true := hcheck.1.1.2
      have hdig : r.digestCheck = true := hcheck.1.2
      have hsig : r.signatureCheck = true := hcheck.2
      have hauth : pin.attestationAuthority = true := by
        simp only [CompCertRunReceipt.pinCheck, Bool.and_eq_true] at hpin
        exact hpin.1.1.1.1
      exact {
        reviewedPin := ⟨pin, hlookup, hauth, hpin⟩
        describes := hspec
        digest := by simpa [CompCertRunReceipt.digestCheck] using hdig
        signatureBinds := by simpa [CompCertRunReceipt.signatureCheck] using hsig }

/-- An **unlisted** enclave is refused.  With `compcertEnclavePins` empty this
refuses everything, which is what "fail closed until an identity has been
reviewed" means -- and it is now a property of the check itself rather than of
whatever pin a caller chose to pass. -/
theorem compcertRunReceiptCheck_eq_false_of_unlisted
    (r : CompCertRunReceipt) (spec : CompCertRunSpec)
    (h : lookupCompCertEnclavePin r.appId = none) :
    compcertRunReceiptCheck r spec = false := by
  -- `rw`, not `simp`: with a non-empty pin table `simp` tries to evaluate the
  -- lookup and exhausts its heartbeats.  The refusal is structural and needs
  -- no evaluation at all.
  unfold compcertRunReceiptCheck
  rw [h]

/-- A receipt whose enclave did **not** match its pinned expectation is
refused, however well signed it is and whoever signed it. -/
theorem compcertRunReceiptCheck_eq_false_of_mismatch
    (r : CompCertRunReceipt) (spec : CompCertRunSpec)
    (hm : r.matchedPinnedExpectation ≠ "1") :
    compcertRunReceiptCheck r spec = false := by
  unfold compcertRunReceiptCheck
  cases hlookup : lookupCompCertEnclavePin r.appId with
  | none => rfl
  | some pin =>
      have : r.specCheck spec = false := by
        simp only [CompCertRunReceipt.specCheck, Bool.and_eq_false_iff,
          beq_eq_false_iff_ne]
        exact Or.inr hm
      simp only [this, Bool.and_false, Bool.false_and]

end SparkInterval.Execution
