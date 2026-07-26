/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPrimitives
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Wire

/-!
# Source-level C byte-read refinement for the Sqrt218 checker

This module connects the cast-before-shift arithmetic in
`tg_read_be16`, `tg_read_be32`, and `tg_read_be64` with the canonical
big-endian decoder used by `Wire`.

The statements require the complete field to lie inside the byte array,
which is the source precondition supplied by the header-size and
`tg_range_inside` checks.  They model the C source expressions only; they do
not claim compiler, ABI, machine-code, loader, or processor refinement.

All proofs are symbolic in the byte array and offset.  No certificate bytes
are opened or reduced.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CWireReadRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

/-- The exact C `uint16_t` big-endian expression agrees with the canonical
wire decoder whenever both source byte reads are in bounds. -/
theorem readBE16_eq_wire
    (raw : ByteArray) (offset : Nat)
    (hbound : offset + 2 ≤ raw.size) :
    Wire.readBE16 raw offset =
      some (CPrimitives.readBE16
        (raw.get! offset)
        (raw.get! (offset + 1))) := by
  unfold Wire.readBE16 Wire.readBE
  rw [if_pos hbound]
  simp only [Option.some.injEq]
  unfold CPrimitives.readBE16
  change
    256 * (256 * 0 + (raw.get! (offset + 0)).toNat) +
        (raw.get! (offset + 1)).toNat =
      (raw.get! offset).toNat * 2 ^ 8 +
        (raw.get! (offset + 1)).toNat
  norm_num
  omega

/-- The exact C `uint32_t` big-endian expression agrees with the canonical
wire decoder whenever all four source byte reads are in bounds. -/
theorem readBE32_eq_wire
    (raw : ByteArray) (offset : Nat)
    (hbound : offset + 4 ≤ raw.size) :
    Wire.readBE32 raw offset =
      some (CPrimitives.readBE32
        (raw.get! offset)
        (raw.get! (offset + 1))
        (raw.get! (offset + 2))
        (raw.get! (offset + 3))) := by
  unfold Wire.readBE32 Wire.readBE
  rw [if_pos hbound]
  simp only [Option.some.injEq]
  unfold CPrimitives.readBE32
  change
    256 *
          (256 *
              (256 *
                  (256 * 0 +
                    (raw.get! (offset + 0)).toNat) +
                (raw.get! (offset + 1)).toNat) +
            (raw.get! (offset + 2)).toNat) +
        (raw.get! (offset + 3)).toNat =
      (raw.get! offset).toNat * 2 ^ 24 +
          (raw.get! (offset + 1)).toNat * 2 ^ 16 +
        (raw.get! (offset + 2)).toNat * 2 ^ 8 +
      (raw.get! (offset + 3)).toNat
  norm_num
  omega

/-- The exact C `uint64_t` big-endian expression agrees with the canonical
wire decoder whenever all eight source byte reads are in bounds. -/
theorem readBE64_eq_wire
    (raw : ByteArray) (offset : Nat)
    (hbound : offset + 8 ≤ raw.size) :
    Wire.readBE64 raw offset =
      some (CPrimitives.readBE64
        (raw.get! offset)
        (raw.get! (offset + 1))
        (raw.get! (offset + 2))
        (raw.get! (offset + 3))
        (raw.get! (offset + 4))
        (raw.get! (offset + 5))
        (raw.get! (offset + 6))
        (raw.get! (offset + 7))) := by
  unfold Wire.readBE64 Wire.readBE
  rw [if_pos hbound]
  simp only [Option.some.injEq]
  unfold CPrimitives.readBE64
  change
    256 *
          (256 *
              (256 *
                  (256 *
                      (256 *
                          (256 *
                              (256 *
                                  (256 * 0 +
                                    (raw.get! (offset + 0)).toNat) +
                                (raw.get! (offset + 1)).toNat) +
                            (raw.get! (offset + 2)).toNat) +
                        (raw.get! (offset + 3)).toNat) +
                    (raw.get! (offset + 4)).toNat) +
                (raw.get! (offset + 5)).toNat) +
            (raw.get! (offset + 6)).toNat) +
        (raw.get! (offset + 7)).toNat =
      (raw.get! offset).toNat * 2 ^ 56 +
          (raw.get! (offset + 1)).toNat * 2 ^ 48 +
        (raw.get! (offset + 2)).toNat * 2 ^ 40 +
          (raw.get! (offset + 3)).toNat * 2 ^ 32 +
        (raw.get! (offset + 4)).toNat * 2 ^ 24 +
          (raw.get! (offset + 5)).toNat * 2 ^ 16 +
        (raw.get! (offset + 6)).toNat * 2 ^ 8 +
      (raw.get! (offset + 7)).toNat
  norm_num
  omega

/-! ## Checked source range arithmetic -/

/-- Source-call composition of `tg_section_end`, excluding only the
non-null output-pointer precondition. -/
def cSectionEnd (start count width : Nat) : Option Nat := do
  let bytes ← CPrimitives.wordMulChecked count width
  CPrimitives.wordAddChecked start bytes

