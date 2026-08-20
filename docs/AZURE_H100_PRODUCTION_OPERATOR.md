# Azure H100 production operator

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../attestation/phala/README.md`](../attestation/phala/README.md).

`azure/h100_production_orchestrator.py` is the fail-closed state machine for
one certificate-capable run on one private
`Standard_NCC40ads_H100_v5` VM. It composes the measured runner, the
challenge-first/no-reset evidence collector, independent off-VM appraisal,
versioned Azure Managed HSM signing, replay protection, and generation of Lean
source **candidates**. It never admits a receipt to the live source registry,
edits a Lean trust pin, or reports theorem acceptance.

Start from the canonical redacted
[campaign example](../examples/trusted-compute/azure_h100_production_campaign.redacted.json)
and its [closed JSON schema](../schemas/azure-h100-production-campaign.schema.json).
The example is structural documentation: every `REPLACE` value, zero digest,
zero size, path, key identity, and policy identity must be replaced. A real
config is accepted only when it is canonical JSON and every operator-side file
matches its declared SHA-256 and byte length.

The packed Dirichlet producer has its own schema-valid site shape at
[`azure_h100_dirichlet_packed_materializer_site.redacted.json`](../examples/trusted-compute/azure_h100_dirichlet_packed_materializer_site.redacted.json).
It is documentation, not a runnable configuration: every zero digest and
placeholder path must be replaced by the exact reviewed artifact before the
materializer will emit a production campaign.

## Production prerequisites and current blockers

The repository supplies the protocol and operator state machine, but it does
not supply or pretend to supply these deployment-specific authorities:

- an exact private Azure Compute Gallery H100 image version containing the
  reviewed worker closure, Azure guest-attestation client at
  `/usr/local/lib/cvm-attestation/attest`, `nvattest`, `nvidia-smi`, TPM tools,
  and NVIDIA CC drivers;
- a reviewed production measured-runner policy bound to that image, a
  production transcript policy bound to the exact job/runner/target/trust
  digests, and a fail-closed NVIDIA production policy. The checked-in baseline
  Rego policy is development-only and is rejected;
- production Azure SEV-SNP/vTPM and NVIDIA appraiser executables, their exact
  policies/root material, and a composite appraisal policy pinning all four
  files plus the MAA/NRAS endpoints;
- a provisioned MAA provider and private NCC subnet with reviewed NSG and
  controlled egress, Azure quota/capacity, and an operator identity allowed to
  create the VM;
- a production Managed HSM RSA-3072 key, immutable key-version URI, reviewed
  public key, production key manifest entry, Managed HSM authorization, and a
  durable issuer-owned replay database;
- an authenticated private transport for worker ingress and certificate
  egress. The repository does not choose Bastion, private Blob/Private Link,
  an enterprise transfer service, or a secure input-release service on the
  operator's behalf; and
- a source-reviewed closed Lean invocation for the computation. The catalog now
  contains exact source-defined invocations for the tutorial/pilot and all
  eleven ternary-Goldbach physical campaigns. Registration alone is not a
  source-realization proof: only CDEM is enabled in the semantic inventory,
  the live receipt registry remains empty, and every other campaign still
  needs reviewed semantic admission before a receipt can be converted into its
  mathematical theorem.

The PT21 source path now has strict `sm_90` build targets for the authenticated
Gamma consumer, persistent DD accumulator, DD transform, partial fused source
worker, and three-stream event scanner.  These targets reject a non-H100
device at runtime.  They are not yet a production PT21 job: real source output
still contains sign-ambiguous cells, and adaptive sign/stationary resolution,
Hardy-Z realization, analytic Turing bounds, compact artifact emission, and a
full H100 calibration remain open.  Do not package the partial fused worker as
the registered PT21 invocation.

The orchestrator stops at the two transport boundaries. It records an explicit
operator staging confirmation before the guest may run and requires the exact
returned archive plus completion manifest before appraisal. Those declarations
do not make an unauthenticated copy secure. Select and audit the transport,
compare the configured hashes at both ends, retain its audit record, and never
put `NV_ATTESTATION_SERVICE_KEY` or Azure credentials in the config, image,
archive, command line, or repository.

Operator-side child environments are capability-scoped. Azure CLI and managed
identity variables are forwarded only to the exact deployment adapter and
receipt issuer/HSM signer path; independent transcript verifiers, hardware
appraisers, collectors, and Lean source generators receive neither Azure
identity material nor the operator's `HOME`/`PATH`.

## Prepare one immutable campaign

Use absolute paths. Operator outputs must be distinct paths below
`outputs.review_root`; the orchestrator rejects the live Lean key, registry,
and key-manifest paths as outputs. The image must be an exact numeric version
in a **private** Compute Gallery and the image, subnet, and selected
subscription must agree. The Managed HSM URI must include its immutable
32-hex-character key version.

The workload archive is an exact pinned input. On the guest, the orchestrator
refuses a pre-existing `worker.artifact_root` and safely extracts the archive
itself, then the measured runner rechecks the job's complete artifact closure.
When `lean_review.registered_invocation` is non-null, the operator resolves it
through the closed source generator and requires an H100 backend plus exact
agreement of the job's algorithm ID/definition hash, input hash, parameter
hash, and domain hash. A null value denotes an operational DAG receipt: it is
still attested and signed, but cannot generate a registry or Lean review
candidate. Result/output hashes are checked after execution, when they exist.
Create the archive with `attestation.measured_run_archive.create_archive`, or
an equivalently reviewed build step that emits that deterministic, link-free
tar format. Do not manually expand an unrelated tree on the worker.

Choose `challenge_ttl_seconds` conservatively. It is at most seven days and
must be strictly greater than:

```text
job command timeout + H100 pre-run gate timeout + 10,800 seconds
```

The final three hours cover post-run quote/evidence work and operational
overhead. Immediately before execution, the guest recomputes the remaining
window and refuses to start unless the same complete-shard budget remains.
Time spent staging consumes the window. If one shard cannot reliably finish
inside seven days, reduce the shard size; do not lengthen or reuse a challenge.
Parallel shards use separate canonical configs, campaign IDs, challenges,
state/output paths, VMs, and worker paths. They may share only the deliberately
centralized, strongly protected replay service/database and reviewed policy
inputs.

`challenge.mode` is either `operator_generated_fresh_v1` with `pin:null` and
shard index zero, or `pinned_portfolio_handoff_v1` with the exact canonical
portfolio challenge file pin and its actual shard index. The latter is copied
into a fresh operator-owned directory; it is never regenerated.

## Review the plan before any cloud mutation

Set the path to the final canonical config:

```bash
CONFIG=/srv/sparkinterval-operator/campaign.json

