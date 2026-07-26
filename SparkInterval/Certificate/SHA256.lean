/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Small, pure SHA-256 implementation

The Phase 8 certificate parser uses this implementation to check the hashes
already present in the canonical reference-certificate format.  It is written
with pure Lean `Nat`, `List`, `Array`, `ByteArray`, and `String` operations, so
certificate checks do not invoke an external hashing executable or an FFI
primitive.

This module provides a deterministic implementation of FIPS 180-4 SHA-256; it
does not make collision-resistance a theorem.  Collision resistance is not
needed for the mathematical certificate theorem because Lean also checks the
complete parsed batch and every result row.  The length field is encoded modulo
`2^64`, as in the SHA-256 padding operation; callers that model the FIPS input
domain must retain the explicit `byteCount * 8 < 2^64` guard.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate.SHA256

def wordModulus : Nat := 2 ^ 32
def wordMask : Nat := wordModulus - 1

/-- Public pure-word API used by source-level SHA implementation proofs. -/
def word (value : Nat) : Nat := value % wordModulus
def xor (left right : Nat) : Nat := Nat.xor left right
def and (left right : Nat) : Nat := Nat.land left right
def not (value : Nat) : Nat := xor wordMask value

def rotateRight (value count : Nat) : Nat :=
  word (Nat.shiftRight value count + Nat.shiftLeft value (32 - count))

def shiftRight (value count : Nat) : Nat := Nat.shiftRight value count

def choose (x y z : Nat) : Nat :=
  xor (and x y) (and (not x) z)

def majority (x y z : Nat) : Nat :=
  xor (xor (and x y) (and x z)) (and y z)

def bigSigma0 (x : Nat) : Nat :=
  xor (xor (rotateRight x 2) (rotateRight x 13)) (rotateRight x 22)

def bigSigma1 (x : Nat) : Nat :=
  xor (xor (rotateRight x 6) (rotateRight x 11)) (rotateRight x 25)

def smallSigma0 (x : Nat) : Nat :=
  xor (xor (rotateRight x 7) (rotateRight x 18)) (shiftRight x 3)

def smallSigma1 (x : Nat) : Nat :=
  xor (xor (rotateRight x 17) (rotateRight x 19)) (shiftRight x 10)

def roundConstants : Array Nat := #[
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
]

structure State where
  a : Nat
  b : Nat
  c : Nat
  d : Nat
  e : Nat
  f : Nat
  g : Nat
  h : Nat
  deriving BEq, Repr

def initialState : State := {
  a := 0x6a09e667
  b := 0xbb67ae85
  c := 0x3c6ef372
  d := 0xa54ff53a
  e := 0x510e527f
  f := 0x9b05688c
  g := 0x1f83d9ab
  h := 0x5be0cd19
}

def byteAt (bytes : List Nat) (index : Nat) : Nat :=
  bytes.getD index 0

def readWordFrom (getByte : Nat → Nat) (index : Nat) : Nat :=
  let offset := index * 4
  word (
    Nat.shiftLeft (getByte offset) 24 +
    Nat.shiftLeft (getByte (offset + 1)) 16 +
    Nat.shiftLeft (getByte (offset + 2)) 8 +
    getByte (offset + 3))

def readWord (block : List Nat) (index : Nat) : Nat :=
  let offset := index * 4
  word (
    Nat.shiftLeft (byteAt block offset) 24 +
    Nat.shiftLeft (byteAt block (offset + 1)) 16 +
    Nat.shiftLeft (byteAt block (offset + 2)) 8 +
    byteAt block (offset + 3))

/-- Initial sixteen words of one SHA-256 message schedule. -/
def initialScheduleFrom (getByte : Nat → Nat) : Array Nat :=
  (List.range 16).map (readWordFrom getByte) |>.toArray

def initialSchedule (block : List Nat) : Array Nat :=
  (List.range 16).map (readWord block) |>.toArray

/-- One of the 48 schedule-extension iterations, indexed from zero. -/
def extendSchedule (schedule : Array Nat) (offset : Nat) : Array Nat :=
  let index := offset + 16
  let next := word (
    smallSigma1 (schedule.getD (index - 2) 0) +
    schedule.getD (index - 7) 0 +
    smallSigma0 (schedule.getD (index - 15) 0) +
    schedule.getD (index - 16) 0)
  schedule.push next

def messageScheduleFrom (getByte : Nat → Nat) : Array Nat :=
  (List.range 48).foldl extendSchedule (initialScheduleFrom getByte)

def messageSchedule (block : List Nat) : Array Nat :=
  (List.range 48).foldl extendSchedule (initialSchedule block)

def round (schedule : Array Nat) (state : State) (index : Nat) : State :=
  let temporary1 := word (
    state.h + bigSigma1 state.e + choose state.e state.f state.g +
    roundConstants.getD index 0 + schedule.getD index 0)
  let temporary2 := word (bigSigma0 state.a + majority state.a state.b state.c)
  {
    a := word (temporary1 + temporary2)
    b := state.a
    c := state.b
    d := state.c
    e := word (state.d + temporary1)
    f := state.e
    g := state.f
    h := state.g
  }

def compressFrom (hash : State) (getByte : Nat → Nat) : State :=
  let schedule := messageScheduleFrom getByte
  let working := (List.range 64).foldl (round schedule) hash
  {
    a := word (hash.a + working.a)
    b := word (hash.b + working.b)
    c := word (hash.c + working.c)
    d := word (hash.d + working.d)
    e := word (hash.e + working.e)
    f := word (hash.f + working.f)
    g := word (hash.g + working.g)
    h := word (hash.h + working.h)
  }

def compress (hash : State) (block : List Nat) : State :=
  let schedule := messageSchedule block
  let working := (List.range 64).foldl (round schedule) hash
  {
    a := word (hash.a + working.a)
    b := word (hash.b + working.b)
    c := word (hash.c + working.c)
    d := word (hash.d + working.d)
    e := word (hash.e + working.e)
    f := word (hash.f + working.f)
    g := word (hash.g + working.g)
    h := word (hash.h + working.h)
  }

def encodedLength (byteCount : Nat) : List Nat :=
  let bitCount := (byteCount * 8) % (2 ^ 64)
  (List.range 8).map fun index =>
    (Nat.shiftRight bitCount (8 * (7 - index))) % 256

def pad (bytes : List Nat) : List Nat :=
  let zeroCount := (56 + 64 - ((bytes.length + 1) % 64)) % 64
  bytes ++ [0x80] ++ List.replicate zeroCount 0 ++ encodedLength bytes.length

/-- The short SHA-256 suffix appended after the unpadded message bytes. -/
def paddingNats (byteCount : Nat) : List Nat :=
  let zeroCount := (56 + 64 - ((byteCount + 1) % 64)) % 64
  [0x80] ++ List.replicate zeroCount 0 ++ encodedLength byteCount

/-- Deliberately simple linked-list reference implementation.  The streaming
implementation below is proved equal to this definition. -/
def hashBytes (bytes : List Nat) : State :=
  let padded := pad bytes
  let blockCount := padded.length / 64
  (List.range blockCount).foldl (fun state index =>
    compress state (padded.drop (index * 64) |>.take 64)) initialState

/-! ## Packed-byte streaming implementation -/

private theorem byteArrayToList_loop_eq (bytes : ByteArray) (index : Nat)
    (accumulator : List UInt8) (hindex : index ≤ bytes.size) :
    ByteArray.toList.loop bytes index accumulator =
      accumulator.reverse ++ bytes.data.toList.drop index := by
  fun_induction ByteArray.toList.loop bytes index accumulator
  · rename_i index accumulator hlt ih
    rw [ih (by omega)]
    rw [List.drop_eq_getElem_cons (i := index) (l := bytes.data.toList)
      (by simpa using hlt)]
    have hget :
        bytes.get! index = bytes.data.toList[index]'(by simpa using hlt) := by
      rw [ByteArray.get!]
      rw [getElem!_pos bytes.data index (by simpa using hlt)]
      exact (Array.getElem_toList _).symm
    rw [hget]
    simp
  · rename_i index accumulator hge
    have : index = bytes.size := by omega
    subst index
    simp

