import SparkInterval.Execution.Statement

/-!
# Attestation evidence containers

Local and mock envelopes are deliberately first-class so development tooling
can exercise the bundle format.  Positive H100 and DGX-operator evidence is
capability based: their constructors are private, so merely changing a JSON
tag cannot create either capability in Lean.  A trusted certificate importer
must validate the corresponding external evidence before constructing one.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- Evidence produced by a production NVIDIA H100 confidential-computing
verifier.

The private constructor is essential.  There is intentionally no public mock
constructor and no parser that blindly trusts an evidence-kind field.
-/
structure H100HardwareEvidence where
  private mk ::
  claim : RunClaim
  attestationReportHash : Digest
  certificateChainHash : Digest
  verifierArtifactHash : Digest

/-- Evidence that a separately approved Ed25519 operator key signed the exact
canonical DGX run bundle.

The signature authenticates an operator statement; it is not hardware
attestation and cannot establish by cryptography alone that a GPU execution
happened.  The private constructor ensures ordinary Lean code cannot relabel a
local JSON object as verified signature evidence.
-/
structure DGXOperatorSignatureEvidence where
  private mk ::
  claim : RunClaim
  runBundleHash : Digest
  publicKeyHash : Digest
  signatureHash : Digest
  verifierArtifactHash : Digest

/-- The two production execution classes supported by compact signed receipts.

An Azure H100 run requires both the Azure SEV-SNP/vTPM evidence and NVIDIA GPU
evidence.  A CPU run deliberately has no GPU evidence and must use the
`azureSEVSNPCPU` target. -/
inductive TrustedComputeBackend where
  | azureSEVSNPCPU
  | azureNCCadsH100v5
  deriving Repr, DecidableEq, BEq

/-- A normalized, externally verified trusted-compute receipt.

This structure is public data, not an evidence capability.  Constructing a
value does not make it acceptable: the only public attestation constructor
stores a receipt hash, and the production policy resolves that hash through
the closed, source-pinned registry.  The registry generator verifies the
pinned signature before emitting any entry.  The signed payload commits to
every field below and to the complete `claim` through its canonical Lean
commitment.
-/
structure TrustedComputeEvidence where
  receiptHash : Digest
  backend : TrustedComputeBackend
  claim : RunClaim
  runBundleHash : Digest
  wireStatementHash : Digest
  platformEvidenceHash : Digest
  azureMaaTokenHash : Digest
  amdSnpReportHash : Digest
  tpmQuoteHash : Digest
  tpmEventLogHash : Digest
  nvidiaEatHash : Digest
  nvidiaEvidenceHash : Digest
  verifierPolicyHash : Digest
  verifierArtifactHash : Digest
  startChallengeHash : Digest
  resultBindingHash : Digest
  issuedAt : String
  expiresAt : String
  verifierKeyId : String
  signatureHex : String
  deriving Repr, DecidableEq, BEq

/-- Evidence envelopes understood by the policy layer.

Only the `h100Hardware` branch is eligible for acceptance by the H100 checker.
Only `dgxOperatorSignature` is eligible for the separate DGX checker; it
authenticates an operator's endorsement, not hardware execution.  The `local`
and `mock` branches are useful for development but carry no physical-execution
authority.
-/
inductive Attestation where
  | local (claim : RunClaim)
  | mock (claim : RunClaim)
  | dgxOperatorSignature (evidence : DGXOperatorSignatureEvidence)
  | h100Hardware (evidence : H100HardwareEvidence)
  /-- Hash of CPU-only or composite CPU/H100 evidence countersigned by the
  pinned verifier and admitted to the closed source registry.  Supplying an
  unknown hash is always rejected. -/
  | trustedCompute (receiptHash : Digest)

end SparkInterval.Execution
