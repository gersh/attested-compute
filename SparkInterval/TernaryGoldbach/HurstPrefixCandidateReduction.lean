/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter
import SparkInterval.TernaryGoldbach.MobiusFusedSupport

/-!
# Exact prefix scan and deterministic Hurst candidate reduction

The production terminal Hurst kernel now decodes each fused support word
directly to an unscanned pair

```
(mertens, squarefree) = (μ, if μ = 0 then 0 else 1),
```

per row, performs an in-place inclusive CUB scan of those pairs, and reduces
exact affine candidates.  This file gives the architecture-independent
specification of those operations.

The qualification path can separately materialize raw signed bytes.
Bytes `0xff`, `0x00`, and `0x01` decode to `-1`, `0`, and `1`; ordinary Lean
proves that initializing those bytes gives exactly the direct production-row
model.  For at most `10^8` rows, every mathematical partial sum fits the
native `int32_t`/`uint32_t` pair.  Candidate order is
`2 * row + endpoint`, with endpoint zero or one, and therefore also fits
`uint32_t`.

The candidate reducer minimizes the already reviewed keys from
`HurstAffineCandidateFilter`:

* `(-value, order)` for a maximum;
* `( value, order)` for a minimum.

Thus arbitrary sequential regrouping gives the same winner, and equal values
are resolved by the earliest source order.

This module does **not** identify a compiled CUB scan, CUDA kernel, PTX/SASS
program, or GPU execution with this list model.  That compiler/library/device
refinement remains an explicit physical boundary.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction

open SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter
open SparkInterval.TernaryGoldbach.MobiusFusedSupport

/-! ## Signed Möbius row bytes -/

/-- Mathematical signed interpretation of the native `int8_t` row byte.
Only the three values accepted by `MobiusByteValid` are used below. -/
def decodeMobiusByte (byte : UInt8) : Int :=
  if byte.toNat = 255 then -1 else (byte.toNat : Int)

/-- The fail-closed native producer may pass only the three Möbius bytes. -/
def MobiusByteValid (byte : UInt8) : Prop :=
  byte.toNat = 255 ∨ byte.toNat = 0 ∨ byte.toNat = 1

instance (byte : UInt8) : Decidable (MobiusByteValid byte) := by
  unfold MobiusByteValid
  infer_instance

/-- Every row of one scan is a canonical Möbius byte. -/
def MobiusRowsValid (rows : List UInt8) : Prop :=
  ∀ byte ∈ rows, MobiusByteValid byte

instance (rows : List UInt8) : Decidable (MobiusRowsValid rows) := by
  unfold MobiusRowsValid
  infer_instance

/-- Squarefree indicator emitted from one nonzero Möbius value. -/
def squarefreeIncrement (byte : UInt8) : Nat :=
  if decodeMobiusByte byte = 0 then 0 else 1

theorem decodeMobiusByte_bounds {byte : UInt8}
    (valid : MobiusByteValid byte) :
    (-1 : Int) ≤ decodeMobiusByte byte ∧
      decodeMobiusByte byte ≤ 1 := by
  rcases valid with hminus | hzero | hone
  · simp [decodeMobiusByte, hminus]
  · simp [decodeMobiusByte, hzero]
  · simp [decodeMobiusByte, hone]

theorem squarefreeIncrement_le_one (byte : UInt8) :
    squarefreeIncrement byte ≤ 1 := by
  unfold squarefreeIncrement
  split <;> omega

/-! ## Exact inclusive prefix scan -/

/-- Architecture-neutral version of `TgMobiusPrefixMQ`. -/
structure PrefixMQ where
  mertens : Int
  squarefree : Nat
  deriving Repr, DecidableEq

namespace PrefixMQ

def zero : PrefixMQ := ⟨0, 0⟩

def add (left right : PrefixMQ) : PrefixMQ :=
  ⟨left.mertens + right.mertens,
   left.squarefree + right.squarefree⟩

instance : Add PrefixMQ := ⟨add⟩

@[simp] theorem add_mertens (left right : PrefixMQ) :
    (left + right).mertens = left.mertens + right.mertens := rfl

@[simp] theorem add_squarefree (left right : PrefixMQ) :
    (left + right).squarefree =
      left.squarefree + right.squarefree := rfl

@[simp] theorem zero_mertens : zero.mertens = 0 := rfl

@[simp] theorem zero_squarefree : zero.squarefree = 0 := rfl

@[simp] theorem zero_add (pfx : PrefixMQ) : zero + pfx = pfx := by
  rcases pfx with ⟨mertens, squarefree⟩
  change
    PrefixMQ.mk (0 + mertens) (0 + squarefree) =
      PrefixMQ.mk mertens squarefree
  simp

@[simp] theorem add_zero (pfx : PrefixMQ) : pfx + zero = pfx := by
  rcases pfx with ⟨mertens, squarefree⟩
  change
    PrefixMQ.mk (mertens + 0) (squarefree + 0) =
      PrefixMQ.mk mertens squarefree
  simp

theorem add_assoc (first second third : PrefixMQ) :
    first + second + third = first + (second + third) := by
  rcases first with ⟨firstMertens, firstSquarefree⟩
  rcases second with ⟨secondMertens, secondSquarefree⟩
  rcases third with ⟨thirdMertens, thirdSquarefree⟩
  change
    PrefixMQ.mk
        ((firstMertens + secondMertens) + thirdMertens)
        ((firstSquarefree + secondSquarefree) + thirdSquarefree) =
      PrefixMQ.mk
        (firstMertens + (secondMertens + thirdMertens))
        (firstSquarefree + (secondSquarefree + thirdSquarefree))
  simp only [Int.add_assoc, Nat.add_assoc]

theorem add_comm (left right : PrefixMQ) :
    left + right = right + left := by
  rcases left with ⟨leftMertens, leftSquarefree⟩
  rcases right with ⟨rightMertens, rightSquarefree⟩
  change
    PrefixMQ.mk
        (leftMertens + rightMertens)
        (leftSquarefree + rightSquarefree) =
      PrefixMQ.mk
        (rightMertens + leftMertens)
        (rightSquarefree + leftSquarefree)
  simp only [Int.add_comm, Nat.add_comm]

end PrefixMQ

/-! ## Production direct-row inclusive scan -/

/-- Exact admissibility condition for one unscanned production pair. -/
def PrefixInputRowValid (row : PrefixMQ) : Prop :=
  (-1 : Int) ≤ row.mertens ∧
    row.mertens ≤ 1 ∧
    row.squarefree =
      if row.mertens = 0 then 0 else 1

instance (row : PrefixMQ) : Decidable (PrefixInputRowValid row) := by
  unfold PrefixInputRowValid
  infer_instance

/-- Every direct input pair has the exact Möbius/squarefree shape. -/
def PrefixInputRowsValid (rows : List PrefixMQ) : Prop :=
  ∀ row ∈ rows, PrefixInputRowValid row

