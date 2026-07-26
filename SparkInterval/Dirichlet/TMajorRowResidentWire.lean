/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Lean.Data.Json
import SparkInterval.Certificate.SHA256

/-!
# Finite wire contract for the row-resident Dirichlet component

This module is the total, fail-closed Lean boundary for the four artifacts
used by the bounded `TGDLTMB1` CUDA component:

* one authenticated `TGDLTMB1` input block;
* its concatenated `TGDAFFI1` output frames;
* the `TGDRCVS1` finite-recovery seed table; and
* the canonical JSON execution summary.

The layouts and constants are byte-for-byte counterparts of
`tg_dirichlet_tmajor_seeded.hpp`, `tg_dirichlet_allchars.hpp`,
`tg_dirichlet_recovery_seeds.hpp`, and
`dirichlet_tmajor_cuda_block.py`.  Acceptance checks framing, source geometry,
ordered finite binary64 boxes, nonnegative Taylor radii, all internal hashes,
and all cross-artifact counts and digests.

Concretely, the checker recomputes every row-payload hash, the row-binding
hash, every target-sidecar hash, both row/target stream hashes, the direct
source-chain hash, every seed-chunk hash, the seed records/root hashes, and the
complete input/output/seed/summary hashes selected by `ExternalPins`.  The
production bundle checker requires direct-MPFR sidecar mode; a structurally
parsed legacy q-major block is not accepted without its absent manifest.

This is deliberately a finite wire theorem.  It does **not** prove that the
CUDA executable refines the mathematical interval algorithm, that the
MPFR/FLINT-generated intervals contain their analytic values, that a
completed-L or zero computation happened, or that Platt's Theorem 7.1 follows.
The summary is required to state all such completion flags as false.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.Dirichlet.TMajorRowResidentWire

open Lean
open SparkInterval.Certificate

/-! ## Pinned source and layout constants -/

def formatVersion : Nat := 1
def tmajorFormatVersion : Nat := 2
def primitiveModulusRosterVersion : Nat := 2
def maximumRows : Nat := 64
def minimumModulus : Nat := 10_001
def maximumModulus : Nat := 400_000
def sourceM : Nat := 4
def sourceMaximumTIndex : Nat := 127_987
def sourceTStepNumerator : Nat := 5
def sourceTDenominator : Nat := 64
def latticeRows : Nat := 2_048
def taylorColumns : Nat := 16
def complexIntervalBytes : Nat := 32
def latticeCellCount : Nat := latticeRows * taylorColumns
def rowPayloadBytes : Nat := latticeCellCount * complexIntervalBytes

def blockHeaderBytes : Nat := 272
def rowHeaderBytes : Nat := 64
def targetHeaderBytes : Nat := 120
def blockFooterBytes : Nat := 160
def allCharsInputHeaderBytes : Nat := 72

def maximumBlockBytes : Nat := 4 * 1024 * 1024 * 1024
def maximumSummaryBytes : Nat := 4 * 1024 * 1024
def maximumSummaryJsonNesting : Nat := 4

def seedHeaderBytes : Nat := 96
def seedChunkHeaderBytes : Nat := 64
def seedRecordBytes : Nat := 48
def seedFooterBytes : Nat := 96
def seedMaximumX : Nat := 1_999_999
def seedMaximumChunkRecords : Nat := 2 ^ 20
def maximumSeedBytes : Nat := 256 * 1024 * 1024

def blockMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x4c, 0x54, 0x4d, 0x42, 0x31]

def rowMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x4c, 0x54, 0x4d, 0x52, 0x31]

def targetMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x4c, 0x54, 0x4d, 0x51, 0x31]

def blockFooterMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x4c, 0x54, 0x4d, 0x46, 0x31]

def allCharsInputMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x41, 0x46, 0x46, 0x49, 0x31]

def seedHeaderMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x52, 0x43, 0x56, 0x53, 0x31]

def seedChunkMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x52, 0x43, 0x56, 0x43, 0x31]

def seedFooterMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x52, 0x43, 0x56, 0x46, 0x31]

def targetSidecarDomain : List UInt8 :=
  "sparkinterval/tg/dirichlet-tmajor-seeded/target-sidecar/v1".toUTF8.toList ++
    [0]

def directSourceChainDomain : List UInt8 :=
  "sparkinterval/tg/dirichlet-tmajor-seeded/direct-source-chain/v1".toUTF8.toList ++
    [0]

def blockRowBindingDomain : List UInt8 :=
  "sparkinterval/tg/dirichlet-tmajor-spool/block-rows/v1".toUTF8.toList ++
    [0]

def seedChunkDomain : List UInt8 :=
  "sparkinterval/dirichlet-recovery-seed-chunk/v1".toUTF8.toList ++ [0]

def seedRootDomain : List UInt8 :=
  "sparkinterval/dirichlet-recovery-seed-root/v1".toUTF8.toList ++ [0]

/-! ## Exact little-endian and digest primitives -/

def checkedSlice? (raw : ByteArray) (offset count : Nat) : Option ByteArray :=
  if offset + count ≤ raw.size then
    some (raw.extract offset (offset + count))
  else
    none

def readLE (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat := do
  let bytes ← checkedSlice? raw offset width
  pure <| (List.range width).foldl
    (fun value index =>
      value + (bytes.get! index).toNat * 256 ^ index) 0

def readU32LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE 4 raw offset

def readU64LE (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE 8 raw offset

def readDigest (raw : ByteArray) (offset : Nat) : Option ByteArray :=
  checkedSlice? raw offset 32

def encodeLE (width value : Nat) : List UInt8 :=
  (List.range width).map fun index =>
    UInt8.ofNat ((value / 256 ^ index) % 256)

private def lowerHexDigit (value : Nat) : Char :=
  "0123456789abcdef".toList.getD value '0'

private def byteLowerHex (value : UInt8) : List Char :=
  [lowerHexDigit (value.toNat / 16), lowerHexDigit (value.toNat % 16)]

def byteArrayLowerHex (raw : ByteArray) : String :=
  String.ofList (raw.toList.flatMap byteLowerHex)

def zeroDigest : ByteArray :=
  (List.replicate 32 (0 : UInt8)).toByteArray

def digestNonzero (digest : ByteArray) : Bool :=
  digest.size == 32 && digest != zeroDigest

def digestMatches (payload digest : ByteArray) : Bool :=
  digest.size == 32 &&
    byteArrayLowerHex digest == SHA256.digestByteArray payload

def magicMatches (raw : ByteArray) (offset : Nat)
    (magic : List UInt8) : Bool :=
  match checkedSlice? raw offset magic.length with
  | none => false
  | some observed => observed == magic.toByteArray

/-! ## Raw IEEE-754 structural checks

No host `Float` is used.  The routines below classify and compare binary64
words directly.  They exactly cover the finite/order checks performed by the
Python and C++ wire readers, including treating the two zero encodings as the
same numerical endpoint.
-/

def binary64Exponent (word : Nat) : Nat :=
  (word / 2 ^ 52) % 2 ^ 11

def binary64Negative (word : Nat) : Bool :=
  decide (2 ^ 63 ≤ word)

def binary64Zero (word : Nat) : Bool :=
  word % 2 ^ 63 == 0

def binary64Finite (word : Nat) : Bool :=
  binary64Exponent word < 2047

def binary64LE (left right : Nat) : Bool :=
  if binary64Zero left && binary64Zero right then
    true
  else if binary64Negative left then
    if binary64Negative right then decide (right ≤ left) else true
  else if binary64Negative right then
    false
  else
    decide (left ≤ right)

def binary64Nonnegative (word : Nat) : Bool :=
  binary64Finite word &&
    (!binary64Negative word || binary64Zero word)

def binary64Between (lower value upper : Nat) : Bool :=
  binary64Finite value && binary64LE lower value && binary64LE value upper

def complexIntervalValidAt (raw : ByteArray) (offset : Nat) : Bool :=
  match
      readU64LE raw offset,
      readU64LE raw (offset + 8),
      readU64LE raw (offset + 16),
      readU64LE raw (offset + 24) with
  | some reLo, some reHi, some imLo, some imHi =>
      binary64Finite reLo && binary64Finite reHi &&
        binary64Finite imLo && binary64Finite imHi &&
        binary64LE reLo reHi && binary64LE imLo imHi
  | _, _, _, _ => false

def complexIntervalsValid (raw : ByteArray) (offset : Nat) :
    Nat → Bool
  | 0 => true
  | count + 1 =>
      complexIntervalValidAt raw offset &&
        complexIntervalsValid raw (offset + complexIntervalBytes) count

def nonnegativeBinary64sValid (raw : ByteArray) (offset : Nat) :
    Nat → Bool
  | 0 => true
  | count + 1 =>
      match readU64LE raw offset with
      | none => false
      | some word =>
          binary64Nonnegative word &&
            nonnegativeBinary64sValid raw (offset + 8) count

def seedRecordsValid (raw : ByteArray) (offset : Nat) : Nat → Bool
  | 0 => true
  | count + 1 =>
      match
          readU64LE raw offset,
          readU64LE raw (offset + 8),
          readU64LE raw (offset + 16),
          readU64LE raw (offset + 24),
          readU64LE raw (offset + 32),
          readU64LE raw (offset + 40) with
      | some ampLo, some ampHi, some reLo, some reHi, some imLo, some imHi =>
          binary64Finite ampLo && binary64Finite ampHi &&
            !binary64Zero ampLo && !binary64Negative ampLo &&
            binary64LE ampLo ampHi &&
            binary64LE ampHi 0x3ff0000000000000 &&
            binary64Between 0xbff0000000000000 reLo
              0x3ff0000000000000 &&
            binary64Between 0xbff0000000000000 reHi
              0x3ff0000000000000 &&
            binary64Between 0xbff0000000000000 imLo
              0x3ff0000000000000 &&
            binary64Between 0xbff0000000000000 imHi
              0x3ff0000000000000 &&
            binary64LE reLo reHi && binary64LE imLo imHi &&
            seedRecordsValid raw (offset + seedRecordBytes) count
      | _, _, _, _, _, _ => false

/-! ## Formulaic source geometry -/

def sourceHeightNumerator (q : Nat) : Nat :=
  max 100_000_000
    (200 * q + if q % 2 = 0 then 75_000_000 else 37_500_000)

def maximumTIndex (q : Nat) : Nat :=
  sourceHeightNumerator q * sourceTDenominator /
    (q * sourceTStepNumerator)

def expectedBatch (firstTIndex stopExclusive q : Nat) : Nat :=
  min stopExclusive (maximumTIndex q + 1) - firstTIndex

/-- Exact nonempty-primitive-character criterion for the `q > 2` source
range.  Version 1 of the transport included the empty cases `q % 4 = 2`;
format version 2 rejects them at the parser boundary. -/
def hasPrimitiveCharacterModulus (q : Nat) : Bool :=
  q % 4 != 2

def canonicalComponentCount (q : Nat) : Nat :=
  q.primeFactorsList.foldl (fun count prime =>
    let exponent := q.factorization prime
    count +
      if prime = 2 then
        if exponent ≤ 1 then 0 else if exponent = 2 then 1 else 2
      else
        1) 0

def expectedTargetQs
    (qStart qStop firstTIndex stopExclusive : Nat) : List Nat :=
  (List.range (qStop - qStart + 1)).map (qStart + ·) |>.filter fun q =>
    hasPrimitiveCharacterModulus q &&
      decide (0 < expectedBatch firstTIndex stopExclusive q)

/-! ## `TGDLTMB1` input -/

structure BlockHeader where
  laneIndex : Nat
  rowCount : Nat
  targetCount : Nat
  qStart : Nat
  qStop : Nat
  m : Nat
  sidecarMode : Nat
  firstTIndex : Nat
  tIndexStopExclusive : Nat
  encodedRowPayloadBytes : Nat
  encodedRowRecordBytes : Nat
  encodedTargetHeaderBytes : Nat
  sourceContractSHA256 : ByteArray
  spoolReceiptSHA256 : ByteArray
  rowBindingsSHA256 : ByteArray
  seedArtifactSHA256 : ByteArray
  seedReplaySHA256 : ByteArray
  sidecarSourceSHA256 : ByteArray
  deriving DecidableEq

def BlockHeader.IsValid (header : BlockHeader) : Prop :=
  1 ≤ header.rowCount ∧
    header.rowCount ≤ maximumRows ∧
    1 ≤ header.targetCount ∧
    minimumModulus ≤ header.qStart ∧
    header.qStart ≤ header.qStop ∧
    header.qStop ≤ maximumModulus ∧
    header.m = sourceM ∧
    (header.sidecarMode = 0 ∨ header.sidecarMode = 1) ∧
    header.firstTIndex ≤ sourceMaximumTIndex ∧
    header.tIndexStopExclusive =
      header.firstTIndex + header.rowCount ∧
    header.tIndexStopExclusive ≤ sourceMaximumTIndex + 1 ∧
    header.firstTIndex * sourceTStepNumerator < 2 ^ 63 ∧
    header.encodedRowPayloadBytes = rowPayloadBytes ∧
    header.encodedRowRecordBytes = rowHeaderBytes + rowPayloadBytes ∧
    header.encodedTargetHeaderBytes = targetHeaderBytes ∧
    header.targetCount =
      (expectedTargetQs header.qStart header.qStop header.firstTIndex
        header.tIndexStopExclusive).length ∧
    digestNonzero header.sourceContractSHA256 = true ∧
    digestNonzero header.spoolReceiptSHA256 = true ∧
    digestNonzero header.rowBindingsSHA256 = true ∧
    digestNonzero header.seedArtifactSHA256 = true ∧
    digestNonzero header.seedReplaySHA256 = true ∧
    digestNonzero header.sidecarSourceSHA256 = true

instance (header : BlockHeader) : Decidable header.IsValid := by
  unfold BlockHeader.IsValid
  infer_instance

def parseBlockHeaderAt (raw : ByteArray) (offset : Nat) :
    Option BlockHeader := do
  if magicMatches raw offset blockMagic then pure () else none
  let version ← readU32LE raw (offset + 8)
  if version = tmajorFormatVersion then pure () else none
  let laneIndex ← readU32LE raw (offset + 12)
  let rowCount ← readU32LE raw (offset + 16)
  let targetCount ← readU32LE raw (offset + 20)
  let qStart ← readU32LE raw (offset + 24)
  let qStop ← readU32LE raw (offset + 28)
  let m ← readU32LE raw (offset + 32)
  let sidecarMode ← readU32LE raw (offset + 36)
  let firstTIndex ← readU64LE raw (offset + 40)
  let tIndexStopExclusive ← readU64LE raw (offset + 48)
  let encodedRowPayloadBytes ← readU64LE raw (offset + 56)
  let encodedRowRecordBytes ← readU64LE raw (offset + 64)
  let encodedTargetHeaderBytes ← readU64LE raw (offset + 72)
  let sourceContractSHA256 ← readDigest raw (offset + 80)
  let spoolReceiptSHA256 ← readDigest raw (offset + 112)
  let rowBindingsSHA256 ← readDigest raw (offset + 144)
  let seedArtifactSHA256 ← readDigest raw (offset + 176)
  let seedReplaySHA256 ← readDigest raw (offset + 208)
  let sidecarSourceSHA256 ← readDigest raw (offset + 240)
  pure {
    laneIndex
    rowCount
    targetCount
    qStart
    qStop
    m
    sidecarMode
    firstTIndex
    tIndexStopExclusive
    encodedRowPayloadBytes
    encodedRowRecordBytes
    encodedTargetHeaderBytes
    sourceContractSHA256
    spoolReceiptSHA256
    rowBindingsSHA256
    seedArtifactSHA256
    seedReplaySHA256
    sidecarSourceSHA256
  }

def parseBlockHeader (raw : ByteArray) : Option BlockHeader := do
  if raw.size = blockHeaderBytes then pure () else none
  let header ← parseBlockHeaderAt raw 0
  if _ : header.IsValid then pure header else none

structure RowHeader where
  tIndex : Nat
  payloadSHA256 : ByteArray
  deriving DecidableEq

def parseRowHeaderAt
    (raw : ByteArray) (offset expectedTIndex : Nat) : Option RowHeader := do
  if magicMatches raw offset rowMagic then pure () else none
  let version ← readU32LE raw (offset + 8)
  let reserved ← readU32LE raw (offset + 12)
  let tIndex ← readU64LE raw (offset + 16)
  let payloadBytes ← readU64LE raw (offset + 24)
  let payloadSHA256 ← readDigest raw (offset + 32)
  if version = tmajorFormatVersion && reserved = 0 &&
      tIndex = expectedTIndex && payloadBytes = rowPayloadBytes &&
      digestNonzero payloadSHA256 then
    pure { tIndex, payloadSHA256 }
  else
    none

structure ParsedRows where
  headers : List RowHeader
  stopOffset : Nat
  deriving DecidableEq

def parseRows (raw : ByteArray) : Nat → Nat → Nat → Option ParsedRows
  | 0, _, offset => some { headers := [], stopOffset := offset }
  | count + 1, expectedTIndex, offset => do
      let header ← parseRowHeaderAt raw offset expectedTIndex
      let payloadOffset := offset + rowHeaderBytes
      let payload ← checkedSlice? raw payloadOffset rowPayloadBytes
      if !digestMatches payload header.payloadSHA256 then none
      if !complexIntervalsValid payload 0 latticeCellCount then none
      let rest ← parseRows raw count (expectedTIndex + 1)
        (payloadOffset + rowPayloadBytes)
      pure { headers := header :: rest.headers, stopOffset := rest.stopOffset }

structure TargetHeader where
  q : Nat
  componentCount : Nat
  batchCount : Nat
  groupOrder : Nat
  firstTNumerator : Nat
  valueCount : Nat
  factorBytes : Nat
  tailBytes : Nat
  sidecarSHA256 : ByteArray
  deriving DecidableEq

def parseTargetHeaderAt
    (raw : ByteArray) (offset : Nat) (block : BlockHeader)
    (expectedQ : Nat) : Option TargetHeader := do
  if magicMatches raw offset targetMagic then pure () else none
  let version ← readU32LE raw (offset + 8)
  let q ← readU32LE raw (offset + 12)
  let componentCount ← readU32LE raw (offset + 16)
  let batchCount ← readU32LE raw (offset + 20)
  let reserved0 ← readU32LE raw (offset + 24)
  let reserved1 ← readU32LE raw (offset + 28)
  let groupOrder ← readU64LE raw (offset + 32)
  let firstTNumerator ← readU64LE raw (offset + 40)
  let tDenominator ← readU64LE raw (offset + 48)
  let tStepNumerator ← readU64LE raw (offset + 56)
  let valueCount ← readU64LE raw (offset + 64)
  let factorBytes ← readU64LE raw (offset + 72)
  let tailBytes ← readU64LE raw (offset + 80)
  let sidecarSHA256 ← readDigest raw (offset + 88)
  let expectedBatchCount :=
    expectedBatch block.firstTIndex block.tIndexStopExclusive expectedQ
  let expectedGroupOrder := Nat.totient expectedQ
  if version = tmajorFormatVersion && q = expectedQ &&
      componentCount = canonicalComponentCount expectedQ &&
      batchCount = expectedBatchCount && 0 < batchCount &&
      reserved0 = 0 && reserved1 = 0 &&
      groupOrder = expectedGroupOrder &&
      firstTNumerator =
        block.firstTIndex * sourceTStepNumerator &&
      firstTNumerator < 2 ^ 63 &&
      tDenominator = sourceTDenominator &&
      tStepNumerator = sourceTStepNumerator &&
      valueCount = batchCount * groupOrder &&
      factorBytes = batchCount * complexIntervalBytes &&
      tailBytes = batchCount * 8 &&
      digestNonzero sidecarSHA256 then
    pure {
      q
      componentCount
      batchCount
      groupOrder
      firstTNumerator
      valueCount
      factorBytes
      tailBytes
      sidecarSHA256
    }
  else
    none

def targetSidecarBytes
    (target : TargetHeader) (factors tails : ByteArray) : ByteArray :=
  (targetSidecarDomain ++
    encodeLE 4 target.q ++
    encodeLE 4 target.batchCount ++
    encodeLE 8 target.firstTNumerator ++
    encodeLE 8 target.groupOrder ++
    factors.toList ++ tails.toList).toByteArray

structure ParsedTargets where
  headers : List TargetHeader
  stopOffset : Nat
  targetRowReferenceCount : Nat
  valueCount : Nat
  sidecarBytes : Nat
  deriving DecidableEq

def parseTargets (raw : ByteArray) (block : BlockHeader) :
    List Nat → Nat → Option ParsedTargets
  | [], offset => some {
      headers := []
      stopOffset := offset
      targetRowReferenceCount := 0
      valueCount := 0
      sidecarBytes := 0
    }
  | expectedQ :: expectedQs, offset => do
      let target ← parseTargetHeaderAt raw offset block expectedQ
      let factorOffset := offset + targetHeaderBytes
      let factors ← checkedSlice? raw factorOffset target.factorBytes
      let tailOffset := factorOffset + target.factorBytes
      let tails ← checkedSlice? raw tailOffset target.tailBytes
      if !complexIntervalsValid factors 0 target.batchCount then none
      if !nonnegativeBinary64sValid tails 0 target.batchCount then none
      if !digestMatches (targetSidecarBytes target factors tails)
          target.sidecarSHA256 then none
      let rest ← parseTargets raw block expectedQs
        (tailOffset + target.tailBytes)
      pure {
        headers := target :: rest.headers
        stopOffset := rest.stopOffset
        targetRowReferenceCount :=
          target.batchCount + rest.targetRowReferenceCount
        valueCount := target.valueCount + rest.valueCount
        sidecarBytes :=
          target.factorBytes + target.tailBytes + rest.sidecarBytes
      }

structure BlockFooter where
  rowCount : Nat
  targetCount : Nat
  targetRowReferenceCount : Nat
  valueCount : Nat
  sidecarBytes : Nat
  sourceInputBytes : Nat
  rowStreamSHA256 : ByteArray
  targetStreamSHA256 : ByteArray
  sourceInputChainSHA256 : ByteArray
  deriving DecidableEq

def parseBlockFooterAt (raw : ByteArray) (offset : Nat) :
    Option BlockFooter := do
  if magicMatches raw offset blockFooterMagic then pure () else none
  let version ← readU32LE raw (offset + 8)
  let reserved ← readU32LE raw (offset + 12)
  let rowCount ← readU64LE raw (offset + 16)
  let targetCount ← readU64LE raw (offset + 24)
  let targetRowReferenceCount ← readU64LE raw (offset + 32)
  let valueCount ← readU64LE raw (offset + 40)
  let sidecarBytes ← readU64LE raw (offset + 48)
  let sourceInputBytes ← readU64LE raw (offset + 56)
  let rowStreamSHA256 ← readDigest raw (offset + 64)
  let targetStreamSHA256 ← readDigest raw (offset + 96)
  let sourceInputChainSHA256 ← readDigest raw (offset + 128)
  if version = tmajorFormatVersion && reserved = 0 &&
      digestNonzero rowStreamSHA256 &&
      digestNonzero targetStreamSHA256 &&
      digestNonzero sourceInputChainSHA256 then
    pure {
      rowCount
      targetCount
      targetRowReferenceCount
      valueCount
      sidecarBytes
      sourceInputBytes
      rowStreamSHA256
      targetStreamSHA256
      sourceInputChainSHA256
    }
  else
    none

def directSourceChainBytes
    (block : BlockHeader) (targets : List TargetHeader) : ByteArray :=
  (directSourceChainDomain ++ block.sidecarSourceSHA256.toList ++
    targets.flatMap fun target =>
      encodeLE 4 target.q ++ encodeLE 8 target.valueCount ++
        target.sidecarSHA256.toList).toByteArray

def rowBindingBytes
    (block : BlockHeader) (rows : List RowHeader) : ByteArray :=
  (blockRowBindingDomain ++ block.spoolReceiptSHA256.toList ++
    rows.flatMap fun row =>
      encodeLE 8 row.tIndex ++ row.payloadSHA256.toList).toByteArray

structure InputArtifact where
  header : BlockHeader
  rows : List RowHeader
  targets : List TargetHeader
  footer : BlockFooter
  deriving DecidableEq

def parseInputArtifact (raw : ByteArray) : Option InputArtifact := do
  if 1 ≤ raw.size && raw.size ≤ maximumBlockBytes then pure () else none
  let header ← parseBlockHeaderAt raw 0
  if _ : header.IsValid then pure () else none
  let rows ← parseRows raw header.rowCount header.firstTIndex blockHeaderBytes
  let expectedQs :=
    expectedTargetQs header.qStart header.qStop header.firstTIndex
      header.tIndexStopExclusive
  let targets ← parseTargets raw header expectedQs rows.stopOffset
  let footer ← parseBlockFooterAt raw targets.stopOffset
  if raw.size = targets.stopOffset + blockFooterBytes then pure () else none
  let rowStream ← checkedSlice? raw blockHeaderBytes
    (rows.stopOffset - blockHeaderBytes)
  let targetStream ← checkedSlice? raw rows.stopOffset
    (targets.stopOffset - rows.stopOffset)
  if footer.rowCount = header.rowCount &&
      footer.targetCount = header.targetCount &&
      footer.targetRowReferenceCount =
        targets.targetRowReferenceCount &&
      footer.valueCount = targets.valueCount &&
      footer.sidecarBytes = targets.sidecarBytes &&
      ((header.sidecarMode = 0 &&
          targets.sidecarBytes ≤ footer.sourceInputBytes) ||
        (header.sidecarMode = 1 && footer.sourceInputBytes = 0)) &&
      digestMatches rowStream footer.rowStreamSHA256 &&
      digestMatches targetStream footer.targetStreamSHA256 &&
      digestMatches (rowBindingBytes header rows.headers)
        header.rowBindingsSHA256 &&
      (header.sidecarMode != 1 ||
        digestMatches (directSourceChainBytes header targets.headers)
          footer.sourceInputChainSHA256) then
    pure {
      header
      rows := rows.headers
      targets := targets.headers
      footer
    }
  else
    none

/-! ## Concatenated `TGDAFFI1` output -/

structure OutputFrame where
  q : Nat
  componentCount : Nat
  batchCount : Nat
  groupOrder : Nat
  firstTNumerator : Nat
  valueCount : Nat
  deriving DecidableEq

def parseOutputFrameAt
    (raw : ByteArray) (offset : Nat) (expected : TargetHeader) :
    Option (OutputFrame × Nat) := do
  if magicMatches raw offset allCharsInputMagic then pure () else none
  let version ← readU32LE raw (offset + 8)
  let q ← readU32LE raw (offset + 12)
  let componentCount ← readU32LE raw (offset + 16)
  let batchCount ← readU32LE raw (offset + 20)
  let groupOrder ← readU64LE raw (offset + 24)
  let firstTNumerator ← readU64LE raw (offset + 32)
  let tDenominator ← readU64LE raw (offset + 40)
  let tStepNumerator ← readU64LE raw (offset + 48)
  let valueCount ← readU64LE raw (offset + 56)
  let reserved0 ← readU64LE raw (offset + 64)
  let payloadOffset := offset + allCharsInputHeaderBytes
  let payloadBytes := valueCount * complexIntervalBytes
  let _payload ← checkedSlice? raw payloadOffset payloadBytes
  if version = formatVersion &&
      q = expected.q &&
      componentCount = expected.componentCount &&
      batchCount = expected.batchCount &&
      groupOrder = expected.groupOrder &&
      firstTNumerator = expected.firstTNumerator &&
      firstTNumerator < 2 ^ 63 &&
      tDenominator = sourceTDenominator &&
      tStepNumerator = sourceTStepNumerator &&
      valueCount = expected.valueCount &&
      reserved0 = 0 &&
      complexIntervalsValid raw payloadOffset valueCount then
    pure ({
      q
      componentCount
      batchCount
      groupOrder
      firstTNumerator
      valueCount
    }, payloadOffset + payloadBytes)
  else
    none

structure OutputArtifact where
  frames : List OutputFrame
  valueCount : Nat
  deriving DecidableEq

private structure ParsedOutputFrames where
  frames : List OutputFrame
  stopOffset : Nat
  valueCount : Nat
  deriving DecidableEq

private def parseOutputFrames (raw : ByteArray) :
    List TargetHeader → Nat → Option ParsedOutputFrames
  | [], offset => some { frames := [], stopOffset := offset, valueCount := 0 }
  | target :: targets, offset => do
      let (frame, nextOffset) ← parseOutputFrameAt raw offset target
      let rest ← parseOutputFrames raw targets nextOffset
      pure {
        frames := frame :: rest.frames
        stopOffset := rest.stopOffset
        valueCount := frame.valueCount + rest.valueCount
      }

def parseOutputArtifact
    (input : InputArtifact) (raw : ByteArray) : Option OutputArtifact := do
  let parsed ← parseOutputFrames raw input.targets 0
  if parsed.stopOffset = raw.size &&
      parsed.frames.length = input.header.targetCount &&
      parsed.valueCount = input.footer.valueCount then
    pure { frames := parsed.frames, valueCount := parsed.valueCount }
  else
    none

/-! ## `TGDRCVS1` recovery-seed artifact -/

structure SeedHeader where
  xStart : Nat
  xStop : Nat
  recordCount : Nat
  generationPrecisionBits : Nat
  unionPrecisionBits : Nat
  chunkRecords : Nat
  deriving DecidableEq

def SeedHeader.IsValid (header : SeedHeader) : Prop :=
  header.xStart = 1 ∧
    header.xStart ≤ header.xStop ∧
    header.xStop ≤ seedMaximumX ∧
    header.recordCount = header.xStop - header.xStart + 1 ∧
    128 ≤ header.generationPrecisionBits ∧
    header.unionPrecisionBits = header.generationPrecisionBits + 64 ∧
    1 ≤ header.chunkRecords ∧
    header.chunkRecords ≤ seedMaximumChunkRecords

instance (header : SeedHeader) : Decidable header.IsValid := by
  unfold SeedHeader.IsValid
  infer_instance

def parseSeedHeaderAt (raw : ByteArray) (offset : Nat) :
    Option SeedHeader := do
  if magicMatches raw offset seedHeaderMagic then pure () else none
  let version ← readU32LE raw (offset + 8)
  let m ← readU32LE raw (offset + 12)
  let maximumQ ← readU32LE raw (offset + 16)
  let recordSize ← readU32LE raw (offset + 20)
  let xStart ← readU64LE raw (offset + 24)
  let xStop ← readU64LE raw (offset + 32)
  let tStepNumerator ← readU64LE raw (offset + 40)
  let tDenominator ← readU64LE raw (offset + 48)
  let recordCount ← readU64LE raw (offset + 56)
  let generationPrecisionBits ← readU32LE raw (offset + 64)
  let unionPrecisionBits ← readU32LE raw (offset + 68)
  let chunkRecords ← readU64LE raw (offset + 72)
  let reserved0 ← readU64LE raw (offset + 80)
  let reserved1 ← readU64LE raw (offset + 88)
  let header : SeedHeader := {
    xStart
    xStop
    recordCount
    generationPrecisionBits
    unionPrecisionBits
    chunkRecords
  }
  if version = formatVersion && m = sourceM &&
      maximumQ = maximumModulus && recordSize = seedRecordBytes &&
      tStepNumerator = sourceTStepNumerator &&
      tDenominator = sourceTDenominator &&
      reserved0 = 0 && reserved1 = 0 then
    if _ : header.IsValid then pure header else none
  else
    none

def parseSeedHeader (raw : ByteArray) : Option SeedHeader := do
  if raw.size = seedHeaderBytes then pure () else none
  parseSeedHeaderAt raw 0

structure SeedChunk where
  firstX : Nat
  recordCount : Nat
  payloadSHA256 : ByteArray
  deriving DecidableEq

private structure ParsedSeedChunks where
  chunks : List SeedChunk
  payloads : List ByteArray
  stopOffset : Nat
  deriving DecidableEq

private def parseSeedChunks
    (raw : ByteArray) (chunkRecords : Nat) :
    Nat → Nat → Nat → Nat → Option ParsedSeedChunks
  | 0, remaining, _, offset =>
      if remaining = 0 then
        some { chunks := [], payloads := [], stopOffset := offset }
      else
        none
  | fuel + 1, remaining, expectedX, offset => do
      if remaining = 0 then
        pure { chunks := [], payloads := [], stopOffset := offset }
      else
      if magicMatches raw offset seedChunkMagic then pure () else none
      let version ← readU32LE raw (offset + 8)
      let reserved ← readU32LE raw (offset + 12)
      let firstX ← readU64LE raw (offset + 16)
      let recordCount ← readU64LE raw (offset + 24)
      let payloadSHA256 ← readDigest raw (offset + 32)
      let expectedCount := min chunkRecords remaining
      let payloadOffset := offset + seedChunkHeaderBytes
      let payload ← checkedSlice? raw payloadOffset
        (recordCount * seedRecordBytes)
      let chunkHashInput :=
        (seedChunkDomain ++ encodeLE 8 firstX ++ encodeLE 8 recordCount ++
          payload.toList).toByteArray
      if version != formatVersion || reserved != 0 ||
          firstX != expectedX || recordCount != expectedCount ||
          recordCount = 0 || !digestNonzero payloadSHA256 ||
          !digestMatches chunkHashInput payloadSHA256 ||
          !seedRecordsValid payload 0 recordCount then
        none
      else
        let rest ← parseSeedChunks raw chunkRecords fuel
          (remaining - recordCount) (expectedX + recordCount)
          (payloadOffset + recordCount * seedRecordBytes)
        pure {
          chunks := {
            firstX
            recordCount
            payloadSHA256
          } :: rest.chunks
          payloads := payload :: rest.payloads
          stopOffset := rest.stopOffset
        }

structure SeedFooter where
  recordCount : Nat
  chunkCount : Nat
  recordsSHA256 : ByteArray
  chunkRootSHA256 : ByteArray
  deriving DecidableEq

def parseSeedFooterAt (raw : ByteArray) (offset : Nat) :
    Option SeedFooter := do
  if magicMatches raw offset seedFooterMagic then pure () else none
  let version ← readU32LE raw (offset + 8)
  let reserved ← readU32LE raw (offset + 12)
  let recordCount ← readU64LE raw (offset + 16)
  let chunkCount ← readU64LE raw (offset + 24)
  let recordsSHA256 ← readDigest raw (offset + 32)
  let chunkRootSHA256 ← readDigest raw (offset + 64)
  if version = formatVersion && reserved = 0 &&
      digestNonzero recordsSHA256 && digestNonzero chunkRootSHA256 then
    pure { recordCount, chunkCount, recordsSHA256, chunkRootSHA256 }
  else
    none

structure SeedArtifact where
  header : SeedHeader
  chunks : List SeedChunk
  footer : SeedFooter
  deriving DecidableEq

def parseSeedArtifact (raw : ByteArray) : Option SeedArtifact := do
  if seedHeaderBytes + seedChunkHeaderBytes + seedRecordBytes +
      seedFooterBytes ≤ raw.size &&
      raw.size ≤ maximumSeedBytes then pure () else none
  let header ← parseSeedHeaderAt raw 0
  let chunks ← parseSeedChunks raw header.chunkRecords header.recordCount
    header.recordCount header.xStart seedHeaderBytes
  let footer ← parseSeedFooterAt raw chunks.stopOffset
  if raw.size = chunks.stopOffset + seedFooterBytes then pure () else none
  let recordPayload :=
    chunks.payloads.flatMap ByteArray.toList |>.toByteArray
  let rootPayload :=
    (seedRootDomain ++
      chunks.chunks.flatMap fun chunk => chunk.payloadSHA256.toList).toByteArray
  if footer.recordCount = header.recordCount &&
      footer.chunkCount = chunks.chunks.length &&
      digestMatches recordPayload footer.recordsSHA256 &&
      digestMatches rootPayload footer.chunkRootSHA256 then
    pure { header, chunks := chunks.chunks, footer }
  else
    none

/-! ## Canonical execution-summary JSON -/

def summarySchema : String :=
  "sparkinterval.tg.dirichlet_tmajor_cuda.execution_summary.v1"

def summaryAlgorithmId : String :=
  "platt-dirichlet-tmajor-row-resident-seeded-cuda-v1"

def summaryClassification : String :=
  "row_resident_seeded_cuda_component_not_zero_or_turing_closure"

def summaryFieldNames : List String := [
  "algorithm_id",
  "all_character_fft_executed",
  "canonical_descriptor_input_bytes",
  "classification",
  "completed_l_zero_state_validated",
  "elapsed_kernel_nanoseconds",
  "external_atom_discharged",
  "input_artifact_sha256",
  "lane_index",
  "lattice_h2d_upload_count",
  "output_stream_sha256",
  "recovery_seed_artifact_sha256",
  "row_bindings_sha256",
  "row_count",
  "row_payload_h2d_bytes",
  "schema",
  "schema_version",
  "sidecar_source_sha256",
  "source_contract_sha256",
  "source_scale_run",
  "spool_receipt_sha256",
  "target_count",
  "transcendental_device_calls",
  "trusted_execution_attested",
  "value_count",
  "zero_completeness_claimed"
]

structure ExecutionSummary where
  allCharacterFFTExecuted : Bool
  completedLZeroStateValidated : Bool
  elapsedKernelNanoseconds : Nat
  externalAtomDischarged : Bool
  inputArtifactSHA256 : String
  laneIndex : Nat
  outputStreamSHA256 : String
  recoverySeedArtifactSHA256 : String
  rowBindingsSHA256 : String
  rowCount : Nat
  rowPayloadH2DBytes : Nat
  sidecarSourceSHA256 : String
  sourceContractSHA256 : String
  sourceScaleRun : Bool
  spoolReceiptSHA256 : String
  targetCount : Nat
  trustedExecutionAttested : Bool
  valueCount : Nat
  zeroCompletenessClaimed : Bool
  deriving DecidableEq

def ExecutionSummary.IsComponentOnly
    (summary : ExecutionSummary) : Prop :=
  summary.allCharacterFFTExecuted = false ∧
    summary.completedLZeroStateValidated = false ∧
    summary.externalAtomDischarged = false ∧
    summary.sourceScaleRun = false ∧
    summary.trustedExecutionAttested = false ∧
    summary.zeroCompletenessClaimed = false

instance (summary : ExecutionSummary) :
    Decidable summary.IsComponentOnly := by
  unfold ExecutionSummary.IsComponentOnly
  infer_instance

private def exactFields
    (json : Json) (expected : List String) : Except String Unit := do
  let object ← json.getObj?
  let keys := object.keys
  if keys.length != expected.length || !keys.all expected.contains then
    throw "execution summary has wrong fields"

private def jsonField (json : Json) (name : String) : Except String Json :=
  match json.getObjVal? name with
  | .ok value => pure value
  | .error _ => throw s!"execution summary is missing {name}"

private def natField (json : Json) (name : String) : Except String Nat := do
  (← jsonField json name).getNat?

private def stringField
    (json : Json) (name : String) : Except String String := do
  (← jsonField json name).getStr?

private def boolField
    (json : Json) (name : String) : Except String Bool := do
  (← jsonField json name).getBool?

private def isLowerHexCharacter (character : Char) : Bool :=
  ('0' ≤ character && character ≤ '9') ||
    ('a' ≤ character && character ≤ 'f')

def isLowerSHA256 (text : String) : Bool :=
  text.length == 64 && text.toList.all isLowerHexCharacter

private structure JsonScanState where
  depth : Nat := 0
  inString : Bool := false
  escaped : Bool := false
  valid : Bool := true

private def scanJsonCharacter
    (state : JsonScanState) (character : Char) : JsonScanState :=
  if !state.valid then
    state
  else if state.inString then
    if state.escaped then
      { state with escaped := false }
    else if character == '\\' then
      { state with escaped := true }
    else if character == '"' then
      { state with inString := false }
    else
      state
  else if character == '"' then
    { state with inString := true }
  else if character == '{' || character == '[' then
    let depth := state.depth + 1
    {
      state with
      depth
      valid := decide (depth ≤ maximumSummaryJsonNesting)
    }
  else if character == '}' || character == ']' then
    if state.depth = 0 then
      { state with valid := false }
    else
      { state with depth := state.depth - 1 }
  else
    state

def summaryJsonNestingWithinLimit (text : String) : Bool :=
  let state := text.foldl scanJsonCharacter {}
  state.valid && !state.inString && state.depth == 0

private def canonicalSummaryJson (summary : ExecutionSummary) : Json :=
  Json.mkObj [
    ("algorithm_id", toJson summaryAlgorithmId),
    ("all_character_fft_executed", .bool summary.allCharacterFFTExecuted),
    ("canonical_descriptor_input_bytes", toJson (0 : Nat)),
    ("classification", toJson summaryClassification),
    ("completed_l_zero_state_validated",
      .bool summary.completedLZeroStateValidated),
    ("elapsed_kernel_nanoseconds", toJson summary.elapsedKernelNanoseconds),
    ("external_atom_discharged", .bool summary.externalAtomDischarged),
    ("input_artifact_sha256", toJson summary.inputArtifactSHA256),
    ("lane_index", toJson summary.laneIndex),
    ("lattice_h2d_upload_count", toJson (1 : Nat)),
    ("output_stream_sha256", toJson summary.outputStreamSHA256),
    ("recovery_seed_artifact_sha256",
      toJson summary.recoverySeedArtifactSHA256),
    ("row_bindings_sha256", toJson summary.rowBindingsSHA256),
    ("row_count", toJson summary.rowCount),
    ("row_payload_h2d_bytes", toJson summary.rowPayloadH2DBytes),
    ("schema", toJson summarySchema),
    ("schema_version", toJson tmajorFormatVersion),
    ("sidecar_source_sha256", toJson summary.sidecarSourceSHA256),
    ("source_contract_sha256", toJson summary.sourceContractSHA256),
    ("source_scale_run", .bool summary.sourceScaleRun),
    ("spool_receipt_sha256", toJson summary.spoolReceiptSHA256),
    ("target_count", toJson summary.targetCount),
    ("transcendental_device_calls", toJson (0 : Nat)),
    ("trusted_execution_attested", .bool summary.trustedExecutionAttested),
    ("value_count", toJson summary.valueCount),
    ("zero_completeness_claimed", .bool summary.zeroCompletenessClaimed)
  ]

def canonicalSummaryBytes (summary : ExecutionSummary) : ByteArray :=
  ((canonicalSummaryJson summary).compress ++ "\n").toUTF8

private def parseSummaryJson (json : Json) :
    Except String ExecutionSummary := do
  exactFields json summaryFieldNames
  let allCharacterFFTExecuted ←
    boolField json "all_character_fft_executed"
  let completedLZeroStateValidated ←
    boolField json "completed_l_zero_state_validated"
  let externalAtomDischarged ←
    boolField json "external_atom_discharged"
  let sourceScaleRun ← boolField json "source_scale_run"
  let trustedExecutionAttested ←
    boolField json "trusted_execution_attested"
  let zeroCompletenessClaimed ←
    boolField json "zero_completeness_claimed"
  if (← stringField json "algorithm_id") != summaryAlgorithmId ||
      (← stringField json "classification") != summaryClassification ||
      (← stringField json "schema") != summarySchema ||
      (← natField json "schema_version") != tmajorFormatVersion ||
      (← natField json "lattice_h2d_upload_count") != 1 ||
      (← natField json "canonical_descriptor_input_bytes") != 0 ||
      (← natField json "transcendental_device_calls") != 0 ||
      allCharacterFFTExecuted ||
      completedLZeroStateValidated ||
      externalAtomDischarged ||
      sourceScaleRun ||
      trustedExecutionAttested ||
      zeroCompletenessClaimed then
    throw "execution summary identity or completion flags differ"
  let elapsedKernelNanoseconds ← natField json "elapsed_kernel_nanoseconds"
  let inputArtifactSHA256 ← stringField json "input_artifact_sha256"
  let laneIndex ← natField json "lane_index"
  let outputStreamSHA256 ← stringField json "output_stream_sha256"
  let recoverySeedArtifactSHA256 ←
    stringField json "recovery_seed_artifact_sha256"
  let rowBindingsSHA256 ← stringField json "row_bindings_sha256"
  let rowCount ← natField json "row_count"
  let rowPayloadH2DBytes ← natField json "row_payload_h2d_bytes"
  let sidecarSourceSHA256 ← stringField json "sidecar_source_sha256"
  let sourceContractSHA256 ← stringField json "source_contract_sha256"
  let spoolReceiptSHA256 ← stringField json "spool_receipt_sha256"
  let targetCount ← natField json "target_count"
  let valueCount ← natField json "value_count"
  let summary : ExecutionSummary := {
    allCharacterFFTExecuted
    completedLZeroStateValidated
    elapsedKernelNanoseconds
    externalAtomDischarged
    inputArtifactSHA256
    laneIndex
    outputStreamSHA256
    recoverySeedArtifactSHA256
    rowBindingsSHA256
    rowCount
    rowPayloadH2DBytes
    sidecarSourceSHA256
    sourceContractSHA256
    sourceScaleRun
    spoolReceiptSHA256
    targetCount
    trustedExecutionAttested
    valueCount
    zeroCompletenessClaimed
  }
  if 2 ^ 64 - 1 < elapsedKernelNanoseconds ||
      2 ^ 32 - 1 < laneIndex ||
      rowCount = 0 || maximumRows < rowCount ||
      2 ^ 64 - 1 < rowPayloadH2DBytes ||
      targetCount = 0 || maximumModulus - minimumModulus + 1 < targetCount ||
      valueCount = 0 || 2 ^ 64 - 1 < valueCount ||
      !isLowerSHA256 inputArtifactSHA256 ||
      !isLowerSHA256 outputStreamSHA256 ||
      !isLowerSHA256 recoverySeedArtifactSHA256 ||
      !isLowerSHA256 rowBindingsSHA256 ||
      !isLowerSHA256 sidecarSourceSHA256 ||
      !isLowerSHA256 sourceContractSHA256 ||
      !isLowerSHA256 spoolReceiptSHA256 then
    throw "execution summary ranges or digests differ"
  pure summary

private def parseExecutionSummaryCertified
    (raw : ByteArray) :
    Option { summary : ExecutionSummary //
      canonicalSummaryBytes summary = raw } := do
  if 0 < raw.size && raw.size ≤ maximumSummaryBytes then pure () else none
  let text ← String.fromUTF8? raw
  if summaryJsonNestingWithinLimit text then pure () else none
  let json ← (Json.parse text).toOption
  let summary ← (parseSummaryJson json).toOption
  if hcanonical : canonicalSummaryBytes summary = raw then
    pure ⟨summary, hcanonical⟩
  else
    none

def parseExecutionSummary (raw : ByteArray) : Option ExecutionSummary :=
  (parseExecutionSummaryCertified raw).map Subtype.val

/-! ## Cross-artifact bundle checker -/

structure Bundle where
  input : InputArtifact
  output : OutputArtifact
  seed : SeedArtifact
  summary : ExecutionSummary
  deriving DecidableEq

def Bundle.IsValid
    (inputRaw outputRaw seedRaw : ByteArray) (bundle : Bundle) : Prop :=
  bundle.input.header.sidecarMode = 1 ∧
    bundle.summary.IsComponentOnly ∧
    SHA256.digestByteArray inputRaw = bundle.summary.inputArtifactSHA256 ∧
    SHA256.digestByteArray outputRaw = bundle.summary.outputStreamSHA256 ∧
    SHA256.digestByteArray seedRaw =
      bundle.summary.recoverySeedArtifactSHA256 ∧
    byteArrayLowerHex bundle.input.header.seedArtifactSHA256 =
      bundle.summary.recoverySeedArtifactSHA256 ∧
    bundle.seed.header.xStop ≥
      (sourceM + 1) * bundle.input.header.qStop - 1 ∧
    bundle.summary.laneIndex = bundle.input.header.laneIndex ∧
    bundle.summary.rowCount = bundle.input.header.rowCount ∧
    bundle.summary.rowPayloadH2DBytes =
      bundle.input.header.rowCount * rowPayloadBytes ∧
    bundle.summary.targetCount = bundle.input.header.targetCount ∧
    bundle.summary.valueCount = bundle.input.footer.valueCount ∧
    bundle.summary.sourceContractSHA256 =
      byteArrayLowerHex bundle.input.header.sourceContractSHA256 ∧
    bundle.summary.spoolReceiptSHA256 =
      byteArrayLowerHex bundle.input.header.spoolReceiptSHA256 ∧
    bundle.summary.rowBindingsSHA256 =
      byteArrayLowerHex bundle.input.header.rowBindingsSHA256 ∧
    bundle.summary.sidecarSourceSHA256 =
      byteArrayLowerHex bundle.input.header.sidecarSourceSHA256

instance (inputRaw outputRaw seedRaw : ByteArray) (bundle : Bundle) :
    Decidable (bundle.IsValid inputRaw outputRaw seedRaw) := by
  unfold Bundle.IsValid
  infer_instance

def checkBundle
    (inputRaw outputRaw seedRaw summaryRaw : ByteArray) : Bool :=
  match parseInputArtifact inputRaw with
  | none => false
  | some input =>
      match parseOutputArtifact input outputRaw with
      | none => false
      | some output =>
          match parseSeedArtifact seedRaw with
          | none => false
          | some seed =>
              match parseExecutionSummary summaryRaw with
              | none => false
              | some summary =>
                  decide (({ input, output, seed, summary } : Bundle).IsValid
                    inputRaw outputRaw seedRaw)

def ValidatedBundle
    (inputRaw outputRaw seedRaw summaryRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    parseInputArtifact inputRaw = some bundle.input ∧
    parseOutputArtifact bundle.input outputRaw = some bundle.output ∧
    parseSeedArtifact seedRaw = some bundle.seed ∧
    parseExecutionSummary summaryRaw = some bundle.summary ∧
    bundle.IsValid inputRaw outputRaw seedRaw

theorem checkBundle_sound
    {inputRaw outputRaw seedRaw summaryRaw : ByteArray}
    (hcheck : checkBundle inputRaw outputRaw seedRaw summaryRaw = true) :
    ValidatedBundle inputRaw outputRaw seedRaw summaryRaw := by
  unfold checkBundle at hcheck
  cases hinput : parseInputArtifact inputRaw with
  | none => simp [hinput] at hcheck
  | some input =>
      cases houtput : parseOutputArtifact input outputRaw with
      | none => simp [hinput, houtput] at hcheck
      | some output =>
          cases hseed : parseSeedArtifact seedRaw with
          | none => simp [hinput, houtput, hseed] at hcheck
          | some seed =>
              cases hsummary : parseExecutionSummary summaryRaw with
              | none =>
                  simp [hinput, houtput, hseed, hsummary] at hcheck
              | some summary =>
                  refine ⟨{ input, output, seed, summary },
                    hinput, houtput, hseed, hsummary, ?_⟩
                  simpa [hinput, houtput, hseed, hsummary] using hcheck

/-! A structural bundle is intentionally not self-authenticating: replacing
all four files together would preserve its internal equalities.  The signed
receipt or release manifest supplies the following immutable pins. -/

structure ExternalPins where
  inputArtifactSHA256 : String
  outputStreamSHA256 : String
  seedArtifactSHA256 : String
  summarySHA256 : String
  sourceContractSHA256 : String
  spoolReceiptSHA256 : String
  rowBindingsSHA256 : String
  seedReplaySHA256 : String
  sidecarSourceSHA256 : String
  deriving DecidableEq

def ExternalPins.IsValid (pins : ExternalPins) : Prop :=
  isLowerSHA256 pins.inputArtifactSHA256 = true ∧
    isLowerSHA256 pins.outputStreamSHA256 = true ∧
    isLowerSHA256 pins.seedArtifactSHA256 = true ∧
    isLowerSHA256 pins.summarySHA256 = true ∧
    isLowerSHA256 pins.sourceContractSHA256 = true ∧
    isLowerSHA256 pins.spoolReceiptSHA256 = true ∧
    isLowerSHA256 pins.rowBindingsSHA256 = true ∧
    isLowerSHA256 pins.seedReplaySHA256 = true ∧
    isLowerSHA256 pins.sidecarSourceSHA256 = true

instance (pins : ExternalPins) : Decidable pins.IsValid := by
  unfold ExternalPins.IsValid
  infer_instance

def Bundle.MatchesPins
    (pins : ExternalPins)
    (inputRaw outputRaw seedRaw summaryRaw : ByteArray)
    (bundle : Bundle) : Prop :=
  pins.IsValid ∧
    SHA256.digestByteArray inputRaw = pins.inputArtifactSHA256 ∧
    SHA256.digestByteArray outputRaw = pins.outputStreamSHA256 ∧
    SHA256.digestByteArray seedRaw = pins.seedArtifactSHA256 ∧
    SHA256.digestByteArray summaryRaw = pins.summarySHA256 ∧
    byteArrayLowerHex bundle.input.header.sourceContractSHA256 =
      pins.sourceContractSHA256 ∧
    byteArrayLowerHex bundle.input.header.spoolReceiptSHA256 =
      pins.spoolReceiptSHA256 ∧
    byteArrayLowerHex bundle.input.header.rowBindingsSHA256 =
      pins.rowBindingsSHA256 ∧
    byteArrayLowerHex bundle.input.header.seedArtifactSHA256 =
      pins.seedArtifactSHA256 ∧
    byteArrayLowerHex bundle.input.header.seedReplaySHA256 =
      pins.seedReplaySHA256 ∧
    byteArrayLowerHex bundle.input.header.sidecarSourceSHA256 =
      pins.sidecarSourceSHA256 ∧
    bundle.summary.inputArtifactSHA256 = pins.inputArtifactSHA256 ∧
    bundle.summary.outputStreamSHA256 = pins.outputStreamSHA256 ∧
    bundle.summary.recoverySeedArtifactSHA256 = pins.seedArtifactSHA256

instance (pins : ExternalPins)
    (inputRaw outputRaw seedRaw summaryRaw : ByteArray) (bundle : Bundle) :
    Decidable (bundle.MatchesPins pins inputRaw outputRaw seedRaw summaryRaw) := by
  unfold Bundle.MatchesPins
  infer_instance

def checkPinnedBundle
    (pins : ExternalPins)
    (inputRaw outputRaw seedRaw summaryRaw : ByteArray) : Bool :=
  match parseInputArtifact inputRaw with
  | none => false
  | some input =>
      match parseOutputArtifact input outputRaw with
      | none => false
      | some output =>
          match parseSeedArtifact seedRaw with
          | none => false
          | some seed =>
              match parseExecutionSummary summaryRaw with
              | none => false
              | some summary =>
                  let bundle : Bundle := { input, output, seed, summary }
                  decide (bundle.IsValid inputRaw outputRaw seedRaw ∧
                    bundle.MatchesPins pins inputRaw outputRaw seedRaw
                      summaryRaw)

def ValidatedPinnedBundle
    (pins : ExternalPins)
    (inputRaw outputRaw seedRaw summaryRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    parseInputArtifact inputRaw = some bundle.input ∧
    parseOutputArtifact bundle.input outputRaw = some bundle.output ∧
    parseSeedArtifact seedRaw = some bundle.seed ∧
    parseExecutionSummary summaryRaw = some bundle.summary ∧
    bundle.IsValid inputRaw outputRaw seedRaw ∧
    bundle.MatchesPins pins inputRaw outputRaw seedRaw summaryRaw

theorem checkPinnedBundle_sound
    {pins : ExternalPins}
    {inputRaw outputRaw seedRaw summaryRaw : ByteArray}
    (hcheck :
      checkPinnedBundle pins inputRaw outputRaw seedRaw summaryRaw = true) :
    ValidatedPinnedBundle pins inputRaw outputRaw seedRaw summaryRaw := by
  unfold checkPinnedBundle at hcheck
  cases hinput : parseInputArtifact inputRaw with
  | none => simp [hinput] at hcheck
  | some input =>
      cases houtput : parseOutputArtifact input outputRaw with
      | none => simp [hinput, houtput] at hcheck
      | some output =>
          cases hseed : parseSeedArtifact seedRaw with
          | none => simp [hinput, houtput, hseed] at hcheck
          | some seed =>
              cases hsummary : parseExecutionSummary summaryRaw with
              | none =>
                  simp [hinput, houtput, hseed, hsummary] at hcheck
              | some summary =>
                  refine ⟨{ input, output, seed, summary },
                    hinput, houtput, hseed, hsummary, ?_⟩
                  simpa [hinput, houtput, hseed, hsummary] using hcheck

theorem checkPinnedBundle_componentOnly
    {pins : ExternalPins}
    {inputRaw outputRaw seedRaw summaryRaw : ByteArray}
    (hcheck :
      checkPinnedBundle pins inputRaw outputRaw seedRaw summaryRaw = true) :
    ∃ summary : ExecutionSummary,
      parseExecutionSummary summaryRaw = some summary ∧
      summary.IsComponentOnly := by
  rcases checkPinnedBundle_sound hcheck with
    ⟨bundle, _, _, _, hsummary, hvalid, _⟩
  exact ⟨bundle.summary, hsummary, hvalid.2.1⟩

theorem parseBlockHeader_size
    {raw : ByteArray} {header : BlockHeader}
    (hparse : parseBlockHeader raw = some header) :
    raw.size = blockHeaderBytes := by
  unfold parseBlockHeader at hparse
  split at hparse
  · assumption
  · contradiction

theorem parseExecutionSummary_canonical
    {raw : ByteArray} {summary : ExecutionSummary}
    (hparse : parseExecutionSummary raw = some summary) :
    canonicalSummaryBytes summary = raw := by
  unfold parseExecutionSummary at hparse
  cases hcertified : parseExecutionSummaryCertified raw with
  | none => simp [hcertified] at hparse
  | some certified =>
      simp [hcertified] at hparse
      cases hparse
      exact certified.property

theorem checkBundle_rejects_claimedAnalyticCompletion
    {inputRaw outputRaw seedRaw summaryRaw : ByteArray}
    (hcheck : checkBundle inputRaw outputRaw seedRaw summaryRaw = true) :
    ∃ summary,
      parseExecutionSummary summaryRaw = some summary ∧
      summary.IsComponentOnly ∧
      canonicalSummaryBytes summary = summaryRaw := by
  rcases checkBundle_sound hcheck with
    ⟨bundle, _, _, _, hsummary, hvalid⟩
  exact ⟨bundle.summary, hsummary, hvalid.2.1,
    parseExecutionSummary_canonical hsummary⟩

end SparkInterval.Dirichlet.TMajorRowResidentWire