/-- Successful C section-end arithmetic is exactly a successful
architecture-neutral `IR.sectionEnd` computation. -/
theorem cSectionEnd_refines
    {start count width result : Nat}
    (hstart : start < limbBase)
    (hcount : count < limbBase)
    (hwidth : width < limbBase)
    (hrun : cSectionEnd start count width = some result) :
    sectionEnd start count width = some result := by
  unfold cSectionEnd at hrun
  rcases Option.bind_eq_some_iff.mp hrun with
    ⟨bytes, hbytes, hresult⟩
  have hbytesSound :=
    CPrimitives.wordMulChecked_sound hcount hwidth hbytes
  have hresultSound :=
    CPrimitives.wordAddChecked_sound
      hstart hbytesSound.1 hresult
  have hmul :
      checkedWordMul count width = some bytes := by
    have hproduct : count * width < limbBase := by
      simpa only [hbytesSound.2] using hbytesSound.1
    unfold checkedWordMul checkedWord
    rw [if_pos hproduct]
    exact congrArg some hbytesSound.2.symm
  have hadd :
      checkedWordAdd start bytes = some result := by
    have hsum : start + bytes < limbBase := by
      simpa only [hresultSound.2] using hresultSound.1
    unfold checkedWordAdd checkedWord
    rw [if_pos hsum]
    exact congrArg some hresultSound.2.symm
  unfold sectionEnd
  rw [hmul]
  change checkedWordAdd start bytes = some result
  exact hadd

/-- Successful branch of `tg_range_inside` after the source-level non-null
view check.  `rawSize` denotes the exact `uint64_t` value of `view->length`;
the caller must separately justify that cast when connecting it to a host
`size_t`. -/
def cRangeInside (rawSize offset width : Nat) : Bool :=
  match CPrimitives.wordAddChecked offset width with
  | none => false
  | some ending => decide (ending ≤ rawSize)

/-- Acceptance by the C range guard implies the canonical half-open byte
range is inside the buffer. -/
theorem cRangeInside_sound
    {rawSize offset width : Nat}
    (hoffset : offset < limbBase)
    (hwidth : width < limbBase)
    (hrun : cRangeInside rawSize offset width = true) :
    offset + width ≤ rawSize := by
  unfold cRangeInside at hrun
  cases hadd : CPrimitives.wordAddChecked offset width with
  | none =>
      rw [hadd] at hrun
      contradiction
  | some ending =>
      rw [hadd] at hrun
      simp only [decide_eq_true_eq] at hrun
      have haddSound :=
        CPrimitives.wordAddChecked_sound
          hoffset hwidth hadd
      rw [← haddSound.2]
      exact hrun

/-- Every canonical in-buffer range follows the accepting C branch when the
host length is representable by the source `uint64_t` cast. -/
theorem cRangeInside_complete
    {rawSize offset width : Nat}
    (hsize : rawSize < limbBase)
    (hinside : offset + width ≤ rawSize) :
    cRangeInside rawSize offset width = true := by
  have hsum : offset + width < limbBase :=
    hinside.trans_lt hsize
  have hadd :
      CPrimitives.wordAddChecked offset width =
        some (offset + width) :=
    CPrimitives.wordAddChecked_eq_some_of_sum_fits hsum
  unfold cRangeInside
  rw [hadd]
  exact decide_eq_true hinside

/-- On genuine source words and a representable host length, the C guard is
equivalent to the canonical Wire in-bounds condition. -/
theorem cRangeInside_iff
    {rawSize offset width : Nat}
    (hsize : rawSize < limbBase)
    (hoffset : offset < limbBase)
    (hwidth : width < limbBase) :
    cRangeInside rawSize offset width = true ↔
      offset + width ≤ rawSize :=
  ⟨cRangeInside_sound hoffset hwidth,
    cRangeInside_complete hsize⟩

/-- The C range check supplies the exact precondition for the two-byte
source read refinement. -/
theorem readBE16_eq_wire_of_cRangeInside
    (raw : ByteArray) (offset : Nat)
    (hsize : raw.size < limbBase)
    (hoffset : offset < limbBase)
    (hrange : cRangeInside raw.size offset 2 = true) :
    Wire.readBE16 raw offset =
      some (CPrimitives.readBE16
        (raw.get! offset)
        (raw.get! (offset + 1))) :=
  readBE16_eq_wire raw offset
    ((cRangeInside_iff hsize hoffset
      (by norm_num [limbBase])).mp hrange)

/-- The C range check supplies the exact precondition for the four-byte
source read refinement. -/
theorem readBE32_eq_wire_of_cRangeInside
    (raw : ByteArray) (offset : Nat)
    (hsize : raw.size < limbBase)
    (hoffset : offset < limbBase)
    (hrange : cRangeInside raw.size offset 4 = true) :
    Wire.readBE32 raw offset =
      some (CPrimitives.readBE32
        (raw.get! offset)
        (raw.get! (offset + 1))
        (raw.get! (offset + 2))
        (raw.get! (offset + 3))) :=
  readBE32_eq_wire raw offset
    ((cRangeInside_iff hsize hoffset
      (by norm_num [limbBase])).mp hrange)

/-- The C range check supplies the exact precondition for the eight-byte
source read refinement. -/
theorem readBE64_eq_wire_of_cRangeInside
    (raw : ByteArray) (offset : Nat)
    (hsize : raw.size < limbBase)
    (hoffset : offset < limbBase)
    (hrange : cRangeInside raw.size offset 8 = true) :
    Wire.readBE64 raw offset =
      some (CPrimitives.readBE64
        (raw.get! offset)
        (raw.get! (offset + 1))
        (raw.get! (offset + 2))
        (raw.get! (offset + 3))
        (raw.get! (offset + 4))
        (raw.get! (offset + 5))
        (raw.get! (offset + 6))
        (raw.get! (offset + 7))) :=
  readBE64_eq_wire raw offset
    ((cRangeInside_iff hsize hoffset
      (by norm_num [limbBase])).mp hrange)

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CWireReadRefinement
