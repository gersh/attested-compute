/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter

namespace SparkInterval.Tests.HurstAffineCandidateFilterTest

open SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter

example :
    57 * 57 ≤ 10 * 10 * 36 := by
  exact squared_bound_of_floor_sqrt_accept (r := 6) (y := 36)
    (by norm_num) (by norm_num)

example :
    10 * 10 * 35 < 61 * 61 := by
  exact squared_bound_fails_of_floor_sqrt_reject
    (L := 61) (C := 10) (r := 5) (y := 35)
    (by norm_num) (by norm_num) (by norm_num)

example
    {candidateApprox candidateExact witnessApprox witnessExact : Int}
    (hcandidate : LowerCorrectionValid candidateApprox candidateExact)
    (hwitness : LowerCorrectionValid witnessApprox witnessExact)
    (houtside : candidateApprox < witnessApprox - 1) :
    candidateExact < witnessExact :=
  lower_outside_threshold_strictly_below hcandidate hwitness houtside

example
    {candidateApprox candidateExact witnessApprox witnessExact : Int}
    (hcandidate : UpperCorrectionValid candidateApprox candidateExact)
    (hwitness : UpperCorrectionValid witnessApprox witnessExact)
    (houtside : witnessApprox + 1 < candidateApprox) :
    witnessExact < candidateExact :=
  upper_outside_threshold_strictly_above hcandidate hwitness houtside

example :
    lowerKey { value := 19, order := 7 } <
      lowerKey { value := 18, order := 0 } := by
  decide

example :
    lowerKey { value := 19, order := 7 } <
      lowerKey { value := 19, order := 8 } := by
  decide

example :
    upperKey { value := 18, order := 7 } <
      upperKey { value := 19, order := 0 } := by
  decide

example :
    upperKey { value := 19, order := 7 } <
      upperKey { value := 19, order := 8 } := by
  decide

#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.squared_bound_of_floor_sqrt_accept
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.squared_bound_fails_of_floor_sqrt_reject
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lower_outside_threshold_strictly_below
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upper_outside_threshold_strictly_above
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.exact_maximizer_inside_lower_threshold
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.exact_minimizer_inside_upper_threshold
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lowerKey_injective
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upperKey_injective
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lowerKey_min_assoc
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upperKey_min_assoc

end SparkInterval.Tests.HurstAffineCandidateFilterTest
