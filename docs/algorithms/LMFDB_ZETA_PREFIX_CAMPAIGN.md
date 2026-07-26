# LMFDB zeta-prefix Azure audit campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Result and non-result

`tg_verifier/lmfdb_zeta_prefix_campaign.py` is a fixed, fail-closed importer
for the public Platt/LMFDB zeta-zero files needed below `10^10`. Its production
plan has SHA-256

```text
4a1e052f3fe9963c9f4ce0170b4ee248a3c5d4b019b903c5d80eee023453dfba
```

and assigns exactly 4,766 ordered files to 149 deterministic shards: 148
shards of 32 files and one terminal shard of 30 files. There is no bounded or
operator-selected production geometry.

The completed campaign can establish all of the following about the imported
source artifacts:

- every basename and source MD5 is the entry in the reviewed, SHA-256-pinned
  LMFDB manifests;
- every byte is committed by a retained per-file SHA-256;
- every binary file is exactly framed, its blocks and multiplicity slots are
  internally ordered, and its exact first and last `(height, N(height))`
  headers are retained;
- adjacent files and adjacent Azure shards have equal boundary heights and
  multiplicity counts;
- the exact `2^-102` cut in `zeros_9998546000.dat` has
  `N(10000000000)=32130158315` and is separated from its two neighboring
  stored intervals;
- a second execution reproduces every file audit; and
- ordered Merkle roots bind all 4,766 file leaves, all 149 audit receipts, and
  all 149 replay receipts.

This is not independently a finite-RH certificate. The importer does not
recompute a Hardy-Z enclosure for each stored ordinate, replay the source
Turing-completeness calculation, or prove that the source Hardy-Z convention
is the one induced by Mathlib's `riemannZeta`. Every plan, shard, replay,
status, and final artifact therefore contains

```json
{
  "source_claim_ready": false,
  "receipt_eligible_without_realization": false,
  "source_turing_completeness_independently_replayed": false,
  "hardy_z_realization_independently_replayed": false,
  "lean_atom_discharged": false
}
```

Attesting that this program ran does not change those values. In particular,
the final JSON must not be registered as the Lean finite-RH receipt.

## Reviewed input identities

The small source metadata is downloaded separately and then copied into the
campaign directory. Initialization accepts it only at these identities:

| object | bytes/count | SHA-256 |
| --- | ---: | --- |
| ordered `filelist` | 315,441 bytes; 14,580 lines | `92da8bb7c28598bc0e20cc36820d80c20f788984bbad1f6bfaf4d9b0d842ebef` |
| `md5sum.log` | 811,161 bytes; 14,580 lines | `6ca3534a1e967f593a93428e6479eac0992c446a105da3eeb0b7a64121808521` |
| reviewed source specification | 3,296 bytes | `a0739db4fc1df1120b001a8688363c2307acc162d09851a18894feba42665703` |
| ordered first-4,766 `(index,name,MD5)` rows | 4,766 rows | `8832d6560e48041525d18a7d2ce4560c5ef07f14059599b007b8bc4e364be86b` |

