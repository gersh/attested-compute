/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxProd5Evidence
import SparkInterval.Execution.PhalaTdxA7BoundaryCertificate

/-!
# The first real Intel TDX receipt, driven through the Lean checks

Everything on the Phala path had been exercised against fixtures: a committed
stand-in signing key, placeholder quote digests, and an enclave identity with
`attestationAuthority := false`.  This module does the thing that had never
been done -- it takes the receipt a genuine dstack-derived enclave signed
inside a genuine Intel TDX trust domain and asks Lean's own checks about it.

The run: **Phala Cloud prod5, CVM `a7-e2e`, 2026-07-27T21:48:16Z**, dstack app
`8428181231415b81042d93de854c0d82b1dab95b`.  Its retained evidence is
committed at `tests/data/phala_tdx_prod5/`; the pin and receipt literals are
machine-derived from it by `tools/tg_phala_tdx_pin_from_evidence.py` into
`Execution/PhalaTdxProd5Evidence.lean`, which proves by `decide` that the
hand-written pin case agrees.

## What is established here

* `prod5Signature_kernelChecked` -- **the Lean kernel itself** runs the ECDSA
  P-256 verifier of `SparkInterval/Certificate/P256.lean` on the enclave's
  real signature over the real statement digest, and it verifies.  Base trio
  only: no `native_decide`, no `ofReduceBool`.
* `prod5OutcomeAccepted` -- the complete fail-closed acceptance check
  `phalaTdxOutcomeCheck` returns `true`: the signature verifies against the
  source-pinned key, the signed statement names the exact closed registered
  invocation, the result `true` is bound to its digest and is in the
  invocation's result language, every deployment coordinate is the pinned one,
  and the SHA-256 the enclave put in the TDX quote's report data is the
  domain-separated commitment to the pinned key, this campaign's challenge and
  this job's binding.
* `prod5Campaign` -- the campaign conclusion with the `authority` premise
  **discharged** rather than assumed.  On the dry-run path that premise was
  the one thing a laptop could not supply; a real Phala run is exactly what
  supplies it.  Two premises remain, and neither is about attestation:
  enclave/reference-model agreement, and the FLINT/Arb-to-Mathlib realization.

## What is established by refusal

A verifier that accepts everything would satisfy the paragraph above too.  So
every tamper case below is closed as a theorem, not as a comment.  Five are
closed by the kernel.  Three are rejected by the P-256 verifier itself:

* (a) an altered enclave public key -- the altered point is not on the curve,
  so `isValidPublicKey` refuses it before any scalar multiplication;
* (b) an altered signature;
* (c) an altered statement, via `issuedAt`, the one signed field that no check
  other than the signature itself inspects -- so the signature is the only
  thing that *can* reject it.

Two are rejected by `phalaTdxOutcomeCheck` inside the kernel, in
`phalaTdxPinCheck`, before any hashing happens:

* (d) an altered app-compose hash -- a different measured code base;
* (e) an altered app id.

Each of (a), (b), (c) is *also* stated at the level of the whole
`phalaTdxOutcomeCheck`, where the reduction is too large for the kernel and
`native_decide` is used; so is the same receipt presented under a different
pinned identity.  Case (a) is worth a note: at outcome level it is refused by
the report-data commitment (a digest *of the pinned key*) before the signature
check is even reached, which is why the P-256-level statement matters.

## `attestationAuthority` is not an input to `phalaTdxOutcomeCheck`

Worth stating plainly, because it is easy to expect otherwise:
`phalaTdxOutcomeCheck` does **not** read `attestationAuthority`, so setting it
to `false` does not make that function return `false`.  Authority is enforced
one level up, as the `authority : enclave.pin.attestationAuthority = true`
premise of `phalaTdxAttestedEmission_sound`, and it is unsatisfiable by
`rfl`/`decide` for an identity that does not carry it.  Both halves are
recorded below: `prod5NoAuthority_blocks_dryRunEnclave` shows the dry-run
identity has no authority, and `prod5DryRunEnclave_rejects` shows that the
same real receipt is refused outright under a different pinned key anyway.

## The `native_decide` disclosure

`prod5Signature_kernelChecked` and the three P-256 refusals are the genuinely
new cryptography and they are **kernel-checked**.  The composite
`phalaTdxOutcomeCheck` statements are not, and that is a disclosed trade.

