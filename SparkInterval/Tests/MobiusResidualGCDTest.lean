/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidualGCD

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusResidualGCDTest

open SparkInterval.TernaryGoldbach.MobiusResidualGCD

theorem six_squarefree : Squarefree 6 := by
  change Squarefree (2 * 3)
  exact (Nat.squarefree_mul (by decide)).2
    ⟨Nat.prime_two.squarefree, Nat.prime_three.squarefree⟩

example :
    ¬Squarefree 12 ↔ 1 < Nat.gcd 6 2 := by
  apply source_row_not_squarefree_iff_one_lt_gcd
  · norm_num
  · norm_num
  · exact six_squarefree
  · exact Or.inr (by norm_num)

example :
    ¬Squarefree 30 ↔ 1 < Nat.gcd 6 5 := by
  apply source_row_not_squarefree_iff_one_lt_gcd
  · norm_num
  · norm_num
  · exact six_squarefree
  · exact Or.inr (by norm_num)

example :
    ¬Squarefree 1 ↔ 1 < Nat.gcd 1 1 := by
  apply source_row_not_squarefree_iff_one_lt_gcd
  · norm_num
  · norm_num
  · exact squarefree_one
  · exact Or.inl rfl

example :
    1 < Nat.gcd 6 (12 / 6) ↔
      ∃ prime, Nat.Prime prime ∧
        prime ∣ 6 ∧ prime * prime ∣ 12 := by
  exact one_lt_gcd_iff_exists_product_prime_square_dvd
    (by norm_num) (by norm_num) six_squarefree
    Nat.prime_two.squarefree

example :
    ArithmeticFunction.cardDistinctFactors (6 * 5) % 2 =
      (ArithmeticFunction.cardDistinctFactors 6 +
        if 1 < 5 then 1 else 0) % 2 := by
  exact cardDistinctFactors_parity_product_residual
    (by decide) (Or.inr Nat.prime_five)

end SparkInterval.Tests.MobiusResidualGCDTest
