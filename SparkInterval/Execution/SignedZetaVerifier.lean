import SparkInterval.Execution.SignedZetaEndpointPayload
import SparkInterval.Zeta.EvenReflectionCertificate
import SparkInterval.Zeta.HardyZContract
import SparkInterval.Zeta.SymmetricCount

/-!
# End-to-end signed finite-height zeta verification

This module is the narrow final composition for the current implementation.
It keeps the two logically different results together without conflating them:

* the sole project trust axiom establishes that the exact formally identified
  historical run returned the exact checked payload bytes; and
* ordinary Lean proofs turn the checked endpoint family, a proved Hardy-Z
  model and endpoint enclosure theorem, and a multiplicity-aware total-count
  upper bound into the finite-height theorem about Mathlib's `riemannZeta`.

Attestation does not manufacture any analytic fact.  In particular, the
Hardy-Z representation, endpoint enclosures, and analytic multiplicity upper
bound are explicit arguments.  A production Riemann-Siegel/Turing checker must
construct those arguments.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Zeta

/-- Accepted-run provenance paired with the exact finite-height mathematical
conclusion.  Only the nested produced outcome crosses the project
run-certificate axiom; this full-payload route proves `mathematics`
independently of its registered projection. -/
structure CertifiedZetaVerification
    {count : Nat}
    (certificate : SignedZetaEndpointPayload count)
    (program : FormalPTXProgram)
    (height : ℝ) : Prop where
  historical : certificate.signed.CertifiedFormalPTXOutcome program
  mathematics : ∀ z ∈ criticalRectangle height,
    riemannZeta z = 0 → z.re = (1 : ℝ) / 2

namespace SignedZetaEndpointPayload

