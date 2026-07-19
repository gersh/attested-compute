# SparkInterval

SparkInterval verifies interval-arithmetic mathematics in Lean, runs and
records CUDA work on NVIDIA DGX Spark, and prepares offline H100 artifacts.
Its certificate and evidence workflows keep those assurance levels distinct.

The project keeps three questions separate:

1. Does the interval algorithm enclose the exact real result?
2. Did a particular program produce the recorded bytes?
3. What evidence identifies the machine or operator behind that run?

## Current support

| Route | Current result | Important boundary |
| --- | --- | --- |
| CPU + Lean full certificate | Lean independently checks every supplied row and proves row or finite-sum bounds | Proves mathematics, not that a GPU ran |
| Generated polynomial model | Lean proves whole-module execution and exact-real containment for the typed generated AST | Does not refine emitted PTX, `ptxas`, SASS, the driver, or hardware |
| DGX Spark (`aarch64`, `sm_121`) | Native CUDA runs, exact CPU replay, artifact audits, and canonical local bundles | GB10 has no supported hardware attestation; evidence is `local_unattested` |
| DGX operator signature | A pinned Ed25519 key endorses the exact local bundle | Proves the pinned key signed; operator attribution is out of band, and neither truth nor GPU execution follows |
| H100 (`x86_64`, `sm_90`) offline | Builds and audits real `compute_90` PTX and `sm_90` cubin/SASS | No H100 execution or accepted confidential-computing evidence yet |

## Choose a workflow

- For a mathematical result independent of GPU provenance, use the
  [CPU and Lean certificate workflow](docs/USING.md#full-lean-result-certificate).
- To run locally on DGX Spark and optionally sign the record, use the
  [DGX workflow](docs/USING.md#dgx-spark-local-bundle-and-operator-signature).
- To compute a rigorous tutorial enclosure of real `zeta(s)`, use the
  [zeta workflow](docs/USING.md#real-integer-zeta-poc).
- To prepare H100 device artifacts without an H100, use the
  [H100 offline workflow](docs/USING.md#h100-offline-work).

## CPU and Lean quick start

Run these commands from the repository root.

Small core proofs:

```bash
./tools/safe_lake_build.py SparkInterval.IntervalOpsSound
./tools/safe_lean.sh examples/lean/IntervalArithmetic.lean
./tools/safe_lean.sh examples/lean/ZetaIdentity.lean
```

Generate and check the complete two-row certificate in a fresh destination:

```bash
mkdir -p build/examples
CERT_DIR="$(mktemp -d build/examples/lean-result-certificate.XXXXXX)"
./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
python3 tools/generate_lean_result_certificate.py \
  --certificate examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001 \
  --decision-mode kernel \
  --output "$CERT_DIR/GeneratedFullCertificate.lean" \
  > "$CERT_DIR/receipt.json"
./tools/safe_lean.sh "$CERT_DIR/GeneratedFullCertificate.lean"
./tools/with_memory_limit.sh \
  .lake/build/bin/sparkinterval-check-certificate \
  examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001
```

In `kernel` mode, the direct typed-data theorem uses kernel reduction without
the `native_decide` proof-reflection axiom. The theorem that binds the exact
serialized JSON still uses `native_decide` for its concrete parser equality.
See the [certificate example](examples/lean-result-certificate/README.md) for
the theorem names and trust details.

## DGX Spark quick start

Check the [DGX Spark prerequisites](docs/DGX_SPARK_SETUP.md), then run:

```bash
./tools/build_dgx_spark.sh
python3 tools/verify_run_bundle.py \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle
```

This builds the library and DGX backend, runs bounded checks, captures
the environment, extracts GPU artifacts, and creates a diagnostic probe
bundle. Verification intentionally reports `hardware_evidence: false`.

For arithmetic execution, operator signing, replay protection, and fresh
challenger nonces, continue with the
[DGX user workflow](docs/USING.md#dgx-spark-local-bundle-and-operator-signature).
Lean builds are serialized and memory-capped; read
[Memory-safe builds](docs/MEMORY_SAFE_BUILDS.md) before changing those limits.

## Explicit nonclaims

- The real-integer zeta POC encloses positive real values for supported integer
  arguments. It does not locate or count critical-strip zeros and does not
  verify the Riemann hypothesis to any height.
- The division-capable CUDA runner used by that POC is not covered by the
  generated polynomial-machine theorem.
- PTX and SASS audits are conservative artifact checks, not formal proofs that
  `ptxas`, the CUDA driver, or physical hardware implements Lean's machine.
- An operator signature is not hardware attestation.
- H100 production acceptance remains fail-closed until a genuine measured
  workload and trusted NVIDIA confidential-computing evidence verifier exist.

## Documentation

- [User workflows](docs/USING.md)
- [Documentation index](docs/README.md)
- [Verification guide](docs/VERIFYING.md)
- [Examples](examples/README.md)
- [DGX Spark setup](docs/DGX_SPARK_SETUP.md)
- [H100 offline and production boundary](docs/H100.md)
- [Run-bundle and certificate formats](docs/FORMAT.md)
- [Memory-safe builds](docs/MEMORY_SAFE_BUILDS.md)
- [Trust model](docs/TRUST_MODEL.md)
- [Correctness claims](docs/CORRECTNESS_CLAIMS.md)
- [Reproducibility details](docs/REPRODUCIBILITY.md)
- [Real-zeta POC algorithm](docs/algorithms/REAL_ZETA_POC.md)
