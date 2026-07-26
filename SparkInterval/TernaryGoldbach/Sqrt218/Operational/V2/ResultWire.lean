/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Fixed128

/-!
# Fixed-width Sqrt218 V2 native-result wire format

This low-level module parses the complete 120-byte `SQ218R2\0` native result
and its canonical ASCII receipt envelope.  It imports neither execution
receipts nor the registered-algorithm catalog, so the closed registry can use
the parser in its `Runs` relation without an import cycle.

No production certificate or event loop occurs in this module.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

/-- Exact ASCII discriminator placed before the complete binary result in
lowercase hexadecimal. -/
def resultEnvelopePrefix : String :=
  "sparkinterval.sqrt218-fixed-v2-result.v1:"

def nativeResultMagic : List UInt8 :=
  [0x53, 0x51, 0x32, 0x31, 0x38, 0x52, 0x32, 0x00]

def nativeResultVersion : Nat := 1
def nativeResultByteWidth : Nat := 120

/-- Read one fixed-width unsigned big-endian natural after an in-bounds
check.  This is public so source-level encoder refinements can prove exact
round trips against the wire parser. -/
def readBE
    (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat :=
  if offset + width ≤ raw.size then
    some ((List.range width).foldl
      (fun value index =>
        256 * value + (raw.get! (offset + index)).toNat) 0)
  else
    none

def readBE16 (raw : ByteArray) (offset : Nat) : Option Nat :=
  readBE 2 raw offset

def readBE32 (raw : ByteArray) (offset : Nat) : Option Nat :=
  readBE 4 raw offset

def readBE64 (raw : ByteArray) (offset : Nat) : Option Nat :=
  readBE 8 raw offset

/-- Public one-nibble encoder used by source-level result refinements. -/
def lowerHexDigit (value : Nat) : Char :=
  "0123456789abcdef".toList.getD value '0'

/-- Public exact two-character byte encoder used by source-level result
refinements. -/
def byteLowerHex (value : UInt8) : List Char :=
  [lowerHexDigit (value.toNat / 16), lowerHexDigit (value.toNat % 16)]

/-- Exact lowercase hexadecimal spelling of every byte, with no prefix,
separators, or newline. -/
def byteArrayLowerHex (raw : ByteArray) : String :=
  String.ofList (raw.toList.flatMap byteLowerHex)

private def lowerHexNibble (character : Char) : Option Nat :=
  if '0' ≤ character ∧ character ≤ '9' then
    some (character.toNat - '0'.toNat)
  else if 'a' ≤ character ∧ character ≤ 'f' then
    some (10 + character.toNat - 'a'.toNat)
  else
    none

private def decodeLowerHexChars : List Char → Option (List UInt8)
  | [] => some []
  | high :: low :: rest => do
      let highValue ← lowerHexNibble high
      let lowValue ← lowerHexNibble low
      let tail ← decodeLowerHexChars rest
      pure (UInt8.ofNat (16 * highValue + lowValue) :: tail)
  | _ => none

/-- Decode lowercase hexadecimal only.  Odd length, uppercase, prefixes, and
non-hexadecimal characters are rejected. -/
def decodeLowerHex (text : String) : Option ByteArray :=
  (decodeLowerHexChars text.toList).map List.toByteArray

private theorem lowerHexNibble_lowerHexDigit
    (value : Nat) (hvalue : value < 16) :
    lowerHexNibble (lowerHexDigit value) = some value := by
  interval_cases value <;> decide

private theorem decodeLowerHexChars_flatMap_byteLowerHex
    (bytes : List UInt8) :
    decodeLowerHexChars (bytes.flatMap byteLowerHex) = some bytes := by
  induction bytes with
  | nil =>
      rfl
  | cons byte bytes ih =>
      have hbyte : byte.toNat < 256 := by
        have := UInt8.toNat_lt byte
        norm_num at this ⊢
        exact this
      have hhigh : byte.toNat / 16 < 16 :=
        Nat.div_lt_of_lt_mul hbyte
      have hlow : byte.toNat % 16 < 16 :=
        Nat.mod_lt _ (by norm_num)
      have hreconstruct :
          UInt8.ofNat
              (16 * (byte.toNat / 16) + byte.toNat % 16) =
            byte := by
        rw [Nat.div_add_mod byte.toNat 16]
        exact UInt8.ofNat_toNat
      simp only [List.flatMap_cons, byteLowerHex, List.cons_append,
        List.nil_append, decodeLowerHexChars,
        lowerHexNibble_lowerHexDigit _ hhigh,
        lowerHexNibble_lowerHexDigit _ hlow, ih]
      exact congrArg (fun value => some (value :: bytes)) hreconstruct

private theorem byteArray_toList_loop_eq
    (raw : ByteArray) (index : Nat) (reversedPrefix : List UInt8) :
    ByteArray.toList.loop raw index reversedPrefix =
      reversedPrefix.reverse ++ raw.data.toList.drop index := by
  fun_induction ByteArray.toList.loop raw index reversedPrefix with
  | case1 index reversedPrefix hindex ih =>
      rw [ih]
      have hlist : index < raw.data.toList.length := by
        simpa using hindex
      have hdrop :
          raw.data.toList.drop index =
            raw.data.toList[index] ::
              raw.data.toList.drop (index + 1) :=
        List.drop_eq_getElem_cons hlist
      have hget :
          raw.get! index = raw.data.toList[index] := by
        cases raw with
        | mk data =>
            exact getElem!_pos data index hindex
      rw [hdrop, hget]
      simp
  | case2 index reversedPrefix hindex =>
      rw [List.drop_eq_nil_of_le]
      · simp
      · simpa using hindex

/-- Converting a byte array to a list and back preserves it.  Public for
source-level byte-serialization refinements. -/
theorem toByteArray_toList (raw : ByteArray) :
    raw.toList.toByteArray = raw := by
  rw [show raw.toList = raw.data.toList by
    simpa [ByteArray.toList] using
      byteArray_toList_loop_eq raw 0 []]
  apply ByteArray.ext
  simp

/-- Converting a byte list to an array and back preserves the exact list. -/
theorem toList_toByteArray (bytes : List UInt8) :
    bytes.toByteArray.toList = bytes := by
  have h := congrArg (fun raw : ByteArray => raw.data.toList)
    (toByteArray_toList bytes.toByteArray)
  simpa using h

/-- Lowercase hexadecimal encoding and strict lowercase decoding are exact
inverses on arbitrary byte arrays.  This is a symbolic theorem; it does not
evaluate a production payload. -/
theorem decodeLowerHex_byteArrayLowerHex (raw : ByteArray) :
    decodeLowerHex (byteArrayLowerHex raw) = some raw := by
  simp only [decodeLowerHex, byteArrayLowerHex,
    String.toList_ofList, decodeLowerHexChars_flatMap_byteLowerHex,
    Option.map_some, toByteArray_toList]

/-- Complete typed view of one 120-byte native wrapper result. -/
structure NativeResultRecord where
  status : Nat
  inputByteLength : Nat
  nextEventIndex : Nat
  lastEventValue : Nat
  weightedUpper : U128
  psiLower : U128
  anchorSlack : U128
  /-- Lowercase hexadecimal encoding of the raw 32 bytes at offsets 88..119. -/
  inputSHA256 : String
  deriving Repr, DecidableEq

/-- Canonical rejection records contain zero in every arithmetic-result
field.  Public visibility supports the C encoder refinement; the definition
is unchanged. -/
def stateAndSlackAreZero (record : NativeResultRecord) : Bool :=
  decide (
    record.nextEventIndex = 0 ∧
      record.lastEventValue = 0 ∧
      record.weightedUpper = U128.zero ∧
      record.psiLower = U128.zero ∧
      record.anchorSlack = U128.zero)

/-- Pure parser core exposed for byte-level source-encoder refinements. -/
def parseNativeResultBytes? (raw : ByteArray) :
    Option NativeResultRecord := do
  if raw.size = nativeResultByteWidth then pure () else none
  if raw.extract 0 8 = nativeResultMagic.toByteArray then pure () else none
  let version ← readBE16 raw 8
  if version = nativeResultVersion then pure () else none
  let width ← readBE16 raw 10
  if width = nativeResultByteWidth then pure () else none
  let status ← readBE32 raw 12
  if status ≤ 5 then pure () else none
  let inputByteLength ← readBE64 raw 16
  let nextEventIndex ← readBE64 raw 24
  let lastEventValue ← readBE64 raw 32
  let weightedUpperHigh ← readBE64 raw 40
  let weightedUpperLow ← readBE64 raw 48
  let psiLowerHigh ← readBE64 raw 56
  let psiLowerLow ← readBE64 raw 64
  let anchorSlackHigh ← readBE64 raw 72
  let anchorSlackLow ← readBE64 raw 80
  let record : NativeResultRecord := {
    status
    inputByteLength
    nextEventIndex
    lastEventValue
    weightedUpper := ⟨weightedUpperHigh, weightedUpperLow⟩
    psiLower := ⟨psiLowerHigh, psiLowerLow⟩
    anchorSlack := ⟨anchorSlackHigh, anchorSlackLow⟩
    inputSHA256 := byteArrayLowerHex (raw.extract 88 120)
  }
  if status = 0 ∨ stateAndSlackAreZero record then
    some record
  else
    none

/-- Strict parser for the fixed 120-byte `SQ218R2\0` result record. -/
def decodeNativeResultBytes (raw : ByteArray) :
    Except String NativeResultRecord :=
  match parseNativeResultBytes? raw with
  | some record => .ok record
  | none => .error "invalid fixed-width Sqrt218 V2 native result"

/-- Field-by-field facts sufficient for the strict native-result parser.

This is the public proof interface for source encoders.  It retains every
read performed by `parseNativeResultBytes?`, including the complete digest
slice and the canonical zero-state condition for nonzero statuses. -/
structure NativeResultByteFacts
    (raw : ByteArray) (record : NativeResultRecord) : Prop where
  byteWidth : raw.size = nativeResultByteWidth
  magic : raw.extract 0 8 = nativeResultMagic.toByteArray
  version : readBE16 raw 8 = some nativeResultVersion
  encodedWidth : readBE16 raw 10 = some nativeResultByteWidth
  status : readBE32 raw 12 = some record.status
  statusRange : record.status ≤ 5
  inputByteLength :
    readBE64 raw 16 = some record.inputByteLength
  nextEventIndex :
    readBE64 raw 24 = some record.nextEventIndex
  lastEventValue :
    readBE64 raw 32 = some record.lastEventValue
  weightedUpperHigh :
    readBE64 raw 40 = some record.weightedUpper.hi
  weightedUpperLow :
    readBE64 raw 48 = some record.weightedUpper.lo
  psiLowerHigh :
    readBE64 raw 56 = some record.psiLower.hi
  psiLowerLow :
    readBE64 raw 64 = some record.psiLower.lo
  anchorSlackHigh :
    readBE64 raw 72 = some record.anchorSlack.hi
  anchorSlackLow :
    readBE64 raw 80 = some record.anchorSlack.lo
  inputSHA256 :
    byteArrayLowerHex (raw.extract 88 120) = record.inputSHA256
  canonical :
    record.status = 0 ∨ stateAndSlackAreZero record = true

/-- The public field facts reconstruct exactly the strict decoder result. -/
theorem decodeNativeResultBytes_of_facts
    {raw : ByteArray} {record : NativeResultRecord}
    (facts : NativeResultByteFacts raw record) :
    decodeNativeResultBytes raw = .ok record := by
  unfold decodeNativeResultBytes parseNativeResultBytes?
  simp only [facts.byteWidth, facts.magic, facts.version,
    facts.encodedWidth, facts.status, facts.inputByteLength,
    facts.nextEventIndex, facts.lastEventValue,
    facts.weightedUpperHigh, facts.weightedUpperLow,
    facts.psiLowerHigh, facts.psiLowerLow,
    facts.anchorSlackHigh, facts.anchorSlackLow,
    facts.inputSHA256]
  simp [facts.statusRange, facts.canonical]

/-- Encode all raw result bytes into the canonical theorem-authorizing
receipt string. -/
def encodeResultEnvelope (raw : ByteArray) : String :=
  resultEnvelopePrefix ++ byteArrayLowerHex raw

private def payloadAfterPrefix (text : String) : Option String :=
  let expectedPrefix := resultEnvelopePrefix.toList
  let characters := text.toList
  if characters.take expectedPrefix.length = expectedPrefix then
    some (String.ofList (characters.drop expectedPrefix.length))
  else
    none

private theorem payloadAfterPrefix_encodeResultEnvelope
    (raw : ByteArray) :
    payloadAfterPrefix (encodeResultEnvelope raw) =
      some (byteArrayLowerHex raw) := by
  simp [payloadAfterPrefix, encodeResultEnvelope, String.toList_append]

/-- Decode the exact result envelope and the complete native record.

The returned pair deliberately retains both the raw 120 bytes and their typed
view.  The final re-encoding comparison prevents alternate text spellings. -/
def decodeResultEnvelope
    (text : String) : Except String (ByteArray × NativeResultRecord) :=
  match payloadAfterPrefix text with
  | none => .error "missing fixed-width Sqrt218 V2 result prefix"
  | some payload =>
      match decodeLowerHex payload with
      | none => .error "invalid fixed-width Sqrt218 V2 lowercase hex"
      | some raw =>
          match decodeNativeResultBytes raw with
          | .error message => .error message
          | .ok record =>
              if encodeResultEnvelope raw = text then
                .ok (raw, record)
              else
                .error
                  "noncanonical fixed-width Sqrt218 V2 result envelope"

/-- Canonical envelope encoding introduces no new verification premise: if
the raw native bytes decode, encoding and immediately decoding the envelope
returns those exact bytes and that exact record. -/
theorem decodeResultEnvelope_encode_of_decodeNative
    {raw : ByteArray} {record : NativeResultRecord}
    (hdecode : decodeNativeResultBytes raw = .ok record) :
    decodeResultEnvelope (encodeResultEnvelope raw) =
      .ok (raw, record) := by
  unfold decodeResultEnvelope
  rw [payloadAfterPrefix_encodeResultEnvelope]
  simp only
  rw [decodeLowerHex_byteArrayLowerHex]
  simp only
  rw [hdecode]
  simp

/-- Acceptance is exactly native checker status zero. -/
def acceptedResultCheck (record : NativeResultRecord) : Bool :=
  decide (record.status = 0)

theorem acceptedResultCheck_sound {record : NativeResultRecord}
    (hcheck : acceptedResultCheck record = true) :
    record.status = 0 := by
  simpa [acceptedResultCheck] using hcheck

/-- Successful envelope decoding exposes the exact canonical spelling of all
returned bytes. -/
theorem decodeResultEnvelope_exact
    {text : String} {raw : ByteArray} {record : NativeResultRecord}
    (hdecode : decodeResultEnvelope text = .ok (raw, record)) :
    encodeResultEnvelope raw = text := by
  unfold decodeResultEnvelope at hdecode
  cases hpayload : payloadAfterPrefix text with
  | none =>
      simp [hpayload] at hdecode
  | some payload =>
      simp only [hpayload] at hdecode
      cases hraw : decodeLowerHex payload with
      | none =>
          simp [hraw] at hdecode
      | some decodedRaw =>
          simp only [hraw] at hdecode
          cases hrecord : decodeNativeResultBytes decodedRaw with
          | error message =>
              simp [hrecord] at hdecode
          | ok decodedRecord =>
              simp only [hrecord] at hdecode
              by_cases hcanonical :
                  encodeResultEnvelope decodedRaw = text
              · simp [hcanonical] at hdecode
                have hbytes : decodedRaw = raw := hdecode.1
                simpa [hbytes] using hcanonical
              · simp [hcanonical] at hdecode

/-- The strict result-envelope decoder is functional. -/
theorem decodeResultEnvelope_unique
    {text : String}
    {leftRaw rightRaw : ByteArray}
    {leftRecord rightRecord : NativeResultRecord}
    (hleft : decodeResultEnvelope text = .ok (leftRaw, leftRecord))
    (hright : decodeResultEnvelope text = .ok (rightRaw, rightRecord)) :
    leftRaw = rightRaw ∧ leftRecord = rightRecord := by
  rw [hleft] at hright
  exact Prod.mk.inj (Except.ok.inj hright)

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire
