/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusFusedFinalization

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusFusedFinalization

open SparkInterval.TernaryGoldbach
open MobiusFusedFinalization
open MobiusResidue235

private theorem squarefree_thirty : Squarefree 30 := by
  rw [Nat.squarefree_iff_nodup_primeFactorsList (by norm_num)]
  norm_num [Nat.primeFactorsList]

private theorem squarefree_six : Squarefree 6 := by
  rw [Nat.squarefree_iff_nodup_primeFactorsList (by norm_num)]
  norm_num [Nat.primeFactorsList]

private theorem not_squarefree_twelve : ¬Squarefree 12 := by
  rw [Nat.squarefree_iff_nodup_primeFactorsList (by norm_num)]
  norm_num [Nat.primeFactorsList]

private theorem not_squarefree_seventy_two : ¬Squarefree 72 := by
  rw [Nat.squarefree_iff_nodup_primeFactorsList (by norm_num)]
  norm_num [Nat.primeFactorsList]

example :
    [2, 3, 5, 7].Perm [7, 5, 2, 3] := by
  decide

example :
    foldSupport 210 [2, 3, 5, 7] =
      foldSupport 210 [7, 5, 2, 3] := by
  apply foldSupport_perm
  decide

private theorem valid_thirty :
    SourceRowSupportValid 30 (foldSupport 30 [2, 3, 5]) := by
  change SourceRowSupportValid 30
    { product := 30, distinctCount := 3, squareful := false }
  refine {
    numberPositive := by norm_num
    productPositive := by norm_num
    productDivides := by norm_num
    productSquarefree := squarefree_thirty
    distinctCount := ?_
    residualOneOrPrime := fun _ => by norm_num
    squareful := by simp [squarefree_thirty]
  }
  norm_num [ArithmeticFunction.cardDistinctFactors,
    Nat.primeFactorsList]

private theorem valid_twelve :
    SourceRowSupportValid 12 (foldSupport 12 [2, 3]) := by
  change SourceRowSupportValid 12
    { product := 6, distinctCount := 2, squareful := true }
  refine {
    numberPositive := by norm_num
    productPositive := by norm_num
    productDivides := by norm_num
    productSquarefree := squarefree_six
    distinctCount := ?_
    residualOneOrPrime := by
      simp [not_squarefree_twelve]
    squareful := by simp [not_squarefree_twelve]
  }
  norm_num [ArithmeticFunction.cardDistinctFactors,
    Nat.primeFactorsList]

private theorem valid_roster_thirty :
    SourceRosterValid 30 [2, 3, 5] := by
  refine {
    numberPositive := by norm_num
    productPositive := by
      norm_num [selectedDivisors]
    productDivides := by
      norm_num [selectedDivisors]
    productSquarefree := by
      simpa [selectedDivisors] using squarefree_thirty
    distinctCount := by
      norm_num [selectedDivisors,
        ArithmeticFunction.cardDistinctFactors,
        Nat.primeFactorsList]
    residualOneOrPrime := fun _ => by
      norm_num [selectedDivisors]
    squareful := by
      simp [hasSquareEvent, squarefree_thirty]
  }

private theorem valid_roster_seventy_two :
    SourceRosterValid 72 [2, 3] := by
  refine {
    numberPositive := by norm_num
    productPositive := by
      norm_num [selectedDivisors]
    productDivides := by
      norm_num [selectedDivisors]
    productSquarefree := by
      simpa [selectedDivisors] using squarefree_six
    distinctCount := by
      norm_num [selectedDivisors,
        ArithmeticFunction.cardDistinctFactors,
        Nat.primeFactorsList]
    residualOneOrPrime := by
      simp [not_squarefree_seventy_two]
    squareful := by
      simp [hasSquareEvent, not_squarefree_seventy_two]
  }

example :
    finalize 30 (foldSupport 30 [2, 3, 5]) =
      ArithmeticFunction.moebius 30 :=
  finalize_eq_moebius valid_thirty

example :
    finalize 12 (foldSupport 12 [2, 3]) =
      ArithmeticFunction.moebius 12 :=
  finalize_eq_moebius valid_twelve

example :
    finalize 30 (foldSupport 30 [2, 3, 5]) =
      ArithmeticFunction.moebius 30 :=
  finalize_foldSupport_eq_moebius valid_roster_thirty

/-- Regression: the residual `72 / 6 = 12` is composite.  This remains a
valid live row because the proved squareful bit takes the zero branch before
the residual parity rule is used. -/
example :
    finalize 72 (foldSupport 72 [2, 3]) =
      ArithmeticFunction.moebius 72 :=
  finalize_foldSupport_eq_moebius valid_roster_seventy_two

example :
    finalize 30
        ([].foldl (applyPrime 30) (residueSeed 30)) =
      ArithmeticFunction.moebius 30 := by
  exact finalize_residueSeeded_eq_moebius 30 [] (by
    simpa [seedPrimes] using valid_thirty)

#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedFinalization.foldSupport_perm
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_eq_moebius
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_foldSupport_eq_moebius
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_residueSeeded_eq_moebius

end SparkInterval.Tests.MobiusFusedFinalization
