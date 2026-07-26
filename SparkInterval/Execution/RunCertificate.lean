import SparkInterval.Execution.DGXOperatorPolicy
import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.Execution.RegisteredAlgorithm
import SparkInterval.Execution.TrustedComputePolicy

/-!
# Unified external-run certificates

`RunCertificate` is the single statement/evidence object consumed by the
trusted execution boundary.  Its Boolean checker accepts only a hash in the
closed trusted-compute receipt registry.  The older H100 and DGX structural
checks remain diagnostic APIs and cannot reach the execution axiom.

This module contains no axiom.  Cryptographic verification and construction
of private evidence capabilities, or admission to the reviewed receipt
registry, belong to a trusted external importer.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- The exact computation statement together with the evidence offered for
that statement. -/
structure RunCertificate where
  statement : RunStatement
  attestation : Attestation

namespace RunCertificate

/-- Accept only the source-pinned trusted-compute receipt policy.

Keeping this definition single-route is defense in depth: neither the legacy
DGX operator-signature structure nor the legacy H100 structure can acquire
theorem authority merely by satisfying a public Boolean structural check. -/
def check (certificate : RunCertificate) : Bool :=
  checkTrustedCompute certificate.statement certificate.attestation

/-- Everything supplied by the sole accepted-run trust boundary.

`historical` preserves the exact returned-bytes fact used by the original API.
`registeredArchitecture` is the low-level, compact physical projection.  It
matches on this certificate's attestation, so the exact trusted-compute
receipt hash is not supplied independently by a caller.  The projection then
quantifies only over the closed architecture-invocation registry; its
machines, pins, entry points, and result meanings are source-installed rather
than caller-selectable.

`registered` is the temporary application-level compatibility projection.  It
is stronger but fail-closed: it exposes formal execution semantics only for a
constructor of the closed `RegisteredAlgorithm` registry whose complete
identity and canonical input hashes match this statement and, for production
invocations, whose exact reviewed receipt matches this attestation.  It
remains while existing consumers migrate to ordinary refinement theorems from
`registeredArchitecture`.

The universal quantifier expresses the binding property expected of the
cryptographic digests checked by the trusted importer.  Thus collision and
second-preimage resistance for an accepted certificate are deliberately part
of the same single trust boundary; they are not claimed as theorems about the
pure Lean SHA-256 implementation. -/
structure ProducedOutcome (certificate : RunCertificate) : Prop where
  historical :
    AlgorithmReturned certificate.statement certificate.statement.result
  registeredArchitecture :
    match certificate.attestation with
    | .trustedCompute receiptHash =>
        Architecture.RegisteredArchitectureOutcomes certificate.statement
          receiptHash
    | _ => True
  registered : ∀ invocation : RegisteredInvocation,
    invocation.certificateBindingCheck certificate.statement
        certificate.attestation = true →
      invocation.Runs certificate.statement.result

@[simp] theorem check_local (statement : RunStatement) (claim : RunClaim) :
    check { statement, attestation := .local claim } = false := by
  rfl

@[simp] theorem check_mock (statement : RunStatement) (claim : RunClaim) :
    check { statement, attestation := .mock claim } = false := by
  rfl

@[simp] theorem check_dgxOperatorSignature (statement : RunStatement)
    (evidence : DGXOperatorSignatureEvidence) :
    check { statement, attestation := .dgxOperatorSignature evidence } = false :=
  rfl

@[simp] theorem check_h100Hardware (statement : RunStatement)
    (evidence : H100HardwareEvidence) :
    check { statement, attestation := .h100Hardware evidence } = false :=
  rfl

/-- A valid pinned trusted-compute receipt is accepted by the unified policy. -/
theorem check_of_trustedCompute {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkTrustedCompute statement attestation = true) :
    check { statement, attestation } = true :=
  accepted

end RunCertificate

end SparkInterval.Execution
