import SparkInterval.Execution.Trusted.DGXOperatorSignature
import SparkInterval.Execution.Trusted.H100Attestation

/-!
# Regression tests for the trusted execution bridges

These tests do not postulate or fabricate production evidence.  They establish
that development evidence is rejected for every statement and demonstrate the
two theorem shapes that later application proofs can consume: verified H100
hardware evidence or a deliberately trusted DGX operator assertion.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.ExecutionBridge

open SparkInterval.Execution
open SparkInterval.Execution.Trusted

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

#print axioms acceptedProductionCertificate_yieldsAlgorithmReturned

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

end SparkInterval.Tests.ExecutionBridge
