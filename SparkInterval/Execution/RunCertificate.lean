import SparkInterval.Execution.DGXOperatorPolicy
import SparkInterval.Execution.RegisteredAlgorithm

/-!
# Unified external-run certificates

`RunCertificate` is the single statement/evidence object consumed by the
trusted execution boundary.  Its Boolean checker dispatches to the exact
policy appropriate for the imported private evidence capability.  Local and
mock evidence are rejected by both policies.

This module contains no axiom.  Cryptographic verification and construction
of private evidence capabilities belong to a trusted external importer.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- The exact computation statement together with the evidence offered for
that statement. -/
structure RunCertificate where
  statement : RunStatement
  attestation : Attestation

namespace RunCertificate

/-- Accept exactly one of the supported production policies.  Each policy
checks the complete statement, successful completion, target, trust profile,
and every imported evidence binding appropriate to its evidence class. -/
def check (certificate : RunCertificate) : Bool :=
  checkDGXOperatorSignature certificate.statement certificate.attestation ||
    checkH100Attestation certificate.statement certificate.attestation

/-- Everything supplied by the sole accepted-run trust boundary.

`historical` preserves the exact returned-bytes fact used by the original API.
`registered` is stronger but fail-closed: it exposes formal execution
semantics only for a constructor of the closed `RegisteredAlgorithm` registry
whose complete identity and canonical input hashes match this statement.

The universal quantifier expresses the binding property expected of the
cryptographic digests checked by the trusted importer.  Thus collision and
second-preimage resistance for an accepted certificate are deliberately part
of the same single trust boundary; they are not claimed as theorems about the
pure Lean SHA-256 implementation. -/
structure ProducedOutcome (certificate : RunCertificate) : Prop where
  historical :
    AlgorithmReturned certificate.statement certificate.statement.result
  registered : ∀ invocation : RegisteredInvocation,
    invocation.statementCheck certificate.statement = true →
      invocation.Runs certificate.statement.result

@[simp] theorem check_local (statement : RunStatement) (claim : RunClaim) :
    check { statement, attestation := .local claim } = false := by
  rfl

@[simp] theorem check_mock (statement : RunStatement) (claim : RunClaim) :
    check { statement, attestation := .mock claim } = false := by
  rfl

theorem check_of_dgxOperatorSignature {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkDGXOperatorSignature statement attestation = true) :
    check { statement, attestation } = true := by
  simp [check, accepted]

theorem check_of_h100Attestation {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkH100Attestation statement attestation = true) :
    check { statement, attestation } = true := by
  simp [check, accepted]

end RunCertificate

end SparkInterval.Execution
