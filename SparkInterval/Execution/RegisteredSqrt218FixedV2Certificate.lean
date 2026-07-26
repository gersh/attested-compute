/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics

/-!
# Registered fixed-width V2 trusted-compute bridge for Helfgott (2.18)

This is distinct from the historical canonical-JSON V1 invocation.  A
successful fixed-V2 run existentially supplies the exact binary certificate,
then requires:

* strict canonical `SQ218V2` decoding and exact EOF;
* exact byte length and SHA-256 equality with the reviewed pin and the signed
  statement `inputHash`;
* the complete fixed-width V2 Lean checker;
* canonical exact-hex decoding of the 120-byte `SQ218R2` result; and
* equality of its accepted arithmetic state, input length, and input digest
  with the checked certificate.

No certificate bytes, digest, deployment, or receipt are installed here.  The
optional reviewed pin is `none`, so the application check is fail-closed and
ordinary builds perform no production replay.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def helfgottSqrt218FixedV2ProductionInvocation : RegisteredInvocation :=
  .helfgottSqrt218FixedProductionV2

namespace RegisteredInvocation

/-- A non-failure fixed-V2 run is necessarily the fully byte-, digest-,
result-, and semantics-bound success branch. -/
theorem helfgottSqrt218FixedProductionV2_success
    {output : String}
    (run : RegisteredInvocation.helfgottSqrt218FixedProductionV2.Runs output)
    (houtput : output ≠ "false") :
    RegisteredAlgorithm.helfgottSqrt218FixedV2Success
      RegisteredInvocation.helfgottSqrt218FixedProductionV2.canonicalInput
      output := by
  rcases run with hfailure | hsuccess
  · exact (houtput hfailure).elim
  · exact hsuccess

/-- A successful fixed-width run implies the exact finite source claim by the
ordinary, data-independent V2 checker soundness theorem. -/
theorem helfgottSqrt218FixedProductionV2_sourceClaim
    {output : String}
    (run : RegisteredInvocation.helfgottSqrt218FixedProductionV2.Runs output)
    (houtput : output ≠ "false") :
    Sqrt218SourceSemantics.SourceClaim := by
  rcases helfgottSqrt218FixedProductionV2_success run houtput with
    ⟨reviewed, rawCertificate, image, arithmeticResult, rawResult,
      nativeResult, hpins, hinput, hbytes, hdecode, hdigest, hrun,
      hcomplete, hresult, haccepted, hresultBytes, hresultDigest,
      hresultState⟩
  exact
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter.sourceClaim_of_completeCheck
      hcomplete

end RegisteredInvocation

namespace SignedResultCertificate

/-- Fail-closed application check for a non-failure, accepted fixed-V2 result
envelope bound to the distinct closed invocation. -/
def helfgottSqrt218FixedV2ProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.outcomeCheckForRegisteredInvocation
      helfgottSqrt218FixedV2ProductionInvocation &&
    (certificate.resultCertificate != "false" &&
      RegisteredInvocation.sqrt218FixedV2AcceptedResultCheck
        certificate.resultCertificate)

end SignedResultCertificate

/-- Exact consequence of one successfully checked fixed-V2 receipt.  The
nested successful-run relation contains the raw-byte, pin, result-record, and
complete-check equalities listed in this module's header. -/
structure CertifiedHelfgottSqrt218FixedV2
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    helfgottSqrt218FixedV2ProductionInvocation
  nonFailure : certificate.resultCertificate ≠ "false"
  successfulRun :
    RegisteredAlgorithm.helfgottSqrt218FixedV2Success
      RegisteredInvocation.helfgottSqrt218FixedProductionV2.canonicalInput
      certificate.resultCertificate
  execution :
    AlgorithmReturned certificate.statement certificate.resultCertificate
  sourceClaim : Sqrt218SourceSemantics.SourceClaim

namespace SignedResultCertificate

/-- Conditional fixed-V2 handoff.  Its only project execution axiom is the
existing `accepted_run_certificate_sound`; parsing, byte hashing, complete
certificate semantics, and the source reduction are explicit in `Runs`. -/
theorem certifyHelfgottSqrt218FixedV2
    {certificate : SignedResultCertificate}
    (hcheck : certificate.helfgottSqrt218FixedV2ProductionCheck = true) :
    CertifiedHelfgottSqrt218FixedV2 certificate := by
  simp only [helfgottSqrt218FixedV2ProductionCheck, Bool.and_eq_true] at hcheck
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck.1
  have hnonFailure : certificate.resultCertificate ≠ "false" := by
    simpa using hcheck.2.1
  have _haccepted :
      RegisteredInvocation.sqrt218FixedV2AcceptedResultCheck
        certificate.resultCertificate = true :=
    hcheck.2.2
  have hsuccess :=
    RegisteredInvocation.helfgottSqrt218FixedProductionV2_success
      certified.run hnonFailure
  exact {
    certified
    nonFailure := hnonFailure
    successfulRun := hsuccess
    execution := certified.outcome.execution
    sourceClaim :=
      RegisteredInvocation.helfgottSqrt218FixedProductionV2_sourceClaim
        certified.run hnonFailure
  }

end SignedResultCertificate

end SparkInterval.Execution
