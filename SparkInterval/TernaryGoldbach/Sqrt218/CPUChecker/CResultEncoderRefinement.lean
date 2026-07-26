/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultSemantics

/-!
# Source-level refinement of the Sqrt218 V2 C result encoder

This module models `tg_sq218_encode_result_v2` from
`cpu_checker/sqrt218/sqrt218_cpu_command.c`.  The model follows the exact
120-byte source layout and the source big-endian writes.  It proves that the
strict `ResultWire` decoder recovers the same status, input metadata, result
limbs, and 32 digest bytes.

The public wrapper always calls the static encoder with a non-null result
pointer.  On nonzero checker status the C source leaves all eight result limbs
at the zero value installed by its initial clearing loop; `selectedResult`
models that branch exactly.

These are C-source arithmetic and wire-format theorems.  They do not claim
compiler, ELF, ISA, operating-system, or physical execution refinement.
No production input or result is evaluated here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

/-- Source spelling of a cast to `uint8_t` after an unsigned right shift. -/
def cByteAt (shift value : Nat) : UInt8 :=
  UInt8.ofNat (value / 2 ^ shift)

/-- Source spelling of `tg_result_put_be16`. -/
def cPutBE16 (value : Nat) : List UInt8 :=
  [cByteAt 8 value, cByteAt 0 value]

/-- Source spelling of `tg_result_put_be32`. -/
def cPutBE32 (value : Nat) : List UInt8 :=
  [cByteAt 24 value, cByteAt 16 value,
    cByteAt 8 value, cByteAt 0 value]

/-- Source spelling of `tg_result_put_be64`. -/
def cPutBE64 (value : Nat) : List UInt8 :=
  [cByteAt 56 value, cByteAt 48 value,
    cByteAt 40 value, cByteAt 32 value,
    cByteAt 24 value, cByteAt 16 value,
    cByteAt 8 value, cByteAt 0 value]

private theorem byteArray_get!_eq_getElem
    (raw : ByteArray) (index : Nat) (hindex : index < raw.size) :
    raw.get! index = raw[index] := by
  cases raw with
  | mk data =>
      exact getElem!_pos data index hindex

theorem readBE16_cPutBE16
    {value : Nat} (hvalue : value < 2 ^ 16) :
    readBE16 (cPutBE16 value).toByteArray 0 =
      some value := by
  unfold readBE16 readBE
  rw [if_pos (by simp [cPutBE16])]
  have h0 :
      (cPutBE16 value).toByteArray.get! 0 = cByteAt 8 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE16])]
    simp [cPutBE16]
  have h1 :
      (cPutBE16 value).toByteArray.get! 1 = cByteAt 0 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE16])]
    simp [cPutBE16]
  rw [show List.range 2 = [0, 1] by decide]
  simp only [List.foldl_cons, List.foldl_nil, h0, h1]
  simp only [cByteAt]
  norm_num at hvalue ⊢
  omega

theorem readBE32_cPutBE32
    {value : Nat} (hvalue : value < 2 ^ 32) :
    readBE32 (cPutBE32 value).toByteArray 0 =
      some value := by
  unfold readBE32 readBE
  rw [if_pos (by simp [cPutBE32])]
  have h0 :
      (cPutBE32 value).toByteArray.get! 0 = cByteAt 24 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE32])]
    simp [cPutBE32]
  have h1 :
      (cPutBE32 value).toByteArray.get! 1 = cByteAt 16 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE32])]
    simp [cPutBE32]
  have h2 :
      (cPutBE32 value).toByteArray.get! 2 = cByteAt 8 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE32])]
    simp [cPutBE32]
  have h3 :
      (cPutBE32 value).toByteArray.get! 3 = cByteAt 0 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE32])]
    simp [cPutBE32]
  rw [show List.range 4 = [0, 1, 2, 3] by decide]
  simp only [List.foldl_cons, List.foldl_nil, h0, h1, h2, h3,
    cByteAt]
  norm_num at hvalue ⊢
  omega

theorem readBE64_cPutBE64
    {value : Nat} (hvalue : value < 2 ^ 64) :
    readBE64 (cPutBE64 value).toByteArray 0 =
      some value := by
  unfold readBE64 readBE
  rw [if_pos (by simp [cPutBE64])]
  have h0 :
      (cPutBE64 value).toByteArray.get! 0 = cByteAt 56 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  have h1 :
      (cPutBE64 value).toByteArray.get! 1 = cByteAt 48 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  have h2 :
      (cPutBE64 value).toByteArray.get! 2 = cByteAt 40 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  have h3 :
      (cPutBE64 value).toByteArray.get! 3 = cByteAt 32 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  have h4 :
      (cPutBE64 value).toByteArray.get! 4 = cByteAt 24 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  have h5 :
      (cPutBE64 value).toByteArray.get! 5 = cByteAt 16 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  have h6 :
      (cPutBE64 value).toByteArray.get! 6 = cByteAt 8 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  have h7 :
      (cPutBE64 value).toByteArray.get! 7 = cByteAt 0 value := by
    rw [byteArray_get!_eq_getElem _ _ (by simp [cPutBE64])]
    simp [cPutBE64]
  rw [show List.range 8 = [0, 1, 2, 3, 4, 5, 6, 7] by decide]
  simp only [List.foldl_cons, List.foldl_nil, h0, h1, h2, h3,
    h4, h5, h6, h7, cByteAt]
  norm_num at hvalue ⊢
  omega

private theorem foldl_congr_of_mem
    {α β : Type}
    (left right : β → α → β)
    (initial : β) (values : List α)
    (heq : ∀ accumulator value, value ∈ values →
      left accumulator value = right accumulator value) :
    values.foldl left initial = values.foldl right initial := by
  induction values generalizing initial with
  | nil =>
      rfl
  | cons head tail ih =>
      simp only [List.foldl_cons]
      rw [heq initial head (by simp)]
      apply ih
      intro accumulator value hvalue
      exact heq accumulator value (by simp [hvalue])

/-- Reading a field is equivalent to reading its exact extracted byte slice
at offset zero. -/
theorem readBE_eq_extract
    (width : Nat) (raw : ByteArray) (offset : Nat)
    (hbound : offset + width ≤ raw.size) :
    readBE width raw offset =
      readBE width (raw.extract offset (offset + width)) 0 := by
  unfold readBE
  have hextractSize :
      (raw.extract offset (offset + width)).size = width := by
    simp only [ByteArray.size_extract]
    omega
  rw [if_pos hbound,
    if_pos (by simp [hextractSize])]
  apply congrArg some
  apply foldl_congr_of_mem
  intro accumulator index hindex
  have hindexWidth : index < width :=
    List.mem_range.mp hindex
  have hrawIndex : offset + index < raw.size := by
    omega
  have hextractIndex :
      index < (raw.extract offset (offset + width)).size := by
    simpa only [hextractSize]
  rw [byteArray_get!_eq_getElem raw (offset + index) hrawIndex]
  simp only [Nat.zero_add]
  rw [byteArray_get!_eq_getElem
      (raw.extract offset (offset + width)) index hextractIndex,
    ByteArray.getElem_extract]

theorem readBE16_of_slice
    (raw : ByteArray) (offset value : Nat)
    (hbound : offset + 2 ≤ raw.size)
    (hslice :
      raw.extract offset (offset + 2) =
        (cPutBE16 value).toByteArray)
    (hvalue : value < 2 ^ 16) :
    readBE16 raw offset = some value := by
  calc
    readBE16 raw offset =
        readBE16 (raw.extract offset (offset + 2)) 0 :=
      readBE_eq_extract 2 raw offset hbound
    _ = readBE16 (cPutBE16 value).toByteArray 0 := by
      rw [hslice]
    _ = some value := readBE16_cPutBE16 hvalue

theorem readBE32_of_slice
    (raw : ByteArray) (offset value : Nat)
    (hbound : offset + 4 ≤ raw.size)
    (hslice :
      raw.extract offset (offset + 4) =
        (cPutBE32 value).toByteArray)
    (hvalue : value < 2 ^ 32) :
    readBE32 raw offset = some value := by
  calc
    readBE32 raw offset =
        readBE32 (raw.extract offset (offset + 4)) 0 :=
      readBE_eq_extract 4 raw offset hbound
    _ = readBE32 (cPutBE32 value).toByteArray 0 := by
      rw [hslice]
    _ = some value := readBE32_cPutBE32 hvalue

theorem readBE64_of_slice
    (raw : ByteArray) (offset value : Nat)
    (hbound : offset + 8 ≤ raw.size)
    (hslice :
      raw.extract offset (offset + 8) =
        (cPutBE64 value).toByteArray)
    (hvalue : value < 2 ^ 64) :
    readBE64 raw offset = some value := by
  calc
    readBE64 raw offset =
        readBE64 (raw.extract offset (offset + 8)) 0 :=
      readBE_eq_extract 8 raw offset hbound
    _ = readBE64 (cPutBE64 value).toByteArray 0 := by
      rw [hslice]
    _ = some value := readBE64_cPutBE64 hvalue

/-! ## Exact source record model -/

/-- Fixed-width source image of `tg_sq218_validation_result_v2`. -/
structure CValidationResult where
  nextEvent : UInt64
  lastEventValue : UInt64
  weightedUpperHigh : UInt64
  weightedUpperLow : UInt64
  psiLowerHigh : UInt64
  psiLowerLow : UInt64
  anchorSlackHigh : UInt64
  anchorSlackLow : UInt64
  deriving Repr, DecidableEq

def CValidationResult.zero : CValidationResult := {
  nextEvent := 0
  lastEventValue := 0
  weightedUpperHigh := 0
  weightedUpperLow := 0
  psiLowerHigh := 0
  psiLowerLow := 0
  anchorSlackHigh := 0
  anchorSlackLow := 0
}

/-- The source condition
`status == TG_SQ218_OK && result != NULL`, specialized to the public wrapper's
non-null `&result` call. -/
def selectedResult
    (status : UInt32) (result : CValidationResult) : CValidationResult :=
  if status.toNat = 0 then result else CValidationResult.zero

/-- The exact typed record denoted by the C source fields. -/
def expectedRecord
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) : NativeResultRecord :=
  let selected := selectedResult status result
  {
    status := status.toNat
    inputByteLength := inputBytes.toNat
    nextEventIndex := selected.nextEvent.toNat
    lastEventValue := selected.lastEventValue.toNat
    weightedUpper :=
      ⟨selected.weightedUpperHigh.toNat,
        selected.weightedUpperLow.toNat⟩
    psiLower :=
      ⟨selected.psiLowerHigh.toNat, selected.psiLowerLow.toNat⟩
    anchorSlack :=
      ⟨selected.anchorSlackHigh.toNat, selected.anchorSlackLow.toNat⟩
    inputSHA256 := byteArrayLowerHex snapshotSHA256
  }

/-- Architecture-neutral arithmetic meaning of the successful C validation
result structure.  Every source `uint64_t` field is interpreted by its exact
mathematical value; no archive computation occurs here. -/
def CValidationResult.arithmeticResult
    (result : CValidationResult) : ArithmeticResult := {
  state := {
    nextEvent := result.nextEvent.toNat
    lastEventValue := result.lastEventValue.toNat
    weightedUpper :=
      ⟨result.weightedUpperHigh.toNat,
        result.weightedUpperLow.toNat⟩
    psiLower :=
      ⟨result.psiLowerHigh.toNat, result.psiLowerLow.toNat⟩
  }
  anchorSlack :=
    ⟨result.anchorSlackHigh.toNat, result.anchorSlackLow.toNat⟩
}

/-- On successful checker status, the strict wire record denotes exactly the
arithmetic value of the source validation structure. -/
@[simp] theorem expectedRecord_zero_arithmeticResult
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (expectedRecord
        (0 : UInt32) inputBytes result snapshotSHA256).arithmeticResult =
      result.arithmeticResult := by
  rfl

/-- Concatenate a source record's adjacent byte regions. -/
def appendBlocks : List ByteArray → ByteArray
  | [] => ByteArray.empty
  | block :: rest => block ++ appendBlocks rest

/-- Total byte width of adjacent source record regions. -/
def blocksByteSize : List ByteArray → Nat
  | [] => 0
  | block :: rest => block.size + blocksByteSize rest

@[simp] theorem appendBlocks_size (blocks : List ByteArray) :
    (appendBlocks blocks).size = blocksByteSize blocks := by
  induction blocks with
  | nil =>
      rfl
  | cons block rest ih =>
      simp [appendBlocks, blocksByteSize, ih]

/-- A block's offset is the total width of the blocks before it. -/
inductive BlockAt : Nat → ByteArray → List ByteArray → Prop where
  | head (block : ByteArray) (rest : List ByteArray) :
      BlockAt 0 block (block :: rest)
  | tail {offset : Nat} {block first : ByteArray}
      {rest : List ByteArray} :
      BlockAt offset block rest →
      BlockAt (first.size + offset) block (first :: rest)

namespace BlockAt

theorem of_get?
    {blocks : List ByteArray} {index : Nat} {block : ByteArray}
    (hget : blocks[index]? = some block) :
    BlockAt (blocksByteSize (blocks.take index)) block blocks := by
  induction blocks generalizing index with
  | nil =>
      simp at hget
  | cons first rest ih =>
      cases index with
      | zero =>
          simp at hget
          subst block
          simpa [blocksByteSize] using BlockAt.head first rest
      | succ index =>
          simp at hget
          have located := ih hget
          simpa [blocksByteSize] using
            (BlockAt.tail (first := first) located)

theorem extract
    {offset : Nat} {block : ByteArray} {blocks : List ByteArray}
    (located : BlockAt offset block blocks) :
    (appendBlocks blocks).extract offset (offset + block.size) =
      block := by
  induction located with
  | head block rest =>
      unfold appendBlocks
      simpa only [Nat.zero_add] using
        (ByteArray.extract_append_eq_left
          (a := block) (b := appendBlocks rest)
          (i := block.size) rfl)
  | @tail offset block first rest located ih =>
      unfold appendBlocks
      calc
        (first ++ appendBlocks rest).extract
            (first.size + offset)
            (first.size + offset + block.size) =
            (appendBlocks rest).extract offset
              (offset + block.size) := by
          simpa only [Nat.add_assoc] using
            (ByteArray.extract_append_size_add
              (a := first) (b := appendBlocks rest)
              (i := offset) (j := offset + block.size))
        _ = block := ih

end BlockAt

/-- The thirteen fully overwritten fixed regions followed by the exact
32-byte digest region. -/
def cResultBlocks
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) : List ByteArray :=
  let selected := selectedResult status result
  [
    nativeResultMagic.toByteArray,
    (cPutBE16 nativeResultVersion).toByteArray,
    (cPutBE16 nativeResultByteWidth).toByteArray,
    (cPutBE32 status.toNat).toByteArray,
    (cPutBE64 inputBytes.toNat).toByteArray,
    (cPutBE64 selected.nextEvent.toNat).toByteArray,
    (cPutBE64 selected.lastEventValue.toNat).toByteArray,
    (cPutBE64 selected.weightedUpperHigh.toNat).toByteArray,
    (cPutBE64 selected.weightedUpperLow.toNat).toByteArray,
    (cPutBE64 selected.psiLowerHigh.toNat).toByteArray,
    (cPutBE64 selected.psiLowerLow.toNat).toByteArray,
    (cPutBE64 selected.anchorSlackHigh.toNat).toByteArray,
    (cPutBE64 selected.anchorSlackLow.toNat).toByteArray,
    snapshotSHA256
  ]

