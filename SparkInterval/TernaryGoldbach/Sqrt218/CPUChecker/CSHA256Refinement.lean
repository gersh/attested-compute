/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Source-level refinement of the Sqrt218 command SHA-256

This module models the pure SHA-256 code in
`cpu_checker/sqrt218/sqrt218_cpu_command.c`.  It does not model the C
implementation by invoking the target digest.  Instead it provides:

* exact `BitVec 8`/`BitVec 32` models of the source byte read, shifts,
  bitwise OR, and unsigned wraparound;
* an independent natural-number normalization of the C schedule and round
  functions; and
* refinement theorems into `SparkInterval.Certificate.SHA256`.

All theorems are symbolic.  This file contains no production bytes and
performs no certificate hashing or replay when imported.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement

open SparkInterval.Certificate

abbrev CByte := BitVec 8
abbrev CWord := BitVec 32

def cWordModulus : Nat := 2 ^ 32
def cWordMask : Nat := cWordModulus - 1

/-! ## Exact C word primitives -/

/-- Exact unsigned source expression
`(value >> amount) | (value << (32 - amount))`. -/
def cRotateRightWord (value : CWord) (amount : Nat) : CWord :=
  value.ushiftRight amount ||| value.shiftLeft (32 - amount)

/-- Exact four-byte source expression used by `tg_sha256_read_be32`. -/
def cReadBE32Word (b0 b1 b2 b3 : CByte) : CWord :=
  (b0.zeroExtend 32 <<< 24) |||
  (b1.zeroExtend 32 <<< 16) |||
  (b2.zeroExtend 32 <<< 8) |||
  b3.zeroExtend 32

def cByteAtWord (block : List CByte) (index : Nat) : CByte :=
  block.getD index 0

def cReadWord (block : List CByte) (index : Nat) : CWord :=
  let offset := index * 4
  cReadBE32Word
    (cByteAtWord block offset)
    (cByteAtWord block (offset + 1))
    (cByteAtWord block (offset + 2))
    (cByteAtWord block (offset + 3))

/-! ## Independent normalized C word model -/

def cWord (value : Nat) : Nat := value % cWordModulus
def cXor (left right : Nat) : Nat := Nat.xor left right
def cAnd (left right : Nat) : Nat := Nat.land left right
def cNot (value : Nat) : Nat := cXor cWordMask value

def cRotateRight (value amount : Nat) : Nat :=
  cWord
    (Nat.shiftRight value amount +
      Nat.shiftLeft value (32 - amount))

def cShiftRight (value amount : Nat) : Nat :=
  Nat.shiftRight value amount

def cChoose (x y z : Nat) : Nat :=
  cXor (cAnd x y) (cAnd (cNot x) z)

def cMajority (x y z : Nat) : Nat :=
  cXor (cXor (cAnd x y) (cAnd x z)) (cAnd y z)

def cBigSigma0 (x : Nat) : Nat :=
  cXor (cXor (cRotateRight x 2) (cRotateRight x 13))
    (cRotateRight x 22)

def cBigSigma1 (x : Nat) : Nat :=
  cXor (cXor (cRotateRight x 6) (cRotateRight x 11))
    (cRotateRight x 25)

def cSmallSigma0 (x : Nat) : Nat :=
  cXor (cXor (cRotateRight x 7) (cRotateRight x 18))
    (cShiftRight x 3)

def cSmallSigma1 (x : Nat) : Nat :=
  cXor (cXor (cRotateRight x 17) (cRotateRight x 19))
    (cShiftRight x 10)

def cByteAt (block : List Nat) (index : Nat) : Nat :=
  block.getD index 0

def cReadWordNat (block : List Nat) (index : Nat) : Nat :=
  let offset := index * 4
  cWord (
    Nat.shiftLeft (cByteAt block offset) 24 +
    Nat.shiftLeft (cByteAt block (offset + 1)) 16 +
    Nat.shiftLeft (cByteAt block (offset + 2)) 8 +
    cByteAt block (offset + 3))

