/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.LoopRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.Run

/-!
# Fixed-width CPU image to the proved Sqrt218 V2 semantics

This adapter gives each flattened binary section the exact typed meaning used
by `Sqrt218Operational.V2.run`:

* factor-reference and gap slices become `PrimeRosterCertificate` rows;
* power-reference slices become the linear-size inverse map;
* fixed-point endpoints become the one-pass log rows; and
* the checked two-limb result becomes `claimedExit`.

The generic theorem `sourceClaim_of_completeRun` is ordinary Lean and does
not evaluate production data.  The absent physical refinement remains the
acceptance-only statement `NativeAcceptanceRefinesV2`; this module constructs
no inhabitant of it.  `NativeRunnerRefinesV2` records the optional stronger
all-outcomes equality.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter

namespace V2

open
  SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

def factorPair
    (pair :
      SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.FactorPair) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.FactorPair :=
  ⟨pair.left, pair.right⟩

def factorRefsAt (image : ArchiveImage) (index : Nat) : List Nat :=
  let row := image.primes.getD index default
  (image.factorRefs.drop row.factorRefIndex).take row.factorRefCount

def gapPairsAt
    (image : ArchiveImage) (index : Nat) :
    List
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.FactorPair :=
  let row := image.primes.getD index default
  ((image.factorPairs.drop row.gapPairIndex).take row.gapPairCount).map
    factorPair

def usedGapPairCount (image : ArchiveImage) : Nat :=
  (image.primes.map PrimeRecord.gapPairCount).sum

def primeRow (image : ArchiveImage) (index : Nat) :
    PrimeRow :=
  let row := image.primes.getD index default
  {
    prime := row.prime
    witness := row.witness
    factorRefs := factorRefsAt image index
    gapPairs := gapPairsAt image index
  }

def roster (image : ArchiveImage) : PrimeRosterCertificate := {
  rows :=
    (List.range image.primes.length).map (primeRow image)
  tailPairs :=
    (image.factorPairs.drop (usedGapPairCount image)).map factorPair
}

def powerRefsAt (image : ArchiveImage) (index : Nat) : List Nat :=
  let row := image.primes.getD index default
  (image.powerRefs.drop row.powerRefIndex).take row.powerRefCount

def powerEvent (event : EventRecord) :
    TGComputeContracts.Sqrt218.PowerEvent := {
  value := event.value
  primeIndex := event.primeIndex
  exponent := event.exponent
  floorSqrt := event.floorSqrt
}

def layout (image : ArchiveImage) : PowerLayoutCertificate := {
  events := image.events.map powerEvent
  eventIndicesByPrime :=
    (List.range image.primes.length).map (powerRefsAt image)
}

def logRow (row : PrimeRecord) : LogRows.Row := {
  prime := row.prime
  lower := row.logLower
  upper := row.logUpper
}

def logs (image : ArchiveImage) : LogRows.Certificate := {
  rows := image.primes.map logRow
}

def archive
    (image : ArchiveImage) (result : ArithmeticResult) :
    Archive := {
  kind := certificateKind
  schemaVersion := image.header.version
  bound := image.header.bound
  logSeedAt := image.header.logSeedAt
  logScale := image.header.logScale
  reciprocalScale := image.header.reciprocalScale
  roster := roster image
  layout := layout image
  logs := logs image
  claimedExit := result.state.toFixedState
}

end V2

/-- Exact complete semantics for one parsed fixed-width image and computed
two-limb exit state. -/
def completeCheck
    (image : ArchiveImage) (result : ArithmeticResult) : Bool :=
  SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.run
    (V2.archive image result)

/-- Reference execution: checked fixed-width arithmetic followed by the
proved complete V2 semantic checker.

Evaluating this on a production image is a cloud task.  Merely compiling the
definition performs no replay. -/
def completeRun (image : ArchiveImage) :
    Except Reject ArithmeticResult := do
  let result ← runArithmetic image
  if completeCheck image result then
    pure result
  else
    throw Reject.arithmeticMismatch

/-- A successful complete reference execution includes the exact generic
fixed-event fold returned by the checked two-limb arithmetic pass.

