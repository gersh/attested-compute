# Analytic artifact source-program audit

This note audits the four analytic campaigns whose finite computations are
still not closed by a complete, data-only source program:

- CH25 Lemma A.7;
- CH25 Lemma 9.2 for \(\psi\);
- Platt's zeta-zero head through height \(20\,000\); and
- the Platt--Trudgian finite-RH computation through
  \(3\,000\,175\,332\,800\).

It records the state as of 2026-07-25.  It is intentionally stricter than an
inventory of useful inner checkers.

## Promotion criterion

A campaign is ready for the architecture-receipt bridge only when all of the
following exist.

1. The runtime input contains the complete retained evidence, rather than a
   small job descriptor or only hashes of omitted evidence.
2. A total parser rejects malformed framing, truncation, suffixes, repeated
   rows, gaps, and wrong campaign parameters.
3. A total `Bool` checks every finite relationship needed by the theorem.
4. An ordinary Lean theorem proves that parse/check success implies the
   exact artifact checker's acceptance relation and then the source-shaped
   mathematical claim.
5. The executable branch runs only the parser and Boolean.  It does not call
   `NativeCheckerSemantics.accepts`, inspect a proof-valued field, or obtain
   source-scale evidence from its caller.
6. A production artifact is installed only after the complete producer,
   replay, and identity bindings exist.

The existing compact checkers consume fixed, small descriptor bytes.  Those
bytes are not certificate artifacts.  A future artifact program must use a
distinct checker and a distinct input format; changing a legacy descriptor
checker to interpret arbitrary certificate bytes would weaken its identity
boundary.

The machine-readable classifications are in
`SparkInterval/TernaryGoldbach/ClosedSourceProgramCatalog.lean`.  Every one
of these four campaigns remains `ProgramStatus.missing`.

## Current boundary

| Campaign | Ordinary Lean already checks/proves | Data or theorem still absent | Production status |
| --- | --- | --- | --- |
| CH25 A.7 | Exact rational leaf geometry, frontier coverage, rational output-box guards, and the final norm inequality in `A7BoundaryCertificate` and `A7BoundarySourceSemantics`; `A7BoundaryWire` now totally parses an exact-length, identity-pinned fixed-width projection of all seven finite leaf fields | A data-only Arb enclosure proof for every leaf, together with a refinement from the Arb function evaluated by the producer to Mathlib's `rawG`; the finite wire is deliberately insufficient for this analytic realization | Absent; fail closed |
| CH25 \(\psi\) | The literal prime-power fold, reduction to `p.log n`, event-gap endpoint guards, and the derivation of the paper-shaped real inequality in `PsiPrimePowerCertificate` | A complete serializable prime/log/gap artifact; formal realization of every directed logarithm as a bound on `Real.log`; prime-power roster completeness, gap coverage, and state constancy through \(10^{13}\) | Absent; fail closed |
| Zeta head through \(20\,000\) | The 22,491 literal Q128 rows, rational-bracket arithmetic, commitment function, and the theorem deriving the head claim from checked evidence in `ZetaHeadSourceSemantics` | Data-only endpoint enclosures tied to a proved `HardyZModel`, plus multiplicity-aware zero isolation and a complete Turing/cardinality artifact proving `slotCard` | Absent; fail closed |
| Finite RH through \(3\,000\,175\,332\,800\) | Exact-rational block arithmetic, touching bracket/Turing combinators, Python/C++ retained-archive replay, and the Lean `PT21BLK1` finite wire checker described below | The complete endpoint and Turing realization artifacts, their Mathlib refinement, multiplicity/completeness proof, and a streaming multi-artifact architecture input | Absent; fail closed |

## PT21 finite wire primitive

`SparkInterval/Zeta/PT21NativeBlockWire.lean` now parses exactly one complete
320-byte `PT21BLK1` record and checks:

- magic, version, width, and little-endian field layout;
- source block geometry;
- lower-count plus main-slot telescoping;
- all five zero finite-failure counters;
- one sparse refinement for every initial ambiguity;
- optional fallback digest/count consistency;
- unique placement and arithmetic linkage of the source-height count; and
- the domain-separated SHA-256 over the first 288 bytes.

