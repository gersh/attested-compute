# CPU/H100 cluster plan for the source atoms and lowered endpoint

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

`tools/tg_h100_cluster.py` is the inventory and deployment boundary for the
thirteen named ternary-Goldbach external atoms and the separate finite endpoint
used by the conditional `10^27` analytic crossover. It reports fourteen
reviewed workloads and eleven physical campaigns. Ten campaigns cover the
thirteen source atoms because one Hurst computation supplies four
Möbius-family atoms; the eleventh is the distinct lowered Goldbach campaign.

The cluster plan is not a certificate, attestation, Lean theorem, or axiom
discharge. A process exit of zero is never promoted to mathematical evidence.
Each campaign's own final receipt must exist and pass its semantic replay.

## Current execution boundary

The v3 manifest distinguishes three execution modes:

- `single_job`: the entire retained supervisor can safely run in one Slurm job;
- `manual_phase_dag`: independent arrays and reducers are implemented, but the
  generic one-job adapter cannot express their dependency DAG; and
- `shared_certificate_alias`: no arithmetic is rerun; the logical atom replays
  the certificate produced by another named atom's physical campaign.

Six source-scale campaigns are explicit manual DAGs. Consequently the
generated `slurm/submit.sh` exits with code 78 before calling `sbatch`. This is
intentional. It prevents a partial portfolio from being presented as an
all-atoms run and prevents a two-pass computation from being flattened into a
single unsafe job. The reviewed phase descriptions are emitted under
`manual-phase-dags/` for translation to the site's Slurm arrays and `afterok`
dependencies.

Each phase record materializes its own `backend_class`, CPU allocation, H100
count, array size, and optional concurrency cap. This matters for the mixed
Goldbach DAG: only the binary worker array requests H100s; the ladder and all
coordinator/replay phases are `cpu_exact_sidecar` work.

`slurm/submit-one.sh` remains usable for a `single_job` atom or a
`shared_certificate_alias`. It refuses a `manual_phase_dag` atom with code 78.
An alias additionally fails unless the shared certificate is already present.

## Thirteen source atoms plus one lowered endpoint

| Logical atom | Physical campaign | Mode | Backend and status |
|---|---|---|---|
| `ch25-a7-boundary` | `ch25-a7-boundary` | single job | CPU/FLINT replay of the retained full boundary transcript. |
| `ch25-psi-1e13` | `ch25-psi-two-pass-v1` | manual DAG | CPU primesieve + CRlibm, 320 worker groups retaining 100,000 summary leaves, reduction, then 320 groups retaining 100,000 independent replay leaves. |
| `platt-head-2e4` | `platt-head-2e4` | single job | Existing FLINT indexed-zero campaign for 22,492 positive zeros. |
| `platt-trudgian-rh-3e12` | `platt-trudgian-rh-3e12` | manual DAG | Native FLINT 3.6 Platt/Turing campaign: exact count and prefix, 1,236,316 independent ten-million-index shards, then Merkle finalization. Source-range complete in form but economically prohibitive. |
| `helfgott-prop-12-2-4` | `helfgott-prop-12-2-4-mpfr-v1` | manual DAG | 12,930 independent directed MPFR/GMP q-rank leaves, then a fixed-plan merge. |
| `cdem-squarefree` | `hurst-four-residuals-v1` | shared alias | Replays the certificate owned by `mertens-hurst`; it never starts another Möbius scan. |
| `cdem-table-abel` | `cdem-table-abel` | single job | Literal five-billion-step OpenMP producer and independent 1,000-chunk replay. |
| `mertens-hurst` | `hurst-four-residuals-v1` | manual DAG owner | CPU Hurst segmented-Möbius implementation: 320 deterministic worker groups retain 10,000 summary leaves, reduction, then 320 groups retain 10,000 replay leaves. |
| `ramare-zuniga-lemma-6-2` | `ramare-zuniga-lemma-6-2` | single job | Existing exact H100 R2Star prefix supervisor. |
| `helfgott-platt-theorem-4-1` | `helfgott-platt-goldbach-gpu-v1` | manual DAG | Hardened 65,536-leaf binary Goldbach prerequisite in 8,192 fixed scheduler groups (at most eight H100 tasks at once), independently overlapped with 320 native CPU ladder groups covering all 492,700 ranges, then a combined replay. Implemented but not run at source scale; the binary branch remains computationally expensive. |
| `platt-dirichlet-theorem-7-1` | `platt-dirichlet-theorem-7-1` | single job | Rigorous CPU/FLINT primitive-character contour fallback; depends on the q=1 zeta final receipt and remains unscaled. The separate optimized path now has directed large-q batches, a fully replayed 96-MB finite-recovery seed table, persistent residue composition/CRT-Bluestein/completed-L streaming, scalable root artifacts, and directed-disk small-q arithmetic. It is not the dispatched atom-level route because source-scale Hurwitz-lattice supply, source-wide interval usefulness, interpolation, exception, and Turing closure remain open. |
| `platt-little-mertens-2-11` | `hurst-four-residuals-v1` | shared alias | Replays the same four-residual Hurst certificate; no arithmetic scan. |
| `platt-little-mertens-stronger` | `hurst-four-residuals-v1` | shared alias | Replays the same four-residual Hurst certificate; no arithmetic scan. |
| `goldbach-finite-below-10pow27` | `ternary-goldbach-finite-below-10pow27-v1` | manual DAG | Separate 65,536-leaf binary campaign through `31250000000000000`, 7,106 n=45 ladder ranges, and a measured CPU finalizer for the exact finite claim through `10^27`. It is source-complete but unrun and is not the stronger Helfgott--Platt source computation. |

The workload backend counts are three H100, four CPU/FLINT, and seven exact CPU
entries. After the three Hurst aliases are deduplicated, the eleven physical
campaigns are three H100, four CPU/FLINT, and four exact CPU campaigns.

## Source-scale phase DAGs

The phase command arrays below are stored literally in `manifest.json` and in
the six files under `manual-phase-dags/`. `${TG_ARRAY_INDEX}` is a scheduler
binding, not a shell loop invented by the verifier.

### CH25 psi through `10^13`

1. `init` captures the shard executable, `reference/tg_psi_residual_shard.cpp`,
   and `specifications/PSI_UPSTREAMS.json`.
2. A 320-element summary worker array partitions the 100,000 fixed
   `10^8`-wide leaves by deterministic stride. Each worker uses up to 40 local
   subprocesses and still retains one receipt per leaf.
3. `reduce` derives every incoming Q64 prefix from the complete summary set.
4. A second 320-element worker array independently reruns all 100,000 leaves
   with their derived prefixes, again retaining one receipt per leaf.
5. `finalize` builds the affine/Merkle certificate.
6. `verify` replays every retained relationship.

Both arrays call `tools/tg_psi_residual_campaign.py run` with
`--worker-group-index ${TG_ARRAY_INDEX} --worker-group-count 320 --workers 40`.
The group helper proves a disjoint strided partition of the fixed plan; it does
not coarsen certificate leaves. The reducer must depend successfully on the
complete first array, and the second array must depend on the reducer. There is
no valid single-pass shortcut.

### Helfgott Proposition 12.2.4

1. A four-element array invokes
   `tools/tg_prop1224_mpfr_campaign.py run-worker-group` with 96 workers. The
   balanced groups retain all 12,930 fixed logical leaf receipts without
   coarsening the certificate plan.
2. `verify` requires every canonical receipt, restores fixed q-rank order, and
   checks the campaign merge.

The q=1 leaf is isolated by the immutable production plan. Every other leaf is
an independent complete-q range; array completion, not submission, is the
dependency for the merge.

### Platt--Trudgian zeta RH through `3000175332800`

1. `init` captures the native FLINT-Platt executable,
   `reference/tg_platt_zeta_shard.cpp`, and the pinned FLINT 3.6 manifest.
2. `count` records the exact multiplicity count
   `N(3000175332800)=12363153437138`.
3. `prefix` checks the ordinary low-index prefix through index 9,999.
4. A 1,236,316-element CPU/FLINT array covers the exact Platt index range in
   fixed ten-million-index shards, including the terminal sentinel geometry.
5. `finalize` orders every semantic receipt and builds the final Merkle root.

The H100 is unused by this host FLINT implementation. At the measured 91.38
zeros/second/process, the complete computation projects to about 13.4 ideal
years across the 320 CPU processes of eight NCC nodes. The phase DAG expresses
capability and exact coverage, not economic feasibility.

### Shared Hurst four-residual campaign

1. `init` captures the executable, `reference/tg_hurst_residual_shard.cpp`, and
   `specifications/HURST_MERTENS_UPSTREAM.json`.
2. A 10,000-element summary array scans the fixed `10^12`-wide source leaves.
3. `reduce` derives all four incoming states.
4. A 10,000-element array independently reruns every leaf.
5. `finalize` creates one certificate containing the Mertens, squarefree, and
   both little-Mertens residual checks.
6. `verify` replays the certificate.

The worker, supervisor, and closed Lean registry are protocol V2.  Its receipt
field `squarefree_threshold_endpoint_policy` must equal
`inclusive-value-and-right-limit-v2`: for a strict-real threshold `t`, the
worker checks the value at every `n >= t` and the right limit at `n+1`.
Pre-V2 receipts are rejected.  The kernel-checked
`HurstSourceSemantics.checked_*_real` theorems convert a full V2
`SourceScaleEvidence` value to all four ordinary real inequalities (including
the proved `6/π²` density enclosure); the cluster has not yet produced that
physical evidence.

The single certificate lives at
`$TG_RUN_ROOT/mertens-hurst/certificate.json`. The other three named atoms run
only `tg_hurst_residual_campaign.py verify` against that workspace. Four
independent Möbius scans are neither scheduled nor represented in the
manifest.

### Hardened binary Goldbach plus the prime ladder

1. `create-production-plan` binds the reviewed hardened source tree, exact
   executable SHA-256, and the fixed inclusive domain `[4, 4*10^18]`. This
   coordinator phase needs no GPU.
2. An 8,192-element H100 array calls `run-group`. Group `g` runs the eight
   immutable checkpoint leaves `g + k*8192` for `0 <= k < 8`, so the complete
   array covers exactly 65,536 leaves. `scheduler_shape` is
   `array[0..8191]%8`: the leaf count and task count are certificate geometry,
   while the `%8` cap is the eight-node concurrency limit.
3. `aggregate` checks all 65,536 receipts and exact coverage and builds their
   ordered Merkle aggregate; binary `verify` then revalidates the plan, every
   receipt, and that aggregate.
4. Independently of steps 1--3, `tg_goldbach_campaign.py init` creates the
   fixed 492,700-range prime-ladder workspace through
   `8.8756941456217735168*10^30`. Its empty dependency list is intentional, so
   the CPU and H100 branches may overlap.
5. A 320-element CPU array calls
   `tg_goldbach_ladder_native.py produce-group` with 40 local workers. Group
   assignment is formulaic and every range still produces its own immutable
   `.tggl`, range receipt, and native-producer receipt. The array has scheduler
   shape `array[0..319]%8`, corresponding to at most eight 40-core CPU nodes at
   once; it is not scheduled on the H100 partition.
6. `reduce-ranges` requires all range indices `0..492699`, independently
   replays every compact proof and coverage relation, and commits their fixed
   order in `ladder-aggregate.json`.
7. `combine-binary-and-prime-ladder` has two `afterok` predecessors: binary
   semantic replay and ladder reduction. Its measured CPU terminal replays
   both complete aggregates directly and writes `combined.json`; neither
   branch is accepted as evidence for the other.

The operator must bind `TG_GOLDBACH_SOURCE_ROOT`,
`TG_GOLDBACH_EXECUTABLE`, and `TG_GOLDBACH_EXECUTABLE_SHA256`. Production
workers enforce the H100 identity and memory policy retained by
`tg_verifier.goldbach_gpu_campaign`.

The ladder's compiled GMP producer sieves the paper's `k*2^52+1` form, and its
Python supervisor independently recomputes every Jacobi symbol and modular
power before retaining the existing campaign format. A native
`complete=false` record creates an exact general-prime obligation; the built-in
Pocklington path must prove it or the task fails closed. The combined receipt
is written only after both independent computations replay.

The five coordinator/replay phase types, all 320 native-ladder groups, and
the terminal now have closed source-reviewed Azure CPU materializers. Each
dependency edge carries a signed receipt and deterministic retained export.
The terminal assembler verifies all 8,512 signed producer receipts, matches
their ordered result hashes to the complete raw binary and ordinary/native
ladder receipt trees, and only then emits the handoff commitment. See
[`GOLDBACH_HISTORICAL_AZURE_MEASURED_DAG.md`](GOLDBACH_HISTORICAL_AZURE_MEASURED_DAG.md).
The historical H100 groups now have a campaign-specific source-reviewed
measured-job/projection/export materializer. It derives the projection from
the exact admitted job rather than accepting a digest chosen by the child
claim, and it checks every signed group result against the corresponding
eight-leaf retained export.

This full DAG is an implemented capability, not a practical runtime claim. The
2026-07-21 optimized high-range GB10 benchmark processed 600,000,000 evens in
a retained median 0.779701 seconds, roughly 769.5 million evens/s. Applying
that measured rate to approximately `2*10^18` source evens projects about
721,945 single-GPU hours, or 90,243 hours (10.3 years) over eight GPUs with
equal per-GPU throughput. This is a GB10 extrapolation, not an H100 benchmark;
the H100 speedup, multi-year availability, failures, durable receipt I/O, and
scheduler overhead remain unmeasured.

For the ladder branch, the local compiled-producer-plus-independent-replay
sample gave a lower-bound linear projection of about 12,700 aggregate core
hours. That is about 40 ideal hours on the planned 320 concurrent CPU cores,
but it omits extra rungs, general-prime fallback, durable multi-terabyte I/O,
and a complete-range measurement. No full binary leaf, ladder range, or source
campaign has been completed here.

### Distinct finite Goldbach campaign below `10^27`

The lowered campaign is not an alias or replacement for the preceding source
campaign. Its versioned identity is
`ternary-goldbach-finite-below-10pow27-v1`, and its closed registered invocation
is `goldbach10Pow27ProductionV1`.

1. `create-analytic-10pow27-plan` fixes the even domain
   `[4,31250000000000000]`, 65,536 binary leaves, and the lowered algorithm
   identity.
2. `init-ladder` fixes exactly 7,106 independent n=45 ranges and the scheduled
   ladder endpoint `1000080592252960768000000000`.
3. The two branches run independently as an 8,192-element H100 array and a
   320-element native CPU array, with at most eight tasks from either array
   active at once.
4. The binary aggregate is built and replayed, while the ladder reducer checks
   all range receipts in fixed order.
5. `tg_goldbach_10pow27_finalizer.py` replays both complete branches, writes the
   combined artifact, and only then immutably writes the exact registered
   result bytes `true`.

The semantic inventory row is deliberately disabled. The main portfolio can
see and schedule the complete DAG. Its seven CPU phase groups now have closed
source-reviewed materializers and signed retained-export handoffs; the
portfolio still reports `semantic_binding_disabled` and a failed production
budget gate. The CUDA worker array now has a closed per-group H100
measured-job/export factory for all 8,192 groups, including exact portfolio
challenge adoption and deterministic retained archive naming. Promotion still
requires a reviewed source realization, production attestation policy
and key, completed branch receipts, finalizer receipt, and an admitted registry
entry. The campaign document
[`GOLDBACH_10POW27_CAMPAIGN.md`](GOLDBACH_10POW27_CAMPAIGN.md) remains the
authority for its exact arithmetic and unrun status.

## Build and input prerequisites

Build the CPU source-scale workers in the directory bound by `TG_TG_BUILD`
(default `$TG_REPOSITORY/build/tg-production`) with their documented pinned
upstreams, including the optional
`sparkinterval-tg-goldbach-ladder-native` GMP target. Build the retained native
H100 runners in `TG_H100_BUILD` (default
`$TG_REPOSITORY/build/h100-native`). The per-campaign build recipes remain the
authority:

- `docs/algorithms/CH25_PSI_VERIFIER.md`;
- `docs/algorithms/PROP1224_H100_CPU_CAMPAIGN.md`;
- the Hurst campaign documentation and upstream manifest;
- the hardened GoldbachGPU fetch/prepare tools and
  `docs/algorithms/GOLDBACH_LADDER_CAMPAIGN.md`; and
- the existing R2Star, CDEM, zeta, and Dirichlet documentation.

The portable plan additionally requires:

- a clean reviewed Git checkout visible on every node;
- persistent shared `TG_RUN_ROOT` storage;
- the exact `TG_A7_TRANSCRIPT`;
- Python and the FLINT environment used by the retained supervisors;
- the site's H100, CPU/FLINT, and exact-CPU Slurm partitions; and
- Bash, `sbatch`, `flock`, and GNU `sync` for generated single-job adapters.

Inspect the non-executing report:

```bash
python3 tools/tg_h100_cluster.py --pretty capability
```

Create and verify a portable plan from a completely clean worktree:

```bash
python3 tools/tg_h100_cluster.py --pretty plan \
  /shared/tg/deployment \
  --repository /shared/src/gpu_prover
python3 tools/tg_h100_cluster.py --pretty verify \
  /shared/tg/deployment \
  --repository /shared/src/gpu_prover
```

Planning binds the commit OID, tree OID, Git object format, and SHA-256 plus
byte size of every tracked regular file. Modified, staged, or unignored
untracked files make planning fail. `verify` reconstructs every generated
adapter and every manual phase-DAG file byte-for-byte.

The deployment contains:

```text
manifest.json
manifest.sha256
manual-phase-dags/
  ch25-psi-1e13.json
  platt-trudgian-rh-3e12.json
  helfgott-prop-12-2-4.json
  mertens-hurst.json
  helfgott-platt-theorem-4-1.json
  goldbach-finite-below-10pow27.json
slurm/
  common.sh
  submit.sh                 # deliberately exits 78
  submit-one.sh             # single jobs and aliases only
  jobs/                     # eight non-DAG logical adapters
```

