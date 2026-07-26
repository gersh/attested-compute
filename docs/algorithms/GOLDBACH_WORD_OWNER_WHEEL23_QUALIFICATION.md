# Goldbach through-23 word-owner wheel qualification

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Outcome

The packed through-23 initializer is exact on the qualification corpus and is
promising enough to measure on H100. It remains a macro-off,
qualification-only candidate. No production source, default target,
registration, receipt, production theorem, or execution trust boundary was
changed.

The companion
[base-trio Lean arithmetic model](GOLDBACH_WORD_OWNER_WHEEL23_LEAN.md) proves
the phase equation, duplicated-table semantics, small-prime restoration, and
composition with the remaining clear list. The
[phase-hoist machine-arithmetic module](../../SparkInterval/TernaryGoldbach/GoldbachWordOwnerWheel23PhaseHoist.lean)
additionally proves the exact host `UInt64` residue, device `UInt32`
multiply/add, no-wrap bounds, two guarded subtractions, and packed-table
address bounds. The qualification has not proved that CUDA, NVCC, PTX, or
SASS refines those Lean models.

On the local NVIDIA CC 12.1 device, the exact historical terminal-segment
initializer measured:

| Path | Median of 101 interleaved launches |
| --- | ---: |
| Current literal clears through 2039 | `4.610080 ms` |
| Phase-hoisted wheel through 23, then literal clears 29 through 2039 | `4.142144 ms` |

The ratio is `1.112969`, or about 10.1% less initializer time. For 100
source-shaped segments, representing a nominal 20-billion-even campaign, the
same run measured:

```text
current initializers                       459.778594 ms
candidate initializers + one table build  415.984801 ms
one table build                              2.399584 ms
```

Each historical segment visits `200,500,000` odd word inputs because it
includes the source overlap. The 100-launch total therefore contains
`20,050,000,000` odd word inputs; “20 billion evens” is the nominal campaign
geometry.

This does not reproduce the earlier approximately 3.55% *whole-program*
pilot as the same metric. The pinned result isolates only the word-owner
initializer and is from CC 12.1, not H100. A source-integrated, repeated H100
measurement is still required before considering promotion.

## Isolation

The experiment consists of:

- `gpu/platform/h100/h100_tg_goldbach_word_owner_wheel23_qualification.cu`;
- `tools/qualify_goldbach_word_owner_wheel23.py`;
- `tests/test_goldbach_word_owner_wheel23_qualification.py`; and
- this document.

The CUDA file refuses to compile unless
`SPARKINTERVAL_ENABLE_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION=1`. The CMake
option
`SPARKINTERVAL_BUILD_TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION` defaults
to `OFF` and creates separate portable and strict-H100 executables only when
requested.

The separate arithmetic proof and its tests are documented in the companion
Lean note. The temporary exploratory prototype was not copied into
production: it also reverted an unrelated packed-coverage-count change. The
qualification source reimplements only the initializer experiment and keeps
the rest of both compared paths identical.

Every result explicitly retains:

```text
classification                    qualification-only-unpromoted-candidate
candidate_selected_in_production  false
production_identity_changed       false
production_ready                  false
performance_evidence_eligible     false
release_build_profile_eligible    true
runtime_instrumentation_status    not-inspected-by-runner
lean_bridge_complete              false
receipt_emitted                   false
theorem_claimed                   false
```

## Three compared semantics

For a word index `w`, bit `j` represents

```text
q_low + 2 * (64*w + j).
```

The independent CPU reference initializes every complete output word to one.
For each of the 308 odd primes through 2039, it clears the arithmetic
progression beginning with the first odd multiple in the full padded span,
raised to `p²` when necessary, and advances by `2p`.

The current CUDA control initializes one word per thread and invokes the
literal compile-time clear helper for every one of those 308 primes.

The candidate replaces only the first eight invocations, for

```text
3, 5, 7, 11, 13, 17, 19, 23,
```