`phalaTdxOutcomeCheck` performs nineteen SHA-256 evaluations over strings (the
canonical payload plus its eighteen committed fields) before it reaches the
curve arithmetic.  Reducing those in the Lean kernel is *possible* -- measured
on this 20-core, 119 GB host with `lake env lean -j1 -M110000`, `decide
+kernel` closes `receipt.statementDigest = <literal>` in **126 s at 34 GB**
resident, and the report-data commitment alone needs a little over **8 GB** --
but this repository builds its Lean libraries under
`weakLeanArgs = ["-j1", "-M8192"]`, an 8 GB ceiling.  A 34 GB declaration
would not build.  So the composite statements are closed with `native_decide`.
This is the same choice, for the same reason, that `dryRunAccepted` in
`SparkInterval/Tests/PhalaTdxDryRunTest.lean` already makes.

On Lean 4.32 a `native_decide` proof no longer routes through
`Lean.ofReduceBool`.  Each such declaration instead gets its own named axiom,
`<theorem>._native.native_decide.ax_1_1`, whose statement is literally
`decide (<the proposition>) = true` -- so `#print axioms` names the compiled
evaluator's verdict on *this* proposition rather than a shared constant.  The
force is the same: the Lean compiler and runtime, rather than the kernel,
computed that boolean.  Six declarations below carry such an axiom, and they
are exactly the six that mention `native_decide`.

### The seam this leaves, stated exactly

`prod5Signature_kernelChecked` verifies the enclave's signature over
`PhalaTdxProd5.statementDigest`, a *literal*.  That the literal really is
`receipt.statementDigest` -- the SHA-256 of the canonical payload built from
the eighteen signed fields -- is checked here by `#guard` (evaluated, no proof
term) and inside `prod5OutcomeAccepted` (`native_decide`), but not by the
kernel, for the memory reason above.  So the kernel-checked statement is
precisely: *this key signed this digest*.  Tying that digest to those fields
by kernel reduction is done out of band, by
`proof_build/ch25_a7_phala_tdx/prod5_kernel_full_check.lean`, which closes the
whole of `phalaTdxOutcomeCheck` -- statement digest, report-data commitment and
ECDSA together -- with `decide +kernel` and no `native_decide` at all.  **That
run has been done**: 1209 s, 42.9 GB peak resident, `#print axioms` reporting
`[propext, Classical.choice, Quot.sound]` and nothing else.  So the
`native_decide` below is a build-budget concession, not an unverified claim:
the same proposition has been reduced by the kernel.  That file is not part of
any `lean_lib`; run it deliberately.

Nothing in `SparkInterval/Certificate/P256.lean`,
`Execution/PhalaTdxAttestation.lean`, `Execution/PhalaTdxProd5Evidence.lean`,
`Execution/PhalaTdxOperationalAttestation.lean` or
`Execution/PhalaTdxCampaignCertificate.lean` uses `native_decide`; the
addition is confined to this test module, and the P-256 verification -- the
one step where a wrong answer would mean a forged enclave signature was
accepted -- does not use it.
-/

set_option autoImplicit false
set_option maxRecDepth 40000
set_option maxHeartbeats 4000000

namespace SparkInterval.Tests.PhalaTdxProd5

open SparkInterval.Execution
open SparkInterval.Execution.PhalaTdxProd5 (receipt)

/-- The reviewed enclave identity for this run. -/
abbrev enclave : PhalaTdxEnclave := .ch25A7BoundaryPhalaProd5V1

/-- The closed registered invocation the signed statement names. -/
abbrev invocation : RegisteredInvocation := .ch25A7BoundaryProductionV1

/-! ## Evaluated, before anything is proved

`#guard` runs the compiled evaluator at elaboration time.  It builds no proof
term and introduces no axiom. -/

-- Lean's canonical payload reproduces the enclave's, byte for byte.
#guard receipt.statementDigest == PhalaTdxProd5.statementDigest

-- The enclave's real P-256 signature verifies against the pinned key.
#guard phalaTdxSignatureCheck enclave receipt

-- Deployment coordinates and the quote report-data commitment match.
#guard phalaTdxPinCheck enclave receipt

-- The signed statement names the exact closed registered invocation.
#guard phalaTdxInvocationCheck invocation receipt

-- The complete acceptance check, and the campaign's production shape.
#guard phalaTdxOutcomeCheck enclave invocation receipt
#guard phalaTdxProductionCheck enclave invocation receipt "true"
#guard ch25A7BoundaryPhalaTdxCheck receipt == false  -- still-empty prod pin

-- The pinned identity carries attestation authority; the fixtures do not.
#guard enclave.pin.attestationAuthority
#guard !(PhalaTdxEnclave.ch25A7BoundaryPhalaProd5TamperedKeyV1.pin).attestationAuthority
#guard !PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1.pin.attestationAuthority

/-! ## The new cryptography, checked by the Lean kernel

This is the decisive test of `SparkInterval/Certificate/P256.lean`: not a NIST
CAVP vector and not a locally generated stand-in, but the signature a
dstack-derived key produced inside an Intel TDX trust domain, over the digest
of the statement that enclave actually signed.  Axioms: the base trio. -/

