# Attested CompCert runs: how the whole thing works

A verified-computation project has a gap at the bottom. You can prove that an
algorithm implies your theorem, and prove that the compiler translates it
faithfully, but you cannot *prove* that a machine ran the binary and printed a
number. That is an empirical fact about the world.

The usual answer is an axiom per computation:

```lean
axiom ceUHarmonic_compcert_run : computation.Returns ((1 : Nat) : Int)
```

`claude_math` has about ninety of these. Each is an unconditional assertion
that some binary once ran, unverifiable by a reader.

This document describes the machinery that replaces that shape with **one**
axiom, applicable only on presentation of a signature produced inside an Intel
TDX enclave, with every other link either computed by the kernel or already
proved.

---

## 1. The pipeline

```
  Lean program value                                      (a datatype, not source code)
        │  emitRolled + the family's main                 ── a Lean function
        ▼
  C text ──sha256──▶ emittedCDigest
        │  ccomp -O                                        ── CompCert's proved backend
        ▼
  x86_64 binary ──sha256──▶ binaryDigest
        │  embedded in docker-compose.yaml, digests declared
        ▼
  Intel TDX enclave: verify digests, run, compare against pinned expectations
        │  GetKey → P-256 key;  report_data = H(pubkey, statement)
        ▼
  signed receipt  ──▶  Lean: check signature, pin, digests  ──▶  one axiom  ──▶  Returns
```

Every arrow is a Lean function, a proved theorem, or a kernel-checked
computation, **except** the single step "the enclave really executed it".

---

## 2. What lives where, and why the split is forced

| piece | where | why there |
| --- | --- | --- |
| `CompCertRunSpec` — what identifies an artifact | `SparkInterval/Execution/CompCertRunLedger.lean` | producer-side identity |
| `CompCertRunReceipt`, the checker, the pin table | `SparkInterval/Execution/CompCertRunReceipt.lean` | the trusted-compute boundary lives here |
| `compcert_run_spec.py`, `compcert_run_receipt.py` | `tg_verifier/` | pure stdlib, so an enclave can run them with no network |
| the junction test | `tests/test_compcert_run_spec_junction.py` | keeps the Lean and Python copies honest |
| **the axiom**, `EmittedCMatches`, the atom instances | `claude_math` | ⟵ see below |

**The axiom cannot live in this repository.** It must conclude
`Computation.Returns`, which is `LeanCompCert`'s type, and this package has no
LeanCompCert dependency. Anything statable here would have to be an `opaque`
token with no elimination rule — exactly the dead end
`PhalaTdxAttestedEmission` already occupies, where the axiom fires and nothing
can be derived from it. The consumer imports both packages and is the only
place the two halves meet.

So: **the mechanism is here; the one axiom that consumes it is downstream.**

---

## 3. The trust surface, exactly

For the worked example (`ceu_harmonic_1048576`):

```
'ceU_harm_fx_le_from_attestation' depends on axioms:
  [propext, Classical.choice, Quot.sound, returns_of_certifiedReceipt]
```

One axiom beyond the base trio. It says, and says only:

> a valid P-256 signature, by a key in the reviewed pin table, over a receipt
> whose digest recomputes, means the artifact really executed.

Everything else is computed or proved:

| link | how |
| --- | --- |
| receipt digest recomputes; signature verifies; key is in the reviewed table | `decide +kernel` — 69 s, 28.3 GB, base trio |
| the artifact is the compilation of *this* program | `decide +kernel` — 45 s, 20.7 GB, base trio |
| `Returns v ↔ denote = some v` | proved: `ProgramClaim.returns_iff` |
| the compiled C computes the denotation | proved: `AProgram.evalCC_compile` |
| the denotation implies the mathematics | proved: each atom's own `sound` |

### The pin table is the trust anchor

```lean
def compcertEnclavePins : List CompCertEnclavePin := [ … ]
def lookupCompCertEnclavePin (appId : String) : Option CompCertEnclavePin
```

`compcertRunReceiptCheck` **looks the pin up** by the receipt's own `appId`.
There is no pin parameter. This is the difference between a gate and a
decoration, and it was learned the hard way — see §6.

`attestationAuthority := true` on an entry is the one line in that file that is
a person's judgement rather than arithmetic: it asserts that a key was produced
inside an enclave by dstack. Adding an entry is a reviewable diff.

---

## 4. What the enclave does

Per `claude_math/audits/compcert/rh_phala/`:

1. decode each embedded artifact and **refuse unless its SHA-256 matches** the
   digest the compose declares — before executing anything;
2. run each artifact; record exit status and the SHA-256 of its transcript;
3. compare both against expectations **pinned in the compose**, so the
   criterion is measured rather than left to the binary's own say-so;
4. rebuild the sources with the enclave's own `gcc` and diff the transcripts —
   a differential check of two toolchains;
5. derive a P-256 key from `/GetKey` on a dedicated path;
6. set `report_data = H(public key, statement)` and fetch the quote, so the
   hardware attests *which key signed* **and** *what was claimed*;
