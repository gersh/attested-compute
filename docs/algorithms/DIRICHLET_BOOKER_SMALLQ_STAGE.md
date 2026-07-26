# Platt--Booker small-conductor Dirichlet stage

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This component implements the small-conductor Fourier algorithm used in David
Platt's *Numerical Computations Concerning the GRH* for primitive characters
with `2 <= q <= 10000`.  The accepted manuscript's Section 7 supplies the
Gaussian formulas and error estimates; Booker's Fourier method is the
underlying construction.  The component is executable and has a fail-closed
Arb/MPFR seed checker plus a directed-disk CUDA engine, but is not by itself a
proof of Theorem 7.1.

## Implemented mathematical boundary

For every canonical primitive character, the planner covers the complete
positive `5/64` lattice through Platt's parity-dependent source height.  The
producer evaluates the displayed even or odd Gaussian series, adds an explicit
geometric bound for the omitted Gaussian terms, bounds both omitted frequency-
periodization wings, applies the positive-sign radix-2 DFT, removes the
exponential tilt, and applies the displayed `E/beta` time-periodization bound.
All retained analytic values are Arb rectangles.  A higher-precision replay
regenerates every rectangle and rejects a corrupted or relabelled chunk.

The implementation deliberately avoids treating the apparent `X(x)` typo in
the arXiv v1 source as an axiom: it derives the two Gaussian wings directly.
It also records that the paper publishes `A=64/5`, but not the complete
production choices of `B` and `eta`; the project's valid choices are therefore
classified as project-derived parameters, not quoted source data.

The exact source plan contains:

| Work item | Exact count |
|---|---:|
| primitive characters | `18,477,108` |
| completed `5/64` lattice samples | `4,729,082,453,090` |
| Fourier-frequency values | `7,078,844,301,312` |
| radix-2 butterflies | `67,133,929,684,992` |
| planned finite Gaussian terms | `1,171,395,337,603,008` |

## GPU and certificate boundaries

`h100_tg_dirichlet_booker_smallq_kernel.cu` evaluates the finite Gaussian sum
in parallel.  Its binary64 midpoint is explicitly untrusted: it is accepted
only as a performance proposal and never becomes an interval certificate by
passing the file format.  The pinned Arb path supplies the analytic tails and
retained enclosure.  A separately written 256-bit MPFR executable also
recomputes the finite arithmetic as a cross-implementation audit.

The production-oriented v2 target,
`h100_tg_dirichlet_booker_smallq_certified.cu`, instead consumes complex disks
for the exact character values, the Gaussian recurrence seed, the frequency
prefactor, and the complete analytic remainder.  A higher-precision pinned Arb
checker independently regenerates the exact parameters, character exponents,
epsilon phase, truncation, every transcendental seed disk, the omitted
Gaussian tail, and both alias wings.  It rejects understated radii, parameter
relabeling, missing frequencies, malformed characters, and non-finite values.

CUDA then uses only directed binary64 addition, subtraction, multiplication,
and square root.  It evaluates the finite Gaussian recurrence and a
positive-sign radix-2 interval DFT in a persistent multi-frame process; MPFR
twiddle disks are anchored every 256 powers.  No CUDA transcendental is part of
the accepted arithmetic boundary.  The checker is linear in the number of
frequency seeds rather than in the much larger number of finite Gaussian
terms.  This removes the old requirement to replay all
`1,171,395,337,603,008` finite terms in Arb.

Five KATs cover primitive characters `(q,Conrey) = (3,2), (4,3), (5,2),
(5,3), (5,4)`.  Their completed samples enclose direct FLINT values; both the
Arb comparison and MPFR audit accept the CUDA output, with maximum observed
absolute midpoint error about `1.11e-16`.  The strict Azure target is compiled
for `sm_90` and refuses physical execution on the local GB10.

A source-shaped `q=10000`, Conrey `1877` GB10 sample processed `16,195,175`
finite Gaussian terms per iteration.  Seven 50-iteration measurements had a
median `8,994,773 ns`, or about `1.8005e9` terms/s.  Ideal linear division of
the exact Gaussian count gives about `180.7` single-GB10 hours or `22.6` hours
on eight equal GPUs.  This excludes the DFT, Arb replay, storage, orchestration,
upsampling, zero closure, and all Azure/H100 calibration.

