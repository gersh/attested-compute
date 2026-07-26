# Finite Goldbach campaign below the `10^27` analytic crossover

Status: **UNRUN** as of 2026-07-22. This repository contains the exact
producer, replay, reduction, and Lean semantic boundary, but it contains no
production branch aggregate, Azure attestation, or accepted finalizer receipt.

This is a new versioned campaign. It does not mutate, weaken, or masquerade as
the historical Helfgott--Platt computation described in
[`GOLDBACH_LADDER_CAMPAIGN.md`](GOLDBACH_LADDER_CAMPAIGN.md).

## Exact claim split

The finite theorem target is

```text
every odd n with 7 <= n <= 10^27 is a sum of three primes.
```

The two independently replayed branches are:

```text
binary Goldbach: every even e in [4, 31_250_000_000_000_000]

prime ladder:
  Proth exponent       = 45
  range width          = 2^47 * 10^9
                       = 140_737_488_355_328_000_000_000
  range count          = 7_106
  scheduled endpoint   = 7_106 * (2^47 * 10^9)
                       = 1_000_080_592_252_960_768_000_000_000
  maximum gap          = 31_250_000_000_000_000
  endpoint tolerance   = 15_625_000_000_000_000
```

The scheduled endpoint is deliberately above `10^27`. The Lean theorem
[`Goldbach10Pow27SourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/Goldbach10Pow27SourceSemantics.lean)
proves, using only the ordinary kernel-checked reduction, that the complete
binary claim and checked ladder imply the target through `10^27`.

The selected gap is a production guard, not an assumed theorem about prime
gaps. Each ladder range fails closed if the Proth producer cannot provide the
next rung. The existing exact Pocklington/external-certificate route may close
such a hole; it may not turn probable-prime evidence into a rung.

## Production commands

The planning and structural-inspection commands below may run locally.
Producers, arithmetic replayers, `combine`, and the finalizer require measured
Azure worker scope. A small `--group-count` or checkpoint count does not turn a
production leaf into a local KAT.

Print the small, human-readable schedule:

```bash
python3 tools/tg_goldbach_10pow27_campaign.py --pretty plan
```

Create the exact 65,536-leaf H100 plan after preparing and building the pinned
GoldbachGPU source closure:

```bash
python3 tools/tg_goldbach_gpu_campaign.py create-analytic-10pow27-plan \
  --source-root /data/goldbach-gpu-hardened \
  --executable /data/bin/goldbach \
  --executable-sha256 SHA256 \
  --out /data/tg10pow27/binary-plan.json
```

Run `run-group`, `aggregate`, and `verify` with the ordinary GoldbachGPU tool.
The plan parser pins the lowered algorithm ID and rejects both a bounded sample
and the historical `[4,4e18]` plan.

There is also a distinct, unregistered optimized route:

```bash
python3 tools/tg_goldbach_gpu_campaign.py \
  create-optimized-analytic-10pow27-plan \
  --candidate-package-root /data/goldbach-gpu-optimized \
  --candidate-manifest-file-sha256 \
    "$OPTIMIZED_CANDIDATE_MANIFEST_FILE_SHA256" \
  --source-root /data/goldbach-gpu-optimized/source \
  --executable /data/goldbach-gpu-optimized/artifacts/goldbach-gpu \
  --executable-sha256 SHA256 \
  --out /data/tg10pow27/optimized-binary-plan.json
```

It uses the reviewed complete source identity
`8c19bf2825ff8a34ef9413f35620487f2062868f723b158228a071a5cf021359`.
Plan creation revalidates the complete qualified package, including its
source and target artifact commitments. It also requires the exact canonical
manifest file digest to occur in the source-reviewed production allowlist;
that allowlist is empty until an Azure x86_64/SM90 package is reviewed, so
this post-review command currently fails closed.
The same `run-group`, `aggregate`, and `verify` commands validate that exact
identity. After both branches exist, `combine-optimized` performs the complete
external replay. Its result is explicitly unregistered and cannot enter the
currently registered v1 finalizer, which remains pinned to the prepared base
source:

```bash
python3 tools/tg_goldbach_10pow27_campaign.py combine-optimized \
  /data/tg10pow27/ladder \
  --ladder-aggregate /data/tg10pow27/ladder-aggregate.json \
  --binary-plan /data/tg10pow27/optimized-binary-plan.json \
  --binary-receipts-dir /data/tg10pow27/optimized-binary-receipts \
  --binary-aggregate /data/tg10pow27/optimized-binary-aggregate.json \
  --out /data/tg10pow27/optimized-combined.json
```

Initialize and produce the CPU ladder:

```bash
python3 tools/tg_goldbach_10pow27_campaign.py init-ladder \
  /data/tg10pow27/ladder

python3 tools/tg_goldbach_ladder_native.py produce-group \
  /data/tg10pow27/ladder \
  --runner /data/bin/sparkinterval-tg-goldbach-ladder-native \
  --group-index GROUP --group-count GROUPS --local-workers WORKERS

python3 tools/tg_goldbach_campaign.py reduce-ranges \
  /data/tg10pow27/ladder --out /data/tg10pow27/ladder-aggregate.json
```

The native protocol commits `proth_exponent=45`. Python independently checks
every exact Jacobi/modular-power witness and records it as generic `proth`
evidence. Historical exponent-52 wire records retain the `proth52` tag.

Finally replay and bind both aggregates:

```bash
python3 tools/tg_goldbach_10pow27_campaign.py combine \
  /data/tg10pow27/ladder \
  --ladder-aggregate /data/tg10pow27/ladder-aggregate.json \
  --binary-plan /data/tg10pow27/binary-plan.json \
  --binary-receipts-dir /data/tg10pow27/binary-receipts \
  --binary-aggregate /data/tg10pow27/binary-aggregate.json \
  --out /data/tg10pow27/combined.json
```

This combined JSON is still unattested and does not enter Lean by itself. The
closed measured finalizer is:

```bash
python3 tools/tg_goldbach_10pow27_finalizer.py \
  /data/tg10pow27/ladder \
  --ladder-aggregate /data/tg10pow27/ladder-aggregate.json \
  --binary-plan /data/tg10pow27/binary-plan.json \
  --binary-receipts-dir /data/tg10pow27/binary-receipts \
  --binary-aggregate /data/tg10pow27/binary-aggregate.json \
  --combined-out /data/tg10pow27/combined.json \
  --registered-result-output /data/tg10pow27/registered-result.txt
```

It immutably writes the exact bytes `true` (and prints `true` for an operator
log) only after replaying both branches. The Azure measured
runner must bind that executable and its immutable input/archive hashes to a
SEV-SNP CPU run, appraise the evidence, sign the trusted-compute receipt, and
admit it with registered invocation `goldbach10Pow27ProductionV1`.

The source importer in `tools/generate_trusted_compute_lean.py` validates the
literal registered algorithm/input/parameter/domain hashes and generates an
application theorem. The closed bridge
[`RegisteredGoldbach10Pow27Certificate.lean`](../../SparkInterval/Execution/RegisteredGoldbach10Pow27Certificate.lean)
then exposes
`Goldbach10Pow27SourceSemantics.SourceClaim`. Its only project axiom is the
same named `accepted_run_certificate_sound` axiom used by the other registered
trusted-compute runs. It cannot be confused with
`helfgottPlattGoldbachProductionV1`, whose algorithm ID, input, parameter,
domain, and proposition are all different.

The main v3 cluster manifest includes this as the separate workload
`goldbach-finite-below-10pow27` and emits its eight-phase manual DAG. The Azure
semantic inventory stages the exact invocation/theorem/result-path tuple with
`enabled:false`. This makes the work visible to the portfolio while preserving
the release gate. All seven CPU phase groups now have closed, source-reviewed
materializers and signed-predecessor handoff packages, but the current plan
still reports `semantic_binding_disabled` and a failed production budget gate
rather than treating the unrun campaign as evidence.

The CPU materializer is
`tools/tg_azure_cpu_goldbach_10pow27_materializer.py`. It fixes all 326 CPU
jobs: plan creation, ladder initialization, 320 ladder worker groups, binary
aggregation, binary replay, ladder reduction, and the measured finalizer. Each
operational job returns a signed JSON result that pins a deterministic retained
archive. A successor rechecks the predecessor signature, exact algorithm
identity, archive hash, archive tree, and mathematical contents inside the
measured VM. The H100-to-CPU packager in
`tools/tg_goldbach_10pow27_azure_measured_workload.py package-h100` accepts
only the eight plan-prescribed leaf receipts whose hashes occur in the signed
H100 group result.

The H100 branch now has a closed factory and materializer for all 8,192 CUDA
groups. Each group adopts the exact portfolio challenge, builds the pinned
`sm_90` executable from the reviewed source closure, refuses the build unless
its hash equals the signed predecessor plan, runs exactly eight strided
leaves, and retains a deterministic eight-receipt archive inside the measured
certificate package. The H100 receipt is operational only: it cannot generate
a Lean review candidate. The CPU aggregate independently compares every
retained leaf receipt with the hashes in the signed H100 result.

The operator site format is
`schemas/azure-cpu-goldbach10pow27-materializer-site.schema.json`; a redacted
template is in
`examples/trusted-compute/azure_cpu_goldbach10pow27_materializer_site.redacted.json`.
The site may select only the pinned GMP source tree, the exact hardened
Goldbach source/binary identity, and content-pinned predecessor exports. It
cannot supply a workload command. The supplied Goldbach binary is copied only
as plan identity data and is never executed by a CPU phase; the only native
CPU producer is built from the pinned GMP and ladder sources.

The corresponding H100 site format is
`schemas/azure-h100-goldbach10pow27-materializer-site.schema.json`, with a
redacted template at
`examples/trusted-compute/azure_h100_goldbach10pow27_materializer_site.redacted.json`.
Materialize a group with
`tools/tg_azure_h100_goldbach_10pow27_materializer.py`. Its manifest names the
exact retained-export path inside the returned certificate package.
After a group has run and its HSM receipt has been returned, the same tool's
`export` subcommand verifies the receipt, replays the exact eight retained leaf
receipts against the signed result and production plan, and copies a
content-pinned archive for the CPU aggregation phase.  This post-run handoff is
operational evidence only; it does not by itself discharge a Lean theorem.

## Runtime projection, not a benchmark

Using the retained GB10 measurement of `769,526,000` evens/second as the
one-GPU baseline, the `15,624,999,999,999,999`-even binary branch projects to:

| H100 throughput relative to GB10 | Eight-H100 wall time |
|---:|---:|
| `1x` | `705.02 h` (`29.38 d`) |
| `2x` | `352.51 h` (`14.69 d`) |
| `5x` | `141.00 h` (`5.88 d`) |

The one-week objective therefore requires about `4.20x` the measured GB10
throughput on each of eight H100s. This has not yet been calibrated on an H100
and must not be presented as a measured runtime.

The reviewed hardening patch now assigns every odd prime through `2039` to the
race-free word-owner kernel; the global atomic sieve starts with the next
prime.  A paired 2026-07-22 GB10 test used the same terminal
`600,000,000`-even range and seven warm runs per executable.  The previous
through-`1021` source had a `0.858128 s` median (`699,196,390` evens/s); the
through-`2039` source had a `0.823758 s` median (`728,369,254` evens/s), a
`4.17%` relative rate improvement.  A post-integration run of the exact
source-pinned closure took `0.816990 s`, and every run reported zero phase-2
fallbacks.  Other repository work was active during this paired test, so the
table deliberately retains the earlier absolute baseline and does not
compound the relative gain into an H100 estimate.  The exact active source
identity is
`9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55`.
A same-range Nsight Systems capture attributed `348.064 ms` to the remaining
global-atomic sieve, `244.002 ms` to phase 1, `13.395 ms` to word-owner
initialization, and `5.418 ms` to result counting.  This makes the remaining
atomic sieve the measured optimization target; it does not establish how the
kernel will partition time on an H100.

The bounded cutoff optimizer is
`tools/benchmark_goldbach_word_owner.py`.  It accepts only an already
source-pinned prepared tree, verifies that the compile-time calls are exactly
the increasing odd primes through the declared cutoff, and moves the cutoff
and global-tail offset together.  Each candidate is rebuilt and run over the
same terminal 600-million-even range above; a timing is retained only when the
exact range, count, success sentence, and zero-fallback result all match.
`GoldbachWordOwnerSieve.lean` proves that the complementary prime-prefix/tail
split clears exactly the candidates cleared by the unsplit base-prime list.
This is an optimization aid, not production evidence: selecting a new cutoff
still requires review, a new hardened-source identity and executable pin, an
H100 calibration, and a fresh production admission.

`tools/benchmark_goldbach_warp_tail.py` evaluates a second checked prototype.
It retains one-thread-per-word initialization, assigns a complete 32-lane warp
to each of the longest remaining prime progressions, and retains the reviewed
one-thread-per-prime atomic tail above a second cutoff.  Lane `l` handles
progression terms congruent to `l` modulo 32, with explicit subtraction-form
overflow guards.  `threeTierClearedBy_iff` proves that this three-way work
partition has the same logical clear set as the unsplit base-prime list.  As
with the cutoff sweep, output equality on the bounded benchmark is a
regression check rather than a proof that CUDA implements the Lean model.

`GoldbachTailProgression.lean` now proves the source-facing arithmetic that
was previously separate from that partition theorem. Its exact guarded start
model follows the CUDA ceiling, parity-successor, square, and upper-return
branches. Bounded completeness proves that an in-window odd multiple above
`p²` survives those guards, reaches an exact sequential index or warp
lane/round, and names a live packed bit; the relevant start and warp stride
fit in 64 bits. It also proves the source `first & 1` parity branch matches
the model's evenness predicate. `GoldbachWarpLaunchIndexing.lean`
additionally proves the
literal 256-thread launch gives every retained prime/lane pair one unique
owner, including the rounded last block, and proves the launch arithmetic
fits its fixed-width fields; it also proves the source `& 31` mask equals
remainder modulo 32. The remaining boundary is compiled
register/instruction realization, pointer addressing, prime-buffer identity,
and atomic realization.

The stronger bounded KAT is
`gpu/platform/h100/h100_tg_goldbach_warp_tail_kat.cu`, invoked by
`tools/run_goldbach_warp_tail_kat.py`.  It compares the warp/tail prototype
bit-for-bit against both the reviewed one-thread-per-prime CUDA kernel and an
independent CPU progression replay.  Four 262,144-odd windows exercise the
`p^2` boundary, the production numerical scale, and an overflow edge whose
last candidate is `UINT64_MAX`.  The runner pins the source, compiler, binary,
geometry, cutoffs, per-window bit counts, and full-word hashes.  This remains
a bounded KAT, not source-scale evidence or compiler/ISA refinement.

On 2026-07-25 a paired confirmation used two warmups and seven timed runs for
each source on the same GB10 and exact 600-million-even terminal range.  The
unchanged through-2039 source had median `0.616505 s`; the through-2039 plus
warp-through-32749 prototype had median `0.585628 s`, a `5.27%` rate
improvement.  A combined through-4093 plus warp-through-32749 build was
slightly slower at `0.587662 s`.  All 21 timed candidate/baseline runs
reported the exact range, exact count, success sentence, and zero phase-2
fallbacks.  The four-window bit-for-bit KAT then matched both comparison
implementations, including its `UINT64_MAX` endpoint, and CUDA Compute
Sanitizer reported zero memory errors.  These are GB10 measurements of an
unpromoted prototype; they do not update the H100 projection table or the
reviewed production source identity.

The next integrated prototype,
`tools/benchmark_goldbach_shifted_coverage.py`, reuses the exact packed q
window produced by that sieve and applies the already-formalized shifted-word
Goldbach equation to phase 1.  It retains the original per-even kernel for
the low boundary segment where every odd-p alignment is not yet nonnegative,
adds an explicit zero carry word for unaligned final loads, and expands the
packed result only for compatibility with the existing CPU-fallback path.
The source transformer fails unless every allocation, padding, phase-1, memory
accounting, and cleanup insertion point is unique.

The same transformer has a diagnostic crosscheck mode.  It computes the
original per-even result and shifted-word result into separate arrays, compares
every live bit on the GPU, synchronizes the mismatch count, and aborts before
the ordinary success path unless that count is zero.  The extra array and
original phase-1 work are included explicitly in its VRAM accounting; this
mode is for qualification, not production throughput.

On 2026-07-25 the crosscheck accepted every one of the 600,000,000 live bits
in the exact terminal benchmark, with zero phase-2 fallback.  Separate runs
accepted the low boundary beginning at 4 and a non-word-aligned terminal
range of 600,000,123 evens.  The warp/tail KAT independently compared four
complete CUDA word arrays with both the original atomic kernel and a CPU
progression replay, including the `p^2` and `UINT64_MAX` boundaries.  CUDA
Compute Sanitizer reported zero errors for the integrated 600-million-even
prototype.

Two seven-run confirmations put the combined warp-through-32749 plus
shifted-phase-1 median at `0.346201 s` and `0.344137 s`, versus respective
unchanged-source medians `0.616369 s` and `0.604948 s`.  Those are
`1.7804x` and `1.7579x` wall-rate improvements on this GB10.  A same-process
Nsight profile attributed `149.258848 ms` of GPU kernel work to all three
segments, or about 4.020 billion evens/s in steady kernel arithmetic.  Ideal
division of the exact lowered branch over eight equal-throughput GB10 GPUs is
therefore about 134.96 kernel-hours.  Leaf setup, checkpointing, retries,
attestation, and final replay are not included.

To reduce the risk of extrapolating a setup-dominated three-segment sample,
the retained prototype was also run three times over 100 contiguous terminal
segments, exactly 20,000,000,000 evens.  The computation times were
`5.27837`, `5.06088`, and `5.22129 s`; all three had zero fallback.  A
separate diagnostic execution ran both phase-1 implementations and compared
all 20 billion result bits without a mismatch.  Using the median
`5.22129 s`, a measured median initialization of `0.423583 s` repeated
conservatively for every one of the 65,536 leaves, and no H100 speedup gives:

- `142.6004` eight-GPU wall hours, or `5.9417` days;
- `$7,962.81` at the checked eight-NCC on-demand hourly price; and
- `$1,618.84` at the checked spot hourly price.

`tools/tg_goldbach_optimized_projection.py` reproduces the unit-bearing
arithmetic.  Its output hard-codes `production_gate_passed=false`,
`target_h100_measured=false`, and `source_identity_promoted=false`; passing
the arithmetic limits cannot admit an executable or theorem.  The envelope
also excludes scheduler, confidential-attestation, retry, storage, and final
replay overhead, leaving `25.40 h` and `$2,037.19` of on-demand margin for
those terms.  It therefore establishes a promising bounded capacity
envelope, not the required Azure capacity gate.

The later cofactor-filtered sieve composes with the shifted-word and packed
count route.  It omits a tail-prime `p*k` atomic clear exactly when a prime at
most `47` dividing `k` caused the word-owner prefix to clear the same bit
already.  `GoldbachWheelFilter.lean` proves this redundancy and the exact
`+2` tail and `+64` warp cofactor equations.

On the same GB10, an integrated seven-run comparison measured a
`0.267971 s` median for all 600,000,000 terminal evens versus `0.636503 s`
for the prepared baseline, a `2.37527x` wall-rate improvement.  Three
100-segment runs took `2.38136`, `2.27927`, and `2.41579 s`; every run
reported the exact 20,000,000,000-even range and zero fallback.  A second
unprofiled set took `2.36017`, `2.32496`, and `2.35908 s`, a median rate of
`8.4779` billion evens/s.  A unified qualification executable then compared
every unfiltered/filtered sieve word, every original/shifted phase-1 result
bit, and the byte/packed missing-bit counts across the same 20 billion evens
without a mismatch.

Using the second median and the largest initialization in the first set
(`0.427747 s`) for every leaf, eight equal-throughput GB10 GPUs, and no H100
speedup gives the new unpromoted arithmetic envelope:

- `64.9675` eight-GPU wall hours, or `2.7070` days;
- `$3,627.79` at the checked on-demand cluster price; and
- `$737.53` at the checked spot cluster price.

This leaves `103.03 h` and `$6,372.21` of arithmetic margin.  It still
excludes scheduler, attestation, retry, storage, and replay overhead, and it
is not a target-SKU measurement.  The generated source and executable are
therefore not registered or admitted.  The exact differential and sanitizer
scope is recorded in
[`GOLDBACH_WHEEL_FILTERED_SIEVE.md`](GOLDBACH_WHEEL_FILTERED_SIEVE.md).

An attempted one-time device cache for the phase-1 offset table did not
improve wall time: its seven-run median was `0.349592 s` versus `0.344137 s`
without the cache.  The roughly 44 ms attributed by the CUDA API profile to
each pageable copy was predominantly synchronization with preceding kernels,
not transfer cost.  The extra cache state was consequently not retained in
the candidate.

The successful implementation is still unpromoted, but it is no longer only a
disconnected diagnostic transform: its exact generated source identity has a
full 65,536-leaf lowered plan/run/aggregate/replay route. The registered
executable pin, Azure materializer identity, and H100 admission remain
unchanged. Promotion requires a reviewed x86_64/SM90 build, exact-binary
confidential-H100 calibration, a new registered identity, and a production
run. `GoldbachOptimizedSourceRefinement.lean` proves complete-roster survivor
primality and packed-mask-to-campaign evidence; it does not by itself refine
CUDA, SASS, the compiler, or hardware execution.

The ladder retains the same approximate number of ladder steps per range as
the historical schedule but only `7,106 / 492,700 = 0.01442...` as many
ranges. Scaling earlier historical/native estimates gives roughly 183--577
CPU core-hours. That is also a projection; the production `n=45` range worker
still needs an Azure CPU benchmark.

## Remaining completion gates

1. The analytic proof must actually expose a proved crossover at `10^27` and
   consume this exact finite proposition.
2. Calibrate the binary executable on the chosen Azure H100 confidential SKU.
3. Complete the closed H100 operational worker package and its signed
   eight-receipt export; the seven CPU materializers are implemented.
4. Run and retain all 65,536 binary receipts and all 7,106 ladder receipts.
5. Replay both exact reducers and the combined finalizer.
6. Bind the combined artifact to measured Azure/NVIDIA evidence and admit the
   already-defined `goldbach10Pow27ProductionV1` registered receipt.
7. Enable the semantic inventory row only after source-realization and receipt
   review, apply the accepted receipt in the capstone, and rerun
   `#print axioms`.

Until all seven gates are complete, this campaign is capability, not proof
completion.
