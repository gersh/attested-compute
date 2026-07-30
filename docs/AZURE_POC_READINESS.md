# Azure confidential-computing proof of concept: readiness

What has to be true before the two-step confidential-computing proof of
concept can run, split by who can do it.

This document is an inventory of what is missing. It is not an authorization
to launch and it does not change any gate. `tools/tg_azure_launch_preflight.py`
still reports all ten campaigns as `site-pin-needed`, all ten as
`calibration-blocked`, and zero as `cloud_launch_ready`; producing this list is
the opposite of declaring the list empty.

Nothing here was verified against a live Azure account. There is no `az` CLI
installed, no `~/.azure`, and no subscription. Every claim below is either
derived from this repository, in which case a file and line is cited, or is an
Azure behaviour taken on report, in which case it is marked. The section
[Not verifiable without an account](#not-verifiable-without-an-account) lists
every item in the second category in one place.

## The two steps

| | Step 1 | Step 2 |
| --- | --- | --- |
| Campaign | `cdem-table-abel` | `ramare-zuniga-lemma-6-2` |
| Backend | `azure_sevsnp_cpu` | `azure_ncc40ads_h100_v5` |
| SKU | confidential AMD SEV-SNP CPU | `NCC40ads_H100_v5`, one node |
| Compute | about 87 s (the local OpenMP producer took 86.574 s) | 1–8 wall hours |
| Terminal factory | `tg_verifier.azure_cpu_workload_factory.CDEM_FACTORY` | `tg_verifier.azure_h100_r2star_workload_factory` |
| Portfolio groups | 1 | 1 |
| Semantic binding | **`enabled`** | `staged_disabled` |

Step 1 is first because it is the only one of the eleven registered campaigns
whose Azure semantic binding is `enabled`
(`SignedResultCertificate.certifyCDEMTableAbel`). The other ten are
`staged_disabled`, so step 1 is the only one that can currently close an atom
end to end. Step 2 is second because it is the only small GPU campaign: the
Goldbach GPU route is sized at 141–352 hours across eight nodes and the
Dirichlet route carries no retained estimate.

Neither step discharges a Lean atom on its own. A successful run produces a
signed receipt; admission is a separate, currently blocked step
(`semantic-admission-blocked` for all ten campaigns).

## Cost

Live pricing, Linux, regular Consumption, `eastus2`, as reported. The two
snapshot rates below also appear in `tg_verifier/azure_production_sizing.py:61`
and `:65` with snapshot date 2026-07-21.

| SKU | On demand | Spot | Low Priority |
| --- | --- | --- | --- |
| `NCC40ads_H100_v5` (confidential H100) | $6.98 | **$1.419034** | $1.396 |
| `DC96as_v6` (confidential CPU) | $4.358 | **$0.805358** | $0.872 |
| `NC40ads_H100_v5` (non-confidential H100) | $6.98 | $5.0256 | — |

**There is no confidential-computing price premium.** The non-confidential
`NC40ads_H100_v5` costs the same $6.98 on demand, and its spot price is
*higher* at $5.0256 — so confidential H100 spot is about 3.5x cheaper than
non-confidential H100 spot. Confidentiality is not what makes this expensive.

### What is expensive: Managed HSM

**Key Vault Managed HSM Pool Standard B1 is $3.20/hour, about $2,336/month,
billed continuously from provisioning regardless of whether any campaign
runs.** This is the single largest fixed cost of the confidential path and it
is not per run.

It cannot be avoided by running the pool only during a campaign. This
repository pins the HSM key *version* immutably in the site configuration
(`$.managed_hsm.key_uri` ends in a 32-hex key version), and receipts are bound
to that version. Destroying and recreating the pool mints a new key version and
invalidates the binding of every receipt already issued.

Put beside the compute, this dominates the proof of concept completely:

| | Spot | On demand |
| --- | --- | --- |
| Step 1, assuming a 1-hour VM lifetime for 87 s of compute | $0.81 | $4.36 |
| Step 2, 8 hours, one node | $11.35 | $55.84 |
| **Both PoC steps** | **$12.16** | **$60.20** |
| Managed HSM, one month | $2,336 | $2,336 |

The entire two-step proof of concept costs about 2.6% of one month of the HSM
at on-demand prices. Deciding *when* to provision the HSM is therefore a larger
financial decision than deciding which price class to run the compute on. The
sizing model already excludes "Managed HSM lifetime" from its cost envelope
(`tg_verifier/azure_production_sizing.py:3548`), so no existing report shows
this number.

For scale: the Goldbach GPU campaign at 352 hours on 8 nodes is about $3,996 on
spot or $19,655 on demand, against roughly $1,126 of HSM for the same window.

## Operator actions

These need credentials, billing, or a portal/support request. They cannot be
done in this repository. Ordered by lead time, longest first.

### 1. Spot quota — start this first

**Spot vCPU quota is separate from regular vCPU quota, defaults low, and is
raised by a support request.** This is the long-lead item.

- Sixteen `NCC40ads_H100_v5` would be 640 spot vCPUs. The two PoC steps need
  far less — step 2 is one node, 40 spot vCPUs — but the large campaigns that
  follow do not.
- The failure mode is an explicit error of the form "X azure spot vCPUs are
  needed for this configuration, but only Y vCPUs remain".
- Raising it requires a support request, which has human turnaround.

Request the PoC quota and the campaign quota at the same time. There is no
reason to discover the campaign-scale limit after the PoC succeeds.

### 2. Subscription and network

- An Azure subscription. Every other Azure identity hangs off it.
- A resource group and a private virtual network with a subnet for the
  confidential VMs. The site file pins the subnet by full ARM resource id.

### 3. A private Compute Gallery image

The site file requires an exact Compute Gallery image **version**, not a
marketplace URN. The guest image is inside the measured boundary, so it has to
be an immutable version that can be re-referenced across runs.

This one blocks more than it looks like it does. The production measured-runner
policy is bound to this exact string: `azure/cpu_production_orchestrator.py:502`
requires `immutable_image_reference` to equal the image and
`immutable_image_reference_sha256` to equal that string's SHA-256. So the image
must exist before that policy file can be written at all.

### 4. Managed HSM

Provision the pool, create the signing key, export its public key. See the cost
warning above before doing this — the meter starts at provisioning.

### 5. Attestation endpoint

Choose the Microsoft Azure Attestation endpoint for SEV-SNP. The composite
appraisal policy's `maa_accepted_issuer` must equal the issuer derived from its
own `maa_attestation_url` (`attestation/verify_azure_ncc_evidence.py:1100`), so
this choice has to be made before that policy can be finalized.

Azure publishes shared regional attestation endpoints whose URLs need no
subscription to name. Whether a shared provider is acceptable here, or whether
a dedicated provider in the operator's own tenant is required, is a policy
decision this repository has not recorded. See
[Not verifiable without an account](#not-verifiable-without-an-account).

### 6. An SSH key pair

`ssh-keygen`, locally. No Azure account is needed and this is not on the
critical path. It is listed as an operator action rather than repository work
for one reason: the private half is a credential the operator must choose and
hold, and committing a key the operator did not choose would be worse than
leaving the pin empty.

### 7. Boost 1.83.0, for step 2 only

The R2Star materializer requires a Boost 1.83.0 header tree whose reviewed
identity is exactly 15,653 headers, 149,594,508 bytes, tree SHA-256
`7ecf4808a419bd489f930c685320cf2745e46c6bc5591122c26773386214d8e2`
(`tg_verifier/azure_h100_r2star_materializer.py:95-100`). It is not vendored here.
The checked-in example carries a plausible concrete path, so no gate flags its
absence.

### 8. A CUDA toolkit on the materialization workstation, for step 2 only

The R2Star materializer runs a closed CUDA build with pinned compilers. The
`nvcc`, `g++`, and `python3` digests in the site file describe the
materialization workstation, not the confidential VM. A GPU is not needed to
build; the toolkit is.

## Repository work

These can be written now, with no Azure account.

### 1. The stale evidence-verifier source pin — blocking, and currently invisible

`attestation/verify_azure_ncc_evidence.py` self-pins the SHA-256 of eight
measured modules and raises at import time if any differs
(`attestation/verify_azure_ncc_evidence.py:43-81`). On this branch seven match
and one does not:

```
STALE  tg_verifier/goldbach_gpu_campaign.py
          pinned 5d9f92228f6aa58cc7ab9975b988200dbda1f932294f4dcb4983b7634aea20c2
          actual 6ccc05fce326f6c12adeee7296ef3371c234a4bd5b63d400a2712c6e657c7c2a
```

So the program currently refuses to start:

```
$ python3 attestation/verify_azure_ncc_evidence.py --help
RuntimeError: measured module tg_verifier/goldbach_gpu_campaign.py differs from verifier source pin
```

The orchestrator invokes this program during the appraisal step of step 1
(`azure/cpu_production_orchestrator.py:1365`), so the CPU proof of concept
would fail on first contact with it. No gate in this repository executes the
verifier, so nothing reports this.

Re-pinning is deliberately **not** done here. It is a review decision about the
attestation trust surface, and the module whose digest moved is campaign-layer
code owned by another workstream. The right fix is to confirm that the current
`goldbach_gpu_campaign.py` is the reviewed one and re-pin, or to revert the
drift — not to make the check softer.

### 2. The two operator policy files, as far as they can be taken

Neither can be finished without operator identities, but both have a fully
determined shape that this repository knows and the operator would otherwise
have to reverse-engineer. `tools/tg_azure_poc_site_pin_inventory.py` reports
both under `repository_derivable_values.operator_policy_templates`:

- **Measured-runner policy.** Kind `sparkinterval_measured_runner_policy`,
  `schema_version` 1, `classification` `production`, `production_ready` true,
  `policy_id` `sparkinterval.runner.azure-cpu.production.v1`, plus the seven
  required claims. Blocked on the image, per operator action 3.
- **Composite appraisal policy.** Kind
  `sparkinterval_azure_evidence_appraisal_policy`, required keys
  `allowed_backends`, `azure_appraiser`, `kind`, `nvidia_appraiser`,
  `schema_version`; `nvidia_appraiser` must be exactly `null` for the CPU
  backend. Blocked on the MAA endpoint, per operator action 5.

### 3. Not needed: an evidence verifier program

Worth stating because the site file's placeholder path
(`/srv/sparkinterval-operator/bin/verify-azure-cpu-evidence`) reads like a
program that has to be written. It does not.
`attestation/verify_azure_ncc_evidence.py` already implements exactly the
six-flag argument list the orchestrator invokes and already branches on the
`azure_sevsnp_cpu` backend. The pin is the digest of the operator's installed
copy. Installed verbatim, that value is
`a15441351c188cef432aadb2e467a8e7d6d9982e21edf072d2886c61fe985c57`
(78,607 bytes).

### 4. Source-closure confirmation

Both materializers refuse to package a tree whose digests differ from the clean
git repository closure. Confirming these before launch removes a class of late
failure. Computed now:

| Campaign | Files | Bytes | Rows digest |
| --- | --- | --- | --- |
| `cdem-table-abel` | 4 | 58,843 | `432aeb13e0c0b5dc1d0f50128c75df4df8cb6aa35d6605b19c3c21b376810ae1` |
| `ramare-zuniga-lemma-6-2` | 26 | 444,722 | `4c20665c376013bcac8bc3e416c771f4d7a35496774c12bdd58ea6c74ab604dd` |

### 5. A SKU disagreement to settle

The CPU site example names `Standard_EC96as_v6`; the retained sizing model
prices `Standard_DC96as_v6`
(`tg_verifier/azure_production_sizing.py:64`). Both are real confidential SKUs
and neither is redacted, so no gate flags it. One of the two is wrong and this
repository does not say which.

## The site-pin gap

`tools/tg_azure_poc_site_pin_inventory.py` enumerates every placeholder for the
two PoC campaigns, classified by who supplies it and when. Run it with
`--table` for the readable form or `--pretty` for JSON.

```
total 18 pins; 5 obtainable without an Azure account; 13 not; 7 silent requirements
  build_host_derivable: 4
  chained_after: 7
  operator_identity_requires_subscription: 6
  operator_local_secret: 1
  repository_derivable: 0
```

- `cdem-table-abel`: 14 pins across two site files, 2 obtainable now.
- `ramare-zuniga-lemma-6-2`: 4 pins in one site file, 3 obtainable now.

`repository_derivable: 0` is the honest headline. **Not one of the eighteen
placeholders is a value this repository can fill in.** The repository-derivable
material is real but sits beside the pins, not in them: source closures, policy
shapes, profile digests, the evidence-verifier reference digest.

The inventory also records seven **silent requirements** — things that block a
launch but that the preflight's redaction scan cannot see, because the
checked-in example already carries a plausible concrete value. The Boost tree
identity, the SKU disagreement, and the stale verifier pin are all in this
category. An operator who cleared all eighteen visible markers would still not
be able to launch.

The inventory fails closed if it ever drifts from the preflight it explains: it
scans the examples with the preflight's own scanner and refuses to build a
report if the reviewed table and the observed markers disagree in either
direction.

## Eviction handling: Batch versus retry

### Recommendation: extend the existing orchestration. Do not map onto Batch.

The cost argument favours Batch and is worth about 1.6%: Low Priority is $1.396
against $1.419034 spot on the GPU SKU. Over the whole Goldbach campaign — 8
nodes, 352 hours — that is roughly $65. Against a $2,336/month HSM it is noise.
The decision should be made on correctness, and on correctness Batch loses.

**The feature that motivates Batch is the feature you would have to turn off.**
Batch's value here is automatic requeue-on-preemption. But this repository's
execution model requires a *fresh attestation challenge nonce per attempt*. The
chain is challenge → job binding → start binding → result binding, and
`azure/measured_runner.py` asserts PCR23 is zero before extending it. An
automatic requeue that re-runs the same task with the same command line would
re-run with a nonce that may already have been extended into PCR23 on the
evicted node. This repository already names that hazard in two places:

- `tg_verifier/azure_portfolio.py:2342` — "existing challenge expired;
  automatic retry is forbidden because the attempt may have run and requires
  operator reconciliation"
- `azure/cpu_production_orchestrator.py:234` — the receipt stage is literally
  called `receipt_issuance_in_progress_challenge_may_be_burned`

To use Batch safely you would set `maxTaskRetryCount` to 0 and add a job
manager task that mints a fresh challenge and submits a *new* task per attempt.
That is the retry layer, reimplemented inside Batch, with a service dependency
and a trust boundary added and nothing removed.

**The Batch node agent would join the measured TCB.** Batch tasks run under a
node agent inside the VM. `azure/measured_runner.py` builds a closure manifest
over exactly the software it measures. Adding an unmeasured, Microsoft-updated
agent inside the confidential boundary works directly against that. This is an
architectural objection, not a performance one.

**The one-VM-per-config assumption is load-bearing.**
`azure/cpu_production_orchestrator.py:755` hard-asserts `nodes == 1`, and the
whole operator state machine — deploy, challenge, ingest, appraise, issue — is
written around one shard on one VM with a manual handoff. Mapping onto Batch
task arrays is not a scheduling change; it is a rewrite of the layer that
currently carries the fail-closed guarantees.

**What actually needed adding was small.** The campaign layer already had the
hard parts: per-leaf receipts written `O_EXCL` under an index-derived name
(`tools/trusted_compute_receipt.py:284`), exact-coverage aggregation
(`tg_verifier/goldbach_gpu_campaign.py:1470`), and a measured runner that
publishes its package with one atomic rename so a killed run leaves a staging
directory and never a package. The gap was one layer up: the orchestrators had
no notion of "this attempt was preempted", so every ambiguous failure landed in
manual reconciliation. Correct on reserved capacity; unusable on spot, where
one eviction in a 65,536-leaf campaign stalls the campaign.

I judged that gap to be one module rather than one cloud service, and
implemented it.

### What was implemented

`tg_verifier/azure_eviction.py`, with `tools/tg_azure_eviction_policy.py` as
its CLI and 25 tests in `tests/test_azure_eviction.py`.

It separates the **leaf**, which has at most one receipt for all time, from the
**attempt**, of which a leaf may have many.

**Retry admissibility is a table, not control flow**, because it is the whole
safety argument:

| Stage at termination | Decision |
| --- | --- |
| `handoff_prepared` | retry admissible |
| `challenge_created` | retry admissible |
| `azure_deployment_in_progress` | operator reconciliation required |
| `azure_deployed` | retry admissible after resource teardown |
| `measured_run_in_progress` | retry admissible |
| `returned_package_ingested` | operator reconciliation required |
| `appraisal_recorded` | operator reconciliation required |
| `receipt_issuance_in_progress` | operator reconciliation required |
| `verified_receipt_recorded` | leaf already complete |

The cut is at package ingest. Before it, the only durable thing a terminated
attempt can have produced is a run package on a VM that is about to be
destroyed, or a staging directory the measured runner already removed. At and
after it, a real attested package, an appraisal, or an HSM signature may exist,
and discarding one silently would be an audit hole. **Receipt issuance stays
manual, permanently** — a signature that exists but was not recorded is exactly
the case a human has to look at. Nothing here weakens
`require_azure_measured_worker_for_workload` or any other fail-closed guard;
the automation is confined to the window where the orchestrators would
otherwise stall, which is where spot evictions actually land, because the
measured run is the long pole.

Two further restrictions, both tested:

- **Only expected reclamation is retried.** An attempt that ended as
  `workload_failure` or `unknown` goes to reconciliation even in a retryable
  stage; retrying would loop on a real fault. A run killed by a signal with no
  Scheduled Events evidence is classified `unknown`, not `preempted` — guessing
  generously there would convert a crash loop into a retry loop.
- **Every retry demands a fresh challenge.** The ledger refuses to record a
  second attempt carrying a challenge digest it has already seen.

The two properties that mattered are enforced mechanically rather than
asserted:

1. *A leaf killed mid-flight leaves no admissible receipt.* Dead attempts are
   **quarantined** by atomic rename into a directory no ingest path reads. Never
   deleted — an evicted attempt is evidence about the campaign — and never left
   in place, where the next attempt's ingest would find a truncated workspace.
2. *Receipts are per completed leaf, not per attempt.*
   `verify_leaf_receipt_coverage` proves this from the ledger and the receipt
   set together, catching the four failure modes the campaign aggregate cannot
   see on its own: a retried leaf counted twice, a leaf counted as missing
   because its successful attempt was lost, a receipt whose leaf never
   completed an attempt, and a receipt sourced from a quarantined attempt.

A worked example — four leaves, two of them evicted, seven attempts, three
wasted:

```
leaf 0 attempt 0: preempted    stage=measured_run_in_progress   -> retry_admissible
leaf 0 attempt 1: preempted    stage=measured_run_in_progress   -> retry_admissible
leaf 0 attempt 2: completed    stage=verified_receipt_recorded  -> leaf_already_complete
leaf 1 attempt 0: completed    stage=verified_receipt_recorded  -> leaf_already_complete
leaf 2 attempt 0: preempted    stage=measured_run_in_progress   -> retry_admissible
leaf 2 attempt 1: completed    stage=verified_receipt_recorded  -> leaf_already_complete
leaf 3 attempt 0: completed    stage=verified_receipt_recorded  -> leaf_already_complete
```

```
$ tools/tg_azure_eviction_policy.py verify-coverage RUN --leaves L.json --receipts R.json
"coverage_exact_one_receipt_per_leaf": true,
"attempt_efficiency": {"leaves_retried": 2, "max_attempts_on_one_leaf": 3,
                       "total_attempts": 7, "wasted_attempts": 3}
"violations": []
```

Seven attempts, four receipts, exact coverage: the retries are not duplicates.
Removing one receipt makes it exit 2 with `missing_receipt` populated: the lost
leaf is a gap, not a silent pass.

An attempt budget (default 8 per leaf) is enforced so an eviction storm
surfaces rather than spends.

### If Batch is revisited

The argument above is architectural and does not depend on any Azure fact I
could not check. If it is revisited, the questions to settle first are whether
Batch pools support confidential VM SKUs at all, and whether a Batch task can
run on a confidential VM without the node agent being part of the measured
guest image. If the answer to the second is no, the TCB objection is decisive
on its own.

## Not verifiable without an account

Everything in this list is either taken on report or genuinely unknown. None of
it was checked against Azure.

**Taken on report, not independently verified:**

1. All live pricing. The two snapshot rates match
   `tg_verifier/azure_production_sizing.py`, which is corroboration between two
   reports and not verification.
2. That spot quota is separate from regular quota, defaults low, and needs a
   support request.
3. The exact spot-quota error text.
4. Managed HSM Standard B1 at $3.20/hour and continuous billing.
5. That `NC40ads_H100_v5` spot is $5.0256, i.e. that confidential spot is
   cheaper than non-confidential spot.
6. Azure Batch Low Priority at $1.396 on the GPU SKU.

**Not established either way:**

7. Whether Azure Batch pools support confidential VM SKUs, and whether
   `NCC40ads_H100_v5` or `DC96as_v6`/`EC96as_v6` are among them.
8. Whether Batch Low Priority VMs are still offered, or have been retired in
   favour of Spot.
9. Batch's exact requeue semantics on preemption — whether the same task id and
   command line are reused, and whether a preemption counts against
   `maxTaskRetryCount`. The recommendation above assumes reuse; if Batch
   instead mints a new task identity per attempt, the nonce objection weakens,
   though the node-agent TCB objection does not.
10. Whether the Batch node agent can be kept out of a confidential guest image.
11. Whether spot capacity for `NCC40ads_H100_v5` exists in `eastus2` at all,
    and at what eviction rate. Every claim above about spot being usable
    assumes it can be obtained. The sizing model already says "Spot price
    arithmetic is not a capacity or interruption guarantee"
    (`tg_verifier/azure_backend_optimizer.py:659`).
12. The advance-notice window for a spot eviction. The implementation does not
    depend on one — it classifies an eviction after the fact rather than racing
    a notice — but a shutdown hook would need it.
13. Whether the Scheduled Events `EventType` values the classifier keys on
    (`Preempt`, `Terminate`, `Reboot`, `Redeploy`, `Freeze`) are exactly right.
    They are a closed set in one function
    (`tg_verifier/azure_eviction.py:classify_termination`) and easy to correct;
    an unrecognised value classifies as `unknown` and routes to reconciliation,
    so an error there fails safe.
14. Whether a shared regional MAA endpoint is acceptable to the composite
    appraisal policy, or a dedicated provider is required.
15. Whether a Managed HSM pool can be paused to stop billing, and what deleting
    one does to key material under purge protection. The recommendation to
    treat the HSM as continuously billed follows from this repository pinning
    key versions immutably, which holds regardless.
16. Real step-2 wall time. The 1–8 hour range is a projection; no
    `NCC40ads_H100_v5` measurement is installed, which is why all ten campaigns
    report `calibration-blocked`.

## Verification

State of the gates, unchanged by everything above:

```
$ tools/tg_azure_launch_preflight.py --pretty
  cloud_launch_ready_campaigns:            0
  site_pin_needed_campaigns:              10
  calibration_blocked_campaigns:          10
  semantic_admission_blocked_campaigns:   10
  theorem_admission_complete_campaigns:    0

$ tools/audit_tg_registered_campaigns.py --check
  named_physical_campaigns:               10
  semantic_bindings_enabled:               1
  semantic_bindings_staged_disabled:      10
  mismatch_count:                          0
```

Both reports are byte-identical to their state before this work. No readiness
or acceptance flag was flipped: `cloud_launch_ready`,
`theorem_admission_complete`, `site_pin_needed`, `production_accept`, and
`external_atom_discharged` all stand where they stood.
