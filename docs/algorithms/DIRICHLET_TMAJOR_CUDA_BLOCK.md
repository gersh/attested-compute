# Authenticated row-resident large-q CUDA block

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

`TGDLTMB1` is the bounded source component between the authenticated t-major
Hurwitz spool and the existing seeded large-\(q\) CUDA composition kernel. It
is a component of the Platt Theorem 7.1 campaign, not a zero or Turing
certificate.

## Direct source path

One artifact contains at most 64 consecutive authenticated 1-MiB Hurwitz rows
and every active modulus target for that block. Each row occurs once. The
target records contain only:

- the exact modulus, ordinate range, unit-group order, and value count;
- a directed binary64 enclosure of \(q^{-1/2-it}\) for each ordinate; and
- the exact-rational Taylor-tail radius for each ordinate.

CRT descriptors are reconstructed canonically from \(q\) by the CUDA
executable and are not transported.

The preferred `build-direct` path does not read a q-major `TGDLQB2` artifact
or a 56,981,100-line primitive-only manifest. It generates each factor with
directed MPFR at 192 bits, regenerates it at 256 bits, and requires containment.
It independently rederives the Taylor radius from
`derive_uniform_tail_bound`. The one source-wide displacement bound is

```text
1/2048 - 1/400000.
```

It covers the clipped \(r=1\) edge; every ordinary nearest-row displacement
is at most \(1/(2\cdot2048)\). The generated recipe binds the two
implementation modules and their exact digests. It records that full runtime
closure and attestation have not been captured.

The transitional `build` command remains as a differential oracle. It
authenticates every q-major `TGDLQB2`, validates its canonical descriptors,
requires every repeated lattice row to equal the spool row byte for byte, and
then removes those repetitions.

## Exact source accounting

For the fixed eight-lane, 2,000-block plan:

| input | exact bytes |
|---|---:|
| 127,988 rows plus row headers | `134,213,336,320` |
| 56,981,100 target headers | `6,837,732,000` |
| 3,637,613,167 directed factors and tails | `145,504,526,680` |
| block headers and footers | `864,000` |
| **TGDLTMB1 total** | **`286,556,459,000`** |
| separate recovery-seed artifact | `96,008,016` |
| **total including recovery seeds** | **`286,652,467,016`** |

This is \(144.522\times\) smaller than the former 41.414-TB t-major model,
which still repeated canonical descriptors, and \(18,078.128\times\) smaller
than the former 5.180-PB q-major seeded-input model. It is exact binary-input
accounting, not a runtime estimate.

This closes a storage/transport blocker, not the one-week campaign gate. The
primitive-only all-character transform model alone remains 3,043--3,087 GB10
GPU-hours (15.85--16.08 ideal days on eight equal GPUs), plus roughly 2.24
ideal days of current host plan preparation. H100 weighted throughput, composition
overlap, completed-\(L\)/zero work, replay, and exception rates are unmeasured.
Accordingly the repository still cannot justify either a one-week or a
USD-10,000 end-to-end claim.

```bash
python3 tools/tg_dirichlet_tmajor_cuda_block.py --pretty projection
python3 tools/tg_dirichlet_tmajor_cuda_block.py build-direct \
  /shared/source-contract.json \
  /shared/lane-0/spool.receipt.json \
  /shared/lane-0/block-0000.bin \
  /shared/lane-0/block-0000.receipt.json \
  --first-t-index 0 \
  --expected-contract-sha256 "$PINNED_CONTRACT_SHA256" \
  --expected-spool-receipt-sha256 "$PINNED_SPOOL_RECEIPT_SHA256"
```

`replay` streams the binary artifact, rechecks its exact q roster, row and
sidecar hashes, finite interval geometry, footer accounting, direct MPFR
bytes, higher-precision containment, and exact-rational tail bytes. A test
constructs a rehashed factor substitution with matching block digests and
receipt hashes; direct semantic replay still rejects it.

The 256-bit MPFR containment pass is a higher-precision replay of the same
MPFR implementation, not an independent library proof.  The bounded
qualification checker can additionally evaluate every factor in a small
block through pinned python-flint 0.9.0 / FLINT 3.6.0 at 384 bits and require
the stored MPFR rectangle to contain the independently produced Arb
rectangle.  It also rederives every stored direct-path Taylor radius from
exact rational arithmetic in a separate implementation.  Rehashed one-ULP
mutations of either a factor or a tail are rejected after all transport
digests have been repaired.

The factor producer retains one fixed 28-value MPFR workspace per precision
instead of initializing and clearing it at every ordinate.  For consecutive
ordinates of one modulus it also retains the directed `log(q)` and
`1/sqrt(q)` endpoints; a q change recomputes them.  Every ordinate-dependent
operation and rounding mode is unchanged.  Fixed hexadecimal known answers
before and after the changes are byte-identical, cache hits and q changes are
tested, and use after explicit close fails closed.

On 2026-07-25, seven bounded local 4,096-factor runs alternating `q=10001`
and `q=10002` on every 64-factor batch generated 192-bit enclosures and
checked 256-bit containment at a median 15,127.9 factors/s.  Alternating
forces the q-dependent cache to be rebuilt at the same per-target cadence as
the source builder, although `q=10002` itself is outside the later
primitive-only production roster. The current benchmark command chooses the
next active source modulus, `q=10003`, instead. The immediately preceding
allocating implementation
measured 6,323.2 factors/s on the same host and geometry.  The retained
implementation therefore gives a straight-line factor/tail-only projection
of 66.79 single-process hours or 0.209 ideal hours on 320 perfectly scaling
processes.
This excludes a second independent campaign replay and every cache, CUDA, FFT,
completed-\(L\), zero, I/O, and attestation cost; it is not an end-to-end or
H100 estimate.

