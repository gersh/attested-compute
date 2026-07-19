import SparkInterval.FPIntervalSound
import SparkInterval.PTX.Generator

/-!
# Arithmetic semantics for the generated PTX subset

This file gives a small mathematical semantics to the pure floating-point
instructions used by the Phase 5 generator.  It intentionally does not model
threads, memory, predicates, branches, or CUDA module loading.  Directed
arithmetic is defined only on finite operands, matching the path that remains
after the generator's finite guards.  A rounded result may be infinite.

The register semantics is in static-single-assignment form: a write succeeds
only when its destination is unbound.  The generator allocates fresh registers,
and this convention makes accidental register aliasing fail closed in this
first formal slice.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

open SparkInterval

/-- A non-NaN numeric binary64 result.  The finite case records its exact real
value; signed zero is deliberately identified in this numeric semantics. -/
inductive F64Value where
  | negInf
  | finite (value : ℝ)
  | posInf

namespace F64Value

private theorem coe_min_real (left right : ℝ) :
    ((min left right : ℝ) : EReal) = min (left : EReal) (right : EReal) := by
  rcases le_total left right with h | h
  · rw [min_eq_left h, min_eq_left (EReal.coe_le_coe_iff.mpr h)]
  · rw [min_eq_right h, min_eq_right (EReal.coe_le_coe_iff.mpr h)]

private theorem coe_max_real (left right : ℝ) :
    ((max left right : ℝ) : EReal) = max (left : EReal) (right : EReal) := by
  rcases le_total left right with h | h
  · rw [max_eq_right h, max_eq_right (EReal.coe_le_coe_iff.mpr h)]
  · rw [max_eq_left h, max_eq_left (EReal.coe_le_coe_iff.mpr h)]

/-- Interpret a numeric PTX value in the extended real line. -/
noncomputable def toEReal : F64Value → EReal
  | .negInf => ⊥
  | .finite value => value
  | .posInf => ⊤

/-- Forget the binary64 representability witness carried by `ExtBinary64`. -/
noncomputable def ofExt : ExtBinary64 → F64Value
  | .negInf => .negInf
  | .finite value => .finite value.1
  | .posInf => .posInf

@[simp] theorem ofExt_toEReal (value : ExtBinary64) :
    (ofExt value).toEReal = value.toEReal := by
  cases value <;> rfl

/-- Numeric semantics of toggling the binary64 sign bit. -/
noncomputable def negate : F64Value → F64Value
  | .negInf => .posInf
  | .finite value => .finite (-value)
  | .posInf => .negInf

@[simp] theorem negate_toEReal (value : F64Value) :
    value.negate.toEReal = -value.toEReal := by
  cases value <;> simp [negate, toEReal]

/-- IEEE numeric minimum on non-NaN values. -/
noncomputable def minimum : F64Value → F64Value → F64Value
  | .negInf, _ => .negInf
  | _, .negInf => .negInf
  | .posInf, right => right
  | left, .posInf => left
  | .finite left, .finite right => .finite (min left right)

/-- IEEE numeric maximum on non-NaN values. -/
noncomputable def maximum : F64Value → F64Value → F64Value
  | .posInf, _ => .posInf
  | _, .posInf => .posInf
  | .negInf, right => right
  | left, .negInf => left
  | .finite left, .finite right => .finite (max left right)

@[simp] theorem minimum_toEReal (left right : F64Value) :
    (minimum left right).toEReal = min left.toEReal right.toEReal := by
  cases left <;> cases right <;> simp [minimum, toEReal, coe_min_real]

@[simp] theorem maximum_toEReal (left right : F64Value) :
    (maximum left right).toEReal = max left.toEReal right.toEReal := by
  cases left <;> cases right <;> simp [maximum, toEReal, coe_max_real]

end F64Value

/-- Decode a raw bit move.  Finite values and infinities succeed; NaNs fail. -/
noncomputable def decodeF64Bits (raw : Nat) : Option F64Value :=
  let bits : Binary64Bits := BitVec.ofNat 64 raw
  if hfinite : bits.IsFinite then
    some (.finite (Binary64Finite.toReal ⟨bits, hfinite⟩))
  else if _hinfinite : bits.IsInfinite then
    if bits.signBit then some .negInf else some .posInf
  else
    none

