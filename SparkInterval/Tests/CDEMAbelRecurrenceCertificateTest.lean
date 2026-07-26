/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate

/-!
# Interface tests for the CDEM recurrence certificate

These examples do not fabricate physical source-scale evidence and do not run
the five-billion-row computation.  They pin the checker and theorem
interfaces that a registered production receipt must use.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CDEMAbelRecurrenceCertificate

open SparkInterval.TernaryGoldbach
open CDEMAbelRecurrenceCertificate

/-- The compact checker exposes its full arithmetic invariant. -/
example {certificate : Certificate}
    (hcheck : certificate.check = true) :
    ChainValid 1 0 certificate.chunks ∧
      certificate.signedTotal ≤ (certificate.signedNumerator : Int) ∧
      certificate.absoluteTotal ≤ certificate.absoluteNumerator :=
  Certificate.check_sound hcheck

/-- New materializers can expose only local recurrence and local-fold
evidence; checked chaining derives the global source proposition. -/
example {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate) :
    CDEMAbelSource.ScaledOutputClaim certificate.signedNumerator
      certificate.absoluteNumerator :=
  scaledOutputClaim_of_checked_local_certificate hcheck evidence

/-- The narrow local interface transports to the established global one. -/
example {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : LocalSourceScaleEvidence certificate) :
    SourceScaleEvidence certificate :=
  sourceScaleEvidence_of_local hcheck evidence

/-- Existing receipt evidence has an explicit compatibility path to the new
local interface, so the registered axiom need not change. -/
example {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) :
    LocalSourceScaleEvidence certificate :=
  localSourceScaleEvidence_of_source hcheck evidence

/-- The established registered bridge continues to consume recurrence
evidence rather than postulating the final real inequalities. -/
example {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate) :
    CDEMAbelSource.ScaledOutputClaim certificate.signedNumerator
      certificate.absoluteNumerator :=
  scaledOutputClaim_of_checked_certificate hcheck evidence

/-- The exact production numerators recover the source-shaped proposition. -/
example {certificate : Certificate}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence certificate)
    (hsigned :
      certificate.signedNumerator = CDEMAbelSource.signedTarget)
    (habsolute :
      certificate.absoluteNumerator = CDEMAbelSource.absoluteTarget) :
    CDEMAbelSource.SourceClaim :=
  sourceClaim_of_checked_production_certificate
    hcheck evidence hsigned habsolute

#print axioms floorState_jump
#print axioms floorSum_eq_floorState_cast
#print axioms sourceScaleEvidence_of_local
#print axioms localSourceScaleEvidence_of_source
#print axioms scaledOutputClaim_of_checked_local_certificate
#print axioms scaledOutputClaim_of_checked_certificate
#print axioms sourceClaim_of_checked_local_production_certificate
#print axioms sourceClaim_of_checked_production_certificate

end SparkInterval.Tests.CDEMAbelRecurrenceCertificate
