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

/-- The exact generic handoff requested by downstream applications: an
accepted certificate proves that its named computation returned its bound
outcome. -/
theorem acceptedRunCertificate_yieldsProducedOutcome
    {certificate : RunCertificate}
    (accepted : certificate.check = true) :
    certificate.ProducedOutcome :=
  accepted_run_certificate_sound accepted

#print axioms acceptedRunCertificate_yieldsProducedOutcome

/-- The stronger registered projection comes from the same sole axiom and a
closed invocation-identity check. -/
theorem acceptedRunCertificate_yieldsRegisteredRun
    {certificate : RunCertificate}
    {invocation : RegisteredInvocation}
    (accepted : certificate.check = true)
    (bound : invocation.statementCheck certificate.statement = true) :
    invocation.Runs certificate.statement.result :=
  accepted_registered_run_sound accepted bound

#print axioms acceptedRunCertificate_yieldsRegisteredRun

example (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.local claim) = false := by
  rfl

example (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.mock claim) = false := by
  rfl

/-- This is the intended handoff theorem: callers supply acceptance of a real
production certificate; the trusted bridge supplies the external run fact. -/
theorem acceptedProductionCertificate_yieldsAlgorithmReturned
    {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkH100Attestation statement attestation = true) :
    AlgorithmReturned statement statement.result :=
  h100_attested_run_sound accepted

example (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.local claim) = false := by
  rfl

example (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.mock claim) = false := by
  rfl

/-- This theorem makes the self-signed mode's trust choice explicit.  Its axiom
does not claim that Ed25519 is hardware attestation. -/
theorem acceptedDGXOperatorCertificate_yieldsAlgorithmReturned
    {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkDGXOperatorSignature statement attestation = true) :
    AlgorithmReturned statement statement.result :=
  dgx_operator_signed_run_sound accepted

#print axioms acceptedDGXOperatorCertificate_yieldsAlgorithmReturned

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
