# Möbius/Hurst combined-candidate paired qualification

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Outcome

`tools/qualify_tg_mobius_hurst_combined.py` is the isolated, fail-closed
comparison path for the two optimizations intended to run together:

```text
current:
  production residue-235 seed
  + production global CUB prefix scan

candidate:
  --qualification-residue-235711-seed
  + --qualification-affine-block-compose
```

Both variants execute from one byte-identical temporary copy of the same
runner. The qualifier compares every exact leaf and terminal semantic field,
not only acceptance bits, extrema values, or aggregate timings. It also
requires distinct receipt domains and receipt digests. The candidate remains
qualification-only: production selection, defaults, production receipt
identity, theorem identity, and every external-atom claim remain unchanged.
The paired runner itself does not invoke Compute Sanitizer, so its report
keeps `runtime_instrumentation.status=not-inspected-by-paired-runner` and does
not bind separate sanitizer logs.

The minimum bounded corpus has `16,777,217` rows. This is deliberate:

- it emits 257 affine summaries, crossing the 256/257 final-composer boundary;
- its terminal-range p=13 stream has 1,290,555 events, so the second
  1,048,576-event block is live; and
- it remains a small bounded qualification rather than a source campaign.

Three local CC 12.1 alternating smoke pairs accepted with identical semantic
transcript SHA-256
`37a297dcd07264c7bfc865aa9647ab9aba304d4a76381afb09cb18c7ffaae3cf`.
The median device-work times were 36.488 ms current and 33.789 ms candidate,
a ratio of 1.0799. This bounded GB10 run is not H100 performance evidence;
the report correctly keeps
`performance_evidence_eligible=false`.

## Exact compared semantics

For every receipt leaf, the qualifier compares:

```text
range and row count
incoming, outgoing, and delta Mertens state
incoming, outgoing, and delta squarefree state
both exact Hurst extrema and their witnesses
both exact squarefree extrema, witnesses, and endpoint sides
poison count
```

It then compares the complete terminal state, all four global extrema with
source-order tie breakers, and both little-Mertens deltas. Above `10^12` the
two little-Mertens coordinates are exactly zero by the source split; they are
still present in the comparison rather than silently omitted.

The current and candidate transcript objects are canonically serialized and
must have the same digest. Every repetition must reproduce the same
transcript and its variant's own deterministic receipt chain. The current
and candidate receipt chains must differ because their domains are
intentionally distinct.

## Binary, source, and build binding

Before running either variant, the tool:

1. hashes a closed manifest of the CUDA kernel, public header, persistent
   runner, H100 wrappers and policy, candidate-order header, and CMake file;
2. invokes a Release build of both the runtime target and the strict H100
   target;
3. records hashes of the CMake cache and available target-specific build
   metadata, the ELF build ID, and the resulting executable;
4. records hashes of NVCC, `cuobjdump`, and their version output;
5. copies the runtime executable once with exclusive creation and verifies
   byte identity; and
6. checks the executable and source manifests again after all alternating
   runs.

Each runner header must report the execution-copy SHA-256 from
`/proc/self/exe`. The same immutable copy is used for current and candidate.
On Azure, the runtime image must also be byte-identical to the freshly built
strict-H100 artifact.

This is reproducible build evidence, not a proof that NVCC implements the C++
and CUDA sources. The report leaves both compiler refinement and CUDA-to-Lean
refinement false.

## Strict SM90 resources

The strict target is freshly built and rejected unless `cuobjdump` finds only
an `sm_90` cubin. Resource roles are selected by unique kernel-name patterns;
a missing or ambiguous match rejects the report. The current local
cross-build reported:

