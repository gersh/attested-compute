/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CWireReadRefinement

/-!
# Successful C-source header refinement for the Sqrt218 checker

This module models the successful source path through
`tg_sq218_view_open_v2` up to construction of the fixed V2 view.  The proof
is deliberately split into three independently reviewable pieces:

* fixed-offset C byte expressions agree with the canonical wire reads;
* the five successful `tg_section_end` calls establish `IR.canonicalEnd`;
* the remaining successful source guards establish the exact wire-header
  preflight predicate.

The model is symbolic in the byte array.  It does not open a production
archive and it does not claim compiler, ABI, executable, loader, ISA, or
processor refinement.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CHeaderRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CWireReadRefinement

/-! ## Literal fixed-offset source reads -/

/-- Exact cast-before-shift expression used by a C 16-bit header read. -/
def cReadBE16At (raw : ByteArray) (offset : Nat) : Nat :=
  CPrimitives.readBE16
    (raw.get! offset)
    (raw.get! (offset + 1))

/-- Exact cast-before-shift expression used by a C 32-bit header read. -/
def cReadBE32At (raw : ByteArray) (offset : Nat) : Nat :=
  CPrimitives.readBE32
    (raw.get! offset)
    (raw.get! (offset + 1))
    (raw.get! (offset + 2))
    (raw.get! (offset + 3))

/-- Exact cast-before-shift expression used by a C 64-bit header read. -/
def cReadBE64At (raw : ByteArray) (offset : Nat) : Nat :=
  CPrimitives.readBE64
    (raw.get! offset)
    (raw.get! (offset + 1))
    (raw.get! (offset + 2))
    (raw.get! (offset + 3))
    (raw.get! (offset + 4))
    (raw.get! (offset + 5))
    (raw.get! (offset + 6))
    (raw.get! (offset + 7))

theorem cReadBE16At_fits (raw : ByteArray) (offset : Nat) :
    cReadBE16At raw offset < 2 ^ 16 := by
  exact CPrimitives.readBE16_fits _ _

theorem cReadBE32At_fits (raw : ByteArray) (offset : Nat) :
    cReadBE32At raw offset < 2 ^ 32 := by
  exact CPrimitives.readBE32_fits _ _ _ _

theorem cReadBE64At_fits (raw : ByteArray) (offset : Nat) :
    cReadBE64At raw offset < limbBase := by
  exact CPrimitives.readBE64_fits _ _ _ _ _ _ _ _

/-- The exact `tg_sq218_header_v2` value assembled by the source assignments.

The wire-only version and flags are retained in the architecture-neutral
`Header`, so the result can be compared directly with `Wire.parseHeader`. -/
def cDecodedHeader (raw : ByteArray) : Header where
  version := cReadBE16At raw 8
  flags := cReadBE32At raw 12
  bound := cReadBE64At raw 16
  reusedPrimeBound := cReadBE64At raw 24
  logSeedAt := cReadBE64At raw 32
  logScale := cReadBE64At raw 40
  reciprocalScale := cReadBE64At raw 48
  primeCount := cReadBE64At raw 56
  factorRefCount := cReadBE64At raw 64
  factorPairCount := cReadBE64At raw 72
  eventCount := cReadBE64At raw 80
  powerRefCount := cReadBE64At raw 88
  primesOffset := cReadBE64At raw 96
  factorRefsOffset := cReadBE64At raw 104
  factorPairsOffset := cReadBE64At raw 112
  eventsOffset := cReadBE64At raw 120
  powerRefsOffset := cReadBE64At raw 128
  archiveBytes := cReadBE64At raw 136

/-! ## Canonical checked-section layout -/

/-- Relational successful trace of the five source `tg_section_end` calls.

