import Mathlib

/-!
# Small, pure SHA-256 implementation

The Phase 8 certificate parser uses this implementation to check the hashes
already present in the canonical reference-certificate format.  It is written
only with pure `Nat`, list, and string operations so certificate checks do not
invoke an external hashing executable or an FFI primitive.

This module provides a deterministic implementation of FIPS 180-4 SHA-256; it
does not make collision-resistance a theorem.  Collision resistance is not
needed for the mathematical certificate theorem because Lean also checks the
complete parsed batch and every result row.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate.SHA256

def wordModulus : Nat := 2 ^ 32
def wordMask : Nat := wordModulus - 1

private def word (value : Nat) : Nat := value % wordModulus
private def xor (left right : Nat) : Nat := Nat.xor left right
private def and (left right : Nat) : Nat := Nat.land left right
private def not (value : Nat) : Nat := xor wordMask value

private def rotateRight (value count : Nat) : Nat :=
  word (Nat.shiftRight value count + Nat.shiftLeft value (32 - count))

private def shiftRight (value count : Nat) : Nat := Nat.shiftRight value count

private def choose (x y z : Nat) : Nat :=
  xor (and x y) (and (not x) z)

private def majority (x y z : Nat) : Nat :=
  xor (xor (and x y) (and x z)) (and y z)

private def bigSigma0 (x : Nat) : Nat :=
  xor (xor (rotateRight x 2) (rotateRight x 13)) (rotateRight x 22)

private def bigSigma1 (x : Nat) : Nat :=
  xor (xor (rotateRight x 6) (rotateRight x 11)) (rotateRight x 25)

private def smallSigma0 (x : Nat) : Nat :=
  xor (xor (rotateRight x 7) (rotateRight x 18)) (shiftRight x 3)

private def smallSigma1 (x : Nat) : Nat :=
  xor (xor (rotateRight x 17) (rotateRight x 19)) (shiftRight x 10)

private def roundConstants : Array Nat := #[
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

private def initialState : State := {
  a := 0x6a09e667
  b := 0xbb67ae85
  c := 0x3c6ef372
  d := 0xa54ff53a
  e := 0x510e527f
  f := 0x9b05688c
  g := 0x1f83d9ab
  h := 0x5be0cd19
}

private def byteAt (bytes : List Nat) (index : Nat) : Nat :=
  bytes.getD index 0

private def readWord (block : List Nat) (index : Nat) : Nat :=
  let offset := index * 4
  word (
    Nat.shiftLeft (byteAt block offset) 24 +
    Nat.shiftLeft (byteAt block (offset + 1)) 16 +
    Nat.shiftLeft (byteAt block (offset + 2)) 8 +
    byteAt block (offset + 3))

private def messageSchedule (block : List Nat) : Array Nat :=
  let first := (List.range 16).map (readWord block) |>.toArray
  (List.range 48).foldl (fun schedule offset =>
    let index := offset + 16
    let next := word (
      smallSigma1 (schedule.getD (index - 2) 0) +
      schedule.getD (index - 7) 0 +
      smallSigma0 (schedule.getD (index - 15) 0) +
      schedule.getD (index - 16) 0)
    schedule.push next) first

private def round (schedule : Array Nat) (state : State) (index : Nat) : State :=
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

private def compress (hash : State) (block : List Nat) : State :=
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

private def encodedLength (byteCount : Nat) : List Nat :=
  let bitCount := (byteCount * 8) % (2 ^ 64)
  (List.range 8).map fun index =>
    (Nat.shiftRight bitCount (8 * (7 - index))) % 256

private def pad (bytes : List Nat) : List Nat :=
  let zeroCount := (56 + 64 - ((bytes.length + 1) % 64)) % 64
  bytes ++ [0x80] ++ List.replicate zeroCount 0 ++ encodedLength bytes.length

private def hashBytes (bytes : List Nat) : State :=
  let padded := pad bytes
  let blockCount := padded.length / 64
  (List.range blockCount).foldl (fun state index =>
    compress state (padded.drop (index * 64) |>.take 64)) initialState

private def hexDigit (value : Nat) : Char :=
  ("0123456789abcdef".toList.getD value '0')

private def wordHex (value : Nat) : String :=
  String.ofList <| (List.range 8).map fun index =>
    hexDigit ((Nat.shiftRight value (4 * (7 - index))) % 16)

/-- SHA-256 of UTF-8 string bytes, encoded as 64 lowercase hexadecimal digits. -/
def digestString (text : String) : String :=
  let bytes := text.toUTF8.toList.map UInt8.toNat
  let hash := hashBytes bytes
  wordHex hash.a ++ wordHex hash.b ++ wordHex hash.c ++ wordHex hash.d ++
    wordHex hash.e ++ wordHex hash.f ++ wordHex hash.g ++ wordHex hash.h

end SparkInterval.Certificate.SHA256
