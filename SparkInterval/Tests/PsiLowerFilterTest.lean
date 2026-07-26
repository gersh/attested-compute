/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiLowerFilter

set_option autoImplicit false

namespace SparkInterval.Tests.PsiLowerFilterTest

open SparkInterval.TernaryGoldbach.PsiLowerFilter

example :
    (10 * 10 < 101 ∨ (False ∧ 10 * 10 ≤ 101)) ↔
      10 ≤ Nat.sqrt 101 ∧
        (10 < Nat.sqrt 101 ∨ False ∨
          Nat.sqrt 101 * Nat.sqrt 101 < 101) :=
  strict_accept_square_iff 101 10 False

example : Nat.sqrt 100 < 11 ↔ 100 < 11 * 11 :=
  sqrt_lt_iff_bound_lt_square 100 11

#print axioms square_lt_iff_sqrt_boundary
#print axioms square_le_iff_le_sqrt
#print axioms strict_accept_square_iff
#print axioms sqrt_lt_iff_bound_lt_square

end SparkInterval.Tests.PsiLowerFilterTest
