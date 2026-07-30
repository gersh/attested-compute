# Platt PT21 windowed source campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

This is the currently preferred implementation route for the expensive
`platt-trudgian-rh-3e12` range.  It invokes D. J. Platt's public windowed
Arb/Turing implementation, rather than asking FLINT's convenient local
zero-isolator API to rediscover trillions of zeros one small index batch at a
time.

This route is implemented and has real known-answer runs, but it is not yet a
complete Azure proof run.  The full H100 port is unfinished and no production
attestation/receipt exists.

Two things once listed here as open are now settled and have their own notes.
The CPU cost is `4,424,804` core-hours, or `504.8` core-years, from a regression
against the corrected binary rather than a round number; see
[`PLATT_PT21_WORK_UNIT_SCHEDULER.md`](PLATT_PT21_WORK_UNIT_SCHEDULER.md) for
the measurement, the preemption-tolerant work-unit design, and the price band.
The interval below `10^10` still needs its own accepted artifact, but the
choice is no longer open: see
[`PLATT_SUB_1E10_PREFIX.md`](PLATT_SUB_1E10_PREFIX.md), which measures the
prefix at `0.54%` of the campaign.

## Upstream source and licensing boundary

The reviewed source is fetched from
[`djplatt/code`](https://github.com/djplatt/code) at commit
`42b21426718e542daa2b006dc05ea2d7f26426e6`.  The eleven files under
`zeta_arb/` that form the executable have aggregate reviewed-source digest

```text
9a748490b327b102d53506e390a42afac796a5b42b42060fe82aa8f5744bb152
```

under the domain `sparkinterval/platt-pt21-reviewed-source-set/v1`.
[`PLATT_PT21_WINDOWED_UPSTREAM.json`](../../specifications/PLATT_PT21_WINDOWED_UPSTREAM.json)
records every file hash and size.

The reviewed split-file source initializes Appendix C's interpolation radius
but does not add it to `arb_inter_t`'s returned value.  The fetch/build tool now
applies one hash-pinned local correction in a temporary tree; it never mutates
the pristine checkout, and its build report records both source identities.
See the exact Lemma C.1/C.3 statement map, the two typesetting corrections,
and the restored-radius known answers in
[`PLATT_LEMMA_C3_SOURCE_MAP.md`](PLATT_LEMMA_C3_SOURCE_MAP.md).  A binary built
without that correction is no longer an acceptable production runner.

The upstream repository contains no license or copying file.  Its license is
therefore recorded as `NOASSERTION`, and this project does not vendor or
redistribute the source.  The fetch/build tool compiles directly from a
detached upstream checkout.  Permission must be obtained before distributing
that source or a source-derived binary.

```bash
python3 tools/fetch_platt_pt21_windowed.py build/upstream/djplatt-code \
  --build build/platt-pt21/arb-zeta \
  --flint-prefix build/upstream/flint-3.6-install \
  --test --pretty
```

The two retained known-answer geometries are:

| interval | rigorously isolated zeros |
|---|---:|
| `[10000000000, 10000001008]` | `3399` |
| `[3000000000000, 3000000001008]` | `4314` |

Both pass with FLINT 3.6 as well as the historical FLINT 2.5.2 / Arb 2.15.1
stack.  The compatibility rebuild was useful, but the earlier failures were
ultimately caused by asking the published parameter set to certify an
over-wide window.

## Why the step is exactly 1008

The source fixes sample spacing `21/512`, FFT length `131072`, intermediate
FFT length `32768`, `768000` Dirichlet terms, and `23` Taylor terms.  A step of
`1008` is exactly `24576` samples and is accepted at both ends of the source
height range.

The executable is not fail-closed by itself: several fatal or inconclusive
paths print `Unknown`, `Missed`, `Problem`, or `Exiting` and then return status
zero.  For example, widths `2100` and `2688` produce intervals too wide to
determine an endpoint sign at height `10^10`, yet the process exits zero.

[`platt_windowed_campaign.py`](../../tg_verifier/platt_windowed_campaign.py)
therefore treats exit status as only a transport check.  For every logical
block it requires exactly one line

```text
looking for MAX-MIN=COUNT zeros
```

and exactly one matching line

```text
All COUNT zeros found in region LOWER to UPPER using stat points.
```

It rejects every known failure token, checks `MAX - MIN = COUNT`, checks the
fixed `1008` height grid, and checks that consecutive Turing counts meet
exactly.  The finalizer repeats the count-continuity check across shard
boundaries.  Full logs are retained next to compact receipt summaries; replay
reruns the source executable and compares the semantic record digest while
allowing timing text to vary.

## Exact high-range geometry

The high-range campaign starts at `10^10` with

```text
N(10^10) = 32130158315.
```

It uses

```text
2966443783 blocks × 1008
```

and ends at `3000175333264`, which is exactly `464` above the theorem endpoint
`3000175332800`.  This deliberately proves a slightly stronger height range
instead of weakening or rounding the source endpoint.

```bash
OUT=build/tg/platt-pt21-windowed
python3 tools/tg_platt_windowed_campaign.py --pretty init "$OUT" \
  --runner build/platt-pt21/arb-zeta
python3 tools/tg_platt_windowed_campaign.py --pretty range "$OUT" 0
python3 tools/tg_platt_windowed_campaign.py --pretty run-shard "$OUT" 0 \
  --runner build/platt-pt21/arb-zeta
python3 tools/tg_platt_windowed_campaign.py --pretty replay-shard "$OUT" 0 \
  --runner build/platt-pt21/arb-zeta
```

The default CPU shard contains `16384` adjacent blocks.  That is an operator
checkpoint choice, not a mathematical parameter, and can be changed only in
a fresh immutable plan.  A future batched H100 runner should use much larger
shards while preserving the same logical block grid and transcript semantics.

The final CPU high-range artifact intentionally reports
`source_claim_ready=false`.  It establishes the expensive range from `10^10`
upward, but a separately reviewed, accepted prefix computation is required to
cover all smaller ordinates.  The
[`LMFDB zeta-prefix importer`](LMFDB_ZETA_PREFIX_IMPORT.md) now pins the public
Platt/LMFDB inventory, checks the complete binary framing/continuity contract,
and independently reproduces the exact boundary count
`N(10^10)=32130158315`.  It remains candidate/source evidence until the
Hardy-Z and Turing realization is either independently replayed or retained as
an explicit trusted-source premise.  Neither path by itself identifies Arb's
Hardy function with Mathlib's `riemannZeta`; that realization remains part of
the registered trusted-compute review boundary.

## Measured CPU work and H100 target

On the local DGX Spark ARM CPU, eight consecutive source-height blocks took
`43.03 s`, or `5.37875 s/block`, with about `281 MB` peak RSS.  Straight
scaling gives approximately `4.43 million` one-core hours for the high range.

A later 1/2/4/8/16-block regression against the corrected binary refines this
to `5.36917 s` marginal per block plus `0.337 s` per runner invocation, and
confirms that the rate does not vary with height (`5.71 s` for one block at
`3*10^12`).  The exact totals, the work-unit design that makes the campaign
survive spot preemption, and the Azure price band are in
[`PLATT_PT21_WORK_UNIT_SCHEDULER.md`](PLATT_PT21_WORK_UNIT_SCHEDULER.md).  The
`504.8` core-years there is `59%` of the roughly `7.5 million` core-hours
reported for the original computation; that note explains why the two figures
are consistent rather than in conflict.  Neither number makes merely deploying
the CPU executable to Azure a finished proof run.

The published loop performs, per logical block:

```text
23 × 4 × (32768/2) × 15 + (65536/2) × 16
= 23134208 radix-2 butterflies,
```

plus `23 × 768000 = 17664000` Dirichlet/Taylor term visits.  The full high
range is therefore:

| work item | exact count |
|---|---:|
| interval FFT butterflies | `68626327496228864` |
| Dirichlet/Taylor term visits | `52399262982912000` |

Eight GPUs must each sustain `14.184 billion` interval butterflies/s to finish
the FFT portion in seven days.  The repository's existing directed-binary64
radix-2 CUDA engine measures `1.38`--`1.55 billion` butterflies/s on the local
GB10.  The following is a sensitivity calculation, not an H100 benchmark:

| per-H100 interval-FFT rate | eight-H100 FFT wall time | PAYG node cost | Spot node cost |
|---:|---:|---:|---:|
| `15.0B/s` | `158.86 h` (`6.62 d`) | `$8,871` | `$1,803` |
| `21.45B/s` | `111.09 h` (`4.63 d`) | `$6,203` | `$1,261` |

Costs use the repository's captured prices of `$6.98` PAYG and `$1.419034`
Spot per `Standard_NCC40ads_H100_v5` node-hour.  They exclude input generation,
the `52.4` quadrillion term visits, ambiguous-block CPU replay, prefix work,
storage, retries, and attestation.  Consequently the lower row is a roofline
target, not a claim that the complete proof already meets the one-week or
`$10k` requirement.

## Bucketed Taylor core

The production-shape CUDA core is now implemented in
[`h100_tg_platt_windowed_core.cu`](../../gpu/platform/h100/h100_tg_platt_windowed_core.cu).
It preserves the source geometry `M=768000`, `K=23`, and `N1=32768`, sorts the
terms by the source's conjugate-order bucket, gives one deterministic warp to
each nonempty bucket, and uses directed binary64 interval multiplication and
addition.  The residual powers are independent of the height window.  The
runner therefore builds the complete

```text
23 * 768000 * 16 = 282624000 byte
```

power table once and reuses it for every window, instead of performing the
source program's 16.9 million residual-power updates again in each window.

```bash
cmake -S . -B build/platt-windowed-core \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON
cmake --build build/platt-windowed-core \
  --target sparkinterval-tg-platt-windowed-core
build/platt-windowed-core/sparkinterval-tg-platt-windowed-core \
  --terms=768000 --stages=23 --blocks=4 --repetitions=1 \
  --source-geometry
```

The first short 2026-07-22 source-geometry run on the local GB10 sustained
`4,617,565,981` directed interval term visits/s.  After the Q192 phase path was
enabled, a longer 256-block run sustained `3,696,992,879` visits/s, or
`209.30` logical blocks/s for this core; this lower number is the appropriate
local planning basis.  The MPFR audit initializer took about 18 seconds but is
outside the timed kernel region.  Exact full-range arithmetic then gives:

| sensitivity | eight-device Taylor-core wall time |
|---:|---:|
| measured long-run GB10 rate | `20.51 d` |
| `3x` GB10 rate per device | `6.84 d` |
| `5x` GB10 rate per device | `4.10 d` |
| `10x` GB10 rate per device | `2.05 d` |

The seven-day Taylor-only gate is `10.830 billion` term visits/s/H100, only
`2.93x` the longer measured GB10 rate.  This is promising but is not the
end-to-end gate: on the same GPUs the FFT work, phase maintenance,
interpolation, zero isolation, and Turing checks consume additional time.  The
executable's JSON therefore labels itself
`gamma_taylor_synthesis_and_exact_fft_work_shape_not_a_source_certificate`.

The 768,000-term host MPFR initializer is useful for known-answer comparison
but cannot be run once per production window.  The CUDA runner stores each
logarithmic
turn at Q192, multiplies the three limbs by the integral block centre modulo
`2^192`, reduces to an octant, and evaluates directed degree-17/18
sine/cosine polynomials.  Every one of the 768,000 initial and step-phase
enclosures passed an independent 320-bit MPFR midpoint audit.  A full phase
anchor measured `179.25 million` terms/s, about `4.28 ms`, and the timed loop
can re-anchor every 256 blocks instead of allowing binary64 rectangle growth
across the whole campaign.

[`FixedPhase.lean`](../../SparkInterval/Zeta/FixedPhase.lean) proves from the
nearest-Q192 premise that the angular, sine, and cosine errors are each at
most `pi * height / 2^192`.  What remains formal at this boundary is the
limb-level CUDA refinement and the exact directed-polynomial trace/remainder
certificate.  The MPFR midpoint audit is a strong implementation test, not a
substitute for those two proofs.

## Compact Gamma-row certificate

The source evaluates 32,768 complex Gamma values in every window.  Streaming
that many CPU values per window would erase the GPU speedup.  The production
replacement now emits six interval Taylor coefficients for

```text
L_T(u) = log Gamma(1/4 + i(T+u)/2) + pi(T+u)/4,
|u| <= 2688.
```

[`tg_platt_gamma_taylor.cpp`](../../reference/tg_platt_gamma_taylor.cpp) uses
the pinned FLINT 3.6 `acb_poly_lgamma_series` implementation at 256 bits.  A
second series evaluation whose centre contains the entire source window
encloses the sixth derivative coefficient uniformly, giving the complex
integral-Taylor remainder.  Each packet contains the exact FLINT dyadic
coefficient endpoints, directed binary64 projections, Q192 phase anchor and
grid step, their angular errors, and separate hashes of the exact and projected
transcripts.  The Gaussian `-u^2/(2*116^2)` stays an exact quadratic evaluated
by the GPU.

The earlier `--repeat` rate of 24,000--29,000 certificates/s reused one height
and was not evidence that the complete varying-height sequence could be
produced.  The same executable now has a genuine range-indexed stream mode.
It evaluates every requested centre

```text
T(block) = 10000000000 + 504 + 1008*block
```

and emits one canonical 264-byte record containing the twelve outward
binary64 coefficient intervals, two Q192 phase values, their independently
computed angular errors, and the uniform logarithmic remainder.  Records are
framed in independently SHA-256-authenticated chunks; a footer binds the
header and the complete ordered stream.  The header pins the Platt source-set
digest, Platt commit, FLINT commit, geometry, precision, degree, and invocation
range.  [`platt_gamma_taylor_stream.py`](../../tg_verifier/platt_gamma_taylor_stream.py)
is an independent streaming decoder that checks every hash, range, interval,
error bound, footer field, and absence of trailing bytes.

Its `open_gamma_taylor_chunk_stream` API is the bounded-memory online-consumer
boundary.  It does not yield a chunk until that chunk's exact position,
length, SHA-256, and every projected interval/error invariant pass.  Chunk
results remain provisional: exhausting the iterator authenticates the footer
and complete ordered-stream digest, and a normal context-manager exit before
that point raises an error.  A GPU worker must therefore defer its final
success artifact until `chunks.authenticated` is true.  The production plan
also binds `chunk_records=4096`, limiting one live payload to 1,081,344 bytes.
The API permits a stricter `max_chunk_records` memory policy and fails while
reading the header if the producer exceeds it.  Retained inputs must be
regular files.  For retention-free colocated production, an explicit
`allow_fifo=True` admits only a nonsymlink named pipe; the known-answer suite
runs the FLINT producer and iterator concurrently through such a pipe and
still requires the terminal footer before success.

```python
with open_gamma_taylor_chunk_stream(
    path,
    expected_first_block=first,
    expected_block_count=count,
    expected_chunk_records=4096,
    max_chunk_records=4096,
) as chunks:
    for chunk in chunks:
        upload_checked_records(chunk.payload)
    assert chunks.authenticated
    stream_digest = chunks.inspection.stream_sha256
```

An initial attempt required the whole Arb phase interval to select one nearest
Q192 integer.  That condition fails honestly at some high windows because a
sound narrow interval can straddle a half-integer.  The producer now selects
the nearest integer to the deterministic Arb midpoint and computes the angular
error against the *entire* interval.  This is both total on the tested high-end
range and mathematically stronger than discarding the straddling uncertainty.

Fresh 100,000-window hash-only runs on the local DGX Spark ARM CPU measured:

| sampled blocks | varying-height records/s | projected full one-core time |
|---:|---:|---:|
| `1000000..1099999` | `34,947.87` | `23.58 h` |
| final 100,000 blocks | `47,255.77` | `17.44 h` |

The full record payload is `783,141,158,712` bytes (`729.36 GiB`), plus about
52 MB of framing at the default 4096-record chunk size.  It need not be
retained: a seven-day campaign consumes only `1.295 MB/s` aggregate, or about
`162 kB/s` at each of eight equally partitioned GPU workers.  Thus a single
ordinary CPU core can generate the full sequence in roughly one day, while
one producer per H100 has ample online headroom.  This closes coefficient
*production*, not consumption: the current CUDA benchmark must still consume
each authenticated record rather than reuse its first-window KAT.

The H100-shaped kernel synthesizes all 32,768 Gamma samples using directed
polynomial, Q192 phase, and range-reduced exponential arithmetic.  On the
local GB10 it sustained 58.66 million Gamma values/s.  Five fixed grid probes,
including both extreme tails and the centre, were independently recomputed by
fresh `acb_lgamma`; every FLINT interval was contained in the GPU interval.

```bash
build/tg-production-kat/sparkinterval-tg-platt-gamma-taylor \
  --height 10000000504 --precision 256 --degree 6 \
  --audit-samples 257

build/tg-production-kat/sparkinterval-tg-platt-gamma-taylor \
  --stream-first-block 0 --stream-blocks 1048576 \
  --stream-chunk-records 4096 --stream-audit-stride 1048576 \
  --audit-samples 9 --stream-output /durable/pt21-gamma-shard-0.bin

python3 tools/tg_platt_gamma_taylor_stream.py \
  /durable/pt21-gamma-shard-0.bin \
  --expected-first-block 0 --expected-block-count 1048576 --pretty

build/platt-windowed-core/sparkinterval-tg-platt-windowed-core \
  --terms=768000 --stages=23 --blocks=256 --repetitions=1 \
  --reanchor-blocks=256 --source-geometry --gamma-synthesis
```

[`GammaTaylorCertificate.lean`](../../SparkInterval/Zeta/GammaTaylorCertificate.lean)
proves, without a project axiom or native evaluation, coefficient-error
propagation, addition of the analytic remainder, Gaussian non-amplification,
complex-exponential error propagation, the exact `|u| <= 2688`, `h=116`
specialization, and final rational-rectangle containment.  The remaining
analytic realization is explicit: a reviewed FLINT transcript must be shown to
enclose the mathematical log-Gamma branch.  The five-point comparison is a
known-answer test, not that analytic theorem.  Likewise, checking all finite
stream records does not itself prove the FLINT-to-Mathlib realization.

## Combined Taylor and exact FFT work shape

The runner also executes the exact transform geometry from the source work
count: four batched length-32768 transforms for each of the 23 Taylor rows,
followed by one length-65536 transform.  It uses one two-dimensional launch to
form all 23 bucket rows, then batched directed-interval radix-2 stages.  This
is the same `23,134,208` butterflies per logical window counted above.

A 256-window source-geometry run on the local GB10, now including Gamma-row
synthesis, measured:

| component | measured rate |
|---|---:|
| compact Gamma-row synthesis | `58.660 million` values/s |
| Q192 phase plus bucketed Taylor rows | `3.791 billion` term visits/s |
| exact batched FFT work shape | `1.879 billion` butterflies/s |
| combined | `57.038` logical windows/s |

Eight equal-throughput GB10 devices would need `75.24` days for these three
components.  The exact seven-day gate is therefore a `10.75x` per-device
uplift.  Applying explicit sensitivity factors to all measured components
gives:

| H100/GB10 sensitivity | eight-device wall time | PAYG H100 cost | Spot H100 cost |
|---:|---:|---:|---:|
| `10x` | `7.52 d` | `$10,082` | `$2,050` |
| `12x` | `6.27 d` | `$8,401` | `$1,708` |
| `14.3x` | `5.26 d` | `$7,050` | `$1,433` |

The `14.3x` row is the advertised H100-NVL/DGX-Spark memory-bandwidth ratio,
not a measured application speedup.  The PAYG costs cover eight H100 nodes for
only these arithmetic components.  Gamma coefficient production is cheap and
the row synthesis is included, but convolution data dependencies,
interpolation/Turing work, prefix verification, replay,
storage, retries, attestation, and CPU nodes remain outside the row.  A
physical strict-H100 end-to-end pilot is therefore still the decision gate;
the `10x` PAYG row leaves essentially no budget margin.

The separate rectangular
[`source-semantic transform runner`](PLATT_WINDOWED_SEMANTIC_TRANSFORMS.md)
executes the actual transform dataflow at `80.27` synthetic-input windows/s.
A Euclidean-disk successor now consumes a hash-bound packet containing the
complete 768,000-term first-window bucket rows and compact-Gamma synthesis;
see
[`PLATT_WINDOWED_DISK_SEMANTIC_PROTOTYPE.md`](PLATT_WINDOWED_DISK_SEMANTIC_PROTOTYPE.md).
It measured `38.142` actual-packet windows/s on GB10. Sequential composition
with the measured `189.20` window/s Gamma/Taylor core gives `31.743` windows/s,
or `135.20` days on eight equal GB10 devices. Equal-throughput sensitivity is
`13.52` days at `10x`, `9.45` days at the uncalibrated `14.3x` bandwidth
roofline, and `6.76` days at `20x`; at least `19.315x` is required to fit seven
days before interpolation, Turing, replay, and operational overhead.

More importantly, the actual first-window disk output had 101,213 ambiguous
real samples out of 131,072. The experiment therefore fails the sign-width
gate regardless of timing.  The runner emits no sign for those samples and a
strict ambiguity mode exits unsuccessfully.  These measurements replace the
older synthetic-input optimism; a physical H100 calibration and a materially
tighter enclosure design are mandatory before an Azure acceptance claim.

A two-limb-center disk successor has now isolated that width problem more
precisely.  It measured `11.3683` windows/s on GB10, but the unchanged v1
source packet still yielded 100,945 ambiguous samples.  An explicitly
non-proof run that discarded only the source-packet radii had zero ambiguous
samples, maximum radius `2.33003e-22`, and minimum sign margin
`1.44178e-21`.  The implication is narrow and operationally useful: the
downstream two-limb transform is promising, but production needs a proved
two-limb Gamma/Taylor packet rather than the current one-ulp binary64 packet.
It does not imply that Turing counts can currently be constructed.

Sequential composition of the measured `189.198` windows/s source core with
the `11.3683` windows/s two-limb transform is `10.7239` windows/s per GB10.
For 16 equal-throughput Azure H100 nodes, the complete 2,966,443,783-window
range has the following sensitivity.  These rows include only those two
machine stages and use the repository's captured prices of `$6.98` PAYG and
`$1.419034` Spot per node-hour:

| H100/GB10 stage sensitivity | 16-H100 wall time | PAYG cost | Spot cost |
|---:|---:|---:|---:|
| `14.3x` | `13.99 d` | `$37,506` | `$7,625` |
| `20x` | `10.01 d` | `$26,817` | `$5,452` |
| `25x` | `8.00 d` | `$21,453` | `$4,361` |
| `30x` | `6.67 d` | `$17,878` | `$3,635` |

The arithmetic-only seven-day gate is a `28.586x` per-H100 uplift over this
GB10 composition.  At exactly seven days, 16 nodes cost about `$18,762` PAYG
or `$3,814` at the captured Spot price.  Thus this 16-node shape can fit both
the time and `$10k` constraints only with discounted/Spot capacity at the
current model; it still has no allowance for interruptions, interpolation,
zero isolation, Turing, prefix work, replay, storage, or attestation.  An H100
pilot and a narrow source packet are both hard gates before treating any row
as a schedule.

## Superseding narrow-DD and shard results

The earlier V1 ambiguity and cost paragraphs above are retained as diagnostic
history.  The current V2 packet stores two-limb centers and honest residual
disks for both the degree-8 Gamma row and all 23 complete Taylor rows.  On the
first window the DD transform certified every sign in the exact source-used
region `[-12870,+12870]`: zero ambiguities among 25,741 retained samples.  It
still reports 72,549 far-tail ambiguities, because those samples are not used
by the source and are not silently promoted.

The source core now has production-shaped absolute-height streaming:

```bash
build/platt-windowed-core/sparkinterval-tg-platt-windowed-core \
  --source-geometry --terms=768000 --stages=23 \
  --blocks=1 --repetitions=1 --fft-passes=0 \
  --dd-source-start-block=0 --dd-source-blocks=32
```

The source core now constructs one rigorous DD phase-step disk per term,
advances the term disks by directed complex-disk multiplication, and performs
a fresh absolute Q192 re-anchor every configurable number of windows (256 by
default).  Its radius is the exact centre-operation residual plus
`|cx| ry + |cy| rx + rx ry`; no rectangle-to-point collapse is used.  A
deterministic 1,024-term final-height MPFR audit fails the run if the recurrent
disk misses the source expression.  The direct first-height audit still checks
all 768,000 terms.  These audits are implementation KATs, not the missing CUDA
instruction-refinement theorem.

Before the accumulator optimization, a 64-window GB10 sample with periodic
recurrence sustained `21.5144801` windows/s versus `15.3723549` windows/s with
direct re-anchor on every window.  The retained implementation now assigns one
block to each active bucket, uses eight warps to consume all 23 stages, and
uses bounded fast DD addition/multiplication.  It keeps both centre limbs and
charges every omitted product, rounded low-part operation, TwoSum underflow,
and input-disk term outwards to an L1 error budget.  A binary64-only centre was
measured and rejected because its roughly `10^-16` bucket radii were unsuitable
for the downstream sign test.

On the same 768,000-term, 23-stage, 64-window GB10 shape, the retained path
sustained `56.8761942` windows/s, a `2.6436x` stream speedup.  An isolated warm
comparison measured `15.8464 ms` for the new accumulator and `44.7547 ms` for
the retained legacy kernel (`2.8243x`).  A directed 320-bit MPFR differential
KAT covered 24 deterministic bucket/stage cases, including the largest bucket:
both kernels had zero failures.  The largest required radius was
`2.1045e-32`; the sampled new radius was at most `1.0868e-31`, versus
`3.2598e-32` for the legacy kernel.  The resulting full first-window packet
also passed the downstream DD transform with zero ambiguities in all 25,741
source-required samples, and the independently parsed sign packet accepted.
These are strong implementation tests, not a CUDA refinement proof.

The downstream transform has since removed power-of-two integer divisions,
cached immutable directed root norms, and replaced its hot Euclidean
square-root error bounds by formally proved L1 upper bounds.  Five fresh
source-shape processes measured a median `14.1516` windows/s; a subsequent
byte-preserving shared-memory fusion of stages 1--8 measured `14.2107`
windows/s in an interleaved A/B.  Sequential composition with the retained
`56.8761942`-window/s accumulator is therefore about `11.3699` windows/s on
this GB10.  The transform remains the local
bottleneck, but the arithmetic-only equal-scaling uplift for 16 devices to
meet seven days falls from `32.21x` to `26.96x` (`53.92x` for eight devices).
At exactly seven days the captured 16-node prices remain about `$3,814` Spot
or `$18,762` PAYG.  These are sensitivity figures, not H100 measurements;
interpolation, event work, attestation, retries, and prefix verification remain
excluded.

The DD transform can now export a 621,202-byte replay packet containing the
25,741 retained disks and their recomputable sign bits.  See
[`PLATT_WINDOWED_DISK_SEMANTIC_PROTOTYPE.md`](PLATT_WINDOWED_DISK_SEMANTIC_PROTOTYPE.md)
and `tools/tg_platt_required_sign_packet.py`.  Keeping such a packet for every
window would consume roughly 1.8 PB, so production must fuse its consumer and
retain only domain-separated event and shard roots.

`tools/tg_platt_h100_campaign.py` now emits immutable `2^20`-block Azure shard
geometry (2,830 shards for the full range), models main, left-flank, and
right-flank event streams separately, and validates source-permitted touching
brackets without allowing interior overlap.  It deliberately reports
`azure_proof_execution_ready=false`: this is a schedulable plan, not a claim
that a fused worker exists.

## Source-shaped blockers and remaining production work

The source does not derive both endpoint counts from one event list.  For a
block `[a,b]` it uses:

| purpose | retained sample offsets | mathematical interval |
|---|---:|---:|
| main isolated count | `[-12288,+12288]` | `[a,b]` |
| lower-count decision | `[-12800,-12288]` | `[a-21,a]` |
| upper-count decision | `[+12288,+12800]` | `[b,b+21]` |

The lower ceiling comes only from the left-flank weight, the isolated slot
count only from the main stream, and the upper floor only from the right-
flank weight.  Acceptance requires the simple equation

```text
lower_count + main_isolated_slots = upper_count.
```

The older Lean `TuringWindowCertificate`/`binds_window` shape ties both weights
and the isolated count to one list, so it is not a valid adapter for this
source. `PairedTuringClosureCertificate` now supplies the source-shaped
replacement: it checks three named streams, binds the left and right weights
to their respective flanks, binds the multiplicity-slot count to the main
stream, and proves the closure equation. Likewise,
`TouchingEndpointCertificate` checks strict sign brackets ordered with `<=`
and proves their selected roots are distinct because they lie in disjoint open
interiors. This covers stationary resolution emitting two brackets sharing a
nonzero midpoint without assuming zero simplicity.

The producer artifact validator correctly permits touching endpoints with the
same nonzero sign and rejects overlapping interiors.
`PT21ArtifactBinding.BlockArtifact` and
`tools/tg_platt_pt21_lean_artifact.py` now strictly decode the v2 compact
rational artifact, derive physical ordinates from rational offsets on the
`21/512` lattice, and construct the three touching families and paired Turing
certificate in Lean.  V2 fixes an important source-fidelity issue in the
earlier draft format: `resolve_stat_point` returns two brackets meeting at a
generally dyadic interpolation point, while `Nleft_int` and `Nright_int`
charge both roots to one conservative integer cell with multiplicity two.
Bracket coordinates and Turing cells are therefore separate fields.  The
checker binds every direct bracket to one multiplicity-one cell and every
stationary pair to one multiplicity-two cell; it does not assume simplicity.

`tools/tg_platt_pt21_fused_artifact.py` is now the deterministic independent
reference finalizer.  Given a required-sign packet and a canonical source
trace, it uses exact Python `Fraction` arithmetic to recover the binary64 DD
endpoint disks, reproduce all direct sign events and source stationary-point
predicates, validate every dyadic stationary resolution, compute both
one-sided event weights, recompute the Turing quotient intervals and unique
integer roundings, require closure, and emit the exact v2 JSON accepted by
Lean.  It also constructs gap-free block/shard Merkle receipts, telescopes
endpoint counts, and—on the unique final block—requires every bracket to lie
strictly to one side of the exact PT21 height before computing
`N(3000175332800)`.  Full production finalization additionally requires the
published count `12363153437138`.

The production-scale chain finalizer is now separately implemented in
[`PLATT_PT21_NATIVE_FINALIZER.md`](PLATT_PT21_NATIVE_FINALIZER.md).  Its
fixed-width `PT21BLK1` records bind the packet, source trace, finite v2 block
artifact, stationary trace, sparse-refinement trace, and measured producer.
The native shard/campaign passes use bounded memory; an independent Python
implementation rescans every retained record and shard and recomputes the
count and Merkle chain.  A validated streaming CPU adapter now joins a
required-sign packet, independently replayed stationary trace, and
block-bound Arb Turing inputs, rebuilds the exact-rational v2 artifact, and
emits the canonical record.  Its authenticated shard mode pipes each record
straight into the pinned native finalizer, releases a terminal `PT21END1`
manifest commitment only after the exact gap-free input manifest succeeds,
and retains the records inside the canonical shard archive without a second
884.07 GiB campaign-wide record spool.  This closes the standalone record
assembly-to-native-shard channel and retained replay.

Worker integration is now partly closed as well.  The fused worker's block
stage runs the stationary Gaussian-sinc resolver and the directed-Arb one-sided
Turing producer inside the same ordered fail-closed loop that already emits
`PT21EVT1`, rebuilds the `PT21SGN1` required-sign packet from the same
replay-owned disks, and streams all three complete adapter inputs as
authenticated `PT21WBF1` frames; an independent Python driver consumes that
stream directly into the exact-rational adapter and the pinned native shard
finalizer, so no per-block artifact and no operator manifest remain.  See
[`PLATT_PT21_BLOCK_INPUT_STREAM.md`](PLATT_PT21_BLOCK_INPUT_STREAM.md).  What
is still not closed is the last clause: the worker does not emit `PT21BLK1`
itself.  The records are produced by the out-of-process Python adapter, which
measured about `3.97` accepted blocks/s on the local GB10 and is therefore the
binding local bottleneck.

The source trace is canonical JSON under
`schemas/platt-pt21-fused-source-trace.schema.json`.  It binds the pinned
upstream commit, interpolation-correction patch, measured worker digest,
required-sign packet digest, 128-bit precision, dyadic stationary outputs,
and four directed Arb inputs for each of the two source-shaped 21-unit Turing
calls: `turing_min` on `[a-21,a]` and `turing_max` on `[b,b+21]`.  Its semantic
status fields are required to remain false.  Consequently neither the Python
replay nor the Lean finite checker can misrepresent a source trace as a proof
that its intervals enclose the mathematical functions.

The actual
Hardy-Z endpoint enclosures, main multiplicity-slot realization, and analytic
Turing realization remain explicit theorem premises; the decoder cannot turn
hashes or sign bits into those facts.

The remaining executable work is therefore:

The varying-height Gamma coefficient boundary is now source-scale capable in
two deliberately distinct formats.  V1 remains available for regression and
compatibility testing: `sparkinterval-tg-platt-gamma-taylor` emits one
264-byte binary64 interval record per logical block.  Its Python, C++, and
CUDA consumers authenticate complete chunks before exposing records and
require the footer, global digest, exact shard range, and EOF before final
acceptance.

The production candidate is V2.
`sparkinterval-tg-platt-gamma-taylor-v2` uses the same pinned FLINT 3.6
certificate construction, but projects all six complex Taylor coefficients
as `ComplexDisk106` values: two binary64 centre limbs plus an outward disk
radius.  Its 312-byte record also retains the constant and one-grid-step phase
at Q192 with independent angular errors and the explicit order-six complex
logarithm remainder.  The header binds the exact rational Gaussian factor
`1/26912` through a canonical DD enclosure.  Chunks and the complete stream
have separate domain-bound SHA-256 authentication, and the bounded reader
rejects payload, footer, range, prefix, and trailing-byte mutations before
acceptance.  Production consumers additionally accept a mandatory
campaign-bound expected whole-stream digest; a different internally
self-consistent stream is rejected at the footer and publishes no row export.

The V2 CUDA synthesizer uses no device transcendental.  It evaluates the real
logarithm and small residual phase with directed DD-disk operations, subtracts
the exact rational Gaussian term, evaluates real exponential after DD
`log(2)` range reduction with an explicit Taylor remainder, and combines a
Q192 phase with DD sine/cosine Taylor disks.  Output is directly
`ComplexDisk106`, the input layout of the persistent accumulator/transform
path.  A 256-bit directed MPFR checker compared every one of the 32,768 output
cells with a fresh direct FLINT V2 row at both the first and terminal campaign
heights.  Both full-row comparisons had zero containment failures.  Maximum
Gamma disk radius was `4.43631e-25` at the first height and `2.22068e-22` at
the terminal height, versus approximately `4.97e-17` in the failed V1 fused
sample.  These are finite implementation checks; FLINT-to-Mathlib realization
and the PT21 source claim remain false.

V1 varying-height generation measured `34,947.87` records/s on a low-range
100,000-record host sample and `47,255.77` records/s on the terminal sample.
V2 measured `32,881.60` and `42,966.75` records/s on the corresponding
100,000-record samples.  That projects to `25.06` and `19.18` one-core hours
for all coefficients.  A retained V2 payload would be `925,530,460,296` bytes,
but a seven-day streamed campaign needs only about `1.530 MB/s` aggregate.
The production design therefore need not retain the complete coefficient
file.  The current V2 worker does, however, require an externally pinned
`--expected-stream-sha256`; self-consistent chunk/footer hashes alone are not
source authentication.  A no-retention deployment must make a deterministic
hash-only producer pass first and stream the pinned second pass through a
FIFO.  A future measured producer-to-consumer channel could replace that
double pass only after its channel binding is part of the receipt contract.
The header's `reviewed_source_sha256` is descriptive metadata: executable
provenance comes from the measured-image/reproducible-build binding, not from
an attacker-copyable header field.

On the GB10, a 16,384-record varying-height sample measured 1,892.24 records/s
inside the GPU pipeline and 1,828.93 records/s end to end.  That projects to
435.47 GPU-hours or 450.54 elapsed hours for the full source on one GB10, and
56.32 elapsed hours under ideal eight-way sharding.  This is a component
benchmark, not an H100 extrapolation and not the rate of the eventual fused
worker.

The two-limb semantic transform is also exposed through
`tg_platt_dd_transform.hpp` as a persistent device-to-device API.  One fixed
source workspace owns all root tables, their one-time directed centre-norm
cache, and scratch arrays (`195,429,312`
device bytes); each call accepts the resident 32,768-cell Gamma row and the
resident `23*32768` Taylor cells, executes the complete source transform, and
leaves all 131,072 real disks—especially the contiguous 25,741-cell required
region—on the device.  Its CUDA smoke test runs the exact source geometry and
checks finite output.  This removes the old 31 MB per-window packet and
process boundary.  The V2 fused worker now calls this API and the implemented
three-stream scanner in one ordered loop.  It emits a terminally authenticated
192-byte `PT21EVT1` record containing the per-stream counts and weights, exact
unresolved-stationary count, and scanner Merkle root, without retaining the
621,202-byte required-sign packet.  See
[`PLATT_PT21_FUSED_EVENT_STREAM.md`](PLATT_PT21_FUSED_EVENT_STREAM.md).
The stationary interpolation and one-sided Turing stages are now joined to the
same fail-closed worker, and a bounded 64-block GB10 run streamed all three
adapter inputs and closed the exact Turing equation for every block.  The
readiness flag `all_window_fused_stream` nevertheless remains false: its
blocker is now exactly that no source-wide run has established useful widths,
and that `PT21BLK1` still comes from the out-of-process exact-rational Python
adapter rather than from the worker.

The V1 `sparkinterval-tg-platt-fused-source-worker` remains a useful negative
regression: its two-window real FLINT-input smoke run processed 51,482
required samples at `9.4754` windows/s on the GB10, but produced 41
sign-ambiguous disks because the binary64 coefficient boxes had already lost
too much width.

`sparkinterval-tg-platt-fused-source-worker-v2` replaces only that Gamma
boundary and preserves the exact 768,000-term/23-stage DD accumulator and
persistent DD transform.  It now continues through the exact left/main/right
device scanner and an authenticated compact event stream; this is a finite
nonterminal handoff, not `PT21BLK1`.  The first block and the terminal block each had
zero invalid and zero ambiguous disks among all 25,741 required samples.
The corresponding maximum transformed radii were `3.67809e-13` and
`1.85320e-10`.  More importantly, 64-window samples at both ends of the
campaign also had zero invalid and zero ambiguous disks among `1,647,424`
required samples per sample.  They sustained `9.2043` and `9.1961` windows/s
on the GB10, with maximum transformed radii `2.92956e-12` and `4.06763e-10`.
Thus V2 removes the observed 41-ambiguity regression without slowing the
local transform bottleneck.  It does not prove useful widths at every one of
2,966,443,783 windows, and it is not an H100 measurement.
The worker now fails the shard when any required disk is invalid *or sign
ambiguous*; it cannot report `accepted:true` for a merely completed transform
with an unresolved finite predicate.

The portable and strict-H100 binaries are reproducible CMake targets:

```bash
cmake -S . -B build/platt-fused \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/platt-fused \
  --target sparkinterval-tg-platt-gamma-v2-gpu-consumer \
           sparkinterval-tg-platt-fused-source-worker-v2

cmake -S . -B build/h100-native \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_H100_NATIVE=ON
cmake --build build/h100-native \
  --target sparkinterval-h100-tg-platt-gamma-v2-gpu-consumer \
           sparkinterval-h100-tg-platt-fused-source-worker-v2
```

The second binary is compiled for `sm_90` and rejects a non-H100 device before
source initialization.

The event benchmark and both V2 workers compile the active CMake configuration
into stdout as `build_profile.cmake_build_config`, report whether `NDEBUG` was
defined, and set `build_profile.release_performance_build` only for the exact
`Release`/`NDEBUG` combination. Throughput projections must require that
boolean to be true. Debug or empty-build-type trees may still be used for
known-answer qualification. These stdout fields do not modify the
authenticated event wire or the worker CLI.

The event stage remains independently exercised as
`sparkinterval-tg-platt-event-scan-benchmark`, and the reusable implementation
is now linked into both V2 worker targets.  Its scanner consumes
the exact 25,741-cell required view, emits separate left/main/right direct and
stationary-candidate streams, preserves the duplicated shared endpoints, and
reproduces strict `stat_pt` and the integer source cell weights.  Malformed,
ambiguous, and capacity-overflow inputs fail closed.  A fixed 2176-bit host
replay checks the compact arrays and a domain-separated SHA-256 Merkle root.
The GB10 measured 254.163 scans/s.  The scanner emits stationary candidates
as unresolved and certifies no multiplicity slots for them, so the scanner by
itself does not close the analytic or Turing boundary.

A bounded first-64-block fused run produced 226,264 direct events and 172
unresolved stationary candidates.  The current worker captures the complete
25,741-disk required view and maximum event arrays into an eight-slot pinned
ring, independently replays them in a bounded eight-thread CPU pool, and
commits results in exact block order.  Against the same frozen binary,
one-slot/one-thread submission took `7.9190 s` and reported `7.9861`
GPU blocks/s; eight slots/threads took `5.3767 s`, reported `10.4750`
GPU blocks/s, and drained in `0.7627 s`.  Both produced the byte-identical
12,672-byte authenticated event artifact
`94d3b2d0a71df3c2251bddce62a70ea8d48c2e96b30ca17e53c5de5f6a2d28ed`.
After the byte-preserving shared-stage fusion, a fresh 64-block run produced
that exact same artifact at `10.4854` GPU blocks/s.  The corresponding
arithmetic-only seven-day uplift is still `29.24x` for 16 equal devices
(`58.47x` for eight), so further transform/finalizer
optimization and a physical H100 calibration remain mandatory.  This is a
GB10 component KAT, not a source-wide or H100 rate.

The bounded adaptive resolver is now implemented as the
[`sparkinterval-tg-platt-stationary-resolver`](PLATT_PT21_STATIONARY_RESOLVER.md)
CPU/FLINT fallback.  It accepts exactly the 25,741 required-region DD disks,
independently reconstructs the complete three-stream stationary-candidate
list, applies the source's 140-term corrected interpolation with a bounded
dyadic search, and repeats every retained endpoint at higher precision.  Its
independent Python validator checks the canonical exact-rational trace, and a
known-answer test inserts the resulting touching pair into the existing v2
block finalizer.  Configure it with the same reviewed FLINT 3.6 checkout used
by the zeta shard:

```bash
cmake -S . -B build/platt-pt21 \
  -DSPARKINTERVAL_FLINT_PLATT_ROOT="$PWD/build/upstream/flint-3.6" \
  -DSPARKINTERVAL_FLINT_PLATT_PREFIX="$PWD/build/upstream/flint-3.6-install"
cmake --build build/platt-pt21 --target \
  sparkinterval-tg-platt-stationary-resolver
ctest --test-dir build/platt-pt21 \
  -R '^tg_platt_stationary_resolver_known_answers$' --output-on-failure
```

The distinct
[qualification-only inline worker](PLATT_PT21_INLINE_STATIONARY.md) now calls
that resolver directly from each accepted captured replay, without a second
scanner replay or process hop, and emits authenticated event/junction/V2
precision-hull frames. One actual block-0 run resolved its single stationary
candidate in `0.033123 s`; the fixed-width host scanner replay took
`0.535333 s`. The strict `sm_90` H100 variant also compiles independently of
the portable event-scan build options. This closes the bounded inline
finite-control implementation, not the PT21 campaign: ambiguous-disk
refinement, full resolver-input retention, one-sided Turing closure, and all
analytic realization flags remain open.

An exact-lattice
[multiwindow transform-reuse qualification](PLATT_PT21_MULTIWINDOW_REUSE_QUALIFICATION.md)
tested whether one transform could serve neighboring logical blocks.  Array
geometry permits deltas `-2..2`, but genuine V2 runs fail closed numerically:
at interior block 2, each `delta=±1` view had about 15.27 thousand ambiguous
disks and each `delta=±2` view had all 25,741 ambiguous.  Only `delta=0`
passed the scanner and FLINT junction.  The probe is retained as a negative
regression test; no pair, three-window, five-window, or whole-pipeline reuse
speedup is claimed.

1. Add an optional sparse high-precision refinement producer whose accepted
   values force a fresh authenticated scan, and define a bounded retained or
   attested resolver-input artifact so an independent checker can regenerate
   the 25,741-sample input digest and candidate completeness. Any ambiguous
   sign, unresolved query, omitted `245/10^42` interpolation widening, or
   unapproved fallback must fail the block.
2. Port or refine the exact reference event/Turing finalizer into the fused
   native worker, emit canonical source traces and compact block commitments,
   and independently replay sampled/full retained traces.  The finite v2
   format, stationary-cell mapping, unique rounding, gap checks, count
   telescoping, and Merkle finalizers are implemented.
3. Prove the remaining semantic bridge: actual Hardy-Z endpoint enclosures, the main
   multiplicity-slot realization, and the analytic Turing inputs and
   inequalities. Until then computation artifacts can be audited but cannot
   discharge the Lean source claim.
4. Wire the implemented native shard/global finalizer into the measured
   worker. Its fixed records already require zero failure counters, bind
   sparse fallback traces and prefix evidence, refuse gaps and
   non-telescoping counts, and independently replay the retained chain. The
   missing step is measured production of those records and attested
   end-to-end evidence, not another finalizer.
5. Benchmark the complete worker on one physical H100.  Only end-to-end
   accepted blocks/s may drive the Azure schedule and cost estimate.
6. Complete or explicitly trust the rigorous prefix through `10^10`, bind all
   binaries/runtime inputs into Azure confidential-compute evidence, appraise
   the run, and admit only the final signed result to the trusted registry.
