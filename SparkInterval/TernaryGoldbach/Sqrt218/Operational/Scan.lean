/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Archive
import TGComputeContracts.Sqrt218.Kernel

/-!
# Exact streaming scan IR for the typed Sqrt218 archive

This evaluator mirrors `_replay_scan` in
`tg_verifier/sqrt218_certificate_verifier.py`: it visits every integer from
two through the selected bound, consumes at most one ordered prime-power
event, checks the strict integer head guard, records the minimum slack, checks
the endpoint Abel guard, and constructs the exact three transcript digests.

There are no production rows here.  `scanCheck_sound` is a generic theorem
about any typed archive and does not evaluate the production bound.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational

namespace StreamingScan

structure State where
  nextValue : Nat
  nextEvent : Nat
  weightedUpper : Nat
  psiLower : Nat
  minimumHeadSlack : Option Nat
  minimumHeadIndex : Nat
  eventTranscript : String
  deriving Repr, DecidableEq

def initial : State := {
  nextValue := 2
  nextEvent := 0
  weightedUpper := 0
  psiLower := 0
  minimumHeadSlack := none
  minimumHeadIndex := 0
  eventTranscript := ""
}

private def eventLine
    (value primeIndex exponent logLower logUpper weighted psi : Nat) :
    String :=
  "event:" ++ toString value ++ ":" ++ toString primeIndex ++ ":" ++
    toString exponent ++ ":" ++ toString logLower ++ ":" ++
    toString logUpper ++ ":" ++ toString weighted ++ ":" ++
    toString psi ++ "\n"

private def consumeEvent
    (archive : Archive) (state : State) : Option State :=
  if state.nextEvent < archive.events.length then
    let event := archive.events.getD state.nextEvent default
    if event.power < state.nextValue then
      none
    else if state.nextValue < event.power then
      some state
    else
      let prime := archive.primes.getD event.primeIndex default
      let root := Nat.sqrt event.power
      let weighted :=
        state.weightedUpper +
          prime.logUpper *
            TGComputeContracts.Sqrt218.reciprocalUpper event.power root
      let psi := state.psiLower + prime.logLower
      some {
        state with
        nextEvent := state.nextEvent + 1
        weightedUpper := weighted
        psiLower := psi
        eventTranscript :=
          state.eventTranscript ++
            eventLine event.power event.primeIndex event.exponent
              prime.logLower prime.logUpper weighted psi
      }
  else
    some state

private def recordHeadGuard (state : State) : Option State :=
  let right :=
    2501 * Nat.sqrt state.nextValue *
      TGComputeContracts.Sqrt218.scale *
      TGComputeContracts.Sqrt218.reciprocalScale
  let left := 1250 * state.weightedUpper
  if left < right then
    let slack := right - left
    let improved :=
      match state.minimumHeadSlack with
      | none => true
      | some previous => slack < previous
    some {
      state with
      nextValue := state.nextValue + 1
      minimumHeadSlack :=
        if improved then some slack else state.minimumHeadSlack
      minimumHeadIndex :=
        if improved then state.nextValue else state.minimumHeadIndex
    }
  else
    none

/-- One integer-prefix transition of the architecture-neutral scan. -/
def step (archive : Archive) (state : State) : Option State := do
  let afterEvent ← consumeEvent archive state
  recordHeadGuard afterEvent

/-- Fuel-bounded scan.  `archive.bound` units are sufficient for the exact
inclusive range `2, ..., archive.bound`; extra fuel is never interpreted as
extra mathematical work. -/
def loop (archive : Archive) : Nat → State → Option State
  | 0, state =>
      if archive.bound < state.nextValue then some state else none
  | fuel + 1, state =>
      if archive.bound < state.nextValue then
        some state
      else
        match step archive state with
        | none => none
        | some next => loop archive fuel next

private def anchorSlack (archive : Archive) (state : State) : Int :=
  let root := Nat.sqrt archive.bound
  let reciprocalLower :=
    TGComputeContracts.Sqrt218.reciprocalLower archive.bound root
  (2501 : Int) * root * TGComputeContracts.Sqrt218.scale *
      TGComputeContracts.Sqrt218.reciprocalScale -
    (2500 : Int) *
      ((state.weightedUpper : Int) -
        (state.psiLower * reciprocalLower : Nat))

private def finalLine
    (archive : Archive) (state : State)
    (minimumSlack minimumIndex anchor : Nat) : String :=
  "final:" ++ toString archive.bound ++ ":" ++
    toString state.weightedUpper ++ ":" ++ toString state.psiLower ++ ":" ++
    toString minimumSlack ++ ":" ++ toString minimumIndex ++ ":" ++
    toString anchor ++ "\n"

private def reusedPrimeCount
    (profile : Profile) (archive : Archive) : Nat :=
  (archive.primes.filter fun row =>
    decide (row.prime ≤ min archive.bound profile.reusedPrimeBound)).length

private def tailPrimeCount
    (profile : Profile) (archive : Archive) : Nat :=
  (archive.primes.filter fun row =>
    decide (
      profile.reusedPrimeBound < row.prime ∧
        row.prime ≤ archive.bound)).length

private def finish
    (profile : Profile) (archive : Archive) (state : State) :
    Option Summary := do
  if state.nextValue ≠ archive.bound + 1 then none else pure ()
  if state.nextEvent ≠ archive.events.length then none else pure ()
  let minimumSlack ← state.minimumHeadSlack
  let anchor := anchorSlack archive state
  if anchor ≤ 0 then none else pure ()
  let anchorNat := anchor.toNat
  let fixedTranscript :=
    state.eventTranscript ++
      finalLine archive state minimumSlack
        state.minimumHeadIndex anchorNat
  pure {
    anchorSlack := anchorNat
    finalPsiLower := state.psiLower
    finalWeightedUpper := state.weightedUpper
    fixedScanDigest :=
      SparkInterval.Certificate.SHA256.digestString fixedTranscript
    layoutDigest :=
      SparkInterval.Certificate.SHA256.digestString archive.layoutTranscript
    minimumHeadIndex := state.minimumHeadIndex
    minimumHeadSlack := minimumSlack
    primePowerEventCount := archive.events.length
    prattDigest :=
      SparkInterval.Certificate.SHA256.digestString archive.prattTranscript
    primeCount := archive.primes.length
    properPrimePowerEventCount :=
      archive.events.length - archive.primes.length
    reusedPrimeCount := reusedPrimeCount profile archive
    tailPrimeCount := tailPrimeCount profile archive
  }

/-- Full typed replay and exact summary reconstruction. -/
def scan (profile : Profile) (archive : Archive) : Option Summary := do
  let terminal ← loop archive archive.bound initial
  finish profile archive terminal

/-- Exact acceptance equation for the full typed streaming replay. -/
def scanCheck (profile : Profile) (archive : Archive) : Bool :=
  decide (scan profile archive = some archive.summary)

structure ScanFacts (profile : Profile) (archive : Archive) : Prop where
  replayed : scan profile archive = some archive.summary

theorem scanCheck_sound {profile : Profile} {archive : Archive}
    (hcheck : scanCheck profile archive = true) :
    ScanFacts profile archive := by
  exact ⟨of_decide_eq_true hcheck⟩

end StreamingScan

end SparkInterval.TernaryGoldbach.Sqrt218Operational
