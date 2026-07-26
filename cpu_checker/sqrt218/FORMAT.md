# Sqrt218 fixed-width CPU checker V2

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

This format is a future verified-CPU target for the finite arithmetic behind
Helfgott's equation (2.18). It is not the canonical-JSON V1 archive currently
named by the registered algorithm, and no V2 production receipt exists.

In this document, “V2” means only the fixed-width `SQ218V2\0`
binary-checker protocol and its matching Lean semantics. The separately named
Lean structure `ReceiptArtifactFieldsV2` is a proposed signed-field extension
around the existing canonical-JSON V1 archive and V1 work trace. It neither
parses this binary format nor binds this checker. A future registered profile
must join them explicitly; the shared version number is not a protocol link.

The design keeps parsing and arithmetic small enough for a future verified
compiler path:

- all multi-byte integers are unsigned big-endian;
- input is read byte-by-byte, without packed-struct casts;
- every section has a fixed record width;
- all section products, additions, indices, and slices are checked;
- the exact accumulator is two `u64` limbs, with explicit overflow rejection;
- every two-limb arithmetic helper passes `hi` and `lo` as scalar arguments
  and returns limbs through scalar output pointers; no helper passes
  `tg_sq218_u128` by value;
- factor entries name earlier prime rows rather than asking the checker to
  decide primality again; and
- explicit nontrivial factor pairs cover every integer in each open gap
  between consecutive primes and in the terminal gap through `bound`.

The receipt layer must hash the complete V2 byte string and bind it to the
exact algorithm/profile/result. The binary format does not replace that
binding.

## Header

The header is exactly 160 bytes.

| Offset | Width | Field |
|---:|---:|---|
| 0 | 8 | magic `53 51 32 31 38 56 32 00` (`SQ218V2\0`) |
| 8 | 2 | version, exactly `2` |
| 10 | 2 | header width, exactly `160` |
| 12 | 4 | flags, exactly zero |
| 16 | 8 | inclusive bound |
| 24 | 8 | reused-prime bound |
| 32 | 8 | log seed endpoint, exactly `30` |
| 40 | 8 | log scale, exactly `2^48` |
| 48 | 8 | reciprocal-square-root scale, exactly `2^30` |
| 56 | 8 | prime-record count |
| 64 | 8 | factor-reference count |
| 72 | 8 | composite factor-pair count |
| 80 | 8 | prime-power event count |
| 88 | 8 | power-index-reference count, exactly the event count |
| 96 | 8 | prime-record offset |
| 104 | 8 | factor-reference offset |
| 112 | 8 | factor-pair offset |
| 120 | 8 | event offset |
| 128 | 8 | power-index-reference offset |
| 136 | 8 | exact archive byte length |
| 144 | 16 | reserved, exactly zero |

Sections must be contiguous in the order above, starting at byte 160. The
power-index-reference section must end at the declared archive byte length
and exactly at EOF. Thus aliases, overlaps, gaps, trailing bytes, and
offset/count overflow all fail closed.

## Prime record

Each prime record is 80 bytes.

| Offset | Width | Field |
|---:|---:|---|
| 0 | 8 | prime value `p` |
| 8 | 8 | Lucas witness |
| 16 | 8 | first factor-reference index |
| 24 | 4 | factor-reference count |
| 28 | 4 | preceding-gap factor-pair count |
| 32 | 8 | first preceding-gap factor-pair index |
| 40 | 8 | first power-index-reference index |
| 48 | 4 | power-index-reference count |
| 52 | 4 | reserved, exactly zero |
| 56 | 8 | directed scale-`2^48` log lower endpoint |
| 64 | 8 | directed scale-`2^48` log upper endpoint |
| 72 | 8 | reserved, exactly zero |

Factor-reference and gap slices are canonical contiguous partitions of their
sections. Every factor reference in row `i` must be less than `i`; the
referenced prime values, with multiplicity, must multiply exactly to `p - 1`.
The Lucas residues are then checked using overflow-free modular arithmetic.
The distinguished base row is `p = 2`, witness `0`, and an empty factor
list, matching the proved V2 prime-roster semantics.

The gap belonging to a row covers every natural number strictly between the
preceding prime (or `1` for the first row) and this row's prime. Any factor
pair `(a,b)` must satisfy `1 < a`, `1 < b`, and `a*b = n` exactly. Unclaimed
factor-pair records after the last row are the canonical terminal gap through
`bound`.

## Factor, event, and inverse-map records

A factor reference is one 8-byte earlier-prime index.

A composite factor pair is 16 bytes: an 8-byte left factor followed by an
8-byte right factor.

Each event is 32 bytes:

| Offset | Width | Field |
|---:|---:|---|
| 0 | 8 | prime-power value |
| 8 | 8 | prime-row index |
| 16 | 4 | positive exponent |
| 20 | 4 | reserved, exactly zero |
| 24 | 8 | floor square root |

Each power-index reference is one 8-byte event index. A prime row's
contiguous slice names the events for exponents `1, 2, ...` in that exact
order. The total number of references equals the number of events. Every
referenced event must agree with its prime row and exponent, and every row
must end at the maximal power not exceeding `bound`. Because distinct
`(prime row, exponent)` cells cannot reference the same event, equal finite
source and target counts make the checked map exhaustive without a
production-sized bitmap or a prime-count-times-event-count scan.

The current scaffold checks every emitted event, strict value order, exact
checked exponentiation, the supplied square root, the flattened inverse map,
the exact 30-seed then integer log ladder, the directed reciprocal formula,
both two-limb accumulators, and the strict event head guard. The sole
production byte entry `tg_sq218_validate_bytes_v2` first parses the canonical
sections and then calls a private all-stages routine, which requires the exact
bound-`2,000,000` profile and invokes roster, layout, log, event-fold, and
anchor stages. Callers cannot bypass byte parsing with a hand-built view. Its
C contract requires one private immutable input snapshot for the entire call
and nonoverlapping result storage. The measured executable must hash and
retain those same bytes; checking a mutable mapping and later hashing a
different snapshot would not meet the Lean byte model.

`tg_sq218_verify_snapshot_v2` is the flat proof-facing ABI proposed for a
future VST/CompCert proof: it accepts a `uint64_t` length, emits the canonical
120-byte record, and returns the checker status through a `uint32_t` pointer.
The established `tg_sq218_validate_bytes_v2` and
`tg_sq218_validate_snapshot_to_record_v2` APIs remain unchanged. The new
entry can now be built through `TG_SQ218_PURE_ENTRY_ONLY`, which excludes
every POSIX include and command-line/file branch from the translation unit.
The production pure-entry target also rejects a non-x86-64 compiler; its
separately named host build is development-only. The mathematical outer
composition is proved in `CCompleteValidationRefinement.lean`: successful
parser, roster, layout, log-row, scan, and anchor traces imply the exact V2
`completeCheck` without replaying the archive. The thirty closed seed cells
have a separate ordinary-Lean proof, and the pure source SHA-256 algorithm is
proved for arbitrary bytes. The literal successful validate-all/bytes-wrapper
call order is also modeled and composed with the wrapper guards and result
encoder. Proving that compiled execution constructs those relational traces
and produces the modeled hash/result bytes through the reviewed CompCert/VST
path remains future work.

`sqrt218_cpu_checker_v2` is the narrow production command around that entry
point. It reads a regular input file into one private owned allocation, closes
the input, validates only that immutable snapshot, and writes a separate
canonical result file with exclusive-create semantics. The exact 120-byte
output is specified in `RESULT_FORMAT.md`; it includes SHA-256 computed
directly over that same owned snapshot before the allocation is freed. It does
not yet construct a confidential-compute receipt. The following stages are
still required before this can replace V1:

1. bind the exact 120-byte result and measured executable identity into the
   V2 production receipt profile;
2. prove the measured compiled entry constructs the existing successful
   parser/roster/layout/log/scan/anchor/hash/result trace;
3. a verified compiler/assembler/linker/loader path, or an equally explicit
   translation-validation boundary, down to the measured x86-64 executable;
4. the actual confidential-cloud run and independently appraised receipt.

Attestation alone proves none of the items above.

## Lean mapping and present trust boundary

`SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/V2Adapter.lean` maps the
flattened sections and computed exit state into the exact
`Sqrt218Operational.V2.Archive` type. Its `completeCheck` is definitionally
`Sqrt218Operational.V2.run`, so ordinary Lean proves a successful
`completeCheck` implies the source claim.

The production Lean entry point `Sqrt218Operational.V2.run` remains fixed to
the paper cutoff `2,000,000`. The generic `runAt expectedBound` is a test
surface, not a source-claim theorem or a way to relax that cutoff.
`Operational/V2/RunTest.lean` builds the complete bound-5 archive matching
the C KAT (primes `2,3,5`, events `2,3,4,5`, directed seed logs, and the exact
four-event exit), checks every V2 semantic pass with `runAt 5`, and confirms
that production `run` rejects the same archive. No anchor or head guard is
weakened for that test.

That theorem does not yet apply directly to a C return code.
`NativeAcceptanceRefinesV2` is the precise, uninhabited obligation saying
that every measured native acceptance is an acceptance by the byte decoder
followed by the complete Lean V2 reference semantics, with the same result.
The stronger `NativeRunnerRefinesV2` also requires exact rejection-reason
equality, which the deliberately coarser C status API does not promise. The
repository does not currently prove the C source, compiler,
assembler/linker, ELF loader, x86-64 execution, or physical CPU refines the
acceptance path. The confidential-compute receipt may bind the exact binary
and run while this remains the single disclosed architecture edge; it must
not be described as a compiler or ISA proof.

## Local scope

`make test` compiles and runs only the C bound-5 known-answer/tamper/alias
tests plus the first post-seed log recurrence at `31`. It also confirms that
both the production-only byte entry and the file command reject the bound-5
profile, that a rejection result is canonical, and that input/output aliases
fail without modifying the input.
`Operational/V2/RunTest.lean` is the complete Lean `runAt 5` KAT, and
`Operational/V2/LogRowsTest.lean` checks the exact 30-seed table. These tests
do not open or generate production data. Production-sized replay belongs
only in the measured cloud job.
