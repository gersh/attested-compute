# Equation (13.15) coupled-cap certificate prototype

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

This stage is deliberately **disabled**. It implements and replays the finite,
outward-rounded cell arithmetic needed for
`PaperEq1315DirectEndpointAwareLowerBandCoupledCap`, but it does not yet prove
the improper Gaussian integral and cannot emit a production success.

The immutable machine-readable status is
[`TG_EQ1315_COUPLED_CAP_DISABLED.json`](../../specifications/TG_EQ1315_COUPLED_CAP_DISABLED.json).
The corresponding Lean source is
`Math/Problems/TernaryGoldbach/MinorArcs/Chapter14/PaperEq1315EndpointRepair.lean`
in `claude_math`.

## Exact boundary

For

```text
y  = n / (98 + (9/4)/sqrt(2*pi))
K  = log(y)/2
r0 = 150000
r1 = (3/8)y^(4/15),
```

the lower-band proposition quantifies over

```text
10^27 <= n <= 8875694145621773516800000000000,
q > 150000,
q <= ((y/K)^(1/3))/6,
abs(delta/y) <= 1/(q*(3/4)*y^(2/3)).
```

The right-hand boundary is kept in its correlated, piecewise form:

```text
q <= r1: min(G(y,K,r0), (26/25)  * G(y,K,q))
q >  r1: min(G(y,K,r0), (101/100) * G(y,K,r1)).
```

Both branches are finally multiplied by `sqrt(pi/2)`. The checker derives the
branch from the outward `u` and integer-`q` ranges. A stale caller-supplied
branch is rejected. A rectangle crossing `q=r1` keeps the hull of the two
arms; a production cover should normally split there for a sharper result.

## Correlated cell coordinates

The cell variables are

```text
u = log(y)
v = log(q)
t = 3*abs(delta)*q/(4*y^(1/3)).
```

In these coordinates the full delta guard is exactly `0 <= t <= 1`, while
the original-versus-fresh direct-piece selector is exactly
`t*w^(2/3) <= 1`. The implementation evaluates `delta` from the same
`(u,v,t)` interval instead of separately maximizing it, so the endpoint and
selector correlations survive replay.

Integer `q` blocks are split into even and odd lanes. Replay runs an exact
segmented totient calculation and recomputes `max(q/phi(q))` over the declared
parity roster. The continuous `q` interval and this exact roster envelope are
then carried together through the source formulas. Every cell also proves
that its complete `q` block is under its own outward lower bound for
`((y/K)^(1/3))/6`; the global ceiling `231861020` is only an enumeration
ceiling and is not substituted for that pointwise guard.

## Directed finite integration

[`eq1315_coupled_cap.py`](../../tg_verifier/eq1315_coupled_cap.py) reuses
`RationalInterval` and the directed elementary-function implementation from
`tg_verifier.prop1224_directed`. Endpoints are exact rationals rounded
outward to a selected dyadic precision. Logarithm uses an atanh series with a
directed remainder, and exponential uses a Taylor enclosure. These
primitives correspond to the elementary interval layer already formalized
under `SparkInterval/Certified`.

For each contiguous `w` panel, replay encloses the complete chosen integrand,
including

```text
w^2 * exp(-w^2/2),
```

and multiplies its nonnegative upper endpoint by the exact panel width. This
is an upper Darboux certificate, not midpoint or floating-point quadrature.
Panels start at the conservative endpoint `2/u_hi`, which is at most the live
`1/K = 2/u`. The v1 prototype permits a finite stop no larger than `w=32`.

The lower target drops the positive
`paperRPhi - paperR(y)` interpolation correction. That is a stronger,
simpler numerical target. The existing Lean theorem
`paperGPhiCorrected_ge` proves the needed target decomposition; the final
bridge must instantiate it and connect its expression to the directed
evaluator.

Odd parity uses the cancellation-preserving theorem-level upper model from
the Chapter-14 audit. It is intentionally described as an upper model, not
as literal equality with the source expression. The theorem connecting this
model to the exact Lean direct-piece integrand remains an adapter obligation.
Its analytic ingredients already exist in Lean, notably
`lowCorrected_main_lines_le_radiusLog` and the corresponding Poisson-error
bound; the missing result packages those ingredients in exactly the
cell-evaluator formula.

## Fail-closed production boundary

The fresh formula develops a remote logarithmic singularity outside the
finite audit scale for part of the parameter domain. Gaussian decay makes
the numerical tail tiny, but a finite cutoff cannot silently delete it or
evaluate a source formula outside its justified range. The v1 certificate
therefore has no accepted tail-witness schema:

```text
verify_truncated_certificate  -> may prove only a bounded-w inequality
verify_production_certificate -> always refuses
```

The capability record contains no registered invocation, deployment pin,
source realization, full-domain artifact, successful result, or receipt.
Forging a tail payload or changing an arithmetic claim, cell coordinate,
parity envelope, selector count, schema, or branch causes replay to fail.

Production enablement requires all of:

1. a reviewed quantitative infinite-tail theorem and checkable witness,
   preferably using
   `paperEq1315DirectPieceEnvelope_le_base_add_scaledHigh` plus explicit
   Gaussian moments so the remote singular formula is never evaluated;
2. Lean adapters for the odd-parity upper model and existing
   `paperGPhiCorrected_ge` target-lower theorem;
3. a complete adaptive `(u,v,t)` cover, split by parity and exact integer
   `q` roster;
4. replay and coverage semantics connected to the named Lean proposition;
5. an independently reviewable artifact and, only then, a registered
   execution/receipt route.

## Tests and reference benchmark

Run:

```bash
python3 -m unittest -v tests.test_tg_eq1315_coupled_cap
python3 tools/benchmark_tg_eq1315_coupled_cap.py --pretty
```

The focused tests cover exact guards, the `q=r1` seam, parity-separated
totients, a positive bounded-w sample, a selector-crossing sample, claim and
coordinate tampering, and unconditional production refusal.

On the local reference host on 2026-07-23, four deliberately coarse
finite-`w` cells with 24 total panels took about 1.95 seconds, or about 2.05
cells/second in single-process `Fraction`-based Python. A purely illustrative
`64 * 512 * 64 * 2 = 4,194,304` cell grid projects to about 569 single-core
hours at that rate. This is not a production grid: adaptive splitting,
totient caching, panel refinement, and the missing tail proof can all change
the work materially.

The same command ran an exact 100,000-row segmented totient/envelope prepass
in about 0.12 seconds, roughly 0.86 million rows/second including exact
`Fraction` maxima. A linear pass through the conservative 231,711,020-row
roster would take about 270 single-core seconds. Both parity envelopes share
one segmented-phi pass; the estimate does not include partition or cache
overhead.

No CPU-vectorized or H100 interval kernel exists for this stage, so the
benchmark emits `null` for CPU and H100 projections. An optional
`--assumed-cells-per-second` argument reports a clearly labeled
user-supplied scenario; it is never presented as a measurement.
