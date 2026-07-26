/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21Tile9Schedule

namespace SparkInterval.Tests.PT21Tile9ScheduleTest

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution
open SparkInterval.Zeta.WindowedRadix2
open SparkInterval.Zeta.PT21Tile9Schedule

#check positive_row_prefix
#check negative_row_prefix
#check positive_final_prefix
#check negative_final_prefix
#check positive_row_full_schedule
#check negative_row_full_schedule
#check positive_final_full_schedule
#check negative_final_full_schedule

#print axioms positive_row_prefix
#print axioms negative_row_prefix
#print axioms positive_final_prefix
#print axioms negative_final_prefix
#print axioms positive_row_full_schedule
#print axioms negative_row_full_schedule
#print axioms positive_final_full_schedule
#print axioms negative_final_full_schedule

end SparkInterval.Tests.PT21Tile9ScheduleTest
