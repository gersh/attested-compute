/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge
import SparkInterval.TernaryGoldbach.ClosedSourceProgramCatalog

set_option autoImplicit false

namespace SparkInterval.Tests.ClosedSourceProgramCatalog

open SparkInterval.Execution.Architecture
open SparkInterval.Dirichlet
open SparkInterval.TernaryGoldbach
open SparkInterval.TernaryGoldbach.ClosedSourceProgramCatalog

example :
    Campaign.all.map Campaign.invocation =
      RegisteredArchitectureInvocation.externalCampaigns ++
        RegisteredArchitectureInvocation.nativeFamilyFallbacks :=
  invocationRoster_exact

example : Campaign.all.length = 11 :=
  auditedCampaignCount

example (campaign : Campaign)
    (notCDEM : campaign ≠ Campaign.cdemTableAbel) :
    isConcrete campaign = false :=
  noConcreteCampaign campaign notCDEM

example : Campaign.all.filter isConcrete = [.cdemTableAbel] :=
  concreteCampaigns

example : (Campaign.all.filter isConcrete).length = 1 :=
  concreteCampaignCount

example :
    isConcrete Campaign.cdemTableAbel = true := by
  rfl

example :
    status Campaign.cdemTableAbel =
      .artifactConcrete cdemAbelConcrete :=
  cdemAbel_status_concrete

#check cdemAbelConcrete.certificate
#check cdemAbelConcrete.projectedCertificate
#check CDEMAbelArtifactProgram.sourceClaim_of_artifact_acceptance
#check CDEMAbelArtifactProgram.legacy_accepts_of_artifact_acceptance

example :
    plattDirichletMissing.existingPieces.contains
      "FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.check" =
        true := by
  decide

example :
    goldbachMissing.existingPieces.contains
      "GoldbachSourceSemantics.PrimeLadder.check" = true := by
  decide

-- Every declaration advertised as an existing partial component is resolved
-- by Lean; the strings in the audit catalog are therefore not stale guesses.
#check A7BoundaryCertificate.Certificate.check
#check A7BoundaryCertificate.Certificate.accepted_of_check_eq_true
#check A7BoundaryCertificate.sourceClaim_of_checked_certificate
#check PsiPrimePowerCertificate.sourceClaim_of_gap_evidence
#check PsiSourceSemantics.lowerEndpointSafe_real
#check PsiSourceSemantics.upperEndpointSafe_real
#check ZetaHeadSourceSemantics.Q128CellTable.commitment
#check SparkInterval.Zeta.RationalBracketFamily.check
#check ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence
#check SparkInterval.Zeta.RationalEndpointChunk.check
#check SparkInterval.Zeta.checkEndpointChunkStream
#check SparkInterval.Zeta.checkEndpointChunkStream_sound
#check ZetaRHSourceSemantics.sourceClaim_of_evidence
#check Prop1224SourceSemantics.Certificate.check
#check Prop1224SourceSemantics.Certificate.checker_sound
#check Prop1224SourceSemantics.sourceClaim_of_checked_certificate
#check HurstAffineCertificate.Certificate.check
#check HurstAffineCertificate.Certificate.checker_sound
#check HurstSourceSemantics.checked_shared_real_source_claims_of_local
#check CDEMAbelRecurrenceCertificate.Certificate.check
#check CDEMAbelReplayAlgorithm.scanSteps
#check CDEMAbelReplayAlgorithm.replayOutput
#check CDEMAbelReplayAlgorithm.locallyRealizes_of_accepts
#check CDEMAbelReplayAlgorithm.Supervisor.sourceClaim_of_acceptance
#check R2StarSourceSemantics.Certificate.check
#check R2StarSourceSemantics.Certificate.checker_sound
#check R2StarSourceSemantics.sourceClaim_of_checked_certificate
#check GoldbachSourceSemantics.PrimeLadder.check
#check GoldbachSourceSemantics.PrimeLadder.check_sound
#check GoldbachSourceSemantics.sourceClaim_of_checked_evidence
#check FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.check
#check
  FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.checker_sound
#check
  FactoredSmallQRosterGRHBridge.grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies_of_two_le
#check SparkInterval.Dirichlet.plattTheorem71_of_source_evidence
#check RamareNativeFoldContracts.ScaledIntervalFold.realizes
#check RamareNativeFoldContracts.sourceClaims_of_finiteFoldEvidence

#print axioms invocationRoster_exact
#print axioms cdemAbel_status_concrete
#print axioms noConcreteCampaign
#print axioms concreteCampaigns
#print axioms concreteCampaignCount

end SparkInterval.Tests.ClosedSourceProgramCatalog
