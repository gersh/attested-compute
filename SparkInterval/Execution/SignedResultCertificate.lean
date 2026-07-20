import SparkInterval.Certificate
import SparkInterval.Execution.RunCertificate

/-!
# Attested execution result certificates

This module defines the data and pure checks used to compose a unified external
run certificate with a Lean-checkable full result certificate.  The historical
name `SignedResultCertificate` is retained for compatibility; its execution
evidence may be an approved DGX operator signature or H100 attestation.  This
module contains no execution or cryptographic axiom.

The historical projection records that the bound physical execution returned
the exact result named by the statement.  For a closed registered invocation,
the same sole trust boundary additionally exposes the registry-fixed `Runs`
relation for this accepted run.  This is a per-run assumption, not a universal
PTX/backend/hardware conformance theorem.

On the full-certificate route, the mathematical conclusion does not follow
from the historical run fact. It is proved separately by parsing and checking
`resultCertificate` with the axiom-free full-certificate checker. On the
closed-registry route, an ordinary algorithm-soundness theorem may instead
derive mathematics from the fixed `Runs` relation. Both routes first bind the
exact result text and its SHA-256 digest to the accepted statement.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- An external execution claim together with the exact canonical full result
certificate expected to be the statement's returned payload. -/
structure SignedResultCertificate where
  statement : RunStatement
  attestation : Attestation
  resultCertificate : String

/-- The executable identity that an application proof expects the signed
statement to name.  These are literal statement pins; they do not by
themselves prove that a cubin was compiled from a particular PTX module. -/
structure ExpectedExecutableIdentity where
  algorithmId : String
  algorithmHash : Digest
  deriving Repr, DecidableEq, BEq

namespace SignedResultCertificate

/-- Forget the mathematical payload and expose the one external-run
certificate consumed by the unified trust boundary. -/
def toRunCertificate (certificate : SignedResultCertificate) : RunCertificate := {
  statement := certificate.statement
  attestation := certificate.attestation
}

/-- Structural acceptance of the private execution-evidence capability and
its complete statement binding. Cryptographic verification and creation of
the private capability remain outside this pure checker. -/
def executionAccepted (certificate : SignedResultCertificate) : Bool :=
  certificate.toRunCertificate.check

/-- Compatibility name for callers of the original DGX-only API.  New code
should use `executionAccepted`. -/
def signatureAccepted (certificate : SignedResultCertificate) : Bool :=
  certificate.executionAccepted

/-- Compare the signed statement's executable identity with the identity
pinned by a downstream theorem. -/
def executableIdentityCheck (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) : Bool :=
  certificate.statement.algorithmId == expected.algorithmId &&
    certificate.statement.algorithmHash == expected.algorithmHash

/-- Propositional form of `executableIdentityCheck`. -/
def ExecutableIdentityBound (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) : Prop :=
  certificate.statement.algorithmId = expected.algorithmId ∧
    certificate.statement.algorithmHash = expected.algorithmHash

/-- Bind both the exact returned text and its bytes' SHA-256 digest to the run
statement. `SHA256.digestString` hashes the UTF-8 bytes of the Lean string; the
wire importer must therefore supply the exact canonical, newline-free JSON
artifact bytes as `resultCertificate`. -/
def resultBindingCheck (certificate : SignedResultCertificate) : Bool :=
  certificate.statement.result == certificate.resultCertificate &&
    SHA256.digestString certificate.resultCertificate ==
      certificate.statement.outputHash

/-- Propositional form of the exact result-payload and output-hash binding. -/
def ResultBound (certificate : SignedResultCertificate) : Prop :=
  certificate.statement.result = certificate.resultCertificate ∧
    SHA256.digestString certificate.resultCertificate =
      certificate.statement.outputHash

/-- Check only the trusted run boundary and the exact returned-text/hash
binding.  This is the smallest check whose soundness theorem says that the
named computation returned the exact supplied result certificate. -/
def outcomeCheck (certificate : SignedResultCertificate) : Bool :=
  certificate.executionAccepted && certificate.resultBindingCheck

/-- Exact historical outcome established by `outcomeCheck`: the named
computation returned these certificate bytes, and those bytes have the output
digest bound by the statement. -/
structure CertifiedOutcome (certificate : SignedResultCertificate) : Prop where
  produced : certificate.toRunCertificate.ProducedOutcome
  execution : AlgorithmReturned certificate.statement certificate.resultCertificate
  binding : certificate.ResultBound

/-- Require the exact application-pinned algorithm ID/hash in addition to the
accepted exact-outcome check. -/
def outcomeCheckForAlgorithm (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) : Bool :=
  certificate.executableIdentityCheck expected && certificate.outcomeCheck

