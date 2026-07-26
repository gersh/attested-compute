# PT21 bounded stationary-point resolver

This component closes the finite adaptive interpolation step that starts when
the PT21 event scanner emits a `StationaryCandidate`. It is deliberately a
CPU/FLINT fallback, not a replacement for the common H100 transform and scan
path, and not an analytic proof of the Riemann hypothesis.

The implementation is split into:

- `gpu/include/sparkinterval/tg_platt_stationary_resolver.hpp`, the bounded
  API and failure vocabulary;
- `reference/tg_platt_stationary_resolver.cpp`, the reviewed-FLINT resolver
  and replay;
- `schemas/platt-pt21-stationary-trace.schema.json`, the self-contained wire
  shape;
- `tg_verifier/platt_stationary_trace.py`, an independent exact-rational wire
  validator; and
- `tools/tg_platt_stationary_trace.py`, a small checker/extractor for inserting
  the `stationary_resolutions` array into the existing fused source trace.

## Exact source map

The code follows `zeta_arb/turing.c::resolve_stat_point` and
`zeta_arb/inter.c::arb_inter_t` from `djplatt/code` commit
`42b21426718e542daa2b006dc05ea2d7f26426e6`. For each source `stat_pt` triple
`[left,left+1,left+2]`, it keeps the same three-point state and:

1. evaluates `(tl+tm)/2`;
2. returns two strict brackets immediately when that value has the opposite
   source sign;
3. otherwise applies the same strict `arb_gt`/`arb_lt` direction tests;
4. if necessary evaluates `(tm+tr)/2`; and
5. applies the same middle/right refinement cases.

Unlike the upstream unbounded `while (true)`, production has an explicit
default cap of 64 dyadic levels (hard cap 96). Unknown interpolation signs,
overlapping direction intervals, lack of a source branch, or exhaustion of
that cap fail the entire block. No partial resolution prefix is retained.

Each non-lattice query evaluates the literal 70 samples to the right followed
by 70 to the left. It uses source spacing `21/512`, Gaussian parameter
`13/64`, the source sine-sign reuse after each integral lattice step, and a
symmetric exact `245/10^42` widening for the combined Appendix C.1 and
corrected-C.3 allowance. The correction is bound by patch SHA-256
`2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3`.

The resolver accepts exactly 25,741 source-required DD disks. It reconstructs
each disk's exact dyadic endpoints from the three binary64 fields and then
independently regenerates every `stat_pt` candidate in the left, main, and
right streams. The supplied scanner list must match this complete canonical
list, so an omitted or extra candidate cannot silently pass.

## Ambiguous lattice samples

Cardinal interpolation cannot narrow an ambiguous value at the same lattice
point: the mathematical cardinal term is that sample itself. Consequently
this resolver never presents interpolation as a repair for a wide H100 disk.
An ambiguous lattice disk requires a separate sparse high-precision producer.
Its replacement is accepted only when both endpoints are canonical finite
`arf_dump_str` dyadics, the interval is contained in the original exact DD
disk, and it has a strict sign. Every original ambiguity must be refined and
refinements of already strict disks are rejected.

This lane is fallback-only. In particular, the 41 ambiguous disks observed in
the first two-window Gamma-v1 fused run are evidence of an overly wide Gamma
Taylor representation, not a normal workload to route through this resolver.
The DD Gamma V2 stream/synthesizer now implements that production fix: first
and terminal 64-window fused samples each had zero required-region
ambiguities. This is not a source-wide result, so the sparse fallback remains
fail-closed and available for genuinely difficult windows.

If any sparse refinement is used, direct-event scanning must be rerun against
the refined sample set. The present v1 required-sign packet rejects ambiguous
disks and cannot itself carry those replacement signs; a production sparse
refinement producer therefore still needs a packet/worker integration if the
DD Gamma width fix does not eliminate all lattice ambiguities.

## Replay and trace boundary

