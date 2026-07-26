import SparkInterval.Execution.FormalPTXProgram

/-!
# Formal emitted-PTX program identity regression tests

These tests exercise the pure identity edge from a caller-selected formal
`ReferenceBatch`, through the validated target-specific emitter, to the digest
named by a run statement.  They do not construct production execution evidence
or add a physical-execution axiom.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.FormalPTXProgram

open SparkInterval.Certificate
open SparkInterval.Execution
open SparkInterval.PTX

private def one : IntervalBits := {
  lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
  hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
}

private def sampleBatch : ReferenceBatch := {
  variableCount := 0
  expression := .const one
  rowCount := 1
}

private def sampleModule : Module := buildModule sampleBatch

private def canonicalInput : String :=
  "{\"algorithm\":\"sparkinterval.binary64_interval_expr.v1\",\"expression\":{\"op\":\"const\",\"value\":{\"hi\":\"3ff0000000000000\",\"lo\":\"3ff0000000000000\"}},\"kind\":\"sparkinterval_reference_batch\",\"rows\":[[]],\"schema_version\":1,\"variable_count\":0}"

private def canonicalParameters : String := "{}"
private def canonicalDomain : String := "{\"kind\":\"test-domain\"}"

private def artifacts : ArtifactHashes := {
  sourceTreeHash := "source"
  hostExecutableHash := "host"
  deviceCubinHash := "cubin"
  kernelManifestHash := "manifest"
}

private def dgxProgram : FormalPTXProgram := {
  algorithmId := "sparkinterval.test.formal_ptx.v1"
  target := .dgxSparkSM121
  canonicalInput
  canonicalParameters
  canonicalDomain
  targetProfileHash := "target-profile"
  artifacts
  batch := sampleBatch
}

private def h100Program : FormalPTXProgram := {
  algorithmId := "sparkinterval.test.formal_ptx.v1"
  target := .nvidiaH100SM90
  canonicalInput
  canonicalParameters
  canonicalDomain
  targetProfileHash := "target-profile"
  artifacts
  batch := sampleBatch
}

private def cpuProgram : FormalPTXProgram := {
  h100Program with
  target := .azureSEVSNPCPU
}

/-- The representative generated module passes the validator shared by both
target-specific emission paths. -/
private theorem sampleModule_valid : validate sampleModule = .ok () := by
  decide

/-- DGX Spark selects the reviewed `sm_121` rendering. -/
private theorem dgxProgram_emits :
    dgxProgram.emit = .ok (renderUncheckedFor .sm121 sampleModule) := by
  simpa [FormalPTXProgram.emit, FormalPTXProgram.emitterTarget?, dgxProgram,
    sampleModule] using
    (emitFor_of_validate (target := EmitterTarget.sm121) sampleModule_valid)

/-- H100 selects the distinct reviewed `sm_90` rendering of the same typed
instruction module. -/
private theorem h100Program_emits :
    h100Program.emit = .ok (renderUncheckedFor .sm90 sampleModule) := by
  simpa [FormalPTXProgram.emit, FormalPTXProgram.emitterTarget?, h100Program,
    sampleModule] using
    (emitFor_of_validate (target := EmitterTarget.sm90) sampleModule_valid)

example : dgxProgram.emit = .ok (renderUncheckedFor .sm121 sampleModule) :=
  dgxProgram_emits

example : h100Program.emit = .ok (renderUncheckedFor .sm90 sampleModule) :=
  h100Program_emits

/-- A CPU trusted-compute target cannot be relabeled as a PTX execution. -/
example : cpuProgram.emit =
    .error "formal PTX emission requires a GPU execution target" := by
  rfl

/-- The architecture directive is part of the emitted bytes, rather than
metadata stored only beside the program. -/
example :
    (renderUncheckedFor .sm121 sampleModule).startsWith
      ".version 9.0\n.target sm_121\n.address_size 64\n" = true := by
  apply String.startsWith_string_iff.mpr
  simp [renderUncheckedFor, EmitterTarget.token]

example :
    (renderUncheckedFor .sm90 sampleModule).startsWith
      ".version 9.0\n.target sm_90\n.address_size 64\n" = true := by
  apply String.startsWith_string_iff.mpr
  simp [renderUncheckedFor, EmitterTarget.token]

private def statementFor (target : ExecutionTarget)
    (algorithmHash : Digest) : RunStatement := {
  algorithmId := "sparkinterval.test.formal_ptx.v1"
  algorithmHash
  inputHash := SHA256.digestString canonicalInput
  parametersHash := SHA256.digestString canonicalParameters
  domainHash := SHA256.digestString canonicalDomain
  result := "{}"
  outputHash := SHA256.digestString "{}"
  nonce := "nonce"
  target
  targetProfileHash := "target-profile"
  trust := .localUnattested
  trustProfileHash := "trust-profile"
  artifacts
}

private def dgxStatement : RunStatement :=
  statementFor .dgxSparkSM121
    (SHA256.digestString (renderUncheckedFor .sm121 sampleModule))

private def h100Statement : RunStatement :=
  statementFor .nvidiaH100SM90
    (SHA256.digestString (renderUncheckedFor .sm90 sampleModule))

private theorem dgxStatement_check
    (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    dgxProgram.statementCheck dgxStatement = true := by
  unfold FormalPTXProgram.statementCheck
  rw [dgxProgram_emits]
  simp only [dgxProgram]
  rw [hparse]
  simp [dgxStatement, statementFor]

private theorem h100Statement_check
    (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    h100Program.statementCheck h100Statement = true := by
  unfold FormalPTXProgram.statementCheck
  rw [h100Program_emits]
  simp only [h100Program]
  rw [hparse]
  simp [h100Statement, statementFor]

example (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    dgxProgram.statementCheck dgxStatement = true :=
  dgxStatement_check hparse

example (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    h100Program.statementCheck h100Statement = true :=
  h100Statement_check hparse

/-- The canonical input parser binds the full input, including its row count,
to the batch used for formal generation. -/
example (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch :=
  hparse

/-- A statement with a different input digest fails even when it names the
same emitted PTX text. -/
example (hwrong :
    "different-input" ≠ SHA256.digestString canonicalInput) :
    dgxProgram.statementCheck
      { dgxStatement with inputHash := "different-input" } = false := by
  apply FormalPTXProgram.statementCheck_eq_false_of_inputHash_ne
  simpa [dgxProgram] using hwrong

/-- Changing only the formal row count is detected by the parsed-batch check,
even though the row-generic emitted PTX module is unchanged. -/
example (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    ({ dgxProgram with batch := { sampleBatch with rowCount := 2 } } :
      FormalPTXProgram).statementCheck dgxStatement = false := by
  apply FormalPTXProgram.statementCheck_eq_false_of_parsedBatch_ne
  · simpa [dgxProgram] using hparse
  · simp [sampleBatch]

/-- Even with the exact DGX emitted-text digest, changing only the claimed
execution target fails closed. -/
example (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    dgxProgram.statementCheck
      { dgxStatement with target := .nvidiaH100SM90 } = false := by
  unfold FormalPTXProgram.statementCheck
  rw [dgxProgram_emits]
  simp only [dgxProgram]
  rw [hparse]
  simp [dgxStatement, statementFor]

/-- The successful Boolean check exposes the emitted text, recomputed digest,
algorithm identity, and target equality as ordinary propositions. -/
example (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    dgxProgram.StatementBound dgxStatement :=
  FormalPTXProgram.statementCheck_sound (dgxStatement_check hparse)

example (hparse : parseCanonicalReferenceBatch canonicalInput = .ok sampleBatch) :
    h100Program.StatementBound h100Statement :=
  FormalPTXProgram.statementCheck_sound (h100Statement_check hparse)

/-- Generic theorem-level handoff for callers that have run the pure statement
check.  This theorem has no axiom dependency. -/
theorem checkedStatement_yieldsFormalProgramIdentity
    {program : FormalPTXProgram} {statement : RunStatement}
    (hcheck : program.statementCheck statement = true) :
    program.StatementBound statement :=
  FormalPTXProgram.statementCheck_sound hcheck

/-- The corresponding outcome handoff adds no new trust assumption: it merely
composes formal program identity with the existing generic run-certificate
boundary used by `outcomeCheck_sound`. -/
theorem checkedOutcome_yieldsFormalProgramIdentity
    {certificate : SignedResultCertificate} {program : FormalPTXProgram}
    (hcheck : certificate.outcomeCheckForFormalPTX program = true) :
    certificate.CertifiedFormalPTXOutcome program :=
  SignedResultCertificate.outcomeCheckForFormalPTX_sound hcheck

#print axioms checkedStatement_yieldsFormalProgramIdentity
#print axioms checkedOutcome_yieldsFormalProgramIdentity

end SparkInterval.Tests.FormalPTXProgram
