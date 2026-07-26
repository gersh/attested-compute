# Pinned numeric-corpus references

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

Large finite computations often need more input rows than should be copied into
an application repository. SparkInterval's numeric-corpus reference format
lets the application retain a small, reviewable pin while the full corpus
remains in another Git repository.

The protocol is about **identity and integrity**. It answers:

- which exact Git commit contains the corpus;
- which exact manifest bytes were reviewed;
- which source and payload blobs the manifest names;
- which logical ranges those payloads cover; and
- which exact human-readable claim the corpus is intended to support.

It does not prove that the claim is true, that the listed generator is correct,
that a program was run, or that the bytes are sufficient for a Lean theorem.
Those conclusions require an independent checker, a proof, or an explicitly
documented external-computation assumption.

The structural schemas are:

- [`pinned-numeric-corpus.schema.json`](../schemas/pinned-numeric-corpus.schema.json);
- [`numeric-corpus-manifest.schema.json`](../schemas/numeric-corpus-manifest.schema.json).

The schemas reject malformed field layouts and common placeholder/path
mistakes. The Python loader is the normative acceptance implementation: it
also enforces canonical wire bytes, deterministic ordering, aggregate hashes,
and cross-field relationships that JSON Schema cannot express.

## The two records

### Consumer pin

A `sparkinterval.pinned_numeric_corpus.v1` record belongs in the consuming
project. It is intended to be small enough for ordinary code review. It binds:

- an HTTPS repository URL;
- a full 40-lowercase-hex Git commit object ID, never a branch or tag;
- a safe repository-relative manifest path;
- the manifest blob's exact byte length and SHA-256 digest; and
- the claim, corpus version, statement digest, aggregate payload/source roots,
  payload count, and payload byte count expected by the consumer.

The repeated `expected` fields are intentional. A verifier must compare them
to the referenced manifest. Replacing the manifest with a different corpus
that happens to live at the same path is not enough.

The pin must arrive through a trusted channel, normally as a reviewed file in
the consuming repository. Downloading both the corpus and its pin from the
same untrusted location does not establish an independent identity.

### Corpus manifest

A `sparkinterval.numeric_corpus_manifest.v1` record lives in the corpus
repository. It contains:

- a source-shaped claim and exact statement digest;
- immutable corpus and claim identifiers and positive integer versions;
- string-valued computation parameters;
- explicit logical coverage intervals;
- ordered payload records with paths, roles, encodings, ranges, row counts,
  sizes, and SHA-256 digests;
- ordered source-file records with paths, roles, executable bits, sizes, and
  SHA-256 digests;
- aggregate roots for the complete payload and source lists; and
- optional application-defined semantic commitments.

`source_files` is a declared source closure, not an assertion that every
compiler, library, operating-system component, or data dependency has been
captured. A production manifest must either include all required inputs or
document separately which environment and execution assumptions remain.

## Canonical bytes and hashes

Pins and manifests use SparkInterval's canonical JSON encoding:

- strict UTF-8;
- no duplicate object keys;
- no floating-point numbers, `NaN`, or infinities;
- object keys sorted lexicographically;
- `,` and `:` separators with no insignificant whitespace; and
- exactly one final line-feed byte.

The schema is not a substitute for this byte-level check. Pretty-printed JSON
with equivalent values is deliberately a different, rejected wire file.

Every file digest is lowercase hexadecimal SHA-256 over the exact blob bytes.
The statement and aggregate roots are domain separated:

```text
statement_sha256 =
  SHA256("sparkinterval/numeric-corpus-statement/v1\0"
         || UTF8(exact statement string))

payload_root.sha256 =
  SHA256("sparkinterval/numeric-corpus-payload-root/v1\0"
         || canonical_json_bytes(complete payloads array))

source_root.sha256 =
  SHA256("sparkinterval/numeric-corpus-source-root/v1\0"
         || canonical_json_bytes(complete source_files array))
```

The terminating `\0` above is one NUL byte. The canonical array encodings
include their final line feed. The corresponding root also records the exact
file count and total byte size, and the validator recomputes those values.

`semantic_commitments` are application-specific domain-separated hashes. They
can bind a parsed or normalized mathematical view of a file when raw layout
hashes are insufficient for human comparison. The generic loader checks their
syntax and ordering, but only an application-specific checker can establish
their meaning.

All-zero commit IDs and SHA-256 values are reserved placeholders and rejected
by production validation.

## Exact ranges and safe paths

Every coverage interval and payload interval is half open:

```text
[index_start, index_stop)
```

For each `coverage_id`, its payloads must form one exact partition of the
declared interval. The validator rejects empty intervals, gaps, overlaps,
duplicate paths, out-of-order shards, inconsistent roles, and a `row_count`
other than `index_stop - index_start`. These are logical coverage checks, not
proof that each row's contents are correct.

