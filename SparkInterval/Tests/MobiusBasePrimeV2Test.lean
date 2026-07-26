/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Generated.MobiusBasePrimeV2

set_option maxRecDepth 100000
set_option maxHeartbeats 0

open SparkInterval.Generated.MobiusBasePrimeV2

-- Runtime validation of the materialized base data.  The public theorem
-- remains conditional, so normal proof elaboration does not replay this.
#guard certificateCheck

#print axioms
  SparkInterval.Generated.MobiusBasePrimeV2.primeRosterThrough
#print axioms
  SparkInterval.Generated.MobiusBasePrimeV2.productionCheck_sound
