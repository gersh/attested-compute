import SparkInterval.Basic

/-!
# Statements and claims for externally executed algorithms

This module contains only data and an abstract proof token.  It does not claim
that a GPU execution happened.  The trusted H100 and DGX operator bridges are
isolated under `SparkInterval.Execution.Trusted`.

The result is represented by its canonical serialized form.  A zeta-specific
layer can parse that string into a richer Lean type and prove the parser's
relationship to the result format independently of attestation.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- A cryptographic digest in the external run-bundle format.

The core treats digests as canonical strings.  Syntax and SHA-256 validation
belong in the certificate importer; the policy below still rejects missing
digests and compares every digest literally.
-/
abbrev Digest := String

/-- Hashes of the exact host and GPU artifacts admitted by a run statement. -/
structure ArtifactHashes where
  sourceTreeHash : Digest
  hostExecutableHash : Digest
  deviceCubinHash : Digest
  kernelManifestHash : Digest
  deriving Repr, DecidableEq, BEq

/-- Hardware target named by a statement and its attested claim. -/
inductive ExecutionTarget where
  | dgxSparkSM121
  | nvidiaH100SM90
  deriving Repr, DecidableEq, BEq

/-- Trust profile named by a statement and its attested claim. -/
inductive TrustProfile where
  | localUnattested
  | mockAttested
  | nvidiaH100ConfidentialCompute
  deriving Repr, DecidableEq, BEq

/-- Completion state asserted by the external run claim. -/
inductive Completion where
  | notStarted
  | failed
  | successful
  deriving Repr, DecidableEq, BEq

/-- Everything a later Lean proof expects an external run to have executed.

`result` is the exact canonical result payload, while `outputHash` binds the
corresponding output artifact.  Keeping both prevents a certificate from being
used for a different displayed result merely because callers retained only a
digest.
-/
structure RunStatement where
  algorithmId : String
  algorithmHash : Digest
  inputHash : Digest
  parametersHash : Digest
  domainHash : Digest
  result : String
  outputHash : Digest
  nonce : String
  target : ExecutionTarget
  targetProfileHash : Digest
  trust : TrustProfile
  trustProfileHash : Digest
  artifacts : ArtifactHashes
  deriving Repr, DecidableEq, BEq

/-- The statement actually reported by an execution-evidence envelope. -/
structure RunClaim where
  algorithmId : String
  algorithmHash : Digest
  inputHash : Digest
  parametersHash : Digest
  domainHash : Digest
  result : String
  outputHash : Digest
  nonce : String
  target : ExecutionTarget
  targetProfileHash : Digest
  trust : TrustProfile
  trustProfileHash : Digest
  artifacts : ArtifactHashes
  completion : Completion
  deriving Repr, DecidableEq, BEq

/-- An abstract proposition recording the externally trusted physical fact
that the stated algorithm completed and returned `result`.

The constructor is private on purpose: ordinary Lean code cannot manufacture
this fact.  The only public producers in this repository are the
conspicuously named execution axioms under `Execution/Trusted`: one for H100
hardware attestation and one for explicitly operator-trusted DGX signatures.
-/
structure AlgorithmReturned (statement : RunStatement) (result : String) : Prop where
  private mk ::
  private physicalExecutionToken : True

end SparkInterval.Execution
