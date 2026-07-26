# PT21 live V2 transform-candidate qualification

Status: qualification only. The joint candidate is not selected by the
production V2 worker, this path emits no trusted-compute receipt, and it does
not discharge the PT21 external atom.

## Purpose

The earlier whole-transform qualification uses a pinned, source-shaped
`PT21SRC2` packet. That is useful arithmetic evidence, but it is not the
current fused worker's producer boundary. The live qualification runner
instead starts with the exact authenticated block-0 `PT21GTS2` stream and
executes the same boundaries as the V2 worker:

1. authenticate the complete V2 stream and its footer before allocating GPU
   state;
2. synthesize the resident 32,768-cell Gamma row;
3. run the exact 768,000-term, 23-stage source accumulator;
4. run the ordinary transform;
5. run the bounded sloppy-root transform;
6. run the tile9 scheduling composition of that sloppy-root transform; and
7. independently replay the exact three-stream scanner for each result.

The logical Gamma-stream SHA-256 is
`d484eb1f0d382ffcf3683e18cd0c9570c5a215efaa595cb9bb677e3c2ebfbdbc`.
The exact 848-byte file used by the bounded KAT has SHA-256
`b1269afd7d15842fb15a86301627280acddd190de9a7e2d961510a555f14f391`.

## State reuse

The runner deliberately owns exactly one instance of each large mutable
device workspace:

| State | Device bytes |
|---|---:|
| Exact source accumulator | 570,977,292 |
| DD transform | 195,429,316 |
| Three-stream scanner | 7,750,989 |
| Gamma row | 1,310,720 |

The accumulator is run once. Its borrowed `23*32768` output remains valid
while all three transform variants run sequentially on one stream. Each
131,072-sample transform output is copied to a roughly 3 MiB host vector
before the same transform workspace is reused. Thus this check duplicates
neither the 570 MB immutable accumulator state nor the 195 MB transform
scratch.

## Acceptance gates

The ordinary run must reproduce all current block-0 known answers:

- required-region XOR diagnostic `55c2a006ce805986`;
- maximum-radius bits `0x3d59e1dd5c163e26`;
- all-sample SHA-256
  `f11156870b9681147f3b48d70bd9bdc3613f015fa9a8783230fc731f49564224`;
- required-sample SHA-256
  `3a12d63c8545aaf98ce6585994412a7e96c817a4b3d93e40da671c58883a97e4`;
- scanner artifact SHA-256
  `583a257079353e8efb334f1be2d7c41514a8f9759898f1dc1b2220fbda2dae60`;
- direct-event counts `(71, 3397, 71)`;
- stationary-candidate counts `(0, 1, 0)`; and
- the exact recorded left/right integer weights.

These hashes are specifically for the fully authenticated live Gamma stream
and exact 570 MB accumulator boundary above. They must not be substituted
with a scanner root from an older source-packet fixture merely because the
event counts happen to agree.

The independent fixed-2,176-bit scanner replay must accept and reproduce the
device arrays byte for byte. The transform failure word, malformed count, and
ambiguous required-sign count must all be zero.

The sloppy-root result is then checked with exact dyadic arithmetic. For all
131,072 output disks, not only the central 25,741 used by the worker,

```text
r_sloppy >= r_ordinary
and
(c_sloppy - c_ordinary)^2
  <= (r_sloppy - r_ordinary)^2.
```

Every required disk must retain the same exact nonzero sign, and the direct
and stationary event topology must remain byte-identical. The scanner Merkle
roots themselves are not expected to equal the ordinary root because they
commit the widened disk bytes.

Finally, the tile9+sloppy result must be byte-identical to the settled
sloppy-root result at all 131,072 positions, including its complete scanner
replay artifact. The frozen candidate all-sample, required-sample, and scanner
hashes are respectively
`06e55d44a684548c93f4ac48996fdca06bca00e1ab4ba493d02f84d03bc16c19`,
`46ceeae8f719f85bf747a9b660f26c426016859293e22bb0e653041365f60c57`,
and
`65292e38a013baa83abc61bd5cdcd8c2e014032d9bceabe08d6fd5578d06ef89`.
Root disks and their directed center-norm table are audited as exact binary64
dyadics before and after the three runs and pinned to
`0b4e51572104edf59d096d680ca010a515157208c6cdba14be867d9c22d52040`.
Runtime CUDA attributes must show the joint tile kernel is launchable, uses
no local memory, and has the expected 32,768 bytes of static shared memory.

The live accumulator audit checks the complete 32,769-entry offset table and
6,674-entry active roster. All 600,162 inactive stage/bucket cells must remain
exact positive zero, while all 153,502 active cells must be finite disks. The
ordered offset/roster geometry is pinned to
`67dc2eda921762f6ad1eaf046188b9500b1b19c87b46e60facf30cfb3bf28ad4`.

## Optional Lean containment handoff

The runner performs the all-sample containment test in exact `cpp_rational`
arithmetic. With

```text
--containment-frames-out=ABSENT_PATH
```

it also serializes every ordinary/candidate pair as one canonical 48-byte
little-endian `inner || outer` `RealDisk106` frame. The output path must not
already exist, and the file is emitted only after every candidate semantic
gate accepts. The writer constructs each binary64 word explicitly in
little-endian order, creates a regular file with exclusive/no-symlink flags,
writes exactly 131,072 frames (6,291,456 bytes), synchronizes it, and rereads
the same file descriptor. It requires stable inode/size/link metadata, byte
identity, and the frozen SHA-256

```text
a4379093cd52ab0b90ed73cf60f617003490eefd2a1379115d9a3b1bdf5125d7
```

This raw frame stream is directly consumable by the base-trio
`checkRawContainmentArtifactBytes expectedCount bytes` checker, whose
soundness theorem reduces to
`checkRawContainmentByteFrames expectedCount frames`. The explicit native
CLI target is:

```bash
lake build sparkinterval-check-pt21-containment
.lake/build/bin/sparkinterval-check-pt21-containment \
  --block0 BLOCK0.containment-frames
```

The retained Python KAT independently decodes every binary64 limb as a
rational and checks all 131,072 containment inequalities.

Emission and rehashing are not authentication. The runner therefore keeps
`containment_frame_artifact_authenticated=false` and
`containment_frame_artifact_lean_check_executed=false`; that field describes
the CUDA runner itself, which does not launch Lean. A campaign envelope must
still domain-separate and authenticate the frame order, count, input-stream
identity, ordinary/candidate executable identities, artifact digest, and
terminal claim before the stream can cross the receipt boundary. A separate
successful CLI replay may be described as Lean-source-checked, but not as
attested or as compiler-refinement evidence.

## Fail-closed fallback

If containment, sign, event-topology, tile identity, root-table, or resource
qualification fails, the candidate is not eligible. The runner then executes
a fresh ordinary transform on the same authenticated Gamma/Skn inputs and
requires its full sample bytes and replay artifact to reproduce the original
ordinary known answer. The report selects `ordinary-fallback`; it never
silently treats a rejected candidate as qualified.

A CUDA launch or runtime exception still aborts the process. The fallback is
for a completed candidate whose semantic gates reject, not for continuing
after an invalid CUDA context.

The qualification-only option
`--force-candidate-rejection-for-test` leaves every semantic comparison
enabled but forces selection through the fallback branch. Its KAT requires a
fresh ordinary transform to reproduce every sample and the complete replay
artifact byte for byte. The JSON distinguishes
`candidate_semantic_gates_accepted` from
`candidate_rejection_forced_for_test`, so a forced fallback cannot be
misreported as an arithmetic rejection.

## Build and bounded run

Portable diagnostic build:

```bash
cmake -S . -B build/pt21-live-candidate \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/pt21-live-candidate --target \
  sparkinterval-tg-platt-pt21-live-transform-candidate-qualification

build/pt21-live-candidate/\
sparkinterval-tg-platt-pt21-live-transform-candidate-qualification \
  BLOCK0.pt21gts2 \
  --expected-stream-sha256=d484eb1f0d382ffcf3683e18cd0c9570c5a215efaa595cb9bb677e3c2ebfbdbc \
  --repetitions=3 \
  --containment-frames-out=BLOCK0.containment-frames
```

The strict target is
`sparkinterval-h100-tg-platt-pt21-live-transform-candidate-qualification`.
It is compiled only for `sm_90` and rejects a non-H100 device. Only a strict
Release run on an actual H100 can set `target_h100_measured`; a portable DGX
Spark run is functional evidence, not H100 timing.

The report distinguishes a qualifying Release build from admissible
performance evidence. It may set `release_build_profile_eligible`, but the
runner cannot detect profiler or sanitizer injection and therefore reports
`runtime_instrumentation_status = "not-inspected-by-runner"` and
`performance_evidence_eligible = false`. A retained calibration wrapper must
establish the runtime instrumentation state separately.

## Bounded evidence recorded 2026-07-26

On a GB10 (`sm_121`) Release build with `--fmad=false --ftz=false`, the full
live block-0 KAT and its forced-fallback KAT passed. The unchanged ordinary V2
worker independently emitted scanner root
`583a257079353e8efb334f1be2d7c41514a8f9759898f1dc1b2220fbda2dae60`
and the same counts and integer weights. One bounded `initcheck` run and one
bounded `memcheck` run each reported zero CUDA errors.

The opt-in writer emitted the exact 6,291,456-byte containment stream above.
An independent Python rational replay accepted every frame and reproduced its
frozen SHA-256. The native Lean-source checker then accepted all 131,072
frames in 5.62 seconds on the local host. This verifies the serialization and
exact-rational checker boundary; receipt authentication, Lean compiler
refinement, and ordinary-Hardy-Z realization remain open.

A three-repetition interleaved diagnostic measured transform-only medians of
69.653 ms ordinary, 59.277 ms settled sloppy-root, and 59.158 ms
tile9+sloppy-root. Thus the qualified joint candidate was about 15% faster than
ordinary on this device, while tile9 added essentially no further GB10 gain
over the settled sloppy-root candidate. These are local diagnostic numbers,
not an H100 benchmark, campaign projection, or production claim.

## Trust boundary

Acceptance establishes a bounded relative statement: on this exact live
block-0 input, the sloppy disk contains the ordinary CUDA disk, and the joint
tile schedule reproduces the settled sloppy result. It does not establish:

- CUDA/compiler/instruction refinement into Lean;
- that the ordinary CUDA disk realizes the intended exact Hardy-Z value;
- FLINT-to-Mathlib realization of the Gamma producer;
- any non-block-0 recurrence, re-anchor, terminal, or all-window claim;
- stationary resolution, Turing closure, or zero completeness;
- Azure confidential-compute execution or a signed receipt; or
- the PT21 theorem or ternary-Goldbach external atom.

An eventual Azure receipt must bind the exact input file, logical stream
digest, final executable/cubin, source and kernel manifests, canonical JSON
result, challenge nonce, target profile, and NVIDIA/SEV-SNP evidence. This
bounded runner intentionally reports every such production claim as false.
