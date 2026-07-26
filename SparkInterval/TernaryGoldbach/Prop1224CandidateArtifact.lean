/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.Execution.CanonicalInstalledArtifactProgram
import SparkInterval.Execution.DeterministicFinalizerIR
import SparkInterval.Execution.FixedWidthCertificateWire
import SparkInterval.Execution.ParsedCertificateProgram
import SparkInterval.TernaryGoldbach.Prop1224CompactChecker

/-!
# Fail-closed Proposition 12.2.4 candidate artifact

This module fixes and parses the arithmetic part of the production artifact:
the exact Azure invocation, the literal rank interval, and the gap-free shard
stream.  The parser is useful now because it prevents the future MPFR
certificate format from silently changing the campaign geometry.

The header selects that invocation as data; it does not authenticate an Azure
run.  Receipt verification remains a separate architecture boundary.

It intentionally does **not** define a successful artifact native checker or
a `DeterministicFinalizerIR.Certificate`.  The current source semantics
requires `ExternalShardRealization.mpfrGmpRows`, a proof-valued function that
has no data-only MPFR/GMP certificate or Boolean replay theorem.  A shard
chain alone cannot imply one source row, so promoting this candidate would be
unsound.

`runCandidate` is total and parses/checks all currently representable data,
but even a valid chain receives the explicit `missingRealizationCode`.  It is
therefore safe to deploy as an Azure format smoke test while the following
ordinary Lean pieces are added:

1. a data-only row enclosure carrying factorization/totient, directed MPFR
   transcendental intervals, exact GMP `G_q`, and integer window decisions;
2. a Boolean row checker;
3. a theorem from that Boolean to `SourceRowClaim (qAtRank rank)`; and
4. exact row-to-shard coverage in the envelope below.

No axiom, `native_decide`, receipt, proposition-valued runtime input, or
source-scale computation occurs here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Prop1224CandidateArtifact

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.Execution.Architecture.FixedWidthCertificateWire
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder

namespace Source

abbrev Certificate :=
  Prop1224SourceSemantics.Certificate

abbrev Shard :=
  Prop1224SourceSemantics.Shard

end Source

/-! ## Exact measured-job identity -/

def invocation : RegisteredArchitectureInvocation :=
  .helfgottProp1224ProductionV1

def artifactHeaderText : String :=
  "TG-PROP1224-CANDIDATE-V1\n" ++
  "invocation=" ++ invocation.invocationId ++ "\n" ++
  "terminal=azure-sev-snp-cpu\n" ++
  "job=" ++ Prop1224CompactChecker.canonicalInputText ++ "\n"

def artifactHeaderBytes : ByteArray :=
  artifactHeaderText.toUTF8

@[simp] theorem invocation_id :
    invocation.invocationId =
      "helfgott-prop-12-2-4-production-v1" := by
  rfl

@[simp] theorem terminal_target :
    invocation.terminalTarget = .azureSEVSNPCPU := by
  rfl

@[simp] theorem terminal_trust :
    invocation.terminalTrust = .azureSEVSNPConfidentialCompute := by
  rfl

@[simp] theorem execution_placement :
    invocation.placement = .azureConfidentialCPU := by
  rfl

/-! ## Exact arithmetic-candidate parser -/

def shardByteSize : Nat :=
  naturalWidth + naturalWidth

def certificateFixedByteSize : Nat :=
  naturalWidth + naturalWidth + 4

def maximumShardCount : Nat :=
  1_000_000

def readShard (bytes : ByteArray) (offset : Nat) :
    Option Source.Shard := do
  let lower ← readNat bytes offset
  let upper ← readNat bytes (offset + naturalWidth)
  pure { lower, upper }

def decode (bytes : ByteArray) : Option Source.Certificate := do
  let offset ← readFixedPrefix bytes artifactHeaderBytes
  let sourceLower ← readNat bytes offset
  let sourceUpper ← readNat bytes (offset + naturalWidth)
  let shardCount ←
    readNatLE? bytes (offset + naturalWidth + naturalWidth) 4
  if shardCount > maximumShardCount then none
  if !countFrameValid bytes offset certificateFixedByteSize
      shardByteSize shardCount then
    none
  let shards ←
    readRows readShard shardByteSize bytes
      (offset + certificateFixedByteSize) shardCount
  pure { sourceLower, sourceUpper, shards }

def encodeShard? (shard : Source.Shard) : Option (List UInt8) := do
  let lower ← encodeNat? shard.lower
  let upper ← encodeNat? shard.upper
  pure (lower ++ upper)

private def encodeShards? : List Source.Shard → Option (List UInt8)
  | [] => some []
  | shard :: rest => do
      let encodedShard ← encodeShard? shard
      let encodedRest ← encodeShards? rest
      pure (encodedShard ++ encodedRest)

