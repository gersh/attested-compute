# Typed Dirichlet FFT pipeline receipt bundle

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

[`dirichlet_fft_pipeline_bundle.py`](../../tg_verifier/dirichlet_fft_pipeline_bundle.py)
turns one retained persistent-pipeline receipt into a typed handoff for one
exact fixed-`q`, at-most-64-ordinate target from the source-supervisor
contract. This removes the previous interface in which an arbitrary 64-digit
string could pose as an FFT pipeline receipt.

The validator fails closed unless a fresh replay:

- reconstructs the externally hash-pinned source contract and its exact
  `fft_batch_descriptor`;
- reparses and hashes the pipeline receipt, both control streams, every
  composition job and its complete upstream artifact/certificate chain, each
  composition receipt, the composer summary, the CUDA transform summary, the
  completed-L consumer receipt, its event stream, and the root artifact and
  receipt;
- recomputes the modulus, source `5/64` grid, batch/value counts, component
  orders and radix-2 butterfly count from formulas;
- checks all nested schemas, algorithms, classifications, false claim
  boundaries, self-hashes and cross-stage stream hashes; and
- requires the reconstructed pipeline coverage to equal the contract target,
  not merely overlap it.

The replay also hashes the canonical one-MiB lattice region inside every
retained `TGDLATI1` and records the ordered
`(t_index, payload_sha256)` list. The
[t-major adapter](DIRICHLET_TMAJOR_ADAPTER.md) compares that list byte for byte
with the independently authenticated `TGDLTCH1` cache rows before admitting a
bundle.

Build the typed bundle immediately after one fixed-`q` pipeline run:

```bash
python3 tools/tg_dirichlet_fft_pipeline_bundle.py build \
  /shared/source-supervisor-contract.json \
  /shared/q-10001/batch-000000/pipeline-receipt.json \
  /shared/q-10001/batch-000000/typed-fft-bundle.json \
  --lane-index 0 --q 10001 --first-t-index 0 \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256" \
  --expected-pipeline-file-sha256 "$MEASURED_PIPELINE_RECEIPT_FILE_SHA256"
```

Replay it in a separate verifier environment:

```bash
python3 tools/tg_dirichlet_fft_pipeline_bundle.py replay \
  /shared/source-supervisor-contract.json \
  /shared/q-10001/batch-000000/typed-fft-bundle.json \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256" \
  --expected-bundle-sha256 "$PINNED_TYPED_BUNDLE_SHA256"
```

The replay needs the retained named input/certificate artifacts. It uses the
root-stage parser, so the pinned Python-FLINT/FLINT runtime is required.
`--allow-structural-kat` is an explicit test-only escape hatch and is rejected
for synthetic contracts unless named. A synthetic KAT bundle keeps the input
certificate-chain decision false; only a production-classified job with the
complete validated chain sets it true.

## Exact trust boundary

The producer deliberately discards the large `TGDAFFI1` and `TGDAFFO1`
streams after hashing them. The typed replay therefore proves that two
independent stage summaries agree on the stream hashes and that all retained
inputs and receipt structure are consistent; it cannot independently replay
the discarded FFT arithmetic from only those hashes. Its receipt consequently
keeps these decisions false:

```text
discarded_composition_stream_arithmetic_independently_replayed
discarded_fft_stream_arithmetic_independently_replayed
consumer_control_upstream_semantics_replayed
zero_state_transition_validated
zero_completeness_claimed
trusted_execution_attested
external_atom_discharged
```

The four legacy consumer-control digest fields are shape-checked but do not
have a canonical pre-run mapping to the composition receipts produced during
the same streaming run. The typed validator therefore does not silently treat
them as semantic evidence. Instead it directly reparses the retained
composition jobs, certificates and receipts, and independently cross-checks
the actual composer/transform/consumer stream hashes. Defining an operational
dynamic-control or deterministic pre-run mapping remains a separate seam.

The bounded cache-row admission adapter now connects typed fixed-`q` bundle
identity to the t-major lane schedule. The
[shared-row spool](DIRICHLET_TMAJOR_SPOOL.md) now provides the exact
producer-side fixed-`q` row spans and complete run roster without duplicating
row payloads. The remaining production work is to implement and measure the
row-resident CUDA or CPU executor that consumes those inputs and emits these
typed pipeline artifacts, implement authenticated zero-state import/export,
run the complete roster, retain measured-execution evidence, and complete
exception refinement and the corrected Turing argument.
