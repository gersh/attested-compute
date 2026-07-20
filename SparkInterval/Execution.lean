import SparkInterval.Execution.CompactAttestedVerifier
import SparkInterval.Execution.FormalPTXProgram
import SparkInterval.Execution.RegisteredCubicSumCertificate
import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.Execution.SignedZetaVerifier
import SparkInterval.Execution.Trusted.DGXOperatorSignature
import SparkInterval.Execution.Trusted.H100Attestation

/-!
# External execution certificates

All accepted execution modes route through `RunCertificate` and the sole
project trust axiom `accepted_run_certificate_sound`.  The DGX and H100 modules
export compatibility theorems, not additional axioms.
-/

/-!
# External execution claims and checked-result composition

This aggregate import exposes run statements, H100 and DGX structural policy,
the two explicit execution trust bridges, and the composition of an
operator-signed returned payload with the independently checked full result
certificate theorem, including the typed finite-height zeta endpoint view.
It also exposes the preferred closed-registry compact-result contract.  On
that route the sole axiom supplies the per-run formal `Runs` fact, while the
checker-to-mathematics soundness theorem remains an ordinary Lean obligation.
-/
