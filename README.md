# SparkInterval

SparkInterval verifies interval-arithmetic mathematics in Lean, runs and
records CUDA work on NVIDIA DGX Spark and H100, and prepares H100 device
artifacts without requiring the target GPU. Its certificate and evidence
workflows keep those assurance levels distinct.

The project keeps three questions separate:

1. Does the interval algorithm enclose the exact real result?
2. Did a particular program produce the recorded bytes?
3. What evidence identifies the machine or operator behind that run?

## Current support

| Route | Current result | Important boundary |
| --- | --- | --- |
| CPU + Lean full certificate | Lean independently checks every supplied row and proves row or finite-sum bounds | Proves mathematics, not that a GPU ran |
| Generated polynomial model | Lean proves whole-module typed-AST execution and exact-real containment; a pinned PTX 9.0 slice adds opcode citations and finite/non-NaN arithmetic refinement | No full emitted-instruction-text, `ptxas`, SASS, driver, or hardware refinement |
| DGX Spark (`aarch64`, `sm_121`) | Native CUDA runs, exact CPU replay, artifact audits, and canonical local bundles | GB10 has no supported hardware attestation; evidence is `local_unattested` |
| DGX operator signature | A pinned Ed25519 key endorses the exact local bundle | Proves the pinned key signed; operator attribution is out of band, and neither truth nor GPU execution follows |
| Accepted Lean run certificate | One explicit axiom supplies both the exact historical return and, after a closed registered-invocation check, that invocation's fixed formal `Runs` relation | Requires a trusted private-evidence importer; the per-run registry bridge is not a universal determinism or backend-refinement theorem |
| Closed registry example | `cubicSumDivThree20000V1` fixes an executable integer cube accumulator followed by one division by three; Lean proves its exact operational result `13334666700000000`, agreement with the rational sum, and u64 safety of every cube and accumulator step, all without `native_decide` | These are axiom-free model and bounded-arithmetic proofs, not a GPU-opcode or physical-execution proof; no signed bundle can enter Lean because the private-evidence importer is absent |
| H100 (`x86_64`, `sm_90`) native | Strict probe, primitive, and postfix-expression runners; exact CPU conformance; PTX/SASS audits; a real-integer zeta POC; and target-selected generated-polynomial conformance | Current runs are local evidence only; the zeta bundle is `local_unattested`, and no NVIDIA confidential-computing evidence is collected or accepted |
| High-bound zeta-zero foundation | Lean canonically checks a signed full endpoint payload, bridges analytic multiplicity to distinct counts, and conditionally composes a Hardy-Z model plus multiplicity bound into the finite-height theorem | Endpoint realization and the analytic Turing/argument-principle bound remain uninstantiated; no height has been certified |

## Choose a workflow

- For a mathematical result independent of GPU provenance, use the
  [CPU and Lean certificate workflow](docs/USING.md#full-lean-result-certificate).
- To run locally on DGX Spark and optionally sign the record, use the
  [DGX workflow](docs/USING.md#dgx-spark-local-bundle-and-operator-signature).
- To compute a rigorous tutorial enclosure of real `zeta(s)` on DGX Spark or
  H100, use the [zeta workflow](docs/USING.md#real-integer-zeta-poc).
- To review or extend the high-bound zero verifier, start with its
  [formal architecture and status](docs/algorithms/ZETA_ZERO_VERIFIER.md).
- To smoke-test the host-side schedule and synthetic streaming-bracket
  scaffolding, run `python3 tools/benchmark_zeta_foundations.py --pretty`; this
  is not a zeta, Lean, GPU, or production-certificate benchmark.
- To build or validate the strict native runners on an H100, use the
  [H100 native workflow](docs/USING.md#h100-native-local-validation).
- To prepare H100 device artifacts without an H100, use the
  [H100 offline workflow](docs/USING.md#h100-offline-artifacts).

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

## H100 quick start

On a host with exactly one visible NVIDIA H100 at compute capability 9.0,
build, audit, and run the strict native validation suite:

```bash
H100_BUILD_JOBS=1 ./tools/run_h100_native_validation.sh
```

The script builds these native artifacts:

- `build/h100-native/sparkinterval-h100-probe-runner`;
- `build/h100-native/sparkinterval-h100-interval-batch`;
- `build/h100-native/sparkinterval-h100-expression-batch`; and
- `build/h100-native/h100/h100_rounding_probe.sm_90.cubin`.

After that succeeds, run the H100-bound real-zeta tutorial in a fresh
directory:

```bash
mkdir -p build/examples
H100_ZETA_PARENT="$(mktemp -d build/examples/h100-zeta2.XXXXXX)"
H100_ZETA_DIR="${H100_ZETA_PARENT}/run"
python3 tools/run_zeta_poc.py run \
  --target-profile h100_sm90 \
  --work-dir "${H100_ZETA_DIR}" \
  --s 2 \
  --terms 4096
python3 tools/run_zeta_poc.py verify "${H100_ZETA_DIR}"
```

Both surfaces are intentionally local and unattested. The zeta verification
receipt reports `evidence_class: local_unattested` and
`hardware_evidence: false`; neither command obtains or validates NVIDIA
confidential-computing evidence. See the [H100 guide](docs/H100.md) for the
offline CLI checks and the separate generated-`sm_90` polynomial path.

## Explicit nonclaims

- The real-integer zeta POC encloses positive real values for supported integer
  arguments. It does not locate or count critical-strip zeros and does not
  verify the Riemann hypothesis to any height.
- The separate high-bound foundation parses and checks a canonical monolithic
  endpoint payload, proves resumable endpoint/chunk composition, and can
  reflect positive-only rows for a proved even evaluator. Its
  Hardy-Z/Riemann-Siegel endpoint realization and analytic multiplicity-count
  premise do not yet have production instances. It therefore does not certify
  any positive height.
- The preferred compact attested-summary theorem uses a closed registered
  invocation, so the sole axiom supplies the per-run physical-to-formal
  `Runs` bridge and no second `ExecutionRefines` premise is needed. It still
  requires an ordinary Lean soundness theorem for that registered checker.
  The older generic FormalPTX compact API remains available and still requires
  its explicit refinement premise.
- The division-capable CUDA runner used by that POC is not covered by the
  generated polynomial-machine theorem.
- PTX and SASS audits are conservative artifact checks, not formal proofs that
  `ptxas`, the CUDA driver, or physical hardware implements Lean's machine.
- An operator signature is not hardware attestation.
- The sole `accepted_run_certificate_sound` axiom establishes one accepted
  certificate's historical outcome and its fixed formal semantics for every
  matching constructor of the closed invocation registry.
  `accepted_registered_run_sound` and the DGX/H100 names are proved projections,
  not additional axioms. This per-run bridge does not say that every future run
  is deterministic or prove a general PTX/cubin/backend refinement theorem.
- The closed registry currently contains only
  `RegisteredAlgorithm.cubicSumDivThreeV1` and
  `RegisteredInvocation.cubicSumDivThree20000V1`; no zeta checker is registered.
- Its `cubicNumeratorLoop`/`cubicSumDivThreeMachine` proofs establish the
  tutorial algorithm and u64 bounds in Lean. They do not establish that a GPU
  executable implements those steps; that particular-run connection remains
  exactly the certificate axiom's responsibility.
- Literal algorithm ID/hash checks do not prove that a cubin was compiled from
  the formal PTX module.
- Successful H100 native, generated-polynomial, or real-zeta validation is
  local execution/conformance evidence, not confidential-computing
  attestation. Production H100 acceptance remains fail-closed until a genuine
  measured workload and trusted NVIDIA evidence verifier exist.

## Documentation

- [User workflows](docs/USING.md)
- [Documentation index](docs/README.md)
- [Verification guide](docs/VERIFYING.md)
- [Examples](examples/README.md)
- [DGX Spark setup](docs/DGX_SPARK_SETUP.md)
- [H100 native, offline, and production boundary](docs/H100.md)
- [Run-bundle and certificate formats](docs/FORMAT.md)
- [Memory-safe builds](docs/MEMORY_SAFE_BUILDS.md)
- [Proof blueprint and NVIDIA-spec traceability](docs/PROOF_BLUEPRINT.md)
- [Trust model](docs/TRUST_MODEL.md)
- [Correctness claims](docs/CORRECTNESS_CLAIMS.md)
- [Reproducibility details](docs/REPRODUCIBILITY.md)
- [Real-zeta POC algorithm](docs/algorithms/REAL_ZETA_POC.md)
- [High-bound zeta-zero verifier status](docs/algorithms/ZETA_ZERO_VERIFIER.md)
