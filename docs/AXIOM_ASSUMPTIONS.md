# What the axiom covers, and what is embedded in it

There is exactly one axiom in the attested-run chain. This document states it,
walks each premise, and then lists — without softening — everything the axiom
assumes but does not check. Each assumption gets a verdict: whether it is
defensible as it stands, and if not, what would fix it.

If you read one section, read §3. It contains an assumption that is currently
**not defensible** and has a known fix.

---

## 1. The axiom

```lean
axiom returns_of_certifiedReceipt {proposition : Prop}
    {claim : ProgramClaim proposition} {name : String}
    {r : CompCertRunReceipt} {spec : CompCertRunSpec} {mainText : String}
    (checked : CertifiedCompCertReceipt r spec)
    (emits : EmittedCMatches spec claim.program name mainText) :
    (claim.computation name).Returns ((claim.acceptingValue : Nat) : Int)
```

In words: *given a receipt that passes every check, and given that the artifact
it names is the compilation of this program, the program's computation returns
its accepting value.*

The returned value is **not** a free parameter — it is `claim.acceptingValue`, a
field of the claim — so the axiom cannot be used to conclude an arbitrary
result.

## 2. What the premises actually give you

`checked : CertifiedCompCertReceipt r spec` unpacks to four facts, all decidable
and all re-checked by the kernel:

| field | what it establishes |
| --- | --- |
| `reviewedPin` | some pin in the **closed source table** matches this receipt's `appId`, carries `attestationAuthority = true`, and is the key, app and compose hash the receipt names |
| `describes` | the receipt's `algorithmId` and `algorithmHash` equal the spec's, and `matchedPinnedExpectation = "1"` |
| `digest` | `SHA256(canonical payload) = receiptSha256` |
| `signatureBinds` | a valid P-256 signature over that digest, under the key the receipt names |

`emits : EmittedCMatches …` is `SHA256(emitRolled program name ++ mainText) =
spec.emittedCDigest` — proved by `decide +kernel`, not assumed.

## 3. What the axiom does **not** verify

### 3.1 Lean never sees the docker-compose

This is the most likely misreading, so state it plainly: **the Lean side does
not check that the compose contains the right thing.** It cannot — the compose
is not one of its inputs.

What `pinCheck` requires is `r.composeHash == pin.composeHash`: that the
receipt names *the compose hash the pin names*. Whether a compose with that
hash actually embeds the artifact, actually verifies its digest before running
it, or actually reports honestly is **not** established in Lean.

The real chain for that is:

1. the entry point refuses unless each artifact's SHA-256 matches the digest the
   compose declares, *before executing anything*; and
2. the entry point is embedded verbatim in the compose, so it is covered by
   `compose_hash`; and
3. that hash is measured into `mr_config_id` and an RTMR3 event.

Every link is real, and `verify_run.py` checks all of them — **outside Lean**.

> ⚠ **Consequence: `attestationAuthority := true` asserts more than it appears
> to.** It is not only "this key came from inside an enclave". Because the pin
> also fixes `composeHash`, setting the flag asserts *"and the compose with this
> hash is the reviewed one — it embeds the artifacts, checks their digests, and
> reports faithfully."* That is a substantial claim resting on a human having
> read the compose and run the verifier.

**Verdict: defensible, but only if the pin is treated as a review record.**
Adding a pin without reading the compose it names silently widens the axiom.
The table should carry, per entry, the verifier report that justified it.

### 3.2 Lean does not check the TDX quote

Lean verifies a P-256 signature over a receipt. It does **not** parse the quote,
walk the Intel certificate chain, replay the RTMRs, or check `mr_config_id`.
All of that is `verify_run.py`, outside the kernel.

So "the run happened inside a genuine enclave" reaches Lean only through the
pin. Lean's contribution is narrower than it may look: *this receipt was signed
by a key someone reviewed and recorded.*

**Verdict: defensible and deliberate.** Quote parsing and PKI in the kernel
would be a large trusted-code surface for little gain, and the external check
is reproducible from committed bytes. But it must not be described as "Lean
verifies the attestation", because it does not.

### 3.3 ⚠ The signing interpreter is downloaded at run time and is **not measured**

The entry point runs, inside the VM:

```sh
apt-get install -y -qq --no-install-recommends gcc libc6-dev python3 ca-certificates
```

and then uses that `python3` to derive the enclave key and **sign the receipt**.

The compose is measured. The base image is pinned by digest. **The packages
installed at run time are neither.** A substituted `python3` — a compromised
mirror, a hostile package, a TLS interception the container accepts — could
compute a false statement and sign it with the genuine enclave key. Every
downstream check would pass, because the signature would be authentic.

The `gcc` installed the same way weakens the differential rebuild for the same
reason: a subverted compiler could be made to agree with a wrong result.

**Verdict: NOT defensible as it stands.** This is the weakest link in the chain
and it undercuts the "everything that runs is measured" claim that the rest of
the design earns.

**Fix:** pre-bake `gcc`, `libc6-dev` and `python3` into an image referenced by
digest, so they are covered by the image digest recorded in the compose; then
run with `network_mode: none`, which also removes the network the substitution
would need. This is already the intended hardening; it is now also a
correctness requirement, not a nicety.

### 3.4 Assumptions about the container runtime

Not checked anywhere, and inherited from Docker and the guest OS:

* the container executes the `command` the compose specifies, unmodified;
* the decoded bytes are what the kernel executes — no `LD_PRELOAD`, no
  `ptrace`, no seccomp filter rewriting behaviour;
* exit statuses are reported faithfully, and `128 + N` really means a signal;
* the artifacts do not interfere with each other or with the entry point;
* the filesystem the entry point writes to is not shared with anything hostile.

**Verdict: defensible.** These are the same assumptions any measured-boot
system makes about its own runtime, and TDX protects the VM from the host. They
are worth stating because they are invisible, not because they are doubtful.
The container currently runs with no hardening flags at all — no `read_only`,
no `cap_drop`, no non-root `user` — which does not create a *new* attacker but
does mean nothing constrains the entry point if it is wrong.

### 3.5 The emitter, and `mainText`

`EmittedCMatches` is proved, not assumed — but it is proved *about a particular
emitter expression*, and `mainText` is supplied by the caller. That is safe:
satisfying the equation for a different program would require
`SHA256(emitRolled p' name ‖ mainText)` to equal a digest already fixed by the
signed receipt, i.e. a preimage.

**Verdict: defensible.**

### 3.6 Everything below CompCert

The compiled C provably computes the program's denotation
(`evalCC_compile`), and `Returns v ↔ denote = some v` is proved
(`ProgramClaim.returns_iff`). Outside those proofs sit CompCert's own Coq
development, the assembler, and the linker.

**Verdict: defensible**, and reduced by freestanding linking — zero undefined
symbols and a five-instruction entry stub. Not zero.

### 3.7 What is irreducibly admitted

That a machine executed the artifact. No proof establishes an event in the
world. This is the part the axiom exists for, and it is gated on a signature
from a key in the reviewed table.

## 4. Summary

| assumption | verdict |
| --- | --- |
| the pin's compose hash names a reviewed compose | defensible **if the pin is a review record** (§3.1) |
| the quote is checked outside Lean, not in it | defensible and deliberate (§3.2) |
| **runtime-installed `python3` signs the receipt** | **not defensible — fix by pre-baking the image** (§3.3) |
| the container runtime behaves | defensible; no hardening flags set (§3.4) |
| the emitter expression and `mainText` | defensible, by preimage (§3.5) |
| CompCert's proof, the assembler, the linker | defensible, reduced by freestanding linking (§3.6) |
| a machine really executed it | irreducible; this is the axiom (§3.7) |

The mechanism is sound in shape. One link — §3.3 — is weaker than the rest and
weaker than the documentation elsewhere implies, and until it is fixed, an
attested run should be read as *"a genuine enclave signed this, using an
interpreter it fetched over the network."*
