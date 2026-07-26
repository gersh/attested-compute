/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDiskContainmentWire

/-!
# Kernel-checked RealDisk106 containment-wire KATs

The positive frame is tight:

```
inner = disk(center = 1 + 1/2, radius = 1/2)
outer = disk(center = 1 + 0,   radius = 1)
```

The centre distance and radius difference are both `1/2`.  Thus the positive
test exercises a nonzero low centre limb and equality in the decisive
squared containment inequality.  Every test below is elaborated by Lean's
ordinary kernel path; this file does not use `native_decide`.
-/

set_option autoImplicit false
set_option maxRecDepth 10000

namespace SparkInterval.Tests.ComplexDiskContainmentWire

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk.Containment.Wire
open SparkInterval.Certificate

/-! ## Named binary64 words and bytes -/

def zeroBits : Nat := 0x0000000000000000
def halfBits : Nat := 0x3fe0000000000000
def quarterBits : Nat := 0x3fd0000000000000
def oneBits : Nat := 0x3ff0000000000000
def minusHalfBits : Nat := 0xbfe0000000000000
def negativeZeroBits : Nat := 0x8000000000000000
def positiveInfinityBits : Nat := 0x7ff0000000000000
def quietNaNBits : Nat := 0x7ff8000000000000
def minimumSubnormalBits : Nat := 0x0000000000000001
def endianReversedOneBits : Nat := 0x000000000000f03f

def minimumSubnormal : ℚ := 1 / (2 ^ 1074 : ℚ)

def zeroBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

def halfBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xe0, 0x3f]

def quarterBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xd0, 0x3f]

def oneBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x3f]

def endianReversedOneBytes : List UInt8 :=
  [0x3f, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

def minusHalfBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xe0, 0xbf]

def negativeZeroBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80]

def positiveInfinityBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x7f]

def quietNaNBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf8, 0x7f]

def minimumSubnormalBytes : List UInt8 :=
  [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

/-! ## Tight positive frame with a nonzero low limb -/

def sample : ComplexDisk.ContainmentCertificate := {
  inner := ⟨3 / 2, 0, 1 / 2⟩
  outer := ⟨1, 0, 1⟩
}

def sampleRaw : RawContainmentPair := {
  inner := ⟨oneBits, halfBits, halfBits⟩
  outer := ⟨oneBits, zeroBits, oneBits⟩
}

theorem sampleRaw_decode :
    sampleRaw.decode = some sample := by
  norm_num [sampleRaw, sample, RawContainmentPair.decode,
    RawRealDisk106.decode, zeroBits, halfBits, oneBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]

theorem sample_tight :
    ComplexDisk.centerDistanceSq sample.inner sample.outer =
      (sample.outer.radius - sample.inner.radius) ^ 2 := by
  norm_num [sample, ComplexDisk.centerDistanceSq]

theorem sampleRaw_check : sampleRaw.check = true := by
  rw [RawContainmentPair.check, sampleRaw_decode]
  norm_num [ComplexDisk.ContainmentCertificate.check,
    ComplexDisk.ContainmentCertificate.WellFormed, sample,
    ComplexDisk.centerDistanceSq]

def sampleBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ halfBytes ++
  oneBytes ++ zeroBytes ++ oneBytes

theorem sampleBytes_parse :
    parseRawContainmentPair sampleBytes = some sampleRaw := by
  rfl

theorem sampleBytes_check :
    checkRawContainmentBytes sampleBytes = true := by
  rw [checkRawContainmentBytes, sampleBytes_parse]
  exact sampleRaw_check

theorem sampleBytes_length :
    sampleBytes.length = rawContainmentPairByteSize :=
  checkRawContainmentBytes_length sampleBytes_check

/-! ## Arithmetic mutations -/

/-- Mutating only the inner low limb moves its exact centre outside the
available outer-radius margin. -/
def centerMutationRaw : RawContainmentPair := {
  sampleRaw with inner := ⟨oneBits, oneBits, halfBits⟩
}

def centerMutationBytes : List UInt8 :=
  oneBytes ++ oneBytes ++ halfBytes ++
  oneBytes ++ zeroBytes ++ oneBytes

theorem centerMutationBytes_parse :
    parseRawContainmentPair centerMutationBytes =
      some centerMutationRaw := by
  rfl

theorem centerMutationBytes_rejected :
    checkRawContainmentBytes centerMutationBytes = false := by
  rw [checkRawContainmentBytes, centerMutationBytes_parse]
  norm_num [RawContainmentPair.check, RawContainmentPair.decode,
    RawRealDisk106.decode, centerMutationRaw, sampleRaw,
    zeroBits, halfBits, oneBits, Binary64.decodeFinite,
    Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold,
    ComplexDisk.ContainmentCertificate.check,
    ComplexDisk.ContainmentCertificate.WellFormed,
    ComplexDisk.centerDistanceSq]

/-- The outer radius is smaller than the inner radius. -/
def radiusOrderMutationRaw : RawContainmentPair := {
  sampleRaw with outer := ⟨oneBits, zeroBits, quarterBits⟩
}

def radiusOrderMutationBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ halfBytes ++
  oneBytes ++ zeroBytes ++ quarterBytes

theorem radiusOrderMutationBytes_parse :
    parseRawContainmentPair radiusOrderMutationBytes =
      some radiusOrderMutationRaw := by
  rfl

theorem radiusOrderMutationBytes_rejected :
    checkRawContainmentBytes radiusOrderMutationBytes = false := by
  rw [checkRawContainmentBytes, radiusOrderMutationBytes_parse]
  norm_num [RawContainmentPair.check, RawContainmentPair.decode,
    RawRealDisk106.decode, radiusOrderMutationRaw, sampleRaw,
    zeroBits, quarterBits, halfBits, oneBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold,
    ComplexDisk.ContainmentCertificate.check,
    ComplexDisk.ContainmentCertificate.WellFormed,
    ComplexDisk.centerDistanceSq]

def negativeRadiusMutationRaw : RawContainmentPair := {
  sampleRaw with inner := ⟨oneBits, halfBits, minusHalfBits⟩
}

def negativeRadiusMutationBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ minusHalfBytes ++
  oneBytes ++ zeroBytes ++ oneBytes

theorem negativeRadiusMutationBytes_parse :
    parseRawContainmentPair negativeRadiusMutationBytes =
      some negativeRadiusMutationRaw := by
  rfl

theorem negativeRadiusMutationBytes_rejected :
    checkRawContainmentBytes negativeRadiusMutationBytes = false := by
  rw [checkRawContainmentBytes, negativeRadiusMutationBytes_parse]
  norm_num [RawContainmentPair.check, RawContainmentPair.decode,
    RawRealDisk106.decode, negativeRadiusMutationRaw, sampleRaw,
    zeroBits, minusHalfBits, halfBits, oneBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold,
    ComplexDisk.ContainmentCertificate.check,
    ComplexDisk.ContainmentCertificate.WellFormed,
    ComplexDisk.centerDistanceSq]

/-! ## Decode rejection: infinity and NaN -/

def infinityMutationRaw : RawContainmentPair := {
  sampleRaw with inner := ⟨positiveInfinityBits, halfBits, halfBits⟩
}

def infinityMutationBytes : List UInt8 :=
  positiveInfinityBytes ++ halfBytes ++ halfBytes ++
  oneBytes ++ zeroBytes ++ oneBytes

theorem infinityMutationBytes_parse :
    parseRawContainmentPair infinityMutationBytes =
      some infinityMutationRaw := by
  rfl

theorem infinityMutationBytes_rejected :
    checkRawContainmentBytes infinityMutationBytes = false := by
  rfl

def nanMutationRaw : RawContainmentPair := {
  sampleRaw with outer := ⟨oneBits, quietNaNBits, oneBits⟩
}

def nanMutationBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ halfBytes ++
  oneBytes ++ quietNaNBytes ++ oneBytes

theorem nanMutationBytes_parse :
    parseRawContainmentPair nanMutationBytes = some nanMutationRaw := by
  rfl

theorem nanMutationBytes_rejected :
    checkRawContainmentBytes nanMutationBytes = false := by
  rfl

/-! ## Signed zero and minimum-subnormal acceptance -/

def signedZeroRaw : RawContainmentPair := {
  sampleRaw with outer := ⟨oneBits, negativeZeroBits, oneBits⟩
}

def signedZeroBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ halfBytes ++
  oneBytes ++ negativeZeroBytes ++ oneBytes

theorem signedZeroBytes_parse_preserved :
    parseRawContainmentPair signedZeroBytes = some signedZeroRaw := by
  rfl

theorem signedZeroRaw_decode :
    signedZeroRaw.decode = some sample := by
  norm_num [signedZeroRaw, sampleRaw, sample,
    RawContainmentPair.decode, RawRealDisk106.decode,
    zeroBits, halfBits, oneBits, negativeZeroBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]

theorem signedZeroBytes_check :
    checkRawContainmentBytes signedZeroBytes = true := by
  rw [checkRawContainmentBytes, signedZeroBytes_parse_preserved]
  change signedZeroRaw.check = true
  rw [RawContainmentPair.check, signedZeroRaw_decode]
  norm_num [ComplexDisk.ContainmentCertificate.check,
    ComplexDisk.ContainmentCertificate.WellFormed, sample,
    ComplexDisk.centerDistanceSq]

/-! ## Complete framed-transform checks -/

def twoFrameStream : List (List UInt8) :=
  [sampleBytes, signedZeroBytes]

theorem twoFrameStream_check :
    checkRawContainmentByteFrames 2 twoFrameStream = true := by
  simp [checkRawContainmentByteFrames, twoFrameStream,
    sampleBytes_check, signedZeroBytes_check]

theorem twoFrameStream_wrong_count_rejected :
    checkRawContainmentByteFrames 3 twoFrameStream = false := by
  simp [checkRawContainmentByteFrames, twoFrameStream]

theorem twoFrameStream_bad_frame_rejected :
    checkRawContainmentByteFrames
      2 [sampleBytes, centerMutationBytes] = false := by
  simp [checkRawContainmentByteFrames, sampleBytes_check,
    centerMutationBytes_rejected]

def flatTwoFrameArtifact : List UInt8 :=
  sampleBytes ++ signedZeroBytes

theorem flatTwoFrameArtifact_frames :
    rawContainmentArtifactFrames flatTwoFrameArtifact =
      twoFrameStream := by
  rfl

theorem flatTwoFrameArtifact_check :
    checkRawContainmentArtifactBytes 2 flatTwoFrameArtifact = true := by
  simpa [checkRawContainmentArtifactBytes,
    flatTwoFrameArtifact_frames] using twoFrameStream_check

theorem flatTwoFrameArtifact_wrong_count_rejected :
    checkRawContainmentArtifactBytes 3 flatTwoFrameArtifact = false := by
  simpa [checkRawContainmentArtifactBytes,
    flatTwoFrameArtifact_frames] using
      twoFrameStream_wrong_count_rejected

theorem flatTwoFrameArtifact_truncated_rejected :
    checkRawContainmentArtifactBytes
      2 flatTwoFrameArtifact.dropLast = false := by
  have hframes :
      rawContainmentArtifactFrames flatTwoFrameArtifact.dropLast =
        [sampleBytes, signedZeroBytes.dropLast] := by
    rfl
  have htruncated :
      checkRawContainmentBytes signedZeroBytes.dropLast = false := by
    rfl
  simp [checkRawContainmentArtifactBytes,
    hframes, checkRawContainmentByteFrames,
    sampleBytes_check, htruncated]

def minimumSubnormalSample :
    ComplexDisk.ContainmentCertificate := {
  inner := ⟨minimumSubnormal, 0, 0⟩
  outer := ⟨minimumSubnormal, 0, 0⟩
}

def minimumSubnormalRaw : RawContainmentPair := {
  inner := ⟨zeroBits, minimumSubnormalBits, zeroBits⟩
  outer := ⟨zeroBits, minimumSubnormalBits, zeroBits⟩
}

def minimumSubnormalFrame : List UInt8 :=
  zeroBytes ++ minimumSubnormalBytes ++ zeroBytes ++
  zeroBytes ++ minimumSubnormalBytes ++ zeroBytes

theorem minimumSubnormalRaw_decode :
    minimumSubnormalRaw.decode = some minimumSubnormalSample := by
  norm_num [minimumSubnormalRaw, minimumSubnormalSample,
    minimumSubnormal, RawContainmentPair.decode,
    RawRealDisk106.decode, zeroBits, minimumSubnormalBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]
  rfl

theorem minimumSubnormalFrame_parse :
    parseRawContainmentPair minimumSubnormalFrame =
      some minimumSubnormalRaw := by
  rfl

theorem minimumSubnormalFrame_check :
    checkRawContainmentBytes minimumSubnormalFrame = true := by
  rw [checkRawContainmentBytes, minimumSubnormalFrame_parse]
  change minimumSubnormalRaw.check = true
  rw [RawContainmentPair.check, minimumSubnormalRaw_decode]
  norm_num [ComplexDisk.ContainmentCertificate.check,
    ComplexDisk.ContainmentCertificate.WellFormed,
    minimumSubnormalSample, ComplexDisk.centerDistanceSq]

/-! ## Endianness and exact framing -/

def endianMutationRaw : RawContainmentPair := {
  sampleRaw with
  outer := ⟨oneBits, zeroBits, endianReversedOneBits⟩
}

def endianMutationBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ halfBytes ++
  oneBytes ++ zeroBytes ++ endianReversedOneBytes

/-- Reversing one field is parsed as a different little-endian word, not
silently interpreted using host or big-endian order. -/
theorem endianMutationBytes_parse_wrong_value :
    parseRawContainmentPair endianMutationBytes =
      some endianMutationRaw := by
  rfl

theorem endianMutation_differs : endianMutationRaw ≠ sampleRaw := by
  norm_num [endianMutationRaw, sampleRaw, endianReversedOneBits, oneBits]

def endianRadius : ℚ := 61503 / (2 ^ 1074 : ℚ)

def endianMutation : ComplexDisk.ContainmentCertificate := {
  sample with outer := ⟨1, 0, endianRadius⟩
}

theorem endianMutationRaw_decode :
    endianMutationRaw.decode = some endianMutation := by
  norm_num [endianMutationRaw, endianMutation, endianRadius, sampleRaw,
    sample, RawContainmentPair.decode, RawRealDisk106.decode,
    zeroBits, halfBits, oneBits, endianReversedOneBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]
  rfl

set_option exponentiation.threshold 1200 in
theorem endianRadius_lt_half : endianRadius < (1 / 2 : ℚ) := by
  norm_num [endianRadius]

theorem endianMutation_not_wellFormed :
    ¬ endianMutation.WellFormed := by
  intro hwellFormed
  rcases hwellFormed with ⟨_, _, hradiusOrder, _⟩
  have : (1 / 2 : ℚ) ≤ endianRadius := by
    dsimp [endianMutation, sample] at hradiusOrder
    linarith
  exact (not_le_of_gt endianRadius_lt_half) this

theorem endianMutationBytes_rejected :
    checkRawContainmentBytes endianMutationBytes = false := by
  rw [checkRawContainmentBytes, endianMutationBytes_parse_wrong_value]
  change endianMutationRaw.check = false
  rw [RawContainmentPair.check, endianMutationRaw_decode]
  simp [ComplexDisk.ContainmentCertificate.check,
    endianMutation_not_wellFormed]

theorem truncated_rejected :
    checkRawContainmentBytes sampleBytes.dropLast = false := by
  rfl

theorem trailing_byte_rejected :
    checkRawContainmentBytes (sampleBytes ++ [0x00]) = false := by
  rfl

/-! ## Semantic live consumer -/

theorem sampleBytes_outer_contains_inner_center :
    sample.outer.ContainsComplex sample.inner.center := by
  apply checkedBytes_outer_contains sampleBytes_check sampleBytes_parse
    sampleRaw_decode
  norm_num [sample, ComplexDisk.ContainsComplex]

theorem sampleBytes_semantic_package :
    ∃ raw : RawContainmentPair,
      ∃ certificate : ComplexDisk.ContainmentCertificate,
        parseRawContainmentPair sampleBytes = some raw ∧
        raw.decode = some certificate ∧
        certificate.WellFormed ∧
        ∀ value : ℂ,
          certificate.inner.ContainsComplex value →
          certificate.outer.ContainsComplex value :=
  checkRawContainmentBytes_semantic sampleBytes_check

#print axioms RawContainmentPair.check_sound
#print axioms RawContainmentPair.outer_contains_of_inner_contains
#print axioms parseRawContainmentPair_length
#print axioms checkRawContainmentBytes_sound
#print axioms checkedBytes_outer_contains
#print axioms checkRawContainmentBytes_semantic
#print axioms checkRawContainmentByteFrames_sound
#print axioms checkRawContainmentByteFrames_semantic
#print axioms sampleBytes_check
#print axioms sample_tight
#print axioms centerMutationBytes_rejected
#print axioms radiusOrderMutationBytes_rejected
#print axioms negativeRadiusMutationBytes_rejected
#print axioms infinityMutationBytes_rejected
#print axioms nanMutationBytes_rejected
#print axioms signedZeroBytes_check
#print axioms twoFrameStream_check
#print axioms twoFrameStream_wrong_count_rejected
#print axioms twoFrameStream_bad_frame_rejected
#print axioms flatTwoFrameArtifact_frames
#print axioms flatTwoFrameArtifact_check
#print axioms flatTwoFrameArtifact_wrong_count_rejected
#print axioms flatTwoFrameArtifact_truncated_rejected
#print axioms minimumSubnormalFrame_check
#print axioms endianMutationBytes_rejected
#print axioms truncated_rejected
#print axioms trailing_byte_rejected
#print axioms sampleBytes_outer_contains_inner_center

end SparkInterval.Tests.ComplexDiskContainmentWire
