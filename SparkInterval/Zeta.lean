import SparkInterval.Zeta.ChunkCertificate
import SparkInterval.Zeta.CriticalLine
import SparkInterval.Zeta.EndpointCertificate
import SparkInterval.Zeta.EvenReflectionCertificate
import SparkInterval.Zeta.HardyZ
import SparkInterval.Zeta.HardyZContract
import SparkInterval.Zeta.MultiplicityCount
import SparkInterval.Zeta.PairedTuringClosureCertificate
import SparkInterval.Zeta.PT21ArtifactBinding
import SparkInterval.Zeta.StreamingEndpointCertificate
import SparkInterval.Zeta.StreamingChunkVerifier
import SparkInterval.Zeta.SymmetricCount
import SparkInterval.Zeta.TouchingEndpointCertificate
import SparkInterval.Zeta.TouchingVerifier
import SparkInterval.Zeta.Verifier
import SparkInterval.Zeta.ZeroCertificate

/-!
# Finite-height Riemann-zeta verification foundations

This aggregate import exposes the critical-rectangle target, ordered and
chunked zero certificates, the executable rational endpoint-family checker
and its resumable endpoint/chunk transitions, positive-only reflection for an
even evaluator, strict sign brackets whose closed endpoints may touch,
the Hardy-Z model contract, the multiplicity-aware total-count bridge, the
explicit positive-ordinate/symmetric-count boundary, and the finite-height
verifier composition.  It also exposes the compact PT21 block decoder that
derives the fixed `21/512` lattice geometry and constructs the three touching
endpoint streams plus their paired Turing closure.

It does not provide the missing certified Hardy-Z/Riemann-Siegel evaluator or
the analytic Turing/argument-principle proof required to construct a concrete
`ZetaMultiplicityCountUpperBound`.
-/
