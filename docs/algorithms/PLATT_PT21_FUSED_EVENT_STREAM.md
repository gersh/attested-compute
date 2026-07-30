# PT21 fused three-stream event stage

This component closes one source-scale junction in the optimized PT21 worker:

```text
authenticated Gamma V2
  -> DD accumulator
  -> DD source transform
  -> resident 25,741-disk required view
  -> exact left/main/right CUDA scanner
  -> authenticated PT21EVT1 stream
```

It does not close the PT21 computation. `PT21EVT1` is deliberately distinct
from `PT21BLK1`: stationary candidates have not undergone Gaussian--sinc
resolution, there is no one-sided Turing count, and the finite event digest
has not been proved to realize Hardy Z.

## Why scanning precedes interpolation

The DD transform already produces the source cardinal lattice with spacing
`21/512`. The source algorithm checks those lattice disks directly. It invokes
the 140-term Gaussian--sinc evaluator only when a same-sign strict `stat_pt`
triple asks an adaptive dyadic question. Interpolating every lattice point
would therefore duplicate work and change the reviewed control flow.

The fused worker now calls
`platt_event_scan::scan_source_required_samples` directly on
`platt_dd_transform::device_required_samples`. The scanner uses:

| stream | inclusive sample range |
|---|---:|
| left one-sided Turing flank | `[-12800,-12288]` |
| main isolated-count window | `[-12288,12288]` |
| right one-sided Turing flank | `[12288,12800]` |

It exactly certifies every DD sign, reproduces the source’s strict interval
comparisons, stably compacts direct events and stationary candidates, checks
the duplicated shared endpoints, and computes a device SHA-256 Merkle root
over the 25,741 disks/signs, stream summaries, direct events, and stationary
candidates.

A candidate certifies zero multiplicity slots. For a stream edge `e`, a
direct event contributes

```text
nleft_units = -e
nright_units = stream_edge_count - e - 1
multiplicity_slots = 1
```

The later stationary resolver must produce two touching strict brackets and
charge the conservative source cell twice before those slots or weights may
enter Turing closure.

## Compact wire

The fused worker accepts:

```text
--event-stream-output=PATH
--producer-sha256=HEX
```

Both options are required together. `PATH` may be absent, in which case the
worker writes a create-only regular artifact through a private partial file,
or it may name an existing FIFO. A regular artifact is linked into place only
after the complete pinned Gamma stream, every event record, and the terminal
event footer succeed. A FIFO consumer must likewise withhold publication
until it receives and authenticates the footer. Early EOF, broken pipe,
trailing input, a late Gamma-footer failure, or any scanner failure yields no
accepted event stream.

One `PT21EVT1` record is 192 bytes:

| offset | bytes | field |
|---:|---:|---|
| `0` | 8 | magic `PT21EVT1` |
| `8` | 4 | version `1` |
| `12` | 4 | record bytes `192` |
| `16` | 8 | logical block |
| `24` | 16 | failure flags, certified-sample count, digest-valid flag, zero reserve |
| `40` | 12 | three direct-event counts |
| `52` | 12 | three stationary-candidate counts |
| `64` | 12 | three certified direct-slot counts |
| `76` | 4 | exact unresolved-stationary total |
| `80` | 24 | three signed `nleft` unit sums |
| `104` | 24 | three signed `nright` unit sums |
| `128` | 32 | CUDA scanner artifact Merkle root |
| `160` | 32 | SHA-256 of the first 160 bytes under the record domain |

The 192-byte `PT21EVH1` header binds shard geometry, the externally pinned
whole Gamma-stream digest, the externally pinned measured-producer digest,
and event contract digest
`7c3a3e984b71315a2fdd9407b4cfc5746ce9d25e1f633cd9f897f2a92d8de1f8`.
The contract digest fixes the required range, all three stream ranges,
capacities, lattice spacing, and reviewed upstream commit.

The 192-byte `PT21EVF1` footer binds the exact block range, total direct and
stationary counts, record-stream SHA-256, header SHA-256, Gamma-stream
SHA-256, and its own domain-separated digest. No terminal footer is emitted
until the Gamma reader has authenticated its global footer and exact EOF.

`tg_verifier/platt_pt21_event_record.py` is an independent bounded-memory
regular-file replay. It rechecks every signed weight and count, all three
domains, exact geometry, terminal totals, pins, file size, and EOF.
`SparkInterval.Zeta.PT21EventWire` gives each record an exact Lean parser,
Boolean checker, soundness theorem, and pending-stationary handoff theorem.
The Lean checker treats the event Merkle root as an opaque finite commitment;
it does not infer an analytic realization from a digest.

