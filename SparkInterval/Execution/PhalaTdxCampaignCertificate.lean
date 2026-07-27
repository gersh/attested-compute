/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxAttestation

/-!
# Generic registered-campaign layer for Phala/dstack Intel TDX receipts

This is the TDX counterpart of
`SparkInterval/Execution/RegisteredCampaignCertificate.lean`: the shape is
stated once here, so a campaign on this path is *data* -- an enclave pin, a
closed registered invocation, and an expected output -- rather than a proof.
A new campaign costs one `def` for the check and one `theorem` whose body is
a single application of `certifyPhalaTdxSourceRun`.

## The one new axiom

`phalaTdxAttestedRun_sound` is this path's entire trust boundary.  It is a
*separate* axiom from `accepted_run_certificate_sound`, so `#print axioms`
distinguishes an Azure-discharged campaign from a TDX-discharged one, and so
that admitting TDX evidence cannot silently widen what the existing Azure
axiom is asserting.

It is deliberately **not** reachable from `ternary_goldbach` or from any
existing capstone: no module that a capstone imports imports this one.  See
`tests/test_phala_tdx_axiom_off_cone.py`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- **The Phala/dstack Intel TDX execution boundary.**

If a receipt passes `phalaTdxOutcomeCheck` against an enclave identity that
the project has reviewed as carrying attestation authority, then the closed
registered invocation really ran and really returned the receipt's exact
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
   retained quote with the pinned policy and it accepted: the measurement
   matched, the TCB level was current, and the QE identity was valid.  Lean
   verifies only that the retained appraisal's SHA-256 is the one committed
   in the signed statement; it does not parse quotes, PCK certificate chains,
   TCB levels, or QE identities, and it must not be read as having done so.
5. **The image really computes the campaign.**  The measured image is the one
   built from `proof_build/ch25_a7_phala_tdx/`, whose entry point runs the
   registered producer and signs its output.

### What this does *not* assume

It does **not** trust Phala the company for the correctness of the
arithmetic.  Phala schedules and hosts the CVM; if Phala substituted a
different image, the measurement in the quote would differ and the external
`dcap-qvl` appraisal against the pinned policy would fail.  What Phala *can*
do is refuse to run the job, or run it and withhold the result -- availability,
not soundness.

It also does not assume anything about the confidentiality of the campaign
input or output; this path is used for integrity only.

### Residual exposure

A break in Intel TDX, a dstack key-derivation flaw, an error in the pinned
`dcap-qvl` appraisal, or a mistaken pin literal would each invalidate this
axiom.  That is a strictly larger and differently-rooted trust surface than
the Azure SEV-SNP/MAA path, which is why it is a separate axiom that no
existing capstone reaches. -/
axiom phalaTdxAttestedRun_sound
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (authority : enclave.pin.attestationAuthority = true)
    (accepted : phalaTdxOutcomeCheck enclave invocation receipt = true) :
    invocation.Runs receipt.result

/-- Generic fail-closed production application check: the receipt is accepted
against the pinned enclave and the closed invocation, and the signed result is
exactly `expected`. -/
def phalaTdxProductionCheck (enclave : PhalaTdxEnclave)
    (invocation : RegisteredInvocation) (receipt : PhalaTdxReceipt)
    (expected : String) : Bool :=
  phalaTdxOutcomeCheck enclave invocation receipt &&
    receipt.result == expected

/-- The conclusions shared by every exact-output TDX campaign, stated once. -/
structure PhalaTdxCertifiedRun (invocation : RegisteredInvocation)
    (receipt : PhalaTdxReceipt) (expected : String) : Prop where
  result_eq : receipt.result = expected
  run : invocation.Runs expected

/-- A complete campaign in one declaration: the shared conclusions plus the
campaign's own source proposition. -/
structure PhalaTdxCertifiedSourceRun (invocation : RegisteredInvocation)
    (receipt : PhalaTdxReceipt) (expected : String) (claim : Prop) : Prop
    extends PhalaTdxCertifiedRun invocation receipt expected where
  sourceClaim : claim

/-- The generic soundness theorem, proved once.

Its only project axiom is `phalaTdxAttestedRun_sound`. -/
theorem certifyPhalaTdxRun {enclave : PhalaTdxEnclave}
    {invocation : RegisteredInvocation} {receipt : PhalaTdxReceipt}
    {expected : String}
    (authority : enclave.pin.attestationAuthority = true)
    (hcheck : phalaTdxProductionCheck enclave invocation receipt expected
      = true) :
    PhalaTdxCertifiedRun invocation receipt expected := by
  simp only [phalaTdxProductionCheck, Bool.and_eq_true] at hcheck
  have hresult : receipt.result = expected := by simpa using hcheck.2
  have hrun := phalaTdxAttestedRun_sound authority hcheck.1
  rw [hresult] at hrun
  exact { result_eq := hresult, run := hrun }

/-- Declarative source campaign: supply the registered success reduction and
the checked receipt, and get the complete campaign conclusion.  No proof
obligation is created at the campaign site.

Its only project axiom is `phalaTdxAttestedRun_sound`. -/
theorem certifyPhalaTdxSourceRun {enclave : PhalaTdxEnclave}
    {invocation : RegisteredInvocation} {receipt : PhalaTdxReceipt}
    {expected : String} {claim : Prop}
    (reduce : ∀ {output : String}, invocation.Runs output → output = expected →
      claim)
    (authority : enclave.pin.attestationAuthority = true)
    (hcheck : phalaTdxProductionCheck enclave invocation receipt expected
      = true) :
    PhalaTdxCertifiedSourceRun invocation receipt expected claim :=
  let run := certifyPhalaTdxRun authority hcheck
  { run with sourceClaim := reduce run.run rfl }

namespace PhalaTdxCertifiedRun

variable {invocation : RegisteredInvocation} {receipt : PhalaTdxReceipt}
  {expected : String}

/-- Apply any registered success reduction whose conclusion does not mention
the returned output.  This is the single line a source-claim campaign needs. -/
theorem claim (certified : PhalaTdxCertifiedRun invocation receipt expected)
    {P : Prop}
    (reduce : ∀ {output : String}, invocation.Runs output → output = expected →
      P) : P :=
  reduce certified.run rfl

end PhalaTdxCertifiedRun

end SparkInterval.Execution
