/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidue23571113BitRefinement

namespace SparkInterval.Tests.MobiusResidue23571113BitRefinementTest

open SparkInterval.TernaryGoldbach.MobiusResidue235711
open SparkInterval.TernaryGoldbach.MobiusResidue23571113
open SparkInterval.TernaryGoldbach.MobiusResidue23571113BitRefinement

example :
    cudaThirteenInitializerStep 13 (residueSeed235711Word 13) =
      residueSeed23571113Word 13 := by
  exact cudaThirteenInitializerStep_p11_eq 13

example :
    cudaThirteenInitializerStep 169 (residueSeed235711Word 169) =
      residueSeed23571113Word 169 := by
  exact cudaThirteenInitializerStep_p11_eq 169

example :
    cudaThirteenInitializerStep 17 (residueSeed235711Word 17) =
      residueSeed23571113Word 17 := by
  exact cudaThirteenInitializerStep_p11_eq 17

#print axioms cudaThirteenInitializerStep_p11_eq

end SparkInterval.Tests.MobiusResidue23571113BitRefinementTest
