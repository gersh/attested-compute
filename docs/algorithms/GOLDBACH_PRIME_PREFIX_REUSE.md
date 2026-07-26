# Goldbach prime-prefix reuse candidate

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

This is one bounded, host-side optimization of the qualified GoldbachGPU v1
candidate. It is a distinct v2 candidate. It does not alter the v1
qualification package, a production registration, a source-scale result, an
attestation, or a Lean atom.

All reports retain these gates as false:

```text
confidential_attestation_completed = false
lean_atom_discharged                = false
production_identity_promoted       = false
source_scale_completion            = false
target_h100_measured                = false
```

The candidate ID is:

```text
sparkinterval.goldbach-10pow27-wheel47-warp32749-shifted-packed-prime-prefix-reuse.v2
```

## Optimization

The v1 executable builds a complete `PrimeBitset` through

```text
smallHigh = max(floor(sqrt(limit)) + 1, pSmall),
```

then scans it in ascending order to construct `small_primes`. At the bounded
source-height range used here, `smallHigh = 176776697`. V1 then independently
runs a second sieve through the phase-2 bound `100000000`.

V2 instead sets

```text
cpu_primes =
  upper_bound(small_primes, 100000000)
```

when `smallHigh >= 100000000`. For smaller inputs it executes the original
independent generator unchanged. This removes one duplicate CPU sieve and
does not change any GPU kernel.

[`GoldbachPrimePrefixReuse.lean`](../../SparkInterval/TernaryGoldbach/GoldbachPrimePrefixReuse.lean)
proves the finite set equation

```text
filter (primeTable smallHigh) (p <= phase2Bound)
  = primeTable phase2Bound
```

under `phase2Bound <= smallHigh`. The theorem uses only the standard Lean
base trio reported by a fresh `#print axioms`. It is a mathematical
prime-table statement, not a compiler or hardware refinement.

The bounded diagnostic goes further at the concrete C++ boundary: it builds
both ordered vectors and evaluates their `std::vector<uint64_t>` equality
before launching GPU work. Thus the check compares all `5761455` entries
element-for-element, rather than comparing only sizes, endpoints, counts, or
digests.

## Identities

| Item | Bytes | SHA-256 |
| --- | ---: | --- |
| qualified v1 `goldbach.cu` | 71853 | `2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c` |
| complete qualified v1 source-closure digest | — | `ebc51bef0b0941c99fe9d7ce994093de16bee07500d22a4e0f86dd2e44f885a0` |
| v2 productive `goldbach.cu` | 72477 | `51e989cc56004290922f99b12653a3cee3a6bcd3321fb35a3e890daf3912694a` |
| v2 exact-vector diagnostic `goldbach.cu` | 72976 | `e2862aec57e3fc2c0c5cb32004690a7e98039133b3a480529f1e74c2d924505a` |
| complete v2 source identity | — | `3c779590babe1a9eb5e5fb21914129a6ed8edd49e4c0814c05c7f481a6dbffeb` |

The complete identity commits the v1 closure, v2 closure, algorithm ID, and
the exact transformer-module bytes. Recreate and revalidate it with:

```bash
python3 tools/prepare_goldbach_prime_prefix_reuse.py \
  /work/goldbach-qualified-v1/source \
  /work/goldbach-prime-prefix-v2 \
  --pretty
```

The retained local native builds used identical compiler flags and produced:

| Role | Executable bytes | SHA-256 |
| --- | ---: | --- |
| v1 control | 1384800 | `01ae21515e2998ba5ab886bd79d529d143c580196ddf72c95923dfd614a779ad` |
| v2 productive | 1384800 | `7bee5124893126e00a0dfc335213552e9361a52a244db667c249c3ce84b97e51` |
| v2 exact-vector diagnostic | 1384952 | `2818220191e07cac609cadfffa2bc9175eab2ce1c69df25b12b5ee12f9cbcb2b` |

These are aarch64/GB10 bounded benchmark binaries, not Azure or production
artifacts.

