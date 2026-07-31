/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxAttestation

/-!
# The purely operational Phala/dstack Intel TDX execution boundary

An Intel TDX quote is evidence about *the world*: a measured binary ran inside
an isolated TD on a particular input and terminated having emitted particular
bytes.  It is not evidence about mathematics.  A quote cannot witness the
existence of a Lean `Certificate`, cannot evaluate `riemannZeta`, and cannot
know what `Certificate.check` is.

This module states exactly that operational fact and nothing else.  It is the
replacement for `phalaTdxAttestedRun_sound` (in
`Execution/PhalaTdxCampaignCertificate.lean`), whose conclusion
`invocation.Runs receipt.result` unfolds, for the CH25 A.7 invocation, to a
Lean-level existential over certificates *and* an analytic statement about
Mathlib's zeta function.  Attestation hardware cannot establish either.

## Why the conclusion is an `opaque` relation

`PhalaTdxAttestedEmission` is declared `opaque` and is given no introduction
rule other than the axiom below and no elimination rule at all.  That is the
mechanical enforcement of "no mathematical proposition appears in the
conclusion": there is no way to derive any statement about `ℂ`, about
`riemannZeta`, or about any `Certificate` from a term of this type.  A
campaign that wants mathematics out of an attested emission must say so, in
its own statement, as a separate named premise -- which is exactly what
`Execution/PhalaTdxA7BoundaryCertificate.lean` now does.

Consequently this axiom is **strictly weaker** than `phalaTdxAttestedRun_sound`:
under the intended reading of `PhalaTdxAttestedEmission` (the emission really
happened) the old axiom implies this one, and this one implies no mathematics
whatsoever.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- **An operational emission fact, and nothing more.**

`PhalaTdxAttestedEmission imageDigest algorithmHash inputHash parametersHash
domainHash output` is to be read as:

> the program contained in the OCI image `imageDigest`, which the project has
> reviewed as the implementation of the registered algorithm whose source text
> hashes to `algorithmHash`, was executed inside an Intel TDX trust domain on
> the input whose SHA-256 is `inputHash` under the parameters and domain whose
> SHA-256s are `parametersHash` and `domainHash`, ran to completion, and
> emitted exactly the bytes `output`.

All six arguments are `String`s.  The relation is `opaque`: Lean is given no
way to compute with it, case on it, or extract anything from it.  That is
intentional and load-bearing.  It is the whole content of what a hardware
attestation can support, and nothing in the Lean development may quietly
assume more. -/
opaque PhalaTdxAttestedEmission
    (imageDigest algorithmHash inputHash parametersHash domainHash
      output : String) : Prop

/-- **The Phala/dstack Intel TDX operational boundary.**

If a receipt passes `phalaTdxOutcomeCheck` against an enclave identity that
the project has reviewed as carrying attestation authority, then the pinned
image really ran on the pinned input and really emitted the receipt's exact
result bytes.

### What this assumes

1. **Intel TDX hardware root of trust.**  The TD is measured and isolated by
   the CPU, its quote is signed by an Intel-rooted attestation key, and the
   host, hypervisor, and cloud operator cannot read or alter the TD's memory
   or forge its quote.
2. **The dstack runtime.**  dstack launched the pinned image inside that TD,
   measured the app-compose document into the quote, and derived the P-256
   signing key inside the TD such that the key never leaves it.
3. **The pinned enclave identity.**  `PhalaTdxEnclave.pin` names the real
   dstack-derived public key, application id, app-compose hash, image digest,
   and `dcap-qvl` policy/binary for that deployment.  Installing those
   literals is a source-review event of the same weight as editing the Azure
   receipt registry.
4. **The external `dcap-qvl` appraisal.**  Someone ran `dcap-qvl` on the
   retained quote with the pinned policy and it accepted.  Lean verifies only
   that the retained appraisal's SHA-256 is the one committed in the signed
   statement.  It does **not** parse PCK certificate chains, TCB levels, or QE
   identities, and must not be read as having done so: the Intel signature
   over the quote is appraised outside Lean and stays a pin.

   Assumption 4 is **unchanged** by the build gate described next.  The gate
   moved the chain check from "someone did it once" to "the build refuses to
   pass without it"; it did not move it into the kernel.

### The Intel chain is checked, but outside the kernel

`lake exe sparkinterval-check-tdx-chain` (see
`Execution/TdxChainGateCLI.lean`, wired into `tools/audit_axioms.sh` and
`.github/workflows/build-provenance.yml`) walks every retained quote's own
ECDSA-P256 signature chain -- attestation key over `header ‖ TD report`, QE
report data binding that key, PCK leaf over the QE report, leaf →
intermediate → root, root self-signed, root fingerprint equal to the Intel
SGX Root CA pinned at `tools/intel_sgx_root_ca.pem`.  That establishes the
link this axiom's assumption 1 needs: the key that signed the quote belongs
to a genuine Intel-rooted TDX platform.

