/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CWireEncodeRefinement

/-!
# Successful C-source whole-archive aggregation refinement

This module lifts the successful fixed-record accessor theorems from
`CRecordRefinement` to the five complete V2 sections.  The source iteration
model is relational: for every source index below the header count, it
records a successful call of the corresponding C accessor at the exact
checked section address.

The resulting theorems establish:

* the exact list returned by each `Wire.parseRecords` call;
* exact list lengths and indexed values;
* `headerCheck` for the assembled `ArchiveImage`; and
* successful `Wire.parseArchiveBytesUnchecked`; and
* exact canonical re-encoding of every byte, hence unconditional successful
  `Wire.decodeCanonicalArchiveBytes`.

The re-encoding step is proved separately before it is composed with the
public canonical decoder.  It uses the exact header and reserved-byte guards,
every source-order record trace, the canonical section equalities, and exact
EOF; accessor success is not silently identified with byte identity.

Everything here is symbolic in `raw`.  Importing the module opens no archive
and performs no production replay.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchiveRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CHeaderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRecordRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CWireEncodeRefinement

/-! ## Exact source-order section images -/

def recordOffset (start width index : Nat) : Nat :=
  start + index * width

def cDecodedPrimes (raw : ByteArray) : List PrimeRecord :=
  (List.range (cDecodedHeader raw).primeCount).map fun index =>
    cDecodedPrimeRecord raw
      (recordOffset (cDecodedHeader raw).primesOffset
        primeRecordBytes index)

def cDecodedFactorRefs (raw : ByteArray) : List Nat :=
  (List.range (cDecodedHeader raw).factorRefCount).map fun index =>
    cReadBE64At raw
      (recordOffset (cDecodedHeader raw).factorRefsOffset
        factorRefBytes index)

def cDecodedFactorPairs (raw : ByteArray) : List FactorPair :=
  (List.range (cDecodedHeader raw).factorPairCount).map fun index =>
    cDecodedFactorPair raw
      (recordOffset (cDecodedHeader raw).factorPairsOffset
        factorPairBytes index)

def cDecodedEvents (raw : ByteArray) : List EventRecord :=
  (List.range (cDecodedHeader raw).eventCount).map fun index =>
    cDecodedEventRecord raw
      (recordOffset (cDecodedHeader raw).eventsOffset
        eventRecordBytes index)

def cDecodedPowerRefs (raw : ByteArray) : List Nat :=
  (List.range (cDecodedHeader raw).powerRefCount).map fun index =>
    cReadBE64At raw
      (recordOffset (cDecodedHeader raw).powerRefsOffset
        powerRefBytes index)

/-- The exact typed image assembled from successful source-order reads. -/
def cDecodedArchive (raw : ByteArray) : ArchiveImage where
  byteLength := raw.size
  header := cDecodedHeader raw
  primes := cDecodedPrimes raw
  factorRefs := cDecodedFactorRefs raw
  factorPairs := cDecodedFactorPairs raw
  events := cDecodedEvents raw
  powerRefs := cDecodedPowerRefs raw

/-! ## Relational source iteration -/

/-- Successful traces of the five source accessor loops.

Each field quantifies over precisely the source loop guard `index < count`.
The offset is the mathematical value forced by a successful
`tg_record_offset`; the lower-level accessor structures retain all checked
word arithmetic, range checks, and reserved-field checks. -/
structure CArchiveIterationAccepted (raw : ByteArray) : Prop where
  opened : COpenV2Accepted raw
  primeAt :
    ∀ index, index < (cDecodedHeader raw).primeCount →
      CPrimeAtAccepted raw index
        (recordOffset (cDecodedHeader raw).primesOffset
          primeRecordBytes index)
  factorRefAt :
    ∀ index, index < (cDecodedHeader raw).factorRefCount →
      CFactorRefAtAccepted raw index
        (recordOffset (cDecodedHeader raw).factorRefsOffset
          factorRefBytes index)
  factorPairAt :
    ∀ index, index < (cDecodedHeader raw).factorPairCount →
      CFactorPairAtAccepted raw index
        (recordOffset (cDecodedHeader raw).factorPairsOffset
          factorPairBytes index)
  eventAt :
    ∀ index, index < (cDecodedHeader raw).eventCount →
      CEventAtAccepted raw index
        (recordOffset (cDecodedHeader raw).eventsOffset
          eventRecordBytes index)
  powerRefAt :
    ∀ index, index < (cDecodedHeader raw).powerRefCount →
      CPowerRefAtAccepted raw index
        (recordOffset (cDecodedHeader raw).powerRefsOffset
          powerRefBytes index)

