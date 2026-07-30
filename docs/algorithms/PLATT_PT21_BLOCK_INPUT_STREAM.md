# PT21 worker block-input stream

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

This component joins the stationary-interpolation and one-sided Turing stages
to the same fail-closed fused worker, so that one ordered loop produces all
three inputs the exact-rational record adapter needs:

```text
authenticated Gamma V2 record
  -> DD accumulator -> DD source transform
  -> resident 25,741-disk required view
  -> CUDA three-stream scan -> pinned host replay
  -> PT21EVT1
  -> FLINT Gaussian-sinc stationary resolver on the same replay payload
  -> PT21STJ1 + canonical stationary trace
  -> PT21SGN1 required-sign packet rebuilt from the same replay disks
  -> directed-Arb one-sided Turing inputs for [a-21,a] and [b,b+21]
  -> one authenticated PT21WBF1 frame
```

It does **not** close PT21.  The stream is deliberately nonterminal: it carries
no `PT21BLK1`, no count telescoping, and no analytic realization.  Hardy-Z
endpoint realization, main multiplicity realization, the analytic Turing
theorem, and the PT21 source claim all remain false, and
`all_window_fused_stream` remains false because no source-wide run exists.

## What this replaces

Before this change the three adapter inputs came from a *standalone assembly
channel*: separate processes wrote a required-sign packet, a stationary trace,
and a Turing artifact per block as retained files, and an operator wrote a
JSON-lines manifest naming them.  The fused worker produced none of the three.

Now the worker produces all three in the same ordered commit that already
writes `PT21EVT1`, and
[`tg_verifier/platt_pt21_block_input_stream.py`](../../tg_verifier/platt_pt21_block_input_stream.py)
drives the existing exact-rational adapter and the pinned native shard
finalizer straight from that stream.  No per-block artifact is retained and no
manifest exists.  What is *not* eliminated is the adapter process itself: the
`PT21BLK1` bytes are still produced by the Python adapter, not by the worker.

## Fail-closed rules preserved and added

The worker already failed a shard when any required disk was invalid *or*
sign-ambiguous.  Every new stage fails the same way:

* `platt_pt21_required_sign_packet::encode_packet` recomputes each DD sign with
  the same rule the independent Python decoder applies and throws on an invalid
  or ambiguous disk, so a completed transform with an unresolved finite
  predicate cannot produce a packet, a Turing artifact bound to that packet's
  digest, or a frame;
* the Turing core requires a 256-bit containment replay of every retained
  128-bit interval and a strictly positive sign for each required positive
  input;
* the frame encoder re-decodes its own bytes with the canonical parser before
  writing them; and
* the stream is published create-only, and only after every frame and the
  terminal footer succeed.  An early failure leaves no artifact.

## Honest `source_packet` binding

`PT21SGN1`'s `source_packet_bytes` / `source_packet_sha256` name the *upstream
input* bytes that produced the window.  V1 bound its 31 MB source packet there.
V2 has no such packet, so the worker binds the exact 312-byte authenticated
Gamma V2 stream record for the same logical block — the actual input the
accumulator and transform consumed.  No event digest, scanner Merkle root, or
other output commitment is ever placed in that field.

## Wire

```text
256-byte PT21WBH1
  first block, count, Gamma/producer/resolver/FLINT identities,
  algorithm-domain digest, finite-qualification flag, packet byte width,
  header digest

one PT21WBF1 per block
  208-byte prefix with all five payload lengths and all five payload digests
  621,202-byte PT21SGN1 required-sign packet
  192-byte PT21EVT1
  400-byte PT21STJ1
  canonical stationary trace
  canonical one-sided Turing artifact
  32-byte domain-separated frame digest

192-byte PT21WBT1
  range, frame/packet/trace/Turing totals, frame-stream digest,
  header digest, Gamma-stream digest, footer digest
```

The producer is
[`tg_platt_pt21_block_input_stream.hpp`](../../gpu/include/sparkinterval/tg_platt_pt21_block_input_stream.hpp);
the second, independent implementation is the Python module above.  The
decoder checks exact lengths, reserved bytes, monotone block order, every
payload digest, the frame digest, the `PT21EVT1`/`PT21STJ1`/trace linkage, the
packet's window centre against the frame's block, the packet's structural and
sign invariants, canonical Turing JSON, the Turing artifact's binding to the
packet digest, footer totals, exact EOF, and the pinned whole-stream digest.

## Byte identity

`reference/tg_platt_pt21_block_input_stream_kat.cpp` emits a two-frame stream
from the *same* producer header the worker uses and the same exact-rational Arb
core.  `tests/test_tg_platt_pt21_block_input_stream.py` decodes it, re-encodes
every frame plus the header and footer with the independent Python encoder, and
requires byte equality with the native bytes.  A separate known answer requires
that the `PT21BLK1` records produced by streaming a frame sequence equal, byte
for byte, the records `adapt_block` produces from the same three inputs
supplied as files.  Header, frame, payload, footer, truncation, and trailing
mutations all fail closed.

