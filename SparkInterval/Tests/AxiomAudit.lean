import SparkInterval.EvalSound
import SparkInterval.FPIntervalSound
import SparkInterval.PTX.Semantics
import SparkInterval.PTX.MachineSemantics
import SparkInterval.PTX.CodeComposition
import SparkInterval.PTX.F64RegisterEffects
import SparkInterval.PTX.InstructionRefinement
import SparkInterval.PTX.ExpressionInstructionRefinement
import SparkInterval.PTX.CompilerDataflow
import SparkInterval.PTX.CompilerFiniteGuardRefinement
import SparkInterval.PTX.CompilerNodeRefinement
import SparkInterval.PTX.CompilerOutputRefinement
import SparkInterval.PTX.PrologueRefinement
import SparkInterval.PTX.OutputLayoutRefinement
import SparkInterval.PTX.GeneratedKernelRunRefinement
import SparkInterval.PTX.Emitter
import SparkInterval.PTX.StructuralCompilerCorrect
import SparkInterval.Certificate

/-!
The output of these commands is part of the mathematical-core and Phase 8
audit surface. No project postulate is declared; only Lean/Mathlib's standard
logical foundations may appear. Concrete generated serialized-certificate
modules print their separate `native_decide` dependency in the generated file.
-/

#print axioms SparkInterval.RealInterval.add_contains
#print axioms SparkInterval.RealInterval.mul_contains
#print axioms SparkInterval.RealInterval.reciprocal_contains
#print axioms SparkInterval.RealInterval.div_contains
#print axioms SparkInterval.evalInterval_sound
#print axioms SparkInterval.Binary64Rounding.roundDown_le
#print axioms SparkInterval.Binary64Rounding.le_roundUp
#print axioms SparkInterval.Binary64Rounding.roundDown_greatest
#print axioms SparkInterval.Binary64Rounding.roundUp_least
#print axioms SparkInterval.FPInterval.add_contains
#print axioms SparkInterval.FPInterval.sub_contains
#print axioms SparkInterval.FPInterval.mul_contains
#print axioms SparkInterval.FPInterval.div_contains
#print axioms SparkInterval.PTX.directedBinary_down_le
#print axioms SparkInterval.PTX.le_directedBinary_up
#print axioms SparkInterval.PTX.decodeF64Bits_of_finite
#print axioms SparkInterval.PTX.decodeF64Bits_of_infinite
#print axioms SparkInterval.PTX.decodeF64Bits_of_nan
#print axioms SparkInterval.PTX.addFragmentResult_contains
#print axioms SparkInterval.PTX.subFragmentResult_contains
#print axioms SparkInterval.PTX.mulFragmentResult_contains
#print axioms SparkInterval.PTX.executeCanonicalAdd_contains
#print axioms SparkInterval.PTX.executeCanonicalSub_contains
#print axioms SparkInterval.PTX.executeCanonicalMul_contains
#print axioms SparkInterval.PTX.PolynomialExpr.evalKernel_sound
#print axioms SparkInterval.PTX.ThreadContext.globalIndex_eq
#print axioms SparkInterval.PTX.globalAddress_eq_of_lt
#print axioms SparkInterval.PTX.executeCode_append
#print axioms SparkInterval.PTX.executeCode_append_fallthrough
#print axioms SparkInterval.PTX.executeCode_append_jump
#print axioms SparkInterval.PTX.executeCode_append_returned
#print axioms SparkInterval.PTX.executeInstruction_preserves_f64_read
#print axioms SparkInterval.PTX.executeCode_preserves_f64_read
#print axioms SparkInterval.PTX.executeFiniteGuard_fallthrough
#print axioms SparkInterval.PTX.executeFiniteGuard_lowerNonfinite
#print axioms SparkInterval.PTX.executeFiniteGuard_upperNonfinite
#print axioms SparkInterval.PTX.executeAddArithmeticFragment
#print axioms SparkInterval.PTX.executeSubArithmeticFragment
#print axioms SparkInterval.PTX.executeMulArithmeticFragment
#print axioms SparkInterval.PTX.executeConstInstructions
#print axioms SparkInterval.PTX.executeLoadIntervalInstructions
#print axioms SparkInterval.PTX.executeNegInstructions
#print axioms SparkInterval.PTX.emitFiniteGuard_body
#print axioms SparkInterval.PTX.emitFiniteGuard_body_size
#print axioms SparkInterval.PTX.executeCompiledFiniteGuard_fallthrough
#print axioms SparkInterval.PTX.executeCompiledFiniteGuard_lowerNonfinite
#print axioms SparkInterval.PTX.executeCompiledFiniteGuard_upperNonfinite
#print axioms SparkInterval.PTX.allocateMulRegisters_destinationIndices_nodup
#print axioms SparkInterval.PTX.compileMul_refinement_freshness
#print axioms SparkInterval.PTX.compileExpr_nextF64
#print axioms SparkInterval.PTX.compileExpr_result_below
#print axioms SparkInterval.PTX.compileExpr_pair_below
#print axioms SparkInterval.PTX.compileMulAllocation_destinationIndices_eq
#print axioms SparkInterval.PTX.executeCompileAddArithmeticFragment
#print axioms SparkInterval.PTX.executeCompileSubArithmeticFragment
#print axioms SparkInterval.PTX.executeCompileMulArithmeticFragment
#print axioms SparkInterval.PTX.executeCompileExprAppendedCode
#print axioms SparkInterval.PTX.emitOutput_body
#print axioms SparkInterval.PTX.writeOutputMemory_contains
#print axioms SparkInterval.PTX.executeCompiledOutput
#print axioms SparkInterval.PTX.executeCompiledOutput_contains
#print axioms SparkInterval.PTX.executeCompiledOutput_observe
#print axioms SparkInterval.PTX.emitPrologue_exact
#print axioms SparkInterval.PTX.executePrologue_outOfRange
#print axioms SparkInterval.PTX.executePrologue_inRange
#print axioms SparkInterval.PTX.executePrologue_inRange_exactNat
#print axioms SparkInterval.PTX.prologueOutputBase_record_safe
#print axioms SparkInterval.PTX.observeOutput_eq_prologueOutputBase
#print axioms SparkInterval.PTX.executeCompiledOutput_observeRow
#print axioms SparkInterval.PTX.executeBuildModuleStructured_inRange
#print axioms SparkInterval.PTX.runBuildModule_outOfRange
#print axioms SparkInterval.PTX.runBuildModule_inRange
#print axioms SparkInterval.PTX.runBuildModule_inRange_containsReal
#print axioms SparkInterval.PTX.buildModule_opcodeTrace
#print axioms SparkInterval.PTX.StructuralCompilerCorrect.buildModule_eq_expectedModule
#print axioms SparkInterval.PTX.Instruction.opcode_mem_allowed
#print axioms SparkInterval.PTX.emit_success
#print axioms SparkInterval.PTX.emit_of_validate
#print axioms SparkInterval.Certificate.CertExpr.eval_sound
#print axioms SparkInterval.Certificate.FullCertificate.check_sound
#print axioms SparkInterval.Certificate.FullCertificate.checkUpperBound_sound
#print axioms SparkInterval.Certificate.FullCertificate.checkSumUpperBound_sound
#print axioms SparkInterval.Certificate.impliesTheorem
#print axioms SparkInterval.Certificate.impliesSumTheorem
