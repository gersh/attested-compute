import SparkInterval.Execution.RegisteredCubicSumCertificate

/-!
# Closed registered-computation certificate tests

The concrete checks below exercise the registry identity without fabricating
private production evidence.  The final generic theorem shows exactly what an
externally accepted certificate unwraps into and prints its one-axiom
dependency.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredCubicSumCertificate

open SparkInterval.Certificate
open SparkInterval.Execution

private def invocation : RegisteredInvocation :=
  cubicSumDivThree20000Invocation

private def artifacts : ArtifactHashes := {
  sourceTreeHash := "source"
  hostExecutableHash := "host"
  deviceCubinHash := "cubin"
  kernelManifestHash := "manifest"
}

/-- A statement with all registry-controlled identity fields populated from
the closed invocation.  The remaining deployment fields would be bound by a
real DGX signature or H100 attestation. -/
private def statement : RunStatement := {
  algorithmId := invocation.algorithm.algorithmId
  algorithmHash := invocation.algorithm.algorithmHash
  inputHash := invocation.canonicalInputHash
  parametersHash := invocation.algorithm.canonicalParametersHash
  domainHash := invocation.algorithm.canonicalDomainHash
  result := cubicSumDivThree20000Output
  outputHash := SHA256.digestString cubicSumDivThree20000Output
  nonce := "nonce"
  target := .dgxSparkSM121
  targetProfileHash := "target-profile"
  trust := .localUnattested
  trustProfileHash := "trust-profile"
  artifacts
}

example : invocation.statementCheck statement = true := by
  simp [RegisteredInvocation.statementCheck,
    RegisteredInvocation.resultCheck,
    RegisteredInvocation.ResultAllowed,
    RegisteredInvocation.deploymentCheck, statement, invocation,
    cubicSumDivThree20000Invocation]

/-- Matching identity metadata cannot select malformed result bytes. -/
example :
    invocation.statementCheck { statement with result := "error" } = false := by
  apply
    RegisteredInvocation.statementCheck_eq_false_of_resultCheck_eq_false
  rfl

/-- A self-declared algorithm ID cannot select the registered semantics. -/
example :
    invocation.statementCheck
      { statement with algorithmId := "caller.selected.algorithm" } = false := by
  rfl

/-- The complete arithmetic result is proved symbolically, without
`native_decide` or enumeration at bound 20,000. -/
example :
    RegisteredAlgorithm.cubicSumDivThree 20000 =
      (13334666700000000 : ℚ) :=
  RegisteredAlgorithm.cubicSumDivThree_20000

/-- This is the requested theorem-unravelling interface.  The premise is the
single combined Boolean check on a real imported certificate. -/
theorem acceptedCertificate_unravelsCompleteAlgorithm
    {certificate : SignedResultCertificate}
    (accepted : certificate.outcomeCheckForRegisteredInvocation invocation = true) :
    certificate.resultCertificate = "13334666700000000" ∧
      certificate.statement.result = "13334666700000000" ∧
      AlgorithmReturned certificate.statement "13334666700000000" ∧
      RegisteredAlgorithm.cubicSumDivThreeMachine 20000 =
        13334666700000000 ∧
      RegisteredAlgorithm.cubicSumDivThree 20000 =
        (13334666700000000 : ℚ) := by
  have certified := certificate.certifyCubicSumDivThree20000 accepted
  exact ⟨certified.resultCertificate_eq, certified.statementResult_eq,
    certified.execution, certified.operationalResult, certified.computation⟩

#print axioms RegisteredAlgorithm.cubicSumDivThree_20000
#print axioms acceptedCertificate_unravelsCompleteAlgorithm

end SparkInterval.Tests.RegisteredCubicSumCertificate
