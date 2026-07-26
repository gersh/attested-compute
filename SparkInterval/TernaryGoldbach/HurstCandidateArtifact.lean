/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.Execution.CanonicalInstalledArtifactProgram
import SparkInterval.Execution.FixedWidthCertificateWire
import SparkInterval.Execution.ParsedCertificateProgram
import SparkInterval.TernaryGoldbach.HurstCompactChecker

/-!
# Fail-closed shared Hurst candidate artifact

This module fixes a canonical data format for the arithmetic block chain of
the shared Hurst campaign.  It binds the exact V2 invocation, the literal
`[1, 10^16 + 1)` source geometry, the zero root, every affine block, and the
Azure SEV-SNP terminal CPU.

The header selects that invocation as data; it does not authenticate an Azure
run.  Receipt verification remains a separate architecture boundary.

The existing arithmetic certificate does not, by itself, prove what a block
delta means.  Its source theorem additionally needs
`ReplayBlockRealization SourceRowDelta SourceRowSafe` for every block:
primitive Möbius/Q96 row deltas, local prefix recurrence, and every integer
guard decision.  Those witnesses are currently proof-valued and there is no
data-only segmented-sieve certificate plus ordinary Lean replay theorem.

Accordingly this module defines no successful artifact checker and no
`DeterministicFinalizerIR.Certificate`.  `runCandidate` parses and checks the
complete representable block transcript, then rejects an otherwise valid
candidate with a dedicated missing-realization code.  This makes the current
boundary deployable as an Azure format smoke test without pretending that
the analytic atoms have been discharged.

No axiom, `native_decide`, receipt, proposition-valued runtime input, or
source-scale computation occurs here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstCandidateArtifact

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.Execution.Architecture.FixedWidthCertificateWire
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder

namespace Replay

abbrev State :=
  HurstAffineCertificate.State

abbrev Guard :=
  HurstAffineCertificate.Guard

abbrev Block :=
  HurstAffineCertificate.Block

abbrev Certificate :=
  HurstAffineCertificate.Certificate

end Replay

/-! ## Exact measured-job identity -/

def invocation : RegisteredArchitectureInvocation :=
  .hurstSharedFourResidualProductionV2

def artifactHeaderText : String :=
  "TG-HURST-SHARED-CANDIDATE-V1\n" ++
  "invocation=" ++ invocation.invocationId ++ "\n" ++
  "terminal=azure-sev-snp-cpu\n" ++
  "job=" ++ HurstCompactChecker.canonicalInputText ++ "\n"

def artifactHeaderBytes : ByteArray :=
  artifactHeaderText.toUTF8

@[simp] theorem invocation_id :
    invocation.invocationId =
      "hurst-shared-four-residual-production-v2" := by
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

def stateByteSize : Nat :=
  4 * integerWidth

def guardByteSize : Nat :=
  2 * stateByteSize

def blockByteSize : Nat :=
  naturalWidth + naturalWidth + stateByteSize + guardByteSize

def certificateFixedByteSize : Nat :=
  naturalWidth + naturalWidth + stateByteSize + stateByteSize + 4

def maximumBlockCount : Nat :=
  1_000_000

def readState (bytes : ByteArray) (offset : Nat) :
    Option Replay.State := do
  let mertens ← readInt bytes offset
  let squarefree ← readInt bytes (offset + integerWidth)
  let littleLowerQ96 ← readInt bytes (offset + 2 * integerWidth)
  let littleUpperQ96 ← readInt bytes (offset + 3 * integerWidth)
  pure { mertens, squarefree, littleLowerQ96, littleUpperQ96 }

def readGuard (bytes : ByteArray) (offset : Nat) :
    Option Replay.Guard := do
  let lower ← readState bytes offset
  let upper ← readState bytes (offset + stateByteSize)
  pure { lower, upper }

def readBlock (bytes : ByteArray) (offset : Nat) :
    Option Replay.Block := do
  let lower ← readNat bytes offset
  let upper ← readNat bytes (offset + naturalWidth)
  let delta ←
    readState bytes (offset + naturalWidth + naturalWidth)
  let guard ←
    readGuard bytes
      (offset + naturalWidth + naturalWidth + stateByteSize)
  pure { lower, upper, delta, guard }

def decode (bytes : ByteArray) : Option Replay.Certificate := do
  let offset ← readFixedPrefix bytes artifactHeaderBytes
  let sourceLower ← readNat bytes offset
  let sourceUpper ← readNat bytes (offset + naturalWidth)
  let rootState ←
    readState bytes (offset + naturalWidth + naturalWidth)
  let finalState ←
    readState bytes
      (offset + naturalWidth + naturalWidth + stateByteSize)
  let blockCount ←
    readNatLE? bytes
      (offset + naturalWidth + naturalWidth +
        stateByteSize + stateByteSize) 4
  if blockCount > maximumBlockCount then none
  if !countFrameValid bytes offset certificateFixedByteSize
      blockByteSize blockCount then
    none
  let blocks ←
    readRows readBlock blockByteSize bytes
      (offset + certificateFixedByteSize) blockCount
  pure { sourceLower, sourceUpper, rootState, finalState, blocks }

/-! ## Canonical producer-side encoder -/

def encodeState? (state : Replay.State) : Option (List UInt8) := do
  let mertens ← encodeInt? state.mertens
  let squarefree ← encodeInt? state.squarefree
  let littleLowerQ96 ← encodeInt? state.littleLowerQ96
  let littleUpperQ96 ← encodeInt? state.littleUpperQ96
  pure
    (mertens ++ squarefree ++ littleLowerQ96 ++ littleUpperQ96)

def encodeGuard? (guard : Replay.Guard) : Option (List UInt8) := do
  let lower ← encodeState? guard.lower
  let upper ← encodeState? guard.upper
  pure (lower ++ upper)

def encodeBlock? (block : Replay.Block) : Option (List UInt8) := do
  let lower ← encodeNat? block.lower
  let upper ← encodeNat? block.upper
  let delta ← encodeState? block.delta
  let guard ← encodeGuard? block.guard
  pure (lower ++ upper ++ delta ++ guard)

private def encodeBlocks? : List Replay.Block → Option (List UInt8)
  | [] => some []
  | block :: rest => do
      let encodedBlock ← encodeBlock? block
      let encodedRest ← encodeBlocks? rest
      pure (encodedBlock ++ encodedRest)

def encode? (certificate : Replay.Certificate) : Option ByteArray := do
  if certificate.blocks.length > maximumBlockCount then none
  let sourceLower ← encodeNat? certificate.sourceLower
  let sourceUpper ← encodeNat? certificate.sourceUpper
  let rootState ← encodeState? certificate.rootState
  let finalState ← encodeState? certificate.finalState
  let blockCount ← encodeNatWidth? 4 certificate.blocks.length
  let blocks ← encodeBlocks? certificate.blocks
  pure ((artifactHeaderBytes.toList ++
    sourceLower ++ sourceUpper ++ rootState ++ finalState ++
    blockCount ++ blocks).toByteArray)

/-- Everything the current data-only format can honestly decide. -/
def arithmeticCheck (certificate : Replay.Certificate) : Bool :=
  certificate.check &&
    (decide
      (certificate.sourceLower = 1 ∧
        certificate.sourceUpper =
          HurstAffineCertificate.sourceUpperExclusive) &&
      decide (certificate.rootState = HurstAffineCertificate.State.zero))

theorem arithmeticCheck_sound
    {certificate : Replay.Certificate}
    (checked : arithmeticCheck certificate = true) :
    certificate.ArithmeticValid ∧
      certificate.FullSourceRange ∧
      certificate.rootState = HurstAffineCertificate.State.zero := by
  simp only [arithmeticCheck, Bool.and_eq_true, decide_eq_true_eq] at checked
  exact
    ⟨HurstAffineCertificate.Certificate.checker_sound checked.1,
      checked.2.1, checked.2.2⟩

/-! ## Explicit fail-closed source-program state -/

def missingRealizationCode : Nat :=
  10_016

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
exists yet, and a vacuous refinement certificate would hide the missing
segmented-sieve/Q96 theorem rather than discharge it. -/
def candidateProgram : Program where
  contractId :=
    "sparkinterval.ternary-goldbach.hurst-shared-four-residual." ++
      "candidate-artifact.v1"
  run := runCandidate

/-- No source-reviewed segmented-sieve/Q96 artifact is installed yet. -/
def installedArtifact : Option ByteArray :=
  none

/-- Legacy-descriptor program certificate for the pre-run state.

This certificate proves only that an absent source-installed artifact cannot
return success.  It must remain catalogued as missing; replacing `none`
requires the nonvacuous row-realization theorem recorded below. -/
def failClosedCertificate :
    Certificate HurstCompactChecker.nativeChecker :=
  CanonicalInstalledArtifactProgram.certificate
    HurstCompactChecker.nativeChecker
    HurstCompactChecker.canonicalInputBytes
    HurstCompactChecker.canonicalResultBytes
    installedArtifact decode arithmeticCheck
    (CanonicalInstalledArtifactProgram.none_sound
      HurstCompactChecker.nativeChecker
      HurstCompactChecker.canonicalInputBytes
      HurstCompactChecker.canonicalResultBytes
      decode arithmeticCheck)

@[simp] theorem failClosed_rejects_canonical :
    failClosedCertificate.program.run
      HurstCompactChecker.canonicalInputBytes =
        .rejected CanonicalInstalledArtifactProgram.artifactAbsentCode := by
  simp [failClosedCertificate,
    CanonicalInstalledArtifactProgram.certificate,
    CanonicalInstalledArtifactProgram.program, installedArtifact]

structure MissingRealizationObligations where
  dataCertificate : String
  booleanReplay : String
  rowSoundness : String
  blockCoverage : String
  deriving Repr, DecidableEq

def missing : MissingRealizationObligations where
  dataCertificate :=
    "Data-only segmented-sieve rows carrying exact Mobius increments, \
squarefree increments, directed Q96 little-Mertens increments, local prefix \
states, and every retained integer guard decision."
  booleanReplay :=
    "A total Boolean which reconstructs each block delta from its rows, \
checks prefix stepping and active-range Q96 freezing, and checks \
HurstSourceSemantics.SourceRowSafe at every row."
  rowSoundness :=
    "Ordinary Lean theorems from accepted primitive row data to \
HurstSourceSemantics.SourceRowDelta and SourceRowSafe, without accepting a \
proposition or proof object at runtime."
  blockCoverage :=
    "An exact parser/checker proof that rows partition every checked block \
and blocks cover [1, 10^16 + 1) from State.zero with no omitted, duplicated, \
or caller-selected source index."

end SparkInterval.TernaryGoldbach.HurstCandidateArtifact
