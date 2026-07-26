# Compact fused Dirichlet character stage

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This is a clean-room follow-on to the conditional Taylor stage described in
[DIRICHLET_LATTICE_H100_STAGE.md](DIRICHLET_LATTICE_H100_STAGE.md). It makes one
important dataflow step concrete: selected coefficients of the unit-group DFT
can be computed without ever writing one request and one result for every unit
residue. It is useful as an exception path, an audit oracle, and a known-answer
oracle for a future FFT. It is **not** Platt's all-character FFT and does not
verify Theorem 7.1.

## Exact computation

At one ordinate `s=1/2+it`, an input contains one shared `2048 x 16` Hurwitz
lattice and any number of strictly ordered modulus tasks. For each `q`, the
host programs independently reconstruct the canonical decomposition used in
Platt's Lemma 4.1:

- an odd prime power contributes its least primitive root and a cyclic factor
  of order `phi(p^e)`;
- `U(4)` contributes the generator `3` of order `2`;
- `U(2^e)`, `e>2`, contributes the `-1` and `5` factors of orders `2` and
  `2^(e-2)`;
- the prime-power factors are combined by explicit CRT cofactors and inverses.

For every mixed-radix unit-group index, the CUDA kernel generates the residue
`a` on device, chooses the canonical nearest row `r/D`, and evaluates the
same directed sixteen-term Taylor interval as the earlier lattice kernel. For
a requested frequency tuple `k`, it then evaluates the character weight

```text
chi_k(a(x)) = product_j root_j ^ (k_j x_j mod order_j)
```

and reduces directly to

```text
sum over a in U(Z/qZ) of chi_k(a) * zeta_M(s,a/q).
```

This is exactly one selected coefficient in the sign convention required by
the Hurwitz identity for `L(s,chi)`. The stage stops before restoring the
finite terms removed from `zeta_M` and before multiplying by `q^(-s)` or the
completed-`L` factors.

One binary input can share its lattice across multiple moduli. It contains
only modulus/factor/component descriptors and selected character frequencies;
there is no per-residue request array. Its output contains one 48-byte interval
row per selected character; there is no per-residue output array. Thus the
stage avoids the earlier full-source standalone-I/O lower bounds of about
7.85 PB of requests and 15.70 PB of results when it is used for sparse selected
coefficients. Requesting all characters would again create a petabyte-scale
output stream; a production FFT must fuse its coefficients into downstream
sign/zero state. A resident scheduler would also keep each ordinate's lattice
on the device while it streams modulus descriptors.

## Independent finite-arithmetic check

`reference/tg_dirichlet_fused_exact.cpp` independently factors each modulus,
finds the canonical generators, validates every CRT descriptor and mixed-radix
frequency, decodes every binary64 endpoint as an exact dyadic rational, and
replays the complete natural interval expression with unbounded integers. It
either produces an outward-rounded reference file or verifies containment of
the CUDA output.

The known-answer test uses `q=5,8,15` and all sixteen characters. These cases
exercise a cyclic order-four group, the `C2 x C2` decomposition of `U(8)`, and
a two-prime CRT product. Every root used there is exactly one of `1,-1,i,-i`,
so the KAT has no hidden trigonometric-library premise. It also confirms that
a forged non-finite endpoint is rejected.

Build and run the native test with:

```bash
cmake --build build/tg-production-kat --target \
  sparkinterval-tg-dirichlet-fused \
  sparkinterval-tg-dirichlet-fused-exact -j
ctest --test-dir build/tg-production-kat \
  -R tg_dirichlet_fused_known_answers --output-on-failure
```

The strict Azure target is `sparkinterval-h100-tg-dirichlet-fused`. It is
compiled for `sm_90` and refuses to run unless the device reports an H100 with
compute capability 9.0.

For a synthetic inspection batch:

```bash
python3 tools/tg_dirichlet_fused_stage.py --pretty capability
python3 tools/tg_dirichlet_fused_stage.py synthetic-input /tmp/fused.bin \
  --q 10001 --q 400000 --t-index 4000 --characters-per-q 16
build/tg-production-kat/sparkinterval-tg-dirichlet-fused \
  /tmp/fused.bin /tmp/fused-output.bin 0 1
build/tg-production-kat/sparkinterval-tg-dirichlet-fused-exact verify \
  /tmp/fused.bin /tmp/fused-output.bin
```

Reproduce the source-shaped local benchmark (which labels itself as not an
atom ETA) with:

```bash
python3 tools/benchmark_tg_dirichlet_fused.py --pretty \
  --runner build/tg-production-kat/sparkinterval-tg-dirichlet-fused
```

Synthetic lattice cells, Taylor radii, and nontrivial root rectangles are test
data, not analytic certificates.

## Measured local performance

On the local NVIDIA GB10, a representative `q=400000`, `phi(q)=160000`,
in-range source-grid ordinate `t=5*4000/64=312.5`, and `K=256` selected characters performed
`40,960,000` group-point evaluations per iteration. Ten iterations took
`9.519837` seconds of CUDA-event time:

```text
43.026 million fused group points/second
```

Each group point includes canonical mixed-radix decoding, modular exponentiation
and CRT, sixteen Taylor terms, interval character powering/multiplication, and
the deterministic block reduction. The compact file was `1,059,160` bytes.
For comparison, just the old explicit request and result arrays for all
`160,000` residues of that one `(q,t)` slice would occupy `3,840,000` and
`7,680,000` bytes respectively.

This timing is not an H100 measurement and is not an atom ETA. It exposes why
the stage is an oracle rather than the production all-character method. Over
the large-q source grid there are
`47,631,269,684,196,653,160` group points in the direct all-character
calculation. At the measured saturated GB10 rate that would take about 35,100
years. Even requesting only 256 coefficients at every source `(q,t)` row would
take about 61.7 GB10-years. The intended use is sparse audit/exception work;
the production main path still needs the quasi-linear multidimensional FFT.

## Trust boundary and remaining work

The exact CPU replay proves containment only relative to three external input
contracts:

1. every lattice rectangle encloses the named `zeta_M` value;
2. the one supplied radius per modulus bounds every omitted Taylor tail in that
   task;
3. each cyclic-component rectangle encloses `exp(2*pi*i/order)`.

The input generator in the CLI is explicitly synthetic and proves none of
these. A production certificate producer for them is absent.

The direct reduction costs `O(K phi(q))` for `K` selected characters. Running
it with all `phi(q)` characters costs `O(phi(q)^2)` and is prohibited as a
source-scale plan. A full source-faithful pipeline still needs:

- a rigorously rounded multidimensional CRT/Bluestein interval FFT producing
  all characters in quasi-linear time;
- certified lattice construction, Taylor tails, finite-term restoration, and
  completed-`L` factors;
- Booker's small-modulus method;
- rigorous upsampling, zero isolation, exception handling, and the paired,
  multiplicity-preserving Turing count;
- independent production receipts and the Lean realization theorem.

Consequently `platt-dirichlet-theorem-7-1` remains an undischarged external
atom.
