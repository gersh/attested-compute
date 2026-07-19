import SparkInterval.EvalSound
import SparkInterval.FPIntervalSound
import SparkInterval.PTX.Semantics

/-!
The output of these commands is part of the Phase 1 audit surface.  No project
postulate is declared; only Lean/Mathlib's standard logical foundations may appear.
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
