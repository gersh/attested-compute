/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.ArchitectureExecution

/-!
# Tiny known-answer test for the architecture-execution boundary

This is a proof-only model of a one-instruction byte-copy machine.  It is not
an x86 or GPU model and carries no production authority.  Its purpose is to
exercise the exact separation:

`receipt -> architecture execution -> native checker acceptance`.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.ArchitectureExecutionBoundary

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

private def bytes (values : List UInt8) : ByteArray :=
  values.toByteArray

private def toyCode : ByteArray :=
  bytes [0x43, 0x4f, 0x50, 0x59]

private def toyInput : ByteArray :=
  bytes [0x00, 0x80, 0xff, 0x2a]

/-- The KAT uses a deliberately trivial digest function.  Production
instantiations must instead select the verified SHA-256 measurement scheme.
Raw bytes remain present in the execution relation even in this toy model. -/
private def toyMeasurement : MeasurementScheme := {
  schemeId := "toy-measurement-v1"
  digestBytes := fun _ => "toy-digest"
}

private def measured (value : ByteArray) : MeasuredBlob := {
  bytes := value
  byteLength := value.size
  digest := "toy-digest"
}

private theorem measured_exact (value : ByteArray) :
    (measured value).Exact toyMeasurement := by
  exact ⟨rfl, rfl⟩

private inductive ToyState where
  | ready (payload : ByteArray)
  | done (payload : ByteArray)

private inductive ToyStep : ToyState → ToyState → Prop where
  | copy (payload : ByteArray) :
      ToyStep (.ready payload) (.done payload)

private inductive ToyLoad :
    String → ByteArray → ByteArray → ToyState → Prop where
  | copy (input : ByteArray) :
      ToyLoad "copy" toyCode input (.ready input)

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
  measurementSchemeId := toyMeasurement.schemeId
  semanticsId := toyMachine.semanticsId
  target := toyMachine.target
  entryPoint := "copy"
  executable := measured toyCode
  input := measured toyInput
  output := measured toyInput
}

private theorem toy_execution :
    ArchitectureExecution toyMeasurement toyMachine toyRun := by
  refine ⟨{
    schemeId := rfl
    executable := measured_exact toyCode
    input := measured_exact toyInput
    output := measured_exact toyInput
  }, rfl, rfl, .ready toyInput, .done toyInput, ?_⟩
  exact ⟨ToyLoad.copy toyInput, Trace.single (ToyStep.copy toyInput),
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

/-- The toy native image refines the byte-copy checker.  This proof analyzes
the machine loader, trace, and halt relation; it does not inspect a receipt. -/
private theorem toy_refines_copy :
    ArchitectureRefinesNativeChecker
      toyMeasurement toyMachine copyChecker (measured toyCode) "copy" := by
  refine {
    executableExact := measured_exact toyCode
    refines := ?_
  }
  intro run executableBound entryPointBound execution
  rcases execution with
    ⟨_measurements, _semantics, _target, initial, final,
      loaded, trace, halted⟩
  have loadedBound :
      ToyLoad "copy" toyCode run.input.bytes initial := by
    simpa [toyMachine, entryPointBound, executableBound, measured] using loaded
  cases loadedBound
  cases halted
  exact Trace.observation_eq
    ToyState.payload ToyStep.payload_eq trace

/-- A receipt token carries only the already proved architecture execution. -/
private theorem toy_receipt :
    ReceiptExecutionFact "toy-receipt-hash"
      toyMeasurement toyMachine toyRun :=
  ⟨toy_execution⟩

/-- End-to-end KAT: the receipt yields the architecture execution, while the
separate refinement theorem yields native checker acceptance. -/
example :
    copyChecker.accepts toyRun.input.bytes toyRun.output.bytes :=
  toy_refines_copy.accepts_of_receipt rfl rfl toy_receipt

#print axioms toy_execution
#print axioms toy_refines_copy
#print axioms ArchitectureRefinesNativeChecker.accepts_of_receipt

end SparkInterval.Tests.ArchitectureExecutionBoundary