## Honest performance status

These are planning measurements, not completed source certificates:

- the new psi worker projects about 7.2 hours for both passes on the local
  20-core host and roughly 0.5--2 hours across eight 40-core NCC nodes;
- Proposition 12.2.4 empty-row slices project roughly 61--73 single-core
  hours per replay. The production model keeps a wider 105.6--640 core-hour
  band per replay; the two-replay protocol is therefore 0.55--3.34 compute
  hours across four 96-core DC96as_v6 nodes before Azure overhead;
- the two-pass Hurst campaign has a broad eight-NCC estimate of roughly 2--22
  days and is the dominant feasible CPU campaign.  A separate exact
  eight-worker affine H100 route is implemented: the current `191.737 ms`
  per 100-million-row complete-device-work measurement on GB10 gives
  `665.687` equal-GB10 hours, while an explicitly unmeasured `12.3x`
  H100 sensitivity gives `54.121` arithmetic-only hours for the terminal
  H100 stage
  (`432.967` node-hours).  This is not target-H100 evidence or a production
  budget claim, and it excludes the CPU prefix through `10^12` and handoff;
- GoldbachGPU remains a long source-scale campaign: the optimized GB10 rate
  gives the approximately 721,945 single-GPU-hour / 90,243 eight-GPU-hour
  equal-throughput projection above, while no production H100 calibration has
  yet been measured; the native ladder is now parallelized but only sampled;
- the separate `10^27` binary profile has a 49--705 hour eight-GPU sensitivity
  envelope across the retained 14.3x--1x throughput factors, with roughly
  183--577 projected ladder core-hours; this is not an H100 benchmark and no
  source-scale receipt exists. A newer unpromoted wheel-47, warp-tail,
  shifted-coverage, and packed-count prototype sustained 20 billion exact
  terminal evens in median 2.35908 seconds on GB10. Repeating the largest
  observed initialization per leaf projects 64.97 hours and $3,627.79 on
  demand for eight equal-throughput GB10 GPUs. A unified 20-billion-even diagnostic
  compared every unfiltered/filtered sieve word, original/shifted coverage
  bit, and byte/packed missing count. Its source and binary are not admitted,
  so it does not replace the retained production profile; and
- the native FLINT-Platt zeta campaign is range-complete in form but projects
  to about 13.4 ideal years on eight NCC nodes, while the literal Dirichlet
  fallback remains unscaled. The optimized Dirichlet components now include
  a persistent large-q process graph, scalable roots, directed-disk small-q
  arithmetic, and a fully replayed finite-recovery seed table that reduces
  the fused boundary from 18.264 PB to 5.180 PB. An authenticated 125-GiB
  t-major cache contract and exact broadcast schedule remove the host-side
  lattice repetition. A direct `TGDLTMB1` source now removes q-major
  descriptors/frames as well, gives an exact 339.469-GB binary input, and has
  a bounded one-upload row-resident CUDA KAT, but the cache is not populated
  and the path is not source-scale measured.
  A source-wide supervisor plan now pins a target roster of 76,770,217
  fixed-q FFT batches. A bounded-memory shared-row spool now authenticates
  each lane row once and emits that exact q-contiguous run roster without
  copying row payloads per modulus; the CUDA composition component consumes
  it, but the multi-q FFT/completed-L pipeline does not. A streaming catalog
  parses and receipt-binds the
  exact 292,500 root artifacts but does not mathematically replay their
  derivation. A bounded fail-closed adapter now freshly replays each typed FFT
  bundle in deterministic target order and matches its `TGDLATI1` lattice
  payloads to the authenticated t-major rows. None of these components has run
  at source scale. Spool-output-to-FFT/typed-bundle wiring and a
  t-major-compatible zero-state path remain unimplemented. They
  also do not solve the source-wide width boundary, the
  uniform interpolation proof, or the theorem-level bridge for the corrected
  reflected Turing upper bound.

Do not infer completion from these estimates or from the existence of a DAG.

## Trust policy

Every manifest entry has `scope: full_source` and `sample: false`. Bounded-test
switches and work-count pause switches are rejected. Array indices are fixed by
the campaign plans; missing, duplicated, reordered, or range-substituted
receipts fail in the atom-specific mergers.

The remaining external-computation boundary includes FLINT/Arb, MPFR/GMP,
CRlibm, primesieve, CUDA hardware and binaries, compilers, Python, the operating
system, scheduler translation, and the chosen Lean realization. Retain the
manifest, phase DAG, captured executable/source identities, every leaf receipt,
final replay output, scheduler logs, toolchain inventory, and attestation
artifacts together for audit.