/-- **The real enclave signature verifies inside the Lean kernel.** -/
theorem prod5Signature_kernelChecked :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxProd5.enclavePublicKeyHex PhalaTdxProd5.statementDigest
      PhalaTdxProd5.signatureHex = true := by
  decide +kernel

/-- Negative (a), kernel-checked: **one character of the enclave public key
altered** and the verifier refuses.  The altered point is not on the curve, so
`isValidPublicKey` rejects it before any scalar multiplication. -/
theorem prod5Signature_rejectsAlteredKey :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxProd5.tamperedPublicKeyHex PhalaTdxProd5.statementDigest
      PhalaTdxProd5.signatureHex = false := by
  decide +kernel

/-- Negative (b), kernel-checked: **one character of the signature
altered** and the verifier refuses. -/
theorem prod5Signature_rejectsAlteredSignature :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxProd5.enclavePublicKeyHex PhalaTdxProd5.statementDigest
      PhalaTdxProd5.tamperedSignatureHex = false := by
  decide +kernel

/-- Negative (c), kernel-checked: **the statement digest altered** and the
verifier refuses.  `tamperedStatementDigest` is the digest of the same receipt
with only `issuedAt` changed, so nothing but the signature could reject it. -/
theorem prod5Signature_rejectsAlteredStatement :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxProd5.enclavePublicKeyHex PhalaTdxProd5.tamperedStatementDigest
      PhalaTdxProd5.signatureHex = false := by
  decide +kernel

/-! ## Deployment-coordinate refusals, checked by the Lean kernel

These reject inside `phalaTdxPinCheck`, before any SHA-256 or curve
arithmetic, so the kernel closes them cheaply. -/

/-- Negative (d), kernel-checked: **the app-compose hash altered** -- a
different measured code base -- and the whole check fails. -/
theorem prod5Outcome_rejectsAlteredComposeHash :
    phalaTdxOutcomeCheck enclave invocation
      { receipt with composeHash := PhalaTdxProd5.tamperedComposeHash }
      = false := by
  decide +kernel

/-- Negative (e), kernel-checked: **the app id altered** and the whole check
fails. -/
theorem prod5Outcome_rejectsAlteredAppId :
    phalaTdxOutcomeCheck enclave invocation
      { receipt with appId := PhalaTdxProd5.tamperedAppId } = false := by
  decide +kernel

/-! ## The composite check

From here on, `native_decide`; see the disclosure in the module docstring.
Each of these declarations, and everything downstream of it, carries its own
`._native.native_decide.ax_1_1` axiom. -/

/-- **The decisive positive.**  The complete fail-closed acceptance check
returns `true` on the real receipt from real Intel TDX hardware.

Adds `prod5OutcomeAccepted._native.native_decide.ax_1_1`; the P-256 half of
this check is separately kernel-checked by `prod5Signature_kernelChecked`
above. -/
theorem prod5OutcomeAccepted :
    phalaTdxOutcomeCheck enclave invocation receipt = true := by
  native_decide

/-- The campaign's production shape, at the reviewed prod5 identity.
Adds `prod5ProductionAccepted._native.native_decide.ax_1_1`. -/
theorem prod5ProductionAccepted :
    phalaTdxProductionCheck enclave invocation receipt "true" = true := by
  native_decide

/-- Negative (a) again, this time at the level of `phalaTdxOutcomeCheck`
rather than of the P-256 primitive: **the enclave public key altered by one
character**.

Two independent guards refuse it, and the first one reached is not the
signature: the quote's report-data commitment is a digest *of the pinned key*,
so a key that is off by one character no longer matches what the TDX quote
attests.  `prod5Signature_rejectsAlteredKey` covers the cryptographic half in
the kernel.  Adds a `native_decide` axiom. -/
theorem prod5Outcome_rejectsAlteredKey :
    phalaTdxOutcomeCheck .ch25A7BoundaryPhalaProd5TamperedKeyV1 invocation
      receipt = false := by
  native_decide

/-- The altered signature, at the level of `phalaTdxOutcomeCheck`.
Adds a `native_decide` axiom. -/
theorem prod5Outcome_rejectsAlteredSignature :
    phalaTdxOutcomeCheck enclave invocation
      { receipt with signatureHex := PhalaTdxProd5.tamperedSignatureHex }
      = false := by
  native_decide

/-- The altered statement, at the level of `phalaTdxOutcomeCheck`: only
`issuedAt` differs, so only the signature can and does refuse it.
Adds a `native_decide` axiom. -/
theorem prod5Outcome_rejectsAlteredStatement :
    phalaTdxOutcomeCheck enclave invocation
      { receipt with issuedAt := PhalaTdxProd5.tamperedIssuedAt } = false := by
  native_decide

