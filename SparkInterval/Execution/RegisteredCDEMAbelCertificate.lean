/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredCampaignCertificate

/-!
# Registered trusted-compute bridge for the CDEM Abel scan

This is the first production ternary-Goldbach external-atom vertical slice.
The closed invocation fixes `K = 199330`, `N = 5000000000`, the scale, the
Möbius/floor-error definitions, and an Azure SEV-SNP CPU deployment.  The
returned decimal natural is decoded by Mathlib's injective `Nat.pair`; its two
components are tied to the fixed generated recurrence certificate and its
`LocalSourceScaleEvidence`.  Ordinary Lean transports those local states by
`floorState_jump` and derives the fixed `ScaledOutputClaim` semantics in
`CDEMAbelSource`.  The older global `SourceScaleEvidence` remains available
only as an off-path compatibility API in the recurrence module.

The application check additionally requires the exact production result
bytes.  Once the sole trusted-run axiom supplies the registered `Runs` fact,
all decoding and the passage to the exact two-conjunct source proposition are
ordinary kernel-checked Lean theorems.

This campaign is an instantiation of the generic layer in
`SparkInterval.Execution.RegisteredCampaignCertificate`: the check is
`productionCheck` at this invocation and output, and the shared conclusions
come from `certifyRun`.  What remains campaign-specific is exactly the two
pieces of data this campaign owns — the proof that its decimal expected
output is not the failure token, and the `Nat.pair` decoding of that output.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- Closed production invocation for the five-billion-step Abel scan. -/
def cdemTableAbelProductionInvocation : RegisteredInvocation :=
  .cdemTableAbelProductionV2

/-- Canonical compact result for the two reviewed directed numerators. -/
def cdemTableAbelProductionOutput : String :=
  RegisteredAlgorithm.cdemTableAbelProductionOutput

namespace SignedResultCertificate

/-- Production application check: closed invocation, accepted receipt,
exact result/hash binding, and exact expected numerator-pair bytes. -/
def cdemTableAbelProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.productionCheck cdemTableAbelProductionInvocation
    cdemTableAbelProductionOutput

end SignedResultCertificate

/-- The canonical CDEM numerator-pair payload is a decimal `Nat.repr`, hence
never the failure token.  This is the one campaign-specific fact the generic
non-failure combinator needs. -/
theorem cdemTableAbelProductionOutput_ne_failure :
    cdemTableAbelProductionOutput ≠ "false" := by
  intro hfailure
  have hparsed := congrArg String.toNat? hfailure
  have hfalseParse : String.toNat? "false" = none := by
    apply String.toNat?_eq_none
    rw [Bool.eq_false_iff]
    intro hnat
    have hdigits := (String.isNat_iff.mp hnat).2.1
    have hf := hdigits 'f' (by simp)
    simp at hf
  have hproductionParse :
      String.toNat? cdemTableAbelProductionOutput =
        some (Nat.pair
          SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
          SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget) := by
    change
      (Nat.repr (Nat.pair
        SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
        SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget)).toNat? =
          some (Nat.pair
            SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
            SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget)
    exact Nat.toNat?_repr _
  rw [hproductionParse, hfalseParse] at hparsed
  cases hparsed

/-- Everything recovered from one accepted production CDEM receipt. -/
structure CertifiedCDEMTableAbel
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    cdemTableAbelProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = cdemTableAbelProductionOutput
  statementResult_eq :
    certificate.statement.result = cdemTableAbelProductionOutput
  execution :
    AlgorithmReturned certificate.statement cdemTableAbelProductionOutput
  recurrenceCheck :
    SparkInterval.Generated.CDEMAbelProduction.certificate.check = true
  localSourceScaleEvidence :
    Nonempty
      (SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence
        SparkInterval.Generated.CDEMAbelProduction.certificate)
  scaledNumerators :
    SparkInterval.TernaryGoldbach.CDEMAbelSource.ScaledOutputClaim
      SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
      SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget
  sourceClaim : SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim

namespace SignedResultCertificate

/-- End-to-end theorem reducing an accepted production result to the exact
source-shaped CDEM Abel proposition.

The only project axiom on this theorem's path is the repository's single
`accepted_run_certificate_sound` boundary.  The output equality, `Nat.pair`
decoding, scaled-to-rational conversion, and complete mathematical
proposition are checked by the Lean kernel. -/
theorem certifyCDEMTableAbel
    {certificate : SignedResultCertificate}
    (hcheck : certificate.cdemTableAbelProductionCheck = true) :
    CertifiedCDEMTableAbel certificate := by
  have run : CertifiedRun certificate cdemTableAbelProductionInvocation
      cdemTableAbelProductionOutput := certifyRun hcheck
  have houtput := run.resultCertificate_eq
  have hsource :=
    run.claim RegisteredInvocation.cdemTableAbelProductionV2_sourceClaim
  rcases
      RegisteredInvocation.cdemTableAbelProductionV2_result run.certified.run
        (run.nonFailure cdemTableAbelProductionOutput_ne_failure) with
    ⟨hencoded, hrecurrenceCheck, hlocalSourceScaleEvidence, hscaled⟩
  have htargets :
      SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator =
          SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget ∧
        SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator =
          SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget := by
    have hpair :
        Nat.pair
            SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
            SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator =
          Nat.pair
            SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
            SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget := by
      have htext :
          toString (Nat.pair
              SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
              SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator) =
            toString (Nat.pair
              SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
              SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget) := by
        exact hencoded.symm.trans (houtput.trans (by
          rfl))
      change
        Nat.repr (Nat.pair
            SparkInterval.Generated.CDEMAbelProduction.certificate.signedNumerator
            SparkInterval.Generated.CDEMAbelProduction.certificate.absoluteNumerator) =
          Nat.repr (Nat.pair
            SparkInterval.TernaryGoldbach.CDEMAbelSource.signedTarget
            SparkInterval.TernaryGoldbach.CDEMAbelSource.absoluteTarget) at htext
      exact Nat.repr_injective htext
    exact Nat.pair_eq_pair.mp hpair
  rcases htargets with ⟨hsigned, habsolute⟩
  rw [hsigned, habsolute] at hscaled
  exact {
    certified := run.certified
    resultCertificate_eq := run.resultCertificate_eq
    statementResult_eq := run.statementResult_eq
    execution := run.execution
    recurrenceCheck := hrecurrenceCheck
    localSourceScaleEvidence := hlocalSourceScaleEvidence
    scaledNumerators := hscaled
    sourceClaim := hsource
  }

end SignedResultCertificate

end SparkInterval.Execution
