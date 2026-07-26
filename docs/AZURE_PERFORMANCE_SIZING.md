# Azure trusted-compute performance sizing

This note records local planning measurements taken on 2026-07-21 on the
repository's DGX Spark (NVIDIA GB10, compute capability 12.1, `aarch64`, 20
logical CPUs). They size an Azure pilot; they are not H100 measurements and do
not verify an unsampled finite range.

## Local repository qualification benchmark

On 2026-07-21, the complete local qualification path was timed on that DGX
Spark with 119 GiB RAM, Lean 4.32.0-rc1, Python 3.12.3, CMake 3.28.3, and CUDA
13.0. The working tree was based on commit
`588bb4b348e7c0a6db19efaf890202e8a51b9b21` and was dirty with the
trusted-compute work under review. This was a cold-project/warm-dependency
run: the existing `.lake/build` was moved aside, while `.lake/packages` and
the operating-system page cache were retained. Checkout, network downloads,
and dependency installation were excluded. The safe wrappers ran their
supported work serially.

| Phase | Exact scope | Cache/input state | Wall time | Result |
| --- | --- | --- | ---: | --- |
| Lean axiom audit | Source and empty-registry audit, all 147 local Lean modules from source, aggregate receipt inventory, and both fixed axiom reports | Cold `.lake/build`; warm pinned packages | 21 min 59.53 s | pass |
| Python suite | Full `test_*.py` discovery, including generated Lean typechecks | Warm Lean tree | 2 min 23.53 s | 554 pass, 2 skip |
| Native configure | Fresh Release CMake tree for `sm_121`, H100-native off, TG CDEM on | Boost 1.83 headers supplied explicitly | 1.83 s | pass |
| Native build | Fresh serial CUDA/C++ build | Configured tree | 14.15 s | pass |
| Native tests | Serial CTest suite | Fresh native build | 31.73 s | 15 pass |
| **Core local qualification total** | Sequential sum of the preceding five phases | As above | **25 min 10.77 s** | pass |
| Blueprint | JSON and TeX facets after the Lean audit | Warm Lean tree | 9 min 10.20 s | pass |
| H100 pilot packaging | Cross-package the closed formal `sm_90` pilot; no H100 execution | Warm generators and native driver | 2.37 s | `accepted=false` |
| **Extended sequential total** | Core total plus blueprint and packaging probes | As above | **34 min 23.34 s** | pass |

`tools/audit_axioms.sh` already performs the complete safe Lean build, so a
second Lean build is not added to either total. The blueprint and H100 package
are release/evidence facets rather than additional mathematical proof checks.
The timing wrapper's process-level RSS does not include every transient
systemd-cgroup child, so this table deliberately reports wall time rather than
misleading aggregate memory numbers.

These totals estimate checking this repository locally. They do **not**
estimate completion of the thirteen ternary-Goldbach source-scale campaigns,
which currently report zero full-source campaigns completed and zero Lean
atoms discharged. They also exclude Azure VM allocation, artifact transfer,
MAA/NRAS appraisal, Managed HSM signing, and real confidential-H100 execution.
The packaging probe expects the local GB10/`aarch64` architecture mismatch;
it reported `architecture_matches_azure_x86_64=false` and
`lean_registry_admission=false`, and no H100 kernel ran.

Recheck that campaign boundary with:

```bash
python3 tools/tg_campaign.py --pretty capability
```

A current bounded CPU planning run of
`tools/benchmark_tg_verifiers.py --no-gpu --psi-limit 100000 --pretty` took
26.80 s. It measured samples such as 9,700 prime-power events and 20,000
little-Mertens indices, then emitted explicit planning ranges. It is useful for
detecting performance regressions, but it is not one of the thirteen complete
campaigns and is not added to either qualification total.

## Reproducible aggregate sample

From the repository root:

```bash
python3 tools/benchmark_tg_verifiers.py \
  --gpu-count 16777216 \
  --gpu-repetitions 10 \
  --mobius-limit 1000000 \
  --exact-fraction-limit 20000 \
  --pretty
```

The GB10 integer work-item microbenchmark processed about 24.8 billion
synthetic items/s and wrote at least 198.4 GB/s. This is a bandwidth-oriented
planning probe, not a sieve, zero verifier, or certificate checker. The same
report records the current full-source feasibility ranges and the command's
explicit nonclaims.

## Measured-run protocol overhead samples

The complete development CPU fixture can be replayed with:

```bash
/usr/bin/time -f 'wall_seconds=%e max_rss_kib=%M' \
  python3 -m unittest \
  tests.test_measured_runner.MeasuredRunnerTests.test_real_static_cubic_job_is_challenge_first_and_transcript_verifies
```

On this DGX Spark, one invocation took 0.80 s wall time and about 122 MiB peak
RSS. That includes compiling the static C++ fixture, executing the
challenge-first fake-vTPM protocol, independently recomputing its 20,001-step
work trace, and verifying the transcript. It does not include MAA, NVIDIA
attestation, network transfer, or Managed HSM signing.

The closed one-row `sm_90` formal-PTX pilot can be packaged locally with
`tools/build_h100_measured_formal_ptx_pilot.py`. Generating the PTX from Lean,
assembling and disassembling the cubin, auditing PTX/SASS, and compiling the
static measured wrapper and independent trace verifier took 2.37 s wall time
and about 164 MiB peak RSS. The package correctly reports that its local
`aarch64` host artifacts do not match Azure's `x86_64` NCC guest. It cannot be
executed as the strict pilot on the GB10 because that pilot requires exactly
one compute-capability-9.0 H100.

