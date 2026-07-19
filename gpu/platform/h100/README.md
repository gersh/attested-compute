# H100 device components

This directory contains the device-side sources used by SparkInterval's H100
offline workflows:

- `h100_rounding_probe.cu` and `h100_probe_runner.cpp` form the directed-
  rounding diagnostic;
- `h100_interval_batch_kernel.cu` and `h100_interval_batch_runner.cpp` form
  the primitive interval batch; and
- `h100_interval_batch_ptx_audit.py` checks the restricted generated PTX.

The offline scripts can produce `compute_90` PTX and `sm_90` cubins without an
H100. On an `aarch64` DGX Spark host, runner sources are syntax-checked but no
H100 host executable, result, or attestation is produced.

Use the [H100 guide](../../../docs/H100.md) for supported commands and the
[trust model](../../../docs/TRUST_MODEL.md) before interpreting any artifact.
