# Optimized GoldbachGPU candidate qualification

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

This package qualifies the wheel-47 + warp-32749 + shifted-phase-1 +
packed-count GoldbachGPU candidate. The exact generated source can now be
selected by distinct 65,536-leaf plans for both the historical `[4,4e18]`
domain and the lowered `[4,31250000000000000]` domain. Plan execution,
receipt reduction, independent replay, and a domain-separated branch combiner
are implemented. None has run at source scale, and this package does not
register the optimized identity, attest an execution, establish source-scale
coverage, or discharge a Lean claim.

The candidate ID is:

```text
sparkinterval.goldbach-10pow27-wheel47-warp32749-shifted-packed.v1
```

Every package and calibration result must retain all five gates below as
false:

```text
confidential_attestation_completed = false
lean_atom_discharged                = false
production_identity_promoted       = false
source_scale_completion            = false
target_h100_measured                = false
```

No top-level production registry was changed for this candidate.

A later host-only prime-table-prefix reuse is deliberately tracked as the
distinct unpromoted v2 candidate in
[`GOLDBACH_PRIME_PREFIX_REUSE.md`](GOLDBACH_PRIME_PREFIX_REUSE.md). Nothing in
that experiment mutates or reinterprets this v1 package.

## Source identity

`tg_verifier/goldbach_optimized_source.py` starts from an exactly verified
hardened GoldbachGPU source tree and applies four transforms in one fixed
order:

1. warp-parallel sieve through prime `32749`;
2. shifted-word phase-1 coverage;
3. cofactor filtering through prime `47`; and
4. packed missing-bit counting.

The generator rejects any unexpected input marker, output size, or output
digest. The reviewed generated `src/goldbach.cu` identity is:

| Item | Value |
| --- | --- |
| hardened source identity | `9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55` |
| generated source bytes | `71853` |
| generated source SHA-256 | `2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c` |
| complete optimized-source identity | `8c19bf2825ff8a34ef9413f35620487f2062868f723b158228a071a5cf021359` |

The complete identity also commits the source closure and the exact bytes of
the three transformer modules. A separate all-live-word diagnostic is
generated from the same hardened source. Its `goldbach.cu` is `80762` bytes
with SHA-256
`7baa018b8e9d2a724c7808c2c5aaca4c98024d673baa3bb0104094c66ac33c67`.

`verify_optimized_source_tree` independently checks the complete transformed
closure against those reviewed bytes. It rejects extra files, symlinks,
multiply linked files, transformed-source drift, and transformer drift; it
does not regenerate a candidate and then trust its self-reported hash.

## Source-scale orchestration, still unrun

The historical optimized route is created with:

```bash
python3 tools/tg_goldbach_gpu_campaign.py \
  create-optimized-production-plan \
  --candidate-package-root /reviewed/goldbach-optimized \
  --candidate-manifest-file-sha256 \
    "$OPTIMIZED_CANDIDATE_MANIFEST_FILE_SHA256" \
  --source-root /reviewed/goldbach-optimized/source \
  --executable /reviewed/goldbach-optimized/artifacts/goldbach-gpu \
  --executable-sha256 SHA256 \
  --out /durable/goldbach-optimized/plan.json
```

The lowered route uses
`create-optimized-analytic-10pow27-plan`. The ordinary `run-group`,
`aggregate`, and `verify` commands dispatch from the plan's exact algorithm
and source identity, so an optimized receipt cannot be replayed under the
prepared base source.
Plan creation also revalidates the candidate package and requires the selected
source and executable to be its literal `source/` and
`artifacts/goldbach-gpu` entries. It rejects a script or an ELF whose class,
endianness, or machine differs from the manifest.

The package's domain-separated manifest self-hash is reproducibility
metadata, not authority: an editor can replace an artifact and recompute all
internal hashes. Production plan creation therefore also hashes the exact
canonical `candidate-manifest.json`, compares it with
`--candidate-manifest-file-sha256`, and requires that file digest to occur in
the source-reviewed
`REVIEWED_PRODUCTION_CANDIDATE_MANIFEST_FILE_SHA256S` allowlist. That
allowlist is intentionally empty until the exact Azure x86_64 package is
independently reviewed. Consequently the command above currently fails
closed; it documents the post-review invocation rather than claiming a
production admission.

