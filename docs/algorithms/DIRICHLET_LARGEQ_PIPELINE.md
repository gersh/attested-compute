# Persistent large-q Dirichlet component pipeline

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This supervisor wires the implemented large-`q` components into one bounded,
back-pressured process graph for a single modulus shard:

```text
canonical composition controls
          |
          v
residue composer -- TGDAFFI1 --> retained q-specific CUDA FFT plan
                                      |
                                  TGDAFFO1
                                      |
                                      v
                 TGDRNRO1-bound completed-L/sign consumer
```

It is an executable production component graph, not a proof of Platt's
Theorem 7.1.  It does not assert zero completeness, run the source campaign,
or discharge a Lean atom.

## What the supervisor enforces

Before launching anything, `preflight` loads and hash-validates every bounded
composition job and requires a one-to-one canonical consumer control.  The two
records must agree on `q`, batch size, first ordinate, denominator, and step;
all jobs must form one contiguous q shard.  Consumer controls must explicitly
select the certified `tgdaff-all-character-gauss-root-phase-v1` mode.

The run command validates the `TGDRNRO1` artifact and receipt, then launches
exactly three persistent processes:

1. `framed-produce` retains one MPFR runtime and one CRT plan and writes pure
   concatenated `TGDAFFI1` to stdout;
2. `--framed-service` retains one CUDA Bluestein plan and writes pure
   concatenated `TGDAFFO1`; and
3. the completed-L consumer retains the root map and sign state for the whole
   modulus.

Ordinary OS pipes provide bounded backpressure.  The supervisor closes its
duplicate pipe descriptors so a failed downstream process produces EOF or a
broken pipe upstream, retains separate diagnostics, and rejects any nonzero
child status.  It then requires

```text
composer.TGDAFFI1_stream_sha256 == transform.input_stream_sha256
transform.output_stream_sha256 == consumer.transform_stream_sha256
```

as well as identical frame, slice, and value counts.  The final immutable
receipt binds all summaries, events, the root artifact, and the root receipt.
No campaign-wide interval stream is retained.

## Usage

The composition control is canonical NDJSON with records of the form

```json
{"job":"/shared/q/job-000000.json","receipt":"/shared/q/composition-000000.json","schema":"sparkinterval.tg.dirichlet_residue_composition.framed_request.v1","schema_version":1}
```

The consumer control has the same frame sequence and uses the ordinary
completed-L control schema with `root_number_mode` set to
`tgdaff-all-character-gauss-root-phase-v1`.

```bash
python3 tools/tg_dirichlet_largeq_pipeline.py preflight \
  /shared/q/composition.ndjson /shared/q/consumer.ndjson \
  --base /shared/q --max-batch-count 64

python3 tools/tg_dirichlet_largeq_pipeline.py run \
  /shared/q/composition.ndjson /shared/q/consumer.ndjson \
  /shared/q/roots.bin /shared/q/roots.json \
  /shared/q/pipeline /shared/q/pipeline-receipt.json \
  --base /shared/q \
  --allchars-runner build/h100-native/sparkinterval-h100-tg-dirichlet-allchars \
  --consumer-python /opt/tg-flint/bin/python \
  --max-batch-count 64 --device 0
```

The strict runner refuses a non-`sm_90` device.  A local synthetic KAT passes
two large-q ordinates through the real composer and CUDA transform, validates
a real q=10001 root artifact, and uses a compact protocol sink to check the
three-process stream binding.  The actual completed-L consumer has a separate
q=5 KAT showing that `TGDRNRO1` produces the same signs and brackets as direct
quadratic Arb Gauss sums.

## Remaining source boundary

The supervisor removes per-batch process creation and the 10.47-PB retained
transform problem.  It does not by itself solve these remaining obligations:

- generate and replay the full lattice/recovery input campaign efficiently;
- prove that every interpolation enclosure remains useful at source scale;
- refine indeterminate samples and execute the paper's padding/upsampling
  paths;
- isolate zeros with multiplicity and complete the corrected Turing argument;
- independently replay the final campaign receipt and connect accepted
  external evidence to Lean.

Accordingly its receipt says `external_atom_discharged: false` and
`zero_completeness_claimed: false`.

The alternative directed CUDA frontend in
`DIRICHLET_LARGEQ_BATCH_STAGE.md` fuses Taylor reconstruction and residue
composition into one kernel per at-most-64-ordinate frame and can feed the same
`TGDAFFI1` transform service.  Its retained V1 schedule reduces the main-grid
kernel count from `4,901,051,274` to `76,770,217`, but its current literal
certified-box input is
18.264 PB.  It therefore complements this process graph; it does not yet
replace the missing colocated box producer and source-scale I/O plan.

The newer `DIRICHLET_RECOVERY_SEEDED_STAGE.md` variant removes the finite-
recovery rectangles and repeated per-residue tail radii, reducing that logical
input to 5.180 PB. `DIRICHLET_LATTICE_CACHE.md` now supplies the exact
125-GiB t-major storage contract, replay-receipt binding, bounded reader, and
work-balanced broadcast plan.
`DIRICHLET_TMAJOR_CUDA_BLOCK.md` now removes the remaining repeated descriptor
tables and q-major source frames: its primitive-only V2 direct
MPFR/exact-tail path has an exact 286,556,459,000-byte binary-input model and
uploads each row block once. The
q-persistent service still needs a mixed-q transform/typed-bundle adapter,
authenticated zero-state handoff, and source-wide width audit before this
supervisor can select it as a production atom route.

`DIRICHLET_SOURCE_SUPERVISOR.md` now pins the exact source-wide cache/recovery
handoff, distinguishes heterogeneous one-ordinate q tiles from the real
fixed-q/up-to-64-ordinate FFT batches, and recomputes the exact 76,770,217 FFT
batch roster. `DIRICHLET_ROOT_CATALOG.md` also provides the missing monotone,
fully parsed root-artifact catalog. These are fail-closed planning and input
contracts. `DIRICHLET_FFT_PIPELINE_RECEIPT_BUNDLE.md` now supplies the typed
fixed-q receipt validator, and `DIRICHLET_TMAJOR_ADAPTER.md` supplies a bounded
deterministic admission path that requires each typed bundle's lattice
payloads to equal the authenticated cache rows.
`DIRICHLET_TMAJOR_SPOOL.md` now supplies an immutable one-copy-per-row archive
and formulaic fixed-q run records with exact source accounting.
`DIRICHLET_TBLOCK_SUPERVISOR.md` adds a 2,000-request, one-block-at-a-time
subprocess protocol and resumable checkpoint chain without the 76,770,217-line
manifest. The native process graph is still fixed-q and does not implement the
required multi-q worker; actual framed typed-bundle-byte output/replay and a
real zero-state import/export path remain unimplemented. The separate
row-resident CUDA component ends at `TGDAFFI1` and has not yet been wired into
this process graph.
