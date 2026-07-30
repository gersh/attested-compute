/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.RegisteredCampaignCertificate
import SparkInterval.TernaryGoldbach.RamareNativeFoldContracts

/-!
# Registered trusted-compute bridge for the three Ramaré production folds

Only a receipt bound to the closed Azure CPU invocation
`ramareProductionFoldsProductionV1` and the exact success result `"true"`
exposes the three source-shaped claims.  The registered program may return
`"false"`, which proves nothing.

This campaign is an instantiation of the generic layer in
`SparkInterval.Execution.RegisteredCampaignCertificate`: the check is
`productionCheck` at this invocation and output, and the whole conclusion —
the four shared run facts plus the campaign's source claim — is
`CertifiedSourceRun`, proved once by `certifySourceRun`.  No structure and no
tactic proof is written here.

The claim replaced by this campaign is exactly the conjunction supplied in
`claude_math` by three `native_decide` leaves:

* `TGNativeCertificates.Ramare.Finite100M.checkFirstMertens100M = true`;
* `TGNativeCertificates.Ramare.Lemma71.checkLemma71_100M = true`;
* `TGNativeCertificates.Ramare.MStar140MEngine.checkLimit 140000000 = true`.

Trust change: those leaves are locally checkable with no network, resting on
`Lean.ofReduceBool` plus the compiler and GMP.  Everything reached through
this module instead rests on `Trusted.accepted_run_certificate_sound` — Azure
confidential compute, the host silicon, MAA appraisal, and an HSM key.  The
two are not comparable; a reader must be able to tell them apart, and the
`#print axioms` output below is the intended way to do that.

No receipt exists.  `ramareProductionFoldsProductionDeployment` is `none`, so
every deployment and receipt check here fails closed and no theorem in this
file is currently inhabited by anything.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.TernaryGoldbach

def ramareProductionFoldsProductionInvocation : RegisteredInvocation :=
  .ramareProductionFoldsProductionV1

def ramareProductionFoldsSuccessOutput : String := "true"

namespace SignedResultCertificate

/-- Fail-closed application check for the exact successful fold campaign. -/
def ramareProductionFoldsProductionCheck
    (certificate : SignedResultCertificate) : Bool :=
  certificate.productionCheck ramareProductionFoldsProductionInvocation
    ramareProductionFoldsSuccessOutput

end SignedResultCertificate

/-- The complete campaign conclusion: the four shared run facts of
`CertifiedRun` plus the three Ramaré source claims. -/
abbrev CertifiedRamareProductionFolds
    (certificate : SignedResultCertificate) : Prop :=
  CertifiedSourceRun certificate ramareProductionFoldsProductionInvocation
    ramareProductionFoldsSuccessOutput
    RamareNativeFoldContracts.SourceClaims

namespace SignedResultCertificate

/-- End-to-end reduction from one accepted successful Azure receipt to the
three literal real-variable Ramaré propositions.  Its only project axiom is
`accepted_run_certificate_sound`; the interval-fold induction and the
floor-drift reduction are ordinary Lean theorems. -/
theorem certifyRamareProductionFolds
    {certificate : SignedResultCertificate}
    (hcheck : certificate.ramareProductionFoldsProductionCheck = true) :
    CertifiedRamareProductionFolds certificate :=
  certifySourceRun
    RegisteredInvocation.ramareProductionFoldsProductionV1_sourceClaims hcheck

end SignedResultCertificate

#print axioms SignedResultCertificate.certifyRamareProductionFolds

end SparkInterval.Execution
