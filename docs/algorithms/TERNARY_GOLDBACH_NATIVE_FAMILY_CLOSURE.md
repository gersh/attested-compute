# Ternary Goldbach native-family closure

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

This document extends the compact-verification plan from the thirteen named
external/source atoms to every native-generated family in the last completed
`claude_math` capstone build. It contains no production certificate rows,
input corpus, execution trace, or theorem authority.

The machine-readable matrix is
[`TERNARY_GOLDBACH_NATIVE_FAMILY_CLOSURE.json`](../../specifications/TERNARY_GOLDBACH_NATIVE_FAMILY_CLOSURE.json).
Validate its accounting with:

```bash
python3 tools/validate_tg_native_family_closure.py
python3 -m unittest tests.test_tg_native_family_closure
```

When the `claude_math` evidence checkout is available, the same validator can
also check the raw SHA-256 and every family count, module count, membership
digest, range label, and root type against the retained manifest:

```bash
python3 tools/validate_tg_native_family_closure.py \
  --authoritative-manifest /path/to/claude_math/problems/ternary-goldbach/native_decide_manifest.json \
  --projection-document /path/to/claude_math/problems/ternary-goldbach/NATIVE_DECIDE_STATIC_PROJECTION.md
```

## Two counts that must not be conflated

The last fresh capstone trust-boundary artifact had **1,371 generated native
atoms in 15 families**. That completed Lean build is the authority for that
snapshot.

The later source-only comparison classified **289** old atoms as having an
unchanged source selection in an import-reachable module. It classified 1,081
selections as changed or removed and one as unchanged but import-unreachable.
Those are diagnostic source states:

| Snapshot/classification | Atoms | Authority |
|---|---:|---|
| Last fresh capstone native atoms | 1,371 | Yes, for that completed build |
| Source selection changed or removed | 1,081 | No; retirement is unknown |
| Unchanged but import-unreachable | 1 | No; retirement is unknown |
| Unchanged and import-reachable | 289 | No; projected carry-forward only |

A changed source selection can disappear, acquire a different proposition, or
generate new native atoms when elaborated. Import reachability is also not
proof-term reachability. Therefore neither `1,371 - 1,081` nor the number 289
is a current axiom count.

## Family matrix

“Local certificate” means that routine builds check compact proof objects with
ordinary Lean/kernel or LeanCert reasoning. It does **not** mean rerunning the
original production scan locally.

| Family | Last-fresh atoms | Changed | Unreachable | Projected | Preferred closure |
|---|---:|---:|---:|---:|---|
| `AnalyticNT.Chebyshev` | 3 | 0 | 0 | 3 | Local prime-event certificate |
| `AnalyticNT.LargeSieve` | 18 | 0 | 0 | 18 | Local linked sieve/checkpoint certificate |
| `HelfgottCertificates` | 4 | 4 | 0 | 0 | Local fixed-width interval certificate |
| `Math.Problems.TernaryGoldbach.Certs` | 7 | 0 | 0 | 7 | Local factor/squarefree certificate |
| `Math.Problems.TernaryGoldbach.MinorArcs.Chapter14` | 34 | 34 | 0 | 0 | Local proof-carrying interval cells |
| `MathExtras.NumberTheory.Analysis` | 3 | 3 | 0 | 0 | Local floor-grid tables |
| `MathExtras.NumberTheory.Certs` | 2 | 0 | 0 | 2 | Local linked Möbius/Liouville shards |
| `MathExtras.NumberTheory.Helfgott` | 202 | 14 | 0 | 188 | Local sharded interval DAGs |
| `MathExtras.NumberTheory.Helfgott.Certs` | 1 | 0 | 1 | 0 | Local 30,000-head certificate |
| `MathExtras.NumberTheory.LSeries` | 2 | 0 | 0 | 2 | Local von-Mangoldt/interval certificate |
| `MathExtras.NumberTheory.Mertens` | 1 | 0 | 0 | 1 | Local shared Möbius certificate |
| `MathExtras.NumberTheory.Vinogradov` | 55 | 0 | 0 | 55 | Local adaptive interval/sieve certificates |
| `Rs62Certificates` | 1,025 | 1,025 | 0 | 0 | Local compressed rows and assemblies |
| `TGNativeCertificates` | 11 | 1 | 0 | 10 | Local linked finite-fold certificates |
| `TGNativeCertificates.Ramare` | 3 | 0 | 0 | 3 | Compact trusted run |
| **Total** | **1,371** | **1,081** | **1** | **289** | **1,368 local; 3 compact fallback** |

The matrix assigns old atoms to engineering routes; it does not imply a
one-to-one replacement certificate. For example, the 1,025 RS62 leaves should
collapse into shared seed/log tables, linked transitions, and a small number
of theorem-level assemblies.

## Why only three atoms use the trusted-run fallback

Fourteen families are finite enough, or compress structurally enough, to use
ordinary proof-carrying certificates. The three
`TGNativeCertificates.Ramare` folds cover \(10^8\) to \(1.4\cdot10^8\)
indices. Retained measurements put each full production evaluation around 62
to 95 minutes, with the \(m^\star\) fold using about 15.33 GiB. Repeating
those computations during routine local Lean builds defeats the isolation
goal.

For that family the intended boundary is:

1. prove once, in ordinary Lean, that the fixed CPU program implements the
   finite checker and that checker acceptance implies the source-shaped
   proposition;
2. run the fixed program over the exact domain inside reviewed Azure
   confidential compute;
3. bind executable, input, result, policy, and launch identity in a compact
   receipt;
4. use the project's existing single trusted-compute axiom to obtain the
   opaque physical execution fact; and
5. derive the mathematical claim locally without replaying the input or
   instruction trace.

The production-data-free Lean half of that boundary is now staged in
`RamareNativeFoldContracts.lean` and
`RamareNativeFoldsCompactChecker.lean`. The closed registry exposes it as one
`nativeFamilyFallback`, separately from the 10 external campaigns. Acceptance
carries integer interval folds and guards rather than a final claim, and the
ordinary evidence-to-all-three-claims theorem is base-trio only. The registry
branch remains `none`; exact binary refinement, reviewed pins, the Azure run,
and the three `claude_math` provider swaps are still missing. See
[`RAMARE_NATIVE_FOLDS_COMPACT_FALLBACK.md`](RAMARE_NATIVE_FOLDS_COMPACT_FALLBACK.md)
for the exact historical Boolean leaf digests and retirement checklist.

This does not authorize a new axiom for each family. A receipt is also not
sound merely because it is signed: the architecture/ABI/compiler refinement,
measurement policy, exact invocation pins, and checker-to-claim theorem all
remain explicit obligations.

## What remains before “zero native” is true

For the fourteen local families:

1. finish each compact checker's generic soundness theorem;
2. prove its output maps to the exact source-shaped proposition;
3. replace the live provider and compile the changed source and consumer; and
4. keep original production generation out of routine builds.

For the Ramaré family, additionally complete the fixed-code refinement,
reviewed deployment pins, measured Azure run, compact receipt verification,
and ordinary receipt-to-source composition.

Finally, run the isolated slow full build and a fresh:

```lean
#print axioms Math.Problems.TernaryGoldbach.ternary_goldbach
```

Then regenerate the trust-surface manifest. Until that print reports no
generated native atoms, every retirement in the current worktree is staged,
not established.
