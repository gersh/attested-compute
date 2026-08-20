# Azure SEV-SNP CPU production operator

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../attestation/phala/README.md`](../attestation/phala/README.md).

`azure/cpu_production_orchestrator.py` is the fail-closed state machine for
one measured CPU computation on one private Azure AMD SEV-SNP confidential
VM. It is a CPU-specific operator: its configuration has no NVIDIA policy,
endpoint, secret, command, or placeholder. The independent composite policy
must allow only `azure_sevsnp_cpu` and must set `nvidia_appraiser` to `null`.

Start with the redacted
[campaign example](../examples/trusted-compute/azure_cpu_production_campaign.redacted.json)
and the closed
[JSON schema](../schemas/azure-cpu-production-campaign.schema.json). A real
configuration must use canonical JSON. Every local workload, policy,
appraiser, public key, and manifest is pinned by SHA-256 and byte length.

The operator composes:

1. exact deployment and post-deployment inspection through
   `azure/cpu_cvm.py`;
2. an operator-retained challenge created before workload release;
3. `azure/measured_runner.py` and the ordered PCR 23
   `zero -> start -> result` protocol;
4. CPU-only MAA/SEV-SNP/vTPM collection and independent appraisal;
5. replay protection and a versioned Azure Managed HSM signature; and
6. generation of registry and Lean **review candidates**.

It never edits `TrustedComputeKey.lean`, `TrustedComputeRegistry.lean`, or the
tracked verifier-key manifest. Every successful CLI response remains
`accepted:false`; only later source review can admit a receipt.

## External production prerequisites

The repository does not supply these deployment authorities:

- Azure quota and capacity for exactly `Standard_EC96as_v6` or
  `Standard_DC96as_v6`;
- an exact numeric Ubuntu confidential-VM marketplace image or exact numeric
  Compute/Community Gallery image version containing the reviewed worker
  closure, TPM tools, and MAA guest client;
- an existing private subnet with subnet NSG, `defaultOutboundAccess=false`,
  and an explicit reviewed NAT gateway or route table;
- a production measured-runner policy bound to the exact image, a production
  transcript policy bound to the job/runner/target/trust hashes, and a
  CPU-only composite appraisal policy;
- independently reviewed Azure MAA/SEV-SNP/vTPM appraiser executable and
  policy/root material;
- a provisioned MAA provider and canonical `/attest/SevSnpVm` endpoint;
- a production RSA-3072 Managed HSM key, immutable key-version URI, reviewed
  public key and key-manifest tuple, HSM authorization, and durable replay DB;
- authenticated private ingress and egress for the two manual handoffs; and
- for a semantic terminal, a closed registered invocation supported by the
  Lean source generator. Operational dependency receipts intentionally use a
  null invocation and cannot generate Lean candidates.

The closed semantic CPU invocations used by current materializers are
`cdemTableAbelProductionV2`, `ch25PsiLemma92ProductionV1`,
`ch25A7BoundaryProductionV1`, `plattHead2e4ProductionV1`, and
`helfgottProp1224ProductionV1`. The latter four remain disabled in the
portfolio semantic inventory pending
source-semantics review and real retained runs.
The presence of the operator does not make other portfolio campaigns
registered or executable.

The first portfolio materializer is now
`tools/tg_azure_cpu_portfolio_materializer.py`, for the single terminal group
`cdem-table-abel::single-job`. Its caller supplies Azure, policy, key, and
fresh-path settings, but cannot supply a workload executable or command. The
closed factory selects four repository-pinned sources, the fixed system C++
compiler, static build argv, the producer, the independent 1,000-chunk
replayer, the measured supervisor/trace verifier, profiles, registered input,
output contract, and both measured argv arrays. It replaces the portfolio's
`${TG_REPOSITORY}`, `${TG_RUN_ROOT}`, `${TG_PYTHON}`, and `${TG_CXX}`
placeholders through an explicit reviewed mapping recorded in the plan.

The materializer emits a canonical measured job, deterministic workload
archive, job-specific transcript policy, CPU campaign config, and exact pins.
It then calls this operator's real `load_config`; a merely well-shaped JSON
file is not enough. The output still says `accepted:false`: no computation,
hardware appraisal, receipt, or Lean theorem exists until the later operator
stages finish. Psi now has its own phase-DAG materializer documented in
`algorithms/CH25_PSI_AZURE_MEASURED_DAG.md`. The Platt head through 20,000 has
one closed pinned-python-flint job documented in
`algorithms/PLATT_HEAD_AZURE_MEASURED_WORKLOAD.md`. The CH25 Lemma A.7
boundary has a separate closed pinned-artifact/python-flint job documented in
`algorithms/CH25_A7_AZURE_MEASURED_WORKLOAD.md`. Proposition 12.2.4 has a
12,930-logical-leaf, four-worker-group plus terminal source-built GMP/MPFR DAG documented in
`algorithms/PROP1224_AZURE_MEASURED_DAG.md`. Hurst has a separate closed
six-phase/644-job materializer documented in
`algorithms/HURST_AZURE_CPU_MATERIALIZER_DESIGN.md`. Every other unmatched CPU
phase remains unavailable until it receives a separate closed factory.

The finite Sqrt218 computation has a standalone source-closed measured job,
exact certificate producer, independent replay, numeric-corpus input binding,
and operational-state-machine/KAT manifests documented in
[`algorithms/SQRT218_AZURE_CPU_CERTIFICATE.md`](algorithms/SQRT218_AZURE_CPU_CERTIFICATE.md).
It is not yet an operator semantic terminal: no production corpus pin or
corpus-backed registered invocation exists. Its full scan is intended for the
Azure CPU path; local checks stop at the small KAT and structural tests.

## Exact configuration boundary

`azure.sku`, `azure.image`, `azure.subnet_id`, subscription, location, zone,
disk size, SSH public key, and one-node count are fixed before Azure is
contacted. `cpu_cvm.py` then rechecks the SKU's CPU/memory/GPU shape, quota,
private subnet, image, `ConfidentialVM`, Secure Boot, vTPM,
`DiskWithVMGuestState`, private NIC, and absence of a public IP.

For a semantic terminal, the selected `lean_review.registered_invocation` is
resolved before deployment. Its algorithm ID, algorithm-definition hash,
input hash, parameter hash, and domain hash must equal the measured job.
Operational phase configs may instead set it to `null`; those jobs are still
fully measured, appraised, signed, and portfolio-bound, but
`generate-review-candidates` rejects them. The job must use:

```text
backend:       azure_sevsnp_cpu
target:        azure_sevsnp_cpu
trust:         azure_sevsnp_hardware_attested
gpu gate:      null
input release: prepositioned_public_after_start
```

The challenge source is explicit. A standalone campaign uses
`operator_generated_fresh_v1`. A portfolio campaign uses
`pinned_portfolio_handoff_v1`, an exact file pin, and the original shard
index. In the latter mode the operator copies the canonical challenge bytes
into a fresh operator-owned directory and never invokes a second nonce
generator. Campaign ID, shard index, byte hash, size, and lifetime must all
agree; this is what lets the eventual receipt return to the originating
portfolio record.

The challenge lifetime is at most seven days and must be strictly greater
than the job timeout plus 10,800 seconds of evidence/operational margin. The
guest checks the remaining lifetime again before execution. Split a longer
computation into independently challenged shards; never extend or reuse a
challenge.

## Review and initialize

For the CDEM portfolio terminal, first prepare the shard through the portfolio
controller, copy and replace every placeholder in
[`azure_cpu_portfolio_materializer_site.redacted.json`](../examples/trusted-compute/azure_cpu_portfolio_materializer_site.redacted.json),
and review the non-executing plan. The completed site document must conform to
`schemas/azure-cpu-portfolio-materializer-site.schema.json`:

```bash
python3 tools/tg_azure_cpu_portfolio_materializer.py plan \
  /operator/portfolio-spec.json cdem-table-abel::single-job 0 \
  /operator/cpu-materializer-site.json

# Run this build on x86_64, matching the reviewed Azure CPU target.
python3 tools/tg_azure_cpu_portfolio_materializer.py materialize \
  /operator/portfolio-spec.json cdem-table-abel::single-job 0 \
  /operator/cpu-materializer-site.json
```

The build refuses the current aarch64 DGX Spark host rather than emitting an
x86 production-labeled package. Review `materialization-manifest.json` against
`schemas/azure-cpu-portfolio-materialization.schema.json`, then use its pinned
`cpu-campaign.json` as `CONFIG` below.

The CDEM job also declares the generic retained-artifact contract for
`work/cdem-abel-artifact.bin`. After ingestion, the exact file is at
`outputs.extracted_certificate_package/bundle-root/work/cdem-abel-artifact.bin`.
Its size and SHA-256 are recorded in the signed execution environment and
independently compared with the trace's `artifact_sha256`; preserve it with
the receipt for the Lean artifact handoff.

```bash
CONFIG=/srv/sparkinterval-operator/cpu-campaign.json

python3 azure/cpu_production_orchestrator.py validate "$CONFIG"
python3 azure/cpu_production_orchestrator.py plan "$CONFIG" > cpu-plan.json
python3 azure/cpu_production_orchestrator.py init "$CONFIG"
python3 azure/cpu_production_orchestrator.py status "$CONFIG"
```

The plan contains argv arrays, never shell strings. Inspect all hashes,
paths, image/SKU/subnet pins, endpoints, HSM key version, replay path, and
review outputs before continuing.

For the CH25 psi DAG, use `tools/tg_azure_cpu_psi_materializer.py` and the
separate psi site and materialization schemas. Each phase site must list
exactly the retained exports required by its reviewed predecessors; their
signed operational result pins and portfolio receipts are rechecked before
the next job is packaged.

For the Platt head, use `tools/tg_azure_cpu_platt_head_materializer.py` and its
dedicated site/materialization schemas. The materializer requires the complete
pinned FLINT 3.6.0 and python-flint 0.9.0 source trees plus the exact reviewed
x86-64 wheel; no caller-selected interpreter, executable, or command is
accepted.

For CH25 Lemma A.7, use `tools/tg_azure_cpu_a7_materializer.py` and its
dedicated site/materialization schemas. It requires the same complete pinned
source/runtime closure plus the exact 1,494,999-byte retained boundary
artifact. Both the measured workload and its trace verifier replay all 16,191
leaves; the semantic row nevertheless stays disabled until the
FLINT-to-Mathlib realization and a real attested receipt are reviewed.

For Proposition 12.2.4, use
`tools/tg_azure_cpu_prop1224_materializer.py` and its dedicated schemas. Each
four 96-worker jobs retain signed archive identities; the terminal accepts
exactly four exports, audits all 12,930 logical-leaf receipts, and performs
the independent full-plan merge. The
production x86-64 source build must be smoke-tested before launch.

The remaining specialized CPU site templates are checked in beside the base
site template:

- [`azure_cpu_hurst_materializer_site.redacted.json`](../examples/trusted-compute/azure_cpu_hurst_materializer_site.redacted.json);
- [`azure_cpu_dirichlet_materializer_site.redacted.json`](../examples/trusted-compute/azure_cpu_dirichlet_materializer_site.redacted.json);
- [`azure_cpu_dirichlet_postcheck_materializer_site.redacted.json`](../examples/trusted-compute/azure_cpu_dirichlet_postcheck_materializer_site.redacted.json).

They are schema-valid shapes only. Zero digests, zero sizes, placeholder
upstream roots, and placeholder Azure/HSM identities deliberately fail
materialization or operator validation until replaced with reviewed pins.

State is an append-only canonical event journal beside `outputs.state`. Every
event includes the previous event hash, exact campaign-config hash, expected
source stage, target stage, and optional immutable artifact hash. The state
file itself is only a cache of that journal. If a crash occurs after an event
is durable but before the cache is replaced, recover only the cache with:

```bash
python3 azure/cpu_production_orchestrator.py recover-state-head "$CONFIG"
```

Do not use this command to excuse a journal mismatch: any changed event,
missing sequence, invalid transition, or different config fails closed.

## Deploy, challenge, and stage

```bash
python3 azure/cpu_production_orchestrator.py deploy "$CONFIG"
python3 azure/cpu_production_orchestrator.py challenge "$CONFIG"
```

The challenge is retained outside the VM. Through the reviewed private
transport, copy the exact canonical config, workload archive, retained
challenge, and transcript policy to their configured guest paths. Leave
`worker.artifact_root` absent; the guest safely extracts the pinned archive.
After comparing hashes, VM identity, and private address:

```bash
python3 azure/cpu_production_orchestrator.py \
  record-worker-stage-handoff "$CONFIG" --confirm-exact-staging
