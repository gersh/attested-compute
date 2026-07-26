# Conditional H100/CPU large-q Dirichlet lattice stage

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This is a project-owned, clean-room implementation of one finite stage in
D. J. Platt, [*Numerical computations concerning the
GRH*](https://arxiv.org/abs/1305.3087v1), Section 4.1 and Lemma 4.2. It is
useful production infrastructure, but it does **not** verify Platt's Theorem
7.1 by itself.

The current sign-quadrant multiplication fast path and its exact/MPFR,
edge-case, benchmark, and sanitizer qualification are recorded in
[`DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md`](DIRICHLET_LARGEQ_FAST_PATH_QUALIFICATION.md).

## Exact scope

The paper constructs, for a fixed ordinate `t`, the Hurwitz-zeta lattice

```text
zeta_M(1/2 + it + c, r/D),  r=1,...,D,  c=0,...,N,
```

with `D=2048` and `N=15`. Thus there are 2048 rows and 16 columns. For every
unit residue `a mod q`, this stage chooses the nearest canonical `r/D`, checks
the strict precondition `|a/q-r/D| < r/D`, and evaluates the sixteen-term
natural interval expression

```text
sum k=0..15 of
  (r/D-a/q)^k * zeta_M(s+k,r/D) * product(j=0..k-1, s+j) / k!
```

at `s=1/2+it`. It finally widens both real and imaginary components by the
supplied nonnegative tail radius. Integer ratios are converted with directed
division and every binary64 add, subtract, multiply, and divide uses the CUDA
directed-rounding intrinsic. Fused multiply-add is disabled.

The input contract is conditional. A separate, still-missing producer must
prove that every lattice rectangle encloses the named Hurwitz value and that
every supplied radius bounds the omitted Taylor tail. The receipt records
these facts as unproved by this stage.

## Implementations and certificate boundary

- `gpu/platform/h100/h100_tg_dirichlet_lattice_kernel.cu` is the parallel
  CUDA implementation. The strict H100 target refuses any device other than a
  compute-capability-9.0 H100.
- `reference/tg_dirichlet_lattice_exact.cpp` is the independent CPU reference.
  It decodes each binary64 endpoint exactly as a dyadic rational, evaluates
  the natural interval expression with unbounded integers, and either emits
  an outward-rounded CPU result or verifies containment of GPU output.
- `tg_verifier/dirichlet_lattice_stage.py` reconstructs the exact source-stage
  work schedule, provides fixed eight-way ordinate shards, and publishes
  immutable batch receipts.
- `tools/tg_dirichlet_lattice_stage.py` is the operator CLI.

An immutable receipt hashes copied runner, checker, input, output, and optional
external lattice certificate. It separately reports successful exact
arithmetic replay and the absent lattice, DFT, and Turing decisions. A
synthetic receipt cannot be relabeled as production, and neither receipt form
sets `external_atom_discharged`.

Build and test the native GB10 targets with:

```bash
cmake -S . -B build/dirichlet-lattice \
  -DSPARKINTERVAL_BOOST_INCLUDE_DIR=/path/to/boost/include
cmake --build build/dirichlet-lattice --target \
  sparkinterval-tg-dirichlet-lattice \
  sparkinterval-tg-dirichlet-lattice-exact -j
ctest --test-dir build/dirichlet-lattice \
  -R tg_dirichlet_lattice_known_answers --output-on-failure
```

For Azure H100, configure `-DSPARKINTERVAL_BUILD_H100_NATIVE=ON` and use
`sparkinterval-h100-tg-dirichlet-lattice`. The ordinary target is architecture
native and is intended for local conformance and benchmarking.

Inspect the fixed plan and make a labeled conformance artifact:

```bash
python3 tools/tg_dirichlet_lattice_stage.py --pretty plan
python3 tools/tg_dirichlet_lattice_stage.py synthetic-input /tmp/input.bin \
  --q-start 10001 --q-stop 10250 --t-index 0 --max-items 1000000
python3 tools/tg_dirichlet_lattice_stage.py --pretty run-batch /tmp/receipt \
  --input /tmp/input.bin \
  --runner build/dirichlet-lattice/sparkinterval-tg-dirichlet-lattice \
  --checker build/dirichlet-lattice/sparkinterval-tg-dirichlet-lattice-exact \
  --synthetic-lattice
```

The synthetic lattice contains exactly representable dyadic test values, not
Hurwitz-zeta values. It tests the format, kernel, exact checker, hashes, and
fail-closed receipt semantics only.

## Fixed source-stage shards

The large-q plan uses `10001 <= q <= 400000`, positive ordinates `t=5k/64`
within the parity-dependent source height, and every unit residue needed by
the later DFT. The plan hash is
`88035e89402c605b1880eda9541423c07358e6d729b2c832333778e64b01c445`.

| H100 shard | `k` half-open range | residue reconstructions |
|---:|---:|---:|
| 0 | `[0,841)` | 40,875,804,061,984 |
| 1 | `[841,1682)` | 40,875,804,061,984 |
| 2 | `[1682,2524)` | 40,924,407,871,808 |
| 3 | `[2524,3365)` | 40,875,804,061,984 |
| 4 | `[3365,4317)` | 40,879,198,699,956 |
| 5 | `[4317,5840)` | 40,880,549,175,606 |
| 6 | `[5840,10300)` | 40,892,958,330,422 |
| 7 | `[10300,127988)` | 40,884,680,019,264 |

Together they cover 327,089,206,283,008 residue reconstructions, or
5,233,427,300,528,128 complex Taylor terms. They are work shards for this
conditional stage, not certificates of zero coverage. The count covers the
main positive grid only; padding, upsampling, and Turing windows are excluded.

The standalone binary protocol is intentionally a reviewable batch interface,
not the final dataflow. Materializing every explicit request would require
about 7.85 PB and materializing every 48-byte result about 15.70 PB. A complete
large-q engine must generate compact requests on device and stream or fuse
these values directly into the unit-group DFT. The follow-on
[compact fused character stage](DIRICHLET_FUSED_CHARACTER_STAGE.md) now does
this for selected DFT coefficients and supplies an exact exception/KAT oracle;
the separate
[all-character stage](DIRICHLET_ALL_CHARACTER_FFT_STAGE.md) now supplies the
quasi-linear CRT/Bluestein interval transform. Persistent fusion between the
two stages and the completed-value consumer is still absent. The kernel-only
timing below is therefore an arithmetic component measurement, not an I/O or
atom plan.

## Measured performance and honest ETA boundary

On the local NVIDIA GB10, the July 25 sign-quadrant implementation has a
seven-run median source-shaped rate of about:

```text
91.80 million residue reconstructions/second
1.469 billion complex Taylor terms/second
```

The complete stage is about 41.2 single-GB10 days, or 123.7 ideal wall hours
on eight equal GPUs. There is no local H100 measurement. The report therefore
uses a 1x--14.3x sensitivity, where 14.3 is only the H100-NVL/DGX-Spark
memory-bandwidth ratio: **8.65--123.7 wall hours on eight H100s**. A
provisional 5x--10x engineering band is 12.4--24.7 hours. Kernel launches, seed
generation, transfers, FFTs, zero isolation, attestation, and retries are
excluded.

The exact CPU checker verified 10,000 GPU rows in 1.65 seconds on one local
core. It is therefore a conformance oracle, not a feasible second full replay
of 327 trillion rows. A source run would rely on the separately reviewed and
attested GPU executable for this stage, with exact bounded conformance checks.

Platt's approximately 400,000 historical core-hours describe the entire 2013
calculation. They are not contradicted by, and must not be compared directly
to, the stage-only H100 projection above.

## What still prevents a Theorem 7.1 producer

The existing rigorous FLINT/Arb contour backend remains the fail-closed
full-semantics route. It is unscaled. Certified lattice cells, an exact-
rational tail, finite recovery, the all-character transform, the small-`q`
formulas, and conditional postprocessing now exist as separate components. A
practical replacement still needs:

1. persistent source-scale composition of Taylor output, `q^(-s)`, finite
   recovery, the all-character transform, and completed-value/zero consumers;
2. a production batched small-`q` FFT and economical independent replay;
3. a uniform Whittaker--Shannon error proof and source exception/window policy;
4. theorem-level review and Lean realization of the corrected reflected
   paired-Turing upper bound;
5. a completed authenticated run and independently auditable closure; and
6. its Lean realization theorem.

Until those items exist and a complete authenticated run succeeds,
`platt-dirichlet-theorem-7-1` remains an external atom.
