/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CHeaderRefinement

/-!
# Successful C-source fixed-record accessor refinement

This module models the successful source paths through `tg_record_offset` and
the five fixed-record accessors in
`cpu_checker/sqrt218/sqrt218_cpu_checker.c`:

* `tg_sq218_prime_at_v2`;
* `tg_sq218_factor_ref_at_v2`;
* `tg_sq218_factor_pair_at_v2`;
* `tg_sq218_event_at_v2`; and
* `tg_sq218_power_ref_at_v2`.

The address model retains the source's ordered `uint64_t` guards: index
comparison, checked multiplication, checked addition, and checked half-open
range.  Successful accessor theorems recover the exact mathematical address,
the index and range facts, and the architecture-neutral `Wire`/`IR` record.
Prime and event accessors also retain their reserved-field rejection guards.

Non-null output/view pointers are preconditions of a successful call and
carry no decoded arithmetic, so they are absent from this pure byte model.
`COpenV2Accepted` supplies the exact host-length/`uint64_t` correspondence.
These are symbolic source proofs: they do not open an archive or claim a
compiler, ABI, executable, loader, ISA, or processor refinement.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRecordRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CHeaderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CWireReadRefinement

/-! ## Exact successful `tg_record_offset` path -/

/-- Pure model of the non-null successful/failed arithmetic path through
`tg_record_offset`.

The order of the tests is the source order.  In particular, neither the
checked addition nor the range guard is evaluated after an earlier failure. -/
def cRecordOffset
    (rawSize sectionStart count width index : Nat) : Option Nat :=
  if index < count then
    match CPrimitives.wordMulChecked index width with
    | none => none
    | some displacement =>
        match CPrimitives.wordAddChecked sectionStart displacement with
        | none => none
        | some offset =>
            if cRangeInside rawSize offset width then some offset else none
  else
    none

/-- Exact architecture-neutral facts recovered from a successful source
`tg_record_offset` call. -/
structure RecordAddressFacts
    (rawSize sectionStart count width index offset : Nat) : Prop where
  indexLt : index < count
  indexFits : index < limbBase
  offsetFits : offset < limbBase
  offsetEq : offset = sectionStart + index * width
  rangeInside : offset + width ≤ rawSize

theorem cRecordOffset_success
    {rawSize sectionStart count width index offset : Nat}
    (hsection : sectionStart < limbBase)
    (hcount : count < limbBase)
    (hwidth : width < limbBase)
    (hrun :
      cRecordOffset rawSize sectionStart count width index = some offset) :
    RecordAddressFacts rawSize sectionStart count width index offset := by
  unfold cRecordOffset at hrun
  by_cases hindex : index < count
  · rw [if_pos hindex] at hrun
    cases hmul : CPrimitives.wordMulChecked index width with
    | none =>
        simp only [hmul] at hrun
        contradiction
    | some displacement =>
        simp only [hmul] at hrun
        cases hadd :
            CPrimitives.wordAddChecked sectionStart displacement with
        | none =>
            simp only [hadd] at hrun
            contradiction
        | some computedOffset =>
            simp only [hadd] at hrun
            by_cases hrange :
                cRangeInside rawSize computedOffset width = true
            · simp only [hrange, ↓reduceIte] at hrun
              cases hrun
              have hindexFits : index < limbBase :=
                hindex.trans hcount
              have hmulSound :=
                CPrimitives.wordMulChecked_sound
                  hindexFits hwidth hmul
              have haddSound :=
                CPrimitives.wordAddChecked_sound
                  hsection hmulSound.1 hadd
              exact {
                indexLt := hindex
                indexFits := hindexFits
                offsetFits := haddSound.1
                offsetEq := by
                  rw [haddSound.2, hmulSound.2]
                rangeInside :=
                  cRangeInside_sound haddSound.1 hwidth hrange
              }
            · simp only [hrange, Bool.false_eq_true, ↓reduceIte] at hrun
              contradiction
  · rw [if_neg hindex] at hrun
    contradiction

/-- Any fixed field contained in a successfully ranged record is itself
inside the same byte array.  Factoring this arithmetic once keeps the record
decoder proofs small and reviewable. -/
private theorem recordFieldInside
    {rawSize offset recordWidth fieldOffset fieldWidth : Nat}
    (hrecord : offset + recordWidth ≤ rawSize)
    (hfield : fieldOffset + fieldWidth ≤ recordWidth) :
    (offset + fieldOffset) + fieldWidth ≤ rawSize := by
  omega

