# Compact receipt closure for every ternary-Goldbach residual

The machine-readable audit is
[`specifications/TERNARY_GOLDBACH_COMPACT_RECEIPT_CLOSURE.json`](../../specifications/TERNARY_GOLDBACH_COMPACT_RECEIPT_CLOSURE.json).
It covers the thirteen named external atoms and the distinct finite endpoint
below `10^27`.  The four Hurst-family atoms share one physical campaign, so
the complete scope is fourteen logical claims and eleven physical campaigns.

This audit is deliberately stricter than “there is a verifier” or “Lean has
an evidence theorem.”  A compact cloud receipt closes a claim only when all
of the following are available:

1. the exact reviewed receipt, machine-semantics, entry-point, executable,
   input, and result pins;
2. a universal data-independent theorem from execution of that exact
   executable to a low-level native checker acceptance;
3. an ordinary theorem from that low-level acceptance to the finite Lean
   evidence structure; and
4. the existing ordinary theorem from the evidence structure to the exact
   source claim.

For a multi-job campaign there is one additional obligation: the terminal
checker must have a proved transitive execution closure for every child
receipt.  A process receipt saying that a finalizer returned `true` does not,
by itself, prove that its H100 or CPU children ran correctly.

No production input or instruction trace is replayed by this audit or by the
generic compact composition theorem.  Those values remain existential and
opaque.  Local checking is limited to small catalogs, source identities,
result pins, and data-independent Lean proofs.

## Exact result boundary

Ten campaigns have the exact four-byte UTF-8 result `true`, whose SHA-256 is
`b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b`.
The CDEM Abel campaign has the exact 46-byte result
`2372685835387717172679029560108650251645442524`, the Mathlib `Nat.pair`
of the two directed source numerators.  Its SHA-256 is
`84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c`.

Every campaign also has exact registered algorithm, input, parameter, and
domain identities.  Those logical pins are not substitutes for physical
pins.  At present all eleven receipt hashes, formal-machine identities,
entry points, exact executable pins, and production-input pins are null.  The
trusted-compute registry is empty.

## Campaign-by-campaign closure