This is a symbolic refinement theorem over arbitrary input.  It neither
loads nor evaluates a production certificate. -/
theorem completeRun_eventFold_refines
    {image : ArchiveImage} {result : ArithmeticResult}
    (hrun : completeRun image = .ok result) :
    headerCheck image = true ∧
      TGComputeContracts.Sqrt218.runFixedEvents
          image.events.length
          (kernelEventAt image)
          (kernelLogLowerAt image)
          (kernelLogUpperAt image)
          0 image.events.length
          TGComputeContracts.Sqrt218.FixedState.zero =
        some result.state.toFixedState := by
  unfold completeRun at hrun
  cases harithmetic : runArithmetic image with
  | error reason =>
      rw [harithmetic] at hrun
      change Except.error reason = Except.ok result at hrun
      contradiction
  | ok arithmeticResult =>
      rw [harithmetic] at hrun
      change
        (if completeCheck image arithmeticResult = true then
          Except.ok arithmeticResult
        else
          Except.error Reject.arithmeticMismatch) =
            Except.ok result at hrun
      split at hrun
      next _hcheck =>
        change Except.ok arithmeticResult = Except.ok result at hrun
        have hresult : arithmeticResult = result :=
          Except.ok.inj hrun
        subst result
        exact runArithmetic_eventFold_refines harithmetic
      next _hcheck =>
        contradiction

/-- The reference V2 execution's successful arithmetic stage refines both
the complete generic event fold and its terminal anchor guard. -/
theorem completeRun_arithmetic_refines
    {image : ArchiveImage} {result : ArithmeticResult}
    (hrun : completeRun image = .ok result) :
    headerCheck image = true ∧
      TGComputeContracts.Sqrt218.runFixedEvents
          image.events.length
          (kernelEventAt image)
          (kernelLogLowerAt image)
          (kernelLogUpperAt image)
          0 image.events.length
          TGComputeContracts.Sqrt218.FixedState.zero =
        some result.state.toFixedState ∧
      TGComputeContracts.Sqrt218.anchorOK
          image.header.bound
          result.state.weightedUpper.toNat
          result.state.psiLower.toNat = true := by
  unfold completeRun at hrun
  cases harithmetic : runArithmetic image with
  | error reason =>
      rw [harithmetic] at hrun
      change Except.error reason = Except.ok result at hrun
      contradiction
  | ok arithmeticResult =>
      rw [harithmetic] at hrun
      change
        (if completeCheck image arithmeticResult = true then
          Except.ok arithmeticResult
        else
          Except.error Reject.arithmeticMismatch) =
            Except.ok result at hrun
      split at hrun
      next _hcheck =>
        change Except.ok arithmeticResult = Except.ok result at hrun
        have hresult : arithmeticResult = result :=
          Except.ok.inj hrun
        subst result
        exact runArithmetic_refines_kernel harithmetic
      next _hcheck =>
        contradiction

theorem sourceClaim_of_completeCheck
    {image : ArchiveImage} {result : ArithmeticResult}
    (hcheck : completeCheck image result = true) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.sourceClaim_of_run
    hcheck

/-- A successful `completeRun` passed `completeCheck` for the same image and
result.

This theorem is symbolic.  Applying it to a supplied equality does not
evaluate `runArithmetic` on the image. -/
theorem completeCheck_eq_true_of_completeRun
    {image : ArchiveImage}
    {result : ArithmeticResult}
    (hrun : completeRun image = .ok result) :
    completeCheck image result = true := by
  unfold completeRun at hrun
  cases harithmetic : runArithmetic image with
  | error reason =>
      rw [harithmetic] at hrun
      change Except.error reason = Except.ok result at hrun
      contradiction
  | ok actual =>
      rw [harithmetic] at hrun
      change
        (if completeCheck image actual = true then
          Except.ok actual
        else
          Except.error Reject.arithmeticMismatch) =
            Except.ok result at hrun
      split at hrun
      next hcheck =>
        have hresult : actual = result :=
          Except.ok.inj hrun
        subst actual
        exact hcheck
      next _hcheck =>
        contradiction

def referenceV2Outcome
    (decode : ByteArray → Except Reject ArchiveImage)
    (bytes : ByteArray) : NativeOutcome :=
  match decode bytes with
  | .error reason => .rejected reason
  | .ok image =>
      match completeRun image with
      | .error reason => .rejected reason
      | .ok result => .accepted result

/-- Physical execution obligation for the complete fixed-width V2 path.

No declaration in the repository currently proves this for C, a compiler,
ELF, x86-64, or a physical CPU.  Secure-enclave attestation binds the measured
artifact and run; it does not prove this proposition. -/
def NativeRunnerRefinesV2
    (decode : ByteArray → Except Reject ArchiveImage)
    (nativeRun : ByteArray → NativeOutcome) : Prop :=
  ∀ bytes, nativeRun bytes = referenceV2Outcome decode bytes

/-- Acceptance-only physical refinement required by the theorem bridge.

The C status API intentionally coarsens several Lean rejection reasons.
Requiring exact failure-code equality would therefore be stronger than the
security claim and would obscure the real obligation: whenever the measured
binary accepts exact bytes with a result, the Lean decoder and complete V2
reference checker accept those same bytes with that same result. -/
def NativeAcceptanceRefinesV2
    (decode : ByteArray → Except Reject ArchiveImage)
    (nativeRun : ByteArray → NativeOutcome) : Prop :=
  ∀ bytes result,
    nativeRun bytes = .accepted result →
      referenceV2Outcome decode bytes = .accepted result

/-- Weaker, no-replay acceptance interface.

Whenever the native checker accepts exact input bytes and an exact result,
those bytes decode to an image for which the already supplied result passes
the proved complete V2 Boolean checker.  Unlike
`NativeAcceptanceRefinesV2`, this relation does not require
`runArithmetic image` or `completeRun image` to be evaluated again in Lean.

A compiler/ISA or source refinement may establish this relation directly
from the accepting execution trace. -/
def NativeAcceptanceSuppliesV2Check
    (decode : ByteArray → Except Reject ArchiveImage)
    (nativeRun : ByteArray → NativeOutcome) : Prop :=
  ∀ bytes result,
    nativeRun bytes = .accepted result →
      ∃ image : ArchiveImage,
        decode bytes = .ok image ∧
          completeCheck image result = true

theorem NativeRunnerRefinesV2.acceptance
    {decode : ByteArray → Except Reject ArchiveImage}
    {nativeRun : ByteArray → NativeOutcome}
    (hrefines : NativeRunnerRefinesV2 decode nativeRun) :
    NativeAcceptanceRefinesV2 decode nativeRun := by
  intro bytes result haccepted
  rw [← hrefines bytes]
  exact haccepted

/-- The older, stronger `completeRun` refinement implies the no-replay
checked-result interface.  The converse is intentionally not claimed. -/
theorem NativeAcceptanceRefinesV2.suppliesV2Check
    {decode : ByteArray → Except Reject ArchiveImage}
    {nativeRun : ByteArray → NativeOutcome}
    (hrefines : NativeAcceptanceRefinesV2 decode nativeRun) :
    NativeAcceptanceSuppliesV2Check decode nativeRun := by
  intro bytes result haccepted
  have href :=
    hrefines bytes result haccepted
  unfold referenceV2Outcome at href
  cases hdecode : decode bytes with
  | error reason =>
      simp only [hdecode] at href
      contradiction
  | ok image =>
      simp only [hdecode] at href
      cases hrun : completeRun image with
      | error reason =>
          simp only [hrun] at href
          contradiction
      | ok actual =>
          simp only [hrun] at href
          have hresult : actual = result :=
            NativeOutcome.accepted.inj href
          subst actual
          exact
            ⟨image, rfl,
              completeCheck_eq_true_of_completeRun hrun⟩

theorem accepted_native_run_is_v2_reference
    {decode : ByteArray → Except Reject ArchiveImage}
    {nativeRun : ByteArray → NativeOutcome}
    (hrefines : NativeAcceptanceRefinesV2 decode nativeRun)
    {bytes : ByteArray} {result : ArithmeticResult}
    (haccepted : nativeRun bytes = .accepted result) :
    referenceV2Outcome decode bytes = .accepted result :=
  hrefines bytes result haccepted

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter
