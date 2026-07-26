# Goldbach `10^27` verification boundary

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

Status: **UNRUN / NOT PRODUCTION-ADMITTED**.

This note audits the exact path from the optimized binary-Goldbach candidate
to the finite ternary claim.  It does not report a source-scale run.

## Exact endpoint

The binary branch is the inclusive interval

```text
[4, 31_250_000_000_000_000], even integers only.
```

The corresponding fixed geometry is:

```text
even targets             15_624_999_999_999_999
packed 64-even words        244_140_625_000_000
live lanes in final word                         63
production leaves                              65_536
```

`Goldbach10Pow27CampaignSemantics.lean` proves these three arithmetic
equalities in Lean.  Its `CheckedCampaignEvidence.binary` field has type

```lean
GoldbachShiftedBitset.CampaignEvidence
  Goldbach10Pow27SourceSemantics.binaryLimit
```

so coverage evidence for a smaller endpoint, or for the historical `4e18`
campaign, cannot be substituted by type conversion.  Ordinary Lean proves:

```text
exact word-indexed campaign evidence
  -> BinaryGoldbachClaim through 31_250_000_000_000_000
  -> CheckedSourceEvidence with the checked n=45 ladder
  -> SourceClaim for every odd n in [7, 10^27].
```

The theorem chain uses only Lean/Mathlib foundations; fresh `#print axioms`
reports no project axiom.

## What the external artifacts currently establish

The Python campaign layer checks:

1. a gap-free 65,536-leaf partition of the exact inclusive even interval;
2. the reviewed source-closure identity and a fixed executable digest;
3. one strictly parsed successful process transcript for every leaf;
4. exact receipt ordering, hashes, and the aggregate Merkle root;
5. every prime-ladder record, primality certificate, and coverage boundary;
6. the exact lowered binary and ladder aggregate identities in the finalizer;
7. immutable result bytes `true`.

Every plan, leaf receipt, aggregate, combined result, and source-candidate
report continues to record the applicable fields as false:

```text
execution_attested
lean_atom_discharged / lean_claim_discharged
production_identity_promoted
target_h100_measured
```

The optimized source materializer is intentionally separate from the
production runner.  Its generated `goldbach.cu` digest is

```text
2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c
```

and its classification is
`qualified-source-candidate-not-production-registration`.  The current
registered Azure materializer accepts only the older reviewed hardened-source
identity. The separate optimized plan path additionally requires an external
SHA-256 pin for the exact canonical candidate manifest and membership in a
source-reviewed production allowlist. That allowlist is empty. Consequently
the optimized candidate cannot presently create a production plan or receipt
without explicit x86_64/SM90 package review, allowlist admission, and identity
migration. Its editable internal manifest self-hash is never sufficient.

## Exact missing link

There is no Goldbach source-scale artifact wire/parser that constructs
`CheckedCampaignEvidence` from retained CUDA bytes.  The leaf receipt keeps
the exact successful stdout transcript, not 244,140,625,000,000 output words
or explicit prime-pair witnesses.  A Merkle aggregate proves structural
coverage of the planned leaf intervals, but by itself does not prove that the
compiled kernels implement the Lean packed-bit model.

The pure arithmetic side is narrower than that sentence alone suggests.
`GoldbachTailProgression.lean` models the optimized source's exact guarded
first-multiple calculation and proves bounded sequential/warp completeness,
loop-guard reachability, live packed-bit indexing, and the relevant 64-bit
bounds, including the equivalence of source `first & 1` and the modeled
evenness branch. `GoldbachWarpLaunchIndexing.lean` models the exact 256-thread,
32-lane launch and proves unique coverage of every retained prime/lane pair
and fixed-width safety, including the rounded final block, as well as the
source `& 31` lane-mask identity.
`GoldbachWheelFilter.lean`, `GoldbachAtomicClears.lean`, and
`GoldbachOptimizedSourceRefinement.lean` prove the redundant-clear
optimization and the path from complete packed rows to campaign evidence.
What remains is the compiler/register/instruction, pointer/bit-address,
prime-buffer, and atomic realization of those models plus a retained
source-scale artifact, not the underlying progression or launch algebra.

The closed registered-receipt route therefore still crosses
`accepted_run_certificate_sound`.  The successful `Runs` relation has been
narrowed to require `Nonempty CheckedCampaignEvidence`; it no longer accepts
an externally supplied `BinaryGoldbachClaim` directly.  This makes the exact
remaining trusted payload visible, but it does not create it.

Because this changes the formal registered semantics, its canonical algorithm
definition was narrowed at the same time.  The new independently recomputed
algorithm hash is:

```text
23ade6c8a6069feec88b20c24ad118a2ed8b93f16d673f20591caa7cbdf167c9
```

Production receipt pins remain `none`, so no previously admitted production
receipt was migrated or silently reinterpreted.

To remove that mathematical payload from the trusted execution axiom, all of
the following remain necessary:

1. promote one reviewed optimized source closure and exact executable;
2. prove or admit a compiler/linker/loader and CUDA/SASS refinement for the
   word-owner, warp/tail, wheel filter, shifted extraction, packed population
   count, and CPU fallback paths;
3. connect each successfully executed shard to the corresponding indexed
   slice of `CampaignEvidence`;
4. prove that the exact child manifest covers every required word once and
   that the measured finalizer authenticates all child executions;
5. install reviewed confidential-compute receipt pins only after the complete
   run and retained-artifact audit.

The cryptographic certificate may remain compact: it can attest execution of
the exact refined binary over the exact complete input.  What cannot be
replaced by the four-byte result or a digest alone is the ordinary theorem
that the measured executable realizes the formal campaign semantics.

## Bounded checks run during this audit

No source-scale computation was run.  The bounded Python suites for the
lowered schedule, GPU plan/receipt parser, and optimized source materializer
passed 18 tests.  The new Lean campaign-semantics module and its test compiled
from source.  Existing retained optimization measurements remain bounded
qualification data, not a production benchmark or theorem.