/-! ## Generic finite list aggregation -/

private theorem mapM_eq_some_map_of_pointwise
    {α β : Type} (values : List α)
    (parse : α → Option β) (decoded : α → β)
    (hpointwise :
      ∀ value, value ∈ values → parse value = some (decoded value)) :
    values.mapM parse = some (values.map decoded) := by
  induction values with
  | nil =>
      rfl
  | cons head tail ih =>
      have hhead : parse head = some (decoded head) :=
        hpointwise head (by simp)
      have htail :
          tail.mapM parse = some (tail.map decoded) :=
        ih fun value hmem =>
          hpointwise value (by simp [hmem])
      simp only [List.mapM_cons, hhead, htail, Option.bind_eq_bind,
        Option.bind_some, List.map_cons]
      rfl

/-! ## Exact `Wire.parseRecords` results -/

theorem CArchiveIterationAccepted.parsePrimes
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.parseRecords raw
        (cDecodedHeader raw).primesOffset primeRecordBytes
        (cDecodedHeader raw).primeCount Wire.parsePrimeRecord =
      some (cDecodedPrimes raw) := by
  unfold Wire.parseRecords cDecodedPrimes
  apply mapM_eq_some_map_of_pointwise
  intro index hindex
  exact (accepted.primeAt index (List.mem_range.mp hindex)).wireDecode

theorem CArchiveIterationAccepted.parseFactorRefs
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.parseRecords raw
        (cDecodedHeader raw).factorRefsOffset factorRefBytes
        (cDecodedHeader raw).factorRefCount Wire.readBE64 =
      some (cDecodedFactorRefs raw) := by
  unfold Wire.parseRecords cDecodedFactorRefs
  apply mapM_eq_some_map_of_pointwise
  intro index hindex
  exact
    (accepted.factorRefAt index (List.mem_range.mp hindex)).wireDecode

theorem CArchiveIterationAccepted.parseFactorPairs
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.parseRecords raw
        (cDecodedHeader raw).factorPairsOffset factorPairBytes
        (cDecodedHeader raw).factorPairCount Wire.parseFactorPair =
      some (cDecodedFactorPairs raw) := by
  unfold Wire.parseRecords cDecodedFactorPairs
  apply mapM_eq_some_map_of_pointwise
  intro index hindex
  exact
    (accepted.factorPairAt index (List.mem_range.mp hindex)).wireDecode

theorem CArchiveIterationAccepted.parseEvents
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.parseRecords raw
        (cDecodedHeader raw).eventsOffset eventRecordBytes
        (cDecodedHeader raw).eventCount Wire.parseEventRecord =
      some (cDecodedEvents raw) := by
  unfold Wire.parseRecords cDecodedEvents
  apply mapM_eq_some_map_of_pointwise
  intro index hindex
  exact (accepted.eventAt index (List.mem_range.mp hindex)).wireDecode

theorem CArchiveIterationAccepted.parsePowerRefs
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.parseRecords raw
        (cDecodedHeader raw).powerRefsOffset powerRefBytes
        (cDecodedHeader raw).powerRefCount Wire.readBE64 =
      some (cDecodedPowerRefs raw) := by
  unfold Wire.parseRecords cDecodedPowerRefs
  apply mapM_eq_some_map_of_pointwise
  intro index hindex
  exact
    (accepted.powerRefAt index (List.mem_range.mp hindex)).wireDecode

/-! ## Exact source-order section re-encoding -/

private theorem encodeRecords_map_eq_some_flatMap
    {α : Type} (indices : List Nat) (decoded : Nat → α)
    (encode : α → Option (List UInt8))
    (output : Nat → List UInt8)
    (hpointwise :
      ∀ index, index ∈ indices →
        encode (decoded index) = some (output index)) :
    Wire.encodeRecords encode (indices.map decoded) =
      some (indices.flatMap output) := by
  induction indices with
  | nil =>
      rfl
  | cons head tail ih =>
      have hhead :
          encode (decoded head) = some (output head) :=
        hpointwise head (by simp)
      have htail :
          Wire.encodeRecords encode (tail.map decoded) =
            some (tail.flatMap output) :=
        ih fun index hmem =>
          hpointwise index (by simp [hmem])
      simp only [List.map_cons, Wire.encodeRecords, hhead, htail,
        Option.bind_eq_bind, Option.bind_some, List.flatMap_cons]
      rfl

