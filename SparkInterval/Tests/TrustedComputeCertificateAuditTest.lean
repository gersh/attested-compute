/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Audit.TrustedComputeCertificates
import SparkInterval.Execution.RegisteredCubicSumCertificate

/-!
# Trusted-compute certificate audit command tests

The live registry is intentionally empty, so there is not yet a genuine
closed receipt theorem to use as a positive fixture.  These commands exercise
the axiom-free case and demonstrate that the current generic bridge is
reported as an unattributed axiom path.  A production generated receipt module
will provide the positive `COVERED` case by using
`acceptedRunCertificateForReceipt` with a literal receipt hash.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.TrustedComputeCertificateAudit

theorem axiomFreeExample : True := True.intro

/-- A higher-order/partial reference is not a concrete receipt use.  This is
an axiom-free regression fixture for the wrapper-spine laundering case. -/
abbrev partialReceiptWrapper :=
  SparkInterval.Execution.Trusted.acceptedRunCertificateForReceipt
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

-- Fail-closed root-axiom classification: an arbitrary helper axiom and the
-- compiler-backed native reduction axiom are rejected, while the disclosed
-- foundations are accepted.  Using bare names here tests the collector logic
-- without introducing a second source axiom into the repository.
#guard SparkInterval.Audit.unexpectedCertificateRootAxioms
  #[``propext, ``Classical.choice, ``Quot.sound,
    ``SparkInterval.Execution.Trusted.accepted_run_certificate_sound,
    `SparkInterval.Tests.syntheticFakeAccepted] ==
  #[`SparkInterval.Tests.syntheticFakeAccepted]
#guard !SparkInterval.Audit.isAllowedCertificateRootAxiom ``Lean.ofReduceBool

/-- error: certificate audit failed -/
#guard_msgs (error, drop info, substring := true) in
#audit certificates partialReceiptWrapper

#print certificates axiomFreeExample
#audit certificates axiomFreeExample

-- This reads actual declarations from the loaded kernel environment.  It is
-- not vulnerable to spelling an axiom as `constant` or creating one through
-- an elaborator.
#print project axioms
#audit project axioms

-- The report must say `FAIL_UNATTRIBUTED`, name the generic axiom path, and
-- contain zero concrete receipts.  `#audit certificates` would deliberately
-- reject this declaration, so this compile-only regression uses the printing
-- form.
#print certificates
  SparkInterval.Execution.SignedResultCertificate.certifyCubicSumDivThree20000

end SparkInterval.Tests.TrustedComputeCertificateAudit
