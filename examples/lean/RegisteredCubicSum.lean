import SparkInterval.Execution.RegisteredCubicSumCertificate

/-!
# Unravelling a signed registered computation

The external bundle/signature contains ordinary bytes and hashes, not a Lean
proof term.  A trusted importer verifies the DGX operator signature or H100
attestation and constructs the private evidence capability.  The theorem below
then consumes one Boolean check and returns the exact historical result plus
the formal algorithm theorem.

The closed registry entry is:

* algorithm: `cubicSumDivThreeV1`;
* input: canonical decimal `"20000"` (inclusive upper bound);
* arithmetic: exact `ℚ`;
* output: canonical decimal natural; and
* meaning: `sum (x = 0 .. 20000) (x^3 / 3)`.

There is no `native_decide` and no 20,001-row result certificate.
-/

set_option autoImplicit false

namespace SparkInterval.Examples.RegisteredCubicSum

open SparkInterval.Execution

/- Running this tutorial file also evaluates the executable loop once and
prints `13334666700000000`. -/
#eval RegisteredAlgorithm.cubicSumDivThreeMachine 20000

/-- Pure arithmetic can be inspected independently of execution trust. -/
example :
    RegisteredAlgorithm.cubicSumDivThree 20000 =
      (13334666700000000 : ℚ) :=
  RegisteredAlgorithm.cubicSumDivThree_20000

/-- End-to-end certificate handoff.  `accepted` is normally discharged only
after the external verifier has checked the signature/attestation and exact
statement binding. -/
example {certificate : SignedResultCertificate}
    (accepted : certificate.outcomeCheckForRegisteredInvocation
      cubicSumDivThree20000Invocation = true) :
    certificate.statement.result = "13334666700000000" ∧
      AlgorithmReturned certificate.statement "13334666700000000" ∧
      RegisteredAlgorithm.cubicSumDivThreeMachine 20000 =
        13334666700000000 ∧
      RegisteredAlgorithm.cubicSumDivThree 20000 =
        (13334666700000000 : ℚ) := by
  have certified := certificate.certifyCubicSumDivThree20000 accepted
  exact ⟨certified.statementResult_eq, certified.execution,
    certified.operationalResult, certified.computation⟩

end SparkInterval.Examples.RegisteredCubicSum
