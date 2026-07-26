import SparkInterval.Execution.Trusted.DGXOperatorSignature
import SparkInterval.Execution.Trusted.H100Attestation

/-!
Only the source-pinned trusted-compute receipt policy reaches the deliberate
run-certificate assumption.  The older DGX and H100 structural checkers remain
diagnostic and are rejected by the unified theorem-admission checker.
-/

namespace SparkInterval.Examples

open SparkInterval.Execution
open SparkInterval.Execution.Trusted

example {certificate : RunCertificate}
    (accepted : certificate.check = true) :
    certificate.ProducedOutcome :=
  checked_run_certificate_sound accepted

example (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.local claim) = false := by
  rfl

example (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.local claim) = false := by
  rfl

example {statement : RunStatement} {evidence : Attestation}
    (diagnostic : checkDGXOperatorSignature statement evidence = true) :
    RunCertificate.check { statement, attestation := evidence } = false :=
  dgx_operator_signature_not_admitted diagnostic

end SparkInterval.Examples
