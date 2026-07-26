# Ternary Goldbach native-root member crosswalk

The machine-readable
[`TERNARY_GOLDBACH_NATIVE_MEMBER_CROSSWALK.json`](../../specifications/TERNARY_GOLDBACH_NATIVE_MEMBER_CROSSWALK.json)
contains one compact row for every one of the 1,371 native-generated roots in
the last fresh `ternary_goldbach` axiom manifest.  Each row retains only the
old generated name, type digest, family, source identity, current static
selection state, progress stage, and an optional replacement-evidence
reference.  It contains no expanded proposition, certificate corpus,
production table, or execution trace.

## What “mapped” means

All 1,371 mapped rows have a concrete repository-relative file and
declaration or grouped artifact target.  This is a staging fact, not a proof
fact.  In particular, the crosswalk does **not** assert that:

- a co-located declaration has the same elaborated type as its historical
  version;
- a grouped replacement proves each discarded implementation leaf;
- the replacement source has compiled;
- a live consumer selects the replacement; or
- a fresh capstone axiom print has retired the old generated root.

Those limitations are machine-enforced: every evidence row has assurance
`target_location_only`, the catalog policy says mapping implies none of
statement identity, integration, or retirement, and all 1,371 members remain
below `live_provider_integrated`.

The staged target mappings currently break down as follows:

| Evidence class | Old roots |
|---|---:|
| Conditional attested source-shaped family bundle | 961 |
| Same historical origin declaration co-located in its current file | 211 |
| RS62 range chunks mapped to exact grouped prefix-replay artifacts | 120 |
| Other grouped RS62 replay artifacts | 44 |
| Moved source-shaped declaration targets | 13 |
| Candidate stronger ordinary declaration targets | 5 |
| Exact ordinary bounded capstone certificate contracts | 7 |
| Compact Chebyshev event-contract bridges | 2 |
| Exact Ramaré compact-family checker target | 3 |
| Ordinary source-contract targets | 2 |
| Grouped replay instantiations | 2 |
| Ordinary source bridge | 1 |
| **Staged mappings** | **1,371** |

No member is left without a replacement target location. This is inventory
closure only: all 1,371 rows still have assurance `target_location_only`.

All 55 `MathExtras.NumberTheory.Vinogradov` roots point to the fixed,
source-shaped conditional bundle in
`CompactVinogradovNativeInputs.lean`.  Its 50 Appendix-C.1.3 interval
cells, four corrected minor-arc cells, and literal C.17 sieve equation are
checked by `FixedDecisionChecker` under the one closed
`nativeGeneratedAggregateProductionV1` invocation.  This is still only a
staged target: the exact executable refinement and physical outcome remain
explicit premises, no receipt is installed, and no live provider has moved.

The 202 `MathExtras.NumberTheory.Helfgott` roots point to a 60-decision
family bundle. For 196 generated roots, the bundle retains direct
source-decision targets. The other six old roots came from private Lemma-3.7
Boolean checkers that cannot be named from another module. They are routed to
public Q96 rectangle predicates, and ordinary `rectCheck_sound` theorems
derive the same six real consumer expressions on the same domains. The
crosswalk deliberately records these as semantic consumer replacements; it
does not claim syntactic identity with the inaccessible private root types.

The three `TGNativeCertificates.Ramare` roots all point to the exact compact
composition theorem
`RamareNativeFoldsCompactChecker.sourceClaims_of_compactRun`.  That is still
only a staged mapping: the executable refinement, reviewed receipt, downstream
provider replacement, and fresh capstone print remain absent.

All seven `Math.Problems.TernaryGoldbach.Certs` roots now have ordinary
contract targets. Six shared odd-squarefree folds use
`OddSquarefreeCombinedOrdinaryContract.lean`; the prime-filtered deficit
product uses `SingularSeriesDeficitOrdinaryContract.lean`. Their segments
contain only row counts and proposed exit states. Lean recomputes every row,
proves adjacent segment composition, proves that each complete scan is
definitionally the corresponding historical fold, and exposes one bridge
with each exact historical proposition. Consequently these routes do not rely
on a CPU/GPU architecture model, compiler correctness, an external replay, a
signature, or a secure-enclave axiom. Production checkpoint rows are still
absent here, so these remain staged targets rather than live replacements.

## Do not merge the two projections

The catalog deliberately records two different non-authoritative static
snapshots:

| Snapshot | Changed/removed | Unchanged, import-unreachable | Unchanged, import-reachable |
|---|---:|---:|---:|
| Pinned 2026-07-23 report | 1,081 | 1 | 289 |
| Later 2026-07-24 dirty-tree diagnostic | 1,085 | 5 | 281 |

The member rows describe only the later 1,085/5/281 diagnostic.  The older
1,081/1/289 values remain pinned aggregate history.  Neither row is a current
axiom count.

## Rebuild the audit

From `claude_math`, produce a new non-Lean diagnostic:

```bash
python3 scripts/tg_native_static_inventory.py --compact \
  > /tmp/tg-native-current.json
```

From `gpu_prover`, rebuild and validate the crosswalk:

```bash
python3 tools/build_tg_native_member_crosswalk.py \
  --manifest ../claude_math/problems/ternary-goldbach/native_decide_manifest.json \
  --static-report /tmp/tg-native-current.json \
  --claude-root ../claude_math \
  --output specifications/TERNARY_GOLDBACH_NATIVE_MEMBER_CROSSWALK.json

python3 tools/validate_tg_native_member_crosswalk.py \
  --manifest ../claude_math/problems/ternary-goldbach/native_decide_manifest.json \
  --static-report /tmp/tg-native-current.json \
  --claude-root ../claude_math \
  --json
```

The validator checks all 1,371 member identities against the authoritative
manifest, rechecks the exact static status of every name, verifies each
referenced file/declaration target without invoking Lean, and rejects any
claim of live integration or retirement.

Actual retirement still requires source compilation, live-consumer builds,
the full `Math MathExtras` build, and a fresh:

```lean
#print axioms Math.Problems.TernaryGoldbach.ternary_goldbach
```
