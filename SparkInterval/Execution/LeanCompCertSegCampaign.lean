/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxOperationalAttestation
import TGComputeContracts.HurstV2

/-!
# A chained leancompcert campaign under Phala TDX: the pin, and what it buys

This module is the Lean half of `proof_build/leancompcert_tdx/`.  It pins one
campaign -- Platt's stronger little-Mertens range,
`|Σ_{m≤n} μ(m)/m| ≤ 1/(2√(n+1))` for `3 ≤ n ≤ 7 727 065 383` -- by the digest
of the *artifacts that compute it*, and states, as an explicit premise rather
than as an axiom, the one thing attestation cannot supply.

## What `canonicalDefinition` names, and why that is the point

`RegisteredAlgorithm.canonicalDefinition` for `.ch25A7BoundaryV1`
(`Execution/RegisteredAlgorithm.lean`) is a 514-byte **paragraph** whose
`producer=` line names a Python file by path.  Editing that file changes
nothing in Lean.

`segCampaignCanonicalDefinition` below is 505 bytes and names
`manifest-sha256`.  That manifest lists, for every window of the chain, its
range, its segment geometry, its carry-in seed, its expected carry-out, its
threshold, the SHA-256 of the emitted C, and the SHA-256 of the linked
executable.  Editing any artifact changes the manifest digest, which changes
`segCampaignAlgorithmHash`, which the enclave's signature is over.

**505 versus 514.**  Replacing a paragraph about a Python file with the digest
of a machine-generated manifest of 230 CompCert-compiled artifacts costs the
Lean kernel *nine bytes less* than what it replaces.  Every kernel budget
in this repository survives the change.

`segCampaignAlgorithmHash_eq` is that binding, proved by `decide +kernel`.
It is the whole reason the definition is kept small: the kernel cannot hash
the artifacts themselves (measured in `docs/COMPCERT_ARTIFACT_UNDER_TDX.md`
§5: a 2 KB input did not finish in 2,885 s at 46.9 GB), so the digests stay
reviewed literals inside a preimage the kernel *can* hash.

## The chain of trust, stated exactly

```text
attested emission of the bytes "true"
  → [phalaTdxAttestedEmission_sound]  image D, algorithmHash A, input I emitted "true"
  → [segCampaignAlgorithmHash_eq]     A = SHA256(canonicalDefinition)   (kernel)
  → [reading canonicalDefinition]     it names manifest-sha256 = M
  → [reviewed literal]                the manifest with digest M
  → [manifest text]                   230 windows, gap-free, correctly chained
  → [CompCert 3.17]                   each artifact's x86_64 code realises its C
  → [AProgram.evalCC_compile]         each C realises its `AProgram`'s `denote`
  → [SegCampaignRealisesLittleStronger]  ← THE PREMISE.  See below.
  → [ordinary Lean]                   the source-shaped claim
```

## The premise, and what it is *not*

`SegCampaignRealisesLittleStronger` is the honest residual, and it is narrower
than the A.7 path's `EnclaveImplementsA7ReferenceModel` in one respect and
wider in another.  Both are stated here because getting this wrong would be
the kind of quiet over-claim this repository exists to avoid.

**Narrower.**  The program whose exit status is attested is *generated from a
Lean object*.  `LeanCompCert.Ports.ArraySegSieve.mobiusProgram` is 130
instructions; `AProgram.evalCC_compile` proves the emitted C computes that
program's `denote`; CompCert proves the x86_64 assembly computes the C.  There
is no separately written Python program standing in for a Lean checker.

**Wider than a reader might assume, and this is the important part.**  Nothing
in that chain proves the register program computes `Σ_{m≤n} μ(m)/m`.
leancompcert proves *compilation* faithful -- `Program` → C → assembly -- and
validates the sieve numerically against a hand-written reference
(`bench/ref_seg.c`).  It does not prove the sieve's mathematics.  So the
premise below is exactly: **a chain of these artifacts all exiting 0 implies
the little-Mertens bound over the covered range.**

What that premise still buys over "trust a Python program": the object to be
audited is 130 data-independent instructions plus a manifest of literals,
every window is individually falsifiable by re-running one 5 KB executable,
and the artifacts are byte-reproducible from a Lean `Program`.

**How to eliminate it.**  Prove, in leancompcert, that
`mobiusProgram`'s `denote` is the Möbius reciprocal partial sum, and that a
zero violation count with a matching carry-out implies the window's threshold
inequality.  That is a Lean lemma about 130 instructions, not a hardware
problem, and it would move this premise into the proved column entirely.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-! ## The pin -/

