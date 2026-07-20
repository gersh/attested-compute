import SparkInterval.Execution.SignedZetaEndpointPayload

/-! Type and reduction tests for the signed endpoint-payload bridge. -/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.SignedZetaEndpointPayload

open SparkInterval.Certificate
open SparkInterval.Execution
open SparkInterval.Zeta

private def digest : String :=
  "0000000000000000000000000000000000000000000000000000000000000000"

private def negativeOne : RawInterval :=
  ⟨0xbff0000000000000, 0xbff0000000000000⟩

private def positiveOne : RawInterval :=
  ⟨0x3ff0000000000000, 0x3ff0000000000000⟩

/-- Two singleton rows and exact identity-expression results form one bracket
around the root of the identity function. -/
private def endpointPayload : FullCertificate := {
  variableCount := 1
  expression := .var 0
  rows := #[#[negativeOne], #[positiveOne]]
  results := #[negativeOne, positiveOne]
  batchHash := digest
  resultHash := digest
}

private def expectedBracket : RationalBracket := {
  lower := -1
  upper := 1
  lowerValue := ⟨-1, -1⟩
  upperValue := ⟨1, 1⟩
}

private theorem endpointAt_zero :
    SignedZetaEndpointPayload.endpointAt? endpointPayload 0 = some expectedBracket := by
  decide_cbv

example :
    SignedZetaEndpointPayload.endpointViewShapeCheck endpointPayload 1 = true := by
  decide_cbv

example :
    (SignedZetaEndpointPayload.endpointFamily endpointPayload 1).check = true := by
  apply RationalBracketFamily.check_eq_true.mpr
  constructor
  · intro i
    fin_cases i
    simp only [SignedZetaEndpointPayload.endpointFamily]
    rw [endpointAt_zero]
    norm_num [expectedBracket, RationalBracket.IsValid, RatInterval.IsValid]
  · intro i j hij
    fin_cases i
    fin_cases j
    simp at hij

example : endpointPayload.check = true := by
  decide_cbv

/-- Public composition shape: exact formal-program identity and the historical
run cross the existing execution boundary, while the parsed endpoint data is
supplied by pure checks. -/
theorem acceptedTypedEndpointPayload
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    (hcheck : certificate.check program = true) :
    certificate.CertifiedForFormalPTX program :=
  SignedZetaEndpointPayload.check_sound hcheck

/-- Endpoint enclosure remains a visible application proof premise. -/
theorem acceptedEndpointZeros
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ}
    (hcheck : certificate.check program = true)
    (hencloses : ∀ i,
      ((SignedZetaEndpointPayload.endpointFamily
        certificate.parsed count).entries i).EnclosesEndpoints f) :
    certificate.signed.CertifiedFormalPTXOutcome program ∧
      ∃ zeros : ZeroCertificate f count,
        ∀ i,
          (zeros.brackets i).lower =
              ((SignedZetaEndpointPayload.endpointFamily
                certificate.parsed count).entries i).lower ∧
            (zeros.brackets i).upper =
              ((SignedZetaEndpointPayload.endpointFamily
                certificate.parsed count).entries i).upper :=
  SignedZetaEndpointPayload.check_exists_zeroCertificate hcheck hencloses

theorem checkedRowsGiveEndpointEnclosures
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {f : ℝ → ℝ}
    (checked : certificate.CheckedPayload)
    (realizes : certificate.EndpointRowsRealize f) :
    ∀ i,
      ((SignedZetaEndpointPayload.endpointFamily
        certificate.parsed count).entries i).EnclosesEndpoints f :=
  checked.enclosesEndpoints realizes

/-- Accepted signed endpoint data is cross-bound to the exact canonical input
of the formal program, not merely to an internally self-consistent batch. -/
theorem acceptedPayloadBindsFormalInput
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    (hcheck : certificate.check program = true) :
    certificate.parsed.batchHash =
      SHA256.digestString program.canonicalInput :=
  (SignedZetaEndpointPayload.check_sound hcheck).batch.2

theorem mismatchedPayloadBatchIsRejected
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    (hne : certificate.parsed.batchHash ≠
      SHA256.digestString program.canonicalInput) :
    certificate.check program = false :=
  SignedZetaEndpointPayload.check_eq_false_of_batchHash_ne hne

#print axioms acceptedTypedEndpointPayload
#print axioms acceptedEndpointZeros
#print axioms checkedRowsGiveEndpointEnclosures
#print axioms acceptedPayloadBindsFormalInput
#print axioms mismatchedPayloadBatchIsRejected

end SparkInterval.Tests.SignedZetaEndpointPayload
