# Production q-order streaming checker

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

`SparkInterval/Dirichlet/QOrderManifestStreamingWire.lean` is the
production-scale pure-Lean checker for the canonical `TGDQORD1` scheduling
manifest. It replaces the materializing reference checker's merge sort,
generic `Nodup` decision, and recursive `List.sum` with proved linear passes.
The reference checker remains useful for small fixtures.

## Exact accepted object

The checker accepts only the full primitive-V2 source manifest with:

- q range `10001..400000`;
- 292,500 formulaic modulus records;
- 3,637,613,167 total ordinate samples;
- increasing-roster SHA-256
  `d80a78ee36a82e2dab0d783b2c2407eff425a5978edb46585fba09d1ca7d5a2c`;
- execution-order SHA-256
  `34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd`;
  and
- complete-manifest SHA-256
  `a5ae1af2e4a9e944ccef559e169a13cd74f21c220ed882950ecd4491cbf13e93`.

It checks the exact file size before parsing. A tail-recursive geometry pass
checks every `(q, sampleCount)` formula, accumulating the exact two totals. A
hash-set pass rejects duplicate execution moduli. A direct pass over every
integer in the source window proves exact coverage, including the exclusion
of moduli congruent to 2 modulo 4. The packed SHA implementation hashes the
formulaic source roster, the execution-order body slice, and the complete
wire.

The checker retains one parsed record list because downstream resident phases
need that execution order. It does not retain a sorted copy. It temporarily
constructs the 2,340,000-byte formulaic source body used for the independent
source-roster digest.

## Proved handoff

Successful `checkFullSourceManifest` evaluation implies:

- the returned header and record list are exactly those parsed from the raw
  bytes;
- every retained row has the exact source formula;
- the q values are unique and cover exactly the formulaic source range;
- row count, sample total, file size, and all three digest pins agree; and
- membership in the retained execution order is equivalent to the exact
  formulaic record predicate.

`checkScheduledFullSourceBundle_exactRoster` then composes the manifest with
the completed-factor streaming checker. Its theorem states that accepted
checkpoint rows are walked against exactly the resident-phase projection of
that checked execution order. No aggregate-only or metadata-only substitute
roster is introduced.

All these theorems have only Lean's ordinary foundational axioms
(`propext`, `Quot.sound`, and `Classical.choice` where hash sets or SHA are
used). The implementation contains no `native_decide`, `unsafe`, FFI,
project axiom, or `sorry`.

## Auditor command

Generate the canonical manifest, build the native wrapper, and check it:

```bash
python3 tools/tg_dirichlet_allchars_q_scheduler.py \
  source-manifest /tmp/TGDQORD1-source.bin

lake build sparkinterval-check-dirichlet-qorder

.lake/build/bin/sparkinterval-check-dirichlet-qorder \
  /tmp/TGDQORD1-source.bin
```

The JSON success report deliberately says
`lean_source_checker_result_unattested`,
`external_atom_discharged:false`, and
`trusted_execution_attested:false`. The wrapper is a convenient native
evaluation of the pure checker, not a compiler-refinement theorem or an
attested cloud receipt.

## Qualification measurements

On the local GB10 host, three native runs of the core checker accepted the
2,340,112-byte canonical manifest in 5.28--5.34 seconds at about 161 MiB RSS.
The former materializing native checker took 301.91 seconds, so the new path
was about 57 times faster. A final-source `lean --run` replay accepted the
same 292,500 rows in 44.02 seconds; its roughly 6 GiB process RSS is dominated
by the repository's Mathlib import closure.

Production-size negative fixtures rejected an invalid q, a two-row swap, a
corrupted source digest, and a trailing byte. The permanent CLI also rejects
non-files and wrong-sized inputs before reading the payload.

These are local qualification results, not Azure timings or source-run
evidence.

## Trust boundary

The Lean proofs establish exact parser, roster, digest-preimage, and
downstream handoff semantics. They do not prove SHA-256 collision resistance,
that the generated manifest came from a particular historical source, that a
compiled native binary refines Lean evaluation, that Arb or CUDA produced any
later artifact, that execution was confidentially attested, or that the
Dirichlet analytic theorem holds. Those remain explicit, independently
auditable boundaries.
