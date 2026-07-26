/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.ArchitectureExecution

/-!
# Compact, opaque architecture-run receipts

This module gives the data-independent shape needed when a production input
and execution trace are too large to replay locally.

A `CompactRunPins` value contains only lengths, digests, the selected entry
point, target, measurement scheme, and formal-machine identity.  It contains
no executable, input, result, architecture state, or trace bytes.  A
`CompactReceiptExecutionFact` existentially supplies those byte strings as
part of an exact `ArchitectureExecution`.  Because the fact is a proposition,
an axiomatically supplied witness is opaque and is erased by code generation;
ordinary local checking does not materialize or hash it.

The trust layers remain deliberately separate:

* signature verification and confidential-compute appraisal decide whether a
  compact receipt is admitted;
* the one execution trust boundary may turn that admitted receipt into a
  `CompactReceiptExecutionFact` for a *closed* measurement scheme and machine;
* `CompactArchitectureRefinement` is an ordinary, universal Lean theorem
  about every byte-level run matching the pins.

In particular, the refinement quantifies over every digest preimage.  This
module neither assumes nor proves that SHA-256 is injective.  A refinement
which applies only to one chosen digest preimage needs an additional,
explicit cryptographic uniqueness assumption; it cannot obtain that
assumption from these definitions.

This file defines no axiom.  The public constructor of the receipt fact is
safe: using it requires an existing proof of the exact architecture
execution.  A trusted importer must not quantify over a caller-selected
`MeasurementScheme`, `ArchitectureSemantics`, or refinement proposition.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture

/-- The only information about one byte string retained by a compact
receipt.  The digest syntax and algorithm are fixed by the external receipt
protocol and `MeasurementScheme`; this structure itself is only data. -/
structure CompactBlobPin where
  byteLength : Nat
  digest : Digest
  deriving Repr, DecidableEq, BEq

namespace CompactBlobPin

/-- A byte string realizes a compact pin under the selected measurement
scheme.

This proposition is useful when stating an explicit cryptographic
preimage-binding assumption.  The compact composition theorem below does not
evaluate it locally; it obtains the same equalities from the opaque
architecture-execution witness. -/
def MatchesBytes
    (scheme : MeasurementScheme)
    (pin : CompactBlobPin)
    (bytes : ByteArray) : Prop :=
  bytes.size = pin.byteLength ∧
    scheme.digestBytes bytes = pin.digest

/-- Optional, explicit uniqueness assumption for a compact digest pin.

This is intentionally not a theorem about SHA-256.  Most callers should avoid
it by proving their semantic refinement for every byte string matching the
pin.  It is named here so any design that instead relies on collision or
second-preimage resistance must expose that reliance as a premise. -/
def UniquelyIdentifies
    (scheme : MeasurementScheme)
    (pin : CompactBlobPin) : Prop :=
  ∀ {left right : ByteArray},
    pin.MatchesBytes scheme left →
    pin.MatchesBytes scheme right →
    left = right

end CompactBlobPin

/-- Compact identity of one exact architecture run.

`result` is the complete native-boundary output, not an application-selected
proposition.  A small application result envelope may be checked separately
and related to this pin by an ordinary parser/refinement theorem. -/
structure CompactRunPins where
  measurementSchemeId : Digest
  semanticsId : Digest
  target : ExecutionTarget
  entryPoint : String
  executable : CompactBlobPin
  input : CompactBlobPin
  result : CompactBlobPin
  deriving Repr, DecidableEq, BEq

namespace MeasuredRun

/-- A full, existentially hidden measured run has exactly the public compact
identity.

These are equalities between advertised fields.  The
`ArchitectureExecution` conjunct in a receipt fact additionally proves that
the advertised fields are the actual lengths and measurements of the hidden
bytes. -/
structure MatchesCompactPins
    (run : MeasuredRun)
    (pins : CompactRunPins) : Prop where
  measurementScheme :
    run.measurementSchemeId = pins.measurementSchemeId
  semantics :
    run.semanticsId = pins.semanticsId
  target :
    run.target = pins.target
  entryPoint :
    run.entryPoint = pins.entryPoint
  executableLength :
    run.executable.byteLength = pins.executable.byteLength
  executableDigest :
    run.executable.digest = pins.executable.digest
  inputLength :
    run.input.byteLength = pins.input.byteLength
  inputDigest :
    run.input.digest = pins.input.digest
  resultLength :
    run.output.byteLength = pins.result.byteLength
  resultDigest :
    run.output.digest = pins.result.digest

end MeasuredRun

/-- The sole semantic payload that a compact physical-run receipt needs to
supply.

The receipt hash is an index, not a signature verifier.  Admission,
freshness, signature validation, and platform appraisal happen before a
trusted boundary can produce this proposition.  The byte and state witnesses
remain under an existential and are never fields of the compact pins.

The `scheme` and `machine` parameters are harmless for ordinary construction,
which already requires a proof of their exact execution.  Any axiom producing
this fact must close over reviewed choices rather than accept them from its
caller. -/
structure CompactReceiptExecutionFact
    (receiptHash : Digest)
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (pins : CompactRunPins) : Prop where
  execution :
    ∃ run : MeasuredRun,
      run.MatchesCompactPins pins ∧
        ArchitectureExecution scheme machine run

/-- Ordinary, data-independent implementation refinement.

The theorem author must handle every hidden byte string admitted by the
compact pins and exact architecture semantics.  Consequently digest
collision resistance is not silently smuggled into the semantic refinement.
The definition has no attestation or receipt premise. -/
def CompactArchitectureRefinement
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (checker : NativeCheckerSemantics)
    (pins : CompactRunPins) : Prop :=
  ∀ {run : MeasuredRun},
    run.MatchesCompactPins pins →
    ArchitectureExecution scheme machine run →
    checker.accepts run.input.bytes run.output.bytes

/-- Existential checker acceptance derived from a compact receipt.

This conclusion deliberately keeps the executable, input, output, states, and
trace opaque.  A downstream theorem may eliminate the existential only into a
proposition, so it can reason symbolically about the witnesses without
turning them into local data or replaying the trace. -/
def OpaqueNativeAcceptance
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (checker : NativeCheckerSemantics)
    (pins : CompactRunPins) : Prop :=
  ∃ run : MeasuredRun,
    run.MatchesCompactPins pins ∧
      ArchitectureExecution scheme machine run ∧
      checker.accepts run.input.bytes run.output.bytes

/-- Composition of the only trusted per-run fact with a universal,
ordinary-Lean refinement theorem.

The proof is just existential elimination and application of `refinement`; it
does not inspect any byte, architecture state, or trace step. -/
theorem opaqueNativeAcceptance_of_compactReceipt
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {pins : CompactRunPins}
    (receipt :
      CompactReceiptExecutionFact receiptHash scheme machine pins)
    (refinement :
      CompactArchitectureRefinement scheme machine checker pins) :
    OpaqueNativeAcceptance scheme machine checker pins := by
  rcases receipt.execution with ⟨run, pinBound, executed⟩
  exact ⟨run, pinBound, executed, refinement pinBound executed⟩

/-- The hidden bytes really have the lengths and measurements advertised by
the compact receipt.

This theorem only projects equalities already contained in the opaque
execution fact.  It does not run `digestBytes` on any locally retained
production byte array. -/
theorem pinnedMeasurements_of_execution
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    {run : MeasuredRun}
    (pinBound : run.MatchesCompactPins pins)
    (executed : ArchitectureExecution scheme machine run) :
    pins.measurementSchemeId = scheme.schemeId ∧
      pins.semanticsId = machine.semanticsId ∧
      pins.target = machine.target ∧
      pins.executable.MatchesBytes scheme run.executable.bytes ∧
      pins.input.MatchesBytes scheme run.input.bytes ∧
      pins.result.MatchesBytes scheme run.output.bytes := by
  rcases executed with
    ⟨measurements, semantics, target, _initial, _final,
      _loaded, _trace, _halted⟩
  refine ⟨pinBound.measurementScheme.symm.trans measurements.schemeId,
    pinBound.semantics.symm.trans semantics,
    pinBound.target.symm.trans target, ?_, ?_, ?_⟩
  · exact ⟨measurements.executable.1.symm.trans pinBound.executableLength,
      measurements.executable.2.trans pinBound.executableDigest⟩
  · exact ⟨measurements.input.1.symm.trans pinBound.inputLength,
      measurements.input.2.trans pinBound.inputDigest⟩
  · exact ⟨measurements.output.1.symm.trans pinBound.resultLength,
      measurements.output.2.trans pinBound.resultDigest⟩

/-- Every compact receipt fact exposes its advertised measurements, still
under an existential.  No hidden witness is returned as computational data.
-/
theorem compactReceipt_hasPinnedMeasurements
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    (receipt :
      CompactReceiptExecutionFact receiptHash scheme machine pins) :
    ∃ run : MeasuredRun,
      run.MatchesCompactPins pins ∧
        ArchitectureExecution scheme machine run ∧
        pins.executable.MatchesBytes scheme run.executable.bytes ∧
        pins.input.MatchesBytes scheme run.input.bytes ∧
        pins.result.MatchesBytes scheme run.output.bytes := by
  rcases receipt.execution with ⟨run, pinBound, executed⟩
  have measured := pinnedMeasurements_of_execution pinBound executed
  exact ⟨run, pinBound, executed, measured.2.2.2.1,
    measured.2.2.2.2.1, measured.2.2.2.2.2⟩

/-! ## Optional explicit executable-preimage binding -/

/-- Derive the universal compact refinement from a theorem about one retained
reviewed executable, with the executable digest's uniqueness assumption
exposed as a premise.

This adapter is appropriate when the static binary is small enough to retain
and validate locally but the production input is not.  It does **not** require
uniqueness for input or result bytes: the concrete executable refinement
already quantifies over arbitrary input and output byte strings.

For SHA-256, `executableUnique` is a cryptographic second-preimage/collision
assumption, not a Lean theorem.  The static-artifact construction below avoids
that premise in the *ordinary refinement theorem* by putting the exact
reviewed executable into the trusted per-run fact itself.  Receipt admission
then owns the digest-to-exact-bytes identification explicitly. -/
theorem compactArchitectureRefinement_of_reviewedExecutable
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {pins : CompactRunPins}
    {executable : MeasuredBlob}
    (reviewedExecutablePinned :
      pins.executable.MatchesBytes scheme executable.bytes)
    (executableUnique :
      pins.executable.UniquelyIdentifies scheme)
    (refinement :
      ArchitectureRefinesNativeChecker
        scheme machine checker executable pins.entryPoint) :
    CompactArchitectureRefinement scheme machine checker pins := by
  intro run pinBound executed
  have measured :=
    pinnedMeasurements_of_execution pinBound executed
  have executableBytes :
      run.executable.bytes = executable.bytes :=
    executableUnique measured.2.2.2.1 reviewedExecutablePinned
  have reviewedLength :
      executable.byteLength = pins.executable.byteLength :=
    refinement.executableExact.1.trans reviewedExecutablePinned.1
  have reviewedDigest :
      executable.digest = pins.executable.digest :=
    refinement.executableExact.2.symm.trans reviewedExecutablePinned.2
  have runLength :
      run.executable.byteLength = pins.executable.byteLength :=
    pinBound.executableLength
  have runDigest :
      run.executable.digest = pins.executable.digest :=
    pinBound.executableDigest
  have executableBound : run.executable = executable := by
    cases runExecutable : run.executable
    cases reviewedExecutable : executable
    simp_all
  exact
    refinement.accepts_of_execution
      executableBound pinBound.entryPoint executed

/-! ## Preferred selective static-artifact boundary -/

/-- An input blob whose advertised measurement is the compact input pin.

The bytes remain a variable.  An `ArchitectureExecution` of a run containing
this blob proves that the variable bytes really have the advertised length
and digest; constructing the term itself performs no digest evaluation. -/
def compactInputBlob
    (pins : CompactRunPins)
    (inputBytes : ByteArray) : MeasuredBlob where
  bytes := inputBytes
  byteLength := pins.input.byteLength
  digest := pins.input.digest

/-- Full measured run with exact, locally retained static executable/result
blobs and only the potentially huge input left opaque.

The header is copied from the compact pins.  Exact agreement with the selected
measurement scheme and machine follows from `ArchitectureExecution`, rather
than from a local replay. -/
def runWithStaticArtifacts
    (pins : CompactRunPins)
    (executable result : MeasuredBlob)
    (inputBytes : ByteArray) : MeasuredRun where
  measurementSchemeId := pins.measurementSchemeId
  semanticsId := pins.semanticsId
  target := pins.target
  entryPoint := pins.entryPoint
  executable := executable
  input := compactInputBlob pins inputBytes
  output := result

/-- Exact local validation of the small static artifacts against the compact
receipt pins.

For Sqrt218 the intended artifacts are the reviewed pure-entry ELF and the
120-byte native result.  Checking these once is static binary validation, not
production certificate or instruction-trace replay. -/
structure StaticArtifactsPinned
    (scheme : MeasurementScheme)
    (pins : CompactRunPins)
    (executable result : MeasuredBlob) : Prop where
  executableExact :
    executable.Exact scheme
  executableLength :
    executable.byteLength = pins.executable.byteLength
  executableDigest :
    executable.digest = pins.executable.digest
  resultExact :
    result.Exact scheme
  resultLength :
    result.byteLength = pins.result.byteLength
  resultDigest :
    result.digest = pins.result.digest

/-- Preferred production fact when only the input/certificate is large.

The static executable and native result are exact parameters and can be
reviewed in the ordinary source tree.  Only `inputBytes` and the architecture
states/trace remain existential.  This shape therefore needs no
caller-supplied digest-injectivity premise in semantic refinement: the trusted
per-run fact itself asserts that the physically measured run used these exact
static bytes.  Establishing that assertion from a digest-only signed receipt
is part of the sole cryptographic/attestation boundary, not a theorem here. -/
structure CompactInputReceiptExecutionFact
    (receiptHash : Digest)
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (pins : CompactRunPins)
    (executable result : MeasuredBlob) : Prop where
  staticArtifacts :
    StaticArtifactsPinned scheme pins executable result
  execution :
    ∃ inputBytes : ByteArray,
      ArchitectureExecution scheme machine
        (runWithStaticArtifacts pins executable result inputBytes)

/-- Runs built from pinned static artifacts match every compact public field,
independently of the hidden input bytes. -/
theorem runWithStaticArtifacts_matchesCompactPins
    {scheme : MeasurementScheme}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    (staticArtifacts :
      StaticArtifactsPinned scheme pins executable result)
    (inputBytes : ByteArray) :
    MeasuredRun.MatchesCompactPins
      (runWithStaticArtifacts pins executable result inputBytes) pins := by
  exact {
    measurementScheme := rfl
    semantics := rfl
    target := rfl
    entryPoint := rfl
    executableLength := staticArtifacts.executableLength
    executableDigest := staticArtifacts.executableDigest
    inputLength := rfl
    inputDigest := rfl
    resultLength := staticArtifacts.resultLength
    resultDigest := staticArtifacts.resultDigest
  }

/-- Forget that the executable and result were retained exactly, obtaining
the fully opaque generic receipt fact.  This is propositional packaging only.
-/
theorem CompactInputReceiptExecutionFact.toCompactReceipt
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result) :
    CompactReceiptExecutionFact receiptHash scheme machine pins := by
  rcases receipt.execution with ⟨inputBytes, executed⟩
  exact ⟨runWithStaticArtifacts pins executable result inputBytes,
    runWithStaticArtifacts_matchesCompactPins
      receipt.staticArtifacts inputBytes,
    executed⟩

/-- Exact acceptance using a retained reviewed executable, retained small
result, and an existentially hidden production input.

The existing concrete `ArchitectureRefinesNativeChecker` applies directly:
the run's executable and entry point are definitionally the reviewed values.
No SHA-256 uniqueness assumption appears in this ordinary composition theorem
and no local input hashing is involved; exact static-byte identification is
already explicit in `receipt.execution`. -/
theorem nativeAcceptance_of_compactInputReceipt
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result)
    (refinement :
      ArchitectureRefinesNativeChecker
        scheme machine checker executable pins.entryPoint) :
    ∃ inputBytes : ByteArray,
      ArchitectureExecution scheme machine
          (runWithStaticArtifacts pins executable result inputBytes) ∧
        checker.accepts inputBytes result.bytes := by
  rcases receipt.execution with ⟨inputBytes, executed⟩
  have accepted :=
    refinement.accepts_of_execution
      (run := runWithStaticArtifacts pins executable result inputBytes)
      rfl rfl executed
  exact ⟨inputBytes, executed, accepted⟩

end SparkInterval.Execution.Architecture
