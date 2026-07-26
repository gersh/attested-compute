# PT21 sloppy-DD root whole-transform qualification

This is a qualification-only comparison of the ordinary PT21 DD transform
with a separately compiled transform whose FFT-root multiplications use the
bounded sloppy-DD arithmetic described in
`PLATT_PT21_DD_SLOPPY_MUL_QUALIFICATION.md`. It does not select the candidate
inside the production `run_source_window` entry point, emit a production
certificate, prove CUDA-to-Lean refinement, or discharge a PT21 atom.

The candidate entry point and root-table inspection API exist only when
`SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION` is defined. The qualification
translation unit also refuses to compile without the explicit
`SPARKINTERVAL_CUDA_FTZ_DISABLED` contract. This makes the experiment a
compile-time-isolated path rather than a runtime mode in the ordinary API.

The later qualification-only composition with the stages-1..9 shared-memory
tile is documented in
`PLATT_PT21_DD_TILE9_SLOPPY_ROOT_WHOLE_TRANSFORM_QUALIFICATION.md`. It remains
unselected: two measured GB10 gains over this settled sloppy-root path were
only `0.226%` and `0.264%`, and there is no H100 runtime result.

## Mandatory authenticated input

The runner has no synthetic-only success mode. It requires both
`--source-packet` and a caller-supplied
`--expected-source-packet-sha256`. The only admitted packet is:

| property | required value |
|---|---|
| format | complete little-endian `PT21SRC2` block 0 |
| bytes | `31,457,408` |
| SHA-256 | `caecf8faee55a1c969062bb5d85cbd50ff70b0f461778e3fcb7fd0d561a058b7` |
| legacy PT21 checksum64 | `39d3821666d7af35` |
| source terms | `768,000` |
| window centre | `kSourceLower + kWindowStep/2` |

The loader hashes the complete file, requires the caller's pin to equal the
qualification pin, checks every fixed header field and exact payload length,
checks the embedded upstream-commit field, recomputes the embedded Gamma and
Skn legacy checksum commitments, and rejects every nonfinite centre limb or
finite negative/nonfinite radius.

This authenticates the bytes used by the qualification against a fixed local
known answer. It does **not** establish the fixture's mathematical provenance
or turn it into a production source claim. The historical packet fields and
older reports called their diagnostic checksum FNV-1a-64, but the project
implementation starts from `1,469,598,103,934,665,603`, not the standard
FNV-1a-64 offset `14,695,981,039,346,656,037`. The runner therefore calls and
reports it `legacy_pt21_checksum`; it does not change the committed bytes or
known answers. This legacy checksum is only an embedded-payload consistency
check. The full-file SHA-256 is the cryptographic content pin.

The complete ordinary output bytes are independently pinned by SHA-256:

| case | ordinary-output SHA-256 |
|---|---|
| genuine block 0 | `81e54dc8806211ecc5c69b484076cd28ba1a0ab56a62a6fc8158ec84972b5a3e` |
| finite edge | `72ba9bacc3a312ae18c5d423388beae52a621f3c81e37a1a006d91acc6d6a713` |

These pins, not the legacy checksums, gate the ordinary known answers and
detect accidental changes to the existing `run_source_window` byte path in
the qualification build. The legacy ordinary checksums remain reported as
diagnostics. Candidate output SHA-256 is reported but not pinned because the
candidate is the object under qualification and is deliberately not expected
to be byte-identical.

## Exact genuine-block whole-transform containment gate

Every one of the `131,072` genuine-block ordinary and candidate output disks is decoded
from its binary64 words into an exact
`boost::multiprecision::cpp_rational`. For ordinary disk
`(c_full,r_full)` and candidate disk `(c_fast,r_fast)`, acceptance requires
both

```text
r_fast >= r_full
(c_fast-c_full)^2 <= (r_fast-r_full)^2.
```

These are the exact real-disk containment obligations: the candidate disk
contains the complete ordinary disk. The checker rejects nonfinite words and
negative radii. There is no floating-point tolerance, sampled subset, overlap
substitute, or centre-only fallback for the authenticated genuine block. A
failure leaves the qualification failed; it must not be weakened to a less
informative comparison.

The report also gives candidate/ordinary radius ratios at the median, 90th,
99th, and maximum quantiles, counts ordinary zero-radius cells separately,
and reports both maximum radii.

## Lean checker for one RealDisk106 pair

