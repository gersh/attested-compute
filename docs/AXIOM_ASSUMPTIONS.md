# What the axiom covers, and what is embedded in it

There is exactly one axiom in the attested-run chain. This document states it,
walks each premise, and then lists — without softening — everything the axiom
assumes but does not check. Each assumption gets a verdict: whether it is
defensible as it stands, and if not, what would fix it.

If you read one section, read §3. Every assumption there is currently
defensible; §3.3 records one that was not, and what it took to fix it, because
a chain like this is best judged by how its worst link was handled.

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

### 3.3 ✔ Everything that runs is measured — resolved

*(Was: "the signing interpreter is downloaded at run time and is not measured".
That is fixed; the history is kept because the fix is only meaningful against
what it replaced.)*

The entry point used to run, inside the VM:

```sh
apt-get install -y -qq --no-install-recommends gcc libc6-dev python3 ca-certificates
```

and then use that `python3` to derive the enclave key and **sign the receipt**.
The compose is measured and the base image is pinned by digest, but packages
fetched at run time are neither. A substituted `python3` — a compromised
mirror, a hostile package, a TLS interception the container accepts — could
compute a false statement and sign it with the genuine enclave key, and every
downstream check would still pass, because the signature would be authentic.
The `gcc` was worse in kind, not degree: a subverted compiler can be made to
agree with a wrong result, which is exactly what the differential rebuild
exists to rule out.

Three things now hold instead.

**The tools come from the measured image.** The base image is
`python@sha256:e5931cdb4a8cec0ad083277c16a39114f14123b8b6c858c8c9689b677789975c`
(`python:3.12`, Debian 13), which already carries `bash`, coreutils, `gcc`,
libc headers and `python3`. The digest is in the compose, the compose is in
`mr_config_id` and in the RTMR3 `compose-hash` event, so every executable the
entry point uses is inside the measurement.

**Nothing is fetched.** The service runs `network_mode: none`. The container
has no network at all, so there is no channel over which a substitution could
arrive. The dstack guest agent is reached over the `AF_UNIX` socket at
`/var/run/dstack.sock`, which is a bind mount and needs no network.

**The entry point refuses rather than repairs.** Before anything else it checks
`bash gcc python3 sha256sum base64 gzip stat cut` and `/usr/include/stdio.h`,
and exits non-zero if any is absent. An image that does not carry the toolchain
produces no run at all, rather than a run that quietly provisions itself.

**Verdict: defensible.** With one caveat worth naming: this reduces trust in
Debian's package mirrors at run time to trust in the contents of one image at
the digest above. That is a much smaller and, more importantly, a *fixed*
target — the same bytes every run, auditable ahead of time by anyone who pulls
the digest — but it is not zero. A reader who wants to check it can pull that
digest and inspect it; the digest is pinned here, in the compose, and in the
measurement.

**How this is kept true.** `attestation/phala/negative_test.sh` gate 5 runs the
committed entry point in an image *without* the toolchain and requires it to
refuse, and greps the entry point (comments stripped) for `apt-get`, `apk add`,
`pip install`, `curl` and `wget`. A regression fails the gate.

There is a related lesson in how this was found. `dry_run.sh` and
`negative_test.sh` used to run the entry point in the local cross-build image
`lcc-x86cross:24.04` while printing the *compose's* image in their logs. That
image has no native `gcc` — which is why the `apt-get` looked necessary, and
why nobody noticed it was outside the measurement. A gate whose purpose is
"what deploys is what was exercised" was exercising something else. Both
scripts now take the image from the compose and bind-mount only
`qemu-x86_64-static` and its sysroot, which real x86_64 hardware has natively.

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

The container runs `read_only` with an `exec` tmpfs at `/tmp`, `cap_drop: ALL`,
`no-new-privileges` and `pids_limit: 512`, in addition to `network_mode: none`.
None of that defends against the host — TDX does — and none of it is
load-bearing for the attestation. It constrains the entry point *if the entry
point is wrong*, which is the one failure mode nothing else here covers: the
compose is measured, so a mistake in it is measured just as faithfully as a
correct one. Because the flags live in the compose, they are inside the compose
hash and the RTMR3 event, so the quote attests the posture the container ran
under rather than our claim about it. The entry point additionally records
`uid`, rootfs writability, `CapEff` and `NoNewPrivs` at run time, which is the
cross-check that the runtime honoured what the compose asked for.

Two caveats, both real:

*The process still runs as root inside the container.* `cap_drop: ALL` and
`no-new-privileges` remove most of what that would otherwise mean, but it is
not the same as a non-root `user:`. The obstacle is factual rather than
philosophical: the dstack socket and the app-compose mount are root-owned, and
a `user:` that cannot read them produces a run with no signature at all. The
posture block records their mode and owner precisely so that decision can be
made from data instead of guessed.

*`exec` on the `/tmp` tmpfs is mandatory, not an oversight.* Docker mounts a
`--tmpfs` `noexec` by default, and the decoded artifacts are executed from
there. This is checked explicitly at startup rather than inferred, because the
rehearsal cannot catch it alone: under qemu the artifacts are read as data by
an interpreter, so `noexec` never touches them.

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
| everything that runs is inside the measurement | defensible; image pinned by digest, no network (§3.3) |
| the container runtime behaves | defensible; no network, read-only, no caps; still root (§3.4) |
| the emitter expression and `mainText` | defensible, by preimage (§3.5) |
| CompCert's proof, the assembler, the linker | defensible, reduced by freestanding linking (§3.6) |
| a machine really executed it | irreducible; this is the axiom (§3.7) |

The mechanism is sound in shape, and every link is now defensible on its own
terms. An attested run should be read as: *"a machine whose entire software
stack hashes to a value recorded in an Intel-signed quote executed these exact
bytes and got this exact transcript."* Nothing more — in particular, not that
the transcript means what the emitter says it means (§3.5), and not that
CompCert's proof is true (§3.6) — but that much, honestly.

What remains open is scope rather than soundness: the container is hardened
but still runs as root inside itself (§3.4), pending the mount-ownership data
that says whether a non-root `user:` can reach the guest agent at all; and §3.1
holds only if the pin table is treated as a review record rather than a list of
hashes someone pasted in. Both are matters of process, not of mechanism.
