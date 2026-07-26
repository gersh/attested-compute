# Bounded t-major factor recurrence

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

[`dirichlet_tmajor_factor_recurrence.py`](../../tg_verifier/dirichlet_tmajor_factor_recurrence.py)
is a bounded, fail-closed experiment for reducing the transcendental cost of
the large-\(q\) factors

\[
q^{-1/2-it_j},\qquad t_j=\frac{5j}{64}.
\]

It uses the exact identity

\[
q^{-1/2-it_{j+1}}
 =q^{-1/2-it_j}\,q^{-i5/64}.
\]

The experiment has its own `TGDFREC1` qualification wire. It does **not**
change `TGDLTMB1`, and it is not presently an admitted production factor
provider.

## Why the recurrence uses disks

A first prototype multiplied outward binary64 rectangles. It was sound in
bounded direct-MPFR comparisons, but dependency wrapping made it unusable:
for \(q=10001\), a 64-step rectangle grew from approximately
`1.73e-18` to `6.28e-8`. That is roughly ten orders of magnitude wider than
the direct enclosure.

`TGDFREC1` instead converts the directed MPFR seed and phase-step rectangles
to Euclidean complex disks. Each subsequent disk multiplication stores the
repository's 96-byte exact-rational `RawMulCertificate`. Its error formula is

\[
e_c + \lVert c_x\rVert r_y+\lVert c_y\rVert r_x+r_xr_y\leq r_{\rm out}.
\]

The Python checker decodes every binary64 word to an exact rational, checks
all squared-norm and radius inequalities, requires an unbroken left/output
chain, requires the same phase-step disk at every step, and reconstructs
every exported rectangle from the certified disk. The corresponding
one-step soundness theorem is already proved without `native_decide` in
[`ComplexDisk.lean`](../../SparkInterval/Certified/ComplexDisk.lean), and its
standalone 96-byte parser is
[`ComplexDiskWire.lean`](../../SparkInterval/Certified/ComplexDiskWire.lean).
[`TMajorFactorRecurrence.lean`](../../SparkInterval/Dirichlet/TMajorFactorRecurrence.lean)
proves that any typed, linked list of those checked multiplications encloses
the seed times the corresponding power of the fixed phase step. Its fresh
axiom print contains only `propext`, `Classical.choice`, and `Quot.sound`.
There is not yet a Lean parser which recovers that typed chain from the
enclosing `TGDFREC1` bytes.

The producer obtains:

- one \(q^{-1/2-it_0}\) seed rectangle at 192-bit directed MPFR;
- one \(q^{-i5/64}\) phase-step rectangle at 192-bit directed MPFR;
- both values again at 256 bits, which must be contained in the first pair;
- 63 exact-rational disk-multiplication certificates for a full block; and
- outward binary64 rectangles containing the resulting disks.

Thus a 64-frame block uses two transcendental boxes per precision instead of
64, a `32x` call-count reduction. The recurrence identity itself remains an
analytic/algebraic realization obligation at the eventual Lean seed bridge.

## Independent Arb check

The optional checker uses the pinned
`python-flint 0.9.0 / FLINT 3.6.0 release 30600` runtime at 384 bits. It first
replays the complete byte and exact-rational chain, then independently
evaluates:

- the MPFR seed;
- the MPFR phase step; and
- either selected frames or all frames in the bounded artifact.

Every Arb interval must be contained in the stored rectangle. The full
64-frame \(q=10001\) check passed locally on 2026-07-25. A one-shot timing was
about `0.017 s` on the development AArch64 host; it is a bounded KAT, not a
source-scale estimate.

```bash
python3 tools/tg_dirichlet_tmajor_factor_recurrence.py build \
  /tmp/q10001-factors.tgdfr \
  --q 10001 --first-t-index 0 --count 64

python3 tools/tg_dirichlet_tmajor_factor_recurrence.py verify \
  /tmp/q10001-factors.tgdfr \
  --expected-sha256 "$PINNED_SHA256" \
  --full-direct-mpfr

PYTHONPATH=. /tmp/tg-flint-venv/bin/python \
  tools/tg_dirichlet_tmajor_factor_recurrence.py verify-arb \
  /tmp/q10001-factors.tgdfr \
  --expected-sha256 "$PINNED_SHA256" \
  --precision-bits 384
```

`verify-arb` without `--frame` checks the complete bounded factor roster.
Repeated, sorted `--frame` arguments request a spot KAT.

## Bounded measurements

The table reports medians of 101 repetitions on the development AArch64 host.
The direct baseline generates all 64 factors at 192 bits and repeats all 64
at 256 bits. The recurrence build includes its exact in-memory serialization
replay; the replay column is a fresh independent parse and arithmetic replay.

| \(q\) | first index | direct MPFR | recurrence build | recurrence replay | max width |
|---:|---:|---:|---:|---:|---:|
| 10,001 | 0 | `0.00714 s` | `0.00605 s` | `0.00550 s` | `7.32e-15` |
| 200,000 | 3,000 | `0.00647 s` | `0.00551 s` | `0.00519 s` | `7.31e-15` |

The bounded Python implementation is therefore a modest wall-clock
optimization as well as a `32x` transcendental-call reduction: the complete
build plus serialization check was `1.18x` faster than the direct
two-precision baseline at both measured points, and fresh replay was
`1.25--1.30x` faster. The fast path proposes ordinary binary64 centers,
outward radii, and a deliberately loose `2^-54` center-error bound; exact
rational replay is the acceptance rule and rejects an insufficient proposal.
The resulting boxes are about `7.3e-15` wide after 63 products. That is much
wider than direct MPFR but still over six orders of magnitude narrower than
the rejected naive rectangle recurrence.

