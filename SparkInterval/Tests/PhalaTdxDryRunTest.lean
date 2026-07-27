/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxA7BoundaryCertificate

/-!
# Local end-to-end dry run of the Phala/dstack TDX campaign path

The receipt literal below is the **verbatim** output of

```
docker run --platform linux/amd64 … sparkinterval-ch25-a7-phala-tdx
```

built from `proof_build/ch25_a7_phala_tdx/Dockerfile`.  Inside that container
the registered CH25 Lemma A.7 producer ran the real FLINT/Arb boundary replay,
emitted the registered result bytes `true`, and signed the canonical statement
with a P-256 key supplied to the container.  `tests/test_phala_tdx_first_run.py`
regenerates the run and checks that these literals still agree.

**Nothing here was attested.**  The signing key is the committed stand-in in
`tests/data/phala_tdx_dry_run/`, not a dstack-derived key, and the quote and
appraisal files are labelled placeholders.  The containment is structural: the
enclave identity used below is `ch25A7BoundaryLocalDryRunV1`, whose pin has
`attestationAuthority := false`, so the trust axiom's authority premise is not
satisfiable for it.  The last `example` therefore states the campaign
conclusion *conditionally* on that premise -- which is precisely the one
ingredient a real Phala run supplies and a laptop cannot.

What the dry run does establish, by kernel evaluation, is that every other
link in the chain is closed: the P-256 signature over the container's real
canonical statement verifies against the pinned key, the statement names the
exact closed registered invocation, the result is bound to its digest and is
in the invocation's result language, the deployment coordinates match the pin,
and the quote report-data commitment matches.
-/

set_option autoImplicit false
set_option maxRecDepth 40000
set_option maxHeartbeats 4000000

namespace SparkInterval.Tests.PhalaTdxDryRun

open SparkInterval.Execution

/-- The exact receipt emitted by the container, field for field. -/
def dryRunReceipt : PhalaTdxReceipt := {
  algorithmId := "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1"
  algorithmHash :=
    "340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa"
  inputHash :=
    "4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674"
  parametersHash :=
    "f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e"
  domainHash :=
    "629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5"
  result := "true"
  outputHash :=
    "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"
  challengeNonce :=
    "1111111111111111111111111111111111111111111111111111111111111111"
  jobBindingHash :=
    "2222222222222222222222222222222222222222222222222222222222222222"
  appId := "327d84eaf0cfb23bfc4260453516a9afc0287705"
  composeHash :=
    "44c2baa7f7fbf92c08d9800071ec0d3d21404c07af1db8254ebd77c717b8e35c"
  imageDigest :=
    "sha256:43233eef77b7ad2463aa6b352a7459ffd42b0d1f8b9373858889d8f1bc0c073c"
  quoteHash :=
    "a4ff43ede0e689065ea92fc5b3257696227fedeaa38178c5b663a8adc501880b"
  quoteAppraisalHash :=
    "716f6fce4c97c5a39e47d767b4d0dd6f7b4d96fa4a46054f75e09a1186acd706"
  quoteAppraisalPolicyHash :=
    "62e29a716d65e330fcce6a137c1eed7e6db903740f490ccd2697c8b668710808"
  quoteAppraisalArtifactHash :=
    "4f5ef2ba3f386e03f21f750f76057f807cf20376d727f4013b052f5c0ab3c171"
  reportDataHash :=
    "4ee13d6ac8b16200a4c80e5238f25446af4b84a80457b7a2a949a2ca05cfe7b5"
  issuedAt := "2026-07-26T00:00:00Z"
  signatureHex :=
    "fb91a1c9d73d3dddda1e7aef19d3386c5723bdfe922885c27605eb73b4d8f9cc" ++
    "5c21648796a33a59c28f550ff375793ca6dae8aaffc6954d474fa43eaca887b6"
}

/-- The digest the container reported signing. -/
def dryRunStatementDigest : String :=
  "4fc17a0ed489d4c6cfd0e974d34ff93a92555ba4139b5b6cb4ab1f1ce510e2a6"

/-! ## Every link except attestation authority, evaluated