private theorem flatMap_recordWindows
    (raw : ByteArray) (start width count : Nat) :
    (List.range count).flatMap
        (fun index => bytesAt raw (start + index * width) width) =
      bytesAt raw start (count * width) := by
  induction count with
  | zero =>
      simp [bytesAt]
  | succ count ih =>
      rw [List.range_succ, List.flatMap_append, ih]
      simp only [List.flatMap_singleton]
      rw [bytesAt_append raw start (count * width) width]
      simp only [Nat.succ_mul]

private theorem encodeRecords_range_eq_some
    {α : Type} (raw : ByteArray) (start width count : Nat)
    (decoded : Nat → α) (encode : α → Option (List UInt8))
    (hpointwise :
      ∀ index, index < count →
        encode (decoded index) =
          some (bytesAt raw (start + index * width) width)) :
    Wire.encodeRecords encode
        ((List.range count).map decoded) =
      some (bytesAt raw start (count * width)) := by
  calc
    Wire.encodeRecords encode ((List.range count).map decoded) =
        some ((List.range count).flatMap
          (fun index =>
            bytesAt raw (start + index * width) width)) := by
      apply encodeRecords_map_eq_some_flatMap
      intro index hindex
      exact hpointwise index (List.mem_range.mp hindex)
    _ = some (bytesAt raw start (count * width)) :=
      congrArg some (flatMap_recordWindows raw start width count)

theorem CArchiveIterationAccepted.encodePrimes
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.encodeRecords Wire.encodePrimeRecord (cDecodedPrimes raw) =
      some
        (bytesAt raw (cDecodedHeader raw).primesOffset
          ((cDecodedHeader raw).primeCount * primeRecordBytes)) := by
  unfold cDecodedPrimes
  apply encodeRecords_range_eq_some
  intro index hindex
  simpa only [recordOffset] using
    CWireEncodeRefinement.CPrimeAtAccepted.encodeRecord
      (accepted.primeAt index hindex)

theorem CArchiveIterationAccepted.encodeFactorRefs
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.encodeRecords Wire.encodeBE64 (cDecodedFactorRefs raw) =
      some
        (bytesAt raw (cDecodedHeader raw).factorRefsOffset
          ((cDecodedHeader raw).factorRefCount * factorRefBytes)) := by
  unfold cDecodedFactorRefs
  apply encodeRecords_range_eq_some
  intro index hindex
  have _sourceAccepted := accepted.factorRefAt index hindex
  simpa only [recordOffset, factorRefBytes] using
    encodeBE64_cReadBE64At raw
      ((cDecodedHeader raw).factorRefsOffset + index * factorRefBytes)

theorem CArchiveIterationAccepted.encodeFactorPairs
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.encodeRecords Wire.encodeFactorPair
        (cDecodedFactorPairs raw) =
      some
        (bytesAt raw (cDecodedHeader raw).factorPairsOffset
          ((cDecodedHeader raw).factorPairCount *
            factorPairBytes)) := by
  unfold cDecodedFactorPairs
  apply encodeRecords_range_eq_some
  intro index hindex
  simpa only [recordOffset] using
    CWireEncodeRefinement.CFactorPairAtAccepted.encodeRecord
      (accepted.factorPairAt index hindex)

theorem CArchiveIterationAccepted.encodeEvents
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.encodeRecords Wire.encodeEventRecord (cDecodedEvents raw) =
      some
        (bytesAt raw (cDecodedHeader raw).eventsOffset
          ((cDecodedHeader raw).eventCount * eventRecordBytes)) := by
  unfold cDecodedEvents
  apply encodeRecords_range_eq_some
  intro index hindex
  simpa only [recordOffset] using
    CWireEncodeRefinement.CEventAtAccepted.encodeRecord
      (accepted.eventAt index hindex)

