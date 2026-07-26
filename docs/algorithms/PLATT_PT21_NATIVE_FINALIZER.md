# PT21 native retained-export finalizer

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

This component removes the Python/JSON scale bottleneck from the optimized
Platt--Trudgian finite-RH artifact chain. It is a finite finalizer, not a proof
of the Riemann hypothesis. In particular, it does not promote a digest, DD
disk, Arb interval, sign bit, or confidential-compute receipt to a theorem
about Hardy Z.

The two implementations are deliberately independent:

- `reference/tg_platt_pt21_native_finalizer.cpp` streams shard and campaign
  finalization with bounded memory;
- `tg_verifier/platt_pt21_native_finalizer.py` rescans every retained record
  and shard and independently recomputes all count, sparse-refinement, SHA-256,
  and duplicate-odd Merkle relationships.

Both implementations require a create-only output and reject symlinks,
truncation, trailing bytes, gaps, reordered shards, non-telescoping counts,
aggregate overflow, duplicate or misplaced source-height counts, and any
nonzero finite failure counter.

## Fixed block commitment

Every accepted window contributes one 320-byte little-endian `PT21BLK1`
record:

| offset | bytes | field |
|---:|---:|---|
| 0 | 8 | magic `PT21BLK1` |
| 8 | 4 | version `1` |
| 12 | 4 | record bytes `320` |
| 16 | 8 | logical block |
| 24 | 8 | lower Turing count |
| 32 | 8 | upper Turing count |
| 40 | 8 | main multiplicity-slot count |
| 48 | 4 | stationary-resolution count |
| 52 | 4 | sparse-refinement count |
| 56 | 4 | initially ambiguous disk count |
| 60 | 4 | invalid-disk count, required zero |
| 64 | 4 | unresolved-disk count, required zero |
| 68 | 4 | unresolved-stationary count, required zero |
| 72 | 4 | Turing-failure count, required zero |
| 76 | 4 | independent-replay-failure count, required zero |
| 80 | 8 | exact source-height count or `UINT64_MAX` |
| 88 | 32 | required-sign-packet SHA-256 |
| 120 | 32 | canonical source-trace SHA-256 |
| 152 | 32 | finite v2 block-artifact SHA-256 |
| 184 | 32 | stationary-trace SHA-256, zero exactly when its count is zero |
| 216 | 32 | sparse-refinement SHA-256, zero exactly when its count is zero |
| 248 | 32 | measured-worker SHA-256, required to equal the shard header |
| 280 | 8 | target-height slots from the block's lower endpoint, otherwise zero |
| 288 | 32 | domain-separated record SHA-256 |

The lower count plus the main slot count must equal the upper count. The
initial ambiguity count must equal the sparse-refinement count, so an
ambiguous lattice disk cannot disappear between the measured worker and the
finalizer. A sparse count requires a nonzero retained trace digest. Conversely,
a worker that needed no sparse fallback must write both count and digest as
zero.

The unique block containing `3000175332800` must carry a source-height count;
every other block must carry the sentinel and zero target-height slots. In the
target block, the lower count plus the retained partial-slot count must equal
the source-height count, and that partial count cannot exceed the block's main
slot count. Full production campaign finalization additionally requires the
published value `12363153437138`.

## Retained archives

A shard archive consists of:

```text
256-byte PT21SHD1 header
block_count × 320-byte PT21BLK1 records
256-byte PT21SFT1 footer
```

The header binds the mode, exact block range, measured worker, immutable plan,
prefix evidence, Platt upstream commit, and interpolation-correction digest.
The footer recomputes the endpoint counts and totals and binds both the whole
record-stream SHA-256 and the duplicate-odd block Merkle root.

A campaign archive contains one 288-byte `PT21CSR1` summary for every shard.
The native campaign pass fully validates every shard before producing the
summary. Independent replay does not trust that summary: it opens and rescans
the corresponding shard archive and requires every field and digest to match
the fresh result. The campaign footer then fixes the gap-free shard chain,
total blocks and slots, source-height count, summary-stream digest, and
duplicate-odd shard Merkle root.

Neither archive has an `accepted analytic semantics` bit. Native stdout
reports `source_claim_ready:false`.

## Build and bounded known answers

```bash
cmake --build build --target \
  sparkinterval-tg-platt-pt21-native-finalizer

TG_PLATT_PT21_NATIVE_FINALIZER=\
build/sparkinterval-tg-platt-pt21-native-finalizer \
python3 -m unittest -v \
  tests.test_tg_platt_pt21_native_finalizer
```

The shard interface is:

```bash
sparkinterval-tg-platt-pt21-native-finalizer shard \
  --input BLOCK_RECORDS \
  --output SHARD_ARCHIVE \
  --first-block FIRST \
  --block-count COUNT \
  --worker-sha256 WORKER \
  --plan-sha256 PLAN \
  --prefix-evidence-sha256 PREFIX
```

For online assembly, `--input -` is accepted only together with
`--stream-auth-sha256 MANIFEST`. After exactly `block-count` records the
finalizer requires a 48-byte `PT21END1` footer containing that same digest and
then exact EOF. It never publishes the create-only shard archive on a missing
footer, a different digest, a truncated record, or trailing input. Regular
file input retains the exact advance-length check above.

The campaign interface replaces the input with a canonical newline-terminated
`--shard-list`. `--bounded-test` is required for fixtures; omitting it selects
production geometry and makes incomplete campaign finalization fail.

Independent operator replay is:

```bash
python3 tools/tg_platt_pt21_native_finalizer.py replay-campaign \
  CAMPAIGN_ARCHIVE \
  --shard-list SHARD_LIST \
  --expected-worker-sha256 WORKER \
  --expected-plan-sha256 PLAN \
  --expected-prefix-evidence-sha256 PREFIX
```

It emits success only after rescanning every shard archive and every retained
record. The `replay-shard` command provides the corresponding single-shard
audit.

## Validated record adapter

`tg_verifier/platt_pt21_native_record_adapter.py` now closes the finite
assembly boundary immediately before the native finalizer. For each window it
loads the complete required-sign packet, an independently replayed stationary
trace, the block-bound Arb Turing-input artifact, and the actual measured
worker executable. It then:

1. rechecks every DD sign and both finite input artifacts;
2. assembles the canonical fused source trace with all analytic status flags
   false;
3. rebuilds the exact-rational v2 block artifact and its Turing counts;
4. links the unique source-height count to the block's partial slots; and
5. emits the exact 320-byte `PT21BLK1` wire.

The `shard` interface reads canonical JSON-lines with safe relative paths,
requires an exact first block and record count, rejects gaps and
non-telescoping counts, and uses create-only output:

```bash
python3 tools/tg_platt_pt21_native_record_adapter.py shard \
  --manifest shard-inputs.jsonl \
  --worker PINNED_FUSED_WORKER \
  --first-block FIRST \
  --block-count COUNT \
  --output shard.records
```

The optional, explicitly selected packet-scan accelerator is documented in
[PT21 qualification-only native packet-scan fast path](PLATT_PT21_NATIVE_SCAN_FASTPATH.md).
It preserves byte-for-byte `PT21BLK1` output in differential tests but is not
used by the manifest or production entry points.

The step-3 exact-rational rebuild also has an explicitly selected native
streaming checker, documented in
[PT21 native v2 artifact builder](PLATT_PT21_NATIVE_ARTIFACT_BUILDER.md).  It
must be byte-identical to the Python reference finalizer, which remains the
independent implementation, and it is likewise absent from the manifest and
production entry points.

The `shard-archive` interface removes that intermediate record file. It opens
and hashes the native finalizer through one retained executable descriptor,
requires both its pinned SHA-256 and the manifest SHA-256, validates each
finite input row, and writes each authenticated record directly to the
finalizer pipe:

```bash
python3 tools/tg_platt_pt21_native_record_adapter.py shard-archive \
  --manifest shard-inputs.jsonl \
  --expected-manifest-sha256 MANIFEST \
  --worker PINNED_FUSED_WORKER \
  --finalizer PINNED_NATIVE_FINALIZER \
  --expected-finalizer-sha256 FINALIZER \
  --first-block FIRST \
  --block-count COUNT \
  --plan-sha256 PLAN \
  --prefix-evidence-sha256 PREFIX \
  --output shard.pt21
```

The adapter emits `PT21END1` only after it has consumed the exact manifest,
matched its pinned digest, checked the declared record count, and closed every
gap and count transition. Thus a late manifest mismatch cannot turn an
already-written prefix into a published shard. The finalizer independently
checks each `PT21BLK1`, incorporates the records into `PT21SHD1/PT21SFT1`,
and the adapter rehashes the published archive against the finalizer summary.
Peak record-channel memory is constant. The canonical records remain retained
inside the shard archive, but the additional campaign-wide 884.07 GiB
`shard.records` spool is no longer required.

This is an executable CPU adapter for already completed finite worker stages;
it is not evidence that the current measured H100 worker streams those stages
for every source window.

## Local finalizer-only measurement

A 2026-07-22 local synthetic run finalized 131,072 distinct, digest-valid
records (40 MiB) in 0.991 s including create-only archive output and `fsync`,
or 40.35 MiB/s. Independent Python replay rescanned the archive in 0.595 s,
or 67.20 MiB/s. The full fixed-width stream is 949,262,010,560 bytes
(884.07 GiB), so straight single-process sensitivities are 6.23 hours for
native finalization and 3.74 hours for replay. Production shards are
independent and can finalize in parallel.

This is a finalizer-only cache/filesystem measurement on synthetic commitment
records. It is not an H100 worker benchmark, a source-height run, or evidence
that the record commitments have the missing analytic realization.

The validated Python record adapter was also measured locally on 2026-07-23
using a complete 25,741-sample direct-event fixture. Seven post-warmup runs
had a median of 0.28339 seconds per block (3.5287 blocks/s; range
0.28067--0.28552 seconds). This includes packet/sign replay, stationary and
Turing-input validation, exact-rational event/Turing reconstruction, and
record encoding. It is a correctness-path measurement, not a source-scale
projection: direct use of this Python implementation for 2.97 billion windows
would be impractical. Production still needs the same adapter contract fused
in-process with the measured native worker, or an independently tested native
implementation.

## Remaining boundary

`compact_artifact_chain_finalizer.production_scale_native_implementation`, its
validated `PT21BLK1` adapter, and its independent retained-export replay are
implemented. The adapter-to-native-shard channel is now authenticated and
bounded-memory and needs no intermediate record spool. The optimized PT21
execution contract remains disabled, but for a narrower reason than before.
The fused worker's block stage now reaches Gaussian-sinc stationary resolution
and one-sided Arb Turing-input production inside the same ordered fail-closed
loop, rebuilds the required-sign packet from the replay-owned disks, and
streams all three complete per-window adapter inputs as authenticated
`PT21WBF1` frames that carry the event Merkle root forward through `PT21STJ1`.
An independent Python driver consumes that stream straight into this adapter
and the pinned native finalizer, so the manifest and per-block artifact channel
is gone. What is still missing is direct `PT21BLK1` emission by the worker:
the records come from the out-of-process Python adapter, measured at about
`3.97` accepted blocks/s on the local GB10 for real source blocks. Sparse
refinement remains unexercised. See
[`PLATT_PT21_BLOCK_INPUT_STREAM.md`](PLATT_PT21_BLOCK_INPUT_STREAM.md). The Python
correctness adapter's measured 3.5287 blocks/s is also not a source-scale
worker. Hardy-Z endpoint realization, multiplicity
realization, analytic Turing realization, Lean source realization, prefix
admission, attestation, the full run, target-SKU measurement, and a supported
one-week/USD-10,000 cost result remain separate blockers.
