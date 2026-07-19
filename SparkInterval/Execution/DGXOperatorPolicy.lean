import SparkInterval.Execution.H100Policy

/-!
# Structural policy for an operator-signed DGX execution claim

The external verifier pins an Ed25519 public key, verifies the signature over
the exact canonical local run bundle, checks every artifact, and applies replay
protection.  This Lean checker performs only the remaining structural binding
between that imported capability and the statement a theorem expects.

An operator signature proves who signed a record.  It is not hardware
attestation and does not itself prove that the record is true.  The stronger
physical-execution assumption is isolated in `Execution/Trusted`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- Require every cryptographic/importer identity bound by the imported
operator-signature capability to be present. -/
def DGXOperatorSignatureEvidence.allMetadataPresent
    (evidence : DGXOperatorSignatureEvidence) : Bool :=
  !evidence.runBundleHash.isEmpty &&
  !evidence.publicKeyHash.isEmpty &&
  !evidence.signatureHash.isEmpty &&
  !evidence.verifierArtifactHash.isEmpty

/-- Check exact statement binding for the operator-signed DGX policy.

Local, mock, and H100 evidence are rejected by construction.  The accepted
branch still carries no `hardware_evidence` claim: it represents a signature
from a separately approved operator key over a local-unattested bundle.
-/
def checkDGXOperatorSignature (statement : RunStatement) : Attestation → Bool
  | .local _ => false
  | .mock _ => false
  | .h100Hardware _ => false
  | .dgxOperatorSignature evidence =>
      statement.target == .dgxSparkSM121 &&
      statement.trust == .localUnattested &&
      statement.allMetadataPresent &&
      evidence.allMetadataPresent &&
      evidence.claim.matches statement

@[simp] theorem checkDGXOperatorSignature_local
    (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.local claim) = false :=
  rfl

@[simp] theorem checkDGXOperatorSignature_mock
    (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.mock claim) = false :=
  rfl

@[simp] theorem checkDGXOperatorSignature_h100
    (statement : RunStatement) (evidence : H100HardwareEvidence) :
    checkDGXOperatorSignature statement (.h100Hardware evidence) = false :=
  rfl

end SparkInterval.Execution
