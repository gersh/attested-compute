# Azure ternary-Goldbach portfolio orchestration

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../attestation/phala/README.md`](../attestation/phala/README.md).

`tools/tg_azure_portfolio.py` is the local, fail-closed control plane between
the portable campaign topology in `tg_verifier/h100_cluster.py` and a
backend-specific one-VM production operator such as
`azure/h100_production_orchestrator.py`. It performs no Azure mutation.

The layer solves a narrower problem than either neighbor:

- it validates the complete ten-source-campaign plus distinct lowered
  `10^27` capability inventory, then compiles one exact source-owned theorem
  profile into a deterministic dependency DAG;
- it preserves every explicit manual phase array instead of flattening it
  into a misleading one-process command;
- it routes each phase independently to an Azure SEV-SNP CPU receipt backend
  or the NCC H100 receipt backend;
- it creates a distinct off-VM challenge, directory, workspace, and canonical
  handoff config for each shard only when its predecessors are complete; and
- it resumes exclusively from hash-checked canonical state and signed
  receipts.

A portfolio plan, shard config, successful process, or operator state is not
mathematical evidence and never discharges a Lean atom. Every command reports
`accepted: false` for that reason.

## Exact completion profiles

The portfolio specification must select one `completion_profile`. It is not a
caller-provided campaign list. `tg_verifier/azure_portfolio.py` owns three
exact profiles and independently compares the complete manifest's physical
campaign IDs and logical-claim partition with a source constant before it
schedules anything:

| Profile | Purpose | Physical campaigns |
|---|---|---:|
| `capability-inventory-v1` | Audit every source and alternate capability; deliberately schedules both finite routes | 11 |
| `all-source-retirement-v1` | Retire all 13 paper-source atoms using the historical Helfgott--Platt endpoint | 10 |
| `lowered-10pow27-theorem-completion-v1` | Complete the theorem using the proved `10^27` analytic crossover and distinct lowered finite certificate | 10 |

The lowered profile contains every campaign in the all-source profile except
`helfgott-platt-goldbach-gpu-v1`, and adds
`ternary-goldbach-finite-below-10pow27-v1`. It does not derive that set by
deleting whatever campaign happens to have a matching name in an editable
manifest. Its exact ten campaign IDs are source owned. The planner also walks
the full logical dependency edge inventory and refuses the profile if a
selected campaign depends on an excluded one.

Every excluded capability must retain an explicit disabled row in the pinned
semantic-binding inventory. A missing or enabled excluded row blocks
initialization. Thus the historical endpoint cannot disappear silently, and
the lowered certificate is never relabelled as the stronger historical
source claim. Inspect the exact sets without a portfolio spec with:

```bash
python3 tools/tg_azure_portfolio.py --pretty profiles
```

## Current production status

The checked-in semantic inventory is
`specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json`. Its eleven rows
are deliberately explicit. `cdem-table-abel` is an enabled terminal:
it binds the Azure SEV-SNP CPU invocation `cdemTableAbelProductionV2` to
`SparkInterval.Execution.SignedResultCertificate.certifyCDEMTableAbel`. That
theorem returns `CertifiedCDEMTableAbel`, including the exact duplicated
`CDEMAbelSource.SourceClaim`. The reviewed terminal argv must also contain
exactly one adjacent `--registered-result-output` and
`${TG_RUN_ROOT}/cdem-table-abel/registered-result.txt` pair. The producer
writes that canonical natural only after both the full scan and independent
all-chunk replay succeed; omitting or changing the pair disables the semantic
terminal.

`ramare-zuniga-lemma-6-2` now stages the exact H100 invocation
`ramareZunigaLemma62ProductionV1`, its source-claim theorem, and the terminal
result path, but remains disabled. The supervisor exclusively emits the four
canonical bytes `true` only after rechecking a gap-free chain through
`21,000,000,000`, a nonzero final chain hash, the retained minimum endpoint
guard, and a separate CPU implementation's reconstruction of every factor,
directed-arithmetic, prefix, and squared-envelope row. The specialized H100
materializer now creates an absent fixed work directory, builds the exact
sm_90 runner and CPU checker from a pinned source/compiler/runtime closure,
forbids resume or imported predecessor state, and retains a canonical full
chain archive which a separate trace-verifier invocation replays, including
the complete CPU arithmetic pass. The
portfolio routes this exact terminal through
`tools/tg_azure_h100_r2star_materializer.py`; any drift falls back to no
production route rather than the generic H100 operator. It still does not
prove the CUDA recurrence-to-
Mathlib refinement, and no target-H100 pilot, complete 21-billion run, production
receipt, or semantic admission exists.

`claude_math` now imports this exact proposition and proves
`CDEMAbelSource.SourceClaim ↔ ReproducibleTableAbelVerifierOutput` directly by
definition, then threads the receipt-backed form into its Section 2.4
provider. No production receipt is present, so the portfolio still reports
zero actually discharged Lean atoms; the remaining CDEM trust is execution,
not a source/consumer statement mismatch.

The `hurst-four-residuals-v1` row is pre-populated with the sound V2 closed
invocation, realization identifier, and theorem name, but has `enabled:false`.
The corrected `hurstSharedFourResidualProductionV2_realClaims` theorem is
present and exposes the five ordinary real inequalities directly, including
the Lean-proved density enclosure. Its receipt importer, exact semantic-replay
command, and exclusive terminal `true` writer are wired; the row remains in
the reviewed pending-shape catalog rather than the enabled source-known
catalog until a complete run and receipt are reviewed. The
`ch25-psi-two-pass-v1` row is likewise staged against
`ch25PsiLemma92ProductionV1_sourceClaim`: its exact endpoint and real-slab
reduction, closed invocation, receipt-import identity, and exclusive terminal
`true` output are implemented. Ordinary Lean now also proves that the
canonical prime-power fold realizes Mathlib's
`Chebyshev.psi`. Its retained C++ rows are not yet reviewed as a realization
of `GapSourceScaleEvidence` (directed prime-log semantics, exact event-gap
coverage/state constancy, and integer boundary guards), and no real retained
source-height receipt chain exists, so the row remains disabled. A closed
six-phase/644-job CPU materializer now exists for producing that chain. The
`helfgott-prop-12-2-4-mpfr-v1` row now stages
`helfgottProp1224ProductionV1`, realization identifier
`helfgottProp1224SourceClaimV1`, and
`helfgottProp1224ProductionV1_sourceClaim`. Its terminal merge has the exact
registered-result path and an exclusive `true` writer, but the row remains
disabled pending the full two-replay Azure run, receipt review, and review of
the MPFR/GMP-to-exact-real source realization. The Platt head also has a
closed one-job CPU materializer which performs the complete count/isolation
replay and literal-table emission. Its exact registered invocation,
conditional source-claim theorem, and exclusive terminal
`${TG_RUN_ROOT}/platt-head-2e4/registered-result.txt` contract are now staged,
although its semantic row remains disabled and no production receipt exists.
CH25 Lemma
A.7 likewise has a closed one-job materializer with two complete 16,191-leaf
FLINT replays; its semantic row remains disabled pending realization review
and a production receipt. The lowered
`ternary-goldbach-finite-below-10pow27-v1` row stages the exact
`goldbach10Pow27ProductionV1` invocation, source-claim theorem, and terminal
registered-result path, but remains disabled until source-realization and
receipt review. The exact reference PT21 computation is now routed as five
Azure CPU phase groups: initialize, exact multiplicity count, ordinary
prefix, all 1,236,316 formulaic index shards, and Merkle finalization. Its
materializer authenticates every predecessor export through its signed
production receipt and refuses the incomplete optimized H100 worker/finalizer.
This is an unscaled package capability, not a completed run: it has no
production receipt, its Lean endpoint/Hardy-Z/Turing realization is not
proved, and its semantic row remains disabled. Its Merkle finalizer now has
the exact exclusive registered-result contract staged alongside the
conditional invocation/theorem identity. See
[the PT21 materializer boundary](algorithms/PLATT_PT21_AZURE_CPU_MATERIALIZER.md).
The Dirichlet terminal postcheck likewise stages its exact invocation,
conditional two-branch theorem, and exclusive registered-result path; the
postcheck emits no `true` until q=1, every q>=2 checker, and the exact source
composition replay successfully.

Consequently, all ten named physical campaigns have reviewed terminal
registered-result contracts (`10/10`), and the distinct lowered alternate has
one as well. This is a topology/review milestone only: ten semantic rows
remain staged-disabled, the audit reports zero analytic realizations and zero
production runs, and only CDEM is enabled.
The control plane may now persist this source-closed topology as local state.
That initialization is not an operator handoff, a cloud launch, a receipt, or
theorem admission.

There are two distinct remaining gates:

1. `azure/cpu_production_orchestrator.py` is the target stateful CPU operator.
   The CDEM terminal now has a closed no-shell materializer which emits an
   operator-validated measured-job campaign and preserves the original
   portfolio challenge. The CH25 psi DAG also has a closed materializer for
   all 643 operational jobs and its one semantic replay job. Availability is
   group-specific: CDEM, psi, the single Platt-head zeta sidecar, and the A.7
   boundary replay are routed. The lowered Goldbach campaign's seven CPU phase
   groups are also routed through a closed 326-job materializer with signed
   predecessor/export handoffs. Hurst's six groups are routed through its
   closed 644-job materializer. The source-height PT21 CPU groups are routed
   through the exact unscaled five-phase materializer, including complete
   formulaic shard coverage and finalizer handoff. The historical Goldbach
   route now has closed factories/materializers for its five coordinator and
   replay phase types, all 320 native-ladder groups, and its registered CPU
   terminal. Signed retained exports are checked at every dependency edge,
   and the terminal assembler binds all 8,512 signed producer receipts to the
   complete raw branches. Its H100 array is now routed through an exact
   campaign-specific 8,192-group measured-job/export materializer whose
   execution-projection digest is independently derived from the admitted
   job. The lowered binary H100 array is separately routed through its exact
   8,192-group measured-job/export materializer, and the Ramaré--Zúñiga
   terminal is routed through its fresh-workspace H100 materializer; no
   production group has run.
2. The source sizing model's hard operator-handoff gate currently fails. The
   selected price class must have a source-closed, target-SKU-calibrated route
   for every campaign in the selected exact profile, using high work/cost
   endpoints no greater than 168
   hours and USD 10,000. The caller cannot loosen either limit. Its current
   eleven-campaign inventory contains a separate exact row for
   `ternary-goldbach-finite-below-10pow27-v1`. That row is source-count exact
   but remains an uncalibrated GB10-to-H100 sensitivity, so it fails the hard
   production budget gate instead of disappearing as `production_sizing_absent`.
   The planner reconstructs the source sizing routes and re-runs the optimizer
   for the selected profile, so an excluded historical campaign cannot block
   or subsidize the lowered profile's gate.

This is intentional fail-closed behavior. Supplying a paper citation, typing
an arbitrary Lean declaration name into JSON, marking a process successful,
or manually advancing state cannot make an operator handoff preparable or
grant theorem authority.

## Canonical inputs

The portfolio specification is validated against
`schemas/azure-tg-portfolio.schema.json`. It binds:

- one canonical `h100_cluster` manifest by absolute path, size, and SHA-256;
- the exact clean Git repository commit/tree and complete tracked-file closure
  already embedded in that cluster manifest;
- the semantic inventory and verifier-key manifest by repository-relative
  path, size, and SHA-256 within that same closure;
- an off-repository run root;
- one challenge lifetime no greater than seven days; and
- an explicit `pay_as_you_go` or `spot` production price class; and
- one exact source-owned `completion_profile`.

`examples/trusted-compute/azure_tg_portfolio.redacted.json` shows the exact
shape and selects the lowered theorem-completion profile. Its zero pins and
`replace-*` identifiers are placeholders and cannot pass runtime validation.

The semantic inventory has its own schema at
`schemas/azure-tg-semantic-bindings.schema.json`. An enabled semantic row is
accepted only when all of the following agree exactly:

1. the physical campaign ID;
2. an invocation supported by the source-pinned trusted-compute importer;
3. that invocation's required receipt backend, if fixed; and
4. a source-known concrete Lean realization for precisely that
   campaign/invocation pair; and
5. a source-reviewed exact terminal argv argument/path pair which writes the
   registered result artifact consumed by that invocation.

Every row has an explicit Boolean `enabled` field. A disabled row remains a
reported semantic-admission gap. It may nevertheless supply a
`terminal_receipt_contract` for execution only when its complete identity
matches the source-owned pending catalog, its invocation is registered for
the terminal backend, and its exact adjacent result argument/path pair occurs
once in the terminal argv. For a selected campaign, a null, partial, unknown,
backend-mismatched, or path-mismatched row blocks even local source
initialization. The staged contract omits the Lean theorem and explicitly carries
`semantic_admission_enabled: false`.

The fourth and fifth checks are separate from the JSON file. A clean-repository
JSON edit alone cannot assert that a Lean theorem exists or that a measured job
emits its input bytes. Moving a staged shape into an execution contract never
moves it into `SOURCE_TG_REALIZATIONS`.

The deterministic output conforms to
`schemas/azure-tg-portfolio-plan.schema.json`. The complete capability profile
has 41 phase groups, while the lowered theorem-completion profile has 33.
Large arrays remain compact groups—for example, the zeta
campaign retains 1,236,316 indexed shards—so planning does not allocate a
million-entry JSON document.

## Backend and dependency model

The mapping is fixed in source:

| Cluster backend class | Receipt backend | Production operator |
|---|---|---|
| `h100_cuda` | `azure_ncc40ads_h100_v5` | existing one-VM H100 operator |
| `cpu_flint_sidecar` | `azure_sevsnp_cpu` | unavailable by default; the exact `platt-head-2e4::single-job` and `ch25-a7-boundary::single-job` groups have closed materializers |
| `cpu_exact_sidecar` | `azure_sevsnp_cpu` | unavailable by default; exact CDEM, CH25 psi, Hurst, Proposition 12.2.4, both raw-Dirichlet groups, and all seven lowered-Goldbach CPU phase groups have closed materializers |

Routing occurs per phase, not merely per physical campaign. Both Goldbach
campaigns therefore send their distinct CUDA checkpoint arrays to NCC H100
while their plan, GMP ladder, reducers, replay, and terminal phases stay on
CPU. Their campaign IDs, domains, ladder exponents, and final artifacts never
interchange.

An edge means `all_shards_have_verified_receipts`; it never means “the prior
process exited zero.” Phase dependencies are copied exactly from the reviewed
cluster plan. Cross-campaign dependencies are added deterministically. In
particular, the complete zeta terminal precedes the Dirichlet root. Shared
Hurst logical atoms remain aliases of one physical terminal rather than four
duplicate computations.

Only separately reviewed terminal receipts can later enter the Lean semantic
boundary. Nonterminal signed receipts provide authenticated operational
provenance and resume ordering; the registered terminal algorithm must replay
and validate all upstream artifacts that its campaign meaning depends on. A
reviewed staged invocation/result contract is enough to run that algorithm and
validate the returned terminal result. It is not enough to admit its theorem:
the portfolio has no promotion command, every state/status remains
`accepted: false`, and `lean_atoms_discharged` remains zero after receipt
recording.

## Inspecting the current plan

First generate and verify a cluster deployment manifest from a clean reviewed
checkout, as documented in `docs/algorithms/H100_TG_CLUSTER.md`. Construct a
canonical portfolio spec with exact pins, then run:

```bash
python3 tools/tg_azure_portfolio.py --pretty validate /operator/portfolio-spec.json
python3 tools/tg_azure_portfolio.py --pretty plan /operator/portfolio-spec.json
```

`validate` lists every current gap and the separate
`local_initialization_ready`, `operator_handoff_ready`, and
`semantic_admission_complete` states. `plan` emits the complete group DAG,
backend decisions, cost/time gate, terminal receipt contracts, optional
semantic bindings, and promotion policy. Neither command writes local state or
calls Azure.

## Local initialization, resume, and shard preparation

Once every source-contract gate is genuinely closed, local initialization is
allowed even while the budget and semantic-admission gates remain false:

```bash
python3 tools/tg_azure_portfolio.py init /operator/portfolio-spec.json
python3 tools/tg_azure_portfolio.py status /operator/portfolio-spec.json

