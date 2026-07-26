/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDisk
import SparkInterval.Certificate.SHA256

/-!
# Total wire checker for completed Dirichlet-factor artifacts

This module is the architecture-independent Lean boundary for the three
completed-factor recurrence inputs:

* `TGDCGAM1`, parity-major gamma disks;
* `TGDCSTP1`, conductor-step disks in execution order; and
* `TGDCCPB1`, direct conductor checkpoints for one resident phase.

The parser reads only `ByteArray`, `Nat`, and exact binary64 words.  A disk is
accepted only when all three words decode to exact finite rationals and its
radius is nonnegative.  No Lean `Float`, FFI, `native_decide`, or producer
execution is used.

Classification is represented by an inductive type.  Full-source gamma and
step artifacts must have the complete source geometry, while full-source
checkpoint artifacts must match one of the ten pinned resident phases,
including its exact record and checkpoint totals.  The separate bounded
bundle checker requires `.bounded` in all three headers.  Consequently a
bounded fixture cannot acquire full-source meaning merely by having plausible
dimensions.

The bundle checker also compares the exact q/sample roster, schedule fields,
factor convention, and the checkpoint file's gamma/step digests against the
actual supplied bytes.  `checkPinnedBoundedBundle` additionally binds all
three complete artifacts.  This last layer is necessary: internal hash links
alone do not prevent replacing a gamma artifact and repairing its link in a
new checkpoint artifact.

Acceptance proves only finite wire well-formedness and these byte identities.
It does not prove Arb containment, a CUDA/CPU refinement, source execution,
attestation, SHA-256 collision resistance, or discharge of an external
analytic atom.
-/

set_option autoImplicit false
set_option maxRecDepth 5000000

namespace SparkInterval.Dirichlet.CompletedFactorWire

open SparkInterval.Certificate
open SparkInterval.Certified

/-! ## Exact format constants -/

def formatVersion : Nat := 1
def boundedClassificationCode : Nat := 0
def fullSourceClassificationCode : Nat := 1
def sourceQStart : Nat := 10_001
def sourceQStop : Nat := 400_000
def sourceQCount : Nat := 292_500
def sourceTIndexStop : Nat := 127_988
def sourceTDenominator : Nat := 64
def sourceTStepNumerator : Nat := 5
def primitiveModulusRosterVersion : Nat := 2
def defaultCheckpointSpan : Nat := 4_096

def diskBytes : Nat := 24
def gammaHeaderBytes : Nat := 128
def stepHeaderBytes : Nat := 144
def checkpointHeaderBytes : Nat := 208
def checkpointRecordHeaderBytes : Nat := 16

def maximumCheckpointRecords : Nat := sourceQStop
def maximumCheckpoints : Nat := 4_000_000

def gammaMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x43, 0x47, 0x41, 0x4d, 0x31]

def stepMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x43, 0x53, 0x54, 0x50, 0x31]

def checkpointMagic : List UInt8 :=
  [0x54, 0x47, 0x44, 0x43, 0x43, 0x50, 0x42, 0x31]

/-- Exact ASCII convention whose digest is embedded in both factor files. -/
def factorConvention : String :=
  "TG_COMPLETED_FACTOR_V1|t=5j/64|" ++
    "gamma=Gamma((1+2a)/4+it/2)*exp(pi*t/4)|" ++
    "conductor=exp(i*t/2*log(q/pi))|" ++
    "step=exp(i*5/128*log(q/pi))|parity-major|" ++
    "one-conductor-step-application-per-sample"

/-- SHA-256 bytes of the exact `TG_COMPLETED_FACTOR_V1` convention string. -/
def factorConventionSHA256 : ByteArray :=
  [0xd4, 0xa3, 0x37, 0xca, 0xef, 0x77, 0x22, 0xd1,
    0x45, 0x36, 0x7b, 0xa2, 0xf8, 0x37, 0x03, 0x53,
    0xc3, 0x3f, 0x1f, 0xd6, 0xc2, 0xd1, 0x64, 0xe3,
    0xbc, 0x71, 0xaf, 0x93, 0x74, 0x73, 0x19, 0x72].toByteArray

/-- Complete canonical `TGDQORD1` file digest used by the source service. -/
def pinnedSourceScheduleManifestSHA256 : ByteArray :=
  [0xa5, 0xae, 0x1a, 0xf2, 0xe4, 0xa9, 0xe9, 0x44,
    0xcc, 0xef, 0x55, 0x9e, 0x16, 0x9a, 0x13, 0xcd,
    0x74, 0xf2, 0x1c, 0x22, 0x0e, 0xd8, 0x82, 0x95,
    0x0e, 0xcd, 0x44, 0x91, 0xcb, 0xf1, 0x3e, 0x93].toByteArray

/-- Execution-order digest inside the canonical full-source q manifest. -/
def pinnedSourceExecutionOrderSHA256 : ByteArray :=
  [0x34, 0xd6, 0x33, 0xf0, 0xe3, 0xed, 0x0d, 0x9c,
    0xf3, 0xf6, 0x84, 0x19, 0x9f, 0xd2, 0x02, 0x4a,
    0x82, 0xe8, 0x02, 0x7b, 0x4f, 0xc6, 0x73, 0x3e,
    0x48, 0x04, 0x0a, 0x36, 0x00, 0x7f, 0x3a, 0xcd].toByteArray

inductive Classification where
  | bounded
  | fullSource
  deriving Repr, DecidableEq, BEq

def Classification.code : Classification → Nat
  | .bounded => boundedClassificationCode
  | .fullSource => fullSourceClassificationCode

def decodeClassification : Nat → Option Classification
  | 0 => some .bounded
  | 1 => some .fullSource
  | _ => none

@[simp] theorem decodeClassification_code (classification : Classification) :
    decodeClassification classification.code = some classification := by
  cases classification <;> rfl

/-! ## Bounded byte and digest primitives -/

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

def digestSized (digest : ByteArray) : Prop :=
  digest.size = 32

instance (digest : ByteArray) : Decidable (digestSized digest) := by
  unfold digestSized
  infer_instance

def artifactDigestMatches (raw digest : ByteArray) : Prop :=
  digestSized digest ∧
    byteArrayLowerHex digest = SHA256.digestByteArray raw

instance (raw digest : ByteArray) :
    Decidable (artifactDigestMatches raw digest) := by
  unfold artifactDigestMatches
  infer_instance

def isLowerSHA256 (text : String) : Bool :=
  text.length = 64 &&
    text.toList.all fun character =>
      ('0' ≤ character && character ≤ '9') ||
        ('a' ≤ character && character ≤ 'f')

/-! ## Exact 24-byte disk rows -/

/-- The three exact binary64 words in one producer `Disk` row. -/
structure Disk where
  realBits : Nat
  imaginaryBits : Nat
  radiusBits : Nat
  deriving Repr, DecidableEq, BEq

namespace Disk

def raw (disk : Disk) : ComplexDisk.Raw :=
  ⟨disk.realBits, disk.imaginaryBits, disk.radiusBits⟩

def decode (disk : Disk) : Option ComplexDisk :=
  disk.raw.decode

/-- Exact finite-disk condition implemented by both producers.  Signed zero
is permitted for the radius because it decodes to rational zero. -/
def IsValid (disk : Disk) : Prop :=
  match disk.decode with
  | none => False
  | some value => 0 ≤ value.radius

instance (disk : Disk) : Decidable disk.IsValid := by
  unfold IsValid
  cases hdecode : disk.decode with
  | none => infer_instance
  | some value => infer_instance

def check (disk : Disk) : Bool :=
  decide disk.IsValid

@[simp] theorem check_eq_true (disk : Disk) :
    disk.check = true ↔ disk.IsValid := by
  simp [check]

theorem check_sound {disk : Disk} (hcheck : disk.check = true) :
    ∃ value : ComplexDisk,
      disk.decode = some value ∧ 0 ≤ value.radius := by
  have hvalid := (check_eq_true disk).mp hcheck
  unfold IsValid at hvalid
  cases hdecode : disk.decode with
  | none => simp [hdecode] at hvalid
  | some value =>
      rw [hdecode] at hvalid
      exact ⟨value, rfl, hvalid⟩

end Disk

def parseDiskAt (raw : ByteArray) (offset : Nat) : Option Disk :=
  match
      readU64LE raw offset,
      readU64LE raw (offset + 8),
      readU64LE raw (offset + 16) with
  | some realBits, some imaginaryBits, some radiusBits =>
      some { realBits, imaginaryBits, radiusBits }
  | _, _, _ => none

/-- Successful row parsing projects the three little-endian words exactly.
Finiteness and radius sign are checked once, at artifact validation. -/
theorem parseDiskAt_sound
    {raw : ByteArray} {offset : Nat} {disk : Disk}
    (hparse : parseDiskAt raw offset = some disk) :
    readU64LE raw offset = some disk.realBits ∧
      readU64LE raw (offset + 8) = some disk.imaginaryBits ∧
      readU64LE raw (offset + 16) = some disk.radiusBits := by
  unfold parseDiskAt at hparse
  cases hreal : readU64LE raw offset with
  | none => simp [hreal] at hparse
  | some realBits =>
      cases himaginary : readU64LE raw (offset + 8) with
      | none => simp [hreal, himaginary] at hparse
      | some imaginaryBits =>
          cases hradius : readU64LE raw (offset + 16) with
          | none => simp [hreal, himaginary, hradius] at hparse
          | some radiusBits =>
              simp only [hreal, himaginary, hradius] at hparse
              cases hparse
              exact ⟨rfl, rfl, rfl⟩

theorem checkedDiskAt_sound
    {raw : ByteArray} {offset : Nat} {disk : Disk}
    (_hparse : parseDiskAt raw offset = some disk)
    (hcheck : disk.check = true) :
    ∃ value : ComplexDisk,
      disk.decode = some value ∧ 0 ≤ value.radius := by
  exact Disk.check_sound hcheck

def parseDisks (raw : ByteArray) : Nat → Nat → Option (List Disk)
  | 0, _ => some []
  | count + 1, offset => do
      let disk ← parseDiskAt raw offset
      let disks ← parseDisks raw count (offset + diskBytes)
      pure (disk :: disks)

def disksValid (disks : List Disk) : Prop :=
  ∀ disk ∈ disks, disk.IsValid

instance (disks : List Disk) : Decidable (disksValid disks) := by
  unfold disksValid
  infer_instance

/-! ## Quasilinear distinctness check

The source phase roster can contain 292,500 moduli.  Evaluating
`List.Nodup` directly is quadratic because it performs a linear membership
test at every row.  Sorting natural keys and checking strict adjacent order
has the same proposition-level meaning and takes `O(n log n)` comparisons.
-/

def sortedNats (values : List Nat) : List Nat :=
  values.mergeSort fun left right => decide (left ≤ right)

def distinctNats (values : List Nat) : Prop :=
  (sortedNats values).SortedLT

instance (values : List Nat) : Decidable (distinctNats values) := by
  unfold distinctNats
  infer_instance

theorem distinctNats_iff_nodup (values : List Nat) :
    distinctNats values ↔ values.Nodup := by
  constructor
  · intro hstrict
    exact List.nodup_mergeSort.mp hstrict.nodup
  · intro hnodup
    exact List.sortedLE_mergeSort.sortedLT_of_nodup
      (List.nodup_mergeSort.mpr hnodup)

/-! ## Full-source phase roster -/

structure PinnedPhase where
  firstTIndex : Nat
  tIndexStopExclusive : Nat
  qCount : Nat
  checkpointCount : Nat
  tIndexRowCount : Nat
  deriving Repr, DecidableEq

def pinnedPhase? : Nat → Option PinnedPhase
  | 0 => some ⟨0, 768, 292_500, 292_500, 224_640_000⟩
  | 1 => some ⟨768, 1_600, 292_500, 292_500, 243_360_000⟩
  | 2 => some ⟨1_600, 2_368, 292_500, 292_500, 224_640_000⟩
  | 3 => some ⟨2_368, 3_200, 292_500, 292_500, 243_360_000⟩
  | 4 => some ⟨3_200, 4_032, 292_500, 292_500, 238_010_582⟩
  | 5 => some ⟨4_032, 5_568, 255_543, 255_543, 342_217_786⟩
  | 6 => some ⟨5_568, 9_600, 187_230, 187_230, 522_510_272⟩
  | 7 => some ⟨9_600, 49_088, 93_257, 359_018, 1_270_668_873⟩
  | 8 => some ⟨49_088, 88_512, 12_056, 71_741, 270_247_283⟩
  | 9 =>
      some
        ⟨88_512, sourceTIndexStop, 3_346, 15_871, 57_958_371⟩
  | _ => none

/-- Phase-schedule digest reconstructed by the source service from the exact
ordered active `(q,sampleCount)` roster. -/
def pinnedPhaseScheduleSHA256? : Nat → Option ByteArray
  | 0 =>
      some [0xb5, 0x25, 0x06, 0xf9, 0x2b, 0x9f, 0x63, 0x13,
        0x48, 0x6b, 0x50, 0x05, 0x20, 0x30, 0x55, 0xe7,
        0xe7, 0xb5, 0x8e, 0xdf, 0x87, 0x6d, 0x25, 0x73,
        0xbd, 0xaf, 0xb0, 0x08, 0x27, 0x9e, 0x09, 0x9a].toByteArray
  | 1 =>
      some [0xb9, 0x5a, 0x0b, 0x87, 0x71, 0x16, 0xa5, 0x4f,
        0x3a, 0x68, 0xea, 0x88, 0x7b, 0x16, 0xf7, 0x34,
        0x6c, 0x28, 0x7a, 0x02, 0xef, 0xc6, 0x23, 0xe1,
        0x26, 0xf1, 0x1e, 0x75, 0x92, 0x29, 0x1a, 0xe9].toByteArray
  | 2 =>
      some [0xb0, 0x75, 0xd5, 0xe9, 0x29, 0x59, 0x72, 0x40,
        0x61, 0x5e, 0xd8, 0x39, 0xbb, 0x13, 0xdf, 0xc8,
        0x36, 0xf4, 0x40, 0x91, 0x97, 0x6b, 0xe0, 0x47,
        0x5a, 0xcc, 0x85, 0xec, 0xcb, 0x39, 0x36, 0x39].toByteArray
  | 3 =>
      some [0xb8, 0x96, 0xa2, 0xc9, 0x53, 0x83, 0x17, 0xbb,
        0xcd, 0x7f, 0xb0, 0x8b, 0xd0, 0x90, 0xad, 0xc7,
        0xb5, 0xc4, 0xb1, 0x88, 0x5a, 0x97, 0x5a, 0x06,
        0x5c, 0x36, 0x28, 0x63, 0x27, 0xdd, 0x58, 0x8a].toByteArray
  | 4 =>
      some [0x1b, 0x66, 0xb2, 0x5c, 0x69, 0x2e, 0x95, 0xda,
        0x50, 0xd9, 0xa9, 0xcd, 0x8b, 0x5d, 0xcb, 0xf3,
        0xa0, 0xd9, 0x2d, 0x00, 0x4e, 0x24, 0xdf, 0x60,
        0xb2, 0x18, 0x20, 0x67, 0xaf, 0x39, 0x67, 0xa5].toByteArray
  | 5 =>
      some [0x1a, 0x95, 0xa8, 0x27, 0x51, 0xec, 0x50, 0x79,
        0x5e, 0x15, 0xc0, 0x73, 0x97, 0x97, 0x66, 0x6e,
        0x89, 0x53, 0xb6, 0xd3, 0x12, 0x7e, 0x56, 0xd8,
        0x66, 0x3e, 0x6f, 0xee, 0x86, 0x8d, 0x62, 0x28].toByteArray
  | 6 =>
      some [0xc7, 0x2a, 0x46, 0x35, 0x5a, 0x5f, 0x31, 0x6b,
        0x1f, 0x07, 0x73, 0x58, 0x89, 0xe8, 0xfd, 0x7a,
        0xbc, 0x89, 0xde, 0xf8, 0xfc, 0x5c, 0x6d, 0xae,
        0xe6, 0x6f, 0x79, 0xe7, 0x77, 0x7e, 0x19, 0x9d].toByteArray
  | 7 =>
      some [0x77, 0x89, 0x50, 0x57, 0xab, 0x76, 0xcd, 0x24,
        0x37, 0xdb, 0xed, 0x1f, 0xfe, 0x06, 0x53, 0x78,
        0x5e, 0x23, 0xef, 0x05, 0x6e, 0xf3, 0x2e, 0xa2,
        0xa2, 0xc9, 0x1f, 0x8d, 0x04, 0x64, 0xff, 0x41].toByteArray
  | 8 =>
      some [0x5b, 0x53, 0x24, 0x7c, 0x4c, 0x14, 0x6a, 0x59,
        0xb8, 0xcd, 0x1d, 0x2e, 0x5e, 0xf8, 0x70, 0x5d,
        0xe7, 0x03, 0x16, 0x1f, 0x53, 0x29, 0xaa, 0x03,
        0xa6, 0xf5, 0xb8, 0x49, 0xb9, 0x0a, 0x4f, 0xb9].toByteArray
  | 9 =>
      some [0x22, 0xe3, 0x07, 0x85, 0x77, 0x07, 0x3b, 0x4c,
        0x1c, 0x05, 0xa8, 0xfc, 0xeb, 0xb6, 0xb9, 0x6b,
        0xf6, 0x06, 0x13, 0xb5, 0x39, 0x61, 0x4e, 0xce,
        0x46, 0x46, 0x95, 0x3b, 0xa9, 0xf9, 0xd8, 0x57].toByteArray
  | _ => none

/-! ## Headers -/

structure GammaHeader where
  magic : ByteArray
  version : Nat
  classification : Classification
  encodedDiskBytes : Nat
  reserved : Nat
  firstTIndex : Nat
  tIndexStopExclusive : Nat
  tDenominator : Nat
  tStepNumerator : Nat
  diskCount : Nat
  factorConventionSHA256 : ByteArray
  producerIdentitySHA256 : ByteArray
  deriving DecidableEq

