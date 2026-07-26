# Goldbach wheel-gap tail qualification

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Outcome

The wheel-gap enumerators are exact on the bounded differential corpus, one
complete historical terminal segment, and the three-window terminal
600-million-even geometry.  They are **not a stable performance improvement
over the retained wheel-through-47 tail on the local NVIDIA GB10**.  Both
candidate timing ratios crossed one across repeated sessions, and the largest
repeatable difference was too small to distinguish from local run-to-run
variation.  The candidates therefore remain macro-off, qualification-only,
and unpromoted.  These are not H100 runtime measurements.

This negative result is useful: replacing ordinary cofactor stepping with a
small-wheel gap lookup removes many loop iterations, but its divergent table
loads and extra state do not materially improve the already filtered
whole-tail kernel.  The nine-running-remainder variant also raises the local
Release register count from 26 to 46 without a stable timing benefit.

No Lean module was added for this rejected experiment.  The existing
[`GoldbachWheelFilter.lean`](../../SparkInterval/TernaryGoldbach/GoldbachWheelFilter.lean)
proves the mathematical justification for omitting cofactor events divisible
by the selected small primes.  A new physical gap-table refinement would not
close the CUDA/compiler boundary and would not support a production choice
after the measured performance result.

## Isolation from production

The experiment consists only of:

- `gpu/platform/h100/h100_tg_goldbach_wheel_gap_tail_qualification.cu`;
- `tools/qualify_goldbach_wheel_gap_tail.py`;
- `tests/test_goldbach_wheel_gap_tail_qualification.py`; and
- this report.

The CUDA source refuses to compile unless
`SPARKINTERVAL_ENABLE_GOLDBACH_WHEEL_GAP_QUALIFICATION` is explicitly
defined.  The qualification runner supplies that macro.  CMake does not
mention it, no default target builds it, and the prepared GoldbachGPU source
transformers do not import it.  No production source body, build default,
hash, registration, campaign profile, or receipt identity changed.

Every accepted report retains:

```text
classification                = qualification-only-unpromoted-candidate
lean_bridge_complete           = false
performance_evidence_eligible  = false
production_identity_promoted   = false
production_ready               = false
```

## Exact table and enumeration

The table is indexed by the `15,015` odd residue classes modulo

```text
30030 = 2 * 3 * 5 * 7 * 11 * 13.
```

Each byte contains:

- bit 7: whether the represented odd residue is coprime to
  `3 * 5 * 7 * 11 * 13`; and
- bits 0 through 4: the least positive even gap to the next such residue.

An exhaustive host check and an independent Python regeneration establish:

```text
encoded entries          15,015
surviving residues        5,760
maximum even gap              22
table SHA-256
8ce0f65ef7925ef7a01e56205d17ee8ce37989d7344f3f10aff0b43f23c8d9ae
```

The checks inspect all entries, recompute the survival bit, require the target
residue to survive, and reject every encoded gap having an earlier positive
even surviving gap.

For each tail prime `p > 32749`, the kernel computes the same overflow-guarded
first odd multiple and `p²` replacement as the ordinary and current
wheel-through-47 controls.  If its initial cofactor is `k`, the exact initial
table index is

```text
((k mod 30030) / 2).
```

After taking an encoded even gap `g`, it updates

```text
composite  := composite + p * g
cofactor   := cofactor + g
wheelIndex := wheelIndex + g / 2  (mod 15015).
```

Only small-wheel survivors are visited.  The first candidate kernel then
applies the unchanged exact modulus tests for

```text
17, 19, 23, 29, 31, 37, 41, 43, 47.
```

The second candidate initializes those nine remainders once and advances
each by `g`.  Since `g <= 22`, subtracting the modulus at most twice gives
the exact new remainder for every listed modulus.

The `15,015`-byte table is allocated in device global memory, copied once,
never written by the program, and loaded through `__ldg`.  This is a
read-only global-cache access, not CUDA `__constant__` memory.  An exploratory
constant-memory placement was roughly 20% slower under divergent indexing
and was discarded before the pinned qualification source.

## Differential boundary

The executable independently generates:

- every odd prefix prime through the word-owner cutoff `2039`;
- every odd tail prime in `(32749, floor(sqrt(qHigh))]`; and
- an exact CPU arithmetic-progression replay that retains the `p²` guard and
  subtraction-form overflow checks.

For every case, it starts all four CUDA routes from the same prefix-cleared
word array:

1. ordinary unfiltered raw tail;
2. retained wheel-through-47 tail;
3. wheel-gap lookup plus exact 17-through-47 filters; and
4. wheel-gap lookup plus running 17-through-47 remainders.

Acceptance requires the CPU output and all four complete packed-word outputs
to be identical.  Separate instrumented launches must also reproduce the
independent CPU raw-visit, small-wheel-survivor, and final-event counts.
Prime generation, CPU replay, host/device copies, and instrumented launches
are outside the reported kernel timings.

The fixed-answer corpus is:

| Case | Odd range | Odds | Raw / small / final events | Set bits | Output SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| low inactive | `4000001..4262143` | 131,072 | 0 / 0 / 0 | 17,240 | `9bbe647ca0591677b39c06a10f217194f076019f7e6aec1bd3ec8161443b6030` |
| `p²` activation | `1073807369..1074069511` | 131,072 | 2 / 1 / 1 | 19,477 | `c500d8de987c489e2c8de5ce5b1e2a1edc4a53b8f8bb06b42edf38ad2053eedd` |
| source height | `31249998799000003..31249998799524289` | 262,144 | 47,718 / 18,279 / 13,217 | 32,093 | `6d3d36b22ecec1fc80d897cd7a0c9f03e3d97eb15f5f11b74e9221c9602fe0bc` |
| non-word end | `31249998799000003..31249998799524295` | 262,147 | 47,719 / 18,280 / 13,217 | 32,093 | `a3764db98d0f1c637bcfb1e8daad50360e1adebbdebe7a770da63ef976ef0b14` |
| `UINT64_MAX` edge | `18446744073709027329..18446744073709551615` | 262,144 | 47,701 / 18,355 / 13,408 | 32,051 | `31fe43fc8c5f80b08a2fcf2292380f2bd7a2406a09a75f112d2df00524f53d23` |

The Python validator accepts exactly the documented schema and values.  Its
mutation tests fail closed on changed table invariants, source boundaries,
event counts, timing ratios, resource claims, promotion flags, and unknown
fields.

## Source-shaped counts and timings

The exact complete terminal-segment measurement fixes:

```text
qLow                         31249999599000003
qHigh                        31250000000000001
odd values                         200,500,000
tail-prime limit                   176,776,695
tail primes in (32749, limit]        9,856,924
raw tail visits                    120,704,837
small-wheel survivors               46,303,329
wheel-through-47 events              33,478,814
output SHA-256
211dc4345fa32379b434e5e3036ea48cb534a17da285865c758b4732886fafe7
```

Nine timed repetitions rotate the launch order among the four algorithms.
Four local sessions gave:

| Session | Current wheel-47 | Gap + direct filters | Gap + remainders |
| --- | ---: | ---: | ---: |
| 1 | `9.6852 ms` | `9.4098 ms` | `9.4960 ms` |
| 2 | `9.4408 ms` | `9.1585 ms` | `9.2476 ms` |
| 3 | `9.8407 ms` | `9.7212 ms` | `9.7988 ms` |
| 4, pinned runner | `8.678176 ms` | `8.688608 ms` | `8.709216 ms` |

The direct-filter candidate ranged from `3.08%` faster to `0.12%` slower;
the remainder candidate ranged from `2.09%` faster to `0.36%` slower.  The
sign reversal prevents a promotion claim.

The terminal-600-million mode measures the same whole-tail work for three
consecutive historical 200-million-even segments.  Each sieve window extends
by the historical one-million cofactor margin, so the exact measured total
is `601,500,000` odd values.  It contains:

```text
raw tail visits                    362,115,104
small-wheel survivors              138,910,143
wheel-through-47 events            100,446,929
aggregate output SHA-256
6424c3b4aaba11b1dc7a6bc534f81bc676f749b61c2893a62b353ea385910567
```

Each timing is the sum of the three tail-kernel event intervals.  Host resets
between windows are excluded:

| Session | Current wheel-47 | Gap + direct filters | Gap + remainders |
| --- | ---: | ---: | ---: |
| 1 | `30.103840 ms` | `30.121535 ms` | `30.136736 ms` |
| 2 | `28.286624 ms` | `28.470560 ms` | `28.176417 ms` |
| 3, pinned runner | `27.707456 ms` | `27.643041 ms` | `27.447776 ms` |

Here the direct-filter result ranges from `0.65%` slower to `0.23%` faster,
and the remainder result from `0.11%` slower to `0.95%` faster.  This is
again a noisy tie, not a material whole-tail improvement.  No timing value is
used for semantic acceptance.

For comparison, the bounded benchmark has `1,048,576` odds, `349,114` raw
visits, `133,841` small-wheel survivors, `97,023` final events, and output
SHA-256
`47e1e4ecfb918f21e9411f32d8904573935c64bca9e720aa2b50e052c1de6076`.
Its sub-20-microsecond timings are not used to infer source-scale speed.

## Compiler, resource, and sanitizer evidence

The local SM 12.1 Release artifact reports:

| Kernel | Registers/thread | Static shared | Local/thread | Max threads |
| --- | ---: | ---: | ---: | ---: |
| ordinary raw | 22 | 0 | 0 | 1024 |
| current wheel-47 | 26 | 0 | 0 | 1024 |
| wheel-gap + direct filters | 28 | 0 | 0 | 1024 |
| wheel-gap + remainders | 46 | 0 | 0 | 1024 |

The separately compiled strict SM90 artifact contains exactly the eight
expected instrumented and uninstrumented kernel sections and only `sm_90`
cubins.  `ptxas` reports:

| Kernel | Uninstrumented registers | Instrumented registers |
| --- | ---: | ---: |
| ordinary raw | 20 | 30 |
| current wheel-47 | 28 | 30 |
| wheel-gap + direct filters | 28 | 30 |
| wheel-gap + remainders | 32 | 32 |

All eight have zero stack bytes, spill loads, spill stores, and barriers.  The
SASS audit requires exactly eight `REDG.E.AND.64.STRONG.GPU`, ten
`REDG.E.ADD.64.STRONG.GPU`, and twelve `LDG.E.U8.CONSTANT` instructions.  It
rejects 32-bit global ANDs, `ATOM` instructions, and local `LDL`/`STL`
accesses.  The audited SASS SHA-256 is
`f2533035400d97f0699a8a8745da32e0c6d7cb8768ba56af5bd507b109d4abe6`.

Bounded Compute Sanitizer runs completed with:

```text
memcheck:  ERROR SUMMARY: 0 errors
initcheck: ERROR SUMMARY: 0 errors
racecheck: 0 hazards displayed (0 errors, 0 warnings)
```

Sanitizer timings are ignored.

These checks are runtime and compiler-inspection evidence.  They do not prove
that NVCC, PTX, SASS, the driver, or the GPU architecture refines the source
or the Lean arithmetic model.  They also do not authenticate a production
run.  Those boundaries are why the report cannot claim Lean closure or
production readiness.

## Reproduction and source pins

Run the three modes with:

```bash
python3 tools/qualify_goldbach_wheel_gap_tail.py \
  --mode bounded --pretty
python3 tools/qualify_goldbach_wheel_gap_tail.py \
  --mode source-segment --pretty
python3 tools/qualify_goldbach_wheel_gap_tail.py \
  --mode terminal-600m --pretty
```

The runner pins:

```text
qualification CUDA source
87ddcf9219e8965aa9626c0f6dc42ce9f01a5dc33f119b25725a9ec9ac855152
current wheel-transform module
b55f048db020430698f4c03b1d82c1f4e02a647e70ca44a20cf84ed2d8c914df
optimized-source verification module
78883b3d18c6b7cac080ee97e430bd464793b832e53637fa4a459e2c1dad2914
verified optimized source identity
8c19bf2825ff8a34ef9413f35620487f2062868f723b158228a071a5cf021359
current generated Goldbach source
2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c
```

It independently regenerates the wheel table before compiling, validates
every exact JSON field, and always builds and audits a strict SM90 artifact.

## Decision and next optimization target

Do not integrate either wheel-gap enumerator.  A more promising next
qualification target is a word-owner-aligned odd-residue wheel through 23:

```text
odd modulus classes       111,546,435
packed table size         about 13.3 MiB plus a 64-bit duplicate margin
access pattern            sequential two-word mask load per owner word
small-prime restoration   explicit for 3, 5, 7, 11, 13, 17, 19, 23
```

Preliminary whole-run GB10 observations for that design were approximately
`3.55%` faster by the median of four sessions, while a wheel only through 17
was about `0.3%`. The separate
[through-23 word-owner qualification](GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION.md)
now supplies the independent CPU/current/candidate all-word comparison,
low/`p²`/end/`UINT64_MAX` corpus, source and table pins, strict SM90
cross-build/resource audit, sanitizer pass, and source-segment initializer
timing. It remains unpromoted pending a repeated H100 and whole-program
source-integrated acceptance gate.
