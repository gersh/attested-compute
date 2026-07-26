import SparkInterval.Execution.RunCertificate

/-!
# SINGLE TRUST AXIOM for external-run certificates

All cryptographic and physical-execution trust is concentrated here.  An
external importer must verify the relevant signature or hardware attestation,
freshness, approved measurements, and exact statement binding before it can
admit the signed receipt to the source-pinned trusted-compute registry.

The conclusion has three deliberate projections.  It records the exact
historical returned bytes; it gives a compact physical architecture outcome
for the exact receipt hash carried by a trusted-compute attestation; and,
temporarily for compatibility, it gives the fixed formal `Runs` relation for
any matching member of the closed registered-algorithm registry.  The
architecture projection is the preferred trusted per-run bridge across
signature verification, artifact measurement, compilation/backend behavior,
and physical execution.  It does not assert a universal hardware-refinement
theorem.

Algorithm soundness downstream is still an ordinary Lean theorem from the
fixed `Runs` relation to an application claim.  Callers cannot supply the
meaning of `Runs` themselves.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Trusted

/-- **SOLE PROJECT EXECUTION/CERTIFICATE TRUST BOUNDARY.**

An accepted run certificate establishes that its exact algorithm, artifacts,
inputs, parameters, and domain produced its exact bound result, including the
registry-fixed formal semantics when the statement matches a registered
invocation. -/
axiom accepted_run_certificate_sound
    {certificate : RunCertificate}
    (accepted : checkTrustedCompute certificate.statement
      certificate.attestation = true) :
    certificate.ProducedOutcome

/-- Compatibility handoff from the unified checker.  Its proof unfolds the
current definition of `RunCertificate.check`; widening that checker in the
future cannot silently widen the axiom premise. -/
theorem checked_run_certificate_sound
    {certificate : RunCertificate}
    (accepted : certificate.check = true) :
    certificate.ProducedOutcome :=
  accepted_run_certificate_sound (by
    simpa only [RunCertificate.check] using accepted)

/-- Derived registered-algorithm handoff.  Its binding premise includes the
exact reviewed production receipt, where applicable.  This is a projection of
the sole axiom above, not another trust assumption. -/
theorem accepted_registered_run_sound
    {certificate : RunCertificate}
    {invocation : RegisteredInvocation}
    (accepted : certificate.check = true)
    (bound : invocation.certificateBindingCheck certificate.statement
      certificate.attestation = true) :
    invocation.Runs certificate.statement.result :=
  (checked_run_certificate_sound accepted).registered invocation bound

/-- Derived compact architecture handoff for the exact hash in a
`trustedCompute` attestation.

The caller chooses neither a receipt hash independent of the accepted
attestation nor a machine, measurement scheme, pin bundle, entry point, or
claim proposition.  Those are fixed by the closed
`RegisteredArchitectureInvocation` registry.  This theorem is a projection
of `accepted_run_certificate_sound`, not another trust assumption. -/
theorem accepted_registered_architecture_outcomes
    {statement : RunStatement}
    {receiptHash : Digest}
    (accepted :
      checkTrustedCompute statement (.trustedCompute receiptHash) = true) :
    Architecture.RegisteredArchitectureOutcomes statement receiptHash :=
  (accepted_run_certificate_sound
    (certificate := {
      statement := statement
      attestation := .trustedCompute receiptHash
    })
    accepted).registeredArchitecture

/-- Historical compatibility projection for callers that only need the exact
returned bytes and not the registered formal execution relation. -/
theorem accepted_algorithm_returned
    {certificate : RunCertificate}
    (accepted : certificate.check = true) :
    AlgorithmReturned certificate.statement certificate.statement.result :=
  (checked_run_certificate_sound accepted).historical

end SparkInterval.Execution.Trusted
