/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDiskWire

set_option autoImplicit false

namespace SparkInterval.Tests.ComplexDiskWire

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk.Wire

def increasingBytes : List UInt8 :=
  [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]

/-- Byte order is least-significant first. -/
theorem increasingBytes_parse :
    parseU64LE increasingBytes = some 0x0807060504030201 := by
  rfl

/-- Seven bytes are a truncation, not a smaller integer. -/
theorem truncated_word_rejected :
    parseU64LE [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07] = none := by
  rfl

/-- Complete-word parsing never silently ignores a suffix. -/
theorem trailing_word_byte_rejected :
    parseU64LE (increasingBytes ++ [0x09]) = none := by
  rfl

def zeroWordBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

def negativeZeroBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80]

def positiveInfinityBytes : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x7f]

def zeroRaw : ComplexDisk.Raw := ⟨0, 0, 0⟩

def zeroRawBytes : List UInt8 :=
  zeroWordBytes ++ zeroWordBytes ++ zeroWordBytes

theorem zeroRaw_parse : parseRaw zeroRawBytes = some zeroRaw := by
  rfl

/-- Structural parsing rejects the alternate negative-zero spelling, even
though the exact binary64 decoder would map it to rational zero. -/
theorem negativeZeroRaw_rejected :
    parseRaw (negativeZeroBytes ++ zeroWordBytes ++ zeroWordBytes) = none := by
  rfl

theorem truncatedRaw_rejected :
    parseRaw zeroRawBytes.dropLast = none := by
  rfl

theorem trailingRawByte_rejected :
    parseRaw (zeroRawBytes ++ [0x00]) = none := by
  rfl

def zeroRawMul : ComplexDisk.RawMulCertificate := {
  left := zeroRaw
  right := zeroRaw
  output := zeroRaw
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0
  rightCenterNormBoundBits := 0
}

def zeroRawMulBytes : List UInt8 :=
  zeroRawBytes ++ zeroRawBytes ++ zeroRawBytes ++
    zeroWordBytes ++ zeroWordBytes ++ zeroWordBytes

theorem zeroRawMul_parse :
    parseRawMulCertificate zeroRawMulBytes = some zeroRawMul := by
  rfl

theorem zeroRawMul_check : zeroRawMul.check = true := by
  norm_num [zeroRawMul, zeroRaw, ComplexDisk.RawMulCertificate.check,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    ComplexDisk.MulCertificate.check, ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq,
    SparkInterval.Certificate.Binary64.decodeFinite,
    SparkInterval.Certificate.Binary64.wordLimit,
    SparkInterval.Certificate.Binary64.exponentBits,
    SparkInterval.Certificate.Binary64.exponentModulus,
    SparkInterval.Certificate.Binary64.fractionModulus,
    SparkInterval.Certificate.Binary64.exponentAllOnes,
    SparkInterval.Certificate.Binary64.finiteValue,
    SparkInterval.Certificate.Binary64.fractionBits,
    SparkInterval.Certificate.Binary64.signBit,
    SparkInterval.Certificate.Binary64.signThreshold]

theorem zeroRawMulBytes_check : checkRawMulBytes zeroRawMulBytes = true := by
  rw [checkRawMulBytes, zeroRawMul_parse]
  exact zeroRawMul_check

def infinityRawMul : ComplexDisk.RawMulCertificate := {
  zeroRawMul with
  left := ⟨0x7ff0000000000000, 0, 0⟩
}

def infinityRawMulBytes : List UInt8 :=
  positiveInfinityBytes ++ zeroWordBytes ++ zeroWordBytes ++
    zeroRawBytes ++ zeroRawBytes ++
    zeroWordBytes ++ zeroWordBytes ++ zeroWordBytes

/-- Infinity is a well-framed binary64 word, so the structural parser accepts
it and preserves its bits exactly. -/
theorem infinityRawMul_parse :
    parseRawMulCertificate infinityRawMulBytes = some infinityRawMul := by
  rfl

/-- Finiteness is checked at the intended downstream boundary. -/
theorem infinityRawMul_downstream_rejected : infinityRawMul.check = false := by
  rfl

theorem infinityRawMulBytes_rejected :
    checkRawMulBytes infinityRawMulBytes = false := by
  rw [checkRawMulBytes, infinityRawMul_parse]
  exact infinityRawMul_downstream_rejected

/-- Canonical zero applies to auxiliary bound words as well as disk fields. -/
def negativeZeroAuxRawMulBytes : List UInt8 :=
  zeroRawBytes ++ zeroRawBytes ++ zeroRawBytes ++
    negativeZeroBytes ++ zeroWordBytes ++ zeroWordBytes

theorem negativeZeroAuxRawMul_rejected :
    parseRawMulCertificate negativeZeroAuxRawMulBytes = none := by
  rfl

theorem negativeZeroAuxRawMul_check_rejected :
    checkRawMulBytes negativeZeroAuxRawMulBytes = false := by
  rw [checkRawMulBytes, negativeZeroAuxRawMul_rejected]

theorem truncatedRawMul_rejected :
    parseRawMulCertificate zeroRawMulBytes.dropLast = none := by
  rfl

theorem trailingRawMulByte_rejected :
    parseRawMulCertificate (zeroRawMulBytes ++ [0x00]) = none := by
  rfl

#print axioms parseU64LE_eight
#print axioms parseU64LE_length
#print axioms parseRaw_length
#print axioms parseRawMulCertificate_length
#print axioms checkRawMulBytes_sound
#print axioms checkRawMulBytes_length
#print axioms checkedBytes_output_contains_mul
#print axioms increasingBytes_parse
#print axioms zeroRaw_parse
#print axioms zeroRawMul_parse
#print axioms zeroRawMulBytes_check
#print axioms infinityRawMul_downstream_rejected
#print axioms negativeZeroAuxRawMul_rejected

end SparkInterval.Tests.ComplexDiskWire
