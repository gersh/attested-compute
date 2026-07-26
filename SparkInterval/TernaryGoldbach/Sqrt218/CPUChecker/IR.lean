/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Fixed128
import TGComputeContracts.Sqrt218.Kernel

/-!
# Architecture-neutral IR for the Sqrt218 fixed-width CPU checker

This module is the review target for
`cpu_checker/sqrt218/sqrt218_cpu_checker.c`.  It models:

* the V2 fixed-width records after byte decoding;
* canonical checked section offsets;
* two-limb event arithmetic and the endpoint guard; and
* the exact proposition a measured native runner must satisfy.

It does **not** supply a V2 byte decoder, a C semantics, a compiler proof, an
x86-64 semantics, an ELF/loader theorem, or a hardware-conformance theorem.
In particular, `NativeRunnerRefines` has no inhabitant in this module.

Roster, prime-power completeness, and the 30-seed log-ladder checker remain
separate mandatory stages.  Consequently `runArithmetic` is intentionally
not named `acceptCertificate` and does not yield
`TGComputeContracts.Sqrt218.CertificateFacts`.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

/-! ## V2 record image -/

def headerBytes : Nat := 160
def primeRecordBytes : Nat := 80
def factorRefBytes : Nat := 8
def factorPairBytes : Nat := 16
def eventRecordBytes : Nat := 32
def powerRefBytes : Nat := 8

def formatVersion : Nat := 2
def logSeedAt : Nat := 30
def logScale : Nat := 281_474_976_710_656
def reciprocalScale : Nat := 1_073_741_824

structure Header where
  version : Nat
  flags : Nat
  bound : Nat
  reusedPrimeBound : Nat
  logSeedAt : Nat
  logScale : Nat
  reciprocalScale : Nat
  primeCount : Nat
  factorRefCount : Nat
  factorPairCount : Nat
  eventCount : Nat
  powerRefCount : Nat
  primesOffset : Nat
  factorRefsOffset : Nat
  factorPairsOffset : Nat
  eventsOffset : Nat
  powerRefsOffset : Nat
  archiveBytes : Nat
  deriving Repr, DecidableEq, Inhabited

structure PrimeRecord where
  prime : Nat
  witness : Nat
  factorRefIndex : Nat
  factorRefCount : Nat
  gapPairIndex : Nat
  gapPairCount : Nat
  powerRefIndex : Nat
  powerRefCount : Nat
  logLower : Nat
  logUpper : Nat
  deriving Repr, DecidableEq, Inhabited

structure FactorPair where
  left : Nat
  right : Nat
  deriving Repr, DecidableEq, Inhabited

structure EventRecord where
  value : Nat
  primeIndex : Nat
  exponent : Nat
  floorSqrt : Nat
  deriving Repr, DecidableEq, Inhabited

structure ArchiveImage where
  byteLength : Nat
  header : Header
  primes : List PrimeRecord
  factorRefs : List Nat
  factorPairs : List FactorPair
  events : List EventRecord
  powerRefs : List Nat
  deriving Repr, DecidableEq

def checkedWord (value : Nat) : Option Nat :=
  if value < limbBase then some value else none

def checkedWordAdd (left right : Nat) : Option Nat :=
  checkedWord (left + right)

def checkedWordMul (left right : Nat) : Option Nat :=
  checkedWord (left * right)

def sectionEnd (offset count width : Nat) : Option Nat := do
  let bytes ← checkedWordMul count width
  checkedWordAdd offset bytes

/-- Compute the only canonical end offset accepted by V2.

Every equality here is mirrored by `tg_sq218_view_open_v2`; hence no two
sections can overlap or alias when this succeeds. -/
def canonicalEnd (header : Header) : Option Nat := do
  if header.primesOffset = headerBytes then pure () else none
  let afterPrimes ←
    sectionEnd header.primesOffset header.primeCount primeRecordBytes
  if header.factorRefsOffset = afterPrimes then pure () else none
  let afterFactors ←
    sectionEnd header.factorRefsOffset header.factorRefCount factorRefBytes
  if header.factorPairsOffset = afterFactors then pure () else none
  let afterPairs ←
    sectionEnd
      header.factorPairsOffset header.factorPairCount factorPairBytes
  if header.eventsOffset = afterPairs then pure () else none
  let afterEvents ←
    sectionEnd header.eventsOffset header.eventCount eventRecordBytes
  if header.powerRefsOffset = afterEvents then pure () else none
  sectionEnd
    header.powerRefsOffset header.powerRefCount powerRefBytes

