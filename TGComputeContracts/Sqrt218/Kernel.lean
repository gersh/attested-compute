/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer

This file is a data-independent port of the project-owned kernel in
`TGNativeCertificates/Sqrt218Ordinary/Kernel.lean`.  Production arrays and
generated shards are intentionally excluded.
-/
import TGComputeContracts.Sqrt218.Source
import Mathlib.Data.Nat.Prime.Int
import Mathlib.Tactic

/-!
# Generic certificate kernel for the finite square-root Mangoldt check

The types in this file are the architecture-neutral contract between a
certificate producer and the real-valued soundness proof.  They record:

* a complete prime roster;
* a complete, strictly ordered prime-power roster with unique multiplicity;
* directed fixed-point logarithm endpoints;
* and the exact natural-number event scan plus terminal anchor guard.

There is no production data and no large closed reduction in this module.
-/

set_option autoImplicit false

noncomputable section

namespace TGComputeContracts.Sqrt218

open Finset

/-! ## Complete prime rosters -/

/-- Semantic boundary for a complete roster of all primes through `bound`. -/
structure PrimeRosterFacts (bound count : Nat)
    (primeAt : Nat → Nat) : Prop where
  count_pos : 0 < count
  prime : ∀ i, i < count → (primeAt i).Prime
  value_le : ∀ i, i < count → primeAt i ≤ bound
  strictMono :
    ∀ i j, i < count → j < count → i < j → primeAt i < primeAt j
  cover :
    ∀ p, p.Prime → p ≤ bound → ∃ i, i < count ∧ primeAt i = p

theorem PrimeRosterFacts.primeAt_injective
    {bound count : Nat} {primeAt : Nat → Nat}
    (h : PrimeRosterFacts bound count primeAt)
    {i j : Nat} (hi : i < count) (hj : j < count)
    (heq : primeAt i = primeAt j) : i = j := by
  rcases lt_trichotomy i j with hij | hij | hij
  · exact (ne_of_lt (h.strictMono i j hi hj hij) heq).elim
  · exact hij
  · exact (ne_of_gt (h.strictMono j i hj hi hij) heq).elim

/-- Concatenate a certified prime prefix with a separately certified tail. -/
def appendPrimeAt (leftCount : Nat) (leftAt rightAt : Nat → Nat)
    (i : Nat) : Nat :=
  if i < leftCount then leftAt i else rightAt (i - leftCount)

/-- Semantic contract for a nonempty prime-roster tail after `lower`. -/
structure PrimeRosterExtensionFacts
    (lower bound count : Nat) (primeAt : Nat → Nat) : Prop where
  count_pos : 0 < count
  prime : ∀ i, i < count → (primeAt i).Prime
  value_le : ∀ i, i < count → primeAt i ≤ bound
  lower_lt_first : lower < primeAt 0
  strictMono :
    ∀ i j, i < count → j < count → i < j → primeAt i < primeAt j
  cover :
    ∀ p, p.Prime → lower < p → p ≤ bound →
      ∃ i, i < count ∧ primeAt i = p

/-- A complete prefix and complete tail concatenate without reevaluating
either roster. -/
theorem PrimeRosterFacts.append_extension
    {leftBound bound leftCount rightCount : Nat}
    {leftAt rightAt : Nat → Nat}
    (hbound : leftBound ≤ bound)
    (hleft : PrimeRosterFacts leftBound leftCount leftAt)
    (hright :
      PrimeRosterExtensionFacts (leftAt (leftCount - 1)) bound
        rightCount rightAt) :
    PrimeRosterFacts bound (leftCount + rightCount)
      (appendPrimeAt leftCount leftAt rightAt) := by
  have hleftPos : 0 < leftCount := hleft.count_pos
  have hrightPos : 0 < rightCount := hright.count_pos
  have hlast : leftCount - 1 < leftCount := by omega
  have hleftToLast :
      ∀ i, i < leftCount → leftAt i ≤ leftAt (leftCount - 1) := by
    intro i hi
    by_cases hEq : i = leftCount - 1
    · simp [hEq]
    · exact
        (hleft.strictMono i (leftCount - 1) hi hlast (by omega)).le
  have hfirstToRight :
      ∀ j, j < rightCount → rightAt 0 ≤ rightAt j := by
    intro j hj
    by_cases hEq : j = 0
    · simp [hEq]
    · exact
        (hright.strictMono 0 j hright.count_pos hj (by omega)).le
  refine
    { count_pos := by omega
      prime := ?_
      value_le := ?_
      strictMono := ?_
      cover := ?_ }
  · intro i hi
    by_cases hileft : i < leftCount
    · simpa [appendPrimeAt, hileft] using hleft.prime i hileft
    · have hiright : i - leftCount < rightCount := by omega
      simpa [appendPrimeAt, hileft] using
        hright.prime (i - leftCount) hiright
  · intro i hi
    by_cases hileft : i < leftCount
    · simpa [appendPrimeAt, hileft] using
        (hleft.value_le i hileft).trans hbound
    · have hiright : i - leftCount < rightCount := by omega
      simpa [appendPrimeAt, hileft] using
        hright.value_le (i - leftCount) hiright
  · intro i j hi hj hij
    by_cases hileft : i < leftCount
    · by_cases hjleft : j < leftCount
      · simpa [appendPrimeAt, hileft, hjleft] using
          hleft.strictMono i j hileft hjleft hij
      · have hjright : j - leftCount < rightCount := by omega
        have hcross :
            leftAt i < rightAt (j - leftCount) :=
          (hleftToLast i hileft).trans_lt
            (hright.lower_lt_first.trans_le
              (hfirstToRight (j - leftCount) hjright))
        simpa [appendPrimeAt, hileft, hjleft] using hcross
    · have hjleft : ¬j < leftCount := by omega
      have hiright : i - leftCount < rightCount := by omega
      have hjright : j - leftCount < rightCount := by omega
      have hsub : i - leftCount < j - leftCount := by omega
      simpa [appendPrimeAt, hileft, hjleft] using
        hright.strictMono (i - leftCount) (j - leftCount)
          hiright hjright hsub
  · intro p hp hpBound
    by_cases hpleft : p ≤ leftBound
    · obtain ⟨i, hi, hip⟩ := hleft.cover p hp hpleft
      refine ⟨i, by omega, ?_⟩
      simpa [appendPrimeAt, hi] using hip
    · have hlower : leftAt (leftCount - 1) < p :=
        (hleft.value_le (leftCount - 1) hlast).trans_lt
          (Nat.lt_of_not_ge hpleft)
      obtain ⟨j, hj, hjp⟩ := hright.cover p hp hlower hpBound
      refine ⟨leftCount + j, by omega, ?_⟩
      simpa [appendPrimeAt] using hjp

/-! ## Complete prime-power layouts -/

/-- One sorted prime-power event. -/
structure PowerEvent where
  value : Nat
  primeIndex : Nat
  exponent : Nat
  floorSqrt : Nat
  deriving DecidableEq, Inhabited, Repr

/-- Real meaning of one prime-power event row. -/
structure PowerEventFacts (bound primeCount : Nat) (primeAt : Nat → Nat)
    (event : PowerEvent) : Prop where
  value_le : event.value ≤ bound
  primeIndex_lt : event.primeIndex < primeCount
  exponent_pos : 0 < event.exponent
  value_eq : event.value = primeAt event.primeIndex ^ event.exponent
  floorSqrt_eq : event.floorSqrt = Nat.sqrt event.value

