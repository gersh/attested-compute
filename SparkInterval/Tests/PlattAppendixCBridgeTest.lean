/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PlattAppendixCBridge

set_option autoImplicit false

namespace SparkInterval.Tests.PlattAppendixCBridgeTest

open SparkInterval.Zeta

example :
    SincInterpolationCertificate.sourceInterpolationError =
      PlattLemmaC3.sourceInterpolationBudget :=
  PlattAppendixCBridge.sourceErrorBudget_eq

#print axioms PlattAppendixCBridge.sourceErrorBudget_eq
#print axioms PlattAppendixCBridge.realization_of_appendixC

end SparkInterval.Tests.PlattAppendixCBridgeTest
