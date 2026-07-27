# The CH25 Lemma A.7 reference model, and what it costs to remove the enclave

This document records (a) how the A.7 boundary campaign now separates the
operational claim from the mathematical one, and (b) **measured** costs for the
four ways of closing the remaining gap. Every number below was measured on the
development host (aarch64, 20 cores, 119 GB), on the real retained artifact
`a7_boundary.json`, SHA-256 `ccc11cec…9f29`, 1,494,999 bytes, 16,191 leaves.

---

## 1. The chain, and where the assumptions are

```text
attested emission of the bytes `true`
  ── axiom  phalaTdxAttestedEmission_sound  (operational only)
  ── premise EnclaveImplementsA7ReferenceModel
∃ raw, A7BoundaryWireEvidence.modelOutput raw = "true"
  ── proved  checkRetainedBytes_sound, accepted_of_check_eq_true
∃ certificate, certificate.check = true
  ── premise A7BoundaryWireEvidence.RetainedAnalyticRealization
A7BoundarySuccessEvidence.SuccessEvidence
  ── proved  sourceClaim_of_successEvidence
A7BoundarySourceSemantics.SourceClaim
```

The reference model is
`SparkInterval/TernaryGoldbach/A7BoundaryWireEvidence.lean`:

```lean
def modelOutput (raw : ByteArray) : String :=
  if checkRetainedBytes raw then "true" else "false"
```

a total `ByteArray → String` with no `native_decide`, no `Float`, and nothing
noncomputable. It is the complete input/output behaviour attributed to the
external checker: consume one `TGA7WIR1` artifact, emit `true` or `false`.

`sparkinterval-check-a7-wire` compiles **that same source text** into an
executable, so the decision procedure the proofs reason about can also be run.

### What is proved that used to be assumed

`phalaTdxAttestedRun_sound` concluded `invocation.Runs receipt.result`. For
this invocation that unfolds to

```lean
∃ certificate, certificate.check = true ∧ Nonempty (AnalyticRealization certificate)
```

so the attestation axiom was asserting a Lean existential over certificates
*and* an analytic statement about Mathlib's `riemannZeta`. Both halves are now
outside the axiom:

* the certificate existential is `ch25A7BoundaryRuns_of_modelOutput`, an
  ordinary Lean theorem whose axiom set is the base trio only;
* the analytic statement is `RetainedAnalyticRealization`, an explicit named
  premise on every theorem that uses it.

### What remains assumed, in one sentence

**`EnclaveImplementsA7ReferenceModel`: if the pinned enclave image, run on the
pinned input, emits the bytes `true`, then some byte string exists that the
Lean reference model also maps to `true`.**

It is falsified by any disagreement between the external checker and
`A7BoundaryWire.checkBytes` on the retained artifact, and it is dischargeable
by computation the moment those bytes are handed to Lean.

`RetainedAnalyticRealization` is *not* part of that residual: it is a
mathematical premise that no attestation and no byte-level checker can supply,
and it was equally unproved before this change. It is the honest remainder of
the A.7 atom.

---

## 2. Measured costs of the four options

### Option 1 — keep the Python/FLINT checker, state one narrow assumption

This is what is implemented today.

* Assumption remaining: `EnclaveImplementsA7ReferenceModel` (above), plus
  `RetainedAnalyticRealization` which every option shares.
* Engineering cost: done.
* Added TCB: CPython, python-flint 0.9.0, FLINT 3.6.0, GMP/MPFR, plus the
  `tg_verifier` sources — for the *combinatorial* verdict, on top of the
  hardware assumptions. FLINT is genuinely needed for the analytic replay, but
  it is not needed for the finite check, so this option pays for it twice.

### Option 2 — in-Lean kernel re-checking of the artifact

Materialize the retained transcript as Lean literals and close
`certificate.check = true` with ordinary `decide`:

