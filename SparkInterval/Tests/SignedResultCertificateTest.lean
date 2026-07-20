import SparkInterval.Execution.SignedResultCertificateComposition

/-!
# Run/result-certificate composition tests

The concrete tests exercise the pure byte/hash binding and fail-closed local
evidence path. The generic wrapper theorems expose the dependency profile of
the complete composition: provenance uses only the one run-certificate axiom,
while result binding and mathematics are ordinary Lean proofs.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.SignedResultCertificate

open SparkInterval.Certificate
open SparkInterval.Execution

private def payload : String := "{}"

private def artifacts : ArtifactHashes := {
  sourceTreeHash := "source"
  hostExecutableHash := "host"
  deviceCubinHash := "cubin"
  kernelManifestHash := "manifest"
}

private def statement : RunStatement := {
  algorithmId := "example.algorithm.v1"
  algorithmHash := "algorithm"
  inputHash := "input"
  parametersHash := "parameters"
  domainHash := "domain"
  result := payload
  outputHash := SHA256.digestString payload
  nonce := "nonce"
  target := .dgxSparkSM121
  targetProfileHash := "target-profile"
  trust := .localUnattested
  trustProfileHash := "trust-profile"
  artifacts
}

private def claim : RunClaim := {
  algorithmId := statement.algorithmId
  algorithmHash := statement.algorithmHash
  inputHash := statement.inputHash
  parametersHash := statement.parametersHash
  domainHash := statement.domainHash
  result := statement.result
  outputHash := statement.outputHash
  nonce := statement.nonce
  target := statement.target
  targetProfileHash := statement.targetProfileHash
  trust := statement.trust
  trustProfileHash := statement.trustProfileHash
  artifacts := statement.artifacts
  completion := .successful
}

private def localCertificate : SignedResultCertificate := {
  statement
  attestation := .local claim
  resultCertificate := payload
}

private def expectedIdentity : ExpectedExecutableIdentity := {
  algorithmId := statement.algorithmId
  algorithmHash := statement.algorithmHash
}

example : localCertificate.executableIdentityCheck expectedIdentity = true := by
  rfl

example :
    localCertificate.executableIdentityCheck
      { expectedIdentity with algorithmHash := "different" } = false := by
  rfl

/-- Exact result bytes and their digest are both checked. -/
example : localCertificate.resultBindingCheck = true := by
  simp only [SignedResultCertificate.resultBindingCheck, localCertificate,
    statement, beq_self_eq_true, Bool.true_and]

/-- Substituting different result bytes fails the binding check. -/
example :
    ({ localCertificate with resultCertificate := "[]" } :
      SignedResultCertificate).resultBindingCheck = false := by
  rfl

/-- A matching but merely local claim cannot enter the execution trust path. -/
example : localCertificate.executionAccepted = false := by
  rfl

/-- Smallest public handoff: the accepted named computation returned the exact
bound result-certificate bytes. -/
theorem acceptedOutcome
    {certificate : SignedResultCertificate}
    (hcheck : certificate.outcomeCheck = true) :
    certificate.CertifiedOutcome :=
  SignedResultCertificate.outcomeCheck_sound hcheck

/-- Exact caller-pinned computation and exact returned bytes. -/
theorem acceptedOutcomeForAlgorithm
    {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity}
    (hcheck : certificate.outcomeCheckForAlgorithm expected = true) :
    certificate.CertifiedOutcomeForAlgorithm expected :=
  SignedResultCertificate.outcomeCheckForAlgorithm_sound hcheck

/-- Public row-bound composition shape for later application proofs. -/
theorem acceptedCheckedUpperBound
    {certificate : SignedResultCertificate} {boundBits : Nat}
    (hcheck : certificate.checkUpperBound boundBits = true) :
    certificate.CertifiedUpperBound boundBits :=
  SignedResultCertificate.checkUpperBound_sound hcheck

/-- Public finite-sum composition shape for later application proofs. -/
theorem acceptedCheckedSumUpperBound
    {certificate : SignedResultCertificate} {bound : ℚ}
    (hcheck : certificate.checkSumUpperBound bound = true) :
    certificate.CertifiedSumUpperBound bound :=
  SignedResultCertificate.checkSumUpperBound_sound hcheck

/-- Strongest public handoff: the run statement is also proved to name the
caller's exact expected executable ID and digest. -/
theorem acceptedCheckedUpperBoundForAlgorithm
    {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity} {boundBits : Nat}
    (hcheck :
      certificate.checkUpperBoundForAlgorithm expected boundBits = true) :
    certificate.CertifiedUpperBoundForAlgorithm expected boundBits :=
  SignedResultCertificate.checkUpperBoundForAlgorithm_sound hcheck

theorem acceptedCheckedSumUpperBoundForAlgorithm
    {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity} {bound : ℚ}
    (hcheck :
      certificate.checkSumUpperBoundForAlgorithm expected bound = true) :
    certificate.CertifiedSumUpperBoundForAlgorithm expected bound :=
  SignedResultCertificate.checkSumUpperBoundForAlgorithm_sound hcheck

#print axioms acceptedOutcome
#print axioms acceptedOutcomeForAlgorithm
#print axioms acceptedCheckedUpperBound
#print axioms acceptedCheckedSumUpperBound
#print axioms acceptedCheckedUpperBoundForAlgorithm
#print axioms acceptedCheckedSumUpperBoundForAlgorithm

end SparkInterval.Tests.SignedResultCertificate