/-! ## Literal source record values -/

/-- Exact field assignments performed by `tg_sq218_prime_at_v2`. -/
def cDecodedPrimeRecord
    (raw : ByteArray) (offset : Nat) : PrimeRecord where
  prime := cReadBE64At raw offset
  witness := cReadBE64At raw (offset + 8)
  factorRefIndex := cReadBE64At raw (offset + 16)
  factorRefCount := cReadBE32At raw (offset + 24)
  gapPairIndex := cReadBE64At raw (offset + 32)
  gapPairCount := cReadBE32At raw (offset + 28)
  powerRefIndex := cReadBE64At raw (offset + 40)
  powerRefCount := cReadBE32At raw (offset + 48)
  logLower := cReadBE64At raw (offset + 56)
  logUpper := cReadBE64At raw (offset + 64)

/-- Exact field assignments performed by `tg_sq218_factor_pair_at_v2`. -/
def cDecodedFactorPair
    (raw : ByteArray) (offset : Nat) : FactorPair :=
  ⟨cReadBE64At raw offset, cReadBE64At raw (offset + 8)⟩

/-- Exact field assignments performed by `tg_sq218_event_at_v2`. -/
def cDecodedEventRecord
    (raw : ByteArray) (offset : Nat) : EventRecord where
  value := cReadBE64At raw offset
  primeIndex := cReadBE64At raw (offset + 8)
  exponent := cReadBE32At raw (offset + 16)
  floorSqrt := cReadBE64At raw (offset + 24)

/-! ## Accepted source accessor paths -/

structure CPrimeAtAccepted
    (raw : ByteArray) (index offset : Nat) : Prop where
  opened : COpenV2Accepted raw
  address :
    cRecordOffset raw.size
        (cDecodedHeader raw).primesOffset
        (cDecodedHeader raw).primeCount
        primeRecordBytes index =
      some offset
  reserved0 : cReadBE32At raw (offset + 52) = 0
  reserved1 : cReadBE64At raw (offset + 72) = 0

structure CFactorRefAtAccepted
    (raw : ByteArray) (index offset : Nat) : Prop where
  opened : COpenV2Accepted raw
  address :
    cRecordOffset raw.size
        (cDecodedHeader raw).factorRefsOffset
        (cDecodedHeader raw).factorRefCount
        factorRefBytes index =
      some offset

structure CFactorPairAtAccepted
    (raw : ByteArray) (index offset : Nat) : Prop where
  opened : COpenV2Accepted raw
  address :
    cRecordOffset raw.size
        (cDecodedHeader raw).factorPairsOffset
        (cDecodedHeader raw).factorPairCount
        factorPairBytes index =
      some offset

structure CEventAtAccepted
    (raw : ByteArray) (index offset : Nat) : Prop where
  opened : COpenV2Accepted raw
  address :
    cRecordOffset raw.size
        (cDecodedHeader raw).eventsOffset
        (cDecodedHeader raw).eventCount
        eventRecordBytes index =
      some offset
  reserved : cReadBE32At raw (offset + 20) = 0

structure CPowerRefAtAccepted
    (raw : ByteArray) (index offset : Nat) : Prop where
  opened : COpenV2Accepted raw
  address :
    cRecordOffset raw.size
        (cDecodedHeader raw).powerRefsOffset
        (cDecodedHeader raw).powerRefCount
        powerRefBytes index =
      some offset

/-! ## Exact address consequences for all five accessors -/

theorem CPrimeAtAccepted.addressFacts
    {raw : ByteArray} {index offset : Nat}
    (accepted : CPrimeAtAccepted raw index offset) :
    RecordAddressFacts raw.size
      (cDecodedHeader raw).primesOffset
      (cDecodedHeader raw).primeCount
      primeRecordBytes index offset := by
  apply cRecordOffset_success
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 96
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 56
  · norm_num [primeRecordBytes, limbBase]
  · exact accepted.address

theorem CFactorRefAtAccepted.addressFacts
    {raw : ByteArray} {index offset : Nat}
    (accepted : CFactorRefAtAccepted raw index offset) :
    RecordAddressFacts raw.size
      (cDecodedHeader raw).factorRefsOffset
      (cDecodedHeader raw).factorRefCount
      factorRefBytes index offset := by
  apply cRecordOffset_success
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 104
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 64
  · norm_num [factorRefBytes, limbBase]
  · exact accepted.address

theorem CFactorPairAtAccepted.addressFacts
    {raw : ByteArray} {index offset : Nat}
    (accepted : CFactorPairAtAccepted raw index offset) :
    RecordAddressFacts raw.size
      (cDecodedHeader raw).factorPairsOffset
      (cDecodedHeader raw).factorPairCount
      factorPairBytes index offset := by
  apply cRecordOffset_success
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 112
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 72
  · norm_num [factorPairBytes, limbBase]
  · exact accepted.address

theorem CEventAtAccepted.addressFacts
    {raw : ByteArray} {index offset : Nat}
    (accepted : CEventAtAccepted raw index offset) :
    RecordAddressFacts raw.size
      (cDecodedHeader raw).eventsOffset
      (cDecodedHeader raw).eventCount
      eventRecordBytes index offset := by
  apply cRecordOffset_success
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 120
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 80
  · norm_num [eventRecordBytes, limbBase]
  · exact accepted.address

theorem CPowerRefAtAccepted.addressFacts
    {raw : ByteArray} {index offset : Nat}
    (accepted : CPowerRefAtAccepted raw index offset) :
    RecordAddressFacts raw.size
      (cDecodedHeader raw).powerRefsOffset
      (cDecodedHeader raw).powerRefCount
      powerRefBytes index offset := by
  apply cRecordOffset_success
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 128
  · simpa only [cDecodedHeader] using cReadBE64At_fits raw 88
  · norm_num [powerRefBytes, limbBase]
  · exact accepted.address

/-! ## Successful byte decodes refine `Wire` and the IR records -/

theorem CPrimeAtAccepted.wireDecode
    {raw : ByteArray} {index offset : Nat}
    (accepted : CPrimeAtAccepted raw index offset) :
    Wire.parsePrimeRecord raw offset =
      some (cDecodedPrimeRecord raw offset) := by
  have hinside : offset + 80 ≤ raw.size := by
    simpa only [primeRecordBytes] using
      accepted.addressFacts.rangeInside
  have h0 :
      Wire.readBE64 raw offset = some (cReadBE64At raw offset) := by
    exact readBE64_eq_wire raw offset
      (recordFieldInside (fieldOffset := 0) (fieldWidth := 8)
        hinside (by norm_num))
  have h8 :
      Wire.readBE64 raw (offset + 8) =
        some (cReadBE64At raw (offset + 8)) := by
    exact readBE64_eq_wire raw (offset + 8)
      (recordFieldInside (fieldOffset := 8) (fieldWidth := 8)
        hinside (by norm_num))
  have h16 :
      Wire.readBE64 raw (offset + 16) =
        some (cReadBE64At raw (offset + 16)) := by
    exact readBE64_eq_wire raw (offset + 16)
      (recordFieldInside (fieldOffset := 16) (fieldWidth := 8)
        hinside (by norm_num))
  have h24 :
      Wire.readBE32 raw (offset + 24) =
        some (cReadBE32At raw (offset + 24)) := by
    exact readBE32_eq_wire raw (offset + 24)
      (recordFieldInside (fieldOffset := 24) (fieldWidth := 4)
        hinside (by norm_num))
  have h28 :
      Wire.readBE32 raw (offset + 28) =
        some (cReadBE32At raw (offset + 28)) := by
    exact readBE32_eq_wire raw (offset + 28)
      (recordFieldInside (fieldOffset := 28) (fieldWidth := 4)
        hinside (by norm_num))
  have h32 :
      Wire.readBE64 raw (offset + 32) =
        some (cReadBE64At raw (offset + 32)) := by
    exact readBE64_eq_wire raw (offset + 32)
      (recordFieldInside (fieldOffset := 32) (fieldWidth := 8)
        hinside (by norm_num))
  have h40 :
      Wire.readBE64 raw (offset + 40) =
        some (cReadBE64At raw (offset + 40)) := by
    exact readBE64_eq_wire raw (offset + 40)
      (recordFieldInside (fieldOffset := 40) (fieldWidth := 8)
        hinside (by norm_num))
  have h48 :
      Wire.readBE32 raw (offset + 48) =
        some (cReadBE32At raw (offset + 48)) := by
    exact readBE32_eq_wire raw (offset + 48)
      (recordFieldInside (fieldOffset := 48) (fieldWidth := 4)
        hinside (by norm_num))
  have h52 :
      Wire.readBE32 raw (offset + 52) =
        some (cReadBE32At raw (offset + 52)) := by
    exact readBE32_eq_wire raw (offset + 52)
      (recordFieldInside (fieldOffset := 52) (fieldWidth := 4)
        hinside (by norm_num))
  have h56 :
      Wire.readBE64 raw (offset + 56) =
        some (cReadBE64At raw (offset + 56)) := by
    exact readBE64_eq_wire raw (offset + 56)
      (recordFieldInside (fieldOffset := 56) (fieldWidth := 8)
        hinside (by norm_num))
  have h64 :
      Wire.readBE64 raw (offset + 64) =
        some (cReadBE64At raw (offset + 64)) := by
    exact readBE64_eq_wire raw (offset + 64)
      (recordFieldInside (fieldOffset := 64) (fieldWidth := 8)
        hinside (by norm_num))
  have h72 :
      Wire.readBE64 raw (offset + 72) =
        some (cReadBE64At raw (offset + 72)) := by
    exact readBE64_eq_wire raw (offset + 72)
      (recordFieldInside (fieldOffset := 72) (fieldWidth := 8)
        hinside (by norm_num))
  have h52zero :
      Wire.readBE32 raw (offset + 52) = some 0 :=
    h52.trans (congrArg some accepted.reserved0)
  have h72zero :
      Wire.readBE64 raw (offset + 72) = some 0 :=
    h72.trans (congrArg some accepted.reserved1)
  simpa only [cDecodedPrimeRecord] using
    Wire.parsePrimeRecord_eq_some_of_reads
      h0 h8 h16 h24 h28 h32 h40 h48 h52zero h56 h64 h72zero

