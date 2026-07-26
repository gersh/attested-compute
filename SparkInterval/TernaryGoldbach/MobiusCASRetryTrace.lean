/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety

/-!
# Abstract CAS-retry trace for the packed Möbius product/count phase

The CUDA loop may lose `atomicCAS` races and retry from a newer predecessor
word.  A lost attempt does not modify memory; a winning attempt commits the
already-certified `cudaDistinctWordStep`.  This file records that control
flow explicitly and proves:

* failed attempts are stuttering steps;
* the complete trace refines exactly the list of committed events;
* every intermediate/final represented word remains below `2^64`; and
* if the committed events are a permutation of the authenticated roster and
  the final word is nonpoison, the result is the schedule-independent
  mathematical distinct-factor pass.

The remaining native boundary is intentionally small: CUDA `atomicCAS` must
linearize each winning update, and the list of winners must contain every
launched roster event exactly once.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusCASRetryTrace

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety
open SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

/-- One abstract invocation of native `atomicCAS`.

`committed = false` represents a lost race and therefore a memory stutter.
The next attempt for that CUDA thread is represented by a later list entry.
-/
structure CASAttempt where
  event : SplitEvent
  committed : Bool
deriving DecidableEq, Repr

/-- Roster of linearization winners, in atomic commit order. -/
def committedEvents : List CASAttempt → List SplitEvent
  | [] => []
  | attempt :: attempts =>
      if attempt.committed then
        attempt.event :: committedEvents attempts
      else
        committedEvents attempts

/-- Exact pure packed-word effect of one atomic attempt. -/
def cudaAttemptStep (word : Nat) (attempt : CASAttempt) : Nat :=
  if attempt.committed then
    cudaDistinctWordStep word attempt.event.prime
  else
    word

/-- Corresponding abstract valid/poison transition. -/
def stateAttemptStep (state : State) (attempt : CASAttempt) : State :=
  if attempt.committed then
    distinctStateStep state attempt.event.prime
  else
    state

def cudaAttemptRun : Nat → List CASAttempt → Nat
  | word, [] => word
  | word, attempt :: attempts =>
      cudaAttemptRun (cudaAttemptStep word attempt) attempts

def stateAttemptRun : State → List CASAttempt → State
  | state, [] => state
  | state, attempt :: attempts =>
      stateAttemptRun (stateAttemptStep state attempt) attempts

/-- Erasing lost attempts leaves precisely the ordinary committed-event
state fold. -/
theorem stateAttemptRun_eq_distinctStateRun
    (state : State) (attempts : List CASAttempt) :
    stateAttemptRun state attempts =
      distinctStateRun state (committedEvents attempts) := by
  induction attempts generalizing state with
  | nil =>
      rfl
  | cons attempt attempts inductionHypothesis =>
      cases committed : attempt.committed <;>
        simp [stateAttemptRun, stateAttemptStep,
          committedEvents, committed, distinctStateRun,
          inductionHypothesis]

/-- Every lost race stutters and every winner preserves the exact packed
representation relation. -/
theorem cudaAttemptRun_splitRepresents
    (attempts : List CASAttempt) {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    SplitRepresents
      (cudaAttemptRun word attempts)
      (stateAttemptRun state attempts) := by
  induction attempts generalizing word state with
  | nil =>
      simpa [cudaAttemptRun, stateAttemptRun] using represents
  | cons attempt attempts inductionHypothesis =>
      cases committed : attempt.committed
      · simp only [cudaAttemptRun, cudaAttemptStep,
          stateAttemptRun, stateAttemptStep, committed]
        exact inductionHypothesis represents
      · simp only [cudaAttemptRun, cudaAttemptStep,
          stateAttemptRun, stateAttemptStep, committed, if_true]
        exact inductionHypothesis
          (cudaDistinctWordStep_splitRepresents
            attempt.event.prime represents)

/-- Every word represented by the valid/poison packed invariant fits exactly
in one native unsigned 64-bit word. -/
theorem word_lt_uint64Radix_of_splitRepresents
    {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    word < uint64Radix := by
  cases represents with
  | valid support productFits countFits =>
      exact encodeSupport_lt_uint64Radix productFits countFits
  | poison support productFits countFits =>
      exact poisonedEncodeSupport_lt_uint64Radix
        productFits countFits

theorem cudaAttemptRun_lt_uint64Radix
    (attempts : List CASAttempt) {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    cudaAttemptRun word attempts < uint64Radix :=
  word_lt_uint64Radix_of_splitRepresents
    (cudaAttemptRun_splitRepresents attempts represents)

/-- A nonpoison trace is exactly the mathematical product/count fold over its
linearization winners. -/
theorem decode_cudaAttemptRun_eq_valid_committed
    {support : Support} (attempts : List CASAttempt)
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix)
    (notPoison :
      decodeWord
          (cudaAttemptRun (encodeSupport support) attempts) ≠
        .poison) :
    decodeWord
        (cudaAttemptRun (encodeSupport support) attempts) =
      .valid
        (distinctRun support (committedEvents attempts)) := by
  have represents :=
    cudaAttemptRun_splitRepresents attempts
      (SplitRepresents.valid support productFits countFits)
  have decoded :
      decodeWord
          (cudaAttemptRun (encodeSupport support) attempts) =
        stateAttemptRun (.valid support) attempts :=
    decodeWord_of_splitRepresents represents
  rw [stateAttemptRun_eq_distinctStateRun] at decoded
  rw [decoded] at notPoison ⊢
  rcases
      distinctStateRun_eq_poison_or_valid
        support (committedEvents attempts) with
    poisoned | valid
  · exact (notPoison poisoned).elim
  · exact valid

/-- The complete CAS retry history has one deterministic mathematical result
once its winners are known to be a permutation of the authenticated event
roster. -/
theorem decode_cudaAttemptRun_eq_valid_of_committed_perm
    {support : Support} {attempts : List CASAttempt}
    {roster : List SplitEvent}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix)
    (complete :
      (committedEvents attempts).Perm roster)
    (notPoison :
      decodeWord
          (cudaAttemptRun (encodeSupport support) attempts) ≠
        .poison) :
    decodeWord
        (cudaAttemptRun (encodeSupport support) attempts) =
      .valid (distinctRun support roster) := by
  rw [decode_cudaAttemptRun_eq_valid_committed
    attempts productFits countFits notPoison]
  exact congrArg State.valid
    (distinctRun_perm support complete)

#print axioms stateAttemptRun_eq_distinctStateRun
#print axioms cudaAttemptRun_splitRepresents
#print axioms word_lt_uint64Radix_of_splitRepresents
#print axioms cudaAttemptRun_lt_uint64Radix
#print axioms decode_cudaAttemptRun_eq_valid_committed
#print axioms decode_cudaAttemptRun_eq_valid_of_committed_perm

end SparkInterval.TernaryGoldbach.MobiusCASRetryTrace
