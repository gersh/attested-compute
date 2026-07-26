/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Log
import Mathlib.Tactic

/-!
# Exact dense-record arithmetic for `TGDCSB03`

The GPU completed-`L` reducer retains four one-bit flags followed by the
transition count in little-endian bit order.  This module specifies that
record as a natural number, proves decoding is inverse to canonical encoding,
and proves that the C++ `4 + bit_length(sampleCount - 1)` record width is
sufficient.

Byte-page packing, parsing, CUDA refinement, and physical execution remain
separate obligations.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.PhaseDenseWire

/-- Dense per-character information retained by `TGDCSB03`. -/
structure Record where
  hasDeterminate : Bool
  firstPositive : Bool
  lastPositive : Bool
  hasSparse : Bool
  transitionCount : Nat
  deriving Repr, DecidableEq

/-- Sign bits are zero when there is no determinate sample. -/
def Canonical (record : Record) : Prop :=
  record.hasDeterminate = false →
    record.firstPositive = false ∧
      record.lastPositive = false

def bit (value : Bool) : Nat :=
  if value then 1 else 0

/-- Low four flag bits in the production order. -/
def flags (record : Record) : Nat :=
  bit record.hasDeterminate +
    2 * bit record.firstPositive +
    4 * bit record.lastPositive +
    8 * bit record.hasSparse

/-- Canonical little-endian dense-record integer. -/
def encode (record : Record) : Nat :=
  flags record + 16 * record.transitionCount

/-- Arithmetic decoder used to specify the corresponding bit extraction. -/
def decode (word : Nat) : Record :=
  { hasDeterminate := word % 2 = 1
    firstPositive := (word / 2) % 2 = 1
    lastPositive := (word / 4) % 2 = 1
    hasSparse := (word / 8) % 2 = 1
    transitionCount := word / 16 }

/-- C++'s loop computes one bit for counts zero and one, otherwise the bit
length of `sampleCount - 1`. -/
def countWidth (sampleCount : Nat) : Nat :=
  if sampleCount ≤ 1 then 1
  else Nat.log 2 (sampleCount - 1) + 1

def recordWidth (sampleCount : Nat) : Nat :=
  4 + countWidth sampleCount

/-- Pack fixed-width natural-number records consecutively, least-significant
record first.  This is the arithmetic meaning of the CUDA page bit loop. -/
def packValues (width : Nat) : List Nat → Nat
  | [] => 0
  | value :: values =>
      value + 2 ^ width * packValues width values

/-- Extract one fixed-width record from the packed natural number. -/
def packedAt (width : Nat) : Nat → Nat → Nat
  | 0, packed => packed % 2 ^ width
  | index + 1, packed =>
      packedAt width index (packed / 2 ^ width)

def packRecords (sampleCount : Nat) (records : List Record) : Nat :=
  packValues (recordWidth sampleCount) (records.map encode)

def recordAt (sampleCount index packed : Nat) : Record :=
  decode (packedAt (recordWidth sampleCount) index packed)

/-- The four flags always occupy the low nibble. -/
theorem flags_lt_sixteen (record : Record) :
    flags record < 16 := by
  rcases record with
    ⟨hasDeterminate, firstPositive, lastPositive, hasSparse,
      transitionCount⟩
  cases hasDeterminate <;> cases firstPositive <;>
    cases lastPositive <;> cases hasSparse <;>
    norm_num [flags, bit]

/-- Canonical dense records round-trip through the arithmetic decoder. -/
theorem decode_encode
    (record : Record) (hcanonical : Canonical record) :
    decode (encode record) = record := by
  rcases record with
    ⟨hasDeterminate, firstPositive, lastPositive, hasSparse,
      transitionCount⟩
  cases hasDeterminate <;> cases firstPositive <;>
    cases lastPositive <;> cases hasSparse
  all_goals simp [Canonical] at hcanonical
  all_goals simp [decode, encode, flags, bit]
  all_goals omega

