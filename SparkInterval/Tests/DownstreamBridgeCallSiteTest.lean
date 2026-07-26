/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/
import SparkInterval.Execution.RegisteredA7BoundaryCertificate
import SparkInterval.Execution.RegisteredCDEMAbelCertificate
import SparkInterval.Execution.RegisteredGoldbach10Pow27Certificate
import SparkInterval.Execution.RegisteredGoldbachCertificate
import SparkInterval.Execution.RegisteredHurstSharedCertificate
import SparkInterval.Execution.RegisteredPlattTheorem71Certificate
import SparkInterval.Execution.RegisteredProp1224Certificate
import SparkInterval.Execution.RegisteredPsiLemma92Certificate
import SparkInterval.Execution.RegisteredR2StarCertificate
import SparkInterval.Execution.RegisteredSqrt218Certificate
import SparkInterval.Execution.RegisteredZetaHeadCertificate
import SparkInterval.Execution.RegisteredZetaRHCertificate
import SparkInterval.Execution.RegisteredCubicSumCertificate
import SparkInterval.Execution.RegisteredSqrt218FixedV2Certificate

/-!
# Downstream bridge call-site compatibility test

Replicates, verbatim, every way the sibling theorem repository consumes the
fourteen registered-campaign modules: its ten
`MathExtras/NumberTheory/Analysis/*GPUProverBridge.lean` files,
`MathExtras/NumberTheory/Helfgott/Section24Sqrt218RegisteredProvider.lean`,
and `Math/Problems/TernaryGoldbach/AzureRegisteredSourceInputs.lean`.

Each theorem below uses the exact hypothesis spelling and the exact field
projection the downstream file uses, with that campaign's own source
proposition as the conclusion.  If any of these stops elaborating, a
downstream bridge is broken -- which this repository would otherwise not
discover, because the consumer lives in a different repository.

This module installs no receipt, executes no campaign, and asserts no
unconditional claim: every statement is conditional on a checked receipt that
does not exist.
-/

set_option autoImplicit false
set_option linter.unusedVariables false

namespace SparkInterval.Tests.DownstreamBridgeCallSite

open SparkInterval.Execution

/-! CH25A7BoundaryGPUProverBridge.lean:91-95 -/
theorem a7 {certificate : SignedResultCertificate}
    (hcheck : certificate.ch25A7BoundaryProductionCheck = true) :
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyCH25A7Boundary hcheck).sourceClaim

/-! CH25PsiGPUProverBridge.lean:65-69 -/
theorem psi {certificate : SignedResultCertificate}
    (hcheck : certificate.ch25PsiLemma92ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyCH25PsiLemma92 hcheck).sourceClaim

/-! PlattHeadGPUProverBridge.lean:251-256 (projects `.sourceClaim.2`) -/
theorem plattHead {certificate : SignedResultCertificate}
    (hcheck : certificate.plattHead2e4ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.Q128SourceClaim
      SparkInterval.Generated.PlattHeadQ128.table :=
  (SignedResultCertificate.certifyPlattHead2e4 hcheck).sourceClaim.2

/-! PlattTrudgianRHGPUProverBridge.lean:50-54 -/
theorem rh {certificate : SignedResultCertificate}
    (hcheck : certificate.plattTrudgianFiniteRHProductionCheck = true) :
    SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyPlattTrudgianFiniteRH hcheck).sourceClaim

/-! PlattDirichletGPUProverBridge.lean:52-56 -/
theorem dirichlet {certificate : SignedResultCertificate}
    (hcheck : certificate.plattDirichletTheorem71ProductionCheck = true) :
    SparkInterval.Dirichlet.PlattTheorem71DirichletVerification :=
  (SignedResultCertificate.certifyPlattDirichletTheorem71 hcheck).sourceClaim

/-! Prop1224GPUProverBridge.lean:203-207 -/
theorem prop1224 {certificate : SignedResultCertificate}
    (hcheck : certificate.helfgottProp1224ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyHelfgottProp1224 hcheck).sourceClaim

/-! RamareZunigaLemma62GPUProverBridge.lean:98-102 -/
theorem r2star {certificate : SignedResultCertificate}
    (hcheck : certificate.ramareZunigaLemma62ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.R2StarSourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyRamareZunigaLemma62 hcheck).sourceClaim

/-! CohenDressElMarrakiGPUProverBridge.lean:180-184 -/
theorem cdemSourceClaim {certificate : SignedResultCertificate}
    (hcheck : certificate.cdemTableAbelProductionCheck = true) :
    SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim :=
  (SignedResultCertificate.certifyCDEMTableAbel hcheck).sourceClaim

/-! CohenDressElMarrakiGPUProverBridge.lean:158-163 (takes the structure as a
hypothesis and projects `.scaledNumerators`) -/
theorem cdemScaled {certificate : SignedResultCertificate}
    (certified : CertifiedCDEMTableAbel certificate) :
    SparkInterval.TernaryGoldbach.CDEMAbelSource.ScaledOutputClaim
      SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
      SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget :=
  certified.scaledNumerators

/-! CohenDressElMarrakiGPUProverBridge.lean:190-195 (composition of both) -/
theorem cdemScaledOfCheck {certificate : SignedResultCertificate}
    (hcheck : certificate.cdemTableAbelProductionCheck = true) :
    SparkInterval.TernaryGoldbach.CDEMAbelSource.ScaledOutputClaim
      SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
      SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget :=
  cdemScaled (SignedResultCertificate.certifyCDEMTableAbel hcheck)

/-! HurstGPUProverBridge.lean:177-182 (projects `.sharedRealClaims`) -/
theorem hurstShared {certificate : SignedResultCertificate}
    (hcheck : certificate.hurstSharedFourResidualProductionCheck = true) :
    TGComputeContracts.HurstV2.RealSourceClaims :=
  (SignedResultCertificate.certifyHurstSharedFourResidual hcheck).sharedRealClaims

/-! HurstGPUProverBridge.lean also reaches `.realClaims` and `.sourceClaims` -/
theorem hurstReal {certificate : SignedResultCertificate}
    (hcheck : certificate.hurstSharedFourResidualProductionCheck = true) :
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.RealSourceClaims :=
  (SignedResultCertificate.certifyHurstSharedFourResidual hcheck).realClaims

theorem hurstRows {certificate : SignedResultCertificate}
    (hcheck : certificate.hurstSharedFourResidualProductionCheck = true) :
    ∀ n, 1 ≤ n → n ≤ SparkInterval.TernaryGoldbach.HurstSourceSemantics.sourceLimit →
      ∃ state : SparkInterval.TernaryGoldbach.HurstAffineCertificate.State,
        SparkInterval.TernaryGoldbach.HurstSourceSemantics.SourceRowPredicate n state :=
  (SignedResultCertificate.certifyHurstSharedFourResidual hcheck).sourceClaims

/-! HelfgottPlattGPUProverBridge.lean:76-81 -/
theorem helfgottPlatt {certificate : SignedResultCertificate}
    (hcheck : certificate.helfgottPlattGoldbachProductionCheck = true) :
    SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyHelfgottPlattGoldbach hcheck).sourceClaim

/-! Goldbach10Pow27GPUProverBridge.lean:41-46 -/
theorem goldbach10Pow27 {certificate : SignedResultCertificate}
    (hcheck : certificate.goldbach10Pow27ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyGoldbach10Pow27 hcheck).sourceClaim

/-! Section24Sqrt218RegisteredProvider.lean:27-31 -/
theorem sqrt218 {certificate : SignedResultCertificate}
    (hcheck : certificate.helfgottSqrt218ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim :=
  (SignedResultCertificate.certifyHelfgottSqrt218 hcheck).sourceClaim

/-! Math/Problems/TernaryGoldbach/AzureRegisteredSourceInputs.lean and
AzureConditional10Pow27.lean take nine of these checks simultaneously as
hypotheses.  This reproduces that hypothesis block shape. -/
theorem nineCheckHypothesisBlock
    {a7Certificate psiCertificate plattHeadCertificate rhCertificate
      prop1224Certificate tableCertificate hurstCertificate
      dirichletCertificate r2Certificate : SignedResultCertificate}
    (hA7 : a7Certificate.ch25A7BoundaryProductionCheck = true)
    (hPsi : psiCertificate.ch25PsiLemma92ProductionCheck = true)
    (hHead : plattHeadCertificate.plattHead2e4ProductionCheck = true)
    (hRH : rhCertificate.plattTrudgianFiniteRHProductionCheck = true)
    (hProp1224 : prop1224Certificate.helfgottProp1224ProductionCheck = true)
    (hTable : tableCertificate.cdemTableAbelProductionCheck = true)
    (hHurst : hurstCertificate.hurstSharedFourResidualProductionCheck = true)
    (hDirichlet :
      dirichletCertificate.plattDirichletTheorem71ProductionCheck = true)
    (hR2 : r2Certificate.ramareZunigaLemma62ProductionCheck = true) :
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim ∧
      SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceClaim ∧
      SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.SourceClaim ∧
      SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.SourceClaim ∧
      SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim ∧
      TGComputeContracts.HurstV2.RealSourceClaims ∧
      SparkInterval.Dirichlet.PlattTheorem71DirichletVerification ∧
      SparkInterval.TernaryGoldbach.R2StarSourceSemantics.SourceClaim :=
  ⟨a7 hA7, psi hPsi, rh hRH, prop1224 hProp1224, cdemSourceClaim hTable,
    hurstShared hHurst, dirichlet hDirichlet, r2star hR2⟩

/-! ## Axiom table for all fourteen campaigns

The complete expected set is the base trio plus the repository's single
`Trusted.accepted_run_certificate_sound` execution boundary.  Printing all
fourteen in one place makes an unintended trust change visible in one diff. -/

#print axioms SignedResultCertificate.certifyCH25A7Boundary
#print axioms SignedResultCertificate.certifyCDEMTableAbel
#print axioms SignedResultCertificate.certifyCubicSumDivThree20000
#print axioms SignedResultCertificate.certifyGoldbach10Pow27
#print axioms SignedResultCertificate.certifyHelfgottPlattGoldbach
#print axioms SignedResultCertificate.certifyHurstSharedFourResidual
#print axioms SignedResultCertificate.certifyPlattDirichletTheorem71
#print axioms SignedResultCertificate.certifyHelfgottProp1224
#print axioms SignedResultCertificate.certifyCH25PsiLemma92
#print axioms SignedResultCertificate.certifyRamareZunigaLemma62
#print axioms SignedResultCertificate.certifyHelfgottSqrt218
#print axioms SignedResultCertificate.certifyHelfgottSqrt218FixedV2
#print axioms SignedResultCertificate.certifyPlattHead2e4
#print axioms SignedResultCertificate.certifyPlattTrudgianFiniteRH

/-! And the downstream-facing consumers themselves. -/

#print axioms a7
#print axioms cdemScaledOfCheck
#print axioms hurstShared
#print axioms plattHead
#print axioms nineCheckHypothesisBlock

end SparkInterval.Tests.DownstreamBridgeCallSite
