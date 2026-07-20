# H100 device components

This directory contains the device and strict host-policy sources used by
SparkInterval's H100 workflows:

- `h100_rounding_probe.cu` and `h100_probe_runner.cpp` form the directed-
  rounding diagnostic;
- `h100_interval_batch_kernel.cu` and `h100_interval_batch_runner.cpp` form
  the primitive interval batch;
- `h100_expression_batch_kernel.cu` and `h100_expression_batch_runner.cpp`
  form the postfix interval evaluator;
- `h100_runtime_policy.h` requires exactly one visible H100 with compute
  capability 9.0 and rejects the generic cross-device override; and
- `h100_interval_batch_ptx_audit.py` checks the restricted generated PTX.

The offline artifact scripts can produce `compute_90` PTX and `sm_90` cubins
without an H100 and only syntax-check their runner sources. The native CMake
targets also produce executables for the current host architecture, including
on an `aarch64` build host, but without a physical H100 they produce no H100
execution result or attestation.

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