theorem CFactorRefAtAccepted.wireDecode
    {raw : ByteArray} {index offset : Nat}
    (accepted : CFactorRefAtAccepted raw index offset) :
    Wire.readBE64 raw offset =
      some (cReadBE64At raw offset) := by
  exact readBE64_eq_wire raw offset (by
    simpa only [factorRefBytes] using
      accepted.addressFacts.rangeInside)

theorem CFactorPairAtAccepted.wireDecode
    {raw : ByteArray} {index offset : Nat}
    (accepted : CFactorPairAtAccepted raw index offset) :
    Wire.parseFactorPair raw offset =
      some (cDecodedFactorPair raw offset) := by
  have hinside : offset + 16 ≤ raw.size := by
    simpa only [factorPairBytes] using
      accepted.addressFacts.rangeInside
  have h0 :
      Wire.readBE64 raw offset = some (cReadBE64At raw offset) := by
    exact readBE64_eq_wire raw offset
      (recordFieldInside (fieldOffset := 0) (fieldWidth := 8)
        hinside (by norm_num))
  have h8 :
      Wire.readBE64 raw (offset + 8) =
        some (cReadBE64At raw (offset + 8)) := by
    exact readBE64_eq_wire raw (offset + 8)
      (recordFieldInside (fieldOffset := 8) (fieldWidth := 8)
        hinside (by norm_num))
  simpa only [cDecodedFactorPair] using
    Wire.parseFactorPair_eq_some_of_reads h0 h8

theorem CEventAtAccepted.wireDecode
    {raw : ByteArray} {index offset : Nat}
    (accepted : CEventAtAccepted raw index offset) :
    Wire.parseEventRecord raw offset =
      some (cDecodedEventRecord raw offset) := by
  have hinside : offset + 32 ≤ raw.size := by
    simpa only [eventRecordBytes] using
      accepted.addressFacts.rangeInside
  have h0 :
      Wire.readBE64 raw offset = some (cReadBE64At raw offset) := by
    exact readBE64_eq_wire raw offset
      (recordFieldInside (fieldOffset := 0) (fieldWidth := 8)
        hinside (by norm_num))
  have h8 :
      Wire.readBE64 raw (offset + 8) =
        some (cReadBE64At raw (offset + 8)) := by
    exact readBE64_eq_wire raw (offset + 8)
      (recordFieldInside (fieldOffset := 8) (fieldWidth := 8)
        hinside (by norm_num))
  have h16 :
      Wire.readBE32 raw (offset + 16) =
        some (cReadBE32At raw (offset + 16)) := by
    exact readBE32_eq_wire raw (offset + 16)
      (recordFieldInside (fieldOffset := 16) (fieldWidth := 4)
        hinside (by norm_num))
  have h20 :
      Wire.readBE32 raw (offset + 20) =
        some (cReadBE32At raw (offset + 20)) := by
    exact readBE32_eq_wire raw (offset + 20)
      (recordFieldInside (fieldOffset := 20) (fieldWidth := 4)
        hinside (by norm_num))
  have h24 :
      Wire.readBE64 raw (offset + 24) =
        some (cReadBE64At raw (offset + 24)) := by
    exact readBE64_eq_wire raw (offset + 24)
      (recordFieldInside (fieldOffset := 24) (fieldWidth := 8)
        hinside (by norm_num))
  have h20zero :
      Wire.readBE32 raw (offset + 20) = some 0 :=
    h20.trans (congrArg some accepted.reserved)
  simpa only [cDecodedEventRecord] using
    Wire.parseEventRecord_eq_some_of_reads h0 h8 h16 h20zero h24

theorem CPowerRefAtAccepted.wireDecode
    {raw : ByteArray} {index offset : Nat}
    (accepted : CPowerRefAtAccepted raw index offset) :
    Wire.readBE64 raw offset =
      some (cReadBE64At raw offset) := by
  exact readBE64_eq_wire raw offset (by
    simpa only [powerRefBytes] using
      accepted.addressFacts.rangeInside)

/-! ## Combined human-audit statements -/

theorem primeAt_refines
    {raw : ByteArray} {index offset : Nat}
    (accepted : CPrimeAtAccepted raw index offset) :
    offset =
        (cDecodedHeader raw).primesOffset +
          index * primeRecordBytes ∧
      index < (cDecodedHeader raw).primeCount ∧
      offset + primeRecordBytes ≤ raw.size ∧
      Wire.parsePrimeRecord raw offset =
        some (cDecodedPrimeRecord raw offset) :=
  ⟨accepted.addressFacts.offsetEq,
    accepted.addressFacts.indexLt,
    accepted.addressFacts.rangeInside,
    accepted.wireDecode⟩

theorem factorRefAt_refines
    {raw : ByteArray} {index offset : Nat}
    (accepted : CFactorRefAtAccepted raw index offset) :
    offset =
        (cDecodedHeader raw).factorRefsOffset +
          index * factorRefBytes ∧
      index < (cDecodedHeader raw).factorRefCount ∧
      offset + factorRefBytes ≤ raw.size ∧
      Wire.readBE64 raw offset =
        some (cReadBE64At raw offset) :=
  ⟨accepted.addressFacts.offsetEq,
    accepted.addressFacts.indexLt,
    accepted.addressFacts.rangeInside,
    accepted.wireDecode⟩

theorem factorPairAt_refines
    {raw : ByteArray} {index offset : Nat}
    (accepted : CFactorPairAtAccepted raw index offset) :
    offset =
        (cDecodedHeader raw).factorPairsOffset +
          index * factorPairBytes ∧
      index < (cDecodedHeader raw).factorPairCount ∧
      offset + factorPairBytes ≤ raw.size ∧
      Wire.parseFactorPair raw offset =
        some (cDecodedFactorPair raw offset) :=
  ⟨accepted.addressFacts.offsetEq,
    accepted.addressFacts.indexLt,
    accepted.addressFacts.rangeInside,
    accepted.wireDecode⟩

theorem eventAt_refines
    {raw : ByteArray} {index offset : Nat}
    (accepted : CEventAtAccepted raw index offset) :
    offset =
        (cDecodedHeader raw).eventsOffset +
          index * eventRecordBytes ∧
      index < (cDecodedHeader raw).eventCount ∧
      offset + eventRecordBytes ≤ raw.size ∧
      Wire.parseEventRecord raw offset =
        some (cDecodedEventRecord raw offset) :=
  ⟨accepted.addressFacts.offsetEq,
    accepted.addressFacts.indexLt,
    accepted.addressFacts.rangeInside,
    accepted.wireDecode⟩

theorem powerRefAt_refines
    {raw : ByteArray} {index offset : Nat}
    (accepted : CPowerRefAtAccepted raw index offset) :
    offset =
        (cDecodedHeader raw).powerRefsOffset +
          index * powerRefBytes ∧
      index < (cDecodedHeader raw).powerRefCount ∧
      offset + powerRefBytes ≤ raw.size ∧
      Wire.readBE64 raw offset =
        some (cReadBE64At raw offset) :=
  ⟨accepted.addressFacts.offsetEq,
    accepted.addressFacts.indexLt,
    accepted.addressFacts.rangeInside,
    accepted.wireDecode⟩

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRecordRefinement
