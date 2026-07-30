# PT21 verification-ladder wire formats

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

Four levels.  Each level names the exact proposition it supports and the
exact thing it stops supporting.

| Level | Unit | Count at source scale | Wire size | Checked by |
|---|---|---:|---:|---|
| L0 | block sign packet | 2,966,443,783 | 3,339 B each, **9.9 TB** | CompCert-compiled `pt21_ladder_check.c` inside the attested run |
| L1 | window summary | 2,966,443,783 | 32 B each (never serialized) | same checker; exists only as a `Prop` witness in Lean |
| L2 | group summary | 90,530 at 32,768 blocks/group | 88 B each, **7.97 MB** | the same checker **and** the Lean kernel |
| L3 | campaign record | 1 | 88 B | the Lean kernel |

The L1 level is deliberately never written out.  It is the granularity at
which the mathematics lives (`WindowSummary` in
`SparkInterval/Zeta/PT21Ladder.lean`), but materializing 2.97e9 records
would cost 95 GB and buy nothing: L2 already commits to every one of them.

## L0 -- block sign packet (3,339 bytes)

All multi-byte integers are big-endian.  Signed fields are two's
complement.  Bit `j` of a bitmap byte string is
`bytes[j >> 3] >> (j & 7) & 1`; `1` means the evaluator enclosure at that
lattice sample is strictly positive and `0` means strictly negative.

| Offset | Width | Field |
|---:|---:|---|
| 0 | 8 | magic `50 54 32 31 4C 30 01 00` (`PT21L0\x01\x00`) |
| 8 | 8 | block index |
| 16 | 8 | multiplicity count at the block's left ordinate |
| 24 | 8 | multiplicity count at the block's right ordinate |
| 32 | 4 | isolated multiplicity slots |
| 36 | 4 | resolved stationary cells, at most 8 |
| 40 | 32 | stationary cell indices (8 x 4 bytes, unused entries zero) |
| 72 | 8 | `S(t)` enclosure low, left flank, scale `2^10` |
| 80 | 8 | `S(t)` enclosure high, left flank |
| 88 | 8 | shared Gamma/log-pi term low, left flank, scale `2^10` |
| 96 | 8 | shared Gamma/log-pi term high, left flank |
| 104 | 8 | `S(t)` enclosure low, right flank |
| 112 | 8 | `S(t)` enclosure high, right flank |
| 120 | 8 | shared Gamma/log-pi term low, right flank |
| 128 | 8 | shared Gamma/log-pi term high, right flank |
| 136 | 3,073 | main-stream sign bitmap, samples `-12288 .. 12288` (24,577 bits) |
| 3,209 | 65 | left-flank sign bitmap, samples `-12800 .. -12288` (513 bits) |
| 3,274 | 65 | right-flank sign bitmap, samples `12288 .. 12800` (513 bits) |

Bits beyond the last sample in each bitmap are padding and must be zero.

### What the L0 checker actually verifies

1. Magic, packet length, and canonical padding.
2. The block index equals the running cursor -- **no block may be skipped,
   repeated, or reordered.**
3. The advertised left-endpoint count equals the running count carried from
   the previous block.
4. `slots = (main-stream sign changes) + 2 * (stationary cells)`.  The slot
   count is *derived from the bitmap*, not trusted.
5. Every stationary cell is inside the main lattice, strictly increasing,
   and sits on a cell with **no** sign change (a resolved double zero is
   invisible to the lattice scan).
6. The endpoint-sign parity check from Platt's source: the two main
   endpoints agree iff `slots` is even.
7. The shared endpoints of the three streams agree.
8. The two one-sided Turing lattice weights are recomputed from the flank
   bitmaps using Platt's `Nleft_int` / `Nright_int` formulas
   (`-multiplicity * leftStep` and `multiplicity * (span - rightStep)`),
   and the ceiling/floor cell conditions are checked in exact integer
   arithmetic at scale `2^10`.  **A producer cannot advertise an endpoint
   count that does not follow from the signs it published.**
9. `lowerCount + slots = upperCount`.

### What the L0 checker does *not* verify

It never sees a Hardy-Z value.  A sign bit is an *assertion* that the
evaluator's directed enclosure at that lattice ordinate had that sign.
Justifying the bit is the evaluator's job, and the evaluator's output is
`1.24e13` directed intervals that no third party will ever re-derive from
the packet.  That obligation is `EndpointRealization` in
`SparkInterval/Zeta/PT21ArtifactBinding.lean` and it is discharged by
attestation, not by this checker.

Likewise the two `S(t)` and Gamma/log-pi enclosures are Arb outputs; the
checker verifies the *integer consequences* of those intervals, not that
the intervals contain the real quantities.

## L2 -- group summary (88 bytes)

| Offset | Width | Field |
|---:|---:|---|
| 0 | 8 | first block index |
| 8 | 8 | block count |
| 16 | 8 | count at the group's left ordinate |
| 24 | 8 | slots in the group |
| 32 | 8 | count at the group's right ordinate |
| 40 | 32 | group digest |
| 72 | 8 | group index |
| 80 | 8 | reserved, zero |

The group digest is SHA-256 over the concatenation, in block order, of
64-byte records

```text
block (8) || lowerCount (8) || slots (8) || upperCount (8) || sha256(packet) (32)
```

so it commits to both the level-1 summary and the level-0 packet bytes.

This is the record the Lean kernel reads.  It is exactly
`SparkInterval.Zeta.PT21Ladder.GroupSummary`; the kernel-side check
`runGroups` verifies first-block contiguity, count contiguity,
non-emptiness, digest length, and local closure.

## L3 -- campaign record (88 bytes)

Same layout, with `first block index = 0`, `block count = 2,966,443,783`,
and `group digest` replaced by the campaign root: SHA-256 over the
concatenation, in group order, of 64-byte records

```text
sha256(groupRecord) (32) || groupIndex (8) || firstBlock (8) || blocks (8) || slots (8)
```

## Building and running

```bash
cd cpu_checker/pt21_ladder
make            # host compiler
make test       # known-answer and mutation tests
make ccomp      # CompCert build of the checker unit only
./pt21_ladder_bench --blocks 300000
./pt21_ladder_bench_ccomp --blocks 300000
```

`--no-packet-commit` disables the per-packet SHA-256.  That is a *weaker*
mode: the group digest then binds only the summaries, so nobody outside
the attested run can re-derive them from retained packets.  It exists to
separate the cost of hashing from the cost of checking, and must not be
used in production.