/-- Source-semantic contract exported by a checked prime-power layout. -/
structure PrimePowerEnumerationFacts
    (bound primeCount : Nat) (primeAt : Nat → Nat)
    (eventCount : Nat) (eventAt : Nat → PowerEvent) : Prop where
  event_facts :
    ∀ j, j < eventCount →
      PowerEventFacts bound primeCount primeAt (eventAt j)
  event_value_le :
    ∀ j, j < eventCount → (eventAt j).value ≤ bound
  event_sound :
    ∀ j, j < eventCount → IsPrimePow (eventAt j).value
  complete :
    ∀ n, IsPrimePow n → n ≤ bound →
      ∃ j, j < eventCount ∧ (eventAt j).value = n
  value_strict :
    ∀ i j, i < eventCount → j < eventCount → i < j →
      (eventAt i).value < (eventAt j).value
  value_injective :
    ∀ i j, i < eventCount → j < eventCount →
      (eventAt i).value = (eventAt j).value → i = j
  representation_unique :
    ∀ j, j < eventCount →
      ∀ i, i < primeCount → ∀ k, 0 < k →
        (eventAt j).value = primeAt i ^ k →
        (eventAt j).primeIndex = i ∧ (eventAt j).exponent = k

private theorem strict_of_adjacent
    {count : Nat} {value : Nat → Nat}
    (hadj : ∀ i, i + 1 < count → value i < value (i + 1)) :
    ∀ i j, i < count → j < count → i < j → value i < value j := by
  intro i j hi hj hij
  induction j with
  | zero => omega
  | succ j ih =>
      by_cases hEq : i = j
      · subst i
        exact hadj j hj
      · have hij' : i < j := by omega
        exact (ih (by omega) hij').trans (hadj j hj)

private theorem exponent_le_exact_count
    {bound p count exponent : Nat}
    (hp : 0 < p) (_hexponent : 0 < exponent)
    (hvalue : p ^ exponent ≤ bound)
    (hmax : bound < p ^ (count + 1)) :
    exponent ≤ count := by
  by_contra hnot
  have hle : count + 1 ≤ exponent := by omega
  have hpows : p ^ (count + 1) ≤ p ^ exponent :=
    Nat.pow_le_pow_right hp hle
  omega

/-- Generic builder for a sharded prime-power trace.  It requires row facts,
adjacent ordering, exact maximal exponents, and a canonical inverse map.
These hypotheses are data-independent and half-open-range friendly. -/
theorem primePowerEnumerationFacts_of_canonical
    {bound primeCount eventCount : Nat}
    {primeAt : Nat → Nat} {eventAt : Nat → PowerEvent}
    {powerCountAt : Nat → Nat}
    {canonicalIndexAt : Nat → Nat → Nat}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hevent :
      ∀ j, j < eventCount →
        PowerEventFacts bound primeCount primeAt (eventAt j))
    (horder :
      ∀ j, j + 1 < eventCount →
        (eventAt j).value < (eventAt (j + 1)).value)
    (hcount :
      ∀ i, i < primeCount →
        0 < powerCountAt i ∧
        primeAt i ^ powerCountAt i ≤ bound ∧
        bound < primeAt i ^ (powerCountAt i + 1))
    (hcoverage :
      ∀ i, i < primeCount → ∀ k, k < powerCountAt i →
        canonicalIndexAt i k < eventCount ∧
        (eventAt (canonicalIndexAt i k)).primeIndex = i ∧
        (eventAt (canonicalIndexAt i k)).exponent = k + 1) :
    PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt := by
  have hstrict :
      ∀ i j, i < eventCount → j < eventCount → i < j →
        (eventAt i).value < (eventAt j).value :=
    strict_of_adjacent horder
  refine
    { event_facts := hevent
      event_value_le := fun j hj => (hevent j hj).value_le
      event_sound := ?_
      complete := ?_
      value_strict := hstrict
      value_injective := ?_
      representation_unique := ?_ }
  · intro j hj
    have hf := hevent j hj
    rw [isPrimePow_nat_iff]
    exact
      ⟨primeAt (eventAt j).primeIndex, (eventAt j).exponent,
        hroster.prime _ hf.primeIndex_lt, hf.exponent_pos,
        hf.value_eq.symm⟩
  · intro n hnPower hnBound
    obtain ⟨p, k, hp, hk, hpow⟩ := (isPrimePow_nat_iff n).mp hnPower
    have hpLePow : p ≤ p ^ k := Nat.le_self_pow hk.ne' p
    have hpBound : p ≤ bound := hpLePow.trans (by simpa [hpow] using hnBound)
    obtain ⟨i, hi, hpi⟩ := hroster.cover p hp hpBound
    have hc := hcount i hi
    have hkCount : k ≤ powerCountAt i := by
      apply exponent_le_exact_count hp.pos hk
      · simpa [hpi, hpow] using hnBound
      · simpa [hpi] using hc.2.2
    let slot := k - 1
    have hslot : slot < powerCountAt i := by
      dsimp [slot]
      omega
    have hm := hcoverage i hi slot hslot
    let j := canonicalIndexAt i slot
    refine ⟨j, hm.1, ?_⟩
    have hf := hevent j hm.1
    rw [hf.value_eq, hm.2.1, hm.2.2]
    simp only [slot]
    rw [Nat.sub_add_cancel hk]
    simpa [hpi] using hpow
  · intro i j hi hj heq
    rcases lt_trichotomy i j with hij | hij | hij
    · exact (ne_of_lt (hstrict i j hi hj hij) heq).elim
    · exact hij
    · exact (ne_of_gt (hstrict j i hj hi hij) heq).elim
  · intro j hj i hi k hk hvalue
    have hf := hevent j hj
    have hpj := hroster.prime _ hf.primeIndex_lt
    have hpi := hroster.prime i hi
    have hpows :
        primeAt (eventAt j).primeIndex ^ (eventAt j).exponent =
          primeAt i ^ k := by
      rw [← hf.value_eq, hvalue]
    have hunique :=
      Nat.Prime.pow_inj' hpj hpi hf.exponent_pos.ne' hk.ne' hpows
    exact
      ⟨hroster.primeAt_injective hf.primeIndex_lt hi hunique.1,
        hunique.2⟩

