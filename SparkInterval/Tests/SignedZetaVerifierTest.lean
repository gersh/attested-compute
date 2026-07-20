import SparkInterval.Execution.SignedZetaVerifier

/-! Theorem-shape and axiom-boundary tests for the final signed composition. -/

set_option autoImplicit false

namespace SparkInterval.Tests.SignedZetaVerifier

open SparkInterval.Execution
open SparkInterval.Zeta

theorem acceptedRunAndAnalyticEvidence_provesFiniteHeightZeta
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (hencloses : ∀ i,
      ((SignedZetaEndpointPayload.endpointFamily
        certificate.parsed count).entries i).EnclosesEndpoints f)
    (hlower : ∀ i,
      -height ≤
        (((SignedZetaEndpointPayload.endpointFamily
          certificate.parsed count).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((SignedZetaEndpointPayload.endpointFamily
        certificate.parsed count).entries i).upper : ℝ) ≤ height)
    (multiplicityUpper : ZetaMultiplicityCountUpperBound height count) :
    CertifiedZetaVerification certificate program height :=
  certificate.verifyFiniteHeight hcheck model hencloses hlower hupper
    multiplicityUpper

theorem acceptedRunAndCheckedCount_provesFiniteHeightZeta
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (hencloses : ∀ i,
      ((SignedZetaEndpointPayload.endpointFamily
        certificate.parsed count).entries i).EnclosesEndpoints f)
    (hlower : ∀ i,
      -height ≤
        (((SignedZetaEndpointPayload.endpointFamily
          certificate.parsed count).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((SignedZetaEndpointPayload.endpointFamily
        certificate.parsed count).entries i).upper : ℝ) ≤ height)
    (countCertificate : ZetaMultiplicityCountCertificate)
    (hcountCheck : countCertificate.check = true)
    (hbound : countCertificate.upperBound = count)
    (analyticUpper : ZetaMultiplicityCountUpperBound height
      countCertificate.claimedMultiplicityCount) :
    CertifiedZetaVerification certificate program height :=
  certificate.verifyFiniteHeightWithCountCertificate hcheck model hencloses
    hlower hupper countCertificate hcountCheck hbound analyticUpper

/-- The full arithmetic checker can discharge endpoint enclosures from the
weaker row-realization semantics of the selected evaluator. -/
theorem acceptedRunAndCheckedRows_provesFiniteHeightZeta
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (realizes : certificate.EndpointRowsRealize f)
    (hlower : ∀ i,
      -height ≤
        (((SignedZetaEndpointPayload.endpointFamily
          certificate.parsed count).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((SignedZetaEndpointPayload.endpointFamily
        certificate.parsed count).entries i).upper : ℝ) ≤ height)
    (multiplicityUpper : ZetaMultiplicityCountUpperBound height count) :
    CertifiedZetaVerification certificate program height :=
  certificate.verifyFiniteHeightFromCheckedRows hcheck model realizes
    hlower hupper multiplicityUpper

theorem acceptedRunAndPositiveCount_provesFiniteHeightZeta
    {positiveCount : Nat}
    {certificate : SignedZetaEndpointPayload (2 * positiveCount)}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (realizes : certificate.EndpointRowsRealize f)
    (hlower : ∀ i,
      -height ≤
        (((SignedZetaEndpointPayload.endpointFamily certificate.parsed
          (2 * positiveCount)).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((SignedZetaEndpointPayload.endpointFamily certificate.parsed
        (2 * positiveCount)).entries i).upper : ℝ) ≤ height)
    (positiveUpper : PositiveZetaMultiplicityCountUpperBound
      height positiveCount)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    CertifiedZetaVerification certificate program height :=
  certificate.verifyFiniteHeightFromPositiveCount hcheck model realizes
    hlower hupper positiveUpper symmetry noRealAxis

/-- An even evaluator needs only the positive arithmetic rows; Lean reflects
the checked family to obtain the matching negative zero brackets. -/
theorem acceptedRunAndPositiveRows_provesFiniteHeightZeta
    {positiveCount : Nat}
    {certificate : SignedZetaEndpointPayload positiveCount}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (heven : Function.Even f)
    (realizes : certificate.EndpointRowsRealize f)
    (hheight : 0 ≤ height)
    (hpositive : ∀ i,
      0 < (((SignedZetaEndpointPayload.endpointFamily certificate.parsed
        positiveCount).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((SignedZetaEndpointPayload.endpointFamily certificate.parsed
        positiveCount).entries i).upper : ℝ) ≤ height)
    (positiveUpper : PositiveZetaMultiplicityCountUpperBound
      height positiveCount)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    CertifiedZetaVerification certificate program height :=
  certificate.verifyFiniteHeightFromPositiveRows hcheck model heven realizes
    hheight hpositive hupper positiveUpper symmetry noRealAxis

#print axioms acceptedRunAndAnalyticEvidence_provesFiniteHeightZeta
#print axioms acceptedRunAndCheckedCount_provesFiniteHeightZeta
#print axioms acceptedRunAndCheckedRows_provesFiniteHeightZeta
#print axioms acceptedRunAndPositiveCount_provesFiniteHeightZeta
#print axioms acceptedRunAndPositiveRows_provesFiniteHeightZeta

end SparkInterval.Tests.SignedZetaVerifier
