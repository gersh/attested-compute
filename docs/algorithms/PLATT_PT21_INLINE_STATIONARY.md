# PT21 qualification-only inline stationary stream

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

This path removes a finite-process boundary from the V2 Platt worker:

```text
resident required DD view
  -> one CUDA scan
  -> one captured independent host replay
  -> exact PT21EVT1 bytes
  -> FLINT stationary resolver using that same replay-owned payload
  -> PT21STJ1 + canonical V2 precision trace
  -> PT21IQF1
```

The junction runs immediately after `replay_captured`. It does not run the
scanner a second time, copy the 25,741 samples through another process, or
invoke a Python finalizer. Ordered serialization still occurs under the
existing replay-ring commit lock.

This is deliberately a separate qualification target:

```text
sparkinterval-tg-platt-inline-stationary-qualification
sparkinterval-h100-tg-platt-inline-stationary-qualification
```

The ordinary `sparkinterval-tg-platt-fused-source-worker-v2` target retains
its original CLI and output. The strict H100 target is compiled for `sm_90`
and rejects a device that is not reported as an NVIDIA H100. Neither target
turns this finite stream into a PT21 source certificate.

## Invocation and identity boundary

The qualification target adds three required arguments:

```text
--inline-stationary-output=PATH
--resolver-sha256=HEX
--flint-sha256=HEX
```

It also requires the existing `--producer-sha256=HEX` and
`--expected-stream-sha256=HEX` pins. The output path may be a create-only
regular file or an existing FIFO. A regular file is published only after all
frames, the input Gamma footer, and the inline footer succeed.

The producer, resolver, and FLINT values are caller-supplied manifest pins.
The worker rejects zero or malformed values and binds the exact bytes into
the stream, but it does **not** hash its own executable or loaded FLINT image.
An external measured manifest or attestation must establish those identities.
The JSON report consequently says:

```text
producer_sha256_self_verified = false
resolver_sha256_self_verified = false
flint_sha256_self_verified = false
identity_pins_require_external_manifest_or_attestation = true
```

## PT21IQ wire

The stream is fail-closed and ordered:

```text
256-byte PT21IQH1
  first block, count, Gamma/producer/resolver/FLINT identities,
  algorithm-domain digest, finite-qualification flag, header digest

one PT21IQF1 per block
  144-byte prefix
  192-byte PT21EVT1
  400-byte PT21STJ1
  variable canonical stationary trace
  32-byte domain-separated frame digest

192-byte PT21IQT1
  range, exact record totals, total trace bytes, frame-stream digest,
  header digest, Gamma-stream digest, footer digest
```

Every decoder checks exact lengths, reserved bytes, range arithmetic,
monotone block order, nested event/junction links, all payload digests,
canonical JSON, footer totals, exact EOF, and the four external identity
pins. Frame size is bounded by the resolver's exact 16 MiB trace cap.
Resolution rosters are independently capped at 10,000.

The bounded KAT covers altered payloads and roots, zero and wrong identities,
range overflow, truncation, trailing data, relabeled/swapped/duplicate
frames, cross-spliced headers and footers, forged totals, and a trace-cap
failure with no partial resolutions. It compares the inline `PT21EVT1`,
`PT21STJ1`, and trace bytes exactly with the existing standalone junction,
whose scanner path uses `replay_and_check`.

## Non-nested precision evidence

Arb evaluations at 128 and 192 bits are both rigorous, but interval
dependency does not imply that the 192-bit result is nested inside the
128-bit result. The version-2 stationary trace therefore retains, for each
lower, midpoint, and upper endpoint:

```text
base_interval
replay_interval
retained_hull =
  [min(base.lo, replay.lo), max(base.hi, replay.hi)]
```

The resolver rechecks that widening preserves the strict sign, independently
evaluates each endpoint again at 192 bits, and requires that fresh replay to
be contained in the retained hull. Thus the fixed `PT21STJ1` field
`higher_precision_containment_complete = 1` means

```text
fresh 192-bit replay is contained in the retained outward hull
```

and does not assert natural 192-in-128 nesting.

[`PT21PrecisionHull.lean`](../../SparkInterval/Zeta/PT21PrecisionHull.lean)
proves the architecture-independent interval facts used at this boundary:
`first_contains_hull`, `second_contains_hull`,
`contains_hull_of_both`, `replay_contains_hull_of_subset_second`,
`positive_of_hull_contains`, and `negative_of_hull_contains`. These theorems
prove interval algebra only; they do not realize FLINT/Arb evaluations as
Mathlib expressions.

