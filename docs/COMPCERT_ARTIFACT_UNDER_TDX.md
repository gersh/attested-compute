# Running a leancompcert CompCert artifact under Phala TDX

Status: design + measurement. Nothing here has been deployed. No CVM was
created and no credits were spent while writing it.

Companion files added with this note:

* `tools/tg_leancompcert_artifact_pin.py` — derives the registry pin
  (`canonicalDefinition` and `algorithmHash`) from an artifact
* `proof_build/leancompcert_tdx/build_artifact.sh` — emit, compile, self-check, pin
* `proof_build/leancompcert_tdx/Dockerfile` — the campaign image
* `proof_build/leancompcert_tdx/run_artifact_campaign.sh` — the container entry point

Every number below is marked **M** (measured, by me, on this host, on the date
given) or **E** (extrapolated, with its basis stated). Host for all M numbers:
20-core aarch64 Linux, 119 GB RAM, CompCert 3.17, Lean 4.32.0, under
concurrent load from unrelated jobs (load average 20–39 throughout), so wall
times are inflated and **`user` time is the honest figure**.

---

## 1. What this replaces, and what it does not

The verified Phala run attested a CPython + python-flint + FLINT program. The
residual assumption it left is `EnclaveImplementsA7ReferenceModel`
(`SparkInterval/Execution/PhalaTdxA7BoundaryCertificate.lean:147`): *if the
pinned image emits `true`, then the Lean reference model would too*. That
assumption exists because a separately written Python program stood in for the
Lean checker, and Lean has no formal model of it.

A leancompcert artifact narrows that. The artifact is **generated** from a
Lean `Program`; `Program.evalCC_compile` proves the emitted C matches the
`Program`'s semantics; CompCert proves the assembly matches the C.

It does not eliminate the assumption. It replaces one broad modelling
assumption with two machine-checked proofs **plus three narrower operational
ones**, and the honest ledger is:

| | old (Python/FLINT) | new (leancompcert/CompCert) |
|---|---|---|
| C matches the intended computation | assumed | **proved** (`Program.evalCC_compile`) |
| machine code matches the C | assumed | **proved** (CompCert, C → assembly) |
| assembly → object → executable | assumed | assumed (assembler + linker are outside CompCert's theorem) |
| the pinned image runs *that* executable | assumed | assumed, but now **checkable**: the digest is in the compose hash and re-checked inside the TD |
| the CompCert binary itself is the reviewed one | n/a | assumed |

Calling this "one modelling assumption becomes two machine-checked proofs" is
close but not exact. It is more precisely: *the largest and least falsifiable
assumption is discharged; three small, individually falsifiable ones remain.*

The attestation axiom is untouched. `phalaTdxAttestedEmission_sound`
(`SparkInterval/Execution/PhalaTdxOperationalAttestation.lean`) remains the
only attestation axiom on the path and still concludes bytes only — the design
below adds no axiom and weakens no guard.

---

## 2. The current weakness, stated exactly

For `.ch25A7BoundaryV1`, `RegisteredAlgorithm.canonicalDefinition`
(`SparkInterval/Execution/RegisteredAlgorithm.lean:653`) is:

```
sparkinterval.registered-algorithm.v1
name=ternary-goldbach-ch25-lemma-a7-boundary
producer=tg_verifier/a7_flint.py
semantics=pinned-full-flint-arb-boundary-replay-with-rational-box-evidence
source-rectangle=(-3,5)+i(-4,4)-frontier
raw-function=-zeta-prime(s)/zeta(s)-1/(s-1)+1/(s+2)
bound=349/250
retained-artifact-sha256=ccc11cec…9f29
source-realization=external-flint-arb-boxes-contain-mathlib-riemannZeta-expression
output=false-or-true-with-boundary-evidence
```

514 bytes (**M**), whose SHA-256 is `340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa`
— exactly the `algorithmHash` literal at line 596 (**M**, verified by
recomputation).

So `algorithmHash` is the hash of a **description**. The `retained-artifact-sha256`
line does commit to the input *data*; the `producer=` line names the *program*
by file path. Edit `tg_verifier/a7_flint.py` and nothing in Lean changes.
`algorithmHashDiagnosticCheck` (line 615) will still pass.

The registry already contains one entry that does better:
`.h100FormalPtxConstantOneV1` sets `canonicalDefinition :=
h100FormalPtxConstantOnePTX` (line 419) — the generated PTX text itself. The
design below generalises that precedent.

---

## 3. What `canonicalDefinition` should be

The artifact is too large to inline (§5), so it is named by digest. The
emitted definition, produced by `tools/tg_leancompcert_artifact_pin.py`, is:

```
sparkinterval.registered-algorithm.v1
name=mertens-odd-floor-sum
producer=leancompcert
program=MertensCert.oddFloorSum
emitter=lake exe lean-compcert emit-mertens-cert-c
emitted-c-sha256=f61ac686aa8578757a287b75fda43fd0e9e94fe75d982a2d58d962a906a36425
emitted-c-bytes=19397
compcert-version=3.17
compcert-target=aarch64-linux
binary-sha256=f60d51671f7deabcb18a44f3cf173c89a91d4f7f48a1fa7e994732bc5feaeb9c
binary-bytes=639632
link=static
semantics=Program.evalCC_compile
success=exit-status-zero
output=false-or-true
```

**515 bytes** (**M**), `algorithmHash =
4537a62ecd1e8476c0b9197fb25a83935ddb8c66b2351f198e3ce4f870df5c7c` (**M**).

The important number is **515 vs 514**. Replacing "a paragraph naming a Python
file" with "digests of the exact C and the exact executable" costs the Lean
kernel *one extra byte*. Every existing kernel-reduction budget in this repo
survives the change unchanged.

What each line buys:

* `emitted-c-sha256` — the semantic identity. This is what
  `Program.evalCC_compile` is about, and it is the digest a future one-off
  theorem should prove (§5).
* `binary-sha256` — what actually ran. Re-checked inside the TD by
  `run_artifact_campaign.sh` before the artifact is invoked, and checked again
  at image build time.
* `compcert-version` + `compcert-target` — the compiler whose theorem is being
  relied on, and the ISA. Not decoration: a CompCert version bump changes what
  was proved.
* `link=static` — see §6; a dynamically linked artifact makes the campaign's
  behaviour depend on the base image's libc, which is neither in CompCert's
  theorem nor named here.
* `success=exit-status-zero` — the whole reason the entry point is short.

### The chain

```
attested emission of the bytes "true"
  → [phalaTdxAttestedEmission_sound]   image D, algorithmHash A, input I emitted "true"
  → [kernel, cheap, 515 B]             A = SHA256(canonicalDefinition)
  → [reading canonicalDefinition]      canonicalDefinition names emitted-c-sha256 = H
  → [kernel, one-off, EXPENSIVE — §5]  SHA256(artifactC) = H
  → [Program.evalCC_compile]           artifactC realises Program P      ← other agent's half
  → [ordinary Lean]                    P returning 0 implies the claim
```

Only the last-but-two arrow is new work for Lean, and §5 is about whether it
is affordable.

---

## 4. What the campaign image contains

### The honest size answer

The brief's framing — "the campaign image contains the ~70 KB static binary,
not a Python stack" — is right about the *workload* and wrong about the
*image*. The A.7 image is 163 MB and only ~24 MB of that is the analytic
stack:

| layer | size | fate |
|---|---:|---|
| `python:3.10` Debian base | ~134 MB | shrinkable, not removable |
| python-flint 0.9.0 wheel (FLINT/Arb) | ~10 MB | **removed** |
| `tg_verifier/` | 9.48 MB | reduced to `phala_tdx_receipt.py` |
| compiled bytecode | 14.5 MB | **removed** |
| entry point + specs | ~50 KB | kept |
| **CompCert artifact** | **~640 KB static** | **added** |

The attestation half cannot go away. `prelude_phala_tdx_inputs.py` (63,760
bytes) talks HTTP to `/var/run/dstack.sock` to derive the P-256 key and fetch
the quote, runs the pinned `dcap-qvl` musl binary, replays the RTMR3 event
log, and signs with RFC-6979 P-256. None of that is expressible as a
leancompcert `Program` — a `Program` is a closed u64 computation with no I/O,
no sockets, and no key material.

So the realistic image is **50–80 MB (E**, basis: `python:3.10-slim` is ~45 MB
plus ~5 MB of kept sources plus the 640 KB artifact**)**, down from 163 MB. To
actually reach ~1 MB you would have to rewrite the prelude in C as well; that
is a separate project and is **not** what a leancompcert artifact gives you.

### Two services, one changed

The compose keeps its shape. `prelude` is **unchanged**. `campaign` changes in
exactly three ways:

| | A.7 campaign service | leancompcert campaign service |
|---|---|---|
| entry point | `run_phala_tdx_campaign.sh` → `tg_a7_phala_tdx_workload.py` → python-flint | `run_artifact_campaign.sh` → `exec` the artifact |
| required inputs | 6 files incl. `a7_boundary.json` (1.5 MB, fetched over HTTPS via `TG_A7_ARTIFACT_URL`) | 5 files; **no external artifact fetch** |
| `allowed_envs` | `["TG_DCAP_QVL_POLICY_B64", "TG_A7_ARTIFACT_URL"]` | `["TG_DCAP_QVL_POLICY_B64"]` |
| tmpfs | `/workspace/runtime:exec,size=64m` (for the wheel) | not needed |

Dropping `TG_A7_ARTIFACT_URL` is a real security improvement and worth naming:
the A.7 campaign pulls a 1.5 MB artifact over HTTPS from a URL supplied in
encrypted env, and verifies its digest. A leancompcert campaign has no
external input at all — the computation is self-contained in the measured
image.

### The compose diff, concretely

`docker-compose.yaml` is 179,901 bytes, 3,804 lines, of which ~96% is
`prelude_phala_tdx_inputs.py` embedded **twice** as a bash heredoc inside a
YAML block scalar under `entrypoint:` (once per service). That embedding is
deliberate — it puts the sources inside the compose hash and therefore inside
RTMR3.

The change to that file is:

1. In the `campaign` service's `entrypoint:` block, replace the
   `run_phala_tdx_campaign.sh` heredoc (138 lines) with the
   `run_artifact_campaign.sh` heredoc.
2. Add to the `campaign` service's `environment:`
   `TG_ALGORITHM_ID`, `TG_ALGORITHM_HASH`, `TG_PARAMETERS_HASH`,
   `TG_DOMAIN_HASH`, `TG_ARTIFACT_PATH`, `TG_ARTIFACT_SHA256`,
   `TG_ARTIFACT_NAME`.
3. Change both `image:` refs to the new image digest.
4. Delete `TG_A7_ARTIFACT_URL` from `allowed_envs` in `app-compose.json`.

The `campaign` service's `network_mode: none` and `read_only: true` are kept.
They matter more here, not less: a self-contained artifact has no reason to
touch the network at all.

**The artifact digest is NOT a fourth pin.** It is inside the compose text
(step 2), so it is inside `compose_hash`, which is already a receipt field
(`PhalaTdxReceipt.composeHash`) and already pinned
(`PhalaTdxEnclavePin.composeHash`). It is *also* inside `canonicalDefinition`,
so it is inside `algorithmHash`. Those two paths are independent, which is the
point: an operator who swaps the binary must defeat both the compose
measurement and the Lean registry.

---

## 5. MEASUREMENT: can the Lean kernel hash an artifact?

This was the highest-value question in the brief. **The answer is no, and by a
wider margin than the "19 KB is 73× smaller than 1.4 MB" framing suggests.**

`SHA256.digestString` is `digestByteArray text.toUTF8`
(`SparkInterval/Certificate/SHA256.lean:671`). All figures below are
`decide +kernel`, no `native_decide`, prefixes of the real `mertens.c`
artifact, `#print axioms` reporting the base trio in every completed case.

### Measured (M), 2026-07-29

| input | statement | user CPU | peak RSS | Δ over baseline |
|---:|---|---:|---:|---|
| — | import only | 2.64 s | 6.27 GB | baseline |
| 8 B | `digestString` | 2.66 s | 6.55 GB | +0.02 s, +0.28 GB |
| 64 B | `digestString` + `utf8ByteSize` | 4.07 s | 6.80 GB | +1.43 s, +0.53 GB |
| 256 B | `digestString` + `utf8ByteSize` | 9.07 s | 8.13 GB | +6.43 s, +1.86 GB |
| 512 B | `digestString` only | 24.46 s | 11.00 GB | +21.8 s, +4.73 GB |
| 1024 B | `toUTF8` **only** (`.size = 1024`) | 23.83 s | 10.20 GB | +21.2 s, +3.93 GB |
| 1024 B | `digestString` + `utf8ByteSize` | 92.34 s | 22.02 GB | +89.7 s, +15.75 GB |
| 2048 B | `digestString` only | **did not complete in 2,885 s** | **46.9 GB** | terminated by me to free the host |

The 2048-byte row is the important one. It ran for **48 minutes**, peaked at
**46.9 GB resident**, and had still not produced a result when I killed it —
against a 512-byte run that finished in 24 s at 11.0 GB. Four times the input,
more than 120× the time, and it did not finish.

### What the numbers say

1. **It is superlinear.** From 256 B to 1024 B (4×) the time rises 14× and the
   memory 8.5×: an exponent of ~1.9 in time and ~1.5 in memory.

2. **`String.toUTF8` is roughly a quarter of it and is itself the fixed
   overhead.** At 1024 bytes, `toUTF8` alone costs 21.2 s and 3.93 GB. A Lean
   string literal has to be unfolded to a `List Char`, and every `Char` is a
   structure carrying a validity proof. That is ~4 MB of kernel term per
   input byte before any SHA-256 round runs.

3. **Extrapolating to 19,397 bytes** (**E**, basis: the 256 B → 1024 B fit,
   exponents 1.90 time / 1.54 memory, applied to the 1024 B point):

   * time ≈ 89.7 s × 19^1.90 ≈ **6.7 CPU-hours**
   * memory ≈ 15.75 GB × 19^1.54 ≈ **1,470 GB**

   Even a purely linear extrapolation from 1024 B — which the data does not
   support and which is a generous lower bound — gives **1,700 s and 300 GB**.
   The host has 119 GB. This is not a "needs a bigger machine" gap.

4. **Even a 2 KB rolled artifact is out of reach.** I had expected rolled
   emission (~2,074 bytes, §7) to rescue the idea, since rolled artifacts are
   the ones that matter for large computations. It does not: the 2048-byte
   probe reached 46.9 GB after 48 minutes without completing. For calibration,
   the repo's existing hardest kernel reduction — the *entire* prod5
   acceptance check, nineteen SHA-256 evaluations plus P-256 ECDSA — is
   1,209 s at 42.9 GB (`proof_build/ch25_a7_phala_tdx/prod5_kernel_full_check.lean`).
   Hashing one 2 KB artifact costs more than that.

### Consequence for the design, and it is a good one

"Which binary ran" **cannot** become a theorem by direct kernel hashing.
But the design in §3 does not need it to, because:

* `canonicalDefinition` is **515 bytes**, one byte more than the paragraph it
  replaces. Kernel-hashing it costs what the repo already pays.
* It contains `emitted-c-sha256` and `binary-sha256` as literals.

So the binding is: `algorithmHash` (kernel-checked, cheap) → the artifact
digests (literals) → the artifact. The last arrow is where the pasted literal
still lives. It is one 64-hex string that a reviewer checks with `sha256sum`,
against an artifact that is deterministically regenerable from a Lean
`Program` — which is a far smaller and more mechanically checkable object than
"a paragraph describing a Python file".

**What would close it properly.** SHA-256 is Merkle–Damgård, and the module
already has the right shape: `compressFrom : State → (Nat → Nat) → State`
(line 158) and `hashSource` (line 510) folding it over blocks via
`foldSourceBlocks`. A chunked proof — block-state at 512-byte boundaries
proved in *separate compilation units*, then composed — would make the cost
linear in files rather than superlinear in one process, because Lean does not
return kernel working memory to the allocator within a file but does between
processes. The missing piece is a `foldSourceBlocks` splitting lemma; it does
not exist today. At the measured 512-byte rate (21.8 s, 4.73 GB) a 19,397-byte
artifact would be **38 files, ~14 CPU-minutes, ~5 GB each** — entirely
affordable. **This is the single highest-value follow-on task in this whole
area**, and it is a Lean lemma, not a hardware problem.

---

## 6. Blockers found by trying it (the "does not actually work" section)

Everything in this section is **M**, found today by running the tools.

### 6.1 The artifact is not static, and it is not x86_64

`ccomp -I…runtime/include -I$(lean --print-prefix)/include -o out mertens.c`
gives a **70,504-byte, dynamically linked, aarch64** ELF. Not static. With
`-static` it is **639,632 bytes** (537,664 stripped) because it pulls in
glibc. So:

* the "~70 KB" figure is the *dynamic* binary. A genuinely self-contained
  artifact is **~640 KB**, or ~100 KB against musl (**E**, not tried — no musl
  toolchain here).
* **Intel TDX is x86_64. This host's CompCert is configured `arch=aarch64`.**
  `ccomp -target x86_64-linux` fails with "Cannot find compcert.ini
  configuration file" — a CompCert install serves exactly one target.
  **No artifact that can run in a Phala TDX CVM can currently be built on
  this machine.** `build_artifact.sh` refuses on this mismatch rather than
  producing an artifact that cannot run.

  This is the one hard blocker on "ready to run". Fix: a second CompCert built
  with `./configure x86_64-linux` plus an x86_64 gcc for assembling and
  linking. Not difficult; just not done, and not doable without touching a
  toolchain install.

### 6.2 The emitted C is not standalone

Every emitted artifact begins:

```c
#include <stdint.h>
#include <stddef.h>
#include <lean/lean.h>
```

It makes **zero** `lean_*` calls (**M**, `grep -c lean_ mertens.c` = 0 after
removing the include line) but the include is still there, which is why the
`ccomp` line needs `-I$(lean --print-prefix)/include`. I removed the line and
recompiled: **70,504 bytes, exit 0** — byte-identical size, works fine
(**M**). The include is spurious. `build_artifact.sh` strips it and refuses if
any real `lean_*` call survives. Worth fixing in the emitter.

### 6.3 `main` returns 1 on failure, and the receipt must not call that `false`

`int main(void) { return l_MertensCert_oddFloorSum() == UINT64_C(192509) ? 0 : 1; }`
— confirmed self-checking (**M**). But exit statuses other than 0 and 1
(signals, OOM, missing loader, a `ccomp` runtime abort) must not be mapped to
`false`: emitting `false` asserts that the artifact *ran and disagreed*.
`run_artifact_campaign.sh` refuses on any other status rather than signing a
verdict it did not observe. This is a small thing that would have been a
soundness hole.

### 6.4 Not everything can be a `Program`

The A.7 campaign is FLINT/Arb ball arithmetic at 128 bits with FFTs. A
leancompcert `Program` is closed u64 arithmetic. The A.7 campaign is
**not** migratable to this architecture without reimplementing interval
arithmetic in u64 — which is a research project, not a port. The same applies
to Platt–Trudgian (§9, 128-bit Arb, FFT length 131072). The architecture fits
the *integer* corpus (sieves, folds, ladders, fixed-point rationals), which is
1,371 of the 1,371 `native_decide` atoms but **not** the two biggest external
atoms.

---

## 7. Cost model

### Pricing basis (given, treated as **M**)

* `tdx.large` (4 vCPU, 8 GB) = **$0.232/hour** = $0.0038667/active-minute
* storage $0.000139/GB/hour, **billed while stopped** → always destroy, never stop
* billed per active minute, no minimum, no subscription
* LEVEL_1 caps: 8 instances, **16 vCPU total**, 16 GB memory each, 80 GB disk each
  → with `tdx.large` at 4 vCPU, **at most 4 concurrent CVMs**
* measured bring-up: ~10 CVM deployments cost **$0.145 total**
  → **provisioning floor ≈ $0.0145 and ≈ 3.75 active-minutes per deployment**

Everything short is dominated by that floor. Call it **$0.0145 / 4 minutes**.

### Native throughput basis

| rate | value | basis |
|---|---|---|
| rolled fixed-point body (22 instr) | **1.31 ns/iteration** | M (leancompcert bench, 13.67 ms at 10⁷) |
| RS62 ladder body (20 instr), word-safe | **8.54 ns/iteration** | M (rs62_compcert.csv, marginal 10⁶→10⁷) |
| process start + exit | **< 0.2 ms** | M (today) |
| `ccomp` compile | ~50 ms + 1.2 ms/KB of C | M |

**Caveat on every native figure**: measured on aarch64. Phala TDX is x86_64,
and TDX adds memory-encryption overhead. Treat all CVM runtimes as ±2×.

### The table

| # | computation | elements | native runtime | basis | CVM wall | cost |
|---|---|---:|---:|:--:|---:|---:|
| 1 | mertens odd-floor-sum (unrolled) | 99 | 0.21 ms | **M** | 4 min (floor) | **$0.0145** |
| 2 | rolled fixed-point checker | 10⁷ | 13.3 ms | **M** | 4 min (floor) | **$0.0145** |
| 3 | all 7 committed native certs, batched | — | **30 ms total** | **M** (today) | 4 min (floor) | **$0.0145** |
| 4 | RS62 full anchor sweep | 3.24×10⁸ | 2.77 s | **E** (8.54 ns/iter M) | 4 min (floor) | **$0.0145** |
| 5 | **entire 1,371-atom native_decide corpus, batched** | 9.62×10⁸ steps | **1.3–8.2 s** | **E** (1.31–8.54 ns/step M) | 4 min (floor) | **$0.0145** |
| 5b | same, one CVM per atom | | | | 22.9 h | $19.88 |
| 6 | the 4 table-streaming atoms | 3.6×10⁸ cells | ≤ 60 s | **E** (numpy replay 13.65 s M for the largest) | 5 min | **$0.0193** |
| 7 | CH25 A.7 (today's campaign) | 16,191 leaves | 1.6 s | **M** | 4 min (floor) | $0.0145 |
| 8 | Platt–Trudgian RH to 3×10¹² | 2.966×10⁹ windows | 3.22×10⁸ s **GPU** | **E** (GB10 9.2 win/s M) | see §9 | **≥$20,800**, wrong hardware |
| 9 | Helfgott–Platt Thm 4.1 | 2.0×10¹⁸ items | 40,000 core-h | **M** (paper) | **104 days** | **$2,348** |
| 10 | Goldbach 10²⁷ | 1.5625×10¹⁶ evens | 2.03×10⁷ s **GPU** | **M** (GB10 7.695×10⁸ ev/s) | see §9 | GPU: n/a on CPU TDX |

Row 5 is the headline: **the entire corpus that motivated this architecture is
one CVM and 1.5 cents.** Row 6 is the second headline: **the four atoms the
Lean kernel can provably never do cost 1.9 cents attested.**

Row 5b is the measured optimisation that matters (§10): batching is 1,371×
cheaper and 340× faster than per-atom CVMs, and the basis is row 3 — seven
independent artifacts ran back to back in 30 ms, so per-artifact overhead is
irrelevant and provisioning is everything.

Storage is negligible for anything at the floor (20 GB × 4 min =
$0.0000185). It is **not** negligible for row 9: 4 instances × 20 GB ×
2,496 h × $0.000139 = **$27.76**, which is why row 9 reads $2,348 not $2,320.

---

## 8. Enclave-readiness, per computation

"Ready to run" means: emit → ccomp → package → deploy without re-deriving
anything. Status today:

| stage | status | what is missing |
|---|---|---|
| emit | **ready** | 9 `emit-*` commands exist; artifacts are byte-reproducible |
| ccomp (aarch64) | **ready** | measured, 0.06 s user, exit 0 |
| **ccomp (x86_64)** | **BLOCKED** | no x86_64-configured CompCert on this host (§6.1) |
| standalone C | **ready** | `build_artifact.sh` strips the spurious `lean/lean.h` (§6.2) |
| pin derivation | **ready** | `tools/tg_leancompcert_artifact_pin.py`, run against the real artifact |
| campaign image | **written, unbuilt** | needs the reviewed Debian-slim digest and an x86_64 artifact |
| entry point | **written, untested** | `run_artifact_campaign.sh`; no local dry run yet |
| compose/manifest | **specified, not generated** | `tools/tg_phala_tdx_compose.py` needs a `--campaign-entry` switch to emit the artifact variant |
| Lean registry entry | **not written** | a new `RegisteredAlgorithm` constructor + `canonicalDefinition` + `algorithmHash` + `Runs` equation; the pin tool prints all three |
| Lean bridge | **other agent's half** | `Program.evalCC_compile` → the mathematical claim |
| local dry run | **not done** | the A.7 path has `tests/test_phala_tdx_first_run.py` with a mock dstack socket; the artifact variant needs the same |

Ordered list of what to do next:

1. Install an x86_64 CompCert. Nothing downstream can be validated without it.
2. Add the `--campaign-entry` switch to `tools/tg_phala_tdx_compose.py`.
3. Mirror `tests/test_phala_tdx_first_run.py` for the artifact image (mock
   dstack `GetKey` socket, verify the receipt is byte-reproducible).
4. Write the `foldSourceBlocks` splitting lemma (§5). This is the one that
   turns "which binary ran" into a theorem.
5. Only then deploy. One CVM, ~$0.015.

---

## 9. The super-slow set

### 9.1 `finite_check_platt_trudgian_rh_zeta_3e12`

`ext/analytic_nt/AnalyticNT/Chebyshev/PlattTrudgianRH.lean:76`, RH up to height
`3,000,175,332,800`.

* **2.966×10⁹ windows** (height step 1008). Per window: Arb ball arithmetic at
  **128 bits**, FFT length 131,072, 768,000 Dirichlet terms, 25,741
  double-double disks.
* Measured rate: **9.2 fused windows/s on one GB10** (`tg_verifier/platt_h100_campaign.py:120`).
  → 3.22×10⁸ s = **3,731 GB10-days on one GPU**.
* Shardable: **yes, perfectly** — windows are independent.
* Under LEVEL_1: irrelevant. This is a **GPU** workload with 128-bit interval
  arithmetic. It is not expressible as a leancompcert u64 `Program` (§6.4) and
  Phala CPU TDX is the wrong hardware.
* Pricing those GPU-hours at `tdx.large` rates gives **$20,777** — a
  meaningless lower bound, since a CPU would be 10–100× slower again.
* **Verdict: infeasible on CPU TDX. Needs confidential GPU. Do not budget for
  it in this architecture.**

### 9.2 `helfgott_platt_theorem_4_1_source`

`Math/Problems/TernaryGoldbach/Statement.lean:61`, threshold
`8,875,694,145,621,773,516,800,000,000,000`.

**Correction to the brief**: this is *not* 8.875×10³⁰ units of work. The
verification is a covering argument — binary Goldbach for every even through
4×10¹⁸, then every odd target covered by a checked prime-ladder interval with
Proth/Pocklington evidence. Actual work: **2.000000000000493×10¹⁸ items**
(2×10¹⁸ evens + 492,700 ladder ranges). That is 4.4×10¹² times less than the
naive reading.

* Measured cost of the original: **~40,000 core-hours** (Helfgott–Platt).
* At LEVEL_1 (4 × `tdx.large` = 16 vCPU): 40,000 / 16 = 2,500 h = **104 days wall**.
* Cost: 4 × 2,500 h × $0.232 = $2,320 compute + $27.76 storage = **$2,348**.
* Shardable: **yes** — 492,700 independent ladder ranges, and the binary sweep
  splits arbitrarily. 8 instances would help only if a 2-vCPU SKU exists;
  16 vCPU is the real cap.
* **Verdict: the one super-slow item that is genuinely budgetable. ~$2,350 and
  ~3.5 months, or proportionally less if the vCPU cap is raised.** Note the
  per-range data files from the original run were deleted, so this is a
  re-run, not a replay.

### 9.3 Goldbach 10²⁷

* **1.5625×10¹⁶ evens**, 65,536 shards, 8,192 H100 groups, 7,106 ladder ranges.
* Measured: **7.695×10⁸ evens/s on GB10** → 2.03×10⁷ s = **235 GB10-days**;
  projected 8×H100 wall 5.9–29.4 days (**E**, explicitly "not an H100
  measurement, no production branch has run").
* CPU route: the repo states plainly that the lowered binary verifier is CUDA
  and **has no calibrated CPU route**.
* CPU estimate (**E**, weak — basis: 1.31 ns per 22-instruction body × ~8
  bodies per even for a bitset check): ~10.5 ns/even/core → 4.1×10⁷ s on
  4 vCPU = 11,390 instance-hours = **~$2,650**, **119 days** wall on 4 CVMs.
  Uncertainty is ≥10× in both directions. Do not budget from this number
  without a calibration run — which costs $0.0145 and would settle it.
* **Verdict: plausibly affordable in dollars, implausible in wall time, and
  currently unmeasured on CPU. The cheapest next action is a one-CVM
  calibration shard.**

### 9.4 The "5 infeasible atoms" — actually 4

`PrimeLogSquare219.check_prime_log_square_2_19_full` **no longer exists**: it
was migrated to an ordinary kernel proof
(`ext/tg_native_certificates/TGNativeCertificates/PrimeLogSquare219Cert.lean:25`,
`exact …PrimeLogSquare219Ordinary.finite_check`, no `native_decide`). The
manifest row and the migration cost report are stale on that row.

The live four:

| atom | arrays | kernel verdict | native |
|---|---|---|---|
| `Ramare.MStar140MCert.full_run` | 1 × `Array ℕ` + 3 × `Array Int`, each 1.4×10⁸ | "40+ min, never completed"; axiomatised out | **13.65 s** measured (numpy replay) |
| `Ramare.Finite100M.check_first_mertens_100m_full` | `Array ℕ`, 10⁸ | ">300 s"; axiomatised out | ≤ 20 s (**E**) |
| `Ramare.Lemma71.check_lemma71_100m_full` | `Array ℕ` 10⁸ + 10⁴ pairs | ">300 s, 25 min still going"; axiomatised out | ≤ 20 s (**E**) |
| `WeightedMoment217.check_weighted_moment_2_17_full` | `factorTable` 1.9×10⁷ | no recorded time | ≤ 3 s (**E**) |

The kernel's own verdict is 17 days and 240 TB *per atom* — and that estimate
is described in the cost report as "a wild under-estimate", because kernel
`Array.get` reduces through the list model, making it Ω(N²).

* **Memory is the only real constraint.** MStar140M holds four arrays of
  1.4×10⁸ entries. At 8 bytes that is 4.5 GB, which does not fit comfortably
  in `tdx.large`'s 8 GB alongside the OS. Two options: provision at the
  LEVEL_1 16 GB ceiling (SKU price not supplied — **flag for budgeting**), or
  narrow the three `Int` arrays to 32-bit, giving 2.24 GB, which fits
  `tdx.large` with room. A leancompcert `Program` chooses its own widths, so
  the narrowing is free at authoring time.
* **All four in one CVM: ≤ 60 s of compute, $0.0193.**
* **Verdict: this is the architecture's best case. The computations the Lean
  kernel can provably never perform are the ones that are trivially cheap
  attested.** Migration cost is authoring four `Program`s, not compute.

---

## 10. Optimisation: what pays, measured

I did not find a new code-level lever, and I am not going to invent one. What
I did measure:

**Batching (new, M, today).** All seven committed native certificates,
compiled and run back to back: **0.03 s user, total**. Individually: 0.18–0.21 ms
each except `rolled-10m` at 10 ms (10⁷ iterations, 1.3 ns/iter — matches the
recorded 13.3 ms within load noise). Process start is under 0.2 ms.
Consequence: **per-CVM provisioning is 100% of the cost of anything under a
minute**, so the optimisation is to batch every atom into one CVM run.
Before/after: 1,371 per-atom CVMs = $19.88 and 22.9 h wall; one batched CVM =
$0.0145 and 4 min. **1,371× cheaper, 340× faster.**

**Standalone-C fix (new, M, today).** Removing the spurious
`#include <lean/lean.h>` — artifact still compiles and runs, exit 0, same
70,504 bytes. Removes the Lean-headers build dependency entirely.

**Existing measured levers, for reference (M, leancompcert bench):**

| rewrite | before | after | ratio |
|---|---:|---:|---|
| `minFac` sweep to 10⁷ → SPF sieve | 1.791 s | 0.058 s | **31× faster** |
| integer sqrt, fixed 6 Newton steps | 0.310 s | 0.093 s | **3.3× faster** |
| RS62 word-safe increments (native) | — | 8.54 ns/iter | enables u64 at all |

The first row applies **directly to all four table-streaming atoms** (§9.4) —
they are SPF-sieve shaped. Worth taking.

**Levers that measurably do not pay** (M, same source), recorded so nobody
retries them: predicated trial division **9.7× slower**; fixed 192-round
binary gcd **7.6× slower**; poison-flag fold instead of early exit **1.5×
slower**.

**And one counter-intuitive one**: the RS62 word-safe rewrite is **23% *worse*
in the Lean kernel** (153 → 188 µs/iteration, M). It is worth doing only
because it makes the fold expressible in u64 at all — i.e. only on the native
side. Do not read it as a general speedup.

---

## 11. Constraint compliance

* No `sorry`, no `native_decide` introduced. All probe theorems in §5 closed
  with `decide +kernel`; `#print axioms` reported
  `[propext, Classical.choice, Quot.sound]` on every completed one.
* No existing guard weakened. `ch25A7BoundaryProductionV1` stays unpinned;
  `ch25A7BoundaryPhalaTdxCheck_eq_false` and
  `ch25A7BoundaryProductionV1_publicKey_unpinned` are untouched. A
  leancompcert campaign is a **new** `PhalaTdxEnclave` constructor and a
  **new** `RegisteredAlgorithm` constructor, not an edit to an existing one.
* `phalaTdxAttestedEmission_sound` remains the only attestation axiom on the
  path and still concludes bytes only. Nothing above adds an axiom.
* No CVM created, no credits spent.