The source-format and provenance review is kept separately in
`LMFDB_ZETA_PREFIX_IMPORT.md`. The primary public endpoints are the
[LMFDB source knowl](https://www.lmfdb.org/knowledge/show/rcs.source.zeros.zeta)
and the [LMFDB public data tree](https://beta.lmfdb.org/riemann-zeta-zeros/).
No source PDF or corpus file is checked into this repository.

## Initialize once

Download the two small manifests from the URLs recorded in
`specifications/LMFDB_ZETA_PREFIX_UPSTREAM.json`. Initialization re-hashes
them, checks their exact line sets, checks the terminal index, snapshots them,
and writes the immutable plan:

```bash
python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty init "$RUN" \
  --filelist "$SOURCE/filelist" \
  --md5-manifest "$SOURCE/md5sum.log"

python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty plan "$RUN"
python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty range "$RUN" 148
```

The expected final range is `[4736,4766)`, from
`zeros_9937646000.dat` through `zeros_9998546000.dat`. Copy the complete
campaign directory, including `reviewed-source/`, to immutable Azure Blob
storage before scheduling workers.

## Safe, shard-at-a-time materialization

The downloader never has a command that requests all 4,766 files. One call
materializes exactly one plan shard:

```bash
python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty materialize-shard \
  "$RUN" "$AZURE_BATCH_TASK_ID" --data-directory "$DATA"
```

It uses the fixed HTTPS origin and exact reviewed basename, requests identity
encoding, supplies LMFDB's public `human=1` gate cookie, rejects redirects,
caps each file at 256 MiB, and refuses to replace an existing path. Bytes are
streamed into a same-filesystem private temporary file, hashed with the
source-manifest MD5 and SHA-256, flushed, and installed by a non-replacing
hard link. The terminal file has the additional pre-reviewed SHA-256 and size
pin. An existing file is reused only after a complete framing and hash audit.

The source MD5 is not treated as a free-standing modern collision-resistant
commitment: it is a field of the SHA-256-pinned source manifest. The newly
computed per-file SHA-256 is retained in every later audit and replay.

For Azure, stage files on encrypted managed disks or BlobFuse outside the
measured audit process, then attach the selected shard read-only. Avoid
placing cloud credentials in the measured job environment. A preempted
materializer can be rerun; a partial temporary file is never accepted as the
destination.

This repository has not downloaded the full corpus. Only the 92,092,112-byte
terminal file was used for a local parser benchmark.

## Audit and replay jobs

Run the audit and replay in separate measured SEV-SNP CPU jobs. H100s provide
no useful advantage for this sequential binary decode and hashing stage.

```bash
python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty audit-shard \
  "$RUN" "$AZURE_BATCH_TASK_ID" --data-directory "$READ_ONLY_DATA"

python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty replay-shard \
  "$RUN" "$AZURE_BATCH_TASK_ID" --data-directory "$READ_ONLY_DATA"
```

Each audit receipt includes all per-file source MD5s, SHA-256s, byte sizes,
block counts, exact first and last heights, exact first and last multiplicity
counts, encoded-slot totals, and the complete target cut when present. A
replay receipt retains the same file records and binds both deterministic
receipt digests. The replay is a distinct execution of the byte-level audit,
not a second implementation of Hardy-Z or Turing's method.

The confidential measured-runner envelope should bind at least:

1. the exact `gpu_prover` Git tree and container image;
2. the campaign plan SHA-256 above;
3. the shard index and exact command line;
4. the read-only input-file identities;
5. the audit or replay JSON SHA-256; and
6. the SEV-SNP evidence, nonce, verifier policy, and signer key identity.

These measured envelopes are useful provenance but remain ineligible for the
finite-RH Lean bridge while the realization flags are false.

## Fail-closed finalization

After all jobs are copied back, finalization requires precisely the 149
canonical receipt filenames and precisely the 149 canonical replay filenames;
missing and extra artifacts both fail. It reparses every retained record,
checks every leaf hash, checks every within-shard and cross-shard boundary,
requires the reviewed terminal file and exact target cut, and constructs the
three ordered Merkle roots.

```bash
python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty status "$RUN"
python3 tools/tg_lmfdb_zeta_prefix_campaign.py --pretty finalize "$RUN"
```

Success means that the source corpus was faithfully imported and internally
audited. It does not mean the zeta-zero proposition is proved.

## Measured local throughput and Azure sizing

On the development ARM host, a fresh audit of the 92,092,112-byte terminal
file took 3.36 seconds and 27,828 KiB maximum RSS. That is about 27.4 MB/s for
the Python framing/audit loop. This is one sample, not an Azure SLA.

At that sample rate, a representative three-GB shard takes roughly two
minutes per pass before download and startup overhead. The 149 independent
shards are straightforward to fan out over confidential CPU VMs; audit and
replay can complete well inside a week even with modest parallelism. Provision
at least 0.6 TiB for the expected corpus plus temporary and retained artifacts,
but obtain the exact size from a completed materialization inventory before
allocating production storage. The hard per-file safety cap gives a much
larger theoretical maximum and is not a storage estimate.

## Tests

The focused test command is

```bash
python3 -m unittest -v tests.test_tg_lmfdb_zeta_prefix_campaign
```

It exercises the immutable 149-shard geometry, the real manifest pin when the
small public metadata cache is present, safe atomic download behavior, a
simulated audit and replay of all 4,766 ordered file records, exact
`N(10^10)=32130158315` finalization, all ordered roots, and negative tests for
record reordering, redirect substitution, and replayed SHA-256 changes.

## Exact remaining trust gap

To turn this prefix into an admissible finite-RH receipt, a separate reviewed
stage must independently produce and check:

1. interval evaluations of the appropriate Hardy-Z function that realize all
   retained ordinates with multiplicity;
2. the Turing-count argument proving no zeros were omitted through `10^10`;
3. the theorem-level identification of that analytic function and zero count
   with the Lean proposition built from Mathlib's `riemannZeta`; and
4. a confidential-compute receipt whose registered semantics include those
   three facts, rather than merely this corpus import.

Until then this campaign closes the data-acquisition and exact-prefix-count
subproblem only. Its false readiness flags are an invariant, not a TODO to
flip after an Azure run.
