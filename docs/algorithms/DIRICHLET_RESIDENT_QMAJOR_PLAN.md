# Resident q-major Dirichlet phase plan

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

This is an exact source-scale partition and resource projection. A
[source-shaped stream candidate](DIRICHLET_RESIDENT_QMAJOR_STREAM.md) now
implements the ten-phase wire, full-schedule parser, incremental row upload,
bounded q lanes, descriptor/event reuse, and back-pressured per-target output.
Its bounded real-CUDA KAT is byte-equivalent to the current resident,
formulaic, and legacy paths. No exact source phase or H100 fit run has
completed, and the semantic/sign reducer is not integrated. All source-run,
H100-measurement, attestation, zero-completeness, and external-atom flags
therefore remain false.

The plan addresses the central conflict between the two existing layouts:

- t-major execution transports each 1-MiB Hurwitz row once, but repeatedly
  changes q and loses the q-major FFT-plan locality; and
- formulaic q-major execution preserves FFT-plan locality, but its current
  bounded service would reread `3,637,613,167` row references, or
  `3,814,313,864,200,192` row-payload bytes.

The proposed production boundary loads a contiguous t range into device
memory once, then executes every active modulus in canonical q-major order
against those resident rows. It emits only q/t outputs and compact terminal
state; lattice rows do not occur in each q frame.

## Exact ten-phase partition

The existing eight work-balanced ranges are retained. The last range would
need 115.61 GiB of resident lattice payload. A two-way split fits only
nominally: the largest shard plus the current seeded/transform buffers and
512-MiB plan cache is about 76.25 GiB, leaving only about 3.75 GiB before the
CUDA context, allocator fragmentation, and downstream state. The pinned plan
therefore splits at the 64-row-aligned indices `49,088` and `88,512`. Its
three pieces run sequentially in GPU slot 7.

| Phase | GPU slot | t range | Resident payload | Active q | Batch-64 targets | Batched butterflies |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0 | `[0,768)` | 0.7500 GiB | 292,500 | 3,510,000 | 1,844,926,924,725,312 |
| 1 | 1 | `[768,1600)` | 0.8125 GiB | 292,500 | 3,802,500 | 1,998,670,835,119,088 |
| 2 | 2 | `[1600,2368)` | 0.7500 GiB | 292,500 | 3,510,000 | 1,844,926,924,725,312 |
| 3 | 3 | `[2368,3200)` | 0.8125 GiB | 292,500 | 3,802,500 | 1,998,670,835,119,088 |
| 4 | 4 | `[3200,4032)` | 0.8125 GiB | 292,500 | 3,736,394 | 1,899,471,145,527,012 |
| 5 | 5 | `[4032,5568)` | 1.5000 GiB | 255,543 | 5,380,665 | 1,967,010,083,383,448 |
| 6 | 6 | `[5568,9600)` | 3.9375 GiB | 187,230 | 8,210,666 | 1,886,569,668,387,388 |
| 7 | 7 | `[9600,49088)` | 38.5625 GiB | 93,257 | 19,894,223 | 1,745,552,940,214,384 |
| 8 | 7 | `[49088,88512)` | 38.5000 GiB | 12,056 | 4,226,917 | 129,013,705,688,052 |
| 9 | 7 | `[88512,127988)` | 38.5508 GiB | 3,346 | 907,235 | 20,152,819,356,972 |

The three slot-7 phases together require
`1,894,719,465,259,408` butterflies. Across eight slots the minimum and
maximum work are `1,844,926,924,725,312` and
`1,998,670,835,119,088`, respectively. The maximum is 4.27% above the exact
eight-slot average.

The ten phases sum to the existing source pins:

```text
targets                     56,981,100
q/t row references       3,637,613,167
group values           266,697,737,764,848
batch-64 butterflies 15,334,965,882,246,056
```

Every one of the `127,988` lattice rows is resident in exactly one phase.
Unique row payload is therefore `134,205,145,088` bytes (124.9883 GiB),
a `28,421.52x` reduction relative to rereading a row for every q/t
reference. The largest phase uses `41,406,169,088` payload bytes
(38.5625 GiB), or `41,408,696,320` bytes including its fixed row headers.
Replacing the two-way split's payload by this shard lowers the current static
payload-plus-known-buffer estimate from 76.25 GiB to 57.0 GiB, leaving
23.0 GiB of nominal headroom on an 80-GiB H100. This is still not a
whole-device fit proof: a compiled executor must measure and cap the CUDA
context, allocator fragmentation, downstream state, and any implementation
allocations not present in the current bounded runner.

## Checked artifacts

[`dirichlet_resident_qmajor_plan.py`](../../tg_verifier/dirichlet_resident_qmajor_plan.py)
independently recomputes every phase count from the complete primitive-V2
source schedule, canonical group orders, and exact batch-aware butterfly
formula. It factors each modulus once and rewrites that formula exactly as a
per-target setup cost plus a per-row cost before scanning the ten phases. A
test retains the original direct `group_order` / `modulus_butterflies` loop as
an independent reference and requires exact equality in all five accounting
columns. The planner rejects gaps, overlaps, reordered phases, non-64-aligned
internal boundaries, a phase above 39,488 rows, or a changed slot assignment.

[`ResidentQMajorPhases.lean`](../../SparkInterval/Dirichlet/ResidentQMajorPhases.lean)
proves in ordinary Lean that:

- every `t < 127988` belongs to exactly one of the ten phases;
- every phase is nonempty and has at most 39,488 rows;
- every phase starts on a 64-row boundary and every internal stop is aligned;
- the ten pinned phase costs aggregate to their exact assigned slot costs;
- every slot's pinned work is below the exact maximum; and
- the eight pinned slot totals sum to the source butterfly total.

Fresh `#print axioms` reports only Lean's standard base trio. There is no
`native_decide`, project axiom, `sorry`, or physical-execution claim.

Recompute the projection and compile the finite proof with:

```bash
python3 -m unittest -v tests.test_tg_dirichlet_resident_qmajor_plan
lake build SparkInterval.Dirichlet.ResidentQMajorPhases
lake env lean SparkInterval/Tests/ResidentQMajorPhasesTest.lean
```

## Required implementation

The source-shaped candidate implements items 1 and 2 at the wire/executor
level, but the source path must still:

1. feed its bounded `TGDAFFI1` frames directly into a back-pressured
   semantic/sign reducer rather than materializing the greater-than-1-PB
   largest raw phase;
2. keep the persistent FFT plan cache and completed-L consumer attached;
3. emit a compact phase terminal state that preserves sign transitions,
   zero multiplicity, unresolved intervals, and both boundary endpoints;
4. merge the ten phase states in t order, with explicit cross-phase
   continuity and Turing-count obligations;
5. measure every phase on the intended H100 and retain the memory preflight
   evidence instead of treating the formula as a fit claim; and
6. bind source, rows, sidecars, binaries, output states, and all child
   receipts into the confidential-compute closure.

Until the downstream reducer/state merge, source-wide usefulness check, zero
isolation, paired Turing closure, H100 calibration, attestation, and complete
source run exist, this candidate changes no production identity and proves no
analytic atom.