The deterministic list orders are exact: coverage records by `coverage_id`,
payload records by `(coverage_id, index_start, index_stop, path)`, source
records by `path`, and semantic commitments by `name`.

Paths are portable, normalized, relative POSIX paths using the restricted
ASCII alphabet accepted by the schema. The loader rejects absolute paths,
empty components, `.` or `..`, backslashes, repeated or aliased paths, and
payloads outside `payload_prefix`. It also rejects a declared file path that
would have to serve as an ancestor directory of another declared file.

When resolving Git objects, the verifier accepts regular blobs with the
declared mode. It does not follow a committed symlink or gitlink. Payloads
must be non-executable regular blobs. Source blobs must match their declared
`executable` bit.

## A checkout is only an untrusted resolver

A checkout path supplied to the verifier is not trusted as the corpus. It can
be dirty, have untracked files, or have a worktree path replaced after review.
The verifier reads the manifest, payloads, and sources from the Git object
database at the pin's exact commit. It does not read those bytes through the
worktree.

In particular, a resolver must:

1. verify that the pinned object resolves to the exact requested commit;
2. disable Git replacement-object behavior, interactive configuration, and
   promisor-remote lazy fetching;
3. inspect each committed tree entry and require the expected regular-blob
   mode;
4. stream that commit's blob bytes while checking size and SHA-256; and
5. compare every repeated expectation in the consumer pin to the canonical
   manifest.

A clean `git status`, a branch name, the checkout's current `HEAD`, and a local
path are not identities. They must never be written into an accepted report.
If no resolver is supplied, the fetch tool creates a fresh temporary Git
repository and fetches the exact commit from the pinned HTTPS URL.

The implementation requires Git 2.43 or newer and sets
`GIT_NO_LAZY_FETCH=1` for every Git subprocess. This is security-critical:
otherwise a missing object in an untrusted partial clone could invoke a
resolver-configured remote or command. When `--checkout` is supplied, the
checkout's configured remote URL is intentionally not compared with the
pin's URL. It is only an object resolver; the commit plus the reviewed
SHA-256 identities decide acceptance. Without `--checkout`, the pin URL is
the exact fetch origin.

The 40-hex Git object ID is useful for repository reachability; SHA-256 hashes
in the reviewed pin and manifest provide the byte identities used by this
protocol. A remote cannot substitute different accepted bytes merely by
moving a branch or tag.

## Private read-only snapshots

An optional materialization step copies only verified manifest, payload, and
source blobs into a fresh private cache. The copy is made from committed Git
blobs, not from worktree paths. A cache entry uses this domain-separated key:

```text
snapshot_key_sha256 =
  SHA256("sparkinterval/numeric-corpus-snapshot-key/v1\0"
         || canonical_json_bytes({
              "manifest_path": exact repository-relative manifest path,
              "manifest_sha256": exact manifest blob SHA-256
            }))
```

Including `manifest_path` prevents two pins for identical manifest bytes at
different in-tree paths from colliding.

Snapshot creation must fail closed:

- create files without following existing links;
- preserve only the declared executable/non-executable distinction;
- hash bytes while writing them;
- reject symlinks, hard links, devices, sockets, and other special files;
- reject missing and extra files;
- make the completed tree read-only; and
- publish it by an atomic rename only after the complete tree verifies.

An existing cache entry is never trusted because its directory name looks
right. It must pass the same exact-file-set, mode, size, and hash audit before
reuse.

This is a private-cache integrity convention, not filesystem-level
immutability against the owner. The cache root must have mode `0700`, and
there must be no concurrent writer using the same account while verification
or consumption is in progress. Modes `0444` and `0555` prevent accidental
changes but cannot stop the owner from changing them. A consumer must call
`verify_snapshot` immediately before consuming the paths, or consume directly
from the Git-object verification stream. Stronger hostile-local-writer
assurance requires facilities such as fs-verity or a read-only mount.

## Binding a corpus reference into a cloud receipt

The compact trusted-compute receipt format has one generic
`claim.input_hash`. It does not duplicate application-specific corpus fields.
For a computation whose large numeric input lives in a corpus repository, use
the **exact canonical pin file as the measured job's input artifact**. Then:

```text
HSM receipt signature
  -> claim.input_hash
  -> SHA256(exact canonical pin bytes)
  -> claim_id, statement_sha256, manifest_sha256, repository commit
  -> payload_root_sha256 and source_root_sha256
  -> every manifest-listed payload/source blob hash and logical range
```

The receipt issuer can require this relationship instead of accepting a
generic input:

```bash
python3 tools/trusted_compute_receipt.py issue \
  ... \
  --require-numeric-corpus-input
```

