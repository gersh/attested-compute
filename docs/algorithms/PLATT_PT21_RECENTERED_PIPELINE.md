# PT21 independently recentered producer/consumer pipeline

Status: qualification only. This path emits no production certificate and
does not discharge the PT21 external atom.

## Invariant

Every logical block is evaluated by the ordinary PT21 path at its own center:

1. authenticate that block's V2 Gamma record;
2. synthesize its own 32,768-cell Gamma row;
3. advance or re-anchor the ordered 768,000-term source phase state;
4. form its own 23 by 32,768 Taylor accumulator row;
5. run one complete 131,072-sample DD transform;
6. scan its ordinary central 25,741 samples; and
7. independently replay the scanner artifact with fixed 2,176-bit host
   arithmetic.

There is no shifted-view reuse, transform reuse, skipped center, or change to
the production V2 worker. The only optimization is temporal overlap:
accumulation for block `b+1` may run while the single transform workspace
consumes block `b`.

## State ownership

The source accumulator owns 570,977,292 device bytes in its ordinary one-row
configuration:

| State | Mutability | Bytes |
|---|---:|---:|
| offsets and 6,674 active-bucket indices | immutable | 157,772 |
| Q192 turns, residuals, amplitudes | immutable | 55,296,000 |
| 23-stage residual-power table | immutable | 423,936,000 |
| sine/cosine coefficient tables | immutable | 960 |
| phase-step row | immutable after setup | 30,720,000 |
| current phase-value row | ordered mutable state | 30,720,000 |
| one accumulator output row | mutable slot | 30,146,560 |

The qualification constructor shares every immutable table and the single
ordered phase-value row. A second slot therefore costs exactly 30,146,560
bytes, not another 570 MB. A second Gamma row costs 1,310,720 bytes. CUDA
events establish these edges:

```text
producer: synthesize[b] -> accumulate[b, slot] -> ready[slot]
consumer: ready[slot] -> transform[b] -> consumed[slot] -> scan/capture[b]
producer: consumed[slot] -> safe reuse of slot for b+2
```

The transform remains a single serial workspace. Its immutable root and norm
tables are only about 2.9 MB; almost all of its 195,429,312 bytes are mutable
FFT scratch. Duplicating transform lanes would therefore add roughly 192.5 MB
per lane and would launch competing copies of the same already-dominant radix
kernels.

The owning `Resources` object is non-copyable. On every exception path its
destructor synchronizes both CUDA streams before freeing a replay capture,
pinned host buffer, device allocation, or workspace. This prevents an
asynchronous capture copy from targeting released host memory.

### Inactive-cell initialization correction

The source roster has 6,674 active buckets out of 32,768. The accumulator
kernel intentionally writes only those active buckets, while the downstream
transform reads every cell in every Taylor row. The API workspace formerly
allocated its output row without explicitly initializing the inactive cells;
the older standalone-core path already zeroed its analogous buffer. Fresh
CUDA allocations happened to produce the intended result in the recorded
runs, but that was not a valid initialization contract.

The shared accumulator implementation now performs one checked `cudaMemset`
over all `23 * 32768 * output_slots` `ComplexDisk106` cells immediately after
allocation. The existing initialization synchronization completes that
default-stream operation before the workspace is returned. Active cells are
then overwritten by the unchanged accumulator kernel; inactive cells retain
the mathematically required exact positive-zero bit pattern.

The expanded accumulator smoke test reads the actual 32,769-entry device
offset table. For each exercised slot it checks all

```text
(32768 - 6674) * 23 = 600162
```

inactive cells, including both limbs of both coordinates and the radius. It
does this for two legacy one-slot windows and both slots of a qualification
workspace. The corrected Release binary passed CUDA Compute Sanitizer
`initcheck` with zero errors.

After the correction:

- the ordinary block-0 production V2 consumer retained the previous required
  sample digest `55c2a006ce805986`, maximum radius
  `3.6780937664373325e-13`, 3,539 direct events, and one stationary candidate;
- the corrected five-block sequential/pipeline comparison again had zero
  sample, artifact, or replay mismatches across every required position
  category.

The 64-block timing below remains useful performance data because the added
memset occurs once during setup and does not alter the measured hot loop. Its
arithmetic is not inferred from timing: the corrected production and
five-block genuine checks above separately revalidated the output.

## Verification

The qualification runner executes two independent workspaces over the same
fully authenticated Gamma stream:

- a one-stream, one-output-row baseline;
- a two-stream, two-output-row pipeline.

For every block it requires:

- both device scans to pass the independent fixed-integer host replay;
- byte-for-byte equality of all 25,741 retained `RealDisk106` samples;
- byte-for-byte equality of `ScanStatus`, all three `StreamSummary` records,
  and every compact direct/stationary event record.

The bounded KAT must include at least one first, recurrence-interior,
re-anchor, and terminal position. The five-block test uses a qualification
re-anchor interval of two. The longer benchmark used 64 blocks and a
re-anchor at index 32.

Release result on the DGX Spark GB10, 2026-07-26:

| Authenticated blocks | Sequential | Two-slot pipeline | Speedup |
|---:|---:|---:|---:|
| 64 | 6.055095091 s | 5.886328052 s | 1.028671x |

The 64-block run reported zero sample mismatches, zero artifact mismatches,
and zero replay failures. Its strict build profile was `Release`, with
`NDEBUG` defined. A five-block anchor-heavy run likewise passed and measured
1.028857x.

The setup cost for both independent workspaces is excluded from these hot-path
times. CPU replay occurs after the measured CUDA submission/drain interval,
but every asynchronous device-to-host capture is included.

The original five-block Release case was run under CUDA Compute Sanitizer:

- `memcheck`: zero errors;
- `racecheck`: zero hazards, errors, or warnings.

Both instrumented executions retained byte-identical samples and artifacts and
passed the independent host replay. Sanitizer timings are intentionally not
performance evidence. After the inactive-cell correction, the expanded
one-slot/two-slot accumulator smoke also passed `initcheck` with zero errors.

## Why four slots are not the next optimization

The one-block Nsight Systems profile on the same GB10 measured:

| Kernel family | GPU time |
|---|---:|
| paired DD radix stages | 31.814 ms |
| ordinary DD radix stages | 28.236 ms |
| source accumulator | 15.742 ms |
| Gamma-row construction inside transform | 3.554 ms |
| event scan | 2.932 ms |

Both radix kernels use 61 registers per thread; the paired kernel uses 20,480
bytes of shared memory per block. The theoretical two-slot opportunity was to
hide much of the 15.742 ms accumulator behind more than 60 ms of radix work.
The measured gain of only 2.87% shows that these kernels contend for device
resources instead. Four slots would add another 60,293,120 bytes of
accumulator output and 2,621,440 bytes of Gamma storage but cannot remove the
single serial transform bottleneck. It is therefore not implemented.

This GB10 result is not an H100 performance measurement. The strict H100
target is compiled separately, and the same byte-identity KAT must be run on
the target SKU before any deployment decision. Because the large grids
already expose substantial parallelism, an H100 should not be assumed to
produce a materially larger overlap benefit without measurement.

## Build and run

```bash
cmake -S . -B build/pt21-pipeline \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/pt21-pipeline --parallel 2 --target \
  sparkinterval-tg-platt-pt21-recentered-pipeline-qualification

build/pt21-pipeline/sparkinterval-tg-platt-pt21-recentered-pipeline-qualification \
  GAMMA_V2_STREAM \
  --expected-stream-sha256=AUTHENTICATED_STREAM_DIGEST \
  --reanchor-blocks=32
```

Run the registered source/contract gate with:

```bash
ctest --test-dir build/pt21-pipeline \
  -R '^tg_platt_pt21_recentered_pipeline_known_answers$' \
  --output-on-failure
```

For a genuine optional KAT, set the three environment variables named in
`tests/test_tg_platt_pt21_recentered_pipeline.py`. Run the genuine test under
Compute Sanitizer `memcheck` and `initcheck` before changing slot ownership or
event placement. Error-path review must retain the destructor rule that
streams drain before replay captures are freed; the source test checks this
ordering and checks that the production worker never calls the qualification
API.