theorem CArchiveIterationAccepted.encodePowerRefs
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.encodeRecords Wire.encodeBE64 (cDecodedPowerRefs raw) =
      some
        (bytesAt raw (cDecodedHeader raw).powerRefsOffset
          ((cDecodedHeader raw).powerRefCount * powerRefBytes)) := by
  unfold cDecodedPowerRefs
  apply encodeRecords_range_eq_some
  intro index hindex
  have _sourceAccepted := accepted.powerRefAt index hindex
  simpa only [recordOffset, powerRefBytes] using
    encodeBE64_cReadBE64At raw
      ((cDecodedHeader raw).powerRefsOffset + index * powerRefBytes)

private theorem sectionEnd_success_value
    {start count width endOffset : Nat}
    (hrun : sectionEnd start count width = some endOffset) :
    endOffset = start + count * width := by
  unfold sectionEnd checkedWordMul checkedWordAdd checkedWord at hrun
  by_cases hmul : count * width < limbBase
  · simp only [hmul, ↓reduceIte, Option.bind_eq_bind,
      Option.bind_some] at hrun
    by_cases hadd : start + count * width < limbBase
    · simp only [hadd, ↓reduceIte, Option.some.injEq] at hrun
      exact hrun.symm
    · simp only [hadd, ↓reduceIte] at hrun
      contradiction
  · simp only [hmul, ↓reduceIte, Option.bind_eq_bind,
      Option.bind_none] at hrun
    contradiction

theorem CArchiveIterationAccepted.encodeCanonicalArchiveBytes
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.encodeCanonicalArchiveBytes (cDecodedArchive raw) =
      some raw := by
  let header := cDecodedHeader raw
  have facts := accepted.opened.sectionFacts
  have hprimesOffset :
      header.primesOffset = headerBytes :=
    facts.primesOffset
  have hfactorRefsOffset :
      header.factorRefsOffset =
        header.primesOffset +
          header.primeCount * primeRecordBytes :=
    sectionEnd_success_value facts.primesEnd
  have hfactorPairsOffset :
      header.factorPairsOffset =
        header.factorRefsOffset +
          header.factorRefCount * factorRefBytes :=
    sectionEnd_success_value facts.factorRefsEnd
  have heventsOffset :
      header.eventsOffset =
        header.factorPairsOffset +
          header.factorPairCount * factorPairBytes :=
    sectionEnd_success_value facts.factorPairsEnd
  have hpowerRefsOffset :
      header.powerRefsOffset =
        header.eventsOffset +
          header.eventCount * eventRecordBytes :=
    sectionEnd_success_value facts.eventsEnd
  have heof :
      raw.size =
        header.powerRefsOffset +
          header.powerRefCount * powerRefBytes :=
    sectionEnd_success_value facts.powerRefsEnd
  have hheaderPrimes :
      bytesAt raw 0 headerBytes ++
          bytesAt raw header.primesOffset
            (header.primeCount * primeRecordBytes) =
        bytesAt raw 0 header.factorRefsOffset := by
    rw [hprimesOffset, hfactorRefsOffset, hprimesOffset]
    exact
      bytesAt_append raw 0 headerBytes
        (header.primeCount * primeRecordBytes)
  have hfactorRefs :
      bytesAt raw 0 header.factorRefsOffset ++
          bytesAt raw header.factorRefsOffset
            (header.factorRefCount * factorRefBytes) =
        bytesAt raw 0 header.factorPairsOffset := by
    rw [hfactorPairsOffset]
    simpa only [Nat.zero_add] using
      bytesAt_append raw 0 header.factorRefsOffset
        (header.factorRefCount * factorRefBytes)
  have hfactorPairs :
      bytesAt raw 0 header.factorPairsOffset ++
          bytesAt raw header.factorPairsOffset
            (header.factorPairCount * factorPairBytes) =
        bytesAt raw 0 header.eventsOffset := by
    rw [heventsOffset]
    simpa only [Nat.zero_add] using
      bytesAt_append raw 0 header.factorPairsOffset
        (header.factorPairCount * factorPairBytes)
  have hevents :
      bytesAt raw 0 header.eventsOffset ++
          bytesAt raw header.eventsOffset
            (header.eventCount * eventRecordBytes) =
        bytesAt raw 0 header.powerRefsOffset := by
    rw [hpowerRefsOffset]
    simpa only [Nat.zero_add] using
      bytesAt_append raw 0 header.eventsOffset
        (header.eventCount * eventRecordBytes)
  have hpowerRefs :
      bytesAt raw 0 header.powerRefsOffset ++
          bytesAt raw header.powerRefsOffset
            (header.powerRefCount * powerRefBytes) =
        bytesAt raw 0 raw.size := by
    rw [heof]
    simpa only [Nat.zero_add] using
      bytesAt_append raw 0 header.powerRefsOffset
        (header.powerRefCount * powerRefBytes)
  have hheader :=
    CWireEncodeRefinement.encodeHeader_cDecodedHeader accepted.opened
  have hprimes := accepted.encodePrimes
  have hfactorRefRecords := accepted.encodeFactorRefs
  have hfactorPairRecords := accepted.encodeFactorPairs
  have heventRecords := accepted.encodeEvents
  have hpowerRefRecords := accepted.encodePowerRefs
  unfold Wire.encodeCanonicalArchiveBytes
  simp only [cDecodedArchive, hheader, hprimes, hfactorRefRecords,
    hfactorPairRecords, heventRecords, hpowerRefRecords,
    Option.bind_eq_bind, Option.bind_some]
  change
    pure
        ((bytesAt raw 0 headerBytes ++
            bytesAt raw header.primesOffset
              (header.primeCount * primeRecordBytes) ++
            bytesAt raw header.factorRefsOffset
              (header.factorRefCount * factorRefBytes) ++
            bytesAt raw header.factorPairsOffset
              (header.factorPairCount * factorPairBytes) ++
            bytesAt raw header.eventsOffset
              (header.eventCount * eventRecordBytes) ++
            bytesAt raw header.powerRefsOffset
              (header.powerRefCount * powerRefBytes)).toByteArray) =
      some raw
  rw [hheaderPrimes, hfactorRefs, hfactorPairs, hevents, hpowerRefs,
    bytesAt_zero_size_toByteArray]
  rfl

/-! ## Length and indexed-value facts -/

theorem cDecodedArchive_lengths (raw : ByteArray) :
    (cDecodedHeader raw).primeCount =
        (cDecodedArchive raw).primes.length ∧
      (cDecodedHeader raw).factorRefCount =
        (cDecodedArchive raw).factorRefs.length ∧
      (cDecodedHeader raw).factorPairCount =
        (cDecodedArchive raw).factorPairs.length ∧
      (cDecodedHeader raw).eventCount =
        (cDecodedArchive raw).events.length ∧
      (cDecodedHeader raw).powerRefCount =
        (cDecodedArchive raw).powerRefs.length := by
  simp [cDecodedArchive, cDecodedPrimes, cDecodedFactorRefs,
    cDecodedFactorPairs, cDecodedEvents, cDecodedPowerRefs]

theorem cDecodedPrimes_getElem
    (raw : ByteArray) (index : Nat)
    (hindex : index < (cDecodedArchive raw).primes.length) :
    (cDecodedArchive raw).primes[index] =
      cDecodedPrimeRecord raw
        (recordOffset (cDecodedHeader raw).primesOffset
          primeRecordBytes index) := by
  simp [cDecodedArchive, cDecodedPrimes] at hindex ⊢

theorem cDecodedFactorRefs_getElem
    (raw : ByteArray) (index : Nat)
    (hindex : index < (cDecodedArchive raw).factorRefs.length) :
    (cDecodedArchive raw).factorRefs[index] =
      cReadBE64At raw
        (recordOffset (cDecodedHeader raw).factorRefsOffset
          factorRefBytes index) := by
  simp [cDecodedArchive, cDecodedFactorRefs] at hindex ⊢

theorem cDecodedFactorPairs_getElem
    (raw : ByteArray) (index : Nat)
    (hindex : index < (cDecodedArchive raw).factorPairs.length) :
    (cDecodedArchive raw).factorPairs[index] =
      cDecodedFactorPair raw
        (recordOffset (cDecodedHeader raw).factorPairsOffset
          factorPairBytes index) := by
  simp [cDecodedArchive, cDecodedFactorPairs] at hindex ⊢

theorem cDecodedEvents_getElem
    (raw : ByteArray) (index : Nat)
    (hindex : index < (cDecodedArchive raw).events.length) :
    (cDecodedArchive raw).events[index] =
      cDecodedEventRecord raw
        (recordOffset (cDecodedHeader raw).eventsOffset
          eventRecordBytes index) := by
  simp [cDecodedArchive, cDecodedEvents] at hindex ⊢

theorem cDecodedPowerRefs_getElem
    (raw : ByteArray) (index : Nat)
    (hindex : index < (cDecodedArchive raw).powerRefs.length) :
    (cDecodedArchive raw).powerRefs[index] =
      cReadBE64At raw
        (recordOffset (cDecodedHeader raw).powerRefsOffset
          powerRefBytes index) := by
  simp [cDecodedArchive, cDecodedPowerRefs] at hindex ⊢

/-! ## Whole typed archive -/

theorem CArchiveIterationAccepted.headerCheck
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.headerCheck
        (cDecodedArchive raw) =
      true := by
  simp only
    [SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.headerCheck,
      decide_eq_true_eq]
  exact
    ⟨accepted.opened.version, accepted.opened.flags,
      accepted.opened.bound, accepted.opened.reusedPrimeBound,
      accepted.opened.logSeedAt, accepted.opened.logScale,
      accepted.opened.reciprocalScale,
      (cDecodedArchive_lengths raw).1,
      (cDecodedArchive_lengths raw).2.1,
      (cDecodedArchive_lengths raw).2.2.1,
      (cDecodedArchive_lengths raw).2.2.2.1,
      (cDecodedArchive_lengths raw).2.2.2.2,
      accepted.opened.powerRefsMatchEvents,
      accepted.opened.archiveBytes,
      accepted.opened.canonicalEnd⟩

theorem CArchiveIterationAccepted.parseArchiveBytesUnchecked
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.parseArchiveBytesUnchecked raw =
      some (cDecodedArchive raw) := by
  simpa only [cDecodedArchive] using
    Wire.parseArchiveBytesUnchecked_eq_some_of_sections
      accepted.opened.parseHeader accepted.parsePrimes
      accepted.parseFactorRefs accepted.parseFactorPairs
      accepted.parseEvents accepted.parsePowerRefs accepted.headerCheck

/-- Consolidated source-to-typed-archive result.

This theorem stops before the separate canonical encoder equality. -/
theorem CArchiveIterationAccepted.refinesTypedArchive
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.parseArchiveBytesUnchecked raw =
        some (cDecodedArchive raw) ∧
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.headerCheck
          (cDecodedArchive raw) =
        true ∧
      (cDecodedHeader raw).primeCount =
        (cDecodedArchive raw).primes.length ∧
      (cDecodedHeader raw).factorRefCount =
        (cDecodedArchive raw).factorRefs.length ∧
      (cDecodedHeader raw).factorPairCount =
        (cDecodedArchive raw).factorPairs.length ∧
      (cDecodedHeader raw).eventCount =
        (cDecodedArchive raw).events.length ∧
      (cDecodedHeader raw).powerRefCount =
        (cDecodedArchive raw).powerRefs.length :=
  ⟨accepted.parseArchiveBytesUnchecked, accepted.headerCheck,
    cDecodedArchive_lengths raw⟩

/-- Generic promotion to the public canonical decoder when a caller already
has an explicit byte-identity proof. -/
theorem CArchiveIterationAccepted.decodeCanonicalArchiveBytes_of_encode
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw)
    (hencode :
      Wire.encodeCanonicalArchiveBytes (cDecodedArchive raw) =
        some raw) :
    Wire.decodeCanonicalArchiveBytes raw =
      .ok (cDecodedArchive raw) :=
  Wire.decodeCanonicalArchiveBytes_eq_ok_of_unchecked
    accepted.parseArchiveBytesUnchecked accepted.headerCheck hencode

/-- Main whole-source-parser theorem: successful opener and complete accessor
traces decode as the exact canonical archive, including the encoder's
full-byte identity guard. -/
theorem CArchiveIterationAccepted.decodeCanonicalArchiveBytes
    {raw : ByteArray} (accepted : CArchiveIterationAccepted raw) :
    Wire.decodeCanonicalArchiveBytes raw =
      .ok (cDecodedArchive raw) :=
  accepted.decodeCanonicalArchiveBytes_of_encode
    accepted.encodeCanonicalArchiveBytes

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchiveRefinement
