import SparkInterval.Execution.RunCertificate

/-!
# SINGLE TRUST AXIOM for external-run certificates

All cryptographic and physical-execution trust is concentrated here.  An
external importer must verify the relevant signature or hardware attestation,
freshness, approved measurements, and exact statement binding before it can
construct the private evidence capability accepted by `RunCertificate.check`.

The conclusion has two deliberate projections.  It records the exact
historical returned bytes, and it gives the fixed formal `Runs` relation for
any matching member of the closed registered-algorithm registry.  The latter
is the one trusted per-run bridge across signature verification, artifact
measurement, compilation/backend behavior, and physical execution.  It does
not assert a universal hardware-refinement theorem.

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
    (accepted : certificate.check = true) :
    certificate.ProducedOutcome

/-- Derived registered-algorithm handoff.  This is a projection of the sole
axiom above, not another trust assumption. -/
theorem accepted_registered_run_sound
    {certificate : RunCertificate}
    {invocation : RegisteredInvocation}
    (accepted : certificate.check = true)
    (bound : invocation.statementCheck certificate.statement = true) :
    invocation.Runs certificate.statement.result :=
  (accepted_run_certificate_sound accepted).registered invocation bound

/-- Historical compatibility projection for callers that only need the exact
returned bytes and not the registered formal execution relation. -/
theorem accepted_algorithm_returned
    {certificate : RunCertificate}
    (accepted : certificate.check = true) :
    AlgorithmReturned certificate.statement certificate.statement.result :=
  (accepted_run_certificate_sound accepted).historical

end SparkInterval.Execution.Trusted