def headerCheck (image : ArchiveImage) : Bool :=
  decide (
    image.header.version = formatVersion ∧
      image.header.flags = 0 ∧
      2 ≤ image.header.bound ∧
      image.header.reusedPrimeBound ≤ image.header.bound ∧
      image.header.logSeedAt = logSeedAt ∧
      image.header.logScale = logScale ∧
      image.header.reciprocalScale = reciprocalScale ∧
      image.header.primeCount = image.primes.length ∧
      image.header.factorRefCount = image.factorRefs.length ∧
      image.header.factorPairCount = image.factorPairs.length ∧
      image.header.eventCount = image.events.length ∧
      image.header.powerRefCount = image.powerRefs.length ∧
      image.header.powerRefCount = image.header.eventCount ∧
      image.header.archiveBytes = image.byteLength ∧
      canonicalEnd image.header = some image.byteLength)

structure HeaderFacts (image : ArchiveImage) : Prop where
  version : image.header.version = formatVersion
  flags : image.header.flags = 0
  primeCount : image.header.primeCount = image.primes.length
  factorRefCount :
    image.header.factorRefCount = image.factorRefs.length
  factorPairCount :
    image.header.factorPairCount = image.factorPairs.length
  eventCount : image.header.eventCount = image.events.length
  powerRefCount :
    image.header.powerRefCount = image.powerRefs.length
  powerRefsMatchEvents :
    image.header.powerRefCount = image.header.eventCount
  archiveBytes : image.header.archiveBytes = image.byteLength
  canonical :
    canonicalEnd image.header = some image.byteLength

theorem headerCheck_sound {image : ArchiveImage}
    (hcheck : headerCheck image = true) :
    HeaderFacts image := by
  simp only [headerCheck, decide_eq_true_eq] at hcheck
  rcases hcheck with
    ⟨hversion, hflags, _hbound, _hreused, _hseed, _hlog,
      _hreciprocal, hprimes, hfactors, hpairs, hevents,
      hpowerRefs, hpowerEvents, hbytes, hcanonical⟩
  exact {
    version := hversion
    flags := hflags
    primeCount := hprimes
    factorRefCount := hfactors
    factorPairCount := hpairs
    eventCount := hevents
    powerRefCount := hpowerRefs
    powerRefsMatchEvents := hpowerEvents
    archiveBytes := hbytes
    canonical := hcanonical
  }

/-! ## Checked event arithmetic -/

inductive Reject where
  | malformed
  | outOfRange
  | overflow
  | arithmeticMismatch
  | strictGuardFailed
  deriving Repr, DecidableEq, Inhabited

private def fromOption {α : Type} (failure : Reject) :
    Option α → Except Reject α
  | none => .error failure
  | some value => .ok value

private def listAt {α : Type} [Inhabited α]
    (values : List α) (index : Nat) :
    Except Reject α :=
  if index < values.length then
    .ok (values.getD index default)
  else
    .error .outOfRange

def checkedPowWord (base : Nat) : Nat → Option Nat
  | 0 => checkedWord 1
  | exponent + 1 => do
      let previous ← checkedPowWord base exponent
      checkedWordMul previous base

structure ScanState where
  nextEvent : Nat
  lastEventValue : Nat
  weightedUpper : U128
  psiLower : U128
  deriving Repr, DecidableEq, Inhabited

def ScanState.initial : ScanState :=
  ⟨0, 0, U128.zero, U128.zero⟩

def ScanState.toFixedState (state : ScanState) :
    TGComputeContracts.Sqrt218.FixedState :=
  ⟨state.weightedUpper.toNat, state.psiLower.toNat⟩

