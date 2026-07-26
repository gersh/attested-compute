/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinDFT
import SparkInterval.Dirichlet.CertifiedRootWire

/-!
# Checked wire format for positive-DFT basis-one output

The maximum-order semantic qualification applies the production positive DFT
to the vector with its only nonzero entry at index one.  Its exact output at
row `k` is therefore

```
exp(2*pi*i*k/order) = unitRoot order k.
```

This module supplies two layers:

* a generic exact-length checker for `order` consecutive 32-byte complex
  rectangles; and
* a parser/checker for the complete standard `TGDAFFO1` artifact.

The standard header is the exact 56-byte little-endian C layout
`<8sIIIIQQQQ>`.  The production capstone pins magic, version, q, component
count, batch count, group order, value count, and radix-2 butterfly count.
Only elapsed nanoseconds is intentionally allowed to vary between runs.

Every scan is source ordered and decodes one row at a time.  No decoded root
table is constructed.  The checker rejects a nonpositive basis-one geometry,
wrong file size, bad header, truncation, trailing bytes, non-finite binary64
words, reversed intervals, and the first failed exact-rational endpoint
comparison.

Acceptance proves a mathematical statement about the supplied bytes.  It
does not attest their provenance and does not prove refinement of a native or
CUDA producer.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedBasisOneOutputWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CertifiedRootWire

def wordBytes : Nat := 8
def recordBytes : Nat := 4 * wordBytes
def headerBytes : Nat := 56

def outputMagic : ByteArray :=
  "TGDAFFO1".toUTF8