def GammaHeader.IsValid (header : GammaHeader) : Prop :=
  header.magic = gammaMagic.toByteArray ∧
    header.version = formatVersion ∧
    header.encodedDiskBytes = diskBytes ∧
    header.reserved = 0 ∧
    header.firstTIndex < header.tIndexStopExclusive ∧
    header.tIndexStopExclusive ≤ sourceTIndexStop ∧
    header.tDenominator = sourceTDenominator ∧
    header.tStepNumerator = sourceTStepNumerator ∧
    header.diskCount =
      2 * (header.tIndexStopExclusive - header.firstTIndex) ∧
    header.factorConventionSHA256 =
      SparkInterval.Dirichlet.CompletedFactorWire.factorConventionSHA256 ∧
    digestSized header.producerIdentitySHA256 ∧
    match header.classification with
    | .bounded => True
    | .fullSource =>
        header.firstTIndex = 0 ∧
          header.tIndexStopExclusive = sourceTIndexStop

instance (header : GammaHeader) : Decidable header.IsValid := by
  unfold GammaHeader.IsValid
  cases header.classification <;> infer_instance

structure StepHeader where
  magic : ByteArray
  version : Nat
  classification : Classification
  encodedDiskBytes : Nat
  reserved : Nat
  rosterVersion : Nat
  qCount : Nat
  qStart : Nat
  qStop : Nat
  scheduleManifestSHA256 : ByteArray
  executionOrderSHA256 : ByteArray
  factorConventionSHA256 : ByteArray
  deriving DecidableEq

def StepHeader.IsValid (header : StepHeader) : Prop :=
  header.magic = stepMagic.toByteArray ∧
    header.version = formatVersion ∧
    header.encodedDiskBytes = diskBytes ∧
    header.reserved = 0 ∧
    header.rosterVersion = primitiveModulusRosterVersion ∧
    0 < header.qCount ∧
    header.qCount ≤ sourceQStop ∧
    3 ≤ header.qStart ∧
    header.qStart ≤ header.qStop ∧
    header.qStop ≤ sourceQStop ∧
    digestSized header.scheduleManifestSHA256 ∧
    digestSized header.executionOrderSHA256 ∧
    header.factorConventionSHA256 =
      SparkInterval.Dirichlet.CompletedFactorWire.factorConventionSHA256 ∧
    match header.classification with
    | .bounded => True
    | .fullSource =>
        header.qStart = sourceQStart ∧
          header.qStop = sourceQStop ∧
          header.qCount = sourceQCount

instance (header : StepHeader) : Decidable header.IsValid := by
  unfold StepHeader.IsValid
  cases header.classification <;> infer_instance

structure CheckpointHeader where
  magic : ByteArray
  version : Nat
  classification : Classification
  encodedDiskBytes : Nat
  encodedRecordHeaderBytes : Nat
  phaseIndex : Nat
  firstTIndex : Nat
  tIndexStopExclusive : Nat
  tDenominator : Nat
  tStepNumerator : Nat
  checkpointSpan : Nat
  qCount : Nat
  checkpointCount : Nat
  scheduleManifestSHA256 : ByteArray
  phaseScheduleSHA256 : ByteArray
  gammaArtifactSHA256 : ByteArray
  stepArtifactSHA256 : ByteArray
  deriving DecidableEq

def CheckpointHeader.IsValid (header : CheckpointHeader) : Prop :=
  header.magic = checkpointMagic.toByteArray ∧
    header.version = formatVersion ∧
    header.encodedDiskBytes = diskBytes ∧
    header.encodedRecordHeaderBytes = checkpointRecordHeaderBytes ∧
    header.phaseIndex < 1_000_000 ∧
    header.firstTIndex < header.tIndexStopExclusive ∧
    header.tIndexStopExclusive ≤ sourceTIndexStop ∧
    header.tDenominator = sourceTDenominator ∧
    header.tStepNumerator = sourceTStepNumerator ∧
    0 < header.checkpointSpan ∧
    header.checkpointSpan ≤ sourceTIndexStop ∧
    0 < header.qCount ∧
    header.qCount ≤ maximumCheckpointRecords ∧
    header.qCount ≤ header.checkpointCount ∧
    header.checkpointCount ≤ maximumCheckpoints ∧
    digestSized header.scheduleManifestSHA256 ∧
    digestSized header.phaseScheduleSHA256 ∧
    digestSized header.gammaArtifactSHA256 ∧
    digestSized header.stepArtifactSHA256 ∧
    match header.classification with
    | .bounded => True
    | .fullSource =>
        match pinnedPhase? header.phaseIndex with
        | none => False
        | some phase =>
            header.firstTIndex = phase.firstTIndex ∧
              header.tIndexStopExclusive = phase.tIndexStopExclusive ∧
              header.checkpointSpan = defaultCheckpointSpan ∧
              header.qCount = phase.qCount ∧
              header.checkpointCount = phase.checkpointCount

instance (header : CheckpointHeader) : Decidable header.IsValid := by
  unfold CheckpointHeader.IsValid
  cases header.classification with
  | bounded => infer_instance
  | fullSource =>
      cases pinnedPhase? header.phaseIndex <;> infer_instance

private def parseGammaHeader (raw : ByteArray) : Option GammaHeader := do
  let magic ← checkedSlice? raw 0 8
  let version ← readU32LE raw 8
  let classificationCode ← readU32LE raw 12
  let classification ← decodeClassification classificationCode
  let encodedDiskBytes ← readU32LE raw 16
  let reserved ← readU32LE raw 20
  let firstTIndex ← readU64LE raw 24
  let tIndexStopExclusive ← readU64LE raw 32
  let tDenominator ← readU64LE raw 40
  let tStepNumerator ← readU64LE raw 48
  let diskCount ← readU64LE raw 56
  let factorConventionSHA256 ← readDigest raw 64
  let producerIdentitySHA256 ← readDigest raw 96
  let header : GammaHeader := {
    magic
    version
    classification
    encodedDiskBytes
    reserved
    firstTIndex
    tIndexStopExclusive
    tDenominator
    tStepNumerator
    diskCount
    factorConventionSHA256
    producerIdentitySHA256
  }
  if _ : header.IsValid then pure header else none

private def parseStepHeader (raw : ByteArray) : Option StepHeader := do
  let magic ← checkedSlice? raw 0 8
  let version ← readU32LE raw 8
  let classificationCode ← readU32LE raw 12
  let classification ← decodeClassification classificationCode
  let encodedDiskBytes ← readU32LE raw 16
  let reserved ← readU32LE raw 20
  let rosterVersion ← readU32LE raw 24
  let qCount ← readU32LE raw 28
  let qStart ← readU64LE raw 32
  let qStop ← readU64LE raw 40
  let scheduleManifestSHA256 ← readDigest raw 48
  let executionOrderSHA256 ← readDigest raw 80
  let factorConventionSHA256 ← readDigest raw 112
  let header : StepHeader := {
    magic
    version
    classification
    encodedDiskBytes
    reserved
    rosterVersion
    qCount
    qStart
    qStop
    scheduleManifestSHA256
    executionOrderSHA256
    factorConventionSHA256
  }
  if _ : header.IsValid then pure header else none

private def parseCheckpointHeader
    (raw : ByteArray) : Option CheckpointHeader := do
  let magic ← checkedSlice? raw 0 8
  let version ← readU32LE raw 8
  let classificationCode ← readU32LE raw 12
  let classification ← decodeClassification classificationCode
  let encodedDiskBytes ← readU32LE raw 16
  let encodedRecordHeaderBytes ← readU32LE raw 20
  let phaseIndex ← readU64LE raw 24
  let firstTIndex ← readU64LE raw 32
  let tIndexStopExclusive ← readU64LE raw 40
  let tDenominator ← readU64LE raw 48
  let tStepNumerator ← readU32LE raw 56
  let checkpointSpan ← readU32LE raw 60
  let qCount ← readU64LE raw 64
  let checkpointCount ← readU64LE raw 72
  let scheduleManifestSHA256 ← readDigest raw 80
  let phaseScheduleSHA256 ← readDigest raw 112
  let gammaArtifactSHA256 ← readDigest raw 144
  let stepArtifactSHA256 ← readDigest raw 176
  let header : CheckpointHeader := {
    magic
    version
    classification
    encodedDiskBytes
    encodedRecordHeaderBytes
    phaseIndex
    firstTIndex
    tIndexStopExclusive
    tDenominator
    tStepNumerator
    checkpointSpan
    qCount
    checkpointCount
    scheduleManifestSHA256
    phaseScheduleSHA256
    gammaArtifactSHA256
    stepArtifactSHA256
  }
  if _ : header.IsValid then pure header else none

/-! Public header-only entry points used by streaming consumers.

These wrappers deliberately expose the already validated fixed-size headers
without forcing clients to call the legacy artifact parsers, which
materialize every body row.  They do not weaken the header checks above. -/

def parseGammaHeaderOnly (raw : ByteArray) : Option GammaHeader :=
  match parseGammaHeader raw with
  | none => none
  | some header =>
      if _ : header.IsValid then some header else none

def parseStepHeaderOnly (raw : ByteArray) : Option StepHeader :=
  match parseStepHeader raw with
  | none => none
  | some header =>
      if _ : header.IsValid then some header else none

def parseCheckpointHeaderOnly
    (raw : ByteArray) : Option CheckpointHeader :=
  match parseCheckpointHeader raw with
  | none => none
  | some header =>
      if _ : header.IsValid then some header else none

theorem parseGammaHeaderOnly_sound
    {raw : ByteArray} {header : GammaHeader}
    (hparse : parseGammaHeaderOnly raw = some header) :
    header.IsValid := by
  unfold parseGammaHeaderOnly at hparse
  cases hheader : parseGammaHeader raw with
  | none =>
      simp [hheader] at hparse
  | some parsed =>
      simp only [hheader] at hparse
      split at hparse
      · rename_i hvalid
        cases hparse
        exact hvalid
      · simp at hparse

theorem parseStepHeaderOnly_sound
    {raw : ByteArray} {header : StepHeader}
    (hparse : parseStepHeaderOnly raw = some header) :
    header.IsValid := by
  unfold parseStepHeaderOnly at hparse
  cases hheader : parseStepHeader raw with
  | none =>
      simp [hheader] at hparse
  | some parsed =>
      simp only [hheader] at hparse
      split at hparse
      · rename_i hvalid
        cases hparse
        exact hvalid
      · simp at hparse

theorem parseCheckpointHeaderOnly_sound
    {raw : ByteArray} {header : CheckpointHeader}
    (hparse : parseCheckpointHeaderOnly raw = some header) :
    header.IsValid := by
  unfold parseCheckpointHeaderOnly at hparse
  cases hheader : parseCheckpointHeader raw with
  | none =>
      simp [hheader] at hparse
  | some parsed =>
      simp only [hheader] at hparse
      split at hparse
      · rename_i hvalid
        cases hparse
        exact hvalid
      · simp at hparse

/-! ## Artifact bodies -/

def canonicalCheckpointCount (sampleCount checkpointSpan : Nat) : Nat :=
  if sampleCount = 0 ∨ checkpointSpan = 0 then 0
  else 1 + (sampleCount - 1) / checkpointSpan

structure CheckpointRecord where
  q : Nat
  sampleCount : Nat
  encodedCheckpointCount : Nat
  reserved : Nat
  checkpoints : List Disk
  deriving Repr, DecidableEq

def CheckpointRecord.GeometryValid
    (phaseSampleCount checkpointSpan : Nat)
    (record : CheckpointRecord) : Prop :=
  3 ≤ record.q ∧
    record.q ≤ sourceQStop ∧
    0 < record.sampleCount ∧
    record.sampleCount ≤ phaseSampleCount ∧
    record.encodedCheckpointCount =
      canonicalCheckpointCount record.sampleCount checkpointSpan ∧
    record.reserved = 0 ∧
    record.checkpoints.length = record.encodedCheckpointCount

def CheckpointRecord.IsValid
    (phaseSampleCount checkpointSpan : Nat)
    (record : CheckpointRecord) : Prop :=
  record.GeometryValid phaseSampleCount checkpointSpan ∧
    disksValid record.checkpoints

instance (phaseSampleCount checkpointSpan : Nat)
    (record : CheckpointRecord) :
    Decidable (record.IsValid phaseSampleCount checkpointSpan) := by
  unfold CheckpointRecord.IsValid CheckpointRecord.GeometryValid
  infer_instance

instance (phaseSampleCount checkpointSpan : Nat)
    (record : CheckpointRecord) :
    Decidable (record.GeometryValid phaseSampleCount checkpointSpan) := by
  unfold CheckpointRecord.GeometryValid
  infer_instance

structure ParsedCheckpointRecords where
  records : List CheckpointRecord
  stopOffset : Nat
  checkpointCount : Nat
  deriving Repr, DecidableEq

def parseCheckpointRecords
    (raw : ByteArray) (phaseSampleCount checkpointSpan : Nat) :
    Nat → Nat → Option ParsedCheckpointRecords
  | 0, offset =>
      some { records := [], stopOffset := offset, checkpointCount := 0 }
  | count + 1, offset => do
      let q ← readU32LE raw offset
      let sampleCount ← readU32LE raw (offset + 4)
      let encodedCheckpointCount ← readU32LE raw (offset + 8)
      let reserved ← readU32LE raw (offset + 12)
      let checkpoints ← parseDisks raw encodedCheckpointCount
        (offset + checkpointRecordHeaderBytes)
      let record : CheckpointRecord := {
        q
        sampleCount
        encodedCheckpointCount
        reserved
        checkpoints
      }
      if _ : record.GeometryValid phaseSampleCount checkpointSpan then
        pure ()
      else
        none
      let nextOffset :=
        offset + checkpointRecordHeaderBytes +
          encodedCheckpointCount * diskBytes
      let rest ← parseCheckpointRecords raw phaseSampleCount checkpointSpan
        count nextOffset
      pure {
        records := record :: rest.records
        stopOffset := rest.stopOffset
        checkpointCount := encodedCheckpointCount + rest.checkpointCount
      }

structure GammaArtifact where
  header : GammaHeader
  disks : List Disk
  wireSize : Nat
  deriving DecidableEq

def GammaArtifact.IsValid
    (raw : ByteArray) (artifact : GammaArtifact) : Prop :=
  artifact.header.IsValid ∧
    artifact.disks.length = artifact.header.diskCount ∧
    disksValid artifact.disks ∧
    artifact.wireSize = raw.size ∧
    artifact.wireSize =
      gammaHeaderBytes + artifact.header.diskCount * diskBytes

instance (raw : ByteArray) (artifact : GammaArtifact) :
    Decidable (artifact.IsValid raw) := by
  unfold GammaArtifact.IsValid
  infer_instance

structure StepArtifact where
  header : StepHeader
  disks : List Disk
  wireSize : Nat
  deriving DecidableEq

def StepArtifact.IsValid
    (raw : ByteArray) (artifact : StepArtifact) : Prop :=
  artifact.header.IsValid ∧
    artifact.disks.length = artifact.header.qCount ∧
    disksValid artifact.disks ∧
    artifact.wireSize = raw.size ∧
    artifact.wireSize =
      stepHeaderBytes + artifact.header.qCount * diskBytes

instance (raw : ByteArray) (artifact : StepArtifact) :
    Decidable (artifact.IsValid raw) := by
  unfold StepArtifact.IsValid
  infer_instance

structure CheckpointArtifact where
  header : CheckpointHeader
  records : List CheckpointRecord
  wireSize : Nat
  deriving DecidableEq

def CheckpointArtifact.IsValid
    (raw : ByteArray) (artifact : CheckpointArtifact) : Prop :=
  artifact.header.IsValid ∧
    artifact.records.length = artifact.header.qCount ∧
    distinctNats (artifact.records.map CheckpointRecord.q) ∧
    (∀ record ∈ artifact.records,
      record.IsValid
        (artifact.header.tIndexStopExclusive -
          artifact.header.firstTIndex)
        artifact.header.checkpointSpan) ∧
    (artifact.records.map CheckpointRecord.encodedCheckpointCount).sum =
      artifact.header.checkpointCount ∧
    artifact.wireSize = raw.size ∧
    artifact.wireSize =
      checkpointHeaderBytes +
        artifact.header.qCount * checkpointRecordHeaderBytes +
        artifact.header.checkpointCount * diskBytes

instance (raw : ByteArray) (artifact : CheckpointArtifact) :
    Decidable (artifact.IsValid raw) := by
  unfold CheckpointArtifact.IsValid
  infer_instance

private def parseGammaArtifactCandidate
    (raw : ByteArray) : Option GammaArtifact := do
  if gammaHeaderBytes ≤ raw.size then pure () else none
  let header ← parseGammaHeader raw
  if raw.size = gammaHeaderBytes + header.diskCount * diskBytes then
    pure ()
  else
    none
  let disks ← parseDisks raw header.diskCount gammaHeaderBytes
  pure { header, disks, wireSize := raw.size }

private def parseStepArtifactCandidate
    (raw : ByteArray) : Option StepArtifact := do
  if stepHeaderBytes ≤ raw.size then pure () else none
  let header ← parseStepHeader raw
  if raw.size = stepHeaderBytes + header.qCount * diskBytes then
    pure ()
  else
    none
  let disks ← parseDisks raw header.qCount stepHeaderBytes
  pure { header, disks, wireSize := raw.size }

private def parseCheckpointArtifactCandidate
    (raw : ByteArray) : Option CheckpointArtifact := do
  if checkpointHeaderBytes ≤ raw.size then pure () else none
  let header ← parseCheckpointHeader raw
  let parsed ← parseCheckpointRecords raw
    (header.tIndexStopExclusive - header.firstTIndex)
    header.checkpointSpan header.qCount checkpointHeaderBytes
  if parsed.stopOffset = raw.size &&
      parsed.checkpointCount = header.checkpointCount then
    pure ()
  else
    none
  pure {
    header
    records := parsed.records
    wireSize := raw.size
  }

