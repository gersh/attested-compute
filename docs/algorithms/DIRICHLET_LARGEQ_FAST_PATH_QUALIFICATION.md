# Large-q lattice and all-character fast-path qualification

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This note records the July 25, 2026 optimization and bounded qualification of
the directed binary64 path

```text
Hurwitz lattice -> Taylor reconstruction -> residue composition
                -> CRT/Bluestein all-character transform.
```

It is a component qualification on the local NVIDIA GB10. It is not an H100
measurement, a source-scale run, a certificate for the analytic input boxes,
zero isolation, a Turing count, or a discharge of
`platt-dirichlet-theorem-7-1`.

## Semantics-preserving changes

### Sign-quadrant interval multiplication

The old CUDA helper evaluated all four endpoint products twice, once rounded
downward and once rounded upward. For ordered finite intervals, monotonicity
selects fewer candidates whenever either operand has a definite sign. For
example,

```text
0 <= x.lo and 0 <= y.lo
  => x*y = [roundDown(x.lo*y.lo), roundUp(x.hi*y.hi)]

x.lo < 0 < x.hi and 0 <= y.lo
  => x*y = [roundDown(x.lo*y.hi), roundUp(x.hi*y.hi)].
```

Only the crossing-by-crossing case needs two lower and two upper candidates.
The implementation retains CUDA's `__dmul_rd`/`__dmul_ru` intrinsics and the
same explicit finite/ordered input guards. No FMA or device transcendental was
introduced. The optimized result is the same outward interval hull as the
four-corner implementation.

`SparkInterval/SignQuadrantIntervalMul.lean` now checks this optimization
symbolically in all nine sign cases. It proves that the selected exact
endpoints equal the tight four-corner product, then proves the stronger
production-shaped statement: applying any operation satisfying
`roundDown(x) <= x` to each selected lower product and any operation
satisfying `x <= roundUp(x)` to each selected upper product preserves
containment. This closes the real-arithmetic identity, including the
two-candidate crossing case. Refinement of CUDA comparisons and
`__dmul_rd`/`__dmul_ru`, compilation, and physical execution remain explicit
downstream obligations.

`SparkInterval/DirectedComplexInterval.lean` lifts the same abstract directed
rounding contract to rectangular complex addition, subtraction, and
multiplication in the exact operation order used by the CUDA butterflies:
four sign-quadrant real products followed by one directed subtraction and one
directed addition. Lean proves that every exact complex result remains inside
the resulting rectangle. This supplies the reusable arithmetic induction
step needed by a staged interval-FFT proof, while deliberately leaving
binary64 instruction, compiler, and hardware refinement separate.

`SparkInterval/Dirichlet/DirectedIntervalFFT.lean` then performs the full
stage induction. Its interval state uses the same `groupAt`, `offsetAt`,
scheduled-left/right, and output-side definitions as the exact radix-2 graph.
Lean proves one butterfly, one stage, every bounded stage suffix, and the
complete bit-reversed positive transform. With the separately stated pure
radix-2 identity, each output rectangle contains the direct DFT coefficient.
Twiddle enclosure is a visible premise, and flat CUDA memory, instruction,
compiler, and physical-execution refinement are still outside this theorem.

`SparkInterval/Dirichlet/BluesteinCUDADataflow.lean` checks the remaining
exact source layout. It proves CUDA's 32-bit `__brev` shift equals the Lean
bit reversal under the live length guard, flattened scatter writes are
collision-free, strided tensor addresses remain in allocation, and the
shared 1024-value prefix is exactly the corresponding global stage prefix.
The capstone follows `initializeA`, kernel copy, both negative forward
transforms, fused pointwise/inverse scatter, positive inverse, post-chirp,
and gather's one `1/L` normalization to the direct positive DFT. This is
exact complex dataflow; it still does not identify a device execution or
compiler output with those functions.

`SparkInterval/Dirichlet/DirectedIntervalBluestein.lean` composes those two
layers. Its hypotheses visibly require rectangles enclosing every source
value, input and output chirp, padded kernel coefficient, negative and
positive twiddle, and the sole `1/L` normalization. It then follows the
production-shaped sequence—pre-chirp, literal zero padding, bit-reversed
scatter, two forward transforms, fused pointwise/inverse scatter, inverse
transform, post-chirp, and normalization—and proves the resulting rectangle
contains the exact CUDA-shaped line. The exact dataflow theorem finally
identifies that value with the direct positive DFT. No root-table validity,
floating-point instruction behavior, compiler output, or physical execution
is hidden in this composition; those remain separate, named premises or
refinement edges.

### Fully checked rational root path

`SparkInterval/Certified/HighDegreeSinCos.lean` supplies an explicitly
configured exact complex-exponential series followed by certified
double-angle steps. Lean proves its single-pass recurrence equals the finite
Taylor sum and applies `Complex.exp_bound` for the factorial tail.
`rootRectConfigured?_containsComplex` proves the root generator sound for
every positive term count and every climb depth; the qualified production
wrapper currently selects thirteen terms and nine steps. The generator in
`SparkInterval/Dirichlet/CertifiedRootTable.lean` first reduces the exponent
modulo the positive order, explicitly rejects order zero, and rounds the
resulting rational rectangle outward. It recognizes the four axis roots
before introducing the finite-width enclosure of `π`, so the checker accepts
exact singleton boxes for `±1` and `±i`.

The original 20-decimal-digit enclosure of `π` was too wide to fit some valid
production boxes: the first cross-language rejection occurred at chirp
length 53, index 52. `SparkInterval/Certified/HighPrecisionPi.lean` now
derives a 128-bit dyadic constant from Machin's identity and proved
exact-rational arctangent tails. The executable root checker uses only that
small dyadic constant; the longer Machin series is evaluated once by the
kernel while checking the theorem, not once per root.

The first implementation then fed that already-reduced, high-precision phase
interval into the older `sinCosTaylorInterval`, which performed another
period reduction using an unrelated coarser `2π` interval. The resulting
fixed `2e-20` widening could not be repaired by increasing the work
precision. `sinCosTaylorBoundedInterval` is the proved nonreducing entry
point: it accepts an already-reduced bounded interval, evaluates the rational
Taylor enclosure, and widens only for the supplied interval diameter. Its
theorem proves simultaneous sine and cosine containment for every real point
in that interval.

The term/depth pair was qualified separately from rational precision.
Sixteen terms with four steps first rejected the recurrence catalog at
length 7, row 6, in the odd-step component. Eighteen terms with four steps
passed 74,948 routine root checks but rejected the full source
maximum-order dump at length 399,988, row 14,560, in the chirp component.
That same row rejected at 160/80, 192/128, and 256/128, identifying the
fixed Taylor remainder rather than rational rounding as the cause. The
conservative twenty-four-term/four-step setting accepted all 399,988 rows in
386.07 seconds.

A theorem-backed parameter sweep then compared lower-degree, deeper-climb
settings without changing the containment theorem. On the same 25,000-root
case at `workPrecision=192`, `outputPrecision=128`, the finalists were:

| terms / steps | wall time | widest combined rational width |
|---:|---:|---:|
| 24 / 4 | 11.90 s | `4 / 2^128` |
| 13 / 9 | 8.08 s | `73 / 2^128` |
| 12 / 10 | 8.08 s | `289 / 2^128` |
| 11 / 11 | 8.12 s | `4394 / 2^128` |

The tied 13/9 setting was narrower on both the retained chirp and FFT
production-box samples. It accepted the full maximum-order recurrence dump:
399,988 rows and 799,976 exact-root containments in 263.13 seconds with
116,044 KiB peak RSS on the local DGX Spark. This is a 31.9% wall-time
reduction from the retained 24/4 replay. The checked dump was 25,599,232
bytes with SHA-256
`a759ae25bda9be6ec2bbe3c6fa0ef13eb5e539a617d7e155ed81c6dd27b15c43`.
The representative preflight also accepted complete recurrence dumps of
lengths 53, 127, 257, 2,500, and 10,000 and all 4,095 flattened roots through
FFT length 4,096. These are native replays of the kernel-checked source
algorithm, not compiler-refinement or execution-attestation claims.

`SparkInterval/Dirichlet/CertifiedBluesteinRootBridge.lean` then checks the
precise interface needed by the FFT proof: a production box must contain both
rational coordinate intervals. Those endpoint inequalities transfer root
containment to the production box. Positive certificates supply every
positive twiddle and half-angle chirp; exact conjugation supplies every
negative twiddle and both kernel wings; the padded middle is singleton zero;
and normalization is the exact singleton `1/L`. The bridge capstone composes
these facts with the complete directed Bluestein theorem.

