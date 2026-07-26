# Azure confidential H100 execution

This directory supplies a fail-closed deployment and evidence-collection path
for independent finite-computation shards on Azure's
`Standard_NCC40ads_H100_v5` confidential VM. It does **not** treat an Azure or
NVIDIA attestation token as a mathematical proof. The intended end state is:

```text
reviewed closed algorithm + exact input + exact output + fresh challenge
        |                         |
        +---- canonical run statement ----+
                                           |
                           SHA-256 statement digest
                                           |
             +-----------------------------+--------------------+
             |                             |                    |
       Azure MAA token              vTPM quote             NVIDIA EAT
       CPU/CVM claims          PCRs + qualifying data    GPU claims + nonce
             |                             |                    |
             +--------- independent relying-party verification-+
                                           |
                            signed acceptance certificate
                                           |
                              one explicit Lean trust axiom
```

The final arrow is a declared trust boundary. Attestation supplies evidence
about measured platform state and nonce freshness; it does not make a false
program correct, prove that arbitrary user-space code produced an output, or
replace review of the closed algorithm and its execution harness.

### Which signature attests the run

The hardware-associated run signature is the fresh **vTPM Attestation Key
(AK) quote**, not the later Managed HSM receipt signature. The measured path
has this exact order:

```text
retained off-VM challenge + job/artifact/policy/profile hashes
        -> start_binding -> reset/extend PCR 23 before execution
canonical statement (algorithm, input, parameters, executable, output)
        -> result_binding(challenge nonce, statement hash)
        -> extend PCR 23 after execution
certified Azure vTPM AK
        -> quote { qualifyingData = result_binding, final PCR 23 }
independent Azure/AMD/vTPM appraisal
        -> authenticate AK chain, quote signature, PCR equation, measured runner
optional NVIDIA appraisal
        -> authenticate an H100 EAT carrying the same result_binding
Managed HSM
        -> countersign the appraised evidence roots and closed claim
```

The AK may be a persistent certified vTPM key; freshness comes from the
off-VM challenge and therefore from the unique quote qualifying data. An
additional ephemeral guest signing key would add no execution assurance
unless its certification and access controls were themselves tied to the
same attested runner. The AK quote already supplies that authenticated
fresh-run binding.

This distinction is important but limited. A valid quote proves that the
certified vTPM signed the stated qualifying data and PCR state. It does not,
by itself, prove that the named program caused the output: sufficiently
privileged guest code could request a quote or extend an unrestricted PCR.
Production admission therefore also requires an immutable measured runner,
exclusive policy around PCR/key use, and an independent appraiser that
validates the executable closure and the ordered start-to-result transcript.
The Managed HSM is a relying-party approval and audit signature over that
appraisal; it is not substituted for the enclave-associated quote.

> **Certificate-path warning.** The certificate-capable execution protocol is
> the challenge-first, no-second-reset path in
> [AZURE_MEASURED_RUNNER.md](AZURE_MEASURED_RUNNER.md). The older
> `collect_azure_ncc_evidence.py` workflow described below is retained only for
> deployment diagnostics and compatibility tests. Because it resets PCR 23
> after the workload, it cannot prove the ordered `zero -> start -> result`
> chain and is structurally inadmissible to the command-line verifier and
> receipt issuer. Do not use the legacy collector for a Lean-bound receipt.

For the end-to-end stateful production sequence, including the exact private
image/config contract, challenge TTL and sharding rule, authenticated manual
ingress/egress gates, Managed HSM issuance, and review-only Lean source output,
use the [Azure H100 production operator runbook](AZURE_H100_PRODUCTION_OPERATOR.md).

## Platform contract

Microsoft documents this size as one 94 GB NVIDIA H100, 40 non-SMT AMD EPYC
Genoa cores, and 320 GiB RAM. Its TEE combines AMD SEV-SNP on the CPU side
with H100 confidential computing on the GPU side. The current Azure onboarding
repository lists `eastus2`, `centralus`, and `westeurope` and provides an
Ubuntu 22.04 confidential-GPU community image with the CPU/GPU setup tools.

The operational consequences are:

- one shard gets one VM and one H100; independent VMs provide horizontal
  sharding, not a claimed confidential multi-GPU fabric;
- every shard gets a distinct externally generated challenge and evidence
  package;
- 40 family vCPUs and 40 total regional vCPUs are needed per shard;
- quota does not reserve physical capacity, so `SkuNotAvailable` at allocation
  time remains possible;
- the deployment resolves the official community image's mutable `latest`
  reference to an exact version ID before VM creation; retain that ID in the
  campaign record; custom images are accepted only as an exact numeric-version
  marketplace URN or a Compute/Community Gallery `/versions/<major.minor.patch>`
  resource ID; and
- the VM has no public IP. The required existing subnet must already have a
  reviewed NSG, `defaultOutboundAccess: false`, an explicit NAT gateway or
  route table for controlled MAA/NRAS egress, a private artifact path, and
  Azure Bastion or control-plane access if interactive administration is
  unavoidable.

## 1. Create challenges outside Azure

Create challenges on the relying-party machine before any shard begins. Keep
the original directory outside the VM and incorporate the matching nonce in
the canonical run statement:

```bash
python3 azure/create_attestation_challenges.py \
  --campaign-id tg-2026-h100-01 \
  --count 8 \
  --ttl-seconds 86400 \
  --output-dir build/tg-2026-h100-01-challenges
```

The files are created atomically with mode `0600`; an existing output
directory is rejected. Each contains canonical whole-second `issued_at_utc`
and `expires_at_utc` values. TTL must be positive and cannot exceed seven days;
the 24-hour default should be shortened whenever the job permits. Collector
and independent verifier both reject future, expired, empty, or overlong
windows. The challenge is not a secret. Its integrity and freshness matter, so
the relying party must keep the exact canonical file outside every worker,
pass that off-VM file directly to the independent verifier and receipt issuer,
and enforce one-time use. Do not replace it with a challenge file returned by
the worker. The verifier requires the complete challenge object (campaign,
shard, nonce, issue time, expiry, kind, and version) to equal the retained
object; supplying only the expected nonce is intentionally insufficient.

## 2. Preflight quota and SKU visibility

Dry-run prints every read-only Azure CLI operation without requiring Azure
credentials:

```bash
python3 azure/ncc_h100.py preflight \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location eastus2 \
  --nodes 8 \
  --dry-run
```

Run the same command without `--dry-run` after `az login`. It rejects an
inactive subscription, malformed Azure response, an unavailable/restricted
exact SKU, a shape other than one GPU, 40 vCPUs, 320 GiB, and Generation 2,
and insufficient `Standard NCCads2023 Family vCPUs` or total regional vCPU
quota. If the live SKU API exposes a GPU/accelerator-memory capability, it must
equal 94 GB. Azure's current SKU response does not consistently expose that
field, so the report says whether it was available; the exact SKU identity and
Microsoft's size specification remain the check when it is omitted. Azure
documents quotas as limits rather than capacity guarantees; only VM allocation
tests capacity.

## 3. Deploy one confidential H100 per shard

Use a pre-existing private subnet. The default is platform-managed
`DiskWithVMGuestState` confidential disk encryption, Secure Boot, vTPM, SSH
key authentication, no NIC-level NSG, and no public IP. Passing `--nsg ""`
means the subnet NSG is the enforcement point. The deploy command queries the
subnet and rejects a missing NSG, default outbound access that is not
explicitly disabled, and the absence of both an explicit NAT gateway and a
reviewed route table. Review the actual NSG, firewall/NAT, DNS, and route rules;
the tool checks that enforcement resources exist, not that every rule is good.

```bash
python3 azure/ncc_h100.py deploy \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location eastus2 \
  --nodes 8 \
  --resource-group tg-h100-attested-01 \
  --name-prefix tg-h100 \
  --admin-username tgoperator \
  --ssh-key "$HOME/.ssh/tgoperator.pub" \
  --subnet-id "$PRIVATE_SUBNET_RESOURCE_ID" \
  --dry-run

# Review the JSON command plan, then remove --dry-run.
```

