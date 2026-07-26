# Authenticated t-major shared-row and fixed-q run spool

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

[`dirichlet_tmajor_spool.py`](../../tg_verifier/dirichlet_tmajor_spool.py)
implements the deterministic host/reference seam between authenticated
`TGDLTCH1` lane rows and the fixed-`q`, at-most-64-ordinate targets consumed by
the existing Dirichlet pipeline.

This is a transport and scheduling component. It does not run CUDA, generate
pipeline receipts or typed bundles, update completed-\(L\) zero state, perform
a Turing count, attest execution, or discharge Platt's Theorem 7.1.

## Why rows are not transposed by copying

The exact source roster contains:

```text
127,988 unique t-major rows
4,901,051,274 (q,t) row references
76,770,217 fixed-q runs of at most 64 ordinates
```

Those are the legacy all-modulus V1 spool counts.  The direct `TGDLTMB1` V2
adapter rejects V1 and excludes the 97,500 moduli `q % 4 = 2`, whose primitive
character rosters are empty.  Its active schedule has 3,637,613,167 row
references and 56,981,100 fixed-q runs; the legacy spool must be versioned
before it can itself advertise that roster.

Each row payload is 1 MiB. Literally copying it once per active modulus would
recreate a multi-petabyte q-major boundary. The spool instead stores every
authenticated lane row exactly once. A fixed-`q` run input names a contiguous
span in that shared row archive:

```text
(lane, q, first_t_index, t_index_stop_exclusive, archive offset and stride)
```

It also commits the exact ordered `(t_index, SHA256(payload))` span. The
descriptor is the same `fft_batch_descriptor` reconstructed by the
[source supervisor](DIRICHLET_SOURCE_SUPERVISOR.md) and later required by the
[t-major admission adapter](DIRICHLET_TMAJOR_ADAPTER.md).

## Pinned immutable formats

The binary archive is versioned by the eight-byte magics:

```text
TGDLQSP1  header
TGDLQSR1  fixed-stride row record
TGDLQSF1  footer
```

Its header binds the source-contract digest, lane assignment, exact \(t\)
range, 1-MiB row size, and record stride. Every row header binds its exact
index, byte length, and payload SHA-256. The footer binds exact row and byte
counts, the complete raw-record digest, and the same domain-separated
row-schedule digest used by `dirichlet_tmajor_adapter`.

The canonical JSON spool receipt is externally pin-able by
`receipt_sha256`. It binds the normalized archive path, complete archive
SHA-256 and size, source contract, lane assignment, binary-format constants,
and exact schedule accounting.

Each canonical JSON run input binds:

- the source contract and spool receipt;
- the exact formulaic fixed-`q` target;
- the archive path/hash/size, first record offset, record stride, and row
  count;
- a domain-separated digest of every ordered row identity in the span; and
- false decisions for every execution or proof claim not established here.

A complete run manifest is newline-delimited canonical JSON. Its builder and
replayer stream one record at a time and retain no source-sized Python list.
The manifest receipt binds the file hash/size, exact run and row-reference
counts, and an ordered run hash chain.

## Fail-closed behavior

The archive reader opens regular files without following a final symlink,
checks the externally pinned receipt, hashes and parses the complete archive,
and retains the authenticated file descriptor. Every row is rehashed again
when a run reads it.

The run cursor derives its next target formulaically in canonical order:

```text
q ascending, then first_t_index ascending by at most 64
```

It rejects a substituted target or row binding, a skipped run, a reordered
run, an extra run, or end of file before the exact roster ends. The focused
tests also mutate and truncate the binary archive and construct internally
rehashed reordered/truncated manifests; all fail closed.

Run them with:

```bash
python3 -m unittest -v tests.test_tg_dirichlet_tmajor_spool
```

## Operator interface

Build one immutable lane spool:

```bash
python3 tools/tg_dirichlet_tmajor_spool.py build-spool \
  /shared/source-contract.json \
  /shared/lane-0/rows.spool \
  /shared/lane-0/rows.spool.receipt.json \
  --lane-index 0 \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256"
```

Audit it from the externally pinned receipt:

```bash
python3 tools/tg_dirichlet_tmajor_spool.py audit-spool \
  /shared/source-contract.json \
  /shared/lane-0/rows.spool.receipt.json \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256" \
  --expected-receipt-sha256 "$PINNED_SPOOL_RECEIPT_SHA256"
```

Emit one fixed-`q` run input, or stream the complete canonical roster:

```bash
python3 tools/tg_dirichlet_tmajor_spool.py emit-run \
  /shared/source-contract.json \
  /shared/lane-0/rows.spool.receipt.json \
  /shared/lane-0/run-q10001-t0.json \
  --q 10001 --first-t-index 0 \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256" \
  --expected-receipt-sha256 "$PINNED_SPOOL_RECEIPT_SHA256"

python3 tools/tg_dirichlet_tmajor_spool.py build-run-manifest \
  /shared/source-contract.json \
  /shared/lane-0/rows.spool.receipt.json \
  /shared/lane-0/runs.ndjson \
  /shared/lane-0/runs.receipt.json \
  --expected-contract-sha256 "$PINNED_SOURCE_CONTRACT_SHA256" \
  --expected-spool-receipt-sha256 "$PINNED_SPOOL_RECEIPT_SHA256"
```

Materializing 76,770,217 JSON run records is supported as a bounded-memory
reference path, but it is not the recommended H100 control plane. The
[t-block supervisor](DIRICHLET_TBLOCK_SUPERVISOR.md) instead represents the
same exact roster with 2,000 formula-bound block requests and no q-major
manifest.

## Row-resident CUDA handoff and remaining execution gap

[`DIRICHLET_TMAJOR_CUDA_BLOCK.md`](DIRICHLET_TMAJOR_CUDA_BLOCK.md) now
freshly replays these authenticated row spans, emits a typed `TGDLTMB1` block,
and runs the seeded large-`q` CUDA kernel after one lattice upload. Its
preferred direct mode generates directed MPFR factors and exact-rational
Taylor tails without q-major `TGDLQB2` inputs. The exact source input is
`286,556,459,000` bytes plus the separate `96,008,016`-byte recovery-seed
artifact.

The remaining production seam is downstream of the row-resident composition
kernel. It must:

1. feed the mixed-q `TGDAFFI1` stream into a persistent multi-q
   all-character transform service;
2. emit typed bundles and admit them through the cache-row adapter without
   gaps or substitutions;
3. implement authenticated per-character completed-\(L\) state
   import/export and the exception/Turing closure;
4. add independent arithmetic replay or an explicitly reviewed measured
   execution boundary; and
5. execute and measure the full Azure workload under the separate
   attestation policy.

Source-scale performance, downstream pipeline consumption, typed-bundle
output, discarded arithmetic replay, zero/Turing completeness, attestation,
and external-atom discharge remain false. Row-resident CUDA implementation is
now true; no source-scale run is implied.
