# Compact capstone for all thirteen external atoms

`SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone` is the
production-data-free audit surface for the ternary-Goldbach external
computations. It accepts semantic success from ten closed native checkers and
projects it to all thirteen logical atoms:

- A7, psi, zeta head, finite RH, Proposition 12.2.4, CDEM Abel, R2-star,
  finite Goldbach, and Platt Theorem 7.1 each have one checker/source
  projection;
- the one shared Hurst checker projects to the squarefree atom, Hurst's
  Mertens atom, and both little-Mertens atoms.

The capstone contains no production receipt, generated table, instruction
trace, `native_decide`, or project axiom. It does not say that any production
run has happened. Architecture/executable refinement and the eventual
reviewed receipt remain separate inputs upstream of the ten checker
acceptances.

## Platt-head table identity

Twelve projections have exactly the proposition exported by their compact
source-semantics module. The zeta-head checker intentionally returns the
weaker, table-opaque proposition
`ZetaHeadCompactChecker.CommittedSourceClaim`: there exists a Q128 table with
the reviewed digest for which the multiplicity-preserving source claim holds.

The current downstream bridge instead names one exact generated Q128 table.
Digest equality does not prove equality of those tables in Lean, and the
capstone does not postulate SHA-256 injectivity. The precise missing handoff
is exposed as
`ZetaHeadTableIdentificationObligation targetTable`, namely the implication
from the committed existential claim to the exact target-table claim.

That implication should ultimately be discharged by preserving the exact
table witness through the executable/checker refinement or by an ordinary
full-row identity proof at integration time. Until then,
`checkerDerivedClaim_of_canonicalAcceptances` proves the honest committed
claim, while the exact-table capstone requires the identification obligation
as an explicit premise.

## Focused audit

Compile only the lightweight capstone and its axiom audit:

```bash
lake build +SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone
lake build +SparkInterval.Tests.CompactExternalAtomCapstoneTest
```

The `#print axioms` output must not name a production execution axiom,
generated certificate, or native evaluator.
