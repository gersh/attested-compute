import SparkInterval.Execution.Trusted.DGXOperatorSignature
import SparkInterval.Execution.Trusted.H100Attestation

/-!
The two execution bridges are deliberately assumptions, not mathematical
proofs. Local unsigned evidence cannot satisfy either positive policy.
-/

namespace SparkInterval.Examples

open SparkInterval.Execution
open SparkInterval.Execution.Trusted

example (statement : RunStatement) (claim : RunClaim) :
    checkDGXOperatorSignature statement (.local claim) = false := by
  rfl

example (statement : RunStatement) (claim : RunClaim) :
    checkH100Attestation statement (.local claim) = false := by
  rfl

example {statement : RunStatement} {evidence : Attestation}
    (accepted : checkDGXOperatorSignature statement evidence = true) :
    AlgorithmReturned statement statement.result :=
  dgx_operator_signed_run_sound accepted

end SparkInterval.Examples