These timings measure packaging and local protocol checks, not the fixed cloud
latency of VM allocation, MAA/NRAS appraisal, evidence return, or HSM signing.
Record those stages separately during the first Azure run.

## Exact production-kernel samples

The machine-readable eight-node model is generated by:

```bash
python3 tools/tg_azure_production_sizing.py --refresh-prices --pretty
```

The command queries Microsoft's Retail Prices API when `--refresh-prices` is
present.  The checked 2026-07-21 East US 2 Linux snapshot is $6.98 per
`Standard_NCC40ads_H100_v5` node-hour on demand and $1.419034 per node-hour
for spot.  Eight nodes therefore cost $55.84 per wall hour ($1,340.16 per
day) on demand or $11.35 per wall hour ($272.45 per day) at the displayed spot
rate.  These formulas exclude Managed HSM lifetime, storage, egress, CPU-only
capacity beyond the modeled cluster, capacity delay, and spot eviction/replay.
Spot is not a reservation or a promise of availability.  The companion CPU
snapshot is $4.358 per `Standard_DC96as_v6` node-hour on demand and $0.805358
spot. Four 96-core nodes cost $17.432 or $3.221432 per wall hour respectively.

The report keeps prices as decimal strings, shows every one of the thirteen
atoms, and currently refuses to claim a complete-portfolio ETA.  The
Dirichlet all-character transform, persistent residue composer, framed
transform service, scalable root-number stage, and factored small-`q` v3
arithmetic are now implemented and benchmarked separately, and the persistent
large-`q` component process graph is wired. Full-source integration of
certified box/seed generation, the small-`q` width boundary, and two analytic
closure conditions remain open. Goldbach has a source-height measurement and an
explicit H100 sensitivity table, but no row in that table is an H100
measurement. The literal FLINT zeta campaign has an ETA, but it is
impractically long rather than missing.

### Fail-closed backend optimizer

The same command now emits `backend_optimizer`, a route matrix for the ten
deduplicated physical campaigns. Every campaign explicitly classifies a
CPU-only, H100-node-only, and mixed route; an inapplicable route is retained as
`unavailable` instead of disappearing from the comparison. Four logical
Möbius-family atoms still count as one physical Hurst run.

The optimizer distinguishes three states:

- `eligible`: the exact implementation has a retained full-source or
  source-shaped reference-host measurement and an explicit node-hour
  conversion;
- `sensitivity_only`: enough arithmetic exists to show a cost range, but a
  target calibration or complete composition is absent; and
- `unavailable`: there is no defensible work/rate conversion for that route.

Only `eligible` rows participate in selection. A GB10-to-H100 multiplier is
never promoted merely because its price is attractive. The current flexible
comparison covers seven campaigns and refuses a complete-portfolio cost because
R2Star and Goldbach have no retained Azure-H100 calibration and the Dirichlet
component graph is not an end-to-end campaign. Their sensitivity costs remain
visible beside those blockers.

Target-SKU measurements are supplied explicitly rather than inferred from the
machine running the planning command:

```bash
python3 tools/tg_azure_production_sizing.py --pretty \
  --target-sku-calibration CALIBRATION.json
```

The compact canonical manifest binds one exact campaign/route/resource tuple,
the executable and closure digests, reviewed target and trust profile hashes,
Azure region/SKU/node count, a source-shaped sample geometry, repeated
producer and independent-replay timings, appraisal/receipt digests, and an
exact rational safety factor. Its conservative source-scale node-hour
endpoint must be at least the measured linear extrapolation and must equal the
route endpoint already under review. A matching manifest may change only the
route's `target_sku_measured` planning field; it cannot make a
`sensitivity_only` route eligible, authorize cloud execution or deployment,
admit a receipt, or prove a Lean theorem. The manifest validator reads no
named executable, closure, or production input bytes.

An optional ideal wall deadline asks how many nodes the high-work endpoint
requires, subject to explicit caps:

```bash
python3 tools/tg_azure_production_sizing.py --pretty \
  --deadline-hours 8766 --max-cpu-nodes 64 --max-h100-nodes 8
```

For example, the literal zeta route requires 45 ideal DC96 nodes to fit one
365.25-day year, while its eight-NCC-host-CPU route fails that deadline. This
is node-hour arithmetic, not a capacity quote: independent mixed branches may
overlap, and queueing, storage, retries, attestation, and contention are not
modeled. Without a deadline the report uses the reviewed default widths. Since
ideal linear scaling leaves compute node-hours unchanged, a deadline can
change feasibility and width without creating a fictitious cost saving.

For each price class, selection minimizes the upper endpoint of the retained
cost range. If ranges overlap, `plausibly_optimal_route_ids` retains every
candidate and `cost_order_resolved` is false. An incomplete scenario reports
only `partial_covered_cost_usd`; `optimized_complete_portfolio_cost_usd` is
`null`. The checked price snapshot remains the default, and
`--refresh-prices` can replace both SKU rates without changing any performance
calibration.

### Active Goldbach `10^27` handoff sensitivity

The optimized race-free word-owner kernel was measured over 600,000,000
terminal source-height evens. Seven retained main-loop timings had a median of
0.779701 s, or 769,525,754 evens/s on the local GB10. The active finite handoff
below the separately proved `10^27` analytic crossover contains exactly
15,624,999,999,999,999 evens in 65,536 immutable checkpoint leaves. Arithmetic
scaling over eight equal-throughput GPUs gives:

| Per-H100 throughput vs measured GB10 | Eight-GPU wall hours | Wall years | Maximum leaf hours | Eight-NCC on-demand cost | Eight-NCC spot cost |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1x | 705.02 | 0.0804 | 0.0861 | $39,369 | $8,004 |
| 2x | 352.51 | 0.0402 | 0.0430 | $19,684 | $4,002 |
| 5x | 141.00 | 0.0161 | 0.0172 | $7,874 | $1,601 |
| 10x | 70.50 | 0.0080 | 0.0086 | $3,937 | $800 |
| 14.3x | 49.30 | 0.0056 | 0.0060 | $2,753 | $560 |

The 1x row is equal measured-device throughput, not an H100 claim. The 14.3x
endpoint is only the `3.9 TB/s / 273 GB/s` H100-NVL-to-DGX-Spark bandwidth
roofline. The kernel still spends substantial time in atomic and integer work,
so that ratio is not a promised runtime multiplier. All rows assume ideal
eight-way division and omit startup, retries, attestation, storage, and final
replay. A production H100 pilot must replace this sensitivity table with
measurements before a run is purchased.

On 2026-07-22 the active source closure moved the exact word-owned prime prefix
from `1021` through `2039`.  In a same-host, same-command, seven-run A/B test,
the old and new medians were `0.858128 s` and `0.823758 s`, respectively:
`699,196,390` versus `728,369,254` evens/s, or a `4.17%` relative rate
improvement.  The integrated source identity is
`9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55`.
Because that A/B session ran under a different host load from the retained
`0.779701 s` session, the machine-readable sensitivity table continues to use
the older absolute baseline and does not claim a compounded speedup.  Azure
procurement still requires an exact-binary H100 calibration.

For provisional procurement, the machine-readable report designates the
**2--5x** rows as the working band. That predicts **141.00--352.51 wall hours
(5.88--14.69 days)** for the eight-H100 binary branch and **$7,874--$19,684**
on demand, or **$1,601--$4,002** at the displayed spot rate. Only the 5x row
fits the one-week/$10,000 objective. This is a sensitivity band, not an H100
benchmark: the report has a fail-closed `h100_calibration_passed = false` gate,
so it cannot promote a budget or one-week claim until the exact confidential
H100 executable is measured.

An unpromoted follow-up combines wheel-filtered redundant-clear elimination,
warp ownership of the medium-prime sieve progressions, formally modeled
word-shifted phase-1 coverage, and packed missing-bit counting.  A
100-segment terminal test checked exactly 20 billion evens in median
`2.35908 s` on the GB10.  A unified diagnostic compared every
unfiltered/filtered sieve word, both phase-1 implementations, and both
missing-count methods across all 20 billion outputs.  Conservatively
repeating the largest observed `0.427747 s` initialization for all 65,536
leaves gives `64.9675 h` (`2.7070 d`) and `$3,627.79/$737.53` on demand/spot for
eight equal-throughput GB10 GPUs.  No H100 speedup is used.

This newer arithmetic envelope is reproduced by
`tools/tg_goldbach_optimized_projection.py`, but it does **not** replace the
active table: the generated source is not reviewed or pinned, no H100 binary
has been calibrated, and scheduling, attestation, retry, storage, and replay
overhead are excluded.  The tool therefore reports all three admission flags
as false even when its arithmetic deadline and budget booleans are true.

The historical `[4,4e18]` reconstruction remains in the machine-readable
report as `goldbach_historical_source_comparison`. Its old 2--5x band is still
18,049--45,122 hours and is not the active handoff.

### Goldbach prime-ladder CPU boundary

The binary run is only one prerequisite for the Goldbach handoff. Its separate
7,106-range `n=45` prime ladder has the same 4,503,600 minimum steps per range.
Scaling the earlier bounded native and Python projections by the exact
`7,106/492,700` range ratio gives about 183 and 3,678 core-hours. Scaling the
paper's 40,000-core-hour historical report the same way gives about 577
core-hours as a comparison. On four ideal 96-core CPU nodes those values are
0.48, 9.58, and 1.50 hours, costing about $8/$2, $167/$31, and $26/$5 on
demand/spot at the displayed rates.

No lowered production range has run. All three rows are projections; the
historical-scaled row is not a measurement of `n=45`. They exclude
general-prime pauses, durable I/O, retries, and attestation. The binary
campaign and ladder can run concurrently, but both must finish, replay, and
enter the measured CPU finalizer before Lean receives the registered claim.

### Literal zeta-RH CPU projection

The pinned FLINT 3.6 count-only benchmark projects 37,580,948 process-hours.
Ideal division over four 96-core `DC96as_v6` nodes is 97,867 wall hours (about
11.16 years), costing approximately $1.706 million on demand or $315,272 at
the displayed spot rate. This is an ETA for the current literal
implementation, not evidence that the campaign ran. Platt--Trudgian reported
7.5 million core-hours for their optimized historical computation; ideal
division of that published work count over the same CPU pool would be 19,531
hours (2.23 years), about $340,469/$62,919, but the repository does not yet
implement that optimized engine.

Even if Dirichlet contributed zero additional time, the current literal zeta
projection would dominate the ideal four-CPU-node concurrent schedule for
every active `10^27` Goldbach row above. That counterfactual envelope remains
about 11.16 years. Binary-plus-zeta compute is about $1.709--$1.745 million on
demand or $315,832--$323,276 spot across the displayed Goldbach sensitivities.
This is deliberately not labeled a thirteen-atom ETA: it assigns zero time to
the missing Dirichlet closure and omits storage, retry, attestation, and replay.

