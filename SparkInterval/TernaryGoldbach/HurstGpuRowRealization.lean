/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstSourceSemantics
import SparkInterval.TernaryGoldbach.MobiusFusedFinalization
import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge
import SparkInterval.TernaryGoldbach.MobiusGuardedMachine
import SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement

/-!
# Fused Möbius rows realize the terminal Hurst source deltas

The shared Hurst campaign freezes both directed little-Mertens coordinates
after `10^12`.  Above that split, one source row therefore needs only:

* the exact Möbius value;
* its exact squarefree indicator; and
* two zero Q96 increments.

`MobiusFusedFinalization` proves that the abstract residue-seeded CUDA
support fold returns Mathlib's Möbius function.  This file projects that
result directly into `HurstSourceSemantics.SourceRowDelta`, the primitive
row proposition used by the ordinary full-campaign theorem.

No native execution theorem is claimed here.  The remaining machine
refinement must establish `SourceRosterValid` for each executed row and
identify the emitted terminal delta with `terminalDelta`.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstGpuRowRealization

open SparkInterval.TernaryGoldbach.HurstAffineCertificate
open SparkInterval.TernaryGoldbach.HurstSourceSemantics
open SparkInterval.TernaryGoldbach.MobiusFusedFinalization
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusResidue235

/-- Exact four-coordinate row emitted on the GPU side of the `10^12` split.
-/
def terminalDelta (number : Nat) (primes : List Nat) :
    HurstAffineCertificate.State where
  mertens := finalize number (foldSupport number primes)
  squarefree :=
    if finalize number (foldSupport number primes) = 0 then 0 else 1
  littleLowerQ96 := 0
  littleUpperQ96 := 0

/-- Terminal row projected directly from the fail-closed residue-seeded
machine, including its impossible poison sentinel. -/
def guardedTerminalDelta
    (number : Nat) (suffix : List Nat) :
    HurstAffineCertificate.State where
  mertens := output number (runResidueSeeded number suffix)
  squarefree :=
    if output number (runResidueSeeded number suffix) = 0 then 0 else 1
  littleLowerQ96 := 0
  littleUpperQ96 := 0

/-- Exact terminal row projected from the production 64-bit packed support
word.  This is the representation emitted immediately before the native
byte-finalization and prefix-scan stages. -/
def packedTerminalDelta
    (number : Nat) (suffix : List Nat) :
    HurstAffineCertificate.State where
  mertens :=
    output number
      (decodeWord (packedRunResidueSeeded number suffix))
  squarefree :=
    if output number
        (decodeWord (packedRunResidueSeeded number suffix)) = 0
      then 0
      else 1
  littleLowerQ96 := 0
  littleUpperQ96 := 0

