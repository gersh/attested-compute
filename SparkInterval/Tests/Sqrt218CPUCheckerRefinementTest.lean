/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.V2Adapter

/-!
# Symbolic Sqrt218 CPU-checker refinement audit

This file intentionally contains no closed archive.  It records the
data-independent event-loop and endpoint theorems and prints their kernel
dependencies without replaying production arithmetic.
-/

#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.stepRefinesKernel

#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.runArithmetic_refines_kernel

#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter.completeRun_arithmetic_refines

