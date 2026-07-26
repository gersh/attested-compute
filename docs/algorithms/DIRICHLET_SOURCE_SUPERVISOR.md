# Source-wide t-major Dirichlet supervisor contract

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This module describes the exact handoff between the authenticated 125-GiB
Hurwitz cache and the existing large-`q` Dirichlet components. It is a
fail-closed source-wide plan, not an executable end-to-end Azure verifier yet.

## Inputs bound by the production contract

[`dirichlet_source_supervisor.py`](../../tg_verifier/dirichlet_source_supervisor.py)
reconstructs and compares its complete canonical body every time it loads a
contract. A production contract requires:

- the complete replay-receipt-backed lattice cache and its fixed eight-lane
  broadcast plan;
- the full finite-recovery seed artifact, manifest, and supplied replay
  report, plus a fresh rerun of the existing higher-precision seed verifier;
- the complete 292,500-entry
  [`TGDRNRO1` root catalog](DIRICHLET_ROOT_CATALOG.md), with every root artifact
  reparsed and checked against its receipt during binding; and
- the exact source modulus interval `10001..400000`.

The contract remains classified
`source_wide_handoff_plan_not_execution_or_grh_evidence`. Its execution,
attestation, zero-completeness, and external-atom flags are false.

After the three full input families exist, bind and immediately revalidate
them with:

```bash
python3 tools/tg_dirichlet_source_supervisor.py bind-source \
  /shared/lattice-cache /shared/lattice-cache/catalog.json \
  /shared/recovery/seeds.bin /shared/recovery/manifest.json \
  /shared/recovery/replay.json \
  /shared/dirichlet-roots /shared/dirichlet-roots/catalog.ndjson \
  /shared/source-supervisor-contract.json
```

This command is intentionally expensive: it freshly replays every recovery
seed and reparses every root artifact. It does not execute the CUDA/FFT/zero
campaign. Record the returned `contract_sha256` outside the mutable run
directory. Every production `audit`, descriptor lookup, or lane reader
requires that externally pinned digest; an internally self-consistent
replacement contract is rejected.

## Two schedules that must not be confused

A t-major `q` tile contains heterogeneous moduli at one fixed ordinate while
one authenticated lattice-row lease is outstanding. This is the natural
cache-supply order. It is not a `TGDAFFI1`/`TGDAFFO1` FFT batch.

The existing all-character interface instead accepts one fixed modulus and at
most 64 consecutive ordinates. The supervisor separately defines that target
FFT descriptor:

```text
(lane, q, first_t_index, batch_count <= 64)
```

If the t-major rows are transposed/spooled into q-contiguous order, the exact
target FFT-batch counts for the pinned eight lanes are:

| lane | t range | fixed-q FFT batches |
|---:|---:|---:|
| 0 | `[0,896)` | `5,460,000` |
| 1 | `[896,1664)` | `4,680,000` |
| 2 | `[1664,2560)` | `5,460,000` |
| 3 | `[2560,3328)` | `4,680,000` |
| 4 | `[3328,4352)` | `5,947,802` |
| 5 | `[4352,5888)` | `7,181,268` |
| 6 | `[5888,10240)` | `11,189,898` |
| 7 | `[10240,127988)` | `32,171,249` |
| total | | `76,770,217` |

These formulas and totals are implemented and pinned as a target roster. They
are not invocations that the current one-row t-major state machine can issue
directly. The
[shared-row spool](DIRICHLET_TMAJOR_SPOOL.md) now authenticates and stores
each lane row once, derives every fixed-`q` contiguous span from this same
roster, and streams a complete fail-closed run manifest without a
source-sized in-memory task list. The existing CUDA/pipeline graph does not
yet consume that spool format, so this closes the host reference
transport/schedule seam but not production execution.

The authenticated reader allows at most one outstanding row lease per lane.
That is a supervisor invariant, not a claim that caller code cannot retain an
old Python byte string or that asynchronous device work has completed. Device
residency requires an acknowledged worker protocol and measured implementation.

## What is still missing

Three integration pieces prevent an Azure production run:

1. The
   [row-resident CUDA component](DIRICHLET_TMAJOR_CUDA_BLOCK.md) now consumes
   the shared-row spool, directly produces replayed MPFR factor and
   exact-rational tail sidecars, and emits mixed-q `TGDAFFI1` frames after one
   lattice-block upload. The
   [t-block subprocess supervisor](DIRICHLET_TBLOCK_SUPERVISOR.md) now streams
   each of the 2,000 source blocks once and binds the exact formulaic q roster,
   but it is not wired to this CUDA output or a persistent multi-q transform
   worker.
2. The
   [typed FFT pipeline bundle validator](DIRICHLET_FFT_PIPELINE_RECEIPT_BUNDLE.md)
   now connects one fixed-q control extent, its retained artifacts, and both
   TGDAFF stream hashes to the exact contract target. A separate
   [t-major admission adapter](DIRICHLET_TMAJOR_ADAPTER.md) now freshly replays
   each bundle in deterministic target order and requires its extracted
   `TGDLATI1` lattice payloads to equal the authenticated cache rows. That
   adapter does not yet receive actual framed bundle bytes from the t-block
   supervisor, drive CUDA, or independently replay the discarded FFT
   arithmetic. Production admission remains disabled at that byte-replay
   boundary even for a worker that self-asserts all capabilities.
3. The completed-L consumer's ordinary interface requires monotone `q`.
   Its explicit
   [TGDQORD1 scheduled interface](DIRICHLET_SCHEDULED_LARGEQ_PIPELINE.md)
   now accepts the manifest permutation, retains actual q labels, and requires
   contiguous ordinates and exact row coverage within each modulus. This
   closes the q-major producer/FFT/consumer scheduling seam, but it still
   cannot import/export per-character sign state in t-major order. The
   t-major production route therefore still needs an authenticated keyed
   state store or equivalent completed-L state handoff.

The root catalog currently proves byte-level parsing, receipt binding, exact
coverage, and ordering. It does not independently recompute the root numbers
from the mathematical additive/transform inputs. Production lane execution
therefore remains disabled, and there is not yet a per-entry execution reader
that reauthenticates a root artifact immediately before use.

The original structural lane state machine exists to test q-tile ordering: it rejects skipped
or reordered q tiles, early row advancement, mismatched row identities, and
broken claimed-state continuity. It binds remaining FFT/zero/measurement
claims into one ordered chain, but deliberately marks them unvalidated. It
must not be treated as a production completion receipt. The implementation
refuses to start this lane state machine for a production-classified contract;
invented 64-digit component claims are accepted only in an explicitly
authorized structural KAT. Production enablement still requires replacing
the executing q-tile path with the typed admission adapter plus real CUDA or
output receipts from the shared-row CUDA component, typed bundle admission,
and a validated zero-state transition.

Even after these software seams close, the full cache/root/seed inputs must be
generated, the Azure run must execute, interval widths and exception
refinement must succeed, and the accepted zero-isolation/Turing closure must be
connected to the Lean evidence bridge.
