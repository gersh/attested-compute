import SparkInterval.Execution.Attestation

/-!
# Structural policy for H100 execution evidence

This legacy diagnostic checker is intentionally small and executable.  It
enforces complete statement/claim binding, but it does **not** implement
signature verification, certificate-chain validation, revocation, firmware
appraisal, or a model of the physical GPU.  It is excluded from
`RunCertificate.check` and cannot reach the execution axiom.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

private def present (value : String) : Bool :=
  !value.isEmpty

/-- Every admitted artifact digest must be present. -/
def ArtifactHashes.allPresent (hashes : ArtifactHashes) : Bool :=
  present hashes.sourceTreeHash &&
  present hashes.hostExecutableHash &&
  present hashes.deviceCubinHash &&
  present hashes.kernelManifestHash

/-- Compare every artifact hash explicitly. -/
def ArtifactHashes.matches (actual expected : ArtifactHashes) : Bool :=
  actual.sourceTreeHash == expected.sourceTreeHash &&
  actual.hostExecutableHash == expected.hostExecutableHash &&
  actual.deviceCubinHash == expected.deviceCubinHash &&
  actual.kernelManifestHash == expected.kernelManifestHash

/-- Reject incomplete statements before considering any evidence. -/
def RunStatement.allMetadataPresent (statement : RunStatement) : Bool :=
  present statement.algorithmId &&
  present statement.algorithmHash &&
  present statement.inputHash &&
  present statement.parametersHash &&
  present statement.domainHash &&
  present statement.result &&
  present statement.outputHash &&
  present statement.nonce &&
  present statement.targetProfileHash &&
  present statement.trustProfileHash &&
  statement.artifacts.allPresent

/-- Exact structural binding from an attested claim to the expected statement.

The successful-completion check is kept here so no caller can accidentally use
the same comparison for a failed or partial run.
-/
def RunClaim.matches (claim : RunClaim) (statement : RunStatement) : Bool :=
  claim.algorithmId == statement.algorithmId &&
  claim.algorithmHash == statement.algorithmHash &&
  claim.inputHash == statement.inputHash &&
  claim.parametersHash == statement.parametersHash &&
  claim.domainHash == statement.domainHash &&
  claim.result == statement.result &&
  claim.outputHash == statement.outputHash &&
  claim.nonce == statement.nonce &&
  claim.target == statement.target &&
  claim.targetProfileHash == statement.targetProfileHash &&
  claim.trust == statement.trust &&
  claim.trustProfileHash == statement.trustProfileHash &&
  claim.artifacts.matches statement.artifacts &&
  claim.completion == .successful

/-- Structural metadata supplied by a production evidence verifier must also
be nonempty. -/
def H100HardwareEvidence.allMetadataPresent
    (evidence : H100HardwareEvidence) : Bool :=
  present evidence.attestationReportHash &&
  present evidence.certificateChainHash &&
  present evidence.verifierArtifactHash

/-- Diagnose structural binding for the legacy H100 evidence container.

The first two equations are unconditional: no local or mock evidence can ever
be accepted, even if its claim byte-for-byte matches a production statement.
-/
def checkH100Attestation (statement : RunStatement) : Attestation → Bool
  | .local _ => false
  | .mock _ => false
  | .dgxOperatorSignature _ => false
  | .trustedCompute _ => false
  | .h100Hardware evidence =>
      statement.target == .nvidiaH100SM90 &&
      statement.trust == .nvidiaH100ConfidentialCompute &&
      statement.allMetadataPresent &&
      evidence.allMetadataPresent &&
      evidence.claim.matches statement

@[simp] theorem checkH100Attestation_local
    (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.local claim) = false :=
  rfl

@[simp] theorem checkH100Attestation_mock
    (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.mock claim) = false :=
  rfl

@[simp] theorem checkH100Attestation_dgxOperatorSignature
    (statement : RunStatement) (evidence : DGXOperatorSignatureEvidence) :
    checkH100Attestation statement (.dgxOperatorSignature evidence) = false :=
  rfl

@[simp] theorem checkH100Attestation_trustedCompute
    (statement : RunStatement) (receiptHash : Digest) :
    checkH100Attestation statement (.trustedCompute receiptHash) = false :=
  rfl

end SparkInterval.Execution
