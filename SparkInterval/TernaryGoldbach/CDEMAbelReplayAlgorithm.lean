/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate

/-!
# Typed operational model of the CDEM Abel chunk replayer

The production CDEM supervisor does not prove a real inequality directly.
For every retained chunk it runs
`reference/tg_cdem_abel_chunk_replay.cpp`, whose successful path:

1. constructs a divisor-jump table;
2. scans the supplied incoming floor state;
3. constructs a directed reciprocal-square-root weight at each event; and
4. returns the terminal state and the two integer Abel folds.

This file gives that algorithm a small, unbounded-integer operational model.
`ReplayKernelData` represents the tables constructed internally by the
reviewed C++ source.  `ValidFor` checks the two facts the C implementation
must establish about those tables: each divisor entry is the closed
`floorJump`, and each square-root weight satisfies its exact integer guard.
`scanSteps` then performs the same serial recurrence and fold.

The main theorem, `locallyRealizes_of_accepts`, is universal in the chunk and
the constructed tables.  It proves that the typed algorithm can accept only
by constructing `Chunk.LocallyRealizes`; it does not mention the real source
claim and does not replay the five-billion-event production run.

`Supervisor.Accepts` is the corresponding typed model of the measured
supervisor after byte parsing.  It requires every retained chunk to have
passed the operational replayer and proves
`LocalSourceScaleEvidence` in ordinary Lean.

The final section names, but does not inhabit, the remaining source and
binary refinement obligations.  In particular this module does **not** claim
that a C++ compiler, an ELF image, or x86-64 execution implements the typed
model.  It defines no axiom.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.CDEMAbelReplayAlgorithm

open Finset
open scoped BigOperators

namespace Recurrence

abbrev Chunk := CDEMAbelRecurrenceCertificate.Chunk
abbrev Certificate := CDEMAbelRecurrenceCertificate.Certificate
abbrev LocalSourceScaleEvidence (certificate : Certificate) :=
  CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence certificate
abbrev sourcePast := CDEMAbelRecurrenceCertificate.sourcePast
abbrev floorJump := CDEMAbelRecurrenceCertificate.floorJump
abbrev errorAtState := CDEMAbelRecurrenceCertificate.errorAtState
abbrev signedTermUpper :=
  CDEMAbelRecurrenceCertificate.signedTermUpper
abbrev absoluteTermUpper :=
  CDEMAbelRecurrenceCertificate.absoluteTermUpper
abbrev SqrtWeightValid :=
  CDEMAbelRecurrenceCertificate.SqrtWeightValid

end Recurrence

/-! ## One typed chunk replay -/

/-- The three fields accepted on the chunk replayer command line after the
fixed production value of `K`. -/
structure ReplayRequest where
  low : Nat
  high : Nat
  before : Int
  deriving Repr, DecidableEq

namespace ReplayRequest

/-- Inclusive event count.  `WellFormed` rules out the truncated-subtraction
case used to make this definition total. -/
def eventCount (request : ReplayRequest) : Nat :=
  request.high + 1 - request.low

/-- Local floor state computed from the command-line incoming state. -/
def localFloorState (request : ReplayRequest) : Nat → Int
  | 0 => request.before
  | offset + 1 =>
      localFloorState request offset +
        Recurrence.floorJump (request.low + offset)

/-- Consecutive local error increment at one source index. -/
def localErrorIncrement
    (request : ReplayRequest) (n : Nat) : Int :=
  (Recurrence.errorAtState n
      (request.localFloorState (n - request.low + 1)) : Int) -
    (Recurrence.errorAtState (n - 1)
      (request.localFloorState (n - request.low)) : Int)

def WellFormed (request : ReplayRequest) : Prop :=
  request.low ≤ request.high ∧ request.high < Recurrence.sourcePast

instance instDecidableWellFormed (request : ReplayRequest) :
    Decidable request.WellFormed := by
  unfold WellFormed
  infer_instance

end ReplayRequest

/-- Tables constructed internally by the independent C++ replayer.

The real source uses a bounded delta array and a binary-search square-root
routine.  Total functions keep the mathematical model independent of an
allocation representation; only values on the requested interval matter. -/
structure ReplayKernelData where
  divisorJump : Nat → Int
  sqrtWeight : Nat → Nat

namespace ReplayKernelData

/-- Exact semantic postconditions of the two table-construction phases.

These are deliberately below `Chunk.LocallyRealizes`: they mention only one
divisor marker and one integer square guard at a time. -/
def ValidFor
    (data : ReplayKernelData) (request : ReplayRequest) : Prop :=
  ∀ n, n ∈ Finset.Ico request.low (request.high + 1) →
    data.divisorJump n = Recurrence.floorJump n ∧
      Recurrence.SqrtWeightValid n (data.sqrtWeight n)

end ReplayKernelData

/-- Unbounded-integer state immediately before the event at
`request.low + offset`. -/
structure ReplayState where
  offset : Nat
  floor : Int
  previousError : Nat
  signedUpper : Int
  absoluteUpper : Nat
  deriving Repr, DecidableEq

/-- The initial state matches the source's special `G(0)=0` rule because
`errorAtState 0 _` is definitionally zero. -/
def initialState (request : ReplayRequest) : ReplayState where
  offset := 0
  floor := request.before
  previousError :=
    Recurrence.errorAtState (request.low - 1) request.before
  signedUpper := 0
  absoluteUpper := 0

/-- One serial iteration of `tg_cdem_abel_chunk_replay.cpp`, expressed with
unbounded integers.  Fixed-width overflow checks belong to the C-source
refinement obligation below. -/
def scanStep
    (request : ReplayRequest) (data : ReplayKernelData)
    (state : ReplayState) : ReplayState :=
  let n := request.low + state.offset
  let nextFloor := state.floor + data.divisorJump n
  let nextError := Recurrence.errorAtState n nextFloor
  let increment : Int :=
    (nextError : Int) - (state.previousError : Int)
  {
    offset := state.offset + 1
    floor := nextFloor
    previousError := nextError
    signedUpper :=
      state.signedUpper +
        Recurrence.signedTermUpper n increment
    absoluteUpper :=
      state.absoluteUpper +
        Recurrence.absoluteTermUpper (data.sqrtWeight n) increment
  }

/-- Execute exactly `steps` serial replay events. -/
def scanSteps
    (request : ReplayRequest) (data : ReplayKernelData) :
    Nat → ReplayState
  | 0 => initialState request
  | steps + 1 =>
      scanStep request data (scanSteps request data steps)

/-- Observable fields printed by one successful chunk replay.  `variation`
and `deltaSum` are independently useful diagnostics but are not consumed by
the CDEM source theorem, so they do not belong to this minimal handoff. -/
structure ReplayOutput where
  after : Int
  signedUpper : Int
  absoluteUpper : Nat
  deriving Repr, DecidableEq

def replayOutput
    (request : ReplayRequest) (data : ReplayKernelData) : ReplayOutput :=
  let terminal :=
    scanSteps request data request.eventCount
  {
    after := terminal.floor
    signedUpper := terminal.signedUpper
    absoluteUpper := terminal.absoluteUpper
  }

/-- Turn the request and returned aggregates into the exact recurrence chunk
consumed by the Lean certificate. -/
def returnedChunk
    (request : ReplayRequest) (output : ReplayOutput) : Recurrence.Chunk where
  low := request.low
  high := request.high
  before := request.before
  after := output.after
  signedUpper := output.signedUpper
  absoluteUpper := output.absoluteUpper

@[simp] theorem returnedChunk_eventCount
    (request : ReplayRequest) (output : ReplayOutput) :
    (returnedChunk request output).eventCount = request.eventCount := by
  rfl

@[simp] theorem returnedChunk_localFloorState
    (request : ReplayRequest) (output : ReplayOutput) (offset : Nat) :
    (returnedChunk request output).localFloorState offset =
      request.localFloorState offset := by
  induction offset with
  | zero =>
      rfl
  | succ offset inductionHypothesis =>
      simp only [
        CDEMAbelRecurrenceCertificate.Chunk.localFloorState,
        ReplayRequest.localFloorState]
      rw [inductionHypothesis]
      rfl

@[simp] theorem returnedChunk_localErrorIncrement
    (request : ReplayRequest) (output : ReplayOutput) (n : Nat) :
    (returnedChunk request output).localErrorIncrement n =
      request.localErrorIncrement n := by
  unfold CDEMAbelRecurrenceCertificate.Chunk.localErrorIncrement
    ReplayRequest.localErrorIncrement
  rw [returnedChunk_localFloorState, returnedChunk_localFloorState]
  rfl

/-- Pure operational acceptance of one chunk.  It is not defined as
`Chunk.LocallyRealizes` and contains no source inequality. -/
def Accepts
    (request : ReplayRequest) (output : ReplayOutput) : Prop :=
  request.WellFormed ∧
    ∃ data : ReplayKernelData,
      data.ValidFor request ∧
        replayOutput request data = output

private theorem event_mem
    {request : ReplayRequest}
    (hwell : request.WellFormed)
    {offset : Nat}
    (hoffset : offset < request.eventCount) :
    request.low + offset ∈
      Finset.Ico request.low (request.high + 1) := by
  have hlowHigh : request.low ≤ request.high := hwell.1
  have hcount :
      request.eventCount = request.high + 1 - request.low := rfl
  rw [Finset.mem_Ico]
  constructor
  · omega
  · rw [hcount] at hoffset
    omega

private theorem localErrorIncrement_at_offset
    (request : ReplayRequest) (offset : Nat) :
    request.localErrorIncrement (request.low + offset) =
      (Recurrence.errorAtState
          (request.low + offset)
          (request.localFloorState (offset + 1)) : Int) -
        (Recurrence.errorAtState
          (request.low + offset - 1)
          (request.localFloorState offset) : Int) := by
  unfold ReplayRequest.localErrorIncrement
  rw [Nat.add_sub_cancel_left]

/-- Prefix invariant for the serial operational scan. -/
structure PrefixInvariant
    (request : ReplayRequest) (data : ReplayKernelData)
    (steps : Nat) (state : ReplayState) : Prop where
  offset : state.offset = steps
  floor :
    state.floor =
      request.localFloorState steps
  previousError :
    state.previousError =
      Recurrence.errorAtState
        (request.low + steps - 1)
        (request.localFloorState steps)
  signedUpper :
    state.signedUpper =
      ∑ offset ∈ Finset.range steps,
        Recurrence.signedTermUpper
          (request.low + offset)
          (request.localErrorIncrement (request.low + offset))
  absoluteUpper :
    state.absoluteUpper =
      ∑ offset ∈ Finset.range steps,
        Recurrence.absoluteTermUpper
          (data.sqrtWeight (request.low + offset))
          (request.localErrorIncrement (request.low + offset))

private theorem initial_prefixInvariant
    (request : ReplayRequest) (data : ReplayKernelData) :
    PrefixInvariant request data 0 (initialState request) := by
  constructor <;> simp [initialState,
    ReplayRequest.localFloorState]

private theorem scanStep_preserves_prefixInvariant
    {request : ReplayRequest} {data : ReplayKernelData}
    (hwell : request.WellFormed)
    (hvalid : data.ValidFor request)
    {steps : Nat}
    (hsteps : steps < request.eventCount)
    {state : ReplayState}
    (hinvariant :
      PrefixInvariant request data steps state) :
    PrefixInvariant request data (steps + 1)
      (scanStep request data state) := by
  have hmem := event_mem hwell hsteps
  have hjump :=
    (hvalid (request.low + steps) hmem).1
  have hlocalIncrement :=
    localErrorIncrement_at_offset request steps
  rcases hinvariant with
    ⟨hoffset, hfloor, hprevious, hsigned, habsolute⟩
  have hnextFloor :
      state.floor + data.divisorJump (request.low + state.offset) =
        request.localFloorState (steps + 1) := by
    rw [hoffset, hfloor, hjump]
    rfl
  rw [hoffset] at hnextFloor
  constructor
  · simp [scanStep, hoffset]
  · simpa only [scanStep, hoffset] using hnextFloor
  · simp only [scanStep]
    rw [hoffset, hnextFloor]
    congr 2
  · simp only [scanStep]
    rw [hoffset, hsigned, hnextFloor, hprevious,
      ← hlocalIncrement, Finset.sum_range_succ]
  · simp only [scanStep]
    rw [hoffset, habsolute, hnextFloor, hprevious,
      ← hlocalIncrement, Finset.sum_range_succ]

/-- Every prefix of a valid typed replay has the exact local-recurrence and
local-fold meaning. -/
theorem scanSteps_prefixInvariant
    {request : ReplayRequest} {data : ReplayKernelData}
    (hwell : request.WellFormed)
    (hvalid : data.ValidFor request)
    {steps : Nat}
    (hsteps : steps ≤ request.eventCount) :
    PrefixInvariant request data steps
      (scanSteps request data steps) := by
  induction steps with
  | zero =>
      exact initial_prefixInvariant request data
  | succ steps inductionHypothesis =>
      have hprior : steps ≤ request.eventCount := by omega
      have hstrict : steps < request.eventCount := by omega
      exact scanStep_preserves_prefixInvariant
        hwell hvalid hstrict (inductionHypothesis hprior)

/-- Universal algorithm-level soundness of one successful chunk replay. -/
theorem locallyRealizes_of_accepts
    {request : ReplayRequest} {output : ReplayOutput}
    (accepted : Accepts request output) :
    (returnedChunk request output).LocallyRealizes := by
  rcases accepted with ⟨hwell, data, hvalid, houtput⟩
  have hinvariant :=
    scanSteps_prefixInvariant hwell hvalid
      (steps := request.eventCount) (by omega)
  rcases hinvariant with
    ⟨_hoffset, hfloor, _hprevious, hsigned, habsolute⟩
  have hrun := houtput
  unfold replayOutput at hrun
  simp only at hrun
  have hafter : output.after =
      (returnedChunk request output).localFloorState
        (returnedChunk request output).eventCount := by
    have hafterRun :
        output.after =
          (scanSteps request data request.eventCount).floor := by
      rw [← hrun]
    rw [hafterRun, hfloor]
    simp
  refine ⟨hafter, data.sqrtWeight, ?_, ?_, ?_⟩
  · intro n hn
    exact (hvalid n hn).2
  · have hsignedRun :
        output.signedUpper =
          (scanSteps request data request.eventCount).signedUpper := by
      rw [← hrun]
    change output.signedUpper =
      ∑ n ∈ Finset.Ico request.low (request.high + 1),
        Recurrence.signedTermUpper n
          ((returnedChunk request output).localErrorIncrement n)
    calc
      output.signedUpper =
          (scanSteps request data request.eventCount).signedUpper :=
        hsignedRun
      _ = ∑ offset ∈ Finset.range request.eventCount,
          Recurrence.signedTermUpper
            (request.low + offset)
            (request.localErrorIncrement (request.low + offset)) :=
        hsigned
      _ = ∑ n ∈ Finset.Ico request.low (request.high + 1),
          Recurrence.signedTermUpper n
            (request.localErrorIncrement n) := by
        rw [Finset.sum_Ico_eq_sum_range]
        rfl
      _ = ∑ n ∈ Finset.Ico request.low (request.high + 1),
          Recurrence.signedTermUpper n
            ((returnedChunk request output).localErrorIncrement n) := by
        apply Finset.sum_congr rfl
        intro n _hn
        rw [returnedChunk_localErrorIncrement request output n]
  · have habsoluteRun :
        output.absoluteUpper =
          (scanSteps request data request.eventCount).absoluteUpper := by
      rw [← hrun]
    change output.absoluteUpper =
      ∑ n ∈ Finset.Ico request.low (request.high + 1),
        Recurrence.absoluteTermUpper (data.sqrtWeight n)
          ((returnedChunk request output).localErrorIncrement n)
    calc
      output.absoluteUpper =
          (scanSteps request data request.eventCount).absoluteUpper :=
        habsoluteRun
      _ = ∑ offset ∈ Finset.range request.eventCount,
          Recurrence.absoluteTermUpper
            (data.sqrtWeight (request.low + offset))
            (request.localErrorIncrement (request.low + offset)) :=
        habsolute
      _ = ∑ n ∈ Finset.Ico request.low (request.high + 1),
          Recurrence.absoluteTermUpper (data.sqrtWeight n)
            (request.localErrorIncrement n) := by
        rw [Finset.sum_Ico_eq_sum_range]
        rfl
      _ = ∑ n ∈ Finset.Ico request.low (request.high + 1),
          Recurrence.absoluteTermUpper (data.sqrtWeight n)
            ((returnedChunk request output).localErrorIncrement n) := by
        apply Finset.sum_congr rfl
        intro n _hn
        rw [returnedChunk_localErrorIncrement request output n]

/-! ## Typed measured-supervisor model -/

namespace Supervisor

/-- Canonical closed input consumed by the measured supervisor. -/
def canonicalInputText : String :=
  "{\"K\":199330,\"N\":5000000000," ++
  "\"weight_scale\":1000000000000000000}"

/-- Canonical result emitted only after all typed chunk replays pass. -/
def canonicalResultText : String :=
  toString
    (Nat.pair CDEMAbelSource.signedTarget CDEMAbelSource.absoluteTarget)

def canonicalInputBytes : ByteArray :=
  canonicalInputText.toUTF8

def canonicalResultBytes : ByteArray :=
  canonicalResultText.toUTF8

/-- The command-line request corresponding to a retained certificate row. -/
def requestOfChunk (chunk : Recurrence.Chunk) : ReplayRequest where
  low := chunk.low
  high := chunk.high
  before := chunk.before

/-- The observable replayer output expected for one retained row. -/
def outputOfChunk (chunk : Recurrence.Chunk) : ReplayOutput where
  after := chunk.after
  signedUpper := chunk.signedUpper
  absoluteUpper := chunk.absoluteUpper

@[simp] theorem returned_request_output (chunk : Recurrence.Chunk) :
    returnedChunk (requestOfChunk chunk) (outputOfChunk chunk) = chunk := by
  cases chunk
  rfl

/-- Typed acceptance after the supervisor has parsed its transcript and all
independent replay outputs.

No generated certificate is named.  The quantified certificate and every
chunk remain arbitrary; the two fixed numerators enter only at the final
result check. -/
def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    ∃ certificate : Recurrence.Certificate,
      certificate.check = true ∧
        certificate.signedNumerator = CDEMAbelSource.signedTarget ∧
        certificate.absoluteNumerator = CDEMAbelSource.absoluteTarget ∧
        ∀ chunk, chunk ∈ certificate.chunks →
          CDEMAbelReplayAlgorithm.Accepts
            (requestOfChunk chunk) (outputOfChunk chunk)

/-- A typed supervisor acceptance constructs the exact local evidence
required by the recurrence theorem. -/
theorem localEvidence_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : Accepts inputBytes resultBytes) :
    ∃ certificate : Recurrence.Certificate,
      certificate.check = true ∧
        Nonempty (Recurrence.LocalSourceScaleEvidence certificate) ∧
        certificate.signedNumerator = CDEMAbelSource.signedTarget ∧
        certificate.absoluteNumerator = CDEMAbelSource.absoluteTarget := by
  rcases accepted with
    ⟨_input, _result, certificate, hcheck, hsigned, habsolute,
      hreplays⟩
  refine ⟨certificate, hcheck, ⟨?__⟩, hsigned, habsolute⟩
  refine ⟨?_⟩
  intro chunk hmem
  have :=
    locallyRealizes_of_accepts (hreplays chunk hmem)
  simpa using this

/-- The pure operational supervisor-to-source theorem. -/
theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : Accepts inputBytes resultBytes) :
    CDEMAbelSource.SourceClaim := by
  rcases localEvidence_of_acceptance accepted with
    ⟨certificate, hcheck, ⟨evidence⟩, hsigned, habsolute⟩
  exact
    CDEMAbelRecurrenceCertificate.sourceClaim_of_checked_local_production_certificate
      hcheck evidence hsigned habsolute

end Supervisor

/-! ## Explicit remaining implementation boundary -/

/-- Identity of the three reviewed source files whose behavior must be
refined to the typed model above.  These strings are audit metadata, not
cryptographic theorems. -/
structure ReviewedSourceIdentity where
  producerSha256 : String
  replayerSha256 : String
  supervisorSha256 : String
  deriving Repr, DecidableEq

def reviewedSourceIdentity : ReviewedSourceIdentity where
  producerSha256 :=
    "188e4dc7f3a17ffe336827b11289a6b23cd81284479c39f462a019d33eee1195"
  replayerSha256 :=
    "00a9ef86c9fef26690b14f63af3c92f7ad9141cc3d7020d69fe4d631e7b56ad1"
  supervisorSha256 :=
    "014c5472b523d4cf40d1427caea8cdb8a4c429e2f4c5594f9f2dc61158d6bfdf"

/-- Abstract successful runs supplied later by a formal C/C++ source
semantics.  No run relation is instantiated in this file. -/
structure CxxSourceExecutionSemantics where
  semanticsId : String
  supervisorAccepts : ByteArray → ByteArray → Prop

/-- Exact source-level refinement obligation still required for the reviewed
supervisor, producer, and independent replayer.

An inhabitant must prove this implication from a formal semantics of the
reviewed C++ sources.  Merely pinning their hashes or observing a receipt is
not an inhabitant. -/
structure CxxSourceRefinesTypedSupervisor
    (source : CxxSourceExecutionSemantics) : Prop where
  successfulRun :
    ∀ {inputBytes resultBytes : ByteArray},
      source.supervisorAccepts inputBytes resultBytes →
        Supervisor.Accepts inputBytes resultBytes

/-- Named compiler/loader/x86 obligation.  `nativeAccepts` is expected to be
the formal execution relation of the exact static ELF, not an attestation
predicate. -/
structure CompilerX86RefinesCxxSource
    (source : CxxSourceExecutionSemantics)
    (nativeAccepts : ByteArray → ByteArray → Prop) : Prop where
  successfulRun :
    ∀ {inputBytes resultBytes : ByteArray},
      nativeAccepts inputBytes resultBytes →
        source.supervisorAccepts inputBytes resultBytes

/-- Composition of the two still-explicit implementation obligations with
the proved typed source theorem. -/
theorem sourceClaim_of_native_acceptance
    {source : CxxSourceExecutionSemantics}
    {nativeAccepts : ByteArray → ByteArray → Prop}
    (compilerX86 : CompilerX86RefinesCxxSource source nativeAccepts)
    (sourceRefinement : CxxSourceRefinesTypedSupervisor source)
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeAccepts inputBytes resultBytes) :
    CDEMAbelSource.SourceClaim :=
  Supervisor.sourceClaim_of_acceptance
    (sourceRefinement.successfulRun
      (compilerX86.successfulRun accepted))

end SparkInterval.TernaryGoldbach.CDEMAbelReplayAlgorithm