python3 azure/cpu_production_orchestrator.py ack-worker-stage "$CONFIG"
```

Copy the generated handoff to `worker.stage_manifest` before the second
command. The confirmation records a human assertion; it does not make an
unauthenticated transport secure.

## Run in the confidential guest

Use the reviewed system Python and preserve no ambient environment:

```bash
sudo -- /usr/bin/python3 azure/cpu_production_orchestrator.py \
  worker-run-local /srv/sparkinterval-worker/input/cpu-campaign.json
```

Do not use `sudo -E`. The guest validates the handoff, archive, job,
invocation, transcript policy, and remaining challenge lifetime. It then runs
the measured job, collects CPU-only MAA/SEV-SNP/vTPM evidence without resetting
PCR 23, and creates `worker.certificate_archive` plus
`worker.completion_manifest`. These artifacts are still pending independent
appraisal.

Return both through the reviewed egress channel to the two configured handoff
paths, then run:

```bash
python3 azure/cpu_production_orchestrator.py ingest-returned "$CONFIG"
python3 azure/cpu_production_orchestrator.py appraise "$CONFIG"
```

The operator safely extracts the archive, verifies the run bundle, replays
the measured transcript, and invokes the pinned independent appraiser. CPU
appraisal rejects every NVIDIA artifact or claim and requires the exact
retained challenge and result binding.

## HSM receipt and source-review candidates

Place the replay database on durable issuer-controlled storage, then:

```bash
python3 azure/cpu_production_orchestrator.py issue-receipt "$CONFIG"
python3 azure/cpu_production_orchestrator.py generate-review-candidates "$CONFIG"
```

Receipt issuance burns/reserves the challenge before signing. The signer is
`azure/managed_hsm_signer.py` with the configured immutable key version. The
final command writes only the configured review paths. Review the exact key,
backend, profiles, verifier/policy hashes, statement, output bytes, signature,
and generated Lean theorem before any separate source change.

## Ambiguous side effects and resume

Completed deploy, challenge, ingestion, appraisal, receipt, and review steps
are idempotent at their immediate completed stage and revalidate their recorded
artifact rather than repeating the side effect. A child failure after a cloud
or signing call enters a named reconciliation stage.

- `reconcile-deployment` adopts only a canonical deployment record that again
  passes the complete `cpu_cvm.py` result contract. It never assumes that a
  failed CLI call created nothing.
- `reconcile-challenge` adopts only a live, campaign-matching retained
  challenge at the exact configured path.
- `reconcile-receipt` adopts only an already persisted receipt whose RSA
  signature, CPU backend, receipt identity, and configured key ID verify.
  If no receipt exists after an ambiguous signing attempt, do not retry: the
  HSM or replay ledger may already have consumed the challenge. Reconcile the
  issuer externally and normally start a fresh campaign/challenge.

Local ingestion/appraisal/review failure stages intentionally require manual
inspection. Do not delete journal events or overwrite outputs to force a
retry. Retain the failed campaign as audit evidence and start a new campaign
when safe reconciliation is unavailable.

## Tests

```bash
python3 -m unittest -v tests.test_cpu_production_orchestrator
python3 -m unittest -v \
  tests.test_azure_cpu_cvm \
  tests.test_azure_evidence_appraiser \
  tests.test_managed_hsm_signer \
  tests.test_measured_runner \
  tests.test_trusted_compute_receipt
```

The focused operator tests cover config/schema drift, tampered pins, backend,
profile, policy and key confusion, CPU/GPU evidence separation, live trust
path rejection, append-only state tampering, idempotent deployment, ambiguous
Azure reconciliation, environment capability isolation, and receipt
backend/key confusion. They do not substitute for an actual Azure run or
review of production appraiser/key material.
