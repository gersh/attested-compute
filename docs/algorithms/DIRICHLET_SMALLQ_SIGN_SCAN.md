# Small-q semantic sign scan

`tg_dirichlet_booker_smallq_sign_scan.py` is the bounded-memory production
stage immediately after the `TGDBSSG1` semantic reducer. It consumes one
complete q-level two-bit sign artifact and emits a deterministic `TGDBSZR1`
artifact containing:

- every maximal range of ambiguous samples, for later refinement; and
- every interval between consecutive resolved samples whose signs are
  opposite.

The scan first reconstructs and replays the canonical primitive-character
roster. It strictly validates the semantic reducer receipt, plan, ordered
batch partition, parity mapping, source grid, control hash, roster hash,
artifact size, and every sign code. Reserved code `3`, nonzero padding,
missing coverage, a changed digest, and trailing bytes fail closed.

## Wire format and replay

The fixed header binds the plan, time-tail control, character roster, complete
sign artifact, and semantic reducer receipt by SHA-256. Each character then
has one fixed summary followed by fixed-size event records in source order.
The summary retains ambiguous, negative, and positive sample counts plus both
event counts. Ambiguity ranges use inclusive sample indices. Opposite-sign
records retain both resolved endpoint indices and both endpoint codes.

Materialization is single-pass over the packed signs and uses configurable
bounded chunks. The scalar and NumPy implementations produce identical bytes
independently of chunk boundaries. The replay command reads the original sign
artifact again, regenerates every character header and event, compares the
artifact byte for byte, checks EOF and all global totals, and emits a distinct
checker receipt.

The NumPy backend constructs the canonical wire records in bounded structured
arrays instead of calling Python once per event. The dtype has literal offsets
`0,1,8,16`, a 24-byte item size, little-endian 64-bit endpoints, and
zero-filled padding. Ambiguity closures and opposite-sign brackets are each
already trigger-sorted; a `searchsorted` merge inserts a range before a
bracket at an equal trigger, exactly matching the scalar
close-range-then-transition rule. The writer and independent replay checker
consume the resulting bytes in blocks of at most 8 MiB. No artifact field,
hash, receipt, or mathematical claim changes.

The scalar implementation remains an independent byte oracle. Focused tests
compare 102 all-equal, alternating, boundary-sensitive, and deterministic
random patterns at six chunk sizes, including ambiguity runs and sign
transitions spanning chunks. They compare complete event bytes and every
summary count, not merely event totals.

The event record is 24 bytes. Its total size depends on the observed number of
ambiguity ranges and sign transitions and can exceed the packed two-bit input.
No genuine source-scale timing or event-density measurement exists yet, so
both receipts retain `source_scale_measured: false` and
`production_ready: false`.
A production composition should stream this output directly into refinement
and Turing aggregation, or replace the fixed records with a separately
replayed delta encoding after measuring the real event distribution.

```bash
python3 tools/tg_dirichlet_booker_smallq_sign_scan.py materialize \
  plan.bin batches/ signs.bin semantic-reducer.json \
  sign-scan.bin sign-scan-producer.json

python3 tools/tg_dirichlet_booker_smallq_sign_scan.py verify \
  plan.bin batches/ signs.bin semantic-reducer.json \
  sign-scan.bin sign-scan-producer.json sign-scan-checker.json

python3 tools/tg_dirichlet_booker_smallq_sign_scan.py --pretty \
  inspect sign-scan.bin
```

## Local-file vector benchmark

The benchmark command writes canonical event payload bytes to an actual local
file, calls `fsync`, then reads and hashes the complete file. Template
generation is timed separately. It refuses to replace an existing output
unless `--overwrite` is explicit.

```bash
PYTHONPATH=. uv run --with numpy \
  python3 tools/benchmark_tg_dirichlet_booker_smallq_sign_scan.py \
  /mnt/local-nvme/tgdbszr-events.bin \
  --codes 200000000 \
  --chunk-codes 1048576 \
  --remove-output --pretty
```

On 2026-07-22, one process on the local aarch64 DGX Spark host and its ext4
NVMe produced the following synthetic sensitivity. The deterministic
1,048,576-code template was repeated; this is an encoder/storage benchmark,
not a source-sign run.

| ambiguity probability | events | bytes | encode + write + fsync | codes/s | event bytes/s | immediate hash read |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0` | `38,628,032` | `927,072,768` | `0.8857794 s` | `225,789,852` | `1.0466 GB/s` | `2.1437 GB/s` |
| `0.001` | `38,831,183` | `931,948,392` | `1.634141709 s` | `122,388,407` | `0.5703 GB/s` | `2.1296 GB/s` |

The zero-ambiguity event density was `0.19314016`. A purely linear projection
over the exact `4,729,082,453,090` small-q codes gives about
`913,375,741,643` events, `21.921` TB of event records, `5.82`
single-process hours for one encode, and `11.64` core-hours for encode plus
replay. At the immediate hash sensitivity, the producer's separate
full-artifact hash adds about `2.84` hours, for roughly `14.5` serial hours
before reading and decoding the two 1.182-TB sign passes.

The `0.001` ambiguity sensitivity projects `10.73` hours for one encode and
`21.47` core-hours for encode plus replay. These extrapolations assume a
repeated synthetic distribution, cached template, constant throughput,
uncontended local storage, and no q-file scheduling overhead. The immediate
hash may read from page cache despite the preceding durable `fsync`. They are
not Azure timings, do not predict source ambiguity density, do not include the
upstream 226.996-TB disk stream, and do not justify changing
`source_scale_measured` or `production_ready`.

The next production benchmark should consume one genuine q-level
`TGDBSSG1`, include packed-code read/decode/hash and independent replay, and
measure concurrent q jobs against the target Azure storage tier. An H100 is
not used by this encoder; a GPU route would need a separately reviewed
prefix-sum/compaction kernel and would still face the retained-event storage
boundary.

## Exact trust boundary

An opposite pair is only an arithmetic sign-transition interval. Turning it
into a zero lower bound requires a separate theorem identifying the codes with
one continuous completed-L evaluator. The stage does not infer exact
multiplicity, does not deduplicate characters, and performs no interpolation,
upsampling, direct exception refinement, Turing count, or GRH proof.

The semantic signs remain conditional on the upstream DFT containment. A
confidential-compute receipt or independently replayable DFT certificate must
establish that earlier boundary before raw disks can be discarded. This scan
implements the bounded-memory format handoff from the 1.182-TB compact sign
family to explicit refinement and sign-transition work. Its source-scale
runtime and storage behavior remain to be measured, and it does not by itself
close Platt's Theorem 7.1.

Focused verification:

```bash
PYTHONPATH=. uv run --with pytest --with numpy pytest -q \
  tests/test_tg_dirichlet_booker_smallq_sign_scan.py
```
