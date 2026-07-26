/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.TernaryGoldbach.A7BoundaryCertificate

/-!
# Total compact-wire parser for the finite CH25 Lemma A.7 transcript

`TGA7WIR1` is a fixed-width binary projection of the retained JSON transcript.
Each 88-byte record preserves exactly the seven semantic leaf fields:

* edge ID, dyadic depth, and dyadic index;
* the positive norm-square mantissa and signed exponent; and
* the positive zeta-lower-bound mantissa and signed exponent.

The 144-byte header commits to the immutable JSON transcript, its canonical
seven-field leaf array, and the complete binary record payload.  The retained
entry point additionally pins the full wire hash.  Parsing is total and
requires exact length, so truncation and suffixes fail closed.  Accepted bytes
feed the existing exact `Certificate.check`, which proves four gap-free edge
covers, positivity, and the strict rational squared-norm inequality.

This file does **not** prove that FLINT/Arb evaluates Mathlib's zeta,
derivative, or `rawG`.  The final source claim remains explicitly conditional
on `AnalyticRealization`.  It also makes no attestation, production-run,
compiler, or architecture claim.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.TernaryGoldbach.A7BoundaryWire

open SparkInterval.Certificate
open A7BoundaryCertificate

/-! ## Exact layout and retained-source pins -/

def formatVersion : Nat := 1
def headerBytes : Nat := 144
def recordBytes : Nat := 88
def maximumLeaves : Nat := 2_000_000
def maximumDepth : Nat := 64
def maximumTranscriptBytes : Nat := 64 * 1024 * 1024

def wireMagic : List UInt8 :=
  [0x54, 0x47, 0x41, 0x37, 0x57, 0x49, 0x52, 0x31]

def retainedTranscriptSHA256 : String :=
  "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"

def retainedTranscriptSizeBytes : Nat := 1_494_999
def retainedLeafCount : Nat := 16_191
def retainedMaxDepth : Nat := 24

def retainedLeavesSHA256 : String :=
  "abac27f61cb8ce53f649cb0c2111c123c761a37793a1bc536033981c215cabef"

def retainedPayloadSHA256 : String :=
  "f2893e9488df7353c31f7d647948b697eb2c88f331b7ea4405c9e328f974148c"

def retainedWireSHA256 : String :=
  "1ea01e78e29143ecfef926faac7b788c2d4dc9dd6240b7d0b401e7f62fa9de4c"

/-! ## Bounded byte primitives -/

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

def readI32LE (raw : ByteArray) (offset : Nat) : Option Int := do
  let value ← readU32LE raw offset
  if value < 2 ^ 31 then
    pure (Int.ofNat value)
  else
    pure (Int.ofNat value - Int.ofNat (2 ^ 32))

def readNatBE (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat := do
  let bytes ← checkedSlice? raw offset width
  pure <| bytes.toList.foldl
    (fun value byte => value * 256 + byte.toNat) 0

def readDigest (raw : ByteArray) (offset : Nat) : Option ByteArray :=
  checkedSlice? raw offset 32

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

/-! ## Total parser -/

structure Header where
  maxDepth : Nat
  leafCount : Nat
  transcriptSizeBytes : Nat
  transcriptSHA256 : ByteArray
  leavesSHA256 : ByteArray
  payloadSHA256 : ByteArray
  deriving DecidableEq

private def parseHeader (raw : ByteArray) : Option Header := do
  let magic ← checkedSlice? raw 0 8
  if magic = wireMagic.toByteArray then pure () else none
  let version ← readU32LE raw 8
  if version = formatVersion then pure () else none
  let encodedHeaderBytes ← readU32LE raw 12
  if encodedHeaderBytes = headerBytes then pure () else none
  let encodedRecordBytes ← readU32LE raw 16
  if encodedRecordBytes = recordBytes then pure () else none
  let reserved ← readU32LE raw 20
  if reserved = 0 then pure () else none
  let maxDepth ← readU32LE raw 24
  if maxDepth ≤ maximumDepth then pure () else none
  let leafCount ← readU32LE raw 28
  if 4 ≤ leafCount && leafCount ≤ maximumLeaves then pure () else none
  let transcriptSizeBytes ← readU64LE raw 32
  if 0 < transcriptSizeBytes &&
      transcriptSizeBytes ≤ maximumTranscriptBytes then
    pure ()
  else
    none
  let transcriptSHA256 ← readDigest raw 40
  let leavesSHA256 ← readDigest raw 72
  let payloadSHA256 ← readDigest raw 104
  if digestNonzero transcriptSHA256 &&
      digestNonzero leavesSHA256 && digestNonzero payloadSHA256 then
    pure ()
  else
    none
  let reservedTail ← readU64LE raw 136
  if reservedTail = 0 then pure () else none
  pure {
    maxDepth
    leafCount
    transcriptSizeBytes
    transcriptSHA256
    leavesSHA256
    payloadSHA256
  }

private def parseLeafAt
    (raw : ByteArray) (maxDepth offset : Nat) : Option DyadicLeaf := do
  let edgeId ← readU32LE raw offset
  if edgeId < 4 then pure () else none
  let depth ← readU32LE raw (offset + 4)
  if depth ≤ maxDepth then pure () else none
  let index ← readU64LE raw (offset + 8)
  if index < 2 ^ depth then pure () else none
  let normSqUpperMantissa ← readNatBE 32 raw (offset + 16)
  if 0 < normSqUpperMantissa then pure () else none
  let normSqUpperExponent ← readI32LE raw (offset + 48)
  if (-16384 : Int) ≤ normSqUpperExponent &&
      normSqUpperExponent ≤ 16384 then
    pure ()
  else
    none
  let zetaAbsLowerMantissa ← readNatBE 32 raw (offset + 52)
  if 0 < zetaAbsLowerMantissa then pure () else none
  let zetaAbsLowerExponent ← readI32LE raw (offset + 84)
  if (-16384 : Int) ≤ zetaAbsLowerExponent &&
      zetaAbsLowerExponent ≤ 16384 then
    pure ()
  else
    none
  pure {
    edgeId
    depth
    index
    normSqUpperMantissa
    normSqUpperExponent
    zetaAbsLowerMantissa
    zetaAbsLowerExponent
  }

private def parseLeaves
    (raw : ByteArray) (maxDepth offset : Nat) :
    Nat → Option (List DyadicLeaf)
  | 0 => some []
  | count + 1 => do
      let leaf ← parseLeafAt raw maxDepth offset
      let leaves ← parseLeaves raw maxDepth (offset + recordBytes) count
      pure (leaf :: leaves)

structure Artifact where
  header : Header
  certificate : Certificate
  wireSize : Nat
  deriving DecidableEq

private def parseSized (raw : ByteArray) : Option Artifact := do
  let header ← parseHeader raw
  let expectedBytes := headerBytes + header.leafCount * recordBytes
  if raw.size = expectedBytes then pure () else none
  let payload ← checkedSlice? raw headerBytes (header.leafCount * recordBytes)
  if SHA256.digestByteArray payload =
      byteArrayLowerHex header.payloadSHA256 then
    pure ()
  else
    none
  let leaves ← parseLeaves raw header.maxDepth headerBytes header.leafCount
  pure {
    header
    certificate := {
      maxDepth := header.maxDepth
      leaves
    }
    wireSize := raw.size
  }

/-- Total parser for one exact `TGA7WIR1` artifact.  All recursion is bounded
by the checked leaf count, and exact length excludes truncation and suffixes. -/
def parse (raw : ByteArray) : Option Artifact :=
  if raw.size < headerBytes then none else parseSized raw

namespace Artifact

/-- Exact finite meaning checked from one parsed binary artifact. -/
def IsAccepted (raw : ByteArray) (artifact : Artifact) : Prop :=
  artifact.wireSize = raw.size ∧
    artifact.wireSize =
      headerBytes + artifact.header.leafCount * recordBytes ∧
    artifact.certificate.check = true

instance (raw : ByteArray) (artifact : Artifact) :
    Decidable (artifact.IsAccepted raw) := by
  unfold IsAccepted
  infer_instance

def check (raw : ByteArray) (artifact : Artifact) : Bool :=
  decide (artifact.wireSize = raw.size) &&
    decide (artifact.wireSize =
      headerBytes + artifact.header.leafCount * recordBytes) &&
    artifact.certificate.check

@[simp] theorem check_eq_true (raw : ByteArray) (artifact : Artifact) :
    artifact.check raw = true ↔ artifact.IsAccepted raw := by
  simp [check, IsAccepted, and_assoc]

end Artifact

/-- A parsed wire whose complete decoded certificate passes the ordinary-Lean
finite checker. -/
def ValidatedBytes (raw : ByteArray) : Prop :=
  ∃ artifact : Artifact,
    parse raw = some artifact ∧ artifact.IsAccepted raw

/-- Total finite checker for arbitrary compact A.7 wire bytes. -/
def checkBytes (raw : ByteArray) : Bool :=
  match parse raw with
  | none => false
  | some artifact => artifact.check raw

theorem checkBytes_sound {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    ValidatedBytes raw := by
  unfold checkBytes at hcheck
  cases hparse : parse raw with
  | none =>
      simp [hparse] at hcheck
  | some artifact =>
      exact ⟨artifact, hparse, (Artifact.check_eq_true raw artifact).mp (by
        simpa [hparse] using hcheck)⟩

/-- Finite acceptance exposes the existing proved coverage/arithmetic
meaning.  This theorem has no analytic realization premise because it stops
at `Certificate.Accepted`. -/
theorem acceptedCertificate_of_checkBytes {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    ∃ artifact : Artifact,
      parse raw = some artifact ∧ artifact.certificate.Accepted := by
  rcases checkBytes_sound hcheck with ⟨artifact, hparse, haccepted⟩
  exact
    ⟨artifact, hparse,
      Certificate.accepted_of_check_eq_true haccepted.2.2⟩

/-- Accepted bytes have exactly the formulaic wire length.  In particular,
the checked language contains neither truncated records nor an ignored
suffix. -/
theorem exactLength_of_checkBytes {raw : ByteArray}
    (hcheck : checkBytes raw = true) :
    ∃ artifact : Artifact,
      parse raw = some artifact ∧
        raw.size =
          headerBytes + artifact.header.leafCount * recordBytes := by
  rcases checkBytes_sound hcheck with ⟨artifact, hparse, haccepted⟩
  exact ⟨artifact, hparse, haccepted.1 ▸ haccepted.2.1⟩

/-! ## Pinned retained-transcript entry point -/

def RetainedPins (raw : ByteArray) (artifact : Artifact) : Prop :=
  artifact.header.maxDepth = retainedMaxDepth ∧
    artifact.header.leafCount = retainedLeafCount ∧
    artifact.header.transcriptSizeBytes = retainedTranscriptSizeBytes ∧
    byteArrayLowerHex artifact.header.transcriptSHA256 =
      retainedTranscriptSHA256 ∧
    byteArrayLowerHex artifact.header.leavesSHA256 =
      retainedLeavesSHA256 ∧
    byteArrayLowerHex artifact.header.payloadSHA256 =
      retainedPayloadSHA256 ∧
    SHA256.digestByteArray raw = retainedWireSHA256

instance (raw : ByteArray) (artifact : Artifact) :
    Decidable (RetainedPins raw artifact) := by
  unfold RetainedPins
  infer_instance

def retainedPinsCheck (raw : ByteArray) (artifact : Artifact) : Bool :=
  decide (RetainedPins raw artifact)

@[simp] theorem retainedPinsCheck_eq_true
    (raw : ByteArray) (artifact : Artifact) :
    retainedPinsCheck raw artifact = true ↔ RetainedPins raw artifact := by
  simp [retainedPinsCheck]

/-- Exact retained-source checker.  Besides all finite certificate checks it
pins the source JSON identity, canonical leaf-array identity, binary payload,
and the complete binary wire. -/
def checkRetainedBytes (raw : ByteArray) : Bool :=
  match parse raw with
  | none => false
  | some artifact =>
      artifact.check raw && retainedPinsCheck raw artifact

def ValidatedRetainedBytes (raw : ByteArray) : Prop :=
  ∃ artifact : Artifact,
    parse raw = some artifact ∧
      artifact.IsAccepted raw ∧ RetainedPins raw artifact

theorem checkRetainedBytes_sound {raw : ByteArray}
    (hcheck : checkRetainedBytes raw = true) :
    ValidatedRetainedBytes raw := by
  unfold checkRetainedBytes at hcheck
  cases hparse : parse raw with
  | none =>
      simp [hparse] at hcheck
  | some artifact =>
      have hpairs :
          artifact.check raw = true ∧
            retainedPinsCheck raw artifact = true := by
        simp only [hparse] at hcheck
        exact Bool.and_eq_true_iff.mp hcheck
      exact
        ⟨artifact, hparse,
          (Artifact.check_eq_true raw artifact).mp hpairs.1,
          (retainedPinsCheck_eq_true raw artifact).mp hpairs.2⟩

/-- The precise remaining boundary: a checked retained finite wire reaches the
CH25 source claim only after an explicit FLINT/Arb-to-Mathlib realization is
provided for its decoded certificate. -/
theorem sourceClaim_of_checked_retained_wire
    {raw : ByteArray} {artifact : Artifact}
    (hparse : parse raw = some artifact)
    (hcheck : checkRetainedBytes raw = true)
    (realization : AnalyticRealization artifact.certificate) :
    A7BoundarySourceSemantics.SourceClaim := by
  unfold checkRetainedBytes at hcheck
  rw [hparse] at hcheck
  have hcertificate : artifact.certificate.check = true := by
    have hfinite : artifact.check raw = true :=
      (Bool.and_eq_true_iff.mp hcheck).1
    exact (Artifact.check_eq_true raw artifact).mp hfinite |>.2.2
  exact sourceClaim_of_checked_certificate hcertificate realization

end SparkInterval.TernaryGoldbach.A7BoundaryWire
