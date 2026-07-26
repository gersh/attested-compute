/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.TMajorFactorRecurrence

set_option autoImplicit false

namespace SparkInterval.Tests.TMajorFactorRecurrence

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk
open SparkInterval.Dirichlet.TMajorFactorRecurrence

def seed : ComplexDisk := ⟨1, 0, 0⟩
def step : ComplexDisk := ⟨0, 1, 0⟩
def product : ComplexDisk := ⟨0, 1, 0⟩

def certificate : ComplexDisk.MulCertificate where
  left := seed
  right := step
  output := product
  centerErrorBound := 0
  leftCenterNormBound := 1
  rightCenterNormBound := 1

theorem certificate_check : certificate.check = true := by
  norm_num [certificate, seed, step, product,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem sample_chain : Chain seed step [certificate] := by
  exact ⟨rfl, rfl, certificate_check, trivial⟩

example {x y : ℂ}
    (hx : seed.ContainsComplex x)
    (hy : step.ContainsComplex y) :
    (output seed [certificate]).ContainsComplex (x * y) := by
  simpa using output_contains_pow sample_chain hx hy

#print axioms output_contains_pow

end SparkInterval.Tests.TMajorFactorRecurrence
