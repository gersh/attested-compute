# Ramaré production folds: compact fallback

The only native-family fallback currently admitted by policy is the three-leaf
`TGNativeCertificates.Ramare` family. It is separate from the 13 external
source atoms and the 10 physical external campaigns.

The lightweight Lean implementation is:

- `SparkInterval/TernaryGoldbach/RamareNativeFoldContracts.lean`;
- `SparkInterval/TernaryGoldbach/RamareNativeFoldsCompactChecker.lean`; and
- `RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1`.

The registry branch is fail closed: `reviewedRun` is `none`. It uses the same
`RegisteredArchitectureOutcomes` projection as every other physical run and
adds no axiom.

## What acceptance contains

The native checker accepts only the exact 100M/100M/140M configuration, the
exact small result envelope, and an existential `FiniteFoldEvidence`.
`FiniteFoldEvidence` contains:

- signed fixed-point lower and upper states;
- signed fixed-point lower and upper increments;
- exact state recurrence equations;
- a local source-realization interval for every increment; and
- integer-only endpoint guards.

It contains no first-Mertens, Lemma 7.1, m-star, or bundled final claim.
`sourceClaims_of_finiteFoldEvidence` proves the three source-shaped claims by
ordinary induction and real arithmetic. `sourceClaims_of_compactRun` then
composes that theorem with one opaque architecture execution and an explicit
universal `ArchitectureRefinesNativeChecker` premise.

No factor table, 100M/140M state array, production input, instruction trace,
or native evaluation is replayed in a routine local Lean build.

## Exact old leaves and retirement status

The last authoritative `claude_math` manifest names these Boolean-origin
leaves:

| declaration | proposition digest |
|---|---|
| `TGNativeCertificates.Ramare.Finite100M.check_first_mertens_100m_full` | `sha256:b37e6955b0a72dab27d1f1bef629d9e2f9dbcbc41bc4c768842f89d8bb82e001` |
| `TGNativeCertificates.Ramare.Lemma71.check_lemma71_100m_full` | `sha256:7c221d68aa489c14c94cb2ce762410b4a8894f8d0c4c77bf5f2bfed325002f39` |
| `TGNativeCertificates.Ramare.MStar140MCert.full_run` | `sha256:7e40b6de7113b12c788ddc30b3559743df47047808b8f93a21d75f7708a4b20b` |

The compact module does not prove those historical Boolean equations and does
not call them retired. The intended retirement is a provider replacement:

1. prove in `claude_math` the exact vocabulary maps from the GPU source copies
   to the existing corrected-remainder, Lemma 7.1, and m-star consumer
   definitions;
2. install reviewed executable/result/receipt pins for the closed registry
   invocation;
3. prove the exact executable/compiler/linker/loader refinement to
   `nativeChecker`;
4. replace all three live providers with the individual compact source-claim
   projections;
5. compile each changed provider and live consumer from source; and
6. run a fresh `#print axioms` on `ternary_goldbach`.

Until those steps pass, the status is “replacement adapter staged,” not
“native leaves retired.”
