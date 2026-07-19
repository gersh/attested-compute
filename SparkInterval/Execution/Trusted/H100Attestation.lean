import SparkInterval.Execution.H100Policy

/-!
# EXPLICITLY TRUSTED H100 execution bridge

This file contains the repository's H100 hardware-attestation execution axiom.
It is not a cryptographic proof in Lean.  The axiom trusts that production
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

/-- **SOLE H100 HARDWARE/CRYPTOGRAPHIC TRUST BOUNDARY.**

An accepted production attestation is imported as the fact that the exact
algorithm statement completed and returned its exact serialized result.
-/
axiom h100_attested_run_sound
    {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkH100Attestation statement attestation = true) :
    AlgorithmReturned statement statement.result

end SparkInterval.Execution.Trusted