The intermediate values are the successive values of the C local
`expected`.  The final two equalities model the accepted
`header.archive_bytes == expected` and `(size_t)expected == length` guards.
-/
def CCanonicalLayout
    (header : Header) (rawSize : Nat) : Prop :=
  ∃ afterPrimes afterFactorRefs afterFactorPairs afterEvents afterPowerRefs,
    cSectionEnd
        header.primesOffset header.primeCount primeRecordBytes =
      some afterPrimes ∧
    header.factorRefsOffset = afterPrimes ∧
    cSectionEnd
        afterPrimes header.factorRefCount factorRefBytes =
      some afterFactorRefs ∧
    header.factorPairsOffset = afterFactorRefs ∧
    cSectionEnd
        afterFactorRefs header.factorPairCount factorPairBytes =
      some afterFactorPairs ∧
    header.eventsOffset = afterFactorPairs ∧
    cSectionEnd
        afterFactorPairs header.eventCount eventRecordBytes =
      some afterEvents ∧
    header.powerRefsOffset = afterEvents ∧
    cSectionEnd
        afterEvents header.powerRefCount powerRefBytes =
      some afterPowerRefs ∧
    header.archiveBytes = afterPowerRefs ∧
    afterPowerRefs = rawSize

/-- The complete successful source path through the fixed-header opener.

`hostLengthFits` makes explicit the source-level fact that the successful
`size_t`/`uint64_t` equality represents the same mathematical byte length.
The non-null pointer checks are caller preconditions and contain no decoded
arithmetic, so they are intentionally absent from this pure byte model. -/
structure COpenV2Accepted (raw : ByteArray) : Prop where
  headerInside : headerBytes ≤ raw.size
  hostLengthFits : raw.size < limbBase
  sameMagic :
    raw.extract 0 8 = Wire.magicBytes.toByteArray
  version :
    (cDecodedHeader raw).version = formatVersion
  width :
    cReadBE16At raw 10 = headerBytes
  flags :
    (cDecodedHeader raw).flags = 0
  reserved0 :
    cReadBE64At raw 144 = 0
  reserved1 :
    cReadBE64At raw 152 = 0
  bound :
    2 ≤ (cDecodedHeader raw).bound
  reusedPrimeBound :
    (cDecodedHeader raw).reusedPrimeBound ≤
      (cDecodedHeader raw).bound
  logSeedAt :
    (cDecodedHeader raw).logSeedAt =
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.logSeedAt
  logScale :
    (cDecodedHeader raw).logScale =
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.logScale
  reciprocalScale :
    (cDecodedHeader raw).reciprocalScale =
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.reciprocalScale
  primeCount :
    0 < (cDecodedHeader raw).primeCount
  powerRefsMatchEvents :
    (cDecodedHeader raw).powerRefCount =
      (cDecodedHeader raw).eventCount
  primesOffset :
    (cDecodedHeader raw).primesOffset = headerBytes
  layout :
    CCanonicalLayout (cDecodedHeader raw) raw.size

/-! ## Checked layout refines the architecture-neutral IR -/

/-- Human-readable architecture-neutral consequences of the five successful
source `tg_section_end` calls.  Each section ends exactly where the next one
begins, and the last section ends at exact EOF. -/
structure CanonicalSectionFacts
    (header : Header) (rawSize : Nat) : Prop where
  primesOffset : header.primesOffset = headerBytes
  primesEnd :
    sectionEnd header.primesOffset header.primeCount primeRecordBytes =
      some header.factorRefsOffset
  factorRefsEnd :
    sectionEnd
        header.factorRefsOffset header.factorRefCount factorRefBytes =
      some header.factorPairsOffset
  factorPairsEnd :
    sectionEnd
        header.factorPairsOffset header.factorPairCount factorPairBytes =
      some header.eventsOffset
  eventsEnd :
    sectionEnd header.eventsOffset header.eventCount eventRecordBytes =
      some header.powerRefsOffset
  powerRefsEnd :
    sectionEnd
        header.powerRefsOffset header.powerRefCount powerRefBytes =
      some rawSize
  archiveBytes : header.archiveBytes = rawSize

