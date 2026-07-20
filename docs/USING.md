# Using SparkInterval

Run commands from the repository root. Generated files and run evidence belong
under `build/`. Private keys must never be committed.

Lean commands in this guide use the repository's serialized, memory-capped
wrappers. Do not replace them with bare parallel `lake` or `lean` commands; see
[Memory-safe builds](MEMORY_SAFE_BUILDS.md).

## Core Lean examples

```bash
./tools/safe_lake_build.py \
  SparkInterval.IntervalOpsSound \
  SparkInterval.Execution
./tools/safe_lean.sh examples/lean/IntervalArithmetic.lean
./tools/safe_lean.sh examples/lean/ZetaIdentity.lean
./tools/safe_lean.sh examples/lean/ExecutionTrust.lean
./tools/safe_lean.sh examples/lean/SignedResultCertificate.lean
./tools/safe_lean.sh examples/lean/RegisteredCubicSum.lean
```

The first example checks a concrete interval enclosure. The second proves
Mathlib's exact `riemannZeta 2 = pi^2 / 6` identity. The third demonstrates the
explicit execution-trust boundary; it does not manufacture execution evidence.
Both the DGX and H100 compatibility entry points depend on the sole
`accepted_run_certificate_sound` axiom. The fourth demonstrates the
signed-result API: `outcomeCheck_sound` proves the exact historical returned
certificate and hash binding. `outcomeCheckForRegisteredInvocation_sound`
additionally exposes fixed formal `Runs` semantics after a closed invocation
check; `accepted_registered_run_sound` is a proved projection of the same sole
axiom. The generic checked-certificate variants independently add certificate
mathematics. The fifth specializes that interface to the complete registered
cubic-sum computation. None of these examples is a concrete signed-bundle importer, a
universal determinism result, or a general proof that a physical backend
implements the formal semantics.

The closed registry currently contains one tutorial invocation:
`cubicSumDivThree20000V1`, representing the exact rational sum
`sum (x = 0 .. 20000) (x^3 / 3)`. Its operational model accumulates integer
cubes with `cubicNumeratorLoop`, then `cubicSumDivThreeMachine` divides once.
Lean proves the exact machine output `13334666700000000`, its agreement with
the rational specification, and that every cube and accumulator step fits
u64. These algorithm and bounded-arithmetic proofs are axiom-free and use
neither `native_decide` nor a 20,001-row result certificate; they do not prove
that GPU opcodes implement the model. `certifyCubicSumDivThree20000` recovers
the canonical output and mathematical equality from a matching accepted
certificate. That theorem remains conditional on private evidence because no
wire-to-Lean importer is implemented.

## Full Lean result certificate

This workflow produces a Lean source module, not merely a command-line
acceptance result. The module materializes the certificate's formula, inputs,
and interval results and exports theorems that another Lean package can import.
The original CPU/GPU producer calculation need not run in the consuming
project. A clean build still checks the certificate module, while later imports
of its current `.olean` reuse the elaborated theorem environment.

For the producer/publisher/consumer model, an import example, and comparison
with `decide`, `native_decide`, and other proof-certificate systems, see
[Using computation certificates from Lean](LEAN_INTEGRATION.md).

The generator refuses to overwrite its Lean output. Always select a fresh
destination:

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

The generated `application_upper_bound_sound` and
`certificate_sum_upper_bound_sound` theorems use complete typed certificate
data. In explicit `kernel` mode they use kernel reduction and do not depend on
`native_decide`. The serialized `application_theorem` and
`application_sum_theorem` additionally bind the canonical JSON, hashes, and
parser result; their concrete parser equality uses `native_decide`.

For a large materialized witness, `--decision-mode native` is an explicit
performance/trust choice that also uses `native_decide` for the direct typed
checks. The selected mode is recorded in the generated namespace and receipt.
See the [full-certificate example](../examples/lean-result-certificate/README.md)
and [format documentation](FORMAT.md#exact-reference-and-full-lean-certificates).

## Exact CPU reference package

For a Python-only exact recomputation example:

```bash
mkdir -p build/examples
REF_DIR="$(mktemp -d build/examples/reference.XXXXXX)"
python3 -m reference.cli evaluate \
  examples/reference-certificate/batch.json "$REF_DIR/result.json"
python3 -m reference.cli certify \
  --result "$REF_DIR/result.json" \
  examples/reference-certificate/batch.json "$REF_DIR/certificate.json"
python3 -m reference.cli check "$REF_DIR/certificate.json"
```

This is exact CPU evidence, not a Lean theorem or execution attestation. Pass
the resulting canonical certificate through the full Lean workflow when an
independently checked mathematical theorem is required.

## DGX Spark local bundle and operator signature

First satisfy the [DGX Spark prerequisites](DGX_SPARK_SETUP.md), then build and
verify the local diagnostic bundle:

```bash
./tools/build_dgx_spark.sh
python3 tools/verify_run_bundle.py \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle
```

For a freshness claim, obtain a 32-byte nonce from the verifier before the run
and set `SPARKINTERVAL_NONCE_HEX` to its 64 lowercase hexadecimal characters
when invoking `build_dgx_spark.sh`. A locally generated nonce establishes
uniqueness only.

For a disposable signing tutorial, use a fresh key directory:

```bash
mkdir -p build/examples
KEY_DIR="$(mktemp -d build/examples/operator-key.XXXXXX)"
SIGNATURE="$KEY_DIR/run-bundle.signature.json"
REPLAY_DB="$KEY_DIR/operator-nonces.sqlite3"
python3 tools/local_operator_signature.py keygen \
  --private-key "$KEY_DIR/operator-private.pem" \
  --public-key "$KEY_DIR/operator-public.pem" \
  --allow-unencrypted-private-key
python3 tools/local_operator_signature.py sign \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle \
  --private-key "$KEY_DIR/operator-private.pem" \
  --out "$SIGNATURE"
python3 tools/local_operator_signature.py verify \
  build/dgx-probe-bundle/run-bundle.json \
  "$SIGNATURE" \
  --artifact-root build/dgx-probe-bundle \
  --trusted-public-key "$KEY_DIR/operator-public.pem"
python3 tools/verify_run_bundle.py \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle \
  --policy dgx_operator_signed \
  --operator-signature "$SIGNATURE" \
  --trusted-operator-key "$KEY_DIR/operator-public.pem" \
  --replay-db "$REPLAY_DB"
```

Use `--passphrase-file` instead of the unencrypted-key option for a retained
key; the private key and passphrase file must be mode `0600`. Pin the public key
through a separate trusted channel. A successful signature proves endorsement
by that key, while the bundle remains `local_unattested` and reports
`hardware_evidence: false`. Reusing the nonce with the same replay database is
rejected. See [Run-bundle format](FORMAT.md#detached-dgx-operator-signatures).

## Real-integer zeta POC

The same verifier supports the strict `dgx_spark_sm121` and `h100_sm90`
profiles. In both cases it produces a `local_unattested` bundle and reports
`hardware_evidence: false`.

### DGX Spark

If `build_dgx_spark.sh` has already completed, the required expression runner
is available. Otherwise build it with one CMake job:

```bash
./tools/with_memory_limit.sh cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
./tools/with_memory_limit.sh cmake --build build/dgx-spark --parallel 1
```

The run command refuses an existing destination, so choose a fresh directory:

```bash
mkdir -p build/examples
ZETA_PARENT="$(mktemp -d build/examples/zeta2.XXXXXX)"
ZETA_DIR="$ZETA_PARENT/run"
python3 tools/run_zeta_poc.py run \
  --target-profile dgx_spark_sm121 \
  --work-dir "$ZETA_DIR" \
  --s 2 \
  --terms 4096
python3 tools/run_zeta_poc.py verify "$ZETA_DIR"
```

The verifier reparses and exactly recomputes every term, requires a
byte-identical GPU replay, repeats the artifact audits, performs outward
interval reduction, and adds an integral-test tail. Supply `--nonce` with a
verifier-provided 64-hex-character challenge when freshness is required. The
result is a rigorous enclosure of real `zeta(s)` for supported integer
`s > 1`; it is not a critical-strip zero or Riemann-hypothesis verifier. See
the [algorithm definition](algorithms/REAL_ZETA_POC.md).

The generated DGX zeta bundle can be signed by replacing the probe bundle root
in the preceding signing commands with `$ZETA_DIR`.

### H100

First build and validate the native H100 backend on a host with exactly one
visible H100 at compute capability 9.0:

```bash
H100_BUILD_JOBS=1 ./tools/run_h100_native_validation.sh
```

The retained H100 target profile requires an `x86_64` host and device zero.
Use a fresh destination and select the profile explicitly:

```bash
mkdir -p build/examples
H100_ZETA_PARENT="$(mktemp -d build/examples/h100-zeta2.XXXXXX)"
H100_ZETA_DIR="${H100_ZETA_PARENT}/run"
python3 tools/run_zeta_poc.py run \
  --target-profile h100_sm90 \
  --work-dir "${H100_ZETA_DIR}" \
  --s 2 \
  --terms 4096 \
  --device 0
python3 tools/run_zeta_poc.py verify "${H100_ZETA_DIR}"
```

This selects
`build/h100-native/sparkinterval-h100-expression-batch` by default, requires
the H100-specific algorithm definition and `sm_90` audit, and rejects a
mislabelled device or target profile. The detached operator-signature policy
is intentionally DGX-specific and cannot be applied to this H100 bundle.
H100 confidential-computing acceptance is a separate, currently fail-closed
policy; this POC does not collect its evidence.

At the Lean boundary, a future trusted importer would construct one
`RunCertificate` from the exact verified statement and private evidence
capability. If `RunCertificate.check` accepts it, the sole project axiom states
that this particular named run returned its statement's exact result and
supplies fixed `Runs` semantics for any matching closed registered invocation.
The current real-zeta tutorial is not registered for either target. For a full
result-certificate payload, `SignedResultCertificate.outcomeCheck_sound`
proves exact payload/hash binding, and the upper-bound or sum checkers add
independently checked mathematics. No current command imports a zeta bundle
into that private Lean capability.

## H100 native local validation

To build the strict native CLIs and check their `sm_90` images and pre-CUDA
fail-closed behavior without executing on an H100:

```bash
cmake -S . -B build/h100-native \
  -DSPARKINTERVAL_BUILD_H100_NATIVE=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/h100-native \
  --target sparkinterval-h100-native \
  --parallel 1
ctest --test-dir build/h100-native \
  -R '^h100_native_cli_offline$' \
  --output-on-failure
```

The fixed generated probe cubin is
`build/h100-native/h100/h100_rounding_probe.sm_90.cubin`; the same build
produces the strict probe, primitive, expression, and three
ternary-Goldbach host runners under `build/h100-native/`:

```text
sparkinterval-h100-tg-r2star-factor-support
sparkinterval-h100-tg-r2star-chunk
sparkinterval-h100-tg-mobius-segment
```

On a host with exactly one visible H100 at compute capability 9.0, run the
complete local suite instead:

```bash
H100_BUILD_JOBS=1 ./tools/run_h100_native_validation.sh \
  --build-dir build/h100-native \
  --output-dir build/h100-native-validation \
  --primitive-count 10000 \
  --expression-count 10000 \
  --expression-program-count 8 \
  --device 0
```

It builds, runs the offline CTest, audits PTX/SASS, executes the rounding
probe, and performs exact primitive and expression conformance. It builds and
offline-checks the ternary-Goldbach executables but does not execute those
kernels. The retained results are `local_unattested`; success is not
confidential-computing attestation. Use fresh directories for evidence that
will be archived. See the [H100 guide](H100.md) and
[reproducibility runbook](REPRODUCIBILITY.md#h100-native-local-validation).

## H100 generated `sm_90` polynomial conformance

The separate typed polynomial path now accepts an explicit `sm_90` target.
After configuring `build/h100-native` as above, run:

```bash
./tools/safe_lake_build.py --target sparkinterval-gen
cmake --build build/h100-native \
  --target sparkinterval-generated-driver \
  --parallel 1
mkdir -p build/examples
GENERATED_H100_DIR="$(mktemp -d build/examples/generated-sm90.XXXXXX)"
python3 tools/run_generated_ptx_conformance.py \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/h100-native/sparkinterval-generated-driver \
  --target sm_90 \
  --count 4096 \
  --work-dir "${GENERATED_H100_DIR}" \
  > "${GENERATED_H100_DIR}/summary.json"
```

The harness writes `kernel.sm_90.cubin`, its SASS and audits, exact results,
and `report.json` into that directory. This is polynomial conformance, not the
division-capable zeta program. The closure and generated-cubin bundle tools
remain DGX/`sm_121` specific, so the H100 report is local conformance evidence
and not a canonical CC-attested bundle.

## H100 offline artifacts

No H100 is needed to build and audit the device artifacts. Choose either the
artifact-only commands:

```bash
./tools/build_h100_offline.sh
./tools/build_h100_interval_batch_offline.sh
```

or the self-testing commands, which each perform their own build:

```bash
./tests/test_h100_offline.sh
./tests/test_h100_interval_batch_offline.sh
```

Do not run both sets merely to validate the same output. `CUDA_ROOT`, `NVCC`,
`NVDISASM`, `CUOBJDUMP`, and `CXX` can select an alternate installed toolchain.
These workflows create real `compute_90` PTX and `sm_90` cubin/SASS, but do not
query an H100, execute a kernel, return an arithmetic result, or produce
attestation. Production confidential-computing acceptance remains fail-closed.
Any future H100-positive importer uses the same `RunCertificate` checker and
same sole execution axiom as DGX; `h100_attested_run_sound` is only a
historical compatibility theorem, and `accepted_registered_run_sound` is the
derived closed-registry projection. See the [H100 guide](H100.md).

## Interpreting results

Read [Correctness claims](CORRECTNESS_CLAIMS.md) and the
[Trust model](TRUST_MODEL.md) before turning a successful command into a claim.
Artifact hashes establish identity only relative to a trusted expected digest;
they do not establish that the recorded fields are true.