/-! ## Primitive refinement -/

theorem cRotateRightWord_refines
    (value : CWord) (amount : Nat)
    (hamount : 0 < amount ∧ amount < 32) :
    (cRotateRightWord value amount).toNat =
      cRotateRight value.toNat amount := by
  unfold cRotateRightWord cRotateRight cWord cWordModulus
  simp only [BitVec.toNat_or]
  change
    (value >>> amount).toNat |||
        (value <<< (32 - amount)).toNat =
      (value.toNat >>> amount +
          value.toNat <<< (32 - amount)) %
        2 ^ 32
  rw [BitVec.toNat_ushiftRight, BitVec.toNat_shiftLeft]
  have hlow :
      value.toNat >>> amount < 2 ^ (32 - amount) := by
    rw [Nat.shiftRight_eq_div_pow]
    apply (Nat.div_lt_iff_lt_mul (Nat.two_pow_pos amount)).2
    rw [← Nat.pow_add, Nat.sub_add_cancel (Nat.le_of_lt hamount.2)]
    exact value.isLt
  rw [Nat.add_comm, Nat.shiftLeft_add_eq_or_of_lt hlow]
  have hlow32 :
      value.toNat >>> amount < 2 ^ 32 :=
    lt_of_le_of_lt (Nat.shiftRight_le _ _) value.isLt
  rw [Nat.or_mod_two_pow, Nat.mod_eq_of_lt hlow32]
  exact Nat.or_comm _ _

theorem cReadBE32Word_eq_add
    (b0 b1 b2 b3 : CByte) :
    cReadBE32Word b0 b1 b2 b3 =
      (b0.zeroExtend 32 <<< 24) +
      (b1.zeroExtend 32 <<< 16) +
      (b2.zeroExtend 32 <<< 8) +
      b3.zeroExtend 32 := by
  unfold cReadBE32Word
  apply BitVec.eq_of_toNat_eq
  simp only [BitVec.toNat_or, BitVec.toNat_add, BitVec.toNat_shiftLeft,
    BitVec.zeroExtend_eq_setWidth, BitVec.toNat_setWidth]
  have h0 := b0.isLt
  have h1 := b1.isLt
  have h2 := b2.isLt
  have h3 := b3.isLt
  norm_num at h0 h1 h2 h3 ⊢
  have h0m : b0.toNat < 4294967296 := by omega
  have h1m : b1.toNat < 4294967296 := by omega
  have h2m : b2.toNat < 4294967296 := by omega
  have h3m : b3.toNat < 4294967296 := by omega
  have hs0 : b0.toNat <<< 24 < 4294967296 := by
    rw [Nat.shiftLeft_eq]
    norm_num
    omega
  have hs1 : b1.toNat <<< 16 < 4294967296 := by
    rw [Nat.shiftLeft_eq]
    norm_num
    omega
  have hs2 : b2.toNat <<< 8 < 4294967296 := by
    rw [Nat.shiftLeft_eq]
    norm_num
    omega
  simp only [Nat.mod_eq_of_lt h0m, Nat.mod_eq_of_lt h1m,
    Nat.mod_eq_of_lt h2m, Nat.mod_eq_of_lt h3m,
    Nat.mod_eq_of_lt hs0, Nat.mod_eq_of_lt hs1,
    Nat.mod_eq_of_lt hs2]
  have h23 : (b2.toNat <<< 8) + b3.toNat < 2 ^ 16 := by
    rw [Nat.shiftLeft_eq]
    norm_num
    omega
  have h123 :
      (b1.toNat <<< 16) + ((b2.toNat <<< 8) + b3.toNat) < 2 ^ 24 := by
    rw [Nat.shiftLeft_eq, Nat.shiftLeft_eq]
    norm_num
    omega
  have h0123 :
      (b0.toNat <<< 24) +
          ((b1.toNat <<< 16) + ((b2.toNat <<< 8) + b3.toNat)) <
        4294967296 := by
    rw [Nat.shiftLeft_eq, Nat.shiftLeft_eq, Nat.shiftLeft_eq]
    norm_num
    omega
  rw [Nat.or_assoc, Nat.or_assoc]
  rw [← Nat.shiftLeft_add_eq_or_of_lt h3 b2.toNat]
  rw [← Nat.shiftLeft_add_eq_or_of_lt h23 b1.toNat]
  rw [← Nat.shiftLeft_add_eq_or_of_lt h123 b0.toNat]
  have hsum :
      b0.toNat <<< 24 + b1.toNat <<< 16 + b2.toNat <<< 8 + b3.toNat <
        4294967296 := by
    omega
  rw [Nat.mod_eq_of_lt hsum]
  omega