/-- A transition count strictly below the sample count fits the exact
production count width. -/
theorem transitionCount_lt_capacity
    {sampleCount transitionCount : Nat}
    (hsample : 0 < sampleCount)
    (htransition : transitionCount < sampleCount) :
    transitionCount < 2 ^ countWidth sampleCount := by
  by_cases hsmall : sampleCount ≤ 1
  · have hsamples : sampleCount = 1 := by omega
    subst sampleCount
    simp [countWidth]
    omega
  · have hnonzero : sampleCount - 1 ≠ 0 := by omega
    have hlog :
        sampleCount - 1 <
          2 ^ (Nat.log 2 (sampleCount - 1)).succ :=
      Nat.lt_pow_succ_log_self (by norm_num) _
    have hle : transitionCount ≤ sampleCount - 1 := by omega
    simpa [countWidth, hsmall, Nat.succ_eq_add_one] using
      hle.trans_lt hlog

/-- Consequently the whole record fits in exactly
`4 + countWidth sampleCount` bits. -/
theorem encode_lt_recordCapacity
    {record : Record} {sampleCount : Nat}
    (hsample : 0 < sampleCount)
    (htransition : record.transitionCount < sampleCount) :
    encode record < 2 ^ recordWidth sampleCount := by
  have hcount :=
    transitionCount_lt_capacity hsample htransition
  have hflags := flags_lt_sixteen record
  rw [encode, recordWidth, Nat.pow_add]
  norm_num
  omega

/-- Fixed-width concatenation recovers every in-range record, including
records that cross byte boundaries. -/
theorem packedAt_packValues
    (width : Nat) (values : List Nat)
    (hvalues : ∀ value ∈ values, value < 2 ^ width)
    (index : Nat) :
    packedAt width index (packValues width values) =
      values.getD index 0 := by
  induction values generalizing index with
  | nil =>
      induction index with
      | zero =>
          simp [packValues, packedAt]
      | succ index induction =>
          have ih : packedAt width index 0 = 0 := by
            simpa [packValues] using induction
          simp [packValues, packedAt, ih]
  | cons value values induction =>
      have hvalue : value < 2 ^ width :=
        hvalues value (by simp)
      have htail :
          ∀ tailValue ∈ values, tailValue < 2 ^ width := by
        intro tailValue hmember
        exact hvalues tailValue (by simp [hmember])
      cases index with
      | zero =>
          rw [packValues, packedAt, Nat.add_mul_mod_self_left,
            Nat.mod_eq_of_lt hvalue]
          rfl
      | succ index =>
          rw [packValues, packedAt,
            Nat.add_mul_div_left value (packValues width values)
              (Nat.two_pow_pos width),
            Nat.div_eq_of_lt hvalue, Nat.zero_add]
          simpa using induction htail index

/-- The complete record codec round-trips every canonical in-range entry of
a packed page. -/
theorem recordAt_packRecords
    {sampleCount : Nat} (records : List Record)
    (hsample : 0 < sampleCount)
    (hcanonical :
      ∀ record ∈ records, Canonical record)
    (htransitions :
      ∀ record ∈ records,
        record.transitionCount < sampleCount)
    (index : Nat) (hindex : index < records.length) :
    recordAt sampleCount index (packRecords sampleCount records) =
      records.get ⟨index, hindex⟩ := by
  have hencoded :
      ∀ value ∈ records.map encode,
        value < 2 ^ recordWidth sampleCount := by
    intro value hvalue
    rcases List.mem_map.mp hvalue with
      ⟨record, hrecord, rfl⟩
    exact encode_lt_recordCapacity
      hsample (htransitions record hrecord)
  rw [recordAt, packRecords,
    packedAt_packValues _ _ hencoded index]
  have hmap :
      (records.map encode).getD index 0 =
        encode (records.get ⟨index, hindex⟩) := by
    simp [List.getD, hindex]
  rw [hmap]
  exact decode_encode _
    (hcanonical (records.get ⟨index, hindex⟩)
      (List.get_mem records ⟨index, hindex⟩))

example : countWidth 1 = 1 := by norm_num [countWidth]
example : countWidth 2 = 1 := by norm_num [countWidth, Nat.log]
example : countWidth 3 = 2 := by norm_num [countWidth, Nat.log]
example : countWidth 8 = 3 := by norm_num [countWidth, Nat.log]
example : countWidth 127988 = 17 := by norm_num [countWidth, Nat.log]

#print axioms flags_lt_sixteen
#print axioms decode_encode
#print axioms transitionCount_lt_capacity
#print axioms encode_lt_recordCapacity
#print axioms packedAt_packValues
#print axioms recordAt_packRecords

end SparkInterval.Dirichlet.PhaseDenseWire
