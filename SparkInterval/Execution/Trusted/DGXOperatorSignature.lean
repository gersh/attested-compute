import SparkInterval.Execution.Trusted.RunCertificate

/-!
# Fail-closed status of legacy DGX operator-signed certificates

The external Ed25519 verifier may establish that an approved operator key
signed an exact canonical run record.  A signature cannot establish that the
record is truthful or that DGX hardware executed it.  Consequently the legacy
structural check is diagnostic only and is excluded from the repository's
single run-certificate axiom.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Trusted

/-- Even a positive legacy DGX diagnostic is rejected by the unified theorem
admission checker. -/
theorem dgx_operator_signature_not_admitted
    {statement : RunStatement}
    {attestation : Attestation}
    (diagnostic : checkDGXOperatorSignature statement attestation = true) :
    RunCertificate.check { statement, attestation } = false := by
  cases attestation <;>
    simp_all [RunCertificate.check, checkDGXOperatorSignature,
      checkTrustedCompute]

end SparkInterval.Execution.Trusted