Keeping only four CPU nodes therefore leaves zeta as the long pole. Matching
the active 2x or 5x Goldbach wall time would require an impractical idealized
**1,111 or 2,777 DC96as_v6 nodes**, respectively. The arithmetic cost remains
about **$1.714--$1.726 million on demand** or **$316,873--$319,274 spot** because
ideal linear CPU scaling does not reduce node-hours. This comparison is useful
for exposing the separate zeta blocker; it is not a suggested procurement
plan and says nothing about quota, queueing, storage, or achievable scaling.

### CH25 psi two-pass CPU pilot

The pinned primesieve/CRlibm runner was measured with twenty concurrent
100,000,000-integer shards next to `10^13`:

```bash
python3 tools/benchmark_tg_psi_residual_shard.py \
  --runner build/psi-strict/sparkinterval-tg-psi-residual-shard \
  --workers 20 --shards 20 --shard-span 100000000 \
  --upper 10000000000000 --pretty
```

One retained local invocation processed 66,816,322 prime-power events per
pass.  Summary took 2.115 s and independent verification took 2.875 s, for
26.78 million event-passes/s and a linear two-pass source projection of 7.18
hours on this 20-core ARM host.  The production calculation is CPU-oriented:
the H100 does not accelerate primesieve or correctly directed CRlibm calls.
An eight-NCC estimate of roughly 0.5--2 wall hours is plausible, but must be
replaced by a 1--2-billion-event pilot on the exact confidential VM image.

### Shared Hurst/Mobius CPU pilot

The pinned Hurst adapter summarized ten billion integers at the top of the
source range in 7.38 s on the same 20-core host, using about 4.6 GiB RSS.  It
checks four residual profiles from the same Mobius stream.  A production
certificate performs a parallel summary pass, derives all four prefix states
from the single zero root, and independently reruns every fixed shard in
verify mode.  Scaling this small measurement is sensitive to x86-64's
division-free path, memory bandwidth, shard startup, and the second-pass
guard cost; the current eight-NCC envelope is therefore a deliberately broad
2--22 wall days.  Do not schedule four separate `10^16` scans: one shared
certificate covers CDEM squarefree, Hurst Mertens, and both little-Mertens
atoms.

An implemented one-pass affine H100 alternative has a narrower, separately
classified planning sensitivity.  Its exact topology partitions
`[10^12+1,10^16+1)` into eight equal workers and composes their summaries by
the proved affine law.  The current complete-device-work measurement is
`191.737 ms` per 100 million rows on GB10.  Equal GB10 throughput therefore
projects to `665.687` wall hours; an explicit but unmeasured `12.3x`
GB10-to-H100 factor projects to `54.121` arithmetic-only hours and
`432.967` H100 node-hours, approximately `$3,022.11` PAYG or `$614.40` Spot.
These terminal-H100-stage figures are not a complete hybrid-campaign ETA or
target-H100 evidence; they do not replace the broad CPU route or pass the
production gate.  The CPU summary/verification prefix through `10^12` and
handoff, startup, receipts and replay, checkpointing, retries, and attestation
remain outside this arithmetic.

A 2026-07-25 scheduler pilot used four independent one-billion-row leaves and
the current source adapter.  Serial 20-thread execution took 6.51 s for the
summary pass and 22.89 s for verification.  Two concurrently pinned
10-thread children took 6.03 s and 20.73 s, respectively, while producing
byte-identical receipts after removing only the nonsemantic elapsed-time
field.  Four pinned five-thread children reduced verification only slightly
further, to 20.54 s, while increasing aggregate child time and memory
pressure.  Unpinned four-by-five execution took 22.19 s for the summary pass
and was decisively worse.  The reviewed 40-vCPU workload therefore uses two
disjoint 20-thread children and fail-closes on oversubscription.  These
four-billion-row measurements validate the scheduler and show only a modest
7--10% local gain; they are not an Azure or full-source ETA.

The same date's arithmetic hot-path check replaced per-row integer divisions
in the maintained floor-square-root state with overflow-safe unsigned
128-bit products.  Three one-billion-row verification pairs had medians
5.6348 s before and 5.5630 s after, a 1.013x gain, with identical complete
semantic receipts and only elapsed time removed.  The native known-answer
suite and bounded ASan/UBSan summary, verify, and affine runs also pass.  This
small gain is retained because it simplifies the exact predicate; it is not
used to narrow the broad Azure envelope.

The exact affine-guard mode has a separate source-shaped optimization result.
At eight threads, 20 million rows fell from 32.28 s to 2.764 s at the low end
and from 23.35 s to 2.85 s near `10^16`; receipts were byte-semantically equal
after removing only elapsed time. Linearizing the 2.764--2.85 s band across
the whole `10^16` range gives 3.071--3.167 million core-hours, or
7,998--8,247 ideal hours on four DC96 nodes. This is intentionally *not*
substituted into the production estimate: the production supervisor still
uses the two-pass summary/verify protocol, while the affine alternative lacks
its one-pass campaign schema and independent replay. The optimizer exposes it
as a calibrated `sensitivity_only` route and cannot select it.

### Proposition 12.2.4 CPU pilot

