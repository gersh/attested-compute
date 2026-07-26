# PT21 bounded persistent worker

`tools/tg_platt_pt21_persistent_worker.py` exercises a bounded, long-lived
version of the finite PT21 junction:

```text
resident CUDA event scanner
  -> PT21EVT1
resident FLINT stationary resolver
  -> PT21STJ1
resident Arb Turing-input producer
  -> exact-rational Python adapter
  -> PT21BLK1
one native shard-finalizer invocation
  -> independently replayed PT21SHD1/PT21SFT1 archive
```

This is an optimization and integration witness, not a source theorem.  It
repeats the explicitly synthetic block-zero fixture.  It does not pretend
that repeated block zero is a gap-free shard, does not extrapolate a source
ETA, and leaves every Hardy-Z, multiplicity, analytic-Turing, attestation,
production, and source-claim flag false.

## Bounded framed protocols

The existing native executables retain their one-shot interfaces as the
reference implementation.  Their new persistent modes accept an exact number
of binary requests and then exit.

The CUDA/FLINT junction request is 24 bytes:

| offset | bytes | value |
|---:|---:|---|
| 0 | 8 | `PT21JRQ1` |
| 8 | 4 | little-endian version `1` |
| 12 | 4 | request bytes `24` |
| 16 | 8 | little-endian block |

The transport field has the full source width, but this benchmark executable
accepts only block zero: its resident disks are the explicit block-zero
synthetic fixture and must not be relabeled as another source block.  A
source-scale worker must feed the genuine V2 transform output instead.

Its response starts with a 40-byte `PT21JRS1` header.  The header binds the
block, total frame length, the exact 192-byte `PT21EVT1` length, exact
400-byte `PT21STJ1` length, stationary-trace length, and zero failure flags.
The three payloads follow without hex or a JSON benchmark envelope.

The Arb request is 56 bytes:

| offset | bytes | value |
|---:|---:|---|
| 0 | 8 | `PT21TRQ1` |
| 8 | 4 | little-endian version `1` |
| 12 | 4 | request bytes `56` |
| 16 | 8 | little-endian block |
| 24 | 32 | required-sign-packet SHA-256 |

Its `PT21TRS1` response has a 16-byte header followed by the same canonical
directed-Arb JSON artifact emitted by one-shot mode.  Retaining that canonical
artifact is intentional: the exact-rational adapter and the existing
commitment chain consume its bytes.

Both processes:

- are opened without following symbolic links;
- are hashed from the descriptor used for `/proc/self/fd/...` execution;
- have a caller-selected request bound (`1..1000` for the junction and
  `1..10000` for Arb);
- reject truncated, malformed, out-of-campaign, or trailing request data;
- require clean native process exit after the exact request count, while the
  bounded driver rejects truncated, malformed, or trailing response data;
- release no accepted response with nonzero finite failure flags; and
- produce no stderr on an accepted run.

`SparkInterval.Zeta.PT21PersistentWorkerWire` gives all four request/response
envelopes total Lean parsers.  Its junction-response checker delegates the
embedded records to the existing `PT21EventWire` and
`PT21StationaryJunctionWire` checkers and proves that acceptance preserves
their common block and event-record digest linkage.  Fresh `#print axioms`
reports only Lean's base trio (`propext`, `Classical.choice`, and
`Quot.sound`).

## Byte identity and replay

The bounded driver first runs the ordinary one-shot block chain.  Every
persistent request must then reproduce these bytes exactly:

- `PT21EVT1`;
- `PT21STJ1`;
- directed-Arb Turing artifact;
- fused source trace;
- exact-rational block artifact; and
- `PT21BLK1`.

The final retained record is independently replayed by the existing Python
checker and passed through the existing native finalizer.  The resulting
bounded shard archive must also be byte-identical to the one-shot archive and
pass the independent native-shard replay.

The source-independent bounded values currently include:

```text
PT21EVT1 SHA-256
  38512c0d8e20f2dd612fb71e13821ba6d4ad82565f0c49f483fc92fd703bcb7d
Turing artifact SHA-256
  fd8f83a9363928e62a78f4a27134f2fd231576c522a3e254e36e1694c3576eb7
```

`PT21STJ1`, its stationary trace, the source/block artifacts, the final
`PT21BLK1`, and the shard all bind measured executable and/or adapter-source
identities, so their digests deliberately change when those sources are
rebuilt or edited.  Their known answer is byte equality between the one-shot
and persistent executions under the same selected identities.

## Bounded local performance

A seven-request DGX Spark run on 2026-07-25 measured:

| component | time |
|---|---:|
| one-shot reference, including independent replay and finalization | 1.329 s |
| median one-shot CUDA/FLINT process (7 runs) | 0.5570 s |
| first persistent CUDA/FLINT response, including CUDA initialization | 0.4635 s |
| median warm CUDA scan/replay plus FLINT response | 0.04740 s |
| median one-shot Arb process (25 runs) | 0.001800 s |
| median warm Arb response | 0.000424 s |
| median exact-rational adapter | 0.1775 s |
| persistent producers plus adapter, amortized | 0.2998 s/request |
| one independent retained-chain replay | 0.2298 s |
| one native shard finalization | 0.00562 s |