/-- `ByteArray.toList` has the same extensional contents as its backing array.
This lemma lets the optimized packed implementation be compared with the
linked-list reference without trusting a second byte interpretation. -/
theorem byteArrayToList_eq_dataToList (bytes : ByteArray) :
    bytes.toList = bytes.data.toList := by
  rw [ByteArray.toList]
  simpa using byteArrayToList_loop_eq bytes 0 [] (Nat.zero_le _)

/-- The exact natural-number byte list represented by a packed byte array. -/
def natBytes (bytes : ByteArray) : List Nat :=
  bytes.toList.map UInt8.toNat

theorem natBytes_length (bytes : ByteArray) :
    (natBytes bytes).length = bytes.size := by
  unfold natBytes
  rw [byteArrayToList_eq_dataToList, List.length_map,
    Array.length_toList, ByteArray.size_data]

/-- Packed `get!`, including its out-of-bounds zero, agrees with the reference
list byte accessor at every index. -/
theorem getBang_toNat_eq_byteAt_natBytes (bytes : ByteArray) (index : Nat) :
    (bytes.get! index).toNat = byteAt (natBytes bytes) index := by
  unfold byteAt natBytes
  change (bytes.get! index).toNat =
    (bytes.toList.map UInt8.toNat).getD index (UInt8.toNat 0)
  rw [List.getD_map bytes.toList 0 UInt8.toNat]
  congr 1
  rw [byteArrayToList_eq_dataToList, List.getD_eq_getElem?_getD,
    Array.getElem?_toList, ← Array.getD_eq_getD_getElem?]
  cases bytes with
  | mk data =>
      exact Array.getElem!_eq_getD

lemma byteAt_drop_take (bytes : List Nat) (offset index width : Nat)
    (hsource : offset + index < bytes.length) (hwidth : index < width) :
    byteAt ((bytes.drop offset).take width) index =
      byteAt bytes (offset + index) := by
  have hdrop : index < (bytes.drop offset).length := by
    simp only [List.length_drop]
    omega
  have htake : index < ((bytes.drop offset).take width).length := by
    simp only [List.length_take]
    omega
  unfold byteAt
  rw [List.getD_eq_getElem?_getD, List.getElem?_eq_getElem htake,
    Option.getD_some, List.getElem_take, List.getElem_drop,
    List.getD_eq_getElem?_getD, List.getElem?_eq_getElem hsource,
    Option.getD_some]

lemma byteAt_append (left right : List Nat) (index : Nat) :
    byteAt (left ++ right) index =
      if index < left.length then byteAt left index
      else byteAt right (index - left.length) := by
  unfold byteAt
  rw [List.getD_eq_getElem?_getD, List.getElem?_append]
  split <;> rfl

/-- Reference blocks in their original indexed order. -/
def fixedBlocks {β : Type} (blockSize : Nat) (bytes : List β)
    (count : Nat) : List (List β) :=
  (List.range count).map fun index =>
    (bytes.drop (index * blockSize)).take blockSize

lemma fixedBlocks_succ {β : Type} (blockSize : Nat) (bytes : List β)
    (count : Nat) :
    fixedBlocks blockSize bytes (count + 1) =
      bytes.take blockSize ::
        fixedBlocks blockSize (bytes.drop blockSize) count := by
  simp only [fixedBlocks, List.range_succ_eq_map, List.map_cons, List.map_map,
    Nat.zero_mul, List.drop_zero]
  congr 1
  apply List.map_congr_left
  intro index hindex
  simp only [Function.comp_apply, Nat.succ_eq_add_one]
  rw [List.drop_drop]
  congr 2
  simp [Nat.add_mul, Nat.add_comm]

/-- Tail-recursive fixed-size block fold.  Unlike the indexed reference, each
step drops only the block just consumed. -/
def foldFixedBlocks {α β : Type} (blockSize : Nat)
    (step : α → List β → α) : Nat → List β → α → α
  | 0, _, state => state
  | count + 1, bytes, state =>
      foldFixedBlocks blockSize step count (bytes.drop blockSize)
        (step state (bytes.take blockSize))