theorem decodeF64Bits_of_finite (raw : Nat)
    (hfinite : Binary64Bits.IsFinite (BitVec.ofNat 64 raw)) :
    decodeF64Bits raw = some (.finite
      (Binary64Finite.toReal ⟨BitVec.ofNat 64 raw, hfinite⟩)) := by
  simp [decodeF64Bits, hfinite]

theorem decodeF64Bits_of_infinite (raw : Nat)
    (hinfinite : Binary64Bits.IsInfinite (BitVec.ofNat 64 raw)) :
    decodeF64Bits raw =
      if Binary64Bits.signBit (BitVec.ofNat 64 raw) then
        some .negInf
      else
        some .posInf := by
  let bits : Binary64Bits := BitVec.ofNat 64 raw
  have hnotFinite : ¬bits.IsFinite :=
    (Binary64Bits.not_finite_iff_infinite_or_nan bits).2 (Or.inl hinfinite)
  simp [decodeF64Bits, bits, hnotFinite, hinfinite]

theorem decodeF64Bits_of_nan (raw : Nat)
    (hnan : Binary64Bits.IsNaN (BitVec.ofNat 64 raw)) :
    decodeF64Bits raw = none := by
  let bits : Binary64Bits := BitVec.ofNat 64 raw
  have hnotFinite : ¬bits.IsFinite :=
    (Binary64Bits.not_finite_iff_infinite_or_nan bits).2 (Or.inr hnan)
  have hnotInfinite : ¬bits.IsInfinite := by
    intro hinfinite
    exact hnan.2 hinfinite.2
  simp [decodeF64Bits, bits, hnotFinite, hnotInfinite]

/-- The exact real operation selected by a typed PTX arithmetic opcode. -/
def exactBinary (op : F64BinaryOp) (left right : ℝ) : ℝ :=
  match op with
  | .add => left + right
  | .sub => left - right
  | .mul => left * right

/-- Mathematical semantics of a directed binary64 operation on finite
operands.  It is deliberately undefined on infinities because the generated
finite guards divert those rows before reaching an arithmetic fragment. -/
noncomputable def directedBinary (op : F64BinaryOp)
    (rounding : DirectedRounding) : F64Value → F64Value → Option F64Value
  | .finite left, .finite right =>
      let exact := exactBinary op left right
      some <| F64Value.ofExt <| match rounding with
        | .down => Binary64Rounding.roundDown exact
        | .up => Binary64Rounding.roundUp exact
  | _, _ => none

theorem directedBinary_down_le (op : F64BinaryOp) (left right : ℝ) :
    ∃ result, directedBinary op .down (.finite left) (.finite right) = some result ∧
      result.toEReal ≤ (exactBinary op left right : EReal) := by
  refine ⟨F64Value.ofExt (Binary64Rounding.roundDown
    (exactBinary op left right)), rfl, ?_⟩
  simpa using Binary64Rounding.roundDown_le (exactBinary op left right)

theorem le_directedBinary_up (op : F64BinaryOp) (left right : ℝ) :
    ∃ result, directedBinary op .up (.finite left) (.finite right) = some result ∧
      (exactBinary op left right : EReal) ≤ result.toEReal := by
  refine ⟨F64Value.ofExt (Binary64Rounding.roundUp
    (exactBinary op left right)), rfl, ?_⟩
  simpa using Binary64Rounding.le_roundUp (exactBinary op left right)

/-- A partial f64 register file.  `none` means that an SSA destination is still
fresh; `some` is a bound numeric value. -/
abbrev F64RegisterFile := Nat → Option F64Value

def readF64 (registers : F64RegisterFile) (reg : Reg .f64) : Option F64Value :=
  registers reg.index

def writeFreshF64 (registers : F64RegisterFile) (reg : Reg .f64)
    (value : F64Value) : Option F64RegisterFile :=
  match registers reg.index with
  | some _ => none
  | none => some fun index =>
      if index = reg.index then some value else registers index

/-- One-step semantics for the pure f64 instruction subset.  Every other typed
PTX instruction is outside this semantics and returns `none`. -/
noncomputable def executeF64Instruction (instruction : Instruction)
    (registers : F64RegisterFile) : Option F64RegisterFile :=
  match instruction with
  | .movF64Bits dst bits => do
      let value ← decodeF64Bits bits
      writeFreshF64 registers dst value
  | .xorF64Sign dst source => do
      let value ← readF64 registers source
      writeFreshF64 registers dst value.negate
  | .binaryF64 op rounding dst left right => do
      let leftValue ← readF64 registers left
      let rightValue ← readF64 registers right
      let result ← directedBinary op rounding leftValue rightValue
      writeFreshF64 registers dst result
  | .minimumF64 dst left right => do
      let leftValue ← readF64 registers left
      let rightValue ← readF64 registers right
      writeFreshF64 registers dst (F64Value.minimum leftValue rightValue)
  | .maximumF64 dst left right => do
      let leftValue ← readF64 registers left
      let rightValue ← readF64 registers right
      writeFreshF64 registers dst (F64Value.maximum leftValue rightValue)
  | _ => none

noncomputable def executeF64List : List Instruction → F64RegisterFile →
    Option F64RegisterFile
  | [], registers => some registers
  | instruction :: rest, registers => do
      let registers ← executeF64Instruction instruction registers
      executeF64List rest registers

/-- Execute a generated pure arithmetic fragment. -/
noncomputable def executeF64Fragment (instructions : Array Instruction)
    (registers : F64RegisterFile) : Option F64RegisterFile :=
  executeF64List instructions.toList registers

/-- Observe two result registers as a numeric interval. -/
structure F64Interval where
  lo : F64Value
  hi : F64Value

namespace F64Interval

def ContainsReal (interval : F64Interval) (value : ℝ) : Prop :=
  interval.lo.toEReal ≤ (value : EReal) ∧
    (value : EReal) ≤ interval.hi.toEReal

end F64Interval

def observeInterval (registers : F64RegisterFile)
    (result : IntervalRegisters) : Option F64Interval := do
  let lo ← readF64 registers result.lo
  let hi ← readF64 registers result.hi
  pure { lo, hi }

/-- The numeric result prescribed by the generated addition fragment. -/
noncomputable def addFragmentResult (left right : RealInterval) : F64Interval := {
  lo := F64Value.ofExt <| Binary64Rounding.roundDown (left.lo + right.lo)
  hi := F64Value.ofExt <| Binary64Rounding.roundUp (left.hi + right.hi)
}

/-- The numeric result prescribed by the generated subtraction fragment. -/
noncomputable def subFragmentResult (left right : RealInterval) : F64Interval := {
  lo := F64Value.ofExt <| Binary64Rounding.roundDown (left.lo - right.hi)
  hi := F64Value.ofExt <| Binary64Rounding.roundUp (left.hi - right.lo)
}

/-- The numeric result prescribed by the generated multiplication fragment:
round all four corners outward, then reduce them with `min`/`max`. -/
noncomputable def mulFragmentResult (left right : RealInterval) : F64Interval :=
  let d00 := F64Value.ofExt <| Binary64Rounding.roundDown (left.lo * right.lo)
  let d01 := F64Value.ofExt <| Binary64Rounding.roundDown (left.lo * right.hi)
  let d10 := F64Value.ofExt <| Binary64Rounding.roundDown (left.hi * right.lo)
  let d11 := F64Value.ofExt <| Binary64Rounding.roundDown (left.hi * right.hi)
  let u00 := F64Value.ofExt <| Binary64Rounding.roundUp (left.lo * right.lo)
  let u01 := F64Value.ofExt <| Binary64Rounding.roundUp (left.lo * right.hi)
  let u10 := F64Value.ofExt <| Binary64Rounding.roundUp (left.hi * right.lo)
  let u11 := F64Value.ofExt <| Binary64Rounding.roundUp (left.hi * right.hi)
  {
    lo := F64Value.minimum (F64Value.minimum d00 d01)
      (F64Value.minimum d10 d11)
    hi := F64Value.maximum (F64Value.maximum u00 u01)
      (F64Value.maximum u10 u11)
  }

/-- The generated addition fragment encloses every exact sum selected from its
two input intervals. -/
theorem addFragmentResult_contains {left right : RealInterval} {x y : ℝ}
    (hx : left.Contains x) (hy : right.Contains y) :
    (addFragmentResult left right).ContainsReal (x + y) := by
  simpa only [addFragmentResult, F64Interval.ContainsReal,
    F64Value.ofExt_toEReal, FPInterval.ContainsReal, FPInterval.quantize,
    RealInterval.add] using
    (FPInterval.quantize_contains (RealInterval.add_contains hx hy))