`#guard` runs the compiled evaluator at elaboration time.  It builds no proof
term and introduces no axiom, exactly as `SparkInterval/Tests/P256VectorTest.lean`
does for the NIST CAVP vectors. -/

-- Lean's canonical payload reproduces the container's, byte for byte.
#guard dryRunReceipt.statementDigest == dryRunStatementDigest

-- The enclave's real P-256 signature verifies against the pinned key.
#guard phalaTdxSignatureCheck .ch25A7BoundaryLocalDryRunV1 dryRunReceipt

-- Deployment coordinates and the quote report-data commitment match.
#guard phalaTdxPinCheck .ch25A7BoundaryLocalDryRunV1 dryRunReceipt

-- The signed statement names the exact closed registered invocation.
#guard phalaTdxInvocationCheck .ch25A7BoundaryProductionV1 dryRunReceipt

-- The complete acceptance check, and the campaign's production check shape
-- at the dry-run enclave.
#guard phalaTdxOutcomeCheck .ch25A7BoundaryLocalDryRunV1
  .ch25A7BoundaryProductionV1 dryRunReceipt

#guard phalaTdxProductionCheck .ch25A7BoundaryLocalDryRunV1
  .ch25A7BoundaryProductionV1 dryRunReceipt "true"

/-! ## Tamper cases are rejected -/

-- Flipping one hexadecimal digit of the signature breaks verification.
#guard !phalaTdxSignatureCheck .ch25A7BoundaryLocalDryRunV1
  { dryRunReceipt with
    signatureHex :=
      "fb91a1c9d73d3dddda1e7aef19d3386c5723bdfe922885c27605eb73b4d8f9cc" ++
      "5c21648796a33a59c28f550ff375793ca6dae8aaffc6954d474fa43eaca887b7" }

-- Changing the signed result invalidates the signature.
#guard !phalaTdxSignatureCheck .ch25A7BoundaryLocalDryRunV1
  { dryRunReceipt with result := "false" }

-- The same receipt under the production enclave identity is rejected: its
-- public key is not pinned yet.
#guard !phalaTdxOutcomeCheck .ch25A7BoundaryProductionV1
  .ch25A7BoundaryProductionV1 dryRunReceipt

-- And it is rejected against a different closed invocation.
#guard !phalaTdxInvocationCheck .plattHead2e4ProductionV1 dryRunReceipt

/-! ## The new cryptography, checked by the Lean kernel

The one genuinely new verification on this path is the P-256 signature.  It is
closed here by `decide +kernel`, so it adds no axiom beyond the base trio:
the container's real signature over the real statement digest verifies against
the pinned key, inside the kernel.  Measured at about 6.6 s wall and well
inside a 16 GB budget on this machine, consistent with the timings recorded in
`SparkInterval/Certificate/P256.lean`. -/

/-- The pinned dry-run enclave key, spelled out so the kernel check below does
no string reduction of its own. -/
def dryRunPinnedKey : String :=
  "04f13d15d34f4c77b7482a2deab601e317c284631899a83b15985d5f9c831bc6" ++
  "be15fade17cf66c016ec35c28adf8c79bb5320400c88f6c979e00ebc85ee13f902"

-- The literal is the pin.
#guard dryRunPinnedKey ==
  PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1.pin.enclavePublicKeyHex

/-- Kernel-checked ECDSA verification of the container's real signature.
Axioms: the base trio only. -/
theorem dryRunSignature_kernelChecked :
    SparkInterval.Certificate.P256.verifyDigestHex dryRunPinnedKey
      dryRunStatementDigest dryRunReceipt.signatureHex = true := by
  decide +kernel

/-! ## The final link, stated conditionally

This is the whole chain: from the container's real signed receipt to the
literal CH25 Lemma A.7 source claim.  Its single open hypothesis is that the
signing key carries Intel TDX attestation authority -- which for this stand-in
key is `false`, and which a real Phala run is exactly what supplies.

The composite check is closed with `native_decide` rather than `decide`.  That
is a deliberate, disclosed trade: the check performs nineteen SHA-256
evaluations over strings (the canonical payload, its seventeen committed
fields, and the invocation's source-binding diagnostics), and reducing those
in the kernel exceeded a 16 GB budget on this machine, while the P-256 part
alone did not.  Consequently `dryRunAccepted` and everything downstream of it
carry `Lean.ofReduceBool`.  Nothing in
`SparkInterval/Certificate/P256.lean`, `Execution/PhalaTdxAttestation.lean`, or
`Execution/PhalaTdxCampaignCertificate.lean` uses `native_decide`; the addition
is confined to this test module. -/

/-- The container's receipt satisfies the complete campaign check at the
dry-run enclave.  Adds `Lean.ofReduceBool`; see the note above. -/
theorem dryRunAccepted :
    phalaTdxProductionCheck .ch25A7BoundaryLocalDryRunV1
      .ch25A7BoundaryProductionV1 dryRunReceipt "true" = true := by
  native_decide

/-- **Legacy path.**  The complete campaign conclusion, one hypothesis away,
via `phalaTdxAttestedRun_sound` -- the axiom that *asserts* this campaign's
mathematics.  Retained for comparison; see `dryRunCampaignFromModel`. -/
theorem dryRunCampaign
    (authority :
      PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1.pin.attestationAuthority
        = true) :
    PhalaTdxCertifiedSourceRun .ch25A7BoundaryProductionV1 dryRunReceipt "true"
      SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim :=
  certifyPhalaTdxSourceRun
    RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim authority
    dryRunAccepted

/-- **Supported path.**  The same conclusion from the same container receipt,
with the mathematics proved instead of assumed.

Compare the hypothesis lists.  The legacy theorem above needs one hypothesis
and an axiom that concludes `invocation.Runs`.  This one needs three
hypotheses and an axiom that concludes only that the pinned image emitted the
bytes `true`:

* `authority` -- Intel TDX attestation authority for the signing key.  `false`
  for this stand-in, exactly as before.
* `model` -- the pinned image decides the same predicate as the Lean reference
  model `A7BoundaryWireEvidence.modelOutput`.  This is the one residual
  assumption, and it is about *bytes*: it is dischargeable by computation as
  soon as the artifact bytes are available to Lean.
* `realization` -- the recorded FLINT/Arb boxes really enclose Mathlib's
  `riemannZeta` and `rawG`.  No attestation, and no byte-level checker, can
  supply this; it is the honest remainder of the A.7 atom.

Everything between those premises and `SourceClaim` -- the wire parser, the
four gap-free edge covers, the exact dyadic guards, the strict `(349/250)^2`
bound, and the final norm estimate -- is ordinary Lean. -/
theorem dryRunCampaignFromModel
    (authority :
      PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1.pin.attestationAuthority
        = true)
    (model :
      EnclaveImplementsA7ReferenceModel .ch25A7BoundaryLocalDryRunV1)
    (realization :
      SparkInterval.TernaryGoldbach.A7BoundaryWireEvidence.RetainedAnalyticRealization) :
    PhalaTdxCertifiedSourceRun .ch25A7BoundaryProductionV1 dryRunReceipt "true"
      SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim :=
  certifyCH25A7BoundaryPhalaTdxFromModelAt authority dryRunAccepted model
    realization

-- The dry-run stand-in key demonstrably has no such authority, so neither
-- `dryRunCampaign` nor `dryRunCampaignFromModel` asserts anything about the
-- world.
#guard !PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1.pin.attestationAuthority

/-! ## Axioms -/

#print axioms certifyPhalaTdxRun
#print axioms certifyPhalaTdxSourceRun
#print axioms certifyCH25A7BoundaryPhalaTdx
#print axioms certifyCH25A7BoundaryPhalaTdxFromModel
#print axioms certifyCH25A7BoundaryPhalaTdxFromModelAt
#print axioms ch25A7BoundaryRuns_of_modelOutput
#print axioms ch25A7BoundaryPhalaTdxCheck_eq_false
#print axioms dryRunSignature_kernelChecked
#print axioms dryRunAccepted
#print axioms dryRunCampaign
#print axioms dryRunCampaignFromModel

end SparkInterval.Tests.PhalaTdxDryRun
