# Platt Theorem 7.1 Lean handoff

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

The accelerated Dirichlet campaign has one final theorem-shaped target:

```lean
SparkInterval.Dirichlet.PlattTheorem71DirichletVerification
```

[`PlattTheorem71Contract.lean`](../../SparkInterval/Dirichlet/PlattTheorem71Contract.lean)
expands that proposition and proves

```lean
SparkInterval.Dirichlet.plattTheorem71_of_modulus_verification
```

from symmetric `GRHVerifiedForModulus` results at the exact source heights.
It has the same mathematical shape as the ternary-Goldbach trust atom
`MathExtras.Helfgott.MajorArcsStart.PlattTheorem71DirichletVerification`:

| Item | Contract |
| --- | --- |
| conductor | every positive `q <= 400000` |
| character | every `DirichletCharacter Complex q` with `IsPrimitive` |
| even height | `max (10^8/q) (200 + 7.5*10^7/q)` |
| odd height | `max (10^8/q) (200 + 3.75*10^7/q)` |
| zero domain | `LFunction chi rho = 0`, `0 < rho.re`, `rho.re < 1`, and `abs rho.im <= height` |
| conclusion | `rho.re = 1/2` |

`GRHVerifiedForModulus` now quantifies over the source-faithful open strip
`(0,1) x [-height,height]`. This excludes the trivial boundary zero at `s=0`
for even primitive characters. Its zero set is finite by an ordinary theorem
showing containment in the closed compact envelope
`[0,1] x [-height,height]`; compactness is not incorrectly asserted for the
open strip itself.

The theorem is intentionally only an interface. To construct either
per-modulus hypothesis, the production proof must provide all of the
following, without replacing any item by a digest:

1. the exact primitive-character roster for the source conductor;
2. a completed-L Hardy model and its nonvanishing phase identity;
3. checked, ordered strict-sign brackets covering the selected critical-line
   zeros, including upsampling and exception handling;
4. conjugation coverage needed to pass from the one-sided scan to the
   symmetric absolute-height statement; and
5. a Turing-method or argument-principle upper count matching the bracket
   count.

The arithmetic bridge supplies increasingly strong inputs to item 3: literal
binary64 Gaussian/postprocess records, a checked radix-2 DFT equal to the
direct positive DFT, source scaling/tail/untilt arithmetic, and strict signs.
`FactoredSmallQZeroBracket.CompletedSignBracketFamily.exists_zeroCertificate`
now gives the exact checked-sign-to-rational-bracket handoff, provided the
caller supplies explicit containment, reality, and evaluator equalities for
the selected endpoints. It does not select the full source pair family or
supply items 1, 2, 4, or 5 by assumption.

The preceding finite join is
`FactoredSmallQRawZeroBracketCampaign.decodedCells_bracket_check`: each typed
endpoint must decode from a real raw campaign cell and is checked against the
literal DFT word at the same key. Thus the remaining endpoint obligation is
semantic equality with the completed-L evaluator, not an unproved arithmetic
or bit-pattern attachment. The corollary
`decodedCells_checkedRationalBracket_of_sourceRealizes` makes that boundary
executable-to-semantic in one place: the raw checker supplies the finite
facts, while the two named `SourceRealizes` premises supply exactly the
analytic facts.

[`FactoredSmallQSourceRealization.lean`](../../SparkInterval/Dirichlet/FactoredSmallQSourceRealization.lean)
makes the two source meanings before that join separately auditable. A
`PrimitiveRosterRealization` is an exact bijection between a noduplicated list
of opaque identifiers and all primitive Dirichlet characters of the modulus;
it deliberately makes no claim that the identifiers are Conrey numbers.
`CharacterInputsRealize` fixes each application row to
`[chi(1), ..., chi(termCount)]` and fixes its parity branch.
`SourceEvaluatorRealizes` fixes Booker's exact `a=64/5` grid and states one
complex equality between the factored/direct-DFT source expression and one
named real evaluator at every retained sample. The requested-cell capstone
requires both contracts and returns the character row, parity, literal raw
word/direct-DFT enclosure, and `EvaluatorLink` for the same decoded cell.
None of these contracts is presently instantiated for production source data.

