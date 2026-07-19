# Run-bundle format

`tools/create_run_bundle.py` emits one canonical, UTF-8 JSON object. The file
has no byte-order mark, insignificant whitespace, or trailing newline. Object
keys are sorted and separators are `,` and `:`. JSON floating-point values,
`NaN`, infinities, duplicate object keys, and non-string object keys are
rejected. Integers are exact JSON integers.

Every SHA-256 value is exactly 64 lowercase hexadecimal characters. Relative
artifact paths use canonical POSIX syntax and cannot leave the artifact root.
The normative structural description is `schemas/run-bundle.schema.json`; the
Python verifier also enforces security relationships that JSON Schema cannot
express.

## Exact-reference formats

Phase 3 also defines three canonical formats under `schemas/`:

- `reference-batch.schema.json` binds the expression, variable count, and
  finite interval input rows;
- `reference-result.schema.json` binds the input hash and exact evaluated
  output rows;
- `reference-certificate.schema.json` is self-contained and packages the
  batch and result for Python recomputation.

These files use canonical compact UTF-8 JSON with sorted keys, exact integers,
and lowercase 16-hex-digit binary64 words. Input and constant endpoints must
be finite; result endpoints may be exact infinities after overflow; NaNs are
never accepted. The parser caps a batch at 1,000,000 rows and the current
non-streaming JSON input at 512 MiB.

Use the reference CLI to evaluate, package, and independently recompute these
objects:

```bash
python3 -m reference.cli evaluate batch.json result.json
python3 -m reference.cli certify --result result.json \
  batch.json certificate.json
python3 -m reference.cli check certificate.json
```

The Python parser is authoritative for relationships JSON Schema cannot fully
express, including row arity, variable indices, row-count equality, hashes,
and exact recomputation. Here “certificate” means a Python-recomputed
reference package. There is no Lean parser/checker or theorem relating this
wire expression to Lean `Expr`/`FPInterval`; it is not execution evidence,
attestation, or a signature.

## Bound run statement

The `statement` serializes and hash-binds all facts that a later proof is
intended to consume:

- target-profile and trust-profile identifiers plus the canonical hash of each
  profile;
- algorithm identifier and formal-definition hash;
- input path, size, and content hash;
- the exact parameter object and its canonical hash;
- the exact domain-coverage object and its canonical hash;
- output path, size, and content hash;
- a 256-bit nonce;
- the exact host executable and at least one GPU execution image (`gpu_cubin`,
  `gpu_fatbin`, `gpu_ptx`, or `gpu_executable`), plus every other named build
  artifact, including each role, path, size, and content hash;
- the execution-environment object and its canonical hash; and
- successful completion, zero exit status, complete output count, an empty
  CUDA-error list, and start/end timestamps.

`statement_sha256` is the SHA-256 of the canonical `statement` value. An H100
attestation verifier must check that the hardware evidence's report-data field
binds this exact digest. `bundle_sha256` covers the complete bundle except for
the `bundle_sha256` field itself. The bundle hash detects accidental or
unrecomputed modification; by itself it is not a signature or evidence of who
ran anything.

Hash binding prevents substitution only relative to a trusted expected digest
or accepted execution-evidence chain. It does not establish that the fields
are true or that an opaque algorithm hash denotes a particular Lean
definition.

## Target and trust profiles

Targets and trust are deliberately independent:

| Target profile | Permitted trust/evidence classes |
| --- | --- |
| `dgx_spark_sm121` | `local_unattested` only |
| `h100_sm90` | `local_unattested`, `mock_attested`, or `hardware_attested` |

The `local_unattested` profile always has `hardware_attestation: null`. This is
the only valid DGX Spark form. It is an integrity and reproducibility record,
not confidential-computing evidence.

### Detached DGX operator signature

`schemas/local-operator-signature.schema.json` defines an optional canonical
Ed25519 sidecar. It does not change the inner run bundle: its trust profile and
evidence class remain `local_unattested`, and `hardware_attestation` remains
`null`.

The sidecar signs a domain-separated canonical payload binding three values:
the SHA-256 of the exact complete `run-bundle.json` bytes, the bundle's own
`bundle_sha256`, and its `statement_sha256`. The `key_id` is SHA-256 of the
RFC 8410 Ed25519 SubjectPublicKeyInfo DER. Although the sidecar embeds that
public key for portability, verification requires a separately supplied pinned
public PEM with the same DER and key ID. Trusting only the embedded key would
prove no operator identity.

A valid signature proves that possession of the selected private key signed
the exact record. It does not prove that the record is true, identify physical
hardware, establish a trustworthy time, isolate the key, or prove a CUDA
kernel ran. The fixed sidecar warning is
`LOCAL OPERATOR SIGNATURE ONLY - NOT HARDWARE ATTESTATION`.

The `mock_attested` profile has a conspicuous test marker in
`mock_attestation` and keeps `hardware_attestation: null`. It exists only to
exercise the offline H100 path. The production policy rejects it before an
attestation verifier is called.

The `h100_hardware_attested` profile requires a hashed evidence artifact. Its
presence is still only structural. Production acceptance additionally requires
a trusted external NVIDIA confidential-computing verifier to validate the
evidence chain, platform policy, freshness, and the report-data binding to
`statement_sha256`.

## Creation

All bound artifacts must be beneath one root. Parameter, coverage, environment,
and completion arguments are JSON files in the integer-only subset.

```bash
python3 tools/create_run_bundle.py \
  --root build/run \
  --target-profile profiles/targets/dgx_spark_sm121.json \
  --trust-profile profiles/trust/local_unattested.json \
  --algorithm-id ExampleIntervalBatch.v1 \
  --algorithm-definition-sha256 "$ALGORITHM_SHA256" \
  --input build/run/input.bin \
  --parameters build/run/parameters.json \
  --domain-coverage build/run/coverage.json \
  --output build/run/output.bin \
  --nonce "$CHALLENGER_NONCE_HEX" \
  --build-artifact host_executable=build/run/sparkinterval-run \
  --build-artifact gpu_executable=build/run/kernel.cubin \
  --execution-environment build/run/environment.json \
  --completion build/run/completion.json \
  --out build/run/run-bundle.json
```

For an anti-replay claim, the nonce must be unpredictable and supplied by the
party that will verify the run. A random value chosen only by the prover shows
uniqueness, not freshness.

For a retained Phase 5 generated-cubin acceptance directory, use the stricter
wrapper rather than manually enumerating artifacts:

```bash
python3 tools/create_dgx_generated_cubin_bundle.py \
  --work-dir build/generated-ptx-conformance/rows-100000 \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --phase4 build/dgx-spark/sparkinterval-expression-batch \
  --output-root build/generated-cubin-run-bundle/rows-100000 \
  --start-time-utc "$RUN_START_UTC" \
  --end-time-utc "$RUN_END_UTC" \
  --nonce "$CHALLENGER_NONCE_HEX"
```

This wrapper first checks strong acceptance, exact-reference summaries, the
literal signed-zero suite, exact-cubin hardware metadata, all replay/hash
bindings, and Phase 4 payload equality. It preserves the exact compiler and
disassembler binaries. The resulting DGX record remains local and unattested.

Create a new operator key and sign an already integrity-checked DGX bundle:

```bash
python3 tools/local_operator_signature.py keygen \
  --private-key operator-private.pem \
  --public-key operator-public.pem \
  --passphrase-file operator-passphrase.txt
python3 tools/local_operator_signature.py sign build/run/run-bundle.json \
  --artifact-root build/run \
  --private-key operator-private.pem \
  --passphrase-file operator-passphrase.txt \
  --out build/run/run-bundle.signature.json
```

The passphrase file and private key must be mode `0600`. For a disposable POC,
`keygen --allow-unencrypted-private-key` explicitly opts into an unencrypted
mode-`0600` key. The tool refuses to overwrite either key and never places the
private key in a bundle.

## Verification policies

Integrity verification can check the canonical bundle and all referenced file
bytes:

```bash
python3 tools/verify_run_bundle.py build/run/run-bundle.json \
  --artifact-root build/run \
  --replay-db verifier-state/nonces.sqlite3
```

The result explicitly reports `hardware_evidence: false` for local and mock
records. The replay database records a nonce only after all requested checks
succeed and rejects its reuse.

Operator-signed DGX verification additionally requires all artifact bytes, a
separately pinned public key, and persistent replay state:

```bash
python3 tools/verify_run_bundle.py build/run/run-bundle.json \
  --artifact-root build/run \
  --policy dgx_operator_signed \
  --operator-signature build/run/run-bundle.signature.json \
  --trusted-operator-key operator-public.pem \
  --replay-db verifier-state/operator-nonces.sqlite3
```

A successful result has `operator_signature_valid: true` and assurance
`operator_signed_local_record_not_hardware_evidence`, while retaining
`hardware_evidence: false`. The nonce must originate with the verifier for a
freshness claim; a prover-chosen nonce is only a uniqueness field.

Production H100 verification is fail-closed:

```bash
python3 tools/verify_run_bundle.py build/run/run-bundle.json \
  --artifact-root build/run \
  --policy h100_production \
  --replay-db verifier-state/nonces.sqlite3 \
  --attestation-verifier /trusted/bin/verify-nvidia-cc-evidence
```

The external verifier is invoked without a shell as:

```text
verify-nvidia-cc-evidence \
  --evidence PATH \
  --format nvidia_cc_evidence \
  --expected-report-data-sha256 HEX_DIGEST
```

It must return zero only after cryptographic and policy validation. Without
that executable, artifact bytes, and persistent replay state, the production
policy rejects the bundle. Selecting a profile, inserting a mock object, or
asserting a verdict in JSON can never satisfy the production policy.
