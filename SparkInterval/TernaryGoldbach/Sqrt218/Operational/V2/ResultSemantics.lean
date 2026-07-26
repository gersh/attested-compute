/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.IR
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Arithmetic meaning of the Sqrt218 V2 native result

The receipt-only wire parser depends only on fixed two-limb data types.
This separate, still registry-independent module joins those fields to the
architecture-neutral arithmetic result used by the complete V2 checker.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

namespace NativeResultRecord

/-- Direct architecture-neutral arithmetic result represented by the six
state limbs and two slack limbs in the native result. Acceptance is checked
separately by `acceptedResultCheck`. -/
def arithmeticResult (record : NativeResultRecord) : ArithmeticResult := {
  state := {
    nextEvent := record.nextEventIndex
    lastEventValue := record.lastEventValue
    weightedUpper := record.weightedUpper
    psiLower := record.psiLower
  }
  anchorSlack := record.anchorSlack
}

end NativeResultRecord

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire
