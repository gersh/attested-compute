# Sqrt218 pure-entry source-refinement map

This is the review map for the successful path rooted at
`tg_sq218_verify_snapshot_v2`. It covers every locally defined `tg_*`
function reachable from that entry in:

- `cpu_checker/sqrt218/sqrt218_cpu_command.c`;
- `cpu_checker/sqrt218/sqrt218_cpu_checker.c`.

The scope is the union of source branches that can participate in a
successful call. It is not one production execution, and nothing in this
document or its audit script reads a certificate.

The map currently contains **50 reachable functions**. The other three local
`tg_*` definitions in the two files—`tg_read_exact_snapshot`,
`tg_write_new_result`, and `tg_sq218_run_files_v2`—belong to the file-I/O
command path and are not reachable from the pure entry.

## How to read the closure column

- **S — source proof closed:** the source-level arithmetic or byte algorithm
  has an ordinary Lean model and a theorem connecting it to the target Lean
  semantics.
- **T — trace composition closed:** Lean proves that the listed successful
  source relation supplies the downstream theorem. Constructing that
  relation from an actual compiled execution remains open.
- **G — successful guard captured:** the exact successful value-level guard
  is recorded, but pointer/ABI execution is deliberately outside pure Lean.

Every row still has the same final physical boundary: this repository does
not contain CompCert semantics or a proof that a particular ELF/ISA
execution implements the C source. In particular,
`CSHA256Refinement.ConcreteExecutionMatchesSource` and
`CPureEntryComposition.CSuccessfulPureEntryTrace` expose rather than hide
that boundary.

## Command-side pure entry, SHA-256, and result record

| C function | Exact source role | Lean model / theorem | Successful status or guard mapping | Closure |
|---|---|---|---|---|
| `tg_sq218_verify_snapshot_v2` | Flat `uint64_t`-length pure ABI; checks pointers, the `size_t` round trip and status-output disjointness, delegates to the inner wrapper, and copies its status. | `CPureEntryComposition.CSuccessfulPureEntryTrace`; `CSuccessfulPureEntryTrace.resultMeaning_of_receipt`; `v2CheckedAcceptance`; `sourceClaim` | `CSuccessfulWrapperGuards` contains the length and both outer overlap guards; `resultEncoderExecution` fixes the exact returned bytes, while receipt decoding fixes their arithmetic-result meaning. | T |
| `tg_pointer_ranges_overlap` | Computes two checked half-open pointer ranges and reports overlap or conversion/wrap failure. | `CResultEncoderAcceptance.cPointerRangesDisjoint`; `CWrapperPointerGuards`; `CFlatWrapperPointerGuards` | Representability and endpoint-no-wrap fields justify the mathematical range test; three inner and two outer disjointness fields select the non-overlap branch. | G |
| `tg_sq218_validate_snapshot_to_record_v2` | Checks inner pointers and aliases, checks the input length/bit-length, hashes the snapshot, calls byte validation, encodes the result, stores checker status, and returns `1`. | Fields `guards`, `sha256Execution`, `validation`, and `resultEncoderExecution` of `CPureEntryComposition.CSuccessfulPureEntryTrace`; `CResultEncoderAcceptance.strictNativeAcceptance_of_successful_cResultV2` | `CSuccessfulWrapperGuards` is the exact successful guard bundle; `CValidateBytesV2Accepted` returns status zero; the encoded result uses that status and the assigned `CValidationResult`. | T |
| `tg_sha256` | SHA-256 initialization, full-block loop, one/two-block padding, length encoding, compression, and digest serialization. | `CSHA256Refinement.cDigestByteArray`; `cDigestByteArray_refines`; explicit boundary `ConcreteExecutionMatchesSource` | `sha256BitLengthGuard` justifies the source `length * 8`; `sha256OutputWidth = 32`; the concrete digest equality is the named execution premise. | S; concrete C edge open |
| `tg_sha256_compress` | Builds/extends the 64-word schedule, executes 64 rounds, and adds the working state back into the hash state. | `CSHA256Refinement.cMessageSchedule`; `cRound`; `cCompress`; `cMessageSchedule_eq_target`; `cRoundFold_refines`; `cCompress_refines` | Fixed 16/64 loop bounds and 32-bit modular additions are encoded by `CWord`/`cWord`; no status return. | S |
| `tg_sha256_read_be32` | Reads one four-byte SHA schedule word with cast-before-shift semantics. | `CSHA256Refinement.cReadBE32Word`; `cReadBE32Word_toNat` | Caller supplies a 64-byte block; `cByteAtWord` gives the exact indexed bytes; no status return. | S |
| `tg_sha256_rotate_right` | Performs the source 32-bit rotate-right expression. | `CSHA256Refinement.cRotateRightWord`; `cRotateRightWord_refines` | SHA uses only nonzero amounts below 32; `BitVec 32` captures wraparound; no status return. | S |
| `tg_result_put_be64` | Serializes a 64-bit result field and also writes the SHA bit length into the padding block. | `CResultEncoderRefinement.cPutBE64`; `readBE64_cPutBE64`; SHA-side `CSHA256Refinement.cEncodedLength_eq_target` | Output regions are established by the enclosing encoder/padding models; no status return. | S |
| `tg_result_put_be32` | Serializes the result status and each SHA digest word. | `CResultEncoderRefinement.cPutBE32`; `readBE32_cPutBE32`; SHA-side `CSHA256Refinement.cPutBE32` and `byteArrayLowerHex_cPutBE32` | Output regions are fixed by the 120-byte record or 32-byte digest construction; no status return. | S |
| `tg_sq218_encode_result_v2` | Clears and fills the exact 120-byte V2 record, selecting nonzero arithmetic fields only when status is zero. | `CResultEncoderRefinement.cEncodeResultV2`; `cEncodeResultV2_facts`; `decodeNativeResultBytes_cEncodeResultV2` | `selectedResult` models `status == 0 && result != NULL`; each slice theorem fixes magic, version, widths, status, limbs, and digest. | S; concrete store execution open |
| `tg_result_put_be16` | Serializes result version and record width. | `CResultEncoderRefinement.cPutBE16`; `readBE16_cPutBE16` | The enclosing encoder proves both two-byte slices are inside the record; no status return. | S |

