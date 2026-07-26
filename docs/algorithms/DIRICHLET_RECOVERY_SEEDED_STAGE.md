# Certified recurrence seeds for large-q finite recovery

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This stage removes the largest avoidable input stream from the optimized
Dirichlet Theorem 7.1 path. It is a rigorous arithmetic component, not a proof
of the theorem. No source-wide zero isolation or Turing argument is claimed.

## Exact identity and finite source geometry

The large-`q` Taylor stage uses `M=4` and the exact positive ordinate grid

```text
t_j = 5j/64.
```

For each finite addback term, put `x=qn+a`. Then

```text
x^(-1/2-i t_j)
  = x^(-1/2) * (exp(-i*(5/64)*log x))^j.
```

For `q <= 400000`, `1 <= a < q`, and `0 <= n <= 4`, every required integer
lies in the single closed range

```text
1 <= x <= 4*400000 + 399999 = 1999999.
```

The table therefore stores only six outward binary64 endpoints per `x`:

```text
[A_lo,A_hi] contains x^(-1/2)
[W_re_lo,W_re_hi] + i[W_im_lo,W_im_hi]
    contains exp(-i*(5/64)*log x).
```

The complete record payload is `1,999,999 * 48 = 95,999,952` bytes. The
authenticated file, including its header, 123 chunk headers, and footer, is
`96,008,016` bytes.

## Fail-closed seed artifact

[`dirichlet_recovery_seeds.py`](../../tg_verifier/dirichlet_recovery_seeds.py)
generates a `TGDRCVS1` artifact with bounded chunks. Each chunk includes its
exact first `x`, record count, and a domain-separated SHA-256 over the complete
payload. A reader buffers and authenticates a whole chunk before exposing any
record. The footer commits both the raw record stream and the ordered chunk
digest root. A caller can additionally require the full-file SHA-256 before
parsing.

Generation uses pinned python-flint 0.9.0 / FLINT 3.6.0 with one Arb thread.
Each stored rectangle is the union of two differently structured evaluations:

- reciprocal square root plus separate sine/cosine at 192 bits; and
- `exp(-log(x)/2)` plus one complex exponential at 256 bits.

Full replay authenticates the file and reevaluates all records at 320 bits
through the second formula. Replay succeeds only if every higher-precision
Arb enclosure is contained in the stored binary64 intervals. The generation
manifest deliberately says `all_records_higher_precision_replayed=false`;
only the separately hash-bound replay report closes that finite check.

The local full run on 2026-07-22 produced:

| item | result |
|---|---:|
| records | `1,999,999` |
| generation time | `58.2363 s` |
| generation rate | `34,342.8 records/s` |
| complete 320-bit replay time | `26.9737 s` |
| replay rate | `74,146.2 records/s` |
| artifact SHA-256 | `55a325bb0fab730db5afa82e7b8227ebe00c306b0f4fb275e043fc6a13099199` |
| replay SHA-256 | `735e59739eadcfeb22e85370e1e0a9b702c08936e662b63ca1cbc9952e6fe29f` |

These hashes identify a local run artifact in `/tmp`; the artifact is not
checked into the repository and is not Azure execution evidence.

## Directed GPU expansion

[`h100_tg_dirichlet_recovery_seeded.cu`](../../gpu/platform/h100/h100_tg_dirichlet_recovery_seeded.cu)
authenticates the complete seed artifact before copying it to the GPU. One
thread handles one `(t_j,a)` output. It obtains the five records for
`x=qn+a`, uses binary exponentiation with CUDA directed binary64 interval
multiplication, scales by the amplitude interval, and adds the five rectangles.
There are no device `log`, `exp`, `sin`, `cos`, `pow`, or other transcendental
calls.

The standalone output is frame-major and then ascending in unit residue `a`.
The Python auditor reconstructs the CPU directed recurrence and separately
computes the literal five-term sum with 384-bit Arb. It can replay a complete
finite output or an explicitly labelled deterministic KAT sample. Corrupt
chunks and wrong full-file hashes fail before a GPU output is created.

At the worst source height for `q=10001`, a 64-ordinate batch contains 626,688
recovery rectangles. On the local NVIDIA GB10, 20 repeated launches measured
about `27.03 million rectangles/s`. A 128-point 384-bit Arb audit passed. The
complete batch had maximum component width about `1.0735e-9`; the audited
sample maximum was about `1.8523e-10`. These widths are observed arithmetic
facts, not a proof that every later completed-L sign remains decidable.

## Fused compact large-q input

The `TGDLQB2` layout removes every per-value recovery rectangle and stores one
Taylor-tail radius per ordinate instead of repeating that radius for every
residue. The converter:

1. checks the original `TGDLQBI1` SHA-256 before and after parsing;
2. validates exact q/grid/CRT/lattice geometry and every interval;
3. requires the Taylor radius to be bitwise identical across all residues of
   one ordinate;
4. binds the seed-artifact and complete-replay hashes; and
5. publishes the compact frame atomically.

[`h100_tg_dirichlet_largeq_seeded_batch.cu`](../../gpu/platform/h100/h100_tg_dirichlet_largeq_seeded_batch.cu)
authenticates the seeds once, keeps them resident, performs Taylor
reconstruction and finite recovery in one kernel, and emits the ordinary
`TGDAFFI1` frame expected by the persistent all-character transform. Its
framed-service mode retains the seed table and allocations for a complete
q-specific stream. No recovery rectangle crosses the host/device boundary.

For the 64-ordinate `q=10001` KAT, the compact input was `67,189,856` bytes,
versus `92,256,864` bytes for the old input. The fused kernel measured about
`19.42 million residue values/s` on GB10 over 20 launches. The exact full
source logical input model changes from

```text
18,263,933,424,590,240 bytes
```

to

```text
5,180,404,381,680,112 bytes.
```

That is a `3.526x` reduction. The remaining `5.180 PB` is dominated by the
same Hurwitz lattice cells being supplied in the q-outer schedule; this stage
does not itself solve that separate cache/broadcast problem. The follow-on
[t-major cache](DIRICHLET_LATTICE_CACHE.md) now provides an exact 125-GiB
source layout, bounded authenticated reader, higher-precision-replay repacker,
gap-free catalog, and work-balanced broadcast assignment. The follow-on
[`TGDLTMB1` component](DIRICHLET_TMAJOR_CUDA_BLOCK.md) now consumes the
authenticated t-major rows, eliminates q-major descriptor/lattice frames, and
runs this seeded CUDA kernel. Its exact binary input is 339.469 GB; downstream
FFT/zero integration and source execution remain open.

At the measured GB10 fused rate, the exact `327,089,206,283,008` large-q
residue computations correspond to about `4,677` single-GPU hours, or `24.36`
ideal days on eight equal GB10 devices. A purely illustrative 5x H100 uplift
would be about `4.87` ideal days on eight H100s. That is a sensitivity, not an
H100 benchmark or a Theorem 7.1 ETA; lattice supply, transforms, completed-L
work, exceptions, Turing closure, and replay remain additional.

## Reproduction

Generate and replay the full seed table (about 96 MB):

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_recovery_seeds.py generate \
  /work/recovery-seeds.bin /work/recovery-seeds.json

.venv-tg-flint/bin/python tools/tg_dirichlet_recovery_seeds.py replay \
  /work/recovery-seeds.bin /work/recovery-seeds.json \
  --report /work/recovery-seeds-replay.json
```

The production binder in
[`DIRICHLET_SOURCE_SUPERVISOR.md`](DIRICHLET_SOURCE_SUPERVISOR.md) does not
accept the replay JSON merely because it self-hashes. It reruns this complete
higher-precision verifier, requires the fresh replay record to match, and
rehashes the seed, manifest, and replay files afterward.

Build the isolated GPU paths without changing shared CMake:

```bash
nvcc -std=c++20 -O3 -lineinfo -arch=sm_90 --fmad=false --ftz=false \
  -I gpu/include \
  -DSPARKINTERVAL_REQUIRE_H100_SM90=1 \
  gpu/platform/h100/h100_tg_dirichlet_recovery_seeded.cu \
  -o sparkinterval-h100-tg-dirichlet-recovery-seeded

nvcc -std=c++20 -O3 -lineinfo -arch=sm_90 --fmad=false --ftz=false \
  -I gpu/include \
  -DSPARKINTERVAL_REQUIRE_H100_SM90=1 \
  gpu/platform/h100/h100_tg_dirichlet_largeq_seeded_batch.cu \
  -o sparkinterval-h100-tg-dirichlet-largeq-seeded-batch
```

Run focused tests after building local binaries:

```bash
TG_DIRICHLET_RECOVERY_SEEDED_BINARY=/path/to/recovery-runner \
TG_DIRICHLET_LARGEQ_SEEDED_BINARY=/path/to/fused-runner \
.venv-tg-flint/bin/python -m unittest -v \
  tests.test_tg_dirichlet_recovery_seeds
```

## Remaining trust boundary

The following remain explicitly false:

- usefulness of every compounded recurrence interval for source-wide sign and
  zero isolation;
- population of the authenticated source cache and integration of the
  implemented t-major CUDA output with the FFT/zero-consumer pipeline;
- complete exception/upsampling/window-shift handling;
- the corrected reflected Turing argument and its Lean analytic bridge;
- a full Azure run and independent replay; and
- discharge of `platt-dirichlet-theorem-7-1`.
