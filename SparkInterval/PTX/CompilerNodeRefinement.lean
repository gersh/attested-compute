import SparkInterval.PTX.CompilerDataflow
import SparkInterval.PTX.InstructionRefinement

/-!
# Concrete compiler-node arithmetic refinement

This layer instantiates the operand-sensitive instruction semantics with the
actual registers selected by the production compiler.  It deliberately covers
only the arithmetic fragments: execution of the preceding finite guards and
composition across a complete expression belong to the next refinement layer.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The proof-facing destination list attached to the production allocation is
definitionally the destination list required by the multiplication instruction
refinement theorem. -/
theorem compileMulAllocation_destinationIndices_eq
    (left right : IntervalRegisters) (builder : Builder) :
    (compileMulAllocation left right builder).destinationIndices =
      mulArithmeticDestinationIndices
        (compileMulAllocation left right builder).result
        (compileMulAllocation left right builder).temporaries := by
  rfl

/-- Execute the exact addition arithmetic fragment with the result registers
selected by `compileAdd`.

The `Below` premises are facts about production allocation order.  They
discharge every non-aliasing premise of `executeAddArithmeticFragment`; the
remaining premises state the finite values currently held by the operands. -/
theorem executeCompileAddArithmeticFragment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (left right : IntervalRegisters) (builder : Builder)
    (leftLo leftHi rightLo rightHi : ℝ)
    (hleftBelow : left.Below builder.nextF64)
    (hrightBelow : right.Below builder.nextF64)
    (hleftLo : state.f64.read left.lo.index = some (.finite leftLo))
    (hleftHi : state.f64.read left.hi.index = some (.finite leftHi))
    (hrightLo : state.f64.read right.lo.index = some (.finite rightLo))
    (hrightHi : state.f64.read right.hi.index = some (.finite rightHi)) :
    let result := (compileAdd left right builder).1
    ∃ final,
      executeCode module parameters thread
          (addArithmeticFragment result left right).toList state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result
        (roundedBinaryInterval .add leftLo leftHi rightLo rightHi) := by
  let result := (compileAdd left right builder).1
  change ∃ final,
    executeCode module parameters thread
        (addArithmeticFragment result left right).toList state =
      some { control := .fallthrough, state := final } ∧
    final.RegistersContain result
      (roundedBinaryInterval .add leftLo leftHi rightLo rightHi)
  rcases compileAdd_result_fresh left right builder hleftBelow hrightBelow with
    ⟨hresult, _, hleftUpper, _, hrightUpper⟩
  exact executeAddArithmeticFragment module parameters thread state
    result left right leftLo leftHi rightLo rightHi
    hleftLo hleftHi hrightLo hrightHi hresult hleftUpper hrightUpper

/-- Execute the exact subtraction arithmetic fragment with the result
registers selected by `compileSub`. -/
theorem executeCompileSubArithmeticFragment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (left right : IntervalRegisters) (builder : Builder)
    (leftLo leftHi rightLo rightHi : ℝ)
    (hleftBelow : left.Below builder.nextF64)
    (hrightBelow : right.Below builder.nextF64)
    (hleftLo : state.f64.read left.lo.index = some (.finite leftLo))
    (hleftHi : state.f64.read left.hi.index = some (.finite leftHi))
    (hrightLo : state.f64.read right.lo.index = some (.finite rightLo))
    (hrightHi : state.f64.read right.hi.index = some (.finite rightHi)) :
    let result := (compileSub left right builder).1
    ∃ final,
      executeCode module parameters thread
          (subArithmeticFragment result left right).toList state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result
        (roundedBinaryInterval .sub leftLo leftHi rightLo rightHi) := by
  let result := (compileSub left right builder).1
  change ∃ final,
    executeCode module parameters thread
        (subArithmeticFragment result left right).toList state =
      some { control := .fallthrough, state := final } ∧
    final.RegistersContain result
      (roundedBinaryInterval .sub leftLo leftHi rightLo rightHi)
  rcases compileSub_result_fresh left right builder hleftBelow hrightBelow with
    ⟨hresult, _, hleftUpper, hrightLower, _⟩
  exact executeSubArithmeticFragment module parameters thread state
    result left right leftLo leftHi rightLo rightHi
    hleftLo hleftHi hrightLo hrightHi hresult hleftUpper hrightLower

/-- Execute the exact fourteen-instruction multiplication fragment using the
temporaries and result registers selected inside the production `compileMul`.

This theorem is the formal bridge from compiler allocation to the generic
instruction-level multiplication result. -/
theorem executeCompileMulArithmeticFragment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (left right : IntervalRegisters) (builder : Builder)
    (leftLo leftHi rightLo rightHi : ℝ)
    (hleftBelow : left.Below builder.nextF64)
    (hrightBelow : right.Below builder.nextF64)
    (hleftLo : state.f64.read left.lo.index = some (.finite leftLo))
    (hleftHi : state.f64.read left.hi.index = some (.finite leftHi))
    (hrightLo : state.f64.read right.lo.index = some (.finite rightLo))
    (hrightHi : state.f64.read right.hi.index = some (.finite rightHi)) :
    let allocation := compileMulAllocation left right builder
    ∃ final,
      executeCode module parameters thread
          (mulArithmeticFragment allocation.result left right
            allocation.temporaries).toList state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain allocation.result
        (roundedBinaryInterval .mul leftLo leftHi rightLo rightHi) := by
  let allocation := compileMulAllocation left right builder
  change ∃ final,
    executeCode module parameters thread
        (mulArithmeticFragment allocation.result left right
          allocation.temporaries).toList state =
      some { control := .fallthrough, state := final } ∧
    final.RegistersContain allocation.result
      (roundedBinaryInterval .mul leftLo leftHi rightLo rightHi)

  have hfresh :=
    compileMul_refinement_freshness left right builder hleftBelow hrightBelow
  have hindices : allocation.destinationIndices =
      mulArithmeticDestinationIndices allocation.result
        allocation.temporaries := by
    exact compileMulAllocation_destinationIndices_eq left right builder
  have hdestinations :
      (mulArithmeticDestinationIndices allocation.result
        allocation.temporaries).Nodup := by
    rw [← hindices]
    exact hfresh.1
  have hleftLoFresh : left.lo.index ∉
      mulArithmeticDestinationIndices allocation.result
        allocation.temporaries := by
    rw [← hindices]
    exact hfresh.2.1
  have hleftHiFresh : left.hi.index ∉
      mulArithmeticDestinationIndices allocation.result
        allocation.temporaries := by
    rw [← hindices]
    exact hfresh.2.2.1
  have hrightLoFresh : right.lo.index ∉
      mulArithmeticDestinationIndices allocation.result
        allocation.temporaries := by
    rw [← hindices]
    exact hfresh.2.2.2.1
  have hrightHiFresh : right.hi.index ∉
      mulArithmeticDestinationIndices allocation.result
        allocation.temporaries := by
    rw [← hindices]
    exact hfresh.2.2.2.2

  exact executeMulArithmeticFragment module parameters thread state
    allocation.result left right allocation.temporaries
    leftLo leftHi rightLo rightHi hleftLo hleftHi hrightLo hrightHi
    hdestinations hleftLoFresh hleftHiFresh hrightLoFresh hrightHiFresh

end SparkInterval.PTX