## Checker primitives and canonical view opening

| C function | Exact source role | Lean model / theorem | Successful status or guard mapping | Closure |
|---|---|---|---|---|
| `tg_read_be16` | Big-endian two-byte header read. | `CPrimitives.readBE16`; `CWireReadRefinement.readBE16_eq_wire` | `offset + 2 ≤ raw.size` is the exact successful read bound; no status return. | S |
| `tg_read_be32` | Big-endian four-byte header/record read. | `CPrimitives.readBE32`; `CWireReadRefinement.readBE32_eq_wire` | `offset + 4 ≤ raw.size` is the exact successful read bound; no status return. | S |
| `tg_read_be64` | Big-endian eight-byte header/record read. | `CPrimitives.readBE64`; `CWireReadRefinement.readBE64_eq_wire` | `offset + 8 ≤ raw.size` is the exact successful read bound; no status return. | S |
| `tg_u64_add_checked` | Adds two words and rejects unsigned overflow. | `CPrimitives.wordAddChecked`; `wordAddChecked_sound`; `wordAddChecked_eq_some_of_sum_fits` | `some result` is exactly the no-overflow branch and proves `result < 2^64` plus `result = left + right`. | S |
| `tg_u64_mul_checked` | Multiplies two words and rejects unsigned overflow. | `CPrimitives.wordMulChecked`; `wordMulChecked_sound`; `CStepRefinement.cWordMulChecked` | `some result` is exactly the no-overflow branch and proves `result < 2^64` plus the exact product. | S |
| `tg_mul64_wide` | Splits two 64-bit inputs into 32-bit halves and returns the exact 128-bit product limbs. | `CPrimitives.mulWide32`; `mulWide32_value`; `mulWide32_valid` | Input word bounds imply valid high/low output limbs; the helper cannot fail. | S |
| `tg_sq218_u128_compare` | Lexicographically compares high then low limbs. | `CPrimitives.compare`; `compare_eq_lt_iff`; `compare_eq_eq_iff`; `compare_eq_gt_iff` | Returned negative/zero/positive branch is mapped to exact natural-number ordering. | S |
| `tg_sq218_u128_add_checked` | Adds two two-limb values with low carry and rejects high overflow. | `CPrimitives.addChecked`; `addChecked_refines` | `some result` maps all source overflow guards to exact `U128.addChecked` success. | S |
| `tg_sq218_u128_sub_checked` | Rejects a negative result, then subtracts with low borrow. | `CPrimitives.subChecked`; `subChecked_refines` | `some result` includes the comparison guard and exact `U128.subChecked` result. | S |
| `tg_sq218_u128_mul_u64_checked` | Uses two wide products, rejects a nonzero discarded high limb/addition overflow, and returns two limbs. | `CPrimitives.mulWordChecked`; `mulWordChecked_refines` | `some result` is the exact successful fixed-width product and supplies `U128.Valid`. | S |
| `tg_same_magic` | Loops over all eight magic bytes and rejects the first mismatch. | Field `CHeaderRefinement.COpenV2Accepted.sameMagic`; `COpenV2Accepted.parseHeader` | Successful condition is exactly `raw.extract 0 8 = Wire.magicBytes.toByteArray`. | G |
| `tg_section_end` | Computes `start + count * width` through checked word helpers. | `CWireReadRefinement.cSectionEnd`; `cSectionEnd_refines`; `CHeaderRefinement.CCanonicalLayout` | `some end` records both successful checked operations; five instances establish contiguous canonical sections. | S |
| `tg_range_inside` | Checks non-null view, checked `offset + width`, and end not past the byte length. | `CWireReadRefinement.cRangeInside`; `cRangeInside_sound`; `cRangeInside_iff` | Boolean true is equivalent to the word-fit and `offset + width ≤ rawSize` guards; typed model treats non-null as a successful-call precondition. | S |
| `tg_sq218_view_open_v2` | Validates fixed header bytes/constants, all five section ends, exact EOF and host-length round trips, then assigns the view. | `CHeaderRefinement.COpenV2Accepted`; `COpenV2Accepted.refinesHeader`; `CArchiveRefinement.CArchiveIterationAccepted.decodeCanonicalArchiveBytes` | Non-null is a typed precondition; every condition leading past `BAD_ARGUMENT`/`BAD_FORMAT` is a named field; success is status zero and the exact canonical decoded header/view. | T |

## Record addressing and accessors

| C function | Exact source role | Lean model / theorem | Successful status or guard mapping | Closure |
|---|---|---|---|---|
| `tg_record_offset` | Checks index, checked displacement/product, checked section addition, and range containment. | `CRecordRefinement.cRecordOffset`; `cRecordOffset_success`; `RecordAddressFacts` | `some offset` corresponds to status zero; null is a typed precondition and all `OUT_OF_RANGE` guards are retained. | S |
| `tg_sq218_prime_at_v2` | Addresses and decodes one 80-byte prime row, including both reserved-field zero guards. | `CRecordRefinement.CPrimeAtAccepted`; `CPrimeAtAccepted.wireDecode`; `primeAt_refines` | The accepted structure contains successful address facts, zero reserved fields and exact assignments; it denotes status zero. | T |
| `tg_sq218_factor_ref_at_v2` | Addresses and reads one factor-reference word. | `CRecordRefinement.CFactorRefAtAccepted`; `wireDecode`; `factorRefAt_refines` | Successful address/range and exact BE64 value correspond to status zero. | T |
| `tg_sq218_factor_pair_at_v2` | Addresses and decodes one two-word factor pair. | `CRecordRefinement.CFactorPairAtAccepted`; `wireDecode`; `factorPairAt_refines` | Successful address/range and both exact fields correspond to status zero. | T |
| `tg_sq218_event_at_v2` | Addresses and decodes one event, including its reserved-word zero guard. | `CRecordRefinement.CEventAtAccepted`; `wireDecode`; `eventAt_refines` | Successful address/range, reserved zero and exact fields correspond to status zero. | T |
| `tg_sq218_power_ref_at_v2` | Addresses and reads one inverse power-reference word. | `CRecordRefinement.CPowerRefAtAccepted`; `wireDecode`; `powerRefAt_refines` | Successful address/range and exact BE64 value correspond to status zero. | T |

## Roster and modular arithmetic

| C function | Exact source role | Lean model / theorem | Successful status or guard mapping | Closure |
|---|---|---|---|---|
| `tg_add_mod` | Overflow-safe modular addition used by binary multiplication. | `CModularRefinement.cAddMod`; `cAddMod_eq_mod`; `cAddMod_word_fits` | Positive modulus and word inputs select the exact branch and keep the result below the modulus. | S |
| `tg_mul_mod` | Binary double-and-add modular multiplication. | `CModularRefinement.cMulModLoop`; `cMulMod`; `cMulMod_eq_mod` | The loop invariant proves exact multiplication modulo a positive word modulus; no status return. | S |
| `tg_pow_mod` | Binary modular exponentiation used for Lucas residues. | `CModularRefinement.cPowModLoop`; `cPowMod`; `cPowMod_eq_mod`; `cPowMod_cast_eq_fastPow` | Positive modulus and word bounds map the source loop to the generic modular power. | S |
| `tg_validate_gap_pair` | Reads one factor pair, checks both factors greater than one, checked product, and the expected consecutive value. | `CRosterRefinement.CGapRun`; `CGapRun.refines_factorRunCheck` | Each `CGapRun.cons` is exactly one status-zero call; any accessor, factor, overflow, or product mismatch is excluded. | T |
| `tg_sq218_validate_roster_v2` | Streams prime rows, factor references and gap pairs, then validates the terminal composite tail. | `CRosterRefinement.CRowAccepted`; `CRosterTrace`; `CRosterAccepted`; `CRosterAccepted.refines_primeRosterCheck` | Every row/accessor/product/residue/cursor guard and the final status-zero exit are fields of the accepted trace. | T |

## Power layout and logarithm ladder

| C function | Exact source role | Lean model / theorem | Successful status or guard mapping | Closure |
|---|---|---|---|---|
| `tg_sq218_scan_initial_v2` | Writes zero into the event cursor, last value, weighted upper, and psi lower state. | `ScanState.initial`; initial endpoint of `CStepRefinement.CScanTrace` | Exact all-zero state is definitional; typed output is the non-null successful branch. | S |
| `tg_floor_sqrt_ok` | Checks `root^2 ≤ value < (root+1)^2` without overflow-prone squaring. | `CStepRefinement.cFloorSqrtOK`; `cFloorSqrtOK_eq_sqrt` | The division/remainder guards are proved equivalent to `root = Nat.sqrt value`. | S |
| `tg_pow_u64_checked` | Binary exponentiation with checked word multiplication. | `CStepRefinement.cPowLoop`; `cPowChecked`; `cPowChecked_refines_checkedPowWord` | `some result` retains every successful multiply and proves the exact bounded natural power. | S |
| `tg_sq218_validate_power_layout_v2` | Checks ordered power events, per-prime inverse reference slices, exponents, square roots, and terminal maximality. | `CPowerLayoutRefinement.CPowerEventTrace`; `CPowerRowTrace`; `CPowerLayoutAccepted`; `refines_powerLayoutCheck` | All source order/cursor/status-zero guards, including the final overflow-or-above-bound maximality test, are explicit. | T |
| `tg_u128_div_u64` | Runs 128 restoring-division bits, rejects zero denominator and quotient bits above 63, and returns quotient/remainder words. | `CU128DivRefinement.cDivLoop`; `cU128DivU64`; `cU128DivU64_sound` | Successful result proves exact natural division/modulus, quotient word fit, and remainder below the positive denominator. | S |
| `tg_log_ladder_next` | Executes the checked integer logarithm recurrence, two exact divisions and the upper ceiling increment. | `CLogLadderRefinement.cLogLadderNext`; `cLogLadderNext_refines` | `some output` retains every word guard and equals `LogBounds.next`; the literal C seed array is separately tied by `cLogSeedAt_eq_seed`. | S |
| `tg_sq218_validate_log_ladder_v2` | Advances seed/recurrence positions through ordered prime rows and compares both stored endpoints. | `CLogLadderRefinement.CLogAdvanceTrace`; `CLogRowsTrace`; `CLogLadderAccepted`; `refines_logRowsCheck` | Prime order/bound, source seed selection, successful recurrence status and row equality are explicit; the 30 fixed rows close by `Sqrt218LogLadderCertificate.seedTableCheck_closed` in the `Sqrt218LogSeedClosure` module. | T |

## Event scan, anchor, and checker wrappers

| C function | Exact source role | Lean model / theorem | Successful status or guard mapping | Closure |
|---|---|---|---|---|
| `tg_reciprocals` | Computes the directed lower/upper reciprocal words and remainder-dependent ceiling. | `CStepRefinement.cReciprocals`; `cReciprocals_facts`; `cReciprocals_upper_refines` | Checked square/doubling/addition, nonzero value/root, and quotient/remainder guards are retained in `CReciprocalFacts`. | S |
| `tg_head_right` | Forms the checked two-limb strict-head right-hand side. | `CArithmeticRefinement.cHeadRight`; `cHeadRight_refines`; `cHeadRight_implies_IR_headRight` | `some result` corresponds to all checked multiplications succeeding and returns the exact IR value. | S |
| `tg_sq218_scan_step_v2` | Reads the current event/prime, checks ordering, power/root/reciprocal facts, updates both accumulators, and enforces the strict head guard. | `CStepRefinement.DecodedStepRecords`; `CStepWordFacts`; `cAcceptedScanStep`; `cAcceptedScanStep_refines_fixedEventStep`; `cAcceptedScanStep_nextEvent` | Accessor status zero and every range/overflow/strict-comparison guard are stored on one accepted transition. | T |
| `tg_sq218_scan_all_events_v2` | Initializes state and repeatedly calls the scan step until `next_event == event_count`. | `CStepRefinement.CScanTrace`; `CScanTrace.complete_refines_fixedEvents` | Each edge is a zero-status step; the exit equality proves complete event consumption and exact no-wrap progress. | T |
| `tg_sq218_anchor_v2` | Searches for the endpoint floor root, computes reciprocals, then recomputes the correction and strict anchor slack with checked two-limb arithmetic. | `CAnchorRefinement.CAnchorRootHeadAccepted`; `CAnchorRootTrace`; `CAnchorAccepted`; `CAnchorAccepted.root_eq_sqrt`; `lower_eq_reciprocalLower`; `refines_cAnchorArithmetic`; `implies_IR_anchorSlack`; `implies_anchorOK` | Both ordered `while` operands, product/increment word-fit invariants, the break/continue guard, exact `root = root + 1` update, successful reciprocal output, and every arithmetic-tail guard are explicit. `CValidationControlFlow.CAnchorStageEvidence` now requires this whole accepted trace. | T |
| `tg_sq218_validate_all_v2` | Checks the five literal production constants, then calls roster, power, log, scan and anchor in order, assigns local result to `*out`, and returns zero. | `CValidationControlFlow.CProductionHeaderGuards`; `CValidateAllV2Accepted`; `CValidateAllV2Accepted.toCompleteValidation` | Every called status is a `CZeroStatusStage`; literal bound `2,000,000`, reused bound `1,517,397`, seed `30`, and both scales are explicit; `resultAssigned` models `*out = result`. | T |
| `tg_sq218_validate_bytes_v2` | Opens the byte view and, only on zero status, directly returns `validate_all` status. | `CValidationControlFlow.CValidateBytesV2Accepted`; `returnedStatusZero`; `toRawCompleteValidation` | `viewOpenStatusZero`, canonical `CArchiveIterationAccepted`, and `returnsValidateAllStatus` mirror the source branches exactly. | T |

## Mechanical completeness check

Run:

```bash
python3 tools/audit_sqrt218_pure_entry_source_map.py
```

The script strips comments and literals, extracts local C function bodies,
computes the `tg_*` call-graph closure from
`tg_sq218_verify_snapshot_v2`, and requires exact set equality with the first
column of the tables above. It therefore fails both when a reachable function
is omitted from this document and when a mapped function disappears or stops
being reachable. It performs no compilation and reads no production data.