/-! ## Directed fixed-point arithmetic -/

/-- Fixed-point denominator `2^48` for logarithm endpoints. -/
def scale : Nat := 281_474_976_710_656

theorem scale_pos : 0 < scale := by norm_num [scale]

/-- Fixed-point denominator `2^30` for reciprocal square roots. -/
def reciprocalScale : Nat := 1_073_741_824

theorem reciprocalScale_pos : 0 < reciprocalScale := by
  norm_num [reciprocalScale]

def sqrtRemainder (n s : Nat) : Nat := n - s ^ 2

def ceilDiv (num den : Nat) : Nat := (num + (den - 1)) / den

def reciprocalLower (n s : Nat) : Nat :=
  let r := sqrtRemainder n s
  reciprocalScale * (2 * s) / (2 * s ^ 2 + r)

def reciprocalUpper (n s : Nat) : Nat :=
  let r := sqrtRemainder n s
  ceilDiv (reciprocalScale * (4 * s ^ 2 + r))
    (s * (4 * s ^ 2 + 3 * r))

def weightedTermUpper (logUpper n floorSqrt : Nat) : Nat :=
  if logUpper = 0 then 0
  else logUpper * reciprocalUpper n floorSqrt

def headOK (_N floorSqrt weightedUpper : Nat) : Bool :=
  decide (1250 * weightedUpper <
    2501 * floorSqrt * scale * reciprocalScale)

def anchorOK (N weightedUpper psiLower : Nat) : Bool :=
  let floorSqrt := Nat.sqrt N
  decide ((2500 : Int) *
      ((weightedUpper : Int) -
        (psiLower * reciprocalLower N floorSqrt : Nat)) <
    (2501 : Int) * floorSqrt * scale * reciprocalScale)

/-- Directed log facts are explicit theorem hypotheses.  The expensive
closed checkpoint replay is intentionally not imported into this package. -/
structure PrimeLogFacts (primeCount : Nat) (primeAt : Nat → Nat)
    (logLowerAt logUpperAt : Nat → Nat) : Prop where
  lower :
    ∀ i, i < primeCount →
      (logLowerAt i : Real) ≤ (scale : Real) * Real.log (primeAt i)
  upper :
    ∀ i, i < primeCount →
      (scale : Real) * Real.log (primeAt i) ≤ (logUpperAt i : Real)

/-- Two exact natural-number accumulators maintained by the event scan. -/
structure FixedState where
  weightedUpper : Nat
  psiLower : Nat
  deriving DecidableEq, Inhabited, Repr

namespace FixedState

def zero : FixedState := ⟨0, 0⟩

end FixedState

def fixedEventStep (eventAt : Nat → PowerEvent)
    (logLowerAt logUpperAt : Nat → Nat) (j : Nat)
    (state : FixedState) : Option FixedState :=
  let event := eventAt j
  let lambdaLower := logLowerAt event.primeIndex
  let lambdaUpper := logUpperAt event.primeIndex
  let weightedUpper :=
    state.weightedUpper +
      weightedTermUpper lambdaUpper event.value event.floorSqrt
  let psiLower := state.psiLower + lambdaLower
  if headOK event.value event.floorSqrt weightedUpper then
    some { weightedUpper, psiLower }
  else
    none

def boundedFixedEventStep (eventCount : Nat)
    (eventAt : Nat → PowerEvent) (logLowerAt logUpperAt : Nat → Nat)
    (start : Nat) (state : FixedState) : Option FixedState :=
  if start < eventCount then
    fixedEventStep eventAt logLowerAt logUpperAt start state
  else
    none

universe u

def runOptionalSteps {α : Type u} (step : Nat → α → Option α) :
    Nat → Nat → α → Option α
  | _, 0, state => some state
  | start, count + 1, state =>
      match step start state with
      | none => none
      | some next => runOptionalSteps step (start + 1) count next

theorem runOptionalSteps_append
    {α : Type u} {step : Nat → α → Option α}
    {start count₁ count₂ : Nat} {entry middle exit : α}
    (h₁ : runOptionalSteps step start count₁ entry = some middle)
    (h₂ : runOptionalSteps step (start + count₁) count₂ middle = some exit) :
    runOptionalSteps step start (count₁ + count₂) entry = some exit := by
  induction count₁ generalizing start entry with
  | zero =>
      change some entry = some middle at h₁
      cases h₁
      simpa only [Nat.add_zero, Nat.zero_add] using h₂
  | succ count ih =>
      rw [runOptionalSteps] at h₁
      split at h₁
      next => contradiction
      next next hstep =>
        rw [Nat.succ_add, runOptionalSteps, hstep]
        have h₂' :
            runOptionalSteps step (start + 1 + count) count₂ middle =
              some exit := by
          simpa only [Nat.add_assoc, Nat.add_comm 1 count] using h₂
        exact ih h₁ h₂'

def runFixedEvents (eventCount : Nat) (eventAt : Nat → PowerEvent)
    (logLowerAt logUpperAt : Nat → Nat)
    (start count : Nat) (state : FixedState) : Option FixedState :=
  runOptionalSteps
    (boundedFixedEventStep eventCount eventAt logLowerAt logUpperAt)
    start count state

theorem runFixedEvents_append
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    {start count₁ count₂ : Nat} {entry middle exit : FixedState}
    (h₁ : runFixedEvents eventCount eventAt logLowerAt logUpperAt
      start count₁ entry = some middle)
    (h₂ : runFixedEvents eventCount eventAt logLowerAt logUpperAt
      (start + count₁) count₂ middle = some exit) :
    runFixedEvents eventCount eventAt logLowerAt logUpperAt
      start (count₁ + count₂) entry = some exit :=
  runOptionalSteps_append h₁ h₂

/-! ## Aggregate semantic certificate boundary -/

/-- All data-dependent facts required by the generic soundness theorem.
Supplying this structure does not require Lean to replay a closed production
corpus in this module. -/
structure CertificateFacts
    {primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    {exit : FixedState} : Prop where
  roster : PrimeRosterFacts sourceCutoff primeCount primeAt
  layout :
    PrimePowerEnumerationFacts sourceCutoff primeCount primeAt
      eventCount eventAt
  logs : PrimeLogFacts primeCount primeAt logLowerAt logUpperAt
  run :
    runFixedEvents eventCount eventAt logLowerAt logUpperAt
      0 eventCount FixedState.zero = some exit
  anchor :
    anchorOK sourceCutoff exit.weightedUpper exit.psiLower = true

end TGComputeContracts.Sqrt218

end