theorem foldFixedBlocks_eq_foldl {α β : Type} (blockSize : Nat)
    (step : α → List β → α) (count : Nat) (bytes : List β) (state : α) :
    foldFixedBlocks blockSize step count bytes state =
      List.foldl step state (fixedBlocks blockSize bytes count) := by
  induction count generalizing bytes state with
  | zero => rfl
  | succ count ih =>
      rw [foldFixedBlocks, fixedBlocks_succ, List.foldl_cons]
      exact ih (bytes := bytes.drop blockSize)
        (state := step state (bytes.take blockSize))

/-- Tail-recursive fold over consecutive 64-byte source offsets. -/
def foldSourceBlocks {α : Type} (step : α → Nat → α) :
    Nat → Nat → α → α
  | 0, _, state => state
  | count + 1, offset, state =>
      foldSourceBlocks step count (offset + 64) (step state offset)

theorem foldSourceBlocks_eq_foldFixedBlocks {α β : Type}
    (stepOffset : α → Nat → α) (stepBlock : α → List β → α)
    (source : List β) (count offset : Nat) (state : α)
    (hbound : offset + count * 64 ≤ source.length)
    (hstep : ∀ (current : α) (position : Nat),
      position + 64 ≤ source.length →
        stepOffset current position =
          stepBlock current ((source.drop position).take 64)) :
    foldSourceBlocks stepOffset count offset state =
      foldFixedBlocks 64 stepBlock count (source.drop offset) state := by
  induction count generalizing offset state with
  | zero => rfl
  | succ count ih =>
      rw [foldSourceBlocks, foldFixedBlocks]
      rw [hstep state offset (by omega)]
      have hdrop :
          (source.drop offset).drop 64 = source.drop (offset + 64) := by
        rw [List.drop_drop]
      rw [hdrop]
      exact ih (offset := offset + 64)
        (state := stepBlock state ((source.drop offset).take 64)) (by omega)

theorem foldFixedBlocks_sha_eq_indexed (bytes : List Nat) (count : Nat)
    (state : State) :
    foldFixedBlocks 64 compress count bytes state =
      List.foldl
        (fun current index =>
          compress current ((bytes.drop (index * 64)).take 64))
        state (List.range count) := by
  rw [foldFixedBlocks_eq_foldl]
  unfold fixedBlocks
  exact List.foldl_map

theorem byteArrayGetBang_eq_getElem (bytes : ByteArray) (index : Nat)
    (hindex : index < bytes.size) :
    bytes.get! index = bytes[index] := by
  cases bytes with
  | mk data =>
      exact getElem!_pos data index hindex

theorem byteArrayGetBang_eq_zero (bytes : ByteArray) (index : Nat)
    (hindex : ¬ index < bytes.size) :
    bytes.get! index = 0 := by
  cases bytes with
  | mk data =>
      exact getElem!_neg data index hindex

theorem byteArrayGetBang_extract (bytes : ByteArray)
    (start stop index : Nat) :
    (bytes.extract start stop).get! index =
      if index < min stop bytes.size - start then
        bytes.get! (start + index)
      else 0 := by
  split
  · next hindex =>
    have hextract : index < (bytes.extract start stop).size := by
      simpa using hindex
    rw [byteArrayGetBang_eq_getElem _ _ hextract,
      ByteArray.getElem_extract]
    rw [byteArrayGetBang_eq_getElem]
  · next hindex =>
    rw [byteArrayGetBang_eq_zero]
    simpa using hindex

/-- A packed, allocation-free view of bytes.  Sources may be virtually sliced
and concatenated while retaining an exact list semantics for proofs. -/
structure ByteSource where
  byteCount : Nat
  getNat : Nat → Nat

namespace ByteSource

/-- `source` reads exactly `bytes`, with both accessors returning zero beyond
the end. -/
def Realizes (source : ByteSource) (bytes : List Nat) : Prop :=
  bytes.length = source.byteCount ∧
    ∀ index, source.getNat index = byteAt bytes index

def ofByteArray (bytes : ByteArray) : ByteSource :=
  { byteCount := bytes.size
    getNat := fun index => (bytes.get! index).toNat }

theorem ofByteArray_realizes (bytes : ByteArray) :
    (ofByteArray bytes).Realizes (natBytes bytes) := by
  constructor
  · exact natBytes_length bytes
  · exact getBang_toNat_eq_byteAt_natBytes bytes

/-- A virtual half-open byte-array range.  Constructing this source does not
copy or convert the selected bytes. -/
def slice (bytes : ByteArray) (start stop : Nat) : ByteSource :=
  let byteCount := min stop bytes.size - start
  { byteCount
    getNat := fun index =>
      if index < byteCount then (bytes.get! (start + index)).toNat else 0 }

/-- Virtual concatenation.  It retains the two sources rather than allocating
their combined contents. -/
def append (left right : ByteSource) : ByteSource :=
  { byteCount := left.byteCount + right.byteCount
    getNat := fun index =>
      if index < left.byteCount then left.getNat index
      else right.getNat (index - left.byteCount) }

theorem append_realizes {left right : ByteSource}
    {leftBytes rightBytes : List Nat}
    (hleft : left.Realizes leftBytes) (hright : right.Realizes rightBytes) :
    (append left right).Realizes (leftBytes ++ rightBytes) := by
  rcases hleft with ⟨hleftLength, hleftGet⟩
  rcases hright with ⟨hrightLength, hrightGet⟩
  constructor
  · simp [append, hleftLength, hrightLength]
  · intro index
    simp only [append]
    rw [byteAt_append, hleftLength]
    split
    · exact hleftGet index
    · rw [hrightGet]

theorem slice_realizes (bytes : ByteArray) (start stop : Nat) :
    (slice bytes start stop).Realizes
      (natBytes (bytes.extract start stop)) := by
  constructor
  · simp [slice, natBytes_length]
  · intro index
    simp only [slice]
    calc
      (if index < min stop bytes.size - start then
          (bytes.get! (start + index)).toNat else 0) =
          ((bytes.extract start stop).get! index).toNat := by
            rw [byteArrayGetBang_extract]
            split <;> rfl
      _ = byteAt (natBytes (bytes.extract start stop)) index :=
        getBang_toNat_eq_byteAt_natBytes (bytes.extract start stop) index

/-- Virtual SHA padding.  Only the at-most-72-byte suffix is represented as a
list; the message itself remains in its packed source. -/
def paddedByte (source : ByteSource) (index : Nat) : Nat :=
  if index < source.byteCount then source.getNat index
  else byteAt (paddingNats source.byteCount) (index - source.byteCount)

def paddedSize (source : ByteSource) : Nat :=
  source.byteCount + (paddingNats source.byteCount).length

end ByteSource

theorem pad_eq_append_paddingNats (bytes : List Nat) :
    pad bytes = bytes ++ paddingNats bytes.length := by
  unfold pad paddingNats
  simp only [List.append_assoc]

namespace ByteSource

theorem paddedByte_eq_byteAt_pad {source : ByteSource} {bytes : List Nat}
    (hrealizes : source.Realizes bytes) (index : Nat) :
    source.paddedByte index = byteAt (pad bytes) index := by
  rcases hrealizes with ⟨hlength, hget⟩
  unfold paddedByte
  rw [pad_eq_append_paddingNats, byteAt_append, hlength]
  split
  · exact hget index
  · rfl

theorem paddedSize_eq_pad_length {source : ByteSource} {bytes : List Nat}
    (hrealizes : source.Realizes bytes) :
    source.paddedSize = (pad bytes).length := by
  rcases hrealizes with ⟨hlength, hget⟩
  rw [pad_eq_append_paddingNats]
  simp [paddedSize, hlength]

end ByteSource

/-- Hash a virtual packed source.  The loop is linear in the number of
64-byte blocks and never builds the message as a linked list. -/
def hashSource (source : ByteSource) : State :=
  foldSourceBlocks
    (fun current offset => compressFrom current fun position =>
      source.paddedByte (offset + position))
    (source.paddedSize / 64) 0 initialState

private lemma byteAt_sourceBlock_eq (source : ByteSource) (bytes : List Nat)
    (hrealizes : source.Realizes bytes) (offset index : Nat)
    (hblock : offset + 64 ≤ (pad bytes).length) (hindex : index < 64) :
    byteAt ((pad bytes).drop offset |>.take 64) index =
      source.paddedByte (offset + index) := by
  rw [byteAt_drop_take]
  · exact (ByteSource.paddedByte_eq_byteAt_pad hrealizes
      (offset + index)).symm
  · omega
  · exact hindex

