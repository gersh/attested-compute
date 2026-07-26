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

## Implemented optimized components

The repository now implements substantially more than the original direct
FLINT fallback, while retaining a fail-closed boundary around their
composition:

- [DIRICHLET_LATTICE_CERTIFICATES.md](DIRICHLET_LATTICE_CERTIFICATES.md)
  generates pinned-Arb `D=2048`, `c=0..15` Hurwitz rectangles, finite addback,
  and a project-derived exact-rational Taylor-tail certificate;
- [DIRICHLET_LATTICE_H100_STAGE.md](DIRICHLET_LATTICE_H100_STAGE.md) performs
  every sixteen-term large-`q` Taylor reconstruction with directed CUDA
  arithmetic and an exact independent checker;
- [DIRICHLET_RESIDUE_COMPOSITION.md](DIRICHLET_RESIDUE_COMPOSITION.md) validates
  the complete lattice/replay chain, encloses `q^(-s)` with MPFR, and emits
  canonical transform frames through a persistent bounded adapter;
- [DIRICHLET_LARGEQ_BATCH_STAGE.md](DIRICHLET_LARGEQ_BATCH_STAGE.md) alternatively
  fuses Taylor reconstruction and residue composition for up to 64 ordinates
  in one directed CUDA kernel with no device transcendental;
- [DIRICHLET_RECOVERY_SEEDED_STAGE.md](DIRICHLET_RECOVERY_SEEDED_STAGE.md)
  replaces the 13.084-PB per-value finite-recovery/tail stream by one fully
  Arb-replayed 96-MB recurrence-seed artifact and a compact fused CUDA format.
  The exact logical input falls to 5.180 PB, with no device transcendental;
- [DIRICHLET_ALL_CHARACTER_FFT_STAGE.md](DIRICHLET_ALL_CHARACTER_FFT_STAGE.md)
  implements the quasi-linear all-character CRT/Bluestein directed interval
  transform, canonical residue/Conrey adapters, persistent per-modulus plans,
  and 192-bit MPFR replay;
- [DIRICHLET_BOOKER_SMALLQ_STAGE.md](DIRICHLET_BOOKER_SMALLQ_STAGE.md)
  implements the complete small-`q` Gaussian formulas and explicit tails, an
  untrusted midpoint accelerator, and a separate v2 directed-disk finite-sum
  and persistent DFT engine whose seeds are independently checked with Arb.
  Its q-level semantic reducer separately replays both parity time-tail
  controls and retains one strict-sign-or-ambiguity code for every bound
  character/sample coordinate;
- [DIRICHLET_ROOT_NUMBER_STAGE.md](DIRICHLET_ROOT_NUMBER_STAGE.md) constructs
  primitive-only, convention-bound all-character Gauss/root-number artifacts
  and supplies them to the completed-L consumer without quadratic work;
- [DIRICHLET_STREAM_ZERO_CONSUMER.md](DIRICHLET_STREAM_ZERO_CONSUMER.md)
  consumes persistent all-character frames without materializing them,
  reconstructs primitive identities, forms completed values, and retains
  multiplicity-lower-bound sign brackets in compact hash-bound receipts;
- [DIRICHLET_ZERO_CLOSURE_STAGE.md](DIRICHLET_ZERO_CLOSURE_STAGE.md) implements
  completed-value reconstruction from interval `L`, finite sinc interpolation,
  separate Weiss/tail budgets, direct-Arb exception closure, multiplicity-
  preserving zero lists, and conjugate-paired Turing arithmetic;
- [DIRICHLET_FACTOR8_POSTPROCESS.md](DIRICHLET_FACTOR8_POSTPROCESS.md) isolates
  the routine factor-eight grid into a directed forty-tap CUDA convolution and
  two-bit sign reducer. Its 280 source coefficients have a complete fresh Arb
  replay, and bounded strict signs have an independent exact-rational endpoint
  checker. It does not prove the uniform interpolation allowance or upstream
  completed values;
- [DIRICHLET_LARGEQ_PIPELINE.md](DIRICHLET_LARGEQ_PIPELINE.md) launches one
  back-pressured persistent composition/FFT/completed-L graph per q shard and
  verifies all cross-stage stream hashes and counts;
- [DIRICHLET_FFT_PIPELINE_RECEIPT_BUNDLE.md](DIRICHLET_FFT_PIPELINE_RECEIPT_BUNDLE.md)
  reparses every retained artifact and binds one pipeline receipt to one exact
  fixed-q source-supervisor FFT target without claiming replay of discarded
  stream arithmetic;
- [DIRICHLET_ROOT_CATALOG.md](DIRICHLET_ROOT_CATALOG.md) parses, receipt-binds,
  and commits
  the exact monotone 292,500-modulus `TGDRNRO1` artifact set; and