The native MPFR/GMP verifier measured roughly 12,600--14,400 empty `q` rows/s
per local core at 192 bits. The fixed source plan contains 3,389,047,618 rows,
so the empty-row extrapolation is about 61--73 core-hours before the isolated
`q=1` and nonempty-row work. The production model preserves a wider
105.6--640 core-hour band per replay. The closed measured protocol performs
two complete replays in four strided 96-worker groups, for 211.2--1,280
aggregate core-hours or 0.55--3.34 ideal hours on four `DC96as_v6` nodes,
before launch, attestation, terminal, and retry overhead. At the recorded
rates this compute band is about `$9.59--$58.22` PAYG or `$1.77--$10.76`
Spot. A complete-node pilot is still required.

### Dirichlet component envelope, not an atom ETA

The large-`q` all-character implementation covers exactly
`15,334,965,882,246,056` primitive-only V2 batch-64 radix-2 butterflies.
Representative GB10 measurements sustain 1.38--1.40 billion butterflies/s,
giving 380.3--385.9 ideal wall hours on eight equal GPUs.
The current one-plan-per-modulus MPFR preparation adds about 66.7 ideal hours
on eight hosts. A deliberately unmeasured 5x--10x H100 sensitivity therefore
places this component, including preparation, at about 104.7--143.9 hours. It
excludes input generation, completed values, I/O, exceptions, and closure.

The primitive-only V2 directed lattice Taylor roster has
`266,697,737,764,848` residue reconstructions. Its 69.60
million-residue/s GB10 rate gives about 133.1 ideal eight-GPU hours before an
H100 multiplier.

A fused alternative combines those Taylor reconstructions with residue
composition in one q-persistent directed CUDA batch. It reduces
3,637,613,167 one-ordinate jobs to exactly 56,981,100 batches of at most 64
ordinates and emits canonical `TGDAFFI1` directly. A source-shaped `q=10001`,
batch-64 GB10 measurement sustained 68,577,057 values/s. Arithmetic scaling
of all `266,697,737,764,848` values is 135.04 hours on eight equal GPUs or
13.50--27.01 hours at an unmeasured 10x--5x H100 sensitivity.

That row is an **alternative** to the separate lattice-Taylor and
residue-composition rows, not extra work, and the before/after totals below do
not double-count it. The retained `18,263,933,424,590,240`-byte input figure
is explicitly the legacy V1 materialization, including
`13,083,568,251,320,320` bytes of repeated tail/finite-recovery rectangles.
It is not a V2 production-input estimate.

The newer authenticated seeded variant replaces those recovery rectangles by
one completely generated and 320-bit-Arb-replayed 96,008,016-byte table. It
also stores one uniform Taylor-tail radius per ordinate rather than per
residue. The retained V1 logical boundary is `5,180,404,381,680,112` bytes
(5.180 PB); the V2 direct format below supersedes it for production planning.
A source-shaped `q=10001`, batch-64 fused measurement sustained
19,424,914 values/s on GB10, including directed seed recurrence. Scaling all
`266,697,737,764,848` values gives 476.72 ideal hours on eight equal GB10 GPUs,
or 47.67--95.35 hours at an unmeasured 10x--5x H100 sensitivity. This is the
honest current arithmetic measurement; the higher legacy rate did not include
the seeded finite-recovery work.

The repeated 5.180-PB boundary has an exact authenticated t-major cache
contract: 127,988 one-MiB rows, 1,000 bounded shards, and
`134,205,145,088` unique payload bytes. The former t-major model still
repeated descriptors and totaled `41,413,846,139,376` bytes. The direct
`TGDLTMB1` path now reconstructs descriptors, produces replayed MPFR
factor/exact-tail sidecars, and reduces exact binary input to
`286,556,459,000` bytes (`286,652,467,016` including recovery seeds) for the
primitive-only V2 roster. Its bounded CUDA KAT uploads a row block once. The
cache has not been populated, the output is not integrated with the multi-q
FFT/zero lane, and no Azure source benchmark exists.
The primitive-only V2 source roster has `56,981,100`
fixed-q/up-to-64-ordinate FFT batches. The existing eight-lane shared-row
spool and 2,000-request structural t-block supervisor are still V1 control
models: they store each lane row once, stream row blocks with backpressure,
and use immutable hash-chained resume checkpoints, but must be regenerated
and version-bound before they may supervise the V2 roster.
Its local 64-MiB structural I/O KAT sustained 180.5--200.1 MiB/s per unique
payload byte, but that is not a CUDA or analytic-compute measurement. Production
admission remains disabled because the current all-character service is
fixed-q and the supervisor does not yet receive, freshly replay, and
adapter-admit actual typed-bundle bytes. A
streaming catalog can parse and receipt-bind all `292,500` source root
artifacts once. These are planning/input contracts, not measured runtime
paths. A bounded adapter now freshly replays typed FFT bundles in deterministic
target order and checks their lattice payloads against authenticated cache
rows, but production spool-to-pipeline/typed-bundle-byte execution wiring and
zero-consumer state/ordering adapter remain absent.
The seeded fused stage therefore remains `source_performance_ready=false`, and
47.67--95.35 hours is kernel arithmetic, not a large-`q` or Theorem 7.1 ETA.

The active small-`q` v3 boundary factors the old per-character frequency seeds
into one shared frequency record with two parity families, plus one phase and
exact exponent table per character. The exact inventory falls from
`7,078,844,301,312` legacy seeds to `16,385,441,792` shared records, a
432.02x cardinality reduction. Its minimum logical payload is
`2,459,841,190,828` bytes (2.460 TB), down from the v2
`622,938,298,515,456` bytes by 253.24x.

The retained `q=997`, 65,536-frequency, 16-character producer built 196,624
distinct families in 3.164728742 s. The independent Arb checker reconstructed
the same families in 3.272058564 s, or about 60,091.8 families/s in one
process. Those are retained compact-KAT rates. A distinct complete
source-parameter `q=997` service plan contains 2,097,152 frequencies, 995
primitive characters, and 6,292,451 distinct families. It took 110.71 s to
produce (`56,837.2/s`) and 126.369121963 s to check (`49,794.2/s`). The
conservative source replay equation deliberately uses that larger, slower
checker measurement:

```text
(3 * 16,385,441,792 + 18,477,108) / 49,794.2 / 3600 / 384,
```

which gives 0.714 ideal hours on 384 processes. This is a source-shaped linear
projection and excludes producer generation and the q-persistent service.

The factored CUDA consumer processed 4,003,136 finite terms and 8,388,608 DFT
butterflies together in 14.160607 ms on GB10. Since the two operation types do
not have identical cost, the report retains one combined-work sensitivity
instead of inventing separate rates. Transferring the current source work
gives 49.14 hours on eight equal GB10 GPUs, or 4.91--9.83 hours at the
unmeasured 10x--5x H100 band. The v2 64.73-GPU-hour, 151.74-CPU-hour, 622.9-TB
row remains machine-readable solely for comparison.

The factored CUDA consumer, independent checker, and q-persistent source
service are implemented. A source-sample-only stream now checks the exact
canonical parameters before omitting unused guard-height outputs, reducing the
output boundary from 339.785 TB to 226.996 TB. A vectorized, hash-tree-bound
consumer measured a cached local median of 4,943.5 MB/s and an actual anonymous-
pipe median of 1,510.2 MB/s. The latter gives 41.75 hours by literal
single-stream division (or an ideal, uncalibrated 5.22 hours across eight
independent q-sharded pipes), and retains no raw output. That consumer proves
coverage and integrity only: it does not prove disk arithmetic and cannot be
replayed after bytes are discarded without trusted-run evidence.

A separate semantic reducer now factors the displayed time-periodization
bound by `(q, parity, source ordinate)`, higher-precision replays the complete
control, and joins it to every exact character/sample coordinate. The active
moduli require `8,116,121,626` two-parity records, or
`129,858,785,904` bytes including headers. Strict negative and positive
decisions plus every ambiguity can be represented by a two-bit family of
exactly `1,182,271,755,191` bytes including q headers, but the active typed
adapter feeds those codes directly into `TGDCSB03` and does not persist that
family. The formulaic final dense state has a `62,259,950,420`-byte floor and
`62,968,524,843` canonical bytes before sparse ambiguity ranges. Eight lane
heads have a `313,234,007,491`-byte dense floor and
`317,542,970,540` canonical bytes before those ranges. Ambiguity density is
not measured, and the retained compact summary performs no multiplicity or
Turing inference. This is exact source-wide format accounting and a tested
q-level implementation, not a measured source run. The CUDA runner now has a
device-side `TGDBSPK1` classifier after the full DFT and before disk transfer.
It applies the exact outward boundary, copies only two-bit codes plus an
eight-byte full-status summary, and feeds the compact reducer directly. A
full-span synthetic `q=5460` GB10 differential run (`B=165`, `N=262144`,
`S=234433`) produced byte-identical host/device payloads and compact states;
device mode copied 9,670,362 payload bytes instead of 1,211,105,280 disk/status
bytes, a 125.24-fold reduction (99.20%). The same local sample spent 230.6 ms
in the shared DFT, 8.40 ms in device classification/status reduction, and
0.18 ms in packed transfer; process wall time was 1.42 s versus 1.91 s for
host packing.

Those numbers are a local synthetic GB10 q-level transport benchmark, not an
H100 or source-wide measurement. The implemented Azure H100 materializer is
nonterminal and binds host versus device location without fallback, but it is
not yet routed through the complete source campaign. The old 226.996-TB
single-stream division is therefore retained only as a superseded host-path
sensitivity, not charged as an unavoidable device transfer. The project also
has not proved that accumulated and scaled full-transform widths remain useful
across every source case. V3 therefore remains component evidence rather than
a Theorem 7.1 ETA.

The routine factor-eight postprocess now has its own dimensionally correct
model. The exact roster contains `196,430,125,886,102` base-grid completed
intervals and `1,571,337,544,104,271` target coordinates. Of those targets,
`1,374,907,418,218,169` are nonaligned and require exactly
`54,996,296,728,726,760` forty-tap interval products. The former 11,255.9-hour
CPU row divided the target count by a rate measured per input sinc term. It
was dimensionally invalid and is now retained only as a named historical
comparison, not charged to the active component total.

The bounded CUDA replacement uses a 280-interval Arb-replayed coefficient
table, directed binary64 convolution, and two-bit strict-sign/ambiguity
packing. Its independent checker replays bounded strict signs from exact
rational interpretations of all binary64 endpoints. A three-trial GB10
benchmark over 8,388,288 targets per trial measured a median 350,576,168
targets/s, versus 212,443,210/s for the retained four-corner reference, a
1.65021x paired median speedup with byte-identical artifacts. Literal scaling
gives 155.63 ideal hours on eight equal GB10s. The machine-readable report
shows a 15.56--31.13-hour 10x--5x H100 sensitivity, but no H100 measurement is
available. Upstream completed-value construction, input transport, padding
and exceptional upsampling, the uniform interpolation theorem, attestation,
and zero/Turing closure remain excluded. See
[DIRICHLET_FACTOR8_POSTPROCESS.md](algorithms/DIRICHLET_FACTOR8_POSTPROCESS.md).

