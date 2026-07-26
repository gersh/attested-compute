/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone

set_option autoImplicit false

namespace SparkInterval.Tests.StaticCPUExecutableCertificateTest

open SparkInterval.Execution.Architecture
open
  SparkInterval.Execution.Architecture.StaticCPUExecutableCertificate
open
  SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone
open
  SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone.StaticCPU

/-- The static-CPU roster covers all ten CPU-terminal external
campaigns. -/
example : FixedCampaign.all.length = 10 := by
  rfl

/-- Every roster entry has the closed CPU terminal target. -/
example (campaign : FixedCampaign) :
    campaign.invocation.terminalTarget = .azureSEVSNPCPU :=
  campaign.terminalTarget

/-- The Ramaré--Zúñiga H100 producer is authorized only through its measured
CPU finalizer. -/
example :
    RegisteredArchitectureInvocation.ramareZunigaLemma62ProductionV1.terminalTarget =
      .azureSEVSNPCPU := by
  rfl

/-- Generic installed certificates expose an actual installed reviewed run. -/
example
    {invocation : RegisteredArchitectureInvocation}
    {checker : NativeCheckerSemantics}
    (certificate : InstalledCertificate invocation checker) :
    ∃ reviewed : ReviewedArchitectureRun invocation,
      invocation.reviewedRun = some reviewed :=
  certificate.installedRunExists

/-- One installed A7 static-CPU certificate supplies the exact closed
refinement expected by the external capstone. -/
example
    (certificate : A7BoundaryInstalledCertificate) :
    ClosedExecutableRefinement
      .ch25A7BoundaryProductionV1
      SparkInterval.TernaryGoldbach.A7BoundaryCompactChecker.nativeChecker :=
  a7BoundaryClosedExecutableRefinement certificate

#print axioms StaticPureEntryRefinement.elfISARefinesLinkedBehavior
#print axioms Certificate.architectureRefinement
#print axioms InstalledCertificate.installedRunExists
#print axioms InstalledCertificate.closedRefinement
#print axioms FixedCampaign.closedExecutableRefinement
#print axioms a7BoundaryClosedExecutableRefinement

end SparkInterval.Tests.StaticCPUExecutableCertificateTest
