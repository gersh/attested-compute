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

end SparkInterval.Execution