/-- The campaign's canonical definition.

Machine-derived by `proof_build/leancompcert_tdx/build_seg_campaign.py`; do
not edit by hand.  `tests/test_leancompcert_seg_campaign_pin.py` fails if this
literal drifts from what the builder emits for the committed manifest. -/
def segCampaignCanonicalDefinition : String :=
  "sparkinterval.registered-algorithm.v1\n" ++
  "name=platt-stronger-range\n" ++
  "producer=leancompcert\n" ++
  "program=Ports.ArraySegSieve.mobiusProgram\n" ++
  "reduced-family=MathExtras.Reductions.PlattStrongerRangeNatFamily\n" ++
  "range=[4,7727065383]\n" ++
  "windows=230\n" ++
  "manifest-sha256=6b20f834c1d8e0d8939625713654884d9a082db9acbbcd979c2e0647046ead38\n" ++
  "manifest-bytes=85644\n" ++
  "compcert-version=3.17\n" ++
  "compcert-target=x86_64-linux\n" ++
  "link=static-freestanding-no-libc\n" ++
  "semantics=AProgram.evalCC_compile\n" ++
  "success=every-window-exit-status-zero\n" ++
  "output=false-or-true\n"

/-- Source-reviewed protocol digest of the campaign definition above. -/
def segCampaignAlgorithmHash : Digest :=
  "ddf877d57c3549dd20e3ba2b846843bb07bd9229537aa38fc54fc67bb0047c10"

/-- Executable audit check for the preimage binding, in the same shape as
`RegisteredAlgorithm.algorithmHashDiagnosticCheck`. -/
def segCampaignAlgorithmHashDiagnosticCheck : Bool :=
  SHA256.digestString segCampaignCanonicalDefinition == segCampaignAlgorithmHash

/-- **The preimage binding is a real kernel theorem, and it does not live
here.**

`proof_build/leancompcert_tdx/seg_campaign_pin_kernel_check.lean` proves

```lean
theorem segCampaignAlgorithmHash_eq :
    SHA256.digestString segCampaignCanonicalDefinition
      = segCampaignAlgorithmHash := by decide +kernel
```

reporting `[propext, Classical.choice, Quot.sound]`.  It is kept out of the
library for a measured reason: hashing this 505-byte string in the kernel
costs **16.4 s user and 10.0 GB resident**, and `lakefile.toml` caps every
module at `-M8192`.  Under that cap the elaboration fails; with the cap lifted
it succeeds.  So the binding is a theorem, it is checked, and it is checked
where a 10 GB reduction is allowed to run -- exactly as
`proof_build/ch25_a7_phala_tdx/prod5_kernel_full_check.lean` does for the
prod5 receipt.

This is also the honest answer to "is naming the artifact by digest free?".
In *bytes* it is better than free: 505 against the 514-byte paragraph it
replaces.  In *kernel memory* it is not free at all, because the repository's
existing 514-byte `canonicalDefinition` is never kernel-hashed either -- the
A.7 registry states plainly that its preimage binding is an import-boundary
obligation rather than "a multi-gigabyte theorem proof".  The upgrade
therefore costs nothing that was previously being paid; it makes a check that
was always available on paper actually affordable to run. -/
theorem segCampaignAlgorithmHashDiagnosticCheck_def :
    segCampaignAlgorithmHashDiagnosticCheck
      = (SHA256.digestString segCampaignCanonicalDefinition
          == segCampaignAlgorithmHash) := rfl

/-! ## The claim -/

/-- Inclusive upper endpoint this campaign actually certifies.

**It is not `TGComputeContracts.HurstV2.littleStrongerLimit`**, and the 3,204
integer gap is a measurement, not an oversight.  See
`segCampaignLimit_lt_littleStrongerLimit` below and the shortfall note. -/
def segCampaignLimit : Nat := 7_727_065_383

open TGComputeContracts.HurstV2 in
/-- The source-shaped conclusion this campaign is about: the `littleStronger`
field of `TGComputeContracts.HurstV2.RealSourceClaims` **restricted to the
range the artifacts certify**.  The campaign computes one atom, so it
concludes one atom, and it concludes it only where it computed it. -/
abbrev LittleStrongerClaim : Prop :=
  ∀ x : Real, 3 ≤ x → x ≤ segCampaignLimit →
    |littleMertensStep x| ≤ 1 / (2 * Real.sqrt x)

/-- The emission this campaign's success verdict corresponds to.

Spelled out over the six strings the operational axiom concludes about, so
that the premise below is about exactly one image, one algorithm identity and
one input, and about no other execution. -/
def SegCampaignAttestedSuccess (imageDigest inputHash parametersHash
    domainHash : String) : Prop :=
  PhalaTdxAttestedEmission imageDigest segCampaignAlgorithmHash inputHash
    parametersHash domainHash "true"

/-- **The single residual assumption of this campaign.**

> If the pinned image, whose `algorithmHash` is the digest of a definition
> naming the pinned manifest, emits the bytes `true` on the pinned input, then
> the little-Mertens bound holds over `[3, 7 727 065 383]`.

Read the module docstring for what this does and does not narrow.  It is
stated as a hypothesis, not an axiom, so that `#print axioms` on the
reduction below reports only the base trio and the one operational
attestation axiom. -/
def SegCampaignRealisesLittleStronger (imageDigest inputHash parametersHash
    domainHash : String) : Prop :=
  SegCampaignAttestedSuccess imageDigest inputHash parametersHash domainHash →
    LittleStrongerClaim

/-! ## The reduction -/

/-- **The end-to-end reduction.**

From one accepted enclave-signed receipt whose invocation carries this
campaign's `algorithmHash`, and the realisation premise, to the source-shaped
little-Mertens bound.

Its only project axiom is the purely operational
`phalaTdxAttestedEmission_sound`, which concludes bytes only.

The `algorithm` hypothesis is what ties the receipt to *this* campaign rather
than to any other registered invocation.  Once a `RegisteredAlgorithm`
constructor for this campaign exists it is discharged by `rfl`; stating it as
a hypothesis keeps this module independent of the closed registry, so that
adding the campaign there is a separate, reviewable edit that weakens no
existing guard. -/
theorem certifySegCampaignLittleStrongerAt
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (authority : enclave.pin.attestationAuthority = true)
    (accepted : phalaTdxOutcomeCheck enclave invocation receipt = true)
    (result : receipt.result = "true")
    (algorithm :
      invocation.algorithm.algorithmHash = segCampaignAlgorithmHash)
    (realises :
      SegCampaignRealisesLittleStronger enclave.pin.imageDigest
        invocation.canonicalInputHash
        invocation.algorithm.canonicalParametersHash
        invocation.algorithm.canonicalDomainHash) :
    LittleStrongerClaim := by
  refine realises ?_
  have emission :=
    phalaTdxAttestedEmission_of_productionOutcome authority accepted result
  simpa [SegCampaignAttestedSuccess, algorithm] using emission

/-! ## Guards

Nothing above is reachable today.  These are the statements that say so, in
the same style as `ch25A7BoundaryPhalaTdxCheck_eq_false`.  They must stay true
until a real receipt exists and a reviewed enclave identity is pinned for it. -/

/-- The campaign's `algorithmHash` is not the hash of any existing registered
algorithm, so no existing receipt can be replayed into this campaign. -/
theorem segCampaignAlgorithmHash_not_ch25A7Boundary :
    segCampaignAlgorithmHash
      ≠ RegisteredAlgorithm.algorithmHash .ch25A7BoundaryV1 := by
  decide

/-- **The shortfall, stated so it cannot be overlooked.**

The campaign does **not** reach `littleStrongerLimit = 7 727 068 587`.  It
stops 3,204 integers short, and the reason is arithmetic rather than budget.

`Ports.ArraySegSieve.plattStrongerThreshold N` is
`⌊2^62 / (2√N)⌋ − ⌈N/2⌉`.  The subtracted term is the accumulated
round-to-nearest budget of the fixed-point accumulator -- one half-ulp per
summand -- and it is what makes a passing integer test a bound on the *real*
sum rather than on its fixed-point image.  At `N ≈ 7.727·10^9` that budget is
`1.47·10^-4` of the threshold, so the artifact certifies
`|S(n)| ≤ (1 − 1.47·10^-4) / (2√N)`.

`7 727 068 587` is the endpoint of Platt's stronger range, i.e. the point at
which the majorant stops holding, so the family's slack there is smaller than
`1.47·10^-4`.  A binary search down to single integers (the halving in
`build_seg_campaign.py`) located the first point the artifact cannot certify:
`n = 7 727 068 562`.  A width-1 window suffers no schedule tightening at all,
so that is the accumulator's budget and nothing else.

Closing it needs a wider accumulator (the budget scales as `N/2^S`, so `S`
rising from 62 to 78 buys four more decimal digits of margin), not a longer
run. -/
theorem segCampaignLimit_lt_littleStrongerLimit :
    segCampaignLimit < TGComputeContracts.HurstV2.littleStrongerLimit := by
  decide

end SparkInterval.Execution
