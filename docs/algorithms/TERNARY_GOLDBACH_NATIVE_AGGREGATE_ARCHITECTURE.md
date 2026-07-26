# Architecture route for every native-generated ternary-Goldbach dependency

The authoritative retained capstone snapshot contains 1,371
compiler-generated native roots. They arise from 1,214 source decisions in
15 families. The exact family counts are now duplicated as kernel-reduced
closed data in
`SparkInterval/TernaryGoldbach/NativeFamilyArchitectureCatalog.lean`; its
two sum theorems check 1,371 and 1,214 without `native_decide`.

This is not 1,371 independent mathematical assumptions. A single source
decision can elaborate to several generated roots, and many decisions are
instances of one certified recurrence or interval theorem. Replacement work
therefore targets source-shaped family contracts and derives the weaker
historical leaves from those contracts.

## Two verification routes

Every family has two possible routes.

1. **Ordinary compact certificate.** An untrusted CPU/GPU/Python program
   generates rows, interval nodes, factor witnesses, or recurrence
   checkpoints. Lean checks the compact artifact and derives the source
   theorem. The generator, compiler, machine architecture, signature, and
   cloud provider are outside the trust boundary. This is the preferred route
   whenever local certificate checking is reasonably small.
2. **Attested aggregate execution.** A fixed cloud portfolio performs the
   costly work. Its confidential CPU finalizer verifies the complete signed
   CPU/H100 child-receipt graph and returns one fixed result. The sole
   project-wide attested-execution axiom supplies only an opaque execution
   fact for the closed
   `nativeGeneratedAggregateProductionV1` invocation. Ordinary Lean must
   still prove that the exact retained executable refines the exact family
   checker and that checker acceptance implies the source propositions.

The second route avoids replaying production input or a full instruction
trace on a developer machine. It does not trust an exit code, a hash, or a
signature as mathematics.

## Formal composition

The common proof chain is:

```text
closed reviewed registry entry
        +
accepted confidential-compute receipt
        |
        v
opaque execution of exact measured executable/input/result
        +
universal ISA/loader/compiler/source refinement
        |
        v
acceptance by a fixed family decision checker
        +
ordinary checker-to-source theorem
        |
        v
exact source-shaped family claims
        |
        v
weaker historical consumer leaves
```

The relevant modules are:

- `CompactArchitectureRegistry.lean`, which fixes the invocation, formal
  machine, entry point, compact pins, and reviewed result and currently fails
  closed;
- `StaticCPUExecutableCertificate.lean`, which gives the reusable
  static-ELF/instruction/block/compiler/source refinement structure;
- `DeterministicFinalizerIR.lean`, which gives a total byte-program semantics
  and the ordinary program-to-fixed-checker theorem;
- `DeterministicProgramObligationRoster.lean`, which requires a concrete
  deterministic program proof for each of the ten external campaigns, the
  all-native aggregate, and the Ramaré fallback;
- `FixedDecisionChecker.lean`, which reflects acceptance of one fixed
  decidable claim;
- `NativeFamilyArchitectureCatalog.lean`, which covers all 15 families; and
- `NativeFamilyAggregateCapstone.lean`, which performs the data-independent
  receipt/refinement/checker composition.

Family adapters must close every parameter exposed by the generic capstone.
They must not export an axiom or registry function which accepts a
caller-selected proposition, machine, executable, checker, entry point, or
pin bundle.

## Why the generic fixed-decision theorem is not a broad trust axiom

`FixedDecisionChecker.claim_of_compactRun` is an ordinary theorem, not an
axiom. Although its statement is polymorphic in `Claim`, it also requires an
ordinary universal proof that the exact executable and formal architecture
semantics refine the checker whose acceptance contains
`decide Claim = true`. For `False`, that refinement cannot be constructed
from a real successful execution. The confidential-compute axiom never takes
`Claim`; it can only return the execution selected by the closed registry.

Public family modules nevertheless close the claim and checker identifier so
the trust path is easy to audit and accidental theorem reuse is visible.

## Current fail-closed state

The aggregate constructor, all-family routing catalog, fixed-decision
reflection, and generic physical composition are implemented. Fixed checker
bundle targets now cover all fifteen families, all 1,214 source decisions,
and all 1,371 historical generated-root rows. The all-family aggregate fixes
one conjunction and supplies fifteen theorem-level projections.

This count is a routing and source-target result, not a statement-identity or
build-retirement result. Most fields repeat historical source decisions.
Within `MathExtras.NumberTheory.Helfgott`, 196 generated roots retain direct
source-decision targets, while six inaccessible private Lemma-3.7 decisions
use public Q96 rectangle predicates. Ordinary `rectCheck_sound` theorems
derive the same six real consumer inequalities; the catalog does not claim
that the new Boolean propositions are syntactically identical to the private
historical root types.

The aggregate `reviewedRun` branch is `none`, so Lean proves that no current
aggregate `PhysicalOutcome` exists. No exact executable refinement, receipt,
or live provider is installed. The complete aggregate source file is also
kept from forcing production-sized local replay: its remaining dependency
isolation work is tracked separately from the proposition/checker mapping.

The new deterministic-program roster closes an earlier accounting gap: all
twelve physical registry constructors now have an explicit source-program
proof slot. It intentionally has no inhabitant yet. For each slot, work still
has to implement the real byte-level verifier and prove that every successful
return satisfies the fixed checker. After that, a verified
compiler/linker/loader/ISA chain must connect the measured executable to that
program. Merely defining the roster does neither.

No family is considered discharged by this routing layer alone. Completion
for a family requires:

- an exact source-decision bundle or stronger source-shaped contract;
- a fixed checker and ordinary acceptance-to-claim theorem;
- a formal executable/compiler/loader/ISA refinement for the reviewed
  aggregate finalizer;
- installed reviewed pins and a successfully appraised receipt;
- live consumer wiring; and
- a fresh source build and capstone `#print axioms`.

Ordinary certificate families may skip the architecture and receipt items.
They are complete only after their certificate data and live provider wiring
are present and the fresh capstone print confirms retirement.
