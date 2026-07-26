# Attested-provenance trust model (prototype, not adopted)

This document describes a *prototype alternative* to the repository's
confidential-computing execution boundary. It replaces TEE attestation with
two cheaper, publicly checkable layers and leaves the result-checking layer
untouched.

**Status.** Nothing here is adopted. The confidential-computing path in
[`AZURE_CONFIDENTIAL_COMPUTE.md`](AZURE_CONFIDENTIAL_COMPUTE.md) and
[`TRUST_MODEL.md`](TRUST_MODEL.md) is unchanged and remains the only route to
a Lean theorem. No readiness or acceptance flag was moved: `cloud_launch_ready`,
`theorem_admission_complete`, `site_pin_needed`, `external_atom_discharged`,
and `production_accept` are exactly as they were. No Lean source was modified.
The proposed axiom in the last section is a *proposal in this document only*;
it does not exist in the repository.

The prototype exists so the owner can evaluate a decision, not so the decision
can be pre-made by tooling.

## 1. The three layers

| Layer | Question it answers | Mechanism | Status in this prototype |
| --- | --- | --- | --- |
| 1. Build provenance | Which source produced these executable bytes? | GitHub artifact attestations (Sigstore/Fulcio/Rekor, in-toto SLSA provenance) plus a reproducible build | New: `.github/workflows/build-provenance.yml`, `tools/reproduce_attested_build.sh`, `tools/verify_build_provenance.py` |
| 2. Execution integrity | Did the computation actually run and produce this Merkle root? | k independent replications on non-confidential capacity, across providers and operators, using the two independent implementations | New: `schemas/attested-provenance-record.schema.json`, `tg_verifier/attested_provenance.py`, `tools/tg_attested_provenance_record.py` |
| 3. Result checking | Does the result imply the theorem? | Lean full result certificates and the closed registered semantics | **Unchanged.** Not touched by this prototype |

Layers 1 and 2 answer different questions and neither substitutes for the
other. That is the single most important sentence in this document, and
section 2 restates it in the strongest available form.

## 2. What a build attestation does not do

A GitHub build-provenance attestation is a signed statement of the form:

> These artifact digests were produced by this workflow, running in this
> repository, at this commit.

It contains **no** evidence that a computation ran. It says nothing about:

- whether the attested binary was ever executed;
- what input it was executed on, if it was;
- how long it ran, on what hardware, or in what region;
- what output it produced; or
- whether a published Merkle root has anything to do with it.

An attestation is a statement about *bytes at rest*. Execution evidence is a
statement about *an event*. A reader who comes away thinking that "the binary
is attested" implies "the campaign ran correctly" has misread the model by a
whole layer. `tools/verify_build_provenance.py` therefore emits an explicit
`authority` block on every result, with
`attests_that_a_computation_ran: false` and
`replaces_execution_evidence: false`, so a downstream consumer cannot quietly
widen the claim while parsing the record.

This is the same discipline the repository already applies to an unsigned DGX
bundle: hashes establish identity relative to an expected digest, not truth.

## 3. Layer 1: build provenance

### 3.1 The workflow

`.github/workflows/build-provenance.yml` has three jobs.

`build` runs inside a digest-pinned toolchain container
(`gcc@sha256:1d71f0f3450214bef38fe09e6f610fb6cca90cf97b43f4ce845bfc32a4168818`,
which was `docker.io/library/gcc:13.3.0-bookworm` on 2026-07-26) and invokes
`tools/reproduce_attested_build.sh`. Its permissions are `contents: read`
only: nothing in the job that compiles code is able to request an OIDC token
or mint a signature.

`attest` runs on a separate ephemeral VM with `id-token: write` and
`attestations: write`. It downloads the artifacts, recomputes every digest
from the bytes rather than trusting the manifest, and only then calls
`actions/attest-build-provenance`. It executes no build step from the
repository.

`independent-rebuild` rebuilds from the same commit in a fresh container and
requires a byte-identical `build-manifest.json`. This is the in-CI rehearsal
of what a third-party rebuilder does.

Every action is pinned to a full commit SHA and every container to a digest.
The workflow's only trigger is `workflow_dispatch`; merging it can never start
a run. `tests/test_attested_provenance.py` enforces all of these properties.

### 3.2 What is built

