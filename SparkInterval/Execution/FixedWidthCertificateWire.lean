/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFDecoder

/-!
# Small canonical wire primitives for integer certificate streams

Large arithmetic campaigns need arbitrary-precision integer fields but do not
need a general-purpose serialization library in their mathematical boundary.
This module fixes a deliberately simple format:

* naturals are 32-byte unsigned little-endian integers;
* integers are one sign byte followed by a 32-byte magnitude;
* sign `0` means nonnegative and sign `1` means strictly negative;
* negative zero and every other sign byte are rejected; and
* campaign parsers separately enforce exact frame length and a fixed header.

The fixed width makes every accepted value's spelling unique.  All arithmetic
is over Lean `Nat`/`Int`; no host integer, FFI, or native decision procedure
is used.
-/

set_option autoImplicit false

namespace
  SparkInterval.Execution.Architecture.FixedWidthCertificateWire

open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder

/-- Width of every unsigned magnitude in the campaign wire format. -/
def naturalWidth : Nat := 32

/-- Width of a signed integer, including its sign byte. -/
def integerWidth : Nat := naturalWidth + 1

def naturalLimit : Nat := 256 ^ naturalWidth

/-- Read one canonical 256-bit natural. -/
def readNat (bytes : ByteArray) (offset : Nat) : Option Nat :=
  readNatLE? bytes offset naturalWidth

/-- Read one sign/magnitude integer, rejecting negative zero and unknown
signs. -/
def readInt (bytes : ByteArray) (offset : Nat) : Option Int := do
  let sign ← readNatLE? bytes offset 1
  let magnitude ← readNat bytes (offset + 1)
  match sign with
  | 0 => some (magnitude : Int)
  | 1 =>
      if magnitude = 0 then none else some (-((magnitude : Nat) : Int))
  | _ => none

/-- Exact `width`-byte little-endian spelling of a natural.

This function is intentionally total and truncates values outside the width;
use `encodeNatWidth?` at an artifact boundary. -/
def encodeNatWidth (width value : Nat) : List UInt8 :=
  (List.range width).map fun index =>
    UInt8.ofNat ((value / 256 ^ index) % 256)

def encodeNatWidth? (width value : Nat) : Option (List UInt8) :=
  if value < 256 ^ width then some (encodeNatWidth width value) else none

/-- Exact fixed-width little-endian spelling of a 256-bit natural.

Callers use `encodeNat?` when truncation must be rejected. -/
def encodeNat (value : Nat) : List UInt8 :=
  encodeNatWidth naturalWidth value

def encodeNat? (value : Nat) : Option (List UInt8) :=
  encodeNatWidth? naturalWidth value

/-- Canonical sign/magnitude spelling of an integer, when its magnitude fits
the fixed field. -/
def encodeInt? (value : Int) : Option (List UInt8) := do
  let magnitude := value.natAbs
  let magnitudeBytes ← encodeNat? magnitude
  if value < 0 then
    if magnitude = 0 then none
    else some ((1 : UInt8) :: magnitudeBytes)
  else
    some ((0 : UInt8) :: magnitudeBytes)

/-- Compare one bounded slice with fixed bytes. -/
def bytesAtEqual
    (bytes : ByteArray) (offset : Nat) (expected : ByteArray) : Bool :=
  match checkedSlice? bytes offset expected.size with
  | none => false
  | some actual => actual == expected

/-- A prefix reader which exposes the first payload offset. -/
def readFixedPrefix
    (bytes expectedPrefix : ByteArray) : Option Nat :=
  if bytesAtEqual bytes 0 expectedPrefix then
    some expectedPrefix.size
  else
    none

/-- Decode exactly `count` fixed-size rows.  The recursive call decreases
`count`; malformed fields fail immediately. -/
def readRows
    {α : Type}
    (readRow : ByteArray → Nat → Option α)
    (rowSize : Nat)
    (bytes : ByteArray) :
    Nat → Nat → Option (List α)
  | _, 0 => some []
  | offset, count + 1 => do
      let row ← readRow bytes offset
      let rest ← readRows readRow rowSize bytes
        (offset + rowSize) count
      pure (row :: rest)

/-- Canonical list-field bound used by campaign parsers before recursive
decoding.  It prevents a four-byte hostile count from forcing a huge
recursion on a tiny artifact. -/
def countFrameValid
    (bytes : ByteArray) (payloadOffset fixedSize rowSize count : Nat) : Bool :=
  rowSize != 0 &&
    bytes.size = payloadOffset + fixedSize + count * rowSize

end SparkInterval.Execution.Architecture.FixedWidthCertificateWire