The persistent large-`q` residue composer covers the same
`266,697,737,764,848` primitive-only V2 values. Its retained batched host
measurements are
1.166--1.303 million values/s per process, giving an **ideal-only**
148.1--165.5 hours if 384 processes scale linearly. Memory bandwidth and
prefetch can prevent that scaling, so this is not a source ETA. The composer
now pipes directly into the all-character framed service and avoids 10.47 PB
of materialized transform inputs. The service also removes the 113,962,200
producer/consumer child launches implied by the primitive-only
56,981,100-batch rolling
harness. No runtime credit is assigned to that fork removal until the complete
full-source supervisor is measured.

The scalable root-number stage now uses one all-character transform per
active modulus instead of the former quadratic Gauss-sum loop. Its exact
large-`q` work is 292,500 moduli, 40,503,165,302 additive input rectangles,
29,547,446,729 primitive root records, and 2,645,418,549,056 butterflies.
Measured DGX rates plus the current twiddle/startup projection give 882.9
CPU-core-hours, or 2.30 ideal hours on 384 cores; its transform arithmetic is
about 0.066 ideal hours on eight equal GB10 GPUs. The 945.5-GB aggregate root
stream is bounded to one modulus in the persistent protocol. The production
completed-`L` consumer now validates and uses those compact artifacts. Cross-`q`
plan caching and a measured q-shard production supervisor are still absent,
so the root stage is not source-performance-ready.

The exact machine-readable report preserves the superseded model so the
effect of these changes is reviewable:

| Conditional Dirichlet component model | Before | v2, superseded | v3, active |
|---|---:|---:|---:|
| 384-core CPU work, serialized | 25,968.7 h | 6,155.0--6,172.4 h | 6,004.0--6,021.4 h |
| eight-GPU work, 10x--5x GB10 sensitivity | 120.46--175.33 h | 140.11--214.62 h | 138.55--211.50 h |
| ideal concurrent component wall time | 25,968.7 h | 6,155.0--6,172.4 h | 6,004.0--6,021.4 h |
| serialized CPU + GPU wall time | 26,089.1--26,144.0 h | 6,295.1--6,387.0 h | 6,142.6--6,232.9 h |
| East US 2 on-demand compute | $459,413--$462,477 | $115,118--$119,582 | $112,399--$116,775 |
| displayed spot compute | $85,024--$85,647 | $21,419--$22,320 | $20,914--$21,799 |

Against the original component model, the active v3 crossed-endpoint savings
are $342,637--$350,078 on demand and $63,225--$64,732 at the displayed spot
rate. Every figure assumes ideal linear CPU/GPU division and excludes the
q-persistent 2.460-TB source service and producer, the superseded host-path
226.996-TB transient small-q stream, 129.859-GB replayed time-tail control,
63-GB final compact state plus unmeasured sparse ambiguities, storage, retries,
attestation, exceptions, and unresolved mathematics. It is a component-budget
revision, not evidence of a source run. The table predates the device packer
and assigns it no runtime credit; it does include the new factor-eight GPU
sensitivity while excluding the retired dimensionally invalid CPU row.

The q-persistent seeded fused large-`q` row is published beside this table as
an alternative sensitivity. It is intentionally excluded from both columns
until the implemented 125-GiB cache is populated and its t-major schedule has
a measured production CUDA integration.

The remaining hard boundary is qualitative as well as computational. The
existing persistent composer, framed transform, root-number artifacts, and
completed-`L` consumer are already joined by a cancellation-, backpressure-,
and receipt-aware component graph. A full-source supervisor must integrate its
certified box and seed producers. The fused alternative now has a fully
replayed finite-recovery seed producer and a t-major Hurwitz cache contract,
but still needs a populated cache and CUDA broadcast integration. The small-`q`
device classifier and reducer still need source-campaign wiring, source-scale
control/reducer measurements, and source-wide width closure. The
accepted manuscript's interpolation bound still needs a
uniform source-range proof. The executable paired-Turing path now corrects
the display by reflection, includes `+2/pi`, and uses the definition-expanded
scaling; its theorem-level analytic/Lean bridge is still absent, and the
literal common-denominator formula still fails the rigorous `q=3` KAT. The direct
FLINT argument-principle fallback is source-domain executable and avoids that
display, but has no defensible practical source ETA.

For historical scale only, Platt reported about 400,000 core-hours. Ideal
division over four 96-core CPU nodes would be 1,041.7 hours (43.4 days), about
$18,158 on demand or $3,356 spot. Those values are not an estimate for the
current code.

