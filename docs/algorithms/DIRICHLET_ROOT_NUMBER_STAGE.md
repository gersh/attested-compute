# Scalable all-character Dirichlet root-number stage

This component replaces the quadratic reference Gauss-sum loop in the
completed-`L` stream consumer with one all-character transform per modulus.
It implements and certifies the root-number arithmetic needed downstream; it
does **not** isolate or count zeros, perform Turing closure, discharge Platt's
Theorem 7.1, or discharge a Lean atom.  No full source campaign has run.

The implementation is project-owned code by Gershon Bialer:

- `tg_verifier/dirichlet_root_number_stage.py` is the arithmetic, format,
  persistent stream, receipt, exact work inventory, and direct replay;
- `tools/tg_dirichlet_root_number_stage.py` is the CLI;
- `tests/tg_dirichlet_root_number_known_answers.py` is a fresh independent
  MPFR-transform/direct-Arb KAT; and
- `tests/test_tg_dirichlet_root_number_stage.py` contains structural,
  arithmetic, persistence, and tamper tests.

The source convention is fixed by a digest in every control and receipt.  If
the canonical group coordinate is `e=(e_j)` and the output frequency is
`k=(k_j)`, the existing `TGDAFF` transform computes

```text
sum_e X[e] exp(+2 pi i sum_j e_j k_j/n_j).
```

The new producer supplies

```text
X[e] = exp(+2 pi i canonical_residue(e)/q),
```

so output `k` is exactly the positive-additive-character Gauss sum

```text
tau(chi_k) = sum_(a mod q) chi_k(a) exp(+2 pi i a/q).
```

For parity `a_chi=(1-chi(-1))/2`, the stage computes

```text
w(chi) = tau(chi) / (i^a_chi sqrt(q)),
h(chi) = principal_sqrt(conj(w(chi))).
```

The downstream real critical-line expression is therefore

```text
h(chi) (q/pi)^(it/2) Gamma((1/2+a_chi+it)/2)
  exp(pi t/4) L(1/2+it,chi).
```

Both signs in the two exponentials and the `i^a_chi` division are part of the
format convention.  A negative-additive-character transform is rejected by
the independent KAT rather than silently being relabeled.

## Certified additive input

For each active `q`, Arb at a pinned precision certifies the single seed

```text
zeta_q = exp(2 pi i/q).
```

An outward Arb power recurrence computes all exponents through `q`, verifies
that the final product encloses one, and writes only unit residues into the
actual-residue order reconstructed by `canonical_residue_order(q)`.  Every
Arb rectangle is converted to enclosing binary64 endpoints by exact dyadic
comparison; the code reconstructs the resulting Arb rectangle and requires
it to contain the original before writing it.  The result is an ordinary
one-batch `TGDAFFI1` file, so both the existing H100 producer and the
independent MPFR implementation can consume it unchanged.

The primitive map has a separate source-scale implementation.  It factors
and reconstructs generators once per `q`, then un-ranks every primitive
frequency, Conrey number, and parity.  Its small-modulus output is tested
against the older scalar map.  This matters operationally: the scalar wrapper
reconstructed a sieve and primitive root for each character and took 4.4
seconds merely to normalize `q=10007`; the bulk map reduced that measured
step to 0.389 seconds.

## Compact `TGDRNRO1` artifact

The root frame has a 96-byte little-endian header:

```text
magic[8] = TGDRNRO1
version:u32, q:u32, component_count:u32, record_size:u32
primitive_character_count:u64
additive_TGDAFFI1_sha256[32]
transform_TGDAFFO1_sha256[32]
```

It is followed by one 32-byte complex interval in canonical primitive ordinal
order.  The interval is `h(chi)`, not `tau(chi)`, because that is the only
phase the completed-`L` consumer needs.  Frequency ID, Conrey number, and
parity are not trusted payload: the reader reconstructs them from `q`.

The canonical JSON receipt binds the artifact hash, both upstream hashes, the
primitive identity-row hash, exact convention digest, component orders,
precision, transform work, and the explicit non-closure classification.  A
receipt cannot be relabeled to a different additive input or transformed
frame.  A measured/attested production run must additionally bind that the
named TGDAFF executable actually consumed the named input; two hashes in a
plain unsigned receipt are commitments, not by themselves proof of execution.

Retaining every large-`q` root frame would use 945,546,375,328 bytes (about
945.5 GB decimal).  Production should instead keep one root frame (at most
12,799,712 bytes), reuse it for all ordinates of that modulus, then retain its
receipt hash.  `consume_streams` accepts canonical NDJSON controls and
concatenated `TGDAFFO1` frames in one process, emits concatenated `TGDRNRO1`
frames and canonical per-`q` receipt lines, and retains only one modulus in
memory.  It requires strictly increasing `q` and rejects trailing data.

## Exact source work

`source-work` recomputes and pins the complete `10001 <= q <= 400000` domain,
skipping moduli with no primitive character:

| quantity | exact count |
|---|---:|
| active moduli / Arb exponential seeds | 292,500 |
| additive power-recurrence multiplications | 59,962,402,500 |
| unit-group input rectangles | 40,503,165,302 |
| component dimensions across active q | 816,177 |
| current per-q twiddle enclosures | 71,135,060,058 |
| cross-q cacheable twiddle enclosures | 12,952,682,706 |
| primitive root records | 29,547,446,729 |
| one-batch radix-2 TGDAFF butterflies | 2,645,418,549,056 |
| unstreamed root artifact bytes | 945,546,375,328 |

These are source-work facts, not evidence that the campaign ran.  The
quasi-linear transform replaces roughly 7.9 quadrillion direct
character/residue visits in the old consumer with 2.65 trillion butterflies.

## Independent KAT and failure modes

The KAT first generates certified additive inputs, then runs the existing
independent MPFR-directed TGDAFF implementation.  A separately written direct
Arb loop evaluates every character Gauss sum for `q=5,7,8,15` and requires the
compact artifact to contain every expected completed phase.  It includes:

- the primitive quadratic character `q=5`, Conrey 4, whose character order is
  2 but whose ambient group exponent is 4;
- non-real primitive characters;
- an explicit positive-versus-negative additive-exponential check;
- artifact and convention tampering; and
- two concatenated moduli through the persistent bounded protocol.

The stage also requires each normalized root and completed multiplier to
contain unit modulus and verifies the square relation.  It fails closed on an
incorrect transform header, q, batch count, group order, primitive map,
parity, convention digest, record order, interval shape, hash, or source-work
count.

## Local benchmark and source projection

Measurements below were taken on the local DGX Spark on 2026-07-21 with the
GB10 CUDA TGDAFF runner and 192-bit Arb.  They are not H100 measurements.

| q | input | TGDAFF process wall | reported plan prep | reported GPU arithmetic | normalization |
|---:|---:|---:|---:|---:|---:|
| 1,009 | 0.0265 s | 0.524 s | 0.0817 s | 0.000221 s | 0.0791 s |
| 10,007 | 0.258 s | 1.531 s | 1.091 s | 0.000512 s | 0.389 s |
| 100,003 | 2.550 s | 9.819 s | 9.379 s | 0.00236 s | 3.782 s |

The stable measured rates were about 39,200 additive rectangles/s and 26,400
primitive normalizations/s on one CPU process.  Applying those rates to the
exact source counts gives roughly 287 CPU-core-hours for input construction
and 311 CPU-core-hours for normalization.  The measured TGDAFF arithmetic
rate from the existing all-character benchmark makes the one-transform-per-q
arithmetic about 0.53 GB10 GPU-hours in aggregate.  Arithmetic is not the
bottleneck.

Fresh per-q TGDAFF plans construct about 71.14 billion complex twiddle
enclosures on the primitive-only roster. The persistent multi-q service now
uses one exact 512-MiB budget split into a `134,216,256`-byte immutable catalog
for all 19 convolution-root pairs and a `402,654,656`-byte component-order
chirp/kernel LRU. Its version-2 summary separately binds both cache layers,
and an independent parser replays its stream hashes, key chain, root catalog,
cache transitions, preparation counts, and residency.

Exact source simulation gives 532,611 order hits from 816,177 accesses and
constructs the 19 roots exactly once. Total preparation falls from
71,070,799,840 enclosures for the preceding whole-plan LRU to
18,106,321,498, a 74.52% reduction. This is still above the
12,952,682,706-enclosure unlimited distinct-order ideal. On the same targeted
eight-modulus GB10 workload sharing component order 5002, seven fresh-process
runs had median preparation `0.5622 s`, GPU arithmetic `0.01118 s`, and wall
time `1.0830 s`; payloads were byte-identical and passed independent 192-bit
MPFR containment. The small reuse case is essentially unchanged from the
previous whole-plan cache because all its useful entries already fit.

`source_performance_ready` remains false: the source supervisor has not wired
the multi-q service, no source-scale execution exists, and the remaining
order-specific preparation has not been scheduled or measured on the actual
cluster. No H100 runtime is inferred from this GB10 component benchmark.

## Exact consumer integration

`tg_verifier/dirichlet_stream_zero_consumer.py` accepts a `TGDRNRO1` artifact
and its receipt as a matched pair.  On the first transform frame it validates
the receipt self-hash, q, convention digest, additive-input and TGDAFF-output
hashes, component and primitive counts, artifact digest, binary shape, and
every stored interval.  It independently reconstructs
`primitive_frequency_records_bulk(q)`, pairs record ordinal `j` with that
identity, and sets `RootRecord.epsilon` to the stored
`principal_sqrt(conj(tau/(i^parity*sqrt(q))))` interval.  The map is retained
through the complete q shard, and both artifact hashes enter the consumer's
root hash chain and final receipt.

The consumer's completed-value formula already multiplied
`RootRecord.epsilon`, so this integration did not change the analytic formula.
The direct quadratic Arb function remains the independent KAT/replay path and
is never needed in the source loop when the artifact is supplied.  This closes
the former quadratic root-number performance gap; it does not supply exception
upsampling, zero isolation, or Turing completeness.

For a source-wide run,
[`DIRICHLET_ROOT_CATALOG.md`](DIRICHLET_ROOT_CATALOG.md) now splits the
persistent output stream into canonical per-q files and builds a streaming
catalog over exactly the 292,500 moduli having primitive characters. It reuses
this module's parser on the exact safely opened bytes and can fully revalidate
every artifact during supervisor binding. The catalog implementation exists;
the roughly 945.5-GB source root stream/catalog has not been generated.

## Commands

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_root_number_stage.py \
  --pretty source-work

.venv-tg-flint/bin/python tools/tg_dirichlet_root_number_stage.py \
  additive-input /tmp/q5.in /tmp/q5.input.json --q 5 --precision 256

build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr \
  compute /tmp/q5.in /tmp/q5.out 256

.venv-tg-flint/bin/python tools/tg_dirichlet_root_number_stage.py \
  consume /tmp/q5.out /tmp/q5.roots /tmp/q5.roots.json --q 5 \
  --additive-receipt /tmp/q5.input.json --precision 256

.venv-tg-flint/bin/python tools/tg_dirichlet_root_number_stage.py \
  direct-replay /tmp/q5.roots /tmp/q5.roots.json --precision 256

.venv-tg-flint/bin/python tests/tg_dirichlet_root_number_known_answers.py \
  --checker build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr

.venv-tg-flint/bin/python -m unittest \
  tests.test_tg_dirichlet_root_number_stage -v
```

The primary source for the surrounding algorithm and computation is Platt,
*Numerical computations concerning the GRH*, arXiv:1305.3087 and the accepted
Mathematics of Computation manuscript linked in the module.  This stage is a
new implementation and does not claim that the paper specifies this artifact
format or execution architecture.
