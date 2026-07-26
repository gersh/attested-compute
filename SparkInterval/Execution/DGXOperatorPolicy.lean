import SparkInterval.Execution.H100Policy

/-!
# Structural policy for an operator-signed DGX execution claim

The external verifier pins an Ed25519 public key, verifies the signature over
the exact canonical local run bundle, checks every artifact, and applies replay
protection.  This Lean checker performs only structural binding between that
record and a statement.  It is a diagnostic API: `RunCertificate.check` does
not call it, and a positive result cannot reach the execution axiom.

An operator signature proves who signed a record.  It is not hardware
attestation and does not itself prove that the record is true.
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

/-- Diagnose exact statement binding for a legacy operator-signed DGX record.

Local, mock, and H100 evidence are rejected by construction.  The accepted
branch still carries no `hardware_evidence` claim: it represents a signature
from a separately approved operator key over a local-unattested bundle and is
never an admission result.
-/
def checkDGXOperatorSignature (statement : RunStatement) : Attestation → Bool
  | .local _ => false
  | .mock _ => false
  | .h100Hardware _ => false
  | .trustedCompute _ => false
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

@[simp] theorem checkDGXOperatorSignature_trustedCompute
    (statement : RunStatement) (receiptHash : Digest) :
    checkDGXOperatorSignature statement (.trustedCompute receiptHash) = false :=
  rfl

end SparkInterval.Execution
