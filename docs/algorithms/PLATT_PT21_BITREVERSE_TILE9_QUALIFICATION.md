# PT21 fused bit-reversal/tile9 qualification

Status: qualification only. This candidate is behind
`SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION`, is linked from separate
portable and strict-H100 archives, is never selected by a production target,
emits no trusted-compute receipt, and does not discharge the PT21 external
atom.

## Candidate

The settled DD transform first launches a bit-reversal scatter and then
launches the shared-memory stages-1..9 tile. For a transform of length
`2^logLength`, the candidate instead loads shared destination `position`
directly from

```text
input[line_base + (__brev(position) >> (32 - logLength))]
```

and then executes the same nine exact tile stages. Each 256-thread block loads
two positions into the 512-element tile. Input and output arrays must be
distinct; the guarded host entry checks that invariant before any launch.
Stages 10 and later are the unchanged settled sloppy-root implementation.

The live source graph applies this substitution to four collections of
23 rows of length 32,768 and one final transform of length 65,536. Therefore
the number of transformed cells per source window is exactly

```text
4 * (23 * 32768) + 65536 = 3,080,192.
```

`DDDisk` is 40 bytes. Removing one complete intermediate write and read
eliminates

```text
3,080,192 * 40 * 2 = 246,415,360 bytes
```

of device-memory traffic and five kernel launches per source window.

## Verification obligations and gates

The qualifier reuses the authenticated live block-0 runner, but redirects
only its tile9 call and resource query to the separately linked fused kernel.
It must pass all of the following:

1. authenticate the exact 848-byte `PT21GTS2` block-0 stream before GPU
   allocation;
2. reproduce the frozen Gamma and 768,000-term source-accumulator identities;
3. reproduce the frozen ordinary, settled-sloppy, and fused all-sample,
   required-sample, and scanner-artifact SHA-256 values;
4. match every event count, stationary count, multiplicity-slot count, and
   left/right integer weight in all three streams;
5. make all 131,072 fused output disks byte-identical to the settled result;
6. prove by exact rational arithmetic that every settled disk contains its
   ordinary counterpart;
7. preserve every required nonzero sign with zero malformed or ambiguous
   samples;
8. show that the immutable directed root table is unchanged;
9. query CUDA attributes for the actual fused kernel, requiring no local
   memory, exactly 32,768 bytes of static shared memory, at least 256 maximum
   threads, and at least one active block per multiprocessor; and
10. on forced rejection, rerun the ordinary transform and reproduce its full
    output and scanner artifact.

The fail-closed Python wrapper binds the executable by SHA-256 through one
open, non-symlink file descriptor, runs that same descriptor, rehashes it
afterward, and independently checks the complete source-shaped roster above.
It also requires every production, receipt, compiler-refinement, source-claim,
and external-atom claim to remain false.

Separately, the wrapper pins and validates
`reference/manifests/pt21_bitreverse_tile9_repo_source_closure.v1.json`.
That manifest was derived from the five portable-build `nvcc` object
dependency files and contains the exact byte count and SHA-256 of all 17
repo-local translation units and transitive headers they named. The wrapper
validates the manifest and every member before and after the run. Mutation of
either the manifest or a member fails closed.

This is an audited repo-source snapshot, not a binary/source proof. The manifest
explicitly does not cover CMake generator state, compile/link command lines,
external CUDA/C++/Boost/GMP/MPFR headers and libraries, compiler/linker/driver
identity, or compiler correctness. The caller-supplied executable digest
authenticates the executable selected by the caller; it does not prove that
the executable was compiled from the manifested sources. Reports therefore
set `binary_to_source_binding_proved=false`,
`build_flags_authenticated=false`, `external_headers_authenticated=false`,
`external_build_dependencies_pinned=false`, and
`compiler_refinement_proved=false`.

The nested reused runner still calls the redirected implementation
`tile9-sloppy-root`. The outer report identifies the actual candidate as
`pt21-bitreverse-tile9-sloppy-root` and explicitly records
`nested_candidate_label_is_inherited_alias=true`; the inherited nested label
is not evidence of which archive was linked.

## Lean schedule proof

`SparkInterval.Zeta.PT21BitreverseTile9Schedule` proves, for both the
32,768-point rows and 65,536-point final transform, that:

- the literal CUDA `__brev` shift equals the mathematical fixed-width bit
  reversal;
- distinct destinations read distinct natural-order input positions;
- every natural-order input is read by exactly one destination, and
  existential OR-reduction of the malformed predicate is unchanged;
- `2^15` and `2^16` instantiate to 64 and 128 chunks respectively; the
  256 threads' slots `thread` and `thread + 256` uniquely cover all 512 tile
  slots; and the literal block quotient/remainder uniquely covers every
  `(line, chunk)` pair;
- direct bit-reversed loads followed by stages 1..9 equal the old scatter
  followed by the same stages; and
- composing stages 10 onward gives the same complete positive- and
  negative-root schedules.

`SparkInterval.Tests.PT21BitreverseTile9ScheduleTest` and the aggregate
`SparkInterval.Tests.AxiomAudit` print the dependencies. They are base-trio
theorems: only `propext`, `Classical.choice`, and `Quot.sound` appear, with no
project axiom and no `native_decide`.

This proves the architecture-independent indexing and exact-butterfly
schedule. It does not prove CUDA execution, DD/binary64 refinement, compiler
correctness, or a performance claim.

## Build and bounded run

Portable qualification build:

```bash
cmake -S . -B build/pt21-bitreverse-tile9 \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/pt21-bitreverse-tile9 --target \
  sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification

exe=build/pt21-bitreverse-tile9/\
sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification
python3 tools/qualify_pt21_bitreverse_tile9.py \
  --executable "$exe" \
  --expected-executable-sha256="$(sha256sum "$exe" | cut -d' ' -f1)" \
  --stream BLOCK0.pt21gts2 \
  --repetitions 3
```

The strict target is
`sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification`. It is built
only inside `SPARKINTERVAL_BUILD_H100_NATIVE`, uses the repository's strict
`sm_90` configuration, and rejects a non-H100 device before running the
workload. Its resource function queries the fused kernel symbol itself; it
does not reuse the settled tile's attributes.

Configure and build it in a separate strict tree:

```bash
cmake -S . -B build/pt21-bitreverse-tile9-sm90 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=90 \
  -DSPARKINTERVAL_BUILD_H100_NATIVE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON
cmake --build build/pt21-bitreverse-tile9-sm90 --target \
  sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
```

Compile-time strict resource inspection is a separate, fail-closed operation:

```bash
strict=build/pt21-bitreverse-tile9-sm90/\
sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
cuobjdump="$(command -v cuobjdump)"
python3 tools/inspect_pt21_bitreverse_tile9_sm90_resources.py \
  --executable "$strict" \
  --expected-executable-sha256="$(sha256sum "$strict" | cut -d' ' -f1)" \
  --cuobjdump "$cuobjdump" \
  --expected-cuobjdump-sha256="$(sha256sum "$cuobjdump" | cut -d' ' -f1)"
```

The inspector fd-runs the pinned `cuobjdump` separately with `--list-elf`,
`--list-ptx`, `--dump-ptx`, and `--dump-resource-usage`. It requires the three
sm90 cubin roles and exact first two labels; the linked archive's third label
is matched by its `.3.sm_90.cubin` role suffix because `cuobjdump` derives its
basename from the inherited `/proc/self/fd/N` argument. The report marks that
label as fd-basename-dependent. It also records the exact two-image PTX
fallback roster and `.target sm_90` labels printed by `cuobjdump`, locates
exactly one actual fused-kernel resource row, and requires the tuple
`REG=77, STACK=0, SHARED=33792, LOCAL=0` as well as explicit feasibility
bounds. For the source's 256-thread launch it checks
`77 * 256 = 19,712 <= 65,536` registers and
`33,792 <= 49,152` shared bytes. It binds both selected files by descriptor
and SHA-256. The launch geometry is not extracted from the cubin, so it still
sets `launch_geometry_extracted_from_binary=false`,
`h100_resource_limit_model_proved=false`,
`ptx_fallback_semantics_proved=false`,
`cuobjdump_semantics_proved=false`,
`runtime_cuda_attributes_measured=false`, and
`h100_execution_performed=false`.

## Bounded evidence recorded 2026-07-26

On the local GB10 (`sm_121`) Release build:

| Check | Result |
|---|---:|
| Fused versus settled output bytes | exact for 131,072/131,072 disks |
| Fused versus settled scanner artifact | exact |
| Malformed / ambiguous / sign mismatches | 0 / 0 / 0 |
| Exact ordinary containment failures | 0 |
| GB10 runtime CUDA attributes | 65 registers, 32,768 static shared bytes, 0 local bytes |
| Strict sm90 `cuobjdump` row | 77 registers, 0 stack, 33,792 shared, 0 local bytes |
| Settled transform median, 3 repetitions | 59.276 ms |
| Fused transform median, 3 repetitions | 57.995 ms |
| Transform-only ratio | 1.0221x |
| Full qualifier wall time | 40.59 s |

The strict `sm_90` cubin compiled successfully. `cuobjdump`'s 33,792-byte
`SHARED` field is recorded separately from the 32,768-byte
`cudaFuncAttributes.sharedSizeBytes` measured for the portable cubin; they are
different tool surfaces and are not silently equated. The strict result is
compile/resource evidence only; the strict binary was not run or timed on an
H100. The GB10 timing is not an H100, campaign, production, receipt, or
compiler-correctness claim.

Bounded `memcheck`, `initcheck`, and `synccheck` executions each returned
success; the captured `initcheck` and `synccheck` summaries reported zero
errors. The forced-rejection KAT also reproduced the complete ordinary output
and scanner artifact.

## Trust boundary

This artifact establishes a strong bounded differential result and a
base-trio schedule theorem. It does not establish:

- a proof that the compiled CUDA implements the Lean DD model;
- a proof that the ordinary CUDA disks realize the intended Hardy-Z values;
- full-window or full-campaign coverage;
- stationary/Turing closure;
- secure-enclave attestation or receipt admissibility; or
- any production or external-atom conclusion.

Those fields remain explicitly false in every accepted report.