- [DIRICHLET_SOURCE_SUPERVISOR.md](DIRICHLET_SOURCE_SUPERVISOR.md) binds the
  cache, fresh recovery replay, root catalog, and the retained legacy-V1
  eight-lane q-tile assignment and 76,770,217 fixed-q FFT batch roster; it
  must be versioned to the primitive-only V2 roster before production use; and
- [DIRICHLET_TMAJOR_SPOOL.md](DIRICHLET_TMAJOR_SPOOL.md) stores each
  authenticated lane row once and emits the exact hash-bound fixed-q run
  roster without petabyte-scale row copying; and
- [DIRICHLET_TMAJOR_CUDA_BLOCK.md](DIRICHLET_TMAJOR_CUDA_BLOCK.md) directly
  generates replayed MPFR factors and exact-rational tails, packages the
  authenticated rows into a 286,556,459,000-byte primitive-only V2
  source-wide `TGDLTMB1`
  model, and runs the seeded composition kernel after one row-block upload;
  and
- [DIRICHLET_FUSED_CHARACTER_STAGE.md](DIRICHLET_FUSED_CHARACTER_STAGE.md)
  remains a useful sparse selected-character exception/audit oracle.

Every component has explicit source-work counts, KATs, and
`external_atom_discharged=false`.  The persistent graph removes per-batch
process creation and never materializes the primitive-only V2 8.534 PB
transformed
rectangle stream.  The fused large-q alternative reduces the main-grid kernel
count from `3,637,613,167` to `56,981,100`. The retained V1 seeded-recovery
model reduces its literal certified input from 18.264 PB to 5.180 PB. The
separate t-major
cache specifies and authenticates the 125-GiB unique lattice payload. The
former model still repeated canonical descriptor tables and totaled 41.414
TB. The direct `TGDLTMB1` path reconstructs those descriptors, eliminates
q-major source frames, and makes the primitive-only V2 binary input
286.556 GB (286.652 GB including recovery seeds), but the cache is not
populated and no
source-scale/H100 run exists.

## Remaining production and analytic work

The optimized component graph is not yet a conforming end-to-end proof of the
atom.  It still needs:

1. populate the implemented authenticated t-major Hurwitz cache and root
   catalog, then connect the implemented row-resident CUDA component's
   mixed-q `TGDAFFI1` output to persistent all-character FFT, typed-bundle
   admission, completed-\(L\), and authenticated zero-state import/export.
   The direct component and its independent factor/tail replay are bounded and
   tested, but no source cache, H100 measurement, source-scale run, or
   attestation exists;
2. source-campaign integration and a measured H100 deployment of the
   implemented small-`q` device classifier and semantic reducer. Its complete
   even/odd time-tail controls and ordered two-bit sign/ambiguity output are
   specified and checked; device mode removes the 226.996-TB raw-disk transfer
   for this component, but only a local synthetic q-level differential run
   exists. A source-wide proof that the accumulated/scaled directed disks
   remain useful for zero isolation is also still required;
3. a uniform proof of the accepted manuscript's interpolation error over every
   source case, including an explicit replacement for its printed "large
   enough" condition;
4. a source-wide exception and window-shift policy;
5. theorem-level review of the corrected reflected Turing upper bound.  The
   executable path now uses Booker upper-at-`+t0` minus lower-at-`-t0`, reflects
   the negative window to `bar-chi`, includes the source `+2/pi`, and scales
   Phi by `1/(h*pi)` but staircase/S terms by `1/h`.  The literal common-
   denominator display still fails the `q=3` KAT, and the corrected candidate
   remains `production_accept=false` until its analytic/Lean bridge exists; and
6. a completed source run, independent replay, and Lean realization theorem.

The direct argument-principle FLINT backend remains a rigorous full-domain
fallback and does not rely on the disputed Turing display, but its subdivision
cost is unsuitable for a practical source-scale claim.  FLINT's indexed-zeta
facilities are not a drop-in Dirichlet completeness proof.  On the formal
side, Lean still needs the theorem connecting whichever retained analytic
certificate is selected to `DirichletCharacter.LFunction`.

The final conditional receipt boundary is already closed. The Azure
CPU/SEV-SNP invocation `plattDirichletTheorem71ProductionV1` accepts `true`
only with the exact universal even/odd `PlattTheorem71SourceEvidence` and then
derives the expanded source proposition by an ordinary Lean theorem; `false`
proves nothing. This prevents a future scheduler digest or partial run from
being promoted by itself. There is not yet a source-evidence materializer,
completed campaign, or successful receipt, so the Azure semantic binding
remains disabled/null.
