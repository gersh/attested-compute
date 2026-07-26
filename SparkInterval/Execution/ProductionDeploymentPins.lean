/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.Attestation

/-!
# Reviewed post-run deployment pins

A registered algorithm hash fixes a logical protocol; confidential-compute
attestation fixes the bytes that actually ran.  A nontrivial production
invocation must bind both before the trusted-run axiom can expose its formal
`Runs` relation.

Each option below is therefore `none` until a completed run has:

* a verified and source-admitted signed receipt whose registry record carries
  the measured-run bundle and verifier-policy identities;
* an exact target/trust-profile identity;
* an exact source, host executable, device binary (or the CPU
  not-applicable digest), and terminal-manifest/runtime-closure tuple.

Installing a value is a review-time trust-boundary change.  A generator may
emit a candidate, but it must not edit this source automatically.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- Exact receipt and statement fields selected by one reviewed production
deployment.

The wire statement, measured-run bundle, verifier policy/artifact, platform
evidence, challenge, and result-binding digests already occur in the exact
source-pinned receipt entry.  They are intentionally not duplicated as
unchecked metadata in this structure. -/
structure ReviewedProductionDeployment where
  receiptHash : Digest
  targetProfileHash : Digest
  trustProfileHash : Digest
  artifacts : ArtifactHashes
  deriving Repr, DecidableEq, BEq

/-- Reviewed deployment data for the distinct fixed-width Sqrt218 V2
invocation.

Unlike the historical string-input registrations, this invocation consumes an
arbitrary binary certificate.  Its signed `RunStatement.inputHash` is
therefore the exact certificate SHA-256 itself.  `certificateBytes` is also
reviewed and must agree with both the supplied bytes and the accepted native
result record. -/
structure ReviewedSqrt218FixedV2Deployment
    extends ReviewedProductionDeployment where
  certificateSHA256 : Digest
  certificateBytes : Nat
  deriving Repr, DecidableEq, BEq

/-- Compare every deployment field available in a run statement.  Missing
post-run pins fail closed. -/
def reviewedProductionDeploymentCheck
    (pins : Option ReviewedProductionDeployment)
    (statement : RunStatement) : Bool :=
  match pins with
  | none => false
  | some expected =>
      decide (
        statement.targetProfileHash = expected.targetProfileHash ∧
        statement.trustProfileHash = expected.trustProfileHash ∧
        statement.artifacts = expected.artifacts)

/-- Bind a registered production invocation to the exact reviewed receipt.

The source-pinned receipt entry itself carries the wire-statement,
run-bundle, verifier-policy, verifier-artifact, platform-evidence, challenge,
and result-binding digests.  Keeping those values in the receipt registry,
rather than duplicating unchecked copies here, gives each review field one
authoritative Lean representation. -/
def reviewedProductionReceiptCheck
    (pins : Option ReviewedProductionDeployment)
    (attestation : Attestation) : Bool :=
  match pins, attestation with
  | some expected, .trustedCompute receiptHash =>
      decide (receiptHash = expected.receiptHash)
  | _, _ => false

/-- Bind all ordinary deployment fields and the signed statement input hash
to one reviewed fixed-width certificate digest. -/
def reviewedSqrt218FixedV2DeploymentCheck
    (pins : Option ReviewedSqrt218FixedV2Deployment)
    (statement : RunStatement) : Bool :=
  match pins with
  | none => false
  | some expected =>
      reviewedProductionDeploymentCheck
          (some expected.toReviewedProductionDeployment) statement &&
        decide (statement.inputHash = expected.certificateSHA256)

/-- Bind a fixed-width Sqrt218 invocation to the exact reviewed receipt. -/
def reviewedSqrt218FixedV2ReceiptCheck
    (pins : Option ReviewedSqrt218FixedV2Deployment)
    (attestation : Attestation) : Bool :=
  match pins with
  | none => false
  | some expected =>
      reviewedProductionReceiptCheck
        (some expected.toReviewedProductionDeployment) attestation

@[simp] theorem reviewedProductionDeploymentCheck_none
    (statement : RunStatement) :
    reviewedProductionDeploymentCheck none statement = false := rfl

@[simp] theorem reviewedProductionReceiptCheck_none
    (attestation : Attestation) :
    reviewedProductionReceiptCheck none attestation = false := by
  cases attestation <;> rfl

@[simp] theorem reviewedProductionReceiptCheck_exact
    (expected : ReviewedProductionDeployment) :
    reviewedProductionReceiptCheck (some expected)
      (.trustedCompute expected.receiptHash) = true := by
  simp [reviewedProductionReceiptCheck]

theorem reviewedProductionReceiptCheck_substitution
    (expected : ReviewedProductionDeployment) {actual : Digest}
    (hdifferent : actual ≠ expected.receiptHash) :
    reviewedProductionReceiptCheck (some expected)
      (.trustedCompute actual) = false := by
  simp [reviewedProductionReceiptCheck, hdifferent]

@[simp] theorem reviewedSqrt218FixedV2DeploymentCheck_none
    (statement : RunStatement) :
    reviewedSqrt218FixedV2DeploymentCheck none statement = false := rfl

@[simp] theorem reviewedSqrt218FixedV2ReceiptCheck_none
    (attestation : Attestation) :
    reviewedSqrt218FixedV2ReceiptCheck none attestation = false := rfl

def cdemTableAbelProductionDeployment :
    Option ReviewedProductionDeployment := none

def hurstSharedFourResidualProductionDeployment :
    Option ReviewedProductionDeployment := none

def ch25PsiLemma92ProductionDeployment :
    Option ReviewedProductionDeployment := none

def ramareZunigaLemma62ProductionDeployment :
    Option ReviewedProductionDeployment := none

def helfgottProp1224ProductionDeployment :
    Option ReviewedProductionDeployment := none

def ch25A7BoundaryProductionDeployment :
    Option ReviewedProductionDeployment := none

def plattHead2e4ProductionDeployment :
    Option ReviewedProductionDeployment := none

def plattDirichletTheorem71ProductionDeployment :
    Option ReviewedProductionDeployment := none

def plattTrudgianFiniteRHProductionDeployment :
    Option ReviewedProductionDeployment := none

def helfgottPlattGoldbachProductionDeployment :
    Option ReviewedProductionDeployment := none

def goldbach10Pow27ProductionDeployment :
    Option ReviewedProductionDeployment := none

/-- Disabled until an exact Sqrt218 replay has a reviewed production receipt,
SEV-SNP evidence, and complete artifact tuple. -/
def helfgottSqrt218ProductionDeployment :
    Option ReviewedProductionDeployment := none

/-- Disabled until a fixed-width certificate, its exact byte length and
SHA-256, the native result, SEV-SNP evidence, artifacts, and receipt have all
been reviewed together. -/
def helfgottSqrt218FixedV2ProductionDeployment :
    Option ReviewedSqrt218FixedV2Deployment := none

end SparkInterval.Execution