instance (rows : List PrefixMQ) :
    Decidable (PrefixInputRowsValid rows) := by
  unfold PrefixInputRowsValid
  infer_instance

/-- Exact total of direct unscanned input pairs. -/
def inputTotal : List PrefixMQ → PrefixMQ
  | [] => PrefixMQ.zero
  | row :: rest => row + inputTotal rest

/-- Exact local prefix through `count` direct input rows. -/
def inputPrefixAt (rows : List PrefixMQ) (count : Nat) : PrefixMQ :=
  inputTotal (rows.take count)

/-- Sequential reference scan over the exact direct input pairs. -/
def inputScanFrom : PrefixMQ → List PrefixMQ → List PrefixMQ
  | _, [] => []
  | incoming, row :: rest =>
      let next := incoming + row
      next :: inputScanFrom next rest

/-- Production-shaped inclusive scan from zero. -/
def inclusiveInputScan (rows : List PrefixMQ) : List PrefixMQ :=
  inputScanFrom PrefixMQ.zero rows

@[simp] theorem inputTotal_append
    (left right : List PrefixMQ) :
    inputTotal (left ++ right) =
      inputTotal left + inputTotal right := by
  induction left with
  | nil => simp [inputTotal]
  | cons row rest inductionHypothesis =>
      simp [inputTotal, inductionHypothesis, PrefixMQ.add_assoc]

/-- Splitting a direct scan into consecutive chunks preserves every prefix;
the second chunk starts at the exact total of the first. -/
theorem inputScanFrom_append
    (incoming : PrefixMQ) (left right : List PrefixMQ) :
    inputScanFrom incoming (left ++ right) =
      inputScanFrom incoming left ++
        inputScanFrom (incoming + inputTotal left) right := by
  induction left generalizing incoming with
  | nil => simp [inputScanFrom, inputTotal]
  | cons row rest inductionHypothesis =>
      simp [inputScanFrom, inputTotal, inductionHypothesis,
        PrefixMQ.add_assoc]

@[simp] theorem inputTotal_mertens (rows : List PrefixMQ) :
    (inputTotal rows).mertens =
      (rows.map PrefixMQ.mertens).sum := by
  induction rows with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp [inputTotal, inductionHypothesis]

@[simp] theorem inputTotal_squarefree (rows : List PrefixMQ) :
    (inputTotal rows).squarefree =
      (rows.map PrefixMQ.squarefree).sum := by
  induction rows with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp [inputTotal, inductionHypothesis]

/-- Literal Mertens prefix of the unscanned production rows. -/
def inputLocalMertens (rows : List PrefixMQ) (count : Nat) : Int :=
  ((rows.take count).map PrefixMQ.mertens).sum

/-- Literal squarefree prefix of the unscanned production rows. -/
def inputLocalSquarefree (rows : List PrefixMQ) (count : Nat) : Nat :=
  ((rows.take count).map PrefixMQ.squarefree).sum

@[simp] theorem inputPrefixAt_mertens
    (rows : List PrefixMQ) (count : Nat) :
    (inputPrefixAt rows count).mertens =
      inputLocalMertens rows count := by
  simp [inputPrefixAt, inputLocalMertens]

@[simp] theorem inputPrefixAt_squarefree
    (rows : List PrefixMQ) (count : Nat) :
    (inputPrefixAt rows count).squarefree =
      inputLocalSquarefree rows count := by
  simp [inputPrefixAt, inputLocalSquarefree]

@[simp] theorem inputScanFrom_length
    (incoming : PrefixMQ) (rows : List PrefixMQ) :
    (inputScanFrom incoming rows).length = rows.length := by
  induction rows generalizing incoming with
  | nil => rfl
  | cons row rest inductionHypothesis =>
      simp [inputScanFrom, inductionHypothesis]

@[simp] theorem inclusiveInputScan_length (rows : List PrefixMQ) :
    (inclusiveInputScan rows).length = rows.length := by
  simp [inclusiveInputScan]

private theorem inputScanFrom_getElem
    (incoming : PrefixMQ) (rows : List PrefixMQ)
    (index : Nat) (inRange : index < rows.length) :
    (inputScanFrom incoming rows)[index]'(by simpa using inRange) =
      incoming + inputPrefixAt rows (index + 1) := by
  induction rows generalizing incoming index with
  | nil => simp at inRange
  | cons row rest inductionHypothesis =>
      cases index with
      | zero =>
          simp [inputScanFrom, inputPrefixAt, inputTotal]
      | succ index =>
          simp only [List.length_cons, Nat.succ_lt_succ_iff] at inRange
          simp only [inputScanFrom, List.getElem_cons_succ]
          rw [inductionHypothesis (incoming + row) index inRange]
          simp [inputPrefixAt, inputTotal, PrefixMQ.add_assoc]

/-- Every direct scan output is the exact inclusive pair prefix. -/
theorem inclusiveInputScan_getElem
    (rows : List PrefixMQ) (index : Nat)
    (inRange : index < rows.length) :
    (inclusiveInputScan rows)[index]'(by simpa using inRange) =
      inputPrefixAt rows (index + 1) := by
  have exactPrefix :=
    inputScanFrom_getElem PrefixMQ.zero rows index inRange
  simpa [inclusiveInputScan] using exactPrefix

/-- Pair initialized by the native row kernel before the inclusive scan. -/
def rowDelta (byte : UInt8) : PrefixMQ :=
  ⟨decodeMobiusByte byte, squarefreeIncrement byte⟩

/-- Exact total of a list of initialized row pairs. -/
def total : List UInt8 → PrefixMQ
  | [] => PrefixMQ.zero
  | byte :: rest => rowDelta byte + total rest

/-- Exact local prefix through `count` rows. -/
def prefixAt (rows : List UInt8) (count : Nat) : PrefixMQ :=
  total (rows.take count)

/-- Sequential inclusive scan from an arbitrary incoming pair.  This is a
small executable reference algorithm for the associative parallel scan. -/
def scanFrom : PrefixMQ → List UInt8 → List PrefixMQ
  | _, [] => []
  | incoming, byte :: rest =>
      let next := incoming + rowDelta byte
      next :: scanFrom next rest

/-- Inclusive local scan from zero, matching the output convention used by
`cub::DeviceScan::InclusiveScan`. -/
def inclusiveScan (rows : List UInt8) : List PrefixMQ :=
  scanFrom PrefixMQ.zero rows

@[simp] theorem total_mertens (rows : List UInt8) :
    (total rows).mertens =
      (rows.map decodeMobiusByte).sum := by
  induction rows with
  | nil => rfl
  | cons byte rest inductionHypothesis =>
      simp [total, rowDelta, inductionHypothesis]

@[simp] theorem total_squarefree (rows : List UInt8) :
    (total rows).squarefree =
      (rows.map squarefreeIncrement).sum := by
  induction rows with
  | nil => rfl
  | cons byte rest inductionHypothesis =>
      simp [total, rowDelta, inductionHypothesis]

/-- Literal local Mertens prefix specified independently of the scan. -/
def localMertens (rows : List UInt8) (count : Nat) : Int :=
  ((rows.take count).map decodeMobiusByte).sum

