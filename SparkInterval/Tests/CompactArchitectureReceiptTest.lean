/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureReceipt

/-!
# Tiny proof-only test for compact opaque execution receipts

All byte strings in this test have at most four bytes.  This is a logical
known-answer model only: it performs no native compilation, production
certificate hashing, or architecture replay.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CompactArchitectureReceipt

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

private def bytes (values : List UInt8) : ByteArray :=
  values.toByteArray

private def toyCode : ByteArray :=
  bytes [0x43, 0x4f, 0x50, 0x59]

private def toyInput : ByteArray :=
  bytes [0x00, 0x80, 0xff, 0x2a]

private def toyDigest (value : ByteArray) : Digest :=
  "toy-" ++ toString value.size

private def toyScheme : MeasurementScheme := {
  schemeId := "toy-size-digest-v1"
  digestBytes := toyDigest
}

private def measured (value : ByteArray) : MeasuredBlob := {
  bytes := value
  byteLength := value.size
  digest := toyDigest value
}

private theorem measured_exact (value : ByteArray) :
    (measured value).Exact toyScheme :=
  ⟨rfl, rfl⟩

private inductive ToyState where
  | ready (payload : ByteArray)
  | done (payload : ByteArray)

private inductive ToyStep : ToyState → ToyState → Prop where
  | copy (payload : ByteArray) :
      ToyStep (.ready payload) (.done payload)

private def ToyLoad
    (entry : String)
    (code input : ByteArray)
    (state : ToyState) : Prop :=
  entry = "copy" ∧ code = toyCode ∧ state = .ready input

private inductive ToyHalted : ToyState → ByteArray → Prop where
  | done (output : ByteArray) :
      ToyHalted (.done output) output

private def toyMachine : ArchitectureSemantics := {
  semanticsId := "toy-copy-semantics-v1"
  target := .azureSEVSNPCPU
  State := ToyState
  load := ToyLoad
  step := ToyStep
  haltedWith := ToyHalted
}

private def toyRun : MeasuredRun := {
  measurementSchemeId := toyScheme.schemeId
  semanticsId := toyMachine.semanticsId
  target := toyMachine.target
  entryPoint := "copy"
  executable := measured toyCode
  input := measured toyInput
  output := measured toyInput
}

private def toyPins : CompactRunPins := {
  measurementSchemeId := toyScheme.schemeId
  semanticsId := toyMachine.semanticsId
  target := toyMachine.target
  entryPoint := "copy"
  executable := {
    byteLength := toyCode.size
    digest := toyDigest toyCode
  }
  input := {
    byteLength := toyInput.size
    digest := toyDigest toyInput
  }
  result := {
    byteLength := toyInput.size
    digest := toyDigest toyInput
  }
}

private theorem toy_pin_bound :
    toyRun.MatchesCompactPins toyPins := by
  exact {
    measurementScheme := rfl
    semantics := rfl
    target := rfl
    entryPoint := rfl
    executableLength := rfl
    executableDigest := rfl
    inputLength := rfl
    inputDigest := rfl
    resultLength := rfl
    resultDigest := rfl
  }

private theorem toy_execution :
    ArchitectureExecution toyScheme toyMachine toyRun := by
  refine ⟨{
    schemeId := rfl
    executable := measured_exact toyCode
    input := measured_exact toyInput
    output := measured_exact toyInput
  }, rfl, rfl, .ready toyInput, .done toyInput, ?_⟩
  exact ⟨⟨rfl, rfl, rfl⟩, Trace.single (ToyStep.copy toyInput),
    ToyHalted.done toyInput⟩

private def ToyState.payload : ToyState → ByteArray
  | .ready payload | .done payload => payload

private theorem ToyStep.payload_eq
    {before after : ToyState} (step : ToyStep before after) :
    before.payload = after.payload := by
  cases step
  rfl

private def copyChecker : NativeCheckerSemantics := {
  checkerId := "toy-copy-checker-v1"
  accepts := fun input output => input = output
}

/-- Universal symbolic refinement: the proof does not depend on the concrete
toy input and handles every run matching the compact pins. -/
private theorem toy_refinement :
    CompactArchitectureRefinement
      toyScheme toyMachine copyChecker toyPins := by
  intro run pinBound executed
  rcases executed with
    ⟨_measurements, _semantics, _target, initial, final,
      loaded, trace, halted⟩
  have entryBound : run.entryPoint = "copy" := by
    simpa [toyPins] using pinBound.entryPoint
  rcases loaded with ⟨_loadedEntry, _loadedCode, initialBound⟩
  subst initial
  cases halted
  exact Trace.observation_eq
    ToyState.payload ToyStep.payload_eq trace

/-- The same machine also has the ordinary exact-executable refinement used
by the preferred static-artifact receipt shape. -/
private theorem toy_exact_refinement :
    ArchitectureRefinesNativeChecker
      toyScheme toyMachine copyChecker (measured toyCode) "copy" := by
  refine {
    executableExact := measured_exact toyCode
    refines := ?_
  }
  intro run executableBound entryBound executed
  rcases executed with
    ⟨_measurements, _semantics, _target, initial, final,
      loaded, trace, halted⟩
  have loadedAtReviewedImage :
      ToyLoad "copy" toyCode run.input.bytes initial := by
    simpa [toyMachine, entryBound, executableBound, measured] using loaded
  rcases loadedAtReviewedImage with
    ⟨_loadedEntry, _loadedCode, initialBound⟩
  subst initial
  cases halted
  exact Trace.observation_eq
    ToyState.payload ToyStep.payload_eq trace

private theorem toy_receipt :
    CompactReceiptExecutionFact
      "toy-receipt-hash" toyScheme toyMachine toyPins :=
  ⟨toyRun, toy_pin_bound, toy_execution⟩

/-- The small reviewed executable and result are retained exactly; only the
input bytes are hidden by the receipt fact. -/
private theorem toy_static_artifacts :
    StaticArtifactsPinned
      toyScheme toyPins (measured toyCode) (measured toyInput) := by
  exact {
    executableExact := measured_exact toyCode
    executableLength := rfl
    executableDigest := rfl
    resultExact := measured_exact toyInput
    resultLength := rfl
    resultDigest := rfl
  }

private theorem toy_compact_input_receipt :
    CompactInputReceiptExecutionFact
      "toy-receipt-hash" toyScheme toyMachine toyPins
      (measured toyCode) (measured toyInput) := by
  exact ⟨toy_static_artifacts, toyInput, toy_execution⟩

/-- Fully symbolic use: executable, input, and output bytes occur only inside
the existential `MeasuredRun`; this theorem performs no digest evaluation. -/
example
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {pins : CompactRunPins}
    (receipt :
      CompactReceiptExecutionFact receiptHash scheme machine pins)
    (refinement :
      CompactArchitectureRefinement scheme machine checker pins) :
    ∃ run : MeasuredRun,
      run.MatchesCompactPins pins ∧
        ArchitectureExecution scheme machine run ∧
        checker.accepts run.input.bytes run.output.bytes :=
  opaqueNativeAcceptance_of_compactReceipt receipt refinement

/-- End-to-end composition keeps the full measured run existentially hidden.
-/
example :
    OpaqueNativeAcceptance toyScheme toyMachine copyChecker toyPins :=
  opaqueNativeAcceptance_of_compactReceipt toy_receipt toy_refinement

/-- Pin projection is a proof-only operation over the opaque witness. -/
example :
    ∃ run : MeasuredRun,
      run.MatchesCompactPins toyPins ∧
        ArchitectureExecution toyScheme toyMachine run ∧
        toyPins.executable.MatchesBytes toyScheme run.executable.bytes ∧
        toyPins.input.MatchesBytes toyScheme run.input.bytes ∧
      toyPins.result.MatchesBytes toyScheme run.output.bytes :=
  compactReceipt_hasPinnedMeasurements toy_receipt

/-- Preferred composition: the reviewed four-byte executable and result stay
static while the input is existential.  Production uses the same theorem
without replacing the existential by a local certificate literal. -/
example :
    ∃ inputBytes : ByteArray,
      ArchitectureExecution toyScheme toyMachine
          (runWithStaticArtifacts toyPins
            (measured toyCode) (measured toyInput) inputBytes) ∧
        copyChecker.accepts inputBytes (measured toyInput).bytes :=
  nativeAcceptance_of_compactInputReceipt
    toy_compact_input_receipt toy_exact_refinement

#print axioms opaqueNativeAcceptance_of_compactReceipt
#print axioms compactReceipt_hasPinnedMeasurements
#print axioms compactArchitectureRefinement_of_reviewedExecutable
#print axioms nativeAcceptance_of_compactInputReceipt
#print axioms toy_refinement

end SparkInterval.Tests.CompactArchitectureReceipt