For the historical atom,
`tools/tg_goldbach_campaign.py combine-optimized-gpu` pairs the exact
optimized binary aggregate with the full 492,700-range ladder. Its result has
a new kind and hash domain and explicitly retains the optimized algorithm,
plan, and source identities. It cannot enter the existing registered-v1
finalizer. The lowered campaign similarly provides `combine-optimized`.
These commands close the source-scale orchestration path without pretending
that the current Azure identity or a production receipt has changed.

The ordinary Lean refinement is
[`GoldbachOptimizedSourceRefinement.lean`](../../SparkInterval/TernaryGoldbach/GoldbachOptimizedSourceRefinement.lean).
It proves that a complete prime roster plus exact sieve survival supplies
prime-window soundness, and that every formulaic packed output row passing the
literal live-mask equation supplies the existing gap-free campaign evidence.
It also proves that at most 3,125,000 packed words, each contributing at most
64 missing bits, cannot wrap the source's 32-bit accumulator.

[`GoldbachTailProgression.lean`](../../SparkInterval/TernaryGoldbach/GoldbachTailProgression.lean)
models the candidate's literal quotient/remainder ceiling, even-multiple
adjustment, `p²` replacement, and subtraction-form upper guards. For every
relevant odd divisible target in the inclusive window it proves that the
start is accepted, the sequential and 32-lane warp loops cannot stop before
the target, and the targeted packed bit is live. It also proves the start and
`64*p` warp stride are below `2^64`, and proves the literal `(first & 1) == 0`
test is exactly the model's evenness branch. These theorems use only Lean's
foundational trio.

[`GoldbachWarpLaunchIndexing.lean`](../../SparkInterval/TernaryGoldbach/GoldbachWarpLaunchIndexing.lean)
then models the qualified source's literal 256-thread grid, 32-lane warp
decode, and rounded final block. It proves that every retained
`(primeIndex,lane)` pair has exactly one active block/thread owner and that
the launch numerator, grid cast, block product, and global index all fit in
32 bits under the live cutoff. It also proves the literal natural-number
bit mask `threadIdx.x & 31` equals remainder modulo 32. This theorem layer
uses only Lean's foundational trio.

The remaining proof boundary is physical CUDA/compiler realization of those
premises—including register/instruction correspondence, prime-buffer
identity, physical bit addresses, and atomic linearizability—not a new
Goldbach axiom.

## Reproducible SM90 artifacts

`tg_verifier/goldbach_optimized_candidate.py` uses a normalized build root,
relative source paths, `--frandom-seed` set to the source digest, prefix maps,
retained CUDA intermediates, one compiler thread, and no linker build ID.
Two fresh builds under different temporary roots produced byte-identical
target artifacts.

The retained local qualification was built with CUDA `13.0.88`,
`nvdisasm 13.0.85`, and GCC `13.3.0`. Its exact artifact pins are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| aarch64 host executable with SM90 device code | 1843552 | `618d18b965758438e1766d6178454c3ad67f0bda1bec969614905464acb05689` |
| PTX 9.0, target SM90 | 569416 | `f285db9852e480f7d08d3d2c84886767ccf12dea0d04ea60d853fea2c597804a` |
| primary SM90 cubin | 674568 | `d3de752cbb63e5bf57c6d6f4f5eb0926f93809e5b3774c03e82983ad74af9e87` |
| device-link SM90 cubin | 1544 | `a5c3dbabba82a6f920dd409b49ce9e397a4566a8f78c004e9b1f72727898d4f9` |
| `nvdisasm` SASS | 2911025 | `af6a382d8d9711178915ffff83e9b55478d0068b63b3716aec21d1b4c5824c39` |

The host executable above is an aarch64/GB10 qualification artifact. It must
not be submitted to Azure. The Azure materializer requires a freshly
qualified `x86_64` package and binds that package's new executable and
manifest digests. After reviewing that exact package, the canonical manifest
file digest—not its editable internal self-hash—must be added to the
production allowlist before any optimized production plan can be emitted.

## Compiler-resource and lexical audits

The SM90 `ptxas` report covered exactly eight kernels, reported no barriers
or register spills, and had the following register counts:

| Kernel role | Registers | Stack bytes |
| --- | ---: | ---: |
| fallback phase 1 | 52 | 96 |
| word-owner initializer | 32 | 0 |
| warp sieve | 32 | 0 |
| tail sieve | 30 | 0 |
| shifted coverage | 24 | 0 |
| coverage expansion | 10 | 0 |
| packed count | 10 | 0 |
| byte count | 8 | 0 |

The fail-closed PTX audit requires the exact eight-entry set, exactly two
64-bit global atomic ANDs, exactly two 32-bit global atomic adds, no 32-bit
atomic AND or CAS, the reviewed shifted-word load/OR/store shape, and the
64-bit packed popcount.

The SASS audit independently requires the exact eight text sections, exactly
two `REDG.E.AND.64.STRONG.GPU` instructions, exactly two
`REDG.E.ADD.STRONG.GPU` instructions, no 32-bit atomic AND, and the reviewed
popcount partition.

These are strict lexical checks. They do not prove reachability, operational
semantics, PTX-to-SASS compiler refinement, driver behavior, or hardware
execution.

## Bounded differential and fixed-answer checks

The full diagnostic independently runs:

- the filtered and unfiltered sieve and compares every live packed word;
- original and shifted phase 1 and compares every live coverage bit; and
- byte and packed missing-bit counting and compares the exact counts.

On the exact terminal range
`[31249998800000002, 31250000000000000]`, comprising `600000000` evens,
the productive binary took `0.268166` reported computation seconds and the
all-live diagnostic took `0.690614` seconds. Both reported zero phase-2
fallbacks on the local NVIDIA GB10. This is bounded differential evidence,
not a source-scale result or an H100 measurement.

Two standalone CUDA KATs are also part of the package closure:

| KAT | Source SHA-256 | Coverage |
| --- | --- | --- |
| warp/tail partition | `eab8912b27de71969b35d85eedabe5b08fa93d0208ed1b12e66a516c2f827d7e` | CPU, one-thread CUDA, and warp CUDA equality |
| wheel-47 filter | `cd9d07cf8d62fe43cac0e14050cd0a50a44f4a704301428a04df049b0330bf22` | CPU, unfiltered CUDA, and filtered CUDA equality |

Each checks four windows of `262144` odd values: a low range, a square
activation range, a source-height range, and a window ending exactly at
`UINT64_MAX`. Qualification requires the exact fixed FNV digests and bit
counts, not merely an `accepted` boolean.

## Package validation and Azure calibration

Build and then independently revalidate a local package with:

```bash
python3 tools/qualify_goldbach_gpu_optimized.py build \
  /work/goldbach-hardened /work/goldbach-qualified \
  --host-cxx /usr/bin/g++ --bounded-arch native

python3 tools/qualify_goldbach_gpu_optimized.py validate \
  /work/goldbach-qualified
```

Validation recomputes the manifest self-hash, rejects extra closure files,
rehashes every source and artifact, reparses every bounded report, checks the
fixed KAT answers, and reruns the PTX and SASS lexical audits.

On the x86_64 Azure build host, create the measured-runner package with:

```bash
python3 tools/materialize_goldbach_optimized_h100_calibration.py \
  /work/goldbach-qualified /work/goldbach-h100-calibration \
  --python /usr/bin/python3 \
  --runner-policy /pinned/runner-policy.json \
  --nvidia-policy attestation/policies/gpu_prover_h100.rego
```

The job requires the Azure NCC40ads H100 target and trust profiles, an NVIDIA
confidential-compute pre-run gate bound to the challenge and job, the exact
candidate closure, one GPU, strict stdout parsing, zero fallbacks, and a
replayable challenge trace. It is a bounded target-SKU performance
calibration only.

`project_from_h100_calibration` uses the median reported computation time,
then separately charges the maximum observed initialization time and the
maximum residual process overhead once for every one of the `65536`
checkpoint leaves. It does not extrapolate from a long-running rate while
silently omitting per-leaf costs.

## Remaining boundary

Before any production promotion, the project still needs:

1. a fresh x86_64 package built with the exact Azure toolchain;
2. an actual confidential H100 calibration and replayed evidence;
3. source-scale completion receipts (the plan/run/reducer routes now exist);
4. review or proof of the compiler/architecture refinement boundary; and
5. an explicit, separately reviewed production registration.
