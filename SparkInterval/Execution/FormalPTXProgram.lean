import SparkInterval.Certificate.SHA256
import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.PTX.Generator

/-!
# Binding an execution statement to the formally generated PTX program

`RunStatement.algorithmHash` is otherwise only an opaque string.  This module
defines an executable check that recomputes the SHA-256 digest of the validated
PTX emitted from the exact Lean `buildModule` and compares it with the run
statement.  Its soundness theorem exposes the emitted text and all equalities
needed by downstream proofs.

This closes the formal-AST-to-emitted-PTX identity edge.  It deliberately does
not claim that `ptxas`, a cubin, SASS, the CUDA driver, or a physical GPU refines
the typed PTX machine.  `FormalPTXProgram` is caller-configurable and is not a
closed registered invocation, so its historical outcome does not acquire that
formal execution relation automatically.  A future closed registration may
place the per-run backend connection inside the single run-certificate trust
boundary; no universal refinement theorem follows.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- A caller-selected generated program and exact run inputs.

`algorithmId` is the stable protocol name and the algorithm digest is derived
from emitted PTX.  The exact canonical input text is parsed and required to
equal `batch`; hashing that text binds all rows and `rowCount`, even though the
row-generic PTX module itself does not embed them.  Parameter/domain text and
deployment artifact identities are caller-selected but checked literally. -/
structure FormalPTXProgram where
  algorithmId : String
  target : ExecutionTarget
  canonicalInput : String
  canonicalParameters : String
  canonicalDomain : String
  targetProfileHash : Digest
  artifacts : ArtifactHashes
  batch : SparkInterval.PTX.ReferenceBatch

namespace FormalPTXProgram

/-- GPU emitter selected by an execution target.  CPU-only confidential runs
have no PTX target and are rejected rather than being silently mapped to one. -/
def emitterTarget? : ExecutionTarget → Option SparkInterval.PTX.EmitterTarget
  | .dgxSparkSM121 => some .sm121
  | .nvidiaH100SM90 => some .sm90
  | .azureSEVSNPCPU => none

/-- Emit the exact typed module through the validated production emitter. -/
def emit (program : FormalPTXProgram) : Except String String :=
  match emitterTarget? program.target with
  | some target =>
      SparkInterval.PTX.emitFor target
        (SparkInterval.PTX.buildModule program.batch)
  | none => .error "formal PTX emission requires a GPU execution target"

/-- Check that the run statement names this exact validated emitted PTX text
and the complete caller-selected input/deployment identity.

Both reviewed deployment directives use the same typed instruction module;
the selected formal program fixes either `sm_121` or `sm_90`. -/
def statementCheck (program : FormalPTXProgram)
    (statement : RunStatement) : Bool :=
  match program.emit,
      SparkInterval.PTX.parseCanonicalReferenceBatch program.canonicalInput with
  | .ok ptx, .ok parsedBatch =>
      decide (
        parsedBatch = program.batch ∧
        statement.algorithmId = program.algorithmId ∧
        statement.algorithmHash = SHA256.digestString ptx ∧
        statement.inputHash = SHA256.digestString program.canonicalInput ∧
        statement.parametersHash =
          SHA256.digestString program.canonicalParameters ∧
        statement.domainHash = SHA256.digestString program.canonicalDomain ∧
        statement.target = program.target ∧
        statement.targetProfileHash = program.targetProfileHash ∧
        statement.artifacts = program.artifacts)
  | _, _ => false

/-- Propositional result of `statementCheck`: the statement's algorithm digest
is recomputed from a successful validated emission of the exact formal module. -/
def StatementBound (program : FormalPTXProgram)
    (statement : RunStatement) : Prop :=
  ∃ ptx : String,
    program.emit = .ok ptx ∧
    SparkInterval.PTX.parseCanonicalReferenceBatch program.canonicalInput =
      .ok program.batch ∧
    statement.algorithmId = program.algorithmId ∧
    statement.algorithmHash = SHA256.digestString ptx ∧
    statement.inputHash = SHA256.digestString program.canonicalInput ∧
    statement.parametersHash = SHA256.digestString program.canonicalParameters ∧
    statement.domainHash = SHA256.digestString program.canonicalDomain ∧
    statement.target = program.target ∧
    statement.targetProfileHash = program.targetProfileHash ∧
    statement.artifacts = program.artifacts

theorem statementCheck_sound {program : FormalPTXProgram}
    {statement : RunStatement}
    (hcheck : program.statementCheck statement = true) :
    program.StatementBound statement := by
  unfold statementCheck at hcheck
  cases hemit : program.emit with
  | error message => simp [hemit] at hcheck
  | ok ptx =>
      cases hparse : SparkInterval.PTX.parseCanonicalReferenceBatch
          program.canonicalInput with
      | error message => simp [hemit, hparse] at hcheck
      | ok parsedBatch =>
          simp only [hemit, hparse, decide_eq_true_eq] at hcheck
          have hinput :
              SparkInterval.PTX.parseCanonicalReferenceBatch
                  program.canonicalInput = .ok program.batch := by
            simpa [hcheck.1] using hparse
          exact ⟨ptx, hemit, hinput, hcheck.2⟩

/-- The checker fails closed when the canonical input parses to a batch other
than the one used to generate the formal module.  This includes metadata such
as `rowCount` that need not occur in row-generic PTX text. -/
theorem statementCheck_eq_false_of_parsedBatch_ne
    {program : FormalPTXProgram} {statement : RunStatement}
    {parsedBatch : SparkInterval.PTX.ReferenceBatch}
    (hparse : SparkInterval.PTX.parseCanonicalReferenceBatch
      program.canonicalInput = .ok parsedBatch)
    (hne : parsedBatch ≠ program.batch) :
    program.statementCheck statement = false := by
  unfold statementCheck
  rw [hparse]
  cases hemit : program.emit <;> simp [hne]

/-- A statement carrying any input digest other than the recomputed digest of
the exact canonical input fails closed, independently of emission/parsing. -/
theorem statementCheck_eq_false_of_inputHash_ne
    {program : FormalPTXProgram} {statement : RunStatement}
    (hne : statement.inputHash ≠ SHA256.digestString program.canonicalInput) :
    program.statementCheck statement = false := by
  unfold statementCheck
  cases hemit : program.emit <;>
    cases hparse : SparkInterval.PTX.parseCanonicalReferenceBatch
      program.canonicalInput <;>
    simp [hne]

/-- Successful formal-program binding also identifies the emitted bytes with
the deterministic rendering of the exact typed module. -/
theorem emitted_eq_renderUnchecked {program : FormalPTXProgram}
    {ptx : String}
    (emission : program.emit = .ok ptx) :
    ∃ target : SparkInterval.PTX.EmitterTarget,
      emitterTarget? program.target = some target ∧
      ptx = SparkInterval.PTX.renderUncheckedFor target
        (SparkInterval.PTX.buildModule program.batch) := by
  unfold emit at emission
  cases htarget : emitterTarget? program.target with
  | none =>
      simp [htarget] at emission
  | some target =>
      have hemit : SparkInterval.PTX.emitFor target
          (SparkInterval.PTX.buildModule program.batch) = .ok ptx := by
        simpa [htarget] using emission
      exact ⟨target, rfl, (SparkInterval.PTX.emitFor_success hemit).2⟩

end FormalPTXProgram

namespace SignedResultCertificate

/-- Require exact formal generated-PTX identity in addition to the accepted
historical run and exact returned-result binding. -/
def outcomeCheckForFormalPTX (certificate : SignedResultCertificate)
    (program : FormalPTXProgram) : Bool :=
  program.statementCheck certificate.statement && certificate.outcomeCheck

/-- Strong outcome handoff for the formally generated PTX identity. -/
structure CertifiedFormalPTXOutcome
    (certificate : SignedResultCertificate)
    (program : FormalPTXProgram) : Prop where
  program : program.StatementBound certificate.statement
  outcome : certificate.CertifiedOutcome

/-- The exact formal PTX identity and returned result follow using only the
single generic run-certificate axiom for the physical historical outcome. -/
theorem outcomeCheckForFormalPTX_sound
    {certificate : SignedResultCertificate}
    {program : FormalPTXProgram}
    (hcheck : certificate.outcomeCheckForFormalPTX program = true) :
    certificate.CertifiedFormalPTXOutcome program := by
  simp only [outcomeCheckForFormalPTX, Bool.and_eq_true] at hcheck
  exact {
    program := FormalPTXProgram.statementCheck_sound hcheck.1
    outcome := outcomeCheck_sound hcheck.2
  }

end SignedResultCertificate

end SparkInterval.Execution
