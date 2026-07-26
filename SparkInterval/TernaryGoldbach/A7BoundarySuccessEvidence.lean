/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundaryCertificate

/-!
# Closed success evidence for the CH25 Lemma A.7 transcript checker

The registered trusted-compute relation should expose a successful A.7 run
only when it retains the exact decoded transcript, a successful run of the
ordinary-Lean checker, and the explicit FLINT/Arb-to-Mathlib analytic
realization for that same transcript.

This small module is independent of the central execution registry.  It
packages that exact success boundary and proves its source consequence using
the transcript-checker soundness theorem.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence

open A7BoundaryCertificate

/-- Exact evidence retained by a successful registered A.7 run.

The existential binds the checked transcript and its analytic realization to
the same `Certificate`; neither component can be substituted independently.
-/
def SuccessEvidence : Prop :=
  ∃ certificate : Certificate,
    certificate.check = true ∧
      Nonempty (AnalyticRealization certificate)

/-- A transcript-shaped successful run implies the literal source claim in
ordinary Lean. -/
theorem sourceClaim_of_successEvidence
    (evidence : SuccessEvidence) :
    A7BoundarySourceSemantics.SourceClaim := by
  rcases evidence with ⟨certificate, hcheck, ⟨realization⟩⟩
  exact sourceClaim_of_checked_certificate hcheck realization

end SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence
