# T-major cache-row to typed FFT bundle adapter

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

[`dirichlet_tmajor_adapter.py`](../../tg_verifier/dirichlet_tmajor_adapter.py)
closes a bounded identity and ordering seam between the authenticated
`TGDLTCH1` cache and the existing fixed-`q` typed FFT bundle. It is an input
admission component, not the row-resident CUDA worker or a zero verifier.

## Fail-closed binding

The typed FFT replay now extracts the canonical one-MiB lattice region from
every retained `TGDLATI1` file and records:

```text
(t_index, SHA256(lattice payload))
```

The adapter first consumes its source-supervisor lane through the
`AuthenticatedLaneReader`. Rows must arrive in the exact assigned `t` order,
only one authenticated row lease is live at a time, and a domain-separated
row-schedule digest commits every `(t_index, payload_sha256)`.

Only after all assigned rows authenticate does the adapter admit typed FFT
bundles. The admission order is formulaic and source-sized lists are not
materialized:

```text
q ascending, then first_t_index ascending in batches of at most 64
```

For every target, a fresh typed-bundle replay must use the lane's reconstructed
source contract and reconstruct the pipeline receipt, controls, nested
artifacts, root artifact, event stream, and exact fixed-`q` descriptor. The
replayed lattice-payload list
must equal the corresponding authenticated t-major cache rows byte for byte.
A skipped target, reordered target, substituted bundle, changed nested
artifact, wrong external bundle digest, or different lattice payload fails
closed. One ordered admission chain binds the row schedule and every accepted
typed bundle.

The separate
[shared-row spool](DIRICHLET_TMAJOR_SPOOL.md) emits the same fixed-`q` target
descriptors and hash-bound contiguous row spans from the authenticated lane.
Thus the producer-side target and row identities compose with this adapter
without copying the 1-MiB row once per active modulus. The pipeline executor
and typed-bundle output wiring between those two checked boundaries remain
open.

The current adapter is explicitly a legacy-V1 control model. The lane session
reconstructs and revalidates its externally pinned source
contract once, before authenticating rows. Each bundle then reuses that exact
in-memory contract object while freshly replaying all bundle-local artifacts;
it does not repeat the full recovery/root/catalog audit 76,770,217 times.
Its roster cannot admit a primitive-only V2 `TGDLTMB1` campaign until the
source contract and manifest format are versioned together.

## Executable bounded known answer

The unit test
`test_tmajor_adapter_bounded_known_answer_and_manifest_path` executes the
complete adapter protocol for two deterministic cache rows and one `q=10001`
FFT bundle. It pins the domain-separated row-schedule answer:

```text
7bd505c71879872b3c124ede718872e29c0f10e90a8d78344779597c2a15e540
```

A negative test builds a structurally valid typed bundle from different
lattice bytes and verifies that admission fails at the cache-row boundary.
These are synthetic format/protocol tests, not analytic evidence.

Run the bounded tests with:

```bash
python3 -m unittest \
  tests.test_tg_dirichlet_fft_pipeline_bundle.DirichletFFTPipelineBundleTest.test_tmajor_adapter_bounded_known_answer_and_manifest_path \
  tests.test_tg_dirichlet_fft_pipeline_bundle.DirichletFFTPipelineBundleTest.test_tmajor_adapter_rejects_typed_bundle_from_different_cache_rows
```

## Operator interface

Authenticate a lane's deterministic row schedule:

```bash
python3 tools/tg_dirichlet_tmajor_adapter.py audit-rows \
  /shared/source-supervisor-contract.json --lane-index 0 \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256"
```

For full admission, provide an externally hash-pinned canonical NDJSON
manifest. Each line has the exact schema
`sparkinterval.tg.dirichlet_tmajor_adapter.bundle_manifest.v1`, an absolute
normalized bundle path, its typed `bundle_sha256`, and an optional absolute
control base. The adapter refuses to publish its immutable lane receipt unless
the manifest covers the complete deterministic roster:

```bash
python3 tools/tg_dirichlet_tmajor_adapter.py admit-lane \
  /shared/source-supervisor-contract.json \
  /shared/lane-0/bundles.ndjson \
  /shared/lane-0/tmajor-admission-receipt.json \
  --lane-index 0 \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256" \
  --expected-manifest-sha256 "$PINNED_BUNDLE_MANIFEST_SHA256"
```

## Exact remaining boundary

This adapter proves cache-row identity, typed receipt validity, and complete
deterministic admission order. The shared-row producer additionally proves
the input roster and row-span identity. Neither proves that the discarded
composition or FFT streams were arithmetically recomputed from those rows.
It also does not:

- wire the implemented
  [row-resident CUDA component](DIRICHLET_TMAJOR_CUDA_BLOCK.md)'s mixed-q
  `TGDAFFI1` output into the persistent FFT and completed-`L` pipeline or
  typed-bundle output (the structural
  [t-block supervisor](DIRICHLET_TBLOCK_SUPERVISOR.md) closes scheduling,
  backpressure, and resume, but production bundle-byte replay remains
  disabled);
- import/export authenticated completed-L per-character sign/zero state;
- version this legacy-V1 adapter to the 56,981,100-target primitive-only V2
  roster, populate the source cache or root catalog, run that V2 roster, or
  establish source-scale throughput;
- prove interval usefulness, exception refinement, interpolation, zero
  isolation, or reflected Turing completeness; or
- attest execution or discharge Platt's Theorem 7.1.

Every adapter receipt keeps those decisions and
`external_atom_discharged=false`. The adapter's own historical receipts still
say `row_resident_cuda_kernel_implemented=false`: they describe what that
receipt executed, not the repository-wide availability of the separate CUDA
component.