[`ComplexDiskContainmentWire.lean`](../../SparkInterval/Certified/ComplexDiskContainmentWire.lean)
provides an ordinary Lean, fixed-width checker for one 48-byte
`inner || outer` pair. Each 24-byte `RealDisk106` is parsed in the actual
`center.hi || center.lo || radius` little-endian order. Finite binary64 limbs
are decoded to exact rationals, the real centre is exactly `hi + lo`, and the
disk is embedded in the generic complex-disk model with imaginary centre
zero. Successful checking proves the generic
`ContainmentCertificate.WellFormed` proposition and therefore proves that
every complex value in the decoded inner disk is in the decoded outer disk.

[`ComplexDiskContainmentWireTest.lean`](../../SparkInterval/Tests/ComplexDiskContainmentWireTest.lean)
checks a tight positive pair with a nonzero low limb and fail-closed mutations
for centre, radius order, negative radius, infinity, NaN, endianness, and
framing, plus signed-zero and minimum-subnormal cases. It uses no
`native_decide`.

This theorem checks supplied bytes only. The qualification runner does not
yet bind each compared CUDA output pair to this Lean frame, and the module
does not prove a compiler/instruction refinement, complete-output coverage,
authenticated-run identity, or physical CUDA execution. Those missing edges
must remain explicit even when all pairwise byte checks pass.

## Root-table audit and negative control

The guarded `device_root_table_qualification` view exposes the exact root
disks and their supplied centre-norm upper bounds from one candidate
workspace. The runner obtains views from the separately initialized ordinary
and candidate workspaces, downloads all `32,768` rows from each, and first
requires byte identity of both root arrays and both norm arrays. Exact
rational arithmetic then
checks

```text
re(root_center)^2 + im(root_center)^2 <= center_norm_upper^2
```

for every row, while independently rejecting a nonfinite/negative root
radius or nonfinite/negative norm. This validates the particular norm table
consumed by the bounded multiplication; it does not independently prove the
trigonometric construction of each root disk.

As a fail-open control, the host copy of the first nonzero root norm is
replaced by zero. The same exact checker must reject exactly that row through
the centre-norm obligation.

## Sign and event preservation

The host checker classifies every complete-output disk and every disk in the
`25,741`-sample scanner view with exact rational endpoint comparisons:

```text
positive  iff c-r > 0
negative  iff c+r < 0
ambiguous otherwise.
```

Malformed values are a fourth, rejecting class. The report gives ordinary
and candidate counts plus exact classification-mismatch counts. A genuine
block is accepted only if the candidate required view has no ambiguity and
its classifications equal the ordinary classifications.

Both required views then run through the CUDA event scanner and its
independent fixed-`2176`-bit host replay. Acceptance requires, separately for
both implementations:

- scanner acceptance and zero failure flags;
- byte agreement between the device artifact and independent host replay;
- duplicated shared-endpoint agreement;
- `3,539` direct events and one stationary candidate; and
- candidate event counts equal to the ordinary counts.

The stationary item remains a candidate for the later adaptive-resolution
stage. This runner verifies scanner and replay acceptance; it does not claim
that the stationary point has been resolved by this executable.

## Fail-closed negative control, edge corpus, and timing

A separate finite overflow-provoking input drives the candidate root
arithmetic into its checked nonfinite-intermediate path. The runner computes
the finite-input precondition over every Gamma and Skn disk, then requires the
failure word to equal `kQualificationArithmeticFailure` (with neither
Gamma nor Skn malformed-input bit present). It also requires all `131,072`
outputs to have the exact canonical bit pattern `{{+0,+0},+infinity}`. This
is a bounded negative control for the candidate's fail-closed plumbing.
Malformed Gamma/Skn boundary cases remain covered by the transform API smoke
test.

Before the genuine packet, the runner executes a deterministic finite-edge
whole-transform input containing signed zero, minimum-subnormal limbs and
radii, and wide-exponent finite values. Its ordinary output is pinned to
`f581990198bdc555`. Both workspaces' transform failure words must remain zero,
and all `131,072` disk pairs must pass the exact dyadic overlap obligation

```text
(c_fast-c_full)^2 <= (r_fast+r_full)^2.
```

This case is deliberately labeled `synthetic-finite-edge-overlap-only`, not
containment-qualified. The initial run found that 130,065 cells do not satisfy
candidate-contains-ordinary: their radii round to the same binary64 value
while their retained centres differ. That fact remains explicit and
non-gating; it was not rewritten as containment. Exact sign classifications
must still agree for all cells. The overlap check establishes only a nonempty
intersection and detects gross divergence. It does **not** validate either
full transform or identify any point in the intersection with the exact
transform. The separately referenced arithmetic corpus is not replayed in
this run. These checks do not establish universal CUDA refinement.

