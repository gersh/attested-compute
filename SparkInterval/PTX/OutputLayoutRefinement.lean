import SparkInterval.PTX.CompilerOutputRefinement
import SparkInterval.PTX.PrologueRefinement

/-!
# Row-indexed output-layout refinement

This module connects the concrete output base computed by the production
prologue to the public row-indexed `observeOutput` ABI.  It deliberately stops
at the isolated output-record slice: expression compilation and the generated
epilogue are not part of these statements.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- An in-range prologue output base leaves room for every byte of its
24-byte output record without u64 address wrap. -/
theorem prologueOutputBase_record_safe
    (parameters : KernelParameters) (thread : ThreadContext)
    (variableCount : Nat)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX <
      parameters.rowCount) :
    prologueOutputBase parameters thread + 23 < 2 ^ 64 := by
  have hindex := ThreadContext.globalIndex_eq thread hthread
  have hinWrapped : thread.globalIndex < parameters.rowCount := by
    simpa [hindex] using hin
  have hbase := prologueOutputBase_eq_of_safeLayout parameters thread
    variableCount hlayout hinWrapped
  rcases hlayout with ⟨_, _, _, _, _, _, houtputsEnd, _⟩
  rw [hbase]
  omega

/-- The public observer for an in-range row is exactly the direct-base
observer at the address computed by the production prologue. -/
theorem observeOutput_eq_prologueOutputBase
    (memory : GlobalMemory) (parameters : KernelParameters)
    (thread : ThreadContext) (variableCount : Nat)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX <
      parameters.rowCount) :
    observeOutput memory parameters.outputs
        (thread.ctaidX * thread.ntidX + thread.tidX) =
      observeOutput memory (prologueOutputBase parameters thread) 0 := by
  let index := thread.ctaidX * thread.ntidX + thread.tidX
  have hindex : thread.globalIndex = index := by
    simpa [index] using ThreadContext.globalIndex_eq thread hthread
  have hinWrapped : thread.globalIndex < parameters.rowCount := by
    simpa [hindex, index] using hin
  have hbase : prologueOutputBase parameters thread =
      parameters.outputs + index * 24 := by
    simpa [hindex, index] using
      prologueOutputBase_eq_of_safeLayout parameters thread variableCount
        hlayout hinWrapped
  have hrowAddress :
      globalAddress parameters.outputs (index * 24) =
        parameters.outputs + index * 24 := by
    apply globalAddress_eq_of_lt
    rcases hlayout with ⟨_, _, _, _, _, _, houtputsEnd, _⟩
    omega
  have hbaseAddress :
      globalAddress (prologueOutputBase parameters thread) 0 =
        prologueOutputBase parameters thread := by
    apply globalAddress_eq_of_lt
    have hsafe := prologueOutputBase_record_safe parameters thread
      variableCount hthread hlayout hin
    omega
  have hrecordBase :
      globalAddress parameters.outputs (index * 24) =
        globalAddress (prologueOutputBase parameters thread) (0 * 24) := by
    rw [Nat.zero_mul]
    exact hrowAddress.trans (hbase.symm.trans hbaseAddress.symm)
  change observeOutput memory parameters.outputs index =
    observeOutput memory (prologueOutputBase parameters thread) 0
  unfold observeOutput
  rw [hrecordBase]

/-- Row-indexed ABI form of `executeCompiledOutput_observe`: if the output
base register contains the address computed by the in-range prologue, then
the isolated production output slice writes the corresponding public row. -/
theorem executeCompiledOutput_observeRow
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder)
    (interval : F64Interval) (variableCount : Nat)
    (hbase : state.u64.read outputBase.index =
      some (prologueOutputBase parameters thread))
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX <
      parameters.rowCount) :
    ∃ final,
      executeCode module parameters thread
          (compiledOutputInstructions outputBase result status builder) state =
        some { control := .fallthrough, state := final } ∧
      observeOutput final.memory parameters.outputs
          (thread.ctaidX * thread.ntidX + thread.tidX) =
        some (expectedObservedOutput interval status) := by
  have hsafe := prologueOutputBase_record_safe parameters thread
    variableCount hthread hlayout hin
  rcases executeCompiledOutput_observe module parameters thread state
      outputBase result status builder (prologueOutputBase parameters thread)
      interval hbase hlo hhi hsafe with
    ⟨final, hexecute, hobserve⟩
  refine ⟨final, hexecute, ?_⟩
  rw [observeOutput_eq_prologueOutputBase final.memory parameters thread
    variableCount hthread hlayout hin]
  exact hobserve

end SparkInterval.PTX
