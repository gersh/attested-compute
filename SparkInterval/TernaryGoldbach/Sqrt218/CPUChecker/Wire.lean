/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.IR

/-!
# Canonical fixed-width wire decoder for the Sqrt218 CPU checker

This is the architecture-independent byte model of
`cpu_checker/sqrt218/sqrt218_cpu_checker.c`.  It parses the fixed-width
`SQ218V2\0` input format into `ArchiveImage` using unsigned big-endian fields.
It checks the exact header, all reserved bytes, checked contiguous section
offsets, fixed record widths, and exact EOF before returning an image.

The final canonical-encoder comparison is intentional.  It proves that every
accepted image re-encodes to every input byte, so a receipt can bind the exact
byte string rather than an under-specified parsed prefix.  This file contains
no production bytes and performs no production replay when imported.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

/-! ## Fixed field encodings -/

/-- Literal input magic `SQ218V2\0`. -/
def magicBytes : List UInt8 :=
  [0x53, 0x51, 0x32, 0x31, 0x38, 0x56, 0x32, 0x00]

/-- Canonical reserved-byte padding used by the V2 encoder. -/
def zeroBytes (count : Nat) : List UInt8 :=
  List.replicate count 0

/-- Read one unsigned big-endian field of a fixed byte width.

This definition is public so source-level parser refinements can compare
their fixed-width byte arithmetic with the exact decoder used here. -/
def readBE
    (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat :=
  if offset + width ≤ raw.size then
    some ((List.range width).foldl
      (fun value index => 256 * value + (raw.get! (offset + index)).toNat) 0)
  else
    none

def readBE16 (raw : ByteArray) (offset : Nat) : Option Nat :=
  readBE 2 raw offset

def readBE32 (raw : ByteArray) (offset : Nat) : Option Nat :=
  readBE 4 raw offset

def readBE64 (raw : ByteArray) (offset : Nat) : Option Nat :=
  readBE 8 raw offset

/-- Encode one unsigned big-endian field, rejecting values which do not fit.

This primitive is public so byte-level source refinements can prove exact
read/encode round trips. -/
def encodeBE (width value : Nat) : Option (List UInt8) :=
  if value < 256 ^ width then
    some ((List.range width).map fun index =>
      UInt8.ofNat
        ((value / 256 ^ (width - (index + 1))) % 256))
  else
    none

def encodeBE16 (value : Nat) : Option (List UInt8) :=
  encodeBE 2 value

def encodeBE32 (value : Nat) : Option (List UInt8) :=
  encodeBE 4 value

def encodeBE64 (value : Nat) : Option (List UInt8) :=
  encodeBE 8 value

/-! ## Header and fixed-record parser -/

/-- Canonical header-only preflight predicate.

It contains the header-only checks performed by `tg_sq218_view_open_v2`
before record allocation.  Checked `u64` section arithmetic is delegated to
the same `canonicalEnd` model used by `IR.headerCheck`.  This is public so
the source-level C opener refinement can prove that its successful
checked-arithmetic path establishes the exact wire predicate. -/
def headerPreflightCheck
    (rawSize : Nat) (header : Header) : Bool :=
  decide (
    header.version = formatVersion ∧
      header.flags = 0 ∧
      2 ≤ header.bound ∧
      header.reusedPrimeBound ≤ header.bound ∧
      header.logSeedAt = logSeedAt ∧
      header.logScale = logScale ∧
      header.reciprocalScale = reciprocalScale ∧
      0 < header.primeCount ∧
      header.powerRefCount = header.eventCount ∧
      header.archiveBytes = rawSize ∧
      canonicalEnd header = some rawSize)

/-- Parse and preflight the fixed 160-byte V2 header.

This is public as the architecture-neutral target of source-parser
refinement proofs. -/
def parseHeader (raw : ByteArray) : Option Header := do
  if raw.extract 0 8 = magicBytes.toByteArray then pure () else none
  let version ← readBE16 raw 8
  let width ← readBE16 raw 10
  let flags ← readBE32 raw 12
  if width = headerBytes then pure () else none
  let bound ← readBE64 raw 16
  let reusedPrimeBound ← readBE64 raw 24
  let logSeedAt ← readBE64 raw 32
  let logScale ← readBE64 raw 40
  let reciprocalScale ← readBE64 raw 48
  let primeCount ← readBE64 raw 56
  let factorRefCount ← readBE64 raw 64
  let factorPairCount ← readBE64 raw 72
  let eventCount ← readBE64 raw 80
  let powerRefCount ← readBE64 raw 88
  let primesOffset ← readBE64 raw 96
  let factorRefsOffset ← readBE64 raw 104
  let factorPairsOffset ← readBE64 raw 112
  let eventsOffset ← readBE64 raw 120
  let powerRefsOffset ← readBE64 raw 128
  let archiveBytes ← readBE64 raw 136
  let reserved0 ← readBE64 raw 144
  let reserved1 ← readBE64 raw 152
  if reserved0 = 0 ∧ reserved1 = 0 then pure () else none
  let header : Header := {
    version
    flags
    bound
    reusedPrimeBound
    logSeedAt
    logScale
    reciprocalScale
    primeCount
    factorRefCount
    factorPairCount
    eventCount
    powerRefCount
    primesOffset
    factorRefsOffset
    factorPairsOffset
    eventsOffset
    powerRefsOffset
    archiveBytes
  }
  if headerPreflightCheck raw.size header then
    some header
  else
    none

/-- Decode one fixed-width prime record at an already selected byte offset.

This is public only as a target for the source-level C accessor refinement.
Callers decoding an archive should continue to use
`decodeCanonicalArchiveBytes`. -/
def parsePrimeRecord
    (raw : ByteArray) (offset : Nat) : Option PrimeRecord := do
  let prime ← readBE64 raw offset
  let witness ← readBE64 raw (offset + 8)
  let factorRefIndex ← readBE64 raw (offset + 16)
  let factorRefCount ← readBE32 raw (offset + 24)
  let gapPairCount ← readBE32 raw (offset + 28)
  let gapPairIndex ← readBE64 raw (offset + 32)
  let powerRefIndex ← readBE64 raw (offset + 40)
  let powerRefCount ← readBE32 raw (offset + 48)
  let reserved0 ← readBE32 raw (offset + 52)
  let logLower ← readBE64 raw (offset + 56)
  let logUpper ← readBE64 raw (offset + 64)
  let reserved1 ← readBE64 raw (offset + 72)
  if reserved0 = 0 ∧ reserved1 = 0 then
    some {
      prime
      witness
      factorRefIndex
      factorRefCount
      gapPairIndex
      gapPairCount
      powerRefIndex
      powerRefCount
      logLower
      logUpper
    }
  else
    none

/-- Decode one fixed-width factor-pair record at an already selected offset.

This is public only as a target for the source-level C accessor refinement. -/
def parseFactorPair
    (raw : ByteArray) (offset : Nat) : Option FactorPair := do
  let left ← readBE64 raw offset
  let right ← readBE64 raw (offset + 8)
  pure ⟨left, right⟩

/-- Decode one fixed-width event record at an already selected byte offset.

This is public only as a target for the source-level C accessor refinement.
In particular, the four reserved bytes remain part of this parser. -/
def parseEventRecord
    (raw : ByteArray) (offset : Nat) : Option EventRecord := do
  let value ← readBE64 raw offset
  let primeIndex ← readBE64 raw (offset + 8)
  let exponent ← readBE32 raw (offset + 16)
  let reserved ← readBE32 raw (offset + 20)
  let floorSqrt ← readBE64 raw (offset + 24)
  if reserved = 0 then
    some { value, primeIndex, exponent, floorSqrt }
  else
    none

/-! The following three lemmas keep source-level accessor proofs small.  They
only assemble already-established fixed-field reads; all byte arithmetic
remains in `readBE16`/`readBE32`/`readBE64`. -/

theorem parsePrimeRecord_eq_some_of_reads
    {raw : ByteArray} {offset prime witness factorRefIndex factorRefCount
      gapPairCount gapPairIndex powerRefIndex powerRefCount logLower
      logUpper : Nat}
    (hprime : readBE64 raw offset = some prime)
    (hwitness : readBE64 raw (offset + 8) = some witness)
    (hfactorRefIndex :
      readBE64 raw (offset + 16) = some factorRefIndex)
    (hfactorRefCount :
      readBE32 raw (offset + 24) = some factorRefCount)
    (hgapPairCount :
      readBE32 raw (offset + 28) = some gapPairCount)
    (hgapPairIndex :
      readBE64 raw (offset + 32) = some gapPairIndex)
    (hpowerRefIndex :
      readBE64 raw (offset + 40) = some powerRefIndex)
    (hpowerRefCount :
      readBE32 raw (offset + 48) = some powerRefCount)
    (hreserved0 : readBE32 raw (offset + 52) = some 0)
    (hlogLower : readBE64 raw (offset + 56) = some logLower)
    (hlogUpper : readBE64 raw (offset + 64) = some logUpper)
    (hreserved1 : readBE64 raw (offset + 72) = some 0) :
    parsePrimeRecord raw offset =
      some {
        prime
        witness
        factorRefIndex
        factorRefCount
        gapPairIndex
        gapPairCount
        powerRefIndex
        powerRefCount
        logLower
        logUpper
      } := by
  simp only [parsePrimeRecord, hprime, hwitness, hfactorRefIndex,
    hfactorRefCount, hgapPairCount, hgapPairIndex, hpowerRefIndex,
    hpowerRefCount, hreserved0, hlogLower, hlogUpper, hreserved1,
    Option.bind_eq_bind, Option.bind_some, and_self, ↓reduceIte]

theorem parseFactorPair_eq_some_of_reads
    {raw : ByteArray} {offset left right : Nat}
    (hleft : readBE64 raw offset = some left)
    (hright : readBE64 raw (offset + 8) = some right) :
    parseFactorPair raw offset = some ⟨left, right⟩ := by
  simp only [parseFactorPair, hleft, hright, Option.bind_eq_bind,
    Option.bind_some]
  rfl

theorem parseEventRecord_eq_some_of_reads
    {raw : ByteArray} {offset value primeIndex exponent floorSqrt : Nat}
    (hvalue : readBE64 raw offset = some value)
    (hprimeIndex : readBE64 raw (offset + 8) = some primeIndex)
    (hexponent : readBE32 raw (offset + 16) = some exponent)
    (hreserved : readBE32 raw (offset + 20) = some 0)
    (hfloorSqrt : readBE64 raw (offset + 24) = some floorSqrt) :
    parseEventRecord raw offset =
      some { value, primeIndex, exponent, floorSqrt } := by
  simp only [parseEventRecord, hvalue, hprimeIndex, hexponent,
    hreserved, hfloorSqrt, Option.bind_eq_bind, Option.bind_some,
    ↓reduceIte]

/-- Decode a contiguous fixed-width section in increasing source index order.

This helper is public only as a target for source-level loop refinements.
It performs no header, layout, or exact-EOF check; ordinary archive consumers
must continue to use `decodeCanonicalArchiveBytes`. -/
def parseRecords {α : Type}
    (raw : ByteArray) (start width count : Nat)
    (parse : ByteArray → Nat → Option α) : Option (List α) :=
  (List.range count).mapM fun index =>
    parse raw (start + index * width)

/-- Assemble the typed archive after header and section parsing.

This unchecked helper is public only as a target for source-level parser
refinement.  It still checks `headerCheck`, but it deliberately does not prove
that re-encoding the resulting image reproduces every input byte.  That final
byte-identity guard remains in `decodeCanonicalArchiveBytes`. -/
def parseArchiveBytesUnchecked
    (raw : ByteArray) : Option ArchiveImage := do
  let header ← parseHeader raw
  let primes ←
    parseRecords raw header.primesOffset primeRecordBytes
      header.primeCount parsePrimeRecord
  let factorRefs ←
    parseRecords raw header.factorRefsOffset factorRefBytes
      header.factorRefCount readBE64
  let factorPairs ←
    parseRecords raw header.factorPairsOffset factorPairBytes
      header.factorPairCount parseFactorPair
  let events ←
    parseRecords raw header.eventsOffset eventRecordBytes
      header.eventCount parseEventRecord
  let powerRefs ←
    parseRecords raw header.powerRefsOffset powerRefBytes
      header.powerRefCount readBE64
  let image : ArchiveImage := {
    byteLength := raw.size
    header
    primes
    factorRefs
    factorPairs
    events
    powerRefs
  }
  if headerCheck image then
    some image
  else
    none

/-- Assemble the unchecked archive from separately proved header and section
decodes.  This theorem is the compact source-refinement interface; it does
not discharge the later canonical re-encoding equality. -/
theorem parseArchiveBytesUnchecked_eq_some_of_sections
    {raw : ByteArray} {header : Header}
    {primes : List PrimeRecord} {factorRefs : List Nat}
    {factorPairs : List FactorPair} {events : List EventRecord}
    {powerRefs : List Nat}
    (hheader : parseHeader raw = some header)
    (hprimes :
      parseRecords raw header.primesOffset primeRecordBytes
          header.primeCount parsePrimeRecord =
        some primes)
    (hfactorRefs :
      parseRecords raw header.factorRefsOffset factorRefBytes
          header.factorRefCount readBE64 =
        some factorRefs)
    (hfactorPairs :
      parseRecords raw header.factorPairsOffset factorPairBytes
          header.factorPairCount parseFactorPair =
        some factorPairs)
    (hevents :
      parseRecords raw header.eventsOffset eventRecordBytes
          header.eventCount parseEventRecord =
        some events)
    (hpowerRefs :
      parseRecords raw header.powerRefsOffset powerRefBytes
          header.powerRefCount readBE64 =
        some powerRefs)
    (hcheck :
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.headerCheck
          {
            byteLength := raw.size
            header
            primes
            factorRefs
            factorPairs
            events
            powerRefs
          } =
        true) :
    parseArchiveBytesUnchecked raw =
      some {
        byteLength := raw.size
        header
        primes
        factorRefs
        factorPairs
        events
        powerRefs
      } := by
  unfold parseArchiveBytesUnchecked
  simp only [hheader, hprimes, hfactorRefs, hfactorPairs, hevents,
    hpowerRefs, Option.bind_eq_bind, Option.bind_some, hcheck,
    ↓reduceIte]

/-! ## Canonical encoder -/

/-- Encode the complete fixed V2 header.  Public for byte-level source
refinement; ordinary consumers should use `encodeCanonicalArchiveBytes`. -/
def encodeHeader (header : Header) : Option (List UInt8) := do
  let version ← encodeBE16 header.version
  let width ← encodeBE16 headerBytes
  let flags ← encodeBE32 header.flags
  let bound ← encodeBE64 header.bound
  let reusedPrimeBound ← encodeBE64 header.reusedPrimeBound
  let logSeedAt ← encodeBE64 header.logSeedAt
  let logScale ← encodeBE64 header.logScale
  let reciprocalScale ← encodeBE64 header.reciprocalScale
  let primeCount ← encodeBE64 header.primeCount
  let factorRefCount ← encodeBE64 header.factorRefCount
  let factorPairCount ← encodeBE64 header.factorPairCount
  let eventCount ← encodeBE64 header.eventCount
  let powerRefCount ← encodeBE64 header.powerRefCount
  let primesOffset ← encodeBE64 header.primesOffset
  let factorRefsOffset ← encodeBE64 header.factorRefsOffset
  let factorPairsOffset ← encodeBE64 header.factorPairsOffset
  let eventsOffset ← encodeBE64 header.eventsOffset
  let powerRefsOffset ← encodeBE64 header.powerRefsOffset
  let archiveBytes ← encodeBE64 header.archiveBytes
  pure (
    magicBytes ++ version ++ width ++ flags ++ bound ++
      reusedPrimeBound ++ logSeedAt ++ logScale ++ reciprocalScale ++
      primeCount ++ factorRefCount ++ factorPairCount ++ eventCount ++
      powerRefCount ++ primesOffset ++ factorRefsOffset ++
      factorPairsOffset ++ eventsOffset ++ powerRefsOffset ++ archiveBytes ++
      zeroBytes 16)

/-- Encode one fixed prime record.  Public for source refinement. -/
def encodePrimeRecord (row : PrimeRecord) :
    Option (List UInt8) := do
  let prime ← encodeBE64 row.prime
  let witness ← encodeBE64 row.witness
  let factorRefIndex ← encodeBE64 row.factorRefIndex
  let factorRefCount ← encodeBE32 row.factorRefCount
  let gapPairCount ← encodeBE32 row.gapPairCount
  let gapPairIndex ← encodeBE64 row.gapPairIndex
  let powerRefIndex ← encodeBE64 row.powerRefIndex
  let powerRefCount ← encodeBE32 row.powerRefCount
  let logLower ← encodeBE64 row.logLower
  let logUpper ← encodeBE64 row.logUpper
  pure (
    prime ++ witness ++ factorRefIndex ++ factorRefCount ++ gapPairCount ++
      gapPairIndex ++ powerRefIndex ++ powerRefCount ++ zeroBytes 4 ++
      logLower ++ logUpper ++ zeroBytes 8)

/-- Encode one fixed factor-pair record.  Public for source refinement. -/
def encodeFactorPair (pair : FactorPair) :
    Option (List UInt8) := do
  let left ← encodeBE64 pair.left
  let right ← encodeBE64 pair.right
  pure (left ++ right)

/-- Encode one fixed event record.  Public for source refinement. -/
def encodeEventRecord (event : EventRecord) :
    Option (List UInt8) := do
  let value ← encodeBE64 event.value
  let primeIndex ← encodeBE64 event.primeIndex
  let exponent ← encodeBE32 event.exponent
  let floorSqrt ← encodeBE64 event.floorSqrt
  pure (
    value ++ primeIndex ++ exponent ++ zeroBytes 4 ++ floorSqrt)

/-- Concatenate a list of successfully encoded fixed-width records. -/
def encodeRecords {α : Type}
    (encode : α → Option (List UInt8)) :
    List α → Option (List UInt8)
  | [] => some []
  | value :: rest => do
      let head ← encode value
      let tail ← encodeRecords encode rest
      pure (head ++ tail)

/-- Canonical byte spelling of a typed fixed-width V2 image.

The result is optional because an arbitrary caller-created `ArchiveImage` may
contain a value too large for its wire field.  Every successfully decoded image
has a successful encoding by `decodeCanonicalArchiveBytes_exact`. -/
def encodeCanonicalArchiveBytes
    (image : ArchiveImage) : Option ByteArray := do
  let header ← encodeHeader image.header
  let primes ← encodeRecords encodePrimeRecord image.primes
  let factorRefs ← encodeRecords encodeBE64 image.factorRefs
  let factorPairs ← encodeRecords encodeFactorPair image.factorPairs
  let events ← encodeRecords encodeEventRecord image.events
  let powerRefs ← encodeRecords encodeBE64 image.powerRefs
  pure
    (header ++ primes ++ factorRefs ++ factorPairs ++ events ++ powerRefs).toByteArray

/-! ## Canonical decoder and byte-identity theorems -/

private def finalizeCanonicalV2
    (raw : ByteArray) (image : ArchiveImage) :
    Except Reject ArchiveImage :=
  if headerCheck image then
    match encodeCanonicalArchiveBytes image with
    | some encoded =>
        if encoded = raw then
          .ok image
        else
          .error .malformed
    | none => .error .malformed
  else
    .error .malformed

/-- Decode one exact canonical fixed-width V2 byte string.

This is a structural parser.  `V2Adapter.completeRun` separately performs the
arithmetic and semantic certificate checks. -/
def decodeCanonicalArchiveBytes
    (raw : ByteArray) : Except Reject ArchiveImage :=
  match parseArchiveBytesUnchecked raw with
  | none => .error .malformed
  | some image => finalizeCanonicalV2 raw image

/-- Promote a successful typed parse to canonical acceptance once the
separate byte-identity obligation has been proved.

Source-level refinements normally establish `parseArchiveBytesUnchecked`
first.  They may use this theorem only after proving the encoder returns the
entire original byte array; accessor success alone is intentionally
insufficient. -/
theorem decodeCanonicalArchiveBytes_eq_ok_of_unchecked
    {raw : ByteArray} {image : ArchiveImage}
    (hparse : parseArchiveBytesUnchecked raw = some image)
    (hheader : headerCheck image = true)
    (hencode : encodeCanonicalArchiveBytes image = some raw) :
    decodeCanonicalArchiveBytes raw = .ok image := by
  unfold decodeCanonicalArchiveBytes
  rw [hparse]
  unfold finalizeCanonicalV2
  simp only [hheader, ↓reduceIte, hencode]

private theorem finalizeCanonicalV2_success
    {raw : ByteArray} {candidate image : ArchiveImage}
    (hdecode : finalizeCanonicalV2 raw candidate = .ok image) :
    candidate = image ∧
      headerCheck image = true ∧
      encodeCanonicalArchiveBytes image = some raw := by
  unfold finalizeCanonicalV2 at hdecode
  by_cases hheader : headerCheck candidate = true
  · rw [if_pos hheader] at hdecode
    cases hencode : encodeCanonicalArchiveBytes candidate with
    | none =>
        simp [hencode] at hdecode
    | some encoded =>
        rw [hencode] at hdecode
        change
          (if encoded = raw then
              (Except.ok candidate : Except Reject ArchiveImage)
            else Except.error .malformed) =
            Except.ok image at hdecode
        by_cases hbytes : encoded = raw
        · rw [if_pos hbytes] at hdecode
          have hequal : candidate = image :=
            Except.ok.inj hdecode
          subst image
          exact
            ⟨rfl, hheader,
              hencode.trans (congrArg some hbytes)⟩
        · rw [if_neg hbytes] at hdecode
          contradiction
  · rw [if_neg hheader] at hdecode
    contradiction

/-- Successful decoding fixes both the checked header/layout and every input
byte. -/
theorem decodeCanonicalArchiveBytes_success
    {raw : ByteArray} {image : ArchiveImage}
    (hdecode : decodeCanonicalArchiveBytes raw = .ok image) :
    headerCheck image = true ∧
      encodeCanonicalArchiveBytes image = some raw := by
  unfold decodeCanonicalArchiveBytes at hdecode
  cases hparse : parseArchiveBytesUnchecked raw with
  | none =>
      rw [hparse] at hdecode
      contradiction
  | some candidate =>
      rw [hparse] at hdecode
      exact (finalizeCanonicalV2_success hdecode).2

/-- Exact-EOF/canonicality theorem: re-encoding a successful result returns
the entire original `ByteArray`. -/
theorem decodeCanonicalArchiveBytes_exact
    {raw : ByteArray} {image : ArchiveImage}
    (hdecode : decodeCanonicalArchiveBytes raw = .ok image) :
    encodeCanonicalArchiveBytes image = some raw :=
  (decodeCanonicalArchiveBytes_success hdecode).2

/-- Short theorem name for consumers which need the canonical
decode-then-encode byte identity. -/
theorem encode_decode_exact
    {raw : ByteArray} {image : ArchiveImage}
    (hdecode : decodeCanonicalArchiveBytes raw = .ok image) :
    encodeCanonicalArchiveBytes image = some raw :=
  decodeCanonicalArchiveBytes_exact hdecode

/-- The decoder is functional: one byte string cannot produce two images. -/
theorem decodeCanonicalArchiveBytes_imageUnique
    {raw : ByteArray} {left right : ArchiveImage}
    (hleft : decodeCanonicalArchiveBytes raw = .ok left)
    (hright : decodeCanonicalArchiveBytes raw = .ok right) :
    left = right := by
  rw [hleft] at hright
  exact Except.ok.inj hright

/-- A returned image has no second accepted wire spelling. -/
theorem decodeCanonicalArchiveBytes_noAlternateEncoding
    {left right : ByteArray} {image : ArchiveImage}
    (hleft : decodeCanonicalArchiveBytes left = .ok image)
    (hright : decodeCanonicalArchiveBytes right = .ok image) :
    left = right := by
  have hencoded :
      (some left : Option ByteArray) = some right :=
    (decodeCanonicalArchiveBytes_exact hleft).symm.trans
      (decodeCanonicalArchiveBytes_exact hright)
  exact Option.some.inj hencoded

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire
