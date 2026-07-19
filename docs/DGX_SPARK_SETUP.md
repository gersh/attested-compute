# DGX Spark setup

The supported native baseline is NVIDIA DGX OS on `aarch64`, one GB10 GPU with
compute capability 12.1, and a CUDA toolkit that supports `sm_121`.

## Prerequisites

The build and validation workflow uses:

- `lean`, `lake`, Python 3, Git, CMake, and a C++ compiler;
- `nvidia-smi` and `/usr/local/cuda/bin/{nvcc,ptxas,cuobjdump,nvdisasm}`;
- `systemd-run`, a working systemd user manager, `flock`, and `sha256sum` for
  serialized memory-capped builds and artifact records; and
- OpenSSL 3.x when operator key generation or signature verification is used.

Use the NVIDIA-provided driver/toolkit pair. Do not replace the driver as part
of this build. The DGX scripts currently require CUDA tools under
`/usr/local/cuda/bin`, and the conformance tools must be discoverable on
`PATH`; the recorded acceptance profile is `sm_121`. Before running the build:

```bash
export PATH="/usr/local/cuda/bin:$PATH"
```

The memory wrapper fails closed if a systemd user manager is unavailable. See
[Memory-safe builds](MEMORY_SAFE_BUILDS.md) for the supported container or
scheduler override and for resource-limit settings.

## Build and validate

From a clean repository root:

```bash
git status --short
./tools/build_dgx_spark.sh
```

The script checks `aarch64`, exactly one compute-capability-12.1 GPU, the pinned
Lean/mathlib toolchain, and required tools. It then runs serialized Lean checks,
Python tests, a one-job CUDA/CMake build, regression-sized CTests, the native
probe, and PTX/cubin/SASS extraction.

Important outputs include:

- `build/run/environment.txt` and `build/run/probe.json`;
- inspectable artifacts and hashes under `build/artifacts/`; and
- `build/dgx-probe-bundle/run-bundle.json`.

Verify the resulting local bundle with:

```bash
python3 tools/verify_run_bundle.py \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle
```

The bundle is deliberately `local_unattested`, has
`hardware_attestation: null`, and reports `hardware_evidence: false`. It records
the diagnostic probe, not a large arithmetic acceptance run.

## Next steps

- For local operator signing with a pinned Ed25519 key and replay database, use
  [DGX local bundle and signature](USING.md#dgx-spark-local-bundle-and-operator-signature).
- For the real-integer zeta tutorial, use
  [Real-integer zeta POC](USING.md#real-integer-zeta-poc).
- For the larger arithmetic and generated-cubin acceptance procedures, use
  [Reproducibility](REPRODUCIBILITY.md).

The strict recorded profile expects exactly one GPU. Portability overrides are
for local experiments and must not be used in a claimed DGX acceptance
run. If a probe or audit fails, retain its error and environment record; do not
weaken expected bit patterns or replace a failed result with an unbounded one.
