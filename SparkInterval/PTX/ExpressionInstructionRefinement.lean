import SparkInterval.PTX.CodeComposition
import SparkInterval.PTX.InstructionRefinement

/-!
# Leaf and unary instruction refinement

These lemmas cover the non-arithmetic expression fragments emitted by the
polynomial compiler.  Together with the guarded binary refinements, they give
an expression-level proof access to constants, row loads, and negation without
unfolding the whole generated module.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The exact pair of `mov.b64` instructions used for an interval constant
loads the two decoded endpoints into its fresh result registers. -/
theorem executeConstInstructions
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (result : IntervalRegisters)
    (loBits hiBits : Nat) (lo hi : F64Value)
    (hlo : decodeF64Bits loBits = some lo)
    (hhi : decodeF64Bits hiBits = some hi)
    (hresult : result.lo.index ≠ result.hi.index) :
    ∃ final,
      executeCode module parameters thread
          [.movF64Bits result.lo loBits, .movF64Bits result.hi hiBits] state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result { lo, hi } := by
  let afterLo := (state.writeF64 result.lo lo).advance
  let final := (afterLo.writeF64 result.hi hi).advance
  refine ⟨final, ?_, ?_⟩
  · simp [executeCode, executeInstruction, hlo, hhi, afterLo, final]
  · constructor
    · simp [final, afterLo, MachineState.advance, MachineState.writeF64,
        RegisterFile.read, RegisterFile.write, hresult]
    · simp [final, MachineState.advance, MachineState.writeF64]

/-- The exact two global loads used for a variable read the row-layout cells
selected by their base register and byte offsets. -/
theorem executeLoadIntervalInstructions
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (result : IntervalRegisters) (base : Reg .u64)
    (baseAddress loOffset hiOffset : Nat) (lo hi : F64Value)
    (hbase : state.u64.read base.index = some baseAddress)
    (hlo : state.memory.loadF64 (globalAddress baseAddress loOffset) = some lo)
    (hhi : state.memory.loadF64 (globalAddress baseAddress hiOffset) = some hi)
    (hresult : result.lo.index ≠ result.hi.index) :
    ∃ final,
      executeCode module parameters thread
          [.loadGlobalF64 result.lo base loOffset,
           .loadGlobalF64 result.hi base hiOffset] state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result { lo, hi } := by
  let afterLo := (state.writeF64 result.lo lo).advance
  let final := (afterLo.writeF64 result.hi hi).advance
  refine ⟨final, ?_, ?_⟩
  · simp [executeCode, executeInstruction, hbase, hlo, hhi, afterLo, final,
      MachineState.advance, MachineState.writeF64]
  · constructor
    · simp [final, afterLo, MachineState.advance, MachineState.writeF64,
        RegisterFile.read, RegisterFile.write, hresult]
    · simp [final, MachineState.advance, MachineState.writeF64]

/-- The compiler's two sign-bit xor instructions reverse and negate an
interval's endpoints.  Fresh allocation supplies the two non-aliasing facts. -/
theorem executeNegInstructions
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (result argument : IntervalRegisters)
    (argumentLo argumentHi : F64Value)
    (hlo : state.f64.read argument.lo.index = some argumentLo)
    (hhi : state.f64.read argument.hi.index = some argumentHi)
    (hresult : result.lo.index ≠ result.hi.index)
    (hargumentLo : result.lo.index ≠ argument.lo.index) :
    ∃ final,
      executeCode module parameters thread
          [.xorF64Sign result.lo argument.hi,
           .xorF64Sign result.hi argument.lo] state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result
        { lo := argumentHi.negate, hi := argumentLo.negate } := by
  unfold RegisterFile.read at hlo hhi
  let afterLo := (state.writeF64 result.lo argumentHi.negate).advance
  let final := (afterLo.writeF64 result.hi argumentLo.negate).advance
  refine ⟨final, ?_, ?_⟩
  · simp [executeCode, executeInstruction, hlo, hhi, afterLo, final,
      MachineState.advance, MachineState.writeF64, RegisterFile.read,
      RegisterFile.write,
      Ne.symm hargumentLo]
  · constructor
    · simp [final, afterLo, MachineState.advance, MachineState.writeF64,
        RegisterFile.read, RegisterFile.write, hresult]
    · simp [final, MachineState.advance, MachineState.writeF64]

end SparkInterval.PTX