theorem cReadBE32Word_toNat
    (b0 b1 b2 b3 : CByte) :
    (cReadBE32Word b0 b1 b2 b3).toNat =
      b0.toNat * 2 ^ 24 +
        b1.toNat * 2 ^ 16 +
        b2.toNat * 2 ^ 8 +
        b3.toNat := by
  rw [cReadBE32Word_eq_add]
  have h0 := b0.isLt
  have h1 := b1.isLt
  have h2 := b2.isLt
  have h3 := b3.isLt
  simp only [BitVec.toNat_add, BitVec.toNat_shiftLeft,
    BitVec.zeroExtend_eq_setWidth, BitVec.toNat_setWidth]
  norm_num at h0 h1 h2 h3 ⊢
  omega

theorem cByteAtWord_toNat (block : List CByte) (index : Nat) :
    (cByteAtWord block index).toNat =
      cByteAt (block.map BitVec.toNat) index := by
  unfold cByteAtWord cByteAt
  exact
    (List.getD_map (l := block) (d := (0 : CByte))
      (n := index) BitVec.toNat).symm

theorem cReadWord_toNat (block : List CByte) (index : Nat) :
    (cReadWord block index).toNat =
      cReadWordNat (block.map BitVec.toNat) index := by
  unfold cReadWord cReadWordNat
  rw [cReadBE32Word_toNat]
  rw [cByteAtWord_toNat block (index * 4),
    cByteAtWord_toNat block (index * 4 + 1),
    cByteAtWord_toNat block (index * 4 + 2),
    cByteAtWord_toNat block (index * 4 + 3)]
  unfold cWord cWordModulus
  have h0 :
      cByteAt (block.map BitVec.toNat) (index * 4) < 256 := by
    rw [← cByteAtWord_toNat block (index * 4)]
    exact (cByteAtWord block (index * 4)).isLt
  have h1 :
      cByteAt (block.map BitVec.toNat) (index * 4 + 1) < 256 := by
    rw [← cByteAtWord_toNat block (index * 4 + 1)]
    exact (cByteAtWord block (index * 4 + 1)).isLt
  have h2 :
      cByteAt (block.map BitVec.toNat) (index * 4 + 2) < 256 := by
    rw [← cByteAtWord_toNat block (index * 4 + 2)]
    exact (cByteAtWord block (index * 4 + 2)).isLt
  have h3 :
      cByteAt (block.map BitVec.toNat) (index * 4 + 3) < 256 := by
    rw [← cByteAtWord_toNat block (index * 4 + 3)]
    exact (cByteAtWord block (index * 4 + 3)).isLt
  norm_num at h0 h1 h2 h3 ⊢
  omega

theorem cWord_eq_target : cWord = SHA256.word := rfl
theorem cXor_eq_target : cXor = SHA256.xor := rfl
theorem cAnd_eq_target : cAnd = SHA256.and := rfl
theorem cNot_eq_target : cNot = SHA256.not := rfl
theorem cRotateRight_eq_target :
    cRotateRight = SHA256.rotateRight := rfl
theorem cShiftRight_eq_target :
    cShiftRight = SHA256.shiftRight := rfl
theorem cChoose_eq_target : cChoose = SHA256.choose := rfl
theorem cMajority_eq_target : cMajority = SHA256.majority := rfl
theorem cBigSigma0_eq_target :
    cBigSigma0 = SHA256.bigSigma0 := rfl
theorem cBigSigma1_eq_target :
    cBigSigma1 = SHA256.bigSigma1 := rfl
theorem cSmallSigma0_eq_target :
    cSmallSigma0 = SHA256.smallSigma0 := rfl
theorem cSmallSigma1_eq_target :
    cSmallSigma1 = SHA256.smallSigma1 := rfl
theorem cReadWordNat_eq_target :
    cReadWordNat = SHA256.readWord := rfl

/-! ## Message schedule -/

def cInitialSchedule (block : List Nat) : Array Nat :=
  (List.range 16).map (cReadWordNat block) |>.toArray

/-- Source order:
`w[i-16] + sigma0(w[i-15]) + w[i-7] + sigma1(w[i-2])`. -/
def cExtendSchedule
    (schedule : Array Nat) (offset : Nat) : Array Nat :=
  let index := offset + 16
  let next := cWord (
    schedule.getD (index - 16) 0 +
    cSmallSigma0 (schedule.getD (index - 15) 0) +
    schedule.getD (index - 7) 0 +
    cSmallSigma1 (schedule.getD (index - 2) 0))
  schedule.push next

def cMessageSchedule (block : List Nat) : Array Nat :=
  (List.range 48).foldl cExtendSchedule (cInitialSchedule block)

theorem cInitialSchedule_eq_target (block : List Nat) :
    cInitialSchedule block = SHA256.initialSchedule block := rfl

theorem cExtendSchedule_eq_target
    (schedule : Array Nat) (offset : Nat) :
    cExtendSchedule schedule offset =
      SHA256.extendSchedule schedule offset := by
  unfold cExtendSchedule SHA256.extendSchedule
  apply congrArg schedule.push
  rw [cWord_eq_target, cSmallSigma0_eq_target,
    cSmallSigma1_eq_target]
  apply congrArg SHA256.word
  omega

theorem cMessageSchedule_eq_target (block : List Nat) :
    cMessageSchedule block = SHA256.messageSchedule block := by
  have hextend : cExtendSchedule = SHA256.extendSchedule := by
    funext schedule offset
    exact cExtendSchedule_eq_target schedule offset
  unfold cMessageSchedule SHA256.messageSchedule
  rw [cInitialSchedule_eq_target, hextend]

/-! ## Compression rounds -/

/-- The eight source `uint32_t` working variables, normalized to naturals. -/
structure CState where
  a : Nat
  b : Nat
  c : Nat
  d : Nat
  e : Nat
  f : Nat
  g : Nat
  h : Nat
  deriving BEq, Repr

/-- The normalized state really denotes eight source `uint32_t` values. -/
structure CState.IsWord32 (state : CState) : Prop where
  a : state.a < cWordModulus
  b : state.b < cWordModulus
  c : state.c < cWordModulus
  d : state.d < cWordModulus
  e : state.e < cWordModulus
  f : state.f < cWordModulus
  g : state.g < cWordModulus
  h : state.h < cWordModulus

theorem cWord_lt (value : Nat) :
    cWord value < cWordModulus := by
  unfold cWord
  apply Nat.mod_lt
  norm_num [cWordModulus]

def CState.toTarget (state : CState) : SHA256.State := {
  a := state.a
  b := state.b
  c := state.c
  d := state.d
  e := state.e
  f := state.f
  g := state.g
  h := state.h
}

@[simp] theorem CState.toTarget_a (state : CState) :
    state.toTarget.a = state.a := rfl
@[simp] theorem CState.toTarget_b (state : CState) :
    state.toTarget.b = state.b := rfl
@[simp] theorem CState.toTarget_c (state : CState) :
    state.toTarget.c = state.c := rfl
@[simp] theorem CState.toTarget_d (state : CState) :
    state.toTarget.d = state.d := rfl
@[simp] theorem CState.toTarget_e (state : CState) :
    state.toTarget.e = state.e := rfl
@[simp] theorem CState.toTarget_f (state : CState) :
    state.toTarget.f = state.f := rfl
@[simp] theorem CState.toTarget_g (state : CState) :
    state.toTarget.g = state.g := rfl
@[simp] theorem CState.toTarget_h (state : CState) :
    state.toTarget.h = state.h := rfl

theorem targetState_ext
    {left right : SHA256.State}
    (ha : left.a = right.a)
    (hb : left.b = right.b)
    (hc : left.c = right.c)
    (hd : left.d = right.d)
    (he : left.e = right.e)
    (hf : left.f = right.f)
    (hg : left.g = right.g)
    (hh : left.h = right.h) :
    left = right := by
  cases left
  cases right
  simp_all

/-- Literal copy of `tg_sha256_round_constants`, kept independent of the
target definition so an accidental edit on either side breaks refinement. -/
def cRoundConstants : Array Nat := #[
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

theorem cRoundConstants_eq_target :
    cRoundConstants = SHA256.roundConstants := rfl

/-- Literal source initialization of `state[0]` through `state[7]`. -/
def cInitialState : CState := {
  a := 0x6a09e667
  b := 0xbb67ae85
  c := 0x3c6ef372
  d := 0xa54ff53a
  e := 0x510e527f
  f := 0x9b05688c
  g := 0x1f83d9ab
  h := 0x5be0cd19
}

theorem cInitialState_refines :
    cInitialState.toTarget = SHA256.initialState := rfl

theorem cInitialState_isWord32 : cInitialState.IsWord32 := by
  constructor <;> norm_num [cInitialState, cWordModulus]

/-- One normalized iteration of the source `index < 64U` loop.  Each
assignment whose C type is `uint32_t` is reduced modulo `2^32`. -/
def cRound
    (schedule : Array Nat) (state : CState) (index : Nat) : CState :=
  let temporary1 := cWord (
    state.h + cBigSigma1 state.e + cChoose state.e state.f state.g +
    cRoundConstants.getD index 0 + schedule.getD index 0)
  let temporary2 :=
    cWord (cBigSigma0 state.a + cMajority state.a state.b state.c)
  {
    a := cWord (temporary1 + temporary2)
    b := state.a
    c := state.b
    d := state.c
    e := cWord (state.d + temporary1)
    f := state.e
    g := state.f
    h := state.g
  }

theorem cRound_refines
    (schedule : Array Nat) (state : CState) (index : Nat) :
    (cRound schedule state index).toTarget =
      SHA256.round schedule state.toTarget index := by
  unfold cRound SHA256.round CState.toTarget
  rw [cRoundConstants_eq_target, cWord_eq_target,
    cBigSigma1_eq_target, cChoose_eq_target,
    cBigSigma0_eq_target, cMajority_eq_target]

theorem cRound_isWord32
    (schedule : Array Nat) (state : CState) (index : Nat)
    (hstate : state.IsWord32) :
    (cRound schedule state index).IsWord32 := by
  refine {
    a := cWord_lt _
    b := hstate.a
    c := hstate.b
    d := hstate.c
    e := cWord_lt _
    f := hstate.e
    g := hstate.f
    h := hstate.g
  }

theorem cRoundFold_refines
    (indices : List Nat) (schedule : Array Nat) (state : CState) :
    (indices.foldl (cRound schedule) state).toTarget =
      indices.foldl (SHA256.round schedule) state.toTarget := by
  induction indices generalizing state with
  | nil => rfl
  | cons index indices inductionHypothesis =>
      simp only [List.foldl_cons]
      rw [inductionHypothesis, cRound_refines]

/-- The source compression loop followed by its eight feed-forward adds. -/
def cCompress (hash : CState) (block : List Nat) : CState :=
  let schedule := cMessageSchedule block
  let working := (List.range 64).foldl (cRound schedule) hash
  {
    a := cWord (hash.a + working.a)
    b := cWord (hash.b + working.b)
    c := cWord (hash.c + working.c)
    d := cWord (hash.d + working.d)
    e := cWord (hash.e + working.e)
    f := cWord (hash.f + working.f)
    g := cWord (hash.g + working.g)
    h := cWord (hash.h + working.h)
  }

theorem cCompress_refines (hash : CState) (block : List Nat) :
    (cCompress hash block).toTarget =
      SHA256.compress hash.toTarget block := by
  unfold cCompress SHA256.compress
  rw [cMessageSchedule_eq_target]
  have hworking :=
    cRoundFold_refines
      (List.range 64) (SHA256.messageSchedule block) hash
  simp only [cWord_eq_target]
  have ha := congrArg SHA256.State.a hworking
  have hb := congrArg SHA256.State.b hworking
  have hc := congrArg SHA256.State.c hworking
  have hd := congrArg SHA256.State.d hworking
  have he := congrArg SHA256.State.e hworking
  have hf := congrArg SHA256.State.f hworking
  have hg := congrArg SHA256.State.g hworking
  have hh := congrArg SHA256.State.h hworking
  apply targetState_ext
  all_goals
    simp only [CState.toTarget_a, CState.toTarget_b,
      CState.toTarget_c, CState.toTarget_d, CState.toTarget_e,
      CState.toTarget_f, CState.toTarget_g, CState.toTarget_h]
      at ha hb hc hd he hf hg hh ⊢
    simp [ha, hb, hc, hd, he, hf, hg, hh]

theorem cCompress_isWord32 (hash : CState) (block : List Nat) :
    (cCompress hash block).IsWord32 := by
  refine {
    a := cWord_lt _
    b := cWord_lt _
    c := cWord_lt _
    d := cWord_lt _
    e := cWord_lt _
    f := cWord_lt _
    g := cWord_lt _
    h := cWord_lt _
  }

/-! ## Source final-buffer padding -/

/-- The eight assignments made by `tg_result_put_be64` for the SHA bit
length, in source order. -/
def cEncodedLength (byteCount : Nat) : List Nat :=
  let bitCount := (byteCount * 8) % (2 ^ 64)
  (List.range 8).map fun index =>
    (Nat.shiftRight bitCount (8 * (7 - index))) % 256

theorem cEncodedLength_eq_target (byteCount : Nat) :
    cEncodedLength byteCount = SHA256.encodedLength byteCount := rfl

def cRemainingCount (byteCount : Nat) : Nat :=
  byteCount % 64

/-- Value assigned to the source variable `padded_length`. -/
def cFinalBufferLength (byteCount : Nat) : Nat :=
  if cRemainingCount byteCount < 56 then 64 else 128

/-- Number of zero bytes left between `0x80` and the final bit length in
`final_blocks`.  The subtraction mirrors positions in the zero-initialized
64- or 128-byte source array. -/
def cFinalZeroCount (byteCount : Nat) : Nat :=
  cFinalBufferLength byteCount - cRemainingCount byteCount - 9

/-- Whole padded byte stream produced by copying the remainder into
`final_blocks`, writing `0x80`, retaining the zero initialization, and
writing the final big-endian length. -/
def cPad (bytes : List Nat) : List Nat :=
  bytes ++ [0x80] ++
    List.replicate (cFinalZeroCount bytes.length) 0 ++
    cEncodedLength bytes.length

theorem cRemainingCount_lt (byteCount : Nat) :
    cRemainingCount byteCount < 64 := by
  unfold cRemainingCount
  exact Nat.mod_lt _ (by norm_num)

