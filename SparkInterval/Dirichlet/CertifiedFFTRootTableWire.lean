/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedRootWire

/-!
# Checked wire format for flattened radix-2 FFT root tables

The production radix-2 table for a convolution length `L` contains `L - 1`
consecutive 32-byte complex rectangles.  Stages are concatenated in the
literal source order

```
s = 2, 4, ..., L.
```

Stage `s` contributes `s / 2` rows, begins at flattened offset `s / 2 - 1`,
and row `j` must enclose

```
exp(2*pi*i*j/s) = unitRoot s j.
```

Each rectangle is four little-endian raw binary64 words in the existing
`CertifiedRootWire.RawComplexBox` format.  This module accepts only the 19
source convolution powers `4, 8, ..., 2^20`, checks the exact byte length and
the exact flattened layout, and invokes the theorem-backed rational root
checker on every row.  It rejects unsupported geometry, truncation, trailing
bytes, non-finite binary64 words, reversed intervals, and failed endpoint
comparisons.

Acceptance is a mathematical statement about the supplied bytes.  It is not
a compiler-refinement theorem, an execution attestation, or a discharge of an
analytic external atom.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedFFTRootTableWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CertifiedRootWire

/-- One production root record is four raw binary64 words. -/
def wordBytes : Nat := 8
def recordBytes : Nat := 4 * wordBytes

/-- The literal source catalog `4, 8, ..., 2^20`. -/
def sourceConvolutionLengths : List Nat :=
  (List.range 19).map fun exponent => 2 ^ (exponent + 2)

def sourceConvolution (length : Nat) : Bool :=
  decide (length ∈ sourceConvolutionLengths)

/-- The mathematical identity assigned to one flattened producer row. -/
structure RootSpec where
  stage : Nat
  exponent : Nat
  deriving BEq, DecidableEq, Repr

/-- Half of the radix-2 stage owning flattened row `index`. -/
def stageHalfAtFlatIndex (index : Nat) : Nat :=
  2 ^ Nat.log2 (index + 1)

/-- Radix-2 stage owning flattened row `index`. -/
def stageAtFlatIndex (index : Nat) : Nat :=
  2 * stageHalfAtFlatIndex index

/-- Literal source offset of the stage owning flattened row `index`. -/
def stageOffsetAtFlatIndex (index : Nat) : Nat :=
  stageHalfAtFlatIndex index - 1

/-- Exponent within the stage owning flattened row `index`. -/
def exponentAtFlatIndex (index : Nat) : Nat :=
  index - stageOffsetAtFlatIndex index

/-- Constant-space decoding of the literal flattened source layout. -/
def specAtFlatIndex (index : Nat) : RootSpec :=
  { stage := stageAtFlatIndex index
    exponent := exponentAtFlatIndex index }

theorem stageOffsetAtFlatIndex_le (index : Nat) :
    stageOffsetAtFlatIndex index ≤ index := by
  have hpow :
      2 ^ Nat.log2 (index + 1) ≤ index + 1 :=
    Nat.log2_self_le (by omega)
  simp only [stageOffsetAtFlatIndex, stageHalfAtFlatIndex]
  omega

/-- The direct decoder really expresses `flat = stage/2-1 + j`. -/
theorem stageOffset_add_exponent (index : Nat) :
    stageOffsetAtFlatIndex index + exponentAtFlatIndex index = index := by
  unfold exponentAtFlatIndex
  exact Nat.add_sub_of_le (stageOffsetAtFlatIndex_le index)

/-- The decoded stage offset is the literal CUDA formula `stage/2-1`. -/
theorem stageOffset_eq_stage_div_two_sub_one (index : Nat) :
    stageOffsetAtFlatIndex index = stageAtFlatIndex index / 2 - 1 := by
  simp [stageOffsetAtFlatIndex, stageAtFlatIndex]

/-- Exact inverse of the flattened stage layout: the `j`th row of stage
`2^(stageExponent+1)` is found at offset `2^stageExponent-1+j`. -/
theorem specAtFlatIndex_stage_row
    {stageExponent exponent : Nat}
    (hexponent : exponent < 2 ^ stageExponent) :
    specAtFlatIndex (2 ^ stageExponent - 1 + exponent) =
      { stage := 2 ^ (stageExponent + 1), exponent } := by
  have hpositive : 0 < 2 ^ stageExponent := by positivity
  have hindex :
      2 ^ stageExponent - 1 + exponent + 1 =
        2 ^ stageExponent + exponent := by
    omega
  have hlog :
      Nat.log2 (2 ^ stageExponent - 1 + exponent + 1) =
        stageExponent := by
    apply (Nat.log2_eq_iff (by omega)).2
    constructor
    · omega
    · rw [Nat.pow_succ]
      omega
  simp only [specAtFlatIndex, stageAtFlatIndex, exponentAtFlatIndex,
    stageOffsetAtFlatIndex, stageHalfAtFlatIndex, hlog]
  congr 1
  · rw [Nat.pow_succ]
    omega
  · omega

/-- Source-shaped spelling of `specAtFlatIndex_stage_row`, with the literal
CUDA offset `stage/2-1+j`. -/
theorem specAtFlatIndex_source_order
    {stageExponent exponent : Nat}
    (hexponent : exponent < 2 ^ stageExponent) :
    specAtFlatIndex
        (2 ^ (stageExponent + 1) / 2 - 1 + exponent) =
      { stage := 2 ^ (stageExponent + 1), exponent } := by
  simpa [Nat.pow_succ] using
    (specAtFlatIndex_stage_row hexponent)

/-- Bounds-checked unsigned little-endian decoding. -/
def readLE? (width : Nat) (raw : ByteArray) (offset : Nat) : Option Nat :=
  if offset + width ≤ raw.size then
    some <| (List.range width).foldl
      (fun value index =>
        value + (raw.get! (offset + index)).toNat * 256 ^ index) 0
  else
    none

def readU64LE? (raw : ByteArray) (offset : Nat) : Option Nat :=
  readLE? wordBytes raw offset

/-- Decode one exact 32-byte root rectangle. -/
def readRoot? (raw : ByteArray) (index : Nat) : Option RawComplexBox := do
  let offset := recordBytes * index
  let reLo ← readU64LE? raw offset
  let reHi ← readU64LE? raw (offset + wordBytes)
  let imLo ← readU64LE? raw (offset + 2 * wordBytes)
  let imHi ← readU64LE? raw (offset + 3 * wordBytes)
  pure
    { re := { lo := reLo, hi := reHi }
      im := { lo := imLo, hi := imHi } }

/-- Check one flattened row against its exact stage root. -/
def checkPositiveRoot
    (workPrecision outputPrecision : Nat)
    (spec : RootSpec) (root : RawComplexBox) : Bool :=
  CertifiedRootWire.check workPrecision outputPrecision
    spec.stage spec.exponent root

theorem checkPositiveRoot_sound
    {workPrecision outputPrecision : Nat}
    {spec : RootSpec} {root : RawComplexBox}
    (hcheck :
      checkPositiveRoot workPrecision outputPrecision spec root = true) :
    ∃ (outer : SparkInterval.Certified.ComplexRect)
        (hvalid : outer.IsValid),
      root.decodeFinite = some outer ∧
      (CertifiedRootWire.toComplexInterval outer hvalid).Contains
        (FactoredSmallQDFT.unitRoot spec.stage spec.exponent) := by
  exact CertifiedRootWire.checked_box_contains hcheck

inductive FailureKind where
  | malformedRecord
  | root
  deriving BEq, DecidableEq, Repr

structure Failure where
  flatIndex : Nat
  stage : Nat
  exponent : Nat
  kind : FailureKind
  deriving BEq, DecidableEq, Repr

/-- First failure in flattened source order. -/
def firstFailureFrom?
    (workPrecision outputPrecision : Nat) (raw : ByteArray) :
    Nat → Nat → Option Failure
  | _, 0 => none
  | index, remaining + 1 =>
      let spec := specAtFlatIndex index
      match readRoot? raw index with
      | none =>
          some
            { flatIndex := index
              stage := spec.stage
              exponent := spec.exponent
              kind := .malformedRecord }
      | some root =>
          if !checkPositiveRoot workPrecision outputPrecision spec root then
            some
              { flatIndex := index
                stage := spec.stage
                exponent := spec.exponent
                kind := .root }
          else
            firstFailureFrom? workPrecision outputPrecision raw
              (index + 1) remaining

def firstFailure?
    (workPrecision outputPrecision length : Nat)
    (raw : ByteArray) : Option Failure :=
  firstFailureFrom? workPrecision outputPrecision raw 0 (length - 1)

/-- Total exact-length checker for one positive production FFT-root table. -/
def checkPositiveDump
    (workPrecision outputPrecision length : Nat)
    (raw : ByteArray) : Bool :=
  sourceConvolution length &&
    raw.size = recordBytes * (length - 1) &&
    (firstFailure? workPrecision outputPrecision length raw).isNone

theorem firstFailureFrom?_eq_none_row
    {workPrecision outputPrecision : Nat}
    {raw : ByteArray} {start remaining : Nat}
    (hscan :
      firstFailureFrom? workPrecision outputPrecision raw
        start remaining = none)
    {offset : Nat} (hoffset : offset < remaining) :
    ∃ root : RawComplexBox,
      readRoot? raw (start + offset) = some root ∧
      checkPositiveRoot workPrecision outputPrecision
        (specAtFlatIndex (start + offset)) root = true := by
  induction remaining generalizing start offset with
  | zero =>
      omega
  | succ remaining ih =>
      let spec := specAtFlatIndex start
      cases hroot : readRoot? raw start with
      | none =>
          simp [firstFailureFrom?, hroot] at hscan
      | some root =>
          cases hcheck :
              checkPositiveRoot workPrecision outputPrecision spec root with
          | false =>
              simp [firstFailureFrom?, spec, hroot, hcheck] at hscan
          | true =>
              have htail :
                  firstFailureFrom? workPrecision outputPrecision raw
                      (start + 1) remaining = none := by
                simpa [firstFailureFrom?, spec, hroot, hcheck] using hscan
              cases offset with
              | zero =>
                  exact
                    ⟨root, by simpa using hroot, by simpa [spec] using hcheck⟩
              | succ offset =>
                  have hnext :=
                    ih htail (offset := offset) (by omega)
                  simpa [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]
                    using hnext

theorem checkPositiveDump_geometry
    {workPrecision outputPrecision length : Nat} {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true) :
    sourceConvolution length = true ∧
      raw.size = recordBytes * (length - 1) := by
  simp only [checkPositiveDump, Bool.and_eq_true, decide_eq_true_eq,
    Option.isNone_iff_eq_none] at hcheck
  exact hcheck.1

theorem checkPositiveDump_rows
    {workPrecision outputPrecision length : Nat} {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    {index : Nat} (hindex : index < length - 1) :
    ∃ root : RawComplexBox,
      readRoot? raw index = some root ∧
      checkPositiveRoot workPrecision outputPrecision
        (specAtFlatIndex index) root = true := by
  simp only [checkPositiveDump, Bool.and_eq_true, decide_eq_true_eq,
    Option.isNone_iff_eq_none] at hcheck
  have hnone :
      firstFailure? workPrecision outputPrecision length raw = none := by
    exact hcheck.2
  simpa [firstFailure?] using
    (firstFailureFrom?_eq_none_row hnone hindex)

/-- Whole-file soundness: every row selected by the literal flattened layout
decodes to a valid rectangle containing its exact positive stage root. -/
theorem checkPositiveDump_root_containments
    {workPrecision outputPrecision length : Nat} {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    {index : Nat} (hindex : index < length - 1) :
    ∃ root : RawComplexBox,
      readRoot? raw index = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (FactoredSmallQDFT.unitRoot
            (specAtFlatIndex index).stage
            (specAtFlatIndex index).exponent) := by
  rcases checkPositiveDump_rows hcheck hindex with
    ⟨root, hroot, hrootCheck⟩
  exact ⟨root, hroot, checkPositiveRoot_sound hrootCheck⟩

/-- Human-facing source-layout theorem.  For every source stage
`s = 2^(stageExponent+1) ≤ length` and every `j < s/2`, acceptance directly
certifies the record at the CUDA offset `s/2-1+j` as an enclosure of
`unitRoot s j`. -/
theorem checkPositiveDump_source_stage_root_containment
    {workPrecision outputPrecision length : Nat} {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    {stageExponent exponent : Nat}
    (hstage : 2 ^ (stageExponent + 1) ≤ length)
    (hexponent : exponent < 2 ^ stageExponent) :
    ∃ root : RawComplexBox,
      readRoot? raw (2 ^ stageExponent - 1 + exponent) = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (FactoredSmallQDFT.unitRoot
            (2 ^ (stageExponent + 1)) exponent) := by
  have hpositive : 0 < 2 ^ stageExponent := by positivity
  have hindex :
      2 ^ stageExponent - 1 + exponent < length - 1 := by
    rw [Nat.pow_succ] at hstage
    omega
  have hspec := specAtFlatIndex_stage_row hexponent
  simpa [hspec] using
    (checkPositiveDump_root_containments hcheck hindex)

end SparkInterval.Dirichlet.CertifiedFFTRootTableWire