The more focused arithmetic executable remains mandatory complementary
evidence. Its `8,192`-row corpus has SHA-256
`50738ee7a4b57069c074b8cbdc373ed6feb0e90991f8ec364b68b8cef725f6c7`
and includes the scalar near-tight, undersized-norm, subnormal, signed-zero,
nonfinite, overflow, and rejection cases. The whole-transform runner reports
the corpus digest as a reference, but explicitly reports that the corpus was
not replayed or result-bound by that invocation. The focused arithmetic
executable must be run and audited separately.

The arithmetic formula is currently duplicated in the focused executable and
the guarded transform translation unit. A fail-closed source manifest pins
both fast-add, fast-multiply, and complex-radius bodies by SHA-256 and checks
their ordered operations and constants. This detects formula drift and ties
both copies to the reviewed formula, but it is not binary binding: the
8,192-row executable still does not invoke the integrated transform symbol.
A small shared qualification-only header is the preferred follow-up.

Genuine-block timings use CUDA events and interleave ordinary-first and
candidate-first repetitions to reduce ordering bias. A Release build is
reported only as `release_build_profile_eligible`; the runner cannot detect
profiler or sanitizer injection, reports
`runtime_instrumentation_status=not-inspected-by-runner`, and therefore always
sets `performance_evidence_eligible=false`. A strict `sm_90` target is
separately compiled with the same candidate guard and rejects any runtime
device that is not an NVIDIA H100 with compute capability 9.0. Portable GB10
timings are not reported as H100 measurements, and successful strict
compilation is not an H100 runtime claim.

## Reproduction

```bash
cmake -S . -B build/pt21-sloppy-whole-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=121 \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON

cmake --build build/pt21-sloppy-whole-release \
  --target \
    sparkinterval-tg-platt-dd-sloppy-mul-qualification \
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification

ctest --test-dir build/pt21-sloppy-whole-release \
  -R '^tg_platt_dd_sloppy_mul_qualification_known_answers$' \
  --output-on-failure

TG_PLATT_DD_FULL_V2_PACKET=/tmp/platt-source-dd-full-v2.bin \
ctest --test-dir build/pt21-sloppy-whole-release \
  -R '^tg_platt_dd_sloppy_root_whole_transform_qualification_known_answers$' \
  --output-on-failure

build/pt21-sloppy-whole-release/\
sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification \
  --source-packet=/tmp/platt-source-dd-full-v2.bin \
  --expected-source-packet-sha256=\
caecf8faee55a1c969062bb5d85cbd50ff70b0f461778e3fcb7fd0d561a058b7 \
  --repetitions=9
```

The strict H100 target and bounded sanitizer/resource/SASS commands are
documented with the build wiring because their exact target names and binary
paths are build-system properties. No H100 runtime result should be added
until the strict binary has actually run on an H100.

## Observed qualification profile

On the local NVIDIA GB10 Release build, nine interleaved repetitions measured
`69.676 ms` for the ordinary transform and `59.322 ms` for the candidate
(median, `1.175x`). This is not an H100 estimate. The genuine candidate radius
inflation was `1.483728009` median, `1.483728043` p90,
`1.483728086` p99, and `1.483728203` maximum.

The strict sm_90 archive compiled, while the strict executable rejected the
local GB10 before loading or running a case. `cuobjdump` reported:

| kernel | ordinary registers | candidate registers | candidate local bytes |
|---|---:|---:|---:|
| radix-2 stage | 62 | 80 | 0 |
| paired radix-2 stages | 64 | 78 | 0 |
| Hermitian preprocess | 72 | 76 | 0 |

The candidate archive contained no `LDL`, `STL`, `LD.LOCAL`, or `ST.LOCAL`
SASS instructions. Its noinline fast multiply contained one explicit `DFMA`
for the TwoProduct residual; fast add contained none. Both bounded
`compute-sanitizer --tool memcheck` and `--tool initcheck` runs completed with
`ERROR SUMMARY: 0 errors`.

Reproduce the binary audit with:

```bash
cuobjdump --dump-resource-usage \
  build/pt21-sloppy-root-h100/\
libsparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification.a

cuobjdump --dump-sass \
  build/pt21-sloppy-root-h100/\
libsparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification.a
```
