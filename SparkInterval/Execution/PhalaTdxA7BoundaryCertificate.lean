/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxCampaignCertificate
import SparkInterval.Execution.PhalaTdxOperationalAttestation
import SparkInterval.TernaryGoldbach.A7BoundaryWireEvidence

/-!
# Phala/dstack TDX bridge for CH25 Lemma A.7

Nothing is installed *at this identity*: `PhalaTdxEnclave`
`.ch25A7BoundaryProductionV1`'s public key is still empty, so
`ch25A7BoundaryPhalaTdxCheck` is `false` for every receipt.

The first real run **has** happened, on Phala prod5 (2026-07-27), and its
reviewed key is pinned at `PhalaTdxEnclave.ch25A7BoundaryPhalaProd5V1`.  It
reaches the campaign conclusion through
`certifyCH25A7BoundaryPhalaTdxFromModelAt`, the enclave-generic form of the
supported reduction below; see `SparkInterval/Tests/PhalaTdxProd5RunTest.lean`.
The empty slot was left empty on purpose, so that every guard already stated
about it stays true as written.

## Two paths, and which one to use

`certifyCH25A7BoundaryPhalaTdxFromModel` is the supported path.  Its only
project axiom is the purely operational `phalaTdxAttestedEmission_sound`, and
every mathematical step from the emitted bytes onwards is an ordinary Lean
theorem.  The two things Lean cannot prove appear as explicit, named premises
in its statement:

* `EnclaveImplementsA7ReferenceModel` -- the pinned image decides the same
  predicate as the Lean reference model `A7BoundaryWireEvidence.modelOutput`;
* `A7BoundaryWireEvidence.RetainedAnalyticRealization` -- the recorded
  FLINT/Arb boxes really enclose Mathlib's `riemannZeta` and `rawG`.

`certifyCH25A7BoundaryPhalaTdx` is the **legacy** path.  It is retained
because deleting a theorem is not in scope, and because the generic layer it
uses is the only shape a future campaign without a Lean reference model could
take.  It reaches the same conclusion from `phalaTdxAttestedRun_sound`, whose
conclusion `invocation.Runs receipt.result` unfolds here to an existential
over Lean certificates together with an analytic statement about Mathlib's
zeta function.  Attestation hardware cannot establish either, so do not build
new work on it.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

/-- Data (1/3): which reviewed enclave identity. -/
def ch25A7BoundaryPhalaTdxEnclave : PhalaTdxEnclave :=
  .ch25A7BoundaryProductionV1

/-- Data (2/3): which closed registered invocation. -/
def ch25A7BoundaryPhalaTdxInvocation : RegisteredInvocation :=
  .ch25A7BoundaryProductionV1

/-- Data (3/3): which exact returned bytes count as success. -/
def ch25A7BoundaryPhalaTdxSuccessOutput : String := "true"

/-- Fail-closed application check for one enclave-signed A.7 replay. -/
def ch25A7BoundaryPhalaTdxCheck (receipt : PhalaTdxReceipt) : Bool :=
  phalaTdxProductionCheck ch25A7BoundaryPhalaTdxEnclave
    ch25A7BoundaryPhalaTdxInvocation receipt
    ch25A7BoundaryPhalaTdxSuccessOutput

/-- The campaign's complete conclusion. -/
abbrev CertifiedCH25A7BoundaryPhalaTdx (receipt : PhalaTdxReceipt) : Prop :=
  PhalaTdxCertifiedSourceRun ch25A7BoundaryPhalaTdxInvocation receipt
    ch25A7BoundaryPhalaTdxSuccessOutput
    A7BoundarySourceSemantics.SourceClaim

/-! ## The supported path: operational attestation plus a Lean reference model

The chain is

```text
attested emission of the bytes `true`
  -> [EnclaveImplementsA7ReferenceModel]  the reference model accepts some artifact
  -> [proved]                             ∃ certificate, certificate.check = true
  -> [RetainedAnalyticRealization]        Nonempty (AnalyticRealization certificate)
  -> [proved]                             SuccessEvidence
  -> [proved]                             invocation.Runs "true"
  -> [proved]                             SourceClaim
```

Only the first arrow is axiomatic, and its axiom says nothing mathematical.
The two bracketed premises are explicit hypotheses, not axioms. -/

/-- The emission this campaign's success verdict corresponds to.

Spelled out so that `EnclaveImplementsA7ReferenceModel` below is about exactly
the image of one reviewed enclave identity, the pinned registered algorithm,
and the pinned input, and about no other execution. -/
def CH25A7BoundaryAttestedSuccess (enclave : PhalaTdxEnclave) : Prop :=
  PhalaTdxAttestedEmission
    enclave.pin.imageDigest
    ch25A7BoundaryPhalaTdxInvocation.algorithm.algorithmHash
    ch25A7BoundaryPhalaTdxInvocation.canonicalInputHash
    ch25A7BoundaryPhalaTdxInvocation.algorithm.canonicalParametersHash
    ch25A7BoundaryPhalaTdxInvocation.algorithm.canonicalDomainHash
    ch25A7BoundaryPhalaTdxSuccessOutput

/-- **The single residual assumption of the A.7 TDX path.**

> If the pinned image, run on the pinned input, emits the bytes `true`, then
> there exist artifact bytes that the Lean reference model
> `A7BoundaryWireEvidence.modelOutput` also maps to `true`.

That is: the enclave program and the Lean model agree on this one input.  It
is the irreducible step between "an attested program printed `true`" and "a
Lean-checkable object exists", and it is unprovable inside Lean because Lean
has no formal model of the Python/FLINT program.

### Why this is the narrowest available form

* The conclusion is a statement about **bytes only**.  It is decidable given
  the bytes: `modelOutput` is a total `ByteArray → String` with no
  `native_decide` and no floating point.
* `checkRetainedBytes`, which `modelOutput` calls, pins the SHA-256 of the
  whole `TGA7WIR1` wire, of its record payload, of the canonical JSON leaf
  array, and of the retained source transcript.  So the existential quantifier
  ranges over (at most) one reviewed byte string.
* It says nothing about any other input, any other campaign, any other output
  value, or any mathematics.

### What would falsify it

Exhibiting the retained artifact together with a run of `modelOutput` on it
that returns `"false"` while the pinned image returns `true`; equivalently, any
disagreement between `tg_verifier/a7_boundary_wire.py` and
`SparkInterval/TernaryGoldbach/A7BoundaryWire.lean` on the accepted language,
or a defect in the JSON-to-`TGA7WIR1` projection that changes a leaf.

### How to eliminate it entirely

Supply the artifact bytes to Lean and discharge the existential by
computation instead of assumption.  Both routes are measured in
`docs/algorithms/CH25_A7_LEAN_MODEL.md`: the Lean kernel accepts the real
16,191-leaf retained certificate by ordinary `decide` in about 5 min 45 s and
20 GB, and the compiled `sparkinterval-check-a7-wire` accepts the real
1,424,952-byte wire in about 2.3 s and 90 MB.  Neither number is prohibitive;
this assumption exists only because the retained artifact is not committed to
this repository. -/
def EnclaveImplementsA7ReferenceModel (enclave : PhalaTdxEnclave) : Prop :=
  CH25A7BoundaryAttestedSuccess enclave →
    ∃ raw : ByteArray,
      TernaryGoldbach.A7BoundaryWireEvidence.modelOutput raw = "true"

/-- The registered success relation for this invocation, **proved** from the
reference model and the analytic premise rather than assumed.

This is the declaration that was previously supplied by
`phalaTdxAttestedRun_sound`.

Axioms: the base trio only. -/
theorem ch25A7BoundaryRuns_of_modelOutput
    {raw : ByteArray}
    (hmodel : TernaryGoldbach.A7BoundaryWireEvidence.modelOutput raw = "true")
    (realization :
      TernaryGoldbach.A7BoundaryWireEvidence.RetainedAnalyticRealization) :
    ch25A7BoundaryPhalaTdxInvocation.Runs
      ch25A7BoundaryPhalaTdxSuccessOutput := by
  refine ⟨rfl, Or.inr ⟨rfl, ?_⟩⟩
  exact
    TernaryGoldbach.A7BoundaryWireEvidence.successEvidence_of_modelOutput
      hmodel realization

/-- **The supported end-to-end reduction.**