`SparkInterval/Dirichlet/CertifiedRootWire.lean` provides the corresponding
total certificate checker for production data. It decodes four raw binary64
words to exact rational coordinate intervals, rejecting NaNs, infinities,
out-of-range words, and reversed endpoints; runs the checked root generator;
and tests four rational inequalities. A successful ordinary `Bool` proves
the decoded production rectangle contains the exact root. Exact-one,
one-ulp-too-low, reversed, NaN, and zero-order regressions exercise both
acceptance and fail-closed branches.

`SparkInterval/Dirichlet/CertifiedChirpStateWire.lean` checks the production
positive recurrence dump as a whole. It requires exactly one 64-byte
little-endian record per declared index, decodes the chirp and odd-step boxes,
and invokes the single-root checker at `(2*N,n^2)` and `(2*N,2*n+1)`.
Zero length, malformed binary64 words, truncation, trailing bytes, reversed
intervals, and the first failed component are rejected. The aggregate theorem
says that acceptance supplies a decoded row and proves both exact-root
containments for every `index < N`. Its native wrapper is:

```bash
lake build sparkinterval-check-dirichlet-chirp-state
.lake/build/bin/sparkinterval-check-dirichlet-chirp-state \
  CHIRP_STATE.bin LENGTH 192 128
```

The wrapper labels successful output
`lean_source_checker_result_unattested`, sets
`trusted_execution_attested=false`, and sets
`external_atom_discharged=false`. Thus a local replay is evidence for the
source checker; it is not confused with a compiler-refinement theorem or a
signed production execution.

`SparkInterval/Dirichlet/CertifiedFFTRootTableWire.lean` applies the same
boundary to a complete positive radix-2 root table. It accepts only the 19
source convolution lengths `4,8,...,2^20` and requires exactly `L-1`
little-endian 32-byte boxes. Its executable layout is the literal CUDA
layout: concatenate stages `s=2,4,...,L`, place stage `s` at flattened offset
`s/2-1`, and check its row `j` against `unitRoot s j`. The whole-file theorem
proves containment for every row selected by that layout. Non-finite words,
reversed endpoints, unsupported lengths, truncation, trailing bytes, and
failed comparisons all fail closed. The native wrapper is:

```bash
lake build sparkinterval-check-dirichlet-fft-roots
.lake/build/bin/sparkinterval-check-dirichlet-fft-roots \
  FFT_ROOTS_POSITIVE.bin LENGTH 192 128
python3 tests/certified_fft_root_table_cli_qualification.py \
  --checker .lake/build/bin/sparkinterval-check-dirichlet-fft-roots
```

Its successful JSON uses the same explicit
`lean_source_checker_result_unattested`,
`trusted_execution_attested=false`, and
`external_atom_discharged=false` labels. The negative production table is
constructed by exact endpoint conjugation of the checked positive table; the
separate Lean Bluestein bridge proves the corresponding mathematical
conjugation step.

The direct flattened-index decoder is constant-space: it does not materialize
a million-entry Lean list. Lean proves both
`flat = stage/2-1+j` and the exact inverse mapping
`specAtFlatIndex (stage/2-1+j) = (stage,j)` for every radix-2 stage row. The
source-shaped capstone combines that mapping with whole-file acceptance:
whenever `stage <= L` and `j < stage/2`, the decoded record at the literal
CUDA offset contains `unitRoot stage j`.

A production recurrence dump at `L=4096` supplied 4,095 flattened
rows to the native Lean checker at `workPrecision=192`,
`outputPrecision=128`. The retained local DGX Spark replay accepted every row
in 1.62 seconds with 88,984 KiB peak RSS. This bounded replay is a
checker/performance qualification, not a maximum-table replay or an
attestation. A linear per-row projection is about 6.9 minutes for the
`2^20-1`-row maximum table on this host; that projection was deliberately not
reported as a measured full replay.

The dedicated native Lean root benchmark replayed 25,000 roots at the
recommended `workPrecision=192`, `outputPrecision=128` on the local DGX Spark
in 8.12 seconds with 89,128 KiB peak RSS for the qualified
thirteen-term/nine-climb generator. Its exact folded width checksum was
`200599 / 2^128`, with widest combined coordinate width `73 / 2^128`.
At that measured rate, generating the
approximately 141 million fresh anchor roots implied by a 256-entry cadence
would cost about 12.7 aggregate CPU-core hours and is embarrassingly
parallel. This estimate covers exact-rational root generation only—not
production-box endpoint replay, recurrence replay, FFTs, hashing,
attestation, or the full campaign. The theorem verifies the mathematical
rational algorithm; refinement of the MPFR/CUDA producer and the physical
run remains separate.

The retained sweep executable can reproduce a candidate benchmark or a
source-order range check without modifying production constants:

```bash
lake build sparkinterval-certified-root-parameter-sweep
.lake/build/bin/sparkinterval-certified-root-parameter-sweep \
  benchmark 13 9 192 128 100003 25000
.lake/build/bin/sparkinterval-certified-root-parameter-sweep \
  chirp CHIRP_STATE.bin LENGTH START COUNT 13 9 192 128
```

### Chirp recurrence preparation path

The source simulation reports `18,106,321,498` prepared transform
enclosures, so independent MPFR sine/cosine calls remain a material
source-scale preparation cost even after cache scheduling.
`SparkInterval/Dirichlet/BluesteinChirpRecurrence.lean` proves the exact
two-state recurrence

```text
c[n+1] = c[n] * d[n]
d[n+1] = d[n] * exp(2*pi*i/N)
```

with `c[n] = exp(pi*i*n^2/N)` and `d[n] = exp(pi*i*(2*n+1)/N)`, then proves
the same recurrence for abstract outward-directed complex rectangles. Thus a
producer needs certified initial roots and two directed products per entry,
not a fresh transcendental evaluation for every chirp. The theorem allows
periodic fresh anchors.

`SparkInterval/Dirichlet/DFTRootRecurrence.lean` proves the analogous
one-state rule for each radix-2 stage: from a certified anchor and a
certified enclosure of `unitRoot(order,1)`, repeated abstract directed
complex multiplication encloses `unitRoot(order,start+count)`. This exposes
the exact mathematical boundary for a twiddle recurrence without asserting
that a particular native or device implementation realizes it.

The production host builder now instantiates this scheme with 256-bit MPFR
rectangles and a fresh anchor every 256 entries. It retains persistent MPFR
scratch space, uses the qualified sign-quadrant product hull, rejects order
zero and every fixed-width overflow, and fails closed if an exposed binary64
component exceeds width `2^-48`. Negative chirps and negative FFT roots are
constructed by exact endpoint conjugation of the positive boxes; independent
negative transcendental generation is retained only as a diagnostic. This
matches the conjugation premises of the Lean root/Bluestein bridge and halves
the production transcendental work.

The radix-2 root optimization has a separate exhaustive source-catalog
qualification:

```bash
cmake --build build/dgx-spark \
  --target sparkinterval-tg-dirichlet-fft-root-recurrence-qualification
```

It covers all 19 production convolution lengths from `2^2` through `2^20`.
For each length it dumps the positive recurrence table, its exact-conjugate
negative production table, and independently generated direct positive and
negative 320-bit MPFR tables. A separate C++ checker then recomputes every
root directly at 192 bits. The retained run checked 8,388,516 root
rectangles: 2,097,129 entries for each of the four tables. Every production
box contained the corresponding direct binary64 box. Of the positive
production boxes, 2,097,005 were byte-identical to direct generation and 124
were strictly wider; the negative counts were 2,096,796 and 333. The largest
internal MPFR component width was `3.284334902e-74`, and the largest exposed
binary64 component width was `3.330669074e-16`, below the
`3.552713679e-15` fail-closed ceiling.

Across the complete catalog, positive recurrence plus exact conjugation took
0.7521 seconds, while direct generation of both signs took 52.2304 seconds,
a 69.45x speedup. The positive maximum-length recurrence table has SHA-256
`76f6addc682fe10684bbf090cc4a05334c098d89f483dc1ab4a6cb0b36f4d3f8`.
The qualification also rejects truncated, trailing, finite-but-forged, and
invalid-length/sign/mode artifacts. This digest identifies the root-table
test payload; it is not the maximum-order impulse-output digest below.