## Bounded measurements

The event-scan benchmark and fused V2 worker stdout reports include:

```json
{"build_profile":{"cmake_build_config":"Release","ndebug_defined":true,"release_performance_build":true}}
```

Only a report with `release_performance_build:true` is eligible to support a
performance number. Debug and empty-build-type executables remain useful for
finite known-answer and fail-closed tests, but their elapsed times are
qualification diagnostics. The profile is compiled into the executable; it
is not a caller-supplied label. It does not alter event-stream wire bytes or
the existing CLI.

Configure a fresh Release tree to reproduce scanner throughput:

```bash
cmake -S . -B build/pt21-event-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/pt21-event-release --target \
  sparkinterval-tg-platt-event-scan-benchmark
build/pt21-event-release/sparkinterval-tg-platt-event-scan-benchmark \
  --mode valid --iterations 1000
TG_PLATT_EVENT_SCAN_BENCHMARK=\
build/pt21-event-release/sparkinterval-tg-platt-event-scan-benchmark \
  python3 -m unittest -v tests.test_tg_platt_event_scan
```

The portable two-record KAT is produced by
`reference/tg_platt_event_record_kat.cpp` and independently accepted by the
Python and Lean decoders. Header, record, footer, prefix, suffix, pin, signed
weight, count, digest, and create-only mutations fail closed.

A real first-64-block V2 run on the local GB10 produced the following
device-stage baseline.  This table predates the full pinned replay ring and
isolates the transform-plus-event cost; the later differential reports the
current end-to-end event replay:

| measurement | result |
|---|---:|
| accepted blocks | `64 / 64` |
| required disks certified | `1,647,424` |
| invalid or ambiguous disks | `0` |
| direct events | `226,264` |
| stationary candidates, still unresolved | `172` |
| GPU elapsed | `7.1358525 s` |
| fused transform-plus-event rate | `8.9687952 blocks/s` |
| prior comparable transform-only rate | `9.2043 blocks/s` |
| observed rate reduction | `2.56%` |
| scanner workspace | `7,750,989` device bytes |
| 64-result pinned host ring | `25,088` bytes |
| authenticated event artifact | `12,672` bytes |

This is a bounded GB10 component measurement, not an H100 calibration and not
a source-wide width audit. The observed `172/64` candidate distribution is
useful sizing evidence, but the interpolation depth and candidate frequency
must be sampled at interior and terminal heights before sizing the FLINT lane.

## Storage impact

One retained `PT21SGN1` packet is 621,202 bytes. Retaining one for every block
would require exactly `1,842,760,810,887,166` bytes, or 1.8428 PB decimal.
The fused stage retains none of them as an artifact.  It now holds at most a
bounded replay ring transiently.

All `PT21EVT1` records would occupy `569,557,206,336` bytes
(`530.441 GiB`) if stored separately. That is not the production design:
records are intended to travel through an authenticated FIFO into a
persistent native stationary/Turing stage and then disappear.  Exact replay
now uses the bounded pinned snapshots described below; no source packet is
written to disk.

## Implemented safe source-scale overlap

The V2 worker no longer calls synchronous `replay_and_check` from the GPU
submission loop or flushes a summaries-only ring after 64 blocks.  The event
scanner exposes an opaque pinned `ReplayCapture`; the worker uses these in a
bounded producer/consumer ring:

1. After each device scan, enqueue copies of the exact 25,741 required disks,
   status, all three summaries, and the fixed-capacity direct/stationary
   arrays into one pinned slot on the same CUDA stream.
2. Record a CUDA event for that slot before the next transform is allowed to
   overwrite either the required view or scanner workspace.
3. Let a bounded CPU pool wait for slot events and execute the same
   independent fixed-2176-bit replay.  A commit condition variable restores
   exact block order before updating totals or writing `PT21EVT1`.
4. Apply back pressure before reusing a slot and publish outputs only after
   every block, the Gamma footer, and the downstream footer are complete.

Copying maximum capacities preserves the current byte-for-byte device/host
array comparison without a count-dependent synchronization.  One slot is
`2,051,576` bytes: `617,784` required-sample bytes, `614,400` direct-event
bytes, `819,008` stationary-candidate bytes, one 48-byte status, and three
112-byte summaries.  At the measured `8.9687952` GB10 blocks/s this is only
about `18.40 MB/s`; eight slots use `16,412,608` pinned bytes.  The latest
bounded persistent audit measured at most `0.04255 s` for scan, host replay,
two-candidate FLINT resolution, and response framing together, versus
`0.11150 s` of GPU time per fused block.  The directed-Arb Turing step was
about `0.00034 s`.  Thus one ordered CPU lane has bounded local headroom, but
this is not an H100 guarantee: a faster H100 must use independently initialized
FLINT process lanes plus an ordered commit queue if the ring begins applying
back pressure.