/-- The genuine receipt under a different reviewed identity is refused: the
pinned key is not the one that signed it, and the report-data commitment is
not the one the quote attests.  Adds a `native_decide` axiom. -/
theorem prod5DryRunEnclave_rejects :
    phalaTdxOutcomeCheck .ch25A7BoundaryLocalDryRunV1 invocation receipt
      = false := by
  native_decide

/-- And the still-unpinned older production identity refuses it too, exactly
as `phalaTdxOutcomeCheck_ch25A7BoundaryProductionV1_eq_false` promises.
Axioms: the base trio. -/
theorem prod5ProductionV1Enclave_rejects :
    phalaTdxOutcomeCheck .ch25A7BoundaryProductionV1 invocation receipt
      = false :=
  phalaTdxOutcomeCheck_ch25A7BoundaryProductionV1_eq_false _ _

/-! ## Authority

`phalaTdxOutcomeCheck` never reads `attestationAuthority`; the flag gates the
axiom, not the check.  These two record both sides of that. -/

/-- The prod5 identity carries attestation authority.  This is the premise the
dry run could not supply, and it is now closed by `rfl`. -/
theorem prod5_authority : enclave.pin.attestationAuthority = true := rfl

/-- The dry-run identity still cannot satisfy the axiom's premise, so nothing
signed by the committed stand-in key can reach a campaign conclusion. -/
theorem prod5NoAuthority_blocks_dryRunEnclave :
    PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1.pin.attestationAuthority
      = false := rfl

/-- Nor can the tampered-key negative-test fixture. -/
theorem prod5NoAuthority_blocks_negativeTestEnclave :
    (PhalaTdxEnclave.ch25A7BoundaryPhalaProd5TamperedKeyV1.pin).attestationAuthority
      = false := rfl

/-! ## The campaign conclusion, one attestation premise lighter -/

/-- **The end-to-end reduction, with the attestation premise discharged.**

Compare `dryRunCampaignFromModel` in
`SparkInterval/Tests/PhalaTdxDryRunTest.lean`: it needs three hypotheses, of
which `authority` was unsatisfiable for a laptop key.  Here `authority` is
supplied by the reviewed prod5 pin, so only the two non-attestation premises
remain:

* `model` -- the pinned image decides the same predicate as the Lean reference
  model `A7BoundaryWireEvidence.modelOutput`.  About bytes; dischargeable by
  computation once the retained artifact is available to Lean.
* `realization` -- the recorded FLINT/Arb boxes really enclose Mathlib's
  `riemannZeta` and `rawG`.  The honest analytic remainder of the A.7 atom;
  no attestation and no byte-level checker can supply it.

Axioms: the base trio, `phalaTdxAttestedEmission_sound` (the purely
operational Intel TDX boundary), and
`prod5ProductionAccepted._native.native_decide.ax_1_1`. -/
theorem prod5Campaign
    (model : EnclaveImplementsA7ReferenceModel .ch25A7BoundaryPhalaProd5V1)
    (realization :
      SparkInterval.TernaryGoldbach.A7BoundaryWireEvidence.RetainedAnalyticRealization) :
    PhalaTdxCertifiedSourceRun .ch25A7BoundaryProductionV1 receipt "true"
      SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim :=
  certifyCH25A7BoundaryPhalaTdxFromModelAt prod5_authority
    prod5ProductionAccepted model realization

/-! ## Axioms -/

#print axioms prod5Signature_kernelChecked
#print axioms prod5Signature_rejectsAlteredKey
#print axioms prod5Signature_rejectsAlteredSignature
#print axioms prod5Signature_rejectsAlteredStatement
#print axioms prod5Outcome_rejectsAlteredComposeHash
#print axioms prod5Outcome_rejectsAlteredAppId
#print axioms prod5OutcomeAccepted
#print axioms prod5ProductionAccepted
#print axioms prod5Outcome_rejectsAlteredKey
#print axioms prod5Outcome_rejectsAlteredSignature
#print axioms prod5Outcome_rejectsAlteredStatement
#print axioms prod5DryRunEnclave_rejects
#print axioms prod5ProductionV1Enclave_rejects
#print axioms prod5_authority
#print axioms prod5Campaign
#print axioms certifyCH25A7BoundaryPhalaTdxFromModelAt
#print axioms certifyCH25A7BoundaryPhalaTdxFromModel
#print axioms phalaTdxProd5_pin_eq_generated
#print axioms phalaTdxProd5_has_attestationAuthority

end SparkInterval.Tests.PhalaTdxProd5