| Path / kernel role | Registers | Stack/thread | Shared/block | Local/thread |
| --- | ---: | ---: | ---: | ---: |
| Current p5 initializer | 18 | 0 | 1,032 | 0 |
| Candidate p11 initializer | 22 | 0 | 1,040 | 0 |
| Current CUB global scan | 48 | 0 | 8,208 | 0 |
| Current thread candidates | 64 | 64 | 0 | 0 |
| Current block candidates | 64 | 64 | 17,408 | 0 |
| Current device candidate | 31 | 0 | 17,408 | 0 |
| Candidate block summaries | 64 | 64 | 19,744 | 0 |
| Candidate ordered composer | 48 | 0 | 19,456 | 0 |

The report also exposes the five shared sieve roles: roster preflight, dense
and sparse distinct-divisor streams, and dense and sparse square strikes.
The resource gate is explicit: at most 64 registers, at most 64 stack bytes,
at most 227,328 shared bytes, and zero reported local bytes for every selected
role. These are compiler-reported resources, not an occupancy or throughput
prediction.

## Allocation equation

For the 16,777,217-row bounded corpus, the paired run reported:

```text
current persistent allocation       314,903,499 bytes
candidate persistent allocation     180,327,956 bytes
candidate saving                    134,575,543 bytes
```

The qualifier does not trust that total in isolation. It checks:

```text
saved =
    current prefix
  + current scan workspace
  - candidate one-row delta
  - candidate block summaries
```

The fused-support allocation must be identical. The candidate must report
zero scan workspace, and its reference prefix byte count must equal the
current runner's actual prefix allocation. Any disagreement rejects the
report.

At 100 million rows the candidate emits at most 1,526 summaries. The base-trio
Lean theorem
`HurstAffineBlockComposition.cudaSummaryThread_machine_bounds` now proves
that its 256-thread composer assigns at most six summaries per thread, all
thread begins are below 1,536, and both begin/end indexes fit `uint32_t`.
This complements the existing ordered-coverage and p11 seeded-Möbius proofs.

## Bounded reproduction

Use a portable runtime build for the local GPU and a separate strict-sm90
cross-build:

```bash
python3 tools/qualify_tg_mobius_hurst_combined.py \
  --runner build/dgx-spark/sparkinterval-tg-mobius-persistent \
  --runtime-build-dir build/dgx-spark \
  --strict-h100-runner \
    build/h100-native/sparkinterval-h100-tg-mobius-persistent \
  --strict-build-dir build/h100-native \
  --prime-roster /path/to/tg-mobius-primes-through-1e8.u32le \
  --repeats 3 \
  --output /new/path/tg-mobius-hurst-combined.json
```

The output path is exclusively created; an existing file or symlink is
rejected. The default range ends at `10^16` and uses the exact 257-summary
crossover count.

## Azure H100 benchmark

Build and run the strict image on the H100:

```bash
python3 tools/qualify_tg_mobius_hurst_combined.py \
  --runner build/h100-native/sparkinterval-h100-tg-mobius-persistent \
  --runtime-build-dir build/h100-native \
  --strict-h100-runner \
    build/h100-native/sparkinterval-h100-tg-mobius-persistent \
  --strict-build-dir build/h100-native \
  --prime-roster /path/to/tg-mobius-primes-through-1e8.u32le \
  --mode azure-h100-benchmark \
  --count 100000000 \
  --repeats 5 \
  --output /new/path/tg-mobius-hurst-combined-h100.json
```

This mode enforces one visible NVIDIA H100 with compute capability 9.0,
executes the exact audited strict image, and alternates five balanced
current/candidate pairs. Only then may the report set
`performance_evidence_eligible=true`. Timings are direct measurements; no
projection is inserted.

Even an accepted H100 report remains unattested and bounded. It does not
prove compiler refinement, GPU execution semantics, the full `10^16`
campaign, or any external analytic atom. Confidential-compute receipt
binding is a separate layer.

For the bounded 262,145-row candidate path on the local CC 12.1 host,
separate Compute Sanitizer `memcheck`, `initcheck`, `racecheck`, and
`synccheck` runs all reported zero errors or hazards. A matching current-path
`memcheck` also reported zero errors. Those bounded logs corroborate memory
safety but are intentionally not represented as authenticated fields in the
paired report.
