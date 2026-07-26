# Ternary-Goldbach zeta-zero campaigns

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

[`tg_verifier/zeta_zero_campaign.py`](../../tg_verifier/zeta_zero_campaign.py)
and [`tools/tg_zeta_campaign.py`](../../tools/tg_zeta_campaign.py) provide the
original Python/FLINT workflow for these named external atoms:

| profile | exact height | required `N(T)` |
|---|---:|---:|
| `platt-head-2e4` | `20000` | `22491` |
| `platt-trudgian-rh-3e12` | `3000175332800` | `12363153437138` |

The second count is the paper count encoded by the profile.  Initialization
does not trust that integer silently: it calls `arb.zeta_nzeros(T)`, requires
an exact integer ball, and fails unless the result equals the encoded value.
The height and count are Theorem 1 of
[Platt--Trudgian (2021)](https://doi.org/10.1112/blms.12460).

This is an external analytic verifier. It trusts the pinned FLINT
implementation and host toolchain and does not connect FLINT's zeta function
to Mathlib's `riemannZeta`. No command marks either Lean atom discharged.

## Install the pinned runtime

Use an isolated environment. The code also checks the versions at runtime and
rejects every other combination.

```bash
python3 -m venv .venv-tg-flint
.venv-tg-flint/bin/pip install -r requirements-tg-flint.txt
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py profiles
```

The required versions are `python-flint==0.9.0` and bundled `FLINT==3.6.0`
(`FLINT_RELEASE=30600`).

For the source-height atom, the native count-only implementation and fixed
parallel plan in
[`PLATT_ZETA_FLINT_CAMPAIGN.md`](PLATT_ZETA_FLINT_CAMPAIGN.md) supersede the
literal Python loop below. The older workflow remains useful for the complete
height-20,000 replay and independent spot checks.

For an arbitrary positive integer height, compute the exact
multiplicity-counted value `N(T)` directly:

```bash
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py count \
  --height 1000000 --expected 1747146
```

An arbitrary consecutive critical-line batch can be isolated by index without
creating a campaign:

```bash
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py isolate \
  --first-index 1 --count 1000 --precision-bits 96
```

That command requires every returned real part to be exactly `1/2`, every
ordinate ball to be positive, finite, and strictly disjoint, and emits a
canonical interval-stream digest.

## Complete height-20,000 replay

The one-command form initializes an immutable plan, isolates all `N(T)+1`
records, and finalizes the chain:

```bash
OUT="$(mktemp -d build/tg/zeta-head-2e4.XXXXXX)"
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty full "$OUT" \
  --profile platt-head-2e4 --batch-size 4096 --precision-bits 96
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty verify \
  "$OUT" --complete

# Reconstruct the exact 22,491 Q128 rows used by the Lean consumer. This
# fails unless both reviewed included-table and sentinel-inclusive digests match.
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty emit-lean-table \
  "$OUT" build/generated/PlattHeadQ128.lean
```

The profile additionally proves the strict reciprocal bound

```text
sum_{0 < gamma <= 20000} 1/gamma < 5.15966.
```

Each reciprocal is rounded outward to a dyadic denominator before summation,
so the artifact size remains bounded without replacing a rigorous inequality
by a floating-point comparison.

## Resuming the source-height campaign

Use separate commands for a long run:

```bash
OUT="build/tg/zeta-rh-3000175332800"
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty init "$OUT" \
  --profile platt-trudgian-rh-3e12 \
  --batch-size 1000000 --precision-bits 96

# Repeat under a scheduler. Every invocation validates the retained prefix,
# recomputes N(T), and atomically adds at most ten batches.
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty run "$OUT" \
  --max-chunks 10

# Only after every batch exists:
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty finalize "$OUT"
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py --pretty verify \
  "$OUT" --complete
```

`--skip-count-replay` avoids repeating the exact `N(T)` call during an
individual resume invocation; initialization always performs it. A killed
process can lose only its currently uncommitted batch. Existing nonidentical
artifacts are never overwritten.

The source-height campaign contains more than twelve trillion zero records.
The original implementation is range-complete and bounded-memory, but a naive
full recomputation remains computationally enormous. The newer native FLINT
Platt campaign removes per-zero artifact storage and supports fixed parallel
shards, Merkle aggregation, and named-API audit replay. It is still a
multi-year computation at available CPU throughput. No source-height run is
claimed merely because either scheduler exists.

## Artifact and proof logic

`campaign.json` pins the source claim, exact count, precision, batch size,
FLINT versions, and exact reusable-module source hash. A changed producer
cannot silently resume an old plan. Each `chunk-NNNNNNNNNNNN.json` contains:

- an exact, gap-free index range;
- the previous artifact SHA-256 and immutable campaign SHA-256;
- exact rational first/last and cutoff-adjacent endpoints;
- a digest over every exact rational ordinate interval in the batch;
- positive/disjoint/critical-line results from the fresh FLINT call; and
- an outward dyadic reciprocal-sum enclosure.

For `platt-head-2e4`, every chunk additionally retains all of its indexed
exact rational interval preimages. The structural verifier recomputes their
digest, ordering, endpoints, and minimum-gap summary. `emit-lean-table` rounds
the first 22,491 rows outward at scale `2^128`, checks every reciprocal
cross-product, and refuses output unless the 22,491 included rows hash to
`e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7`
and all 22,492 rows including the cutoff sentinel hash to
`fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca`.
Both are computed from the same table audited in `claude_math`; distinguishing
them prevents the source-table commitment from accidentally naming the longer
sentinel table. The generated module contains literal `Q128Cell` rows and no
axiom. The source-height profile keeps this field null: retaining trillions of
interval preimages is not viable.

The final checker verifies contiguous index and hash coverage, strict
disjointness across chunk boundaries, exactly one last-included and one
first-excluded interval, `gamma_N <= T < gamma_(N+1)`, and the aggregate
reciprocal enclosure. Since `zeta_nzeros(T)` counts every zero with
multiplicity while there are `N(T)` disjoint critical-line isolations below
the cutoff, equality forces every retained isolation to be simple and leaves
no additional on-line or off-line zero below the height.

Structural `verify` checks retained arithmetic and the artifact chain but does
not reevaluate zeta. Use `replay-chunk` for a fresh byte-for-byte FLINT replay
of any retained batch:

```bash
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py replay-chunk "$OUT" 0
```

## Closed measured Azure head job

The `platt-head-2e4` profile is also wrapped as one challenge-bound Azure
SEV-SNP CPU job. The wrapper runs the complete campaign, replays all six
chunks, emits and retains the literal table, and then independently replays
the retained archive in the external trace verifier. Its materializer pins
the full FLINT/python-flint source trees and exact x86-64 runtime wheel and
accepts no caller-selected command. See
[`PLATT_HEAD_AZURE_MEASURED_WORKLOAD.md`](PLATT_HEAD_AZURE_MEASURED_WORKLOAD.md)
for the exact closure and operator workflow. No Azure run or accepted receipt
is currently claimed, and the semantic inventory row remains disabled.
