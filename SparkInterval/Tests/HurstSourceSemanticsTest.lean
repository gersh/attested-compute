/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstSourceSemantics

set_option autoImplicit false

namespace SparkInterval.Tests.HurstSourceSemantics

open SparkInterval.TernaryGoldbach.HurstAffineCertificate
open SparkInterval.TernaryGoldbach.HurstSourceSemantics

example : HurstSafeAt 100 ⟨5, 0, 0, 0⟩ := by
  norm_num [HurstSafeAt]
example : ¬HurstSafeAt 100 ⟨6, 0, 0, 0⟩ := by
  norm_num [HurstSafeAt]

example : LittleIntervalSafe 2 false
    ⟨0, 0, -(littleScale : Int), littleScale⟩ := by
  norm_num [LittleIntervalSafe, LittleEndpointSafe, littleScale]

example : ¬LittleIntervalSafe 3 true
    ⟨0, 0, -(littleScale : Int), littleScale⟩ := by
  norm_num [LittleIntervalSafe, LittleEndpointSafe, littleScale]

/-- The V2 predicate checks the integer value at each strict-real squarefree
threshold, not merely the right limit. -/
example {state : State} (h : SourceRowSafe 9_243 state) :
    SquarefreeSafeAt 9_243 state.squarefree 151 2_000 :=
  h.2.1 (by norm_num)

example {state : State} (h : SourceRowSafe 438_429 state) :
    SquarefreeSafeAt 438_429 state.squarefree 57 2_000 :=
  h.2.2.2.1 (by norm_num)

example :
    DensityEnclosure ((densityLower : Real) / densityScale) := by
  constructor
  · rfl
  · norm_num [densityLower, densityUpper, densityScale]

#print axioms mertensStep_eq_sourceSum
#print axioms littleMertensStep_eq_sourceSum
#print axioms squarefreeStep_eq_sourceSum
#print axioms mertensPrefix_succ
#print axioms squarefreePrefix_succ
#print axioms littleMertensPrefix_succ
#print axioms prefixRealization_add_sourceRowDelta
#print axioms checked_full_source_claims_of_local
#print axioms checked_full_source_claims
#print axioms checked_hurst_endpoint
#print axioms checked_squarefree_endpoints
#print axioms checked_little211_endpoint
#print axioms checked_little_stronger_endpoint
#print axioms densityEnclosure_six_div_pi_sq
#print axioms checked_hurst_real
#print axioms checked_squarefree_b1_real
#print axioms checked_squarefree_b2_real
#print axioms checked_little211_real
#print axioms checked_little_stronger_real
#print axioms checked_real_source_claims
#print axioms checked_real_source_claims_of_local
#print axioms checked_shared_real_source_claims
#print axioms checked_shared_real_source_claims_of_local

end SparkInterval.Tests.HurstSourceSemantics
