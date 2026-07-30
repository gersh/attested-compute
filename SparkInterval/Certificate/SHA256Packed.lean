/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256Chunked

/-!
# Packed-natural byte sources

`SHA256.ByteSource.ofByteArray` reads bytes with `ByteArray.get!`.  That is the
right production implementation, but in the Lean *kernel* an `Array` is a
structure over a linked list, so `get!` at index `i` costs `i` reduction
steps.  Hashing an `n`-byte literal therefore costs `Θ(n²)` steps, and the
term that reduction builds exceeds the build's `-M8192` cap well before the
sizes this repository's attestation evidence uses.  Measured with the
byte-array source and the chunk splitting of `SHA256Chunked`, a 1 111-byte
message fails at every chunk size tried: the late chunks are the ones that
die, because their byte indices are the largest.

This file supplies the other representation.  A byte string is packed
big-endian into a single natural number, and the source reads byte `i` with

```text
(value >>> (8 * (byteCount - 1 - i))) &&& 255
```

`Nat.shiftRight` and `Nat.land` are both GMP-accelerated kernel primitives, so
each byte costs one big-integer shift and one mask rather than a list walk.

**The packing is not trusted.**  `packedByteSource_realizes` proves that a
packed source realizes exactly the byte list it was built from, which is the
hypothesis `SHA256.hashSource_eq_hashBytes_of_realizes` needs.  So a digest
computed through a packed source is, as a Lean theorem, the digest of those
bytes under the linked-list reference implementation.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate.SHA256

/-- Big-endian packing of a byte list into one natural number.

`packBytes [0x41, 0x42] = 0x4142`. -/
def packBytes : List Nat → Nat
  | [] => 0
  | byte :: rest => byte * 256 ^ rest.length + packBytes rest

/-- A byte list all of whose entries are genuine bytes packs below the
corresponding power of 256.  This is what makes the leading digit
recoverable. -/
theorem packBytes_lt {bytes : List Nat} (hbytes : ∀ b ∈ bytes, b < 256) :
    packBytes bytes < 256 ^ bytes.length := by
  induction bytes with
  | nil => simp [packBytes]
  | cons byte rest ih =>
      have hbyte : byte < 256 := hbytes byte (by simp)
      have hrest : packBytes rest < 256 ^ rest.length :=
        ih fun b hb => hbytes b (by simp [hb])
      have hpos : 0 < 256 ^ rest.length := by positivity
      simp only [packBytes, List.length_cons]
      calc byte * 256 ^ rest.length + packBytes rest
          < byte * 256 ^ rest.length + 256 ^ rest.length := by omega
        _ = (byte + 1) * 256 ^ rest.length := by ring
        _ ≤ 256 * 256 ^ rest.length :=
              Nat.mul_le_mul_right _ (by omega)
        _ = 256 ^ (rest.length + 1) := by ring

/-- Base-256 digit extraction recovers the original bytes, most significant
first. -/
theorem packBytes_digit {bytes : List Nat} (hbytes : ∀ b ∈ bytes, b < 256) :
    ∀ index, index < bytes.length →
      packBytes bytes / 256 ^ (bytes.length - 1 - index) % 256 =
        bytes.getD index 0 := by
  induction bytes with
  | nil => intro index hindex; simp at hindex
  | cons byte rest ih =>
      intro index hindex
      have hbyte : byte < 256 := hbytes byte (by simp)
      have hrest : packBytes rest < 256 ^ rest.length :=
        packBytes_lt fun b hb => hbytes b (by simp [hb])
      have hpos : 0 < 256 ^ rest.length := by positivity
      match index with
      | 0 =>
          simp only [List.length_cons, Nat.add_sub_cancel, Nat.sub_zero,
            packBytes, List.getD_cons_zero]
          rw [Nat.mul_comm byte, Nat.mul_add_div hpos,
            Nat.div_eq_of_lt hrest, Nat.add_zero, Nat.mod_eq_of_lt hbyte]
      | index + 1 =>
          have hindex' : index < rest.length := by
            simpa using hindex
          have hshift : rest.length + 1 - 1 - (index + 1) =
              rest.length - 1 - index := by omega
          -- The exponent the recursive call uses.
          set shift := rest.length - 1 - index with hshiftdef
          have hle : shift + 1 ≤ rest.length := by omega
          obtain ⟨gap, hgap⟩ : ∃ gap, rest.length = shift + (gap + 1) :=
            ⟨rest.length - shift - 1, by omega⟩
          have hsplit : (256 : Nat) ^ rest.length =
              256 ^ (gap + 1) * 256 ^ shift := by
            rw [hgap, Nat.pow_add]; ring
          have hshiftpos : 0 < (256 : Nat) ^ shift :=
            by positivity
          simp only [List.length_cons, packBytes, hshift, List.getD_cons_succ]
          rw [hsplit]
          rw [show byte * (256 ^ (gap + 1) * 256 ^ shift) + packBytes rest =
              packBytes rest + byte * 256 ^ (gap + 1) * 256 ^ shift by ring]
          rw [Nat.add_mul_div_right _ _ hshiftpos]
          have hdvd : (256 : Nat) ∣ byte * 256 ^ (gap + 1) := by
            refine Dvd.dvd.mul_left ?_ byte
            exact dvd_pow_self 256 (Nat.succ_ne_zero gap)
          obtain ⟨multiple, hmultiple⟩ := hdvd
          rw [hmultiple, Nat.add_mul_mod_self_left]
          exact ih (fun b hb => hbytes b (by simp [hb])) index hindex'

/-- A packed big-endian natural viewed as `byteCount` bytes.

Byte reads are one shift and one mask, both GMP-accelerated in the kernel. -/
def packedByteSource (value byteCount : Nat) : ByteSource where
  byteCount := byteCount
  getNat index :=
    if index < byteCount then
      Nat.land (Nat.shiftRight value (8 * (byteCount - 1 - index))) 255
    else 0

/-- **The packed source really reads the bytes it was packed from.**

With this, everything `SHA256.hashSource_eq_hashBytes_of_realizes` and
`SHA256.digestSource_eq_hashBytes_of_realizes` say about a realized source
applies to the packed representation. -/
theorem packedByteSource_realizes {bytes : List Nat}
    (hbytes : ∀ b ∈ bytes, b < 256) :
    (packedByteSource (packBytes bytes) bytes.length).Realizes bytes := by
  refine ⟨rfl, fun index => ?_⟩
  simp only [packedByteSource, byteAt]
  by_cases hindex : index < bytes.length
  · simp only [hindex, if_pos]
    have hmask : ∀ x : Nat, Nat.land x 255 = x % 256 := by
      intro x
      have h := Nat.and_two_pow_sub_one_eq_mod x 8
      norm_num at h
      exact h
    have hshift : ∀ x n : Nat, Nat.shiftRight x n = x / 2 ^ n :=
      fun x n => Nat.shiftRight_eq_div_pow x n
    have hpow : (2 : Nat) ^ (8 * (bytes.length - 1 - index)) =
        256 ^ (bytes.length - 1 - index) := by
      rw [Nat.pow_mul]
    rw [hmask, hshift, hpow]
    exact packBytes_digit hbytes index hindex
  · simp only [hindex, if_neg, not_false_eq_true]
    exact (List.getD_eq_default bytes 0 (by omega)).symm

/-- A source determines its byte list.  Together with
`packedByteSource_realizes` this says that a packed value and a byte count
name exactly one byte string, so committing to the pair is committing to the
bytes. -/
theorem ByteSource.Realizes.unique {source : ByteSource} {left right : List Nat}
    (hleft : source.Realizes left) (hright : source.Realizes right) :
    left = right := by
  have hlength : left.length = right.length := by
    rw [hleft.1, hright.1]
  refine List.ext_getElem hlength ?_
  intro index hindexLeft hindexRight
  have hbyte : byteAt left index = byteAt right index :=
    (hleft.2 index).symm.trans (hright.2 index)
  simpa [byteAt, List.getD_eq_getElem, hindexLeft, hindexRight] using hbyte

/-! ## Packed byte strings as a first-class object -/

/-- An exact byte string carried as one big-endian natural number plus its
length.  Field extraction is a shift and a mask, so reading a 32- or 48-byte
field out of a multi-kilobyte structure costs two GMP operations in the
kernel rather than thousands of list steps. -/
structure PackedBytes where
  /-- Big-endian packing of the bytes. -/
  packed : Nat
  /-- Exact number of bytes. -/
  byteCount : Nat
  deriving DecidableEq, Repr, BEq

namespace PackedBytes

/-- The byte source these bytes denote. -/
def source (bytes : PackedBytes) : ByteSource :=
  packedByteSource bytes.packed bytes.byteCount

/-- The big-endian value of the `width`-byte field at `start`.

Out-of-range reads are fail-closed in the same sense as the source: bytes at
or past the end read as zero, because the mask keeps only the requested
width. -/
def field (bytes : PackedBytes) (start width : Nat) : Nat :=
  Nat.land
    (Nat.shiftRight bytes.packed (8 * (bytes.byteCount - start - width)))
    (2 ^ (8 * width) - 1)

/-- One byte. -/
def byte (bytes : PackedBytes) (index : Nat) : Nat :=
  bytes.field index 1

/-- Little-endian unsigned 16-bit read, as Intel quote headers use. -/
def leUInt16 (bytes : PackedBytes) (start : Nat) : Nat :=
  bytes.byte start + 256 * bytes.byte (start + 1)

/-- Little-endian unsigned 32-bit read. -/
def leUInt32 (bytes : PackedBytes) (start : Nat) : Nat :=
  bytes.byte start + 256 * bytes.byte (start + 1) +
    65536 * bytes.byte (start + 2) + 16777216 * bytes.byte (start + 3)

/-- SHA-256 of the whole byte string, as 64 lowercase hexadecimal digits. -/
def digest (bytes : PackedBytes) : String :=
  digestSource bytes.source

end PackedBytes

/-- Render a natural number as exactly `byteWidth` bytes of lowercase
hexadecimal, most significant digit first.  This is the spelling every
`Digest` in this repository uses, so a field parsed out of a packed structure
can be compared with a reviewed hexadecimal literal directly. -/
def hexOfNat (byteWidth value : Nat) : String :=
  String.ofList <| (List.range (2 * byteWidth)).map fun index =>
    hexDigit ((value / 16 ^ (2 * byteWidth - 1 - index)) % 16)

/-- Convenience: the digest of a packed source is the digest of its bytes
under the linked-list reference implementation. -/
theorem digestSource_packed_eq_hashBytes {bytes : List Nat}
    (hbytes : ∀ b ∈ bytes, b < 256) :
    digestSource (packedByteSource (packBytes bytes) bytes.length) =
      stateHex (hashBytes bytes) :=
  digestSource_eq_hashBytes_of_realizes _ bytes (packedByteSource_realizes hbytes)

end SparkInterval.Certificate.SHA256
