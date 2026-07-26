# Source-streaming Dirichlet state v3

`TGDCSB03` is a bounded-memory producer-to-finalizer vertical slice for the
Platt Theorem 7.1 sign scan. It removes two storage hazards from the older
prototype:

- it does not retain the 226.996-TB `TGDBSQR3` sample stream or the 1.182-TB
  packed-sign family when the arithmetic producer supplies character-major
  sign chunks directly; and
- it replaces the 104-byte `TGDCSB02` index for every primitive character
  with a dense bit record and formulaic primitive ordinal.

This is engineering infrastructure, not source evidence. No source-scale
arithmetic run has used this path. The typed host-side small-q producer
boundary and runner-side two-bit packing described below are implemented.
GPU-side packing, interval usefulness, ambiguity refinement, Turing
realization, trusted execution, and the physical Lean realization remain
absent.

## Production record

For a fixed q and exact half-open sample grid, each primitive character has:

- four bits for determinate, first-positive, last-positive, and sparse flags;
- a transition count packed at
  `max(1, (sample_count - 1).bit_length())` bits; and
- no fixed byte offset or character identifier.

The primitive character is the canonical list position. The complete roster
SHA-256 binds that list, but a digest is never promoted to mathematical
completeness. The later Lean handoff needs the explicit
`PrimitiveRosterRealization.characterEquiv` / `indexEquiv` equivalence.

Pages contain at most 4,096 characters. The sparse flag is a rank/select
bitmap: popcount before one ordinal selects its sparse row. Production sparse
rows retain only maximal half-open ambiguity ranges. First and last
determinate ordinates are uniquely derived from the page span and its leading
and trailing ranges. Replay rejects impossible flag combinations, nonzero
padding, count overflow, reordered or adjacent split ranges, roster changes,
and source-span substitutions.

Exact 32-byte bracket coordinates are available only in debug mode. Any debug
artifact has `source_scale_layout=false`; the source admission function still
fails unconditionally. At the earlier illustrative—not measured—38-trillion
bracket count, exact bracket rows would still require 1.216 PB.

## Factored small-q producer boundary

`dirichlet_booker_smallq_compact_v3.py` consumes the existing typed,
character-major `TGDBSQR3` service stream and feeds strict completed-real
codes directly into `TGDCSB03`. It does not write the 226.996-TB disk stream
or the 1.182-TB `TGDBSSG1` sign family.

The certified CUDA runner now also has a distinct full-span `TGDBSPK1` mode.
Its host reference applies the outward binary64 boundary after copying the
full disk array; its device mode applies the same rule to final CUDA disks and
copies only four two-bit codes per byte plus one bounded status summary. The
compact-v3 packed consumer validates exact
plan/batch/control/receipt/partition/roster/pinset/span/mode bindings, a
domain-separated frame-hash chain, payload hashes, terminal coverage, and
EOF. This reduces the transient runner-to-consumer stream to approximately
1.182 TB without persisting that family and removes the complete disk
device-to-host copy in device mode. The exact format, invocation, local
differential benchmark, tests, and remaining boundary are in
[`DIRICHLET_SMALLQ_PACKED_SIGN_TRANSPORT.md`](DIRICHLET_SMALLQ_PACKED_SIGN_TRANSPORT.md).

The adapter fails closed unless one typed external pinset exactly matches:

- the SHA-256 of the complete `TGDBSQP3` shared-frequency plan/cache;
- the time-tail control and its higher-precision replay receipt;
- the ordered character-batch partition;
- both the plan-format roster commitment and canonical `TGDCSB03` roster
  commitment; and
- q, exact 5/64 half-open span, and structural-KAT/full-source mode.

It also replays the canonical primitive character identifiers and parities,
checks each service header/batch binding and every item identity/status,
requires EOF, binds the control-table file descriptor to the pinned input
snapshot, and rehashes and restats every bound input before publication. The
artifact, lane, exception, and retirement entry points reject symbolic input
files and dangling symbolic output paths rather than resolving through them.
The exact raw-stream SHA-256 is computed during the single consuming pass and is
in the fused receipt only; it is not known or pinned before reduction. The
compact artifact's source-binding field covers the immutable pinset but
cannot recover that raw-stream hash. Therefore the self-hashed receipt and
state must be retained and reviewed as a pair; neither is an execution
attestation.

Batch preflight streams each q-word exponent table, checks its wire shape and
that every word is in the group-exponent range, and hashes the exact table
into the pinned ordered batch partition. It does **not** recompute the
canonical character exponent or epsilon values. Likewise, preflight streams
and structurally validates every shared-frequency seed record but does not
higher-precision-recompute its analytic value. That independent
higher-precision factored-campaign replay remains an upstream obligation (or
must be covered by the eventual trusted execution receipt). The fused receipt
states these limitations explicitly. Host memory is bounded by the compact
character roster, a 1,024-record shared-seed validation chunk, one q-word
table, an item chunk of at most 1,048,576 rows, one v3 page, and sparse ranges
for those active characters—not by the raw sample count or the complete
exponent campaign.

Production mode accepts only the complete canonical small-q source span. An
explicit `structural_bounded_span_kat` mode exists only for bounded protocol
tests and never enables source admission. The q=5460 test uses the complete
165-character canonical roster and a six-sample prefix, exercises both scalar
and NumPy paths, and injects pin, span-mode, row, truncation, trailing-byte,
control-descriptor substitution, post-hash input mutation, and mid-run input
mutation failures. It also exhibits two structurally valid raw streams with
the same sign state but different receipt-only raw hashes, making the
receipt/state retention boundary executable rather than implicit. It is not
an arithmetic/source KAT.
On the local aarch64 DGX Spark host on 2026-07-23, after adding complete
structural shared-seed replay, that synthetic NumPy slice streamed 47,688
bytes into a 7,041-byte state in 0.800 seconds for the reducer call, of which
0.047 seconds was the state writer. The one-off Python process including
fixture construction took 1.06 seconds with 67,740 KiB maximum RSS. These
numbers measure only the bounded protocol fixture, not DFT production or
source throughput.

The operational CLI loads a canonical
`sparkinterval.tg.dirichlet_booker_smallq.compact_v3_pinset.v1` file and
requires its digest again through an out-of-band argument:

```bash
python3 tools/tg_dirichlet_booker_smallq_semantic_reducer.py \
  reduce-compact-v3 PLAN BATCH_DIRECTORY CONTROL CONTROL_RECEIPT \
  PINSET STATE RECEIPT \
  --expected-pinset-sha256 EXPECTED_SHA256 \
  --input TGDBSQR3_PATH_OR_FIFO
```

For runner-packed input, use `reduce-packed-compact-v3` with the same typed
inputs and pinset. The stream may arrive on stdin or through `--input`; no
packed-sign artifact is required.

“Out of band” is an authority boundary: the expected digest must come from a
reviewed manifest or trusted campaign configuration. Computing it from the
same unreviewed pin file immediately before this command proves only file
consistency, not that the pins are the intended source identities. The
reducer can report exact pin/input equality but explicitly cannot establish
that external authority. Likewise, its formulaic duplicate-free roster check
does not realize the later Lean roster equivalences.

## Cross-lane closure

The finalizer freshly replays up to eight adjacent lane heads. It streams the
same primitive ordinal from every lane, sums internal transition counts, and
adds exactly one boundary transition when the outer determinate signs differ.
The merged output derives its count width from the full merged span, so a
lane-width count is never narrowed into the final artifact.

The output header's grouping-independent `source_binding_sha256` is SHA-256
over q, roster, full span, and the associative rolling-field leaf summary.
The rolling-field input is not collision resistant, so this value does
**not** cryptographically commit every lane's upstream SHA-256 binding. The
finalizer receipt separately pins the ordered lane artifact SHA-256 values;
those pins are receipt-only and are not recoverable from the merged artifact
alone. Source admission therefore remains false.

After merge, the dense pages can be retired only when their aggregate matches
the supplied q-level Turing total. Retirement retains:

- one q summary containing the aggregate transition count and supplied Turing
  total; and
- a sparse ambiguity artifact with exact ranges and an ordered Merkle-mountain
  commitment.

The implementation durably links and directory-fsyncs the retained summary
before unlinking and directory-fsyncing the dense state. A pre-existing
summary or an aggregate mismatch refuses retirement without deleting the
dense state. This ordering is crash-durability engineering, not evidence for
the analytic meaning of either aggregate.

`discard_dense_state=false` is the reproducibility default. The q summary and
ambiguity artifact do not retain the per-character transition counts or
endpoint families consumed by the Lean theorem below, so they cannot support
an independent replay by themselves. Destructive retirement is appropriate
only after a separately retained archive or accepted trusted-execution result
assumes responsibility for that lost replay surface.

Aggregate equality alone is not completeness. The summary names the exact
boundary proved by
`SparkInterval.Dirichlet.AggregateTuringClosure`: every per-character
transition count must already be a multiplicity-preserving zero lower bound,
every Turing count must be an upper bound for the same character, and both
sums must range over the same complete duplicate-free roster. Nonnegative
deficits plus equal finite sums can then force per-character equality. The
physical v3 receipt currently sets all three realization flags to false. The
q=1 zeta case is separate.

## Exact storage projection

The projection recomputes all values from `primitive_character_count`,
`maximum_t_index`, and the authenticated eight-lane boundaries. For
q=10001..400000 it finds 29,547,446,729 character states and
191,701,043,433,012 character samples.

| retained state | dense byte floor | canonical bytes before ambiguity ranges |
|---|---:|---:|
| one merged final state | 62,259,950,420 | 62,968,524,843 |
| eight lane heads total | 313,234,007,491 | 317,542,970,540 |

Per-q/page padding alone makes the eight-lane dense payload
313,234,745,972 bytes. The final count-width histogram is:

| bits | characters |
|---:|---:|
| 12 | 10,240,064,835 |
| 13 | 14,719,219,258 |
| 14 | 3,478,761,803 |
| 15 | 845,913,314 |
| 16 | 211,464,707 |
| 17 | 52,022,812 |

No genuine ambiguity density is known. A deliberately conservative
sensitivity charges one 8-byte sparse header and one 16-byte range for every
ambiguous sample. Under that pessimistic no-clustering model, densities of
10^-6, 10^-5, 10^-4, and 10^-3 add approximately 4.60 GB, 46.01 GB,
460.08 GB, and 4.60 TB. These are not expectations or measurements; maximal
ranges and multiple ranges in one character reduce the row-header component.

## Bounded q=10001 benchmark

On the local aarch64 DGX Spark host on 2026-07-23, the synthetic 64-sample
q=10001 path processed 9,585 characters and 613,440 sign codes. Ten
characters had one two-sample ambiguity range. The 12,694-byte artifact took
0.243 seconds to write and freshly replayed in 0.054 seconds, with 48,284 KiB
maximum RSS. This is a codec/control-plane KAT, not an arithmetic or
source-scale throughput estimate.

```bash
python3 tools/benchmark_tg_dirichlet_compact_state_v3.py --pretty

PYTHONPATH=. python3 -m unittest -v \
  tests.test_tg_dirichlet_compact_state_streaming_v3 \
  tests.test_tg_dirichlet_booker_smallq_compact_v3
```

The focused tests cover direct producer output, exact replay, page padding,
count overflow, power-of-two count capacity, maximal-range canonicalization,
full-span lane widening, cross-boundary changes, three-lane associativity,
debug-mode rejection, roster/span substitution, exception MMR replay and
post-read mutation rejection, and fail-closed/durable dense-page retirement.
Replay returns the hash and
metadata accumulated by its single semantic pass and checks inode, size,
mode, mtime, and ctime stability around that pass. The finalizer captures
each lane hash/header from that same exhausted semantic pass; it does not
reopen lanes later to construct a receipt for potentially different bytes.
