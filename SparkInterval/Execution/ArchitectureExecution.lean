/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.Statement

/-!
# Exact architecture-execution boundary

This module is the small, application-neutral boundary between a measured
physical run and a native checker specification.  It keeps three propositions
separate:

1. `ArchitectureExecution scheme machine run` is an execution in an exact
   formal CPU or GPU architecture semantics.  It consumes the complete
   executable and input bytes and produces the complete output bytes.
2. `ArchitectureRefinesNativeChecker` is an ordinary Lean refinement theorem
   for one exact executable image and entry point.
3. `ReceiptExecutionFact receiptHash ...` carries only the first proposition
   for one run.  It has no application-level `Runs`, checker-acceptance, or
   mathematical-claim field.

A future trusted receipt importer may supply a
`ReceiptExecutionFact` for an Azure run.  That trust step must bind the receipt
to the exact `MeasuredRun`; it cannot replace either the formal architecture
semantics or the executable-to-checker refinement proof.

In particular, the trusted entry point must select a closed, reviewed
`MeasurementScheme` and `ArchitectureSemantics`.  An axiom quantified over a
caller-selected machine would be unsound: a caller could choose a semantics
whose step relation accepts everything.  No such entry point is defined here.

The generic `ArchitectureSemantics` is intentionally suitable for either an
x86-64 CPU model or an NVIDIA GPU model.  Its loader relation is responsible
for parsing the exact ELF/cubin image, selecting the named entry point, and
constructing the initial architectural state.  Its step relation must be the
selected ISA semantics, not an application-level shortcut.

This module adds no axiom and does not use `AlgorithmReturned` or
`RegisteredInvocation.Runs`.
-/

set_option autoImplicit false

universe u

namespace SparkInterval.Execution.Architecture

/-- A digest algorithm used to identify exact byte strings.

Production instances should use the repository's verified SHA-256 function
and a reviewed, nonempty `schemeId`.  Keeping the function explicit prevents
the core execution relation from silently treating an opaque digest string as
the executable itself. -/
structure MeasurementScheme where
  schemeId : Digest
  digestBytes : ByteArray → Digest

/-- Complete bytes plus the length and digest committed to by a run receipt. -/
structure MeasuredBlob where
  bytes : ByteArray
  byteLength : Nat
  digest : Digest

namespace MeasuredBlob

/-- The advertised size and digest are exactly those of the retained bytes. -/
def Exact (scheme : MeasurementScheme) (blob : MeasuredBlob) : Prop :=
  blob.byteLength = blob.bytes.size ∧
    scheme.digestBytes blob.bytes = blob.digest

end MeasuredBlob

/-- The complete identity and byte-level I/O of one architecture run.

`executable` is the measured ELF, cubin, or other native image interpreted by
the architecture model.  `input` and `output` are the complete byte strings
at the native checker boundary, not merely application summaries. -/
structure MeasuredRun where
  measurementSchemeId : Digest
  semanticsId : Digest
  target : ExecutionTarget
  entryPoint : String
  executable : MeasuredBlob
  input : MeasuredBlob
  output : MeasuredBlob

namespace MeasuredRun

/-- All three byte strings are tied to the explicitly selected measurement
scheme. -/
structure ExactMeasurements
    (scheme : MeasurementScheme) (run : MeasuredRun) : Prop where
  schemeId : run.measurementSchemeId = scheme.schemeId
  executable : run.executable.Exact scheme
  input : run.input.Exact scheme
  output : run.output.Exact scheme

end MeasuredRun

/-- Reflexive-transitive execution of an architecture's single-step relation.

Defining this closure locally keeps the trusted shape of the boundary small
and makes an explicit trace relation available to architecture-model
instantiations. -/
inductive Trace {State : Type u} (step : State → State → Prop) :
    State → State → Prop where
  | refl (state : State) : Trace step state state
  | tail {initial middle final : State} :
      Trace step initial middle →
      step middle final →
      Trace step initial final

namespace Trace

/-- One architecture step is a finite trace. -/
theorem single {State : Type u} {step : State → State → Prop}
    {initial final : State} (hstep : step initial final) :
    Trace step initial final :=
  .tail (.refl initial) hstep

/-- An invariant preserved by every architecture step is preserved by a
finite trace. -/
theorem preserves {State : Type u} {step : State → State → Prop}
    (invariant : State → Prop)
    (stepPreserves :
      ∀ {before after}, step before after →
        invariant before → invariant after)
    {initial final : State}
    (trace : Trace step initial final)
    (initialInvariant : invariant initial) :
    invariant final := by
  induction trace with
  | refl =>
      exact initialInvariant
  | tail priorTrace lastStep ih =>
      exact stepPreserves lastStep ih

/-- A state observation unchanged by every architecture step is unchanged
across a finite trace. -/
theorem observation_eq {State Observation : Type u}
    {step : State → State → Prop}
    (observe : State → Observation)
    (stepPreserves :
      ∀ {before after}, step before after →
        observe before = observe after)
    {initial final : State}
    (trace : Trace step initial final) :
    observe initial = observe final := by
  induction trace with
  | refl =>
      rfl
  | tail priorTrace lastStep ih =>
      exact ih.trans (stepPreserves lastStep)

end Trace

/-- A formal native architecture semantics.

For x86-64, `State` should include registers, flags, memory, and relevant
system state; for an H100 it should include the modeled SASS machine and
memory/thread state.  `load` interprets the exact image and input bytes.
`haltedWith` observes the exact result bytes at the native ABI boundary. -/
structure ArchitectureSemantics where
  semanticsId : Digest
  target : ExecutionTarget
  State : Type u
  load :
    String → ByteArray → ByteArray → State → Prop
  step : State → State → Prop
  haltedWith : State → ByteArray → Prop

/-- Exact formal architecture execution of one measured code/input/output
triple.

The initial and final architecture states are existential witnesses inside
this proposition.  They are intentionally not data fields of a Prop-valued
structure. -/
def ArchitectureExecution
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (run : MeasuredRun) : Prop :=
  run.ExactMeasurements scheme ∧
    run.semanticsId = machine.semanticsId ∧
    run.target = machine.target ∧
    ∃ initialState finalState : machine.State,
      machine.load run.entryPoint run.executable.bytes run.input.bytes
          initialState ∧
        Trace machine.step initialState finalState ∧
        machine.haltedWith finalState run.output.bytes

/-- Architecture-neutral behavior of the native checker.

This relation may be instantiated by a deterministic Lean checker function,
but a relation also accommodates explicit rejection or error outcomes without
forcing those outcomes into the architecture core. -/
structure NativeCheckerSemantics where
  checkerId : String
  accepts : ByteArray → ByteArray → Prop

/-- Ordinary-Lean proof obligation connecting one exact native image to an
application checker.

The equality hypotheses prevent a theorem for one binary or entry point from
being reused for a different measured image.  This proposition contains no
attestation assumption. -/
structure ArchitectureRefinesNativeChecker
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (checker : NativeCheckerSemantics)
    (executable : MeasuredBlob)
    (entryPoint : String) : Prop where
  executableExact : executable.Exact scheme
  refines :
    ∀ {run : MeasuredRun},
      run.executable = executable →
      run.entryPoint = entryPoint →
      ArchitectureExecution scheme machine run →
      checker.accepts run.input.bytes run.output.bytes

/-- A receipt-indexed token whose sole semantic content is the exact
architecture execution of this one run.

The public constructor is harmless: constructing the token inside Lean
already requires proving the architecture execution.  A future trusted
receipt axiom/importer would be needed only to create the same fact for a
physical run whose full trace is intentionally not replayed locally.  That
importer must be closed over a reviewed measurement scheme and machine model;
it must never accept either as a caller-controlled argument. -/
structure ReceiptExecutionFact
    (receiptHash : Digest)
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (run : MeasuredRun) : Prop where
  execution : ArchitectureExecution scheme machine run

namespace ArchitectureRefinesNativeChecker

/-- A proved architecture execution of the selected image implies the native
checker relation. -/
theorem accepts_of_execution
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {executable : MeasuredBlob}
    {entryPoint : String}
    {run : MeasuredRun}
    (refinement :
      ArchitectureRefinesNativeChecker
        scheme machine checker executable entryPoint)
    (executableBound : run.executable = executable)
    (entryPointBound : run.entryPoint = entryPoint)
    (execution : ArchitectureExecution scheme machine run) :
    checker.accepts run.input.bytes run.output.bytes :=
  refinement.refines executableBound entryPointBound execution

/-- Receipt composition does only one projection: receipt to exact
architecture execution.  The independent image-refinement theorem performs
the architecture-to-checker step. -/
theorem accepts_of_receipt
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {executable : MeasuredBlob}
    {entryPoint : String}
    {run : MeasuredRun}
    (refinement :
      ArchitectureRefinesNativeChecker
        scheme machine checker executable entryPoint)
    (executableBound : run.executable = executable)
    (entryPointBound : run.entryPoint = entryPoint)
    (receipt :
      ReceiptExecutionFact receiptHash scheme machine run) :
    checker.accepts run.input.bytes run.output.bytes :=
  refinement.accepts_of_execution
    executableBound entryPointBound receipt.execution

end ArchitectureRefinesNativeChecker

end SparkInterval.Execution.Architecture
