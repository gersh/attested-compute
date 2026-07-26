/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.RSA
import SparkInterval.Certificate.CanonicalHex
import SparkInterval.Execution.H100Policy
import SparkInterval.Execution.TrustedComputeKey
import SparkInterval.Execution.TrustedComputeRegistry

/-!
# Signed trusted-compute receipt policy

This is the executable Lean-side admission policy for Azure confidential CPU
runs and composite Azure SEV-SNP plus NVIDIA H100 runs.  The external verifier
does the large and time-sensitive work: certificate-chain validation,
revocation, MAA/NRAS token verification, PCR/event-log appraisal, NVIDIA RIM
checks, replay protection, and measured-runner policy.  It emits one normalized
receipt and signs its canonical payload.

The importer independently resolves the verifier key through a source-reviewed
key manifest, checks its signature, canonical digests, validity window, and
domain-separated post-run binding before emitting a source-pinned registry
entry. Lean then checks exact registry lookup, claim binding, result/output
hashing, challenge/result binding, and backend separation before the
repository's single execution axiom can be applied.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- Distinguished digest used only where an evidence artifact cannot exist,
not as a substitute for missing required evidence. -/
def trustedComputeNotApplicableDigest : Digest :=
  "b272852e69f12bacf5fbb095bc43233bfd184f238a86f5bb66d85772b849d02b"

/-- Audit-only recomputation of the reviewed protocol constant.  Runtime
acceptance uses the literal above, so a small structural certificate never
expands the full SHA-256 evaluator in its proof term. -/
def trustedComputeNotApplicableDigestMatchesDiagnostic : Bool :=
  trustedComputeNotApplicableDigest ==
    SHA256.digestString "sparkinterval.trusted-compute.not-applicable.v1"

def trustedComputeZeroDigest : Digest :=
  "0000000000000000000000000000000000000000000000000000000000000000"

/-- Check the unique lowercase hexadecimal representation of a SHA-256
digest. -/
def isCanonicalSHA256 (value : String) : Bool :=
  Certificate.isCanonicalLowerHexOfLength 64 value

/-- Check the unique fixed-width lowercase representation of an RSA-3072
signature.  Signature validity is established by the fail-closed registry
generator; this inexpensive check prevents malformed reviewed literals from
being admitted accidentally. -/
def isCanonicalRSA3072Signature (value : String) : Bool :=
  Certificate.isCanonicalLowerHexOfLength 768 value

def trustedComputeRequiredDigest (value : String) : Bool :=
  isCanonicalSHA256 value && value != trustedComputeZeroDigest &&
    value != trustedComputeNotApplicableDigest

/-- Assemble one required-digest check from a compositional syntax
certificate and the two protocol-specific non-placeholder checks. -/
theorem trustedComputeRequiredDigest_of_canonical {value : String}
    (canonical : isCanonicalSHA256 value = true)
    (nonzero : (value != trustedComputeZeroDigest) = true)
    (applicable : (value != trustedComputeNotApplicableDigest) = true) :
    trustedComputeRequiredDigest value = true := by
  simp [trustedComputeRequiredDigest, canonical, nonzero, applicable]

private def targetName : ExecutionTarget → String
  | .dgxSparkSM121 => "dgx_spark_sm121"
  | .nvidiaH100SM90 => "nvidia_h100_sm90"
  | .azureSEVSNPCPU => "azure_sevsnp_cpu"

private def trustName : TrustProfile → String
  | .localUnattested => "local_unattested"
  | .mockAttested => "mock_attested"
  | .nvidiaH100ConfidentialCompute => "nvidia_h100_confidential_compute"
  | .azureSEVSNPConfidentialCompute => "azure_sevsnp_confidential_compute"

private def completionName : Completion → String
  | .notStarted => "not_started"
  | .failed => "failed"
  | .successful => "successful"

private def backendName : TrustedComputeBackend → String
  | .azureSEVSNPCPU => "azure_sevsnp_cpu"
  | .azureNCCadsH100v5 => "azure_ncc40ads_h100_v5"

private def committedField (name value : String) : String :=
  name ++ "=" ++ SHA256.digestString value ++ "\n"

