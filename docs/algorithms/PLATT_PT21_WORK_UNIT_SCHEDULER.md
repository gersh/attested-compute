# Platt PT21 windowed work-unit schedule and CPU cost

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

[`PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md`](PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md)
fixes the mathematics of the CPU route: the pinned
[`djplatt/code@42b2142`](https://github.com/djplatt/code) `zeta_arb` program with
one hash-pinned Appendix C interpolation correction, the `1008`-height logical
block grid starting at `10^10`, the fail-closed transcript contract, and the
telescoping Turing-count chain.  This note covers only what has to be true for
that campaign to actually be *run*: how the work is divided, how a worker
survives being killed, what each piece of evidence is, and what the whole thing
costs.

Nothing here changes the trust boundary.  Every artifact still reports
`source_claim_ready=false`.  Hardy-Z realization, the analytic Turing inputs,
and the interval below `10^10` remain separate obligations.

## Getting a runner at all

The campaign document's build command assumes a FLINT 3.6 prefix already
exists.  Producing one from the pinned checkout on a bare Ubuntu 24.04 host,
without root, needed three things that are worth writing down because the Azure
image will need them too:

* `libgmp-dev` headers live under `/usr/include/aarch64-linux-gnu/`, which the
  compiler finds by default, but `libmpfr-dev` is not installed.  `apt-get
  download libmpfr-dev libmpfr6` plus `dpkg -x` into a local prefix is enough;
  pass that prefix through `CPPFLAGS`/`LDFLAGS` to FLINT's `configure` and
  through `--mpfr-prefix` to `fetch_platt_pt21_windowed.py`.
* FLINT ships `configure.ac`, not `configure`, so `./bootstrap.sh` must run
  first.  It needs `libtool`, `libtool-bin`, and `libltdl-dev`.  Extracted to a
  local prefix, `libtoolize` still hard-codes `/usr/share/libtool`; the
  supported override is the `_lt_pkgdatadir` environment variable, and the
  directory it points at must contain `build-aux/`, `libltdl/`, and `m4/`.
* `tools/fetch_flint_platt.py --build` calls `./configure` directly and
  therefore cannot be used until `bootstrap.sh` has run.  Use it for
  `--verify-only`, which is the part that matters, and drive the build
  separately.

With that done the documented command works unmodified and both retained known
answers pass:

```bash
python3 tools/fetch_platt_pt21_windowed.py build/upstream/djplatt-code \
  --build build/platt-pt21/arb-zeta \
  --flint-prefix build/upstream/flint-3.6-install \
  --mpfr-prefix build/upstream/mpfr-prefix/usr --test --pretty
```

```text
[10000000000, 10000001008]   -> 3399 zeros
[3000000000000, 3000000001008] -> 4314 zeros
runner sha256 96a3648eafb9cdeb1b3b9c0016491052225502822bf95ba1798366d61aa3cb1c
```

The build report records the interpolation correction identities, so a binary
built without the Appendix C radius cannot be mistaken for this one.

## Measured basis

All of the arithmetic below rests on two numbers obtained by regressing runner
CPU time against block count on one core of the local DGX Spark ARM host,
2026-07-30, against the corrected pinned binary
`96a3648eafb9cdeb1b3b9c0016491052225502822bf95ba1798366d61aa3cb1c` built on
FLINT 3.6:

| blocks in one invocation | user CPU seconds |
|---:|---:|
| `1` | `5.74` |
| `2` | `11.06` |
| `4` | `21.83` |
| `8` | `43.23` |
| `16` | `86.27` |

Least squares on those five points gives

```text
marginal cost   5.36917 s per 1008-height logical block
fixed cost      0.337 s per runner invocation
peak RSS        about 281 MB, independent of block count
```

Two facts matter more than the fit itself.

**The rate does not depend on height.**  One block at `3*10^12` took `5.71` s
against `5.74` s at `10^10`.  The Dirichlet sum length `M=768000`, the Taylor
order `K=23`, and both FFT lengths are compile-time constants, so the program
does the same work at every window.  Linear extrapolation across the full
`2,966,443,783`-block range is therefore sound rather than optimistic.

**Per-invocation cost is negligible.**  `0.337` s of startup against `5.369` s
of useful work per block means even a one-block work unit would waste only
`6%`, and a 512-block unit wastes `0.012%`.  Restart cost is consequently not
what sizes the work unit; preemption and receipt volume are.

The 8-block figure reproduces the `43.03` s / `5.37875` s per block recorded in
the campaign document, to `0.2%`.  Two further regressions through the tool's
own `--calibrate` path, which measures child user+system CPU rather than
`/usr/bin/time`, were run *concurrently with each other* to see how much
memory-bandwidth contention costs.  They returned `5.35843` and `5.45513` s per
block.  So four independent regressions on a busy shared host span

```text
5.3584 -- 5.4551 s per block  =  503.8 -- 512.9 core-years,
```

a `1.8%` spread that is entirely accounted for by contention.  The `5.36917`
used below is the quietest of them; a reader who prefers the pessimistic end
should read every dollar figure as `1.8%` higher.  Contamination at that scale
does not move any decision this document supports.

## Work unit

A **unit** is `blocks_per_unit` adjacent logical blocks; the default is `512`,
about `2749` s or `0.76` core-hours.  A **shard** is `units_per_shard = 2048`
adjacent units, so `2^20` blocks -- deliberately the same shard geometry the
H100 plan already uses, which keeps the two schedules describing the same
brackets.  The full range is then

```text
2,966,443,783 blocks = 5,793,836 units = 2,830 shards.
```

Unit size is a three-way trade:

* *smaller is better for preemption*, because an eviction discards at most the
  work since the last checkpoint;
* *larger is better for receipt volume*, because each unit costs one small JSON
  file and one entry in a Merkle level;
* *start cost is irrelevant* at any size above a handful of blocks, per the
  measurement above.

At `512` blocks the campaign has `5.79` million unit receipts of about `900`
bytes, roughly `5` GB before sealing.  Sealing a shard replaces its `2048` unit
receipts with one shard receipt plus an ordered `2048`-line digest file, so the
retained artifact set falls to about `380` MB for the whole campaign and stays
independently re-Merkle-able.  Halving the unit to `256` blocks would double
both counts for no scheduling benefit, because the checkpoint already bounds
preemption loss; doubling it to `1024` saves little and lengthens the tail at
the end of the campaign.

### Segments, and why a unit is not one process

A unit does not have to be produced by one process.  It is executed as a
sequence of **segments**, each a fresh runner invocation covering the blocks
the previous segments did not commit.  The source program is stateless across
logical blocks -- each block derives its own left and right Turing flanks -- so
splitting a unit is semantically invisible.

The scheduler exploits this in two ways.  It writes a progress checkpoint every
`checkpoint_blocks` completed blocks (default `32`, about `172` s), and it
installs a `SIGTERM`/`SIGINT` handler that flushes every completed block before
terminating the child.  An Azure Spot eviction, which delivers a scheduled
event roughly `30` s ahead, therefore loses only the single in-flight block;
an ungraceful kill loses at most one checkpoint interval.

### Determinism

Unit identity is a **semantic digest** `unit_sha256` over the schedule digest,
the unit index, the block and height range, the endpoint Turing counts, the
total, the digest of the ordered per-block record list, the runner digest, the
reviewed-source digest, the precision, and the step.  It excludes wall time and
it excludes the segment list.  Consequently:

* a unit run in one shot and the same unit resumed across three preemptions on
  three different machines produce byte-identical digests;
* a re-run is a free cross-check rather than a hazard.  `_commit_unit` writes a
  receipt only if none exists, and otherwise requires the retained
  `unit_sha256` to match.  A disagreement fails the campaign closed and is
  reported as nondeterminism, not silently resolved;
* `replay-unit` re-executes a retained unit in one segment and requires digest
  equality, which is the direct test that segmentation changed nothing.

Assignment is a pure function of the immutable plan: unit `i` is blocks
`[i*512, min((i+1)*512, block_count))`.  Nothing about a worker, a host, or an
order of events enters it.

## Scheduler

```bash
OUT=/durable/pt21-windowed
python3 tools/tg_platt_windowed_scheduler.py --pretty init "$OUT" \
  --runner build/platt-pt21/arb-zeta

# one worker, pulling units until told to stop
python3 tools/tg_platt_windowed_scheduler.py --pretty work "$OUT" \
  --runner build/platt-pt21/arb-zeta --max-units 64 --worker-id node-17

# fixed partition among cooperating workers
python3 tools/tg_platt_windowed_scheduler.py --pretty work "$OUT" \
  --runner build/platt-pt21/arb-zeta --stride 4096 --offset 17

python3 tools/tg_platt_windowed_scheduler.py --pretty seal-shard "$OUT" 0 \
  --prune-units
python3 tools/tg_platt_windowed_scheduler.py --pretty finalize "$OUT"
```

Claims are **advisory leases**, not locks.  A worker takes a unit by creating
`leases/unit-NNNNNNNNNN.lease` with `O_EXCL`; the file is touched at every
checkpoint, so a live worker's claim stays fresh.  A lease older than
`lease_seconds` is stealable, which is how a lost node's units come back into
circulation.  Correctness never depends on the lease being honoured, because
duplicate execution is caught by digest equality.  Losing a lease costs time,
never a wrong answer.

`next_unit` never enumerates the whole unit space.  It walks shards from a
starting index, skips any shard that has a receipt without listing its units at
all, and lists at most `units_per_shard` directory entries for the first
unsealed shard.  Resume cost after a mass eviction is therefore bounded by the
size of one shard, not by the five million completed units behind it.

## Aggregation

Three levels, each of which only ever holds one level's worth of data:

| level | count (full range) | binds |
|---|---:|---|
| unit receipt | `5,793,836` | block/height range, endpoint counts, ordered record digest, runner digest, reviewed-source digest, precision, step |
| shard receipt | `2,830` | unit contiguity, count-chain continuity, telescoping total, Merkle root over `unit_sha256` |
| campaign artifact | `1` | shard contiguity, count-chain continuity, telescoping total, Merkle root over `shard_sha256`, prefix binding |

The Merkle rule is the one already recorded in
`PLATT_PT21_AZURE_EXECUTION_CONTRACTS.json`: domain-separated leaves and nodes,
odd levels duplicating their final entry.  `seal-shard --prune-units` deletes
the unit receipts after writing `unit-digests.txt`, so the root stays
recomputable by an independent checker from the retained files alone.

The campaign artifact is a single JSON object under two kilobytes.  It is the
object an Azure confidential-compute receipt should cover, and it is what
`SparkInterval/Execution/RegisteredZetaRHCertificate.lean` ultimately needs a
signed `true` outcome about: that file's
`plattTrudgianFiniteRHProductionCheck` consumes a `SignedResultCertificate`
whose `resultCertificate` is exactly `"true"` for
`plattTrudgianFiniteRHProductionV1`.  The scheduler therefore does not invent a
second result format; it produces the small, count-telescoped, Merkle-rooted
object that such a registered program would be checking, and leaves
`execution_attested` and `lean_atom_discharged` false because it is not itself
that program.

## Dry run

A `64`-block bounded schedule (`8` units of `8` blocks, `2` shards of `4`
units) was run end to end against the real corrected binary on the local host.
Its measured behaviour:

| step | result |
|---|---|
| `init` | `schedule_sha256 = 87c2a6ec34544d87ea0dab5582acec4339e87ca95c070d43a2ec628655e3ca68` |
| `run-unit 0` | `43.50` s wall, `8` blocks, `27,193` zeros, `first_count = 32,130,158,315` |
| `SIGTERM` after `20` s of unit `1` | exit `3`, `3` of `8` blocks committed, checkpoint retained |
| resume unit `1` | `27.33` s, completed as two segments (`3` then `5` blocks) |
| `replay-unit 1` | single-shot re-execution reproduced `unit_sha256` exactly |

The `first_count` of unit `0` is the interesting one.  The Turing method
derives `N(10^10)` from the block's own left flank, so the runner independently
states

```text
N(10000000000) = 32130158315,
```

which is exactly the value the LMFDB prefix importer reconstructs from block
`693` of `zeros_9998546000.dat` by the unrelated route `32130155617 + 2698`.
Two independent artifacts agreeing on the boundary count is a real check on
both.

Full transcripts and the complete dry-run measurement table are reproduced by
`tests/test_tg_platt_windowed_scheduler.py`, which drives a stub runner and
covers geometry, digest stability under segmentation, duplicate-execution
rejection, failure tokens, lease stealing, Merkle recomputation, pruning, and
every gap/chain rejection.

## Cost

`tools/model_platt_pt21_cpu_cost.py` computes the table from the two measured
constants and live Azure retail prices.  `--calibrate RUNNER` redoes the
regression locally; `--live-prices` refetches and reports drift against the
captured values.  As of 2026-07-30 the live query reproduced the captured
prices with zero drift.

Work, exactly:

```text
block work        2,966,443,783 * 5.36917 s = 4,424,261 core-hours
invocation work   5,793,836     * 0.337 s   =       542 core-hours
total useful                                = 4,424,804 core-hours
                                            =     504.8 core-years
```

That is `59%` of the `7.5` million core-hours reported for the original
computation.  The two numbers are not in conflict and neither is wrong.  The
published figure covers a 2020 run on 2020-era cores, across a parameter
schedule that raises `M` with height (the pinned upstream tree contains a
ladder of parameter sets from `M=198000` at `2*10^11` up to `M=714000` at
`2.6*10^12`), plus its own prefix, replay, and operational overhead.  The
`504.8` core-years here is the same algorithm at one fixed parameter set,
remeasured on a 2025-era ARM core, for the high range only.  The honest reading
is that hardware and a single parameter choice account for the gap; it is not
evidence that the published number was inflated.

Preemption adds very little.  With `172`-second checkpoints, a `120`-second
replacement-node cost, and a mean twelve hours to eviction, the expected
overhead is

```text
(172/2 + 120) / 43200 = 0.48%.
```

Even at a punishing one-hour mean time to eviction it is `5.7%`.  This is the
payoff from checkpointing inside the unit: without it, a `0.76`-core-hour unit
re-run from scratch would cost `3.3%` at twelve hours and `50%` at one hour.

Prices are US East, Linux, `Consumption`, captured and re-verified live on
2026-07-30:

| SKU | vCPU | physical cores | on-demand $/node-h | spot $/node-h |
|---|---:|---:|---:|---:|
| `Standard_D64ps_v6` (Cobalt 100, no SMT) | `64` | `64` | `2.246` | `0.70165` |
| `Standard_F64s_v2` (x86, SMT) | `64` | `32` | `2.706` | `0.59532` |
| `Standard_D96as_v6` (x86, SMT) | `96` | `48` | `4.358` | `0.913437` |

The one genuinely unknown factor is how an Azure vCPU compares with a DGX Spark
core on this workload.  The model does not hide it:

| relative core speed | SKU | spot | on-demand |
|---:|---|---:|---:|
| `1.0` | `Standard_F64s_v2` | `$41,355` | `$187,086` |
| `1.0` | `Standard_D96as_v6` | `$42,303` | `$200,868` |
| `1.0` | `Standard_D64ps_v6` | `$48,742` | `$155,283` |
| `0.7` | `Standard_F64s_v2` | `$59,079` | `$267,266` |
| `0.7` | `Standard_D64ps_v6` | `$69,631` | `$221,833` |
| `0.5` | `Standard_F64s_v2` | `$82,710` | `$374,172` |
| `0.5` | `Standard_D64ps_v6` | `$97,483` | `$310,566` |

`1.0` is optimistic for every row.  The `F64s_v2` and `D96as_v6` rows charge
per vCPU, and two hyperthreads on one physical core do not deliver two cores of
FFT throughput, so their realistic factor is nearer `0.5`--`0.6`.  `D64ps_v6`
is a genuine core per vCPU but is Neoverse N2 against the measured host's much
wider cores, so its realistic factor is more like `0.6`--`0.8`.  **The
defensible planning band is therefore `$60k`--`$100k` at Spot and
`$220k`--`$310k` on demand**, and the single measurement that would collapse it
to a point is one calibration run of the same binary on the intended SKU:

```bash
python3 tools/model_platt_pt21_cpu_cost.py --pretty --live-prices \
  --calibrate build/platt-pt21/arb-zeta --calibrate-blocks 1,2,4,8
```

Wall clock is a pure division, since units are independent and the campaign has
no cross-node communication at all:

| concurrent cores | wall days (spot, with preemption overhead) |
|---:|---:|
| `1,000` | `185.2` |
| `5,000` | `37.0` |
| `20,000` | `9.3` |
| `50,000` | `3.7` |

At `20,000` concurrent vCPUs the whole high range finishes in about nine days
of wall clock at relative speed `1.0`, or about eighteen at `0.5`.  Quota, not
money or algorithm, is the binding constraint at that width.

Excluded from every row above: the interval below `10^10` (see
[`PLATT_SUB_1E10_PREFIX.md`](PLATT_SUB_1E10_PREFIX.md)), receipt storage and
egress, confidential-compute attestation and its appraisal, audit replay beyond
the campaign itself, and operator time.

## What this does not close

1. No production attestation exists.  `execution_attested` is false in every
   artifact this module writes, and the campaign object is not a signed
   registered-program outcome.
2. The analytic realization is untouched: Arb's Hardy function is still not
   identified with Mathlib's `riemannZeta`, and the Turing inputs remain
   theorem premises.  A perfectly executed campaign produces auditable finite
   evidence, not the Lean atom.
3. The Appendix C obligations in
   [`PLATT_LEMMA_C3_SOURCE_MAP.md`](PLATT_LEMMA_C3_SOURCE_MAP.md) are
   unchanged.
4. Relative core speed on the target SKU is unmeasured, which is the entire
   width of the cost band.
