import SparkInterval.Execution.Trusted.RunCertificate

/-!
# Fail-closed status of legacy H100 evidence structures

The old structural checker can still diagnose claim substitution in imported
`H100HardwareEvidence`, but it does not validate the evidence chain and cannot
reach the execution axiom.  The authoritative route is a signed, externally
appraised receipt admitted to `TrustedComputeRegistry`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Trusted

/-- Even a positive legacy H100 diagnostic is rejected by the unified theorem
admission checker. -/
theorem h100_attestation_not_admitted
    {statement : RunStatement}
    {attestation : Attestation}
    (diagnostic : checkH100Attestation statement attestation = true) :
    RunCertificate.check { statement, attestation } = false := by
  cases attestation <;>
    simp_all [RunCertificate.check, checkH100Attestation,
      checkTrustedCompute]

end SparkInterval.Execution.Trusted