These are bounded component timings, not source-scale rates.  In particular,
the synthetic packet is resident and repeated; no source transform or
source-sized I/O was measured.

Every persistent request reruns the actual CUDA event scan and its host
replay; only the device allocation and synthetic source samples remain
resident.  The persistent protocol made that bounded warm CUDA-scan/FLINT
response about `11.75x` faster than the median one-shot process and the warm
Arb response about `4.25x` faster.  These ratios measure process/initialization
amortization on one synthetic fixture, not source arithmetic throughput.  A
second optimization caches exact sample intervals only
when they are needed and uses outward-widened binary64 intervals merely as a
strict-comparison filter.  Every inconclusive comparison falls back to
`Fraction`, and the generated artifact is checked byte-for-byte against the
one-shot reference.  On the same bounded fixture this reduced the median adapter from
about 0.378 seconds to 0.177 seconds.

`SparkInterval.Zeta.PT21StationaryCandidateFilter` proves that an enclosing
outer interval can soundly certify both the positive and negative strict
stationary predicates, can soundly reject a separated reverse comparison,
can reject an exact constant middle pair, and can certify a strictly signed
exact interval from the corresponding endpoint of an enclosing box.  The
same filter now precedes the fixed-2176-bit sign and stationary comparisons
in the independent C++ event replay; every inconclusive C++ branch still
executes the original fixed-integer predicate.  Those theorems use only the
base trio.  The remaining low-level premise—that the binary64
`nextafter` widenings really enclose the executed additions/subtractions—is
kept explicit as an IEEE/architecture refinement obligation; the code never
uses a failed or inconclusive fast comparison as a decision.

An independent five-run audit after enabling the C++ replay filter used seven
requests per run and measured a median warm junction response of `0.04255 s`
while preserving the two source-independent output digests above.  The
median exact Python adapter remained `0.1785 s`, so the source-scale design
still must overlap the CPU replay with the GPU and replace the Python
artifact builder rather than extrapolate this bounded fixture.

The remaining measured bottleneck was the Python exact-rational artifact
construction and validation, not FLINT or Arb.  That replay now has a compact
native streaming checker, documented in
[PT21 native v2 artifact builder](PLATT_PT21_NATIVE_ARTIFACT_BUILDER.md).  It
preserves byte identity, and the Python reference finalizer remains the
independent implementation the differential known answers compare against.

A 2026-07-26 DGX Spark measurement on the same repeated block-zero fixture,
timing whole `PT21BLK1` adaptations, gave:

| stage | median | runs |
|---|---:|---:|
| Python reference `build_block_artifact` | 0.16435 s | 15 |
| Python reference `adapt_block` | 0.16699 s | 15 |
| native fast-path adapter, pinned one-shot | 0.06495 s | 15 |
| native fast-path adapter, pinned session | 0.06780 s | 15 |

That is `2.46x` on the whole record adapter for byte-identical `PT21BLK1`,
source-trace, and block-artifact output.  The exact-rational replay is no
longer the largest component: the two remaining costs are the native build
itself (median warm framed response `0.02649 s`, which includes its own
SHA-256 over the 2.24 MiB document) and the Python side's independent
canonical/identity revalidation of the returned bytes (median `0.03141 s`).

## Opt-in native artifact builder in this worker

The bounded worker can now run that native builder in place of the Python
exact-rational v2 construction.  It is never selected implicitly: both

```text
--native-artifact-builder PATH
--expected-native-artifact-builder-sha256 SHA256
```

must be supplied together, the image is copied into a sealed `memfd` and
re-hashed before execution, and one builder process serves the whole bounded
batch.  Omitting them keeps the Python reference builder, which stays the
default.

Nothing about the verification structure changes.  The one-shot reference
chain that runs first in the same invocation always uses the Python reference
builder, so the existing per-request byte comparison of `PT21EVT1`,
`PT21STJ1`, the stationary trace, the Turing artifact, the source trace, the
block artifact, and `PT21BLK1` is the differential oracle for every fast-path
response.  The independent retained-chain replay and the native shard replay
are unchanged and still run.

`adapter_sources_sha256`, and therefore `chain_commitment_sha256`, bind the
six Python reference adapter sources.  The native builder does not enter that
identity: it must reproduce their bytes, and it is reported separately as
`native_artifact_builder_sha256` with
`artifact_builder_implementation: pinned_native_fastpath`.

### Measured effect, 2026-07-26, same host and fixture

Three runs per configuration, block zero, medians of the reported per-run
values.  Every one of the twelve runs produced the same
`chain_commitment_sha256`, `shard_archive_sha256`, `block_record_sha256`,
`event_record_sha256`, `stationary_junction_record_sha256`,
`stationary_trace_sha256`, and `turing_inputs_sha256`, and every request in
every run was byte-identical to the one-shot reference.

Seven requests per run:

| field | Python reference | pinned native fast path |
|---|---:|---:|
| `persistent_seconds_per_request` | 0.32020 s | 0.22055 s |
| `exact_adapter_median_seconds` | 0.18035 s | 0.08158 s |
| `junction_warm_response_median_seconds` | 0.04247 s | 0.04247 s |
| `independent_replay_seconds` | 0.23935 s | 0.23369 s |

Three requests per run, matching the earlier bounded runs:

| field | Python reference | pinned native fast path |
|---|---:|---:|
| `persistent_seconds_per_request` | 0.43668 s | 0.35469 s |
| `exact_adapter_median_seconds` | 0.18409 s | 0.09643 s |

So the end-to-end bounded rate improves by `1.45x` at seven requests and
`1.23x` at three, while the adapter window itself improves by `2.21x` and
`1.91x`.  The end-to-end gain is smaller than the adapter gain because the
per-request cost also contains the warm CUDA scan and FLINT response, the
amortized first CUDA response, the stationary/Turing sidecar validation, and
the byte comparisons against the one-shot reference.

The `exact_adapter_median_seconds` window is wider than the artifact build:
it also covers the chain commitment, the `PT21BLK1` binding, and
`_validate_multiplicity`, which re-parses the whole 2.24 MiB block artifact.
That independent check is deliberately retained.

With the fast path enabled the reported `performance_bottleneck` becomes
`native_artifact_build_and_python_canonical_revalidation`.  The adapter window
is still the largest single per-request component (`0.08158 s` against
`0.04247 s` for the warm junction), but it no longer dominates by four times.

These remain bounded component timings on one resident, repeated synthetic
fixture.  No source transform, source-sized input/output, or source-scale rate
was measured, and they do not justify a full-campaign ETA.

## Reproducibility caution: the pinned FLINT lives on volatile storage

Every measurement and every pinned digest above depends on the upstream FLINT
3.6 build at `/tmp/flint-3.6-install`, whose real object
`libflint.so.24.0.0` has SHA-256
`5e7cbb0c68aa9cee8f940f98914600ce7eeef3ef03d30d7ad635ac744cfdaeea` and size
`69975536`.  That path is volatile storage: it disappears on reboot, after
which none of the FLINT-dependent digests here, including
`chain_commitment_sha256`, can be reproduced without rebuilding the same
upstream and re-pinning it.  This is recorded, not fixed.

Note also that the worker requires the real shared object, not the
`libflint.so` alias.  The loader pin refuses to follow symbolic links and
fails with `Too many levels of symbolic links` if the alias is passed.

## Run and verify

```bash
python3 tools/tg_platt_pt21_persistent_worker.py \
  --junction-executable \
    build/pt21-junction/sparkinterval-tg-platt-stationary-junction-benchmark \
  --turing-executable \
    build/tg-production-kat/sparkinterval-tg-platt-pt21-turing-inputs \
  --flint-library /path/to/libflint.so.24.0.0 \
  --finalizer-executable \
    build/platt-fused/sparkinterval-tg-platt-pt21-native-finalizer \
  --output-directory /new/empty/directory \
  --requests 7 --pretty

# Optional, opt-in only: both flags are required together.
python3 tools/tg_platt_pt21_persistent_worker.py \
  ... \
  --native-artifact-builder \
    build/sparkinterval-tg-platt-pt21-native-artifact-builder \
  --expected-native-artifact-builder-sha256 SHA256 \
  --output-directory /new/empty/directory \
  --requests 7 --pretty

TG_PLATT_PT21_NATIVE_ARTIFACT_BUILDER=\
build/sparkinterval-tg-platt-pt21-native-artifact-builder \
python3 -m unittest -v \
  tests.test_tg_platt_pt21_persistent_worker \
  tests.test_tg_platt_pt21_bounded_block_chain \
  tests.test_tg_platt_pt21_fused_artifact \
  tests.test_tg_platt_pt21_native_record_adapter

lake build SparkInterval.Zeta.PT21PersistentWorkerWire
lake env lean SparkInterval/Tests/PT21PersistentWorkerWireTest.lean
lake build SparkInterval.Zeta.PT21StationaryCandidateFilter
lake env lean SparkInterval/Tests/PT21StationaryCandidateFilterTest.lean
```

The tests include fixed request-frame known answers, malformed-frame
rejection, 2,003 deterministic directed-filter/exact-reference comparisons,
source-independent digest known answers, per-request byte equality, independent retained
replay, and native shard replay.  They also include a fail-closed check that
the native artifact builder cannot be half-selected from either the API or the
CLI, and an end-to-end known answer that runs the same bounded batch with and
without the fast path and requires all seven retained digests, including
`chain_commitment_sha256`, to be equal.  A one-request persistent CUDA/FLINT
run under `compute-sanitizer --tool memcheck` reported
`ERROR SUMMARY: 0 errors`.