The prototype attests the CPU-only closure that a third party can rebuild
without a GPU:

- `sqrt218_cpu_checker_v2`, the checker CLI;
- `sqrt218_cpu_checker_kat`, whose known-answer test must pass before anything
  is attested;
- `sqrt218_cpu_checker_pure_entry_x86_64_v2`, the freestanding proof-facing
  ELF, when an x86-64 driver is present; and
- `sparkinterval-worker-closure.tar.gz`, a `git archive` of `tg_verifier`,
  `tools`, `schemas`, `cpu_checker`, and `profiles`, so the Python worker and
  verifier implementation carry the same commit-bound identity as the
  binaries.

The CUDA device code and the Lean build are **not** covered. Extending
provenance to them is real work: `nvcc` output determinism across driver and
toolkit versions has not been measured here, and Lake builds are not
byte-reproducible without further pinning. Do not describe the campaign
executables as provenance-covered on the strength of this prototype.

### 3.3 Reproducible build

`tools/reproduce_attested_build.sh` is the single build definition used by
both the workflow and any third party. It refuses to run from a dirty
worktree, derives `SOURCE_DATE_EPOCH` from the commit rather than the wall
clock, fixes `LC_ALL` and `TZ`, uses `gzip -n` so the archive container holds
no timestamp, and writes the manifest with POSIX text tools so no interpreter
version can perturb the bytes.

A third party checks the claim like this:

```bash
git clone https://github.com/<owner>/gpu_prover.git
cd gpu_prover
git checkout <attested-commit>

docker run --rm -v "$PWD:/src" -w /src \
  gcc@sha256:1d71f0f3450214bef38fe09e6f610fb6cca90cf97b43f4ce845bfc32a4168818 \
  bash -c 'git config --global --add safe.directory /src &&
           tools/reproduce_attested_build.sh --output-dir /src/rebuild'

# 1. do my bytes match the manifest I just produced?
python3 tools/verify_build_provenance.py --pretty \
  check-manifest rebuild/build-manifest.json

# 2. do those exact bytes carry a signed attestation naming this commit?
python3 tools/verify_build_provenance.py --pretty verify \
  --artifact rebuild/artifacts/sqrt218_cpu_checker_v2 \
  --repo <owner>/gpu_prover \
  --source-commit <attested-commit> \
  --signer-workflow \
    <owner>/gpu_prover/.github/workflows/build-provenance.yml
```

Step 2 requires GitHub CLI 2.49.0 or newer, because the `gh attestation`
command group does not exist before that release. The tool fails closed with
`status: gh_attestation_unavailable` on an older CLI rather than reporting a
soft pass. It also passes `--deny-self-hosted-runners` and pins
`--predicate-type https://slsa.dev/provenance/v1` by default.

`tools/verify_build_provenance.py inspect-bundle` reads a Sigstore bundle
offline and reports its subjects, predicate type, build type, and builder ID.
It performs no cryptographic verification and always reports
`signature_verified: false` and `accepted: false`. It is a reading aid, never
an acceptance.

### 3.4 SLSA level actually achieved

**Build L2.** The provenance is generated and signed by the build platform,
is authenticated, and is available to consumers, and the build runs on hosted
infrastructure from a version-controlled definition.

It is **not L3**, and must not be described as L3. L3 requires that provenance
generation be isolated from user-defined build steps in a way the build steps
cannot influence. This workflow gets part of the way there and no further:

- *Done:* signing happens in a separate job on a separate ephemeral VM, and
  the build job holds neither `id-token: write` nor `attestations: write`, so
  the compiling job cannot mint a signature at all.
- *Not done:* the signing job's OIDC identity is still this repository's own
  workflow ref. Anyone who can modify `.github/workflows/build-provenance.yml`
  and dispatch it can obtain a valid attestation for whatever bytes they
  choose. The provenance faithfully records *which* workflow ref signed, so
  such a change is visible in the certificate, but it is not prevented.
- The recognised route to L3 on GitHub is a trusted reusable workflow whose
  own identity appears in the certificate, such as
  `slsa-framework/slsa-github-generator`. Adopting it is a separate decision
  with its own supply-chain surface, and this prototype does not take it.

The replication-record validator refuses any record whose replicas claim
`slsa_build_level: "L3"`, so the overstatement cannot enter the evidence chain
by assertion.

## 4. Layer 2: N-way independent replication

### 4.1 Design

Instead of one attested run, the campaign runs k times on ordinary
non-confidential capacity. Each replica publishes its Merkle root and output
digest. The roots are compared; agreement is the evidence.

The independence axes, in decreasing order of how much they buy:

1. **Implementation.** The repository already mandates two independent
   implementations with independent replay. Two replicas that share a binary
   share its bugs, so a second *implementation* is worth far more than a
   second *machine*.
2. **Operator.** At least one replica run by someone other than the author is
   the only thing in this model that resists author fabrication at all.
3. **Provider.** Separate cloud accounts, ideally separate providers, so no
   single account compromise or single provider fault is common to all
   replicas.
4. **Time and region.** Weak, but it separates transient regional faults.

### 4.2 The record type

`schemas/attested-provenance-record.schema.json` defines
`sparkinterval.attested-provenance-replication-record.v1` with backend
`attested_provenance_replicated`. It sits alongside the signed
trusted-compute receipt and is deliberately **not** a member of that receipt's
`backend` enum.

Containment is enforced, not merely intended:

- `schemas/trusted-compute-receipt.schema.json` is unmodified and its
  `backend` enum is still exactly `["azure_sevsnp_cpu",
  "azure_ncc40ads_h100_v5"]`;
- `tools/trusted_compute_receipt.py` `BACKENDS` is unmodified, so this record
  can never be issued as a signed receipt, admitted to
  `TrustedComputeRegistry.lean`, or reach `accepted_run_certificate_sound`;
- the new trust profile `profiles/trust/attested_provenance_replicated.json`
  declares `evidence_class: local_unattested` and
  `production_hardware_evidence: false`, which is the honest classification
  for a single replica. Its `accepted_attestation_formats` list is
  deliberately **empty**: that field names *run*-evidence formats, and a
  Sigstore build attestation is not one. The repository's existing
  `create_run_bundle.validate_profile` invariant — a `local_unattested`
  profile must accept no attestation format — is what enforces this, and the
  first draft of the profile was rejected by it; and
- `tests/test_attested_provenance.py` asserts all three.

Two new target profiles, `replicated_public_cloud_cpu` and
`replicated_public_cloud_gpu`, describe ordinary non-confidential capacity.
Neither allows `hardware_attested` evidence. The GPU profile's description
states explicitly that it is not interchangeable with
`azure_ncc40ads_h100_v5`.

### 4.3 What the validator checks

`tools/tg_attested_provenance_record.py` rejects a record unless:

- every replica reports the same Merkle root and the same output digest, and
  both equal the record's claim;
- the replica count, distinct implementation count, distinct operator count,
  and distinct provider count all meet the record's own declared policy;
- at least one replica is marked third-party, when the policy requires one;
- every replica's build provenance was verified and has a transparency-log
  entry, when the policy requires them;
- two replicas naming the same `implementation_id` ran the same artifact
  digests, so "same implementation" is a fact rather than a label;
- replica identifiers are unique; and
- the record's `authority` block asserts nothing. Every field there must be
  `false`, and the schema pins each one to the constant `false`, so a record
  cannot even be written that claims Lean authority.

### 4.4 What replication does and does not establish

Establishes: k executions, whose binaries were built from a named commit by an
attested workflow, independently produced the same Merkle root.

Does not establish:

- **Correctness.** k agreeing runs of the same wrong algorithm agree on the
  wrong answer. Only layer 3 addresses this.
- **Anything about shared code.** If both implementations share the Merkle
  construction, the serialization, the certificate format, libc, or the same
  compiler, agreement says nothing about the shared part. The declared
  "independent implementations" must be audited for their shared surface, and
  that surface should be written down. This prototype does not measure it.
- **Resistance to a host that controls all k replicas.** See section 5.
- **Freshness.** There is no challenger-issued nonce in this model. Replicas
  can be replayed from stored outputs. A verifier-issued nonce per replica,
  with durable replay state, would be needed for an anti-replay claim, exactly
  as the repository already requires for DGX bundles.

## 5. What is lost versus confidential computing

Two things are genuinely lost, and calling them anything less would be
dishonest.

### 5.1 Resistance to a malicious cloud host

Under SEV-SNP plus vTPM, a compromised hypervisor cannot read or alter guest
memory undetected, and the AK quote binds the fresh challenge and the ordered
PCR 23 transitions to a hardware root of trust. Under attested provenance,
**there is no such property at all.** The host sees everything and can change
everything. The `authority` block of every record and validator output states
`resists_malicious_cloud_host: false`.

Replication weakens the *scope* of a host attack rather than the attack
itself: an adversary must now corrupt k replicas, across k accounts, across
providers, consistently enough that their Merkle roots still match. That is a
substantially harder operation than corrupting one VM. It is not a
cryptographic guarantee, and it degrades to nothing if the replicas share a
provider, an account, or an image.

### 5.2 The strongest form of resistance to author fabrication

This is the loss that matters most for a mathematical result, and it is the
one most easily glossed over.

Under the confidential path, a receipt is signed by a Managed HSM key over
independently appraised Azure/NVIDIA evidence, and the vTPM AK quote is
produced by hardware the author does not control. The author cannot
manufacture that evidence for a run that did not happen. The residual trust is
in the author's *registry admission decision*, which the repository already
documents as trust-equivalent to asserting that the receipts are valid.

Under attested provenance, an author who runs all k replicas themselves can
fabricate all k records. Every digest in the record is a number the author
typed. Sigstore signs the *binaries*, not the *run*. So the model's resistance
to author fabrication collapses to exactly one thing: **whether an independent
party ran one of the replicas and published the root themselves.**

That is a weaker guarantee than the confidential path in kind, not only in
degree. It is a social and operational guarantee rather than a cryptographic
one. It may still be adequate — for a mathematical claim that others are
invited to re-derive, an independent replication that anyone can repeat is
arguably the more convincing artifact — but the substitution must be made with
open eyes.

### 5.3 Lesser losses

- **Measured-runner causality.** The confidential path's dm-verity/IMA
  measured runner plus PCR 23 extension constrains which user-space code could
  have produced the output. Nothing here does.
- **Freshness and anti-replay.** The confidential path issues fresh
  off-VM challenges and burns them in a durable replay ledger. This model has
  no challenge, so a published root can be replayed.
- **Statement binding to an enclave.** The confidential path binds the exact
  run statement digest into the quote's qualifying data. Here, the binding
  between a statement and a replica is an ordinary assertion in a JSON file.

### 5.4 What is gained

- **Public checkability.** Anyone can rebuild the binaries and match the
  digests without an Azure subscription, a Managed HSM, or a
  confidential-capacity quota. The confidential path is checkable only by
  someone who can obtain and appraise Azure and NVIDIA evidence.
- **A transparency log.** Rekor gives an independent, append-only timestamp
  showing the binaries existed at a stated time, which is evidence the
  confidential path does not produce.
- **Replication as a scientific artifact.** For a mathematical result, "three
  independent groups got the same root" is a form of evidence a referee
  understands.

## 6. Mitigations

If the model is adopted, these are the mitigations that actually carry the
weight, in priority order:

1. **One replica run by a third party**, under their own account, with the
   root published by them, not relayed by the author. Without this, the model
   provides essentially no resistance to author fabrication. The validator's
   `require_third_party_replica` policy exists for this reason.
2. **Separate provider accounts, ideally separate providers**, so an account
   compromise is not common to all replicas. The validator enforces a minimum
   distinct-provider count.
3. **Two genuinely independent implementations**, with the shared code surface
   audited and documented, not merely two invocations of the same binary. The
   validator rejects a record where two replicas claim the same implementation
   but ran different bytes, and requires a minimum distinct-implementation
   count.
4. **Rekor timestamps** on every replica's binaries, recorded in the record so
   a reader can independently confirm the binaries predate the claimed run
   window. The validator can require a transparency-log entry per replica.
5. **Reproducible builds**, so a third party can confirm the attested digest
   corresponds to the reviewed source rather than trusting that it does. The
   `independent-rebuild` job is the continuous check that this stays true.
6. **Verifier-issued nonces**, if a freshness claim is ever wanted. This
   prototype does not implement them and does not claim freshness.

## 7. Re-examining the two premises behind the proposal

Both premises for dropping confidential computing were checked against the
repository and against Azure's public retail price API. Both are weaker than
stated, and the owner should see the numbers before deciding.

### 7.1 The cost premise

The sizing table in
[`AZURE_PERFORMANCE_SIZING.md`](AZURE_PERFORMANCE_SIZING.md#active-goldbach-1027-handoff-sensitivity)
shows $39,369 on demand against $8,004 spot for the 8-GPU Goldbach run. Both
columns are for the **same confidential SKU**, `Standard_NCC40ads_H100_v5`.
That gap is on-demand versus spot; it is not a confidential-computing premium.

Queried on 2026-07-26 in `eastus2` via
`https://prices.azure.com/api/retail/prices`:

| SKU | Confidential? | On demand | Spot | Low priority |
| --- | --- | ---: | ---: | ---: |
| `Standard_NCC40ads_H100_v5` | yes | $6.98 | $1.419034 | $1.396 |
| `Standard_NC40ads_H100_v5` | no | $6.98 | $5.0256 | $1.396 |
| `Standard_DC96as_v6` | yes | $4.358 | $0.805358 | $0.872 |
| `Standard_D96as_v6` | no | $4.358 | $0.805358 | $0.872 |
| `Standard_EC96as_v6` | yes | $5.722 | $1.057426 | $1.144 |
| `Standard_E96as_v6` | no | $5.722 | $1.057426 | $1.144 |

At list price, in this region, on this date: the confidential SKUs cost the
same on demand as their non-confidential counterparts, they do have published
spot rates, and the confidential H100 spot rate was in fact *lower* than the
non-confidential one. Dropping confidential computing does not, by itself,
reduce the VM bill.

Caveats that cut the other way, and that this table cannot settle:

- A published spot rate is not obtainable capacity. Confidential H100 quota
  and physical availability are the real constraint, and nothing here measures
  them. If confidential capacity cannot actually be got on spot, the practical
  cost difference is real even though the price sheet does not show it.
- Spot means eviction, and an evicted campaign must be replayed. The sizing
  document already warns that eviction and replay are not modelled.
- Prices vary by region and change over time. Re-run the queries before
  relying on them.

What the confidential path *does* cost, and the VM table does not show, is the
Managed HSM. Azure Key Vault HSM Pool `Standard B1` was $3.20 per hour in
`eastus2` on 2026-07-26, about $2,336 per 30-day month, billed for as long as
the receipt-signing key must exist — which, given the repository's immutable
key-version pinning requirement, is indefinitely rather than only during a
run. That, plus quota approval, appraiser and policy review, and the
engineering time in
[`AZURE_MANAGED_HSM_SIGNING.md`](AZURE_MANAGED_HSM_SIGNING.md), is where the
confidential path's cost actually sits.

So the honest form of the cost argument is not "confidential SKUs are
expensive". It is: *the confidential path carries a large fixed operational
cost and a capacity risk, and three replications on ordinary capacity may be a
better use of the same budget.* That is a defensible argument. It is a
different argument from the one in the proposal.

### 7.2 The `site-pin-needed` premise

`python3 tools/tg_azure_launch_preflight.py` reports `site_pin_needed: true`
for all 10 physical campaigns, and `cloud_launch_ready_campaigns: 0`. The
blocker is `usable_as_production_site_configuration`, which requires that a
site example contain no redaction marker at all.

Across the 15 site examples there are 59 marker instances. Exactly 15 of those
instances, each at a distinct path, are confidential-computing specific: the
four `managed_hsm` fields, the three `policies` entries (composite appraisal,
evidence verifier, measured runner), `worker.maa_attestation_url`,
`nvidia_policy`, `azure.image` (a private confidential-compute gallery image),
and four predecessor trusted-receipt pins. The remaining 44 instances, spread
over 30 distinct paths, are not: workload artifact digests,
`nvcc`/`host_cxx`/`python` toolchain digests, python-flint wheels,
build-admission status, `base_site` and `base_campaign` pins, PT21 runtime
pins, and child-identity commitments.

Every one of the 10 campaigns is blocked by at least one non-confidential
marker — in most cases `base_site.sha256` or `base_campaign.sha256`. So while
dropping confidential computing would remove those 15 markers and let the
shared operator site configuration shrink considerably, it would **not clear
`site_pin_needed` for a single campaign.** Those campaigns are blocked because
no operator has yet filled in real values for a real deployment, and that is
true under either trust model.

The premise that `site-pin-needed` "is largely CC deployment-identity pinning"
is therefore about a quarter right by marker count, and wrong about the
consequence.

## 8. Proposed Lean axiom (proposal only)

**Nothing in this section exists in the repository, and no Lean file was
modified.** It is written out so the owner can judge the shape of the
commitment before anyone writes it.

### 8.1 Shape

The premise must mirror the structure that makes `checkTrustedCompute`
reviewable: a decidable Boolean over a *closed*, source-pinned registry, with
no caller-supplied proposition anywhere.

```lean
-- PROPOSAL. Not present in the repository.

/-- One replica of a replicated campaign.  Every field is a digest or a
closed identifier; none is a proposition. -/
structure AttestedReplica where
  replicaId          : String
  operatorId         : String
  operatorThirdParty : Bool
  providerId         : String
  implementationId   : String
  sourceCommit       : Digest
  workflowRef        : String
  artifactDigests    : List Digest
  transparencyIndex  : Nat
  merkleRoot         : Digest
  outputHash         : Digest

structure ReplicationPolicy where
  minReplicas        : Nat
  minImplementations : Nat
  minOperators       : Nat
  minProviders       : Nat
  requireThirdParty  : Bool

/-- Source-admitted replication record, looked up by hash in a closed
registry exactly as a trusted-compute receipt is. -/
structure AttestedReplicationRecord where
  statement : RunStatement
  policy    : ReplicationPolicy
  replicas  : List AttestedReplica

/-- Decidable, kernel-checked premise.  It checks: exact registry membership
for `recordHash`; complete equality of the record's statement with
`statement`; that every replica reports `statement`'s output hash and the same
Merkle root; the four independence counts against the record's own policy; a
third-party replica when required; and that each replica's artifact digests
match the reviewed build-provenance pins for its `implementationId`. -/
def checkAttestedReplication
    (statement : RunStatement) (recordHash : Digest) : Bool := ...

/-- **PROPOSED SECOND EXECUTION AXIOM.**  Deliberately separate from
`accepted_run_certificate_sound` so that `#print axioms` distinguishes a
result resting on confidential-compute evidence from one resting on
replication agreement. -/
axiom accepted_replicated_run_sound
    {certificate : RunCertificate}
    (accepted :
      checkAttestedReplication certificate.statement
        certificate.replicationRecordHash = true) :
    certificate.ProducedOutcome
```

In English: *k independent runs of provenance-attested binaries, meeting the
declared independence thresholds and agreeing on Merkle root R, imply that the
registered invocation produced the bytes committed to by R.*

### 8.2 Design decisions and why

**A second, separately named axiom, not a new `Attestation` constructor.**
Extending `checkTrustedCompute` to accept a replication attestation would
silently weaken every existing theorem that cites
`accepted_run_certificate_sound`, because the same axiom name would then cover
two very different justifications. A separate axiom keeps the two evidence
classes distinguishable in `#print axioms`, lets
`tools/check_axiom_report.py` count them in separate allowlists, and makes a
downgrade visible in review. This costs the repository its "sole execution
axiom" property, and that cost should be stated plainly rather than hidden by
reusing a name.

**A closed source-admitted registry.** As with the receipt registry, editing
`AttestedReplicationRegistry.lean` would be trust-equivalent to asserting that
the replicas are genuine. That is the correct place for the trust to sit and
the correct thing to review.

**Independence thresholds inside the kernel-checked premise.** If the counts
were checked only by a Python tool, the axiom would be strictly weaker than it
reads. Putting them in the decidable Boolean means a record that fails them
cannot satisfy the premise at all.

**Refusal of L3 claims.** The premise should pin the reviewed SLSA level to
what the lane actually produces.

### 8.3 What this axiom would and would not be

It would be a **per-run** bridge, exactly like the existing one: it says
nothing about future executions, nothing about universal backend refinement,
and nothing about the mathematics. `Runs` still has to be turned into an
application claim by an ordinary Lean theorem, and the full result certificate
still has to be checked independently.

It would be **strictly weaker in justification** than
`accepted_run_certificate_sound`. The existing axiom's premise is discharged by
hardware evidence the author cannot forge. This one's premise is discharged by
an author-curated JSON record whose only unforgeable component is a signature
over *binaries*. The honest documentation sentence is: *this axiom trusts the
independence of the replica operators.*

Because of that, a reasonable adoption path is to require **both** where the
stakes are highest: a confidential receipt for the terminal aggregate, and
replication for the bulk campaigns. That keeps the unforgeable evidence at the
point where the result is committed, while letting the expensive,
capacity-constrained part run on cheap capacity with replication.

## 9. Threat model comparison

| Threat | Confidential path | Attested provenance + replication |
| --- | --- | --- |
| Bug in our own code | Not addressed | Partly addressed: two independent implementations disagree, unless the bug is in shared code |
| Silent hardware error over ~10^16 operations | Not addressed | Addressed: independent hardware must produce the same root |
| Malicious cloud host | Addressed by SEV-SNP/vTPM | **Not addressed.** Only made more expensive to exploit, by requiring k consistent compromises |
| Author fabricates a run | Addressed, up to registry-admission review | Addressed only by the third-party replica |
| Wrong binary executed | Measured runner plus artifact digests in the quote | Build attestation plus digest comparison; nothing binds the attested binary to the reported run |
| Replay of an old result | Fresh challenge plus durable replay ledger | **Not addressed.** No challenge exists |
| Result does not imply the theorem | Lean certificate layer | Lean certificate layer, unchanged |

Note the first two rows. The owner's observation is correct and worth
restating: confidential computing addresses neither the realistic failure mode
for a mathematical proof (our own bugs) nor the second one (silent hardware
error), while replication addresses both to a degree. That is the strongest
argument for this model, and it is stronger than the cost argument.

## 10. Files added by this prototype

| Path | Role |
| --- | --- |
| `.github/workflows/build-provenance.yml` | Build, attest, and independently rebuild; `workflow_dispatch` only |
| `tools/reproduce_attested_build.sh` | The single deterministic build definition |
| `tools/verify_build_provenance.py` | `verify` / `inspect-bundle` / `check-manifest`, machine-readable |
| `tools/tg_attested_provenance_record.py` | Replication-record audit CLI |
| `tg_verifier/attested_provenance.py` | Replication-record validator |
| `schemas/attested-provenance-record.schema.json` | The new record type |
| `profiles/targets/replicated_public_cloud_cpu.json` | Non-confidential CPU replica target |
| `profiles/targets/replicated_public_cloud_gpu.json` | Non-confidential H100 replica target |
| `profiles/trust/attested_provenance_replicated.json` | Trust profile; `local_unattested`, no hardware evidence |
| `examples/attested-provenance/replication_record.example.json` | Synthetic example; all digests are derived from labels |
| `tests/test_attested_provenance.py` | 26 tests, including the confidential-path containment assertions |

Nothing under `SparkInterval/`, `specifications/`, `azure/`, or `attestation/`
was modified, and no existing schema, profile, or tool was edited.

## 11. Open items and things not verified

- **No workflow has been run.** The workflow is syntactically valid
  (`actionlint` 1.7.7, clean) and structurally tested, but it has never
  executed. Whether `actions/attest-build-provenance` behaves as expected in
  this job layout is unverified.
- **`gh attestation verify` was never exercised against a real attestation.**
  The installed CLI is 2.45.0, which predates the command. The success path
  was exercised against a stub; the failure and unavailable paths were
  exercised for real. `inspect-bundle` *was* exercised against genuine
  GitHub-issued Sigstore bundles downloaded from the `cli/cli` repository,
  including a real `https://slsa.dev/provenance/v1` statement.
- **The container image is unverified in use.** The digest was resolved from
  Docker Hub, but no build has run inside it. Whether it provides an
  `x86_64-*` driver that satisfies the pure-entry target's guard is untested;
  the local host is `aarch64`, so that target was skipped in every local run.
- **Determinism was measured on one host only.** Repeated builds on this
  `aarch64` machine produced byte-identical manifests. Cross-host and
  cross-architecture reproducibility is what the `independent-rebuild` job
  exists to measure, and it has not run.
- **CUDA and Lean artifacts are not covered**, as stated in section 3.2.
- **The shared-code surface between the two implementations has not been
  measured**, and it is the main thing that limits what replication buys.
- **Azure prices were read once**, on 2026-07-26, in `eastus2`. Re-read them
  before relying on section 7.1.
