/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.ClosedSourceProgramCatalog
import SparkInterval.Zeta.PT21NativeBlockWire

/-!
# Focused audit for the four incomplete analytic artifact programs

These tests prevent a finite inner checker from being mistaken for a closed
source program.  The PT21 block checker is checked separately as the one new
finite primitive; it does not promote the finite-RH campaign.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.AnalyticArtifactBoundaryAudit

open SparkInterval.TernaryGoldbach.ClosedSourceProgramCatalog

def analyticCampaigns : List Campaign :=
  [.ch25A7Boundary, .ch25PsiLemma92, .plattHead2e4,
    .plattTrudgianRH3e12]

example : analyticCampaigns.length = 4 := by
  decide

example : analyticCampaigns.all (fun campaign => !isConcrete campaign) =
    true := by
  decide

example (campaign : Campaign)
    (notCDEM : campaign ≠ Campaign.cdemTableAbel) :
    isConcrete campaign = false := by
  exact noConcreteCampaign campaign notCDEM

-- These are the exact ordinary-theorem endpoints that future data-only
-- artifact programs must construct.
#check
  SparkInterval.TernaryGoldbach.A7BoundaryCertificate.sourceClaim_of_checked_certificate
#check
  SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_gap_evidence
#check
  SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence
#check
  SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.sourceClaim_of_evidence

-- The finite PT21 record primitive is available, while the encompassing
-- campaign deliberately remains missing.
#check SparkInterval.Zeta.PT21NativeBlockWire.checkBytes
#check SparkInterval.Zeta.PT21NativeBlockWire.checkBytes_sound

example :
    isConcrete Campaign.plattTrudgianRH3e12 = false :=
  noConcreteCampaign Campaign.plattTrudgianRH3e12 (by decide)

#print axioms SparkInterval.Zeta.PT21NativeBlockWire.checkBytes_sound
#print axioms
  SparkInterval.TernaryGoldbach.ClosedSourceProgramCatalog.noConcreteCampaign

end SparkInterval.Tests.AnalyticArtifactBoundaryAudit
