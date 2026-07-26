# PT21 qualification-only DD FFT stages-1..9 tile

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

This experiment replaces the existing early FFT launch sequence

```text
(stages 1,2), (3,4), (5,6), (7,8), stage 9
```

with one 256-thread CUDA block per aligned 512-value tile. The block loads
512 `ComplexDisk106` values into shared memory, applies the existing
`dd_radix2_butterfly` in the same stage order with a barrier after each
stage, publishes the stage-9 result, and then uses the ordinary kernels for
stages 10 onward. The 256 roots and norm bounds used by stage 9 form a grid
that contains every earlier root lookup, so the kernel also caches those
exact table entries.

Per block, the kernel uses:

```text
512 DD values       20,480 bytes
256 DD roots        10,240 bytes
256 norm bounds      2,048 bytes
total               32,768 bytes
```

`cuobjdump --dump-resource-usage` reports 62 registers per thread and 32,768
bytes of shared memory on the measured `sm_75` code object. The ordinary pair
kernel uses 61 registers and 20,480 bytes of shared memory there. A separate
Release `sm_90` compile succeeds; its code object reports 64 registers and
33,792 bytes for the tile kernel versus 64 registers and 21,504 bytes for the
ordinary pair kernel. The extra 1,024 bytes in both `sm_90` reports are
compiler-reported shared allocation overhead beyond the declared arrays.

## Isolation and acceptance boundary

The default API remains `run_source_window`. The experiment is available
only through:

```text
run_source_window_tile9_qualification
sparkinterval-tg-platt-dd-tile9-qualification
sparkinterval-h100-tg-platt-dd-tile9-qualification
```

The last target is compiled only in the H100-native build, uses the strict
`sm_90` transform and scanner libraries, and rejects a runtime device unless
CUDA reports compute capability 9.0 and a name containing `H100`.

The executable runs the ordinary and tile implementations in separate
workspaces. Acceptance requires byte-for-byte equality of all 131,072 output
`RealDisk106` records. When event checking is enabled, it also runs the two
outputs through separate CUDA scanners and the independent fixed-2176-bit
host replay, then compares the complete replay-owned samples, status,
summaries, ordered direct events, ordered stationary candidates, payload
seal, and event-artifact SHA-256.

An identical rejected synthetic scan is useful for transform byte identity,
but is not useful source evidence. The JSON therefore reports scanner
acceptance separately. A timing is marked
`performance_evidence_eligible=true` only when all of the following hold:

- the packet is the exact complete block-0 PT21SRC2 schema;
- the caller supplies a matching full-file SHA-256 pin;
- all 131,072 records and both event artifacts are byte-identical;
- both independent scanner replays accept;
- the build reports both CMake `Release` and `NDEBUG`.

`--skip-event-artifact` and every synthetic case are always ineligible.
Every successful report includes:

```text
build_profile = {
  cmake_build_config,
  ndebug_defined,
  release_performance_build
}
device_profile = { name, major, minor }
strict_h100_target
target_h100_measured
```

`release_performance_build` is true only for the exact
CMake-`Release`/`NDEBUG` combination.
`target_h100_measured` is true only when the strict target actually completes
on a runtime NVIDIA H100 sm_90 device. It is independent of
`performance_evidence_eligible`: the latter records input, replay, and Release
build eligibility and does not turn a GB10 timing into an H100 measurement.

## Lean schedule theorem

[`PT21Tile9Schedule.lean`](../../SparkInterval/Zeta/PT21Tile9Schedule.lean)
instantiates the existing reusable
`BluesteinCUDADataflow.initialStages_grouped_by_tile` and negative-root
counterpart at the two PT21 lengths:

```text
row transforms:   logLength = 15, tileLog = 9
final transform:  logLength = 16, tileLog = 9
```

It also instantiates the full grouped-prefix-plus-ordinary-suffix theorem for
both signs and both lengths. Fresh `#print axioms` reports only Lean's base
trio (`propext`, `Classical.choice`, and `Quot.sound`). This proves the exact
complex-arithmetic butterfly schedule. It does not prove DD rounding
refinement, CUDA execution, compiler preservation, or hardware correctness;
the byte-identity KAT is complementary finite evidence, not a replacement
for those missing refinements.

## Bounded results

The strict genuine-input run used the complete block-0 packet

```text
SHA-256
caecf8faee55a1c969062bb5d85cbd50ff70b0f461778e3fcb7fd0d561a058b7
bytes 31,457,408
source terms 768,000
```

On the local NVIDIA GB10, a Release build and 13 interleaved repetitions
gave:

| path | median | observed range |
|---|---:|---:|
| ordinary full source transform | 70.2990 ms | 69.7971–70.3800 ms |
| stages-1..9 tile | 70.0506 ms | 69.7827–70.1058 ms |

The nominal median speedup is `1.00355x`, approximately 0.35%; the observed
ranges overlap, so this should be treated as a very small local effect, not a
robust target prediction. All 131,072 disks were byte-identical. Both event
artifacts were byte-identical and accepted, with 3,539 direct events and one
stationary candidate. The two synthetic cases (all-zero and finite
signed-zero/subnormal sparse edges) also had zero disk mismatches and
byte-identical event artifacts, but their expected ambiguous scans were not
promoted to useful-source acceptance.

The small gain matters: eliminating four global round trips did not remove
the DD butterfly arithmetic itself. This GB10 result does not justify
enabling the path by default and is not an H100 performance prediction.
Its report has `target_h100_measured=false`.

The bounded sanitizer run used the synthetic cases and one repetition:

```text
memcheck:  0 errors, 0 leaked bytes
initcheck: 0 errors
racecheck: 0 hazards, 0 errors, 0 warnings
synccheck: 0 errors
```

## Reproduction

```bash
cmake -S . -B build/pt21-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/pt21-release --parallel 2 \
  --target sparkinterval-tg-platt-dd-tile9-qualification

build/pt21-release/sparkinterval-tg-platt-dd-tile9-qualification \
  --source-packet=/path/to/complete-block0.pt21src2 \
  --expected-source-packet-sha256=HEX \
  --repetitions=13

cmake -S . -B build/pt21-h100 \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_H100_NATIVE=ON
cmake --build build/pt21-h100 --parallel 2 \
  --target sparkinterval-h100-tg-platt-dd-tile9-qualification
```

The source packet is not stored in this repository. The output is a
qualification JSON report, not a PT21 source certificate or a trusted-run
receipt.

## Deliberate nonclaims

This experiment does not establish Hardy-Z realization, DD-to-real
refinement, PTX/SASS correctness, an H100 campaign rate, a production
receipt, or the PT21 theorem atom. It remains fail-closed and off the default
worker path.
