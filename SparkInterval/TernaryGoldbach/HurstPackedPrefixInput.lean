/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstGpuRowRealization
import SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction

/-!
# Packed Möbius rows realize direct Hurst scan inputs

The optimized production CUDA path does not write an intermediate signed
Möbius byte.  It decodes each terminal packed support word directly to

```
{ mertens := μ, squarefree := if μ = 0 then 0 else 1 }.
```

A malformed or poisoned packed word increments the separate poison count and
writes a neutral pair.  Acceptance requires the poison count to be zero.

This file connects that interface to the packed-word finalization theorem and
to `HurstPrefixCandidateReduction.PrefixInputRowsValid`.  Consequently the
production inclusive-scan proof starts from exact mathematical row pairs,
while the retained byte path is only a differential qualification route.

The definitions are architecture independent.  Showing that a compiled CUDA
finalizer and atomic poison counter implement them remains a physical
refinement obligation.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstPackedPrefixInput

open SparkInterval.TernaryGoldbach.HurstGpuRowRealization
open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
open SparkInterval.TernaryGoldbach.MobiusFusedFinalization
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235

/-- One-row poison count emitted by the direct packed finalizer model. -/
def packedPoisonCount (number : Nat) (suffix : List Nat) : Nat :=
  if decodeWord (packedRunResidueSeeded number suffix) =
      MobiusGuardedMachine.State.poison
    then 1
    else 0

/-- The production receipt records one aggregate poison count for the whole
leaf, rather than one field per row. -/
def packedPoisonCountTotal
    (numbers : List Nat) (suffix : List Nat) : Nat :=
  (numbers.map fun number => packedPoisonCount number suffix).sum

theorem packedPoisonCount_le_one
    (number : Nat) (suffix : List Nat) :
    packedPoisonCount number suffix ≤ 1 := by
  simp only [packedPoisonCount]
  split <;> omega

theorem packedPoisonCountTotal_le_length
    (numbers : List Nat) (suffix : List Nat) :
    packedPoisonCountTotal numbers suffix ≤ numbers.length := by
  induction numbers with
  | nil =>
      simp [packedPoisonCountTotal]
  | cons head tail inductionHypothesis =>
      have headBound := packedPoisonCount_le_one head suffix
      simpa [packedPoisonCountTotal, Nat.add_comm] using
        Nat.add_le_add headBound inductionHypothesis

/-- One production leaf has at most `10^8` rows, so its 32-bit atomic poison
counter cannot wrap even if every row is poisoned. -/
theorem packedPoisonCountTotal_fits_uint32
    {numbers : List Nat} {suffix : List Nat}
    (leafBound : numbers.length ≤ 100_000_000) :
    packedPoisonCountTotal numbers suffix < 2 ^ 32 := by
  have totalBound :=
    (packedPoisonCountTotal_le_length numbers suffix).trans leafBound
  omega

private theorem member_eq_zero_of_sum_eq_zero :
    ∀ (values : List Nat), values.sum = 0 →
      ∀ value ∈ values, value = 0
  | [], _zero, value, member => by
      simp at member
  | head :: tail, totalZero, value, member => by
      simp only [List.sum_cons] at totalZero
      have headZero : head = 0 := by omega
      have tailZero : tail.sum = 0 := by omega
      rcases List.mem_cons.mp member with rfl | member
      · exact headZero
      · exact member_eq_zero_of_sum_eq_zero
          tail tailZero value member

/-- A zero aggregate poison count implies the exact zero-poison fact for
every row committed to that leaf.  This is the receipt-shaped elimination
rule used below. -/
theorem packedPoisonCount_eq_zero_of_total
    {numbers suffix : List Nat}
    (totalZero : packedPoisonCountTotal numbers suffix = 0)
    {number : Nat}
    (numberMember : number ∈ numbers) :
    packedPoisonCount number suffix = 0 := by
  apply member_eq_zero_of_sum_eq_zero
    (numbers.map fun current => packedPoisonCount current suffix)
  · simpa [packedPoisonCountTotal] using totalZero
  · exact List.mem_map.mpr ⟨number, numberMember, rfl⟩

/-- Exact unscanned pair emitted by the direct packed finalizer model.
Poison contributes a neutral pair because the separate nonzero poison count
makes the enclosing receipt fail closed. -/
def packedPrefixInput
    (number : Nat) (suffix : List Nat) : PrefixMQ :=
  if decodeWord (packedRunResidueSeeded number suffix) =
      MobiusGuardedMachine.State.poison
    then PrefixMQ.zero
    else
      let mu :=
        output number
          (decodeWord (packedRunResidueSeeded number suffix))
      {
        mertens := mu
        squarefree := if mu = 0 then 0 else 1
      }

theorem packedPoisonCount_eq_zero_iff
    (number : Nat) (suffix : List Nat) :
    packedPoisonCount number suffix = 0 ↔
      decodeWord (packedRunResidueSeeded number suffix) ≠
        MobiusGuardedMachine.State.poison := by
  simp [packedPoisonCount]

