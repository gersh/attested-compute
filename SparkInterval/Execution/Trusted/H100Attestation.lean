import SparkInterval.Execution.Trusted.RunCertificate

/-!
# Compatibility theorem for H100 execution certificates

This file retains the H100-specific public theorem shape.  It is not a
cryptographic proof in Lean.  The single run-certificate axiom trusts that production
`H100HardwareEvidence` was created only after authentic NVIDIA H100
confidential-computing evidence was cryptographically verified, that the
physical run completed, and that the verified evidence truthfully contains its
`RunClaim`.

The executable checker still prevents claim substitution: algorithm ID/hash, input,
parameters, domain, exact result, output, nonce, target, trust profile, every
artifact hash, and successful completion must all match.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Trusted

/-- Backward-compatible H100 handoff.  It introduces no axiom beyond
`accepted_run_certificate_sound`. -/
theorem h100_attested_run_sound
    {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkH100Attestation statement attestation = true) :
    AlgorithmReturned statement statement.result := by
  exact accepted_algorithm_returned
    (certificate := { statement, attestation })
    (RunCertificate.check_of_h100Attestation accepted)

end SparkInterval.Execution.Trusted