/-- Unambiguous commitment preimage for the complete claim.  Every variable
string is SHA-256 committed before entering the line-oriented format, while
the enum spellings are fixed by this source file. -/
def RunClaim.trustedComputeCommitmentPayload (claim : RunClaim) : String :=
  "sparkinterval.trusted-compute.claim.v1\n" ++
  committedField "algorithm_id" claim.algorithmId ++
  committedField "algorithm_hash" claim.algorithmHash ++
  committedField "input_hash" claim.inputHash ++
  committedField "parameters_hash" claim.parametersHash ++
  committedField "domain_hash" claim.domainHash ++
  committedField "result" claim.result ++
  committedField "output_hash" claim.outputHash ++
  committedField "nonce" claim.nonce ++
  committedField "target" (targetName claim.target) ++
  committedField "target_profile_hash" claim.targetProfileHash ++
  committedField "trust" (trustName claim.trust) ++
  committedField "trust_profile_hash" claim.trustProfileHash ++
  committedField "source_tree_hash" claim.artifacts.sourceTreeHash ++
  committedField "host_executable_hash" claim.artifacts.hostExecutableHash ++
  committedField "device_cubin_hash" claim.artifacts.deviceCubinHash ++
  committedField "kernel_manifest_hash" claim.artifacts.kernelManifestHash ++
  committedField "completion" (completionName claim.completion)

/-- SHA-256 commitment used by the compact receipt. -/
def RunClaim.trustedComputeCommitment (claim : RunClaim) : Digest :=
  SHA256.digestString claim.trustedComputeCommitmentPayload

/-- Diagnostic reconstruction of the post-run attestation binding derived
from the unpredictable start challenge and canonical wire statement.

The registry generator checks this equation before source admission, and the
Lean acceptance Boolean recomputes it as defense in depth. -/
def TrustedComputeEvidence.expectedResultBindingHash
    (evidence : TrustedComputeEvidence) : Digest :=
  SHA256.digestString
    ("sparkinterval.trusted-compute.result-binding.v1\n" ++
      "start_challenge_sha256=" ++ evidence.startChallengeHash ++ "\n" ++
      "wire_statement_sha256=" ++ evidence.wireStatementHash ++ "\n")

/-- Exact bytes signed by the external trusted verifier.  The RSA signature
field itself is intentionally excluded. -/
def TrustedComputeEvidence.canonicalSignedPayload
    (evidence : TrustedComputeEvidence) : String :=
  "sparkinterval.trusted-compute-receipt.v1\n" ++
  "backend=" ++ backendName evidence.backend ++ "\n" ++
  "claim_sha256=" ++ evidence.claim.trustedComputeCommitment ++ "\n" ++
  "run_bundle_sha256=" ++ evidence.runBundleHash ++ "\n" ++
  "wire_statement_sha256=" ++ evidence.wireStatementHash ++ "\n" ++
  "platform_evidence_sha256=" ++ evidence.platformEvidenceHash ++ "\n" ++
  "azure_maa_token_sha256=" ++ evidence.azureMaaTokenHash ++ "\n" ++
  "amd_snp_report_sha256=" ++ evidence.amdSnpReportHash ++ "\n" ++
  "tpm_quote_sha256=" ++ evidence.tpmQuoteHash ++ "\n" ++
  "tpm_event_log_sha256=" ++ evidence.tpmEventLogHash ++ "\n" ++
  "nvidia_eat_sha256=" ++ evidence.nvidiaEatHash ++ "\n" ++
  "nvidia_evidence_sha256=" ++ evidence.nvidiaEvidenceHash ++ "\n" ++
  "verifier_policy_sha256=" ++ evidence.verifierPolicyHash ++ "\n" ++
  "verifier_artifact_sha256=" ++ evidence.verifierArtifactHash ++ "\n" ++
  "start_challenge_sha256=" ++ evidence.startChallengeHash ++ "\n" ++
  "result_binding_sha256=" ++ evidence.resultBindingHash ++ "\n" ++
  committedField "issued_at" evidence.issuedAt ++
  committedField "expires_at" evidence.expiresAt ++
  committedField "verifier_key_id" evidence.verifierKeyId

/-- Every required normalized verifier field has a real canonical digest. -/
def TrustedComputeEvidence.allMetadataPresent
    (evidence : TrustedComputeEvidence) : Bool :=
  trustedComputeRequiredDigest evidence.receiptHash &&
  trustedComputeRequiredDigest evidence.runBundleHash &&
  trustedComputeRequiredDigest evidence.wireStatementHash &&
  trustedComputeRequiredDigest evidence.platformEvidenceHash &&
  trustedComputeRequiredDigest evidence.azureMaaTokenHash &&
  trustedComputeRequiredDigest evidence.amdSnpReportHash &&
  trustedComputeRequiredDigest evidence.tpmQuoteHash &&
  trustedComputeRequiredDigest evidence.tpmEventLogHash &&
  trustedComputeRequiredDigest evidence.verifierPolicyHash &&
  trustedComputeRequiredDigest evidence.verifierArtifactHash &&
  trustedComputeRequiredDigest evidence.startChallengeHash &&
  trustedComputeRequiredDigest evidence.resultBindingHash &&
  !evidence.issuedAt.isEmpty &&
  !evidence.expiresAt.isEmpty &&
  trustedComputeVerifierKeyAllowed evidence.verifierKeyId

/-- Require canonical digests throughout the statement.  This is stronger
than the legacy private-capability policies' nonempty check. -/
def RunStatement.allDigestsCanonical (statement : RunStatement) : Bool :=
  trustedComputeRequiredDigest statement.algorithmHash &&
  trustedComputeRequiredDigest statement.inputHash &&
  trustedComputeRequiredDigest statement.parametersHash &&
  trustedComputeRequiredDigest statement.domainHash &&
  trustedComputeRequiredDigest statement.outputHash &&
  trustedComputeRequiredDigest statement.nonce &&
  trustedComputeRequiredDigest statement.targetProfileHash &&
  trustedComputeRequiredDigest statement.trustProfileHash &&
  trustedComputeRequiredDigest statement.artifacts.sourceTreeHash &&
  trustedComputeRequiredDigest statement.artifacts.hostExecutableHash &&
  isCanonicalSHA256 statement.artifacts.deviceCubinHash &&
  trustedComputeRequiredDigest statement.artifacts.kernelManifestHash

private def backendEvidenceCheck
    (statement : RunStatement) (evidence : TrustedComputeEvidence) : Bool :=
  match evidence.backend with
  | .azureSEVSNPCPU =>
      statement.target == .azureSEVSNPCPU &&
      statement.trust == .azureSEVSNPConfidentialCompute &&
      evidence.nvidiaEatHash == trustedComputeNotApplicableDigest &&
      evidence.nvidiaEvidenceHash == trustedComputeNotApplicableDigest &&
      statement.artifacts.deviceCubinHash == trustedComputeNotApplicableDigest
  | .azureNCCadsH100v5 =>
      statement.target == .nvidiaH100SM90 &&
      statement.trust == .nvidiaH100ConfidentialCompute &&
      trustedComputeRequiredDigest evidence.nvidiaEatHash &&
      trustedComputeRequiredDigest evidence.nvidiaEvidenceHash &&
      trustedComputeRequiredDigest statement.artifacts.deviceCubinHash

/-- Diagnostic pure-Lean check for receipts made with the development-only
bootstrap key.

This function is intentionally not part of `checkTrustedCompute`: production
keys are rotatable and are authenticated against the reviewed public-key
manifest by the fail-closed registry generator.  Source-registry membership,
not this diagnostic, is the authoritative Lean admission capability. -/
def TrustedComputeEvidence.bootstrapSignatureValidDiagnostic
    (evidence : TrustedComputeEvidence) : Bool :=
  evidence.verifierKeyId == trustedComputeVerifierKeyId &&
    RSA.verifyPkcs1v15Sha256 trustedComputeVerifierModulusHex
      evidence.canonicalSignedPayload evidence.signatureHex

/-- Recover the statement portion of a successful normalized claim. -/
def RunClaim.toStatement (claim : RunClaim) : RunStatement := {
  algorithmId := claim.algorithmId
  algorithmHash := claim.algorithmHash
  inputHash := claim.inputHash
  parametersHash := claim.parametersHash
  domainHash := claim.domainHash
  result := claim.result
  outputHash := claim.outputHash
  nonce := claim.nonce
  target := claim.target
  targetProfileHash := claim.targetProfileHash
  trust := claim.trust
  trustProfileHash := claim.trustProfileHash
  artifacts := claim.artifacts
}

/-- Lightweight structural conditions required of an entry already admitted
by the fail-closed source importer.  The final conjunct is deliberately the
exact production issuer tuple, making development-key rejection inspectable
and independently regression-testable in Lean.  The generator has already
validated canonical digest/signature syntax, the result-binding equation,
validity window, and cryptographic signature before these literal bytes can
enter the closed registry. -/
def TrustedComputeEvidence.sourcePinnedWellFormed
    (evidence : TrustedComputeEvidence) : Bool :=
  !evidence.receiptHash.isEmpty &&
  !evidence.runBundleHash.isEmpty &&
  !evidence.wireStatementHash.isEmpty &&
  !evidence.platformEvidenceHash.isEmpty &&
  !evidence.azureMaaTokenHash.isEmpty &&
  !evidence.amdSnpReportHash.isEmpty &&
  !evidence.tpmQuoteHash.isEmpty &&
  !evidence.tpmEventLogHash.isEmpty &&
  !evidence.verifierPolicyHash.isEmpty &&
  !evidence.verifierArtifactHash.isEmpty &&
  !evidence.startChallengeHash.isEmpty &&
  !evidence.resultBindingHash.isEmpty &&
  trustedComputeProductionVerifierProfileAllowed
    evidence.verifierKeyId
    (backendName evidence.backend)
    evidence.claim.targetProfileHash
    evidence.claim.trustProfileHash
    evidence.verifierArtifactHash
    evidence.verifierPolicyHash

/-- Production signed-receipt policy for CPU and composite H100 runs.

Local/mock/private-capability branches are rejected.  A receipt identifier is
accepted only when it resolves to exact data in the source-pinned import
registry.  This avoids introducing either a second axiom or a
`native_decide`-based cryptographic oracle.  Editing the registry is therefore
part of the one disclosed trusted-execution boundary.
-/
def checkTrustedCompute (statement : RunStatement) : Attestation → Bool
  | .local _ => false
  | .mock _ => false
  | .dgxOperatorSignature _ => false
  | .h100Hardware _ => false
  | .trustedCompute receiptHash =>
      match lookupImportedTrustedComputeRun receiptHash with
      | none => false
      | some evidence =>
          receiptHash == evidence.receiptHash &&
          statement.allMetadataPresent &&
          statement.allDigestsCanonical &&
          evidence.allMetadataPresent &&
          isCanonicalRSA3072Signature evidence.signatureHex &&
          evidence.sourcePinnedWellFormed &&
          evidence.claim.matches statement &&
          SHA256.digestString statement.result == statement.outputHash &&
          evidence.resultBindingHash == evidence.expectedResultBindingHash &&
          evidence.claim.nonce == evidence.startChallengeHash &&
          backendEvidenceCheck statement evidence

/-- Fast theorem handoff for one exact source-registry entry.

The registry generator emits a lookup theorem for each admitted receipt.  The
remaining premises are small structural facts about that literal entry; this
theorem prevents generated consumers from expanding thousands of characters
of Boolean equality into a multi-gigabyte `decide_cbv` proof. -/
theorem checkTrustedCompute_of_imported
    {receiptHash : Digest} {evidence : TrustedComputeEvidence}
    (lookup : lookupImportedTrustedComputeRun receiptHash = some evidence)
    (receiptBound : (receiptHash == evidence.receiptHash) = true)
    (metadata : evidence.claim.toStatement.allMetadataPresent = true)
    (statementDigests : evidence.claim.toStatement.allDigestsCanonical = true)
    (evidenceMetadata : evidence.allMetadataPresent = true)
    (signatureCanonical : isCanonicalRSA3072Signature evidence.signatureHex = true)
    (sourcePinned : evidence.sourcePinnedWellFormed = true)
    (claimMatches : evidence.claim.matches evidence.claim.toStatement = true)
    (resultHashBound : SHA256.digestString evidence.claim.toStatement.result =
      evidence.claim.toStatement.outputHash)
    (resultBindingBound : evidence.resultBindingHash =
      evidence.expectedResultBindingHash)
    (nonceBound : (evidence.claim.nonce == evidence.startChallengeHash) = true)
    (backendBound : backendEvidenceCheck evidence.claim.toStatement evidence = true)
    : checkTrustedCompute evidence.claim.toStatement
      (.trustedCompute receiptHash) = true := by
  simp only [checkTrustedCompute, lookup]
  simp [receiptBound, metadata, statementDigests, evidenceMetadata,
    signatureCanonical, sourcePinned, claimMatches, resultHashBound,
    resultBindingBound, nonceBound, backendBound]

@[simp] theorem checkTrustedCompute_local
    (statement : RunStatement) (claim : RunClaim) :
    checkTrustedCompute statement (.local claim) = false :=
  rfl

@[simp] theorem checkTrustedCompute_mock
    (statement : RunStatement) (claim : RunClaim) :
    checkTrustedCompute statement (.mock claim) = false :=
  rfl

end SparkInterval.Execution