7. sign one receipt per artifact and print everything as delimited base64.

### Three upstream facts that shaped this

From [`Dstack-TEE/dstack`](https://github.com/Dstack-TEE/dstack), not from
guesswork:

* **`/Sign` exists** but offers `ed25519`, `secp256k1`, `secp256k1_prehashed`
  — no P-256. Lean has a P-256 verifier and no other, so using `/Sign` would
  mean writing new verified crypto before any receipt could be checked. We
  sign P-256 ourselves; this is a considered choice.
* **`/GetKey`'s `algorithm` field "does not domain-separate the derivation"** —
  the same 32 bytes back every algorithm. Reading them as a P-256 scalar is
  documented behaviour.
* ...and therefore **a shared path is key reuse across algorithms**, which the
  docs warn about. Hence the dedicated `sparkinterval/compcert-run/p256`.

`docs/normalized-app-compose.md` also specifies the compose-hash
canonicalization exactly — sorted keys, no whitespace, `ensure_ascii=False` —
and the measured document matches it byte for byte.

---

## 5. Adding a new attested run

1. Build the artifact: `claude_math/tools/x86cross/build.sh` (x86_64 CompCert
   on an aarch64 host; Intel TDX is x86 only).
2. Regenerate the compose (`build_compose.py`) — it embeds the artifacts with
   their digests and the expected results.
3. `dry_run.sh` — runs the **committed** entry point against a mock guest agent.
   Never skip this: it has caught a missing `libc6-dev`, a `set -e` trap that
   silently swallowed refusals, and a fabricated trailing newline.
4. `deploy.sh` — deploys, captures, verifies, and destroys. About $0.005.
5. `verify_run.py` — checks the evidence offline against the pinned Intel root.
6. Add the enclave identity to `compcertEnclavePins` (the reviewed decision).
7. Downstream: instantiate the receipt, prove `EmittedCMatches` by
   `decide +kernel`, apply the axiom.

Adding a run touches **no** enumeration: `CompCertRunSpec` is data, and the
check is keyed on `ExpectedExecutableIdentity`-style strings rather than on
`RegisteredAlgorithm`, which is a closed 16-constructor inductive whose every
extension recompiles a 2,388-line file and everything downstream.

---

## 6. Traps, each of which cost something

**A forged receipt was accepted.** `compcertRunReceiptCheck` took the pin as a
*parameter* and never consulted the table, so a caller supplied the trust
anchor: an attacker keypair plus an invented pin with
`attestationAuthority := true` passed every check with no enclave involved.
Demonstrated by constructing one. The axiom could have proved anything. Fixed
by looking the pin up; the forgery is now a refusal test.

**A field was mislabelled.** `emittedCDigest` carried the *binary* hash while
its name and docstring said C. The alignment story — re-emit, compare digests —
depends on it being the C. The spec now carries both digests, because they
answer different questions and neither implies the other.

**A premise left a value unconstrained.** `ArtifactRealises` had
`acceptedValue = value`, but `acceptedValue` is the *exit code* while `value`
is what the computation must yield; nothing pinned `value`, so the axiom could
conclude `Returns v` for any `v`. Fixed by parameterising on the
`ProgramClaim`, whose `acceptingValue` is a field.

**A premise was assumed that the kernel can just check.** `EmittedCMatches` was
`opaque` on the belief that binding bytes to a Lean value needs a human. The
emitter is a Lean function, so it is an equation between computable values:
45 s in the kernel, and the axiom disappeared.

**Cost is about `String`, not crypto.** ECDSA is 3.9 s. `digestString` of 1,024
bytes is 92 s / 22 GB, and of 2,048 bytes does not complete in 2,885 s, because
a String literal unfolds to `List Char` with per-character validity proofs.
`SHA256Packed` digests 5,010 bytes by `rfl`; that is the route for anything
larger than about a kilobyte.

**Lean specifics settled by the compiler, not by memory.** `&&` associates
**left**. Extract conjuncts by projection or `tauto`, never `obtain` — it
attempts dependent elimination on String and P-256 terms and fails. Keep
`beq_iff_eq` out of the simp set for the same reason. Once the pin table is
non-empty, `tauto` exhausts its heartbeats and refusal proofs must use `rw`
rather than `simp`, which tries to evaluate the lookup.

---

## 7. What none of this establishes

That an artifact computes the mathematical object its atom names. That is the
`evaluates_atom_predicate` field of each campaign stamp, proved separately per
atom, and it is `false` for both RH pilots.

Nor is it a TCB appraisal: chain validity says the attestation key is
Intel-rooted, not that the platform's microcode is current or that no
certificate was revoked. That needs Intel's live collateral and is
`dcap-qvl`'s job — and in-enclave strict appraisal conflicts with running the
container without network, a tension recorded in commit `0b368fc`.

A receipt says a binary ran and reported a number. Everything above exists to
make that one sentence checkable, and to keep it from being mistaken for more.