/-- Literal local squarefree-count prefix specified independently of the
scan. -/
def localSquarefree (rows : List UInt8) (count : Nat) : Nat :=
  ((rows.take count).map squarefreeIncrement).sum

@[simp] theorem prefixAt_mertens (rows : List UInt8) (count : Nat) :
    (prefixAt rows count).mertens = localMertens rows count := by
  simp [prefixAt, localMertens]

@[simp] theorem prefixAt_squarefree (rows : List UInt8) (count : Nat) :
    (prefixAt rows count).squarefree =
      localSquarefree rows count := by
  simp [prefixAt, localSquarefree]

@[simp] theorem scanFrom_length
    (incoming : PrefixMQ) (rows : List UInt8) :
    (scanFrom incoming rows).length = rows.length := by
  induction rows generalizing incoming with
  | nil => rfl
  | cons byte rest inductionHypothesis =>
      simp [scanFrom, inductionHypothesis]

@[simp] theorem inclusiveScan_length (rows : List UInt8) :
    (inclusiveScan rows).length = rows.length := by
  simp [inclusiveScan]

private theorem scanFrom_getElem
    (incoming : PrefixMQ) (rows : List UInt8)
    (index : Nat) (inRange : index < rows.length) :
    (scanFrom incoming rows)[index]'(by simpa using inRange) =
      incoming + prefixAt rows (index + 1) := by
  induction rows generalizing incoming index with
  | nil => simp at inRange
  | cons byte rest inductionHypothesis =>
      cases index with
      | zero =>
          simp [scanFrom, prefixAt, total]
      | succ index =>
          simp only [List.length_cons, Nat.succ_lt_succ_iff] at inRange
          simp only [scanFrom, List.getElem_cons_succ]
          rw [inductionHypothesis (incoming + rowDelta byte) index inRange]
          simp [prefixAt, total, PrefixMQ.add_assoc]

/-- Every produced row is the exact inclusive Mertens/squarefree prefix
through the corresponding source byte. -/
theorem inclusiveScan_getElem
    (rows : List UInt8) (index : Nat)
    (inRange : index < rows.length) :
    (inclusiveScan rows)[index]'(by simpa using inRange) =
      prefixAt rows (index + 1) := by
  have exactPrefix :=
    scanFrom_getElem PrefixMQ.zero rows index inRange
  simpa [inclusiveScan] using exactPrefix

/-- A valid qualification byte initializes an admissible direct production
row. -/
theorem rowDelta_prefixInputRowValid
    {byte : UInt8} (valid : MobiusByteValid byte) :
    PrefixInputRowValid (rowDelta byte) := by
  have bounds := decodeMobiusByte_bounds valid
  refine ⟨bounds.1, bounds.2, ?_⟩
  simp [rowDelta, squarefreeIncrement]

/-- Byte initialization maps a valid qualification stream to valid direct
production rows. -/
theorem map_rowDelta_prefixInputRowsValid
    {rows : List UInt8} (valid : MobiusRowsValid rows) :
    PrefixInputRowsValid (rows.map rowDelta) := by
  intro row member
  rw [List.mem_map] at member
  rcases member with ⟨byte, byteMember, rfl⟩
  exact rowDelta_prefixInputRowValid (valid byte byteMember)

/-- The byte reference total is exactly the direct-pair total after
initialization. -/
theorem inputTotal_map_rowDelta (rows : List UInt8) :
    inputTotal (rows.map rowDelta) = total rows := by
  induction rows with
  | nil => rfl
  | cons byte rest inductionHypothesis =>
      simp [inputTotal, total, inductionHypothesis]

/-- The qualification byte scan is definitionally simulated by the direct
production-row scan after row initialization. -/
theorem inputScanFrom_map_rowDelta
    (incoming : PrefixMQ) (rows : List UInt8) :
    inputScanFrom incoming (rows.map rowDelta) =
      scanFrom incoming rows := by
  induction rows generalizing incoming with
  | nil => rfl
  | cons byte rest inductionHypothesis =>
      simp [inputScanFrom, scanFrom, inductionHypothesis]

/-- Complete qualification-to-production scan equivalence. -/
theorem inclusiveInputScan_map_rowDelta (rows : List UInt8) :
    inclusiveInputScan (rows.map rowDelta) =
      inclusiveScan rows := by
  exact inputScanFrom_map_rowDelta PrefixMQ.zero rows

/-! ## Fixed-width safety -/

private theorem inputTotal_bounds
    {rows : List PrefixMQ} (valid : PrefixInputRowsValid rows) :
    -(rows.length : Int) ≤ (inputTotal rows).mertens ∧
      (inputTotal rows).mertens ≤ (rows.length : Int) ∧
      (inputTotal rows).squarefree ≤ rows.length := by
  induction rows with
  | nil => simp [inputTotal]
  | cons row rest inductionHypothesis =>
      have rowValid : PrefixInputRowValid row :=
        valid row (by simp)
      have restValid : PrefixInputRowsValid rest := by
        intro other member
        exact valid other (by simp [member])
      have rowSquarefreeBound : row.squarefree ≤ 1 := by
        rw [rowValid.2.2]
        split <;> omega
      have rowLower := rowValid.1
      have rowUpper := rowValid.2.1
      have tailBounds := inductionHypothesis restValid
      simp only [inputTotal, PrefixMQ.add_mertens,
        PrefixMQ.add_squarefree, List.length_cons, Nat.cast_add,
        Nat.cast_one]
      omega

private theorem total_bounds
    {rows : List UInt8} (valid : MobiusRowsValid rows) :
    -(rows.length : Int) ≤ (total rows).mertens ∧
      (total rows).mertens ≤ (rows.length : Int) ∧
      (total rows).squarefree ≤ rows.length := by
  induction rows with
  | nil => simp [total]
  | cons byte rest inductionHypothesis =>
      have byteValid : MobiusByteValid byte :=
        valid byte (by simp)
      have restValid : MobiusRowsValid rest := by
        intro other member
        exact valid other (by simp [member])
      have bounds := decodeMobiusByte_bounds byteValid
      have incrementBound := squarefreeIncrement_le_one byte
      have tailBounds := inductionHypothesis restValid
      simp only [total, rowDelta, PrefixMQ.add_mertens,
        PrefixMQ.add_squarefree, List.length_cons, Nat.cast_add,
        Nat.cast_one]
      omega

/-- Machine-field bounds for one exact local prefix. -/
def PrefixFitsMachineWords (pfx : PrefixMQ) : Prop :=
  -(2 ^ 31 : Int) ≤ pfx.mertens ∧
    pfx.mertens < 2 ^ 31 ∧
    pfx.squarefree < 2 ^ 32

/-- Every direct production-row prefix fits losslessly in the native
signed/unsigned 32-bit pair. -/
theorem inputPrefixAt_fits_machine_words
    {rows : List PrefixMQ} (valid : PrefixInputRowsValid rows)
    (rowCountBound : rows.length ≤ maximumSegmentRows)
    (count : Nat) :
    PrefixFitsMachineWords (inputPrefixAt rows count) := by
  have takeValid : PrefixInputRowsValid (rows.take count) := by
    intro row member
    exact valid row (List.mem_of_mem_take member)
  have bounds := inputTotal_bounds takeValid
  have takeLengthBound :
      (rows.take count).length ≤ maximumSegmentRows := by
    rw [List.length_take]
    omega
  have mertensFits :=
    localMertens_fits_int32 takeLengthBound bounds.1 bounds.2.1
  have squarefreeFits :=
    localSquarefree_fits_uint32 takeLengthBound bounds.2.2
  exact ⟨mertensFits.1, mertensFits.2, squarefreeFits⟩

/-- Fixed-width safety at every direct CUB-shaped scan output. -/
theorem inclusiveInputScan_getElem_fits_machine_words
    {rows : List PrefixMQ} (valid : PrefixInputRowsValid rows)
    (rowCountBound : rows.length ≤ maximumSegmentRows)
    (index : Nat) (inRange : index < rows.length) :
    PrefixFitsMachineWords
      ((inclusiveInputScan rows)[index]'(by simpa using inRange)) := by
  rw [inclusiveInputScan_getElem rows index inRange]
  exact inputPrefixAt_fits_machine_words
    valid rowCountBound (index + 1)

/-- Every exact local prefix of a valid production-sized byte list fits
losslessly in the native signed/unsigned 32-bit pair. -/
theorem prefixAt_fits_machine_words
    {rows : List UInt8} (valid : MobiusRowsValid rows)
    (rowCountBound : rows.length ≤ maximumSegmentRows)
    (count : Nat) :
    PrefixFitsMachineWords (prefixAt rows count) := by
  have takeValid : MobiusRowsValid (rows.take count) := by
    intro byte member
    exact valid byte (List.mem_of_mem_take member)
  have bounds := total_bounds takeValid
  have takeLengthBound :
      (rows.take count).length ≤ maximumSegmentRows := by
    rw [List.length_take]
    omega
  have mertensFits :=
    localMertens_fits_int32 takeLengthBound bounds.1 bounds.2.1
  have squarefreeFits :=
    localSquarefree_fits_uint32 takeLengthBound bounds.2.2
  exact ⟨mertensFits.1, mertensFits.2, squarefreeFits⟩

/-- The same lossless-width statement, phrased directly for every CUB
inclusive-scan output row. -/
theorem inclusiveScan_getElem_fits_machine_words
    {rows : List UInt8} (valid : MobiusRowsValid rows)
    (rowCountBound : rows.length ≤ maximumSegmentRows)
    (index : Nat) (inRange : index < rows.length) :
    PrefixFitsMachineWords
      ((inclusiveScan rows)[index]'(by simpa using inRange)) := by
  rw [inclusiveScan_getElem rows index inRange]
  exact prefixAt_fits_machine_words valid rowCountBound (index + 1)

/-! ## Deterministic affine candidate reduction -/

/-- One candidate per inclusive prefix.  `endpoint = 0` is the integer
endpoint and `endpoint = 1` is its right limit. -/
def rowCandidates
    (value : Nat → PrefixMQ → Int) (endpoint : Nat)
    (prefixes : List PrefixMQ) : List OrderedCandidate :=
  prefixes.mapIdx fun index pfx =>
    { value := value index pfx
      order := 2 * index + endpoint }

@[simp] theorem rowCandidates_length
    (value : Nat → PrefixMQ → Int) (endpoint : Nat)
    (prefixes : List PrefixMQ) :
    (rowCandidates value endpoint prefixes).length =
      prefixes.length := by
  simp [rowCandidates]

/-- Every generated candidate retains the exact prefix and source order from
which it was computed. -/
theorem mem_rowCandidates_iff
    {value : Nat → PrefixMQ → Int} {endpoint : Nat}
    {prefixes : List PrefixMQ} {candidate : OrderedCandidate} :
    candidate ∈ rowCandidates value endpoint prefixes ↔
      ∃ index, ∃ inRange : index < prefixes.length,
        candidate =
          { value := value index prefixes[index]
            order := 2 * index + endpoint } := by
  simp only [rowCandidates, List.mem_mapIdx]
  constructor
  · rintro ⟨index, inRange, equality⟩
    exact ⟨index, inRange, equality.symm⟩
  · rintro ⟨index, inRange, equality⟩
    exact ⟨index, inRange, equality.symm⟩

/-- A candidate generated by the production-shaped direct scan rewrites to
the literal prefix of the unscanned input pairs. -/
theorem mem_inputScanRowCandidates_iff
    {rows : List PrefixMQ} {value : Nat → PrefixMQ → Int}
    {endpoint : Nat} {candidate : OrderedCandidate} :
    candidate ∈
        rowCandidates value endpoint (inclusiveInputScan rows) ↔
      ∃ index, ∃ _inRange : index < rows.length,
        candidate =
          { value := value index (inputPrefixAt rows (index + 1))
            order := 2 * index + endpoint } := by
  rw [mem_rowCandidates_iff]
  constructor
  · rintro ⟨index, inScanRange, equality⟩
    have inRange : index < rows.length := by
      simpa using inScanRange
    refine ⟨index, inRange, ?_⟩
    calc
      candidate =
          { value := value index
              (inclusiveInputScan rows)[index]
            order := 2 * index + endpoint } := equality
      _ =
          { value := value index
              (inputPrefixAt rows (index + 1))
            order := 2 * index + endpoint } := by
          rw [inclusiveInputScan_getElem rows index inRange]
  · rintro ⟨index, inRange, equality⟩
    have inScanRange :
        index < (inclusiveInputScan rows).length := by
      simpa using inRange
    refine ⟨index, inScanRange, ?_⟩
    calc
      candidate =
          { value := value index
              (inputPrefixAt rows (index + 1))
            order := 2 * index + endpoint } := equality
      _ =
          { value := value index
              (inclusiveInputScan rows)[index]
            order := 2 * index + endpoint } := by
          rw [inclusiveInputScan_getElem rows index inRange]

/-- A candidate generated from the scan can be rewritten directly to the
literal local prefix, without retaining the implementation scan in its
statement. -/
theorem mem_scanRowCandidates_iff
    {rows : List UInt8} {value : Nat → PrefixMQ → Int}
    {endpoint : Nat} {candidate : OrderedCandidate} :
    candidate ∈
        rowCandidates value endpoint (inclusiveScan rows) ↔
      ∃ index, ∃ _inRange : index < rows.length,
        candidate =
          { value := value index (prefixAt rows (index + 1))
            order := 2 * index + endpoint } := by
  rw [mem_rowCandidates_iff]
  constructor
  · rintro ⟨index, inScanRange, equality⟩
    have inRange : index < rows.length := by
      simpa using inScanRange
    refine ⟨index, inRange, ?_⟩
    calc
      candidate =
          { value := value index
              (inclusiveScan rows)[index]
            order := 2 * index + endpoint } := equality
      _ =
          { value := value index (prefixAt rows (index + 1))
            order := 2 * index + endpoint } := by
          rw [inclusiveScan_getElem rows index inRange]
  · rintro ⟨index, inRange, equality⟩
    have inScanRange :
        index < (inclusiveScan rows).length := by
      simpa using inRange
    refine ⟨index, inScanRange, ?_⟩
    calc
      candidate =
          { value := value index (prefixAt rows (index + 1))
            order := 2 * index + endpoint } := equality
      _ =
          { value := value index
              (inclusiveScan rows)[index]
            order := 2 * index + endpoint } := by
          rw [inclusiveScan_getElem rows index inRange]

/-- The exact native order word is lossless for every production-sized scan,
including right-limit endpoints. -/
theorem rowCandidate_order_fits_uint32
    {value : Nat → PrefixMQ → Int} {endpoint : Nat}
    {prefixes : List PrefixMQ} {candidate : OrderedCandidate}
    (rowCountBound : prefixes.length ≤ maximumSegmentRows)
    (endpointBound : endpoint ≤ 1)
    (member : candidate ∈ rowCandidates value endpoint prefixes) :
    candidate.order < 2 ^ 32 := by
  rw [mem_rowCandidates_iff] at member
  rcases member with ⟨index, inRange, rfl⟩
  norm_num [maximumSegmentRows] at rowCountBound ⊢
  omega

/-- Integer and optional right-limit candidates emitted for each prefix.

`includeRight` is evaluated at the source-row index recovered from the exact
odd order word.  The production terminal range uses it to omit the right
limit at the final source endpoint. -/
def pairedEndpointCandidates
    (integerValue rightValue : Nat → PrefixMQ → Int)
    (includeRight : Nat → Bool)
    (prefixes : List PrefixMQ) : List OrderedCandidate :=
  rowCandidates integerValue 0 prefixes ++
    (rowCandidates rightValue 1 prefixes).filter
      (fun candidate => includeRight (candidate.order / 2))

/-- Every retained paired-endpoint candidate came from either the integer or
right-limit row list. -/
theorem mem_pairedEndpointCandidates
    {integerValue rightValue : Nat → PrefixMQ → Int}
    {includeRight : Nat → Bool}
    {prefixes : List PrefixMQ} {candidate : OrderedCandidate}
    (member :
      candidate ∈ pairedEndpointCandidates
        integerValue rightValue includeRight prefixes) :
    candidate ∈ rowCandidates integerValue 0 prefixes ∨
      candidate ∈ rowCandidates rightValue 1 prefixes := by
  rw [pairedEndpointCandidates, List.mem_append] at member
  rcases member with integerMember | rightMember
  · exact Or.inl integerMember
  · exact Or.inr (List.mem_of_mem_filter rightMember)

/-- Every retained integer/right-limit order is lossless in `uint32_t`. -/
theorem pairedEndpointCandidate_order_fits_uint32
    {integerValue rightValue : Nat → PrefixMQ → Int}
    {includeRight : Nat → Bool}
    {prefixes : List PrefixMQ} {candidate : OrderedCandidate}
    (rowCountBound : prefixes.length ≤ maximumSegmentRows)
    (member :
      candidate ∈ pairedEndpointCandidates
        integerValue rightValue includeRight prefixes) :
    candidate.order < 2 ^ 32 := by
  rcases mem_pairedEndpointCandidates member with
      integerMember | rightMember
  · exact rowCandidate_order_fits_uint32
      rowCountBound (by omega) integerMember
  · exact rowCandidate_order_fits_uint32
      rowCountBound (by omega) rightMember

/-- Every production-shaped direct-scan endpoint candidate rewrites to an
integer or right-limit value evaluated at the literal unscanned-row prefix. -/
theorem mem_inputScanPairedEndpointCandidates
    {rows : List PrefixMQ}
    {integerValue rightValue : Nat → PrefixMQ → Int}
    {includeRight : Nat → Bool}
    {candidate : OrderedCandidate}
    (member :
      candidate ∈ pairedEndpointCandidates
        integerValue rightValue includeRight
        (inclusiveInputScan rows)) :
    (∃ index, ∃ _inRange : index < rows.length,
      candidate =
        { value := integerValue index
            (inputPrefixAt rows (index + 1))
          order := 2 * index }) ∨
    (∃ index, ∃ _inRange : index < rows.length,
      candidate =
        { value := rightValue index
            (inputPrefixAt rows (index + 1))
          order := 2 * index + 1 }) := by
  rcases mem_pairedEndpointCandidates member with
      integerMember | rightMember
  · left
    exact
      (mem_inputScanRowCandidates_iff.mp integerMember)
  · right
    exact
      (mem_inputScanRowCandidates_iff.mp rightMember)

/-- Select the smaller key, retaining the corresponding complete candidate.
This is the neutral form of one native candidate-combine step. -/
def combineByKey {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (left right : OrderedCandidate) : OrderedCandidate :=
  if key left ≤ key right then left else right

theorem key_combineByKey
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (left right : OrderedCandidate) :
    key (combineByKey key left right) =
      min (key left) (key right) := by
  rw [combineByKey, min_def]
  split <;> rfl

theorem combineByKey_eq_left_or_right
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (left right : OrderedCandidate) :
    combineByKey key left right = left ∨
      combineByKey key left right = right := by
  unfold combineByKey
  split
  · exact Or.inl rfl
  · exact Or.inr rfl

/-- Sequential reference reduction.  Associativity below permits the same
list to be split into thread, block, and device subreductions. -/
def foldByKey {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (initial : OrderedCandidate)
    (candidates : List OrderedCandidate) : OrderedCandidate :=
  candidates.foldl (combineByKey key) initial

@[simp] theorem foldByKey_append
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (initial : OrderedCandidate)
    (left right : List OrderedCandidate) :
    foldByKey key initial (left ++ right) =
      foldByKey key (foldByKey key initial left) right := by
  simp [foldByKey, List.foldl_append]

private theorem foldByKey_key_le_initial
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (initial : OrderedCandidate)
    (candidates : List OrderedCandidate) :
    key (foldByKey key initial candidates) ≤ key initial := by
  induction candidates generalizing initial with
  | nil => simp [foldByKey]
  | cons candidate rest inductionHypothesis =>
      change
        key (foldByKey key
          (combineByKey key initial candidate) rest) ≤ key initial
      exact (inductionHypothesis
        (combineByKey key initial candidate)).trans
        (by
          rw [key_combineByKey key initial candidate]
          exact min_le_left _ _)

private theorem foldByKey_key_le_of_mem
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (initial : OrderedCandidate)
    {candidates : List OrderedCandidate}
    {candidate : OrderedCandidate}
    (member : candidate ∈ candidates) :
    key (foldByKey key initial candidates) ≤ key candidate := by
  induction candidates generalizing initial with
  | nil => simp at member
  | cons head rest inductionHypothesis =>
      rw [List.mem_cons] at member
      change
        key (foldByKey key
          (combineByKey key initial head) rest) ≤ key candidate
      rcases member with rfl | member
      · exact (foldByKey_key_le_initial key
          (combineByKey key initial candidate) rest).trans
          (by
            rw [key_combineByKey key initial candidate]
            exact min_le_right _ _)
      · exact inductionHypothesis
          (combineByKey key initial head) member

private theorem foldByKey_mem
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    (initial : OrderedCandidate)
    (candidates : List OrderedCandidate) :
    foldByKey key initial candidates ∈ initial :: candidates := by
  induction candidates generalizing initial with
  | nil => simp [foldByKey]
  | cons candidate rest inductionHypothesis =>
      change
        foldByKey key (combineByKey key initial candidate) rest ∈
          initial :: candidate :: rest
      have member :=
        inductionHypothesis (combineByKey key initial candidate)
      rw [List.mem_cons] at member
      rcases member with equality | member
      · rw [equality]
        rcases combineByKey_eq_left_or_right key initial candidate with
          left | right
        · simp [left]
        · simp [right]
      · simp [member]

/-- Optional reduction used for a candidate list which may be empty. -/
def reduceByKey {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ) :
    List OrderedCandidate → Option OrderedCandidate
  | [] => none
  | first :: rest => some (foldByKey key first rest)

/-- A nonempty candidate list always returns a winner. -/
theorem reduceByKey_exists_of_ne_nil
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    {candidates : List OrderedCandidate}
    (nonempty : candidates ≠ []) :
    ∃ best, reduceByKey key candidates = some best := by
  cases candidates with
  | nil => exact (nonempty rfl).elim
  | cons first rest =>
      exact ⟨foldByKey key first rest, rfl⟩

/-- Complete correctness statement for the generic deterministic reducer:
the returned identity came from the input and its key is no greater than
every input key. -/
theorem reduceByKey_sound
    {κ : Type} [LinearOrder κ]
    (key : OrderedCandidate → κ)
    {candidates : List OrderedCandidate}
    {best : OrderedCandidate}
    (reduced : reduceByKey key candidates = some best) :
    best ∈ candidates ∧
      ∀ candidate ∈ candidates, key best ≤ key candidate := by
  cases candidates with
  | nil => simp [reduceByKey] at reduced
  | cons first rest =>
      simp only [reduceByKey, Option.some.injEq] at reduced
      have bestEquality :
          best = foldByKey key first rest := reduced.symm
      rw [bestEquality]
      constructor
      · exact foldByKey_mem key first rest
      · intro candidate member
        rw [List.mem_cons] at member
        rcases member with equality | member
        · rw [equality]
          exact foldByKey_key_le_initial key first rest
        · exact foldByKey_key_le_of_mem key first member

def reduceMaximum : List OrderedCandidate → Option OrderedCandidate :=
  reduceByKey lowerKey

def reduceMinimum : List OrderedCandidate → Option OrderedCandidate :=
  reduceByKey upperKey

/-- A nonempty direct production-row leaf produces both deterministic
extrema. -/
theorem inputScanReducers_return_winners
    {rows : List PrefixMQ} (nonempty : rows ≠ [])
    (lowerValue upperValue : Nat → PrefixMQ → Int)
    (lowerEndpoint upperEndpoint : Nat) :
    ∃ lowerBest upperBest,
      reduceMaximum
          (rowCandidates lowerValue lowerEndpoint
            (inclusiveInputScan rows)) = some lowerBest ∧
      reduceMinimum
          (rowCandidates upperValue upperEndpoint
            (inclusiveInputScan rows)) = some upperBest := by
  have scanNonempty : inclusiveInputScan rows ≠ [] := by
    apply List.ne_nil_of_length_pos
    rw [inclusiveInputScan_length]
    exact List.length_pos_of_ne_nil nonempty
  have lowerCandidatesNonempty :
      rowCandidates lowerValue lowerEndpoint
          (inclusiveInputScan rows) ≠ [] := by
    apply List.ne_nil_of_length_pos
    rw [rowCandidates_length]
    exact List.length_pos_of_ne_nil scanNonempty
  have upperCandidatesNonempty :
      rowCandidates upperValue upperEndpoint
          (inclusiveInputScan rows) ≠ [] := by
    apply List.ne_nil_of_length_pos
    rw [rowCandidates_length]
    exact List.length_pos_of_ne_nil scanNonempty
  rcases reduceByKey_exists_of_ne_nil lowerKey
      lowerCandidatesNonempty with ⟨lowerBest, lowerReduced⟩
  rcases reduceByKey_exists_of_ne_nil upperKey
      upperCandidatesNonempty with ⟨upperBest, upperReduced⟩
  exact ⟨lowerBest, upperBest, lowerReduced, upperReduced⟩

/-- A nonempty byte leaf produces both deterministic extrema. -/
theorem scanReducers_return_winners
    {rows : List UInt8} (nonempty : rows ≠ [])
    (lowerValue upperValue : Nat → PrefixMQ → Int)
    (lowerEndpoint upperEndpoint : Nat) :
    ∃ lowerBest upperBest,
      reduceMaximum
          (rowCandidates lowerValue lowerEndpoint
            (inclusiveScan rows)) = some lowerBest ∧
      reduceMinimum
          (rowCandidates upperValue upperEndpoint
            (inclusiveScan rows)) = some upperBest := by
  have scanNonempty : inclusiveScan rows ≠ [] := by
    apply List.ne_nil_of_length_pos
    rw [inclusiveScan_length]
    exact List.length_pos_of_ne_nil nonempty
  have lowerCandidatesNonempty :
      rowCandidates lowerValue lowerEndpoint
          (inclusiveScan rows) ≠ [] := by
    apply List.ne_nil_of_length_pos
    rw [rowCandidates_length]
    exact List.length_pos_of_ne_nil scanNonempty
  have upperCandidatesNonempty :
      rowCandidates upperValue upperEndpoint
          (inclusiveScan rows) ≠ [] := by
    apply List.ne_nil_of_length_pos
    rw [rowCandidates_length]
    exact List.length_pos_of_ne_nil scanNonempty
  rcases reduceByKey_exists_of_ne_nil lowerKey
      lowerCandidatesNonempty with ⟨lowerBest, lowerReduced⟩
  rcases reduceByKey_exists_of_ne_nil upperKey
      upperCandidatesNonempty with ⟨upperBest, upperReduced⟩
  exact ⟨lowerBest, upperBest, lowerReduced, upperReduced⟩

/-- Exact meaning of the maximum reduction key: larger value wins, and equal
values are resolved by smaller source order. -/
theorem lowerKey_le_iff (left right : OrderedCandidate) :
    lowerKey left ≤ lowerKey right ↔
      right.value ≤ left.value ∧
        (right.value = left.value → left.order ≤ right.order) := by
  rcases left with ⟨leftValue, leftOrder⟩
  rcases right with ⟨rightValue, rightOrder⟩
  unfold lowerKey
  dsimp
  rw [Prod.Lex.toLex_le_toLex]
  constructor
  · rintro (strict | ⟨equal, order⟩)
    · constructor
      · omega
      · intro valuesEqual
        omega
    · constructor
      · omega
      · intro
        exact order
  · rintro ⟨value, tie⟩
    by_cases equal : rightValue = leftValue
    · right
      exact ⟨by omega, tie equal⟩
    · left
      omega

/-- Exact meaning of the minimum reduction key: smaller value wins, and
equal values are resolved by smaller source order. -/
theorem upperKey_le_iff (left right : OrderedCandidate) :
    upperKey left ≤ upperKey right ↔
      left.value ≤ right.value ∧
        (left.value = right.value → left.order ≤ right.order) := by
  rcases left with ⟨leftValue, leftOrder⟩
  rcases right with ⟨rightValue, rightOrder⟩
  unfold upperKey
  dsimp
  rw [Prod.Lex.toLex_le_toLex]
  constructor
  · rintro (strict | ⟨equal, order⟩)
    · constructor
      · omega
      · intro valuesEqual
        omega
    · constructor
      · omega
      · intro
        exact order
  · rintro ⟨value, tie⟩
    by_cases equal : leftValue = rightValue
    · right
      exact ⟨equal, tie equal⟩
    · left
      omega

/-- The maximum reducer returns an input with globally maximal value and the
earliest order among every tied maximum. -/
theorem reduceMaximum_sound
    {candidates : List OrderedCandidate}
    {best : OrderedCandidate}
    (reduced : reduceMaximum candidates = some best) :
    best ∈ candidates ∧
      ∀ candidate ∈ candidates,
        candidate.value ≤ best.value ∧
          (candidate.value = best.value →
            best.order ≤ candidate.order) := by
  have sound :=
    reduceByKey_sound lowerKey reduced
  exact ⟨sound.1, fun candidate member =>
    (lowerKey_le_iff best candidate).mp
      (sound.2 candidate member)⟩

/-- The minimum reducer returns an input with globally minimal value and the
earliest order among every tied minimum. -/
theorem reduceMinimum_sound
    {candidates : List OrderedCandidate}
    {best : OrderedCandidate}
    (reduced : reduceMinimum candidates = some best) :
    best ∈ candidates ∧
      ∀ candidate ∈ candidates,
        best.value ≤ candidate.value ∧
          (best.value = candidate.value →
            best.order ≤ candidate.order) := by
  have sound :=
    reduceByKey_sound upperKey reduced
  exact ⟨sound.1, fun candidate member =>
    (upperKey_le_iff best candidate).mp
      (sound.2 candidate member)⟩

/-- Production-shaped maximum over integer plus retained right-limit
candidates: the winner is retained, width-safe, globally maximal, and the
earliest tied endpoint. -/
theorem reducePairedEndpointMaximum_sound
    {integerValue rightValue : Nat → PrefixMQ → Int}
    {includeRight : Nat → Bool}
    {prefixes : List PrefixMQ} {best : OrderedCandidate}
    (rowCountBound : prefixes.length ≤ maximumSegmentRows)
    (reduced :
      reduceMaximum
          (pairedEndpointCandidates
            integerValue rightValue includeRight prefixes) =
        some best) :
    best ∈ pairedEndpointCandidates
        integerValue rightValue includeRight prefixes ∧
      best.order < 2 ^ 32 ∧
      ∀ candidate ∈ pairedEndpointCandidates
          integerValue rightValue includeRight prefixes,
        candidate.value ≤ best.value ∧
          (candidate.value = best.value →
            best.order ≤ candidate.order) := by
  have sound := reduceMaximum_sound reduced
  exact ⟨sound.1,
    pairedEndpointCandidate_order_fits_uint32
      rowCountBound sound.1,
    sound.2⟩

/-- Production-shaped minimum over integer plus retained right-limit
candidates: the winner is retained, width-safe, globally minimal, and the
earliest tied endpoint. -/
theorem reducePairedEndpointMinimum_sound
    {integerValue rightValue : Nat → PrefixMQ → Int}
    {includeRight : Nat → Bool}
    {prefixes : List PrefixMQ} {best : OrderedCandidate}
    (rowCountBound : prefixes.length ≤ maximumSegmentRows)
    (reduced :
      reduceMinimum
          (pairedEndpointCandidates
            integerValue rightValue includeRight prefixes) =
        some best) :
    best ∈ pairedEndpointCandidates
        integerValue rightValue includeRight prefixes ∧
      best.order < 2 ^ 32 ∧
      ∀ candidate ∈ pairedEndpointCandidates
          integerValue rightValue includeRight prefixes,
        best.value ≤ candidate.value ∧
          (best.value = candidate.value →
            best.order ≤ candidate.order) := by
  have sound := reduceMinimum_sound reduced
  exact ⟨sound.1,
    pairedEndpointCandidate_order_fits_uint32
      rowCountBound sound.1,
    sound.2⟩

theorem combineMaximum_assoc
    (first second third : OrderedCandidate) :
    combineByKey lowerKey
        (combineByKey lowerKey first second) third =
      combineByKey lowerKey first
        (combineByKey lowerKey second third) := by
  apply lowerKey_injective
  simp only [key_combineByKey, min_assoc]

theorem combineMaximum_comm
    (first second : OrderedCandidate) :
    combineByKey lowerKey first second =
      combineByKey lowerKey second first := by
  apply lowerKey_injective
  simp only [key_combineByKey, min_comm]

theorem combineMaximum_idem (candidate : OrderedCandidate) :
    combineByKey lowerKey candidate candidate = candidate := by
  apply lowerKey_injective
  simp only [key_combineByKey, min_self]

theorem combineMinimum_assoc
    (first second third : OrderedCandidate) :
    combineByKey upperKey
        (combineByKey upperKey first second) third =
      combineByKey upperKey first
        (combineByKey upperKey second third) := by
  apply upperKey_injective
  simp only [key_combineByKey, min_assoc]

theorem combineMinimum_comm
    (first second : OrderedCandidate) :
    combineByKey upperKey first second =
      combineByKey upperKey second first := by
  apply upperKey_injective
  simp only [key_combineByKey, min_comm]

theorem combineMinimum_idem (candidate : OrderedCandidate) :
    combineByKey upperKey candidate candidate = candidate := by
  apply upperKey_injective
  simp only [key_combineByKey, min_self]

/-! ## Scan-plus-reduction capstone -/

/-- Architecture-independent correctness boundary for one production native
leaf whose fused finalizer has already emitted the unscanned input pairs.

The first conjunct proves every CUB-shaped inclusive row equals the literal
Mertens/squarefree prefix and fits its fixed-width fields.  The remaining
conjuncts prove that any returned lower/upper candidate is a genuine row
candidate, its source order fits `uint32_t`, its value is globally extremal,
and its tie order is the earliest one.

The value functions are parameters because Hurst and the two squarefree
endpoints use different exact integer formulas; this theorem proves the
common scan/reduction algorithm once. -/
theorem inputScanAndCandidateReduction_sound
    {rows : List PrefixMQ}
    (valid : PrefixInputRowsValid rows)
    (rowCountBound : rows.length ≤ maximumSegmentRows)
    (lowerValue upperValue : Nat → PrefixMQ → Int)
    {lowerEndpoint upperEndpoint : Nat}
    (lowerEndpointBound : lowerEndpoint ≤ 1)
    (upperEndpointBound : upperEndpoint ≤ 1) :
    (∀ index, (inRange : index < rows.length) →
      let pfx :=
        (inclusiveInputScan rows)[index]'(by simpa using inRange)
      pfx.mertens = inputLocalMertens rows (index + 1) ∧
        pfx.squarefree =
          inputLocalSquarefree rows (index + 1) ∧
        PrefixFitsMachineWords pfx) ∧
    (∀ best,
      reduceMaximum
          (rowCandidates lowerValue lowerEndpoint
            (inclusiveInputScan rows)) = some best →
        best ∈ rowCandidates lowerValue lowerEndpoint
            (inclusiveInputScan rows) ∧
        best.order < 2 ^ 32 ∧
        ∀ candidate ∈ rowCandidates lowerValue lowerEndpoint
            (inclusiveInputScan rows),
          candidate.value ≤ best.value ∧
            (candidate.value = best.value →
              best.order ≤ candidate.order)) ∧
    (∀ best,
      reduceMinimum
          (rowCandidates upperValue upperEndpoint
            (inclusiveInputScan rows)) = some best →
        best ∈ rowCandidates upperValue upperEndpoint
            (inclusiveInputScan rows) ∧
        best.order < 2 ^ 32 ∧
        ∀ candidate ∈ rowCandidates upperValue upperEndpoint
            (inclusiveInputScan rows),
          best.value ≤ candidate.value ∧
            (best.value = candidate.value →
              best.order ≤ candidate.order)) := by
  constructor
  · intro index inRange
    have exactPrefix :=
      inclusiveInputScan_getElem rows index inRange
    rw [exactPrefix]
    exact ⟨inputPrefixAt_mertens rows (index + 1),
      inputPrefixAt_squarefree rows (index + 1),
      inputPrefixAt_fits_machine_words
        valid rowCountBound (index + 1)⟩
  constructor
  · intro best reduced
    have sound := reduceMaximum_sound reduced
    refine ⟨sound.1, ?_, sound.2⟩
    apply rowCandidate_order_fits_uint32
      (endpoint := lowerEndpoint)
      (prefixes := inclusiveInputScan rows)
    · simpa using rowCountBound
    · exact lowerEndpointBound
    · exact sound.1
  · intro best reduced
    have sound := reduceMinimum_sound reduced
    refine ⟨sound.1, ?_, sound.2⟩
    apply rowCandidate_order_fits_uint32
      (endpoint := upperEndpoint)
      (prefixes := inclusiveInputScan rows)
    · simpa using rowCountBound
    · exact upperEndpointBound
    · exact sound.1

/-- Qualification-byte specialization of the production scan/reduction
boundary.  `inclusiveInputScan_map_rowDelta` proves that this path initializes
the same direct input pairs before scanning. -/
theorem scanAndCandidateReduction_sound
    {rows : List UInt8}
    (valid : MobiusRowsValid rows)
    (rowCountBound : rows.length ≤ maximumSegmentRows)
    (lowerValue upperValue : Nat → PrefixMQ → Int)
    {lowerEndpoint upperEndpoint : Nat}
    (lowerEndpointBound : lowerEndpoint ≤ 1)
    (upperEndpointBound : upperEndpoint ≤ 1) :
    (∀ index, (inRange : index < rows.length) →
      let pfx :=
        (inclusiveScan rows)[index]'(by simpa using inRange)
      pfx.mertens = localMertens rows (index + 1) ∧
        pfx.squarefree = localSquarefree rows (index + 1) ∧
        PrefixFitsMachineWords pfx) ∧
    (∀ best,
      reduceMaximum
          (rowCandidates lowerValue lowerEndpoint
            (inclusiveScan rows)) = some best →
        best ∈ rowCandidates lowerValue lowerEndpoint
            (inclusiveScan rows) ∧
        best.order < 2 ^ 32 ∧
        ∀ candidate ∈ rowCandidates lowerValue lowerEndpoint
            (inclusiveScan rows),
          candidate.value ≤ best.value ∧
            (candidate.value = best.value →
              best.order ≤ candidate.order)) ∧
    (∀ best,
      reduceMinimum
          (rowCandidates upperValue upperEndpoint
            (inclusiveScan rows)) = some best →
        best ∈ rowCandidates upperValue upperEndpoint
            (inclusiveScan rows) ∧
        best.order < 2 ^ 32 ∧
        ∀ candidate ∈ rowCandidates upperValue upperEndpoint
            (inclusiveScan rows),
          best.value ≤ candidate.value ∧
            (best.value = candidate.value →
              best.order ≤ candidate.order)) := by
  constructor
  · intro index inRange
    have exactPrefix := inclusiveScan_getElem rows index inRange
    rw [exactPrefix]
    exact ⟨prefixAt_mertens rows (index + 1),
      prefixAt_squarefree rows (index + 1),
      prefixAt_fits_machine_words
        valid rowCountBound (index + 1)⟩
  constructor
  · intro best reduced
    have sound := reduceMaximum_sound reduced
    refine ⟨sound.1, ?_, sound.2⟩
    apply rowCandidate_order_fits_uint32
      (endpoint := lowerEndpoint)
      (prefixes := inclusiveScan rows)
    · simpa using rowCountBound
    · exact lowerEndpointBound
    · exact sound.1
  · intro best reduced
    have sound := reduceMinimum_sound reduced
    refine ⟨sound.1, ?_, sound.2⟩
    apply rowCandidate_order_fits_uint32
      (endpoint := upperEndpoint)
      (prefixes := inclusiveScan rows)
    · simpa using rowCountBound
    · exact upperEndpointBound
    · exact sound.1

#print axioms inclusiveInputScan_getElem
#print axioms inputScanFrom_append
#print axioms inputPrefixAt_fits_machine_words
#print axioms inputScanAndCandidateReduction_sound
#print axioms inclusiveInputScan_map_rowDelta
#print axioms mem_inputScanRowCandidates_iff
#print axioms mem_inputScanPairedEndpointCandidates
#print axioms inputScanReducers_return_winners
#print axioms inclusiveScan_getElem
#print axioms mem_scanRowCandidates_iff
#print axioms prefixAt_fits_machine_words
#print axioms reduceMaximum_sound
#print axioms reduceMinimum_sound
#print axioms reducePairedEndpointMaximum_sound
#print axioms reducePairedEndpointMinimum_sound
#print axioms scanReducers_return_winners
#print axioms combineMaximum_assoc
#print axioms combineMinimum_assoc
#print axioms scanAndCandidateReduction_sound

end SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
