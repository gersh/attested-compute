# Azure Managed HSM receipt signing

The receipt signer belongs on the independent relying-party side of the
trusted-compute pipeline, never on an Azure computation worker. It signs only
after the pinned Azure/NVIDIA appraisers have accepted the complete evidence
pack and the receipt issuer has rebound that appraisal to the exact canonical
run bundle, output, challenge, and registered algorithm claim.

This repository includes
[`azure/managed_hsm_signer.py`](../azure/managed_hsm_signer.py), a narrow
adapter for an RSA-3072 key in Azure Managed HSM. It requires an immutable key
version URI, asks Azure to sign the SHA-256 digest with `RS256`, and verifies
the returned 384-byte signature again with the locally pinned public key
before releasing it. It does not create a key, choose a mutable latest
version, grant roles, or treat possession of an Azure login as evidence of a
computation.

## Provision and pin a production key

The exact identity, role assignments, network policy, and key-creation record
need a separate security review. Microsoft's current key-attestation procedure
requires Azure CLI 2.73.0 or later and lists Python 3.13.2 for its validation
script; record the actual `az version` and `python3 --version` outputs with the
campaign and recheck the upstream prerequisites before use. A typical
administrative sequence is:

```bash
az keyvault key create \
  --hsm-name "$HSM_NAME" \
  --name sparkinterval-receipt-2026 \
  --kty RSA-HSM \
  --size 3072 \
  --ops sign verify

# Read the immutable version from the create/show result, then use it below.
KEY_URI="https://${HSM_NAME}.managedhsm.azure.net/keys/sparkinterval-receipt-2026/${KEY_VERSION}"

az keyvault key download \
  --id "$KEY_URI" \
  --encoding PEM \
  --file sparkinterval-receipt-2026-public.pem

sha256sum sparkinterval-receipt-2026-public.pem

az keyvault key get-attestation \
  --id "$KEY_URI" \
  --file sparkinterval-receipt-2026-key-attestation.json
```

Validate and retain the key-attestation package using Microsoft's current
Managed HSM key-attestation procedure. The package is audit evidence for the
origin and protection of the signing key; it is not embedded in every Lean
theorem. Record its digest, the exact versioned key URI, the downloaded public
key digest, Azure tenant/subscription/HSM identity, administrative approvals,
and the least-privilege signing role with the campaign record.

Add the public PEM and a `classification: "production"` entry to
[`profiles/verifier_keys/trusted_compute_keys.json`](../profiles/verifier_keys/trusted_compute_keys.json).
Its nonempty `allowed_verifier_profiles` must pin every approved exact backend,
target-profile SHA-256, trust-profile SHA-256, verifier-executable SHA-256, and
composite appraisal-policy SHA-256 tuple; no wildcard is accepted. Add the
identical classified tuples to the source-
reviewed allowlist in
[`TrustedComputeKey.lean`](../SparkInterval/Execution/TrustedComputeKey.lean).
Tests keep the JSON and Lean lists synchronized, and Lean admits only tuples
classified `production`. Both edits change the trusted receipt-admission
boundary and require the same review as adding a receipt to the Lean registry.
The checked-in bootstrap key is development-only; even an explicit
`--allow-development-key` can inspect its fixture but cannot generate an
accepted Lean consumer.

## Sign an appraised receipt

Pass each signer argument literally; no shell command string is evaluated:

```bash
python3 tools/trusted_compute_receipt.py issue \
  --bundle /returned/shard-000/run-bundle.json \
  --artifact-root /returned/shard-000 \
  --backend azure_ncc40ads_h100_v5 \
  --evidence-pack /returned/shard-000/azure-evidence \
  --evidence-verifier attestation/verify_azure_ncc_evidence.py \
  --evidence-policy /reviewed-policy/composite-policy.json \
  --retained-challenge /retained-off-vm/shard-000.challenge.json \
  --replay-db /retained-off-vm/issuer-state/spent-challenges.sqlite3 \
  --signer-command azure/managed_hsm_signer.py \
  --signer-arg=--key-uri \
  --signer-arg="$KEY_URI" \
  --signer-arg=--public-key \
  --signer-arg=/reviewed-keys/sparkinterval-receipt-2026-public.pem \
  --verifier-key-id sparkinterval-receipt-2026 \
  --public-key /reviewed-keys/sparkinterval-receipt-2026-public.pem \
  --out /returned/shard-000/trusted-compute-receipt.json
```

The issuer invokes `--signer-command` from a fresh mode-`0700` private
snapshot, with the executable mode `0500`, and drops inherited Python and ELF
loader injection variables. Only the explicit Azure identity/config variables
needed by the adapter are forwarded. This prevents a concurrent pathname swap;
it does not make the signer adapter, Python interpreter, Azure CLI, shared
libraries, or root store part of the receipt's verifier-artifact hash. Pin that
runtime through the measured issuer image/container and retain its provenance.
The exact returned signature is still independently verified against the
source-approved public key before the receipt is installed.

The receipt's validity interval comes from the independently verified
attestation evidence. Operators cannot extend it with command-line timestamp
arguments. Before appraisal the issuer atomically burns the exact challenge in
the required durable replay ledger. Failure remains spent. It installs the
receipt at a fresh no-overwrite path with an fsync before marking that ledger
row signed. Before a receipt enters Lean, the registry generator re-parses
canonical JSON, resolves the key through the source manifest, verifies the
public-key file digest, exact backend/target-profile/trust-profile/verifier/
policy tuple, and RSA signature,
checks admission time, rejects duplicate run/challenge/binding identities, and
emits an exact closed source entry.

## What the HSM signature establishes

The signature authenticates the relying party's appraisal and protects every
field in the compact receipt from alteration. Managed HSM key attestation can
add evidence that the signing key was generated and protected by the expected
HSM. Neither fact independently proves that arbitrary user-space code caused
the output. That residual requires the reviewed measured-runner policy and is
named explicitly by SparkInterval's single accepted-run axiom. Ordinary Lean
theorems then derive the mathematical result from the closed registered
algorithm semantics; the signer cannot choose an arbitrary proposition.

Microsoft's current command references are:

- [Managed HSM key creation, download, signing, and attestation CLI](https://learn.microsoft.com/en-us/cli/azure/keyvault/key?view=azure-cli-latest)
- [Managed HSM key-attestation validation](https://learn.microsoft.com/en-us/azure/key-vault/managed-hsm/key-attestation)

Recheck those primary sources and the installed Azure CLI version immediately
before a production campaign because cloud interfaces and attestation roots
can change.