Creation is sequential so a partial capacity allocation names the exact failed
shard. The adapter does not trust the `az vm create` response. It reads each VM
and its one primary NIC back and requires provisioning success, the exact SKU
and pinned image, `ConfidentialVM`, Secure Boot, vTPM,
`DiskWithVMGuestState`, one private IPv4 address, and no public-IP resource.
A successful deployment still has `attestation_collected: false` and
`resources_proven_attested: 0`. Provisioning is not evidence of a run.

For production, copy a reviewed, content-addressed source/build closure over a
private channel. Record all executable, cubin/PTX/SASS, input, parameter,
output, and environment hashes in the normal run statement. Prefer an
immutable OS image plus dm-verity/IMA or an equivalently reviewed measured
launch policy. Secure Boot alone does not measure every user-space byte.

## 4. Legacy NVIDIA ready-state diagnostic

NVIDIA's current supported attestation client is the C++ NVAT SDK and its
`nvattest` CLI; the older Python SDK is deprecated. Before releasing inputs or
starting the finite computation, appraise the GPU with the campaign policy.
NVIDIA documents that successful attestation does not automatically put the
GPU in Ready state:

```bash
sudo nvattest --format json attest \
  --device gpu \
  --verifier local \
  --relying-party-policy attestation/policies/gpu_prover_h100.rego
sudo nvidia-smi conf-compute -srs 1
```

For a certificate-capable H100 run, use the measured runner's pinned
`gpu_pre_run_gate` command and retain its challenge/job-bound evidence. The
input-release controller must not release an input until that gate succeeds.
The standalone commands above are useful operator diagnostics, but their
terminal output is not a gate certificate. Post-run collection also queries
`nvidia-smi conf-compute -q` and fails unless `CC GPUs Ready State` is exactly
`Ready`. A production campaign should pin the NVAT release,
NVIDIA RIM/appraisal policy, accepted driver/VBIOS/firmware measurements,
certificate roots, and revocation policy.

## 5. Legacy post-run collection (diagnostic only)

The command in this section emits the legacy manifest and cannot enter the
receipt path. For the certificate-capable commands, job format, H100 gate, and
no-reset evidence handoff, follow
[AZURE_MEASURED_RUNNER.md](AZURE_MEASURED_RUNNER.md).

After the algorithm has durably produced and checked its exact output, build
the canonical run statement and compute its SHA-256. Copy only the shard's
challenge into the VM, then run:

```bash
sudo python3 attestation/collect_azure_ncc_evidence.py \
  --challenge /secure-input/shard-000.challenge.json \
  --backend azure_ncc40ads_h100_v5 \
  --statement-file /run/shard-000/statement.json \
  --statement-sha256 "$STATEMENT_SHA256" \
  --maa-attestation-url "$MAA_ATTESTATION_URL" \
  --output-dir /run/shard-000/azure-evidence
```

`MAA_ATTESTATION_URL` is required; there is no shared-provider default. It must
name the reviewed custom provider's exact HTTPS endpoint:

```text
https://<provider>.<region>.attest.azure.net/attest/SevSnpVm?api-version=2022-08-01
```

The endpoint is retained in `maa_config.json` and the evidence manifest. The
independent policy separately pins that URL plus the one accepted token issuer,
audience, and `maa_snp` provider identity. Collection from an endpoint does not
authorize or authenticate it.

The statement file must be canonical JSON when supplied. The collector derives
exactly:

```text
binding_nonce = SHA256(UTF8(
  "sparkinterval.trusted-compute.result-binding.v1\n" ||
  "start_challenge_sha256=" || start_challenge || "\n" ||
  "wire_statement_sha256=" || statement_sha256 || "\n"))
```

It then requires and retains all of the following:

1. exactly one visible H100 with compute capability 9.0, CC mode `ON`, CC
   environment `PRODUCTION`, and CC GPUs Ready State `Ready`;
2. an Azure CVM **guest** attestation through the official
   `/usr/local/lib/cvm-attestation/attest` adapter, with the start challenge,
   statement digest, and binding nonce placed in MAA user claims;
3. the MAA compact JWS, HCL/SEV report, runtime data, and the exact SHA-512
   user-claims digest reported by the adapter;
