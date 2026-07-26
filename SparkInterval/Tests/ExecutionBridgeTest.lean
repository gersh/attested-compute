import SparkInterval.Execution.Trusted.DGXOperatorSignature
import SparkInterval.Execution.Trusted.H100Attestation
import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.Execution.SignedZetaVerifier
import SparkInterval.Execution.CompactAttestedVerifier
import SparkInterval.Execution.RegisteredCubicSumCertificate

/-!
# Regression tests for the single trusted execution bridge

These tests do not postulate or fabricate production evidence.  They establish
that development evidence is rejected for every statement and demonstrate
that generic, H100, DGX, and composed result theorems all depend on the same
single run-certificate axiom.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.ExecutionBridge

open SparkInterval.Execution
open SparkInterval.Execution.Trusted

example (statement : RunStatement) (claim : RunClaim) :
    RunCertificate.check { statement, attestation := .local claim } = false := by
  rfl

example (statement : RunStatement) (claim : RunClaim) :
    RunCertificate.check { statement, attestation := .mock claim } = false := by
  rfl

/-- The reviewed registry is intentionally empty before a production receipt
is imported, so every evidence envelope—including any guessed receipt hash—is
currently rejected by kernel reduction. -/
theorem emptySourceRegistry_rejectsEveryAttestation
    (statement : RunStatement) (attestation : Attestation) :
    RunCertificate.check { statement, attestation } = false := by
  cases attestation <;> rfl

/-- The checked-in bootstrap issuer tuple is useful only for importer tests;
it is definitionally excluded from production theorem admission. -/
example :
    trustedComputeProductionVerifierProfileAllowed
      "sparkinterval-bootstrap-rsa3072-2026-07"
      "azure_sevsnp_cpu"
      "27c1f9d99d4a2bafae009c09310eec8bd710663bcdc463f90244019da1f948d5"
      "dfec83fa16f6740346d6d9d79c02200e2bdd2757d30e6252b96e670c5b540e72"
      "88c9eae68eb300b2971a2bec9e5a26ff4179fd661d6b7d861e4c6557b9aaee14"
      "823412d1eacb67956220e532959f0104603057c88704863ca38e7cd188fda812" =
        false := by
  rfl

/-- Consequently no evidence carrying that exact development issuer tuple can
satisfy the source-pinned production predicate, regardless of its other
fields. -/
example (evidence : TrustedComputeEvidence)
    (key : evidence.verifierKeyId =
      "sparkinterval-bootstrap-rsa3072-2026-07")
    (backend : evidence.backend = .azureSEVSNPCPU)
    (artifact : evidence.verifierArtifactHash =
      "88c9eae68eb300b2971a2bec9e5a26ff4179fd661d6b7d861e4c6557b9aaee14")
    (policy : evidence.verifierPolicyHash =
      "823412d1eacb67956220e532959f0104603057c88704863ca38e7cd188fda812") :
    evidence.sourcePinnedWellFormed = false := by
  simp [TrustedComputeEvidence.sourcePinnedWellFormed,
    trustedComputeProductionVerifierProfileAllowed,
    trustedComputeAllowedVerifierProfiles, key, backend, artifact, policy]

/-- The exact generic handoff requested by downstream applications: an
accepted certificate proves that its named computation returned its bound
outcome. -/
theorem acceptedRunCertificate_yieldsProducedOutcome
    {certificate : RunCertificate}
    (accepted : certificate.check = true) :
    certificate.ProducedOutcome :=
  checked_run_certificate_sound accepted

#print axioms acceptedRunCertificate_yieldsProducedOutcome

/-- The stronger registered projection comes from the same sole axiom and a
closed invocation-identity check. -/
theorem acceptedRunCertificate_yieldsRegisteredRun
    {certificate : RunCertificate}
    {invocation : RegisteredInvocation}
    (accepted : certificate.check = true)
    (bound : invocation.certificateBindingCheck certificate.statement
      certificate.attestation = true) :
    invocation.Runs certificate.statement.result :=
  accepted_registered_run_sound accepted bound

