/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.PTX.Generator

/-!
# Formal source identity for the registered H100 constant-one pilot

This module kernel-links the human-readable PTX preimage in the closed
algorithm registry to the ordinary formally defined `ReferenceBatch` compiler.
It is deliberately separate from physical execution evidence and the trusted
run axiom.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate
open SparkInterval.PTX

/-- Public application-layer name for the registry's exact pilot interval. -/
abbrev h100FormalPtxConstantOneInterval : IntervalBits :=
  RegisteredAlgorithm.h100FormalPtxConstantOneInterval

/-- Public application-layer name for the registry's exact pilot batch. -/
abbrev h100FormalPtxConstantOneBatch : ReferenceBatch :=
  RegisteredAlgorithm.h100FormalPtxConstantOneBatch

/-- The duplicated protocol PTX literal is definitionally exactly the output
of the formal target-selected emitter on the closed registered batch. -/
theorem h100FormalPtxConstantOnePTX_eq_formalEmitter :
    RegisteredAlgorithm.h100FormalPtxConstantOnePTX =
      renderUncheckedFor .sm90
        (buildModule h100FormalPtxConstantOneBatch) := by
  rfl

/-- Receipt consumers that already hold the registry-fixed `Runs` projection
recover the exact manifest, both decoded endpoints, and the formal PTX source
identity without repeating application-specific proof plumbing. -/
theorem h100FormalPtxConstantOne_result_of_run
    {output : String}
    (run : RegisteredInvocation.h100FormalPtxConstantOneV1.Runs output) :
    output = RegisteredAlgorithm.h100FormalPtxConstantOneOutput ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) ∧
      RegisteredAlgorithm.h100FormalPtxConstantOnePTX =
        renderUncheckedFor .sm90
          (buildModule h100FormalPtxConstantOneBatch) := by
  have result :=
    RegisteredInvocation.h100FormalPtxConstantOneV1_result run
  exact ⟨result.1, result.2.1, result.2.2,
    h100FormalPtxConstantOnePTX_eq_formalEmitter⟩

/-- The closed H100 pilot invocation used by the receipt importer. -/
def h100FormalPtxConstantOneInvocation : RegisteredInvocation :=
  .h100FormalPtxConstantOneV1

/-- Everything Lean recovers from an accepted certificate for the exact H100
pilot invocation.  The physical run crosses the repository's sole trusted-run
axiom in `outcomeCheckForRegisteredInvocation_sound`; the manifest, binary64
interpretation, and formal-emitter identity are then ordinary Lean theorems. -/
structure CertifiedH100FormalPtxConstantOne
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    h100FormalPtxConstantOneInvocation
  resultCertificate_eq :
    certificate.resultCertificate =
      RegisteredAlgorithm.h100FormalPtxConstantOneOutput
  statementResult_eq :
    certificate.statement.result =
      RegisteredAlgorithm.h100FormalPtxConstantOneOutput
  execution :
    AlgorithmReturned certificate.statement
      RegisteredAlgorithm.h100FormalPtxConstantOneOutput
  lowerEndpoint :
    Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ)
  upperEndpoint :
    Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ)
  formalProgramIdentity :
    RegisteredAlgorithm.h100FormalPtxConstantOnePTX =
      renderUncheckedFor .sm90
        (buildModule h100FormalPtxConstantOneBatch)

namespace SignedResultCertificate

/-- End-to-end theorem for the closed H100 formal-PTX pilot.

The premise checks production evidence acceptance, exact result-byte binding,
the complete closed registry identity, and the H100 confidential-compute
deployment restriction.  From that one Boolean check, this theorem exposes
the exact returned manifest, proves both binary64 endpoints equal one, and
links the registered PTX bytes definitionally to the formal PTX emitter. -/
theorem certifyH100FormalPtxConstantOne
    {certificate : SignedResultCertificate}
    (hcheck : certificate.outcomeCheckForRegisteredInvocation
      h100FormalPtxConstantOneInvocation = true) :
    CertifiedH100FormalPtxConstantOne certificate := by
  have certified := outcomeCheckForRegisteredInvocation_sound hcheck
  have hresult :=
    RegisteredInvocation.h100FormalPtxConstantOneV1_result certified.run
  have hexecution := certified.outcome.execution
  rw [hresult.1] at hexecution
  exact {
    certified := certified
    resultCertificate_eq := hresult.1
    statementResult_eq := certified.outcome.binding.1.trans hresult.1
    execution := hexecution
    lowerEndpoint := hresult.2.1
    upperEndpoint := hresult.2.2
    formalProgramIdentity := h100FormalPtxConstantOnePTX_eq_formalEmitter
  }

end SignedResultCertificate

end SparkInterval.Execution