theorem COpenV2Accepted.sectionFacts
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    CanonicalSectionFacts (cDecodedHeader raw) raw.size := by
  rcases accepted.layout with
    ⟨afterPrimes, afterFactorRefs, afterFactorPairs, afterEvents,
      afterPowerRefs, hprimes, hfactorRefsOffset, hfactorRefs,
      hfactorPairsOffset, hfactorPairs, heventsOffset, hevents,
      hpowerRefsOffset, hpowerRefs, harchive, heof⟩
  have hprimesOffsetWord :
      (cDecodedHeader raw).primesOffset < limbBase := by
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 96
  have hprimeCountWord :
      (cDecodedHeader raw).primeCount < limbBase := by
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 56
  have hafterPrimesWord : afterPrimes < limbBase := by
    rw [← hfactorRefsOffset]
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 104
  have hfactorRefCountWord :
      (cDecodedHeader raw).factorRefCount < limbBase := by
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 64
  have hafterFactorRefsWord : afterFactorRefs < limbBase := by
    rw [← hfactorPairsOffset]
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 112
  have hfactorPairCountWord :
      (cDecodedHeader raw).factorPairCount < limbBase := by
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 72
  have hafterFactorPairsWord : afterFactorPairs < limbBase := by
    rw [← heventsOffset]
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 120
  have heventCountWord :
      (cDecodedHeader raw).eventCount < limbBase := by
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 80
  have hafterEventsWord : afterEvents < limbBase := by
    rw [← hpowerRefsOffset]
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 128
  have hpowerRefCountWord :
      (cDecodedHeader raw).powerRefCount < limbBase := by
    simpa only [cDecodedHeader] using cReadBE64At_fits raw 88
  have hprimeEnd :=
    cSectionEnd_refines
      hprimesOffsetWord hprimeCountWord
      (by norm_num [primeRecordBytes, limbBase]) hprimes
  have hfactorRefEnd :=
    cSectionEnd_refines
      hafterPrimesWord hfactorRefCountWord
      (by norm_num [factorRefBytes, limbBase]) hfactorRefs
  have hfactorPairEnd :=
    cSectionEnd_refines
      hafterFactorRefsWord hfactorPairCountWord
      (by norm_num [factorPairBytes, limbBase]) hfactorPairs
  have heventEnd :=
    cSectionEnd_refines
      hafterFactorPairsWord heventCountWord
      (by norm_num [eventRecordBytes, limbBase]) hevents
  have hpowerRefEnd :=
    cSectionEnd_refines
      hafterEventsWord hpowerRefCountWord
      (by norm_num [powerRefBytes, limbBase]) hpowerRefs
  exact {
    primesOffset := accepted.primesOffset
    primesEnd := by
      simpa only [hfactorRefsOffset] using hprimeEnd
    factorRefsEnd := by
      simpa only [hfactorRefsOffset, hfactorPairsOffset] using
        hfactorRefEnd
    factorPairsEnd := by
      simpa only [hfactorPairsOffset, heventsOffset] using
        hfactorPairEnd
    eventsEnd := by
      simpa only [heventsOffset, hpowerRefsOffset] using heventEnd
    powerRefsEnd := by
      simpa only [hpowerRefsOffset, heof] using hpowerRefEnd
    archiveBytes := harchive.trans heof
  }

theorem CanonicalSectionFacts.canonicalEnd
    {header : Header} {rawSize : Nat}
    (facts : CanonicalSectionFacts header rawSize) :
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.canonicalEnd
        header =
      some rawSize := by
  rcases facts with
    ⟨hprimesOffset, hprimesEnd, hfactorRefsEnd, hfactorPairsEnd,
      heventsEnd, hpowerRefsEnd, _harchiveBytes⟩
  unfold SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.canonicalEnd
  simp only [if_pos hprimesOffset, hprimesEnd, hfactorRefsEnd,
    hfactorPairsEnd, heventsEnd, hpowerRefsEnd]
  simp only [Option.bind_eq_bind, Option.bind_none, Option.bind_some,
    ↓reduceIte]

theorem COpenV2Accepted.canonicalEnd
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.canonicalEnd
        (cDecodedHeader raw) =
      some raw.size :=
  accepted.sectionFacts.canonicalEnd

theorem COpenV2Accepted.archiveBytes
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    (cDecodedHeader raw).archiveBytes = raw.size := by
  rcases accepted.layout with
    ⟨_afterPrimes, _afterFactorRefs, _afterFactorPairs, _afterEvents,
      afterPowerRefs, _hprimes, _hfactorRefsOffset, _hfactorRefs,
      _hfactorPairsOffset, _hfactorPairs, _heventsOffset, _hevents,
      _hpowerRefsOffset, _hpowerRefs, harchive, heof⟩
  exact harchive.trans heof

theorem COpenV2Accepted.headerPreflight
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    Wire.headerPreflightCheck raw.size (cDecodedHeader raw) = true := by
  simp only [Wire.headerPreflightCheck, decide_eq_true_eq]
  exact ⟨accepted.version, accepted.flags, accepted.bound,
    accepted.reusedPrimeBound, accepted.logSeedAt, accepted.logScale,
    accepted.reciprocalScale, accepted.primeCount,
    accepted.powerRefsMatchEvents, accepted.archiveBytes,
    accepted.canonicalEnd⟩

/-! ## Exact wire-header reconstruction -/

/-- All fixed wire reads consumed by `Wire.parseHeader`, packaged separately
from semantic preflight facts. -/
structure HeaderWireReads (raw : ByteArray) (header : Header) : Prop where
  version : Wire.readBE16 raw 8 = some header.version
  width : Wire.readBE16 raw 10 = some headerBytes
  flags : Wire.readBE32 raw 12 = some header.flags
  bound : Wire.readBE64 raw 16 = some header.bound
  reusedPrimeBound :
    Wire.readBE64 raw 24 = some header.reusedPrimeBound
  logSeedAt : Wire.readBE64 raw 32 = some header.logSeedAt
  logScale : Wire.readBE64 raw 40 = some header.logScale
  reciprocalScale :
    Wire.readBE64 raw 48 = some header.reciprocalScale
  primeCount : Wire.readBE64 raw 56 = some header.primeCount
  factorRefCount :
    Wire.readBE64 raw 64 = some header.factorRefCount
  factorPairCount :
    Wire.readBE64 raw 72 = some header.factorPairCount
  eventCount : Wire.readBE64 raw 80 = some header.eventCount
  powerRefCount :
    Wire.readBE64 raw 88 = some header.powerRefCount
  primesOffset : Wire.readBE64 raw 96 = some header.primesOffset
  factorRefsOffset :
    Wire.readBE64 raw 104 = some header.factorRefsOffset
  factorPairsOffset :
    Wire.readBE64 raw 112 = some header.factorPairsOffset
  eventsOffset : Wire.readBE64 raw 120 = some header.eventsOffset
  powerRefsOffset :
    Wire.readBE64 raw 128 = some header.powerRefsOffset
  archiveBytes : Wire.readBE64 raw 136 = some header.archiveBytes
  reserved0 : Wire.readBE64 raw 144 = some 0
  reserved1 : Wire.readBE64 raw 152 = some 0

private theorem readBE16_of_headerInside
    (raw : ByteArray) (offset : Nat)
    (hheader : headerBytes ≤ raw.size)
    (hoffset : offset + 2 ≤ headerBytes) :
    Wire.readBE16 raw offset = some (cReadBE16At raw offset) := by
  exact readBE16_eq_wire raw offset (hoffset.trans hheader)

private theorem readBE32_of_headerInside
    (raw : ByteArray) (offset : Nat)
    (hheader : headerBytes ≤ raw.size)
    (hoffset : offset + 4 ≤ headerBytes) :
    Wire.readBE32 raw offset = some (cReadBE32At raw offset) := by
  exact readBE32_eq_wire raw offset (hoffset.trans hheader)

private theorem readBE64_of_headerInside
    (raw : ByteArray) (offset : Nat)
    (hheader : headerBytes ≤ raw.size)
    (hoffset : offset + 8 ≤ headerBytes) :
    Wire.readBE64 raw offset = some (cReadBE64At raw offset) := by
  exact readBE64_eq_wire raw offset (hoffset.trans hheader)

theorem COpenV2Accepted.wireReads
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    HeaderWireReads raw (cDecodedHeader raw) := by
  refine {
    version := ?_
    width := ?_
    flags := ?_
    bound := ?_
    reusedPrimeBound := ?_
    logSeedAt := ?_
    logScale := ?_
    reciprocalScale := ?_
    primeCount := ?_
    factorRefCount := ?_
    factorPairCount := ?_
    eventCount := ?_
    powerRefCount := ?_
    primesOffset := ?_
    factorRefsOffset := ?_
    factorPairsOffset := ?_
    eventsOffset := ?_
    powerRefsOffset := ?_
    archiveBytes := ?_
    reserved0 := ?_
    reserved1 := ?_
  }
  · simpa only [cDecodedHeader] using
      readBE16_of_headerInside raw 8 accepted.headerInside
        (by norm_num [headerBytes])
  · rw [readBE16_of_headerInside raw 10 accepted.headerInside
        (by norm_num [headerBytes])]
    exact congrArg some accepted.width
  · simpa only [cDecodedHeader] using
      readBE32_of_headerInside raw 12 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 16 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 24 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 32 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 40 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 48 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 56 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 64 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 72 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 80 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 88 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 96 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 104 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 112 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 120 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 128 accepted.headerInside
        (by norm_num [headerBytes])
  · simpa only [cDecodedHeader] using
      readBE64_of_headerInside raw 136 accepted.headerInside
        (by norm_num [headerBytes])
  · rw [readBE64_of_headerInside raw 144 accepted.headerInside
        (by norm_num [headerBytes])]
    exact congrArg some accepted.reserved0
  · rw [readBE64_of_headerInside raw 152 accepted.headerInside
        (by norm_num [headerBytes])]
    exact congrArg some accepted.reserved1

/-- A successful set of fixed wire reads plus the semantic preflight check
is sufficient for the canonical parser to return the supplied header. -/
theorem parseHeader_of_wireReads
    {raw : ByteArray} {header : Header}
    (hmagic : raw.extract 0 8 = Wire.magicBytes.toByteArray)
    (reads : HeaderWireReads raw header)
    (hpreflight :
      Wire.headerPreflightCheck raw.size header = true) :
    Wire.parseHeader raw = some header := by
  unfold Wire.parseHeader
  simp only [hmagic, ↓reduceIte, reads.version, reads.width,
    reads.flags, reads.bound, reads.reusedPrimeBound,
    reads.logSeedAt, reads.logScale, reads.reciprocalScale,
    reads.primeCount, reads.factorRefCount, reads.factorPairCount,
    reads.eventCount, reads.powerRefCount, reads.primesOffset,
    reads.factorRefsOffset, reads.factorPairsOffset,
    reads.eventsOffset, reads.powerRefsOffset, reads.archiveBytes,
    reads.reserved0, reads.reserved1, Option.bind_eq_bind,
    Option.bind_none, Option.bind_some, and_true, hpreflight]

/-- Main source-to-wire theorem for the fixed V2 header opener. -/
theorem COpenV2Accepted.parseHeader
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    Wire.parseHeader raw = some (cDecodedHeader raw) :=
  parseHeader_of_wireReads accepted.sameMagic accepted.wireReads
    accepted.headerPreflight

/-- Consolidated source-refinement result: the successful C opener returns
the exact IR header selected by the canonical wire parser, while exposing
the preflight and each canonical section boundary for independent review. -/
theorem COpenV2Accepted.refinesHeader
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    Wire.parseHeader raw = some (cDecodedHeader raw) ∧
      Wire.headerPreflightCheck raw.size (cDecodedHeader raw) = true ∧
      CanonicalSectionFacts (cDecodedHeader raw) raw.size :=
  ⟨accepted.parseHeader, accepted.headerPreflight,
    accepted.sectionFacts⟩

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CHeaderRefinement
