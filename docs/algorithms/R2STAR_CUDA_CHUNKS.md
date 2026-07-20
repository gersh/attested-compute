# Bounded exact CUDA chunks for the Ramaré R2Star campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

## Scope

`sparkinterval-tg-r2star-chunk` produces a bounded chunk for the exact Python
contract in `tg_verifier/r2star.py`. The contract suite independently
recomputes every chunk it invokes: factor rows, rational logarithm bounds,
Euler-gamma bounds, coefficient intervals, prefix interval, minimum squared
slack, and canonical record hash. A standalone successful runner receipt only
sets `python_contract_replay_required: true`; it does not claim that replay
already occurred.

This is not a completed run through 21 billion, a Lean realization theorem,
or a discharge of `ramare_zuniga_2024_lemma_6_2_source`.

The fixed CUDA configuration is:

| Parameter | Value |
| --- | ---: |
| scale bits | 32 |
| atanh-series terms | 20 |
| harmonic terms | 100,000 |
| directed Euler-gamma lower integer | 2,479,051,107 |
| directed Euler-gamma upper integer | 2,479,194,040 |

The two gamma integers are exactly what the arbitrary-precision Python
contract computes for this configuration.

## Exact-or-reject logarithms

For `1 <= x <= 2`, the Python reference uses

```text
z = (x-1)/(x+1)
log(x) = 2 * sum z^(2j+1)/(2j+1)
```

with a positive geometric-tail bound.  The CUDA kernel encloses that same
rational expression in Q64 integer intervals:

- four radix-`2^16` division digits compute exact floor and ceiling bounds for
  `z*2^64` without floating point or an implicit 128-bit division;
- `__umul64hi` and the low product word give exact directed Q64 products;
- every division by an odd series denominator is rounded explicitly;
- the geometric tail uses a rigorous lower bound for `1-z^2`; and
- the exponent and mantissa intervals are accumulated in two-word unsigned
  integers.

The kernel converts Q64 to scale `2^32` only if both ends determine the same
floor for the lower rational bound and the same ceiling for the upper rational
bound.  Otherwise status `log_resolution_ambiguous` rejects the entire chunk.
It never silently widens a row because that would no longer reproduce the
Python chunk state.  For example, `n = 1,364,330` exercises this fail-closed
path and is pinned by the contract test.

## Transition and overflow boundary

Valid rows reproduce the Python coefficient formulas:

```text
omega(n) = 1:  [-ceil(log(p)_up^2/S), -floor(log(p)_lo^2/S)]
omega(n) = 2:  [ floor(2 log(p)_lo log(q)_lo/S),
                 ceil(2 log(p)_up log(q)_up/S)]
otherwise:     [0, 0]
```

where `S = 2^32`.  Twice the directed Euler-gamma interval is then added.
A deterministic blocked CUDA transition scans 1,024-row local prefixes,
composes their signed incoming offsets with checked additions, evaluates the
envelope rows in parallel, and reduces block minima in index order.  It checks

```text
(100 * max(abs(R_lower), abs(R_upper)))^2
  <= 193^2 * n * log(n)_lower^2.
```

Every signed prefix addition is guarded before evaluation.  The left side is
accepted only when `100*magnitude` fits `u64`; its square then fits `u128`.
For the source range, `log(n)_lower < 2^37`, so the right-side coarse maximum

```text
193^2 * 21,000,000,000 * (2^37)^2 < 2^128
```

fits the checked two-word multiplication.  Every intermediate multiplication
still has an explicit overflow test.  A successful chunk therefore has no
unreported machine-integer wraparound.  This does not assume the theorem to
bound the prefix: an out-of-range incoming or intermediate state simply
rejects.

The original one-thread transition remains available behind
`--cross-check-serial`.  The contract suite compares every summary field
across internal block boundaries, including a negative incoming state.  A
synthetic known-answer test makes every endpoint's squared slack equal to zero
across three blocks and checks that strict ordered reduction retains the
earliest witness, `n = 3`.  Block-total and per-row signed additions are
checked before use; an overflow rejects rather than wrapping.

Scale 40 was not selected.  At the source endpoint the claimed bound itself
can occupy about 79% of signed 64-bit range, versus about 0.31% at scale 32.
It also leaves only 24 Q64 guard bits, causing far more unresolved rounding
rows.  Scale 32 gives substantially clearer overflow and resolution margins.

## Hash compatibility and composability

The GPU factor record retains the first two factors and caps `omega` at three,
which is enough for the coefficient.  The receipt's factor-support digest is
stronger: independent host trial factorization emits every distinct factor
using Python's exact encoding

```text
"r2star-distinct-prime-support-u64be-v1" NUL
u64be(n) | u64be(factor_count) | factor_count * u64be(factor)
```

and checks that each capped GPU record agrees.  The chunk body is serialized
with exactly Python's sorted compact JSON spelling before SHA-256.  Tests feed
the resulting fields directly to `R2StarChunk` and verify them with the
arbitrary-precision Python implementation.

`previous_hash`, the incoming interval, and the half-open range make chunks
composable.  SHA-256 provides deterministic integrity and linkage, not
authentication or evidence of a particular physical GPU execution.

## Commands and measured boundary

```bash
cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark --target sparkinterval-tg-r2star-chunk

./build/dgx-spark/sparkinterval-tg-r2star-chunk \
  --lower 1 --count 1000000

python3 tests/tg_r2star_cuda_chunk_contract.py \
  --runner build/dgx-spark/sparkinterval-tg-r2star-chunk
```

On the local GB10, the factor kernel took 2.411 ms, log/coefficient rows took
1.211 ms, and the blocked prefix/envelope transition took 2.584 ms for
`[1,1000001)`, for 6.207 ms of measured kernels. The output fields and record
hash exactly matched the former serial transition.  Independent host factor
checking and hashing took 610.999 ms and dominated the process wall
time.  Naively scaling the low-range host check alone over 21,000 million-row
chunks is about 3.6 hours, but that is not a campaign ETA: high-range trial
division is substantially more expensive, process/artifact overhead remains,
and exact fallback rows are not implemented.  This is also not an H100
measurement.

The remaining production work is concrete:

1. implement an exact fallback artifact for the Q64-ambiguous rows;
2. replace per-process host trial division with an independently checkable
   segmented full-factor digest producer;
3. run, retain, and independently replay the complete gap-free chain; and
4. prove that the integer recurrence and transcendental enclosures realize the
   Lean definition of `R2Star`.