with a packed wheel load. Its segment-invariant starting residue is computed
once on the host, not once per owner thread. A single shared macro expands the
unchanged exact prime roster from 29 through 2039 in both CUDA paths. Because
a residue wheel would also clear each small prime itself, the candidate
explicitly restores 3 through 23 when the prime lies in the owned word. The
later literal clears retain the original `candidate >= p²` guard.

Acceptance compares the CPU, current CUDA, and candidate CUDA arrays at every
word. Counts or sampled bits are not sufficient.

## Wheel table, phase, and carry

The odd-residue modulus is

```text
M = 3 * 5 * 7 * 11 * 13 * 17 * 19 * 23
  = 111,546,435.
```

Logical bit `r` records whether `2r + 1` is coprime to the eight wheel primes.
The table appends 64 duplicated logical bits so every unaligned 64-bit load
can read two adjacent packed words without a wrap branch:

```text
logical bits             111,546,499 = M + 64
packed words               1,742,915
device bytes              13,943,320
surviving residues        36,495,360
table SHA-256
18dab40449926ec6b691b5052aaaf7f16528827bfcb8371eb78e4fcfa02b1faa
```

The device initializer evaluates the eight divisibility predicates directly.
The independent host builder instead starts from set bits and clears eight
arithmetic progressions. Qualification requires all `1,742,915` packed words
to match, every one of the 64 carry bits to equal the corresponding head bit,
all physical padding bits to be zero, and the survivor count and digest above
to match.

For word `w`, the candidate phase is

```text
phase(w) = (((q_low - 1) / 2) + 64*w) mod M.
```

Because `q_low` is odd, the host computes

```text
q_half_mod = (q_low >> 1) mod M.
```

The pinned source segment has at most `3,132,813` words. Thus every live
`w ≤ 3,132,812` satisfies `w < M`, and the unreduced phase numerator obeys

```text
64*w                                      ≤ 200,499,968 < 2M
q_half_mod + 64*w                         ≤ 312,046,402 < 3M
312,046,402                               < 2^32
```

The kernel therefore forms that numerator in `uint32_t` and applies exactly
two guarded subtractions of `M`. This is the exact residue without either
per-thread modulus. The host launcher rejects any word count above the
qualified bound before launching the kernel. Every qualification run also
attempts `3,132,814` words and requires that oversized launch to be rejected
before CUDA dispatch. The result records the bound, largest numerator, `3M`,
`UINT32_MAX`, accepted live launches, and rejected oversized launch as
fail-closed fields.

After reducing the phase, the kernel extracts a 64-bit mask from two
successive table words. The wheel-period-carry case begins 32 odd positions
before the period end and exercises the duplicated margin. The source-shaped
and terminal cases exercise all successive phase values through the maximum
qualified word index.

## Exact differential corpus

The fixed cases are:

| Case | `q_low` | Odd inputs | Padding | Set bits | Output SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| Low-prime restoration | `3` | 256 | 0 | 96 | `98a48380edf9293dfc45e644ca7ebd6637edab6342e955de4d6ec2730571d35f` |
| Wheel-period carry | `223092807` | 256 | 0 | 33 | `79543ba9e14f6856ae97e620f134a1bd43cba91c2df753428a78925b35586aba` |
| Source height/non-word end | `31249998799000003` | 262,147 | 61 | 38,444 | `215cc8aebd0ea6f8424cc62ccae0944154150c8e4b2bbd04370a9709d85f6041` |
| `UINT64_MAX` edge | `18446744073709027329` | 262,144 | 0 | 38,564 | `58c15a92591ed0ecc04b399e0b212e30b113691e60974013efdc5a74f6ff0073` |

The harness also centers a 256-odd-input case at `p²` for every one of the
308 primes. The aggregate transcript digest is:

```text
1ea5fd5c3498ec7914892f90c15ec4c0081f3348e2c55a73121c488c94c3f0aa
```