A successful native call performs two checks after the first resolution:

- it reruns the complete bounded control path and requires byte-identical
  rational resolution data; and
- it reevaluates all three retained endpoints with 64 extra precision bits and
  requires those fresh intervals to be contained in the recorded 128-bit
  intervals.

The trace hashes original DD words, scanner queries, and any refinement
sidecars in a fixed little-endian domain. A second domain hashes the canonical
`stationary_resolutions` JSON array. That array is field-for-field compatible
with `platt-pt21-fused-source-trace.schema.json`; the integration test feeds a
native pair through `tg_verifier.platt_pt21_fused_artifact.build_block_artifact`
and obtains one multiplicity-two source cell and two touching strict brackets.

The independent Python validator checks canonical JSON, exact reduced
rationals, dyadic coordinates, stream ranges, two-bracket sign geometry,
ordering, the resolution digest, caps, and all-or-nothing failure behavior.
It keeps these semantic fields false:

```text
hardy_z_endpoint_realization_proved = false
analytic_turing_realization_proved = false
flint_to_mathlib_realization_proved = false
```

Thus successful finite replay does not assert that a DD/Arb interval encloses
the mathematical Hardy Z function. That realization and the source-shaped
Turing inequalities remain separate proof obligations.

The V2 H100 worker reaches the scanner and emits the authenticated compact
`PT21EVT1` boundary documented in
[`PLATT_PT21_FUSED_EVENT_STREAM.md`](PLATT_PT21_FUSED_EVENT_STREAM.md).
The bounded
[`PT21STJ1` junction](PLATT_PT21_STATIONARY_JUNCTION.md) now consumes the
scanner's replay-owned disks and complete ordered candidate arrays, checks
their link to that event root, invokes this resolver, and binds the input,
refinement, replay, output, resolver, and FLINT identities. The source-scale
worker still needs the pinned-host ring and persistent resolver pool that
schedule this implemented junction without retaining the payload.

## Local build and GB10 measurement

Using a checkout and install accepted by
`tools/fetch_flint_platt.py --verify-only`, the normal CMake/CTest path is:

```bash
cmake -S . -B build/platt-pt21 \
  -DSPARKINTERVAL_FLINT_PLATT_ROOT="$PWD/build/upstream/flint-3.6" \
  -DSPARKINTERVAL_FLINT_PLATT_PREFIX="$PWD/build/upstream/flint-3.6-install"
cmake --build build/platt-pt21 --target \
  sparkinterval-tg-platt-stationary-resolver
ctest --test-dir build/platt-pt21 \
  -R '^tg_platt_stationary_resolver_known_answers$' --output-on-failure
```

CTest supplies the built binary through `TG_PLATT_STATIONARY_RESOLVER` and
runs the native success, sparse-refinement, fail-closed mutation, v2 finalizer
integration, independent-validator, and bounded benchmark checks.

On the NVIDIA GB10 host CPU, 100 full fallback invocations measured
`147.896` blocks/s (`0.676149` seconds total). Each invocation converted and
checked all 25,741 disks, regenerated all three candidate streams, resolved
one synthetic candidate on its first dyadic evaluation, repeated the source
control path, and performed the extra-precision endpoint replay. This is a
component measurement on a deliberately non-Hardy-Z fixture. It is not an
estimate of candidate frequency, a full PT21 runtime, or an H100 result.
A 200-invocation repeat while roughly fifteen concurrent Lean compiler
processes drove host load above 70 measured `44.5029` blocks/s. The spread is
CPU-contention sensitivity, not an algorithm change; a quiet target-SKU pilot
is still required for production sizing.

## Remaining production work

This component and its authenticated junction still need integration into the
source-scale fused worker. A complete PT21 source acceptance artifact also
needs the actual one-sided Turing input producer, Hardy-Z
endpoint realization, analytic Turing realization, block/shard finalization across all
2,966,443,783 windows, attested execution, and the final Lean receipt binding.