| Physical campaign | Implementation | Existing data-independent Lean conclusion | Receipt shape eventually required | Missing physical/formal edge |
|---|---|---|---|---|
| `ch25-a7-boundary` | CPU Python/FLINT/Arb replay and deterministic Lean-certificate renderer | Checked boundary leaves plus an `AnalyticRealization` imply the exact A.7 source claim | One direct CPU receipt | Exact executable refinement, native transcript-to-`SuccessEvidence`, and FLINT/Arb-to-Mathlib analytic realization |
| `ch25-psi-two-pass-v1` | Source-scale C++ prime-power/Q64 producer and independent two-pass replay | `GapSourceScaleEvidence` implies the real-variable Lemma 9.2 claim | Transitive campaign receipt for all summary, replay, and finalizer jobs | Graph closure, executable refinement, and native rows-to-gap-evidence theorem |
| `platt-head-2e4` | Complete CPU FLINT isolation through the sentinel and literal Q128 table generation | `CheckedQ128HeadEvidence` implies the multiplicity-preserving Q128 source claim | One direct CPU receipt | Executable refinement and endpoint/Hardy-Z/count realization of the retained table |
| `platt-trudgian-rh-3e12` | Source-complete but impractical CPU FLINT reference route; optimized PT21 components are not yet end-to-end | `SourceEvidence` implies finite RH through the exact source height | Transitive campaign receipt | Economical source-scale worker, graph closure, executable refinement, and endpoint/Hardy-Z/Turing realization |
| `helfgott-prop-12-2-4-mpfr-v1` | Source-scale C++ MPFR/GMP q-rank scan with independent replay | Checked `SourceScaleEvidence` implies all source finite windows | Transitive campaign receipt | Graph closure, executable refinement, native rows-to-certificate theorem, and MPFR/GMP-to-Lean-real realization |
| `hurst-four-residuals-v1` | One source-scale C++ two-pass Möbius campaign | Local source-scale evidence implies a `RealSourceClaims` structure containing squarefree B1/B2, Hurst Mertens, and both little-Mertens claims | One transitive campaign receipt, followed by four ordinary projections | Graph closure, executable refinement, and native row/guard evidence realization |
| `cdem-table-abel` | Full OpenMP producer, independent bounded-memory replay, and generated fixed Lean recurrence certificate | Checked local recurrence evidence implies the exact source claim | One direct CPU receipt | Exact executable refinement and native output/local-fold evidence realization |
| `ramare-zuniga-lemma-6-2` | H100 CUDA Q32 producer plus independent exact CPU replay in one closed job | Checked source-scale certificate implies the real `R₂*` claim | Composite child-H100 evidence authenticated by one confidential-CPU finalizer receipt | Exact producer/finalizer executable refinements, transitive child binding, and native coefficient/log evidence realization |
| `helfgott-platt-goldbach-gpu-v1` | H100 binary-Goldbach leaves, CPU native prime ladder, and CPU finalizer | `CheckedSourceEvidence` implies the historical finite three-prime theorem | Transitive campaign receipt covering both branches | Child execution closure, exact H100/CPU refinements, and native branch artifacts-to-evidence theorem |
| `platt-dirichlet-theorem-7-1` | Rigorous unscaled CPU FLINT fallback; optimized H100 pipeline remains incomplete | `PlattTheorem71SourceEvidence` implies the exact two-parity source theorem | Transitive closure including the separate q=1 finite-RH dependency | Complete optimized algorithm, child/q=1 closure, exact executable refinements, and completed-L/Hardy-Z/count realization |
| `ternary-goldbach-finite-below-10pow27-v1` | Lowered H100 binary-Goldbach branch, CPU n=45 ladder, and CPU finalizer | `CheckedSourceEvidence` implies the finite claim through `10^27` | Transitive campaign receipt covering both branches | Child execution closure, exact H100/CPU refinements, and native branch artifacts-to-evidence theorem |

Thus every logical claim has an ordinary conditional Lean soundness path, and
all eleven campaigns now have an axiom-free compact acceptance-to-claim
adapter. The Platt-head adapter deliberately stops at the existential claim
for the reviewed table commitment; exact downstream table identity remains a
separate obligation. Zero campaigns currently have the exact
machine/compiler refinement needed to use a compact architecture receipt as
theorem authority.

## Minimal adapter pattern

The generic composition is
`SparkInterval.Execution.Architecture.claim_of_compactInputReceipt` in
`SparkInterval/Execution/CompactClaimReceipt.lean`.  A campaign-specific
adapter should supply only:

- a closed `NativeCheckerSemantics` whose acceptance is a byte-level
  certificate/checker predicate, never the source claim itself;
- an `ArchitectureRefinesNativeChecker` theorem for the exact reviewed
  executable and entry point;
- an `AcceptanceImpliesClaim` theorem which decodes the small result and
  derives the existing finite evidence structure; and
- for DAG campaigns, a low-level graph certificate whose validation proves
  every child execution fact required by the finalizer.

The direct campaigns now have one such conditional adapter each. Hurst has
one adapter, not four: its four external declarations are projections of one
`RealSourceClaims`.  The two Goldbach campaigns should share their
binary-branch and prime-ladder refinement lemmas while retaining distinct
domain and terminal identities.  The two zeta campaigns should share
Hardy-Z/endpoint/Turing primitives without conflating their distinct tables,
heights, or multiplicity counts.

## Static verification

Run:

```bash
python3 tools/audit_tg_compact_receipt_closure.py
python3 -m unittest tests.test_tg_compact_receipt_closure
```

These commands hash only small repository source files and inspect the
data-independent declaration catalogs.  They do not compile native code,
open a production artifact, replay a certificate, or execute a campaign.
