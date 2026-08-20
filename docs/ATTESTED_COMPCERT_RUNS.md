# Attested runs: turning a computation you cannot re-run into a theorem

## The problem

Some facts are only reachable by computation. Checking a bound over every
integer below 10¹², enumerating zeros of an L-function, exhausting a case
split — these take core-hours to core-years. A reader cannot repeat them, so
the result arrives as an assertion and has to be believed.

Inside a proof assistant this shows up as an axiom:

```lean
axiom my_computation_ran : computation.Returns 1
```

The proof above it may be immaculate. That line is still someone's word.

## What this project does about it

Run the computation inside a **confidential VM**, and arrange for the hardware
to sign *both* the code it measured and the results it produced. Then the
axiom becomes conditional:

> a valid signature, by a key the hardware attests came from inside an enclave,
> over a statement naming this program and this result

and everything else — that the signature verifies, that the artifact is the
compilation of the program the theorem is about, that the program's result
implies the theorem — is either computed by the proof assistant's kernel or
already proved.

The trust surface for the worked example is:

```
[propext, Classical.choice, Quot.sound, returns_of_certifiedReceipt]
```

One axiom beyond Lean's own, and it says only *that a machine executed the
artifact*. That is the irreducible part: no proof establishes that something
happened in the world.

**This is a general mechanism.** Nothing in it is specific to a subject area.
It applies to any bounded computation you can express as a verified program.

---

## 1. The pipeline

```
  program value (a datatype, not source code)
        │  emitter                                   ── a function inside Lean
        ▼
  C text ──sha256──▶ emittedCDigest
        │  ccomp                                     ── CompCert's proved backend
        ▼
  binary ──sha256──▶ binaryDigest
        │  embedded in the compose, digests declared
        ▼
  Intel TDX enclave: verify digests, run, compare against pinned expectations
        │  derive key;  report_data = H(pubkey, statement)
        ▼
  signed receipt ──▶ kernel-checked ──▶ one axiom ──▶ Returns ──▶ your theorem
```

Every arrow is a function, a proved theorem, or a kernel computation, except
the single step "the enclave really executed it".

## 2. What each link costs, and how it is discharged

| link | how | measured |
| --- | --- | --- |
| receipt digest recomputes; signature verifies; key is in the reviewed table | `decide +kernel` | 69 s, 28.3 GB |
| the artifact is the compilation of *this* program | `decide +kernel` | 45 s, 20.7 GB |
| `Returns v ↔ denote = some v` | proved (`ProgramClaim.returns_iff`) | — |
| the compiled C computes the denotation | proved (`evalCC_compile`) | — |
| the denotation implies your statement | proved, per computation | — |
| the machine executed it | **admitted**, gated on the signature | — |

Cost is dominated by `String`, not cryptography: ECDSA is 3.9 s, while
`digestString` of 1,024 bytes is 92 s / 22 GB and of 2,048 bytes does not
finish in 2,885 s. `SHA256Packed` digests 5,010 bytes by `rfl` and is the route
for anything larger than about a kilobyte.

## 3. Using it

1. Express the computation as a verified program and prove that its accepting
   value implies your statement. That is the mathematical work and it is yours.
2. Emit and compile the artifact. Reproducibility matters — hosted links need
   `-Wl,-s`, because CompCert names its intermediate object with a random
   temporary that the linker records in the symbol table.
3. Generate the deployment, embedding the artifacts with their digests and the
   expected results, so the success criterion is *measured* rather than left to
   the binary's own say-so.
4. Rehearse against a mock guest agent before spending anything. This step has
   caught a missing `libc6-dev`, a `set -e` trap that silently swallowed
   refusals, and a fabricated trailing newline. It runs the entry point from
   the **committed compose, in the compose's own image** — if you ever find
   yourself pointing it at a convenient local image instead, the gate stops
   testing the thing that deploys, and that has happened here (§6).
5. Deploy, capture the evidence, verify it offline, destroy the VM.
6. Add the enclave identity to the reviewed pin table — the one human judgement
   in the chain.
7. In Lean: instantiate the receipt, discharge the artifact-to-program binding
   by `decide +kernel`, apply the axiom. Generate the receipt literal rather
   than transcribing it — the consuming repository has
   `tools/attest/emit_lean_receipt.py <evidence-dir> <algorithm-id>`, which
   reads the receipt the enclave signed and prints the Lean structure. A hand
   transcription that is wrong in one field fails as a bare `false` from the
   kernel, with nothing to say which field; one that is wrong *consistently* on
   both sides typechecks and pins nothing.

Adding a run touches no enumeration; an artifact is *data*.

## 4. Where the pieces live

| piece | module |
| --- | --- |
| what identifies an artifact | `SparkInterval/Execution/CompCertRunLedger.lean` |
| the receipt checker and the pin table | `SparkInterval/Execution/CompCertRunReceipt.lean` |
| splitting a TDX check into four affordable parts | `SparkInterval/Execution/PhalaTdxOutcomeSplit.lean` |
| producer-side mirrors, pure stdlib so an enclave can run them | `tg_verifier/compcert_run_spec.py`, `compcert_run_receipt.py` |
| the Lean↔Python junction test | `tests/test_compcert_run_spec_junction.py` |

**The axiom itself lives in the consumer, not here**, and that is forced: it
must conclude `Computation.Returns`, a type from the verified-compiler package,
which this repository does not depend on. Anything statable here would be an
`opaque` token with no elimination rule — the dead end `PhalaTdxAttestedEmission`
already occupies, where the axiom fires and nothing can be derived from it.

For why the resulting certificate should be believed, and how to check one
yourself, see [`TRUSTING_THE_ENCLAVE.md`](TRUSTING_THE_ENCLAVE.md).

## 5. Worked example

The first consumer is a formalisation of the ternary Goldbach conjecture, which
carries about ninety such computations. One of them,
`AnalyticNT.LargeSieve.ceU_harm_fx_le` — a bound on `∑_{i ≤ 2²⁰} ⌈2⁴⁴/i⌉` — is
closed end to end from an Intel TDX run: the receipt is kernel-checked, the
artifact-to-program binding is kernel-proved, and the statement follows with
one axiom.

It is an example, not the point. The mechanism knows nothing about number
theory.

## 6. Traps, each of which cost something

**A forged receipt was accepted.** The checker took the enclave pin as a
*parameter* and never consulted the reviewed table, so the caller supplied the
trust anchor: an attacker keypair plus an invented pin passed every check with
no enclave involved. Demonstrated by constructing one. Fixed by looking the pin
up; the forgery is now a refusal test. **Test that a gate refuses, not only
that it accepts.**

**A field was mislabelled.** A digest field named and documented as the C's
hash carried the binary's. The whole re-emit-and-compare argument depends on it
being the C. The spec now carries both, because they answer different questions.

**A premise left a value unconstrained**, so the axiom could conclude a result
nothing pinned. Fixed by parameterising on the claim, whose accepting value is
a field rather than a free choice.

**A premise was assumed that the kernel can simply check.** The
artifact-to-program binding was `opaque` on the belief that relating bytes to a
program needs a human. The emitter is a function inside Lean, so it is an
equation between computable values: 45 s, and the axiom disappeared.

**The rehearsal ran a different image than the deployment.** `dry_run.sh` and
`negative_test.sh` existed to guarantee "what deploys is what was exercised",
and both ran the entry point in a local cross-build image while *printing the
compose's image* in their logs. That image had no native `gcc`, which is
exactly why the entry point's `apt-get install gcc … python3` looked necessary
— and so the `python3` that signs the receipt sat outside the TDX measurement
for nine real runs without anyone noticing. A substituted interpreter could
have signed a false statement with the genuine enclave key.

The gate was self-confirming: it ran, it passed, its log named the right image.
Nothing it printed ever contradicted the one line that chose the wrong one.
**For any harness whose claim is "this is what production runs", check the line
that selects the artifact, not the banner it prints** — and make the harness
derive that value from the same artifact the deployment uses, so the two cannot
drift. Where production and rehearsal genuinely differ (here: `qemu` and its
sysroot, which real x86_64 hardware has natively), bind-mount the difference
*into* the deployed image rather than swapping the image.

It surfaced only because the fix — refuse if `gcc` is missing — *failed* in the
rehearsal. A gate failing where you expected it to pass is information.

**Lean specifics settled by the compiler, not by memory.** `&&` associates
left. Extract conjuncts by projection or `tauto`, never `obtain` — it attempts
dependent elimination on String and P-256 terms. Keep `beq_iff_eq` out of the
simp set for the same reason. Once the pin table is non-empty, `tauto` exhausts
its heartbeats and refusal proofs must use `rw`, since `simp` tries to evaluate
the lookup.

## 7. What none of this establishes

That an artifact computes the object your theorem names. That is a per-
computation obligation, proved separately, and no amount of signing supplies
it. A receipt says a binary ran and reported a number; everything here exists
to make that one sentence checkable, and to keep it from being mistaken for
more.