`DirichletHardyModel.verifyCompletedSignBracketFamily` then exposes the next
join in one theorem: checked brackets plus the Hardy model, height bounds, and
the complete L-zero upper count imply finite GRH for that character.
`grhVerifiedForModulus_of_completedSignBracketFamilies` assembles these
explicit inputs over all primitive characters of one modulus. The remaining
source-wide theorem must instantiate those arguments at the two displayed
height functions before calling `plattTheorem71_of_modulus_verification`.

[`FactoredSmallQRosterGRHBridge.lean`](../../SparkInterval/Dirichlet/FactoredSmallQRosterGRHBridge.lean)
removes the remaining indexing ambiguity: roster completeness selects the
unique opaque identifier for an arbitrary primitive character, and the
checked equality `family.characterId = id` is used to rewrite the
source-indexed endpoint evaluator into the Hardy model for that character.
The Hardy model, bracket completeness, symmetric/conjugation coverage, the
separate `q=1` zeta case, and the total-zero upper bound are still genuine
analytic obligations.

## Closed Azure receipt endpoint

[`RegisteredPlattTheorem71Certificate.lean`](../../SparkInterval/Execution/RegisteredPlattTheorem71Certificate.lean)
provides the final conditional receipt boundary. The closed invocation
`plattDirichletTheorem71ProductionV1` pins:

- the source conductor range `1 <= q <= 400000`;
- the exact even and odd height formulas above;
- all primitive Dirichlet characters and the scheduler's exact
  29,565,923,837-character count for `q=2..400000`;
- `platt-trudgian-rh-3e12` as the separate stronger `q=1` source; and
- an Azure SEV-SNP CPU finalizer deployment.

The registered execution relation is fail closed. Output `false` is
satisfiable and proves no source statement. Output `true` requires
`Nonempty PlattTheorem71SourceEvidence`, whose fields are exactly the two
universal parity branches; a digest, aggregate count, or sample cannot replace
them. The signed wrapper then derives
`PlattTheorem71DirichletVerification` through the ordinary theorem
`plattTheorem71_of_source_evidence` and adds only the repository's disclosed
accepted-run axiom.

This endpoint is ready to consume a reviewed campaign result, but there is no
completed source-scale campaign, successful receipt, or formal realization of
the operational artifacts as `PlattTheorem71SourceEvidence` in the repository.
The corresponding Azure semantic row therefore remains disabled. Its exact
invocation, conditional theorem, and
`${TG_RUN_ROOT}/platt-dirichlet-theorem-7-1/registered-result.txt` postcheck
contract are staged explicitly. The legacy postcheck creates literal `true`
exclusively only after replaying q=1, every q>=2 checker, and the exact source
composition; this is a reviewed interface, not evidence that it has run.

## Downstream replacement procedure

Once the campaign theorem is complete, the safest integration is to pin this
repository as a Lake dependency at the same Lean/Mathlib revision and prove a
small adapter in the ternary-Goldbach repository by unfolding the two
source-shaped definitions. Then replace only
`platt_theorem_7_1_dirichlet_verification_source` with that adapter theorem and
run a fresh `#print axioms` on `ternary_goldbach`.

The repositories currently use different Lean/Mathlib revisions, so the
adapter has deliberately not been claimed or admitted yet. Copying a receipt,
MMR root, or textual theorem statement across that boundary would not be a
Lean proof.

## Audit commands

```bash
lake build SparkInterval.Tests.PlattTheorem71ContractTest
lake build SparkInterval.Tests.RegisteredPlattTheorem71CertificateTest
lake build SparkInterval.Tests.FactoredSmallQSourceRealizationTest
lake build SparkInterval.Tests.FactoredSmallQRosterGRHBridgeTest
lake env lean SparkInterval/Tests/PlattTheorem71ContractTest.lean
```

The contract and handoff theorem print only `propext`, `Classical.choice`, and
`Quot.sound`.