For v2, a source-shaped `q=997`, 65,536-frequency prefix processed
`118,816,929` directed recurrence terms at about `651.5 million terms/s` and
`2,097,152` radix-2 butterflies at about `1.015 billion butterflies/s` on the
local GB10.  Linear division gives about `62.4` hours of recurrence work and
`2.30` hours of DFT work on eight equal GB10 GPUs.  Treating the H100-versus-
GB10 binary64 roofline ratio of about `14.3` as an optimistic ceiling lowers
the recurrence arithmetic to about `4.37` hours; this is not an H100
measurement.

The higher-precision Arb seed checker sustained about `33,746.7` frequencies
per second.  Ideal division of all `7,078,844,301,312` frequencies over four
96-vCPU nodes is about `151.7` hours.  That estimate assumes perfect CPU
parallelism and excludes transport and storage.  The literal v2 seed stream is
about `622,938,298,515,456` bytes (623 TB decimal), so compressed anchor
generation is still necessary before this is a practical source campaign.

### Factored v3 boundary

Version 3 removes the repeated analytic work rather than merely compressing
its bytes. The character phase and exponent table are stored once per
character; `w` and the two parity-dependent prefactor/tail records are stored
once per frequency. The CUDA consumer selects one parity record and combines
it with the character phase by certified disk multiplication. It accepts both
v2 and v3 magic values without reinterpreting one as the other.

| v3 work item | Exact source count or size |
| --- | ---: |
| character epsilon records | `18,477,108` |
| shared frequency records | `16,385,441,792` |
| character exponent words | `123,175,108,679` |
| minimum logical v3 payload | `2,459,841,190,828` bytes |
| physical split-service payload at 80 GiB usable/device | `2,459,842,579,084` bytes |
| literal per-frequency service outputs | `339,784,527,970,104` bytes |
| source-sample-only streamed outputs | `226,995,959,255,448` bytes |
| guard-frequency output bytes avoided | `112,788,568,714,656` bytes |
| character batches at 80 GiB usable/device | `8,971` |
| largest batch count for one modulus | `2` |
| reduction from literal v2 payload | `253.24x` |
| reduction in independently regenerated frequency families | `432.02x` |

On the retained `q=997`, transform-length `65,536`, 16-character benchmark,
the producer took `3.165 s`, the independent higher-precision Arb checker took
`3.272 s`, and CUDA took `14.161 ms` per frame. The checker regenerated
`196,624` distinct families at about `60,091.8/s`. This remains the compact KAT
rate; it is not used for the source replay projection.

A separate complete source-parameter `q=997` plan has transform length
`2,097,152`, 995 primitive characters, and `6,292,451` distinct replay
families. Its producer took `110.71 s` (`56,837.2` families/s), and its
independent checker took `126.369121963 s` (`49,794.2` families/s). Applying
this larger, slower measurement to the exact source family count gives
`0.714` ideal hours on 384 CPU processes. The combined recurrence/DFT
projection is `49.14` equal-GB10 hours, or a
strictly uncalibrated `4.91--9.83` H100 hours under 10x--5x sensitivity. These
are arithmetic projections, not end-to-end source-run measurements.

The retained split-service rerun divided the same 16 characters into two
eight-character batches. It wrote one plan plus both batches in `3.121 s`,
independently streamed/replayed them in `3.463 s` (`56,833` distinct
families/s), and used `7,929,296` input bytes—only 288 bytes more than the
one-shot v3 frame. Ten local GB10 iterations averaged `8.238 ms` and
`8.281 ms` for the two batches, or `16.519 ms` combined. That is about 16.7%
slower than the retained 16-character one-shot timing, quantifying the cost of
the deliberately bounded batch. After removing their different headers and
bindings, the two service output item streams were byte-for-byte identical to
the retained one-shot output.

The split service uses distinct, fail-closed `TGDBSQP3` plan and `TGDBSQB3`
batch formats. A plan contains the exact parameters and shared frequency seed
stream once, and commits to the ordered character-id roster. Each bounded
batch contains only character epsilon disks and exact exponent tables, commits
to the SHA-256 of the complete plan, and records its contiguous range and
ordinal. The CUDA runner preflights the full roster and all batch bindings
before execution, keeps the plan, directed-disk buffers, character-root table,
and FFT plan resident, and rejects gaps, reordered batches, hash mismatches,
trailing bytes, or parameter relabeling.

Each `TGDBSQO3` output repeats the plan hash, the complete character-batch
hash, and the range/ordinal binding before its disk values. This prevents a
valid output shard from being relabelled as a shard of another plan, batch
payload, or character range. The Arb KAT includes a negative binding-tamper
check.

With an already-safe `80 GiB` allocation budget, the exact allocation model
needs at most two character batches for any active modulus. The complete
shared stream remains device-resident for every modulus except `q=3` and
`q=4`: their transform length is `2^29`, so their 64.4-GB seed stream is fed in
bounded chunks. Each has exactly one primitive character and therefore one
character batch, so streaming still reads each shared seed exactly once per
execution rather than repeating it across batches. The retained CUDA KAT
exercises both the resident two-batch path and a forced 17-record streaming
path, with every output disk checked against a fresh Arb evaluation.

The executable syntax is:

```bash
sparkinterval-tg-dirichlet-booker-smallq-certified \
  [--iterations N] [--shared-seed-chunk-records N] [--source-samples-only] \
  --factored-service PLAN BATCH OUTPUT [BATCH OUTPUT ...]
```

The companion orchestration entry point reports the exact whole-source work,
writes a canonical primitive-character campaign for one modulus, and performs
the independent streaming replay:

```bash
python3 tools/tg_dirichlet_booker_smallq_factored.py source-work
python3 tools/tg_dirichlet_booker_smallq_factored.py \
  plan-q Q PLAN BATCH_DIRECTORY
python3 tools/tg_dirichlet_booker_smallq_factored.py \
  verify-q Q PLAN BATCH_DIRECTORY
```

The producer writes the shared plan incrementally in 8-MiB buffers, and the
independent checker streams and rehashes it, so the 64.4-GB low-conductor plan
does not need to be materialized in Python memory. The runner similarly hashes
and validates its plan scan and rechecks the digest during resident upload or
streamed execution.

The canonical little-endian layouts to be mirrored by the Lean literal
generator/parser are deliberately short:

| Artifact | Byte layout |
| --- | --- |
| `TGDBSQP3` plan | 64-byte input header; 32-byte ordered-roster commitment; 48-byte exact-parameter header; `N` 120-byte shared seeds |
| `TGDBSQB3` batch | 64-byte input header; 64-byte plan/range binding; `batch_count` blocks of one 48-byte character header plus `4q` exponent bytes |
| `TGDBSQO3` output | 72-byte output header; 96-byte plan-hash/batch-hash/range binding; `batch_count*N` 48-byte disk items |
| `TGDBSQR3` reduced output | same header and binding; `batch_count*sample_count` items after an exact canonical-source-parameter check |

The roster commitment is SHA-256 of the ASCII domain
`SparkInterval/DirichletBookerSmallQ/roster/v3`, one zero byte, then the
ordered sequence of little-endian unsigned 64-bit Conrey ids. The plan hash
and batch hash cover every byte of their respective files. Reserved words,
noncanonical rationals, unexpected sizes, and trailing bytes are rejected.

### Streaming output reduction

The service no longer has to publish one regular file per output batch. An
output path of `-` writes consecutive self-framing `TGDBSQO3` records to
standard output and moves the JSON timing diagnostics to standard error. The
new `--source-samples-only` mode first proves by exact integer comparisons that
the plan has the canonical source `A=64/5`, `b=N/A`,
`eta=H/(H+64)`, full DFT range, and Platt source height. It then emits distinct
`TGDBSQR3` frames containing only indices `0..sample_count-1`. The full DFT is
still computed; only the unused guard-height time outputs are omitted. This
reduces the exact cross-process stream from 339.785 TB to 226.996 TB and avoids
112.789 TB (33.2%) before any analytic decision is attempted. Existing file
output and full `TGDBSQO3` output remain the default.

`dirichlet_booker_smallq_output_stream.py` consumes either full or reduced
frames from stdin, a FIFO, or a regular file. Before reading values it hashes
the complete plan and batches and proves that the batches are the committed,
ordered, gap-free character partition. It then checks every output's character
id, frequency index, finite center/radius, nonnegative radius, zero status, and
zero reserved word. Fixed item chunks and frame bindings are committed into a
domain-separated SHA-256 Merkle mountain range. Only a sub-4-KB canonical JSON
receipt remains; no raw output file is required.

The commitment is specified independently of Python object serialization.
All integers below are little-endian unsigned 64-bit words and every ASCII
domain ends in one zero byte:

```text
item_leaf  = SHA256(item_domain || frame || chunk || flat_start || raw_items)
header_leaf = SHA256(header_domain || frame || raw_header || raw_binding)
node(h,l,r) = SHA256(node_domain || h || l || r)
frame_leaf = SHA256(frame_domain || frame || batch_sha || raw_binding || frame_mmr)
```

Each MMR combines adjacent equal-height peaks. Its root is
`SHA256(root_domain || leaf_count || peak_count || (height || peak)...)`, with
occupied peaks serialized from highest to lowest. The receipt records the item
chunk size, and `receipt_sha256` hashes the canonical JSON body before that
self-hash field is added. This is deliberately small enough for a later Lean
literal parser or trusted-run registry entry; importing the digest alone must
not be mistaken for importing the arithmetic proposition.

The four domains are, respectively,
`SparkInterval/DirichletBookerSmallQ/output-item-chunk/v1`,
`.../output-frame-header/v1`, `.../output-mmr-node/v1`, and
`.../output-frame-leaf/v1`; the root uses `.../output-mmr-root/v1`. The omitted
prefix in each abbreviated entry is the same
`SparkInterval/DirichletBookerSmallQ` prefix shown in the first entry.

For example, a full q service can be connected directly to the reducer:

```bash
build/tg-production-kat/sparkinterval-tg-dirichlet-booker-smallq-certified \
  --source-samples-only --factored-service PLAN \
  BATCH_0 - BATCH_1 - \
| python3 tools/tg_dirichlet_booker_smallq_output_stream.py \
    PLAN BATCH_DIRECTORY RECEIPT.json
```

On the local DGX Spark, seven cached-file runs over a 201,326,760-byte
synthetic stream (4,194,304 structurally checked disk items) had a median of
`4,943.5 MB/s` with eight NumPy/SHA worker threads. Seven actual anonymous-pipe
runs had a median of `1,510.2 MB/s`. Literal single-stream division at the pipe
rate projects `62.50` hours for the old full stream or `41.75` hours for the
reduced stream. Perfect division across eight independent q-sharded pipes
would be `5.22` hours for the reduced bytes, but that is only an ideal
sensitivity: these are cached local synthetic measurements, not concurrent
CUDA, Azure, H100, or source-run calibration, and one host's memory bandwidth
may prevent eight-way scaling.

### Semantic time-tail/sign reduction

`tg_dirichlet_booker_smallq_semantic_reducer.py` now implements the next
q-level streaming operation without repeating transcendental work for every
character. Its `TGDBSQT1` control contains, in natural source-sample order, one
outward binary64 upper bound for

```text
time_periodization_tail / (2*pi/b)
```

for each parity. The header binds the complete v3 plan, the ordered hashes of
all character batches, each character's parity, the exact source transform
length, and the source sample count. The producer uses the existing Arb
implementation of Platt's displayed time-periodization expression. A separate
higher-precision pass must replay every even and odd record before the reducer
accepts the control receipt. A missing sample, understated bound, parity swap,
batch reorder, noncanonical source parameter, or receipt/hash mismatch fails
closed.

For a streamed disk with real centre `x` and Euclidean radius `r`, let `e` be
the replayed parity control. The reducer advances the binary64 sum `r+e` one
word toward positive infinity. It emits positive only when `x` is strictly
larger than that outward bound and negative only when `x` is strictly smaller
than its negation. Since both `2*pi/b` and the untilt are positive, these are
exactly sufficient completed-real sign tests. Every other coordinate is
retained as ambiguous. The output `TGDBSSG1` artifact uses two bits per
character/sample in the exact roster-times-source-grid order:

| code | meaning |
| ---: | --- |
| `0` | ambiguous; refinement required |
| `1` | certified negative, conditional on the input DFT disk containment |
| `2` | certified positive, conditional on the input DFT disk containment |
| `3` | reserved and rejected |

Across active small-q moduli, the control has `8,116,121,626` records and an
exact `129,858,785,904`-byte wire size (including q headers). The complete
two-bit sign artifacts occupy `1,182,271,755,191` bytes including q headers,
versus `226,995,959,255,448` bytes for the input `TGDBSQR3` stream. This is an
exact format/cardinality reduction, not a source-run timing: neither complete
control production/replay nor concurrent source-scale reduction has been
measured. A typed host adapter now streams `TGDBSQR3` frames through the
strict semantic sign test directly into `TGDCSB03`, so neither the
226.996-TB raw stream nor the 1.182-TB sign family must be stored. Every raw
disk row crosses that transient pipe in host mode. Device-mode `TGDBSPK1`
instead performs the same outward sign classification after the final DFT and
copies only the packed codes plus a full-status summary. Source-campaign
wiring and H100 calibration remain engineering boundaries. See the
[source-streaming v3 design](DIRICHLET_SOURCE_STREAMING_V3.md).

The older MMR reducer remains deliberately integrity-only. The semantic
reducer adds checked time-tail/sign decisions, but neither receipt proves that
the input disk contains the mathematical DFT value. Discarding those disks
still requires measured/trusted execution evidence or a separately replayable
arithmetic artifact. `TGDBSQR3` values are tilted completed small-q Fourier
samples, not `TGDAFFO1` all-character residue-transform frames, so they cannot
be relabelled into the existing large-q completed-L consumer. No sign-change
scan, zero count, interpolation, exception closure, multiplicity inference, or
Turing completeness claim occurs; ambiguous codes and every sample coordinate
are preserved for those later stages.

The Lean arithmetic adapter checks multiplication by the positive `2*pi/b`
scale, inflation by a named complex-norm time-periodization bound, and
multiplication by a positive untilt before strict-sign reduction. The
byte-stream/DFT-output link and the subsequent upsampling, exception, and
Turing closure are not yet implemented. In particular, a square complex box
with component radius `E` cannot be reused as a norm-`E` disk without a
`sqrt 2` allowance unless the analytic source directly supplies the norm
bound.

The Lean side now mirrors the arithmetic data representation instead of stopping at a
generic rectangle lemma. `ComplexDisk.RawMulCertificate` decodes each
binary64 word to an exact rational, checks squared centre-error and norm bounds
with an ordinary Boolean rational checker, and proves the output disk contains
the true complex product. `DiskPrefactorCertificate.expanded_contains` applies
that theorem to the parity-base/epsilon expansion. The Gaussian recurrence
and its closed-form powers are also proved in Lean. A raw trace checker now
decodes every binary64 word, enforces exactly `T - 1` recurrence rows, and
proves the final state. A source-owned campaign checker separately fixes `q`,
the ordered character roster, transform length, and every term count; accepted
keys must literally equal the expected character/frequency Cartesian product,
including exact batch boundaries. Focused `#print axioms` checks show only the
ordinary Lean base trio and no `native_decide` or project execution axiom. See
the [arithmetic bridge](../LEAN_ARITHMETIC_BRIDGE.md).

A bounded raw DFT checker additionally consumes canonical finite binary64
input, twiddle, butterfly-trace, and output lists. It checks resource bounds
before decoding, replays every typed radix-2 butterfly, checks the supplied
output pointwise against the derived state, and returns each literal raw word
with exact-transform containment. The existing CUDA stream does not emit this
complete trace, so a practical sidecar producer or a proved/refined compact
checker is still required; the stream MMR receipt is only integrity and
coverage metadata, never arithmetic evidence.
The reference trace has `logLength * transformLength / 2` butterfly rows per
character (`22,020,096` at the source `logLength=21`), so emitting it literally
for the full roster is not the intended production design.

The final Lean join checks the source-sample/full-DFT domain equation and each
retained Fourier-disk equality. Its theorem exposes the literal raw output
word, proves containment of the exact direct positive DFT, and derives the
strict sign after checked scaling, time-tail inflation, and untilting. The
source-shaped corollary uses one header-wide `a,b,eta`, derives
`t=sample/a`, checks `0<a`, `0<b`, `-1<eta<1`, and
`b=2^logLength/a`, and names the production constant `a=64/5` separately. The
Gaussian/root/factor/tail/reality inputs remain named premises, so this does
not turn the integrity-stream receipt into arithmetic evidence.

The fixed-size raw completed-sign wrapper additionally decodes both
multiplication witnesses and the time-tail inflation from binary64 words. It
uses the producer-compatible signed convention `-1`/`+1`, rejects zero, and
requires literal attachment to the Fourier word before decoding. The fully
raw ordered all-modulus theorem stores the raw DFT and raw sign campaigns in
the same bundle, looks up the exact character/sample word, and aligns each
finite bundle, source header, and analytic premise by the same ordered
relation.

The next Lean layer projects pairs of those completed-value disks to exact
rational intervals. Its checker fixes one character and sampling rate,
requires exact `time=sample/a`, increasing endpoints, opposite strict signs,
and global bracket separation, and then feeds the established rational
zero-certificate theorem. The raw campaign adapter proves that each typed
endpoint is the deterministic decode of an actual campaign cell and checks it
against the disk decoded from the literal DFT word at the same key. It also
proves exact rational/real time alignment, including `a=64/5`; detached words
and signed-zero aliases fail. The equality between the checked completed
values and the analytic completed-L evaluator remains an explicit proof
obligation.
`FactoredSmallQSourceRealization` now states that obligation without an
informal identifier convention: a supplied exact roster bijects opaque source
identifiers with all primitive Dirichlet characters, a separate predicate
fixes every character row and parity, and one complex equation fixes the real
evaluator on Booker's `a=64/5` grid. Its requested-cell theorem requires both
contracts and composes them with the raw-word arithmetic proof to return the
character row, parity, direct-DFT enclosure, and evaluator link for the same
decoded cell. These contracts are not yet inhabited by the production source,
and they make no Conrey-number claim.
The GRH capstone composes that family directly with a supplied Dirichlet
Hardy model and total L-zero upper count, first for one character and then for
every primitive character of a modulus; none of those analytic premises is
inferred from the raw payload.
`FactoredSmallQRosterGRHBridge` then uses exact roster completeness and the
checked equality `family.characterId = id` to assemble the ID-indexed families
into the mathematical per-modulus GRH statement. The equality materially
rewrites the source-indexed evaluator in the proof.
Finally,
[`PlattTheorem71Contract.lean`](../../SparkInterval/Dirichlet/PlattTheorem71Contract.lean)
states the exact parity-dependent source proposition and proves it from the
per-modulus finite-GRH results that the remaining zero-isolation and Turing
layers must construct.

## Build and checks

```bash
cmake -S . -B build/tg-production-kat -DCMAKE_BUILD_TYPE=Release
cmake --build build/tg-production-kat --target \
  sparkinterval-tg-dirichlet-booker-smallq \
  sparkinterval-tg-dirichlet-booker-smallq-mpfr \
  sparkinterval-tg-dirichlet-booker-smallq-certified -j

PYTHONPATH=. .venv-tg-flint/bin/python -m unittest -v \
  tests.test_tg_dirichlet_booker_smallq \
  tests.test_tg_dirichlet_booker_smallq_certified \
  tests.test_tg_dirichlet_booker_smallq_factored \
  tests.test_tg_dirichlet_booker_smallq_output_stream \
  tests.test_tg_dirichlet_booker_smallq_semantic_reducer

python3 tools/benchmark_tg_dirichlet_booker_smallq_output_stream.py \
  --transform-length 65536 --characters 64 --repetitions 7

lake build SparkInterval.Certified.ComplexDisk \
  SparkInterval.Dirichlet.FactoredSmallQSeed \
  SparkInterval.Dirichlet.FactoredSmallQRawCampaign \
  SparkInterval.Dirichlet.FactoredSmallQRawDFT \
  SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition \
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign \
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign \
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign \
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign \
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign \
  SparkInterval.Dirichlet.FactoredSmallQZeroBracket \
  SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign \
  SparkInterval.Dirichlet.FactoredSmallQSourceRealization \
  SparkInterval.Dirichlet.FactoredSmallQGRHBridge \
  SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge \
  SparkInterval.Dirichlet.PlattTheorem71Contract
lake env lean SparkInterval/Tests/ComplexDiskCertificateTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQSeedTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawTraceTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQCampaignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawCampaignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawDFTTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawDFTCompositionTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawCompletedSignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawCompletedSignCampaignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawCompletedSignPayloadCampaignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawCompletedSignModulusCampaignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawCompletedSignPayloadModulusCampaignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQZeroBracketTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRawZeroBracketCampaignTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQSourceRealizationTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQGRHBridgeTest.lean
lake env lean SparkInterval/Tests/FactoredSmallQRosterGRHBridgeTest.lean
lake env lean SparkInterval/Tests/PlattTheorem71ContractTest.lean

PYTHONPATH=. .venv-tg-flint/bin/python \
  tests/tg_dirichlet_booker_smallq_known_answers.py \
  build/tg-production-kat/sparkinterval-tg-dirichlet-booker-smallq \
  --mpfr-auditor \
  build/tg-production-kat/sparkinterval-tg-dirichlet-booker-smallq-mpfr
```

The strict targets are `sparkinterval-h100-tg-dirichlet-booker-smallq` and
`sparkinterval-h100-tg-dirichlet-booker-smallq-certified` in a build configured
with `SPARKINTERVAL_BUILD_H100_NATIVE=ON`.  Both require a physical `sm_90`
H100 at execution; the latter is the directed-disk boundary.

## Remaining boundary

The v3 producer, independent checker, factored CUDA consumer, q-persistent
split protocol, exact memory planner, resident/streaming service, reduced
source-sample output, and coverage/integrity stream reducer are
implemented and covered by bounded KATs. They have not had a complete source
run or an H100 calibration. Producer, storage, plan-hashing, host/device
transfer, and service time are not part of the 0.714-hour checker projection.
The reducer removes persistent 339.8-TB materialization, and reduced output
avoids 112.8 TB of guard samples. The runner-side `TGDBSPK1` mode additionally
replaces the remaining 227.0-TB disk pipe with an approximately 1.182-TB
two-bit pipe that feeds `TGDCSB03` without a persistent sign family. Its
device mode classifies the final CUDA disks before device-to-host transfer,
copies only the packed codes plus an eight-byte status summary, and is
byte-differentially checked against the host mode. The nonterminal Azure
materializer binds the selected host/device location without fallback. This
removes the raw disk transfer for that component, but it has not been
source-wide integrated or H100-calibrated; see
`DIRICHLET_SMALLQ_PACKED_SIGN_TRANSPORT.md`.
The largest
observed pre-DFT binary64 radii in the earlier source-shaped sample were about
`1.44e-7`; no source-wide proof yet shows that the accumulated and scaled DFT
disks remain narrow enough for zero isolation. Uniform
upsampling and exception policy, analytic realization of the completed-L
scale/tail/reality premises, concrete inhabitants of the exact primitive-
roster/character-row/source-evaluator contracts, zero isolation, Turing
completeness, the separate `q=1` zeta case, an H100 calibration and completed
source run, and a Lean
whole-frame byte parser or deterministic sidecar generator, a practical
complete-trace producer or proved compact-checker refinement, analytic input
and root containment, and final finite-GRH realization
also remain open. Consequently this stage has a source-capable bounded-memory
execution protocol, but it does not yet discharge the external atom.