python3 azure/h100_production_orchestrator.py validate "$CONFIG"
python3 azure/h100_production_orchestrator.py plan "$CONFIG" \
  > /srv/sparkinterval-operator/plan.json
```

Both commands emit `accepted:false`. `plan` contains only argv arrays (never a
shell command), the TTL contract, every state-machine action, and all three
manual review boundaries. Inspect it, the pinned file hashes, exact image and
subnet, guest paths, appraiser endpoints, key version, replay path, and source
candidate paths. A plan is not an Azure preflight, evidence appraisal, receipt,
or theorem.

Initialization is idempotent for the exact unchanged config. Existing state is
revalidated and returned; existing outputs are never overwritten:

```bash
python3 azure/h100_production_orchestrator.py init "$CONFIG"
python3 azure/h100_production_orchestrator.py status "$CONFIG"
```

Every mutating operator command takes an advisory exclusive lock and makes an
atomic state transition. A cloud/signing action first enters an `in_progress`
state. Ambiguous failure enters a named `*_manual_reconciliation_required`
state instead of retrying a possibly completed side effect. Successful
`deploy`, `challenge`, stage acknowledgment, ingestion, appraisal, receipt,
and candidate-generation commands are also idempotent: they revalidate their
recorded artifact hashes before returning.

## Deploy and create the retained challenge

Authenticate the Azure CLI with the reviewed operator identity, then run:

```bash
python3 azure/h100_production_orchestrator.py deploy "$CONFIG"
python3 azure/h100_production_orchestrator.py challenge "$CONFIG"
```

Deployment rechecks the exact private subnet, SKU, image, ConfidentialVM,
Secure Boot, vTPM, disk security, private NIC, and absence of a public IP. The
In standalone mode the challenge is generated and retained on the operator
after deployment. In portfolio mode the exact already-pinned portfolio
challenge is adopted without changing its bytes. Neither is accepted from the
worker. Preserve the deployment and challenge records.

If deployment or challenge generation had an ambiguous exit, inspect Azure or
the retained challenge out of band and persist the exact canonical record at
its configured path. Then adopt it without re-running the side effect:

```bash
python3 azure/h100_production_orchestrator.py reconcile-deployment "$CONFIG"
python3 azure/h100_production_orchestrator.py reconcile-challenge "$CONFIG"
```

Each command is available only from its matching reconciliation state and
reapplies the full deployment or still-live challenge validator before
recording the artifact hash.

## Manual authenticated ingress and stage handoff

Through the reviewed private transport, place these exact bytes at the paths
declared under `worker`:

1. the canonical campaign config at an operator-chosen guest path;
2. `workload.package` at `worker.workload_package` (leave
   `worker.artifact_root` absent);
3. the retained challenge at `worker.challenge`;
4. `policies.nvidia` at `worker.nvidia_policy`; and
5. `policies.transcript_appraisal` at
   `worker.transcript_appraisal_policy`.

On the guest, compare SHA-256 and byte lengths to the config. Confirm the VM
identity/private address against the deployment record. Only after those
manual checks, record the assertion locally:

```bash
python3 azure/h100_production_orchestrator.py \
  record-worker-stage-handoff "$CONFIG" --confirm-exact-staging