/-- Checked fixed-width right-hand side shared by the event and endpoint
guards.  This is public so source-level C refinement modules can state their
correspondence to the exact IR computation. -/
def headRight (image : ArchiveImage) (root : Nat) :
    Except Reject U128 := do
  let start ← fromOption .overflow (U128.ofWord root)
  let withConstant ←
    fromOption .overflow (U128.mulWordChecked start 2501)
  let withLogScale ←
    fromOption .overflow
      (U128.mulWordChecked withConstant image.header.logScale)
  fromOption .overflow
    (U128.mulWordChecked
      withLogScale image.header.reciprocalScale)

/-- One architecture-neutral event transition.

The reciprocal formula is the package-neutral mathematical definition.
`Operational.ArithmeticRefinement` separately proves the external
quotient/remainder spelling equivalent. -/
def step (image : ArchiveImage) (state : ScanState) :
    Except Reject ScanState := do
  let event ← listAt image.events state.nextEvent
  let prime ← listAt image.primes event.primeIndex
  if event.value < limbBase ∧
      prime.prime < limbBase ∧
      event.exponent < limbBase ∧
      0 < event.exponent ∧
      event.value ≤ image.header.bound ∧
      event.floorSqrt = Nat.sqrt event.value ∧
      (state.nextEvent = 0 ∨ state.lastEventValue < event.value)
    then pure ()
    else throw .arithmeticMismatch
  let expectedPower ←
    fromOption .overflow (checkedPowWord prime.prime event.exponent)
  if expectedPower = event.value then pure ()
    else throw .arithmeticMismatch
  let upperReciprocal :=
    TGComputeContracts.Sqrt218.reciprocalUpper
      event.value event.floorSqrt
  let upperWord ← fromOption .overflow (checkedWord upperReciprocal)
  let upperLog ← fromOption .overflow (U128.ofWord prime.logUpper)
  let term ←
    fromOption .overflow (U128.mulWordChecked upperLog upperWord)
  let weighted ←
    fromOption .overflow
      (U128.addChecked state.weightedUpper term)
  let lowerLog ← fromOption .overflow (U128.ofWord prime.logLower)
  let psi ←
    fromOption .overflow (U128.addChecked state.psiLower lowerLog)
  let left ←
    fromOption .overflow (U128.mulWordChecked weighted 1250)
  let right ← headRight image event.floorSqrt
  if left.lessThan right then
    pure {
      nextEvent := state.nextEvent + 1
      lastEventValue := event.value
      weightedUpper := weighted
      psiLower := psi
    }
  else
    throw Reject.strictGuardFailed

def runLoop (image : ArchiveImage) : Nat → ScanState →
    Except Reject ScanState
  | 0, state =>
      if state.nextEvent = image.events.length then
        pure state
      else
        throw .outOfRange
  | fuel + 1, state =>
      if state.nextEvent = image.events.length then
        pure state
      else do
        let next ← step image state
        runLoop image fuel next

def runEvents (image : ArchiveImage) : Except Reject ScanState :=
  runLoop image image.events.length ScanState.initial

/-- Checked endpoint arithmetic.  This is public for source-level refinement;
ordinary consumers should use `anchorSlack_refines_anchorOK`. -/
def anchorSlack (image : ArchiveImage) (state : ScanState) :
    Except Reject U128 := do
  let root := Nat.sqrt image.header.bound
  let lowerReciprocal :=
    TGComputeContracts.Sqrt218.reciprocalLower
      image.header.bound root
  let lowerWord ← fromOption .overflow (checkedWord lowerReciprocal)
  let correction ←
    fromOption .overflow
      (U128.mulWordChecked state.psiLower lowerWord)
  let right ← headRight image root
  if correction.toNat ≤ state.weightedUpper.toNat then
    let difference ←
      fromOption .overflow
        (U128.subChecked state.weightedUpper correction)
    let left ←
      fromOption .overflow (U128.mulWordChecked difference 2500)
    if left.lessThan right then
      fromOption .overflow (U128.subChecked right left)
    else
      throw Reject.strictGuardFailed
  else
    let difference ←
      fromOption .overflow
        (U128.subChecked correction state.weightedUpper)
    let extra ←
      fromOption .overflow (U128.mulWordChecked difference 2500)
    fromOption .overflow (U128.addChecked right extra)