```bash
python3 tools/tg_a7_lean_certificate.py \
  --input .../a7_boundary.json --output /review/A7BoundaryProduction.lean
lake env lean -j1 -M100000 /review/A7BoundaryProduction.lean
```

**Measured, on the real retained artifact:**

| Quantity | Value |
| --- | --- |
| generated Lean source | 5,000,565 bytes, SHA-256 `694b195a…e72f8` |
| elaboration + kernel `decide` | **5 min 45 s** wall (327 s user) |
| peak RSS | **20.2 GB** |
| `#print axioms certificate_check` | `[propext]` |

That is the whole thing: the real 16,191-leaf certificate is accepted by the
Lean kernel, with `propext` as its only axiom — no `Classical.choice`, no
`Quot.sound`, no `Lean.ofReduceBool`, no `sorryAx`.

Two caveats, stated plainly:

* 20 GB exceeds the repository's habitual `-M8192` build budget, so this cannot
  go into the default `lake build` as it stands. It needs its own target and
  its own memory allowance, or a split of the certificate into per-edge
  modules (each edge is roughly a quarter of the work, so ~5 GB and ~90 s
  each — untested).
* Running the **whole** wire parser in the kernel, rather than just
  `Certificate.check` on literals, is a different and much worse proposition:
  `checkRetainedBytes` computes four SHA-256 digests over ~1.4 MB, and kernel
  SHA-256 is already known in this repository to blow a 16 GB budget on
  nineteen *short strings* (see the note on `dryRunAccepted`). Option 2 means
  literals plus `Certificate.check`, not `decide (checkBytes raw)`.

* Assumption remaining after this option: only `RetainedAnalyticRealization`.
  The enclave becomes mathematically unnecessary for the finite half.
* Engineering cost: small — the generator already exists; the work is choosing
  a build target and a review procedure for a 5 MB generated file.
* Added TCB: none. Strictly the Lean kernel, which is already trusted.

### Option 3 — compile the Lean checker and run it in the enclave

`SparkInterval/TernaryGoldbach/A7BoundaryWireCLI.lean` plus the
`sparkinterval-check-a7-wire` `lean_exe` target.

**Measured:**

| Quantity | Value |
| --- | --- |
| `lake build sparkinterval-check-a7-wire` | 16.6 s (artifacts warm) |
| binary size | 181 MB; 111 MB after `strip` |
| dynamic dependencies | glibc only (`libc`, `libpthread`, `libdl`, `librt`, `libm`) — GMP is linked in |
| `checkBytes` on the real 1,424,952-byte wire | **1.22 s**, 90 MB RSS |
| `checkRetainedBytes` (adds four SHA-256 over 1.4 MB) | **2.29 s**, 90 MB RSS |
| verdict on the real artifact | `true` |

Nothing in the transitive closure is `noncomputable` or `partial`; it compiled
without modification.

**Agreement with the Python/FLINT checker**, on the same bytes:

| Input | Lean binary | `tg_verifier.a7_boundary_wire` |
| --- | --- | --- |
| genuine wire | `true` | accepted |
| one flipped mantissa bit | `false` | rejected (payload digest) |
| last leaf's norm exponent set to 0, payload digest repaired | `false` | rejected: `records[16190].norm_sq_upper fails the strict source bound` |
| truncated by one byte | `false` | — |
| one appended byte | `false` | — |

One caveat that this option does **not** remove: the enclave consumes the JSON
transcript, while the Lean model consumes the `TGA7WIR1` binary projection. If
the Lean binary is what runs in the enclave, the JSON→wire projection must
either happen inside the enclave (still unmodelled Python) or the projection
must be reviewed as part of the artifact identity. The wire header commits to
the JSON's SHA-256 and to the canonical leaf array's SHA-256, so the projection
is auditable and reproducible — this run reproduced the pinned wire SHA-256
`1ea01e78…de4c` exactly — but it is not itself a Lean-modelled step. Closing
that would mean a Lean JSON+base64url parser, which is ordinary work but not
free.

