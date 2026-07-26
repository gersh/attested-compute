/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusFusedSupport

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusFusedSupportTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport

example : pack 1 0 false = 1 := by decide

example : pack (2 ^ 54 - 1) 31 true < 2 ^ 60 := by decide

example :
    pack 30 3 false ≠ pack 30 3 true := by decide

example : unpackProduct (pack 30 3 true) = 30 := by decide
example : unpackCount (pack 30 3 true) = 3 := by decide
example : unpackSquareful (pack 30 3 true) = true := by decide

example :
    update (update ⟨1, 0, false⟩ 2 true) 3 false =
      update (update ⟨1, 0, false⟩ 3 false) 2 true := by
  exact update_comm ⟨1, 0, false⟩ 2 3 true false

example :
    update ⟨1, 0, false⟩ 5 true =
      markSquareful
        (updateProductCount ⟨1, 0, false⟩ 5) true := by
  exact update_eq_markSquareful_updateProductCount
    ⟨1, 0, false⟩ 5 true

example :
    markSquareful
        (updateProductCount ⟨1, 0, false⟩ 5) true =
      updateProductCount
        (markSquareful ⟨1, 0, false⟩ true) 5 := by
  exact markSquareful_updateProductCount_comm
    ⟨1, 0, false⟩ 5 true

example :
    -(2 ^ 31 : Int) ≤ -100_000_000 ∧
      (-100_000_000 : Int) < 2 ^ 31 := by
  exact localMertens_fits_int32
    (count := 100_000_000) (delta := -100_000_000)
    (by decide) (by decide) (by decide)

#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.divisor_lt_productRadix
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.update_comm
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.update_eq_markSquareful_updateProductCount
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.markSquareful_updateProductCount_comm
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.localMertens_fits_int32
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.localSquarefree_fits_uint32
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.pack_injective
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackProduct_pack
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackCount_pack
#print axioms
  SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackSquareful_pack

end SparkInterval.Tests.MobiusFusedSupportTest