/-- Bounds-checked unsigned little-endian decoding. -/
def readLE? (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat :=
  if offset + width ≤ raw.size then
    some <| (List.range width).foldl
      (fun value index =>
        value + (raw.get! (offset + index)).toNat * 256 ^ index) 0
  else
    none

def readU32LE? (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE? 4 raw offset

def readU64LE? (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE? wordBytes raw offset

def magicMatches (raw : ByteArray) : Bool :=
  raw.size ≥ outputMagic.size &&
    raw.extract 0 outputMagic.size == outputMagic

/-- The complete semantic header of one standard all-character output frame. -/
structure OutputHeader where
  version : Nat
  q : Nat
  componentCount : Nat
  batchCount : Nat
  groupOrder : Nat
  valueCount : Nat
  radix2Butterflies : Nat
  elapsedNanoseconds : Nat
  deriving BEq, DecidableEq, Repr

/-- Parse the exact native `OutputHeader` layout. -/
def readHeader? (raw : ByteArray) : Option OutputHeader := do
  if !magicMatches raw then
    none
  let version ← readU32LE? raw 8
  let q ← readU32LE? raw 12
  let componentCount ← readU32LE? raw 16
  let batchCount ← readU32LE? raw 20
  let groupOrder ← readU64LE? raw 24
  let valueCount ← readU64LE? raw 32
  let radix2Butterflies ← readU64LE? raw 40
  let elapsedNanoseconds ← readU64LE? raw 48
  pure
    { version
      q
      componentCount
      batchCount
      groupOrder
      valueCount
      radix2Butterflies
      elapsedNanoseconds }

theorem readHeader?_magic
    {raw : ByteArray} {header : OutputHeader}
    (hread : readHeader? raw = some header) :
    magicMatches raw = true := by
  unfold readHeader? at hread
  cases hmagic : magicMatches raw with
  | false =>
      simp [hmagic] at hread
  | true =>
      rfl

/-- All stable semantic fields of a single-component, single-batch
basis-one output.  Elapsed time is deliberately absent. -/
def HeaderMatches
    (expectedQ order expectedButterflies : Nat)
    (header : OutputHeader) : Prop :=
  header.version = 1 ∧
    header.q = expectedQ ∧
    header.componentCount = 1 ∧
    header.batchCount = 1 ∧
    header.groupOrder = order ∧
    header.valueCount = order ∧
    header.radix2Butterflies = expectedButterflies

instance
    (expectedQ order expectedButterflies : Nat) (header : OutputHeader) :
    Decidable (HeaderMatches expectedQ order expectedButterflies header) := by
  unfold HeaderMatches
  infer_instance

def headerMatches
    (expectedQ order expectedButterflies : Nat)
    (header : OutputHeader) : Bool :=
  decide (HeaderMatches expectedQ order expectedButterflies header)

theorem headerMatches_eq_true
    {expectedQ order expectedButterflies : Nat}
    {header : OutputHeader} :
    headerMatches expectedQ order expectedButterflies header = true ↔
      HeaderMatches expectedQ order expectedButterflies header := by
  simp [headerMatches]

/-- Decode one complex rectangle at a supplied byte base. -/
def readRootAt? (raw : ByteArray) (base index : Nat) :
    Option RawComplexBox := do
  let offset := base + recordBytes * index
  let reLo ← readU64LE? raw offset
  let reHi ← readU64LE? raw (offset + wordBytes)
  let imLo ← readU64LE? raw (offset + 2 * wordBytes)
  let imHi ← readU64LE? raw (offset + 3 * wordBytes)
  pure
    { re := { lo := reLo, hi := reHi }
      im := { lo := imLo, hi := imHi } }

/-- Decode one row of a headerless sequential payload. -/
def readPayloadRoot? (raw : ByteArray) (index : Nat) :
    Option RawComplexBox :=
  readRootAt? raw 0 index

/-- Check a row against the exact positive root assigned to its index. -/
def checkPositiveRow
    (workPrecision outputPrecision order index : Nat)
    (root : RawComplexBox) : Bool :=
  CertifiedRootWire.check
    workPrecision outputPrecision order index root

theorem checkPositiveRow_sound
    {workPrecision outputPrecision order index : Nat}
    {root : RawComplexBox}
    (hcheck :
      checkPositiveRow workPrecision outputPrecision order index root = true) :
    ∃ (outer : SparkInterval.Certified.ComplexRect)
        (hvalid : outer.IsValid),
      root.decodeFinite = some outer ∧
      (CertifiedRootWire.toComplexInterval outer hvalid).Contains
        (FactoredSmallQDFT.unitRoot order index) := by
  exact CertifiedRootWire.checked_box_contains hcheck

inductive FailureKind where
  | malformedRecord
  | root
  deriving BEq, DecidableEq, Repr

structure Failure where
  index : Nat
  kind : FailureKind
  deriving BEq, DecidableEq, Repr

/-- First failure in sequential source order.  `remaining` makes the scan
structurally recursive and avoids constructing a decoded table. -/
def firstFailureFromAt?
    (workPrecision outputPrecision order : Nat)
    (raw : ByteArray) (base : Nat) :
    Nat → Nat → Option Failure
  | _, 0 => none
  | index, remaining + 1 =>
      match readRootAt? raw base index with
      | none => some { index, kind := .malformedRecord }
      | some root =>
          if !checkPositiveRow
              workPrecision outputPrecision order index root then
            some { index, kind := .root }
          else
            firstFailureFromAt? workPrecision outputPrecision order raw base
              (index + 1) remaining

def firstPayloadFailure?
    (workPrecision outputPrecision order : Nat)
    (raw : ByteArray) : Option Failure :=
  firstFailureFromAt?
    workPrecision outputPrecision order raw 0 0 order

/-- Exact-length checker for a headerless sequential positive-root payload.
The strict `1 < order` guard is the live regime of the basis-one DFT theorem. -/
def checkPositivePayload
    (workPrecision outputPrecision order : Nat)
    (raw : ByteArray) : Bool :=
  decide (1 < order) &&
    raw.size = recordBytes * order &&
    (firstPayloadFailure?
      workPrecision outputPrecision order raw).isNone

theorem firstFailureFromAt?_eq_none_row
    {workPrecision outputPrecision order : Nat}
    {raw : ByteArray} {base start remaining : Nat}
    (hscan :
      firstFailureFromAt? workPrecision outputPrecision order raw base
        start remaining = none)
    {offset : Nat} (hoffset : offset < remaining) :
    ∃ root : RawComplexBox,
      readRootAt? raw base (start + offset) = some root ∧
      checkPositiveRow workPrecision outputPrecision order
        (start + offset) root = true := by
  induction remaining generalizing start offset with
  | zero =>
      omega
  | succ remaining ih =>
      cases hroot : readRootAt? raw base start with
      | none =>
          simp [firstFailureFromAt?, hroot] at hscan
      | some root =>
          cases hcheck :
              checkPositiveRow
                workPrecision outputPrecision order start root with
          | false =>
              simp [firstFailureFromAt?, hroot, hcheck] at hscan
          | true =>
              have htail :
                  firstFailureFromAt?
                      workPrecision outputPrecision order raw base
                      (start + 1) remaining = none := by
                simpa [firstFailureFromAt?, hroot, hcheck] using hscan
              cases offset with
              | zero =>
                  exact
                    ⟨root, by simpa using hroot, by simpa using hcheck⟩
              | succ offset =>
                  have hnext :=
                    ih htail (offset := offset) (by omega)
                  simpa [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]
                    using hnext

theorem checkPositivePayload_geometry
    {workPrecision outputPrecision order : Nat} {raw : ByteArray}
    (hcheck :
      checkPositivePayload
        workPrecision outputPrecision order raw = true) :
    1 < order ∧ raw.size = recordBytes * order := by
  simp only [checkPositivePayload, Bool.and_eq_true, decide_eq_true_eq,
    Option.isNone_iff_eq_none] at hcheck
  exact hcheck.1

theorem checkPositivePayload_rows
    {workPrecision outputPrecision order : Nat} {raw : ByteArray}
    (hcheck :
      checkPositivePayload
        workPrecision outputPrecision order raw = true)
    {index : Nat} (hindex : index < order) :
    ∃ root : RawComplexBox,
      readPayloadRoot? raw index = some root ∧
      checkPositiveRow
        workPrecision outputPrecision order index root = true := by
  simp only [checkPositivePayload, Bool.and_eq_true, decide_eq_true_eq,
    Option.isNone_iff_eq_none] at hcheck
  have hnone :
      firstPayloadFailure?
        workPrecision outputPrecision order raw = none := by
    exact hcheck.2
  simpa [firstPayloadFailure?, readPayloadRoot?] using
    (firstFailureFromAt?_eq_none_row hnone
      (offset := index) hindex)

/-- Whole-payload soundness: every row decodes to a valid rectangle
containing its exact sequential positive root. -/
theorem checkPositivePayload_root_containments
    {workPrecision outputPrecision order : Nat} {raw : ByteArray}
    (hcheck :
      checkPositivePayload
        workPrecision outputPrecision order raw = true)
    {index : Nat} (hindex : index < order) :
    ∃ root : RawComplexBox,
      readPayloadRoot? raw index = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (FactoredSmallQDFT.unitRoot order index) := by
  rcases checkPositivePayload_rows hcheck hindex with
    ⟨root, hroot, hrootCheck⟩
  exact ⟨root, hroot, checkPositiveRow_sound hrootCheck⟩

/-- The sequential root claim is exactly the positive DFT of the vector
supported at input index one. -/
theorem checkPositivePayload_basisOne_dft_containments
    {workPrecision outputPrecision order : Nat} {raw : ByteArray}
    (hcheck :
      checkPositivePayload
        workPrecision outputPrecision order raw = true)
    (frequency : Fin order) :
    ∃ root : RawComplexBox,
      readPayloadRoot? raw frequency.val = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (BluesteinDFT.positiveDFT order
            (BluesteinDFT.basisVector
              ⟨1, (checkPositivePayload_geometry hcheck).1⟩)
            frequency) := by
  rcases checkPositivePayload_root_containments
      hcheck frequency.isLt with
    ⟨root, hroot, outer, hvalid, hdecode, hcontains⟩
  refine ⟨root, hroot, outer, hvalid, hdecode, ?_⟩
  rw [BluesteinDFT.positiveDFT_basisOne_eq_unitRoot
    (checkPositivePayload_geometry hcheck).1 frequency]
  exact hcontains

/-- Full standard-artifact checker with caller-supplied stable semantic pins. -/
def checkArtifact
    (workPrecision outputPrecision expectedQ order
      expectedButterflies : Nat)
    (raw : ByteArray) : Bool :=
  decide (1 < order) &&
    raw.size = headerBytes + recordBytes * order &&
    match readHeader? raw with
    | none => false
    | some header =>
        headerMatches expectedQ order expectedButterflies header &&
          (firstFailureFromAt?
            workPrecision outputPrecision order raw headerBytes
            0 order).isNone

theorem checkArtifact_components
    {workPrecision outputPrecision expectedQ order
      expectedButterflies : Nat}
    {raw : ByteArray}
    (hcheck :
      checkArtifact workPrecision outputPrecision expectedQ order
        expectedButterflies raw = true) :
    1 < order ∧
      raw.size = headerBytes + recordBytes * order ∧
      ∃ header : OutputHeader,
        readHeader? raw = some header ∧
        HeaderMatches expectedQ order expectedButterflies header ∧
        firstFailureFromAt?
          workPrecision outputPrecision order raw headerBytes
          0 order = none := by
  unfold checkArtifact at hcheck
  cases hheader : readHeader? raw with
  | none =>
      simp [hheader] at hcheck
  | some header =>
      simp only [hheader, Bool.and_eq_true, decide_eq_true_eq,
        Option.isNone_iff_eq_none, headerMatches_eq_true] at hcheck
      exact
        ⟨hcheck.1.1, hcheck.1.2, header, rfl,
          hcheck.2.1, hcheck.2.2⟩

theorem checkArtifact_rows
    {workPrecision outputPrecision expectedQ order
      expectedButterflies : Nat}
    {raw : ByteArray}
    (hcheck :
      checkArtifact workPrecision outputPrecision expectedQ order
        expectedButterflies raw = true)
    {index : Nat} (hindex : index < order) :
    ∃ root : RawComplexBox,
      readRootAt? raw headerBytes index = some root ∧
      checkPositiveRow
        workPrecision outputPrecision order index root = true := by
  rcases checkArtifact_components hcheck with
    ⟨_, _, header, _, _, hscan⟩
  simpa using
    (firstFailureFromAt?_eq_none_row
      hscan (offset := index) hindex)

/-- Whole-artifact soundness for a generic pinned basis-one frame. -/
theorem checkArtifact_basisOne_dft_containments
    {workPrecision outputPrecision expectedQ order
      expectedButterflies : Nat}
    {raw : ByteArray}
    (hcheck :
      checkArtifact workPrecision outputPrecision expectedQ order
        expectedButterflies raw = true)
    (frequency : Fin order) :
    ∃ root : RawComplexBox,
      readRootAt? raw headerBytes frequency.val = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (BluesteinDFT.positiveDFT order
            (BluesteinDFT.basisVector
              ⟨1, (checkArtifact_components hcheck).1⟩)
            frequency) := by
  rcases checkArtifact_rows hcheck frequency.isLt with
    ⟨root, hroot, hrowCheck⟩
  rcases checkPositiveRow_sound hrowCheck with
    ⟨outer, hvalid, hdecode, hcontains⟩
  refine ⟨root, hroot, outer, hvalid, hdecode, ?_⟩
  rw [BluesteinDFT.positiveDFT_basisOne_eq_unitRoot
    (checkArtifact_components hcheck).1 frequency]
  exact hcontains

/-! ## Source-scale maximum-order capstone -/

def productionQ : Nat := 399989
def productionOrder : Nat := 399988
def productionButterflies : Nat := 31457280
def productionArtifactBytes : Nat :=
  headerBytes + recordBytes * productionOrder

/-- Exact production mode used by the maximum-order delta-one qualification. -/
def checkMaximumOrderDeltaOneArtifact
    (workPrecision outputPrecision : Nat)
    (raw : ByteArray) : Bool :=
  checkArtifact workPrecision outputPrecision
    productionQ productionOrder productionButterflies raw

/-- Acceptance exposes the parsed standard header and every pinned stable
semantic field.  Elapsed nanoseconds remains an arbitrary parsed natural. -/
theorem checkMaximumOrderDeltaOneArtifact_header
    {workPrecision outputPrecision : Nat} {raw : ByteArray}
    (hcheck :
      checkMaximumOrderDeltaOneArtifact
        workPrecision outputPrecision raw = true) :
    magicMatches raw = true ∧
      raw.size = 12799672 ∧
      ∃ header : OutputHeader,
        readHeader? raw = some header ∧
        header.version = 1 ∧
        header.q = 399989 ∧
        header.componentCount = 1 ∧
        header.batchCount = 1 ∧
        header.groupOrder = 399988 ∧
        header.valueCount = 399988 ∧
        header.radix2Butterflies = 31457280 := by
  rcases checkArtifact_components hcheck with
    ⟨_, hsize, header, hheader, hmatches, _⟩
  refine ⟨readHeader?_magic hheader, ?_, header, hheader, ?_⟩
  · norm_num [headerBytes, recordBytes, wordBytes, productionOrder] at hsize ⊢
    exact hsize
  · simpa [HeaderMatches, productionQ, productionOrder,
      productionButterflies] using hmatches

/-- Production capstone: every accepted standard-artifact output box contains
the exact positive DFT value of the maximum-order basis-one input. -/
theorem checkMaximumOrderDeltaOneArtifact_basisOne_dft_containments
    {workPrecision outputPrecision : Nat} {raw : ByteArray}
    (hcheck :
      checkMaximumOrderDeltaOneArtifact
        workPrecision outputPrecision raw = true)
    (frequency : Fin productionOrder) :
    ∃ root : RawComplexBox,
      readRootAt? raw headerBytes frequency.val = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (BluesteinDFT.positiveDFT productionOrder
            (BluesteinDFT.basisVector
              ⟨1, by norm_num [productionOrder]⟩)
            frequency) := by
  simpa [checkMaximumOrderDeltaOneArtifact] using
    (checkArtifact_basisOne_dft_containments hcheck frequency)

end SparkInterval.Dirichlet.CertifiedBasisOneOutputWire
