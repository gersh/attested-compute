/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.Execution.FixedWidthCertificateWire
import SparkInterval.Execution.ParsedCertificateProgram
import SparkInterval.Execution.ProjectedCertificateProgram
import SparkInterval.TernaryGoldbach.CDEMAbelClosedReplay
import SparkInterval.TernaryGoldbach.CDEMAbelCompactChecker

/-!
# Self-contained CDEM Abel artifact finalizer

The legacy compact checker consumes a small job descriptor and leaves the
source-scale transcript existential.  This module defines a separate,
stronger artifact checker whose input is the complete recurrence transcript.
Its fixed header binds:

* `cdem-table-abel-production-v2`;
* the exact legacy `K`, `N`, and fixed-point-scale descriptor; and
* the Azure SEV-SNP terminal CPU finalizer.

After that header, every natural is a canonical 32-byte little-endian value
and every integer is a canonical sign byte plus a 32-byte magnitude.  The
payload is

```
signed target || absolute target || u32 chunk count || chunks
```

and each chunk is

```
low || high || before || after || signed upper || absolute upper.
```

The parser rejects truncation, suffixes, negative zero, unknown signs, and
overlarge row counts.  The deterministic program parses the complete runtime
input and runs `CDEMAbelClosedReplay.check`; it never calls its acceptance
relation.  Ordinary Lean proves that any accepted artifact implies the
literal source claim.

Header equality selects the registered statement; it is not evidence that
Azure executed anything.  Physical execution and attestation remain the
separate compact architecture-receipt boundary.

This is a source-program certificate only.  It does not claim that the
reviewed C++, a compiler, an ELF binary, or a physical Azure run refines the
program.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.CDEMAbelArtifactProgram

open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open SparkInterval.Execution.Architecture.FixedWidthCertificateWire
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder

namespace Recurrence

abbrev Certificate :=
  CDEMAbelRecurrenceCertificate.Certificate

abbrev Chunk :=
  CDEMAbelRecurrenceCertificate.Chunk

end Recurrence

/-! ## Exact measured-job identity -/

def invocation : RegisteredArchitectureInvocation :=
  .cdemTableAbelProductionV2

def artifactHeaderText : String :=
  "TG-CDEM-ABEL-ARTIFACT-V1\n" ++
  "invocation=" ++ invocation.invocationId ++ "\n" ++
  "terminal=azure-sev-snp-cpu\n" ++
  "job=" ++ CDEMAbelCompactChecker.canonicalInputText ++ "\n"

def artifactHeaderBytes : ByteArray :=
  artifactHeaderText.toUTF8

@[simp] theorem invocation_id :
    invocation.invocationId = "cdem-table-abel-production-v2" := by
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

/-! ## Exact binary parser -/

def chunkByteSize : Nat :=
  naturalWidth + naturalWidth +
    integerWidth + integerWidth + integerWidth + naturalWidth

def certificateFixedByteSize : Nat :=
  naturalWidth + naturalWidth + 4

/-- Defensive list cap.  The production transcript has only one thousand
rows; this looser cap avoids making topology an unproved parser assumption. -/
def maximumChunkCount : Nat :=
  100_000

def readChunk (bytes : ByteArray) (offset : Nat) :
    Option Recurrence.Chunk := do
  let low ← readNat bytes offset
  let high ← readNat bytes (offset + naturalWidth)
  let before ←
    readInt bytes (offset + naturalWidth + naturalWidth)
  let after ←
    readInt bytes
      (offset + naturalWidth + naturalWidth + integerWidth)
  let signedUpper ←
    readInt bytes
      (offset + naturalWidth + naturalWidth +
        integerWidth + integerWidth)
  let absoluteUpper ←
    readNat bytes
      (offset + naturalWidth + naturalWidth +
        integerWidth + integerWidth + integerWidth)
  pure {
    low
    high
    before
    after
    signedUpper
    absoluteUpper
  }

/-- Parse exactly one complete CDEM artifact. -/
def decode (bytes : ByteArray) : Option Recurrence.Certificate := do
  let offset ← readFixedPrefix bytes artifactHeaderBytes
  let signedNumerator ← readNat bytes offset
  let absoluteNumerator ← readNat bytes (offset + naturalWidth)
  let chunkCount ←
    readNatLE? bytes (offset + naturalWidth + naturalWidth) 4
  if chunkCount > maximumChunkCount then none
  if !countFrameValid bytes offset certificateFixedByteSize
      chunkByteSize chunkCount then
    none
  let chunks ←
    readRows readChunk chunkByteSize bytes
      (offset + certificateFixedByteSize) chunkCount
  pure { signedNumerator, absoluteNumerator, chunks }

/-! ## Canonical producer-side encoder

The encoder is not used by the soundness theorem.  It fixes the format for
the Azure materializer and makes focused round-trip tests possible.
-/

def encodeChunk? (chunk : Recurrence.Chunk) : Option (List UInt8) := do
  let low ← encodeNat? chunk.low
  let high ← encodeNat? chunk.high
  let before ← encodeInt? chunk.before
  let after ← encodeInt? chunk.after
  let signedUpper ← encodeInt? chunk.signedUpper
  let absoluteUpper ← encodeNat? chunk.absoluteUpper
  pure (low ++ high ++ before ++ after ++ signedUpper ++ absoluteUpper)

private def encodeChunks? :
    List Recurrence.Chunk → Option (List UInt8)
  | [] => some []
  | chunk :: rest => do
      let encodedChunk ← encodeChunk? chunk
      let encodedRest ← encodeChunks? rest
      pure (encodedChunk ++ encodedRest)

def encode? (certificate : Recurrence.Certificate) : Option ByteArray := do
  if certificate.chunks.length > maximumChunkCount then none
  let signedNumerator ← encodeNat? certificate.signedNumerator
  let absoluteNumerator ← encodeNat? certificate.absoluteNumerator
  let chunkCount ← encodeNatWidth? 4 certificate.chunks.length
  let chunks ← encodeChunks? certificate.chunks
  pure ((artifactHeaderBytes.toList ++
    signedNumerator ++ absoluteNumerator ++ chunkCount ++ chunks).toByteArray)

/-! ## Fixed artifact checker and deterministic source program -/

def artifactAccepts (inputBytes resultBytes : ByteArray) : Prop :=
  ∃ certificate : Recurrence.Certificate,
    decode inputBytes = some certificate ∧
      CDEMAbelClosedReplay.check certificate = true ∧
      resultBytes = CDEMAbelCompactChecker.canonicalResultBytes

/-- Strong artifact-input checker.  This is intentionally distinct from the
legacy descriptor-input checker. -/
def artifactNativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.cdem-table-abel.artifact.v1"
  accepts := artifactAccepts

theorem sourceClaim_of_artifact_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : artifactNativeChecker.accepts inputBytes resultBytes) :
    CDEMAbelSource.SourceClaim := by
  rcases accepted with ⟨certificate, _decoded, checked, _result⟩
  exact CDEMAbelClosedReplay.sourceClaim_of_check checked

/-- Compatibility with the existing descriptor-input checker.

This direction forgets the concrete artifact bytes only after their parse and
closed replay have succeeded.  It is an ordinary theorem, not a receipt or a
runtime call to the legacy acceptance relation. -/
theorem legacy_accepts_of_artifact_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : artifactNativeChecker.accepts inputBytes resultBytes) :
    CDEMAbelCompactChecker.nativeChecker.accepts
      CDEMAbelCompactChecker.canonicalInputBytes
      CDEMAbelCompactChecker.canonicalResultBytes := by
  rcases accepted with ⟨certificate, _decoded, checked, _result⟩
  exact ⟨rfl, rfl, CDEMAbelClosedReplay.supervisor_accepts_of_check checked⟩

theorem parseCheckSound :
    ParsedCertificateProgram.ParseCheckSound
      artifactNativeChecker decode CDEMAbelClosedReplay.check
        CDEMAbelCompactChecker.canonicalResultBytes := by
  intro inputBytes certificate decoded checked
  exact ⟨certificate, decoded, checked, rfl⟩

/-- Closed total source-program certificate for complete artifact bytes. -/
def sourceProgramCertificate :
    DeterministicFinalizerIR.Certificate artifactNativeChecker :=
  ParsedCertificateProgram.certificate
    artifactNativeChecker decode CDEMAbelClosedReplay.check
      CDEMAbelCompactChecker.canonicalResultBytes parseCheckSound

/-- Complete artifact program together with its ordinary projection to the
fixed descriptor-era checker used by the application capstone.

An architecture certificate for this value must target
`artifactNativeChecker` and therefore take the complete artifact as its
measured input.  The descriptor acceptance is derived only afterward. -/
def projectedSourceProgramCertificate :
    SparkInterval.Execution.Architecture.ProjectedCertificateProgram.Certificate
      artifactNativeChecker CDEMAbelCompactChecker.nativeChecker where
  sourceProgram := sourceProgramCertificate
  downstreamInput := CDEMAbelCompactChecker.canonicalInputBytes
  downstreamResult := CDEMAbelCompactChecker.canonicalResultBytes
  project := legacy_accepts_of_artifact_acceptance

/-- Once the architecture boundary has established acceptance of the exact
complete-artifact checker, ordinary Lean derives the mathematical source
claim without exposing or locally replaying the source-scale artifact.

This theorem is deliberately only the final composition step.  It does not
construct `OpaqueNativeAcceptance`, prove an executable/ISA/compiler
refinement, or admit a receipt. -/
theorem sourceClaim_of_opaqueNativeAcceptance
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    (accepted :
      OpaqueNativeAcceptance scheme machine artifactNativeChecker pins) :
    CDEMAbelSource.SourceClaim := by
  rcases accepted with ⟨_run, _pinBound, _execution, sourceAccepted⟩
  exact sourceClaim_of_artifact_acceptance sourceAccepted

end SparkInterval.TernaryGoldbach.CDEMAbelArtifactProgram
