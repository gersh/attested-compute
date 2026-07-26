/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.LogRows

/-!
# Small regression checks for the Sqrt218 V2 log seeds

These guards evaluate only the fixed thirty-row seed table.  They prevent the
exact `log 1 = 0` seed from accidentally being sent back through a
nonzero-width interval enclosure, which would make every V2 production
certificate fail before its cloud-only replay.
-/

namespace SparkInterval.Tests.Sqrt218V2LogRows

open SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

#guard seedCellCheck 1
#guard seedCellCheck 2
#guard seedCellCheck seedAt
#guard seedTableCheck

example : (seed 1).Valid 1 := by
  simp [seed, TGComputeContracts.Sqrt218.LogBounds.Valid]

end SparkInterval.Tests.Sqrt218V2LogRows