The default is eight slots and up to eight replay threads; both are bounded
CLI parameters.  Capture events use CUDA's blocking-host-wait flag, so CPU
lanes do not burn cores while an earlier GPU window is still running.  A
post-change 64-block source differential accepted all 64 independent
replays and preserved `226,264` direct events and `172` unresolved stationary
candidates.  The one-slot/one-thread and eight-slot/eight-thread executions
produced byte-identical 12,672-byte event streams:

```text
94d3b2d0a71df3c2251bddce62a70ea8d48c2e96b30ca17e53c5de5f6a2d28ed
```

With the same frozen binary, the serialized run used `7.9190 s` of submission
wall time and reported `7.9861` GPU blocks/s; the ordered pool used `5.3767 s`
and reported `10.4750` GPU blocks/s, then drained in `0.7627 s`.  The
approximately 38-second one-time source-workspace setup dominates either
short process, so the worker reports setup, submission, replay-drain, and
post-replay timings separately.  This validates overlap mechanics and byte
identity on the GB10; it is not an H100 throughput claim.

The default `sparkinterval-tg-platt-fused-source-worker-v2` target still stops
at event replay, and its 64-block authenticated event artifact is unchanged at
`94d3b2d0a71df3c2251bddce62a70ea8d48c2e96b30ca17e53c5de5f6a2d28ed`. A distinct
[block-stage target](PLATT_PT21_BLOCK_INPUT_STREAM.md) continues through
stationary resolution and one-sided Turing inputs and streams all three record
adapter inputs; its 64 `PT21EVT1` records are byte-identical to the default
worker's, and only the stream header differs because the header binds a
different `--producer-sha256` pin. A distinct
[qualification-only inline target](PLATT_PT21_INLINE_STATIONARY.md) now calls
`resolve_replayed_block` immediately after `replay_captured`, using the same
replay-owned samples and candidates without a second scanner replay or
process hop. It emits authenticated `PT21EVT1` + `PT21STJ1` + canonical V2
precision-hull traces. This is bounded finite evidence, not a Turing input or
`PT21BLK1`, and the compact stream does not retain enough resolver input to
recompute candidate completeness independently.

Two format issues must be fixed rather than papered over:

- V2 intentionally does not create a `PT21SGN1` packet, while the current
  Turing JSON and `PT21BLK1` adapter bind that packet's SHA-256.  The event
  root is not a packet digest.  Introduce a versioned Turing/block wire that
  directly binds the authenticated Gamma-stream digest, `PT21EVT1` digest,
  and scanner root (or define an honestly source-shaped `PT21SGN2`); do not
  place an event digest in a field named as a V1 packet digest.
- The Python exact-artifact adapter measured about `0.1785 s` per bounded
  block and would cap a serial source worker below the current GPU rate.
  Port its exact Turing rounding/count equations and commitment construction
  into the native consumer, preserving independent sampled replay, before
  claiming an end-to-end source rate.

## Implemented qualification fusion and remaining terminal scheduler

The bounded
[`PT21STJ1` junction](PLATT_PT21_STATIONARY_JUNCTION.md) now consumes the
complete replay-owned disk array and canonical candidate list, proves their
link to `PT21EVT1`, runs the FLINT resolver and higher-precision replay, and
emits a fixed record binding every finite identity. The qualification worker
now performs that handoff inline and publishes `PT21IQH1/PT21IQF1/PT21IQT1`.
The source-scale terminal scheduler must still:

1. define and authenticate the resolver-input retention or attested replay
   boundary needed for a genuinely independent candidate-completeness check;
2. rerun the event scan after any sparse disk refinement;
3. connect the accepted junction to native one-sided Turing arithmetic; and
4. emit a versioned terminal block record only after Turing
   arithmetic, count telescoping,
   and every stationary resolution succeed.

`PT21STJ1` repairs this specific payload link by consuming the scanner's own
replay object and carrying the root forward. The legacy retained-packet and
Python record adapters remain unbound to this new root and are not acceptable
substitutes for the junction.

Still missing are uniform source-wide enclosure usefulness, the corrected
Appendix-C realization in Lean, physical CUDA/FLINT refinement, actual
Hardy-Z endpoint realization, multiplicity realization, analytic one-sided
Turing inequalities, a complete target-H100 benchmark, attested execution,
and the full source run. Consequently the under-one-week/$10k gate and the
PT21 source claim remain false.
