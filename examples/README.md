# Examples

Run commands from the repository root. Generated outputs belong under
`build/`, and private keys must not be committed. The complete runnable paths
are collected in [Using SparkInterval](../docs/USING.md).

## Exact CPU reference certificate

Recompute a two-row `x * (1 + y)` example using exact rational binary64
arithmetic:

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

See [reference-certificate/README.md](reference-certificate/README.md).

## Full Lean result certificate

Generate a complete typed Lean witness in a fresh directory and check both the
generated module and canonical serialized certificate:

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

See [lean-result-certificate/README.md](lean-result-certificate/README.md).

## Small Lean proofs

```bash
./tools/safe_lake_build.py \
  SparkInterval.IntervalOpsSound \
  SparkInterval.Execution.Trusted.DGXOperatorSignature \
  SparkInterval.Execution.Trusted.H100Attestation
./tools/safe_lean.sh examples/lean/IntervalArithmetic.lean
./tools/safe_lean.sh examples/lean/ZetaIdentity.lean
./tools/safe_lean.sh examples/lean/ExecutionTrust.lean
```

These demonstrate interval containment, an exact Mathlib zeta identity, and
the explicit execution-trust boundary respectively.

## GPU workflows

- [DGX local execution and operator signing](../docs/USING.md#dgx-spark-local-bundle-and-operator-signature)
- [Real-integer zeta POC](../docs/USING.md#real-integer-zeta-poc)
- [H100 offline work](../docs/USING.md#h100-offline-work)

The DGX signature is operator provenance, not hardware evidence. The zeta POC
encloses positive real values and does not verify critical-strip zeros. The
H100 workflow builds device artifacts but does not execute or attest a run.
