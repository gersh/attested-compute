import SparkInterval.Execution.CompactAttestedVerifier

/-! Type-level tests for compact attested-verifier composition. -/

set_option autoImplicit false

namespace SparkInterval.Tests.CompactAttestedVerifier

open SparkInterval.Execution

example {Summary : Type}
    {certificate : SignedResultCertificate}
    {program : FormalPTXProgram}
    {contract : CompactVerifierContract Summary}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForFormalPTX program = true)
    (hdecode : contract.decode certificate.resultCertificate = some summary)
    (refinement : contract.ExecutionRefines program)
    (sound : contract.Sound program) :
    CertifiedCompactVerifierOutcome certificate program contract summary :=
  certificate.certifyCompactVerifierOutcome hcheck hdecode refinement sound

example {Summary : Type}
    {certificate : SignedResultCertificate}
    {program : FormalPTXProgram}
    {decode : String → Option Summary}
    {semantics : FormalPTXProgram → RunStatement → Summary → Prop}
    {heightOf : Summary → ℝ}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForFormalPTX program = true)
    (hdecode : decode certificate.resultCertificate = some summary)
    (refinement :
      CompactVerifierContract.ExecutionRefines
        (compactFiniteHeightZetaContract decode semantics heightOf) program)
    (verifierSound :
      ∀ {statement : RunStatement} {result : Summary},
        semantics program statement result →
          FiniteHeightZetaClaim (heightOf result)) :
    FiniteHeightZetaClaim (heightOf summary) := by
  have certified := certificate.certifyCompactFiniteHeightZeta
    hcheck hdecode refinement verifierSound
  exact certified.mathematics

/-- Preferred closed-registry path: there is no caller-supplied
physical-to-formal refinement premise. -/
example {Summary : Type}
    {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation}
    {contract : RegisteredCompactVerifierContract Summary}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForRegisteredInvocation invocation = true)
    (hdecode : contract.decode certificate.resultCertificate = some summary)
    (sound : contract.Sound invocation) :
    CertifiedRegisteredCompactVerifierOutcome
      certificate invocation contract summary :=
  certificate.certifyRegisteredCompactVerifierOutcome hcheck hdecode sound

/-- Registered compact zeta composition likewise needs only the checker-to-
mathematics proof after certificate acceptance. -/
example {Summary : Type}
    {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation}
    {decode : String → Option Summary}
    {heightOf : Summary → ℝ}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForRegisteredInvocation invocation = true)
    (hdecode : decode certificate.resultCertificate = some summary)
    (verifierSound :
      ∀ {output : String} {result : Summary},
        invocation.Runs output →
          decode output = some result →
            FiniteHeightZetaClaim (heightOf result)) :
    FiniteHeightZetaClaim (heightOf summary) := by
  have certified := certificate.certifyRegisteredCompactFiniteHeightZeta
    hcheck hdecode verifierSound
  exact certified.mathematics

/-! ### Concrete registered cubic-sum contract -/

/-- Decode the compact output as a canonical natural and require the exact
registered result.  The contract contains no execution relation of its own;
that relation is fixed by `RegisteredInvocation.cubicSumDivThree20000V1`. -/
private def cubicSumContract : RegisteredCompactVerifierContract Nat := {
  decode := RegisteredAlgorithm.parseCanonicalNat
  claim := fun summary => summary = 13334666700000000
}

/-- Pure, axiom-free soundness of the compact cubic-sum contract. -/
theorem cubicSumContract_sound :
    cubicSumContract.Sound
      RegisteredInvocation.cubicSumDivThree20000V1 := by
  intro output summary hrun hdecode
  change summary = 13334666700000000
  change RegisteredAlgorithm.parseCanonicalNat output = some summary at hdecode
  rcases hrun with ⟨_, result, houtput, hresult⟩
  have hsummary : summary = result :=
    Option.some.inj (hdecode.symm.trans houtput)
  have hresultNat : result = 13334666700000000 := by
    rw [← hresult]
    exact RegisteredAlgorithm.cubicSumDivThreeMachine_20000
  exact hsummary.trans hresultNat

/-- Once the registered certificate is accepted, its decoded compact summary
is the exact finite-sum result.  No `ExecutionRefines` premise is needed: the
sole accepted-run boundary supplies the fixed registered `Runs` fact. -/
theorem acceptedCubicSumCertificate_summary
    {certificate : SignedResultCertificate}
    {summary : Nat}
    (hcheck : certificate.outcomeCheckForRegisteredInvocation
      RegisteredInvocation.cubicSumDivThree20000V1 = true)
    (hdecode : cubicSumContract.decode certificate.resultCertificate =
      some summary) :
    summary = 13334666700000000 := by
  have certified := certificate.certifyRegisteredCompactVerifierOutcome
    hcheck hdecode cubicSumContract_sound
  exact certified.mathematics

#print axioms cubicSumContract_sound
#print axioms acceptedCubicSumCertificate_summary

end SparkInterval.Tests.CompactAttestedVerifier
