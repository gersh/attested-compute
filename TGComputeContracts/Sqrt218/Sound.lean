/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer

This file is a data-independent port of the project-owned proof in
`TGNativeCertificates/Sqrt218Ordinary/Sound.lean`.  It has been separated
from the generated production corpus.
-/
import TGComputeContracts.Sqrt218.Kernel

/-!
# Source soundness of the generic square-root Mangoldt certificate

This file proves the exact paper-shaped `SourceClaim` from five explicit
semantic inputs: a complete prime roster, a complete prime-power layout,
directed logarithm facts, the full symbolic fixed-event run, and its endpoint
anchor.  No closed production computation is evaluated here.
-/

set_option autoImplicit false
set_option maxHeartbeats 10000000
set_option maxRecDepth 100000

noncomputable section

open scoped BigOperators ArithmeticFunction
open Finset

namespace TGComputeContracts.Sqrt218

/-! ## Reciprocal-square-root enclosures -/

private theorem real_le_ceilDiv (a b : Nat) (hb : 0 < b) :
    (a : Real) / (b : Real) ≤ (ceilDiv a b : Real) := by
  have hmod := Nat.div_add_mod (a + (b - 1)) b
  have hlt : (a + (b - 1)) % b < b := Nat.mod_lt _ hb
  have hkey : a ≤ b * ((a + (b - 1)) / b) := by omega
  have hb' : (0 : Real) < (b : Real) := by exact_mod_cast hb
  rw [div_le_iff₀ hb']
  calc
    (a : Real) ≤ ((b * ((a + (b - 1)) / b) : Nat) : Real) := by
      exact_mod_cast hkey
    _ = (((a + (b - 1)) / b : Nat) : Real) * (b : Real) := by
      push_cast
      ring

theorem reciprocalLower_le (n s : Nat) (hn : 0 < n)
    (hs : s = Nat.sqrt n) :
    (reciprocalLower n s : Real) / (reciprocalScale : Real) ≤
      1 / Real.sqrt (n : Real) := by
  have hspos : 0 < s := by simpa [hs] using (Nat.sqrt_pos.mpr hn)
  have hs2 : s ^ 2 ≤ n := by simpa [hs] using Nat.sqrt_le' n
  let r := sqrtRemainder n s
  have hnr : n = s ^ 2 + r := by
    simp only [r, sqrtRemainder]
    omega
  have hnR : (0 : Real) < (n : Real) := by exact_mod_cast hn
  have hS : (0 : Real) < (reciprocalScale : Real) := by
    exact_mod_cast reciprocalScale_pos
  have hsR : (0 : Real) < (s : Real) := by exact_mod_cast hspos
  have hsqrt : (0 : Real) < Real.sqrt (n : Real) := Real.sqrt_pos.mpr hnR
  have hsqrtSq : (Real.sqrt (n : Real)) ^ 2 = (n : Real) :=
    Real.sq_sqrt hnR.le
  have hcross : (2 * (s : Real)) * Real.sqrt (n : Real) ≤
      2 * (s : Real) ^ 2 + (r : Real) := by
    have hid :
        (2 * (s : Real) ^ 2 + (r : Real)) ^ 2 -
            ((2 * (s : Real)) * Real.sqrt (n : Real)) ^ 2 =
          (r : Real) ^ 2 := by
      calc
        (2 * (s : Real) ^ 2 + (r : Real)) ^ 2 -
              ((2 * (s : Real)) * Real.sqrt (n : Real)) ^ 2 =
            (2 * (s : Real) ^ 2 + (r : Real)) ^ 2 -
              (2 * (s : Real)) ^ 2 * (Real.sqrt (n : Real)) ^ 2 := by ring
        _ = (2 * (s : Real) ^ 2 + (r : Real)) ^ 2 -
              (2 * (s : Real)) ^ 2 * (n : Real) := by rw [hsqrtSq]
        _ = (r : Real) ^ 2 := by
          have hnrR : (n : Real) = (s : Real) ^ 2 + (r : Real) := by
            exact_mod_cast hnr
          rw [hnrR]
          ring
    apply (sq_le_sq₀ (by positivity)
      (by positivity : (0 : Real) ≤ 2 * (s : Real) ^ 2 + r)).mp
    nlinarith [sq_nonneg (r : Real)]
  have hfloor : (reciprocalLower n s : Real) ≤
      ((reciprocalScale * (2 * s) : Nat) : Real) /
        ((2 * s ^ 2 + r : Nat) : Real) := by
    simpa [reciprocalLower, r] using
      (Nat.cast_div_le :
        (((reciprocalScale * (2 * s)) / (2 * s ^ 2 + r) : Nat) : Real) ≤
          ((reciprocalScale * (2 * s) : Nat) : Real) /
            ((2 * s ^ 2 + r : Nat) : Real))
  have hden : (0 : Real) < ((2 * s ^ 2 + r : Nat) : Real) := by positivity
  have hraw : (reciprocalLower n s : Real) * Real.sqrt (n : Real) ≤
      (reciprocalScale : Real) := by
    calc
      (reciprocalLower n s : Real) * Real.sqrt (n : Real) ≤
          (((reciprocalScale * (2 * s) : Nat) : Real) /
            ((2 * s ^ 2 + r : Nat) : Real)) * Real.sqrt (n : Real) :=
        mul_le_mul_of_nonneg_right hfloor hsqrt.le
      _ ≤ (reciprocalScale : Real) := by
        rw [div_mul_eq_mul_div, div_le_iff₀ hden]
        push_cast
        nlinarith
  rw [div_le_div_iff₀ hS hsqrt]
  simpa [mul_comm] using hraw

theorem le_reciprocalUpper (n s : Nat) (hn : 0 < n)
    (hs : s = Nat.sqrt n) :
    1 / Real.sqrt (n : Real) ≤
      (reciprocalUpper n s : Real) / (reciprocalScale : Real) := by
  have hspos : 0 < s := by simpa [hs] using (Nat.sqrt_pos.mpr hn)
  have hs2 : s ^ 2 ≤ n := by simpa [hs] using Nat.sqrt_le' n
  let r := sqrtRemainder n s
  have hnr : n = s ^ 2 + r := by
    simp only [r, sqrtRemainder]
    omega
  let A : Nat := 4 * s ^ 2 + r
  let B : Nat := s * (4 * s ^ 2 + 3 * r)
  have hA : (0 : Real) < (A : Real) := by
    dsimp [A]
    positivity
  have hB : (0 : Real) < (B : Real) := by
    dsimp [B]
    positivity
  have hnR : (0 : Real) < (n : Real) := by exact_mod_cast hn
  have hS : (0 : Real) < (reciprocalScale : Real) := by
    exact_mod_cast reciprocalScale_pos
  have hsqrt : (0 : Real) < Real.sqrt (n : Real) := Real.sqrt_pos.mpr hnR
  have hnrR : (n : Real) = (s : Real) ^ 2 + (r : Real) := by
    exact_mod_cast hnr
  have hBA : (B : Real) / (A : Real) ≤ Real.sqrt (n : Real) := by
    rw [Real.le_sqrt (div_nonneg (by positivity) hA.le) hnR.le]
    rw [div_pow, div_le_iff₀ (sq_pos_of_pos hA)]
    have hid :
        (n : Real) * (A : Real) ^ 2 - (B : Real) ^ 2 = (r : Real) ^ 3 := by
      dsimp [A, B]
      push_cast
      rw [hnrR]
      ring
    nlinarith [pow_nonneg (by positivity : (0 : Real) ≤ r) 3]
  have hinv : 1 / Real.sqrt (n : Real) ≤ (A : Real) / (B : Real) := by
    have hone := one_div_le_one_div_of_le (div_pos hB hA) hBA
    calc
      1 / Real.sqrt (n : Real) ≤ 1 / ((B : Real) / (A : Real)) := hone
      _ = (A : Real) / (B : Real) := by field_simp
  have hceil :
      (((reciprocalScale * A : Nat) : Real) / (B : Real)) ≤
        (reciprocalUpper n s : Real) := by
    simpa [reciprocalUpper, ceilDiv, A, B, r] using
      real_le_ceilDiv (reciprocalScale * A) B (by exact_mod_cast hB)
  calc
    1 / Real.sqrt (n : Real) ≤ (A : Real) / (B : Real) := hinv
    _ = (((reciprocalScale * A : Nat) : Real) / (B : Real)) /
        (reciprocalScale : Real) := by
      push_cast
      field_simp [hS.ne', hB.ne']
    _ ≤ (reciprocalUpper n s : Real) / (reciprocalScale : Real) :=
      div_le_div_of_nonneg_right hceil (by positivity)

/-! ## Exact Mangoldt sums and prime-power reindexing -/

/-- The source sum with its zero `n = 1` term omitted. -/
noncomputable def mangoldtSqrtSum (N : Nat) : Real :=
  ∑ n ∈ Finset.Ioc 1 N,
    ArithmeticFunction.vonMangoldt n / Real.sqrt (n : Real)

/-- Finite Chebyshev sum with the zero `n = 1` term omitted. -/
noncomputable def psiSum (N : Nat) : Real :=
  ∑ n ∈ Finset.Ioc 1 N, ArithmeticFunction.vonMangoldt n

theorem vonMangoldtSqrtNat_eq_mangoldtSqrtSum
    (N : Nat) (hN : 1 ≤ N) :
    vonMangoldtSqrtNat N = mangoldtSqrtSum N := by
  have hset : Finset.Icc 1 N = insert 1 (Finset.Ioc 1 N) := by
    ext n
    simp only [Finset.mem_Icc, Finset.mem_insert, Finset.mem_Ioc]
    omega
  unfold vonMangoldtSqrtNat mangoldtSqrtSum
  rw [hset, Finset.sum_insert (by simp [Finset.mem_Ioc])]
  simp [ArithmeticFunction.vonMangoldt_apply, not_isPrimePow_one]

theorem psiSum_eq_chebyshevPsi (N : Nat) :
    psiSum N = Chebyshev.psi (N : Real) := by
  unfold psiSum Chebyshev.psi
  rw [Nat.floor_natCast]
  by_cases hN : N = 0
  · simp [hN]
  · have hset : Finset.Ioc 0 N = insert 1 (Finset.Ioc 1 N) := by
      ext n
      simp only [Finset.mem_Ioc, Finset.mem_insert]
      omega
    rw [hset, Finset.sum_insert (by simp [Finset.mem_Ioc])]
    simp [ArithmeticFunction.vonMangoldt_apply, not_isPrimePow_one]

theorem psiSum_nonneg (N : Nat) : 0 ≤ psiSum N := by
  unfold psiSum
  exact Finset.sum_nonneg fun _ _ => ArithmeticFunction.vonMangoldt_nonneg

/-- Event indices whose prime-power value is at most `N`. -/
def eventIndexSet (eventCount : Nat) (eventAt : Nat → PowerEvent)
    (N : Nat) : Finset Nat :=
  (Finset.range eventCount).filter fun j => (eventAt j).value ≤ N

noncomputable def eventSqrtContribution
    (primeAt : Nat → Nat) (eventAt : Nat → PowerEvent)
    (j : Nat) : Real :=
  Real.log (primeAt (eventAt j).primeIndex : Real) /
    Real.sqrt ((eventAt j).value : Real)

noncomputable def eventLogContribution
    (primeAt : Nat → Nat) (eventAt : Nat → PowerEvent)
    (j : Nat) : Real :=
  Real.log (primeAt (eventAt j).primeIndex : Real)

noncomputable def eventSqrtPrefix
    (primeAt : Nat → Nat) (eventAt : Nat → PowerEvent)
    (count : Nat) : Real :=
  ∑ j ∈ Finset.range count, eventSqrtContribution primeAt eventAt j

noncomputable def eventLogPrefix
    (primeAt : Nat → Nat) (eventAt : Nat → PowerEvent)
    (count : Nat) : Real :=
  ∑ j ∈ Finset.range count, eventLogContribution primeAt eventAt j

theorem mangoldtSqrtSum_eq_event_sum
    {bound primeCount N : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hNB : N ≤ bound) :
    mangoldtSqrtSum N =
      ∑ j ∈ eventIndexSet eventCount eventAt N,
        eventSqrtContribution primeAt eventAt j := by
  let source := eventIndexSet eventCount eventAt N
  let target := (Finset.Ioc 1 N).filter fun n => IsPrimePow n
  have hreindex :
      (∑ j ∈ source, eventSqrtContribution primeAt eventAt j) =
        ∑ n ∈ target,
          ArithmeticFunction.vonMangoldt n / Real.sqrt (n : Real) := by
    refine Finset.sum_bij (fun j _ => (eventAt j).value) ?_ ?_ ?_ ?_
    · intro j hjSource
      have hjData :
          j < eventCount ∧ (eventAt j).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hjSource
      have hpower := hlayout.event_sound j hjData.1
      simp only [target, Finset.mem_filter, Finset.mem_Ioc]
      exact ⟨⟨hpower.one_lt, hjData.2⟩, hpower⟩
    · intro i hiSource j hjSource heq
      have hi :
          i < eventCount ∧ (eventAt i).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hiSource
      have hj :
          j < eventCount ∧ (eventAt j).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hjSource
      exact hlayout.value_injective i j hi.1 hj.1 heq
    · intro n hnTarget
      have hn :
          (1 < n ∧ n ≤ N) ∧ IsPrimePow n := by
        simpa only [target, Finset.mem_filter, Finset.mem_Ioc] using hnTarget
      obtain ⟨j, hj, hjn⟩ :=
        hlayout.complete n hn.2 (hn.1.2.trans hNB)
      refine ⟨j, ?_, hjn⟩
      simp only [source, eventIndexSet, Finset.mem_filter,
        Finset.mem_range]
      exact ⟨hj, by simpa [hjn] using hn.1.2⟩
    · intro j hjSource
      have hj :
          j < eventCount ∧ (eventAt j).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hjSource
      have hf := hlayout.event_facts j hj.1
      have hp := hroster.prime _ hf.primeIndex_lt
      unfold eventSqrtContribution
      rw [hf.value_eq,
        ArithmeticFunction.vonMangoldt_apply_pow hf.exponent_pos.ne',
        ArithmeticFunction.vonMangoldt_apply_prime hp]
  have htargetSubset : target ⊆ Finset.Ioc 1 N :=
    Finset.filter_subset _ _
  have hvanish :
      ∀ n ∈ Finset.Ioc 1 N, n ∉ target →
        ArithmeticFunction.vonMangoldt n / Real.sqrt (n : Real) = 0 := by
    intro n hnIoc hnTarget
    have hnotPower : ¬IsPrimePow n := by
      intro hpower
      apply hnTarget
      simp only [target, Finset.mem_filter]
      exact ⟨hnIoc, hpower⟩
    rw [ArithmeticFunction.vonMangoldt_eq_zero_iff.mpr hnotPower, zero_div]
  have htarget :
      (∑ n ∈ target,
          ArithmeticFunction.vonMangoldt n / Real.sqrt (n : Real)) =
        mangoldtSqrtSum N := by
    unfold mangoldtSqrtSum
    exact Finset.sum_subset htargetSubset hvanish
  exact (hreindex.trans htarget).symm

theorem psiSum_eq_event_sum
    {bound primeCount N : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hNB : N ≤ bound) :
    psiSum N =
      ∑ j ∈ eventIndexSet eventCount eventAt N,
        eventLogContribution primeAt eventAt j := by
  let source := eventIndexSet eventCount eventAt N
  let target := (Finset.Ioc 1 N).filter fun n => IsPrimePow n
  have hreindex :
      (∑ j ∈ source, eventLogContribution primeAt eventAt j) =
        ∑ n ∈ target, ArithmeticFunction.vonMangoldt n := by
    refine Finset.sum_bij (fun j _ => (eventAt j).value) ?_ ?_ ?_ ?_
    · intro j hjSource
      have hjData :
          j < eventCount ∧ (eventAt j).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hjSource
      have hpower := hlayout.event_sound j hjData.1
      simp only [target, Finset.mem_filter, Finset.mem_Ioc]
      exact ⟨⟨hpower.one_lt, hjData.2⟩, hpower⟩
    · intro i hiSource j hjSource heq
      have hi :
          i < eventCount ∧ (eventAt i).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hiSource
      have hj :
          j < eventCount ∧ (eventAt j).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hjSource
      exact hlayout.value_injective i j hi.1 hj.1 heq
    · intro n hnTarget
      have hn :
          (1 < n ∧ n ≤ N) ∧ IsPrimePow n := by
        simpa only [target, Finset.mem_filter, Finset.mem_Ioc] using hnTarget
      obtain ⟨j, hj, hjn⟩ :=
        hlayout.complete n hn.2 (hn.1.2.trans hNB)
      refine ⟨j, ?_, hjn⟩
      simp only [source, eventIndexSet, Finset.mem_filter,
        Finset.mem_range]
      exact ⟨hj, by simpa [hjn] using hn.1.2⟩
    · intro j hjSource
      have hj :
          j < eventCount ∧ (eventAt j).value ≤ N := by
        simpa only [source, eventIndexSet, Finset.mem_filter,
          Finset.mem_range] using hjSource
      have hf := hlayout.event_facts j hj.1
      have hp := hroster.prime _ hf.primeIndex_lt
      unfold eventLogContribution
      rw [hf.value_eq,
        ArithmeticFunction.vonMangoldt_apply_pow hf.exponent_pos.ne',
        ArithmeticFunction.vonMangoldt_apply_prime hp]
  have htargetSubset : target ⊆ Finset.Ioc 1 N :=
    Finset.filter_subset _ _
  have hvanish :
      ∀ n ∈ Finset.Ioc 1 N, n ∉ target →
        ArithmeticFunction.vonMangoldt n = 0 := by
    intro n hnIoc hnTarget
    apply ArithmeticFunction.vonMangoldt_eq_zero_iff.mpr
    intro hpower
    apply hnTarget
    simp only [target, Finset.mem_filter]
    exact ⟨hnIoc, hpower⟩
  have htarget :
      (∑ n ∈ target, ArithmeticFunction.vonMangoldt n) = psiSum N := by
    unfold psiSum
    exact Finset.sum_subset htargetSubset hvanish
  exact (hreindex.trans htarget).symm

/-- At event `count - 1`, the selected set is exactly the first `count`
strictly ordered rows. -/
theorem eventIndexSet_at_event
    {bound primeCount count : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hcountPos : 0 < count) (hcount : count ≤ eventCount) :
    eventIndexSet eventCount eventAt (eventAt (count - 1)).value =
      Finset.range count := by
  ext j
  simp only [eventIndexSet, Finset.mem_filter, Finset.mem_range]
  constructor
  · rintro ⟨hjSize, hjValue⟩
    by_contra hjCount
    have hlast : count - 1 < eventCount := by omega
    have hstrict :=
      hlayout.value_strict (count - 1) j hlast hjSize (by omega)
    omega
  · intro hjCount
    have hjSize : j < eventCount := hjCount.trans_le hcount
    refine ⟨hjSize, ?_⟩
    by_cases hjLast : j = count - 1
    · simp [hjLast]
    · exact
        (hlayout.value_strict j (count - 1) hjSize (by omega)
          (by omega)).le

/-- At the certified bound every event is selected. -/
theorem eventIndexSet_at_bound
    {bound primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt) :
    eventIndexSet eventCount eventAt bound = Finset.range eventCount := by
  ext j
  simp only [eventIndexSet, Finset.mem_filter, Finset.mem_range]
  constructor
  · exact fun h => h.1
  · intro hj
    exact ⟨hj, hlayout.event_value_le j hj⟩

/-! ## Fixed-point prefix enclosures -/

/-- Exact natural-number state represented by the first `count` events. -/
def fixedPrefix (eventAt : Nat → PowerEvent)
    (logLowerAt logUpperAt : Nat → Nat) (count : Nat) : FixedState where
  weightedUpper :=
    ∑ j ∈ Finset.range count,
      weightedTermUpper
        (logUpperAt (eventAt j).primeIndex)
        (eventAt j).value (eventAt j).floorSqrt
  psiLower :=
    ∑ j ∈ Finset.range count,
      logLowerAt (eventAt j).primeIndex

theorem eventSqrtContribution_le_fixed
    {bound primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hlogs :
      PrimeLogFacts primeCount primeAt logLowerAt logUpperAt)
    {j : Nat} (hj : j < eventCount) :
    eventSqrtContribution primeAt eventAt j ≤
      (weightedTermUpper
          (logUpperAt (eventAt j).primeIndex)
          (eventAt j).value (eventAt j).floorSqrt : Real) /
        ((scale * reciprocalScale : Nat) : Real) := by
  have hf := hlayout.event_facts j hj
  have hp := hroster.prime _ hf.primeIndex_lt
  let L := logUpperAt (eventAt j).primeIndex
  let R := reciprocalUpper (eventAt j).value (eventAt j).floorSqrt
  have hscale : (0 : Real) < (scale : Real) := by
    exact_mod_cast scale_pos
  have hrecScale : (0 : Real) < (reciprocalScale : Real) := by
    exact_mod_cast reciprocalScale_pos
  have hlog :
      Real.log (primeAt (eventAt j).primeIndex : Real) ≤
        (L : Real) / (scale : Real) := by
    rw [le_div_iff₀ hscale]
    simpa [L, mul_comm] using
      hlogs.upper (eventAt j).primeIndex hf.primeIndex_lt
  have hvaluePos : 0 < (eventAt j).value := by
    rw [hf.value_eq]
    exact pow_pos hp.pos _
  have hrec :
      1 / Real.sqrt ((eventAt j).value : Real) ≤
        (R : Real) / (reciprocalScale : Real) := by
    simpa [R, hf.floorSqrt_eq] using
      le_reciprocalUpper (eventAt j).value
        (eventAt j).floorSqrt hvaluePos hf.floorSqrt_eq
  have hLPos : 0 < L := by
    have hlogPos :
        0 < Real.log (primeAt (eventAt j).primeIndex : Real) := by
      apply Real.log_pos
      exact_mod_cast hp.one_lt
    have hLR : 0 < (L : Real) :=
      (mul_pos hscale hlogPos).trans_le (by
        simpa [L] using
          hlogs.upper (eventAt j).primeIndex hf.primeIndex_lt)
    exact_mod_cast hLR
  unfold eventSqrtContribution
  calc
    Real.log (primeAt (eventAt j).primeIndex : Real) /
          Real.sqrt ((eventAt j).value : Real) =
        Real.log (primeAt (eventAt j).primeIndex : Real) *
          (1 / Real.sqrt ((eventAt j).value : Real)) := by ring
    _ ≤ ((L : Real) / (scale : Real)) *
          ((R : Real) / (reciprocalScale : Real)) :=
      mul_le_mul hlog hrec (by positivity) (by positivity)
    _ =
        (weightedTermUpper L (eventAt j).value
            (eventAt j).floorSqrt : Real) /
          ((scale * reciprocalScale : Nat) : Real) := by
      simp only [weightedTermUpper, if_neg hLPos.ne']
      dsimp [R]
      push_cast
      ring

theorem fixed_le_eventLogContribution
    {bound primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hlogs :
      PrimeLogFacts primeCount primeAt logLowerAt logUpperAt)
    {j : Nat} (hj : j < eventCount) :
    (logLowerAt (eventAt j).primeIndex : Real) / (scale : Real) ≤
      eventLogContribution primeAt eventAt j := by
  have hf := hlayout.event_facts j hj
  unfold eventLogContribution
  have hscale : (0 : Real) < (scale : Real) := by
    exact_mod_cast scale_pos
  rw [div_le_iff₀ hscale]
  simpa [mul_comm] using
    hlogs.lower (eventAt j).primeIndex hf.primeIndex_lt

theorem eventSqrtPrefix_le_fixedPrefix
    {bound primeCount count : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hlogs :
      PrimeLogFacts primeCount primeAt logLowerAt logUpperAt)
    (hcount : count ≤ eventCount) :
    eventSqrtPrefix primeAt eventAt count ≤
      ((fixedPrefix eventAt logLowerAt logUpperAt count).weightedUpper : Real) /
        ((scale * reciprocalScale : Nat) : Real) := by
  unfold eventSqrtPrefix fixedPrefix
  rw [Nat.cast_sum, Finset.sum_div]
  apply Finset.sum_le_sum
  intro j hj
  exact eventSqrtContribution_le_fixed hroster hlayout hlogs
    ((Finset.mem_range.mp hj).trans_le hcount)

theorem fixedPrefix_le_eventLogPrefix
    {bound primeCount count : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hlogs :
      PrimeLogFacts primeCount primeAt logLowerAt logUpperAt)
    (hcount : count ≤ eventCount) :
    ((fixedPrefix eventAt logLowerAt logUpperAt count).psiLower : Real) /
        (scale : Real) ≤
      eventLogPrefix primeAt eventAt count := by
  unfold eventLogPrefix fixedPrefix
  rw [Nat.cast_sum, Finset.sum_div]
  apply Finset.sum_le_sum
  intro j hj
  exact fixed_le_eventLogContribution hlayout hlogs
    ((Finset.mem_range.mp hj).trans_le hcount)

/-! ## Extracting every head guard from the symbolic scan -/

private theorem fixedEventStep_prefix_iff
    {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat} {start : Nat}
    {next : FixedState} :
    fixedEventStep eventAt logLowerAt logUpperAt start
        (fixedPrefix eventAt logLowerAt logUpperAt start) = some next ↔
      headOK (eventAt start).value (eventAt start).floorSqrt
          (fixedPrefix eventAt logLowerAt logUpperAt
            (start + 1)).weightedUpper = true ∧
        next = fixedPrefix eventAt logLowerAt logUpperAt (start + 1) := by
  let current := fixedPrefix eventAt logLowerAt logUpperAt start
  let weighted :=
    current.weightedUpper +
      weightedTermUpper
        (logUpperAt (eventAt start).primeIndex)
        (eventAt start).value (eventAt start).floorSqrt
  let psi := current.psiLower + logLowerAt (eventAt start).primeIndex
  let nextState : FixedState :=
    { weightedUpper := weighted, psiLower := psi }
  have hprefix :
      fixedPrefix eventAt logLowerAt logUpperAt (start + 1) =
        nextState := by
    simp [fixedPrefix, current, weighted, psi, nextState,
      Finset.sum_range_succ]
  rw [hprefix]
  by_cases hhead :
      headOK (eventAt start).value (eventAt start).floorSqrt
        nextState.weightedUpper = true
  · constructor
    · intro hstep
      refine ⟨hhead, ?_⟩
      have heq : nextState = next := by
        simpa [fixedEventStep, current, weighted, psi, nextState, hhead] using
          hstep
      exact heq.symm
    · rintro ⟨_, rfl⟩
      simp [fixedEventStep, current, weighted, psi, nextState, hhead]
  · constructor
    · intro hstep
      have hfalse :
          headOK (eventAt start).value (eventAt start).floorSqrt
            nextState.weightedUpper = false :=
        Bool.eq_false_of_not_eq_true hhead
      simp [fixedEventStep, current, weighted, nextState, hfalse] at hstep
    · exact fun h => (hhead h.1).elim

private theorem runFixedEvents_from_prefix_sound
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    {start count : Nat} {exit : FixedState}
    (hspan : start + count ≤ eventCount)
    (hrun :
      runFixedEvents eventCount eventAt logLowerAt logUpperAt
        start count (fixedPrefix eventAt logLowerAt logUpperAt start) =
          some exit) :
    exit = fixedPrefix eventAt logLowerAt logUpperAt (start + count) ∧
      ∀ j, start ≤ j → j < start + count →
        headOK (eventAt j).value (eventAt j).floorSqrt
          (fixedPrefix eventAt logLowerAt logUpperAt
            (j + 1)).weightedUpper = true := by
  induction count generalizing start exit with
  | zero =>
      have hexit :
          exit = fixedPrefix eventAt logLowerAt logUpperAt start := by
        simpa [runFixedEvents, runOptionalSteps] using
          Option.some.inj hrun.symm
      exact ⟨by simpa using hexit, by omega⟩
  | succ count ih =>
      have hstart : start < eventCount := by omega
      unfold runFixedEvents at hrun
      rw [runOptionalSteps] at hrun
      cases hstep :
          boundedFixedEventStep eventCount eventAt logLowerAt logUpperAt
            start (fixedPrefix eventAt logLowerAt logUpperAt start) with
      | none =>
          simp [hstep] at hrun
      | some next =>
          rw [hstep] at hrun
          have hstep' :
              fixedEventStep eventAt logLowerAt logUpperAt start
                  (fixedPrefix eventAt logLowerAt logUpperAt start) =
                some next := by
            simpa [boundedFixedEventStep, hstart] using hstep
          obtain ⟨hhead, hnext⟩ :=
            fixedEventStep_prefix_iff.mp hstep'
          subst next
          have htail :
              runFixedEvents eventCount eventAt logLowerAt logUpperAt
                (start + 1) count
                (fixedPrefix eventAt logLowerAt logUpperAt (start + 1)) =
                  some exit :=
            hrun
          obtain ⟨hexit, hall⟩ := ih (by omega) htail
          refine
            ⟨by simpa [Nat.add_assoc, Nat.add_comm 1 count] using hexit, ?_⟩
          intro j hjLow hjHigh
          by_cases hj : j = start
          · simpa [hj] using hhead
          · apply hall j
            · omega
            · omega

/-- A successful full scan has the exact final prefix and checked every
prime-power-event head guard. -/
theorem runFixedEvents_sound
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat} {exit : FixedState}
    (hrun :
      runFixedEvents eventCount eventAt logLowerAt logUpperAt
        0 eventCount FixedState.zero = some exit) :
    exit = fixedPrefix eventAt logLowerAt logUpperAt eventCount ∧
      ∀ j, j < eventCount →
        headOK (eventAt j).value (eventAt j).floorSqrt
          (fixedPrefix eventAt logLowerAt logUpperAt
            (j + 1)).weightedUpper = true := by
  have hzero :
      FixedState.zero =
        fixedPrefix eventAt logLowerAt logUpperAt 0 := by
    simp [FixedState.zero, fixedPrefix]
  rw [hzero] at hrun
  simpa using
    runFixedEvents_from_prefix_sound (start := 0) (count := eventCount)
      (by omega) hrun

/-! ## Skipped integers and real head guards -/

theorem mangoldtSqrtSum_succ_of_not_primePower
    {n : Nat} (hn : 1 ≤ n) (hpower : ¬IsPrimePow (n + 1)) :
    mangoldtSqrtSum (n + 1) = mangoldtSqrtSum n := by
  have hset :
      Finset.Ioc 1 (n + 1) =
        insert (n + 1) (Finset.Ioc 1 n) := by
    ext k
    simp only [Finset.mem_Ioc, Finset.mem_insert]
    omega
  unfold mangoldtSqrtSum
  rw [hset, Finset.sum_insert]
  · simp [ArithmeticFunction.vonMangoldt_apply, hpower]
  · simp [Finset.mem_Ioc]

theorem head_between_primePower_events
    {event N : Nat} (_hevent : 1 ≤ event) (heventN : event ≤ N)
    (hconstant : mangoldtSqrtSum N = mangoldtSqrtSum event)
    (hhead :
      mangoldtSqrtSum event <
        2 * 1.0004 * Real.sqrt (event : Real)) :
    mangoldtSqrtSum N < 2 * 1.0004 * Real.sqrt (N : Real) := by
  rw [hconstant]
  have hsqrt :
      Real.sqrt (event : Real) ≤ Real.sqrt (N : Real) := by
    apply Real.sqrt_le_sqrt
    exact_mod_cast heventN
  nlinarith [Real.sqrt_nonneg (event : Real)]

theorem mangoldtSqrtSum_one : mangoldtSqrtSum 1 = 0 := by
  simp [mangoldtSqrtSum]

private theorem head_of_fixed_enclosure
    {N floorSqrt weighted : Nat}
    (hsqrt : floorSqrt = Nat.sqrt N)
    (hsum :
      mangoldtSqrtSum N ≤
        (weighted : Real) /
          ((scale * reciprocalScale : Nat) : Real))
    (hcheck : headOK N floorSqrt weighted = true) :
    mangoldtSqrtSum N <
      2 * 1.0004 * Real.sqrt (N : Real) := by
  unfold headOK at hcheck
  simp only [decide_eq_true_eq] at hcheck
  have hintR :
      (1250 : Real) * (weighted : Real) <
        (2501 : Real) * (floorSqrt : Real) * (scale : Real) *
          (reciprocalScale : Real) := by
    exact_mod_cast hcheck
  have hscale : (0 : Real) < (scale : Real) := by
    exact_mod_cast scale_pos
  have hrecScale : (0 : Real) < (reciprocalScale : Real) := by
    exact_mod_cast reciprocalScale_pos
  have hden :
      (0 : Real) < (scale : Real) * (reciprocalScale : Real) :=
    mul_pos hscale hrecScale
  have hfixed :
      (weighted : Real) /
          ((scale * reciprocalScale : Nat) : Real) <
        (2501 / 1250 : Real) * (floorSqrt : Real) := by
    push_cast at hintR ⊢
    rw [div_lt_iff₀ hden]
    norm_num
    nlinarith
  calc
    mangoldtSqrtSum N ≤
        (weighted : Real) /
          ((scale * reciprocalScale : Nat) : Real) := hsum
    _ < (2501 / 1250 : Real) * (floorSqrt : Real) := hfixed
    _ ≤ 2 * 1.0004 * Real.sqrt (N : Real) := by
      have hs := Real.nat_sqrt_le_real_sqrt (a := N)
      rw [hsqrt]
      norm_num at hs ⊢
      nlinarith

theorem head_at_event_of_fixedPrefix
    {bound primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hlogs :
      PrimeLogFacts primeCount primeAt logLowerAt logUpperAt)
    {j : Nat} (hj : j < eventCount)
    (hcheck :
      headOK (eventAt j).value (eventAt j).floorSqrt
        (fixedPrefix eventAt logLowerAt logUpperAt
          (j + 1)).weightedUpper = true) :
    mangoldtSqrtSum (eventAt j).value <
      2 * 1.0004 * Real.sqrt ((eventAt j).value : Real) := by
  have hset :
      eventIndexSet eventCount eventAt (eventAt j).value =
        Finset.range (j + 1) := by
    simpa using
      eventIndexSet_at_event hlayout (count := j + 1)
        (by omega) (by omega)
  have hsumEq :=
    mangoldtSqrtSum_eq_event_sum hroster hlayout
      (N := (eventAt j).value) (hlayout.event_value_le j hj)
  have hprefixEq :
      mangoldtSqrtSum (eventAt j).value =
        eventSqrtPrefix primeAt eventAt (j + 1) := by
    rw [hsumEq, hset]
    rfl
  have hsum :
      mangoldtSqrtSum (eventAt j).value ≤
        ((fixedPrefix eventAt logLowerAt logUpperAt
            (j + 1)).weightedUpper : Real) /
          ((scale * reciprocalScale : Nat) : Real) := by
    rw [hprefixEq]
    exact eventSqrtPrefix_le_fixedPrefix hroster hlayout hlogs (by omega)
  exact head_of_fixed_enclosure
    (hlayout.event_facts j hj).floorSqrt_eq hsum hcheck

/-- Event checks imply the head estimate at every integer through `bound`.
Away from a prime power the Mangoldt prefix is unchanged. -/
theorem head_through_bound_of_event_checks
    {bound primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    (hroster : PrimeRosterFacts bound primeCount primeAt)
    (hlayout :
      PrimePowerEnumerationFacts bound primeCount primeAt eventCount eventAt)
    (hlogs :
      PrimeLogFacts primeCount primeAt logLowerAt logUpperAt)
    (hevents :
      ∀ j, j < eventCount →
        headOK (eventAt j).value (eventAt j).floorSqrt
          (fixedPrefix eventAt logLowerAt logUpperAt
            (j + 1)).weightedUpper = true) :
    ∀ N, 1 ≤ N → N ≤ bound →
      mangoldtSqrtSum N <
        2 * 1.0004 * Real.sqrt (N : Real) := by
  intro N hN
  induction N, hN using Nat.le_induction with
  | base =>
      intro _
      rw [mangoldtSqrtSum_one]
      positivity
  | succ n hn ih =>
      intro hNB
      by_cases hpower : IsPrimePow (n + 1)
      · obtain ⟨j, hj, hjValue⟩ :=
          hlayout.complete (n + 1) hpower hNB
        simpa [hjValue] using
          head_at_event_of_fixedPrefix hroster hlayout hlogs hj
            (hevents j hj)
      · exact
          head_between_primePower_events hn (Nat.le_succ n)
            (mangoldtSqrtSum_succ_of_not_primePower hn hpower) (ih (by omega))

/-! ## Endpoint anchor -/

private theorem anchor_of_fixed_enclosures
    {N weighted psiLowerFixed : Nat}
    (hN : 0 < N)
    (hsum :
      mangoldtSqrtSum N ≤
        (weighted : Real) /
          ((scale * reciprocalScale : Nat) : Real))
    (hpsi :
      (psiLowerFixed : Real) / (scale : Real) ≤ psiSum N)
    (hcheck : anchorOK N weighted psiLowerFixed = true) :
    mangoldtSqrtSum N - psiSum N / Real.sqrt (N : Real) <
      1.0004 * Real.sqrt (N : Real) := by
  let R := reciprocalLower N (Nat.sqrt N)
  have hrec :
      (R : Real) / (reciprocalScale : Real) ≤
        1 / Real.sqrt (N : Real) := by
    simpa [R] using reciprocalLower_le N (Nat.sqrt N) hN rfl
  have hprod :
      ((psiLowerFixed : Real) / (scale : Real)) *
          ((R : Real) / (reciprocalScale : Real)) ≤
        psiSum N * (1 / Real.sqrt (N : Real)) := by
    exact mul_le_mul hpsi hrec (by positivity) (psiSum_nonneg N)
  have hsum' :
      mangoldtSqrtSum N ≤
        (weighted : Real) /
          ((scale : Real) * (reciprocalScale : Real)) := by
    simpa only [Nat.cast_mul] using hsum
  have henclose :
      mangoldtSqrtSum N - psiSum N / Real.sqrt (N : Real) ≤
        ((weighted : Real) -
            ((psiLowerFixed * R : Nat) : Real)) /
          ((scale * reciprocalScale : Nat) : Real) := by
    push_cast
    calc
      mangoldtSqrtSum N - psiSum N / Real.sqrt (N : Real) =
          mangoldtSqrtSum N -
            psiSum N * (1 / Real.sqrt (N : Real)) := by ring
      _ ≤ (weighted : Real) /
            ((scale : Real) * reciprocalScale) -
          ((psiLowerFixed : Real) / (scale : Real)) *
            ((R : Real) / (reciprocalScale : Real)) :=
        sub_le_sub hsum' hprod
      _ =
          ((weighted : Real) -
              (psiLowerFixed : Real) * (R : Real)) /
            ((scale : Real) * (reciprocalScale : Real)) := by ring
  unfold anchorOK at hcheck
  simp only [decide_eq_true_eq] at hcheck
  change
    ((2500 : Int) *
        ((weighted : Int) - (psiLowerFixed * R : Nat)) <
      (2501 : Int) * Nat.sqrt N * scale * reciprocalScale) at hcheck
  have hintR :
      (2500 : Real) *
          ((weighted : Real) -
            ((psiLowerFixed * R : Nat) : Real)) <
        (2501 : Real) * (Nat.sqrt N : Real) * (scale : Real) *
          (reciprocalScale : Real) := by
    exact_mod_cast hcheck
  have hscale : (0 : Real) < (scale : Real) := by
    exact_mod_cast scale_pos
  have hrecScale : (0 : Real) < (reciprocalScale : Real) := by
    exact_mod_cast reciprocalScale_pos
  have hden :
      (0 : Real) < (scale : Real) * (reciprocalScale : Real) :=
    mul_pos hscale hrecScale
  have hfixed :
      ((weighted : Real) -
          ((psiLowerFixed * R : Nat) : Real)) /
          ((scale * reciprocalScale : Nat) : Real) <
        (2501 / 2500 : Real) * (Nat.sqrt N : Real) := by
    push_cast at hintR ⊢
    rw [div_lt_iff₀ hden]
    norm_num
    nlinarith
  calc
    mangoldtSqrtSum N - psiSum N / Real.sqrt (N : Real) ≤
        ((weighted : Real) -
            ((psiLowerFixed * R : Nat) : Real)) /
          ((scale * reciprocalScale : Nat) : Real) := henclose
    _ < (2501 / 2500 : Real) * (Nat.sqrt N : Real) := hfixed
    _ ≤ 1.0004 * Real.sqrt (N : Real) := by
      have hs := Real.nat_sqrt_le_real_sqrt (a := N)
      norm_num at hs ⊢
      nlinarith

/-! ## Public composition theorem -/

/-- Generic source-shaped theorem for a complete semantic certificate. -/
theorem sourceClaim_of_ordinary
    {primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    {exit : FixedState}
    (hroster :
      PrimeRosterFacts sourceCutoff primeCount primeAt)
    (hlayout :
      PrimePowerEnumerationFacts sourceCutoff primeCount primeAt
        eventCount eventAt)
    (hlogs :
      PrimeLogFacts primeCount primeAt logLowerAt logUpperAt)
    (hrun :
      runFixedEvents eventCount eventAt logLowerAt logUpperAt
        0 eventCount FixedState.zero = some exit)
    (hanchor :
      anchorOK sourceCutoff exit.weightedUpper exit.psiLower = true) :
    SourceClaim := by
  obtain ⟨hexit, hevents⟩ := runFixedEvents_sound hrun
  have hhead :=
    head_through_bound_of_event_checks hroster hlayout hlogs hevents
  constructor
  · intro N hN hNB
    rw [vonMangoldtSqrtNat_eq_mangoldtSqrtSum N hN]
    exact hhead N hN hNB
  · have hset := eventIndexSet_at_bound hlayout
    have hsumEq :=
      mangoldtSqrtSum_eq_event_sum hroster hlayout
        (N := sourceCutoff) (le_refl sourceCutoff)
    have hpsiEq :=
      psiSum_eq_event_sum hroster hlayout
        (N := sourceCutoff) (le_refl sourceCutoff)
    have hsum :
        mangoldtSqrtSum sourceCutoff ≤
          (exit.weightedUpper : Real) /
            ((scale * reciprocalScale : Nat) : Real) := by
      rw [hexit, hsumEq, hset]
      exact eventSqrtPrefix_le_fixedPrefix hroster hlayout hlogs le_rfl
    have hpsi :
        (exit.psiLower : Real) / (scale : Real) ≤
          psiSum sourceCutoff := by
      rw [hexit, hpsiEq, hset]
      exact fixedPrefix_le_eventLogPrefix hlayout hlogs le_rfl
    rw [vonMangoldtSqrtNat_eq_mangoldtSqrtSum sourceCutoff
      (by norm_num [sourceCutoff]), ← psiSum_eq_chebyshevPsi]
    exact anchor_of_fixed_enclosures
      (by norm_num [sourceCutoff]) hsum hpsi hanchor

/-- Method form of the public composition theorem. -/
theorem CertificateFacts.sourceClaim
    {primeCount : Nat} {primeAt : Nat → Nat}
    {eventCount : Nat} {eventAt : Nat → PowerEvent}
    {logLowerAt logUpperAt : Nat → Nat}
    {exit : FixedState}
    (facts : @CertificateFacts primeCount primeAt eventCount eventAt
      logLowerAt logUpperAt exit) :
    SourceClaim :=
  sourceClaim_of_ordinary facts.roster facts.layout facts.logs
    facts.run facts.anchor

end TGComputeContracts.Sqrt218

end