#print axioms acceptedRunCertificate_yieldsRegisteredRun

/-- The exact trusted-compute receipt hash also yields the closed physical
architecture projection through the same sole axiom.  No machine, pin bundle,
entry point, or mathematical claim is an argument to this theorem. -/
theorem acceptedTrustedCompute_yieldsRegisteredArchitecture
    {statement : RunStatement}
    {receiptHash : Digest}
    (accepted :
      checkTrustedCompute statement (.trustedCompute receiptHash) = true) :
    Architecture.RegisteredArchitectureOutcomes statement receiptHash :=
  accepted_registered_architecture_outcomes accepted

#print axioms acceptedTrustedCompute_yieldsRegisteredArchitecture

/-- Every source-scale constructor rejects bytes outside its two canonical
success/failure tokens before the execution axiom can expose `Runs`. -/
example (statement : RunStatement) :
    RegisteredInvocation.hurstSharedFourResidualProductionV2.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.ch25PsiLemma92ProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.ramareZunigaLemma62ProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.helfgottProp1224ProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.ch25A7BoundaryProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.plattHead2e4ProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.plattDirichletTheorem71ProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.plattTrudgianFiniteRHProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.helfgottPlattGoldbachProductionV1.resultCheck
        { statement with result := "error" } = false ∧
      RegisteredInvocation.goldbach10Pow27ProductionV1.resultCheck
        { statement with result := "error" } = false := by
  rfl

/-- Every constructor has at least one safe output satisfying its fixed
`Runs` relation.  Source constructors use their explicit failure branch; this
does not assert that a successful external computation occurred. -/
example (invocation : RegisteredInvocation) :
    ∃ output : String, invocation.Runs output :=
  RegisteredInvocation.runs_satisfiable invocation

#print axioms RegisteredInvocation.runs_satisfiable

example (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.local claim) = false := by
  rfl

example (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.mock claim) = false := by
  rfl

/-- A positive legacy H100 structural diagnostic still cannot reach theorem
admission.  Only a source-pinned trusted-compute receipt can do that. -/
theorem legacyH100Diagnostic_isNotAdmitted
    {statement : RunStatement}
    {attestation : Attestation}
    (diagnostic : checkH100Attestation statement attestation = true) :
    RunCertificate.check { statement, attestation } = false :=
  h100_attestation_not_admitted diagnostic

example (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.local claim) = false := by
  rfl

example (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.mock claim) = false := by
  rfl

/-- An operator signature remains useful provenance, but its diagnostic cannot
reach the physical-execution axiom. -/
theorem legacyDGXDiagnostic_isNotAdmitted
    {statement : RunStatement}
    {attestation : Attestation}
    (diagnostic : checkDGXOperatorSignature statement attestation = true) :
    RunCertificate.check { statement, attestation } = false :=
  dgx_operator_signature_not_admitted diagnostic

#print axioms legacyH100Diagnostic_isNotAdmitted
#print axioms legacyDGXDiagnostic_isNotAdmitted

/-! The composed results expose provenance, exact result/hash binding, and
independently checked mathematics. They add no project axiom beyond the same
generic run-certificate bridge used above. -/

#print axioms SparkInterval.Execution.SignedResultCertificate.outcomeCheckForAlgorithm_sound
#print axioms SparkInterval.Execution.SignedResultCertificate.checkSumUpperBoundForAlgorithm_sound
#print axioms SparkInterval.Execution.SignedResultCertificate.outcomeCheckForFormalPTX_sound
#print axioms SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightWithCountCertificate
#print axioms SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromCheckedRows
#print axioms SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromPositiveCount
#print axioms SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromPositiveRows
#print axioms SparkInterval.Execution.SignedResultCertificate.certifyCompactFiniteHeightZeta
#print axioms SparkInterval.Execution.SignedResultCertificate.certifyRegisteredCompactFiniteHeightZeta
#print axioms SparkInterval.Execution.SignedResultCertificate.certifyCubicSumDivThree20000

end SparkInterval.Tests.ExecutionBridge
