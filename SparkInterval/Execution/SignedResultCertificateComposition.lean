import SparkInterval.Execution.SignedResultCertificate
import SparkInterval.Execution.Trusted.RunCertificate

/-!
# Composition of attested execution and mathematical result certificates

This is the downstream proof layer. Once the one named run-certificate trust
axiom has supplied the approved physical-return assertion and, for a closed
registered invocation, its fixed `Runs` relation, all remaining steps
are proved:

1. the returned string is exactly the checked certificate text;
2. its SHA-256 digest is exactly the statement's output digest; and
3. the existing full-certificate theorem supplies the mathematical result.

The full certificate supports division, but that fact must not be confused
with the generated typed-PTX whole-kernel theorem, whose source language is
currently polynomial. In particular, the division-capable real-zeta POC is
not yet an instance of the typed-PTX whole-kernel refinement theorem, and this
generic composition does not itself prove an analytic theorem about
`riemannZeta` or zeta zeros.

In particular, `AlgorithmReturned` is not used to prove the full-certificate
`mathematics` field; that field comes independently from the checker. The
registered API separately retains the fixed `Runs` projection supplied by the
sole axiom. No universal backend/hardware-conformance proposition is claimed
by this module.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate
open SparkInterval.Execution.Trusted

namespace SignedResultCertificate

/-- The accepted run certificate and exact payload binding prove that the
named computation returned the supplied result-certificate bytes.  The only
project axiom used is `accepted_run_certificate_sound`. -/
theorem outcomeCheck_sound {certificate : SignedResultCertificate}
    (hcheck : certificate.outcomeCheck = true) :
    certificate.CertifiedOutcome := by
  simp only [outcomeCheck, Bool.and_eq_true] at hcheck
  have hbinding := resultBindingCheck_sound hcheck.2
  have hproduced := accepted_run_certificate_sound
    (certificate := certificate.toRunCertificate) hcheck.1
  have hexecution := hproduced.historical
  change AlgorithmReturned certificate.statement certificate.statement.result at hexecution
  rw [hbinding.1] at hexecution
  exact {
    produced := hproduced
    execution := hexecution
    binding := hbinding
  }

/-- Pinning the expected algorithm identity proves that the exact
caller-selected computation returned the exact certificate bytes. -/
theorem outcomeCheckForAlgorithm_sound
    {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity}
    (hcheck : certificate.outcomeCheckForAlgorithm expected = true) :
    certificate.CertifiedOutcomeForAlgorithm expected := by
  simp only [outcomeCheckForAlgorithm, Bool.and_eq_true] at hcheck
  exact {
    identity := executableIdentityCheck_sound hcheck.1
    outcome := outcomeCheck_sound hcheck.2
  }

/-- A successful closed-registry check uses the registered projection of the
same sole axiom to expose the complete fixed algorithm execution relation.
No caller-provided execution predicate is accepted. -/
theorem outcomeCheckForRegisteredInvocation_sound
    {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation}
    (hcheck :
      certificate.outcomeCheckForRegisteredInvocation invocation = true) :
    certificate.CertifiedOutcomeForRegisteredInvocation invocation := by
  simp only [outcomeCheckForRegisteredInvocation, Bool.and_eq_true] at hcheck
  have houtcome := outcomeCheck_sound hcheck.2
  have hbinding :
      invocation.statementCheck certificate.statement = true ∧
        invocation.receiptCheck certificate.attestation = true := by
    simpa only [RegisteredInvocation.certificateBindingCheck,
      Bool.and_eq_true] using hcheck.1
  have hrun := houtcome.produced.registered invocation hcheck.1
  change invocation.Runs certificate.statement.result at hrun
  rw [houtcome.binding.1] at hrun
  exact {
    identity := RegisteredInvocation.statementCheck_sound hbinding.1
    receiptBound := hbinding.2
    outcome := houtcome
    run := hrun
  }

/-- A structurally accepted run certificate whose exact returned certificate
passes the full row-wise upper-bound checker establishes the combined
provenance, byte-binding, and mathematical claim. -/
theorem checkUpperBound_sound {certificate : SignedResultCertificate}
    {boundBits : Nat}
    (hcheck : certificate.checkUpperBound boundBits = true) :
    certificate.CertifiedUpperBound boundBits := by
  simp only [checkUpperBound, Bool.and_eq_true] at hcheck
  have hbinding := resultBindingCheck_sound hcheck.1.2
  have hproduced := accepted_run_certificate_sound
    (certificate := certificate.toRunCertificate) hcheck.1.1
  exact {
    produced := hproduced
    execution := hproduced.historical
    binding := hbinding
    mathematics := by
      rw [hbinding.1]
      exact impliesTheorem hcheck.2
  }

/-- Aggregate version of `checkUpperBound_sound`. -/
theorem checkSumUpperBound_sound {certificate : SignedResultCertificate}
    {bound : ℚ}
    (hcheck : certificate.checkSumUpperBound bound = true) :
    certificate.CertifiedSumUpperBound bound := by
  simp only [checkSumUpperBound, Bool.and_eq_true] at hcheck
  have hbinding := resultBindingCheck_sound hcheck.1.2
  have hproduced := accepted_run_certificate_sound
    (certificate := certificate.toRunCertificate) hcheck.1.1
  exact {
    produced := hproduced
    execution := hproduced.historical
    binding := hbinding
    mathematics := by
      rw [hbinding.1]
      exact impliesSumTheorem hcheck.2
  }

/-- Exact-algorithm row-wise handoff.  The identity equalities and all
non-execution fields are ordinary Lean consequences; the nested `produced`
field crosses `accepted_run_certificate_sound` and `execution` projects its
historical component. -/
theorem checkUpperBoundForAlgorithm_sound
    {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity} {boundBits : Nat}
    (hcheck : certificate.checkUpperBoundForAlgorithm expected boundBits = true) :
    certificate.CertifiedUpperBoundForAlgorithm expected boundBits := by
  simp only [checkUpperBoundForAlgorithm, Bool.and_eq_true] at hcheck
  exact {
    identity := executableIdentityCheck_sound hcheck.1
    checked := checkUpperBound_sound hcheck.2
  }

/-- Exact-algorithm finite-sum handoff. -/
theorem checkSumUpperBoundForAlgorithm_sound
    {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity} {bound : ℚ}
    (hcheck :
      certificate.checkSumUpperBoundForAlgorithm expected bound = true) :
    certificate.CertifiedSumUpperBoundForAlgorithm expected bound := by
  simp only [checkSumUpperBoundForAlgorithm, Bool.and_eq_true] at hcheck
  exact {
    identity := executableIdentityCheck_sound hcheck.1
    checked := checkSumUpperBound_sound hcheck.2
  }

end SignedResultCertificate

end SparkInterval.Execution