python3 tools/tg_azure_portfolio.py prepare-shard \
  /operator/portfolio-spec.json \
  --group helfgott-prop-12-2-4-mpfr-v1::mpfr-shards \
  --shard-index 0
```

Initialization writes immutable `portfolio-plan.json` and an initially empty
canonical state file under the run root. It never creates an operator config or
contacts Azure. `prepare-shard` is stricter: it refuses unless the unchanged
hard cost/time gate passes, and also refuses an out-of-range index or incomplete
predecessor, then creates:

```text
run-root/
  shards/<full-group-sha256>/<nine-digit-index>/
    challenge.json
    shard-config.json
    workspace/
```

The config binds the plan hash, campaign/phase/group IDs, resolved array
index, argv array, remaining environment names, exact backend, operator
adapter, optional closed materializer adapter, challenge path/hash/nonce/expiry,
workspace, non-authorizing terminal receipt contract, and optional enabled
source semantic binding. It always says `semantic_admission_enabled: false`.
Parallel shards never share these files or paths.

Calling `prepare-shard` again returns the byte-identical existing handoff. It
does not rotate the nonce. If an unfinished challenge has expired, automatic
retry is refused because the attempt might have run; an operator must reconcile
the external state before a future explicit retry design can be safe.

The shard config is a portfolio-to-operator handoff contract, not itself an
Azure campaign. For CDEM, psi, the Platt head, or A.7, the named materializer consumes that
immutable handoff, checks the exact source-known argv and dependencies, and
emits a fully pinned CPU campaign accepted by the CPU operator. The closed
factories have no caller-selected executable field. Psi additionally requires
the exact signed predecessor receipts and hash-matching retained exports.
The Platt-head materializer additionally requires complete pinned FLINT and
python-flint source trees and the exact x86-64 runtime wheel. A.7 requires the
same runtime/source closure plus its exact retained artifact. Other groups
remain handoffs only. This portfolio command intentionally has no `run`,
`deploy`, or generic shell-command operation.

## Recording progress

The only completion operation accepts a trusted-compute receipt:

```bash
python3 tools/tg_azure_portfolio.py record-receipt \
  /operator/portfolio-spec.json \
  --group GROUP_ID --shard-index INDEX --receipt /operator/returned-receipt.json
```

The receipt is parsed canonically, signature-verified under the exact pinned
key manifest, checked against the deterministic CPU/NCC route and retained
challenge, and snapshotted immutably. A staged or enabled terminal receipt must
additionally match the complete registered invocation/result contract. Status
re-verifies the stored
challenge, recomputes the entire shard config, and re-verifies every receipt;
editing state plus recomputing local file hashes cannot manufacture progress.

There is no manual-completion command. There is also no automatic challenge
replacement, semantic “override,” partial/sample promotion, or process-exit
promotion.

## Remaining deployment and proof work

Every phase group in the ten-campaign source-retirement profile now has a
closed campaign-specific materializer route. The checked-in redacted site
templates cover the common CPU operator, every specialized CPU wrapper, and
every H100 wrapper. Source-closure tests launch each measured entry point from
only the files declared by its factory, and the Azure unit suite exercises the
operator, materializer, challenge, replay, and fail-closed seams without doing
source-scale arithmetic.

That is package readiness, not a completed Azure run or theorem authority.
Production still requires:

- replacing every redacted site value with reviewed x86-64/H100 compiler,
  runtime, image, policy, appraiser, network, and immutable Managed HSM pins;
- target-SKU calibration and a reviewed budget decision. The literal PT21 and
  historical Goldbach reference routes are complete but economically
  impractical, while the optimized PT21 and Dirichlet routes still have
  source-wide algorithm/analytic closure gaps;
- an x86-64 materialization smoke test followed by one small confidential-VM
  end-to-end pilot through attestation, off-VM appraisal, HSM signing, receipt
  return, and portfolio recording before any source-scale launch;
- complete artifact-consuming Boolean finalizers and ordinary Lean
  parser/checker-to-source theorems. A receipt hash or the current small job
  descriptor is not a substitute for the retained mathematical certificate;
- reviewed production receipts and post-run installation of their exact
  deployment pins. The checked-in registry deliberately remains empty; and
- production Azure quota/capacity, durable replay storage, authenticated
  ingress/egress, and operator reconciliation procedures.

Until the budget/calibration and deployment inputs are present,
`prepare-shard` and therefore every portfolio-derived operator handoff remain
intentionally refused. Local initialization may retain the deterministic,
schema-checked plan, but it cannot spend cloud resources. Until reviewed
receipts and the separate source-admission work are present, semantic
admission remains false and the portfolio cannot discharge a Lean atom.
