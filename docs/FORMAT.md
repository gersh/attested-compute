# Certificates and run-bundle formats

SparkInterval has two independent evidence families:

- A **full result certificate** lets Lean recompute the mathematics from a
  self-contained witness. It does not establish who produced the witness or
  whether a GPU ran.
- A **run bundle** binds an algorithm, inputs, result, artifacts, environment,
  completion record, and evidence class. Its assurance depends on the selected
  verification policy.

See [Correctness claims](CORRECTNESS_CLAIMS.md) for what each path proves and
the [Trust model](TRUST_MODEL.md) for the assumptions behind execution
provenance.

Run relative commands in this reference from the repository root.

## Canonical JSON

The certificate, receipt, bundle, and signature wire formats use a strict
UTF-8 JSON subset. Profile values use the same restricted value types and are
hashed through the same canonical encoder.

- object keys are strings, sorted in encoded output, and may not be duplicated;
- separators are `,` and `:` with no insignificant whitespace;
- floating-point JSON numbers, `NaN`, and infinities are forbidden;
- integers are exact JSON integers;
- SHA-256 values are 64 lowercase hexadecimal characters; and
- canonical wire files have no byte-order mark or trailing newline.

The schemas describe structure. The Python and Lean parsers additionally
enforce canonical bytes and relationships that JSON Schema cannot express,
such as row arity, nested hashes, profile compatibility, and artifact-root
containment.

## Exact-reference and full Lean certificates

The certificate family uses these schemas:

| Object | Schema | Purpose |
| --- | --- | --- |
| Batch | [reference-batch.schema.json](../schemas/reference-batch.schema.json) | Expression, variable count, and finite interval input rows |
| Result | [reference-result.schema.json](../schemas/reference-result.schema.json) | Batch hash and claimed output intervals |
| Self-contained certificate | [reference-certificate.schema.json](../schemas/reference-certificate.schema.json) | Complete batch and result with their hashes |
| Lean-generation receipt | [lean-result-certificate-receipt.schema.json](../schemas/lean-result-certificate-receipt.schema.json) | Certificate identity, bound, decision mode, generated declarations, and source hash |

Binary64 values are lowercase 16-hex-digit words. Inputs and constants must be
finite. Results may contain exact positive or negative infinity after
overflow; NaNs are never accepted.

### Python exact-reference workflow

```bash
python3 -m reference.cli evaluate batch.json result.json
python3 -m reference.cli certify \
  --result result.json batch.json certificate.json
python3 -m reference.cli check certificate.json
```

The checker uses exact rational binary64 arithmetic rather than native Python
floating-point arithmetic. Used alone, this workflow supplies independently
recomputed reference data. It is neither a Lean proof nor execution evidence.

### Lean full-certificate workflow

The serialized checker validates the canonical certificate and a finite
binary64 application upper bound:

```bash
./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
./tools/with_memory_limit.sh \
  .lake/build/bin/sparkinterval-check-certificate \
  certificate.json --upper-bound 4010000000000001
```

To emit an importable Lean module and its canonical receipt:

```bash
mkdir -p build/certificate-check
CERT_DIR="$(mktemp -d build/certificate-check/run.XXXXXX)"
python3 tools/generate_lean_result_certificate.py \
  --certificate certificate.json \
  --upper-bound 4010000000000001 \
  --output "$CERT_DIR/GeneratedFullCertificate.lean" \
  > "$CERT_DIR/receipt.json"
./tools/safe_lean.sh "$CERT_DIR/GeneratedFullCertificate.lean"
```

The generator refuses to overwrite its Lean output. The fresh directory also
prevents shell redirection from replacing a receipt from an earlier attempt.

Lean parses the canonical bytes, checks the nested SHA-256 bindings, decodes
every binary64 endpoint into an exact rational, and reevaluates every row.
The mathematical checker accepts a claimed result when it contains that exact
reevaluation. The Python-backed generator is deliberately stricter: it emits a
module only when the supplied result exactly matches Python's independent
reference result.

Generated modules provide row-wise and finite-sum upper-bound theorems. Their
namespace and receipt bind the certificate digest, application bound, and
decision mode, allowing distinct certificates and reduction modes to coexist.

### Lean decision modes

The `--decision-mode` option controls concrete proof reduction, not GPU
execution:

