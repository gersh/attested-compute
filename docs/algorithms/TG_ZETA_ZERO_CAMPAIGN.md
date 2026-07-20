# Ternary-Goldbach zeta-zero campaigns

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

[`tg_verifier/zeta_zero_campaign.py`](../../tg_verifier/zeta_zero_campaign.py)
and [`tools/tg_zeta_campaign.py`](../../tools/tg_zeta_campaign.py) provide one
bounded-memory FLINT/Arb workflow for these named external atoms:

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
The implementation is range-complete and bounded-memory, but a naive full
recomputation remains computationally enormous. No source-height run is
claimed merely because the profile and scheduler exist.

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

The final checker verifies contiguous index and hash coverage, strict
disjointness across chunk boundaries, exactly one last-included and one
first-excluded interval, `gamma_N <= T < gamma_(N+1)`, and the aggregate
reciprocal enclosure. Since `zeta_nzeros(T)` counts every zero with
multiplicity while there are `N(T)` disjoint critical-line isolations below
the cutoff, equality forces every retained isolation to be simple and leaves
no additional on-line or off-line zero below the height.

The compact chunk does not retain all interval preimages. Structural
`verify` checks the artifact chain but does not reevaluate zeta. Use
`replay-chunk` for a fresh byte-for-byte FLINT replay of any retained batch:

```bash
.venv-tg-flint/bin/python tools/tg_zeta_campaign.py replay-chunk "$OUT" 0
```