/-- The generated subtraction fragment encloses every exact difference. -/
theorem subFragmentResult_contains {left right : RealInterval} {x y : ℝ}
    (hx : left.Contains x) (hy : right.Contains y) :
    (subFragmentResult left right).ContainsReal (x - y) := by
  simpa only [subFragmentResult, F64Interval.ContainsReal,
    F64Value.ofExt_toEReal, FPInterval.ContainsReal, FPInterval.quantize,
    RealInterval.sub] using
    (FPInterval.quantize_contains (RealInterval.sub_contains hx hy))

/-- The per-corner rounded multiplication fragment encloses every exact
product.  This uses the Phase 2 exact four-corner containment theorem and the
two directed-rounding inequalities. -/
theorem mulFragmentResult_contains {left right : RealInterval} {x y : ℝ}
    (hx : left.Contains x) (hy : right.Contains y) :
    (mulFragmentResult left right).ContainsReal (x * y) := by
  have hExact := RealInterval.mul_contains hx hy
  constructor
  · calc
      (mulFragmentResult left right).lo.toEReal =
          min
            (min
              (Binary64Rounding.roundDown (left.lo * right.lo)).toEReal
              (Binary64Rounding.roundDown (left.lo * right.hi)).toEReal)
            (min
              (Binary64Rounding.roundDown (left.hi * right.lo)).toEReal
              (Binary64Rounding.roundDown (left.hi * right.hi)).toEReal) := by
                simp [mulFragmentResult]
      _ ≤
          min
            (min ((left.lo * right.lo : ℝ) : EReal)
              ((left.lo * right.hi : ℝ) : EReal))
            (min ((left.hi * right.lo : ℝ) : EReal)
              ((left.hi * right.hi : ℝ) : EReal)) :=
        min_le_min
          (min_le_min
            (Binary64Rounding.roundDown_le _)
            (Binary64Rounding.roundDown_le _))
          (min_le_min
            (Binary64Rounding.roundDown_le _)
            (Binary64Rounding.roundDown_le _))
      _ ≤ ((x * y : ℝ) : EReal) := by
        exact EReal.coe_le_coe_iff.mpr hExact.1
  · calc
      ((x * y : ℝ) : EReal) ≤
          max
            (max ((left.lo * right.lo : ℝ) : EReal)
              ((left.lo * right.hi : ℝ) : EReal))
            (max ((left.hi * right.lo : ℝ) : EReal)
              ((left.hi * right.hi : ℝ) : EReal)) := by
        exact EReal.coe_le_coe_iff.mpr hExact.2
      _ ≤
          max
            (max
              (Binary64Rounding.roundUp (left.lo * right.lo)).toEReal
              (Binary64Rounding.roundUp (left.lo * right.hi)).toEReal)
            (max
              (Binary64Rounding.roundUp (left.hi * right.lo)).toEReal
              (Binary64Rounding.roundUp (left.hi * right.hi)).toEReal) :=
        max_le_max
          (max_le_max
            (Binary64Rounding.le_roundUp _)
            (Binary64Rounding.le_roundUp _))
          (max_le_max
            (Binary64Rounding.le_roundUp _)
            (Binary64Rounding.le_roundUp _))
      _ = (mulFragmentResult left right).hi.toEReal := by
        simp [mulFragmentResult]

/- Canonical register layouts are alpha-representatives of the fragment
schemas.  The public fragment constructors are parametric in register names;
these layouts make the operational regression theorems compact. -/
def canonicalLeft : IntervalRegisters := { lo := ⟨0⟩, hi := ⟨1⟩ }
def canonicalRight : IntervalRegisters := { lo := ⟨2⟩, hi := ⟨3⟩ }
def canonicalAddSubResult : IntervalRegisters := { lo := ⟨4⟩, hi := ⟨5⟩ }
def canonicalMulResult : IntervalRegisters := { lo := ⟨16⟩, hi := ⟨17⟩ }

def canonicalMulTemporaries : MulArithmeticTemporaries := {
  down0 := ⟨4⟩, down1 := ⟨5⟩, down2 := ⟨6⟩, down3 := ⟨7⟩,
  up0 := ⟨8⟩, up1 := ⟨9⟩, up2 := ⟨10⟩, up3 := ⟨11⟩,
  down01 := ⟨12⟩, down23 := ⟨13⟩, up01 := ⟨14⟩, up23 := ⟨15⟩
}

noncomputable def canonicalInputRegisters (left right : RealInterval) :
    F64RegisterFile
  | 0 => some (.finite left.lo)
  | 1 => some (.finite left.hi)
  | 2 => some (.finite right.lo)
  | 3 => some (.finite right.hi)
  | _ => none

/-- Executing the exact addition instruction array used by the generator
produces its mathematical fragment result on a canonical fresh layout. -/
theorem executeCanonicalAdd (left right : RealInterval) :
    (do
      let registers ← executeF64Fragment
        (addArithmeticFragment canonicalAddSubResult canonicalLeft canonicalRight)
        (canonicalInputRegisters left right)
      observeInterval registers canonicalAddSubResult) =
      some (addFragmentResult left right) := by
  simp [executeF64Fragment, executeF64List, addArithmeticFragment,
    executeF64Instruction, canonicalInputRegisters, canonicalAddSubResult,
    canonicalLeft, canonicalRight, readF64, writeFreshF64, directedBinary,
    exactBinary, addFragmentResult, observeInterval]

/-- Executing the exact subtraction instruction array produces its specified
mathematical result. -/
theorem executeCanonicalSub (left right : RealInterval) :
    (do
      let registers ← executeF64Fragment
        (subArithmeticFragment canonicalAddSubResult canonicalLeft canonicalRight)
        (canonicalInputRegisters left right)
      observeInterval registers canonicalAddSubResult) =
      some (subFragmentResult left right) := by
  simp [executeF64Fragment, executeF64List, subArithmeticFragment,
    executeF64Instruction, canonicalInputRegisters, canonicalAddSubResult,
    canonicalLeft, canonicalRight, readF64, writeFreshF64, directedBinary,
    exactBinary, subFragmentResult, observeInterval]

/-- Executing the exact fourteen-instruction multiplication array produces
the per-corner rounded fragment result. -/
theorem executeCanonicalMul (left right : RealInterval) :
    (do
      let registers ← executeF64Fragment
        (mulArithmeticFragment canonicalMulResult canonicalLeft canonicalRight
          canonicalMulTemporaries)
        (canonicalInputRegisters left right)
      observeInterval registers canonicalMulResult) =
      some (mulFragmentResult left right) := by
  simp [executeF64Fragment, executeF64List, mulArithmeticFragment,
    executeF64Instruction, canonicalInputRegisters, canonicalMulResult,
    canonicalMulTemporaries, canonicalLeft, canonicalRight, readF64,
    writeFreshF64, directedBinary, exactBinary, mulFragmentResult,
    observeInterval]

/-- Operational addition corollary: the exact generated fragment computes an
interval enclosing the selected exact sum. -/
theorem executeCanonicalAdd_contains {left right : RealInterval} {x y : ℝ}
    (hx : left.Contains x) (hy : right.Contains y) :
    ∃ result,
      (do
        let registers ← executeF64Fragment
          (addArithmeticFragment canonicalAddSubResult canonicalLeft canonicalRight)
          (canonicalInputRegisters left right)
        observeInterval registers canonicalAddSubResult) = some result ∧
      result.ContainsReal (x + y) := by
  exact ⟨addFragmentResult left right, executeCanonicalAdd left right,
    addFragmentResult_contains hx hy⟩

/-- Operational subtraction corollary for the exact generated fragment. -/
theorem executeCanonicalSub_contains {left right : RealInterval} {x y : ℝ}
    (hx : left.Contains x) (hy : right.Contains y) :
    ∃ result,
      (do
        let registers ← executeF64Fragment
          (subArithmeticFragment canonicalAddSubResult canonicalLeft canonicalRight)
          (canonicalInputRegisters left right)
        observeInterval registers canonicalAddSubResult) = some result ∧
      result.ContainsReal (x - y) := by
  exact ⟨subFragmentResult left right, executeCanonicalSub left right,
    subFragmentResult_contains hx hy⟩

/-- Operational multiplication corollary for the exact generated fragment. -/
theorem executeCanonicalMul_contains {left right : RealInterval} {x y : ℝ}
    (hx : left.Contains x) (hy : right.Contains y) :
    ∃ result,
      (do
        let registers ← executeF64Fragment
          (mulArithmeticFragment canonicalMulResult canonicalLeft canonicalRight
            canonicalMulTemporaries)
          (canonicalInputRegisters left right)
        observeInterval registers canonicalMulResult) = some result ∧
      result.ContainsReal (x * y) := by
  exact ⟨mulFragmentResult left right, executeCanonicalMul left right,
    mulFragmentResult_contains hx hy⟩

end SparkInterval.PTX
