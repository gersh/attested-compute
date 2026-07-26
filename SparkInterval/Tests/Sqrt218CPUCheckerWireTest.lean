/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Wire

/-!
# Tiny fixed-width Sqrt218 CPU-checker wire tests

This reconstructs the C checker's inclusive-bound-5 KAT using independent,
offset-directed byte writes.  It tests the canonical Lean encoder against
those bytes, then tests exact decoding and representative one-byte
corruptions.  The 600-byte KAT is deliberately not a production replay.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.Sqrt218CPUCheckerWire

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire

private def tinyHeader : Header := {
  version := 2
  flags := 0
  bound := 5
  reusedPrimeBound := 5
  logSeedAt := 30
  logScale := 281_474_976_710_656
  reciprocalScale := 1_073_741_824
  primeCount := 3
  factorRefCount := 3
  factorPairCount := 1
  eventCount := 4
  powerRefCount := 4
  primesOffset := 160
  factorRefsOffset := 400
  factorPairsOffset := 424
  eventsOffset := 440
  powerRefsOffset := 568
  archiveBytes := 600
}

private def primeRow
    (prime witness factorRefIndex factorRefCount gapPairIndex gapPairCount
      powerRefIndex powerRefCount logLower logUpper : Nat) :
    PrimeRecord := {
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

private def eventRow
    (value primeIndex exponent floorSqrt : Nat) : EventRecord := {
  value
  primeIndex
  exponent
  floorSqrt
}

private def tinyImage : ArchiveImage := {
  byteLength := 600
  header := tinyHeader
  primes := [
    primeRow
      2 0 0 0 0 0 0 2
      195_103_586_431_999 195_103_586_572_737,
    primeRow
      3 2 0 1 0 0 2 1
      309_231_868_028_532 309_231_868_693_940,
    primeRow
      5 2 1 2 0 1 3 1
      453_016_498_773_239 453_016_499_054_997
  ]
  factorRefs := [0, 0, 0]
  factorPairs := [{ left := 2, right := 2 }]
  events := [
    eventRow 2 0 1 1,
    eventRow 3 1 1 1,
    eventRow 4 0 2 2,
    eventRow 5 2 1 2
  ]
  powerRefs := [0, 2, 1, 3]
}

/-! ## Independent offset-directed C-KAT construction -/

private def zeroed (size : Nat) : ByteArray :=
  ByteArray.mk (Array.replicate size 0)

private def putBE
    (width : Nat) (raw : ByteArray) (offset value : Nat) : ByteArray :=
  (List.range width).foldl
    (fun bytes index =>
      bytes.set! (offset + index)
        (UInt8.ofNat
          ((value / 256 ^ (width - (index + 1))) % 256)))
    raw

private def putBE16 (raw : ByteArray) (offset value : Nat) : ByteArray :=
  putBE 2 raw offset value

private def putBE32 (raw : ByteArray) (offset value : Nat) : ByteArray :=
  putBE 4 raw offset value

private def putBE64 (raw : ByteArray) (offset value : Nat) : ByteArray :=
  putBE 8 raw offset value

private def putMagic (raw : ByteArray) : ByteArray :=
  (magicBytes.zipIdx).foldl
    (fun bytes entry => bytes.set! entry.2 entry.1)
    raw

private def putPrime
    (raw : ByteArray) (index prime witness factorIndex factorCount
      gapIndex gapCount powerIndex powerCount logLower logUpper : Nat) :
    ByteArray :=
  let offset := 160 + index * 80
  let raw := putBE64 raw offset prime
  let raw := putBE64 raw (offset + 8) witness
  let raw := putBE64 raw (offset + 16) factorIndex
  let raw := putBE32 raw (offset + 24) factorCount
  let raw := putBE32 raw (offset + 28) gapCount
  let raw := putBE64 raw (offset + 32) gapIndex
  let raw := putBE64 raw (offset + 40) powerIndex
  let raw := putBE32 raw (offset + 48) powerCount
  let raw := putBE64 raw (offset + 56) logLower
  putBE64 raw (offset + 64) logUpper

private def putEvent
    (raw : ByteArray) (index value primeIndex exponent floorSqrt : Nat) :
    ByteArray :=
  let offset := 440 + index * 32
  let raw := putBE64 raw offset value
  let raw := putBE64 raw (offset + 8) primeIndex
  let raw := putBE32 raw (offset + 16) exponent
  putBE64 raw (offset + 24) floorSqrt

private def cKatBytes : ByteArray :=
  let raw := putMagic (zeroed 600)
  let raw := putBE16 raw 8 2
  let raw := putBE16 raw 10 160
  let raw := putBE32 raw 12 0
  let raw := putBE64 raw 16 5
  let raw := putBE64 raw 24 5
  let raw := putBE64 raw 32 30
  let raw := putBE64 raw 40 281_474_976_710_656
  let raw := putBE64 raw 48 1_073_741_824
  let raw := putBE64 raw 56 3
  let raw := putBE64 raw 64 3
  let raw := putBE64 raw 72 1
  let raw := putBE64 raw 80 4
  let raw := putBE64 raw 88 4
  let raw := putBE64 raw 96 160
  let raw := putBE64 raw 104 400
  let raw := putBE64 raw 112 424
  let raw := putBE64 raw 120 440
  let raw := putBE64 raw 128 568
  let raw := putBE64 raw 136 600
  let raw :=
    putPrime raw 0 2 0 0 0 0 0 0 2
      195_103_586_431_999 195_103_586_572_737
  let raw :=
    putPrime raw 1 3 2 0 1 0 0 2 1
      309_231_868_028_532 309_231_868_693_940
  let raw :=
    putPrime raw 2 5 2 1 2 0 1 3 1
      453_016_498_773_239 453_016_499_054_997
  let raw := putBE64 raw 400 0
  let raw := putBE64 raw 408 0
  let raw := putBE64 raw 416 0
  let raw := putBE64 raw 424 2
  let raw := putBE64 raw 432 2
  let raw := putEvent raw 0 2 0 1 1
  let raw := putEvent raw 1 3 1 1 1
  let raw := putEvent raw 2 4 0 2 2
  let raw := putEvent raw 3 5 2 1 2
  let raw := putBE64 raw 568 0
  let raw := putBE64 raw 576 2
  let raw := putBE64 raw 584 1
  putBE64 raw 592 3

/- The independent builder agrees with the canonical encoder byte-for-byte. -/
#guard encodeCanonicalArchiveBytes tinyImage = some cKatBytes

/- Header framing is big-endian and starts with the literal format magic. -/
#guard cKatBytes.extract 0 8 = magicBytes.toByteArray
#guard
  cKatBytes.extract 8 16 =
    ([0, 2, 0, 160, 0, 0, 0, 0] : List UInt8).toByteArray
#guard cKatBytes.size = 600

/- The complete fixed-width KAT decodes to the expected typed image. -/
#guard decodeCanonicalArchiveBytes cKatBytes = .ok tinyImage
#guard headerCheck tinyImage

/-! ## Canonical-framing tamper cases -/

private def malformed (raw : ByteArray) : Bool :=
  decide (decodeCanonicalArchiveBytes raw = .error .malformed)

private def fillByte
    (raw : ByteArray) (offset count : Nat) (value : UInt8) : ByteArray :=
  (List.range count).foldl
    (fun bytes index => bytes.set! (offset + index) value)
    raw

/- Literal magic, big-endian version, header width, and flags are binding. -/
#guard malformed (cKatBytes.set! 0 0)
#guard malformed ((cKatBytes.set! 8 2).set! 9 0)
#guard malformed (cKatBytes.set! 11 159)
#guard malformed (cKatBytes.set! 15 1)

/- Every fixed reserved-field class is required to remain zero. -/
#guard malformed (cKatBytes.set! 144 1)
#guard malformed (cKatBytes.set! 152 1)
#guard malformed (cKatBytes.set! 212 1)
#guard malformed (cKatBytes.set! 232 1)
#guard malformed (cKatBytes.set! 460 1)

/- Section offsets must be contiguous, canonical, and checked for u64
overflow before allocating or traversing record lists. -/
#guard malformed (cKatBytes.set! 111 0x91)
#guard malformed (fillByte cKatBytes 56 8 0xff)

/- Exact EOF rejects both a suffix and truncation. -/
#guard malformed (cKatBytes.push 0)
#guard malformed (cKatBytes.extract 0 599)

/- The metatheorems themselves have only Lean's standard logical axioms. -/
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire.encode_decode_exact
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire.decodeCanonicalArchiveBytes_imageUnique
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire.decodeCanonicalArchiveBytes_noAlternateEncoding

end SparkInterval.Tests.Sqrt218CPUCheckerWire