The committed regression fixture
[`pt21_block0_precision_non_nesting.json`](../../tests/fixtures/pt21_block0_precision_non_nesting.json)
comes from real block 0. Its midpoint and upper 192-bit intervals are not
subsets of their 128-bit intervals. The independent Python test reconstructs
all three exact-rational hulls and checks their strict signs.

The legacy V1 trace remains the default for the standalone resolver.
Precision-hull evidence is explicitly selected by the qualification path and
uses schema `sparkinterval.tg.platt-pt21-stationary-trace.v2`. V2 pins the
base and replay precisions to 128 and 192 bits; replay increments of 63 or 65
bits fail closed.

## What the independent checker can and cannot replay

`tg_verifier.platt_pt21_inline_stationary.validate_bytes` independently
checks the complete wire, nested records, exact-rational trace geometry,
strict signs, precision hulls, and all hashes present in the stream.

The compact frame does not retain the 25,741 resolver samples, full supplied
candidate rows, or sparse-refinement payload. Therefore it cannot regenerate
the resolver input SHA-256 or prove candidate-list completeness. It reports:

```text
resolver_inputs_retained = false
resolver_input_sha256_recomputed_from_frame = false
candidate_completeness_recomputed_from_frame = false
independent_checker_complete = false
```

That limitation is intentional and must not be hidden by calling the compact
decoder a full source replay. A future independently replayable format would
need a bounded side artifact committing and retaining those resolver inputs,
or a separate attested replay service with an explicit trust boundary.

## Bounded measurements

All figures below are 2026-07-26 local GB10 qualification measurements, not
H100 performance claims.

The synthetic one-candidate KAT, measured for 40 iterations, improved from
`31.004164` to `31.281090` junctions/s after one 192-bit
`SourceInterpolator` was constructed per candidate-bearing block and passed
to both independent endpoint evaluations in the direct before/after run. The
output bytes were unchanged. After the separate fixed-capacity output-buffer
initialization described below, the final complete KAT measured `30.992692`
junctions/s; changes below one percent are measurement noise at this scale.
An interposed-call profile counted 14,560 `arb_exp` calls over ten bounded KAT
iterations but only `0.002881 s` inside `arb_exp`; Gaussian exponentials were
not the measured bottleneck, so the riskier recurrence rewrite was not
enabled.

The original one-block measurement below came from a CMake tree whose
`CMAKE_BUILD_TYPE` was empty.  That tree did not pass the Release `-O3` flags
to the independent host replay or FLINT junction:

| stage | measured value |
|---|---:|
| one-time workspace/table setup | `38.365854 s` |
| GPU arithmetic | `0.097872 s` |
| scanner replay thread | `0.538335 s` |
| stationary resolution | `0.032698 s` |
| inline serialization | `0.000784 s` |
| replay drain | `0.572160 s` |
| total wall time | `39.045677 s` |
| direct events | `3,539` |
| stationary candidates/resolutions | `1 / 1` |
| resolved multiplicity slots | `2` |
| V2 trace bytes | `4,339` |
| complete inline stream bytes | `5,555` |

A separately configured `CMAKE_BUILD_TYPE=Release` tree accepted the same
real block-0 source record with the same event/resolution counts and wire
sizes:

| stage | Release measured value |
|---|---:|
| one-time workspace/table setup | `37.919360 s` |
| GPU arithmetic | `0.121257 s` |
| scanner replay thread | `0.114181 s` |
| stationary resolution | `0.011686 s` |
| inline serialization | `0.000242 s` |
| replay drain | `0.126719 s` |
| post-replay finalization | `0.014513 s` |
| total wall time | `38.177952 s` |
| direct events | `3,539` |
| stationary candidates/resolutions | `1 / 1` |
| resolved multiplicity slots | `2` |
| V2 trace bytes | `4,339` |
| complete inline stream bytes | `5,555` |

