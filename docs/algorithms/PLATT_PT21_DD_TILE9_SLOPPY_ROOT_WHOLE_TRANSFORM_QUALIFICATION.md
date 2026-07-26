# PT21 tile9 plus sloppy-root whole-transform qualification

Status: qualification-only, accepted on the authenticated local corpus, and
**not selected for production**. Two nine-repetition local runs improved on
the settled sloppy-root path by only `0.226%` and `0.264%`, and no H100
runtime measurement or CUDA-to-Lean refinement exists.

This experiment composes two previously separate candidates:

- the conservative sloppy-DD formula for multiplication by immutable FFT
  roots; and
- one shared-memory tile for iterative radix-2 stages 1 through 9.

The composition has its own guarded entry point,
`run_source_window_tile9_sloppy_root_qualification`, archive, executable, and
strict `sm_90` target. It is compiled only when both
`SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1` and
`SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION=1` are present. The
production transform archive has neither macro and exports neither the
settled sloppy-root nor joint entry point.

## Schedule and arithmetic identity

The joint kernel changes storage and launch scheduling, not the butterfly
formula. A 512-value tile is closed under stages 1 through 9. At stage
`stage_log`, the shared root slot is

```text
root_slot = offset * 2^(9-stage_log).
```

The cached stage-9 table itself has stride
`2^(maximum_log-9)`, so the global root index is exactly

```text
root_slot * 2^(maximum_log-9)
  = offset * 2^(maximum_log-stage_log),
```

which is the index used by the settled per-stage and paired-stage kernels.
Each shared-memory butterfly calls the same
`dd_radix2_butterfly_sloppy_root_qualification` operation in the same stage
order. There is one barrier after initial loading and one after each of the
nine stages.

Stages 10 and later still use the settled sloppy-root stage kernel. The
Hermitian preprocessing multiplication still uses the settled bounded
sloppy-root operation. Every invalid or nonfinite arithmetic result ORs
`kQualificationArithmeticFailure` into the same workspace failure word, and
final extraction canonicalizes every sample to `{{+0,+0},+infinity}` when
that word is nonzero.

Source tests pin by SHA-256 the complete braced bodies of the joint tile
kernel, transform scheduler, whole-window entry, and resource-query function.
Those source pins detect unreviewed formula or scheduling drift. They are not
a compiler or SASS proof.

## Mandatory evidence gates

The evidence executable runs three independent workspaces: ordinary,
settled-sloppy, and joint. Acceptance requires all of the following:

- the complete `31,457,408`-byte block-0 packet has SHA-256
  `caecf8faee55a1c969062bb5d85cbd50ff70b0f461778e3fcb7fd0d561a058b7`;
- all `32,768` root and norm-table rows are byte-identical among the three
  workspaces, pass exact rational norm checks, and fail the deliberate
  bad-norm mutation;
- all `131,072` genuine joint output disks are byte-identical to the settled
  sloppy output;
- the joint and settled output SHA-256 values both equal
  `7d24ab69c3f2851809e13ab6d9a594345c75f26423ca5a9fea136e7a1b861a0e`;
- all `131,072` genuine joint disks exactly contain the corresponding
  ordinary disks under
  `r_joint >= r_ordinary` and
  `(c_joint-c_ordinary)^2 <= (r_joint-r_ordinary)^2`;
- both joint and settled failure words are zero;
- the required-view scanner and independent 2176-bit host replay artifacts
  are byte-identical between joint and settled, with `3,539` direct events
  and one stationary candidate;
- the finite-overflow control produces flag `4` and exactly `131,072`
  canonical malformed outputs in both paths, with byte-identical output; and
- the linked joint kernel reports a feasible nonspilling resource profile.

The finite edge case is also byte-identical to the pinned settled output
`adc7cfb2cdd84556b051d4037cc52afc93b3e44b1ce7024c8bdae8e635ea12cc`.
As in the settled qualification, that synthetic case is overlap-only:
`130,065` cells do not satisfy candidate-contains-ordinary. This remains
explicit and non-gating; it is not evidence of whole-transform correctness.

Fixture authentication binds the exact local bytes used by this experiment.
It does not establish the fixture's mathematical provenance or make the
packet a production source claim.

## Local resource and timing result

The `sm_121` Release run on NVIDIA GB10 reported the actual linked kernel
attributes:

