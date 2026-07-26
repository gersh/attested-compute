/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDisk

/-!
# Typed complex-disk recurrence boundary

This module composes the one-step exact-rational complex-disk multiplication
theorem into a recurrence theorem.  It is deliberately independent of the
experimental `TGDFREC1` byte format: a format-specific parser must still
recover these typed certificates, their order, the seed, and the fixed phase
step.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.TMajorFactorRecurrence

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk

/-- A typed recurrence chain.  Each certificate consumes the preceding disk,
uses the same phase-step disk, and passes the exact rational checker. -/
def Chain
    (seed step : ComplexDisk) :
    List ComplexDisk.MulCertificate → Prop
  | [] => True
  | certificate :: rest =>
      certificate.left = seed ∧
      certificate.right = step ∧
      certificate.check = true ∧
      Chain certificate.output step rest

/-- The final disk of a chain; an empty chain returns its seed. -/
def output :
    ComplexDisk → List ComplexDisk.MulCertificate → ComplexDisk
  | seed, [] => seed
  | _, certificate :: rest => output certificate.output rest

/-- Every accepted typed chain encloses the corresponding repeated complex
multiplication.  No floating-point operation, FFI, or `native_decide`
participates in this theorem. -/
theorem output_contains_pow
    {seed step : ComplexDisk}
    {certificates : List ComplexDisk.MulCertificate}
    {x y : ℂ}
    (hchain : Chain seed step certificates)
    (hseed : seed.ContainsComplex x)
    (hstep : step.ContainsComplex y) :
    (output seed certificates).ContainsComplex
      (x * y ^ certificates.length) := by
  induction certificates generalizing seed x with
  | nil =>
      simpa [output] using hseed
  | cons certificate rest inductionHypothesis =>
      rcases hchain with ⟨hleft, hright, hcheck, hrest⟩
      have hproduct : certificate.output.ContainsComplex (x * y) := by
        apply ComplexDisk.MulCertificate.output_contains_mul hcheck
        · simpa [hleft] using hseed
        · simpa [hright] using hstep
      have htail :=
        inductionHypothesis hrest hproduct
      rw [output]
      convert htail using 1
      simp only [List.length_cons, pow_succ]
      ring

/-- The empty recurrence is a genuine seed statement rather than a vacuous
or contradictory parameter regime. -/
@[simp] theorem chain_nil (seed step : ComplexDisk) :
    Chain seed step [] := by
  trivial

end SparkInterval.Dirichlet.TMajorFactorRecurrence