At length `2^20`, cadence 256 generated the positive table in 0.333 seconds
and differed from direct binary64 generation in only eight wider entries.
Cadences 128 and 64 took 0.373 and 0.454 seconds and reduced that count only
to seven and six. Their maximum-order impulse widths were respectively
`8.474442004e-8` and `8.473623236e-8`, versus `8.474665147e-8` at cadence
256. That at-most 0.012% width improvement did not justify the slower
preparation, so production retains cadence 256.

An independent 192-bit MPFR replay covered lengths
`1,2,8,9,72,136,2500,399988`, both signs, and 805,432 chirp/odd-step state
records. Every recurrence box contained the independently generated direct
box; 805,210 of the production/direct records were byte-identical, with the
remaining 222 strictly wider. The largest internal MPFR component width was
`1.669278858e-37`; the largest exposed binary64 width was
`3.330669074e-16`, below the `3.552713679e-15` fail-closed ceiling.
Truncated, trailing, finite-but-forged, zero-length, oversized, and invalid
sign inputs were rejected.

Nine-run host medians for actual positive-plus-conjugate production were
about 31.0x faster than direct two-sign generation for the `q=10001`
component orders `[72,136]` and 29.4x faster for the `q=100000` orders
`[2,8,2500]`. In a separate full-plan comparison at `q=100000`, preparation
fell from 218.73 ms to 106.58 ms, and all 1,280,000 transformed payload bytes
were unchanged and passed the 192-bit replay. A controlled 320/256-bit test
selected 256 bits: the maximum-order case passed at both precisions, while
256 bits was faster and retained over `2e22` margin between measured internal
width and the binary64 fail-closed ceiling.

These are host preparation measurements, not H100 kernel timings. Lean proves
the recurrence, conjugation, and abstract directed arithmetic. MPFR
`sinpi`/`cospi`, the C++ implementation, binary64 conversion, compiler output,
and physical execution remain separate refinement/attestation boundaries.

### Maximum-order CUDA impulse qualification

The routine known-answer suite intentionally avoids a complete MPFR replay at
the largest cyclic order. A separate bounded qualification now exercises the
missing source-edge geometry:

```text
q = 399989
cyclic order = 399988
Bluestein convolution = 2^20
radix-2 butterflies = 31457280
```

The input is the exact impulse `x[0] = 1`, `x[n] = 0` for `n > 0`, so every
positive-character DFT output is exactly `1 + 0i`. The production executable
constructs the ordinary maximum-order plan, runs the kernel, checks that all
399,988 output rectangles contain that exact value, rejects any malformed or
wider-than-`2^-16` rectangle, and atomically writes a standard `TGDAFFO1`
artifact. An independent Python pass reparses every rectangle, repeats the
identity and width checks, and verifies the payload SHA-256.

Before allocating the plan, the executable requires a conservative
239,725,440-byte CUDA estimate plus 256 MiB of free-memory headroom. Both the
executable and Python supervisor enforce a 300-second bound. The qualification
is opt-in, so it does not enlarge routine CTest runs:

```bash
cmake -S . -B build/dgx-spark \
  -DSPARKINTERVAL_ENABLE_SLOW_QUALIFICATION_TESTS=ON
cmake --build build/dgx-spark \
  --target sparkinterval-tg-dirichlet-allchars
ctest --test-dir build/dgx-spark --output-on-failure \
  -R '^tg_dirichlet_allchars_max_order_impulse_qualification$'
```

It is also available without changing the CTest registration:

```bash
cmake --build build/dgx-spark \
  --target sparkinterval-tg-dirichlet-allchars-max-order-impulse-qualification
```

With the former direct-per-root builder, one retained local GB10 baseline
reported 13.168 seconds of certified plan preparation, 9.36 milliseconds for
the three `2^20` CUDA FFTs, maximum output component width
`7.567148463e-8`, and payload SHA-256
`519ed6891bf432e7941afcf7d980925ac8d6e186935837342310842ecb2f0f80`.
With the final cadence-256 recurrence, an independent retained run reported
0.648730742 seconds of plan preparation, 9.269087 milliseconds for the FFTs,
0.970528275 seconds for executable compute plus validation, and 1.414 seconds
for the complete Python qualification. Maximum output component width was
`8.474665147417682e-8`, about 12% wider than the direct-root baseline but
still roughly 180 times below the `2^-16` rejection threshold. Its standard
`TGDAFFO1` payload SHA-256 is
`d06cae659e98c56435d56d7a60a445d09dc2ca65792dac170768fe96089a71a9`.
Peak host RSS remained about 176 MiB. The strict H100 executable also
compiled to an `sm_90` cubin with `--fmad=false --ftz=false --prec-div=true
--prec-sqrt=true`; it was compiled, not executed, on the GB10.

The ordinary output publisher now independently rejects every non-finite,
reversed, or count-mismatched payload before creating its temporary output.
The routine KAT includes a finite-`DBL_MAX` input that overflows during the FFT
and confirms that no output artifact is published.

### Maximum-order delta-one semantic qualification

The maximum-order impulse above is a useful allocation, launch, and width
test, but the transform of `delta_0` is constant. A coherent high-stage
twiddle sign or index error can therefore be hidden by the matching forward
kernel and inverse tables. The separate delta-one qualification closes that
test gap without replacing the retained impulse check.

`SparkInterval.Dirichlet.BluesteinDFT.positiveDFT_basisOne_eq_unitRoot`
formally proves the expected output:

```text
x[1] = 1, x[n] = 0 for n != 1
DFT(x)[k] = exp(2*pi*i*k/399988).
```

The production executable runs this input through the ordinary
`399988`-order, `2^20` CUDA plan and checks all 399,988 output rectangles
against freshly generated 320-bit direct MPFR roots. The separate
`reference/tg_dirichlet_allchars_mpfr.cpp` checker independently reparses the
standard output artifact and recomputes every expected root at 192 bits. It
does not consume the production recurrence table. Thus a high-stage sign,
root offset, stage offset, or flattened-layout error cannot pass merely by
remaining internally consistent with the inverse table.

An additional Python pass checks the exact `TGDAFFO1` identity, every finite
ordered interval and width, the payload hash, and a hash of the complete
header-plus-payload artifact. Truncated, trailing, finite-but-forged,
swapped-index, conjugated-sign, wrong-header, invalid-precision,
invalid-device, and invalid-runtime cases fail closed. The qualification
remains opt-in:

`SparkInterval/Dirichlet/CertifiedBasisOneOutputWire.lean` now supplies a
second, theorem-backed audit of that same retained artifact. Its reusable
headerless layer requires exactly `order` consecutive 32-byte binary64 boxes
and proves that every accepted row `k` contains `unitRoot order k`. The full
artifact layer parses the literal 56-byte `<8sIIIIQQQQ>` `TGDAFFO1` header
and pins version 1, q 399989, one component, one batch, group order and value
count 399988, and 31,457,280 butterflies. Only elapsed nanoseconds is allowed
to vary. Its capstone composes every row containment with
`positiveDFT_basisOne_eq_unitRoot`, so acceptance identifies each box with
the exact positive DFT output of `delta_1`. The scan constructs no decoded
root table and fails closed on a size mismatch, wrong header, non-finite or
reversed endpoints, and a failed rational-containment comparison.

The native wrapper reads the complete frame, rechecks its size after the read,
and hashes all header and payload bytes:

```bash
lake build sparkinterval-check-dirichlet-basis-one-output
.lake/build/bin/sparkinterval-check-dirichlet-basis-one-output \
  --maximum-order-delta-one TGDAFFO1.bin 192 128
```

It reports `lean_source_checker_result_unattested`,
`trusted_execution_attested=false`, and
`external_atom_discharged=false`. Its full-file SHA-256 can be compared with
the producer and independent qualification reports. The hash includes the
run-dependent elapsed-time word; it is therefore an identity for one
particular artifact, not a stable arithmetic-output identifier. This Lean
source theorem does not itself establish native-code refinement, CUDA
compilation correctness, execution attestation, or an analytic result.

```bash
cmake --build build/dgx-spark --target \
  sparkinterval-tg-dirichlet-allchars-max-order-delta-one-qualification
```

With slow CTest registration enabled, its test name is
`tg_dirichlet_allchars_max_order_delta_one_qualification`. The runner and
checker reports identify this as a bounded semantic qualification; they are
not execution attestations or compiler-refinement proofs.

A retained local GB10 run checked all 399,988 outputs twice and completed the
full Python orchestration, including hostile artifacts, in 18.55 seconds wall
time with 179,896 KiB peak host RSS. Plan preparation took 0.662144794
seconds, the three `2^20` CUDA FFTs took 9.320832 milliseconds, production
320-bit semantic validation took 5.055045280 seconds, and the independent
192-bit checker took 3.778098296 seconds. The maximum output component width
was `1.0818025353298566e-7`, over 141 times below `2^-16`. The payload SHA-256
was `d0749a7d4fff4880a2361b3c1bbcab036f7f1f02094f74094c06958f5e90c6f0`;
the complete standard artifact SHA-256 was
`b8bd4d20a13e408eb5d8c55c4436deb3cf57662819bf790fa061fdf842afc159`.
The complete-artifact hash is intentionally run-specific because the standard
header includes the measured transform time; the payload hash identifies the
retained arithmetic output.

A fresh retained frame was then generated specifically for the Lean checker.
The producer validated all 399,988 rows against its 320-bit direct roots in
6.05 seconds of guarded compute plus validation, and the independent MPFR-192
executable accepted the complete frame in 3.61 seconds. The rebuilt
13-term/9-step Lean native checker accepted all rows and hashed the complete
12,799,672-byte artifact in 2:21.32 wall time with 102,044 KiB peak RSS. It
reported the full-file SHA-256
`0dd900b97f26bed7048d5217ef527727c4633dd96ae41d73f9e8c3a76ff92394`,
exactly matching both `sha256sum` and the producer report. That hash differs
from the earlier retained run above only because this standard header records
a different elapsed transform time; the payload SHA-256 remained
`d0749a7d4fff4880a2361b3c1bbcab036f7f1f02094f74094c06958f5e90c6f0`.
As a semantic negative control, the same Lean CLI rejected the identically
sized maximum-order delta-zero artifact at output index one.

This helper is used by:

- `h100_tg_dirichlet_lattice_kernel.cu`;
- `h100_tg_dirichlet_largeq_batch.cu`, including the seeded frontend that
  reuses it; and
- `h100_tg_dirichlet_allchars_bluestein.cu`.

### Shared-memory radix-2 prefix

The first at most ten DIT radix-2 stages cannot communicate outside a
1024-value aligned tile. `fftInitialStages` loads one such tile into 32 KiB of
shared memory, executes the identical stage/butterfly graph with a barrier
after every stage, and writes it back once. Later stages still use the
original global-memory kernel.

This changes storage locality, not the mathematical graph or directed
operation order. A 2048-value/64-KiB candidate was rejected: after opting in to
the larger dynamic shared-memory allocation it did not improve the stable
`q=100000` GB10 median.

### Fused pointwise product and inverse bit reversal

Bluestein's pointwise product is now written directly to the bit-reversed
address consumed by the inverse DIT transform. The product is rounded exactly
where it was before; the eliminated kernel only copied those bits. This
removes one full workspace read/write pass and one launch per transformed
dimension.

### Exact source-grid ordinate scaling

The large-q source contract checks `t_denominator = 64` and
`t_numerator <= 2^53`. Therefore

```text
double(t_numerator) * 0x1p-6
```

is exact and equals both directed endpoints of `t_numerator / 64`. The batch
and seeded kernels use that singleton instead of performing two directed
divisions per residue. A forged denominator is rejected before launch.

## Bounded GB10 measurements

All medians below are kernel event times. Preparation, input parsing, hashing,
host/device transfer, analytic box generation, FFT consumers, and attestation
are excluded.

| Stage and bounded shape | Repetitions | Before | After | Improvement |
|---|---:|---:|---:|---:|
| Standalone Taylor, 1,000,000 residues, `q=10001..10250`, `t=635/64` | 7 runs x 100 | 1472.285 ms | 1089.280 ms | 26.01% less time, 1.352x |
| All-character, `q=10001`, orders `72 x 136`, batch 64 | 7/5 runs x 10 | 30.526 ms | 13.552 ms | 55.61% less time, 2.253x |
| All-character, `q=100000`, orders `2 x 8 x 2500`, batch 64 | 5 runs x 5 | 110.212 ms | 95.870 ms | 13.01% less time, 1.150x |
| Taylor plus certified-box composition, `q=10001`, batch 64 | 7/5 runs x 20 | 68.075 M values/s | 115.113 M values/s | 1.691x throughput |
| Seeded Taylor/recovery frontend, `q=10001`, batch 64 | 5 runs x 20 | 67.428 M values/s | 69.403 M values/s | 1.029x throughput |

The arithmetic bottleneck remains the transform. On the bounded `q=10001`
shape, the optimized composer takes about 5.44 ms and the optimized transform
takes about 13.55 ms, so the transform is roughly 71% of their combined kernel
time. The relative gain depends strongly on the component orders: a
convolution that fits entirely in the shared prefix benefits more than one
with many later global stages.

These are local GB10 observations. They are not converted into an H100
speedup, source runtime, Azure cost, or complete-proof ETA.

## Independent arithmetic checks

The normal known-answer tests were extended with:

- exact-rational Taylor replay at the maximum-`q` edge and at `t=0`;
- 192-bit MPFR transform replay for `q=5,7,8,15,257,509,1031`;
- explicit positive, negative, and zero-crossing interval quadrants;
- signed-zero and subnormal-width input boxes;
- 192-bit MPFR replay at source-shaped `q=10001` and `q=100000`;
- 384-bit MPFR replay of the fused Taylor/composition output;
- rejection of a reversed transform input interval, a negative Taylor radius,
  a forged CRT descriptor, and a forged source-grid denominator.

The optimized and immediately preceding binaries were also compared directly.
After excluding timing fields in their headers:

- `q=10001`, batch 64 all-character payload: zero differing bytes;
- `q=100000`, batch 64 all-character payload: zero differing bytes;
- seven `q=10001`, batch 64 certified-box outputs: zero differing bytes; and
- five `q=10001`, batch 64 seeded outputs: zero differing bytes.

The exact/MPFR tests are the semantic authority; byte identity is an additional
regression check, not a substitute for containment replay.

The chirp corpus additionally checks the periodic-anchor producer against
direct 192-bit MPFR at the maximum source component order and exercises
hostile state-dump lengths, payloads, signs, and geometry. The strict H100
cross-build contains an `sm_90` cubin; this establishes compiler acceptance,
not H100 execution semantics.

Build and run the principal checks with:

```bash
cmake --build build/dgx-spark --target \
  sparkinterval-tg-dirichlet-lattice \
  sparkinterval-tg-dirichlet-lattice-exact \
  sparkinterval-tg-dirichlet-largeq-batch \
  sparkinterval-tg-dirichlet-largeq-seeded \
  sparkinterval-tg-dirichlet-allchars \
  sparkinterval-tg-dirichlet-allchars-mpfr \
  sparkinterval-tg-dirichlet-residue-composition-mpfr -j4

ctest --test-dir build/dgx-spark --output-on-failure -R \
  '^(tg_dirichlet_lattice_known_answers|tg_dirichlet_largeq_batch_known_answers|tg_dirichlet_allchars_known_answers|tg_dirichlet_resident_handoff_known_answers|tg_dirichlet_tmajor_row_resident_seeded_known_answers)$'
```

Both local `sm_121` targets and strict `sm_90` targets were rebuilt from
source. Cross-building an `sm_90` binary on the GB10 is only a compiler audit,
not H100 execution evidence.

## CUDA sanitizer qualification

Each of `memcheck`, `initcheck`, `racecheck`, and `synccheck` completed with
zero errors. The bounded invocations covered:

- 257 maximum-`q` Taylor requests;
- a `q=1031` all-character transform whose 4096-point convolution executes
  both the shared prefix and later global stages;
- 19,584 fused certified-box values; and
- 19,584 seeded-recovery values.

The command form was:

```bash
for tool in memcheck initcheck racecheck synccheck; do
  compute-sanitizer --tool "$tool" --error-exitcode 99 \
    RUNNER INPUT OUTPUT 0 1
done
```

Compute Sanitizer tests memory, initialization, race, and barrier behavior for
these bounded executions. It does not prove CUDA hardware semantics, compiler
correctness, numerical containment, or source-scale liveness.

## Remaining trust and production boundary

This optimization does not change any trust flag. In particular:

- no full source computation was run;
- no H100 performance result was measured;
- no certified Hurwitz-lattice source artifact was produced here;
- no completed-L zero-isolation or multiplicity/completeness artifact was
  admitted;
- no compiler or native-execution refinement was added; and
- no external atom was discharged.

The fast path is ready for bounded conformance and for later measured H100
qualification once the source producer, typed multi-q handoff, useful-width
audit, zero closure, and attested execution boundary are complete.