| property | joint tile |
|---|---:|
| registers per thread | 65 |
| static shared memory | 32,768 bytes |
| local bytes per thread | 0 |
| required threads per block | 256 |
| maximum threads per block | 896 |
| active blocks per multiprocessor | 3 |

The runner rejects nonzero local memory, a shared-memory size other than
32,768 bytes, fewer than 256 supported threads, or zero active blocks per SM.
`cuobjdump` independently reported `REG:65 STACK:0 SHARED:32768 LOCAL:0`.
The joint SASS slice contains ten `BAR.SYNC` instructions and no local-memory
load or store.

Nine three-way interleaved repetitions measured:

| whole source window | median milliseconds | relative to joint |
|---|---:|---:|
| ordinary | 69.6567 | 1.178698x |
| settled sloppy-root | 59.2297 | 1.002256x |
| joint tile9 plus sloppy-root | 59.0963 | 1.000000x |

This final run differs from settled sloppy by `0.1333 ms`, or `0.226%`.
An independent preceding nine-repetition run measured `0.1560 ms`, or
`0.264%`. Both are too small to justify production selection from one
machine.

An uninstrumented-by-invocation Nsight Systems trace explains the small whole
gain. Across four complete joint-path invocations, the 20 stages-1..9 joint
tile launches consumed `116.963 ms`. Across four settled invocations, the 80
paired stages-1..8 launches consumed `104.460 ms`; the settled path then also
needs its stage-9 launches. Thus the joint tile makes stages 1..8 slower, and
only removing stage 9 barely offsets that cost.

The executable reports raw CUDA-event timings but deliberately sets
`performance_evidence_eligible=false`: it cannot detect profiler or sanitizer
injection. `release_build_profile_eligible` describes only the Release build
profile, while `runtime_instrumentation_status` remains
`not-inspected-by-runner`.

These are GB10 measurements, not H100 estimates. The strict archive contains
an `sm_90` cubin and the strict executable rejects the local GB10 before
opening the fixture. The strict binary has not run on an H100, so
`target_h100_measured` and `h100_runtime_claimed` remain false.

## Sanitizer results

On the same local build:

- full memcheck completed with `ERROR SUMMARY: 0 errors`;
- full initcheck completed with `ERROR SUMMARY: 0 errors`;
- a racecheck filtered to one complete launch of the new joint tile kernel
  completed in 7 seconds with `0 hazards`; and
- an unfiltered whole-program racecheck hit its 60-second timebox and is
  therefore **not** reported as a pass.

The filtered racecheck targets the new shared-memory/barrier risk. It does not
replace the exact byte-identity, containment, and replay gates.

## Reproduction

```bash
cmake -S . -B build/pt21-tile9-sloppy-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=121 \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON

cmake --build build/pt21-tile9-sloppy-release \
  --target \
    sparkinterval-tg-platt-dd-sloppy-mul-qualification \
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification \
    sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification

TG_PLATT_DD_FULL_V2_PACKET=/tmp/platt-source-dd-full-v2.bin \
ctest --test-dir build/pt21-tile9-sloppy-release \
  -R 'tg_platt_dd_(sloppy_mul|sloppy_root_whole_transform|tile9_sloppy_root_whole_transform)_qualification_known_answers' \
  --output-on-failure

build/pt21-tile9-sloppy-release/\
sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification \
  --source-packet=/tmp/platt-source-dd-full-v2.bin \
  --expected-source-packet-sha256=\
caecf8faee55a1c969062bb5d85cbd50ff70b0f461778e3fcb7fd0d561a058b7 \
  --repetitions=9
```

For the new shared-memory kernel's bounded racecheck:

```bash
compute-sanitizer --tool racecheck \
  --kernel-name \
    kns=dd_radix2_stages_1_through_9_tile_sloppy_root_qualification \
  --launch-count 1 --error-exitcode 99 \
  build/pt21-tile9-sloppy-release/\
sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification \
  --source-packet=/tmp/platt-source-dd-full-v2.bin \
  --expected-source-packet-sha256=\
caecf8faee55a1c969062bb5d85cbd50ff70b0f461778e3fcb7fd0d561a058b7 \
  --repetitions=1
```

## Trust status

This result proves no CUDA instruction semantics, compiler correctness,
physical execution, fixture provenance, or CUDA-to-Lean refinement. It emits
no source/production certificate and discharges no PT21 atom. The joint path
remains separately guarded, reports
`optimization_selected_for_production=false`, and must not be linked into the
production worker from this evidence alone.
