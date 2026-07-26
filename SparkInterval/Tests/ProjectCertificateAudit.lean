/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution

/-!
# Whole-production-environment certificate audit

`SparkInterval.Execution` is the aggregate production certificate API import.
Running the project command here makes its loaded-environment scope explicit
and prevents a narrower test import from being mistaken for the production
certificate inventory. The live receipt registry is intentionally empty, so
zero concrete sites is a valid passing result.
-/

#audit project certificates