This bounded speedup is not yet a source-scale projection. Python object and
certificate overhead, process topology, downstream sensitivity to the wider
factor boxes, and the cost of source-wide independent replay remain
unmeasured. A production attempt should move the same checked disk operations
to bounded C++/GMP or generate compact witnesses for the existing Lean
checker, then measure interval usefulness through the CUDA composition and
FFT stages.

## Downstream qualification

[`dirichlet_tmajor_recurrence_downstream.py`](../../tg_verifier/dirichlet_tmajor_recurrence_downstream.py)
now performs that bounded downstream measurement instead of extrapolating
from factor widths. Its default fixture has two source-range moduli,
`q=10001,10003`, and all 64 ordinates in the first t-major block. It runs:

1. direct 192-bit factors with complete 256-bit containment replay;
2. `TGDFREC1` production and exact-rational chain replay, followed by a
   complete direct-MPFR differential check;
3. two ordinary, freshly replayed `TGDLTMB1` blocks over the same authenticated
   synthetic lattice rows, using direct sidecars for one and a q-major
   manifest containing the recurrence boxes for the other;
4. the real row-resident CUDA residue-composition runner;
5. the real persistent CUDA multi-q all-character transform; and
6. the standalone MPFR all-character checker on every direct and recurrence
   transform frame.

It compares every binary interval after composition and after the transform.
Containment is the acceptance condition: widening a recurrence endpoint
inward past even one direct endpoint is an attack-test failure. CUDA summary
hashes, block receipts, sidecar manifests, frame identities, and the
independent MPFR transform checker are all replayed before the comparison.

The deterministic 64-row comparison on the development GB10 found:

| layer | direct maximum width | recurrence maximum width | median recurrence/direct width |
|---|---:|---:|---:|
| factors | `1.734723475976807e-18` | `7.310124727766265e-15` | reported in each fresh run |
| residue composition | `6.543376951384516e-15` | `3.4904371060129336e-14` | `2.057103825136612` |
| all-character transform | `2.0516550132687605e-6` | `6.532481735987972e-6` | `2.212861166794328` |

All `128` recurrence factors contained their direct-MPFR counterparts, all
`1,175,040` recurrence composition intervals contained the direct CUDA
intervals, and all `1,175,040` transformed recurrence intervals contained the
direct transformed intervals. The streams are intentionally not
byte-identical: containment, not equality, is the relevant relation.

The qualification report separately records factor-production wall time,
CUDA composition kernel and wall times, CUDA all-character kernel and wall
times, independent-checker frame counts, and the width statistics. Its
conservative `recurrence_beneficial_for_current_pipeline` decision requires
both faster factor production and no loss of final enclosure quality. It is
therefore `false`: the recurrence saves transcendental calls, but factor
generation is already a small part of this path and the approximately `2.2x`
median transform widening is a real downstream cost.

The real Arb/FLINT completed-\(L\) consumer is also exercised as a protocol
KAT. The synthetic lattice fixture does not have completed-\(L\) source
semantics, and the consumer correctly rejects its raw phase-rotated values
when the imaginary rectangle misses zero. The KAT therefore applies an
explicit outward hull with complex zero **after** the raw CUDA output has
passed containment and independent MPFR replay. This makes the Arb pass
deliberately sign-indeterminate. The report exposes
`raw_CUDA_transform_consumed_without_broadening=false` and does not use the
Arb result to claim source usefulness. This tests the actual FLINT parsing,
root-artifact, gamma-factor, and completed-\(L\) machinery without disguising
synthetic values as analytic evidence.

Run the complete opt-in test with the pinned FLINT environment:

```bash
TG_RUN_DIRICHLET_RECURRENCE_DOWNSTREAM_KAT=1 \
PYTHONPATH="$PWD:/home/gersh/.local/lib/python3.12/site-packages" \
/tmp/tg-flint-venv/bin/python -m unittest -v \
  tests.test_tg_dirichlet_tmajor_recurrence_downstream
```

The complete two-modulus test took `303.065 s` on the development host on
2026-07-25. The normal suite runs the fast containment/endpoint attacks and
skips this five-minute hardware KAT unless the environment variable is set.
A persistent, inspectable report can instead be produced with:

```bash
PYTHONPATH="$PWD:/home/gersh/.local/lib/python3.12/site-packages" \
/tmp/tg-flint-venv/bin/python \
  tools/tg_dirichlet_tmajor_recurrence_downstream.py \
  --pretty /tmp/tg-recurrence-downstream
```

`--skip-arb-consumer` retains both real CUDA stages and the complete
independent MPFR transform replay when only enclosure and timing diagnostics
are wanted. It is recorded by a null `Arb_FLINT_consumer` report and is not
equivalent to the complete KAT.

The full 64-frame qualification artifact is `8,344` bytes. Its factor
rectangles alone occupy `2,048` bytes; the extra size is primarily the 63
standalone 96-byte multiplication witnesses. A production design must decide
whether those witnesses are retained per target, aggregated into a separately
authenticated audit sample, or regenerated by an independently measured
checker. That choice cannot be hidden behind the unchanged `TGDLTMB1` wire.

## Exact remaining boundary

Successful bounded replay proves the finite disk-arithmetic chain conditional
on the two seed rectangles. It does not prove:

- that MPFR or Arb implements Mathlib's complex power;
- the algebraic recurrence and seed realization in the live Lean theorem;
- a `TGDFREC1` byte parser and byte-to-typed-chain theorem in Lean;
- refinement from a compiled C++/CUDA/SASS implementation;
- compatibility with the existing direct-sidecar recipe or its identities;
- source-wide interval usefulness after Taylor composition and FFT;
- source-scale execution, independent replay, or attestation; or
- completed-\(L\) signs, zero isolation, Turing completeness, or Platt
  Theorem 7.1.

All reports therefore retain `external_atom_discharged=false`.
