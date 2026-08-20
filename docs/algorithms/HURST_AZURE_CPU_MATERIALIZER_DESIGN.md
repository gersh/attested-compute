# Closed Azure CPU materialization for the Hurst V2 campaign

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../../attestation/phala/README.md`](../../attestation/phala/README.md).

Status: terminal byte contract, 320-group partition, source-closed Azure CPU
phase materializers, and portfolio-catalog routing are implemented.
Confidential-VM calibration and the production run remain pending.

## Required end-to-end claim

Only the final signed receipt may cross into Lean.  It must match the closed
invocation `hurstSharedFourResidualProductionV2`, whose fixed input is the
literal range `[1, 10^16 + 1)`, whose result is exactly the four bytes `true`,
and whose ordinary Lean consequence is
`HurstSourceSemantics.RealSourceClaims`.

The arithmetic after that execution fact is already kernel checked.  In
particular, Lean proves the prefix rewrites, source-range coverage projection,
squarefree real slabs (including both V2 threshold endpoints), directed Q96
little-Mertens projection, and the enclosure of `6 / pi^2`.  The external
boundary is therefore a physical statement about one exact full-range run,
not an unbounded analytic estimate.  The registered `Runs` branch exposes
`LocalSourceScaleEvidence`: literal range, zero root, primitive
Möbius/squarefree/Q96 row deltas, and local integer guard decisions.  Lean
derives global prefix identities along the actual checked chain.  It does not
trust the older, overly broad assertion that every state in an affine guard is
the unique global prefix.

## Why the CDEM single-job factory cannot be reused

The reviewed Hurst plan has 10,000 summary leaves, one ordered reduction,
10,000 independent verification leaves, one finalizer, and one semantic
replay.  A single Azure SEV-SNP job is not a credible substitute: the current
eight-node estimate is 2--22 wall days, while a challenge may live for at most
seven days.

The current CPU operator also requires every measured job to match one
registered Lean invocation.  Hurst leaf and reducer results are dynamic and
are not the full Hurst theorem.  Pretending that any of those jobs realizes
`hurstSharedFourResidualProductionV2` would be a semantic type error.  Adding
20,000 caller-populated Lean propositions would recreate the arbitrary-`Prop`
weakness that the closed registry was designed to prevent.

## Production shape

The fixed 10,000-leaf mathematical plan is retained.  The scheduler now
partitions it into 320 deterministic strided worker groups per pass.  Group
`g` contains precisely the indices

```text
g, g + 320, g + 2*320, ... < 10000.
```

This changes launch, attestation, and HSM overhead only.  Every leaf keeps its
own row hash, delta, exact range, and immutable receipt.

Inside each 40-vCPU group job, the reviewed supervisor runs at most two leaf
processes concurrently with 20 OpenMP threads apiece.  It discovers the
process CPU affinity, assigns the two children disjoint explicit
`OMP_PLACES`, and rejects a worker/thread product larger than the available
CPU set.  A completed slot is reused only after its prior child exits.  Thus
the optimization cannot oversubscribe the measured worker or merge leaf
receipts; it changes scheduling only.  The exact two-by-twenty setting remains
subject to a target-SKU pilot.

```text
initialize
    |
320 summary groups  -- each returns a bundle of its individual leaf receipts
    |
ordered reducer     -- reconstructs all 10,000 incoming four-coordinate states
    |
320 verify groups   -- independently resieve; row hashes and deltas must match
    |
finalize            -- gap-free affine/Merkle certificate
    |
semantic terminal  -- replays every retained relationship; exclusively emits true
    |
one registered Hurst receipt -> one Lean execution axiom instance
```

## Two receipt classes

The scalable design needs two explicitly different classes.  They must not be
represented by a Boolean flag that a caller can freely change.

1. **Operational phase receipt.** It authenticates an exact closed phase job,
   challenge, artifact closure, input bundle, output bundle, and successful
   completion.  It is scheduler evidence only.  Its importer must not generate
   Lean, update the trusted-compute registry, or invoke
   `accepted_run_certificate_sound`.
2. **Semantic terminal receipt.** It is accepted only for the exact Hurst V2
   registered invocation and exact result `true`.  The terminal executable
   consumes and rechecks the complete operational artifact graph.  This is the
   sole receipt from this campaign that may generate a Lean theorem.

A distinct operator configuration kind (or a sum-typed `review_mode`) should
enforce this split.  Operational mode must omit `lean_review` entirely and
must have no code path that invokes `generate_trusted_compute_lean.py`.

## Immutable artifact handoff

Recording only a signed receipt is insufficient: the next phase needs the
actual producer bytes.  For each completed phase group, the portfolio state
must retain an immutable pair:

```text
signed trusted-compute receipt
returned output bundle whose SHA-256 equals the receipt output hash
```

The output bundle is canonical and contains a sorted manifest plus the exact
leaf JSON bytes.  A downstream materializer accepts it only after replaying the
receipt signature, backend, nonce, job binding, output hash, group identifier,
and shard/group index.  Reducer and terminal inputs are deterministic Merkle
manifests over those accepted bundles.  Missing, duplicate, overlapping, or
out-of-plan indices fail before execution.

The terminal closure must contain one canonical source/dependency closure
manifest with statement role `source_tree`; individual source and receipt
files remain entries of that manifest rather than multiple `source_tree`
statement roles.  This matches the receipt issuer's exactly-one-role rule and
binds the complete replay input without relying on a mutable shared directory.

## Closed workload executables

No factory may accept a caller-provided executable or shell string.  A Hurst
factory must choose all of the following from source:

- the pinned Greg Hurst commit and every file in
  `specifications/HURST_MERTENS_UPSTREAM.json`;
- `reference/tg_hurst_residual_shard.cpp`, SHA-256 implementation, compiler,
  flags, architecture, OpenMP policy, and worker-group size;
- a no-shell measured supervisor/trace verifier;
- the reducer/finalizer implementation and canonical bundle codecs;
- exact argv arrays, timeout, output format, target/trust profiles, and trace
  definition; and
- for the terminal only, the Hurst registered algorithm/input/parameter/domain
  hashes and the literal output hash of `true`.

The source-reviewed compiler route does not prove compiler correctness.  The
receipt exposes compiler and binary hashes, independent second-pass replay,
SEV-SNP/vTPM evidence, and the terminal artifact graph; the single disclosed
execution axiom remains responsible for connecting that measured execution to
the registry-fixed `Runs` semantics.  More precisely, that boundary must
justify every primitive row increment and every local guard decision.  The
latter is quantified over the guard's incoming states because it is exactly
the affine safety claim; production two-pass guards are root-derived
singletons.  Endpoint deltas alone cannot prove either physical fact.

## Implemented handoff pieces

- `grouped_shard_indices` proves by construction that the 320 groups are
  disjoint and cover the fixed plan without changing the 10,000 leaves.
- `run_phase` bounds its process pool, assigns disjoint CPU places, preserves
  leaf-sized stdout and timeout limits, and validates each result against the
  authenticated plan before retaining it.  Bounded regression tests compare
  the parallel and serial semantic receipts.
- The cluster phase DAG uses 320 summary and 320 verification groups.
- `write_registered_result` replays the complete campaign under its lock and
  exclusively writes `true` only for a complete literal full-source run.
- The terminal phase fixes its output path to
  `${TG_RUN_ROOT}/mertens-hurst/registered-result.txt`.
- The registered Lean invocation, generated receipt consumer, and
  `claude_math` conditional arithmetic adapters are source complete.  The
  registered success relation uses the local replay interface; global Mertens,
  squarefree, and active-range little-Mertens prefixes are ordinary Lean
  consequences.
- `azure_cpu_hurst_workload_factory.py` closes all 644 jobs in the six phase
  groups. The 643 nonterminal jobs have `registered_invocation = null`, so the
  CPU operator can sign their operational receipts but cannot generate Lean or
  registry candidates from them. Only `semantic-replay` selects
  `hurstSharedFourResidualProductionV2`.
- `azure_cpu_hurst_materializer.py` builds the adapter from the exact pinned
  Greg Hurst commit, the repository-bound adapter and SHA-256 source, the
  reviewed Boost 1.83 header tree, fixed compiler flags, and a static x86-64
  executable. It records the compiler and executable hashes and runs a bounded
  summary/verify replay before packaging.
- Every operational result and retained-export manifest carries the actual
  runner, adapter-source, and upstream-manifest hashes and sizes. The compact
  receipt signs those bytes as its result. Every downstream materializer and
  measured worker requires exact equality with its freshly built closure;
  source-equivalent but binary-different phase jobs cannot be combined.
- Direct and required transitive dependencies are supplied as deterministic,
  link-free archives. Each archive has a canonical tree commitment, and both
  the materializer and the separate `verify-trace` command replay it. Missing,
  duplicate, wrong-phase, overlapping, or out-of-plan groups fail closed.
- Focused tests cover the six factory shapes, registered hashes, dependency
  cardinalities, schema/CLI closure, binary-identity tampering, retained-tree
  tampering, measured-job roles, and an initialize/export/independent-replay
  round trip. The current source also compiles and passes both bounded passes
  as a static native binary; an x86-64 production-host build is still required
  before Azure staging.
- The local host is AArch64. The native static build was reproducible across
  two build roots, but the exact x86-64-v2 closure still needs to be built on
  the reviewed Azure host. Static `libgomp` also emitted a glibc `dlopen`
  warning, so runtime closure must be confirmed by the pilot rather than
  inferred from the local link.
- Full-scale finalizer storage and transfer for its 321 predecessor exports
  are not yet measured.

## Remaining implementation order

1. Materialize a bounded fixture on an x86-64 packaging host and exercise the
   full operational receipt/export return path. Bounded campaign state must
   remain unable to emit the registered result.
2. Run a calibrated 1--2-shard confidential-VM pilot, then schedule the source
   campaign.  Only after source review of the retained terminal receipt should
   the Hurst semantic inventory row and trusted registry entry be enabled.

Until those steps are complete, the repository correctly exposes a runnable
arithmetic campaign and a clean Lean handoff, but no positive production Hurst
receipt.
