/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness

/-!
# Fail-closed guarded machine for the fused Möbius event stream

The CUDA CAS loop poisons a row when a packed-field guard fails.  A poison is
absorbing, and the native finalizer emits `2`, outside the Möbius codomain.
This file models that control flow independently of CUDA scheduling.

The key theorem does not assume every arithmetic guard in advance.  It says
that if a completed row is not poisoned, then every successful guarded step
is exactly the corresponding mathematical distinct-prime update.  Combined
with event-order commutativity, the residue-235 seed theorem, and a checked
complete prime roster, its output is Mathlib's Möbius function.

The remaining refinement is deliberately concrete: show that the packed
UInt64 CAS implementation realizes `step`, that its event stream is the
selected roster stream, and that the copied poison count is zero.  No native
execution or compiler theorem is asserted here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusGuardedMachine

open SparkInterval.TernaryGoldbach.MobiusFusedFinalization
open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235

/-- Guard values mirrored by the native CAS loop before one distinct-prime
event is committed. -/
def StepAdmissible (support : Support) (prime : Nat) : Prop :=
  0 < support.product ∧
    support.distinctCount < 13 ∧
    2 ≤ prime ∧
    support.product * prime < productRadix

instance (support : Support) (prime : Nat) :
    Decidable (StepAdmissible support prime) := by
  unfold StepAdmissible
  infer_instance

/-- Abstract decoded state of one packed row. -/
inductive State where
  | valid (support : Support)
  | poison
  deriving DecidableEq

/-- Mathematical update carried by one native divisor event. -/
def mathematicalStep
    (number : Nat) (support : Support) (prime : Nat) : Support :=
  update support prime (decide (prime * prime ∣ number))

/-- Fail-closed guarded event transition. -/
def step (number : Nat) : State → Nat → State
  | .poison, _ => .poison
  | .valid support, prime =>
      if StepAdmissible support prime then
        .valid (mathematicalStep number support prime)
      else
        .poison

/-- Ordered event fold from an arbitrary decoded starting state. -/
def foldEvents (number : Nat) : List Nat → State → State
  | [], state => state
  | prime :: rest, state =>
      foldEvents number rest (step number state prime)

@[simp] theorem foldEvents_poison
    (number : Nat) (events : List Nat) :
    foldEvents number events .poison = .poison := by
  induction events with
  | nil => rfl
  | cons prime rest inductionHypothesis =>
      simpa [foldEvents, step] using inductionHypothesis

/-- Every guarded fold either poisons or is exactly the unguarded
mathematical event fold. -/
theorem foldEvents_eq_poison_or_valid
    (number : Nat) (events : List Nat) (support : Support) :
    foldEvents number events (.valid support) = .poison ∨
      foldEvents number events (.valid support) =
        .valid
          (events.foldl (mathematicalStep number) support) := by
  induction events generalizing support with
  | nil =>
      exact Or.inr rfl
  | cons prime rest inductionHypothesis =>
      by_cases admissible : StepAdmissible support prime
      · simpa [foldEvents, step, admissible,
          List.foldl_cons] using
          inductionHypothesis
            (mathematicalStep number support prime)
      · exact Or.inl (by
          simp [foldEvents, step, admissible])

/-- Absence of the poison sentinel therefore identifies the exact support
without separately trusting each guard decision. -/
theorem foldEvents_eq_valid_of_ne_poison
    (number : Nat) (events : List Nat) (support : Support)
    (notPoison :
      foldEvents number events (.valid support) ≠ .poison) :
    foldEvents number events (.valid support) =
      .valid
        (events.foldl (mathematicalStep number) support) := by
  rcases foldEvents_eq_poison_or_valid number events support with
    poisoned | exact
  · exact (notPoison poisoned).elim
  · exact exact

/-- Filtering the roster to actual divisor events and applying the
unconditional mathematical step is exactly the ordinary conditional roster
fold. -/
theorem selectedDivisors_foldl_mathematicalStep
    (number : Nat) (primes : List Nat) (support : Support) :
    (selectedDivisors number primes).foldl
        (mathematicalStep number) support =
      primes.foldl (applyPrime number) support := by
  induction primes generalizing support with
  | nil =>
      rfl
  | cons prime rest inductionHypothesis =>
      by_cases divides : prime ∣ number
      · simp [selectedDivisors, mathematicalStep, applyPrime,
          divides]
        simpa only [selectedDivisors] using
          inductionHypothesis
            (update support prime
              (decide (prime * prime ∣ number)))
      · simp [selectedDivisors, applyPrime, divides]
        simpa only [selectedDivisors] using
          inductionHypothesis support

/-- Guarded run over precisely the divisor events selected from a roster. -/
def runSelectedFrom
    (number : Nat) (primes : List Nat) (support : Support) : State :=
  foldEvents number (selectedDivisors number primes) (.valid support)

/-- A nonpoison selected-event run is exactly the conditional roster fold. -/
theorem runSelectedFrom_eq_valid_of_ne_poison
    (number : Nat) (primes : List Nat) (support : Support)
    (notPoison :
      runSelectedFrom number primes support ≠ .poison) :
    runSelectedFrom number primes support =
      .valid (primes.foldl (applyPrime number) support) := by
  rw [runSelectedFrom,
    foldEvents_eq_valid_of_ne_poison _ _ _ notPoison,
    selectedDivisors_foldl_mathematicalStep]

/-- Production event run after the exact modulo-900 seed. -/
def runResidueSeeded
    (number : Nat) (suffix : List Nat) : State :=
  runSelectedFrom number suffix (residueSeed number)

/-- Any nonpoison residue-seeded serialization realizes the same support as
the complete `[2,3,5] ++ suffix` mathematical fold. -/
theorem runResidueSeeded_eq_foldSupport_of_ne_poison
    (number : Nat) (suffix : List Nat)
    (notPoison :
      runResidueSeeded number suffix ≠ .poison) :
    runResidueSeeded number suffix =
      .valid (foldSupport number (seedPrimes ++ suffix)) := by
  rw [runResidueSeeded,
    runSelectedFrom_eq_valid_of_ne_poison
      number suffix (residueSeed number) notPoison]
  exact congrArg State.valid
    (fold_prefix_suffix_eq_residueSeed number suffix).symm

/-- Native output convention: poison maps to the impossible sentinel `2`;
valid support uses the ordinary Möbius finalizer. -/
def output (number : Nat) : State → Int
  | .poison => 2
  | .valid support => finalize number support

/-- End-to-end fail-closed abstract machine theorem.

A complete checked roster and a zero poison count suffice; the receipt need
not assert products, factor counts, residual primality, or squarefreeness
row-by-row. -/
theorem output_runResidueSeeded_eq_moebius
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number (seedPrimes ++ suffix))
    (notPoison :
      runResidueSeeded number suffix ≠ .poison) :
    output number (runResidueSeeded number suffix) =
      ArithmeticFunction.moebius number := by
  rw [runResidueSeeded_eq_foldSupport_of_ne_poison
    number suffix notPoison]
  exact roster.finalize_foldSupport_eq_moebius

#print axioms foldEvents_poison
#print axioms foldEvents_eq_poison_or_valid
#print axioms foldEvents_eq_valid_of_ne_poison
#print axioms selectedDivisors_foldl_mathematicalStep
#print axioms runSelectedFrom_eq_valid_of_ne_poison
#print axioms runResidueSeeded_eq_foldSupport_of_ne_poison
#print axioms output_runResidueSeeded_eq_moebius

end SparkInterval.TernaryGoldbach.MobiusGuardedMachine