The exact historical terminal segment is:

```text
q_low                     31,249,999,599,000,003
intended q_high           31,250,000,000,000,001
full padded-word q_high   31,250,000,000,000,065
odd inputs                           200,500,000
packed words                            3,132,813
padding bits                                   32
set bits                               29,453,809
output SHA-256
2a643ef55c59f4d3eb4bc8884737a208233116178aff81e2ebd007478564dd24
```

All `3,132,813` CPU/current/phase-hoisted-candidate words match. Padding is
intentionally included because the source initializer writes complete words.

## Compiler and runtime checks

The local Release artifact reported:

| Kernel | Registers/thread | Local/thread | Static shared |
| --- | ---: | ---: | ---: |
| Table initializer | 26 | 0 | 0 |
| Current literal initializer | 50 | 0 | 0 |
| Through-23 candidate | 50 | 0 | 0 |

The separately cross-compiled strict SM90 artifact contains only `sm_90`
cubins. `ptxas` reported 25, 34, and 34 registers respectively, with zero
stack frame, spill stores, and spill loads for all three kernels. This was a
cross-build; the strict binary was not run on H100.

Bounded CUDA Compute Sanitizer runs completed with:

```text
initcheck: ERROR SUMMARY: 0 errors
memcheck:  ERROR SUMMARY: 0 errors
racecheck: 0 hazards displayed (0 errors, 0 warnings)
```

The two output buffers are each bounded by `3,132,813 * 8 = 25,062,504`
bytes for the exact terminal run. The wheel occupies `13,943,320` device
bytes. The table initialization completes before any candidate launch; every
table word and every output word has one owner. The sanitizer evidence checks
the implemented accesses and initialization order but is not a formal CUDA
memory-model proof.

## Reproduction

The fail-closed runner requires the exact generated Goldbach source rather
than trusting an asserted hash:

```bash
python3 tools/qualify_goldbach_word_owner_wheel23.py \
  --current-source /path/to/optimized/source/src/goldbach.cu \
  --mode bounded --pretty

python3 tools/qualify_goldbach_word_owner_wheel23.py \
  --current-source /path/to/optimized/source/src/goldbach.cu \
  --mode source-segment --pretty
```

It checks the source SHA-256, parses the complete increasing 308-prime
word-owner roster, compiles and runs the native artifact, validates every JSON
field and known answer, and separately builds and audits strict SM90 SASS.
Unknown fields, changed trust flags, changed digests, resource drift, stack or
spills, and non-sm90 cubins are rejected.

The source pins are:

```text
qualification CUDA source
c7a43e1839ab46c31c7d1f7d22baa7359e7927df36e70a66fbd819405d0510ef
current generated Goldbach source
2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c
```

The machine-arithmetic proof can be checked independently with:

```bash
lake env lean \
  SparkInterval/TernaryGoldbach/GoldbachWordOwnerWheel23PhaseHoist.lean
```

The portable CMake target is:

```bash
cmake -S . -B build-wheel23 -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION=ON
cmake --build build-wheel23 \
  --target sparkinterval-tg-goldbach-word-owner-wheel23-qualification
```

Adding `-DSPARKINTERVAL_BUILD_H100_NATIVE=ON` exposes the separate strict
`sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification` target.

## Trust boundary and next gate

The base-trio Lean module proves the pure arithmetic model. This qualification
does not prove CUDA/NVCC/SASS refinement to that model. It authenticates no
physical run and emits no receipt. The independent CPU comparison, source
pins, SASS/resource checks, and sanitizers are strong engineering evidence for
algorithm selection, not a formal execution certificate.

The next gate is a repeated strict-H100 run followed by a source-integrated
A/B campaign that retains every other optimized GoldbachGPU transform. Only
if that whole-program result is stable should a separate reviewed source
transform, new production source identity, and CUDA-to-Lean refinement be
considered.
