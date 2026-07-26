/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Audit.TrustedComputeCertificates

/-!
# Project certificate audit fail-closed regressions

This deliberately small import keeps the negative scanner regression quick.
The separate `ProjectCertificateAudit` module checks the aggregate production
environment.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.ProjectCertificateAuditNegative

/-- A partial wrapper is not a concrete receipt site. -/
abbrev partialReceiptWrapper :=
  SparkInterval.Execution.Trusted.acceptedRunCertificateForReceipt
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

/-- A new generic caller cannot silently enlarge the reviewed direct-call
surface. This theorem introduces no additional axiom; it deliberately uses
the existing one through an unreviewed declaration for the audit regression. -/
theorem syntheticUnexpectedDirectCaller
    {certificate : SparkInterval.Execution.RunCertificate}
    (accepted : SparkInterval.Execution.checkTrustedCompute
      certificate.statement certificate.attestation = true) :
    certificate.ProducedOutcome :=
  SparkInterval.Execution.Trusted.accepted_run_certificate_sound accepted

-- One full-environment failure scan checks both independent rejection
-- conditions.
/-- error: project certificate audit failed: invalid_wrappers=1, unexpected_direct_callers=1 -/
#guard_msgs (error, drop info, substring := true) in
#audit project certificates

end SparkInterval.Tests.ProjectCertificateAuditNegative
