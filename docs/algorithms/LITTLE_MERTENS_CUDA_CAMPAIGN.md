# Exact little-Mertens CUDA campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

The `sparkinterval-tg-mobius-segment` runner can produce resumable exact
external-computation evidence for both finite claims used by ternary Goldbach:

```text
|sum_(n <= x) mu(n)/n| <= sqrt(2/x)       (1 <= x <= 10^12)
|sum_(n <= x) mu(n)/n| <= 1/(2 sqrt(x))   (3 <= x <= 7,727,068,587).
```

The implementation is full-range-capable, but no complete production campaign
is retained in this repository.  Receipts are local external evidence.  They
are neither GPU attestation nor a Lean theorem connecting the computation to
`ArithmeticFunction.moebius` and real square roots.

## Exact directed state

Let `S = 2^96`.  The runner carries two signed 128-bit integers `L_n,U_n`.
Starting with `L_0=U_0=0`, it applies

```text
L_n = L_(n-1) + floor(mu(n) S/n)
U_n = U_(n-1) + ceil (mu(n) S/n).
```

Consequently, by induction using integer division only,

```text
L_n/S <= sum_(k <= n) mu(k)/k <= U_n/S.
```

Each nonzero Möbius term widens the interval by at most one fixed-point unit.
Even the elementary worst-case width through `10^12` is therefore at most
`10^12/2^96 < 1.27e-17`.  Every signed-state addition is checked before it is
performed; an overflow terminates the runner without a receipt.

For a real `x` with `floor(x)=n`, the sum is constant on `[n,n+1)`, while both
right sides decrease.  The runner therefore uses right endpoint `r=n+1` for
every nonfinal slab and the closed source endpoint `r=N` at `n=N`.  If
`A=max(|L_n|,|U_n|)`, it checks the source-shaped integer comparisons

```text
r A^2 <= 2 S^2             for equation (2.11),
4 r A^2 <= S^2             for the stronger range.
```

These comparisons use unsigned 256-bit products with explicit overflow
failure.  No floating-point value decides a Möbius value, interval endpoint,
or inequality.  Floating point appears only in diagnostic CUDA timing fields.

The GPU Möbius records are compared row-for-row with a separate host segmented
sieve.  The receipt hash commits to both prefix states, both directed
little-Mertens endpoints and deltas, all checked slab counts and first
failures, the record digest, the executable digest, and the previous receipt
digest.

## Full campaigns and resume

Build the existing target-neutral runner and run both claims through `10^12`:

```bash
cmake -S . -B build/dgx-spark -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark --target sparkinterval-tg-mobius-segment

python3 tools/tg_mobius_campaign.py run \
  --runner build/dgx-spark/sparkinterval-tg-mobius-segment \
  --output-dir /durable/path/little-mertens-both \
  --target both \
  --segment-count 100000000 \
  --allow-other-device
```

For a strict H100 run, build `sparkinterval-h100-tg-mobius-segment`, select it
as `--runner`, and omit `--allow-other-device`.  To run only the shorter claim,
use `--target stronger`.  `--target 2-11` and `--target both` both end at
`10^12`; the latter label makes the intended simultaneous interpretation
explicit.

The supervisor copies and hashes the runner once, invokes gap-free segments,
checks each receipt before retaining it, writes receipts and the manifest
atomically, and resumes only when the runner hash and immutable configuration
match.  Stop after a bounded sample with `--max-chunks N`; rerunning the same
command without that option resumes from the last checked state.  An optional
per-invocation wall limit is available as `--chunk-timeout-seconds`.

The same receipt carries the exact Hurst-Mertens and CDEM squarefree states.
The supervisor therefore also accepts `--target hurst` and
`--target squarefree`, both ending at `10^16` and stopping only on the failure
fields for the selected predicate. Those linear modes are formally runnable
and resumable, but their expected resource cost is prohibitive; they are not a
practical substitute for the missing compressed Hurst/squarefree argument.

Retained files can be checked without executing CUDA:

```bash
python3 tools/tg_mobius_campaign.py verify \
  /durable/path/little-mertens-both
```

That verifier checks the captured executable hash, duplicate-free JSON,
receipt schema and canonical hashes, exact state composition, segment sizes,
gap-free coverage, endpoints, and manifest.  It deliberately reports
`locally_supervised_execution=false`, `execution_attested=false`, and
`lean_atoms_discharged=false`: files alone do not authenticate where they ran,
and a separate Lean realization/checker is still required.

With the maximum 100-million-row segment size, the stronger campaign has 78
segments and the `10^12` campaign has 10,000.  The latter is a long serial
campaign because each segment consumes the preceding directed interval.  Do
not commit its runner copy, receipts, manifest, or build products to the
repository.

A fresh bounded v2 run over the first 10,000,000 rows on GB10 took 4.32 seconds
wall time: 40.26 ms in CUDA and 3.717 seconds in independent CPU replay plus
the exact Hurst, squarefree, and little-Mertens checks. Both little-Mertens
failure fields were null. This is an implementation regression/throughput
sample only, not evidence for either full endpoint and not an H100 estimate.