private lemma readWordFrom_sourceBlock (source : ByteSource)
    (bytes : List Nat) (hrealizes : source.Realizes bytes)
    (offset index : Nat) (hblock : offset + 64 ≤ (pad bytes).length)
    (hindex : index < 16) :
    readWordFrom (fun position => source.paddedByte (offset + position)) index =
      readWord ((pad bytes).drop offset |>.take 64) index := by
  simp only [readWordFrom, readWord]
  rw [byteAt_sourceBlock_eq source bytes hrealizes offset
      (index * 4) hblock (by omega),
    byteAt_sourceBlock_eq source bytes hrealizes offset
      (index * 4 + 1) hblock (by omega),
    byteAt_sourceBlock_eq source bytes hrealizes offset
      (index * 4 + 2) hblock (by omega),
    byteAt_sourceBlock_eq source bytes hrealizes offset
      (index * 4 + 3) hblock (by omega)]

private lemma initialScheduleFrom_sourceBlock (source : ByteSource)
    (bytes : List Nat) (hrealizes : source.Realizes bytes) (offset : Nat)
    (hblock : offset + 64 ≤ (pad bytes).length) :
    initialScheduleFrom
        (fun position => source.paddedByte (offset + position)) =
      initialSchedule ((pad bytes).drop offset |>.take 64) := by
  unfold initialScheduleFrom initialSchedule
  apply congrArg List.toArray
  apply List.map_congr_left
  intro index hindex
  exact readWordFrom_sourceBlock source bytes hrealizes offset index hblock
    (List.mem_range.mp hindex)

private lemma messageScheduleFrom_sourceBlock (source : ByteSource)
    (bytes : List Nat) (hrealizes : source.Realizes bytes) (offset : Nat)
    (hblock : offset + 64 ≤ (pad bytes).length) :
    messageScheduleFrom
        (fun position => source.paddedByte (offset + position)) =
      messageSchedule ((pad bytes).drop offset |>.take 64) := by
  unfold messageScheduleFrom messageSchedule
  rw [initialScheduleFrom_sourceBlock source bytes hrealizes offset hblock]

private lemma compressFrom_sourceBlock (source : ByteSource)
    (bytes : List Nat) (hrealizes : source.Realizes bytes) (offset : Nat)
    (state : State) (hblock : offset + 64 ≤ (pad bytes).length) :
    compressFrom state
        (fun position => source.paddedByte (offset + position)) =
      compress state ((pad bytes).drop offset |>.take 64) := by
  unfold compressFrom compress
  rw [messageScheduleFrom_sourceBlock source bytes hrealizes offset hblock]

/-- Main refinement theorem: every realized packed source hashes to exactly the
linked-list FIPS reference value. -/
theorem hashSource_eq_hashBytes_of_realizes (source : ByteSource)
    (bytes : List Nat) (hrealizes : source.Realizes bytes) :
    hashSource source = hashBytes bytes := by
  unfold hashSource hashBytes
  have hsize := ByteSource.paddedSize_eq_pad_length hrealizes
  rw [hsize]
  have hbound :
      0 + ((pad bytes).length / 64) * 64 ≤ (pad bytes).length := by
    simpa using Nat.div_mul_le_self (pad bytes).length 64
  rw [foldSourceBlocks_eq_foldFixedBlocks (hbound := hbound)]
  · exact foldFixedBlocks_sha_eq_indexed
      (pad bytes) ((pad bytes).length / 64) initialState
  · intro current position hposition
    exact compressFrom_sourceBlock
      source bytes hrealizes position current hposition

def hexDigit (value : Nat) : Char :=
  ("0123456789abcdef".toList.getD value '0')

def wordHex (value : Nat) : String :=
  String.ofList <| (List.range 8).map fun index =>
    hexDigit ((Nat.shiftRight value (4 * (7 - index))) % 16)

