/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedRootWire

/-!
# Checked wire format for positive Bluestein chirp states

The production `--dump-chirp` stream contains one 64-byte record per natural
index. Each record is

```
chirp.re.lo, chirp.re.hi, chirp.im.lo, chirp.im.hi,
odd.re.lo,   odd.re.hi,   odd.im.lo,   odd.im.hi
```

as eight little-endian raw binary64 words. For a positive chirp of length
`N`, row `n` must enclose the two exact roots

```
exp(pi*i*n^2/N)       = unitRoot (2*N) (n^2)
exp(pi*i*(2*n+1)/N)   = unitRoot (2*N) (2*n+1).
```

This module parses that literal layout and invokes `CertifiedRootWire.check`
for both boxes. It rejects zero length, truncation, trailing bytes, malformed
binary64 intervals, and the first endpoint comparison that fails. The
checker is mathematical and deterministic; it does not attest that a
particular native producer or physical run emitted the bytes.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedChirpStateWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CertifiedRootWire

def wordBytes : Nat := 8
def complexBoxBytes : Nat := 4 * wordBytes
def recordBytes : Nat := 2 * complexBoxBytes

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

/-- Decode the four raw binary64 words of one production complex box. -/
def readRawComplexBox? (raw : ByteArray) (offset : Nat) :
    Option RawComplexBox := do
  let reLo ← readU64LE? raw offset
  let reHi ← readU64LE? raw (offset + wordBytes)
  let imLo ← readU64LE? raw (offset + 2 * wordBytes)
  let imHi ← readU64LE? raw (offset + 3 * wordBytes)
  pure
    { re := { lo := reLo, hi := reHi }
      im := { lo := imLo, hi := imHi } }

structure RawChirpStateRow where
  chirp : RawComplexBox
  oddStep : RawComplexBox
  deriving BEq, DecidableEq, Repr

/-- Decode one exact 64-byte producer record. -/
def readRow? (raw : ByteArray) (index : Nat) : Option RawChirpStateRow := do
  let offset := recordBytes * index
  let chirp ← readRawComplexBox? raw offset
  let oddStep ← readRawComplexBox? raw (offset + complexBoxBytes)
  pure { chirp, oddStep }

/-- Check both mathematical roots carried by row `index`. -/
def checkPositiveRow
    (workPrecision outputPrecision length index : Nat)
    (row : RawChirpStateRow) : Bool :=
  CertifiedRootWire.check workPrecision outputPrecision
      (2 * length) (index ^ 2) row.chirp &&
    CertifiedRootWire.check workPrecision outputPrecision
      (2 * length) (2 * index + 1) row.oddStep

theorem checkPositiveRow_chirp_sound
    {workPrecision outputPrecision length index : Nat}
    {row : RawChirpStateRow}
    (hcheck :
      checkPositiveRow workPrecision outputPrecision length index row = true) :
    ∃ (outer : SparkInterval.Certified.ComplexRect)
        (hvalid : outer.IsValid),
      row.chirp.decodeFinite = some outer ∧
      (CertifiedRootWire.toComplexInterval outer hvalid).Contains
        (FactoredSmallQDFT.unitRoot (2 * length) (index ^ 2)) := by
  simp only [checkPositiveRow, Bool.and_eq_true] at hcheck
  exact CertifiedRootWire.checked_box_contains hcheck.1

theorem checkPositiveRow_oddStep_sound
    {workPrecision outputPrecision length index : Nat}
    {row : RawChirpStateRow}
    (hcheck :
      checkPositiveRow workPrecision outputPrecision length index row = true) :
    ∃ (outer : SparkInterval.Certified.ComplexRect)
        (hvalid : outer.IsValid),
      row.oddStep.decodeFinite = some outer ∧
      (CertifiedRootWire.toComplexInterval outer hvalid).Contains
        (FactoredSmallQDFT.unitRoot (2 * length) (2 * index + 1)) := by
  simp only [checkPositiveRow, Bool.and_eq_true] at hcheck
  exact CertifiedRootWire.checked_box_contains hcheck.2

inductive FailureKind where
  | malformedRow
  | chirp
  | oddStep
  deriving BEq, DecidableEq, Repr

structure Failure where
  index : Nat
  kind : FailureKind
  deriving BEq, DecidableEq, Repr

/-- First row failure in source order. `remaining` makes the scan structurally
recursive and bounds every attempted record read. -/
def firstFailureFrom?
    (workPrecision outputPrecision length : Nat) (raw : ByteArray) :
    Nat → Nat → Option Failure
  | _, 0 => none
  | index, remaining + 1 =>
      match readRow? raw index with
      | none => some { index, kind := .malformedRow }
      | some row =>
          if !CertifiedRootWire.check workPrecision outputPrecision
              (2 * length) (index ^ 2) row.chirp then
            some { index, kind := .chirp }
          else if !CertifiedRootWire.check workPrecision outputPrecision
              (2 * length) (2 * index + 1) row.oddStep then
            some { index, kind := .oddStep }
          else
            firstFailureFrom? workPrecision outputPrecision length raw
              (index + 1) remaining

