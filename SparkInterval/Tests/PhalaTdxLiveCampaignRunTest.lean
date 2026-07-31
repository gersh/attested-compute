/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxLiveCampaignEvidence

/-!
# The per-integer leancompcert campaign's Intel TDX receipt, driven through Lean

The run this module is about is the second real Intel TDX run in this
repository, and the first whose *subject matter* is a leancompcert artifact:
ten statically linked, freestanding, CompCert-compiled x86_64 executables that
test `|Σ_{m≤n} μ(m)/m| ≤ 1/(2√(n+1))` at **every** integer `n` in
`[5, 7 727 068 586]`, chained through a two-limb accumulator at scale `2^78`.
That upper endpoint is the whole point of the campaign: the earlier windowed
campaign (`Execution/LeanCompCertSegCampaign.lean`) stopped at
`7 727 065 383`, 3 204 integers short, because a single threshold per window
plus a `⌈n/2⌉` rounding budget at scale `2^62` cannot carry the last few
thousand integers of a range whose majorant is nearly tight at its end.

## Why there is no `native_decide` in this module

`SparkInterval/Tests/PhalaTdxProd5RunTest.lean` closes the composite
`phalaTdxOutcomeCheck ... = true` with `native_decide`, because nineteen
SHA-256 reductions plus a quote hash plus ECDSA do not fit the repository's
`-M8192` build ceiling.  This module deliberately does not do that.  Every
*proved* statement below is either `rfl`/`decide` on small data or
`decide +kernel` on the P-256 verification, and the composite claim is stated
and reduced **by the kernel** out of band, in
`proof_build/leancompcert_tdx/live_campaign_kernel_check.lean`.  The `#guard`s
here are evaluated at elaboration time and build no proof term and introduce
no axiom, so they are diagnostics, not claims.

## What the acceptance check does and does not license

Even with `phalaTdxOutcomeCheck` returning `true` and this deployment carrying
`attestationAuthority`, nothing in this repository concludes the little-Mertens
bound from it.  `PhalaTdxAttestedEmission` is `opaque` and has no elimination
rule; the operational axiom concludes *bytes*, and turning those bytes into
mathematics needs the separate realisation premise that
`mobiusLiveProgram.denote` really is `Σ_{m≤n} μ(m)/m` and that a zero exit
status really means the threshold inequality.  That premise is not discharged
here and is not implied by any theorem in this file.
-/

set_option autoImplicit false
set_option maxRecDepth 40000
set_option maxHeartbeats 4000000

namespace SparkInterval.Tests.PhalaTdxLiveCampaign

open SparkInterval.Execution
open SparkInterval.Execution.PhalaTdxLiveCampaign (receipt)

/-- The reviewed enclave identity for this run. -/
abbrev enclave : PhalaTdxEnclave := .plattStrongerRangeLivePhalaV1

/-- The closed registered invocation the signed statement names. -/
abbrev invocation : RegisteredInvocation := .plattStrongerRangeLiveProductionV1

/-! ## Evaluated, before anything is proved

`#guard` runs the compiled evaluator at elaboration time.  It builds no proof
term and introduces no axiom. -/

-- Lean's canonical payload reproduces the enclave's, byte for byte.
#guard receipt.statementDigest == PhalaTdxLiveCampaign.statementDigest

-- The enclave's real P-256 signature verifies against the pinned key.
#guard phalaTdxSignatureCheck enclave receipt

-- Deployment coordinates and the quote report-data commitment match.
#guard phalaTdxPinCheck enclave receipt

-- The signed statement names the exact closed registered invocation.
#guard phalaTdxInvocationCheck invocation receipt

-- The quote parses, measures the pinned app-compose, and binds this
-- statement; and its SHA-256 is the one the enclave signed.
#guard phalaTdxQuoteCheck enclave receipt

-- The complete acceptance check.  Proved by kernel reduction in
-- `proof_build/leancompcert_tdx/live_campaign_kernel_check.lean`.
#guard phalaTdxOutcomeCheck enclave invocation receipt

-- The pinned identity carries attestation authority; the fixture does not.
#guard enclave.pin.attestationAuthority
#guard !(PhalaTdxEnclave.plattStrongerRangeLiveTamperedKeyV1.pin).attestationAuthority

/-! ## The campaign's own identity, by `rfl`

The receipt names this campaign and no other.  These are the equalities that
would break if the manifest, the artifacts, or the registered definition
changed. -/

/-- The signed `algorithm_hash` is the registered algorithm's, which is the
SHA-256 of a definition naming the campaign manifest by digest. -/
theorem liveReceipt_algorithmHash :
    receipt.algorithmHash
      = RegisteredAlgorithm.algorithmHash .plattStrongerRangeLiveV1 := rfl

/-- The signed `input_hash` is the closed invocation's canonical input
digest. -/
theorem liveReceipt_inputHash :
    receipt.inputHash
      = RegisteredInvocation.canonicalInputHash
          .plattStrongerRangeLiveProductionV1 := rfl

/-- The campaign returned `true`: every one of the ten artifacts exited 0. -/
theorem liveReceipt_result : receipt.result = "true" := rfl

/-! ## The new cryptography, checked by the Lean kernel

The signature a dstack-derived key produced inside an Intel TDX trust domain,
over the digest of the statement that enclave actually signed.  Axioms: the
base trio. -/

/-- **The real enclave signature verifies inside the Lean kernel.** -/
theorem liveSignature_kernelChecked :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxLiveCampaign.enclavePublicKeyHex
      PhalaTdxLiveCampaign.statementDigest
      PhalaTdxLiveCampaign.signatureHex = true := by
  decide +kernel

/-- One character of the enclave public key altered, and the verifier refuses:
the altered point is not on the curve, so `isValidPublicKey` rejects it before
any scalar multiplication. -/
theorem liveSignature_rejectsAlteredKey :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxLiveCampaign.tamperedPublicKeyHex
      PhalaTdxLiveCampaign.statementDigest
      PhalaTdxLiveCampaign.signatureHex = false := by
  decide +kernel

/-- One character of the signature altered, and the verifier refuses. -/
theorem liveSignature_rejectsAlteredSignature :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxLiveCampaign.enclavePublicKeyHex
      PhalaTdxLiveCampaign.statementDigest
      PhalaTdxLiveCampaign.tamperedSignatureHex = false := by
  decide +kernel

/-- The statement obtained by altering only `issuedAt` -- the one signed field
no check other than the signature itself inspects -- is refused. -/
theorem liveSignature_rejectsAlteredStatement :
    SparkInterval.Certificate.P256.verifyDigestHex
      PhalaTdxLiveCampaign.enclavePublicKeyHex
      PhalaTdxLiveCampaign.tamperedStatementDigest
      PhalaTdxLiveCampaign.signatureHex = false := by
  decide +kernel

end SparkInterval.Tests.PhalaTdxLiveCampaign