def encode? (certificate : Source.Certificate) : Option ByteArray := do
  if certificate.shards.length > maximumShardCount then none
  let sourceLower ← encodeNat? certificate.sourceLower
  let sourceUpper ← encodeNat? certificate.sourceUpper
  let shardCount ← encodeNatWidth? 4 certificate.shards.length
  let shards ← encodeShards? certificate.shards
  pure ((artifactHeaderBytes.toList ++
    sourceLower ++ sourceUpper ++ shardCount ++ shards).toByteArray)

/-- Everything the current data-only format can honestly decide. -/
def arithmeticCheck (certificate : Source.Certificate) : Bool :=
  certificate.check &&
    decide
      (certificate.sourceLower = 0 ∧
        certificate.sourceUpper =
          Prop1224SourceSemantics.sourceRankCount)

theorem arithmeticCheck_sound
    {certificate : Source.Certificate}
    (checked : arithmeticCheck certificate = true) :
    certificate.ArithmeticValid ∧ certificate.FullSourceRange := by
  simp only [arithmeticCheck, Bool.and_eq_true, decide_eq_true_eq] at checked
  exact
    ⟨Prop1224SourceSemantics.Certificate.checker_sound checked.1,
      checked.2⟩

/-! ## Explicit fail-closed source-program state -/

def missingRealizationCode : Nat :=
  12_224

/-- Total pre-realization program.  A well-formed arithmetic candidate is
distinguished from malformed input but is never returned as a success. -/
def runCandidate (inputBytes : ByteArray) : Outcome :=
  match decode inputBytes with
  | none => .rejected
      SparkInterval.Execution.Architecture.ParsedCertificateProgram.parseRejectedCode
  | some certificate =>
      if arithmeticCheck certificate then
        .rejected missingRealizationCode
      else
        .rejected
          SparkInterval.Execution.Architecture.ParsedCertificateProgram.checkRejectedCode

theorem runCandidate_rejects (inputBytes : ByteArray) :
    ∃ code, runCandidate inputBytes = .rejected code := by
  unfold runCandidate
  cases decode inputBytes with
  | none =>
      simp
  | some certificate =>
      by_cases checked : arithmeticCheck certificate = true <;>
        simp [checked]

/-- Reviewable deterministic pre-realization program.

It is deliberately not packaged as a `Certificate`: no successful behavior
exists yet, and a vacuous refinement certificate would obscure the missing
MPFR/GMP theorem rather than discharge it. -/
def candidateProgram : Program where
  contractId :=
    "sparkinterval.ternary-goldbach.helfgott-proposition-12-2-4." ++
      "candidate-artifact.v1"
  run := runCandidate

/-- No source-reviewed MPFR/GMP artifact is installed yet. -/
def installedArtifact : Option ByteArray :=
  none

/-- Legacy-descriptor program certificate for the pre-run state.

This certificate proves only that an absent source-installed artifact cannot
return success.  It must remain catalogued as missing; replacing `none`
requires the nonvacuous row-realization theorem recorded below. -/
def failClosedCertificate :
    Certificate Prop1224CompactChecker.nativeChecker :=
  CanonicalInstalledArtifactProgram.certificate
    Prop1224CompactChecker.nativeChecker
    Prop1224CompactChecker.canonicalInputBytes
    Prop1224CompactChecker.canonicalResultBytes
    installedArtifact decode arithmeticCheck
    (CanonicalInstalledArtifactProgram.none_sound
      Prop1224CompactChecker.nativeChecker
      Prop1224CompactChecker.canonicalInputBytes
      Prop1224CompactChecker.canonicalResultBytes
      decode arithmeticCheck)

@[simp] theorem failClosed_rejects_canonical :
    failClosedCertificate.program.run
      Prop1224CompactChecker.canonicalInputBytes =
        .rejected CanonicalInstalledArtifactProgram.artifactAbsentCode := by
  simp [failClosedCertificate,
    CanonicalInstalledArtifactProgram.certificate,
    CanonicalInstalledArtifactProgram.program, installedArtifact]

structure MissingRealizationObligations where
  dataCertificate : String
  booleanReplay : String
  rowSoundness : String
  sourceCoverage : String
  deriving Repr, DecidableEq

def missing : MissingRealizationObligations where
  dataCertificate :=
    "Data-only factorization/totient, directed MPFR log/exp/power and \
Euler-gamma/c_E enclosures, exact GMP G_q accumulation, and integer-window \
decisions for every retained source rank."
  booleanReplay :=
    "A total Boolean which checks every enclosure, exact accumulator, \
factorization link, window guard, shard/rank link, and complete payload \
framing."
  rowSoundness :=
    "An ordinary Lean theorem: accepted row data at rank r implies \
Prop1224SourceSemantics.SourceRowClaim \
(Prop1224SourceSemantics.qAtRank r)."
  sourceCoverage :=
    "An exact parser/checker proof that accepted row records cover every \
rank in every checked shard, with no omitted, duplicated, or caller-selected \
row."

end SparkInterval.TernaryGoldbach.Prop1224CandidateArtifact
