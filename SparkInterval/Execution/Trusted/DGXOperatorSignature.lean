import SparkInterval.Execution.Trusted.RunCertificate

/-!
# Compatibility theorem for DGX operator-signed certificates

The external Ed25519 verifier establishes that an approved operator key signed
the exact canonical run record.  A signature cannot establish that the record
is truthful or that DGX hardware executed it.  This compatibility theorem now
routes the accepted policy through the repository's single run-certificate
axiom in `Trusted.RunCertificate`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Trusted

/-- Backward-compatible DGX handoff.  It introduces no axiom beyond
`accepted_run_certificate_sound`. -/
theorem dgx_operator_signed_run_sound
    {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkDGXOperatorSignature statement attestation = true) :
    AlgorithmReturned statement statement.result := by
  exact accepted_algorithm_returned
    (certificate := { statement, attestation })
    (RunCertificate.check_of_dgxOperatorSignature accepted)

end SparkInterval.Execution.Trusted