/-- Complete composition using a direct analytic multiplicity upper bound
equal to the number of checked sign-change brackets. -/
theorem verifyFiniteHeight
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (hencloses : ∀ i,
      ((endpointFamily certificate.parsed count).entries i).EnclosesEndpoints f)
    (hlower : ∀ i,
      -height ≤
        (((endpointFamily certificate.parsed count).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((endpointFamily certificate.parsed count).entries i).upper : ℝ) ≤
        height)
    (multiplicityUpper : ZetaMultiplicityCountUpperBound height count) :
    CertifiedZetaVerification certificate program height := by
  have certified := check_sound hcheck
  refine {
    historical := certified.formalOutcome
    mathematics := ?_
  }
  exact model.verifyEndpointFamily
    (endpointFamily certificate.parsed count)
    certified.payload.family hencloses hlower hupper
    multiplicityUpper.toZetaZeroCountUpperBound

/-- Stronger arithmetic composition: instead of assuming the final endpoint
enclosures, callers prove that the checked expression realizes the selected
real evaluator on each singleton endpoint row.  `FullCertificate.check_sound`
then derives the enclosures from the returned arithmetic rows. -/
theorem verifyFiniteHeightFromCheckedRows
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (realizes : certificate.EndpointRowsRealize f)
    (hlower : ∀ i,
      -height ≤
        (((endpointFamily certificate.parsed count).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((endpointFamily certificate.parsed count).entries i).upper : ℝ) ≤
        height)
    (multiplicityUpper : ZetaMultiplicityCountUpperBound height count) :
    CertifiedZetaVerification certificate program height := by
  have checked := check_sound hcheck
  exact certificate.verifyFiniteHeight hcheck model
    (checked.payload.enclosesEndpoints realizes) hlower hupper
    multiplicityUpper

/-- Conventional positive-ordinate count entry point.  The factor of two,
zeta conjugation/multiplicity symmetry, and real-axis boundary premise are all
visible.  The endpoint payload contains the matching positive and negative
critical-line brackets, while the analytic count need only be produced for
`0 < im z ≤ height`. -/
theorem verifyFiniteHeightFromPositiveCount
    {positiveCount : Nat}
    {certificate : SignedZetaEndpointPayload (2 * positiveCount)}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (realizes : certificate.EndpointRowsRealize f)
    (hlower : ∀ i,
      -height ≤
        (((endpointFamily certificate.parsed (2 * positiveCount)).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((endpointFamily certificate.parsed (2 * positiveCount)).entries i).upper : ℝ) ≤
        height)
    (positiveUpper : PositiveZetaMultiplicityCountUpperBound
      height positiveCount)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    CertifiedZetaVerification certificate program height := by
  exact certificate.verifyFiniteHeightFromCheckedRows hcheck model realizes
    hlower hupper
    (positiveUpper.toZetaMultiplicityCountUpperBound symmetry noRealAxis)

/-- Positive-row high-bound variant.  For an even Hardy-Z evaluator, the
checked positive brackets are reflected inside Lean, so the signed payload
contains only `positiveCount` brackets (two arithmetic rows each) rather than
materializing the matching negative-side rows.  Evaluator evenness remains a
visible analytic theorem; attestation does not supply it. -/
theorem verifyFiniteHeightFromPositiveRows
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
      0 < (((endpointFamily certificate.parsed positiveCount).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((endpointFamily certificate.parsed positiveCount).entries i).upper : ℝ) ≤
        height)
    (positiveUpper : PositiveZetaMultiplicityCountUpperBound
      height positiveCount)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    CertifiedZetaVerification certificate program height := by
  have checked := check_sound hcheck
  let positiveFamily := endpointFamily certificate.parsed positiveCount
  let symmetricFamily := positiveFamily.reflectPositive
  have hpositiveValid : positiveFamily.IsValid :=
    RationalBracketFamily.check_eq_true.mp checked.payload.family
  have hpositiveRat : ∀ i, 0 < (positiveFamily.entries i).lower := by
    intro i
    exact_mod_cast hpositive i
  have hsymmetricValid : symmetricFamily.IsValid :=
    RationalBracketFamily.reflectPositive_isValid
      hpositiveValid hpositiveRat
  have hsymmetricCheck : symmetricFamily.check = true :=
    RationalBracketFamily.check_eq_true.mpr hsymmetricValid
  have hpositiveEncloses : ∀ i,
      (positiveFamily.entries i).EnclosesEndpoints f := by
    exact checked.payload.enclosesEndpoints realizes
  have hsymmetricEncloses : ∀ i,
      (symmetricFamily.entries i).EnclosesEndpoints f :=
    RationalBracketFamily.reflectPositive_enclosesEndpoints
      heven hpositiveEncloses
  have hsymmetricLower : ∀ i,
      -height ≤ ((symmetricFamily.entries i).lower : ℝ) :=
    RationalBracketFamily.reflectPositive_lower_bound
      hheight hpositive hupper
  have hsymmetricUpper : ∀ i,
      ((symmetricFamily.entries i).upper : ℝ) ≤ height :=
    RationalBracketFamily.reflectPositive_upper_bound
      hheight hpositive hupper
  have totalUpper : ZetaZeroCountUpperBound
      height (positiveCount + positiveCount) := by
    simpa [two_mul] using
      (positiveUpper.toZetaZeroCountUpperBound symmetry noRealAxis)
  refine {
    historical := checked.formalOutcome
    mathematics := ?_
  }
  exact model.verifyEndpointFamily symmetricFamily hsymmetricCheck
    hsymmetricEncloses hsymmetricLower hsymmetricUpper totalUpper

/-- Variant accepting the small checked arithmetic wrapper around an analytic
multiplicity count.  This permits the analytic checker to produce a tighter
claim than the endpoint-family count while making the final comparison
executable and exact. -/
theorem verifyFiniteHeightWithCountCertificate
    {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ} {height : ℝ}
    (hcheck : certificate.check program = true)
    (model : HardyZModel f height)
    (hencloses : ∀ i,
      ((endpointFamily certificate.parsed count).entries i).EnclosesEndpoints f)
    (hlower : ∀ i,
      -height ≤
        (((endpointFamily certificate.parsed count).entries i).lower : ℝ))
    (hupper : ∀ i,
      (((endpointFamily certificate.parsed count).entries i).upper : ℝ) ≤
        height)
    (countCertificate : ZetaMultiplicityCountCertificate)
    (hcountCheck : countCertificate.check = true)
    (hbound : countCertificate.upperBound = count)
    (analyticUpper : ZetaMultiplicityCountUpperBound height
      countCertificate.claimedMultiplicityCount) :
    CertifiedZetaVerification certificate program height := by
  have totalUpper : ZetaZeroCountUpperBound height count := by
    have checked := countCertificate.check_sound hcountCheck analyticUpper
    simpa only [hbound] using checked
  have certified := check_sound hcheck
  refine {
    historical := certified.formalOutcome
    mathematics := ?_
  }
  exact model.verifyEndpointFamily
    (endpointFamily certificate.parsed count)
    certified.payload.family hencloses hlower hupper totalUpper

end SignedZetaEndpointPayload

end SparkInterval.Execution