/-- Strongest outcome-only handoff: the exact caller-pinned computation ran and
returned the exact supplied certificate bytes. -/
structure CertifiedOutcomeForAlgorithm
    (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) : Prop where
  identity : certificate.ExecutableIdentityBound expected
  outcome : certificate.CertifiedOutcome

/-- Require a closed registered invocation in addition to the accepted exact
outcome check. -/
def outcomeCheckForRegisteredInvocation
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) : Bool :=
  invocation.statementCheck certificate.statement && certificate.outcomeCheck

/-- Complete handoff for a registered invocation: exact statement identity,
the accepted historical outcome, exact returned bytes, and the fixed formal
execution relation. -/
structure CertifiedOutcomeForRegisteredInvocation
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation) : Prop where
  identity : invocation.StatementBound certificate.statement
  outcome : certificate.CertifiedOutcome
  run : invocation.Runs certificate.resultCertificate

/-- Check execution-certificate acceptance, exact result binding, and every row
of the full result certificate against one finite binary64 upper bound. -/
def checkUpperBound (certificate : SignedResultCertificate)
    (boundBits : Nat) : Bool :=
  certificate.executionAccepted && certificate.resultBindingCheck &&
    checkCanonicalFullCertificateUpperBound
      certificate.resultCertificate boundBits

/-- Check execution-certificate acceptance, exact result binding, and the
complete full result certificate against a finite-sum bound. -/
def checkSumUpperBound (certificate : SignedResultCertificate)
    (bound : ℚ) : Bool :=
  certificate.executionAccepted && certificate.resultBindingCheck &&
    checkCanonicalFullCertificateSumUpperBound
      certificate.resultCertificate bound

/-- Require the exact expected algorithm ID/hash in addition to every check
performed by `checkUpperBound`. -/
def checkUpperBoundForAlgorithm (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) (boundBits : Nat) : Bool :=
  certificate.executableIdentityCheck expected &&
    certificate.checkUpperBound boundBits

/-- Aggregate counterpart of `checkUpperBoundForAlgorithm`. -/
def checkSumUpperBoundForAlgorithm (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) (bound : ℚ) : Bool :=
  certificate.executableIdentityCheck expected &&
    certificate.checkSumUpperBound bound

/-- Everything established for an accepted, checked row-wise upper-bound
certificate. `produced` crosses the one run-certificate trust axiom and
`execution` is its historical compatibility projection; `binding` and
`mathematics` are proved by ordinary Lean definitions and the existing
certificate soundness theorem. -/
structure CertifiedUpperBound (certificate : SignedResultCertificate)
    (boundBits : Nat) : Prop where
  produced : certificate.toRunCertificate.ProducedOutcome
  execution : AlgorithmReturned certificate.statement
    certificate.statement.result
  binding : certificate.ResultBound
  mathematics : SerializedUpperBoundTheorem
    certificate.statement.result boundBits

/-- Aggregate counterpart of `CertifiedUpperBound`. -/
structure CertifiedSumUpperBound (certificate : SignedResultCertificate)
    (bound : ℚ) : Prop where
  produced : certificate.toRunCertificate.ProducedOutcome
  execution : AlgorithmReturned certificate.statement
    certificate.statement.result
  binding : certificate.ResultBound
  mathematics : SerializedSumUpperBoundTheorem
    certificate.statement.result bound

/-- The strongest row-wise handoff: exact executable identity, trusted
execution provenance, exact result binding, and independently checked
mathematics. -/
structure CertifiedUpperBoundForAlgorithm
    (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) (boundBits : Nat) : Prop where
  identity : certificate.ExecutableIdentityBound expected
  checked : certificate.CertifiedUpperBound boundBits

/-- Finite-sum counterpart of `CertifiedUpperBoundForAlgorithm`. -/
structure CertifiedSumUpperBoundForAlgorithm
    (certificate : SignedResultCertificate)
    (expected : ExpectedExecutableIdentity) (bound : ℚ) : Prop where
  identity : certificate.ExecutableIdentityBound expected
  checked : certificate.CertifiedSumUpperBound bound

/-- The executable identity check proves both literal pins. -/
theorem executableIdentityCheck_sound
    {certificate : SignedResultCertificate}
    {expected : ExpectedExecutableIdentity}
    (hcheck : certificate.executableIdentityCheck expected = true) :
    certificate.ExecutableIdentityBound expected := by
  simpa [executableIdentityCheck, ExecutableIdentityBound] using hcheck

/-- The executable binding check proves both exact equalities used later. -/
theorem resultBindingCheck_sound {certificate : SignedResultCertificate}
    (hcheck : certificate.resultBindingCheck = true) :
    certificate.ResultBound := by
  simpa [resultBindingCheck, ResultBound] using hcheck

end SignedResultCertificate

end SparkInterval.Execution
