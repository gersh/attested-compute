/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstAffineTerminalInvariants

set_option autoImplicit false

namespace SparkInterval.Tests.HurstAffineTerminalInvariantsTest

open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
open SparkInterval.TernaryGoldbach.HurstAffineTerminalInvariants

#check inputTotal_terminalDeltaValid
#check inputTotal_host_sanity_checks
#check rowCandidate_order_lt_twice_actual_length
#check pairedEndpointCandidate_order_lt_twice_actual_length
#check inputPrefixAt_squarefree_le_inputTotal

example :
    TerminalDeltaValid 5
      (inputTotal
        [ { mertens := -1, squarefree := 1 }
        , { mertens := 0, squarefree := 0 }
        , { mertens := 1, squarefree := 1 }
        , { mertens := 1, squarefree := 1 }
        , { mertens := -1, squarefree := 1 } ]) := by
  apply inputTotal_terminalDeltaValid
  intro row member
  simp only [List.mem_cons, List.not_mem_nil, or_false] at member
  rcases member with rfl | rfl | rfl | rfl | rfl <;>
    simp [PrefixInputRowValid]

#print axioms inputTotal_terminalDeltaValid
#print axioms rowCandidate_order_lt_twice_actual_length

end SparkInterval.Tests.HurstAffineTerminalInvariantsTest
