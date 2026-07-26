/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDiskDDWire

/-!
# Kernel-checked KATs for the DD complex-disk wire checker

The positive certificate uses nonzero low limbs:

```
(1 + 1/2 + (2 + 1/2)i) * (3 + 1/2 + (4 + 1/2)i)
  = -6 + (15 + 1/2)i.
```

All radii and centre error are zero.  Mutations separately invalidate the
centre-error obligation, the right-norm obligation, basic radius
nonnegativity, finite decoding, and exact framing.  A signed-zero KAT proves
that a CUDA `-0.0` low limb is preserved in the raw record and accepted with
the same rational meaning as positive zero.
-/

set_option autoImplicit false
set_option maxRecDepth 10000

namespace SparkInterval.Tests.ComplexDiskDDWire

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk.DD
open SparkInterval.Certified.ComplexDisk.DD.Wire
open SparkInterval.Certificate

def zeroBits : Nat := 0x0000000000000000
def halfBits : Nat := 0x3fe0000000000000
def oneBits : Nat := 0x3ff0000000000000
def twoBits : Nat := 0x4000000000000000
def threeBits : Nat := 0x4008000000000000
def fourBits : Nat := 0x4010000000000000
def eightBits : Nat := 0x4020000000000000
def fifteenBits : Nat := 0x402e000000000000
def minusOneBits : Nat := 0xbff0000000000000
def minusFiveBits : Nat := 0xc014000000000000
def minusSixBits : Nat := 0xc018000000000000
def positiveInfinityBits : Nat := 0x7ff0000000000000
def minimumSubnormalBits : Nat := 0x0000000000000001
def endianReversedOneBits : Nat := 0x000000000000f03f

def minimumSubnormal : ℚ := 1 / (2 ^ 1074 : ℚ)

def sample : ComplexDisk.MulCertificate := {
  left := ⟨3 / 2, 5 / 2, 0⟩
  right := ⟨7 / 2, 9 / 2, 0⟩
  output := ⟨-6, 31 / 2, 0⟩
  centerErrorBound := 0
  leftCenterNormBound := 4
  rightCenterNormBound := 8
}

def sampleRaw : RawMulCertificate := {
  left := {
    re := ⟨oneBits, halfBits⟩
    im := ⟨twoBits, halfBits⟩
    radiusBits := zeroBits
  }
  right := {
    re := ⟨threeBits, halfBits⟩
    im := ⟨fourBits, halfBits⟩
    radiusBits := zeroBits
  }
  output := {
    re := ⟨minusSixBits, zeroBits⟩
    im := ⟨fifteenBits, halfBits⟩
    radiusBits := zeroBits
  }
  centerErrorBoundBits := zeroBits
  leftCenterNormBoundBits := fourBits
  rightCenterNormBoundBits := eightBits
}

theorem sampleRaw_decode : sampleRaw.decode = some sample := by
  norm_num [sampleRaw, sample, RawMulCertificate.decode, RawDisk.decode,
    RawDD.decode, zeroBits, halfBits, oneBits, twoBits, threeBits,
    fourBits, eightBits, fifteenBits, minusSixBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem sample_obligationChecks :
    obligationChecks sample =
      ⟨true, true, true, true, true⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound, sample,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem sampleRaw_check : sampleRaw.check = true := by
  rw [RawMulCertificate.check, sampleRaw_decode]
  change (obligationChecks sample).accepted = true
  rw [sample_obligationChecks]
  rfl

/-! ## Canonical little-endian byte KAT -/

def zeroBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

def halfBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xe0, 0x3f]

def oneBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x3f]

def endianReversedOneBytes : List UInt8 :=
  [0x3f, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

def twoBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40]

def threeBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x40]

def fourBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x40]

def eightBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x40]

def fifteenBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2e, 0x40]

def minusOneBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0xbf]

def minusFiveBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x14, 0xc0]

def minusSixBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0xc0]

def positiveInfinityBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x7f]

def minimumSubnormalBytes : List UInt8 :=
  [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

def negativeZeroBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80]

def sampleBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ twoBytes ++ halfBytes ++ zeroBytes ++
  threeBytes ++ halfBytes ++ fourBytes ++ halfBytes ++ zeroBytes ++
  minusSixBytes ++ zeroBytes ++ fifteenBytes ++ halfBytes ++ zeroBytes ++
  zeroBytes ++ fourBytes ++ eightBytes

theorem sampleBytes_parse :
    parseRawMulCertificate sampleBytes = some sampleRaw := by
  rfl

theorem sampleBytes_check :
    checkRawMulBytes sampleBytes = true := by
  rw [checkRawMulBytes, sampleBytes_parse]
  exact sampleRaw_check

theorem sampleBytes_length :
    sampleBytes.length = rawMulCertificateByteSize :=
  checkRawMulBytes_length sampleBytes_check

/-! ## Reason-specific arithmetic mutations -/

def centerMutation : ComplexDisk.MulCertificate := {
  sample with output := ⟨-5, 31 / 2, 0⟩
}

def centerMutationRaw : RawMulCertificate := {
  sampleRaw with
  output := {
    sampleRaw.output with re := ⟨minusFiveBits, zeroBits⟩
  }
}

theorem centerMutationRaw_decode :
    centerMutationRaw.decode = some centerMutation := by
  norm_num [centerMutationRaw, centerMutation, sampleRaw, sample,
    RawMulCertificate.decode, RawDisk.decode, RawDD.decode, zeroBits,
    halfBits, oneBits, twoBits, threeBits, fourBits, eightBits,
    fifteenBits, minusFiveBits, Binary64.decodeFinite,
    Binary64.wordLimit, Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem centerMutation_obligationChecks :
    obligationChecks centerMutation =
      ⟨true, false, true, true, true⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound,
    centerMutation, sample, ComplexDisk.productCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem centerMutation_rejected :
    centerMutationRaw.check = false := by
  rw [RawMulCertificate.check, centerMutationRaw_decode]
  change (obligationChecks centerMutation).accepted = false
  rw [centerMutation_obligationChecks]
  rfl

/-- Only the output low limb changes.  Acceptance changes because DD decoding
uses `hi + lo` rather than silently projecting the high limb. -/
def lowLimbMutation : ComplexDisk.MulCertificate := {
  sample with output := ⟨-11 / 2, 31 / 2, 0⟩
}

def lowLimbMutationRaw : RawMulCertificate := {
  sampleRaw with
  output := {
    sampleRaw.output with re := ⟨minusSixBits, halfBits⟩
  }
}

theorem lowLimbMutationRaw_decode :
    lowLimbMutationRaw.decode = some lowLimbMutation := by
  norm_num [lowLimbMutationRaw, lowLimbMutation, sampleRaw, sample,
    RawMulCertificate.decode, RawDisk.decode, RawDD.decode, zeroBits,
    halfBits, oneBits, twoBits, threeBits, fourBits, eightBits,
    fifteenBits, minusSixBits, Binary64.decodeFinite,
    Binary64.wordLimit, Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem lowLimbMutation_obligationChecks :
    obligationChecks lowLimbMutation =
      ⟨true, false, true, true, true⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound,
    lowLimbMutation, sample, ComplexDisk.productCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem lowLimbMutation_rejected :
    lowLimbMutationRaw.check = false := by
  rw [RawMulCertificate.check, lowLimbMutationRaw_decode]
  change (obligationChecks lowLimbMutation).accepted = false
  rw [lowLimbMutation_obligationChecks]
  rfl

def rightNormMutation : ComplexDisk.MulCertificate := {
  sample with rightCenterNormBound := 1
}

def rightNormMutationRaw : RawMulCertificate := {
  sampleRaw with rightCenterNormBoundBits := oneBits
}

theorem rightNormMutationRaw_decode :
    rightNormMutationRaw.decode = some rightNormMutation := by
  norm_num [rightNormMutationRaw, rightNormMutation, sampleRaw, sample,
    RawMulCertificate.decode, RawDisk.decode, RawDD.decode, zeroBits,
    halfBits, oneBits, twoBits, threeBits, fourBits, fifteenBits,
    minusSixBits, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rightNormMutation_obligationChecks :
    obligationChecks rightNormMutation =
      ⟨true, true, true, false, true⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound,
    rightNormMutation, sample, ComplexDisk.productCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem rightNormMutation_rejected :
    rightNormMutationRaw.check = false := by
  rw [RawMulCertificate.check, rightNormMutationRaw_decode]
  change (obligationChecks rightNormMutation).accepted = false
  rw [rightNormMutation_obligationChecks]
  rfl

def negativeRadiusMutation : ComplexDisk.MulCertificate := {
  sample with left := { sample.left with radius := -1 }
}

def negativeRadiusMutationRaw : RawMulCertificate := {
  sampleRaw with left := { sampleRaw.left with radiusBits := minusOneBits }
}

theorem negativeRadiusMutationRaw_decode :
    negativeRadiusMutationRaw.decode = some negativeRadiusMutation := by
  norm_num [negativeRadiusMutationRaw, negativeRadiusMutation, sampleRaw,
    sample, RawMulCertificate.decode, RawDisk.decode, RawDD.decode,
    zeroBits, halfBits, oneBits, twoBits, threeBits, fourBits, eightBits,
    fifteenBits, minusOneBits, minusSixBits, Binary64.decodeFinite,
    Binary64.wordLimit, Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem negativeRadiusMutation_obligationChecks :
    obligationChecks negativeRadiusMutation =
      ⟨false, true, true, true, true⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound,
    negativeRadiusMutation, sample, ComplexDisk.productCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem negativeRadiusMutation_rejected :
    negativeRadiusMutationRaw.check = false := by
  rw [RawMulCertificate.check, negativeRadiusMutationRaw_decode]
  change (obligationChecks negativeRadiusMutation).accepted = false
  rw [negativeRadiusMutation_obligationChecks]
  rfl

def negativeCenterErrorMutation : ComplexDisk.MulCertificate := {
  sample with centerErrorBound := -1
}

def negativeCenterErrorMutationRaw : RawMulCertificate := {
  sampleRaw with centerErrorBoundBits := minusOneBits
}

theorem negativeCenterErrorMutationRaw_decode :
    negativeCenterErrorMutationRaw.decode =
      some negativeCenterErrorMutation := by
  norm_num [negativeCenterErrorMutationRaw, negativeCenterErrorMutation,
    sampleRaw, sample, RawMulCertificate.decode, RawDisk.decode,
    RawDD.decode, zeroBits, halfBits, oneBits, twoBits, threeBits,
    fourBits, eightBits, fifteenBits, minusOneBits, minusSixBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]

theorem negativeCenterErrorMutation_obligationChecks :
    obligationChecks negativeCenterErrorMutation =
      ⟨false, true, true, true, true⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound,
    negativeCenterErrorMutation, sample,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem negativeCenterErrorMutation_rejected :
    negativeCenterErrorMutationRaw.check = false := by
  rw [RawMulCertificate.check, negativeCenterErrorMutationRaw_decode]
  change (obligationChecks negativeCenterErrorMutation).accepted = false
  rw [negativeCenterErrorMutation_obligationChecks]
  rfl

/-- Only the complete radius inequality fails: all decoded scalars remain
nonnegative and all three squared inequalities still hold. -/
def finalRadiusMutation : ComplexDisk.MulCertificate := {
  sample with left := { sample.left with radius := 1 / 2 }
}

def finalRadiusMutationRaw : RawMulCertificate := {
  sampleRaw with left := { sampleRaw.left with radiusBits := halfBits }
}

theorem finalRadiusMutationRaw_decode :
    finalRadiusMutationRaw.decode = some finalRadiusMutation := by
  norm_num [finalRadiusMutationRaw, finalRadiusMutation, sampleRaw, sample,
    RawMulCertificate.decode, RawDisk.decode, RawDD.decode, zeroBits,
    halfBits, oneBits, twoBits, threeBits, fourBits, eightBits,
    fifteenBits, minusSixBits, Binary64.decodeFinite,
    Binary64.wordLimit, Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem finalRadiusMutation_obligationChecks :
    obligationChecks finalRadiusMutation =
      ⟨true, true, true, true, false⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound,
    finalRadiusMutation, sample, ComplexDisk.productCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem finalRadiusMutation_rejected :
    finalRadiusMutationRaw.check = false := by
  rw [RawMulCertificate.check, finalRadiusMutationRaw_decode]
  change (obligationChecks finalRadiusMutation).accepted = false
  rw [finalRadiusMutation_obligationChecks]
  rfl

/-! ## Decode and framing rejection KATs -/

def minimumSubnormalSample : ComplexDisk.MulCertificate := {
  left := ⟨minimumSubnormal, 0, 0⟩
  right := ⟨0, 0, 0⟩
  output := ⟨0, 0, 0⟩
  centerErrorBound := 0
  leftCenterNormBound := 1
  rightCenterNormBound := 0
}

def minimumSubnormalRaw : RawMulCertificate := {
  left := {
    re := ⟨zeroBits, minimumSubnormalBits⟩
    im := ⟨zeroBits, zeroBits⟩
    radiusBits := zeroBits
  }
  right := {
    re := ⟨zeroBits, zeroBits⟩
    im := ⟨zeroBits, zeroBits⟩
    radiusBits := zeroBits
  }
  output := {
    re := ⟨zeroBits, zeroBits⟩
    im := ⟨zeroBits, zeroBits⟩
    radiusBits := zeroBits
  }
  centerErrorBoundBits := zeroBits
  leftCenterNormBoundBits := oneBits
  rightCenterNormBoundBits := zeroBits
}

theorem minimumSubnormalDD_decode :
    (RawDD.mk zeroBits minimumSubnormalBits).decode =
      some minimumSubnormal := by
  norm_num [RawDD.decode, zeroBits, minimumSubnormalBits,
    minimumSubnormal, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]
  rfl

theorem minimumSubnormalRaw_decode :
    minimumSubnormalRaw.decode = some minimumSubnormalSample := by
  norm_num [minimumSubnormalRaw, minimumSubnormalSample,
    minimumSubnormal, RawMulCertificate.decode, RawDisk.decode,
    RawDD.decode, zeroBits, oneBits, minimumSubnormalBits,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]
  rfl

theorem minimumSubnormal_obligationChecks :
    obligationChecks minimumSubnormalSample =
      ⟨true, true, true, true, true⟩ := by
  norm_num [obligationChecks, BasicBounds, CenterErrorBound,
    LeftCenterNormBound, RightCenterNormBound, RadiusBound,
    minimumSubnormalSample, minimumSubnormal,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]
  apply inv_le_one_of_one_le₀
  apply one_le_pow₀
  apply one_le_pow₀
  norm_num

theorem minimumSubnormalRaw_check :
    minimumSubnormalRaw.check = true := by
  rw [RawMulCertificate.check, minimumSubnormalRaw_decode]
  change (obligationChecks minimumSubnormalSample).accepted = true
  rw [minimumSubnormal_obligationChecks]
  rfl

def minimumSubnormalBytesFrame : List UInt8 :=
  zeroBytes ++ minimumSubnormalBytes ++ zeroBytes ++ zeroBytes ++ zeroBytes ++
  zeroBytes ++ zeroBytes ++ zeroBytes ++ zeroBytes ++ zeroBytes ++
  zeroBytes ++ zeroBytes ++ zeroBytes ++ zeroBytes ++ zeroBytes ++
  zeroBytes ++ oneBytes ++ zeroBytes

theorem minimumSubnormalBytes_parse :
    parseRawMulCertificate minimumSubnormalBytesFrame =
      some minimumSubnormalRaw := by
  rfl

theorem minimumSubnormalBytes_check :
    checkRawMulBytes minimumSubnormalBytesFrame = true := by
  rw [checkRawMulBytes, minimumSubnormalBytes_parse]
  exact minimumSubnormalRaw_check

def infinityMutationRaw : RawMulCertificate := {
  sampleRaw with
  left := {
    sampleRaw.left with
    re := ⟨positiveInfinityBits, halfBits⟩
  }
}

theorem infinityMutation_decode_rejected :
    infinityMutationRaw.decode = none := by
  rfl

theorem infinityMutation_rejected :
    infinityMutationRaw.check = false := by
  rw [RawMulCertificate.check, infinityMutation_decode_rejected]

def centerMutationBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ twoBytes ++ halfBytes ++ zeroBytes ++
  threeBytes ++ halfBytes ++ fourBytes ++ halfBytes ++ zeroBytes ++
  minusFiveBytes ++ zeroBytes ++ fifteenBytes ++ halfBytes ++ zeroBytes ++
  zeroBytes ++ fourBytes ++ eightBytes

theorem centerMutationBytes_parse :
    parseRawMulCertificate centerMutationBytes =
      some centerMutationRaw := by
  rfl

theorem centerMutationBytes_rejected :
    checkRawMulBytes centerMutationBytes = false := by
  rw [checkRawMulBytes, centerMutationBytes_parse]
  exact centerMutation_rejected

def lowLimbMutationBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ twoBytes ++ halfBytes ++ zeroBytes ++
  threeBytes ++ halfBytes ++ fourBytes ++ halfBytes ++ zeroBytes ++
  minusSixBytes ++ halfBytes ++ fifteenBytes ++ halfBytes ++ zeroBytes ++
  zeroBytes ++ fourBytes ++ eightBytes

theorem lowLimbMutationBytes_parse :
    parseRawMulCertificate lowLimbMutationBytes =
      some lowLimbMutationRaw := by
  rfl

theorem lowLimbMutationBytes_rejected :
    checkRawMulBytes lowLimbMutationBytes = false := by
  rw [checkRawMulBytes, lowLimbMutationBytes_parse]
  exact lowLimbMutation_rejected

def endianReversedMutationRaw : RawMulCertificate := {
  sampleRaw with
  left := {
    sampleRaw.left with
    re := ⟨endianReversedOneBits, halfBits⟩
  }
}

def endianReversedMutationBytes : List UInt8 :=
  endianReversedOneBytes ++
    halfBytes ++ twoBytes ++ halfBytes ++ zeroBytes ++
  threeBytes ++ halfBytes ++ fourBytes ++ halfBytes ++ zeroBytes ++
  minusSixBytes ++ zeroBytes ++ fifteenBytes ++ halfBytes ++ zeroBytes ++
  zeroBytes ++ fourBytes ++ eightBytes

/-- Reversing one field is not silently interpreted as big endian: the exact
little-endian parser preserves the resulting, different word. -/
theorem endianReversedMutationBytes_parse_wrong_value :
    parseRawMulCertificate endianReversedMutationBytes =
      some endianReversedMutationRaw := by
  rfl

theorem endianReversedMutation_differs :
    endianReversedMutationRaw ≠ sampleRaw := by
  decide

def negativeZeroLimbRaw : RawMulCertificate := {
  sampleRaw with
  output := {
    sampleRaw.output with re := ⟨minusSixBits, 0x8000000000000000⟩
  }
}

def negativeZeroLimbBytes : List UInt8 :=
  oneBytes ++ halfBytes ++ twoBytes ++ halfBytes ++ zeroBytes ++
  threeBytes ++ halfBytes ++ fourBytes ++ halfBytes ++ zeroBytes ++
  minusSixBytes ++ negativeZeroBytes ++
    fifteenBytes ++ halfBytes ++ zeroBytes ++
  zeroBytes ++ fourBytes ++ eightBytes

theorem negativeZeroLimb_parse_preserved :
    parseRawMulCertificate negativeZeroLimbBytes =
      some negativeZeroLimbRaw := by
  rfl

theorem negativeZeroLimb_decode :
    negativeZeroLimbRaw.decode = some sample := by
  norm_num [negativeZeroLimbRaw, sampleRaw, sample,
    RawMulCertificate.decode, RawDisk.decode, RawDD.decode, zeroBits,
    halfBits, oneBits, twoBits, threeBits, fourBits, eightBits,
    fifteenBits, minusSixBits, Binary64.decodeFinite,
    Binary64.wordLimit, Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem negativeZeroLimb_check_accepted :
    checkRawMulBytes negativeZeroLimbBytes = true := by
  rw [checkRawMulBytes, negativeZeroLimb_parse_preserved]
  change negativeZeroLimbRaw.check = true
  rw [RawMulCertificate.check, negativeZeroLimb_decode]
  change (obligationChecks sample).accepted = true
  rw [sample_obligationChecks]
  rfl

theorem truncated_rejected :
    checkRawMulBytes sampleBytes.dropLast = false := by
  rfl

theorem trailing_byte_rejected :
    checkRawMulBytes (sampleBytes ++ [0x00]) = false := by
  rfl

/-! ## Semantic live consumer -/

theorem sampleBytes_output_contains_center_product :
    sample.output.ContainsComplex
      (sample.left.center * sample.right.center) := by
  apply checkedBytes_output_contains_mul sampleBytes_check sampleBytes_parse
    sampleRaw_decode
  · norm_num [sample, ComplexDisk.ContainsComplex]
  · norm_num [sample, ComplexDisk.ContainsComplex]

#print axioms obligationChecks_accepted_iff
#print axioms fiveObligations_iff_wellFormed
#print axioms RawMulCertificate.check_sound
#print axioms RawMulCertificate.output_contains_mul
#print axioms parseRawMulCertificate_length
#print axioms checkRawMulBytes_sound
#print axioms checkedBytes_output_contains_mul
#print axioms sampleBytes_check
#print axioms centerMutationBytes_rejected
#print axioms lowLimbMutationBytes_rejected
#print axioms rightNormMutation_rejected
#print axioms negativeRadiusMutation_rejected
#print axioms negativeCenterErrorMutation_rejected
#print axioms finalRadiusMutation_rejected
#print axioms minimumSubnormalBytes_check
#print axioms infinityMutation_rejected
#print axioms endianReversedMutationBytes_parse_wrong_value
#print axioms endianReversedMutation_differs
#print axioms negativeZeroLimb_check_accepted
#print axioms sampleBytes_output_contains_center_product

end SparkInterval.Tests.ComplexDiskDDWire