```

Copy the newly created operator `handoffs.worker_stage_manifest` through the
same authenticated channel to `worker.stage_manifest`; compare its SHA-256 on
the guest. Then seal the operator transition:

```bash
python3 azure/h100_production_orchestrator.py ack-worker-stage "$CONFIG"
```

`record-worker-stage-handoff` is an explicit human assertion, not proof that a
copy command was secure. The orchestrator intentionally has no SSH/SCP command
and cannot make this assertion automatically.

## Run inside the measured H100 guest

Expose `NV_ATTESTATION_SERVICE_KEY` only in the root process environment if the
pinned NVIDIA policy selects remote NRAS appraisal. The orchestrator forwards
it in memory only to the exact measured runner (which forwards only to its
pre-run gate) and the exact remote evidence collector. It is absent from argv,
plans, state, manifests, and completion metadata.

Run from the reviewed repository/image installation, using the staged config:

```bash
sudo --preserve-env=NV_ATTESTATION_SERVICE_KEY /usr/bin/python3 \
  azure/h100_production_orchestrator.py \
  worker-run-local /srv/sparkinterval-worker/input/campaign.json
```

For local NVIDIA verification, omit `--preserve-env` entirely. Do not use
`sudo -E`: the orchestrator sanitizes child environments, but cannot undo a
loader or Python-path injection that affected its own interpreter startup.

The guest verifies the handoff, archive, job, and two policies; safely extracts
the workload; checks that enough challenge lifetime remains; runs the
challenge-first measured job; and invokes
`collect_azure_measured_evidence.py`. That collector uses the reviewed
in-image MAA client, `nvattest`, and `nvidia-smi`; it does **not** execute the
off-VM appraiser binaries. PCR 23 is not reset between runner and collector.
The command produces `worker.certificate_archive` and
`worker.completion_manifest`, both still pending independent appraisal.

## Manual authenticated return and independent appraisal

Return those two files through the reviewed egress channel to
`handoffs.returned_certificate_archive` and
`handoffs.returned_worker_completion`. Compare the completion-declared archive
hash and size before proceeding. The operator then performs safe extraction,
bundle verification, and an independent transcript replay:

```bash
python3 azure/h100_production_orchestrator.py ingest-returned "$CONFIG"
python3 azure/h100_production_orchestrator.py appraise "$CONFIG"
```

`appraise` invokes the separately pinned off-VM composite verifier and requires
authenticated MAA/SEV-SNP/vTPM and NVIDIA results for the exact retained
challenge and measured result binding. This is deliberately separate from the
guest collectors.

## Burn the challenge and sign with Managed HSM

Create the replay parent with its final issuer ownership and mode before the
run; do not place it on rollback-prone ephemeral worker storage:

```bash
install -d -m 0700 "$(dirname /srv/sparkinterval-operator/review/replay/trusted-compute.sqlite3)"
python3 azure/h100_production_orchestrator.py issue-receipt "$CONFIG"
```

The receipt issuer reserves the retained challenge in the replay database
before appraisal/signing. An interrupted attempt may have burned it, so it is
never retried automatically. If and only if a complete receipt was persisted,
adopt it with:

```bash
python3 azure/h100_production_orchestrator.py reconcile-receipt "$CONFIG"
```

That command independently verifies the signature under the pinned public
key, backend, HSM key ID, and canonical receipt identity. If no such receipt
exists or any check fails, treat the challenge as spent and start a fresh
campaign. The signer addresses the exact versioned Managed HSM key and the
receipt is verified against the pinned public key before installation.
Keep the replay database and its external audit/backup history after VM
cleanup.

## Generate review-only Lean sources

```bash
python3 azure/h100_production_orchestrator.py \
  generate-review-candidates "$CONFIG"
```

This writes fresh files only to `outputs.registry_candidate` and
`outputs.lean_candidate`, below the review root. It never edits
`TrustedComputeKey.lean`, `TrustedComputeRegistry.lean`, or the live key
manifest. Review the receipt, signature, exact registered invocation and
result, generated literals, verifier/key tuple, and `git diff` in a separate
source-admission change. Until that review is merged, the live trusted-compute
registry remains unchanged and Lean gains no theorem.

## Cleanup and ambiguous failures

Do not delete the VM until the archive and completion manifest have crossed the
authenticated return channel and their hashes are retained. When a dedicated
resource group is used, delete it through the reviewed Azure control-plane
procedure only after the run is either safely returned or formally abandoned.
Retain the operator state, plan, deployment record, off-VM challenge, policies,
appraiser binaries, image version, archive, reports, receipt, replay record,
HSM key-attestation review, transport logs, and cleanup record.

Never force the state file forward. For deployment, challenge, and receipt
ambiguities, use only the three exact reconciliation commands above; they
adopt persisted, independently checkable artifacts and never rerun the
external side effect. Other `*_manual_reconciliation_required` states have no
adoption command: preserve their partial artifacts for incident review and
create a new campaign with fresh paths and challenge. Treat an unknown
challenge/signature as spent. The orchestrator intentionally provides no
automatic rollback, VM deletion, registry admission, or live-trust update.