| Mode | Direct typed-data checks | Serialized JSON/parser binding |
| --- | --- | --- |
| `kernel` (default) | `decide_cbv`; no `native_decide` dependency | Uses `native_decide` for the concrete parser equality |
| `native` | Uses `native_decide` | Uses `native_decide` |

The generic certificate soundness theorems are independent of this choice.
The generated source prints its theorem dependencies, and the receipt records
the selected mode. Native proof reflection is not evidence that a GPU ran.

### Certificate resource limits

Both implementations reject oversized or arithmetically explosive witnesses
before exact evaluation. Current limits include:

- 512 MiB of canonical certificate JSON;
- 1,000,000 rows and 65,536 variables;
- expression depth 256, expression nodes 100,000, and JSON nesting 300;
- natural-power exponents at most 64;
- symbolic arithmetic cost at most 4,096 per row; and
- row-count times arithmetic cost at most 10,000,000.

Use the [memory-safe entry points](MEMORY_SAFE_BUILDS.md) for every Lean build
or generated-module check.

## Run bundles

The normative structure is
[run-bundle.schema.json](../schemas/run-bundle.schema.json). A bundle contains
a `statement`, the canonical `statement_sha256`, an evidence object, and a
`bundle_sha256` over the remaining bundle fields.

The statement binds:

- target and trust profile identifiers plus hashes of the complete profiles;
- algorithm identifier and definition hash;
- input and output artifact paths, sizes, and hashes;
- parameters and domain coverage as canonical integer-only JSON;
- a 256-bit nonce;
- the host executable, at least one GPU execution image, and all other named
  build artifacts;
- the execution environment; and
- successful completion, output coverage, timestamps, and an empty CUDA-error
  list.

Artifact paths are canonical relative POSIX paths beneath one supplied root.
The verifier rejects absolute paths, traversal, non-regular files, and byte or
size mismatches.

`bundle_sha256` detects modification only when an expected digest arrives
through a trusted channel. A bundle and every digest inside it can otherwise
be fabricated together. For H100 production evidence, the external verifier
must check that report data binds the exact `statement_sha256`.

Specialized repository workflows create bundles for the DGX probe,
generated-cubin acceptance, and real-zeta tutorial. See the
[reproducibility runbook](REPRODUCIBILITY.md). The generic creator is
`tools/create_run_bundle.py`; run it with `--help` for the complete required
field list.

### Lean closed-registry binding

Wire-level algorithm fields do not let a caller invent formal semantics.
`RegisteredInvocation.statementCheck` accepts only a constructor of Lean's
closed registry and recomputes its library-defined algorithm-definition,
canonical-input, parameter, and domain digests. The combined
`SignedResultCertificate.outcomeCheckForRegisteredInvocation` also requires
exact result text and output-digest binding. Only then can the sole execution
axiom expose that invocation's fixed `Runs` proposition.

The current registry contains only the tutorial invocation
`cubicSumDivThree20000V1`; no zeta or production GPU checker is registered.
The bundle/signature tools do not yet import a verified wire record into the
private positive-evidence capability used by Lean. Consequently, valid JSON
and signature bytes alone cannot construct a registered Lean theorem in this
repository.

## Target and trust profiles

Targets and evidence classes are separate:

| Target profile | Permitted evidence classes | Current meaning |
| --- | --- | --- |
| [`dgx_spark_sm121`](../profiles/targets/dgx_spark_sm121.json) | `local_unattested` | DGX Spark/GB10 has no supported confidential-computing run attestation in this project |
| [`h100_sm90`](../profiles/targets/h100_sm90.json) | `local_unattested`, `mock_attested`, `hardware_attested` | Hardware evidence is meaningful only after external NVIDIA CC verification |

The trust profiles are:

- [`local_unattested`](../profiles/trust/local_unattested.json): artifact and
  reproducibility metadata, forgeable by the host;
- [`mock_attested`](../profiles/trust/mock_attested.json): parser/integration
  fixture that production policy rejects; and
- [`h100_hardware_attested`](../profiles/trust/h100_hardware_attested.json):
  structural profile requiring a trusted external evidence verifier.

Selecting a profile or inserting an evidence object does not itself establish
hardware evidence.

## Detached DGX operator signatures

The optional sidecar format is
[local-operator-signature.schema.json](../schemas/local-operator-signature.schema.json).
It signs a domain-separated payload containing:

- SHA-256 of the exact `run-bundle.json` file bytes;
- the bundle's `bundle_sha256`; and
- the bundle's `statement_sha256`.

The Ed25519 key ID is SHA-256 of its RFC 8410 SubjectPublicKeyInfo DER. The
sidecar embeds the public key for portability, but verification requires a
separately supplied pinned public key. Trusting only the embedded key proves
no operator identity.

After creating `build/dgx-probe-bundle`, create and use a passphrase-protected
operator key outside the artifact root as follows. The fresh directory keeps a
new passphrase from ever being paired with an older encrypted key, and the
restrictive `umask` protects the generated secret files:

```bash
mkdir -p build
umask 077
OPERATOR_KEY_DIR="$(mktemp -d build/operator-keys.XXXXXX)"
BUNDLE_ROOT=build/dgx-probe-bundle
SIGNATURE="$OPERATOR_KEY_DIR/run-bundle.signature.json"
openssl rand -base64 32 > "$OPERATOR_KEY_DIR/operator-passphrase.txt"
python3 tools/local_operator_signature.py keygen \
  --private-key "$OPERATOR_KEY_DIR/operator-private.pem" \
  --public-key "$OPERATOR_KEY_DIR/operator-public.pem" \
  --passphrase-file "$OPERATOR_KEY_DIR/operator-passphrase.txt"
python3 tools/local_operator_signature.py sign \
  "$BUNDLE_ROOT/run-bundle.json" \
  --artifact-root "$BUNDLE_ROOT" \
  --private-key "$OPERATOR_KEY_DIR/operator-private.pem" \
  --passphrase-file "$OPERATOR_KEY_DIR/operator-passphrase.txt" \
  --out "$SIGNATURE"
```

The private key and passphrase file must have mode `0600`. The tool also
supports an explicit `--allow-unencrypted-private-key` option for disposable
local tests. Never place a private key in an artifact bundle or repository.

A valid signature identifies the signing key and protects the exact record
from undetected modification. It does not prove that the record is true, that
a GPU ran, or that timestamps and hardware identities are trustworthy. The
inner bundle remains `local_unattested` and verification reports
`hardware_evidence: false`.

## Verification policies

### Integrity only

```bash
python3 tools/verify_run_bundle.py \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle
```

This checks canonical structure, compatible profiles, hashes, and every bound
artifact. It supplies no execution provenance.

### DGX operator-signed policy

```bash
BUNDLE_ROOT=build/dgx-probe-bundle
OPERATOR_KEY_DIR=/path/to/retained-operator-key-directory
SIGNATURE="$OPERATOR_KEY_DIR/run-bundle.signature.json"
TRUSTED_OPERATOR_KEY="$OPERATOR_KEY_DIR/operator-public.pem"
mkdir -p verifier-state
python3 tools/verify_run_bundle.py \
  "$BUNDLE_ROOT/run-bundle.json" \
  --artifact-root "$BUNDLE_ROOT" \
  --policy dgx_operator_signed \
  --operator-signature "$SIGNATURE" \
  --trusted-operator-key "$TRUSTED_OPERATOR_KEY" \
  --replay-db verifier-state/operator-nonces.sqlite3
```

The replay database is required and records a nonce only after all checks
succeed. A nonce proves freshness only when the verifier supplied it
unpredictably before the run.

### H100 production policy

No accepted positive H100 bundle currently exists in the repository. The
following is a deployment template, not an offline success path; replace both
absolute paths with independently provisioned production inputs:

```bash
H100_RUN=/path/to/accepted-h100-run
ATTESTATION_VERIFIER=/trusted/bin/verify-nvidia-cc-evidence
mkdir -p verifier-state
python3 tools/verify_run_bundle.py \
  "$H100_RUN/run-bundle.json" \
  --artifact-root "$H100_RUN" \
  --policy h100_production \
  --replay-db verifier-state/h100-nonces.sqlite3 \
  --attestation-verifier "$ATTESTATION_VERIFIER"
```

The external executable is invoked without a shell with the evidence path,
format, and expected report-data SHA-256. It must validate the cryptographic
chain, pinned platform policy, freshness, and statement binding before
returning success. Without that executable, complete artifact bytes, and
persistent replay state, production verification fails closed. See
[H100 support](H100.md).
