/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxCampaignCertificate
import SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence

/-!
# Phala/dstack TDX bridge for CH25 Lemma A.7

This is the complete cost of a campaign on the TDX path: three lines of data,
one check, one conclusion abbreviation, and one theorem whose body is a single
application of the generic layer.  Compare
`Execution/RegisteredA7BoundaryCertificate.lean`, the Azure sibling.

Nothing here is installed: `PhalaTdxEnclave.ch25A7BoundaryProductionV1`'s
public key is unpinned, so `ch25A7BoundaryPhalaTdxCheck` is `false` for every
receipt until a reviewed first run supplies it.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

/-- Data (1/3): which reviewed enclave identity. -/
def ch25A7BoundaryPhalaTdxEnclave : PhalaTdxEnclave :=
  .ch25A7BoundaryProductionV1

/-- Data (2/3): which closed registered invocation. -/
def ch25A7BoundaryPhalaTdxInvocation : RegisteredInvocation :=
  .ch25A7BoundaryProductionV1

/-- Data (3/3): which exact returned bytes count as success. -/
def ch25A7BoundaryPhalaTdxSuccessOutput : String := "true"

/-- Fail-closed application check for one enclave-signed A.7 replay. -/
def ch25A7BoundaryPhalaTdxCheck (receipt : PhalaTdxReceipt) : Bool :=
  phalaTdxProductionCheck ch25A7BoundaryPhalaTdxEnclave
    ch25A7BoundaryPhalaTdxInvocation receipt
    ch25A7BoundaryPhalaTdxSuccessOutput

/-- The campaign's complete conclusion. -/
abbrev CertifiedCH25A7BoundaryPhalaTdx (receipt : PhalaTdxReceipt) : Prop :=
  PhalaTdxCertifiedSourceRun ch25A7BoundaryPhalaTdxInvocation receipt
    ch25A7BoundaryPhalaTdxSuccessOutput
    A7BoundarySourceSemantics.SourceClaim

/-- End-to-end reduction from one accepted enclave-signed successful A.7
replay to the literal source-shaped boundary estimate.

Its only project axiom is `phalaTdxAttestedRun_sound`. -/
theorem certifyCH25A7BoundaryPhalaTdx {receipt : PhalaTdxReceipt}
    (authority :
      ch25A7BoundaryPhalaTdxEnclave.pin.attestationAuthority = true)
    (hcheck : ch25A7BoundaryPhalaTdxCheck receipt = true) :
    CertifiedCH25A7BoundaryPhalaTdx receipt :=
  certifyPhalaTdxSourceRun
    RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim authority
    hcheck

/-- Today the campaign is unreachable: no receipt satisfies the check. -/
theorem ch25A7BoundaryPhalaTdxCheck_eq_false (receipt : PhalaTdxReceipt) :
    ch25A7BoundaryPhalaTdxCheck receipt = false := by
  simp [ch25A7BoundaryPhalaTdxCheck, phalaTdxProductionCheck,
    ch25A7BoundaryPhalaTdxEnclave,
    phalaTdxOutcomeCheck_ch25A7BoundaryProductionV1_eq_false]

end SparkInterval.Execution
