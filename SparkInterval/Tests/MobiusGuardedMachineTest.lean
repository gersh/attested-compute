/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusGuardedMachine

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusGuardedMachineTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235

private theorem rosterSeventySeven :
    CompletePrimeRoster 77 (seedPrimes ++ [7]) := by
  refine {
    numberPositive := by norm_num
    nodup := by decide
    entriesPrime := ?_
    completeThroughSqrt := ?_
  }
  · intro prime member
    simp only [seedPrimes, List.mem_append, List.mem_cons,
      List.not_mem_nil, or_false] at member
    rcases member with (rfl | rfl | rfl) | rfl <;> norm_num
  · intro prime primePrime primeSquareLe
    have primeLe : prime ≤ 8 := by
      nlinarith
    interval_cases prime <;> norm_num at primePrime
    all_goals simp [seedPrimes]

#guard
  foldEvents 77 [7] (.valid initialSupport) ≠ State.poison

#guard
  foldEvents 77 [1] (.valid initialSupport) = State.poison

#guard output 77 State.poison = 2

example :
    output 77 (runResidueSeeded 77 [7]) =
      ArithmeticFunction.moebius 77 :=
  output_runResidueSeeded_eq_moebius
    rosterSeventySeven (by decide)

#print axioms
  SparkInterval.TernaryGoldbach.MobiusGuardedMachine.foldEvents_eq_valid_of_ne_poison
#print axioms
  SparkInterval.TernaryGoldbach.MobiusGuardedMachine.runResidueSeeded_eq_foldSupport_of_ne_poison
#print axioms
  SparkInterval.TernaryGoldbach.MobiusGuardedMachine.output_runResidueSeeded_eq_moebius

end SparkInterval.Tests.MobiusGuardedMachineTest