/-- A complete roster for one terminal row supplies exactly the primitive
Hurst source delta consumed by the global prefix proof. -/
theorem terminalDelta_sourceRowDelta
    {number : Nat} {primes : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (valid : SourceRosterValid number primes) :
    HurstSourceSemantics.SourceRowDelta number
      (terminalDelta number primes) := by
  have mobiusExact :
      finalize number (foldSupport number primes) =
        ArithmeticFunction.moebius number :=
    finalize_foldSupport_eq_moebius valid
  refine ⟨?_, ?_, ?_⟩
  · exact mobiusExact
  · simp [terminalDelta, mobiusExact]
  · have notBelowLittleMertens :
        ¬ number ≤ HurstSourceSemantics.little211Limit :=
      Nat.not_le_of_lt aboveLittleMertens
    simp [terminalDelta, notBelowLittleMertens]

/-- Residue-seeded presentation of the same row theorem. -/
theorem residueSeededTerminalDelta_sourceRowDelta
    {number : Nat} {suffix : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (valid :
      SourceRosterValid number
        (MobiusResidue235.seedPrimes ++ suffix)) :
    HurstSourceSemantics.SourceRowDelta number
      (terminalDelta number
        (MobiusResidue235.seedPrimes ++ suffix)) :=
  terminalDelta_sourceRowDelta aboveLittleMertens valid

/-- Production-shaped row theorem from the short conventional roster
contract: duplicate-free prime entries and completeness through the row's
square root.  All product/count/residual/square-event fields are derived in
ordinary Lean rather than supplied by a receipt. -/
theorem terminalDelta_completePrimeRoster_sourceRowDelta
    {number : Nat} {primes : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (valid : CompletePrimeRoster number primes) :
    HurstSourceSemantics.SourceRowDelta number
      (terminalDelta number primes) :=
  terminalDelta_sourceRowDelta aboveLittleMertens
    valid.sourceRosterValid

/-- One duplicate-free roster containing exactly enough primes through
`10^8` supplies the short row contract uniformly over the production source
domain through `10^16`. -/
theorem terminalDelta_productionPrimeRoster_sourceRowDelta
    {number : Nat} {primes : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (numberAtMostSourceLimit :
      number ≤ HurstSourceSemantics.sourceLimit)
    (valid :
      PrimeRosterThrough productionPrimeBound primes) :
    HurstSourceSemantics.SourceRowDelta number
      (terminalDelta number primes) := by
  have numberPositive : 0 < number := by
    omega
  have numberLePrimeBoundSquare :
      number ≤ productionPrimeBound * productionPrimeBound := by
    rw [productionPrimeBound_square]
    simpa [
      HurstSourceSemantics.sourceLimit,
      SparkInterval.TernaryGoldbach.MobiusFusedSupport.sourceLimit
    ] using numberAtMostSourceLimit
  exact terminalDelta_completePrimeRoster_sourceRowDelta
    aboveLittleMertens
    (valid.completePrimeRoster numberPositive
      numberLePrimeBoundSquare)

/-- Fully data-certificate-shaped terminal row theorem: the existing
Lucas/Pratt plus composite-gap Boolean checker supplies the one global prime
roster premise, and ordinary Lean supplies the exact Hurst row semantics. -/
theorem terminalDelta_checkedProductionPrimeRoster_sourceRowDelta
    {number : Nat}
    {certificate :
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.PrimeRosterCertificate}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (numberAtMostSourceLimit :
      number ≤ HurstSourceSemantics.sourceLimit)
    (checked :
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.primeRosterCheck
        productionPrimeBound certificate = true) :
    HurstSourceSemantics.SourceRowDelta number
      (terminalDelta number (rosterList certificate)) :=
  terminalDelta_productionPrimeRoster_sourceRowDelta
    aboveLittleMertens numberAtMostSourceLimit
    (productionPrimeRosterThrough_of_checkedCertificate checked)

/-- Same data-certificate theorem for the exact decoded raw roster consumed
by CUDA.  The second Boolean check prevents substituting a different prime
list after certifying the V2 roster. -/
theorem terminalDelta_checkedBoundProductionPrimeRoster_sourceRowDelta
    {number : Nat} {rawPrimes : List Nat}
    {certificate :
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.PrimeRosterCertificate}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (numberAtMostSourceLimit :
      number ≤ HurstSourceSemantics.sourceLimit)
    (certificateChecked :
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.primeRosterCheck
        productionPrimeBound certificate = true)
    (bindingChecked :
      rosterBindingCheck rawPrimes certificate = true) :
    HurstSourceSemantics.SourceRowDelta number
      (terminalDelta number rawPrimes) :=
  terminalDelta_productionPrimeRoster_sourceRowDelta
    aboveLittleMertens numberAtMostSourceLimit
    (productionPrimeRosterThrough_of_checkedBoundCertificate
      certificateChecked bindingChecked)

/-- A nonpoison guarded CUDA-model row realizes the primitive Hurst source
delta.  No product/count/residual proposition is accepted from the runtime. -/
theorem guardedTerminalDelta_sourceRowDelta
    {number : Nat} {suffix : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (roster :
      CompletePrimeRoster number (seedPrimes ++ suffix))
    (notPoison :
      runResidueSeeded number suffix ≠
        MobiusGuardedMachine.State.poison) :
    HurstSourceSemantics.SourceRowDelta number
      (guardedTerminalDelta number suffix) := by
  have mobiusExact :
      output number (runResidueSeeded number suffix) =
        ArithmeticFunction.moebius number :=
    output_runResidueSeeded_eq_moebius roster notPoison
  refine ⟨?_, ?_, ?_⟩
  · exact mobiusExact
  · simp [guardedTerminalDelta, mobiusExact]
  · have notBelowLittleMertens :
        ¬ number ≤ HurstSourceSemantics.little211Limit :=
      Nat.not_le_of_lt aboveLittleMertens
    simp [guardedTerminalDelta, notBelowLittleMertens]

/-- One globally checked `10^8` roster and a zero poison count suffice for
every guarded terminal row through `10^16`. -/
theorem guardedTerminalDelta_productionPrimeRoster_sourceRowDelta
    {number : Nat} {suffix : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (numberAtMostSourceLimit :
      number ≤ HurstSourceSemantics.sourceLimit)
    (roster :
      PrimeRosterThrough productionPrimeBound
        (seedPrimes ++ suffix))
    (notPoison :
      runResidueSeeded number suffix ≠
        MobiusGuardedMachine.State.poison) :
    HurstSourceSemantics.SourceRowDelta number
      (guardedTerminalDelta number suffix) := by
  have numberPositive : 0 < number := by
    omega
  have numberLePrimeBoundSquare :
      number ≤ productionPrimeBound * productionPrimeBound := by
    rw [productionPrimeBound_square]
    simpa [
      HurstSourceSemantics.sourceLimit,
      SparkInterval.TernaryGoldbach.MobiusFusedSupport.sourceLimit
    ] using numberAtMostSourceLimit
  exact guardedTerminalDelta_sourceRowDelta
    aboveLittleMertens
    (roster.completePrimeRoster numberPositive
      numberLePrimeBoundSquare)
    notPoison

/-- A nonpoison decoded production packed word realizes the primitive Hurst
source row directly.  The packed product/count/squareful arithmetic and its
fail-closed poison behavior are therefore inside the Lean proof boundary. -/
theorem packedTerminalDelta_sourceRowDelta
    {number : Nat} {suffix : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (roster :
      CompletePrimeRoster number (seedPrimes ++ suffix))
    (notPoison :
      decodeWord (packedRunResidueSeeded number suffix) ≠
        MobiusGuardedMachine.State.poison) :
    HurstSourceSemantics.SourceRowDelta number
      (packedTerminalDelta number suffix) := by
  have mobiusExact :
      output number
          (decodeWord (packedRunResidueSeeded number suffix)) =
        ArithmeticFunction.moebius number :=
    output_decodeWord_packedRunResidueSeeded_eq_moebius
      roster notPoison
  refine ⟨?_, ?_, ?_⟩
  · exact mobiusExact
  · simp [packedTerminalDelta, mobiusExact]
  · have notBelowLittleMertens :
        ¬ number ≤ HurstSourceSemantics.little211Limit :=
      Nat.not_le_of_lt aboveLittleMertens
    simp [packedTerminalDelta, notBelowLittleMertens]

/-- The production `10^8` roster contract lifts the direct packed-row theorem
uniformly over every terminal source row through `10^16`. -/
theorem packedTerminalDelta_productionPrimeRoster_sourceRowDelta
    {number : Nat} {suffix : List Nat}
    (aboveLittleMertens :
      HurstSourceSemantics.little211Limit < number)
    (numberAtMostSourceLimit :
      number ≤ HurstSourceSemantics.sourceLimit)
    (roster :
      PrimeRosterThrough productionPrimeBound
        (seedPrimes ++ suffix))
    (notPoison :
      decodeWord (packedRunResidueSeeded number suffix) ≠
        MobiusGuardedMachine.State.poison) :
    HurstSourceSemantics.SourceRowDelta number
      (packedTerminalDelta number suffix) := by
  have numberPositive : 0 < number := by
    omega
  have numberLePrimeBoundSquare :
      number ≤ productionPrimeBound * productionPrimeBound := by
    rw [productionPrimeBound_square]
    simpa [
      HurstSourceSemantics.sourceLimit,
      SparkInterval.TernaryGoldbach.MobiusFusedSupport.sourceLimit
    ] using numberAtMostSourceLimit
  exact packedTerminalDelta_sourceRowDelta
    aboveLittleMertens
    (roster.completePrimeRoster numberPositive
      numberLePrimeBoundSquare)
    notPoison

#print axioms terminalDelta_sourceRowDelta
#print axioms residueSeededTerminalDelta_sourceRowDelta
#print axioms terminalDelta_completePrimeRoster_sourceRowDelta
#print axioms terminalDelta_productionPrimeRoster_sourceRowDelta
#print axioms terminalDelta_checkedProductionPrimeRoster_sourceRowDelta
#print axioms terminalDelta_checkedBoundProductionPrimeRoster_sourceRowDelta
#print axioms guardedTerminalDelta_sourceRowDelta
#print axioms guardedTerminalDelta_productionPrimeRoster_sourceRowDelta
#print axioms packedTerminalDelta_sourceRowDelta
#print axioms packedTerminalDelta_productionPrimeRoster_sourceRowDelta

end SparkInterval.TernaryGoldbach.HurstGpuRowRealization