/-- Parse and validate one exact `TGDCGAM1` artifact. -/
def parseGammaArtifact (raw : ByteArray) : Option GammaArtifact :=
  match parseGammaArtifactCandidate raw with
  | none => none
  | some artifact =>
      if _ : artifact.IsValid raw then some artifact else none

/-- Parse and validate one exact `TGDCSTP1` artifact. -/
def parseStepArtifact (raw : ByteArray) : Option StepArtifact :=
  match parseStepArtifactCandidate raw with
  | none => none
  | some artifact =>
      if _ : artifact.IsValid raw then some artifact else none

/-- Parse and validate one exact `TGDCCPB1` artifact. -/
def parseCheckpointArtifact
    (raw : ByteArray) : Option CheckpointArtifact :=
  match parseCheckpointArtifactCandidate raw with
  | none => none
  | some artifact =>
      if _ : artifact.IsValid raw then some artifact else none

theorem parseGammaArtifact_sound
    {raw : ByteArray} {artifact : GammaArtifact}
    (hparse : parseGammaArtifact raw = some artifact) :
    artifact.IsValid raw := by
  unfold parseGammaArtifact at hparse
  cases hcandidate : parseGammaArtifactCandidate raw with
  | none => simp [hcandidate] at hparse
  | some candidate =>
      simp only [hcandidate] at hparse
      split at hparse
      · rename_i hvalid
        cases hparse
        exact hvalid
      · simp at hparse

theorem parseStepArtifact_sound
    {raw : ByteArray} {artifact : StepArtifact}
    (hparse : parseStepArtifact raw = some artifact) :
    artifact.IsValid raw := by
  unfold parseStepArtifact at hparse
  cases hcandidate : parseStepArtifactCandidate raw with
  | none => simp [hcandidate] at hparse
  | some candidate =>
      simp only [hcandidate] at hparse
      split at hparse
      · rename_i hvalid
        cases hparse
        exact hvalid
      · simp at hparse

theorem parseCheckpointArtifact_sound
    {raw : ByteArray} {artifact : CheckpointArtifact}
    (hparse : parseCheckpointArtifact raw = some artifact) :
    artifact.IsValid raw := by
  unfold parseCheckpointArtifact at hparse
  cases hcandidate : parseCheckpointArtifactCandidate raw with
  | none => simp [hcandidate] at hparse
  | some candidate =>
      simp only [hcandidate] at hparse
      split at hparse
      · rename_i hvalid
        cases hparse
        exact hvalid
      · simp at hparse

/-! ## Exact bounded bundle -/

structure QSample where
  q : Nat
  sampleCount : Nat
  deriving Repr, DecidableEq, BEq

def rosterQStart : List QSample → Nat
  | [] => 0
  | first :: rest => rest.foldl (fun current row => min current row.q) first.q

def rosterQStop : List QSample → Nat
  | [] => 0
  | first :: rest => rest.foldl (fun current row => max current row.q) first.q

structure BoundedExpectations where
  phaseIndex : Nat
  firstTIndex : Nat
  tIndexStopExclusive : Nat
  checkpointSpan : Nat
  roster : List QSample
  scheduleManifestSHA256 : ByteArray
  executionOrderSHA256 : ByteArray
  phaseScheduleSHA256 : ByteArray
  producerIdentitySHA256 : ByteArray
  deriving DecidableEq

def BoundedExpectations.IsValid
    (expected : BoundedExpectations) : Prop :=
  expected.phaseIndex < 1_000_000 ∧
    expected.firstTIndex < expected.tIndexStopExclusive ∧
    expected.tIndexStopExclusive ≤ sourceTIndexStop ∧
    0 < expected.checkpointSpan ∧
    expected.checkpointSpan ≤ sourceTIndexStop ∧
    expected.roster ≠ [] ∧
    expected.roster.length ≤ maximumCheckpointRecords ∧
    distinctNats (expected.roster.map QSample.q) ∧
    (∀ row ∈ expected.roster,
      3 ≤ row.q ∧ row.q ≤ sourceQStop ∧
        0 < row.sampleCount ∧
        row.sampleCount ≤
          expected.tIndexStopExclusive - expected.firstTIndex) ∧
    digestSized expected.scheduleManifestSHA256 ∧
    digestSized expected.executionOrderSHA256 ∧
    digestSized expected.phaseScheduleSHA256 ∧
    digestSized expected.producerIdentitySHA256

instance (expected : BoundedExpectations) :
    Decidable expected.IsValid := by
  unfold BoundedExpectations.IsValid
  infer_instance

def recordRoster (records : List CheckpointRecord) : List QSample :=
  records.map fun record =>
    { q := record.q, sampleCount := record.sampleCount }

def expectedCheckpointTotal (expected : BoundedExpectations) : Nat :=
  (expected.roster.map fun row =>
    canonicalCheckpointCount row.sampleCount expected.checkpointSpan).sum

structure Bundle where
  gamma : GammaArtifact
  step : StepArtifact
  checkpoint : CheckpointArtifact
  deriving DecidableEq

def Bundle.GammaMatchesBounded
    (expected : BoundedExpectations) (bundle : Bundle) : Prop :=
  bundle.gamma.header.classification = .bounded ∧
    bundle.gamma.header.firstTIndex = expected.firstTIndex ∧
    bundle.gamma.header.tIndexStopExclusive =
      expected.tIndexStopExclusive ∧
    bundle.gamma.header.diskCount =
      2 * (expected.tIndexStopExclusive - expected.firstTIndex) ∧
    bundle.gamma.header.producerIdentitySHA256 =
      expected.producerIdentitySHA256

def Bundle.StepMatchesBounded
    (expected : BoundedExpectations) (bundle : Bundle) : Prop :=
  bundle.step.header.classification = .bounded ∧
    bundle.step.header.qCount = expected.roster.length ∧
    bundle.step.header.qStart = rosterQStart expected.roster ∧
    bundle.step.header.qStop = rosterQStop expected.roster ∧
    bundle.step.header.scheduleManifestSHA256 =
      expected.scheduleManifestSHA256 ∧
    bundle.step.header.executionOrderSHA256 =
      expected.executionOrderSHA256

def Bundle.CheckpointMatchesBounded
    (expected : BoundedExpectations) (bundle : Bundle) : Prop :=
  bundle.checkpoint.header.classification = .bounded ∧
    bundle.checkpoint.header.phaseIndex = expected.phaseIndex ∧
    bundle.checkpoint.header.firstTIndex = expected.firstTIndex ∧
    bundle.checkpoint.header.tIndexStopExclusive =
      expected.tIndexStopExclusive ∧
    bundle.checkpoint.header.checkpointSpan = expected.checkpointSpan ∧
    bundle.checkpoint.header.qCount = expected.roster.length ∧
    bundle.checkpoint.header.checkpointCount =
      expectedCheckpointTotal expected ∧
    bundle.checkpoint.header.scheduleManifestSHA256 =
      expected.scheduleManifestSHA256 ∧
    bundle.checkpoint.header.phaseScheduleSHA256 =
      expected.phaseScheduleSHA256 ∧
    recordRoster bundle.checkpoint.records = expected.roster

def Bundle.CrossArtifactBindings
    (gammaRaw stepRaw : ByteArray) (bundle : Bundle) : Prop :=
    bundle.gamma.header.factorConventionSHA256 =
      SparkInterval.Dirichlet.CompletedFactorWire.factorConventionSHA256 ∧
    bundle.step.header.factorConventionSHA256 =
      SparkInterval.Dirichlet.CompletedFactorWire.factorConventionSHA256 ∧
    bundle.checkpoint.header.scheduleManifestSHA256 =
      bundle.step.header.scheduleManifestSHA256 ∧
    artifactDigestMatches gammaRaw
      bundle.checkpoint.header.gammaArtifactSHA256 ∧
    artifactDigestMatches stepRaw
      bundle.checkpoint.header.stepArtifactSHA256

/-- Fields that remain to be checked after all three total artifact parsers
have already validated framing and disk bodies.  Keeping this separate avoids
re-decoding every disk at the bundle layer. -/
def Bundle.BoundedBindings
    (expected : BoundedExpectations)
    (gammaRaw stepRaw : ByteArray)
    (bundle : Bundle) : Prop :=
  expected.IsValid ∧
    bundle.GammaMatchesBounded expected ∧
    bundle.StepMatchesBounded expected ∧
    bundle.CheckpointMatchesBounded expected ∧
    bundle.CrossArtifactBindings gammaRaw stepRaw

instance (expected : BoundedExpectations)
    (gammaRaw stepRaw : ByteArray) (bundle : Bundle) :
    Decidable (bundle.BoundedBindings expected gammaRaw stepRaw) := by
  unfold Bundle.BoundedBindings Bundle.GammaMatchesBounded
    Bundle.StepMatchesBounded Bundle.CheckpointMatchesBounded
    Bundle.CrossArtifactBindings
  infer_instance

def Bundle.IsBoundedValid
    (expected : BoundedExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray)
    (bundle : Bundle) : Prop :=
  expected.IsValid ∧
    bundle.gamma.IsValid gammaRaw ∧
    bundle.step.IsValid stepRaw ∧
    bundle.checkpoint.IsValid checkpointRaw ∧
    bundle.GammaMatchesBounded expected ∧
    bundle.StepMatchesBounded expected ∧
    bundle.CheckpointMatchesBounded expected ∧
    bundle.CrossArtifactBindings gammaRaw stepRaw

instance (expected : BoundedExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) (bundle : Bundle) :
    Decidable
      (bundle.IsBoundedValid expected gammaRaw stepRaw checkpointRaw) := by
  unfold Bundle.IsBoundedValid Bundle.GammaMatchesBounded
    Bundle.StepMatchesBounded Bundle.CheckpointMatchesBounded
    Bundle.CrossArtifactBindings
  infer_instance

def checkBoundedBundle
    (expected : BoundedExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Bool :=
  match parseGammaArtifact gammaRaw with
  | none => false
  | some gamma =>
      match parseStepArtifact stepRaw with
      | none => false
      | some step =>
          match parseCheckpointArtifact checkpointRaw with
          | none => false
          | some checkpoint =>
              decide
                (({ gamma, step, checkpoint } : Bundle).BoundedBindings
                  expected gammaRaw stepRaw)

def ValidatedBoundedBundle
    (expected : BoundedExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    parseGammaArtifact gammaRaw = some bundle.gamma ∧
    parseStepArtifact stepRaw = some bundle.step ∧
    parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
    bundle.IsBoundedValid expected gammaRaw stepRaw checkpointRaw

theorem checkBoundedBundle_sound
    {expected : BoundedExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkBoundedBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ValidatedBoundedBundle expected gammaRaw stepRaw checkpointRaw := by
  unfold checkBoundedBundle at hcheck
  cases hgamma : parseGammaArtifact gammaRaw with
  | none => simp [hgamma] at hcheck
  | some gamma =>
      cases hstep : parseStepArtifact stepRaw with
      | none => simp [hgamma, hstep] at hcheck
      | some step =>
          cases hcheckpoint : parseCheckpointArtifact checkpointRaw with
          | none => simp [hgamma, hstep, hcheckpoint] at hcheck
          | some checkpoint =>
              have hbindings :
                  ({ gamma, step, checkpoint } : Bundle).BoundedBindings
                    expected gammaRaw stepRaw := by
                simpa [hgamma, hstep, hcheckpoint] using hcheck
              exact
                ⟨{ gamma, step, checkpoint },
                  hgamma, hstep, hcheckpoint,
                  hbindings.1,
                  parseGammaArtifact_sound hgamma,
                  parseStepArtifact_sound hstep,
                  parseCheckpointArtifact_sound hcheckpoint,
                  hbindings.2.1,
                  hbindings.2.2.1,
                  hbindings.2.2.2.1,
                  hbindings.2.2.2.2⟩

/-- Checked bounded bytes expose the exact classification and expected field
projections.  No geometric coincidence can turn these headers into
`.fullSource`. -/
theorem checkBoundedBundle_fields
    {expected : BoundedExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkBoundedBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseGammaArtifact gammaRaw = some bundle.gamma ∧
      parseStepArtifact stepRaw = some bundle.step ∧
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      bundle.GammaMatchesBounded expected ∧
      bundle.StepMatchesBounded expected ∧
      bundle.CheckpointMatchesBounded expected ∧
      bundle.CrossArtifactBindings gammaRaw stepRaw := by
  rcases checkBoundedBundle_sound hcheck with
    ⟨bundle, hgamma, hstep, hcheckpoint, hvalid⟩
  exact
    ⟨bundle, hgamma, hstep, hcheckpoint,
      hvalid.2.2.2.2.1,
      hvalid.2.2.2.2.2.1,
      hvalid.2.2.2.2.2.2.1,
      hvalid.2.2.2.2.2.2.2⟩

/-- Every accepted checkpoint record has exactly the canonical number of
checkpoint disks for its sample count and the checked span. -/
theorem checkBoundedBundle_checkpointCounts
    {expected : BoundedExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkBoundedBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      ∀ record ∈ bundle.checkpoint.records,
        record.encodedCheckpointCount =
          canonicalCheckpointCount record.sampleCount
            bundle.checkpoint.header.checkpointSpan ∧
        record.checkpoints.length = record.encodedCheckpointCount := by
  rcases checkBoundedBundle_sound hcheck with
    ⟨bundle, _, _, hcheckpoint, hvalid⟩
  refine ⟨bundle, hcheckpoint, ?_⟩
  intro record hrecord
  have hartifact : bundle.checkpoint.IsValid checkpointRaw :=
    hvalid.2.2.2.1
  have hrecords :=
    hartifact.2.2.2.1 record hrecord
  exact ⟨hrecords.1.2.2.2.2.1, hrecords.1.2.2.2.2.2.2⟩

/-- Every 24-byte row accepted anywhere in the bundle has an exact finite
binary64 decoding with a nonnegative radius. -/
theorem checkBoundedBundle_diskRows
    {expected : BoundedExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkBoundedBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseGammaArtifact gammaRaw = some bundle.gamma ∧
      parseStepArtifact stepRaw = some bundle.step ∧
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      disksValid bundle.gamma.disks ∧
      disksValid bundle.step.disks ∧
      ∀ record ∈ bundle.checkpoint.records,
        disksValid record.checkpoints := by
  rcases checkBoundedBundle_sound hcheck with
    ⟨bundle, hgamma, hstep, hcheckpoint, hvalid⟩
  have hgammaValid : bundle.gamma.IsValid gammaRaw := hvalid.2.1
  have hstepValid : bundle.step.IsValid stepRaw := hvalid.2.2.1
  have hcheckpointValid :
      bundle.checkpoint.IsValid checkpointRaw := hvalid.2.2.2.1
  refine
    ⟨bundle, hgamma, hstep, hcheckpoint,
      hgammaValid.2.2.1, hstepValid.2.2.1, ?_⟩
  intro record hrecord
  exact (hcheckpointValid.2.2.2.1 record hrecord).2

/-! ## Exact full-source phase bundle

The source service reconstructs the ordered active q roster from its
canonical `TGDQORD1` schedule.  This checker deliberately accepts that roster
as an explicit runtime expectation rather than pretending the aggregate
phase counts identify it.  `QOrderManifestWire` now constructs the same
`FullSourceExpectations` value from a checked `TGDQORD1` file and exposes an
end-to-end schedule-to-factor checker without changing this artifact API.
-/

structure FullSourceExpectations where
  phaseIndex : Nat
  phase : PinnedPhase
  roster : List QSample
  scheduleManifestSHA256 : ByteArray
  executionOrderSHA256 : ByteArray
  phaseScheduleSHA256 : ByteArray
  producerIdentitySHA256 : ByteArray
  deriving DecidableEq

def fullSourceCheckpointTotal
    (expected : FullSourceExpectations) : Nat :=
  (expected.roster.map fun row =>
    canonicalCheckpointCount row.sampleCount defaultCheckpointSpan).sum

def fullSourceSampleTotal
    (expected : FullSourceExpectations) : Nat :=
  (expected.roster.map QSample.sampleCount).sum

def FullSourceExpectations.IsValid
    (expected : FullSourceExpectations) : Prop :=
  pinnedPhase? expected.phaseIndex = some expected.phase ∧
    pinnedPhaseScheduleSHA256? expected.phaseIndex =
      some expected.phaseScheduleSHA256 ∧
    expected.scheduleManifestSHA256 =
      pinnedSourceScheduleManifestSHA256 ∧
    expected.executionOrderSHA256 =
      pinnedSourceExecutionOrderSHA256 ∧
    digestSized expected.producerIdentitySHA256 ∧
    expected.roster.length = expected.phase.qCount ∧
    distinctNats (expected.roster.map QSample.q) ∧
    (∀ row ∈ expected.roster,
      sourceQStart ≤ row.q ∧ row.q ≤ sourceQStop ∧
        0 < row.sampleCount ∧
        row.sampleCount ≤
          expected.phase.tIndexStopExclusive -
            expected.phase.firstTIndex) ∧
    fullSourceSampleTotal expected = expected.phase.tIndexRowCount ∧
    fullSourceCheckpointTotal expected =
      expected.phase.checkpointCount

instance (expected : FullSourceExpectations) :
    Decidable expected.IsValid := by
  unfold FullSourceExpectations.IsValid
  infer_instance

def Bundle.GammaMatchesFullSource
    (expected : FullSourceExpectations) (bundle : Bundle) : Prop :=
  bundle.gamma.header.classification = .fullSource ∧
    bundle.gamma.header.firstTIndex = 0 ∧
    bundle.gamma.header.tIndexStopExclusive = sourceTIndexStop ∧
    bundle.gamma.header.diskCount = 2 * sourceTIndexStop ∧
    bundle.gamma.header.producerIdentitySHA256 =
      expected.producerIdentitySHA256

def Bundle.StepMatchesFullSource
    (expected : FullSourceExpectations) (bundle : Bundle) : Prop :=
  bundle.step.header.classification = .fullSource ∧
    bundle.step.header.qCount = sourceQCount ∧
    bundle.step.header.qStart = sourceQStart ∧
    bundle.step.header.qStop = sourceQStop ∧
    bundle.step.header.scheduleManifestSHA256 =
      expected.scheduleManifestSHA256 ∧
    bundle.step.header.executionOrderSHA256 =
      expected.executionOrderSHA256

def Bundle.CheckpointMatchesFullSource
    (expected : FullSourceExpectations) (bundle : Bundle) : Prop :=
  bundle.checkpoint.header.classification = .fullSource ∧
    bundle.checkpoint.header.phaseIndex = expected.phaseIndex ∧
    bundle.checkpoint.header.firstTIndex = expected.phase.firstTIndex ∧
    bundle.checkpoint.header.tIndexStopExclusive =
      expected.phase.tIndexStopExclusive ∧
    bundle.checkpoint.header.checkpointSpan = defaultCheckpointSpan ∧
    bundle.checkpoint.header.qCount = expected.phase.qCount ∧
    bundle.checkpoint.header.checkpointCount =
      expected.phase.checkpointCount ∧
    bundle.checkpoint.header.scheduleManifestSHA256 =
      expected.scheduleManifestSHA256 ∧
    bundle.checkpoint.header.phaseScheduleSHA256 =
      expected.phaseScheduleSHA256 ∧
    recordRoster bundle.checkpoint.records = expected.roster

def Bundle.FullSourceBindings
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw : ByteArray)
    (bundle : Bundle) : Prop :=
  expected.IsValid ∧
    bundle.GammaMatchesFullSource expected ∧
    bundle.StepMatchesFullSource expected ∧
    bundle.CheckpointMatchesFullSource expected ∧
    bundle.CrossArtifactBindings gammaRaw stepRaw

instance (expected : FullSourceExpectations)
    (gammaRaw stepRaw : ByteArray) (bundle : Bundle) :
    Decidable (bundle.FullSourceBindings expected gammaRaw stepRaw) := by
  unfold Bundle.FullSourceBindings Bundle.GammaMatchesFullSource
    Bundle.StepMatchesFullSource Bundle.CheckpointMatchesFullSource
    Bundle.CrossArtifactBindings
  infer_instance

def Bundle.IsFullSourceValid
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray)
    (bundle : Bundle) : Prop :=
  expected.IsValid ∧
    bundle.gamma.IsValid gammaRaw ∧
    bundle.step.IsValid stepRaw ∧
    bundle.checkpoint.IsValid checkpointRaw ∧
    bundle.GammaMatchesFullSource expected ∧
    bundle.StepMatchesFullSource expected ∧
    bundle.CheckpointMatchesFullSource expected ∧
    bundle.CrossArtifactBindings gammaRaw stepRaw

instance (expected : FullSourceExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) (bundle : Bundle) :
    Decidable
      (bundle.IsFullSourceValid expected gammaRaw stepRaw checkpointRaw) := by
  unfold Bundle.IsFullSourceValid Bundle.GammaMatchesFullSource
    Bundle.StepMatchesFullSource Bundle.CheckpointMatchesFullSource
    Bundle.CrossArtifactBindings
  infer_instance

/-- Validate the complete gamma/step catalogs and exactly one pinned
full-source checkpoint phase.  The ordered q/sample roster is a runtime input,
so ordinary builds do not materialize hundreds of thousands of rows. -/
def checkFullSourceBundle
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Bool :=
  match parseGammaArtifact gammaRaw with
  | none => false
  | some gamma =>
      match parseStepArtifact stepRaw with
      | none => false
      | some step =>
          match parseCheckpointArtifact checkpointRaw with
          | none => false
          | some checkpoint =>
              decide
                (({ gamma, step, checkpoint } : Bundle).FullSourceBindings
                  expected gammaRaw stepRaw)

def ValidatedFullSourceBundle
    (expected : FullSourceExpectations)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    parseGammaArtifact gammaRaw = some bundle.gamma ∧
    parseStepArtifact stepRaw = some bundle.step ∧
    parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
    bundle.IsFullSourceValid expected gammaRaw stepRaw checkpointRaw

theorem checkFullSourceBundle_sound
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ValidatedFullSourceBundle expected gammaRaw stepRaw checkpointRaw := by
  unfold checkFullSourceBundle at hcheck
  cases hgamma : parseGammaArtifact gammaRaw with
  | none => simp [hgamma] at hcheck
  | some gamma =>
      cases hstep : parseStepArtifact stepRaw with
      | none => simp [hgamma, hstep] at hcheck
      | some step =>
          cases hcheckpoint : parseCheckpointArtifact checkpointRaw with
          | none => simp [hgamma, hstep, hcheckpoint] at hcheck
          | some checkpoint =>
              have hbindings :
                  ({ gamma, step, checkpoint } : Bundle).FullSourceBindings
                    expected gammaRaw stepRaw := by
                simpa [hgamma, hstep, hcheckpoint] using hcheck
              exact
                ⟨{ gamma, step, checkpoint },
                  hgamma, hstep, hcheckpoint,
                  hbindings.1,
                  parseGammaArtifact_sound hgamma,
                  parseStepArtifact_sound hstep,
                  parseCheckpointArtifact_sound hcheckpoint,
                  hbindings.2.1,
                  hbindings.2.2.1,
                  hbindings.2.2.2.1,
                  hbindings.2.2.2.2⟩

theorem checkFullSourceBundle_fields
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseGammaArtifact gammaRaw = some bundle.gamma ∧
      parseStepArtifact stepRaw = some bundle.step ∧
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      bundle.GammaMatchesFullSource expected ∧
      bundle.StepMatchesFullSource expected ∧
      bundle.CheckpointMatchesFullSource expected ∧
      bundle.CrossArtifactBindings gammaRaw stepRaw := by
  rcases checkFullSourceBundle_sound hcheck with
    ⟨bundle, hgamma, hstep, hcheckpoint, hvalid⟩
  exact
    ⟨bundle, hgamma, hstep, hcheckpoint,
      hvalid.2.2.2.2.1,
      hvalid.2.2.2.2.2.1,
      hvalid.2.2.2.2.2.2.1,
      hvalid.2.2.2.2.2.2.2⟩

/-- The phase aggregate pins are not used as a substitute for identity:
accepted checkpoint records equal the complete ordered runtime roster. -/
theorem checkFullSourceBundle_exactRoster
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      expected.IsValid ∧
      recordRoster bundle.checkpoint.records = expected.roster := by
  rcases checkFullSourceBundle_sound hcheck with
    ⟨bundle, _, _, hcheckpoint, hvalid⟩
  have hmatches : bundle.CheckpointMatchesFullSource expected :=
    hvalid.2.2.2.2.2.2.1
  exact
    ⟨bundle, hcheckpoint, hvalid.1,
      hmatches.2.2.2.2.2.2.2.2.2⟩

theorem checkFullSourceBundle_checkpointCounts
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      recordRoster bundle.checkpoint.records = expected.roster ∧
      bundle.checkpoint.header.checkpointCount =
        expected.phase.checkpointCount ∧
      ∀ record ∈ bundle.checkpoint.records,
        record.encodedCheckpointCount =
          canonicalCheckpointCount record.sampleCount
            defaultCheckpointSpan ∧
        record.checkpoints.length = record.encodedCheckpointCount := by
  rcases checkFullSourceBundle_sound hcheck with
    ⟨bundle, _, _, hcheckpoint, hvalid⟩
  have hartifact : bundle.checkpoint.IsValid checkpointRaw :=
    hvalid.2.2.2.1
  have hmatches : bundle.CheckpointMatchesFullSource expected :=
    hvalid.2.2.2.2.2.2.1
  refine
    ⟨bundle, hcheckpoint, hmatches.2.2.2.2.2.2.2.2.2,
      hmatches.2.2.2.2.2.2.1, ?_⟩
  intro record hrecord
  have hrecords := hartifact.2.2.2.1 record hrecord
  have hspan :
      bundle.checkpoint.header.checkpointSpan =
        defaultCheckpointSpan :=
    hmatches.2.2.2.2.1
  exact
    ⟨by simpa [hspan] using hrecords.1.2.2.2.2.1,
      hrecords.1.2.2.2.2.2.2⟩

theorem checkFullSourceBundle_diskRows
    {expected : FullSourceExpectations}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkFullSourceBundle expected gammaRaw stepRaw checkpointRaw = true) :
    ∃ bundle : Bundle,
      parseGammaArtifact gammaRaw = some bundle.gamma ∧
      parseStepArtifact stepRaw = some bundle.step ∧
      parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
      disksValid bundle.gamma.disks ∧
      disksValid bundle.step.disks ∧
      ∀ record ∈ bundle.checkpoint.records,
        disksValid record.checkpoints := by
  rcases checkFullSourceBundle_sound hcheck with
    ⟨bundle, hgamma, hstep, hcheckpoint, hvalid⟩
  have hgammaValid : bundle.gamma.IsValid gammaRaw := hvalid.2.1
  have hstepValid : bundle.step.IsValid stepRaw := hvalid.2.2.1
  have hcheckpointValid :
      bundle.checkpoint.IsValid checkpointRaw := hvalid.2.2.2.1
  refine
    ⟨bundle, hgamma, hstep, hcheckpoint,
      hgammaValid.2.2.1, hstepValid.2.2.1, ?_⟩
  intro record hrecord
  exact (hcheckpointValid.2.2.2.1 record hrecord).2

/-! ## Complete-artifact pins -/

structure ArtifactPins where
  gammaArtifactSHA256 : String
  stepArtifactSHA256 : String
  checkpointArtifactSHA256 : String
  deriving Repr, DecidableEq

def ArtifactPins.IsValid (pins : ArtifactPins) : Prop :=
  isLowerSHA256 pins.gammaArtifactSHA256 = true ∧
    isLowerSHA256 pins.stepArtifactSHA256 = true ∧
    isLowerSHA256 pins.checkpointArtifactSHA256 = true

instance (pins : ArtifactPins) : Decidable pins.IsValid := by
  unfold ArtifactPins.IsValid
  infer_instance

def Bundle.MatchesPins
    (_bundle : Bundle) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Prop :=
  pins.IsValid ∧
    SHA256.digestByteArray gammaRaw = pins.gammaArtifactSHA256 ∧
    SHA256.digestByteArray stepRaw = pins.stepArtifactSHA256 ∧
    SHA256.digestByteArray checkpointRaw =
      pins.checkpointArtifactSHA256

instance (bundle : Bundle) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) :
    Decidable (bundle.MatchesPins pins gammaRaw stepRaw checkpointRaw) := by
  unfold Bundle.MatchesPins
  infer_instance

def checkPinnedBoundedBundle
    (expected : BoundedExpectations) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Bool :=
  match parseGammaArtifact gammaRaw with
  | none => false
  | some gamma =>
      match parseStepArtifact stepRaw with
      | none => false
      | some step =>
          match parseCheckpointArtifact checkpointRaw with
          | none => false
          | some checkpoint =>
              let bundle : Bundle := { gamma, step, checkpoint }
              decide
                (bundle.BoundedBindings expected gammaRaw stepRaw ∧
                  bundle.MatchesPins pins gammaRaw stepRaw checkpointRaw)

def ValidatedPinnedBoundedBundle
    (expected : BoundedExpectations) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    parseGammaArtifact gammaRaw = some bundle.gamma ∧
    parseStepArtifact stepRaw = some bundle.step ∧
    parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
    bundle.IsBoundedValid expected gammaRaw stepRaw checkpointRaw ∧
    bundle.MatchesPins pins gammaRaw stepRaw checkpointRaw

theorem checkPinnedBoundedBundle_sound
    {expected : BoundedExpectations} {pins : ArtifactPins}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkPinnedBoundedBundle expected pins gammaRaw stepRaw
        checkpointRaw = true) :
    ValidatedPinnedBoundedBundle expected pins gammaRaw stepRaw
      checkpointRaw := by
  unfold checkPinnedBoundedBundle at hcheck
  cases hgamma : parseGammaArtifact gammaRaw with
  | none => simp [hgamma] at hcheck
  | some gamma =>
      cases hstep : parseStepArtifact stepRaw with
      | none => simp [hgamma, hstep] at hcheck
      | some step =>
          cases hcheckpoint : parseCheckpointArtifact checkpointRaw with
          | none => simp [hgamma, hstep, hcheckpoint] at hcheck
          | some checkpoint =>
              have hpairs :
                  ({ gamma, step, checkpoint } : Bundle).BoundedBindings
                      expected gammaRaw stepRaw ∧
                    ({ gamma, step, checkpoint } : Bundle).MatchesPins
                      pins gammaRaw stepRaw checkpointRaw := by
                simpa [hgamma, hstep, hcheckpoint] using hcheck
              exact
                ⟨{ gamma, step, checkpoint },
                  hgamma, hstep, hcheckpoint,
                  ⟨hpairs.1.1,
                    parseGammaArtifact_sound hgamma,
                    parseStepArtifact_sound hstep,
                    parseCheckpointArtifact_sound hcheckpoint,
                    hpairs.1.2.1,
                    hpairs.1.2.2.1,
                    hpairs.1.2.2.2.1,
                    hpairs.1.2.2.2.2⟩,
                  hpairs.2⟩

theorem checkPinnedBoundedBundle_digests
    {expected : BoundedExpectations} {pins : ArtifactPins}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkPinnedBoundedBundle expected pins gammaRaw stepRaw
        checkpointRaw = true) :
    SHA256.digestByteArray gammaRaw = pins.gammaArtifactSHA256 ∧
      SHA256.digestByteArray stepRaw = pins.stepArtifactSHA256 ∧
      SHA256.digestByteArray checkpointRaw =
        pins.checkpointArtifactSHA256 := by
  rcases checkPinnedBoundedBundle_sound hcheck with
    ⟨_, _, _, _, _, hpins⟩
  exact hpins.2

/-- Full-source counterpart of `checkPinnedBoundedBundle`. -/
def checkPinnedFullSourceBundle
    (expected : FullSourceExpectations) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Bool :=
  match parseGammaArtifact gammaRaw with
  | none => false
  | some gamma =>
      match parseStepArtifact stepRaw with
      | none => false
      | some step =>
          match parseCheckpointArtifact checkpointRaw with
          | none => false
          | some checkpoint =>
              let bundle : Bundle := { gamma, step, checkpoint }
              decide
                (bundle.FullSourceBindings expected gammaRaw stepRaw ∧
                  bundle.MatchesPins pins gammaRaw stepRaw checkpointRaw)

def ValidatedPinnedFullSourceBundle
    (expected : FullSourceExpectations) (pins : ArtifactPins)
    (gammaRaw stepRaw checkpointRaw : ByteArray) : Prop :=
  ∃ bundle : Bundle,
    parseGammaArtifact gammaRaw = some bundle.gamma ∧
    parseStepArtifact stepRaw = some bundle.step ∧
    parseCheckpointArtifact checkpointRaw = some bundle.checkpoint ∧
    bundle.IsFullSourceValid expected gammaRaw stepRaw checkpointRaw ∧
    bundle.MatchesPins pins gammaRaw stepRaw checkpointRaw

theorem checkPinnedFullSourceBundle_sound
    {expected : FullSourceExpectations} {pins : ArtifactPins}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkPinnedFullSourceBundle expected pins gammaRaw stepRaw
        checkpointRaw = true) :
    ValidatedPinnedFullSourceBundle expected pins gammaRaw stepRaw
      checkpointRaw := by
  unfold checkPinnedFullSourceBundle at hcheck
  cases hgamma : parseGammaArtifact gammaRaw with
  | none => simp [hgamma] at hcheck
  | some gamma =>
      cases hstep : parseStepArtifact stepRaw with
      | none => simp [hgamma, hstep] at hcheck
      | some step =>
          cases hcheckpoint : parseCheckpointArtifact checkpointRaw with
          | none => simp [hgamma, hstep, hcheckpoint] at hcheck
          | some checkpoint =>
              have hpairs :
                  ({ gamma, step, checkpoint } : Bundle).FullSourceBindings
                      expected gammaRaw stepRaw ∧
                    ({ gamma, step, checkpoint } : Bundle).MatchesPins
                      pins gammaRaw stepRaw checkpointRaw := by
                simpa [hgamma, hstep, hcheckpoint] using hcheck
              exact
                ⟨{ gamma, step, checkpoint },
                  hgamma, hstep, hcheckpoint,
                  ⟨hpairs.1.1,
                    parseGammaArtifact_sound hgamma,
                    parseStepArtifact_sound hstep,
                    parseCheckpointArtifact_sound hcheckpoint,
                    hpairs.1.2.1,
                    hpairs.1.2.2.1,
                    hpairs.1.2.2.2.1,
                    hpairs.1.2.2.2.2⟩,
                  hpairs.2⟩

theorem checkPinnedFullSourceBundle_digests
    {expected : FullSourceExpectations} {pins : ArtifactPins}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkPinnedFullSourceBundle expected pins gammaRaw stepRaw
        checkpointRaw = true) :
    SHA256.digestByteArray gammaRaw = pins.gammaArtifactSHA256 ∧
      SHA256.digestByteArray stepRaw = pins.stepArtifactSHA256 ∧
      SHA256.digestByteArray checkpointRaw =
        pins.checkpointArtifactSHA256 := by
  rcases checkPinnedFullSourceBundle_sound hcheck with
    ⟨_, _, _, _, _, hpins⟩
  exact hpins.2

/-- A semantic gamma substitution cannot survive unchanged external pins,
even if an attacker also repairs the checkpoint file's internal gamma link. -/
theorem checkPinnedFullSourceBundle_rejectsGammaSubstitution
    {expected : FullSourceExpectations} {pins : ArtifactPins}
    {gammaRaw stepRaw checkpointRaw : ByteArray}
    (hchanged :
      SHA256.digestByteArray gammaRaw ≠ pins.gammaArtifactSHA256) :
    checkPinnedFullSourceBundle expected pins gammaRaw stepRaw
      checkpointRaw = false := by
  apply Bool.eq_false_of_not_eq_true
  intro hcheck
  exact hchanged (checkPinnedFullSourceBundle_digests hcheck).1

end SparkInterval.Dirichlet.CompletedFactorWire