def stateHex (hash : State) : String :=
  wordHex hash.a ++ wordHex hash.b ++ wordHex hash.c ++ wordHex hash.d ++
    wordHex hash.e ++ wordHex hash.f ++ wordHex hash.g ++ wordHex hash.h

/-- SHA-256 of a virtual packed source. -/
def digestSource (source : ByteSource) : String :=
  stateHex (hashSource source)

theorem digestSource_eq_hashBytes_of_realizes (source : ByteSource)
    (bytes : List Nat) (hrealizes : source.Realizes bytes) :
    digestSource source = stateHex (hashBytes bytes) := by
  unfold digestSource
  rw [hashSource_eq_hashBytes_of_realizes source bytes hrealizes]

/-- Slow specification retained as a separately named, executable reference. -/
def digestByteArrayReference (bytes : ByteArray) : String :=
  stateHex (hashBytes (natBytes bytes))

/-- SHA-256 of an exact arbitrary byte array, encoded as 64 lowercase
hexadecimal digits.  This path does not interpret or normalize the bytes as
UTF-8.  It reads the packed array directly and does not allocate a linked list
of all input bytes. -/
def digestByteArray (bytes : ByteArray) : String :=
  digestSource (ByteSource.ofByteArray bytes)

/-- The production packed-byte digest is exactly the linked-list reference. -/
theorem digestByteArray_eq_reference (bytes : ByteArray) :
    digestByteArray bytes = digestByteArrayReference bytes := by
  unfold digestByteArray digestByteArrayReference
  exact digestSource_eq_hashBytes_of_realizes
    (ByteSource.ofByteArray bytes) (natBytes bytes)
    (ByteSource.ofByteArray_realizes bytes)

theorem natBytes_append (left right : ByteArray) :
    natBytes (left ++ right) = natBytes left ++ natBytes right := by
  simp only [natBytes, byteArrayToList_eq_dataToList, ByteArray.data_append,
    Array.toList_append, List.map_append]

/-- Hash a prefix followed by a half-open range of a packed byte array.  The
executable path is a virtual composition: it does not materialize the range or
convert it to a linked list. -/
def digestPrefixSlice (domainPrefix bytes : ByteArray)
    (start stop : Nat) : String :=
  digestSource (ByteSource.append (ByteSource.ofByteArray domainPrefix)
    (ByteSource.slice bytes start stop))

/-- Specification theorem for `digestPrefixSlice`.  The right side expresses
the familiar concatenation equation but need not be evaluated in production. -/
theorem digestPrefixSlice_eq_digestByteArray_append_extract
    (domainPrefix bytes : ByteArray) (start stop : Nat) :
    digestPrefixSlice domainPrefix bytes start stop =
      digestByteArray (domainPrefix ++ bytes.extract start stop) := by
  rw [digestByteArray_eq_reference]
  unfold digestPrefixSlice digestSource digestByteArrayReference
  rw [hashSource_eq_hashBytes_of_realizes _ _
    (ByteSource.append_realizes
      (ByteSource.ofByteArray_realizes domainPrefix)
      (ByteSource.slice_realizes bytes start stop))]
  rw [natBytes_append]

/-- String-domain convenience wrapper around `digestPrefixSlice`. -/
def digestDomainSlice (domain : String) (bytes : ByteArray)
    (start stop : Nat) : String :=
  digestPrefixSlice domain.toUTF8 bytes start stop

theorem digestDomainSlice_eq_digestByteArray_append_extract
    (domain : String) (bytes : ByteArray) (start stop : Nat) :
    digestDomainSlice domain bytes start stop =
      digestByteArray (domain.toUTF8 ++ bytes.extract start stop) := by
  exact digestPrefixSlice_eq_digestByteArray_append_extract
    domain.toUTF8 bytes start stop

/-- SHA-256 of UTF-8 string bytes, encoded as 64 lowercase hexadecimal digits. -/
def digestString (text : String) : String :=
  digestByteArray text.toUTF8

/-- The historical string API is exactly the byte-array API on the string's
UTF-8 representation. -/
theorem digestString_eq_digestByteArray_toUTF8 (text : String) :
    digestString text = digestByteArray text.toUTF8 := by
  rfl

end SparkInterval.Certificate.SHA256