Thus the apparent fixed-width replay bottleneck was mostly an unoptimized-host
benchmark artifact: Release replay was 4.71 times faster and Release
stationary resolution was 2.80 times faster on this one-block comparison.  A
portable-scalar versus OpenSSL SHA microbenchmark showed only a 1.24-fold
small-message SHA difference, so no new cryptographic dependency or
byte-format change was justified.  The 38-second setup remains a one-time
process cost and should be amortized over a long stream.  Campaign projections
must name their CMake build type and must not use the empty-build-type timings
as production estimates.

Both the fused V2 worker and this qualification target now report a
`build_profile` object in their stdout JSON:

```json
{"build_profile":{"cmake_build_config":"Release","ndebug_defined":true,"release_performance_build":true}}
```

`release_performance_build` is deliberately strict: it is true only when the
CMake configuration compiled into the executable is exactly `Release` and
`NDEBUG` is defined. An empty, `Debug`, or otherwise unreported configuration
may still run all finite qualification checks, but its timings must not be
quoted as performance measurements. This metadata changes neither
`PT21EVT1` nor `PT21IQH1/PT21IQF1/PT21IQT1` bytes and adds no CLI option.

The fixed-width capture copies full-capacity direct and stationary arrays to
avoid a count-dependent synchronization. CUDA `initcheck` exposed that their
unused suffixes were indeterminate. The scanner now zeros the bounded 1.43 MB
of output arrays before each scan; accepted compact bytes are unchanged and
the captured suffix is deterministic. Final `memcheck`, `initcheck`,
`racecheck`, and `synccheck` runs over the one-iteration inline KAT reported
zero errors or hazards.

Trace byte cost is data-dependent because exact rational numerators and
denominators have variable decimal lengths. The KAT measured 832 bytes for
zero candidates and 7,191 bytes for two representative candidates, or 3,179
incremental bytes per representative candidate. The real one-candidate trace
used 4,339 bytes, an observed 3,507-byte increment; extrapolating that one
sample gives 4,783 candidates inside 16 MiB. Neither extrapolation is a
universal maximum. The exact 16 MiB runtime cap and 10,000-row roster cap are
the authorities.

## Reproduction

Configure a distinct Release tree before reproducing any timing:

```bash
cmake -S . -B build/pt21-inline-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON \
  -DSPARKINTERVAL_FLINT_PLATT_ROOT=/path/to/flint-3.6 \
  -DSPARKINTERVAL_FLINT_PLATT_PREFIX=/path/to/flint-3.6-install
cmake --build build/pt21-inline-release --target \
  sparkinterval-tg-platt-inline-stationary-qualification \
  sparkinterval-tg-platt-inline-stationary-kat \
  sparkinterval-tg-platt-stationary-junction-benchmark \
  sparkinterval-tg-platt-event-scan-benchmark
ctest --test-dir build/pt21-inline-release \
  -R 'tg_platt_(stationary_resolver|stationary_junction|inline_stationary)_known_answers' \
  --output-on-failure
TG_PLATT_EVENT_SCAN_BENCHMARK=\
build/pt21-inline-release/sparkinterval-tg-platt-event-scan-benchmark \
  python3 -m unittest -v tests.test_tg_platt_event_scan
```

The same tests are valid in a `Debug` or empty-build-type tree. In that case
the emitted `release_performance_build` must be `false`, and the run is a
correctness qualification only.

The strict `sm_90` compile-only qualification is:

```bash
cmake -S . -B build/pt21-inline-h100-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_H100_NATIVE=ON \
  -DSPARKINTERVAL_FLINT_PLATT_ROOT=/path/to/flint-3.6 \
  -DSPARKINTERVAL_FLINT_PLATT_PREFIX=/path/to/flint-3.6-install
cmake --build build/pt21-inline-h100-release --target \
  sparkinterval-h100-tg-platt-inline-stationary-qualification
```

## Remaining boundary

This work does not provide a source-wide H100 run, an authenticated SGN2 or
static code manifest, native one-sided Turing closure, a terminal PT21 block
record, Hardy-Z endpoint realization, FLINT-to-Mathlib realization, or the
analytic Turing theorem. It also does not bind the unretained resolver inputs
for full independent replay. Accordingly:

```text
hardy_z_endpoint_realization_proved = false
flint_to_mathlib_realization_proved = false
analytic_turing_realization_proved = false
sgn2_static_manifest_bound = false
multi_block_source_chain_closed = false
source_claim_ready = false
production_ready = false
pt21_atom_discharged = false
```
