/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.HurstSourceSemantics

/-!
# Registered trusted-compute bridge for the shared Hurst campaign

The closed invocation binds the literal `[1, 10^16 + 1)` source range, the
four-coordinate Möbius state, directed Q96 arithmetic, all four residual
identities, independent two-pass replay, and an Azure SEV-SNP CPU deployment.
The program may return `false` without proving anything.  Only an accepted
receipt whose exact result is `true` exposes local primitive-row, local guard,
full-range, and root-zero evidence.  Ordinary Lean derives the actual global
prefixes and the real-source capstone.  The registered premise does not assert
the combined global source row predicate directly.  It still owns the
physical claims that every primitive row has the stated delta and that every
guard-admissible local replay state passes the finite integer guards;
production two-pass guards are root-derived singletons.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate
open SparkInterval.TernaryGoldbach

def hurstSharedFourResidualProductionInvocation : RegisteredInvocation :=
  .hurstSharedFourResidualProductionV2

def hurstSharedFourResidualSuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful source campaign. -/
def hurstSharedFourResidualProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      hurstSharedFourResidualProductionInvocation &&
    certificate.resultCertificate == hurstSharedFourResidualSuccessOutput

end SignedResultCertificate

structure CertifiedHurstSharedFourResidual
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    hurstSharedFourResidualProductionInvocation
  resultCertificate_eq :
    certificate.resultCertificate = hurstSharedFourResidualSuccessOutput
  statementResult_eq :
    certificate.statement.result = hurstSharedFourResidualSuccessOutput
  execution :
    AlgorithmReturned certificate.statement hurstSharedFourResidualSuccessOutput
  sourceClaims :
    ∀ n, 1 ≤ n → n ≤ HurstSourceSemantics.sourceLimit →
      ∃ state : HurstAffineCertificate.State,
        HurstSourceSemantics.SourceRowPredicate n state
  realClaims : HurstSourceSemantics.RealSourceClaims
  sharedRealClaims : TGComputeContracts.HurstV2.RealSourceClaims

namespace SignedResultCertificate

/-- End-to-end reduction from one accepted successful receipt to all four
exact source predicates and all five ordinary real inequalities through their
source ranges.  Its only project axiom is `accepted_run_certificate_sound`;
range coverage, prefix composition, fallback arithmetic, and real-slab
projection are ordinary Lean theorems. -/
theorem certifyHurstSharedFourResidual
    {certificate : SignedResultCertificate}
    (hcheck : certificate.hurstSharedFourResidualProductionCheck = true) :
    CertifiedHurstSharedFourResidual certificate := by
  simp only [hurstSharedFourResidualProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have houtput :
      certificate.resultCertificate = hurstSharedFourResidualSuccessOutput := by
    simpa using hcheck.2
  have hsource :=
    RegisteredInvocation.hurstSharedFourResidualProductionV2_sourceClaims
      certified.run houtput
  have hreal :=
    RegisteredInvocation.hurstSharedFourResidualProductionV2_realClaims
      certified.run houtput
  have hshared :=
    RegisteredInvocation.hurstSharedFourResidualProductionV2_sharedRealClaims
      certified.run houtput
  have hexecution := certified.outcome.execution
  rw [houtput] at hexecution
  exact {
    certified := certified
    resultCertificate_eq := houtput
    statementResult_eq := certified.outcome.binding.1.trans houtput
    execution := hexecution
    sourceClaims := hsource
    realClaims := hreal
    sharedRealClaims := hshared
  }

end SignedResultCertificate

end SparkInterval.Execution