/-- Exact block-concatenation model of `tg_sq218_encode_result_v2`.

The C function first clears all 120 bytes, then overwrites these adjacent
ranges.  On a nonzero status `selectedResult` is zero, so offsets 24--87
retain the zero bytes from that clearing loop. -/
def cEncodeResultV2
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) : ByteArray :=
  appendBlocks (cResultBlocks status inputBytes result snapshotSHA256)

theorem cEncodeResultV2_size
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    (hdigest : snapshotSHA256.size = 32) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).size =
      nativeResultByteWidth := by
  simp [cEncodeResultV2, cResultBlocks, blocksByteSize,
    cPutBE16, cPutBE32, cPutBE64, nativeResultMagic,
    nativeResultByteWidth, hdigest]

private theorem cResultBlock_extract
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    (offset : Nat)
    (block : ByteArray)
    (hlocated :
      BlockAt offset block
        (cResultBlocks status inputBytes result snapshotSHA256)) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract
        offset (offset + block.size) =
      block :=
  hlocated.extract

private theorem cResultBlock_extract_index
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    {index : Nat} {block : ByteArray}
    (hget :
      (cResultBlocks status inputBytes result snapshotSHA256)[index]? =
        some block) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract
        (blocksByteSize
          ((cResultBlocks status inputBytes result snapshotSHA256).take index))
        (blocksByteSize
            ((cResultBlocks status inputBytes result snapshotSHA256).take index) +
          block.size) =
      block :=
  (BlockAt.of_get? hget).extract

theorem cEncodeResultV2_magic
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 0 8 =
      nativeResultMagic.toByteArray := by
  have hlocated :
      BlockAt 0 nativeResultMagic.toByteArray
        (cResultBlocks status inputBytes result snapshotSHA256) := by
    unfold cResultBlocks
    exact .head _ _
  have hextract :=
    cResultBlock_extract status inputBytes result snapshotSHA256
      0 nativeResultMagic.toByteArray hlocated
  simpa [nativeResultMagic] using hextract

theorem cEncodeResultV2_versionSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 8 10 =
      (cPutBE16 nativeResultVersion).toByteArray := by
  have hlocated :
      BlockAt 8 (cPutBE16 nativeResultVersion).toByteArray
        (cResultBlocks status inputBytes result snapshotSHA256) := by
    unfold cResultBlocks
    simpa [nativeResultMagic] using
      (BlockAt.tail (first := nativeResultMagic.toByteArray)
        (BlockAt.head
          (cPutBE16 nativeResultVersion).toByteArray _))
  have hextract :=
    cResultBlock_extract status inputBytes result snapshotSHA256
      8 (cPutBE16 nativeResultVersion).toByteArray hlocated
  simpa [cPutBE16] using hextract

theorem cEncodeResultV2_widthSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 10 12 =
      (cPutBE16 nativeResultByteWidth).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 2)
      (block := (cPutBE16 nativeResultByteWidth).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16] using hextract

theorem cEncodeResultV2_statusSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 12 16 =
      (cPutBE32 status.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 3)
      (block := (cPutBE32 status.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32] using hextract

theorem cEncodeResultV2_inputLengthSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 16 24 =
      (cPutBE64 inputBytes.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 4)
      (block := (cPutBE64 inputBytes.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_nextEventSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 24 32 =
      (cPutBE64
        (selectedResult status result).nextEvent.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 5)
      (block :=
        (cPutBE64
          (selectedResult status result).nextEvent.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_lastEventSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 32 40 =
      (cPutBE64
        (selectedResult status result).lastEventValue.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 6)
      (block :=
        (cPutBE64
          (selectedResult status result).lastEventValue.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_weightedUpperHighSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 40 48 =
      (cPutBE64
        (selectedResult status result).weightedUpperHigh.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 7)
      (block :=
        (cPutBE64
          (selectedResult status result).weightedUpperHigh.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_weightedUpperLowSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 48 56 =
      (cPutBE64
        (selectedResult status result).weightedUpperLow.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 8)
      (block :=
        (cPutBE64
          (selectedResult status result).weightedUpperLow.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_psiLowerHighSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 56 64 =
      (cPutBE64
        (selectedResult status result).psiLowerHigh.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 9)
      (block :=
        (cPutBE64
          (selectedResult status result).psiLowerHigh.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_psiLowerLowSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 64 72 =
      (cPutBE64
        (selectedResult status result).psiLowerLow.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 10)
      (block :=
        (cPutBE64
          (selectedResult status result).psiLowerLow.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_anchorSlackHighSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 72 80 =
      (cPutBE64
        (selectedResult status result).anchorSlackHigh.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 11)
      (block :=
        (cPutBE64
          (selectedResult status result).anchorSlackHigh.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_anchorSlackLowSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 80 88 =
      (cPutBE64
        (selectedResult status result).anchorSlackLow.toNat).toByteArray := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 12)
      (block :=
        (cPutBE64
          (selectedResult status result).anchorSlackLow.toNat).toByteArray)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64] using hextract

theorem cEncodeResultV2_digestSlice
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    (hdigest : snapshotSHA256.size = 32) :
    (cEncodeResultV2 status inputBytes result snapshotSHA256).extract 88 120 =
      snapshotSHA256 := by
  have hextract :=
    cResultBlock_extract_index status inputBytes result snapshotSHA256
      (index := 13) (block := snapshotSHA256)
      (by simp [cResultBlocks])
  simpa [cResultBlocks, blocksByteSize, nativeResultMagic,
    cPutBE16, cPutBE32, cPutBE64, hdigest] using hextract

theorem expectedRecord_canonical
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray) :
    (expectedRecord status inputBytes result snapshotSHA256).status = 0 ∨
      stateAndSlackAreZero
        (expectedRecord status inputBytes result snapshotSHA256) = true := by
  by_cases hstatus : status.toNat = 0
  · exact Or.inl (by simpa [expectedRecord] using hstatus)
  · right
    simp [expectedRecord, selectedResult, hstatus,
      CValidationResult.zero, stateAndSlackAreZero, U128.zero]

/-- The exact C source encoder establishes every field fact required by the
strict 120-byte decoder. -/
theorem cEncodeResultV2_facts
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    (hdigest : snapshotSHA256.size = 32)
    (hstatus : status.toNat ≤ 5) :
    NativeResultByteFacts
      (cEncodeResultV2 status inputBytes result snapshotSHA256)
      (expectedRecord status inputBytes result snapshotSHA256) := by
  let raw := cEncodeResultV2 status inputBytes result snapshotSHA256
  let record := expectedRecord status inputBytes result snapshotSHA256
  have hsize : raw.size = nativeResultByteWidth := by
    simpa [raw] using
      cEncodeResultV2_size status inputBytes result snapshotSHA256 hdigest
  have fieldBound (offset width : Nat)
      (h : offset + width ≤ nativeResultByteWidth) :
      offset + width ≤ raw.size := by
    rw [hsize]
    exact h
  refine {
    byteWidth := hsize
    magic := by
      simpa [raw] using
        cEncodeResultV2_magic status inputBytes result snapshotSHA256
    version := ?_
    encodedWidth := ?_
    status := ?_
    statusRange := by
      simpa [record, expectedRecord] using hstatus
    inputByteLength := ?_
    nextEventIndex := ?_
    lastEventValue := ?_
    weightedUpperHigh := ?_
    weightedUpperLow := ?_
    psiLowerHigh := ?_
    psiLowerLow := ?_
    anchorSlackHigh := ?_
    anchorSlackLow := ?_
    inputSHA256 := ?_
    canonical := by
      simpa [record] using
        expectedRecord_canonical
          status inputBytes result snapshotSHA256
  }
  · apply readBE16_of_slice raw 8 nativeResultVersion
    · exact fieldBound 8 2 (by norm_num [nativeResultByteWidth])
    · simpa [raw] using
        cEncodeResultV2_versionSlice
          status inputBytes result snapshotSHA256
    · norm_num [nativeResultVersion]
  · apply readBE16_of_slice raw 10 nativeResultByteWidth
    · exact fieldBound 10 2 (by norm_num [nativeResultByteWidth])
    · simpa [raw] using
        cEncodeResultV2_widthSlice
          status inputBytes result snapshotSHA256
    · norm_num [nativeResultByteWidth]
  · have hread :=
      readBE32_of_slice raw 12 status.toNat
        (fieldBound 12 4 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_statusSlice
              status inputBytes result snapshotSHA256))
        (UInt32.toNat_lt status)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 16 inputBytes.toNat
        (fieldBound 16 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_inputLengthSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt inputBytes)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 24
        (selectedResult status result).nextEvent.toNat
        (fieldBound 24 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_nextEventSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).nextEvent)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 32
        (selectedResult status result).lastEventValue.toNat
        (fieldBound 32 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_lastEventSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).lastEventValue)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 40
        (selectedResult status result).weightedUpperHigh.toNat
        (fieldBound 40 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_weightedUpperHighSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).weightedUpperHigh)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 48
        (selectedResult status result).weightedUpperLow.toNat
        (fieldBound 48 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_weightedUpperLowSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).weightedUpperLow)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 56
        (selectedResult status result).psiLowerHigh.toNat
        (fieldBound 56 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_psiLowerHighSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).psiLowerHigh)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 64
        (selectedResult status result).psiLowerLow.toNat
        (fieldBound 64 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_psiLowerLowSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).psiLowerLow)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 72
        (selectedResult status result).anchorSlackHigh.toNat
        (fieldBound 72 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_anchorSlackHighSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).anchorSlackHigh)
    simpa [record, expectedRecord] using hread
  · have hread :=
      readBE64_of_slice raw 80
        (selectedResult status result).anchorSlackLow.toNat
        (fieldBound 80 8 (by norm_num [nativeResultByteWidth]))
        (by
          simpa [raw] using
            (cEncodeResultV2_anchorSlackLowSlice
              status inputBytes result snapshotSHA256))
        (UInt64.toNat_lt (selectedResult status result).anchorSlackLow)
    simpa [record, expectedRecord] using hread
  · have hdigestSlice :=
      cEncodeResultV2_digestSlice
        status inputBytes result snapshotSHA256 hdigest
    simpa [raw, record, expectedRecord] using
      congrArg byteArrayLowerHex hdigestSlice

/-- The source-level model of `tg_sq218_encode_result_v2` is accepted by the
strict native-result decoder as exactly the record it encodes.  The only
runtime-side premises are the C wrapper's fixed 32-byte digest width and its
documented status range. -/
theorem decodeNativeResultBytes_cEncodeResultV2
    (status : UInt32)
    (inputBytes : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    (hdigest : snapshotSHA256.size = 32)
    (hstatus : status.toNat ≤ 5) :
    decodeNativeResultBytes
        (cEncodeResultV2 status inputBytes result snapshotSHA256) =
      .ok (expectedRecord status inputBytes result snapshotSHA256) :=
  decodeNativeResultBytes_of_facts
    (cEncodeResultV2_facts
      status inputBytes result snapshotSHA256 hdigest hstatus)

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderRefinement
