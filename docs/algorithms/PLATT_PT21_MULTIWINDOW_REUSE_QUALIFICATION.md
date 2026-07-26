# PT21 multiwindow transform-reuse qualification

## Result

The exact lattice geometry permits one 131,072-sample transform to expose
five complete 25,741-sample views at logical deltas `-2,-1,0,1,2`.
The numerical qualification is nevertheless negative: on every genuine V2
sample tested, only `delta=0` passed the exact sign scanner.  Adjacent shifted
views contained thousands of zero-ambiguous disks and two-step views were
entirely ambiguous.  Pair, three-window, and five-window transform reuse are
therefore **not viable with the current transform enclosure**.

The retained executable is a fail-closed feasibility/regression probe, not a
production worker:

```text
sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification
```

Its strict H100 counterpart is:

```text
sparkinterval-h100-tg-platt-pt21-multiwindow-reuse-qualification
```

Neither target changes the default V2 worker.

## Checked boundary

`tg_platt_dd_transform.hpp` now supplies a bounds-checked qualification view
instead of asking a caller to perform unchecked device-pointer arithmetic.
For the current allocation it accepts exactly:

| delta | zero-based beginning | final exclusive index |
|---:|---:|---:|
| -2 | 3,514 | 29,255 |
| -1 | 28,090 | 53,831 |
| 0 | 52,666 | 78,407 |
| 1 | 77,242 | 102,983 |
| 2 | 101,818 | 127,559 |

`-3`, `3`, and extreme signed inputs fail closed.  The exact ordinate and
array geometry is proved separately in
`SparkInterval/Zeta/PT21PairedWindowGeometry.lean`.

For each in-campaign delta the qualification runner:

1. authenticates a complete V2 Gamma stream against a caller-pinned digest;
2. runs a genuine Gamma synthesis, 768,000-term/23-stage accumulator, and DD
   transform;
3. scans the shifted complete view on CUDA;
4. runs the scanner's full fixed-2176-bit host replay;
5. independently recomputes all disk signs with arbitrary-precision exact
   dyadic integers;
6. computes a separately centered genuine transform for the same logical
   block;
7. compares complete signs and finite direct/stationary event semantics;
8. for candidate-bearing accepted views, runs both sides through the real
   FLINT stationary junction and compares resolution cell/offset semantics,
   resolved multiplicity slots, and the resulting finite `Nleft`/`Nright`
   units.

Endpoint disk bytes and artifact hashes are diagnostics, not equality
requirements: independently centered and shifted transforms use different
center-dependent Gaussian weights.  Resolver and FLINT SHA-256 values are
caller-supplied labels; the executable reports that it does not self-verify
them and requires an external manifest or attestation.

## Genuine V2 results

All measurements below used the Release build on the local DGX Spark
(GB10/sm_121).  Every independently centered control had zero malformed and
zero ambiguous disks and passed the FLINT junction.  Every shifted disk was
finite and had a nonnegative finite radius.

The two genuine runs were repeated after the reusable accumulator began
explicitly zero-filling every inactive bucket in every output slot.  The
interior ambiguity counts, terminal ambiguity counts, decisive-sign
agreement, event counts, and maximum radii reproduced exactly.  Thus the
negative conclusion below no longer relies on allocator-provided contents
for mathematically zero cells.

The curated, small regression record is
`tests/fixtures/pt21_multiwindow_negative_qualification.json`.  It contains
the authenticated stream digests, build profile, counts, radii, and timings,
but no source stream, raw runner output, or binary digest.  It is explicitly a
measurement summary rather than a certificate.  Its invariants are checked by
`tests/test_tg_platt_pt21_multiwindow_reuse.py`.

| center | delta | roster-owned | shifted ambiguous | shifted certified | certified sign mismatches | shifted max radius | result |
|---:|---:|:---:|---:|---:|---:|---:|:---|
| 0 | 0 | yes | 0 | 25,741 | 0 | 3.6780937664373325e-13 | junction accepted, 1 candidate / 2 slots |
| 0 | +1 | yes | 14,634 | 11,107 | 0 | 3.6780937664373325e-13 | rejected before junction |
| 0 | +2 | yes | 25,741 | 0 | 0 | 3.678093766437332e-13 | rejected before junction |
| 2 | -2 | yes | 25,741 | 0 | 0 | 2.216934570801321e-12 | rejected before junction |
| 2 | -1 | yes | 15,269 | 10,472 | 0 | 2.216934570801321e-12 | rejected before junction |
| 2 | 0 | yes | 0 | 25,741 | 0 | 2.216934570801321e-12 | junction accepted, 4 candidates / 8 slots |
| 2 | +1 | yes | 15,274 | 10,467 | 0 | 2.216934570801321e-12 | rejected before junction |
| 2 | +2 | yes | 25,741 | 0 | 0 | 2.216934570801321e-12 | rejected before junction |
| 2,966,443,781 (`N-2`) | -1 | yes | 17,034 | 8,707 | 0 | 5.822170217405081e-11 | rejected before junction |
| 2,966,443,781 (`N-2`) | 0 | yes | 0 | 25,741 | 0 | 5.822170217405081e-11 | junction accepted, 6 candidates / 12 slots |
| 2,966,443,781 (`N-2`) | +1 | yes | 17,045 | 8,696 | 0 | 5.822170217405081e-11 | rejected before junction |

The terminal command used an explicit `--owned-deltas=-1,0,1` mask.  The
geometrically available `delta=-2` belongs to the preceding five-block group
and is only a diagnostic; it is not counted in the claimed roster reduction.

The failures are exact zero-containment failures, not malformed disks.  Raw
shifted and independently centered intervals are mostly disjoint because the
source transform includes a positive Gaussian weight centered at the chosen
window, so the two raw amplitudes are not expected to agree.  The zero
certified-sign mismatch count rules out an observed orientation flip on every
shifted sample that remains decisive.  A rigorous Gaussian renormalization
comparison was not implemented, and no normalized-disk equivalence is
claimed.  Operationally, the positive off-center attenuation leaves the
transformed center too small relative to the retained absolute enclosure, so
the exact scanner correctly refuses the shifted view.

## Timing

The Release center-2 run measured:

- setup: `37.793472399 s`;
- five ordinary transform invocations: the transform-only ratio against one
  center invocation was `5.0111516016x`;
- complete qualification wall time: `38.68575097 s`.

The roster-correct final three-block group measured:

- setup: `37.847703994 s`;
- transform-only ratio: `3.0013388652x`;
- complete qualification wall time: `38.586761234 s`.

These ratios merely confirm that deleting transform invocations would save
the expected transform work.  The shifted outputs fail acceptance, so they
are not a usable optimization.  There is no whole-pipeline speedup claim.
In particular, the accumulator has no stride/skip API or Q192
anchor/re-anchor refinement for jumping directly between group centers.

Machine output records
`build_profile.cmake_build_config`, `build_profile.ndebug_defined`, and
`build_profile.release_performance_build`.  The last field is true only for
the exact `Release`/`NDEBUG` combination; timings from any other profile are
not performance evidence.

## Reproduction

Release configure and build:

```bash
cmake -S . -B build/pt21-multiwindow-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE=ON \
  -DSPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC=ON \
  -DSPARKINTERVAL_FLINT_PLATT_ROOT="$FLINT_SOURCE" \
  -DSPARKINTERVAL_FLINT_PLATT_PREFIX="$FLINT_PREFIX" \
  -DSPARKINTERVAL_BOOST_INCLUDE_DIR="$BOOST_INCLUDE" \
  -DSPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR="$MPFR_INCLUDE"
cmake --build build/pt21-multiwindow-release --parallel 2 \
  --target sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification
```

Bounds KAT:

```bash
ctest --test-dir build/pt21-multiwindow-release \
  -R '^tg_platt_pt21_multiwindow_reuse_bounds_known_answers$' \
  --output-on-failure
```

Interior run (an exit status of `3` is the expected fail-closed
qualification result):

```bash
build/pt21-multiwindow-release/sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification \
  "$FIRST_FIVE_V2_STREAM" 2 \
  --expected-stream-sha256=809f00d039bd8d4e0c4ee78f00ebff130305ca26d8e3ee2b5de4bcac228de6ad \
  --resolver-sha256=0f19db9650e755ad7a93939352a7290652fa861817f10325467b3ac28de3eecf \
  --flint-sha256=5e7cbb0c68aa9cee8f940f98914600ce7eeef3ef03d30d7ad635ac744cfdaeea
```

Terminal roster run:

```bash
build/pt21-multiwindow-release/sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification \
  "$TERMINAL_FIVE_V2_STREAM" 2966443781 \
  --expected-stream-sha256=b839e3f61637b9d0bdbfe5e19963c78957b4b3594540b68d006571bfb41c8326 \
  --resolver-sha256=0f19db9650e755ad7a93939352a7290652fa861817f10325467b3ac28de3eecf \
  --flint-sha256=5e7cbb0c68aa9cee8f940f98914600ce7eeef3ef03d30d7ad635ac744cfdaeea \
  --owned-deltas=-1,0,1
```

The H100 target compiled successfully in Release, but was not executed on
this non-H100 machine.  A no-FLINT configuration omits both qualification
targets and still builds the unchanged default V2 worker.

## Trust and readiness

Machine-readable output keeps all of the following false:

- whole-pipeline speedup claimed;
- accumulator stride/skip implemented or KAT-complete;
- Q192 stride/anchor refinement proved;
- Gaussian rescaling normalization implemented;
- campaign partition implemented;
- full campaign qualified;
- Hardy-Z, FLINT-to-Mathlib, and analytic Turing realization proved;
- source claim ready;
- production ready;
- PT21 atom discharged.
