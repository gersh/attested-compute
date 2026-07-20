import SparkInterval.Execution.SignedResultCertificateComposition

/-!
# End-to-end registered computation certificate example

This module demonstrates the intended certificate architecture on the complete
algorithm

`sum (x = 0 .. 20000) (x^3 / 3)`

with exact rational division.  A signed or hardware-attested statement does
not contain a Lean theorem.  It binds the closed registry entry, the canonical
input `"20000"`, and the canonical returned bytes.  The sole accepted-run
axiom exposes the registry-fixed `Runs` relation, and ordinary Lean theorems
then recover the exact output and mathematical equality.

No 20,001-row result certificate, `native_decide`, or evaluation of 20,001
summands is required.  The arithmetic theorem uses the symbolic sum-of-cubes
identity proved in `RegisteredAlgorithm`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- The closed tutorial invocation used by the end-to-end theorem. -/
def cubicSumDivThree20000Invocation : RegisteredInvocation :=
  .cubicSumDivThree20000V1

/-- Canonical exact output bytes for the tutorial computation. -/
def cubicSumDivThree20000Output : String :=
  "13334666700000000"

/-- Everything Lean recovers after one accepted certificate passes the closed
registry and exact result-binding checks. -/
structure CertifiedCubicSumDivThree20000
    (certificate : SignedResultCertificate) : Prop where
  certified : certificate.CertifiedOutcomeForRegisteredInvocation
    cubicSumDivThree20000Invocation
  resultCertificate_eq :
    certificate.resultCertificate = cubicSumDivThree20000Output
  statementResult_eq :
    certificate.statement.result = cubicSumDivThree20000Output
  execution :
    AlgorithmReturned certificate.statement cubicSumDivThree20000Output
  operationalResult :
    RegisteredAlgorithm.cubicSumDivThreeMachine 20000 =
      13334666700000000
  operationalSound :
    (RegisteredAlgorithm.cubicSumDivThreeMachine 20000 : ℚ) =
      RegisteredAlgorithm.cubicSumDivThree 20000
  computation :
    RegisteredAlgorithm.cubicSumDivThree 20000 =
      (13334666700000000 : ℚ)
  accumulatorFitsU64 : ∀ {count : Nat}, count ≤ 20001 →
    RegisteredAlgorithm.cubicNumeratorLoop count < 2 ^ 64
  squareFitsU64 : ∀ {x : Nat}, x ≤ 20000 → x ^ 2 < 2 ^ 64
  cubeFitsU64 : ∀ {x : Nat}, x ≤ 20000 → x ^ 3 < 2 ^ 64
  accumulatorStepFitsU64 : ∀ {x : Nat}, x ≤ 20000 →
    RegisteredAlgorithm.cubicNumeratorLoop x + x ^ 3 < 2 ^ 64
  quotientFitsU64 :
    RegisteredAlgorithm.cubicSumDivThreeMachine 20000 < 2 ^ 64

namespace SignedResultCertificate

/-- End-to-end certificate theorem for the complete tutorial algorithm.

`hcheck` includes:

* production evidence acceptance under the unified certificate policy;
* exact returned-text and output-hash binding; and
* exact matching against the closed invocation's algorithm ID, formal
  definition digest, input digest, parameter digest, and domain digest.

The one project axiom is used only inside
`outcomeCheckForRegisteredInvocation_sound`.  Exact output decoding and the
sum theorem are proved in Lean. -/
theorem certifyCubicSumDivThree20000
    {certificate : SignedResultCertificate}
    (hcheck : certificate.outcomeCheckForRegisteredInvocation
      cubicSumDivThree20000Invocation = true) :
    CertifiedCubicSumDivThree20000 certificate := by
  have certified :=
    outcomeCheckForRegisteredInvocation_sound hcheck
  have hresult :=
    RegisteredInvocation.cubicSumDivThree20000V1_result certified.run
  have hexecution := certified.outcome.execution
  rw [hresult.1] at hexecution
  exact {
    certified := certified
    resultCertificate_eq := hresult.1
    statementResult_eq := certified.outcome.binding.1.trans hresult.1
    execution := hexecution
    operationalResult := RegisteredAlgorithm.cubicSumDivThreeMachine_20000
    operationalSound :=
      RegisteredAlgorithm.cubicSumDivThreeMachine_sound_20000
    computation := hresult.2
    accumulatorFitsU64 := RegisteredAlgorithm.cubicNumeratorLoop_lt_u64
    squareFitsU64 := RegisteredAlgorithm.square_lt_u64
    cubeFitsU64 := RegisteredAlgorithm.cube_lt_u64
    accumulatorStepFitsU64 :=
      RegisteredAlgorithm.cubicNumeratorStep_lt_u64
    quotientFitsU64 := RegisteredAlgorithm.cubicSumDivThreeMachine_lt_u64
  }

end SignedResultCertificate

end SparkInterval.Execution