```bash
python3 tools/tg_dirichlet_tmajor_cuda_block.py --pretty benchmark \
  --q 10001 --batch-count 64 --repetitions 64
```

The separate
[bounded factor-recurrence experiment](DIRICHLET_TMAJOR_FACTOR_RECURRENCE.md)
reduces 64 direct factor evaluations to one seed and one phase step per
precision, with exact-rational complex-disk certificates and an independent
Arb KAT.  Its bounded Python path is about `1.18x` faster than the
workspace-optimized direct MPFR baseline.  A real two-modulus, 64-row
CUDA-composition/all-character qualification now confirms containment but
measures approximately `2.2x` median widening after the transform.  It still
has no source-scale usefulness measurement, compiled refinement, or Lean
byte-to-seed realization.  It therefore has not replaced this direct recipe
or changed any `TGDLTMB1` identity.

## CUDA execution

`sparkinterval-tg-dirichlet-largeq-seeded --tmajor-block` performs a complete
CPU preflight before emitting stdout, uploads the lattice block once, derives
canonical descriptors for each target, and invokes the existing directed
seeded composition kernel. It emits the existing self-delimiting `TGDAFFI1`
frames and publishes an immutable canonical summary binding the complete
output-stream SHA-256.

The seed loader now hashes the bytes it actually parses, rather than relying
only on a hash from an earlier file open.  The row-resident execution pass
likewise hashes every block byte it actually consumes and publishes no
summary unless that digest equals the external input pin.  These checks close
path-swap gaps between preflight and execution.  As before, callers must stage
stdout and discard it when the process exits unsuccessfully; only a validated
summary is an admissible output identity.

`validate-arithmetic` strengthens summary typing for bounded qualification
runs.  It authenticates the complete block, seed, summary, and output streams,
then chooses deterministic endpoint-and-interior values from every target.
For those values it independently emulates each CUDA `__dadd_rd/ru`,
`__dsub_rd/ru`, `__dmul_rd/ru`, and `__ddiv_rd/ru` operation by computing an
exact rational intermediate and tightly rounding it to binary64.  It
reconstructs the Taylor polynomial and the seeded finite-recovery recurrence
and requires exact endpoint equality with CUDA.  A one-ULP output mutation
with a freshly supplied output hash is rejected by this arithmetic check.
The execution-summary parser also uses strict JSON integer typing, so values
such as `true` can no longer impersonate the integer upload count `1`.

```bash
python3 tools/tg_dirichlet_tmajor_cuda_block.py --pretty \
  validate-arithmetic \
  block.summary.json block.bin block.receipt.json seeds.bin output.tgdaffi \
  --expected-summary-sha256 "$SUMMARY_SHA256" \
  --expected-receipt-sha256 "$RECEIPT_SHA256" \
  --expected-seed-artifact-sha256 "$SEED_SHA256" \
  --maximum-targets 8 \
  --maximum-values-per-target 64

# Optional independent factor containment in the pinned FLINT environment:
PYTHONPATH=. .venv-tg-flint/bin/python \
  tools/tg_dirichlet_tmajor_cuda_block.py --pretty \
  validate-arithmetic \
  block.summary.json block.bin block.receipt.json seeds.bin output.tgdaffi \
  --expected-summary-sha256 "$SUMMARY_SHA256" \
  --expected-receipt-sha256 "$RECEIPT_SHA256" \
  --expected-seed-artifact-sha256 "$SEED_SHA256" \
  --independent-arb-factor-precision-bits 384
```

The local CUDA KAT:

- produced byte-identical output to the old q-major seeded kernel for two
  moduli and two rows;
- executed the direct-MPFR input mode;
- reported exactly one lattice H2D upload; and
- rejected a wrong externally pinned input digest before stdout or summary
  publication;
- rejected an internally valid seed artifact substituted after the initial
  path hash but before parsing;
- rejected a lattice row substituted after block preflight even when the
  original pinned pathname was restored before the execution check, and
  published no summary;
- matched 128 deterministically spread values through the exact-rational
  directed-arithmetic checker and rejected a rehashed one-ULP result
  mutation; and
- enclosed all four direct MPFR factors in an independent 384-bit Arb replay.

This is a GB10 component KAT, not an H100 measurement, SASS attestation, or
source-scale run.  The arithmetic replay samples values rather than replaying
the full output, and the factor KAT covers only this two-modulus block.  The
repository's existing restricted SASS slice covers one legacy unseeded
addback pair; it does not certify the seeded recurrence kernel, the new host
parsing, upload residency, or execution summary.  The exact-rational checker
also does not prove that the compiled SASS implements the reviewed CUDA
source or that the seed rectangles contain the analytic recurrence values.

## Exact remaining boundary

The component ends at a hash-bound stream of residue-domain `TGDAFFI1`
frames. It does not:

- keep all-character transform plans resident across the mixed-q stream;
- emit or admit the existing typed FFT pipeline bundles;
- import or export authenticated completed-\(L\) sign/zero state;
- independently replay all discarded CUDA composition arithmetic;
- run the bounded arithmetic replay over the source-scale output or prove the
  CUDA-to-SASS refinement (the new checker only qualifies bounded samples);
- populate the 1,000 lattice-cache shards or the root catalog;
- prove source-wide interval usefulness or execute exception/refinement
  policy;
- prove interpolation, multiplicity-preserving zero isolation, or the
  corrected reflected paired-Turing closure;
- capture complete Python/MPFR/FLINT/GMP/CUDA runtime identity or attestation;
  or
- run the source campaign or discharge Platt's Theorem 7.1.

Every artifact, replay, and execution summary keeps those claims and
`external_atom_discharged=false`.
