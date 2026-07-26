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

- target and trust profile identifiers plus hashes of the complete profiles,
  and a `backend_kind` that must equal the target profile's `cpu` or `gpu`
  classification;
- algorithm identifier and definition hash;
- input and output artifact paths, sizes, and hashes;
- parameters and domain coverage as canonical integer-only JSON;
- a 256-bit nonce;
- the host executable and all other named build artifacts; GPU targets also
  require at least one exact GPU execution image, while CPU targets reject GPU
  execution-image roles;
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
canonical-input, parameter, and domain digests. It also rejects results outside
the constructor's explicit canonical result language before any `Runs`
semantics can be selected. The combined
`SignedResultCertificate.outcomeCheckForRegisteredInvocation` also requires
exact result text and output-digest binding. Only then can the sole execution
axiom expose that invocation's fixed `Runs` proposition.

The current registry contains the CPU tutorial, the one-row
`h100FormalPtxConstantOneV1` `sm_90` deployment pilot, and closed
Ternary-Goldbach computations including an exact conditional PT21 finite-RH
slice and an exact conditional Platt Dirichlet Theorem 7.1 finalizer.
Registration is not evidence of a successful run: those success relations
still require explicit complete source evidence, which has not been
materialized. The source importer can generate a
review candidate only after independently verifying the exact wire record,
evidence appraisal, signature, and closed invocation. The tracked receipt
registry is empty, so valid JSON and signature bytes alone cannot construct an
accepted registered Lean theorem in this repository.

## Target and trust profiles

Targets and evidence classes are separate:

| Target profile | Permitted evidence classes | Current meaning |
| --- | --- | --- |
| [`dgx_spark_sm121`](../profiles/targets/dgx_spark_sm121.json) | `local_unattested` | DGX Spark/GB10 has no supported confidential-computing run attestation in this project |
| [`h100_sm90`](../profiles/targets/h100_sm90.json) | `local_unattested`, `mock_attested`, `hardware_attested` | Hardware evidence is meaningful only after external NVIDIA CC verification |
| [`azure_sevsnp_cpu`](../profiles/targets/azure_sevsnp_cpu.json) | `local_unattested`, `hardware_attested` | Generic CPU-only Azure SEV-SNP confidential-VM target |
| [`azure_ncc40ads_h100_v5`](../profiles/targets/azure_ncc40ads_h100_v5.json) | `local_unattested`, `hardware_attested` | Exact `Standard_NCC40ads_H100_v5` target: 40 AMD EPYC Genoa vCPUs, 320 GiB system memory, and one 94 GB H100 NVL GPU |

The trust profiles are:

- [`local_unattested`](../profiles/trust/local_unattested.json): artifact and
  reproducibility metadata, forgeable by the host;
- [`mock_attested`](../profiles/trust/mock_attested.json): parser/integration
  fixture that production policy rejects; and
- [`h100_hardware_attested`](../profiles/trust/h100_hardware_attested.json):
  legacy generic H100 structural profile requiring a trusted external evidence
  verifier;
- [`azure_sevsnp_hardware_attested`](../profiles/trust/azure_sevsnp_hardware_attested.json):
  Azure Attestation/SEV-SNP evidence for the CPU-only target; and
- [`azure_ncc_sevsnp_vtpm_nvidia_cc_attested`](../profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json):
  exact NCC composite policy requiring the external verifier to validate and
  jointly bind SEV-SNP, vTPM, and NVIDIA confidential-computing evidence.

The exact NCC dimensions and CPU/GPU-spanning TEE are recorded by Microsoft's
[`NCCads_H100_v5` size reference](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nccadsh100v5-series)
and [Azure confidential-GPU overview](https://learn.microsoft.com/en-us/azure/confidential-computing/gpu-options).
The generic `h100_sm90` and `h100_hardware_attested` profiles remain available
for non-Azure or historical bundles; they are not aliases for the composite
Azure NCC policy.

### Azure CPU CVM deployment profile

[`azure/cpu_cvm.py`](../azure/cpu_cvm.py) is a separate CPU-only control-plane
adapter. It admits exactly two reviewed AMD SEV-SNP shapes:

| Azure SKU | Role | vCPUs | Memory | Accelerators |
| --- | --- | ---: | ---: | --- |
| `Standard_EC96as_v6` | Default memory-heavy finite computation | 96 | 672 GiB | None |
| `Standard_DC96as_v6` | Explicit lower-memory alternative | 96 | 384 GiB | None |

These dimensions, Generation 2 support, absence of accelerators, and AMD EPYC
9004/SEV-SNP classification come from Microsoft's current
[`ECasv6` reference](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/memory-optimized/ecasv6-series)
and [`DCasv6` reference](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dcasv6-series).
The adapter checks the exact live SKU record, subscription restrictions, SKU
family quota, and total regional-vCPU quota. Quota is not a capacity guarantee;
allocation remains the authoritative capacity test.
Both reviewed shapes currently use the generic `azure_sevsnp_cpu` run-bundle
target. The exact selected SKU, resolved image, preflight result, and
post-create inspection therefore remain required execution-environment
artifacts; the generic profile name alone does not assert either shape.

Deployment requires `ConfidentialVM`, Secure Boot, vTPM,
`DiskWithVMGuestState`, an existing subnet with `defaultOutboundAccess=false`,
a subnet-level NSG and explicit NAT gateway or reviewed route table, and no
public IP. The default Canonical Ubuntu confidential-VM image uses the
Microsoft-documented CVM offer, but `latest` is resolved to an exact numeric
marketplace version before creation. Custom images must be exact marketplace
URNs or Compute Gallery version resource IDs. These settings follow
Microsoft's [confidential-VM CLI guidance](https://learn.microsoft.com/en-us/azure/confidential-computing/quick-create-confidential-vm-azure-cli)
and the Compute API's
[`DiskWithVMGuestState` security profile](https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/create-or-update?tabs=HTTP&view=rest-compute-2023-10-02).

After allocation, the adapter reads each VM and its NIC back and rejects any
mismatch in SKU, pinned image, security type, Secure Boot, vTPM, disk security,
provisioning status, or absence of a private-only NIC. A dry run is
deliberately reported as `accepted: false`,
performs no Azure query, creates nothing, and makes no capacity or attestation
claim. A successful deployment still reports `attestation_collected: false`
and `resources_proven_attested: 0`; deployment configuration is not execution
evidence.

```bash
python3 azure/cpu_cvm.py preflight \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location eastus2 \
  --nodes 1 \
  --dry-run

python3 azure/cpu_cvm.py deploy \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location eastus2 \
  --nodes 1 \
  --resource-group tg-private \
  --name-prefix tg-cpu \
  --admin-username tgoperator \
  --ssh-key "$HOME/.ssh/id_ed25519.pub" \
  --subnet-id "$AZURE_PRIVATE_SUBNET_ID" \
  --dry-run
```

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