structure ArithmeticResult where
  state : ScanState
  anchorSlack : U128
  deriving Repr, DecidableEq

/-- The current fixed-width arithmetic stage.

This checks the canonical parsed header, all present event rows, both
accumulators, event head guards, and the endpoint guard.  It does not yet
assert roster/log/layout completeness. -/
def runArithmetic (image : ArchiveImage) :
    Except Reject ArithmeticResult := do
  if headerCheck image then pure () else throw .malformed
  let state ← runEvents image
  let slack ← anchorSlack image state
  pure ⟨state, slack⟩

/-! ## Exact future refinement boundary -/

def kernelPrimeAt (image : ArchiveImage) (index : Nat) : Nat :=
  (image.primes.getD index default).prime

def kernelLogLowerAt (image : ArchiveImage) (index : Nat) : Nat :=
  (image.primes.getD index default).logLower

def kernelLogUpperAt (image : ArchiveImage) (index : Nat) : Nat :=
  (image.primes.getD index default).logUpper

def kernelEventAt (image : ArchiveImage) (index : Nat) :
    TGComputeContracts.Sqrt218.PowerEvent :=
  let event := image.events.getD index default
  {
    value := event.value
    primeIndex := event.primeIndex
    exponent := event.exponent
    floorSqrt := event.floorSqrt
  }

private theorem listAt_ok {α : Type} [Inhabited α]
    {values : List α} {index : Nat} {value : α}
    (hget : listAt values index = .ok value) :
    index < values.length ∧ value = values.getD index default := by
  unfold listAt at hget
  split at hget
  next hindex =>
    simp only [Except.ok.injEq] at hget
    exact ⟨hindex, hget.symm⟩
  next =>
    contradiction

private theorem checkedWord_ok {input word : Nat}
    (hword : checkedWord input = some word) :
    input < limbBase ∧ word = input := by
  unfold checkedWord at hword
  split at hword
  next hinput =>
    simp only [Option.some.injEq] at hword
    exact ⟨hinput, hword.symm⟩
  next =>
    contradiction

private theorem exceptBind_ok {ε α β : Type}
    {first : Except ε α} {rest : α → Except ε β} {result : β}
    (hbind : first >>= rest = .ok result) :
    ∃ value, first = .ok value ∧ rest value = .ok result := by
  change Except.bind first rest = .ok result at hbind
  cases first <;> simp_all [Except.bind]

private theorem fromOption_ok {α : Type} {failure : Reject}
    {option : Option α} {value : α}
    (hoption : fromOption failure option = .ok value) :
    option = some value := by
  cases option <;> simp_all [fromOption]

