import SparkInterval.Execution.DGXOperatorPolicy

/-!
# EXPLICITLY TRUSTED DGX operator-signature execution bridge

The external Ed25519 verifier establishes that an approved operator key signed
the exact canonical run record.  A signature cannot establish that the record
is truthful or that DGX hardware executed it.  This file exposes precisely that
additional operator-trust assumption as a named axiom, separate from the
axiom-free arithmetic and application proofs.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Trusted

/-- **DGX OPERATOR-TRUSTED PHYSICAL-EXECUTION BOUNDARY.**

If a trusted importer supplies a cryptographically verified operator-signature
capability and the complete claim matches the expected DGX statement, this
axiom imports the operator's assertion that the algorithm ran and returned the
serialized result.  It is intentionally not described as hardware evidence.
-/
axiom dgx_operator_signed_run_sound
    {statement : RunStatement}
    {attestation : Attestation}
    (accepted : checkDGXOperatorSignature statement attestation = true) :
    AlgorithmReturned statement statement.result

end SparkInterval.Execution.Trusted
