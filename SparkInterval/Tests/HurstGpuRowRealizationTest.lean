/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstGpuRowRealization

set_option autoImplicit false

namespace SparkInterval.Tests.HurstGpuRowRealizationTest

open SparkInterval.TernaryGoldbach.HurstGpuRowRealization
open SparkInterval.TernaryGoldbach.HurstSourceSemantics
open SparkInterval.TernaryGoldbach.MobiusFusedFinalization
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusResidue235

/-- The production theorem is polymorphic in the physical row number and
roster; a machine refinement only has to supply its two explicit premises. -/
example {number : Nat} {primes : List Nat}
    (aboveSplit : little211Limit < number)
    (valid : SourceRosterValid number primes) :
    SourceRowDelta number (terminalDelta number primes) :=
  terminalDelta_sourceRowDelta aboveSplit valid

/-- The modulo-900 seeded roster has the identical terminal-row interface. -/
example {number : Nat} {suffix : List Nat}
    (aboveSplit : little211Limit < number)
    (valid : SourceRosterValid number (seedPrimes ++ suffix)) :
    SourceRowDelta number
      (terminalDelta number (seedPrimes ++ suffix)) :=
  residueSeededTerminalDelta_sourceRowDelta aboveSplit valid

/-- One globally authenticated prime roster supports every production GPU
row; no per-row product/count/residual assertions are needed. -/
example {number : Nat} {primes : List Nat}
    (aboveSplit : little211Limit < number)
    (upper : number ≤ sourceLimit)
    (valid : PrimeRosterThrough productionPrimeBound primes) :
    SourceRowDelta number (terminalDelta number primes) :=
  terminalDelta_productionPrimeRoster_sourceRowDelta
    aboveSplit upper valid

/-- The production fail-closed interface needs only the global roster and a
nonpoison terminal row. -/
example {number : Nat} {suffix : List Nat}
    (aboveSplit : little211Limit < number)
    (upper : number ≤ sourceLimit)
    (valid :
      PrimeRosterThrough productionPrimeBound
        (seedPrimes ++ suffix))
    (notPoison :
      runResidueSeeded number suffix ≠
        SparkInterval.TernaryGoldbach.MobiusGuardedMachine.State.poison) :
    SourceRowDelta number
      (guardedTerminalDelta number suffix) :=
  guardedTerminalDelta_productionPrimeRoster_sourceRowDelta
    aboveSplit upper valid notPoison

/-- The exact packed word emitted by the optimized row kernel has the same
production source-row interface; no separate semantic row assertion is
needed after decoding. -/
example {number : Nat} {suffix : List Nat}
    (aboveSplit : little211Limit < number)
    (upper : number ≤ sourceLimit)
    (valid :
      PrimeRosterThrough productionPrimeBound
        (seedPrimes ++ suffix))
    (notPoison :
      decodeWord (packedRunResidueSeeded number suffix) ≠
        SparkInterval.TernaryGoldbach.MobiusGuardedMachine.State.poison) :
    SourceRowDelta number
      (packedTerminalDelta number suffix) :=
  packedTerminalDelta_productionPrimeRoster_sourceRowDelta
    aboveSplit upper valid notPoison

#print axioms
  SparkInterval.TernaryGoldbach.HurstGpuRowRealization.terminalDelta_sourceRowDelta
#print axioms
  SparkInterval.TernaryGoldbach.HurstGpuRowRealization.residueSeededTerminalDelta_sourceRowDelta
#print axioms
  SparkInterval.TernaryGoldbach.HurstGpuRowRealization.terminalDelta_productionPrimeRoster_sourceRowDelta
#print axioms
  SparkInterval.TernaryGoldbach.HurstGpuRowRealization.guardedTerminalDelta_productionPrimeRoster_sourceRowDelta
#print axioms
  SparkInterval.TernaryGoldbach.HurstGpuRowRealization.packedTerminalDelta_productionPrimeRoster_sourceRowDelta

end SparkInterval.Tests.HurstGpuRowRealizationTest