`SparkInterval/Tests/PT21NativeBlockWireTest.lean` checks two literal records
emitted by Python's `encode_block_record`, including the unique source-height
case, and verifies framing, arithmetic, digest, and suffix tampering fail
closed.  Its soundness theorem uses ordinary Lean; neither file contains
`axiom`, `sorry`, or `native_decide`.

This is deliberately a finite primitive, not a finite-RH certificate.  In
particular, a nonzero digest says that bytes were committed; it does not say
that the omitted bytes enclose Hardy Z or prove a Turing count.

## Why PT21 is not one `ByteArray` program yet

The production record stream contains 2,966,443,783 records.  At 320 bytes
per record, the raw records alone occupy 949,262,010,560 bytes
(about 884.07 GiB), before shard framing.  The reviewed native finalizer
therefore streams separate shard files and a campaign archive.

The current architecture `Program` interface has one in-memory `ByteArray`
input.  Packing all retained shards into that input would create a nominal
949 GB program argument and would not model the reviewed streaming
implementation.  Passing only the campaign Merkle root would omit the rows
whose replay is the point of the computation.

The honest next step is a multi-artifact streaming input whose semantics bind:

1. an ordered roster of regular shard files;
2. each complete shard's bytes and digest;
3. the campaign archive;
4. gap-free block and Turing-count chains;
5. bounded-memory SHA-256 and duplicate-odd Merkle accumulation; and
6. exact end-of-stream with no extra artifact.

Until that interface and its implementation refinement exist, the block
checker remains reusable but the production PT21 source program remains
absent.

## Per-campaign next proofs

### CH25 Lemma A.7

1. Define a canonical binary envelope for all input intervals and Arb output
   balls.
2. Parse exact dyadic endpoints and bind every row to the retained producer
   artifact.
3. Check edge ordering, full four-edge coverage, and every rational guard.
4. Supply a data-checkable analytic enclosure certificate and prove that its
   successful replay encloses Mathlib's `rawG` on each interval.
5. Derive `A7BoundarySourceSemantics.SourceClaim` using the existing ordinary
   theorem.

The existing `AnalyticRealization` field is a proposition.  It identifies the
right theorem boundary, but it cannot be passed to the runtime checker.

### CH25 Lemma 9.2

1. Serialize the complete directed prime-log table and prime-power event
   roster through \(10^{13}\).
2. Stream-check roster ordering, primality/power relationships, exact gaps,
   and lower/upper fold states.
3. Replace the proof-valued `PrimeLogBounds.Realizes` input with a
   data-checkable directed-log certificate and prove its refinement to
   `Real.log`.
4. Construct gap coverage and constant-state evidence from the checked
   roster.
5. Apply `sourceClaim_of_gap_evidence`.

### Zeta head

1. Give the 22,491-row Q128 table a complete artifact parser and prove its
   reviewed commitment.
2. Retain outward endpoint enclosures, not only Q128 sign cells.
3. Prove the endpoint evaluator implements a `HardyZModel`.
4. Retain isolation, multiplicity, and Turing-completeness data and derive
   `slotCard`.
5. Construct `CheckedQ128HeadEvidence` from the Boolean checker.

### Platt--Trudgian finite RH

1. Extend the finite `PT21BLK1` primitive to the reviewed streaming
   shard/campaign API without replacing retained records by roots.
2. Retain and parse every block's endpoint, stationary-resolution,
   multiplicity, and one-sided Turing inputs.
3. Prove endpoint enclosure and Hardy-Z realization.
4. Prove the analytic Turing bounds and the global multiplicity-aware count.
5. Construct `ZetaRHSourceSemantics.SourceEvidence` from checked data.

## Focused verification

```bash
lake env lean SparkInterval/Zeta/PT21NativeBlockWire.lean
lake env lean SparkInterval/Tests/PT21NativeBlockWireTest.lean
lake env lean SparkInterval/Tests/AnalyticArtifactBoundaryAuditTest.lean
python3 -m unittest tests.test_tg_platt_pt21_native_finalizer
```

These are bounded structural and cross-language tests.  They do not run the
source-scale computations locally and do not change any production campaign
to ready.