The KAT's disks are synthetic, so its real Arb counts deliberately do not close
the Turing equation; that is why the `PT21BLK1` byte-identity known answer uses
the engineered adapter fixture instead.

## Bounded GB10 measurements

All figures below are 2026-07-26 local measurements on a **GB10** (DGX Spark),
not an H100, on the first 64 source blocks.  Both binaries reported
`build_profile.release_performance_build = true`.

| measurement | result |
|---|---:|
| accepted blocks | `64 / 64` |
| invalid or ambiguous required disks | `0` |
| direct events | `226,264` |
| stationary candidates resolved | `172 / 172` |
| resolved multiplicity slots | `344` |
| GPU rate, block stage | `10.4942` blocks/s |
| GPU rate, unmodified V2 worker, same input | `10.5459` blocks/s |
| one-time workspace/table setup | `37.88 s` |
| total required-sign packet construction | `0.0394 s` |
| total in-worker Arb Turing construction | `0.1234 s` |
| total block-input serialization | `1.3958 s` |
| block-input stream bytes | `40,612,960` |
| independent Python stream validation | `4.05 s` |
| adapter-plus-finalizer drive of the same stream | `16.12 s` |

The three joined stages therefore cost about `1.56 s` of the `44.09 s` total
wall time for 64 blocks on this host, and the GPU rate is within noise of the
unmodified worker.  The `16.12 s` adapter pass, about `3.97` blocks/s, is the
binding local bottleneck and is Python, not FLINT or Arb.

Retaining the block-input stream is not a production design: at `634,578`
bytes per block the full source range would be about `1.88 PB`.  Production
must use the FIFO form so frames disappear after the adapter consumes them.

## The 64-block chain actually closes

Driving the same 64-block stream through the adapter and the pinned native
finalizer produced a `20,992`-byte `PT21SHD1/PT21SFT1` archive with

```text
first_count  32130158315
last_count   32130375861
main slots      217546
stationary resolutions 172
sparse refinements       0
archive sha256 69e8c5c7c628f1db3ec8ebb5faaa11be51e512ddddc704ebd73621d18b08bce0
```

and the independent Python `replay-shard` rescanned every retained record and
reproduced all of it.  `first_count` equals the published boundary count
`N(10^10) = 32130158315`.  That is a finite arithmetic agreement between the
directed-Arb Turing quotients, the DD sign events, and the published value; it
is **not** the analytic theorem, and 64 blocks is not 2,966,443,783 blocks.

## Build and run

```bash
cmake -S . -B build/pt21-block-stage \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON \
  -DSPARKINTERVAL_FLINT_PLATT_ROOT=/path/to/flint-3.6 \
  -DSPARKINTERVAL_FLINT_PLATT_PREFIX=/path/to/flint-3.6-install
cmake --build build/pt21-block-stage --target \
  sparkinterval-tg-platt-block-stage-qualification \
  sparkinterval-tg-platt-pt21-block-input-stream-kat \
  sparkinterval-tg-platt-pt21-native-finalizer

build/pt21-block-stage/sparkinterval-tg-platt-block-stage-qualification \
  GAMMA_V2_STREAM 0 64 \
  --expected-stream-sha256=HEX \
  --event-stream-output=events.bin --producer-sha256=HEX \
  --inline-stationary-output=inline.bin \
  --resolver-sha256=HEX --flint-sha256=HEX \
  --block-input-output=block-inputs.pt21wb

python3 tools/tg_platt_pt21_block_input_stream.py validate \
  block-inputs.pt21wb --expected-stream-sha256=HEX --pretty

python3 tools/tg_platt_pt21_block_input_stream.py shard-archive \
  block-inputs.pt21wb --expected-stream-sha256=HEX \
  --worker PINNED_WORKER --finalizer PINNED_FINALIZER \
  --expected-finalizer-sha256=HEX --output shard.pt21 \
  --first-block 0 --block-count 64 \
  --plan-sha256=HEX --prefix-evidence-sha256=HEX --bounded-test
```

The strict `sm_90` variant is
`sparkinterval-h100-tg-platt-block-stage-qualification`, built with
`-DSPARKINTERVAL_BUILD_H100_NATIVE=ON`.  It rejects a device that is not an
NVIDIA H100 before source initialization, so it compiles but does not run on a
GB10.

## Remaining boundary

1. No source-wide run.  Width usefulness, candidate frequency, and resolver
   depth are sampled at 64 low blocks only.
2. `PT21BLK1` is still produced by the out-of-process Python adapter at about
   `3.97` blocks/s.  The adapter contract must be ported into the native worker
   before an end-to-end source rate exists.
3. The adapter's file-based API means the driver writes the three payloads into
   an ephemeral private directory per block.  Nothing is retained, but the
   in-process API is still file-shaped.
4. The compact frame does not retain the resolver's supplied candidate rows or
   sparse-refinement payload, so candidate completeness still cannot be
   recomputed from the frame alone.
5. No physical H100 measurement, no attested execution, no prefix admission,
   and no analytic realization of Hardy Z, the multiplicity slots, or the
   one-sided Turing inequalities.
