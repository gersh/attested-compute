/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachPrimePrefixReuse

namespace SparkInterval.Tests.GoldbachPrimePrefixReuseTest

open TernaryGoldbach.GoldbachPrimePrefixReuse

example :
    (primeTable 1_000_000).filter (· ≤ 100_000) =
      primeTable 100_000 := by
  exact filter_primeTable_eq 100_000 1_000_000 (by norm_num)

example {n : Nat} :
    n ∈ (primeTable 176_776_695).filter (· ≤ 100_000_000) ↔
      n.Prime ∧ n ≤ 100_000_000 := by
  exact mem_filtered_primeTable_iff
    100_000_000 176_776_695 n (by norm_num)

end SparkInterval.Tests.GoldbachPrimePrefixReuseTest