def firstFailure?
    (workPrecision outputPrecision length : Nat)
    (raw : ByteArray) : Option Failure :=
  firstFailureFrom? workPrecision outputPrecision length raw 0 length

/-- Total exact-length checker for a positive producer dump. -/
def checkPositiveDump
    (workPrecision outputPrecision length : Nat)
    (raw : ByteArray) : Bool :=
  length != 0 &&
    raw.size = recordBytes * length &&
    (firstFailure? workPrecision outputPrecision length raw).isNone

theorem firstFailureFrom?_eq_none_row
    {workPrecision outputPrecision length : Nat}
    {raw : ByteArray} {start remaining : Nat}
    (hscan :
      firstFailureFrom? workPrecision outputPrecision length raw
        start remaining = none)
    {offset : Nat} (hoffset : offset < remaining) :
    ∃ row : RawChirpStateRow,
      readRow? raw (start + offset) = some row ∧
      checkPositiveRow workPrecision outputPrecision length
        (start + offset) row = true := by
  induction remaining generalizing start offset with
  | zero =>
      omega
  | succ remaining ih =>
      cases hrow : readRow? raw start with
      | none =>
          simp [firstFailureFrom?, hrow] at hscan
      | some row =>
          cases hchirp :
              CertifiedRootWire.check workPrecision outputPrecision
                (2 * length) (start ^ 2) row.chirp with
          | false =>
              simp [firstFailureFrom?, hrow, hchirp] at hscan
          | true =>
              cases hodd :
                  CertifiedRootWire.check workPrecision outputPrecision
                    (2 * length) (2 * start + 1) row.oddStep with
              | false =>
                  simp [firstFailureFrom?, hrow, hchirp, hodd] at hscan
              | true =>
                  have htail :
                      firstFailureFrom? workPrecision outputPrecision length raw
                          (start + 1) remaining = none := by
                    simpa [firstFailureFrom?, hrow, hchirp, hodd] using hscan
                  cases offset with
                  | zero =>
                      exact
                        ⟨row, by simpa using hrow,
                          by simp [checkPositiveRow, hchirp, hodd]⟩
                  | succ offset =>
                      have hnext :=
                        ih htail (offset := offset) (by omega)
                      simpa [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]
                        using hnext

theorem checkPositiveDump_geometry
    {workPrecision outputPrecision length : Nat} {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true) :
    length ≠ 0 ∧ raw.size = recordBytes * length := by
  simp only [checkPositiveDump, Bool.and_eq_true, bne_iff_ne,
    decide_eq_true_eq, Option.isNone_iff_eq_none] at hcheck
  exact hcheck.1

theorem checkPositiveDump_rows
    {workPrecision outputPrecision length : Nat} {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    {index : Nat} (hindex : index < length) :
    ∃ row : RawChirpStateRow,
      readRow? raw index = some row ∧
      checkPositiveRow workPrecision outputPrecision length index row = true := by
  simp only [checkPositiveDump, Bool.and_eq_true, bne_iff_ne,
    decide_eq_true_eq, Option.isNone_iff_eq_none] at hcheck
  have hnone :
      firstFailure? workPrecision outputPrecision length raw = none := by
    exact hcheck.2
  simpa [firstFailure?] using
    (firstFailureFrom?_eq_none_row hnone (offset := index) hindex)

/-- Whole-file soundness: acceptance gives a decoded source row and
kernel-proved containment for both exact roots at every declared index. -/
theorem checkPositiveDump_root_containments
    {workPrecision outputPrecision length : Nat} {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    {index : Nat} (hindex : index < length) :
    ∃ row : RawChirpStateRow,
      readRow? raw index = some row ∧
      (∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        row.chirp.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (FactoredSmallQDFT.unitRoot (2 * length) (index ^ 2))) ∧
      (∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        row.oddStep.decodeFinite = some outer ∧
        (CertifiedRootWire.toComplexInterval outer hvalid).Contains
          (FactoredSmallQDFT.unitRoot (2 * length) (2 * index + 1))) := by
  rcases checkPositiveDump_rows hcheck hindex with
    ⟨row, hrow, hrowCheck⟩
  exact
    ⟨row, hrow,
      checkPositiveRow_chirp_sound hrowCheck,
      checkPositiveRow_oddStep_sound hrowCheck⟩

end SparkInterval.Dirichlet.CertifiedChirpStateWire
