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
  SparkInterval.Execution.Trusted.DGXOperatorSignature \
  SparkInterval.Execution.Trusted.H100Attestation
./tools/safe_lean.sh examples/lean/IntervalArithmetic.lean
./tools/safe_lean.sh examples/lean/ZetaIdentity.lean
./tools/safe_lean.sh examples/lean/ExecutionTrust.lean
```

The first example checks a concrete interval enclosure. The second proves
Mathlib's exact `riemannZeta 2 = pi^2 / 6` identity. The third demonstrates the
explicit execution-trust boundary; it does not manufacture execution evidence.

## Full Lean result certificate

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
  --work-dir "$ZETA_DIR" --s 2 --terms 4096
python3 tools/run_zeta_poc.py verify "$ZETA_DIR"
```

The verifier reparses and exactly recomputes every term, requires a
byte-identical GPU replay, repeats the artifact audits, performs outward
interval reduction, and adds an integral-test tail. Supply `--nonce` with a
verifier-provided 64-hex-character challenge when freshness is required. The
result is a rigorous enclosure of real `zeta(s)` for supported integer
`s > 1`; it is not a critical-strip zero or Riemann-hypothesis verifier. See
the [algorithm definition](algorithms/REAL_ZETA_POC.md).

The generated zeta bundle can be signed by replacing the probe bundle root in
the preceding signing commands with `$ZETA_DIR`.

## H100 offline work

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
See the [H100 guide](H100.md).

## Interpreting results

Read [Correctness claims](CORRECTNESS_CLAIMS.md) and the
[Trust model](TRUST_MODEL.md) before turning a successful command into a claim.
Artifact hashes establish identity only relative to a trusted expected digest;
they do not establish that the recorded fields are true.