theorem cFinalZeroCount_eq_target (byteCount : Nat) :
    cFinalZeroCount byteCount =
      (56 + 64 - ((byteCount + 1) % 64)) % 64 := by
  unfold cFinalZeroCount cFinalBufferLength cRemainingCount
  have hremainder : byteCount % 64 < 64 :=
    Nat.mod_lt _ (by norm_num)
  rw [Nat.add_mod]
  norm_num
  split <;> omega

theorem cPad_eq_target (bytes : List Nat) :
    cPad bytes = SHA256.pad bytes := by
  unfold cPad SHA256.pad
  rw [cEncodedLength_eq_target, cFinalZeroCount_eq_target]

/-! ## Normalized source block loop -/

def cBlockAt (bytes : List Nat) (index : Nat) : List Nat :=
  (bytes.drop (index * 64)).take 64

def cHashBytes (bytes : List Nat) : CState :=
  let padded := cPad bytes
  let blockCount := padded.length / 64
  (List.range blockCount).foldl
    (fun state index => cCompress state (cBlockAt padded index))
    cInitialState

theorem cCompressBlocks_refines
    (indices : List Nat) (padded : List Nat) (state : CState) :
    (indices.foldl
        (fun current index =>
          cCompress current (cBlockAt padded index))
        state).toTarget =
      indices.foldl
        (fun current index =>
          SHA256.compress current (cBlockAt padded index))
        state.toTarget := by
  induction indices generalizing state with
  | nil => rfl
  | cons index indices inductionHypothesis =>
      simp only [List.foldl_cons]
      rw [inductionHypothesis, cCompress_refines]

theorem cCompressBlocks_isWord32
    (indices : List Nat) (padded : List Nat) (state : CState)
    (hstate : state.IsWord32) :
    (indices.foldl
      (fun current index =>
        cCompress current (cBlockAt padded index))
      state).IsWord32 := by
  induction indices generalizing state with
  | nil => exact hstate
  | cons index indices inductionHypothesis =>
      simp only [List.foldl_cons]
      exact inductionHypothesis _
        (cCompress_isWord32 state (cBlockAt padded index))

theorem cHashBytes_refines (bytes : List Nat) :
    (cHashBytes bytes).toTarget = SHA256.hashBytes bytes := by
  unfold cHashBytes SHA256.hashBytes
  rw [cPad_eq_target]
  simpa only [cBlockAt, cInitialState_refines] using
    cCompressBlocks_refines
      (List.range ((SHA256.pad bytes).length / 64))
      (SHA256.pad bytes) cInitialState

theorem cHashBytes_isWord32 (bytes : List Nat) :
    (cHashBytes bytes).IsWord32 := by
  unfold cHashBytes
  exact cCompressBlocks_isWord32 _ _ _
    cInitialState_isWord32

def cHashByteArray (bytes : ByteArray) : CState :=
  cHashBytes (bytes.toList.map UInt8.toNat)

theorem cHashByteArray_refines (bytes : ByteArray) :
    (cHashByteArray bytes).toTarget =
      SHA256.hashBytes (bytes.toList.map UInt8.toNat) := by
  exact cHashBytes_refines _

/-! ## Big-endian digest output -/

/-- The four assignments performed by `tg_result_put_be32`. -/
def cPutBE32 (value : Nat) : List UInt8 :=
  [ UInt8.ofNat (Nat.shiftRight value 24)
  , UInt8.ofNat (Nat.shiftRight value 16)
  , UInt8.ofNat (Nat.shiftRight value 8)
  , UInt8.ofNat value
  ]

def cStateDigestBytes (state : CState) : ByteArray :=
  (cPutBE32 state.a ++ cPutBE32 state.b ++
    cPutBE32 state.c ++ cPutBE32 state.d ++
    cPutBE32 state.e ++ cPutBE32 state.f ++
    cPutBE32 state.g ++ cPutBE32 state.h).toByteArray

def cDigestByteArray (bytes : ByteArray) : ByteArray :=
  cStateDigestBytes (cHashByteArray bytes)

theorem byteArrayLowerHex_cPutBE32 (value : Nat) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
        (cPutBE32 value).toByteArray =
      SHA256.wordHex value := by
  unfold
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
    cPutBE32 SHA256.wordHex
  rw [
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.toList_toByteArray]
  apply congrArg String.ofList
  have hrange : List.range 8 = [0, 1, 2, 3, 4, 5, 6, 7] := by
    decide
  have h24 :
      value / 16777216 % 256 / 16 =
        value / 268435456 % 16 := by
    omega
  have h16 :
      value / 65536 % 256 / 16 =
        value / 1048576 % 16 := by
    omega
  have h8 :
      value / 256 % 256 / 16 =
        value / 4096 % 16 := by
    omega
  have h0 :
      value % 256 / 16 = value / 16 % 16 := by
    omega
  rw [hrange]
  simp [
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteLowerHex,
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.lowerHexDigit,
    SHA256.hexDigit, Nat.shiftRight_eq_div_pow, h24, h16, h8, h0]

theorem byteArrayLowerHex_listAppend
    (left right : List UInt8) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
        (left ++ right).toByteArray =
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
          left.toByteArray ++
        SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
          right.toByteArray := by
  unfold
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
  rw [
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.toList_toByteArray,
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.toList_toByteArray,
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.toList_toByteArray]
  simp [List.flatMap_append, String.ofList_append]

theorem byteArrayLowerHex_cStateDigestBytes (state : CState) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
        (cStateDigestBytes state) =
      SHA256.stateHex state.toTarget := by
  unfold cStateDigestBytes SHA256.stateHex
  simp only [byteArrayLowerHex_listAppend,
    byteArrayLowerHex_cPutBE32, CState.toTarget_a,
    CState.toTarget_b, CState.toTarget_c, CState.toTarget_d,
    CState.toTarget_e, CState.toTarget_f, CState.toTarget_g,
    CState.toTarget_h]

theorem cStateDigestBytes_size (state : CState) :
    (cStateDigestBytes state).size = 32 := by
  unfold cStateDigestBytes cPutBE32
  simp

theorem cDigestByteArray_size (bytes : ByteArray) :
    (cDigestByteArray bytes).size = 32 := by
  exact cStateDigestBytes_size _

/-- End-to-end correctness of the independent normalized source algorithm:
the 32 bytes emitted in source big-endian order spell the pure Lean SHA-256
digest when rendered in lowercase hexadecimal. -/
theorem cDigestByteArray_refines (bytes : ByteArray) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
        (cDigestByteArray bytes) =
      SHA256.digestByteArray bytes := by
  rw [SHA256.digestByteArray_eq_reference]
  unfold cDigestByteArray SHA256.digestByteArrayReference SHA256.natBytes
  rw [byteArrayLowerHex_cStateDigestBytes, cHashByteArray_refines]

/-!
The theorem above is a refinement of a pure model extracted from the source
expressions and loop bounds.  It deliberately does not assert that an
arbitrary compiler or executable ran that model.  That last step is the
architecture/compiler execution boundary and remains a visible premise.
-/

/-- Observable source-execution boundary.  A compiler or architecture proof
must establish that the concrete 32 output bytes equal the pure source model;
this module neither assumes nor axiomatizes that fact. -/
def ConcreteExecutionMatchesSource
    (inputBytes outputBytes : ByteArray) : Prop :=
  outputBytes = cDigestByteArray inputBytes

theorem digest_correct_of_concreteExecution
    (inputBytes outputBytes : ByteArray)
    (execution :
      ConcreteExecutionMatchesSource inputBytes outputBytes) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.byteArrayLowerHex
        outputBytes =
      SHA256.digestByteArray inputBytes := by
  rw [execution]
  exact cDigestByteArray_refines inputBytes

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement
