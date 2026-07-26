# PT21 bounded sloppy-DD multiplication qualification

This component is a qualification-only arithmetic and performance experiment.
It is not linked into the PT21 transform, does not change the default
`run_source_window` path, and emits no source, production, attestation, or
CUDA-to-Lean refinement certificate.

The PT21 radix-2 butterfly spends most of its time multiplying one two-limb
complex disk by a root disk. The current implementation expands every
high/low limb product with FMA and compresses all resulting terms. The
qualification executable compares that implementation with the bounded
sloppy-DD helpers already used by the source accumulator.

## Candidate formula

Write two real centres as

```text
a = ah + al
b = bh + bl.
```

Let `eta = 2^-1074`, and let

```text
kappa = 0x1.0000000000001p-53
E(r) = RU(kappa * |r| + eta).
```

`kappa` is an upward binary64 bound for `u/(1-u)`. Thus `E(r)` bounds
round-to-nearest error without assuming that the exact result is normal.
The `eta` term explicitly covers zero and subnormal results.

The candidate computes

```text
(p,q) = TwoProductFMA(ah,bh)
c0    = RN(ah*bl)
c1    = RN(al*bh)
c     = RN(c0+c1)
low   = RN(q+c)
(h,l) = TwoSum(p,low).
```

Its outward real-centre error is

```text
eta + E(c0) + E(c1) + E(c) + E(low)
    + RU(|al|*|bl|) + 6*eta.
```

The omitted `al*bl` product is charged explicitly. No non-overlap,
normalization, relative limb-size, normal-result, or no-cancellation
assumption is made. The fast addition used to combine the four real
products similarly charges both rounded low additions plus an underflow
budget for its two `TwoSum` operations.

Four real multiplications and two real additions form the complex centre.
Their componentwise error bounds are added with directed rounding. The
result radius uses the same `MulCertificate` decomposition as the current
root multiplication:

```text
centerError
  + leftCenterNormBound * rightRadius
  + rightCenterNormBound * leftRadius
  + leftRadius * rightRadius.
```

The left-centre bound and centre-error bound use inexpensive L1 bounds.
The supplied right-centre norm is independently checked before the result
is accepted.

Every input and every arithmetic intermediate is checked for finiteness.
Negative radii or bounds and every nonfinite intermediate fail closed.
Compilation requires both `--ftz=false` and the explicit
`SPARKINTERVAL_CUDA_FTZ_DISABLED=1` contract. Underflow is not silently
excluded: the minimum-subnormal budgets cover it, and the corpus exercises
signed zero, subnormal inputs, and subnormal products.

## Independent exact checker

The executable decodes every finite binary64 word to a
`boost::multiprecision::cpp_rational`. It then checks, with exact dyadic
arithmetic:

1. the squared complex-centre error is at most the squared emitted centre
   error bound;
2. both squared centre norms are at most their squared emitted bounds; and
3. the complete radius expression above is at most the output radius.

These are the executable obligations of
`SparkInterval.Certified.ComplexDisk.MulCertificate`. The checker does not
derive its expected centre from either CUDA implementation and therefore
does not assume that the new CUDA arithmetic is correct. The existing Lean
theorem proves the semantic disk-multiplication decomposition, but this
qualification does not claim a physical CUDA-to-Lean refinement.

The deterministic 8,192-row corpus has SHA-256 commitment
`50738ee7a4b57069c074b8cbdc373ed6feb0e90991f8ec364b68b8cef725f6c7`
and diagnostic FNV-1a identifier `c514385c1781a38e`. The digest is over a
canonical, field-by-field, little-endian encoding of IEC-559 binary64 and
32-bit integer words; it does not depend on C++ structure padding or native
endianness. Its 4,113 nonpadding rows include 4,096 PT21-like two-limb/root
cells plus signed-zero, minimum-subnormal, maximum-subnormal, minimum-normal,
overlapping-limb, cancellation, wide-exponent, and intentional rejection
cases.

Three malformed/overflow cases must fail with their exact expected status:
two invalid inputs and one nonfinite-intermediate/nonfinite-output overflow.
A fourth negative KAT supplies a deliberately undersized root-centre norm.
Both CUDA implementations accept its finite arithmetic, but the independent
checker must reject specifically the right-norm obligation. A dedicated
near-tight `fast_add_center` KAT checks a fuzz-derived overlapping-limb case:
its exact centre error is `0x1p+215`, while the emitted bound must have the
deterministic binary64 word `0x1.0000000000003p+215`. Eight direct scalar
`fast_mul_center` KATs independently check exact centre error against the
emitted bound, avoiding any masking between complex components.

## GB10 qualification result

On 2026-07-26, a Release `sm_121` build on the local NVIDIA GB10 ran
1,048,576 root multiplications per trial with 13 interleaved repetitions:

| implementation | median | minimum | registers/thread | local bytes |
|---|---:|---:|---:|---:|
| current full expansion | 2.966656 ms | 2.939200 ms | 68 | 0 |
| bounded sloppy DD | 1.337792 ms | 1.325376 ms | 54 | 0 |

The isolated median speedup was `2.21758x`. The timed input is exactly the
4,096 PT21-like rows; malformed and adversarial KATs are excluded. This is
not a full-transform speedup. The fast helpers are out-of-line in this
microbenchmark, while the production transform may expose different register,
call, and occupancy behavior. The candidate changes the centre and radius, so
byte identity with the current transform is neither expected nor claimed.

An `sm_121` SASS audit counted 374 scalar FP64 arithmetic instructions in
the full root-multiplication kernel. The candidate has 16 in the caller,
two 20-instruction fast-add calls, and four 27-instruction fast-multiply
calls, or 164 dynamically executed scalar FP64 instructions. This is a
56.1% reduction. The strict `sm_90` build has 373 versus the same 164
dynamic FP64 instructions; it compiled at 64 versus 52 registers/thread,
with no local-memory allocation. No H100 runtime measurement has occurred.
Bounded runs of CUDA memcheck, initcheck, and racecheck on the final GB10
binary reported zero errors and zero race hazards.

All ordinary rows passed the independent exact-dyadic check, all rejection
KATs produced their expected failure reason, and the deliberately bad norm
was caught by the intended exact obligation. For the 4,096 PT21-like rows,
candidate/current output-radius ratios were:

| quantile | ratio |
|---|---:|
| median | 1.0014729681 |
| 90th percentile | 1.0019448378 |
| 99th percentile | 1.0023088987 |
| maximum | 1.0028517497 |

These are one-multiplication ratios. They do not bound accumulated
inflation through an FFT. Before considering integration, a separate
qualification must run the complete transform on genuine source packets,
check every final disk independently, measure ambiguity/event changes, and
benchmark an H100. Until then the production transform remains unchanged.

## Reproduction

```bash
cmake -S . -B build/pt21-sloppy-release-sm121 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=121

cmake --build build/pt21-sloppy-release-sm121 \
  --target sparkinterval-tg-platt-dd-sloppy-mul-qualification

ctest --test-dir build/pt21-sloppy-release-sm121 \
  -R '^tg_platt_dd_sloppy_mul_qualification_known_answers$' \
  --output-on-failure

build/pt21-sloppy-release-sm121/sparkinterval-tg-platt-dd-sloppy-mul-qualification \
  --repetitions=13 --benchmark-log2=20

cmake --build build/pt21-inline-h100 \
  --target sparkinterval-h100-tg-platt-dd-sloppy-mul-qualification
```

The strict H100 executable rejects every non-H100 device before running.
