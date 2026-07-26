# Closed architecture invocations for every ternary-Goldbach computation

`SparkInterval/Execution/CompactArchitectureRegistry.lean` is the
production-data-free registry for the compact architecture receipt boundary.
It has four closed tables:

- 13 `TernaryGoldbachExternalAtom` constructors, matching
  `TERNARY_GOLDBACH_EXTERNAL_ATOMS.json`; and
- 10 entries in `RegisteredArchitectureInvocation.externalCampaigns` for
  the distinct external-atom campaigns; and
- 1 entry in `RegisteredArchitectureInvocation.nativeAggregateCampaigns`
  for the fixed aggregate computation covering all 15 historically
  native-generated families and all 1,371 generated roots in the pinned
  trust-boundary snapshot; and
- 1 entry in `RegisteredArchitectureInvocation.nativeFamilyFallbacks` for
  the separately classified Ramaré production-fold fallback.

The count differs because squarefree, Mertens, and both little-Mertens claims
are four projections of the same Hurst four-residual computation. They map to
one physical invocation rather than authorizing four unrelated receipts.

The Ramaré fallback has `claimKind = nativeFamilyFallback` and `claims = []`.
It therefore cannot be mistaken for a fourteenth external atom or silently
alter the 13-to-10 external campaign accounting. It still uses the same sole
`RegisteredArchitectureOutcomes` physical projection; there is no
family-specific axiom.

The aggregate invocation similarly has `claims = []`; the external-atom
roster cannot be used to obtain a native claim.  Its
`claimKind = nativeGeneratedAggregate` instead requires a downstream closed
adapter to fix the exact family decision bundle.  The adapter must prove both
that the retained executable implements that checker and that checker
acceptance implies each exact source proposition.  A digest, successful exit
status, or receipt by itself proves none of those propositions.

The aggregate is an optional no-local-full-replay route.  It does not replace
ordinary Lean/LeanCert certificates where a compact artifact is practical.
In that stronger route, the cloud generator remains untrusted and no
architecture or attestation assumption is needed because Lean checks the
artifact directly.

## What a reviewed registration fixes

A `ReviewedArchitectureRun invocation` fixes:

- the accepted receipt hash, displayed result, nonce, and all logical
  statement hashes;
- exact target and trust profiles;
- the complete signed artifact tuple;
- compact launcher and execution-closure digest/length pins;
- one exact formal `ArchitectureSemantics`, not just its name;
- the native entry point;
- compact executable, input, and result digest/length pins; and
- the small exact executable and result artifacts tied to those pins, with
  the result bytes required to equal the UTF-8 encoding of the exact signed
  statement result.

The registration is indexed by a closed invocation. Its formal machine must
have that invocation's exact terminal target. All twelve current invocations
terminate in the Azure confidential-CPU verifier. CPU runs distinguish the
measured launcher from the architecture-modeled pure-entry executable; the
signed execution-closure artifact binds that relationship. H100 cubins and
receipts are child artifacts of hybrid invocations, not substitutes for the
terminal CPU execution.

The production input bytes, machine states, and instruction trace are not
registration fields. They remain existential witnesses in
`CompactInputReceiptExecutionFact`, so local theorem checking never replays
them. Retaining and statically validating the small executable and result is
not a production arithmetic replay; it avoids smuggling a SHA-256
digest-injectivity assumption into the ordinary binary-refinement theorem.

## CPU/H100 split

The placement type can describe three cases:

- Azure confidential CPU terminal;
- confidential H100 terminal; and
- H100 producers followed by an Azure confidential CPU finalizer.

No current invocation selects the direct-H100-terminal case. Ramaré--Zúñiga
Lemma 6.2, Goldbach, Dirichlet, and the native-generated aggregate are
hybrid. Their compact top-level fact describes the CPU terminal execution;
its formally refined checker must authenticate and verify every required
H100/CPU child receipt. A CPU receipt for a finalizer that does not perform
that verification is not enough.

## Fail-closed status

Every `reviewedRun` branch, including
`nativeGeneratedAggregateProductionV1` and
`ramareProductionFoldsCompactV1`, is currently `none`. This is intentional. A
branch may become `some reviewed` only after the exact CPU/H100 semantics,
binary refinement, signed production receipt, and all compact pins have been
jointly reviewed. Until then, ordinary Lean proves that neither
`ReceiptSelected` nor `PhysicalOutcome` can hold for that invocation.

No placeholder machine relation and no application-level success proposition
is installed merely to make a receipt selectable.

## Single-axiom projection

`RegisteredArchitectureOutcomes statement receiptHash` is the axiom-free
shape returned by the existing single trusted-certificate boundary:

```text
for every closed RegisteredArchitectureInvocation,
  if its closed reviewed registration selects this statement and receipt,
  return its exact compact PhysicalOutcome
```

`RunCertificate.ProducedOutcome.registeredArchitecture` now returns this
projection by matching directly on the accepted certificate's attestation.
For a `trustedCompute receiptHash` attestation it therefore uses that exact
hash; it cannot be instantiated with a second caller-chosen hash.
`accepted_registered_architecture_outcomes` is the derived handoff from the
same sole `accepted_run_certificate_sound` axiom. Neither entry point takes a
measurement scheme, machine, pin bundle, entry point, or proposition from its
caller.

The remaining production-materialized adapter has two jobs:

1. prove that each lightweight invocation identity agrees with the existing
   `RegisteredInvocation` identity and certificate-binding check; and
2. use ordinary executable/checker and checker/claim refinement theorems to
   derive each existing `RegisteredInvocation.Runs` result from
   `PhysicalOutcome`.

Only after all live consumers use those derived results should the current
application-level `ProducedOutcome.registered` field be removed from the
single axiom's conclusion.
