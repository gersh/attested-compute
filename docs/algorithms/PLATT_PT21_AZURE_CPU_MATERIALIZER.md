# Exact PT21 Azure CPU materialization route

The reference Platt--Trudgian finite-RH campaign now has a fail-closed Azure
SEV-SNP CPU packaging route. It preserves the existing FLINT 3.6 computation
without claiming that the computation is fast, cheap, already executed, or
already connected to the Lean analytic definitions.

The immutable interface is
`specifications/PLATT_PT21_AZURE_EXECUTION_CONTRACTS.json`. Its raw SHA-256 is
`ad280f4795d0bf9f6172a8be3b104075b2eace86ebbe74d387a41d377b551176`.
The reference contract fixes:

- source height `3000175332800`;
- multiplicity-counted total `12363153437138`;
- ordinary prefix indices through `9999`;
- Platt/Turing indices beginning at `10000`;
- the `N+1` sentinel at index `12363153437139`;
- `1236316` formulaic shards of at most `10000000` indices; and
- count, prefix, complete-shard, and duplicate-odd SHA-256 Merkle finalizer
  semantics.

Multiplicity is preserved. The contract does not assume that zeta zeros are
simple.

## Five exact phase groups

The portfolio exposes the following dependency chain without allocating an
in-memory list of all shard descriptors:

| Phase | Jobs | Dependency |
|---|---:|---|
| `initialize` | 1 | none |
| `exact-multiplicity-count` | 1 | initialize |
| `ordinary-low-index-prefix` | 1 | exact count |
| `platt-turing-index-shards` | 1,236,316 | ordinary prefix |
| `finalize-merkle-certificate` | 1 | every indexed shard |

`tg_verifier/azure_cpu_platt_pt21_workload_factory.py` converts each exact
portfolio group and shard index into a closed measured-job identity. The
first four phases return canonical operational JSON containing the retained
export identity. Only the terminal phase uses the registered invocation
`plattTrudgianFiniteRHProductionV1` and can return the literal bytes `true`.

`tools/tg_platt_pt21_azure_measured_workload.py` invokes the existing
`tg_verifier/platt_zeta_campaign.py` implementation and independently replays
the phase in its work-trace verifier. It does not substitute an optimized
algorithm for the reference computation.

## Authenticated predecessor handoff

The operator retains each nonterminal export at the formulaic path

```text
<retained_export_root>/<phase>/<seven-digit-shard-index>.tar
```

Before packaging a dependent phase,
`tg_verifier/azure_cpu_platt_pt21_materializer.py`:

1. loads the predecessor's portfolio record and verifies that it reached
   `verified_receipt_recorded`;
2. verifies the signed production receipt against the portfolio verifier-key
   manifest;
3. compares the receipt's algorithm, input, parameters, domain, phase, and
   shard index with the closed factory;
4. requires the signed result to name the exact retained archive hash, size,
   and structural tree hash;
5. replays the retained archive structure; and
6. copies the verified immutable predecessor into a fresh handoff.

The terminal materializer repeats that procedure for the prefix and every
indexed shard from `0` through `1236315`. It extracts one canonical campaign
receipt from each shard export, computes streaming Merkle commitments to the
export identities and signed portfolio receipts, and refuses a missing,
duplicated, reordered, substituted, or extra shard. The terminal measured job
then reconstructs the complete campaign workspace and calls the existing
finalizer.

An operator state record, a retained archive, or a locally created package is
not sufficient by itself. The signed predecessor receipt and all fixed
identities must agree.

## Runtime closure

The redacted site shape is
`examples/trusted-compute/azure_cpu_platt_pt21_materializer_site.redacted.json`.
It supplies:

- the ordinary Azure CPU materializer site;
- the reviewed FLINT 3.6.0 source checkout at commit
  `8d5454b96761fafe4d5a9da76a369a602f500f49`;
- an executable x86-64 CPython host;
- a static x86-64 `tg_platt_zeta_shard` runner;
- a canonical runtime-closure manifest; and
- an off-repository retained-export root.

The runtime manifest pins the Python and runner bytes, the FLINT tracked-tree
digest, both repository source digests, the compiler identifier, and a
reviewed build-recipe digest. All four production capability flags must be
literal `true`. This is an operator-reviewed reproducible-build record, not a
formal proof of a compiler or binary.

The materializer copies the exact runtime and reviewed source closure into the
measured package and asks the ordinary CPU production operator to validate the
resulting job. Its challenge must remain valid for strictly longer than the
phase timeout plus the CPU operator's three-hour evidence-collection margin.
The longest reference shard timeout is 44 hours, so deployments need a
challenge lifetime greater than 47 hours. The checked-in 48-hour portfolio
example satisfies that containment check.

Schemas:

- `schemas/platt-pt21-azure-execution-contracts.schema.json`;
- `schemas/azure-cpu-platt-pt21-materializer-site.schema.json`;
- `schemas/azure-cpu-platt-pt21-runtime-closure.schema.json`; and
- `schemas/azure-cpu-platt-pt21-materialization.schema.json`.

For a prepared portfolio shard:

```bash
python3 tools/tg_azure_cpu_platt_pt21_materializer.py plan \
  /srv/sparkinterval/run/portfolio.json \
  platt-trudgian-rh-3e12::initialize 0 \
  /srv/sparkinterval-operator/site/pt21-materializer-site.json

python3 tools/tg_azure_cpu_platt_pt21_materializer.py materialize \
  /srv/sparkinterval/run/portfolio.json \
  platt-trudgian-rh-3e12::initialize 0 \
  /srv/sparkinterval-operator/site/pt21-materializer-site.json
```

Both planning and materialization report `accepted: false`: they create a
reviewable operator package, not execution evidence or a Lean theorem.

## Deliberate production gates

The exact CPU/FLINT route is source-complete in algorithm and geometry, but
the measured extrapolation is multi-year. Both
`economic_production_gate_passed` and
`under_one_week_and_10000_usd` therefore remain false. This route closes a
control-plane gap; it does not make the portfolio satisfy the one-week /
USD 10,000 sizing policy.

The same contract inventory describes the future
`optimized-h100-windowed-v2` interface so a replacement worker can preserve
the mathematical count, prefix, shard coverage, multiplicity, and finalizer
boundary. That implementation is explicitly refused because its measured
all-window width audit, Gaussian-sinc stationary resolution, canonical
Turing output, sparse-refinement composition, in-process `PT21BLK1` emission,
and target-SKU run are not yet complete. The V2 worker now fuses the exact
three-stream scanner and can stream authenticated nonterminal `PT21EVT1`
records without required-sign packet retention; see
[`PLATT_PT21_FUSED_EVENT_STREAM.md`](PLATT_PT21_FUSED_EVENT_STREAM.md). That
finite event boundary still carries unresolved stationary candidates and is
not a native block record. The validated finite record adapter, standalone
production-scale native finalizer, and independent retained-export replay are
implemented. The adapter can now authenticate its complete manifest and stream
the resulting records directly into a pinned native shard finalizer, so the
additional fixed-width record spool is not required; see
[`PLATT_PT21_NATIVE_FINALIZER.md`](PLATT_PT21_NATIVE_FINALIZER.md). They do not
enable the materializer until the measured worker streams its complete finite
outputs through the adapter or directly emits the same fail-closed fixed-width
records. Individual optimized components or bounded tests cannot enable the
materializer.

Finally, even a successful complete confidential-compute run would still
leave the documented Lean realization obligation: connect the FLINT endpoint
enclosures, Hardy-Z sign/isolation facts, multiplicity count, and analytic
Turing argument to the source-shaped Lean evidence. The semantic binding
remains disabled until that proof and a reviewed successful receipt exist.
