# H100 device components

This directory contains the device and strict host-policy sources used by
SparkInterval's H100 workflows:

- `h100_rounding_probe.cu` and `h100_probe_runner.cpp` form the directed-
  rounding diagnostic;
- `h100_interval_batch_kernel.cu` and `h100_interval_batch_runner.cpp` form
  the primitive interval batch;
- `h100_expression_batch_kernel.cu` and `h100_expression_batch_runner.cpp`
  form the postfix interval evaluator;
- `h100_tg_r2star_factor_support_kernel.cu` and its runner compile the bounded
  Ramaré-campaign factor-support primitive for `sm_90`; the runner still checks
  every GPU row by independent host factorization and does not prove the
  analytic R2Star inequality;
- `h100_tg_r2star_chunk_kernel.cu` and its runner extend that primitive with
  exact-or-reject Q64 log rounding, coefficient bounds, a deterministic
  blocked prefix/envelope transition, and a retained serial cross-check for
  bounded hash-linked chunks;
- `h100_tg_mobius_segment_kernel.cu` and its runner compile the exact bounded
  Möbius/squarefree transition producer for `sm_90`; it also carries a directed
  scale-`2^96` little-Mertens interval and checks both published real-slab
  bounds with exact squared integer comparisons. Hash-linked prefix states can
  be structurally composed or resumed by `tools/tg_mobius_campaign.py`, whose
  retained files do not authenticate execution. No complete production chain
  or Hurst-style compressed algorithm is retained;
- `h100_runtime_policy.h` requires exactly one visible H100 with compute
  capability 9.0 and rejects the generic cross-device override; and
- `sparkinterval-h100-grh-lambda` builds the upstream rigorous Dirichlet-L
  interval evaluator as an `sm_90` executable and enforces the same H100/9.0
  device identity. It is the documented moderate-height GRH POC, not the
  missing Platt-scale lattice/FFT algorithm; and
- `h100_interval_batch_ptx_audit.py` checks the restricted generated PTX.

The offline artifact scripts can produce `compute_90` PTX and `sm_90` cubins
without an H100 and only syntax-check their runner sources. The native CMake
targets also produce executables for the current host architecture, including
on an `aarch64` build host, but without a physical H100 they produce no H100
execution result or attestation.

The native R2Star runner's exact ambiguity fallback uses the header-only
Boost.Multiprecision library. Install the platform's Boost development headers
or pass `-DSPARKINTERVAL_BOOST_INCLUDE_DIR=/path/to/include` at configure time.

To compile all native-host runners plus the fixed probe cubin, configure with
`-DSPARKINTERVAL_BUILD_H100_NATIVE=ON` and build the
`sparkinterval-h100-native` target. The resulting CLIs and embedded `sm_90`
images can be checked without device execution using the CTest
`h100_native_cli_offline`. On a physical H100 host,
`tools/run_h100_native_validation.sh` builds, statically audits, and runs the
probe plus exact primitive and expression conformance suites. That command
produces local, unattested evidence only.

Use the [H100 guide](../../../docs/H100.md) for supported commands and the
[trust model](../../../docs/TRUST_MODEL.md) before interpreting any artifact.
