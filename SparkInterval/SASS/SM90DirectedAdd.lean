/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.PTX.Semantics

/-!
# A restricted SM90 directed-add translation slice

This file models one deliberately small post-compilation vocabulary: an
unpredicated SM90 `DADD.RM` followed by an unpredicated `DADD.RP`.  Unlike an
opcode-count audit, an `AddSlice` records the destination and both source
registers of each instruction.  Its executable checker verifies the complete
two-instruction dataflow, the two rounding modes, permitted source commutation,
and the anti-aliasing facts needed when the compiler updates an input interval
in place.

The semantics below is a repository model of those two SASS instructions.  It
reuses the already proved binary64 directed-rounding model and proves that a
validated slice refines outward real-interval addition.  It is not a formal
semantics of the NVIDIA SASS encoding, a proof that `ptxas` emitted the decoded
instructions, or a driver/hardware conformance theorem.  Those boundaries are
kept explicit by the artifact certificate in `FusedLargeQAddbackSlice`.
-/

set_option autoImplicit false

namespace SparkInterval.SASS.SM90

open SparkInterval
open SparkInterval.PTX

/-- Base register named by a double-precision SASS arithmetic instruction. -/
abbrev DRegister := Nat

/-- The only SASS rounding modes admitted by this first slice. -/
inductive DAddRounding where
  | rm
  | rp
  deriving Repr, DecidableEq, BEq

namespace DAddRounding

/-- Translation into the existing formal directed-rounding model. -/
def toDirected : DAddRounding -> DirectedRounding
  | .rm => .down
  | .rp => .up

def mnemonic : DAddRounding -> String
  | .rm => "DADD.RM"
  | .rp => "DADD.RP"

end DAddRounding

/-- Decoded restricted SASS instruction.  `offset` is artifact identity, not
part of the arithmetic semantics.  Predication, negated operands, immediates,
reuse flags, and every opcode other than `DADD.RM/RP` are intentionally absent
from this type, so an extractor must reject them rather than erase them. -/
structure DAddInstruction where
  offset : String
  rounding : DAddRounding
  destination : DRegister
  left : DRegister
  right : DRegister
  deriving Repr, DecidableEq, BEq

namespace DAddInstruction

/-- Canonical text placed in the compact translation certificate. -/
def render (instruction : DAddInstruction) : String :=
  "/*" ++ instruction.offset ++ "*/ " ++ instruction.rounding.mnemonic ++
    " R" ++ toString instruction.destination ++ ", R" ++
    toString instruction.left ++ ", R" ++ toString instruction.right ++ " ;"

end DAddInstruction

/-- A pair of registers interpreted as lower and upper interval endpoints. -/
structure IntervalLayout where
  lo : DRegister
  hi : DRegister
  deriving Repr, DecidableEq, BEq

/-- Complete symbolic certificate for one in-place real-interval addition.

The Boolean commutation flags make the validator reusable across harmless
compiler operand reordering while retaining an exact operand-level check. -/
structure AddSlice where
  lowerOffset : String
  upperOffset : String
  instructions : List DAddInstruction
  left : IntervalLayout
  right : IntervalLayout
  result : IntervalLayout
  lowerOperandsSwapped : Bool := false
  upperOperandsSwapped : Bool := false
  deriving Repr, DecidableEq, BEq

namespace AddSlice

private def operands (swapped : Bool) (left right : DRegister) :
    DRegister × DRegister :=
  if swapped then (right, left) else (left, right)

/-- Exact two-instruction lowering described by the register layouts and
commutation flags. -/
def expectedInstructions (slice : AddSlice) : List DAddInstruction :=
  let lower := operands slice.lowerOperandsSwapped slice.left.lo slice.right.lo
  let upper := operands slice.upperOperandsSwapped slice.left.hi slice.right.hi
  [{ offset := slice.lowerOffset
     rounding := .rm
     destination := slice.result.lo
     left := lower.1
     right := lower.2 },
   { offset := slice.upperOffset
     rounding := .rp
     destination := slice.result.hi
     left := upper.1
     right := upper.2 }]

/-- Pure structural condition needed by the arithmetic refinement theorem.

The first result may overwrite a lower input, as in the production cubin.  It
must not overwrite either upper operand before the second instruction, and the
second result must not overwrite the retained lower result. -/
def WellFormed (slice : AddSlice) : Prop :=
  slice.instructions = slice.expectedInstructions ∧
    slice.result.lo ≠ slice.result.hi ∧
    slice.result.lo ≠ slice.left.hi ∧
    slice.result.lo ≠ slice.right.hi

instance instDecidableWellFormed (slice : AddSlice) : Decidable slice.WellFormed := by
  unfold WellFormed
  infer_instance

/-- Executable operand-sensitive validator. -/
def check (slice : AddSlice) : Bool :=
  decide (slice.instructions = slice.expectedInstructions) &&
    slice.result.lo != slice.result.hi &&
    slice.result.lo != slice.left.hi &&
    slice.result.lo != slice.right.hi

theorem check_sound {slice : AddSlice} (hcheck : slice.check = true) :
    slice.WellFormed := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq, bne_iff_ne] at hcheck
  rcases hcheck with ⟨⟨⟨hcode, hresult⟩, hleftUpper⟩, hrightUpper⟩
  exact ⟨hcode, hresult, hleftUpper, hrightUpper⟩

/-- Canonical rendering of the decoded two-instruction slice. -/
def render (slice : AddSlice) : String :=
  String.intercalate "\n" (slice.instructions.map DAddInstruction.render) ++ "\n"

/-- Partial register file for the two-instruction arithmetic model. -/
abbrev RegisterFile := Nat -> Option F64Value

def write (registers : RegisterFile) (destination : DRegister)
    (value : F64Value) : RegisterFile :=
  fun register => if register = destination then some value else registers register

/-- Semantics of one admitted SM90 `DADD` instruction.

Nonfinite operands fail closed, exactly as in the finite-only arithmetic model
used by the formal PTX layer. -/
noncomputable def executeInstruction (instruction : DAddInstruction)
    (registers : RegisterFile) : Option RegisterFile := do
  let left <- registers instruction.left
  let right <- registers instruction.right
  let result <- directedBinary .add instruction.rounding.toDirected left right
  pure (write registers instruction.destination result)

noncomputable def executeList : List DAddInstruction -> RegisterFile ->
    Option RegisterFile
  | [], registers => some registers
  | instruction :: rest, registers => do
      let registers <- executeInstruction instruction registers
      executeList rest registers

/-- Execute exactly the decoded slice. -/
noncomputable def execute (slice : AddSlice) (registers : RegisterFile) :
    Option RegisterFile :=
  executeList slice.instructions registers

/-- The observable arithmetic claim proved for a validated slice. -/
def ProducesAdd (slice : AddSlice) (registers : RegisterFile)
    (left right : RealInterval) : Prop :=
  registers slice.result.lo = some (addFragmentResult left right).lo ∧
    registers slice.result.hi = some (addFragmentResult left right).hi

/-- Semantic refinement of the restricted post-compilation slice. -/
def RefinesIntervalAdd (slice : AddSlice) : Prop :=
  ∀ (registers : RegisterFile) (left right : RealInterval),
    registers slice.left.lo = some (.finite left.lo) ->
    registers slice.left.hi = some (.finite left.hi) ->
    registers slice.right.lo = some (.finite right.lo) ->
    registers slice.right.hi = some (.finite right.hi) ->
    ∃ final,
      slice.execute registers = some final ∧
      slice.ProducesAdd final left right

/-- Main Lean translation theorem: every structurally validated restricted
SASS slice implements the same outward binary64 interval addition already used
by the formal arithmetic layer. -/
theorem wellFormed_refinesIntervalAdd {slice : AddSlice}
    (hwell : slice.WellFormed) : slice.RefinesIntervalAdd := by
  rcases hwell with ⟨hcode, hresult, hleftUpper, hrightUpper⟩
  intro registers left right hleftLo hleftHi hrightLo hrightHi
  unfold execute
  rw [hcode]
  cases hlower : slice.lowerOperandsSwapped <;>
    cases hupper : slice.upperOperandsSwapped
  all_goals
    let final := write
      (write registers slice.result.lo
        (F64Value.ofExt (Binary64Rounding.roundDown (left.lo + right.lo))))
      slice.result.hi
        (F64Value.ofExt (Binary64Rounding.roundUp (left.hi + right.hi)))
    refine ⟨final, ?_, ?_⟩
  all_goals
    simp [expectedInstructions, operands, hlower, hupper, executeList,
      executeInstruction, write, final, hleftLo, hleftHi, hrightLo, hrightHi,
      DAddRounding.toDirected, hresult, Ne.symm hleftUpper,
      Ne.symm hrightUpper, directedBinary, exactBinary,
      add_comm, ProducesAdd, addFragmentResult]

/-- Boolean-checker form of the semantic translation theorem. -/
theorem check_refinesIntervalAdd {slice : AddSlice}
    (hcheck : slice.check = true) : slice.RefinesIntervalAdd :=
  wellFormed_refinesIntervalAdd (check_sound hcheck)

/-- A successful restricted execution therefore encloses every exact sum of
points selected from the input intervals. -/
theorem producesAdd_contains {slice : AddSlice} {registers : RegisterFile}
    {left right : RealInterval} {x y : Real}
    (hproduces : slice.ProducesAdd registers left right)
    (hx : left.Contains x) (hy : right.Contains y) :
    ∃ output : F64Interval,
      registers slice.result.lo = some output.lo ∧
      registers slice.result.hi = some output.hi ∧
      output.ContainsReal (x + y) := by
  refine ⟨addFragmentResult left right, hproduces.1, hproduces.2, ?_⟩
  exact addFragmentResult_contains hx hy

end AddSlice

end SparkInterval.SASS.SM90
