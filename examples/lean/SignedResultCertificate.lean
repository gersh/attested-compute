import SparkInterval.Execution

/-!
An application consumes one Boolean acceptance proof and receives three
separate facts: the certificate-trusted physical return, exact result/hash
binding, and independently checked mathematics. `AlgorithmReturned` is not
used to prove the mathematical field.

The current full certificate language includes division. The generated
typed-PTX whole-kernel theorem does not, so this example must not be presented
as a Lean proof that the division-capable zeta CUDA kernel implements the typed
PTX machine.
-/

set_option autoImplicit false

namespace SparkInterval.Examples

open SparkInterval.Execution

example {certificate : SignedResultCertificate}
    (accepted : certificate.outcomeCheck = true) :
    certificate.CertifiedOutcome :=
  SignedResultCertificate.outcomeCheck_sound accepted

example {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity}
    (accepted : certificate.outcomeCheckForAlgorithm expected = true) :
    certificate.CertifiedOutcomeForAlgorithm expected :=
  SignedResultCertificate.outcomeCheckForAlgorithm_sound accepted

example {certificate : SignedResultCertificate} {bound : ℚ}
    (accepted : certificate.checkSumUpperBound bound = true) :
    certificate.CertifiedSumUpperBound bound :=
  SignedResultCertificate.checkSumUpperBound_sound accepted

example {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity} {bound : ℚ}
    (accepted :
      certificate.checkSumUpperBoundForAlgorithm expected bound = true) :
    certificate.CertifiedSumUpperBoundForAlgorithm expected bound :=
  SignedResultCertificate.checkSumUpperBoundForAlgorithm_sound accepted

#print axioms SparkInterval.Execution.SignedResultCertificate.checkUpperBound_sound
#print axioms SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound
#print axioms SparkInterval.Execution.SignedResultCertificate.checkSumUpperBound_sound
#print axioms SparkInterval.Execution.SignedResultCertificate.checkSumUpperBoundForAlgorithm_sound

end SparkInterval.Examples
