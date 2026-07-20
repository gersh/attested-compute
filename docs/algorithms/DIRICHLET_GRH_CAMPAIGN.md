# Platt Theorem 7.1 full-source campaign boundary

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This workflow schedules the exact finite domain in D. J. Platt,
[*Numerical computations concerning the GRH*](https://arxiv.org/abs/1305.3087v1),
Theorem 7.1. It deliberately distinguishes three different accomplishments:

1. `tools/run_grh_poc.py` and `gpu/src/grh_lambda_poc.cu` already provide the
   repository's concrete, directed-interval completed-
   `L` evaluator and critical-line bracket producer for moderate ordinates.
   Its bundle checker binds every endpoint to recorded GPU output. Its
   Turing comparison is numeric sanity only, and binary64 interval widths make
   the direct method unsuitable at the largest source heights.
2. `tg_verifier/dirichlet_campaign.py` now supplies exact, bounded-memory
   enumeration of every primitive character, exact source heights, compact
   chunk requests, atomic resume, hash chaining, and complete artifact replay
   through `q = 400000`.
3. `tools/tg_dirichlet_flint_backend.py` is a concrete, rigorous but
   deliberately unscaled FLINT/Arb reference producer and checker. It uses a
   certified argument-principle winding count, not the POC's numeric Turing
   estimate. It accepts canonical source-height requests, but it is orders of
   magnitude slower than Platt's lattice/FFT algorithms and has not been
   benchmarked at the source scale.

Thus both the control plane and a literal reference analytic path are
full-source capable. A practical high-height engine remains missing. Neither
a completed external FLINT campaign nor its checker receipt supplies the
still-missing Lean realization theorem.

## Exact source schedule

For each conductor `q`, the source height is represented as a reduced exact
rational:

```text
q even: max(100000000/q, 200 + 75000000/q)
q odd:  max(100000000/q, 200 + 37500000/q)
```

The range is the closed symmetric ordinate interval `[-T_q,T_q]`, and zeros
must be counted with multiplicity. The canonical CRT enumeration uses:

- for odd `p^e`, the least primitive root modulo `p^e`; at `e=1`, exponents
  `1,...,p-2`, and at `e>=2`, all exponents not divisible by `p`;
- for modulus `4`, exponent `1` against generator `3`;
- for `2^e`, `e>=3`, generators `-1` and `5`, with the exponent of `5` odd;
- mixed-radix lexicographic order across increasing prime powers.

Each descriptor also contains the corresponding Conrey number, so a backend
can construct the same character as `python-flint`'s
`dirichlet_char(q, number)`. The mapping was cross-checked against pinned
python-flint 0.9.0 / FLINT 3.6.0 for every conductor through 500.

Platt explicitly separates `q=1` as Riemann zeta in the introduction and
reports `29,565,923,837` L-functions for the Dirichlet-GRH computation. The
paper-computation schedule therefore covers `2 <= q <= 400000` and reproduces
that exact count. The literal Lean atom also quantifies over `q=1`; finishing
it requires the separate Riemann-zeta statement through height `10^8`. The
project's `platt-trudgian-rh-3e12` atom is much stronger in height and is the
recorded prerequisite for that one case.

There are no primitive characters at a conductor congruent to `2 mod 4`; the
schedule commits those zero rows rather than silently skipping an unexplained
gap. The full paper-computation schedule commitment is:

```text
074a34d0b0fe4024781efa878e82601a1139628cc4144f90875d1d090f22f8fc
```

Inspect it without any analytic backend:

```bash
python3 tools/tg_dirichlet_campaign.py --pretty capability
python3 tools/tg_dirichlet_campaign.py --pretty schedule
python3 tools/tg_dirichlet_campaign.py --pretty modulus 400000
python3 tools/tg_dirichlet_campaign.py --pretty describe --q 16 --ordinal 0
```

## External producer/checker protocol

Campaign initialization copies and hashes two self-contained executables. A
production deployment should make them independently implemented binaries and
should separately preserve their compiler, library closure, source revision,
and build log. The campaign records whether their bytes differ, but does not
mistake differing hashes for a proof of independence.

For a Python backend, the copied script hash does not pin the interpreter or
shared-library closure. The reference certificate records and enforces
python-flint `0.9.0`, FLINT `3.6.0`, and FLINT release `30600`, and a fresh
checker must see the same versions. A release-grade run should additionally
retain a lockfile/container digest and hashes of the Python executable and
loaded FLINT/GMP/MPFR libraries.

The producer handshake is:

```text
PRODUCER protocol-version
# stdout, exactly:
sparkinterval.dirichlet-grh-producer.v1
```

It is then invoked without a shell:

```text
PRODUCER produce --request REQUEST.json --output RESULT.json \
  --artifact-root PAYLOAD_DIRECTORY
```

`REQUEST.json` compactly names one or more conductor/character-ordinal
segments. It includes each factorization model, exact height, closed symmetric
range, global range, and hashes of both the plan and compact task set.
`RESULT.json` is canonical JSON of kind
`sparkinterval.tg.dirichlet_campaign.external_result.v1`; it binds the exact
request and a sorted manifest of regular payload files by SHA-256 and byte
length. Large zero/bracket/count data belongs in those payloads, not in the
control JSON.

The checker handshake is:

```text
CHECKER protocol-version
# stdout, exactly:
sparkinterval.dirichlet-grh-checker.v1
```

It is invoked as:

```text
CHECKER verify --request REQUEST.json --result RESULT.json \
  --artifact-root PAYLOAD_DIRECTORY --receipt CHECKER-RECEIPT.json
```

The canonical receipt must bind the request and result hashes and affirm all
of the following separately:

- exact coverage of every requested canonical primitive character;
- the exact source height and its closed symmetric endpoint convention;
- rigorous raw-`L(s,chi)` contour and Hardy-`Z` enclosures;
- a zero-free critical-strip contour boundary;
- a multiplicity-preserving rigorous Turing or argument-principle count; and
- equality of that total count with the isolated critical-line count.

Any false or omitted field fails closed. In particular, the
`turing_consistent` field emitted by `run_grh_poc.py` cannot satisfy this
contract. Internal replay authenticates this as a statement by the pinned
checker; it does not independently redo the analytic proof.

## Resumable run

With conforming production executables:

```bash
python3 tools/tg_dirichlet_campaign.py --pretty init \
  build/tg/platt-dirichlet-7-1 \
  --producer /absolute/path/to/rigorous-producer \
  --checker /absolute/path/to/independent-rigorous-checker \
  --characters-per-chunk 1000000

python3 tools/tg_dirichlet_campaign.py --pretty run \
  build/tg/platt-dirichlet-7-1 --max-chunks 10

python3 tools/tg_dirichlet_campaign.py --pretty verify \
  build/tg/platt-dirichlet-7-1 --rerun-checker

python3 tools/tg_dirichlet_campaign.py --pretty run \
  build/tg/platt-dirichlet-7-1
python3 tools/tg_dirichlet_campaign.py --pretty finalize \
  build/tg/platt-dirichlet-7-1
```

Every resume first reconstructs the canonical request sequence from the root,
rehashes all payloads, validates all external receipts, and recomputes the
chain. Chunk publication is an atomic directory rename. `--max-chunks` is a
pause control only; it never changes the source profile or turns partial
coverage into full coverage.

For integration testing, `--mode bounded_sample --q-start A --q-stop B` makes
the narrowed domain explicit in both plan and final receipt. Full-source mode
refuses any range other than the exact paper-computation range `[2,400000]`
and records the separate `q=1` zeta prerequisite.

## Concrete FLINT/Arb reference backend

For one primitive nonprincipal character, the reference backend evaluates
`L(s,chi)` on adaptive complex boxes covering the counterclockwise rectangle

```text
[-1/2, 3/2] x [-T_q, T_q].
```

Each image box must lie wholly in the open right, upper, left, or lower
half-plane. The resulting certified octant transitions give the contour's
winding number, hence the number of enclosed zeros with multiplicity. There
are no poles for a primitive nonprincipal `L`-function. The only trivial zero
inside this rectangle is the simple zero at `s=0` for an even character; the
backend subtracts exactly that one. It then scans FLINT's real Hardy `Z`
function with exact rational ordinates. The actual contour and scan use the
slightly stronger height `T_q + 1/64`, so a zero exactly at the source cutoff
is interior rather than an argument-principle boundary case. Equality between the remaining
multiplicity count and the number of disjoint strict sign-change brackets
forces every nontrivial zero in the closed source-height strip onto the
critical line. A contour zero, unresolved interval, nonintegral winding,
missing bracket, or exhausted precision/subdivision limit fails closed.

Pinned python-flint 0.9.0 / FLINT 3.6.0 tests give:

| Character | Height | Contour count | Trivial correction | Hardy brackets |
|---|---:|---:|---:|---:|
| primitive mod 3, Conrey 2 | 10 | 2 | 0 | 2 |
| primitive mod 4, Conrey 3 | 10 | 2 | 0 | 2 |
| even primitive mod 5, Conrey 4 | 5 | 1 | 1 | 0 |

Run those tests with the pinned environment:

```bash
.venv-tg-flint/bin/python -m unittest -v \
  tests.test_tg_dirichlet_flint_backend
```

The producer and checker protocols can both use the reference file. The
campaign copies it twice under role-specific names and invokes Python sources
with the same pinned interpreter used by the campaign CLI. Their hashes are
then equal, so receipts correctly say the checker is not an independent
implementation; the checker nevertheless performs a fresh complete replay.

The single empty-workspace source command also makes the formally quantified
`q=1` case explicit. It first validates a completed stronger
`platt-trudgian-rh-3e12` zeta campaign, pins that campaign/final identity, then
initializes or resumes every `q=2..400000` task with the reference backend and
finalizes only after exact coverage:

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_campaign.py --pretty source \
  build/tg/platt-dirichlet-7-1-source \
  --q1-zeta-final build/tg/zeta-rh-3000175332800/final.json
```

The command exits nonzero on a partial run or any failed external decision.
`--max-chunks N` deliberately produces a resumable prefix and therefore also
exits nonzero. This source command is executable in principle, not a runtime
claim: the direct Arb contour method may be vastly slower than Platt's
400,000-core-hour optimized computation.

After copying or resuming artifacts, recheck the complete composite boundary
(including the supplied q=1 campaign, rather than only the q>=2 hash chain):

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_campaign.py verify-source \
  build/tg/platt-dirichlet-7-1-source \
  --q1-zeta-final build/tg/zeta-rh-3000175332800/final.json
```

This structural command does not freshly rerun trillions of FLINT evaluations;
fresh q>=2 checker replay remains available chunk by chunk.

The source command removes the reference backend's default ten-million-box
ceiling and raises the precision/depth/refinement limits. These immutable
resume parameters are stored beside the q=1 requirement. Operators can adjust
them explicitly with `--reference-max-precision`,
`--reference-max-contour-depth`,
`--reference-max-contour-evaluations` (`0` means unlimited), and
`--reference-max-grid-refinements`; changing one on resume fails closed.

## Remaining implementation work

The principal remaining computation work is a practical implementation of
Platt's high-height lattice/Taylor, unit-group FFT, and Turing pipeline, plus
an independently implemented checker. FLINT's built-in certified Turing and
indexed-zero facilities are for Riemann zeta, not a drop-in Dirichlet
completeness proof. The reference backend avoids that gap with a general
zero-free-contour argument, but its interval subdivision cost is unsuitable
for claiming a feasible source run. On the formal side, Lean still needs the
theorems connecting FLINT's raw-`L` contour/Hardy-Z computations and the
external multiplicity count to `DirichletCharacter.LFunction`.