From one accepted enclave-signed successful A.7 replay, the enclave/model
agreement premise, and the FLINT/Arb-to-Mathlib realization premise, to the
literal source-shaped boundary estimate.

Its only project axiom is the purely operational
`phalaTdxAttestedEmission_sound`.  In particular it does **not** depend on
`phalaTdxAttestedRun_sound`.

Stated at an arbitrary reviewed enclave identity so that
`SparkInterval/Tests/PhalaTdxDryRunTest.lean` can exercise the whole chain
with the committed stand-in key.  The authority premise is what keeps that
harmless. -/
theorem certifyCH25A7BoundaryPhalaTdxFromModelAt
    {enclave : PhalaTdxEnclave} {receipt : PhalaTdxReceipt}
    (authority : enclave.pin.attestationAuthority = true)
    (hcheck :
      phalaTdxProductionCheck enclave ch25A7BoundaryPhalaTdxInvocation receipt
        ch25A7BoundaryPhalaTdxSuccessOutput = true)
    (model : EnclaveImplementsA7ReferenceModel enclave)
    (realization :
      TernaryGoldbach.A7BoundaryWireEvidence.RetainedAnalyticRealization) :
    CertifiedCH25A7BoundaryPhalaTdx receipt := by
  simp only [phalaTdxProductionCheck, Bool.and_eq_true] at hcheck
  have hresult : receipt.result = ch25A7BoundaryPhalaTdxSuccessOutput := by
    simpa using hcheck.2
  have attested : CH25A7BoundaryAttestedSuccess enclave :=
    phalaTdxAttestedEmission_of_productionOutcome authority hcheck.1 hresult
  obtain ⟨raw, hmodel⟩ := model attested
  exact
    { result_eq := hresult
      run := ch25A7BoundaryRuns_of_modelOutput hmodel realization
      sourceClaim :=
        TernaryGoldbach.A7BoundaryWireEvidence.sourceClaim_of_modelOutput
          hmodel realization }

/-- The supported reduction at the production enclave identity: exactly the
same premises, with the campaign's own fail-closed check.

Its only project axiom is the purely operational
`phalaTdxAttestedEmission_sound`. -/
theorem certifyCH25A7BoundaryPhalaTdxFromModel {receipt : PhalaTdxReceipt}
    (authority :
      ch25A7BoundaryPhalaTdxEnclave.pin.attestationAuthority = true)
    (hcheck : ch25A7BoundaryPhalaTdxCheck receipt = true)
    (model :
      EnclaveImplementsA7ReferenceModel ch25A7BoundaryPhalaTdxEnclave)
    (realization :
      TernaryGoldbach.A7BoundaryWireEvidence.RetainedAnalyticRealization) :
    CertifiedCH25A7BoundaryPhalaTdx receipt :=
  certifyCH25A7BoundaryPhalaTdxFromModelAt authority hcheck model realization

/-! ## The legacy path -/

/-- **Legacy.**  End-to-end reduction from one accepted enclave-signed
successful A.7 replay to the literal source-shaped boundary estimate.

Its only project axiom is `phalaTdxAttestedRun_sound` -- which, for this
invocation, *asserts* the mathematical content that
`certifyCH25A7BoundaryPhalaTdxFromModel` proves.  Prefer that theorem.  This
one is retained only so that no existing theorem is deleted. -/
theorem certifyCH25A7BoundaryPhalaTdx {receipt : PhalaTdxReceipt}
    (authority :
      ch25A7BoundaryPhalaTdxEnclave.pin.attestationAuthority = true)
    (hcheck : ch25A7BoundaryPhalaTdxCheck receipt = true) :
    CertifiedCH25A7BoundaryPhalaTdx receipt :=
  certifyPhalaTdxSourceRun
    RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim authority
    hcheck

/-- Today the campaign is unreachable: no receipt satisfies the check. -/
theorem ch25A7BoundaryPhalaTdxCheck_eq_false (receipt : PhalaTdxReceipt) :
    ch25A7BoundaryPhalaTdxCheck receipt = false := by
  simp [ch25A7BoundaryPhalaTdxCheck, phalaTdxProductionCheck,
    ch25A7BoundaryPhalaTdxEnclave,
    phalaTdxOutcomeCheck_ch25A7BoundaryProductionV1_eq_false]

end SparkInterval.Execution
