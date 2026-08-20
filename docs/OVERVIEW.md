# attested-compute

*(The Lean library inside is still called `SparkInterval`; only the repository
was renamed, to say what it does.)*

**Calculate once, verify once, use the result as a theorem.**

SparkInterval is infrastructure for a specific problem: you have a computation
too expensive for anyone to repeat, and you want its result to be usable as a
proved fact rather than as a claim people take on faith.

It has nothing to say about what you compute. It is about the join between an
expensive calculation and a proof assistant that will not run it.

---

## The problem

A bounded calculation — a bound checked over every integer below 10¹², a case
split exhausted, zeros of a function isolated — can take core-hours to
core-years. Inside a proof assistant that becomes an axiom:

```lean
axiom my_computation_ran : computation.Returns 1
```

Everything above that line can be immaculate. The line itself is somebody's
word, and a reader who wants to check it must redo the calculation.

## The approach

Three things, layered:

**1. Make the computation a value, not a program you trust.**
Express it in a small verified fragment — a bounded fold over a register
machine — and *prove* that its accepting result implies your statement.
Compiling that value to C is a function inside the proof assistant, and the
compiled C provably computes what the value means.

**2. Run it where the hardware will witness it.**
Execute inside a confidential VM (Intel TDX). The CPU measures the code before
running it, and signs those measurements together with 64 bytes you choose. Put
the digest of the *results* in those bytes and one signature covers both what
ran and what came out.

**3. Check the certificate in the kernel, not by eye.**
The proof assistant re-derives the receipt's digest, verifies its signature,
and confirms the signing key is one a reviewed table names. What remains
admitted is a single axiom: *that a machine executed the artifact.* That part
is irreducible — no proof establishes an event in the world.

## What you end up with

```
[propext, Classical.choice, Quot.sound, returns_of_certifiedReceipt]
```

The base axioms of the logic, plus one that cannot be applied without a
signature the hardware vouches for.

Compare: an ordinary `native_decide` admits the compiler, the runtime and GMP
opaquely, and a bare run axiom admits an unverifiable claim about the past.
Neither can be checked by a reader. This can be, offline, from committed bytes.

---

## Where to go next

| you want to | read |
| --- | --- |
| run one on Phala / dstack | [`PHALA_TDX_DEPLOYMENT.md`](PHALA_TDX_DEPLOYMENT.md) |
| --- | --- |
| understand the mechanism and use it | [`ATTESTED_COMPCERT_RUNS.md`](ATTESTED_COMPCERT_RUNS.md) |
| decide whether to believe a certificate, and check one | [`TRUSTING_THE_ENCLAVE.md`](TRUSTING_THE_ENCLAVE.md) |
| audit the axiom's premises and assumptions | [`AXIOM_ASSUMPTIONS.md`](AXIOM_ASSUMPTIONS.md) |
| know precisely what is and is not claimed | [`CORRECTNESS_CLAIMS.md`](CORRECTNESS_CLAIMS.md) |
| see the whole trust chain named | [`VERIFYING.md`](VERIFYING.md) |

## Honest scope

* **Attestation says nothing about mathematics.** That your artifact computes
  the object your theorem names is a separate obligation, proved per
  computation. A receipt says a binary ran and reported a number.
* **This is not a TCB appraisal.** Certificate-chain validity says the
  attestation key is Intel-rooted; it says nothing about whether the platform's
  microcode is current or whether a certificate was revoked.
* **You still trust Intel**, the guest agent that derives the signing key, the
  assembler and linker below CompCert's proof, and the human judgement that a
  pinned key really came from an enclave. All four are named, and
  [`TRUSTING_THE_ENCLAVE.md`](TRUSTING_THE_ENCLAVE.md) says why each is there.

## Examples, not the point

The first consumer is a formalisation of the ternary Goldbach conjecture, which
carries about ninety such computations; one is closed end to end from a real
Intel TDX run. A GPU interval evaluator for Dirichlet L-function zeros
(following Platt) is the other worked example.

Both are illustrations. The mechanism knows nothing about number theory, and
the interesting question for a new user is whether *their* computation fits the
verified fragment — not whether it resembles these.