theorem packedPrefixInput_of_notPoison
    {number : Nat} {suffix : List Nat}
    (notPoison :
      decodeWord (packedRunResidueSeeded number suffix) ≠
        MobiusGuardedMachine.State.poison) :
    packedPrefixInput number suffix =
      {
        mertens :=
          output number
            (decodeWord (packedRunResidueSeeded number suffix))
        squarefree :=
          if output number
              (decodeWord (packedRunResidueSeeded number suffix)) = 0
            then 0
            else 1
      } := by
  simp [packedPrefixInput, notPoison]

/-- A complete roster and zero poison count make one direct scan input the
exact mathematical Möbius/squarefree pair. -/
theorem packedPrefixInput_eq_moebius
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number (seedPrimes ++ suffix))
    (poisonFree : packedPoisonCount number suffix = 0) :
    packedPrefixInput number suffix =
      {
        mertens := ArithmeticFunction.moebius number
        squarefree :=
          if ArithmeticFunction.moebius number = 0 then 0 else 1
      } := by
  have notPoison :
      decodeWord (packedRunResidueSeeded number suffix) ≠
        MobiusGuardedMachine.State.poison :=
    (packedPoisonCount_eq_zero_iff number suffix).mp poisonFree
  rw [packedPrefixInput_of_notPoison notPoison]
  rw [output_decodeWord_packedRunResidueSeeded_eq_moebius
    roster notPoison]

/-- Every accepted direct packed row satisfies the exact native input-row
shape required by the prefix-scan proof. -/
theorem packedPrefixInput_valid
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number (seedPrimes ++ suffix))
    (poisonFree : packedPoisonCount number suffix = 0) :
    PrefixInputRowValid (packedPrefixInput number suffix) := by
  rw [packedPrefixInput_eq_moebius roster poisonFree]
  have absoluteBound :
      |ArithmeticFunction.moebius number| ≤ (1 : Int) :=
    ArithmeticFunction.abs_moebius_le_one
  have bounds :
      (-1 : Int) ≤ ArithmeticFunction.moebius number ∧
        ArithmeticFunction.moebius number ≤ 1 :=
    (abs_le.mp absoluteBound)
  exact ⟨bounds.1, bounds.2, rfl⟩

/-- The direct scan pair is the two-coordinate projection of the packed
terminal Hurst row already proved from the same word. -/
theorem packedPrefixInput_eq_terminalProjection
    {number : Nat} {suffix : List Nat}
    (poisonFree : packedPoisonCount number suffix = 0) :
    (packedPrefixInput number suffix).mertens =
        (packedTerminalDelta number suffix).mertens ∧
      ((packedPrefixInput number suffix).squarefree : Int) =
        (packedTerminalDelta number suffix).squarefree := by
  have notPoison :
      decodeWord (packedRunResidueSeeded number suffix) ≠
        MobiusGuardedMachine.State.poison :=
    (packedPoisonCount_eq_zero_iff number suffix).mp poisonFree
  rw [packedPrefixInput_of_notPoison notPoison]
  simp [packedTerminalDelta]

/-- Direct packed inputs for one ordered leaf.  The suffix is the one global
authenticated prime roster shared by every row. -/
def packedPrefixInputs
    (numbers : List Nat) (suffix : List Nat) : List PrefixMQ :=
  numbers.map fun number => packedPrefixInput number suffix

/-- Pointwise complete-roster and zero-poison evidence lifts to the exact
whole-leaf input condition consumed by the production scan theorem. -/
theorem packedPrefixInputs_valid
    {numbers suffix : List Nat}
    (roster :
      ∀ number ∈ numbers,
        CompletePrimeRoster number (seedPrimes ++ suffix))
    (poisonFree :
      ∀ number ∈ numbers,
        packedPoisonCount number suffix = 0) :
    PrefixInputRowsValid (packedPrefixInputs numbers suffix) := by
  intro row rowMember
  rw [packedPrefixInputs, List.mem_map] at rowMember
  rcases rowMember with ⟨number, numberMember, rfl⟩
  exact packedPrefixInput_valid
    (roster number numberMember)
    (poisonFree number numberMember)

/-- The actual production acceptance field is an aggregate zero count.  A
complete roster plus that single receipt field therefore implies the exact
whole-leaf input condition consumed by the prefix-scan theorem. -/
theorem packedPrefixInputs_valid_of_totalPoisonCount_zero
    {numbers suffix : List Nat}
    (roster :
      ∀ number ∈ numbers,
        CompletePrimeRoster number (seedPrimes ++ suffix))
    (totalZero : packedPoisonCountTotal numbers suffix = 0) :
    PrefixInputRowsValid (packedPrefixInputs numbers suffix) := by
  apply packedPrefixInputs_valid roster
  intro number numberMember
  exact packedPoisonCount_eq_zero_of_total
    totalZero numberMember

#print axioms packedPoisonCount_eq_zero_iff
#print axioms packedPoisonCountTotal_le_length
#print axioms packedPoisonCountTotal_fits_uint32
#print axioms packedPoisonCount_eq_zero_of_total
#print axioms packedPrefixInput_eq_moebius
#print axioms packedPrefixInput_valid
#print axioms packedPrefixInput_eq_terminalProjection
#print axioms packedPrefixInputs_valid
#print axioms packedPrefixInputs_valid_of_totalPoisonCount_zero

end SparkInterval.TernaryGoldbach.HurstPackedPrefixInput