The flag parses the run bundle's exact input artifact as a canonical
`sparkinterval.pinned_numeric_corpus.v1` record, rehashes those same bytes,
checks their size, and requires the resulting SHA-256 to equal the signed
`claim.input_hash`. It emits a small audit projection containing the claim,
manifest, commit, payload-root, and source-root identities. The projection is
not added to receipt v1 and is not independently trusted; its authority is
the signed input hash.

A reviewer can reproduce the same projection from a returned receipt and the
reviewed pin:

```bash
python3 tools/trusted_compute_receipt.py verify \
  /returned/shard-000/trusted-compute-receipt.json \
  --public-key /reviewed-keys/production-receipt-public.pem \
  --numeric-corpus-pin path/to/reviewed-pin.json
```

This command verifies the receipt signature first and then requires the pin's
exact canonical bytes to match `claim.input_hash`. A pin downloaded from the
same untrusted worker is not a reviewed identity; use the source-controlled
consumer pin.

This binding proves identity, not semantic use. The source-reviewed cloud
workload must still resolve and verify the pinned manifest/blobs, and its
closed registered semantics must say how those bytes determine the result.
If the workload fetches shards after the challenge is installed, the corpus
resolver/checker belongs in the measured artifact closure and its complete
verification report belongs in the retained output/trace closure. Merely
placing a pin in the job does not prove that arbitrary code consumed all
listed rows.

The full payload does not need to live in this repository or be recomputed
locally. Local admission needs the small reviewed pin, code and artifact
hashes, focused known-answer/sample tests, independent evidence appraisal,
signature verification, and the Lean registry/consumer check. The exhaustive
finite scan can run on the selected Azure CPU/H100 workers. A full local rerun
is optional reproducibility evidence, not a prerequisite for cryptographically
binding a genuine cloud run.

## Publishing a production corpus

Use this sequence; do not generate a production pin from a dirty worktree:

1. Put the complete source closure and all payload shards in a dedicated
   corpus repository.
2. Write a source-shaped claim that a reviewer can compare directly with the
   theorem or external result that will consume it.
3. Declare every coverage range, parameter, payload, source file, and any
   application-specific semantic commitment.
4. Compute per-file SHA-256 values and sizes from the intended committed
   bytes. Compute the statement digest and aggregate roots with the domain
   rules above.
5. Serialize the manifest as canonical JSON, commit all referenced bytes, and
   obtain the exact immutable commit ID.
6. Independently read the manifest blob back from that commit. Record its
   exact byte size and SHA-256 in a new consumer pin.
7. Copy the manifest's identifiers and root expectations into the pin, and
   canonicalize the pin.
8. Have a second reviewer audit the statement, ranges, parameters, source
   closure, and pin before admitting it to the consuming repository.
9. Run the strict fetch/verify tool against the exact pin. If desired,
   materialize and separately archive the verified read-only snapshot.

For example, verify through an existing untrusted object resolver:

```bash
python3 tools/fetch_tg_numeric_corpus.py \
  path/to/reviewed-pin.json \
  --checkout /path/to/corpus-repository
```

Or fetch the pin's exact HTTPS origin and build a private verified snapshot:

```bash
install -d -m 0700 /path/to/numeric-corpus-cache
python3 tools/fetch_tg_numeric_corpus.py \
  path/to/reviewed-pin.json \
  --cache-root /path/to/numeric-corpus-cache
```

An accepted resolver report establishes only that the pinned bytes were found
and checked. Record the separate mathematical checker or proof that consumes
those bytes.

## Review checklist

Before accepting a pin, a human reviewer should be able to answer yes to each
question:

- Is the repository URL the intended public or controlled origin?
- Is the reference a full commit ID rather than a mutable name?
- Was the pin reviewed independently of the location serving the corpus?
- Does the exact statement say what the consuming theorem needs?
- Does `statement_sha256` recompute from that exact text?
- Do claim and corpus version changes reflect semantic changes?
- Do parameters include every bound, scale, rounding convention, and format
  choice needed to interpret the rows?
- Does each coverage interval have an exact, gap-free, non-overlapping shard
  partition?
- Do the source records include the generator, checker, and non-code inputs
  required for reproduction?
- Do all file sizes, file SHA-256 values, aggregate roots, and repeated pin
  expectations recompute?
- Were the bytes read from the pinned Git commit rather than a worktree?
- Is the downstream checker or trust assumption stated separately?

## Templates are deliberately invalid

[`examples/numeric-corpus`](../examples/numeric-corpus/) contains a complete
field-layout example. Its commit and digest values are all-zero placeholders,
which the structural schemas reject, and the JSON is formatted for reading
instead of canonical wire use. Production validation must reject both
templates.

Do not replace only the zeroes and call the result a pin. Generate all sizes,
hashes, roots, and canonical bytes from committed production content, then
review the resulting claim and coverage as described above.