It establishes it **in Python, in a subprocess, at build time**.  No proof
term in this development mentions a PCK certificate, and none may be written
as though one did.  The gate also says nothing about TCB freshness, QE
identity, or revocation, which need Intel's live collateral and remain
`dcap-qvl`'s job.  Its offline mode is deterministic and never touches the
network; confirming that the pinned PEM still matches Intel's published root
is a separate `--live` mode for CI.

### How this assumption narrowed when the quote parser landed

Assumption 3 used to have to carry two further things that are now checked.
`phalaTdxOutcomeCheck` calls `phalaTdxQuoteCheck`
(`Execution/PhalaTdxAttestation.lean`), which reads the retained quote bytes
with `Execution/TdxQuoteV4.lean` and requires, by kernel-reducible
computation:

* that the bytes are a v4 quote from an Intel TDX platform and are long
  enough to contain a TD report body;
* that the quote's own `mrconfigid` is `01 ‖ composeHash ‖ 0…0` for the
  **pinned** app-compose hash -- so "the CPU measured the reviewed
  configuration" is now a parsed fact rather than a receipt field;
* that the quote's own report data is the SHA-256, **recomputed from the
  pinned public key and this run's challenge and job binding**, with the upper
  32 bytes zero -- so "the enclave committed to the pinned key in the quote"
  is now a parsed fact rather than a receipt field; and
* that the SHA-256 of those exact quote bytes is the `tdx_quote_sha256` the
  enclave signed -- so a genuine receipt cannot be presented alongside an
  unrelated genuine quote.

Before that, `reportDataHash` and `composeHash` were fields of the receipt.
Lean checked the first against a computed commitment and the second against
the pin, but had no way to tell whether the *quote* contained either.  A
receipt assembler who put the right strings in the receipt and any bytes at
all in the quote file satisfied the old check.

The axiom's statement is unchanged; its premise is strictly stronger, so what
it assumes about the world is strictly smaller.  Concretely, three former
failure modes are now build failures instead: a quote from a differently
measured app-compose document, a quote whose report data does not commit to
the pinned key, and a quote unrelated to the one whose digest was signed.
`Certificate/SHA256Vectors.lean` checks the SHA-256 that does this work
against the FIPS 180-4 vectors, and
`Tests/PhalaTdxSegEvidenceTest.lean` closes the whole
statement-to-digest-to-report-data-to-quote chain on real retained evidence
with `rfl` alone.

### What this deliberately does *not* assume

It does **not** assume that the image computes anything in particular, that
its output means anything, or that any mathematical proposition holds.  The
image identity appears in the conclusion purely as a string; connecting that
string to a decision procedure is a separate, separately named, separately
reviewed premise at each campaign site.

### What would falsify it

A break in Intel TDX; a dstack key-derivation flaw that lets a key escape the
TD or lets a non-TD party obtain it; an error in the pinned `dcap-qvl`
appraisal; a mistaken pin literal that names an image, app id, or key other
than the deployed one; or a SHA-256 / P-256 break that lets a receipt be
forged or a different result be bound to a genuine signature. -/
axiom phalaTdxAttestedEmission_sound
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (authority : enclave.pin.attestationAuthority = true)
    (accepted : phalaTdxOutcomeCheck enclave invocation receipt = true) :
    PhalaTdxAttestedEmission enclave.pin.imageDigest
      invocation.algorithm.algorithmHash
      invocation.canonicalInputHash
      invocation.algorithm.canonicalParametersHash
      invocation.algorithm.canonicalDomainHash
      receipt.result

/-- Convenience form: an accepted receipt whose result is exactly `expected`
attests the emission of `expected`.

Axioms: the base trio plus `phalaTdxAttestedEmission_sound`. -/
theorem phalaTdxAttestedEmission_of_productionOutcome
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt} {expected : String}
    (authority : enclave.pin.attestationAuthority = true)
    (accepted : phalaTdxOutcomeCheck enclave invocation receipt = true)
    (result : receipt.result = expected) :
    PhalaTdxAttestedEmission enclave.pin.imageDigest
      invocation.algorithm.algorithmHash
      invocation.canonicalInputHash
      invocation.algorithm.canonicalParametersHash
      invocation.algorithm.canonicalDomainHash
      expected :=
  result ▸ phalaTdxAttestedEmission_sound authority accepted

end SparkInterval.Execution