* Assumption remaining: `RetainedAnalyticRealization`, plus "the Lean compiler
  and runtime correctly executed this program", plus the JSON→wire projection
  caveat above. The "does the program implement the model" assumption is gone
  in the sense that the program *is* the model's source text.
* Engineering cost: moderate. The binary exists and works; the enclave image
  needs the compiled binary only (no toolchain), so a two-stage Docker build
  cross-compiled for `linux/amd64` — note this machine is aarch64, so the
  measurements above are aarch64 and the image build is a cross-build.
* Added TCB: the Lean compiler and its runtime, which is the same object the
  project's existing `Lean.ofReduceBool` policy already covers, and a
  well-studied one. No new third-party library.

### Option 4 — verifiable-subset Rust + Aeneas

Reimplement the checker in a Rust subset Charon/Aeneas can handle, extract a
Lean model, prove the extracted model equals `Certificate.check`, and run the
Rust binary in the enclave.

Not measured, because it is a from-scratch reimplementation: FLINT is C and is
outside Aeneas's scope, so only the finite checker could be treated this way —
and the finite checker is precisely the part that Options 2 and 3 already close
for a few seconds of compute.

* Assumption remaining: `RetainedAnalyticRealization`, plus rustc's correctness,
  plus the faithfulness of Charon's MIR extraction and Aeneas's translation.
* Engineering cost: high. A new checker, a new proof that the extracted model
  agrees with `Certificate.check`, and a new toolchain to pin and reproduce.
* Added TCB: charon + aeneas + rustc + the Rust runtime, all new, on top of
  Lean. Strictly larger than Option 3's.

---

## 3. Recommendation

**Option 2, with Option 3 as the operational front end.** In that order, and
for one reason: Option 2 removes the assumption entirely rather than narrowing
it, and it costs 5 min 45 s and 20 GB *once*, on a machine that has 119 GB.
The premise this whole enclave path was built on — that kernel-checking 16,191
leaves is too expensive — is measurably false.

Concretely:

1. Commit the generated literal certificate under its own build target with an
   explicit memory allowance (or split per edge), and discharge
   `EnclaveImplementsA7ReferenceModel` by exhibiting the bytes instead of
   assuming agreement. After this, the A.7 finite content depends on the Lean
   kernel and nothing else.
2. Keep `sparkinterval-check-a7-wire` as the fast reviewer-facing and
   enclave-facing checker (1.2 s), and use it in the enclave in place of the
   Python checker if the enclave path is kept at all. It is the same source
   text as the model, so it cannot silently drift from it.
3. Do not pursue Option 4. It buys nothing that Option 2 does not already give
   for free, and it triples the toolchain TCB.

The thing worth being blunt about: after any of these, **`SourceClaim` still
rests on `RetainedAnalyticRealization`**, which is the statement that FLINT/Arb
ball arithmetic really enclosed Mathlib's `riemannZeta` and `rawG` on each of
16,191 segments. No amount of attestation, kernel checking, or verified
extraction touches that. It is the actual open problem in this atom; the enclave
machinery was never addressing it.

---

## 4. Reproducing the measurements

```bash
# Option 2
python3 tools/tg_a7_lean_certificate.py \
  --input .../a7_boundary.json --output /review/A7BoundaryProduction.lean
/usr/bin/time -v lake env lean -j1 -M100000 /review/A7BoundaryProduction.lean
# measured file SHA-256:
#   694b195ac4b4877f6d52f6bc7c33f3571a075cdbc687b5ceb1725c28c30e72f8

# Option 3
python3 tools/tg_a7_boundary_wire.py \
  --input .../a7_boundary.json --output /review/a7_boundary.tga7wir1
lake build sparkinterval-check-a7-wire
/usr/bin/time -v ./.lake/build/bin/sparkinterval-check-a7-wire \
  /review/a7_boundary.tga7wir1 --retained
```
