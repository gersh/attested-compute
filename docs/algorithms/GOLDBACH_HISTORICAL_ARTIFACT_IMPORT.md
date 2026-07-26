# Historical Goldbach artifact import

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status and conclusion

The historical-artifact route is potentially much cheaper than recomputing
binary Goldbach through `4*10^18`, but no complete importable package has been
verified public. The surviving public material is enough to make the citation
more inspectable, not enough to independently replay either historical
computation.

This distinction is enforced in code. The archived Oliveira e Silva summary
auditor emits all of

```text
full_27gb_shard_corpus_present=false
historical_execution_independently_replayed=false
independently_proves_binary_goldbach=false
receipt_eligible=false
source_scale_completed=false
```

No historical file is represented as Azure attestation. A future Azure
receipt could attest only that a reviewed importer revalidated exact
historical bytes and their provenance. The 2001--2012 execution would remain
an external-source fact inside the one disclosed certificate trust boundary.

## Primary-source inventory

The sources checked on 2026-07-22 were the authors' pages, the AMS paper, the
arXiv article and source package, the University of Bristol author page, and
Internet Archive captures of the author-hosted files. Search-engine mirrors
and third-party Goldbach implementations were not treated as artifacts of the
named computations.

| Item | Verified public status | What it establishes |
| --- | --- | --- |
| [Oliveira e Silva project page](https://sweet.ua.pt/tos/goldbach.html) | Author-origin page is indexed and archived. Direct retrieval from this development host returned `404`, so no live-file availability claim is made. | Reports testing every even through `4*10^18`, the shard geometry, partial double checking, and links an aggregate table. |
| [AMS paper](https://doi.org/10.1090/S0025-5718-2013-02787-1) | Public paper. | Specifies 4,000,000 intervals of `10^12`, 4,000 result files totaling about 27 GB, recorded fields, and the error-screening process. |
| [`t0.txt.gz` archive capture](https://web.archive.org/web/20160119111827id_/http://sweet.ua.pt/tos/goldbach/t0.txt.gz) | Retrieved successfully from the 2016-01-19 author-site capture. | Aggregate `L(p)` counts and `S(p)` first occurrences; it is not the 27 GB corpus. |
| [Author's prime-count tables](https://sweet.ua.pt/tos/primes.html) | Archived `pi(k*10^15)` and twin-prime `pi2(k*10^15)` tables were retrieved and pinned. | Coarse corroborating counts. They omit the paper's per-`10^12` prime counts and per-`10^15` mod-120 counts, and do not establish Goldbach coverage. |
| [Author's segmented-sieve page](https://sweet.ua.pt/tos/software/prime_sieve.html) | Page and source tarball are archived. | Explicitly offers proof-of-concept prime-sieve code; it is not the production Goldbach worker. |
| [Helfgott--Platt arXiv v2](https://arxiv.org/abs/1305.3062v2) | Article and one-file TeX source package are public. | Gives the algorithm, exact 492,700-range geometry, independent checker description, counts, and theorem endpoint. It contains no computation artifact or program source. |
| Historical Helfgott--Platt range files | The paper says that each range's checked data file was deleted. No retained copy was verified public. | No current replay input. |

The exact reviewed identities are recorded in
`specifications/GOLDBACH_HISTORICAL_ARTIFACTS.json`. Important values are:

```text
t0.txt.gz bytes                         24,812
t0.txt.gz SHA-256                       fa5e73f253154342e2d13ad095f32bab
                                        4a1670c517baaf9b3da42751f8010fce
Internet Archive CDX SHA-1 (base32)     OJ22U62I6YI2UVRCI7SATJPJZMVW5YH5
uncompressed bytes                      81,850
uncompressed SHA-256                    c3030137b247f6895bb003b413ac3328
                                        5456d7821e680e1ec653b3de364c60ed
proof-of-concept sieve tar SHA-256      cf77510ffcf2af76500a7c1426fd8541
                                        d168880f67481aba2757ff8f0594782f
pi(k*10^15) table SHA-256               60b1a2f0fc6df08fafe2072d4af52421
                                        41f4f09ed1620485c83535cf50cfba6e
pi2(k*10^15) table SHA-256              f05651263bb57e026d6665c7720b62d5
                                        d36dd49f5524fc30712fb57de6191b9f
arXiv v2 compressed source SHA-256      376ec723223d4f014e55f80263137b88
                                        800c3a71d6c021cdab0a476b171bf408
```

No production-source checksum, corpus manifest, historical executable
checksum, or retained ladder checksum was found in those primary locations.
That is a bounded search result, not a claim that no private copy exists.

## What the surviving table lets us check

Run the offline auditor on the exact archive capture:

```bash
python3 tools/tg_goldbach_historical_summary.py /path/to/t0.txt.gz --pretty
```

The auditor reads a regular non-symlink file once, pins both compressed and
uncompressed SHA-256, matches the Internet Archive CDX SHA-1, and requires the
author's exact test-range header. It then independently checks:

1. all 1,206 prime rows are exactly the consecutive primes through 9,781;
2. their `pi(p)` indices are correct;
3. each of the 1,101 numeric `S(p)` rows contains an actual prime partition;
4. no smaller prime produces a partition for that displayed `S(p)`;
5. zero counts and unknown first occurrences agree; and
6. the sum of all displayed `L(p)` values is exactly
   `1,999,999,999,999,999,999`, the number of even integers in
   `[4,4*10^18]`.

This reproduces a strong internal invariant used by the original master, and
it makes the source claim easy to compare with the paper. It cannot check that
the displayed aggregate counts arose from one assignment for every even
integer: the per-even assignments and original shard records are absent.
Consequently the table is a compact source-shaped *citation artifact*, not an
independent binary-Goldbach certificate.

## Exact material to request

### Oliveira e Silva, Herzog and Pardi

Ask for the following, preferably published on an institutional page and
covered by one author-signed SHA-256 manifest:

1. the 4,000 files (about 27 GB) described in section 1.3 of the paper;
2. a byte-level format specification, including integer widths, byte order,
   record framing, compression, and the exact CRC-32 polynomial,
   initialization, reflection and final-XOR conventions;
3. the production 32-bit x86 worker and master source at the version that
   produced the retained corpus, plus the slower C comparison routines;
4. build scripts, compiler/assembler versions and, if retained, hashes of the
   Linux and Windows worker binaries;
5. the mapping from each record to interval index `k`, worker IDs and any
   double-check record;
6. the independent `pi(x)`/residue-class check outputs and the exact source
   identity of the Deleglise checker;
7. the final global aggregate that generated `t0.txt.gz`; and
8. a signed statement mapping the manifest root to the paper's exact claim.

If the 27 GB corpus has been lost, the smallest useful fallback is a signed
statement pinning the archived table digest above, its column semantics and
the exact `[4,4*10^18]` coverage claim. That would improve provenance, but it
would still be a citation certificate rather than an independent replay.

### Helfgott and Platt

Ask for:

1. the exact C/GMP producer and C++/CLN independent checker source;
2. any master completion ledger for all 492,700 ranges of width
   `2^54*10^9`;
3. any retained range output, checksum, worker log or aggregate endpoint log;
4. the list of 130,917 general-form primes and the independently checked ECPP
   certificates or verifier transcripts;
5. exact PARI, GMP, CLN and Morain-ECPP versions and build flags; and
6. an author-signed manifest and statement for whatever survives.

The paper explicitly says the per-range files containing Proth `(k,a)` pairs
and general primes were deleted after checking. If there is no backup, an
independent ladder replay requires reconstruction.

## Smallest independently checkable formats

For binary Goldbach, the 27 GB aggregate corpus is the smallest known
historical package worth requesting, but its counts are still not a
standalone mathematical witness. Independent semantic checking requires
either the original computation under an accepted execution boundary or a
coverage/assignment stream large enough to associate each even integer with a
prime pair. A digest or global count cannot supply that missing association.

For the Helfgott--Platt branch, the smallest direct mathematical certificate
is an ordered, delta-encoded ladder stream:

```text
proth rung:   range_index, delta_k, witness_base
              p = k*2^52 + 1
general rung: range_index, delta_p, primality_certificate_digest
```

The replay derives each Proth prime, checks the Jacobi symbol and Proth modular
power, checks each general-prime certificate, checks strict ordering, begins
with 3, verifies the parity-sensitive adjacency condition

```text
next + 4 <= current + 4*10^18 + 2
```

and checks that the last translated interval reaches the exact source limit.
This is already the proposition implemented by
`GoldbachSourceSemantics.PrimeLadder.ArithmeticValid`.

Even after thinning to the widest permitted gaps, a source-height ladder has
about 2.219 trillion adjacency steps. It can be compressed because most rungs
have the Proth form, but it is not a small artifact. A per-range signed
`PASS` record is much smaller only because it moves the deleted witness replay
back into the external execution trust boundary.

## Fail-closed importer and receipt design

A future package should use canonical JSON for a small manifest and
content-addressed immutable payload files. Every file entry needs

```text
relative_path, role, exact byte length, SHA-256
```

and the entries must be sorted, duplicate-free and committed by a
domain-separated package root. The importer must reject absolute paths,
`..`, symlinks, non-regular files, missing or extra payloads, duplicate JSON
keys, noncanonical numbers, hash/size mismatches, unsupported record versions,
gaps, overlaps, duplicate range indices, CRC mismatches, failed primality
proofs, and incomplete endpoints. Inputs must be snapshotted before appraisal
to avoid time-of-check/time-of-use replacement.

The validation pipeline should be:

```text
author/institution publication + detached signature
        |
        v
source-pinned key and exact package manifest
        |
        v
Azure SEV-SNP historical importer/replayer
  - identity and signature
  - safe file closure
  - OeS record/continuity/global invariant replay
  - HP primality/adjacency/endpoint replay
        |
        v
canonical result containing both corpus roots and exact endpoints
        |
        v
existing run bundle -> independent appraiser -> signed receipt
        |
        v
source-pinned Lean registry -> sole accepted_run_certificate_sound axiom
        |
        v
ordinary Lean GoldbachSourceSemantics reduction
```

Do not reuse `helfgottPlattGoldbachProductionV1`: that identity pins the new
GPU/native reconstruction campaigns, not historical inputs. Add a distinct
`helfgottPlattGoldbachHistoricalImportV1` invocation whose canonical input
pins the author key fingerprint, signed manifest SHA-256, both corpus roots,
the paper/arXiv identities and the importer policy. Its result should contain
those roots and `accepted`, not a context-free `true`.

In the existing receipt fields:

* `algorithm_hash` binds the reviewed importer/replayer;
* `input_hash` binds the signed historical manifest;
* `parameters_hash` binds the exact decoding and validation policy;
* `domain_hash` binds `4*10^18`, the exact source endpoint, four million
  binary shards, and 492,700 ladder ranges;
* `output_hash` binds the canonical root-bearing result;
* the CPU executable/source/policy hashes occupy the artifact fields; and
* the existing Azure evidence fields attest the new replay only.

The registered `Runs` proposition should retain the two historical roots and
the exact `CheckedSourceEvidence`, closing the presently documented
transitive-provenance gap. Human review can then trace a theorem use to one
source-pinned manifest and from there to every retained historical byte.

Until the requested package exists, the implemented summary audit must remain
outside receipt admission.
