# Hurst affine versus two-pass bounded qualification

Status: bounded exact-output qualification implemented and replayed; no
source-scale run, primitive-row proof, compiler proof, attestation, or Lean
atom discharge is claimed.

## What is compared

`tg_verifier/hurst_affine_equivalence.py` runs the same captured Hurst adapter
in all three of its modes:

1. `summary`, which emits one exact four-coordinate delta;
2. `verify`, which replays the shard at an exact incoming state; and
3. `affine`, which emits the incoming-state guards for the same replay.

The qualification retains the exact stdout bytes for every mode, their
SHA-256 digests, and a readable copy parsed with exact decimal numbers.
Independent replay requires equality of every mode-independent field,
including:

- range and segment geometry;
- row encoding and V2 squarefree endpoint policy;
- fixed reduction-block size;
- Möbius-row SHA-256;
- state-component order and four-coordinate delta;
- acceptance; and
- the two negative trust-boundary fields.

Timing, mode, guards, and exact-fallback counters are deliberately not in the
cross-mode equality projection because their meanings differ by mode. Within
one mode, every repeated output must be byte-semantically identical after
removing only `elapsed_seconds`.

For multiple shards, the checker translates every affine guard back to the
initial root by subtracting all preceding exact deltas, intersects every
translated atom guard, chooses or checks one root in that intersection, and
then reconstructs every incoming, outgoing, and terminal state. The verify
receipts must contain singleton guards equal to those exact derived incoming
states. This is the bounded computational counterpart of the ordinary-Lean
prefix fold.

The retained format rejects missing records, repeated records in a different
order, changed ranges, changed raw bytes, changed readable reports, changed
hashes, cross-mode row/delta disagreements, timing arithmetic changes, and
any positive trust-boundary flag.

## Current source-built measurements

On 2026-07-25 the current adapter source was compiled on the 20-core ARM DGX
Spark host against the pinned Hurst source. The resulting bounded executable
had SHA-256
`a1bd906424ca53ad7c6171d371344015d707249c4b7e9d28313e9a59ea2dd486`.
The separately bound files were:

| Item | SHA-256 |
| --- | --- |
| `reference/tg_hurst_residual_shard.cpp` | `0db4fb4cf0ff4e0d69e1c46ad7c618d467779d9a61346f067c5384143e92be6f` |
| `specifications/HURST_MERTENS_UPSTREAM.json` | `e6fa9d5b94f1aa4d5d0c62be872934076014947372ad5dd6e076c684ebb0fbcd` |

The representative terminal range was
`[9,999,999,980,000,001, 10,000,000,000,000,001)`, or 20 million rows,
with one 20-million-row shard, one segment, eight OpenMP threads, and three
mode-rotated repeats. Exact runner medians were:

| Mode | Median seconds |
| --- | ---: |
| summary | `0.930034` |
| verify | `1.058600` |
| two-pass total | `1.988634` |
| affine | `1.133840` |

Thus `(summary + verify) / affine` was
`1.753892965497777464192478657`. Process-wall medians gave
`1.764013366468774603661431561`. This reproduces the previously reported
approximately `1.75x` improvement using the current source-built binary and a
single artifact that also proves exact output/terminal-state equivalence. It
is a bounded terminal-range measurement, not a full-source ETA.

The exact same 20-million-row interval was also split into four consecutive
five-million-row shards. That replay exercised translated guard intersection
and four-step prefix merging. It produced the same final state

```text
(M, Q, littleLowerQ96, littleUpperQ96)
= (5808, 6079271015690292, 0, 0)
```

as the single-shard qualification. Its runner medians were `3.616063` seconds
for summary, `3.802122` seconds for verify, and `3.904366` seconds for affine,
or `1.899971723962353939154269861x`. The larger ratio includes repeated
per-process prime-table startup and is not the representative source
arithmetic speedup; its purpose is merge qualification.

The two local artifacts had canonical SHA-256 digests:

| Shape | Artifact SHA-256 |
| --- | --- |
| one 20-million-row shard | `dcd7142f664716b955ef867c565497e6c8760fb36adb089884d40d96fe2d06a4` |
| four five-million-row shards | `d0d2f7ab25beb370f6d1bdd882e97789dafbe576aa6e0b17b2a42583e692aaa8` |

They are intentionally not checked into the repository: they are local
benchmark outputs, not production evidence.

## Reproduction

After building the current Hurst adapter, run:

```bash
python3 tools/tg_hurst_affine_equivalence.py run \
  --runner /path/to/sparkinterval-tg-hurst-residual-shard \
  --runner-source reference/tg_hurst_residual_shard.cpp \
  --upstream-manifest specifications/HURST_MERTENS_UPSTREAM.json \
  --output /tmp/hurst-affine-equivalence.json \
  --domain-lower 9999999980000001 \
  --domain-upper-exclusive 10000000000000001 \
  --shard-span 20000000 \
  --segment-size 20000000 \
  --repeat-count 3 \
  --runner-threads 8 \
  --timeout-seconds 120

python3 tools/tg_hurst_affine_equivalence.py verify \
  --runner /path/to/sparkinterval-tg-hurst-residual-shard \
  --runner-source reference/tg_hurst_residual_shard.cpp \
  --upstream-manifest specifications/HURST_MERTENS_UPSTREAM.json \
  /tmp/hurst-affine-equivalence.json
```

The qualifier intentionally refuses the literal full source range. Its
capability record fixes all of the following to false:

- full-source completion;
- independent primitive-row realization;
- proof that the executable was compiled from the bound source;
- execution attestation;
- Lean atom discharge; and
- extrapolation of the bounded speedup to a source-scale ETA.

## Remaining production seam

The one-pass arithmetic transformation is now strongly qualified at the
bounded executable level. Production still needs a reviewed physical-row
realization for the affine worker, a source/compiler or machine-code
refinement boundary acceptable to the project, calibrated source-scale Azure
partitioning, a complete confidential run, and receipt admission through the
registered Lean execution bridge. Until those are supplied, the registered
two-pass source-capable campaign remains the trust-bearing route.