4. raw NVIDIA evidence collected with `binding_nonce`, then appraised by the
   C++ `nvattest` CLI with the checked-in Rego policy;
5. a detached NVIDIA EAT whose claims report secure boot, disabled debug, and
   nonce matching;
6. a fail-closed **post-work** reset of SHA-256 PCR 23, a read proving its value is exactly
   32 zero bytes, extension with the 32 binding bytes, and a second read proving
   exactly `SHA256(00^32 || bytes(binding_nonce))`, followed by a quote over
   PCRs `0-7,23` whose `qualifyingData` is the same binding;
7. a successful local `tpm2_checkquote`, the vTPM AK public key/certificate,
   Azure HCL report/runtime indexes, PCR bytes, and the TCG event log (absence
   of the event log is fatal for certificate-capable collection); and
8. a canonical manifest containing SHA-256 and length of every retained
   artifact.

Both raw `pcr23.before.bin` and `pcr23.after.bin` are retained. Measured-boot
event-log replay covers the boot PCRs; it does not explain a manual post-boot
PCR 23 extension. Consequently the independent appraiser must separately prove
that the signed quote selected PCR 23 and that its value is the exact extend
formula above.

This post-work reset is precisely why the legacy evidence is diagnostic: it
does not commit to the challenge before execution and it destroys any prior
execution chain. The command-line verifier accepts only the measured-runner
manifest produced by `collect_azure_measured_evidence.py`; its private
test-only legacy hook is not exposed by the CLI or receipt issuer.

The output directory is atomically renamed into place only after every
collection consistency check passes. Missing commands, tokens, evidence,
expected claims, or mismatched nonces are fatal. Collector output marked
`evidence_collected: true, accepted: false` means only that a complete pending
evidence package was retained; it is not an evidence appraisal or a
run-acceptance certificate. `--dry-run` performs no device or cloud operation
and emits both fields false.

For NVIDIA remote appraisal, add `--gpu-verifier remote` and provide
`NV_ATTESTATION_SERVICE_KEY` out of band. Never put that key in a run bundle,
command line, log, repository, or VM image.

## 6. Independent verification and certificate issuance

The certificate-capable adapter deliberately writes
`status: measured_evidence_collected_pending_independent_verification`. A verifier
outside the worker VM must fail closed unless it independently checks:

- canonical statement and artifact hashes, completion counts, exact challenge,
  expiry, and shard assignment against the exact canonical challenge file
  retained off the worker;
- the MAA JWS signature against the issuer's current pinned/authorized signing
  keys, exact custom-provider endpoint, issuer, audience, provider identity,
  validity interval, policy hash, SEV-SNP compliance, Secure Boot, vTPM,
  non-debug state, and the user-claims/report-data binding;
- the vTPM AK certificate/root binding, quote signature, qualifying data, PCR
  selection and values, measured-boot/runtime event-log replay, and the
  separate PCR 23 zero-to-binding extend equation;
- the NVIDIA certificate chain, revocation status, RIM measurements, policy,
  EAT signature, H100 production/debug/security state, and exact nonce;
- the CPU/GPU evidence describes the same VM/shard and falls within the
  challenge's authorized time window; the normalized appraisal interval is
  intersected with the challenge's expiry; and
- the measured runner policy is strong enough to justify the statement
  “this closed invocation returned this exact output.” A bare PCR extension by
  a root process only proves that the vTPM signed an extension chain; it is not
  proof that the named program caused the value.

One-time use is enforced by the receipt issuer's required `--replay-db`. It
requires an issuer-owned, non-symlink parent with exact mode `0700` and an
issuer-owned regular database with exact mode `0600` and exactly one hard
link. The issuer retains the securely opened file descriptor while SQLite
opens the pathname and rejects an owner, mode, link-count, device, or inode
change. It then takes a `BEGIN IMMEDIATE` transaction and atomically inserts
the nonce together with the exact retained challenge hash, wire-statement hash,
and backend before invoking the appraiser or signer. Any prior row is fatal,
including a prior failed/interrupted attempt. After the receipt is installed
durably at a fresh no-overwrite path, the row transitions from `reserved` to
`signed` with the receipt hash.

These checks do **not** turn local SQLite into a rollback-resistant or global
consensus ledger. Restoring an old filesystem/database snapshot can erase a
spent challenge, and issuers pointed at different databases can each accept
the same challenge. A production service must use one isolated relying-party
identity and one strongly consistent durable ledger for the whole campaign,
with an externally anchored append-only audit sequence or HSM signing policy
when rollback resistance is required. Backups are necessary for availability
but do not themselves detect rollback. Root or another process running as the
issuer UID remains inside this filesystem trust boundary.

`attestation/verify_azure_ncc_evidence.py` implements the relying-party
adapter expected by `tools/trusted_compute_receipt.py`. It does not trust the
collector's local booleans. It first recomputes the complete artifact closure,
the exact challenge/statement result binding, MAA user-claims digest, TPM quote
component manifest, and every retained artifact hash. It then executes:

- a separately supplied Azure SEV-SNP/vTPM cryptographic appraiser; and
- for H100 runs, a separately supplied C++ `nvattest` executable over the raw
  retained GPU evidence and the exact result-binding nonce.

Both executables and both appraisal-policy files are SHA-256 pinned by a
canonical policy matching
`schemas/azure-evidence-appraisal-policy.schema.json`. Relative paths resolve
beside the composite policy. A CPU policy must set `nvidia_appraiser` to
`null`; an H100 policy must provide it. Example shape:

```json
{
  "allowed_backends": ["azure_ncc40ads_h100_v5"],
  "azure_appraiser": {
    "executable_path": "azure-sevsnp-vtpm-appraiser",
    "executable_sha256": "<64 lowercase hex>",
    "maa_attestation_url": "https://<provider>.<region>.attest.azure.net/attest/SevSnpVm?api-version=2022-08-01",
    "maa_accepted_issuer": "https://<provider>.<region>.attest.azure.net",
    "maa_accepted_audience": "<exact approved aud claim>",
    "maa_accepted_provider": "maa_snp",
    "policy_path": "azure-production-policy.json",
    "policy_sha256": "<64 lowercase hex>",
    "timeout_seconds": 600
  },
  "kind": "sparkinterval_azure_evidence_appraisal_policy",
  "nvidia_appraiser": {
    "executable_path": "nvattest",
    "executable_sha256": "<64 lowercase hex>",
    "nras_url": "https://nras.attestation.nvidia.com",
    "policy_path": "nvidia-production-policy.rego",
    "policy_sha256": "<64 lowercase hex>",
    "timeout_seconds": 600,
    "verifier": "local"
  },
  "schema_version": 1
}
```

Do not check in a machine-specific production policy. Retain the exact policy,
appraiser binaries, their provenance/signatures, and their hashes with the
campaign audit record.

Before any appraiser is invoked, the adapter copies the retained challenge,
canonical evidence manifest and its complete manifest-selected artifact
closure, composite policy, appraiser executables, and appraiser policies
through `O_NOFOLLOW` file descriptors into a fresh mode-`0700` private
directory. Data files are mode `0400` and executables are mode `0500`. All
parsing, hashing, and subprocess arguments after that point use only these
snapshots. Replacing an original pathname during appraisal therefore cannot
change the bytes being appraised. The receipt issuer independently snapshots
its verifier entry point, policy, and retained challenge in the same way; the
external Managed HSM signer adapter is also invoked from a private executable
snapshot.

The Azure appraiser is invoked as a live process with explicit paths for the
MAA compact JWS, raw SNP report/runtime data, HCL report/runtime data, vTPM AK
public key/certificate, quote message/signature/PCRs, event log, and the raw PCR
23 before/after values. It also receives the pinned Azure policy, exact MAA
endpoint/issuer/audience/provider, expected binding, and expected user-claims
SHA-512. In H100 mode it additionally receives the explicit backend and paths
to the retained raw NVIDIA evidence, detached EAT, and collector appraisal so
that a composite appraiser can evaluate their relationship to the CVM; none of
those retained files is trusted merely because the collector wrote it. It must
cryptographically verify the MAA signature/time/policy, AMD
SEV-SNP and runtime-data binding, AK chain, TPM quote signature and qualifying
data, boot event-log/PCR replay, and that the quote's selected PCR 23 equals the
specified zero-to-binding extend. It must also return
`measured_runner_policy_valid: true` and
`result_artifact_bound_to_execution: true`. An H100 appraisal must return
`accelerator_attestation_bound_to_cvm: true`; CPU-only appraisal must return
the literal `"not_applicable"` for that claim. It must return
`pcr23_binding_valid: true`; the normalizer also recomputes the equation before
invoking it. Its exact JSON output contract is defined by
`AZURE_APPRAISAL_KEYS` and `AZURE_CLAIM_KEYS` in the verifier; any missing,
extra, false, or hash-mismatched field is fatal. This deliberately leaves
vendor/root-store implementation outside the small normalizer instead of
pretending Python structure checks verify those cryptographic chains.

Security-sensitive subprocesses receive a small deterministic environment:
fixed system `PATH`, UTC/C locale, user-site Python disabled, and no inherited
`PYTHONPATH`, `PYTHONHOME`, `LD_PRELOAD`, or `LD_LIBRARY_PATH`. The NVIDIA
service key is forwarded only for an explicitly configured remote NVIDIA
appraisal. The Managed HSM signer receives only the named Azure identity/config
variables needed by its adapter. Production images must still pin the Python
interpreter, standard library, ELF loader/shared libraries, CA/root stores,
vendor tools, and every appraiser dependency. The verifier source pins its
local collector-module hash, but the existing single verifier-artifact receipt
field does not commit this entire runtime closure. Use an immutable measured
image/container or introduce and source-approve a canonical closure-manifest
ABI before treating that wider closure as cryptographically pinned.

The test suite supplies a fake appraiser only to exercise this fail-closed
ABI. No production SEV-SNP/vTPM/composite appraiser or accepted root policy is
checked in. In particular, the currently collected vendor evidence may not by
itself establish that the GPU evidence came from the same CVM or that the
measured runner caused the exact output. Unless the measured protocol and a
reviewed appraiser can establish all three claims above, production receipt
issuance remains blocked. The verifier rehashes the composite policy and each
pinned private executable/policy snapshot after the appraisers return,
rejecting mutation of the actual bytes used rather than relying on a
before/after check of attacker-controlled source pathnames.

Run the independent adapter directly before issuance:

```bash
attestation/verify_azure_ncc_evidence.py \
  --evidence-pack /returned/shard-000/azure-evidence \
  --policy /reviewed-policy/composite-policy.json \
  --backend azure_ncc40ads_h100_v5 \
  --expected-challenge-file /retained-off-vm/shard-000.challenge.json \
  --expected-start-challenge-sha256 "$START_CHALLENGE" \
  --expected-result-binding-sha256 "$RESULT_BINDING"
```

It emits only the normalized contract consumed by the receipt tool:

```text
schema_version, kind=sparkinterval_evidence_appraisal, accepted=true,
backend, start_challenge_sha256, result_binding_sha256, policy_sha256,
appraised_at_utc, not_before_utc, not_after_utc,
evidence_hashes={platform, MAA, SNP, TPM quote, event log, EAT, GPU evidence}
```

For CPU-only evidence, both NVIDIA hashes are the fixed project
not-applicable digest. For H100 evidence they must be real, non-placeholder
hashes, and the retained detached EAT must be structurally identical to the
detached EAT returned by the freshly invoked pinned `nvattest` appraiser. The
receipt issuer passes private snapshots of the exact retained off-VM challenge
and policy into a private snapshot of this verifier, burns the challenge in the
replay ledger, and rehashes the snapshots after invocation before signing. It
rechecks all keys, bindings, policy hash, time interval, and evidence hashes. A
non-bootstrap verifier key ID also requires an explicit public-key file; it
cannot silently fall back to the checked-in bootstrap key, and production key
IDs cannot use the development PEM-signing mode.

Only that relying party should issue the signed acceptance certificate which
the Lean-side checker consumes. The project may choose one explicit axiom that
maps a fully checked certificate for a registered closed invocation to its
formal outcome. The axiom must name this residual physical/cryptographic trust;
neither this collector nor Azure attestation removes it. See
[Azure Managed HSM receipt signing](AZURE_MANAGED_HSM_SIGNING.md) for the
separate key provisioning and signing procedure.

### What one signed receipt binds

The RSA signature covers a domain-separated commitment to the following
identities. “Transitive” means that the signed receipt contains the hash of a
canonical record whose validated contents contain the named value.

| Required identity | Receipt binding | Audit qualification |
| --- | --- | --- |
| Mathematical/source claim ID | Transitive through `claim.input_hash` when the exact input is a reviewed numeric-corpus pin; otherwise through the closed registered invocation selected by the exact algorithm/input/result tuple | Use `verify --numeric-corpus-pin` for corpus-backed runs. A free-form `algorithm_id` is not by itself a mathematical theorem. |
| Numeric input corpus | Transitive from `claim.input_hash` to the canonical pin, then to manifest SHA-256, exact Git commit, payload root, source root, file hashes, and logical ranges | The measured workload must actually verify/consume those references; the pin alone proves identity, not use. |
| Algorithm definition and source | Direct `algorithm_hash` plus `source_tree_hash`; the signed run/wire hashes also bind the source-reviewed job and artifact closure | Source-to-binary compilation correctness remains within the one accepted-run trust boundary. |
| Executable binary/image | Direct `host_executable_hash`, `device_cubin_hash`, and `kernel_manifest_hash` | CPU receipts require the device hash to be the fixed not-applicable digest; H100 receipts require a real device image. |
| Parameters and domain | Direct `parameters_hash` and `domain_hash`; exact values remain in the hashed canonical run bundle | Retain the run bundle so a reviewer can reconstruct the values rather than seeing only digests. |
| Output/final state | Direct exact UTF-8 `result` plus `output_hash`; validation recomputes their equality | A campaign needing more state must make its terminal state/receipt tree part of that canonical output or registered result semantics. |
| Nonce and run identity | Direct unpredictable `nonce`; transitive job/campaign/shard IDs through the retained challenge, job-spec hash, wire statement, run-bundle hash, and platform evidence manifest | `run_bundle_sha256` is the compact per-run identity; retain the challenge/job/run bundle for human-readable IDs. |
| Verifier | Direct `verifier_policy_sha256`, `verifier_artifact_sha256`, validity interval, and key ID | The entry point source-pins its imported verifier modules. Interpreter, libraries, vendor tools, and root stores require a measured/pinned issuer/appraiser image. |
| Platform measurements | Direct hashes of the complete platform-evidence manifest, MAA token, SNP report, TPM quote record, event log, NVIDIA EAT, and raw NVIDIA evidence | Actual PCR/measurement values and their certificate paths live in the retained hash-closed evidence pack and are independently appraised under the signed policy hash. |
| Receipt signature/key | Direct RSA-3072 signature and source-approved key ID/public-key digest at registry import | The immutable Managed HSM key URI, HSM key-attestation package, administrative roles, and its vendor verification record are campaign-level external provisioning, not repeated in receipt v1. |
| Vendor signature chains | Transitive through the retained evidence-manifest/token/EAT/AK-certificate hashes after pinned appraisers validate them | CA roots, revocation state, NRAS/MAA availability, and appraiser root-store closure remain externally provisioned and must be archived/reviewed. |

Changing any directly or transitively bound byte changes a signed digest and
invalidates either the receipt signature, the independent evidence appraisal,
or the closed Lean registry/invocation match. This relies on SHA-256
collision/second-preimage resistance and the signing key/appraiser trust
named by the sole accepted-run axiom; it is not a proof of those cryptographic
assumptions inside Lean.

## CPU-only finite jobs

`Standard_NCC40ads_H100_v5` also offers 40 confidential CPU cores, and the
collector supports CPU/FLINT sidecars with:

```bash
sudo python3 attestation/collect_azure_ncc_evidence.py \
  --backend azure_sevsnp_cpu \
  --challenge /secure-input/shard-000.challenge.json \
  --statement-file /run/shard-000/statement.json \
  --statement-sha256 "$STATEMENT_SHA256" \
  --maa-attestation-url "$MAA_ATTESTATION_URL" \
  --output-dir /run/shard-000/azure-cpu-evidence
```

CPU mode collects the Azure CVM/MAA/vTPM half of the same binding and neither
requires nor permits NVIDIA evidence during independent appraisal. It retains
the same challenge, statement, MAA, vTPM quote, measured-runner, event-log, and
replay requirements.

## Performance and scaling notes

- Exhaustive finite scans belong on Azure in the production workflow. A local
  machine needs only compilation/hash generation, small known-answer and
  sampling tests, receipt/evidence appraisal, and the final Lean
  registry/consumer check. Source-scale independent replay belongs on a
  separately measured cloud verifier. Optional archival review may stream
  artifact hashes locally, but ordinary local verification neither regenerates
  nor arithmetically replays a production certificate.
- Use one process/shard per VM for GPU kernels. Do not ask a shard to infer a
  second H100; the SKU has exactly one.
- Use the 40 CPU cores for exact parsing, FLINT/Arb validation, output hashing,
  and independent CPU sidecars. Reserve memory explicitly; the VM has 320 GiB.
- Keep output and checkpoint formats deterministic. Attestation overhead is
  normally small compared with long finite scans, but remote NRAS/MAA and OCSP
  availability must be budgeted at the final evidence step.
- Benchmark kernel/chunk size on a DGX Spark only for performance tuning. Its
  different GPU/host architecture and local-unattested status cannot predict
  H100 confidential-mode throughput exactly and cannot substitute for the
  Azure evidence run.
- Parallel independent VMs require quota and available capacity for
  `40 * shard_count` family and regional vCPUs. Plan retryable allocation and
  checkpointing, but never reuse a completed challenge after an ambiguous
  failure.

## Official sources

- [Azure confidential GPU options](https://learn.microsoft.com/en-us/azure/confidential-computing/gpu-options)
- [NCCads H100 v5 size specification](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nccadsh100v5-series)
- [Azure confidential-GPU onboarding repository](https://github.com/Azure/az-cgpu-onboarding)
- [Azure VMI command-line deployment](https://github.com/Azure/az-cgpu-onboarding/blob/main/docs/Confidential-GPU-H100-VMI-Creation-CLI.md)
- [Azure VM model/instance readback contract](https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/get)
- [`az network nic show` readback command](https://learn.microsoft.com/en-us/cli/azure/network/nic#az-network-nic-show)
- [Azure SNP guest-attestation verification](https://github.com/Azure/az-cgpu-onboarding/blob/main/docs/SNP-Guest-Attestation-Verification.md)
- [Azure CVM attestation tools](https://github.com/Azure/cvm-attestation-tools)
- [Azure CVM guest-attestation design](https://learn.microsoft.com/en-us/azure/confidential-computing/guest-attestation-confidential-virtual-machines-design)
- [Azure vTPM quote and PCR guidance](https://learn.microsoft.com/en-us/azure/confidential-computing/how-to-leverage-virtual-tpms-in-azure-confidential-vms)
- [`tpm2_pcrreset` command contract](https://tpm2-tools.readthedocs.io/en/latest/man/tpm2_pcrreset.1/)
- [`tpm2_pcrread` output-format contract](https://tpm2-tools.readthedocs.io/en/latest/man/tpm2_pcrread.1/)
- [Azure default outbound access and private subnets](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access)
- [Azure outbound-egress design guidance](https://learn.microsoft.com/en-us/azure/networking/design-guide/outbound-egress)
- [Microsoft Azure Attestation overview](https://learn.microsoft.com/en-us/azure/attestation/overview)
- [NVIDIA C++ Attestation SDK / `nvattest`](https://docs.nvidia.com/attestation/nv-attestation-sdk-cpp/latest/overview.html)
- [NVIDIA `nvattest` command reference](https://docs.nvidia.com/attestation/nv-attestation-sdk-cpp/latest/sdk-cli/command-reference.html)
- [NVIDIA Hopper single-GPU attestation example](https://docs.nvidia.com/attestation/quick-start-guide/latest/attestation-examples/hopper_single_gpu.html)

Cloud and attestation interfaces change. Recheck the linked primary sources,
region availability, image version, driver/NVAT compatibility matrix, and
claim names immediately before a production run.
