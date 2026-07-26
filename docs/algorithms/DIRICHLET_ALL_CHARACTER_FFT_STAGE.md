# Platt all-character CRT/Bluestein interval transform

This module implements the quasi-linear all-character transform in David
Platt, [*Numerical Computations Concerning the
GRH*](https://research-information.bris.ac.uk/ws/portalfiles/portal/67056136/platt_grh3.0.pdf),
Section 4, Lemma `dc_dft` (the same transform lemma appears in
[arXiv:1305.3087v1](https://arxiv.org/abs/1305.3087v1)).  It is a
real production component, but it is **not** a verification of Theorem 7.1 and
does not close `platt-dirichlet-theorem-7-1`.

The current 1024-value shared-memory radix-2 prefix, fused
pointwise/bit-reversal pass, sign-quadrant interval multiplication, bounded
benchmarks, and exact/MPFR/sanitizer qualification are documented in
[`DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md`](DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md).

## Exact source mapping

Platt defines the unnormalised forward DFT with a negative exponential, then
proves that all sums

```text
sum_(1 <= a < q, gcd(a,q)=1) A(a) chi(a)
```

can be obtained in `O(phi(q) log q)` operations by decomposing `U(Z/qZ)` into
cyclic prime-power components.  The four cases in the paper are represented
literally:

- odd prime powers use one cyclic factor of order `phi(p^e)`;
- a single factor `2` is trivial;
- `U(Z/4Z)` has the generator `3` and order `2`;
- `U(Z/2^e Z)`, `e > 2`, has generators `-1,5` and orders
  `2,2^(e-2)`.

The binary transform uses the following explicit convention.  If `e_j` is a
group coordinate and `k_j` the output frequency, with the first component
varying fastest, output `k` encloses

```text
sum_e X[e] exp(+2*pi*i * sum_j e_j*k_j/order_j).
```

Thus it is the sum against the character which maps generator `j` to
`exp(+2*pi*i*k_j/order_j)`.  This positive character convention is deliberate:
it matches the repository's primitive-character exponent descriptors.  The
negative-exponent DFT in Platt's preliminary definition differs only by the
frequency permutation `k -> -k`.  The KAT checks the positive convention
against direct asymmetric complex sums for `q=5,7,8,15`; it does not rely on a
conjugation-symmetric input.

`canonical_residue_order(q)` reconstructs every actual residue `a mod q` from
the least odd-prime-power generators, the `-1,5` decomposition, and exact CRT
cofactors/inverses.  `write_residue_batches_input` is the explicit adapter from
residue-labelled lattice/recovery enclosures to mixed-radix transform input.
`primitive_frequency_records(q)` maps every retained frequency to the exact
primitive ordinal, Conrey number, and parity already used by
`tg_verifier.dirichlet_campaign`.

## Rigorous arbitrary-length transform

Each cyclic dimension of length `N` uses Bluestein's identity

```text
exp(+2*pi*i*n*k/N)
  = exp(+pi*i*n^2/N) exp(+pi*i*k^2/N) exp(-pi*i*(n-k)^2/N).
```

The convolution length is the least power of two at least `2N-1`.  All radix-2
butterflies use CUDA's directed binary64 operations with contraction and FTZ
disabled.  The host constructs rigorous double enclosures of every chirp and
twiddle using MPFR 4.2 `sinpi`/`cospi` with directed rounding.  Extrema at
integer and half-integer arguments are included explicitly.

`SparkInterval/Dirichlet/BluesteinDFT.lean` proves the exact algebraic layer in
ordinary Lean: the signed chirp identity, centered circular indexing, the
`2N-1` no-alias condition, both wrapped kernel wings, elimination of every
zero-padded tail term, and equality of the resulting post-chirped convolution
with the direct DFT. `BluesteinFFTConvolution.lean` closes the next exact
edge: normalized Fourier inversion, cyclic convolution, the proved radix-2
network, CUDA's mirrored forward/inverse signs, and its literal-zero kernel
middle all compose to that direct arbitrary-length DFT. The remaining
mathematical-execution edge is directed containment of the exact chirps,
twiddles, and every fused interval operation; compiled-CUDA refinement and
physical execution remain separately auditable after that.

The independent CPU executable reconstructs the unit-group orders itself and
repeats the same mathematical Bluestein transform at configurable MPFR
precision.  Verification succeeds only when every MPFR output rectangle is a
subset of the CUDA rectangle.  Its implementation does not share interval
operators, roots, FFT code, or group-factorisation code with the CUDA runner.
In addition to the small KATs, a complete one-ordinate `q=400000` output
(`160,000` character rectangles) passed 192-bit MPFR replay in 15.4 seconds on
the local CPU.

Key files are:

- `gpu/platform/h100/h100_tg_dirichlet_allchars_bluestein.cu`;
- `reference/tg_dirichlet_allchars_mpfr.cpp`;
- `SparkInterval/Dirichlet/BluesteinDFT.lean`;
- `SparkInterval/Dirichlet/BluesteinFFTConvolution.lean`;
- `SparkInterval/Dirichlet/DFTRootRecurrence.lean`;
- `SparkInterval/Dirichlet/CertifiedBasisOneOutputWire.lean`;
- `SparkInterval/Dirichlet/CertifiedBasisOneOutputCLI.lean`;
- `tg_verifier/dirichlet_allchars_stage.py`;
- `tools/tg_dirichlet_allchars_stage.py`;
- `tests/tg_dirichlet_allchars_known_answers.py`;
- `tests/tg_dirichlet_fft_root_recurrence_qualification.py`, the exhaustive
  all-19-length direct-MPFR root-table comparison;
- `tests/tg_dirichlet_allchars_max_order_impulse_qualification.py`, the
  opt-in `399988`-order/`2^20` CUDA allocation/dataflow check;
- `tests/tg_dirichlet_allchars_max_order_delta_one_qualification.py`, the
  nonconstant maximum-order sign/index/layout qualification; and
- `SparkInterval/Tests/CertifiedBasisOneOutputWireTest.lean`, the focused
  positive and fail-closed source-checker suite.

The maximum-order delta-one qualification sends the vector supported at
index one through the ordinary `399988`-order CUDA plan. Unlike the constant
transform of delta zero, its output is the complete nonconstant root row
`exp(2*pi*i*k/399988)`, so coherent high-stage sign and indexing errors cannot
hide. Production compares every result against fresh 320-bit roots and the
separate MPFR executable repeats the comparison at 192 bits.

The Lean output checker goes one step closer to the proof boundary without
claiming execution refinement. It parses the complete standard `TGDAFFO1`
frame, pins every stable header field (leaving only elapsed time variable),
checks all 399,988 raw-binary64 boxes with exact-rational root certificates,
and proves that each accepted box contains the exact positive DFT value of
the basis-one input. Its CLI reports a SHA-256 of the complete artifact so
the checked bytes can be matched to a producer or receipt. The result is
explicitly labelled unattested and does not by itself establish compiler
correctness, physical CUDA execution, or Platt's analytic theorem.

## Persistent output-bounded mode

The version-2 primitive-only large-q domain has exactly `3,637,613,167`
modulus/ordinate transforms and `266,697,737,764,848` input group values.
Materialising every 32-byte output rectangle would require exactly
`8,534,327,608,475,136` bytes (about **8.53 PB** decimal), so a production run
must not retain the transform stream.

The runner's persistent mode is:

```text
sparkinterval-tg-dirichlet-allchars \
  --stream MANIFEST.tsv CONSUMER SUMMARY.json DEVICE
```

One manifest contains exactly one modulus and any number of bounded batches.
The process prepares that modulus's chirps, radix-2 twiddles, transformed
Bluestein kernels, and maximum-size CUDA buffers once.  It then:

1. loads one batch;
2. transforms all of its ordinates;
3. pipes the output header and rectangles directly to `CONSUMER` on standard
   input;
4. waits for a compact consumer receipt;
5. releases/reuses the batch buffers; and
6. commits all ordered receipt hashes with a binary Merkle root.

No transformed-output file exists in this mode.  The manifest format is a
literal header `TGDAFF_STREAM_V1` followed by tab-separated input and receipt
paths.  This mode is output-bounded only: it does **not** imply that every
manifest input may be pre-materialised.  A source run must feed a rolling
producer or named pipes and retain at most a bounded number of input batches.
The manifest-mode KAT consumer is deliberately named and classified as a
**test-only format sink**.  The separate persistent completed-L/sign-candidate
consumer is documented in `DIRICHLET_STREAM_ZERO_CONSUMER.md`; neither that
component nor this transform alone closes the analytic claim.

For bounded-storage conformance testing, rolling mode is also available:

```text
sparkinterval-tg-dirichlet-allchars \
  --rolling PLAN PRODUCER CONSUMER WORKDIR SUMMARY DEVICE
```

It asks a producer for exactly one batch, loads and deletes that input, reuses
the prepared transform, pipes the result to a consumer, hashes and deletes the
consumer receipt, and finally retains one Merkle summary.  The KAT confirms
zero retained input batches, output batches, and leaf receipts.

The source-scale transform boundary is now a persistent binary service:

```text
PRODUCER | sparkinterval-tg-dirichlet-allchars \
  --framed-service Q MAX_BATCH SUMMARY.json DEVICE | CONSUMER
```

`PRODUCER` writes concatenated self-delimiting `TGDAFFI1` frames and
`CONSUMER` receives the corresponding concatenated `TGDAFFO1` frames.  The
runner retains one q-specific transform plan, rejects a changed modulus,
oversized batch, malformed interval, or non-contiguous ordinate progression,
and writes no status text into the binary stdout channel.  On clean EOF it
atomically publishes a compact summary binding SHA-256 hashes of both complete
streams.  Its KAT passes two differently sized frames through one process,
independently MPFR-checks both outputs, and confirms a discontinuous stream is
rejected.  Thus the transform itself no longer needs the approximately 114
million producer/consumer forks implied by the primitive-only batch-64 rolling
test harness.

For a q-ordered source shard, the bounded cross-q service is:

```text
PRODUCER | sparkinterval-tg-dirichlet-allchars \
  --multiq-framed-service MAX_BATCH 512 SUMMARY.json DEVICE | CONSUMER
```

It releases q-specific input/output/workspace buffers at each modulus
transition. Its device cache has one exact 512-MiB total budget. It reserves
`134,216,256` bytes for the complete immutable catalog of 19 forward/inverse
radix-2 root pairs, leaving `402,654,656` bytes for an LRU keyed by cyclic
component order and containing only the outward-MPFR chirp and transformed
Bluestein kernel. Roots are constructed lazily but never evicted, and their
full source-domain allocation is reserved before the first order entry. A
chirp/kernel plan too large for the order budget remains live only for its
current q. None of these objects depends on q, CRT stride, batch size, or input
values. The service rejects any cache argument other than exactly `512`, and
accepts only grouped, strictly increasing q with contiguous ordinate frames
within each q.

Its version-2 summary commits the exact input/output streams, ordered
`(component order, convolution length)` key chain, and fixed root-catalog
digest. It separately reports root and order accesses, hits, misses, retained
bytes, prepared enclosure counts, and total peak residency. The independent
Python validator re-parses every interval and frame, reconstructs each CRT
plan, regenerates the root catalog, and replays both cache layers. The CUDA KAT
checks cached output payloads byte-for-byte against the ordinary uncached
runner, checks every result with the independent 192-bit MPFR implementation,
mutates order counters, root counters, and the root-catalog digest, rejects a
non-512-MiB budget, and confirms decreasing-q input is rejected.

The increasing-q mode remains a compatibility baseline. The intended
primitive-V2 execution now has an explicit receipt-bound permutation:

```text
PRODUCER | sparkinterval-tg-dirichlet-allchars \
  --scheduled-multiq-framed-service \
  MAX_BATCH 512 SCHEDULE.bin SUMMARY.json DEVICE | CONSUMER
```

`SCHEDULE.bin` is the versioned `TGDQORD1` manifest described in
`DIRICHLET_ALL_CHARACTER_Q_SCHEDULER.md`. It commits both the exact increasing
source roster and the execution permutation, including every actual q and
source-height row count. The runner rejects a q transition, gap, overlap,
truncation, or trailing group that differs from that manifest. The independent
Python replay reconstructs the permutation and exact coverage instead of
treating arbitrary nonmonotone input as valid.

The full source supervisor is still **not production-ready**.  It must launch
and bind the persistent residue composer, this service, a matching canonical
control stream, the certified root-number artifact reader, and the
completed-L/zero-closure consumer; propagate a downstream failure to every
producer; and commit the resulting receipt graph.  Rolling mode remains a
bounded-storage test harness, not the recommended source execution path.

The version-2 production roster includes exactly the 292,500 moduli with a
nonempty primitive-character roster.  Since every source q is greater than
2, this is exactly `q % 4 != 2`; the 97,500 moduli congruent to 2 modulo 4
have no primitive character and are excluded before lattice composition or
FFT.  A bounded KAT checks the criterion against the canonical primitive
character counter and the TGDLTMB1/Lean wire independently enforces the same
roster.  Batch size 64 then gives:

| Quantity | Exact count |
|---|---:|
| active moduli | `292,500` |
| excluded empty-roster moduli | `97,500` |
| modulus/ordinate rows | `3,637,613,167` |
| group values | `266,697,737,764,848` |
| batch-64 invocations | `56,981,100` |
| unbatched radix-2 butterflies | `16,899,137,523,971,596` |
| batch-64 radix-2 butterflies | `15,334,965,882,246,056` |

Manifest mode keeps one transform process alive per assigned modulus/shard but
requires bounded external production of its named inputs.  Rolling mode bounds
both sides on disk but retains the producer/consumer fork overhead disclosed
above.  Framed-service mode removes that process overhead and materialization;
it should not be confused with the still-needed receipt-binding production
supervisor for the complete analytic pipeline.

## Build and test

```bash
cmake -S . -B build/dirichlet-allchars
cmake --build build/dirichlet-allchars --target \
  sparkinterval-tg-dirichlet-allchars \
  sparkinterval-tg-dirichlet-allchars-mpfr -j
ctest --test-dir build/dirichlet-allchars \
  -R tg_dirichlet_allchars_known_answers --output-on-failure
```

The strict Azure/H100 target is
`sparkinterval-h100-tg-dirichlet-allchars`.  It is compiled only for `sm_90`
and refuses physical execution on a non-H100 GPU.  Cross-building and PTX/SASS
inspection on another architecture are build audits, not H100 conformance.

## GB10 source-shaped measurements

These July 21, 2026 measurements use batch 64 and include exact work counters.
Transform time excludes the separately reported one-time persistent-modulus
MPFR/CUDA preparation:

| `q` | component orders | values/batch | butterflies/batch | transform time | butterflies/s | values/s | preparation |
|---:|---|---:|---:|---:|---:|---:|---:|
| `10001` | `72 x 136` | `626,688` | `39,062,784` | `0.027943733 s` | `1.39791e9` | `2.24268e7` | `0.042255207 s` |
| `100000` | `2 x 8 x 2500` | `2,560,000` | `139,825,188` | `0.100978166 s` | `1.38471e9` | `2.53520e7` | `0.321085282 s` |
| `399989` | `399988` | `25,599,232` | `1,352,663,040` | `0.870108438 s` | `1.55459e9` | `2.94207e7` | `38.251803157 s` |
| `400000` | `2 x 32 x 2500` | `10,240,000` | `600,101,060` | `0.428803181 s` | `1.39948e9` | `2.38804e7` | `0.466365610 s` |

The July 25 qualified fast path supersedes the first two arithmetic
measurements: the stable medians are `0.013551701 s` (`2.88250e9`
butterflies/s) at `q=10001` and `0.095869764 s` (`1.45849e9`
butterflies/s) at `q=100000`. The two larger moduli were not rerun, so the
source-wide projection below intentionally retains the older conservative
rate instead of extrapolating from the favorable small convolution.

The near-constant transform rate and the separately visible 38.25-second
large-prime preparation show why the persistent per-modulus interface is
necessary.  These four points are still not a weighted full-domain benchmark.
At the conservative observed `1.38e9`--`1.40e9` transform rate, the
primitive-only batch-64 arithmetic corresponds to roughly
`3,043`--`3,087` GB10 GPU-hours, or `15.85`--`16.08` ideal days on
eight equal GPUs.  This omits preparation, lattice/recovery production,
completed-L work, exception handling, zero scans, Turing closure, I/O, and
replay.  It is therefore a component estimate, not a Theorem 7.1 ETA.

### Preparation inventory

Preparation is not free.  Across `q=10001..400000` there are exactly:

| Preparation object | Count |
|---|---:|
| component dimensions in primitive-only per-q plans | `816,177` |
| distinct complete q component-order plans | `219,015` |
| distinct component orders | `34,000` |
| distinct radix-2 convolution lengths | `19` (`4` through `1,048,576`) |
| complex twiddle enclosures prepared by one fresh plan per active q | `71,135,060,058` |
| complex twiddle enclosures after ideal cross-q order/FFT-root caching | `12,952,682,706` |

The representative preparation rates range from about 46,000 to 75,700
complex twiddle enclosures per second, including allocation and transformed
Bluestein-kernel setup.  At the conservative 46,000/s rate the fresh-plan
inventory is about `429.6` serial CPU-hours, or `53.7` ideal hours on eight
nodes.  H100 kernels do not accelerate this host MPFR work.

The split cache removes the dominant duplication while preserving one hard
memory bound. On the exact increasing primitive-only source roster it gives:

| Split-cache object | Exact count |
|---|---:|
| total cache reservation | `536,870,912` bytes |
| immutable 19-root reservation | `134,216,256` bytes |
| root-catalog SHA-256 | `1bc2d74e4a76b5981a8b56c9b3c8ac517931a952c8c2166dcfbcad1c9373b728` |
| order-specific LRU capacity | `402,654,656` bytes |
| order accesses / hits / misses | `816,177 / 532,611 / 283,566` |
| order evictions / retained entries | `283,494 / 72` |
| root accesses / hits / misses | `283,566 / 283,547 / 19` |
| root enclosures prepared once | `4,194,258` |
| order chirp/kernel enclosures prepared | `18,102,127,240` |
| total prepared enclosures | `18,106,321,498` |
| exact peak actual residency | `536,870,848` bytes |

This is `52,964,478,342` fewer generated enclosures, a 74.52% reduction from
the preceding whole-plan 512-MiB LRU. At the conservative measured
46,000-enclosure/s preparation rate it is about 109.3 serial CPU-hours or 13.7
ideal hours across eight perfectly scaling hosts. It remains
`5,153,638,792` enclosures above the unlimited distinct-order ideal in
increasing-q order.

The versioned component-signature scheduler closes that remaining preparation
gap on the exact source roster:

| Scheduled split-cache object | Exact count |
|---|---:|
| order accesses / hits / misses | `816,177 / 782,177 / 34,000` |
| order evictions / retained entries | `33,992 / 8` |
| root accesses / hits / misses | `34,000 / 33,981 / 19` |
| order chirp/kernel enclosures prepared | `12,948,488,448` |
| root enclosures prepared | `4,194,258` |
| total prepared enclosures | `12,952,682,706` |
| exact peak actual residency | `536,869,184` bytes |

This saves `5,153,638,792` enclosures, or 28.46% of increasing-q split-cache
work. Since the source has exactly 34,000 distinct component orders and 19
distinct root lengths, the schedule's one miss per distinct object attains
the cold-cache preparation lower bound. At the conservative
46,000-enclosure/s rate, the exact count is about 78.2 serial hours or 9.78
ideal hours on eight perfectly scaling hosts. This conversion is not an H100
or source-run measurement.

A bounded eight-modulus GB10 measurement used
`q = 5003 * (3,5,7,9,11,13,15,17)`, so every plan shares the nontrivial
component order 5002. Seven fresh-process split-cache runs had median reported
preparation `0.5622 s`, GPU arithmetic `0.01118 s`, and wall time `1.0830 s`.
The summary had 17 order accesses with 10 hits and 7 misses, plus 7 root
accesses with 2 hits and 5 misses. Against the retained zero-cache measurement
of `4.4630 s` preparation and `5.0530 s` wall, this is 7.94x and 4.67x,
respectively. It is essentially unchanged from the old 32-MiB whole-plan result
on this deliberately easy reuse sequence; the split's benefit is the exact
source-wide root de-duplication above. Each run processed 10,244,672 input
bytes. This is a targeted GB10 benchmark, not a weighted source run or H100
forecast.

## Exact remaining boundary

The following are still required before Theorem 7.1 can be certified:

- connect certified Hurwitz lattice cells, Taylor tails, finite recovery, and
  the `q^(-s)` factor into residue-labelled transform inputs;
- implement the completed-L phase and a production streaming sign/zero scan;
- retain only primitive frequencies with the provided Conrey/parity map and
  handle conjugate pairing and exceptional recomputation;
- implement Platt's small-q algorithm;
- isolate all required zeros with multiplicity and execute the complete
  Booker/Rumely/Trudgian Turing argument; and
- independently replay and attest the full campaign.

Accordingly `full_source` is false and the external atom remains live.