The report also emits a deliberately conditional all-thirteen engineering
sensitivity. With independent four-node CPU pools, the literal current zeta
projection fixes wall time at about 11.16 years in every Goldbach row; sharing
one four-node pool between zeta and the current Dirichlet reference
sensitivities gives about 13.29 years. Depending on the GB10-to-H100 Goldbach
sensitivity, dominant compute is about $2.041M--$2.082M on demand or
$0.377M--$0.386M at the displayed spot rates. The provisional 2x--5x Goldbach
rows narrow that to about $2.046M--$2.062M on demand or $0.378M--$0.382M spot. This
excludes storage, retries, attestation, unquantified exception work, and the
still-open analytic and integration conditions, so it is a procurement
sensitivity and not a complete-portfolio ETA. See the
[all-character stage](algorithms/DIRICHLET_ALL_CHARACTER_FFT_STAGE.md),
[small-q stage](algorithms/DIRICHLET_BOOKER_SMALLQ_STAGE.md),
[root-number stage](algorithms/DIRICHLET_ROOT_NUMBER_STAGE.md),
[residue-composition stage](algorithms/DIRICHLET_RESIDUE_COMPOSITION.md), and
[zero-closure boundary](algorithms/DIRICHLET_ZERO_CLOSURE_STAGE.md).

The complete CDEM Abel computation was repeated locally on 2026-07-23 through
the fail-closed reviewed-source supervisor. The eight-thread five-billion-step
producer took 86.574 seconds. The independent implementation then replayed all
1,000 chunks with 363.411 aggregate worker-seconds across eight workers; the
whole command finished in under three minutes. The retained transcript SHA-256
is
`2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123`,
and its canonical registered result has SHA-256
`84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c`.
Those rows generated the 1,000-chunk ordinary-`decide` Lean arithmetic
certificate. This was a local aarch64 run, not an Azure SEV-SNP run or an
attested production receipt; the physical recurrence realization remains in
the disclosed trusted-compute boundary.

The exact R2Star producer/replayer pair was sampled historically with the
following production-scale benchmark command. It now requires measured-worker
scope and is not part of local qualification:

```bash
python3 tools/tg_r2star_benchmark.py \
  --runner build/dgx-spark/sparkinterval-tg-r2star-chunk \
  --arithmetic-replayer \
  build/dgx-spark/sparkinterval-tg-r2star-arithmetic-replay \
  --lower 1 --count 1000000 --repetitions 3
```

On 2026-07-23, three GB10 repetitions at both the low million rows and the
terminal million rows gave producer medians of 1.003546042 s and 1.036697658 s.
The separate one-thread CPU replay medians were 0.921640459 s and
0.897319285 s. It exactly matched the CUDA receipt's factor-support digest,
directed-row digest, outgoing state, fallback count, and minimum-slack witness.
Linear sensitivity is therefore 5.85--6.05 hours for the serial producer and
5.23--5.38 single-thread hours for replay, before campaign and attestation
overhead.

For local smoke testing, use `--count 64 --repetitions 1`; this is a KAT, not a
throughput estimate.

The benchmark wire format and output say `BENCHMARK_ONLY`; the source-scale
registered-result path cannot consume them. The report also says both
`admissible_as_external_atom_evidence: false` and
`target_sku_measurement: false`. The exact production factory is one serial
incoming-state chain on one NCC H100 node, so the optimizer now caps its
parallelism at one and retains a 1--8 uncalibrated node-hour sensitivity. The
corresponding compute-only snapshot is `$6.98`--`$55.84` PAYG or
`$1.42`--`$11.35` Spot. The target-SKU pilot remains mandatory, and these
figures exclude storage, retries, evidence collection, and capacity.

The exact Möbius transition path was sampled with:

```bash
/usr/bin/time -f 'wall_seconds=%e max_rss_kib=%M' \
  ./build/dgx-spark/sparkinterval-tg-mobius-segment \
  --lower 1 --count 10000000 --device 0
```

Ten million records took 4.33 s wall time and about 556 MiB peak RSS. The GPU
kernel took 40.52 ms (246.8 million rows/s); independent CPU comparison and
exact bounds took 3.73 s. The run compared every GPU record with the CPU
segmented sieve and reported no mismatch. It did **not** prove any complete
external atom because it covered only `[1, 10,000,000]`.

## Azure implications

- Calibrate the optimized Goldbach kernel on one H100 before reserving eight.
  Its word-owner initialization removed the old race and much of the
  small-prime atomic traffic, but residual atomics and integer work still make
  a pure memory-bandwidth multiplier unsafe.
- Use one `Standard_NCC40ads_H100_v5` VM per independent GPU shard. That SKU
  exposes one H100, so assigning several GPU shards to one VM does not add GPU
  concurrency.
- Use the confidential CPU profile for FLINT/Arb, parsing, exact replay, and
  aggregation jobs that do not need a GPU. This avoids paying for an idle H100
  and avoids pretending CPU evidence is NVIDIA evidence.
- Start with short, practical campaigns: the retained A.7 replay, the
  CDEM/Abel scan, the small zeta head, psi, Proposition 12.2.4, and R2Star.
  The literal trillion-zero zeta range remains measured in years. The active
  Goldbach `10^27` handoff has an unpromoted 5.94-day equal-GB10 envelope,
  while the retained production profile still carries its older
  5.88--14.69-day 2x--5x sensitivity. It is UNRUN and its fail-closed H100
  calibration gate has not passed. Source-scale Dirichlet still lacks
  persistent component composition and analytic closure despite having its
  principal optimized arithmetic components. The shared `10^16` Hurst stream
  has a broad 2--22-day estimate rather than a completed Azure calibration.
- Treat the repository's H100 runtime ranges as planning estimates until a
  confidential-mode Azure H100 calibration is retained. Memory-bandwidth
  ratios are roofline inputs, not runtime multipliers.

Attestation collection, remote appraisal, and HSM signing should normally be
seconds-to-minutes of fixed overhead. Measure them during the pilot and retain
their timings alongside the run receipt; do not extrapolate those network and
service latencies from the DGX Spark.
