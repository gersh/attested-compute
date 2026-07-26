/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDiskDD
import SparkInterval.Certified.ComplexDiskWire

/-!
# Fixed-width little-endian wire for DD complex-disk certificates

This module gives `ComplexDisk.DD.RawMulCertificate` a standalone 144-byte
wire:

```
left || right || output || centerErrorBound ||
  leftCenterNormBound || rightCenterNormBound
```

Each disk is:

```
reHi || reLo || imHi || imLo || radius
```

Every field is exactly eight bytes, least-significant byte first.  Truncation
and trailing bytes fail closed.  Both binary64 signed-zero words are accepted
and preserved in the raw record because CUDA may legitimately emit `-0.0`;
the exact decoder in `ComplexDiskDD` maps either spelling to rational zero.
Thus "canonical" here fixes width, field order, and endianness, not a unique
numerical DD decomposition or zero spelling.

The byte checker has no trusted axiom and does not claim that a CUDA
instruction trace, compiler, or physical GPU produced the supplied frame.
-/

set_option autoImplicit false

namespace SparkInterval.Certified.ComplexDisk.DD.Wire

/-- Consume one fixed-width little-endian 16-byte DD pair. -/
def readRawDD
    (input : List UInt8) : Option (RawDD × List UInt8) := do
  let (hiBits, rest) ←
    ComplexDisk.Wire.readU64LE input
  let (loBits, rest) ←
    ComplexDisk.Wire.readU64LE rest
  pure (⟨hiBits, loBits⟩, rest)

/-- Consume one fixed-width little-endian 40-byte DD complex disk. -/
def readRawDisk
    (input : List UInt8) : Option (RawDisk × List UInt8) := do
  let (re, rest) ← readRawDD input
  let (im, rest) ← readRawDD rest
  let (radiusBits, rest) ←
    ComplexDisk.Wire.readU64LE rest
  pure (⟨re, im, radiusBits⟩, rest)

/-- Consume one fixed-width little-endian 144-byte DD certificate. -/
def readRawMulCertificate
    (input : List UInt8) :
    Option (RawMulCertificate × List UInt8) := do
  let (left, rest) ← readRawDisk input
  let (right, rest) ← readRawDisk rest
  let (output, rest) ← readRawDisk rest
  let (centerErrorBoundBits, rest) ←
    ComplexDisk.Wire.readU64LE rest
  let (leftCenterNormBoundBits, rest) ←
    ComplexDisk.Wire.readU64LE rest
  let (rightCenterNormBoundBits, rest) ←
    ComplexDisk.Wire.readU64LE rest
  pure ({
    left
    right
    output
    centerErrorBoundBits
    leftCenterNormBoundBits
    rightCenterNormBoundBits
  }, rest)

def rawDDByteSize : Nat := 16
def rawDiskByteSize : Nat := 40
def rawMulCertificateByteSize : Nat := 144

/-- Parse one complete standalone DD multiplication certificate. -/
def parseRawMulCertificate
    (input : List UInt8) : Option RawMulCertificate :=
  ComplexDisk.Wire.parseExact rawMulCertificateByteSize
    readRawMulCertificate input

theorem parseRawMulCertificate_length
    {input : List UInt8} {raw : RawMulCertificate}
    (hparse : parseRawMulCertificate input = some raw) :
    input.length = rawMulCertificateByteSize :=
  ComplexDisk.Wire.parseExact_length hparse

/-! ## Byte-to-arithmetic composition -/

/-- Strict framing, exact raw words (including signed zero), finite DD
decoding, and all five exact obligation groups in one Boolean. -/
def checkRawMulBytes (input : List UInt8) : Bool :=
  match parseRawMulCertificate input with
  | none => false
  | some raw => raw.check

def ValidatedRawMulBytes (input : List UInt8) : Prop :=
  ∃ raw : RawMulCertificate,
    parseRawMulCertificate input = some raw ∧ raw.Validated

theorem checkRawMulBytes_sound {input : List UInt8}
    (hcheck : checkRawMulBytes input = true) :
    ValidatedRawMulBytes input := by
  unfold checkRawMulBytes at hcheck
  cases hparse : parseRawMulCertificate input with
  | none => simp [hparse] at hcheck
  | some raw =>
      exact ⟨raw, hparse, RawMulCertificate.check_sound (by
        simpa [hparse] using hcheck)⟩

theorem checkRawMulBytes_length {input : List UInt8}
    (hcheck : checkRawMulBytes input = true) :
    input.length = rawMulCertificateByteSize := by
  rcases checkRawMulBytes_sound hcheck with ⟨raw, hparse, _⟩
  exact parseRawMulCertificate_length hparse

/-- End-to-end exact arithmetic theorem for a named parse and decode. -/
theorem checkedBytes_output_contains_mul
    {input : List UInt8}
    {raw : RawMulCertificate}
    {certificate : ComplexDisk.MulCertificate}
    {x y : ℂ}
    (hcheck : checkRawMulBytes input = true)
    (hparse : parseRawMulCertificate input = some raw)
    (hdecode : raw.decode = some certificate)
    (hx : certificate.left.ContainsComplex x)
    (hy : certificate.right.ContainsComplex y) :
    certificate.output.ContainsComplex (x * y) := by
  have hraw : raw.check = true := by
    unfold checkRawMulBytes at hcheck
    simpa [hparse] using hcheck
  exact RawMulCertificate.output_contains_mul hraw hdecode hx hy

end SparkInterval.Certified.ComplexDisk.DD.Wire