private theorem headRight_ok {image : ArchiveImage} {root : Nat}
    {right : U128} (hright : headRight image root = .ok right) :
    right.toNat =
      root * 2501 * image.header.logScale *
        image.header.reciprocalScale := by
  unfold headRight at hright
  rcases exceptBind_ok hright with ⟨start, hstart, hright⟩
  have hstart' : U128.ofWord root = some start :=
    fromOption_ok hstart
  rcases exceptBind_ok hright with
    ⟨withConstant, hconstant, hright⟩
  have hconstant' :
      U128.mulWordChecked start 2501 = some withConstant :=
    fromOption_ok hconstant
  rcases exceptBind_ok hright with
    ⟨withLogScale, hlog, hright⟩
  have hlog' :
      U128.mulWordChecked withConstant image.header.logScale =
        some withLogScale :=
    fromOption_ok hlog
  have hreciprocal' :
      U128.mulWordChecked
          withLogScale image.header.reciprocalScale =
        some right :=
    fromOption_ok hright
  rw [(U128.mulWordChecked_sound hreciprocal').2.2,
    (U128.mulWordChecked_sound hlog').2.2,
    (U128.mulWordChecked_sound hconstant').2.2,
    (U128.ofWord_sound hstart').2.2]

/-- Successful endpoint-slack evaluation implies the generic exact anchor
guard.

The returned slack is operational evidence only; the theorem uses no
particular slack value.  In the branch where the correction is below the
weighted accumulator, native success exposes the strict comparison directly.
In the opposite branch the left side of `anchorOK` is negative while its
right side is nonnegative. -/
theorem anchorSlack_refines_anchorOK
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    (hheader : headerCheck image = true)
    (hslack : anchorSlack image state = .ok slack) :
    TGComputeContracts.Sqrt218.anchorOK
        image.header.bound
        state.weightedUpper.toNat
        state.psiLower.toNat = true := by
  simp only [headerCheck, decide_eq_true_eq] at hheader
  have hlogScale :
      image.header.logScale =
        TGComputeContracts.Sqrt218.scale := by
    calc
      image.header.logScale = logScale :=
        hheader.2.2.2.2.2.1
      _ = TGComputeContracts.Sqrt218.scale := rfl
  have hreciprocalScale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale := by
    calc
      image.header.reciprocalScale = reciprocalScale :=
        hheader.2.2.2.2.2.2.1
      _ = TGComputeContracts.Sqrt218.reciprocalScale := rfl
  unfold anchorSlack at hslack
  rcases exceptBind_ok hslack with
    ⟨lowerWord, hlowerWord, hslack⟩
  have hlowerWord' :
      checkedWord
          (TGComputeContracts.Sqrt218.reciprocalLower
            image.header.bound (Nat.sqrt image.header.bound)) =
        some lowerWord :=
    fromOption_ok hlowerWord
  rcases exceptBind_ok hslack with
    ⟨correction, hcorrection, hslack⟩
  have hcorrection' :
      U128.mulWordChecked state.psiLower lowerWord =
        some correction :=
    fromOption_ok hcorrection
  rcases exceptBind_ok hslack with ⟨right, hright, hslack⟩
  have hrightNat :=
    headRight_ok (image := image)
      (root := Nat.sqrt image.header.bound) hright
  have hlowerNat :
      lowerWord =
        TGComputeContracts.Sqrt218.reciprocalLower
          image.header.bound (Nat.sqrt image.header.bound) :=
    (checkedWord_ok hlowerWord').2
  have hcorrectionNat :
      correction.toNat =
        state.psiLower.toNat *
          TGComputeContracts.Sqrt218.reciprocalLower
            image.header.bound (Nat.sqrt image.header.bound) := by
    rw [(U128.mulWordChecked_sound hcorrection').2.2, hlowerNat]
  by_cases hbelow :
      correction.toNat ≤ state.weightedUpper.toNat
  · simp only [if_pos hbelow] at hslack
    rcases exceptBind_ok hslack with
      ⟨difference, hdifference, hslack⟩
    have hdifference' :
        U128.subChecked state.weightedUpper correction =
          some difference :=
      fromOption_ok hdifference
    rcases exceptBind_ok hslack with ⟨left, hleft, hslack⟩
    have hleft' :
        U128.mulWordChecked difference 2500 = some left :=
      fromOption_ok hleft
    by_cases hstrict : left.lessThan right = true
    · simp only [if_pos hstrict] at hslack
      have hdifferenceNat :=
        (U128.subChecked_sound hdifference').2.2
      have hleftNat :=
        (U128.mulWordChecked_sound hleft').2.2
      have hstrictNat : left.toNat < right.toNat :=
        U128.lessThan_eq_true.mp hstrict
      have hanchorNat :
          2500 *
              (state.weightedUpper.toNat -
                state.psiLower.toNat *
                  TGComputeContracts.Sqrt218.reciprocalLower
                    image.header.bound
                    (Nat.sqrt image.header.bound)) <
            2501 * Nat.sqrt image.header.bound *
              TGComputeContracts.Sqrt218.scale *
              TGComputeContracts.Sqrt218.reciprocalScale := by
        rw [← hcorrectionNat, ← hdifferenceNat, Nat.mul_comm]
        rw [← hlogScale, ← hreciprocalScale]
        simpa only [Nat.mul_assoc, Nat.mul_comm, Nat.mul_left_comm,
          hleftNat, hrightNat] using hstrictNat
      unfold TGComputeContracts.Sqrt218.anchorOK
      simp only [decide_eq_true_eq]
      have hbelow' :
          state.psiLower.toNat *
                TGComputeContracts.Sqrt218.reciprocalLower
                  image.header.bound (Nat.sqrt image.header.bound) ≤
              state.weightedUpper.toNat := by
        rwa [← hcorrectionNat]
      have hanchorInt :
          ((2500 *
              (state.weightedUpper.toNat -
                state.psiLower.toNat *
                  TGComputeContracts.Sqrt218.reciprocalLower
                    image.header.bound
                    (Nat.sqrt image.header.bound)) : Nat) : Int) <
            ((2501 * Nat.sqrt image.header.bound *
              TGComputeContracts.Sqrt218.scale *
              TGComputeContracts.Sqrt218.reciprocalScale : Nat) : Int) :=
        Int.ofNat_lt.2 hanchorNat
      push_cast at hanchorInt
      rw [Int.ofNat_sub hbelow'] at hanchorInt
      exact hanchorInt
    · simp only [if_neg hstrict] at hslack
      cases hslack
  · simp only [if_neg hbelow] at hslack
    have habove :
        state.weightedUpper.toNat <
          state.psiLower.toNat *
            TGComputeContracts.Sqrt218.reciprocalLower
              image.header.bound (Nat.sqrt image.header.bound) := by
      rw [← hcorrectionNat]
      omega
    unfold TGComputeContracts.Sqrt218.anchorOK
    simp only [decide_eq_true_eq]
    have hnegative :
        (state.weightedUpper.toNat : Int) -
            ((state.psiLower.toNat *
                TGComputeContracts.Sqrt218.reciprocalLower
                  image.header.bound
                  (Nat.sqrt image.header.bound) : Nat) : Int) <
          0 := by
      have haboveInt :
          (state.weightedUpper.toNat : Int) <
            ((state.psiLower.toNat *
                TGComputeContracts.Sqrt218.reciprocalLower
                  image.header.bound
                  (Nat.sqrt image.header.bound) : Nat) : Int) :=
        Int.ofNat_lt.2 habove
      omega
    have hrightNonnegative :
        (0 : Int) ≤
          (2501 : Int) * (Nat.sqrt image.header.bound : Int) *
            (TGComputeContracts.Sqrt218.scale : Int) *
            (TGComputeContracts.Sqrt218.reciprocalScale : Int) := by
      positivity
    nlinarith

/-- The endpoint component of every successful arithmetic run satisfies the
generic kernel's exact anchor guard.  This theorem is symbolic in `image`; it
does not reduce any closed archive. -/
theorem runArithmetic_anchorOK
    {image : ArchiveImage} {result : ArithmeticResult}
    (hrun : runArithmetic image = .ok result) :
    TGComputeContracts.Sqrt218.anchorOK
        image.header.bound
        result.state.weightedUpper.toNat
        result.state.psiLower.toNat = true := by
  unfold runArithmetic at hrun
  by_cases hheader : headerCheck image = true
  · simp only [hheader] at hrun
    rcases exceptBind_ok hrun with ⟨state, _hevents, hrun⟩
    rcases exceptBind_ok hrun with ⟨slack, hslack, hresult⟩
    change Except.ok ⟨state, slack⟩ = Except.ok result at hresult
    have hresult' : ArithmeticResult.mk state slack = result :=
      Except.ok.inj hresult
    cases hresult'
    exact anchorSlack_refines_anchorOK hheader hslack
  · have hheaderFalse : headerCheck image = false :=
      Bool.eq_false_of_not_eq_true hheader
    simp only [hheaderFalse] at hrun
    contradiction

private theorem weightedTermUpper_eq_mul
    (logUpper n floorSqrt : Nat) :
    TGComputeContracts.Sqrt218.weightedTermUpper
        logUpper n floorSqrt =
      logUpper *
        TGComputeContracts.Sqrt218.reciprocalUpper n floorSqrt := by
  by_cases hzero : logUpper = 0
  · simp [TGComputeContracts.Sqrt218.weightedTermUpper, hzero]
  · simp [TGComputeContracts.Sqrt218.weightedTermUpper, hzero]

/-- Exact data-independent refinement obligation for one event step.

The header premise is essential.  `step` deliberately consumes the scale
words decoded from the image, while `fixedEventStep` uses the fixed kernel
constants.  Without `headerCheck image = true`, inflating both decoded scales
can make the fixed-width head guard succeed when the kernel guard fails. -/
def StepRefinesKernel : Prop :=
  ∀ image state next,
    headerCheck image = true →
    step image state = .ok next →
      TGComputeContracts.Sqrt218.fixedEventStep
          (kernelEventAt image)
          (kernelLogLowerAt image)
          (kernelLogUpperAt image)
          state.nextEvent state.toFixedState =
        some next.toFixedState

theorem stepRefinesKernel : StepRefinesKernel := by
  intro image state next hheader hstep
  simp only [headerCheck, decide_eq_true_eq] at hheader
  have hlogScale :
      image.header.logScale =
        TGComputeContracts.Sqrt218.scale := by
    calc
      image.header.logScale = logScale :=
        hheader.2.2.2.2.2.1
      _ = TGComputeContracts.Sqrt218.scale := rfl
  have hreciprocalScale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale := by
    calc
      image.header.reciprocalScale = reciprocalScale :=
        hheader.2.2.2.2.2.2.1
      _ = TGComputeContracts.Sqrt218.reciprocalScale := rfl
  unfold step at hstep
  rcases exceptBind_ok hstep with ⟨event, hevent, hstep⟩
  rcases exceptBind_ok hstep with ⟨prime, hprime, hstep⟩
  by_cases hguard :
      event.value < limbBase ∧
        prime.prime < limbBase ∧
        event.exponent < limbBase ∧
        0 < event.exponent ∧
        event.value ≤ image.header.bound ∧
        event.floorSqrt = Nat.sqrt event.value ∧
        (state.nextEvent = 0 ∨
          state.lastEventValue < event.value)
  · simp only [if_pos hguard] at hstep
    rcases exceptBind_ok hstep with
      ⟨expectedPower, hpower, hstep⟩
    have hpower' :
        checkedPowWord prime.prime event.exponent =
          some expectedPower :=
      fromOption_ok hpower
    by_cases hpowerValue : expectedPower = event.value
    · simp only [if_pos hpowerValue] at hstep
      rcases exceptBind_ok hstep with
        ⟨upperWord, hupperWord, hstep⟩
      have hupperWord' :
          checkedWord
              (TGComputeContracts.Sqrt218.reciprocalUpper
                event.value event.floorSqrt) =
            some upperWord :=
        fromOption_ok hupperWord
      rcases exceptBind_ok hstep with
        ⟨upperLog, hupperLog, hstep⟩
      have hupperLog' :
          U128.ofWord prime.logUpper = some upperLog :=
        fromOption_ok hupperLog
      rcases exceptBind_ok hstep with ⟨term, hterm, hstep⟩
      have hterm' :
          U128.mulWordChecked upperLog upperWord = some term :=
        fromOption_ok hterm
      rcases exceptBind_ok hstep with
        ⟨weighted, hweighted, hstep⟩
      have hweighted' :
          U128.addChecked state.weightedUpper term = some weighted :=
        fromOption_ok hweighted
      rcases exceptBind_ok hstep with
        ⟨lowerLog, hlowerLog, hstep⟩
      have hlowerLog' :
          U128.ofWord prime.logLower = some lowerLog :=
        fromOption_ok hlowerLog
      rcases exceptBind_ok hstep with ⟨psi, hpsi, hstep⟩
      have hpsi' :
          U128.addChecked state.psiLower lowerLog = some psi :=
        fromOption_ok hpsi
      rcases exceptBind_ok hstep with ⟨left, hleft, hstep⟩
      have hleft' :
          U128.mulWordChecked weighted 1250 = some left :=
        fromOption_ok hleft
      rcases exceptBind_ok hstep with ⟨right, hright, hstep⟩
      by_cases hhead : left.lessThan right = true
      · simp only [if_pos hhead] at hstep
        cases hstep
        have heventGet := (listAt_ok hevent).2
        have hprimeGet := (listAt_ok hprime).2
        have hupperWordNat := (checkedWord_ok hupperWord').2
        have hupperLogNat :=
          (U128.ofWord_sound hupperLog').2.2
        have htermNat :=
          (U128.mulWordChecked_sound hterm').2.2
        have hweightedNat :=
          (U128.addChecked_sound hweighted').2
        have hlowerLogNat :=
          (U128.ofWord_sound hlowerLog').2.2
        have hpsiNat :=
          (U128.addChecked_sound hpsi').2
        have hleftNat :=
          (U128.mulWordChecked_sound hleft').2.2
        have hrightNat := headRight_ok hright
        have hheadNat : left.toNat < right.toNat :=
          U128.lessThan_eq_true.mp hhead
        have hkernelHead :
            TGComputeContracts.Sqrt218.headOK
                event.value event.floorSqrt weighted.toNat =
              true := by
          simp only [TGComputeContracts.Sqrt218.headOK,
            decide_eq_true_eq]
          rw [← hlogScale, ← hreciprocalScale,
            Nat.mul_comm 1250 weighted.toNat,
            Nat.mul_comm 2501 event.floorSqrt,
            ← hleftNat, ← hrightNat]
          exact hheadNat
        simp only [TGComputeContracts.Sqrt218.fixedEventStep,
          kernelEventAt, kernelLogLowerAt, kernelLogUpperAt,
          ScanState.toFixedState]
        rw [← heventGet, ← hprimeGet,
          weightedTermUpper_eq_mul,
          ← hupperWordNat, ← hupperLogNat, ← htermNat,
          ← hweightedNat, ← hlowerLogNat, ← hpsiNat,
          hkernelHead]
        simp
      · simp only [if_neg hhead] at hstep
        change Except.error Reject.strictGuardFailed =
          .ok next at hstep
        cases hstep
    · simp only [if_neg hpowerValue] at hstep
      change Except.error Reject.arithmeticMismatch =
        .ok next at hstep
      cases hstep
  · simp only [if_neg hguard] at hstep
    change Except.error Reject.arithmeticMismatch =
      .ok next at hstep
    cases hstep

inductive NativeOutcome where
  | rejected (reason : Reject)
  | accepted (result : ArithmeticResult)
  deriving Repr, DecidableEq

def referenceOutcome
    (decode : ByteArray → Except Reject ArchiveImage)
    (bytes : ByteArray) : NativeOutcome :=
  match decode bytes with
  | .error reason => .rejected reason
  | .ok image =>
      match runArithmetic image with
      | .error reason => .rejected reason
      | .ok result => .accepted result

/-- Exact source-to-native refinement obligation.

`nativeRun` must denote execution of the measured binary, including its
actual input bytes and output convention.  Merely hashing, signing, or
attesting that binary does not construct this proof. -/
def NativeRunnerRefines
    (decode : ByteArray → Except Reject ArchiveImage)
    (nativeRun : ByteArray → NativeOutcome) : Prop :=
  ∀ bytes, nativeRun bytes = referenceOutcome decode bytes

theorem accepted_native_run_is_reference
    {decode : ByteArray → Except Reject ArchiveImage}
    {nativeRun : ByteArray → NativeOutcome}
    (hrefines : NativeRunnerRefines decode nativeRun)
    {bytes : ByteArray} {result : ArithmeticResult}
    (haccepted : nativeRun bytes = .accepted result) :
    referenceOutcome decode bytes = .accepted result := by
  rw [← hrefines bytes]
  exact haccepted

/-- Mathematical closure still required around the arithmetic IR.

This pins the exact generic facts a completed V2 checker must produce.  The
current arithmetic stage does not construct this proposition. -/
def SuppliesCertificateFacts
    (image : ArchiveImage) (result : ArithmeticResult) : Prop :=
  @TGComputeContracts.Sqrt218.CertificateFacts
    image.primes.length
    (kernelPrimeAt image)
    image.events.length
    (kernelEventAt image)
    (kernelLogLowerAt image)
    (kernelLogUpperAt image)
    result.state.toFixedState

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