A separate aarch64 `sm_90` rebuild used the same normalized qualification
flags and compiler random seed as v1. Its host executable changed, as
expected, to SHA-256
`5e3d8ccc6fe067b4e3832b959469f2202906972de09bea58df47324ba9c74425`
(`1843552` bytes). Because the optimization is host-only, all retained device
artifacts were byte-identical to v1:

| Device artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| PTX | 569416 | `f285db9852e480f7d08d3d2c84886767ccf12dea0d04ea60d853fea2c597804a` |
| primary cubin | 674568 | `d3de752cbb63e5bf57c6d6f4f5eb0926f93809e5b3774c03e82983ad74af9e87` |
| device-link cubin | 1544 | `a5c3dbabba82a6f920dd409b49ce9e397a4566a8f78c004e9b1f72727898d4f9` |
| SASS | 2911025 | `af6a382d8d9711178915ffff83e9b55478d0068b63b3716aec21d1b4c5824c39` |

The existing strict PTX and SASS lexical audits both accepted these exact v2
device artifacts. This proves identity of the retained device bytes under
that build, not semantics of the changed host code or compiler correctness.

## Bounded differential result

The benchmark used the exact terminal range

```text
[31249998800000002, 31250000000000000]
```

of `600000000` evens. It first ran the exact-vector diagnostic, then one
warmup per role and six timed observations per role in repeated ABBA order.
Every v1, v2, and diagnostic run had identical non-timing semantic transcript
fields, reported the complete range satisfied, and had zero phase-2
fallbacks.

A separate low-boundary branch check used
`[2800002, 4000000]`, where `smallHigh = 1000001` is below the phase-2 bound.
V2 therefore selected the unchanged independent-sieve branch, checked all
`600000` evens, and reported zero fallbacks. This guards the branch that is
not exercised by the source-height benchmark.

On the local NVIDIA GB10:

| Measurement | v1 median | v2 median | Change |
| --- | ---: | ---: | ---: |
| initialization | 425.8275 ms | 175.634 ms | 2.42452x |
| reported GPU computation | 0.263419 s | 0.269001 s | no claimed improvement |
| whole-process wall | 0.946567608 s | 0.6994770265 s | 1.35325x |

The initialization saving was `250.1935 ms` per process. If the old
one-process-per-leaf geometry were retained for all `65536` leaves over eight
equal-throughput GPUs, this bounded GB10 measurement would reduce repeated
initialization from about `0.96899` to `0.39966` wall hours, saving
`0.56933` wall hours.

The retained machine-readable qualification report had SHA-256
`03bc4611af69e6064758c4792cec83b3195b2399c2d8c503166e9dfcf8c84b06`.
The report itself is a local bounded artifact, not a repository dependency.
Reproduce a report with:

```bash
python3 tools/benchmark_goldbach_prime_prefix_reuse.py \
  /work/v1-native/goldbach-gpu \
  /work/v2-native/goldbach-gpu \
  /work/v2-crosscheck-native/goldbach-gpu \
  --rounds 3 --warmups 1 --pretty
```

## What remains dominant

This optimization addresses the dominant cost of a short bounded invocation,
but not the dominant source-scale cost. The retained 20-billion-even profile
attributes `52.1%` of GPU kernel time to the atomic tail, `21.8%` to
word-owner initialization, `16.4%` to the warp sieve, and `9.3%` to shifted
coverage. Across the projected full campaign, work proportional to the
number of evens remains roughly sixty-four wall hours under the conservative
eight-GB10 envelope, while v2 repeated host initialization is roughly
`0.40` wall hours.

Before any promotion, v2 still needs:

1. a reproducible x86_64 SM90 qualification package with the new host
   executable and a v2 manifest (the aarch64 diagnostic device artifacts and
   lexical audits are complete);
2. an actual confidential H100 measurement;
3. source-scale checkpoint and completion receipts;
4. compiler/architecture refinement for the compiled program; and
5. a separately reviewed production registration.
