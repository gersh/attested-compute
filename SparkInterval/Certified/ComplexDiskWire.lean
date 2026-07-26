/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDisk

/-!
# Canonical little-endian complex-disk certificate parsing

This module closes the byte-to-`Nat` edge for the exact complex-disk
arithmetic certificates.  It uses `List UInt8` deliberately: the parser and
all of its checks reduce in Lean's kernel and do not invoke `Float`, an FFI,
or `native_decide`.

Every binary64 field is encoded as exactly eight bytes, least-significant
byte first.  A `ComplexDisk.Raw` is the concatenation

```
reBits || imBits || radiusBits
```

and a `ComplexDisk.RawMulCertificate` is the 96-byte concatenation

```
left || right || output || centerErrorBoundBits ||
  leftCenterNormBoundBits || rightCenterNormBoundBits.
```

The framing parsers reject truncation and trailing bytes.  They also reject
the binary64 negative-zero word `0x8000000000000000`, making positive zero
the unique wire spelling of rational zero.  They intentionally do *not*
decide finiteness: infinity and NaN encodings are structurally valid words,
then fail closed in `Raw.decode` / `RawMulCertificate.check`.

This is the canonical format for these standalone wire primitives.  It does
not assert that the field order or framing matches any larger production v3
campaign frame; that requires a separate, format-specific refinement proof.
-/

set_option autoImplicit false

namespace SparkInterval.Certified.ComplexDisk.Wire

open SparkInterval.Certificate

/-- Eight bytes in their on-disk, least-significant-first order. -/
structure Bytes8 where
  b0 : UInt8
  b1 : UInt8
  b2 : UInt8
  b3 : UInt8
  b4 : UInt8
  b5 : UInt8
  b6 : UInt8
  b7 : UInt8
  deriving Repr, DecidableEq, BEq

namespace Bytes8

/-- The literal byte sequence represented by an eight-byte block. -/
def toList (bytes : Bytes8) : List UInt8 :=
  [bytes.b0, bytes.b1, bytes.b2, bytes.b3,
    bytes.b4, bytes.b5, bytes.b6, bytes.b7]

/-- Exact unsigned value of a little-endian eight-byte block. -/
def toNat (bytes : Bytes8) : Nat :=
  bytes.b0.toNat +
    256 * bytes.b1.toNat +
    256 ^ 2 * bytes.b2.toNat +
    256 ^ 3 * bytes.b3.toNat +
    256 ^ 4 * bytes.b4.toNat +
    256 ^ 5 * bytes.b5.toNat +
    256 ^ 6 * bytes.b6.toNat +
    256 ^ 7 * bytes.b7.toNat

end Bytes8

/-- Consume exactly one eight-byte block, retaining the unconsumed suffix. -/
def readBytes8 : List UInt8 → Option (Bytes8 × List UInt8)
  | b0 :: b1 :: b2 :: b3 :: b4 :: b5 :: b6 :: b7 :: rest =>
      some (⟨b0, b1, b2, b3, b4, b5, b6, b7⟩, rest)
  | _ => none

/-- Consume one canonical little-endian unsigned 64-bit word. -/
def readU64LE (input : List UInt8) : Option (Nat × List UInt8) := do
  let (bytes, rest) ← readBytes8 input
  pure (bytes.toNat, rest)

/-- Parse one complete eight-byte frame.  The explicit length test and empty
suffix match make both truncation and trailing data fail closed. -/
def parseU64LE (input : List UInt8) : Option Nat :=
  if input.length = 8 then
    match readU64LE input with
    | some (word, []) => some word
    | _ => none
  else
    none

/-- Eight explicitly supplied bytes parse to precisely their positional
little-endian natural number, not a host-endian or runtime integer. -/
@[simp] theorem parseU64LE_eight
    (b0 b1 b2 b3 b4 b5 b6 b7 : UInt8) :
    parseU64LE [b0, b1, b2, b3, b4, b5, b6, b7] =
      some (b0.toNat +
        256 * b1.toNat +
        256 ^ 2 * b2.toNat +
        256 ^ 3 * b3.toNat +
        256 ^ 4 * b4.toNat +
        256 ^ 5 * b5.toNat +
        256 ^ 6 * b6.toNat +
        256 ^ 7 * b7.toNat) := by
  rfl

/-- Successful complete-word parsing proves exact framing length. -/
theorem parseU64LE_length {input : List UInt8} {word : Nat}
    (hparse : parseU64LE input = some word) : input.length = 8 := by
  unfold parseU64LE at hparse
  split at hparse
  · assumption
  · contradiction

/-- The only disallowed structurally valid binary64 spelling.  Rejecting it
ensures that exact rational zero has one canonical disk-certificate wire
representation. -/
def negativeZeroWord : Nat := 2 ^ 63

/-- Consume one binary64 word and reject its noncanonical negative-zero
spelling.  Finiteness remains an arithmetic-decoder obligation. -/
def readCanonicalBinary64LE
    (input : List UInt8) : Option (Nat × List UInt8) := do
  let (word, rest) ← readU64LE input
  if word = negativeZeroWord then none else pure (word, rest)

/-- Consume the canonical 24-byte representation of one raw complex disk. -/
def readRaw (input : List UInt8) : Option (ComplexDisk.Raw × List UInt8) := do
  let (reBits, rest) ← readCanonicalBinary64LE input
  let (imBits, rest) ← readCanonicalBinary64LE rest
  let (radiusBits, rest) ← readCanonicalBinary64LE rest
  pure (⟨reBits, imBits, radiusBits⟩, rest)

/-- Run a prefix parser against an exact-length frame and reject any suffix. -/
def parseExact {α : Type} (size : Nat)
    (parser : List UInt8 → Option (α × List UInt8))
    (input : List UInt8) : Option α :=
  if input.length = size then
    match parser input with
    | some (value, []) => some value
    | _ => none
  else
    none

theorem parseExact_length {α : Type} {size : Nat}
    {parser : List UInt8 → Option (α × List UInt8)}
    {input : List UInt8} {value : α}
    (hparse : parseExact size parser input = some value) :
    input.length = size := by
  unfold parseExact at hparse
  split at hparse
  · assumption
  · contradiction

def rawByteSize : Nat := 24

/-- Parse exactly one standalone complex-disk raw primitive. -/
def parseRaw (input : List UInt8) : Option ComplexDisk.Raw :=
  parseExact rawByteSize readRaw input

theorem parseRaw_length {input : List UInt8} {raw : ComplexDisk.Raw}
    (hparse : parseRaw input = some raw) : input.length = rawByteSize :=
  parseExact_length hparse

/-- Consume the canonical concatenation of one raw multiplication witness. -/
def readRawMulCertificate
    (input : List UInt8) :
    Option (ComplexDisk.RawMulCertificate × List UInt8) := do
  let (left, rest) ← readRaw input
  let (right, rest) ← readRaw rest
  let (output, rest) ← readRaw rest
  let (centerErrorBoundBits, rest) ← readCanonicalBinary64LE rest
  let (leftCenterNormBoundBits, rest) ← readCanonicalBinary64LE rest
  let (rightCenterNormBoundBits, rest) ← readCanonicalBinary64LE rest
  pure ({
    left := left
    right := right
    output := output
    centerErrorBoundBits := centerErrorBoundBits
    leftCenterNormBoundBits := leftCenterNormBoundBits
    rightCenterNormBoundBits := rightCenterNormBoundBits
  }, rest)

def rawMulCertificateByteSize : Nat := 96

/-- Parse exactly one standalone 96-byte raw multiplication certificate. -/
def parseRawMulCertificate
    (input : List UInt8) : Option ComplexDisk.RawMulCertificate :=
  parseExact rawMulCertificateByteSize readRawMulCertificate input

theorem parseRawMulCertificate_length
    {input : List UInt8} {raw : ComplexDisk.RawMulCertificate}
    (hparse : parseRawMulCertificate input = some raw) :
    input.length = rawMulCertificateByteSize :=
  parseExact_length hparse

/-! ## Byte-to-arithmetic composition -/

/-- A single fail-closed checker for the complete standalone byte frame.  A
successful result covers strict framing, canonical signed zero, finite
binary64 decoding, and all exact rational multiplication inequalities. -/
def checkRawMulBytes (input : List UInt8) : Bool :=
  match parseRawMulCertificate input with
  | none => false
  | some raw => raw.check

/-- The typed arithmetic evidence recovered from accepted bytes. -/
def ValidatedRawMulBytes (input : List UInt8) : Prop :=
  ∃ raw : ComplexDisk.RawMulCertificate,
    parseRawMulCertificate input = some raw ∧ raw.Validated

theorem checkRawMulBytes_sound {input : List UInt8}
    (hcheck : checkRawMulBytes input = true) :
    ValidatedRawMulBytes input := by
  unfold checkRawMulBytes at hcheck
  cases hparse : parseRawMulCertificate input with
  | none => simp [hparse] at hcheck
  | some raw =>
      exact ⟨raw, hparse,
        ComplexDisk.RawMulCertificate.check_sound (by
          simpa [hparse] using hcheck)⟩

theorem checkRawMulBytes_length {input : List UInt8}
    (hcheck : checkRawMulBytes input = true) :
    input.length = rawMulCertificateByteSize := by
  rcases checkRawMulBytes_sound hcheck with ⟨raw, hparse, _⟩
  exact parseRawMulCertificate_length hparse

/-- End-to-end arithmetic application for a named parse and decode.  The
byte checker alone supplies the arithmetic check; the two equations merely
name the exact raw and rational structures whose disks contain `x` and `y`.
-/
theorem checkedBytes_output_contains_mul
    {input : List UInt8}
    {raw : ComplexDisk.RawMulCertificate}
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
  exact ComplexDisk.RawMulCertificate.output_contains_mul
    hraw hdecode hx hy

end SparkInterval.Certified.ComplexDisk.Wire
