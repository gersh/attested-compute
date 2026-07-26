/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer

Ported from the project-owned
`TGNativeCertificates/Sqrt218Ordinary/TailKernel.lean`.
-/
import TGComputeContracts.Sqrt218.Kernel

/-!
# Composable prime-roster extensions

This module joins semantic prime-roster extensions.  It contains no prime
table, generated gap witness, or production replay.
-/

set_option autoImplicit false

namespace TGComputeContracts.Sqrt218

/-- The final cell of a concatenated nonempty roster is the final cell of its
right-hand roster. -/
theorem appendPrimeAt_right_last
    {leftCount rightCount : Nat} {leftAt rightAt : Nat → Nat}
    (_hleft : 0 < leftCount) (hright : 0 < rightCount) :
    appendPrimeAt leftCount leftAt rightAt
        (leftCount + rightCount - 1) =
      rightAt (rightCount - 1) := by
  have hnot : ¬leftCount + rightCount - 1 < leftCount := by
    omega
  simp only [appendPrimeAt, if_neg hnot]
  congr 1
  omega

/-- Join two consecutive semantic prime-roster extensions.  The intermediate
number `middle` is a numerical partition boundary; it need not itself be
prime. -/
theorem PrimeRosterExtensionFacts.append
    {lower middle bound leftCount rightCount : Nat}
    {leftAt rightAt : Nat → Nat}
    (hleft :
      PrimeRosterExtensionFacts lower middle leftCount leftAt)
    (hright :
      PrimeRosterExtensionFacts middle bound rightCount rightAt) :
    PrimeRosterExtensionFacts lower bound (leftCount + rightCount)
      (appendPrimeAt leftCount leftAt rightAt) := by
  have hleftPos : 0 < leftCount := hleft.count_pos
  have hrightPos : 0 < rightCount := hright.count_pos
  have hmiddleBound : middle ≤ bound :=
    (hright.lower_lt_first.trans_le
      (hright.value_le 0 hrightPos)).le
  have hleftToMiddle :
      ∀ i, i < leftCount → leftAt i ≤ middle :=
    hleft.value_le
  have hfirstToRight :
      ∀ j, j < rightCount → rightAt 0 ≤ rightAt j := by
    intro j hj
    by_cases hEq : j = 0
    · simp [hEq]
    · exact
        (hright.strictMono 0 j hrightPos hj (by omega)).le
  refine
    { count_pos := by omega
      prime := ?_
      value_le := ?_
      lower_lt_first := ?_
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
        (hleft.value_le i hileft).trans hmiddleBound
    · have hiright : i - leftCount < rightCount := by omega
      simpa [appendPrimeAt, hileft] using
        hright.value_le (i - leftCount) hiright
  · simpa [appendPrimeAt, hleftPos] using hleft.lower_lt_first
  · intro i j hi hj hij
    by_cases hileft : i < leftCount
    · by_cases hjleft : j < leftCount
      · simpa [appendPrimeAt, hileft, hjleft] using
          hleft.strictMono i j hileft hjleft hij
      · have hjright : j - leftCount < rightCount := by omega
        have hcross :
            leftAt i < rightAt (j - leftCount) :=
          (hleftToMiddle i hileft).trans_lt
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
  · intro p hp hlower hpBound
    by_cases hpmiddle : p ≤ middle
    · obtain ⟨i, hi, hip⟩ :=
        hleft.cover p hp hlower hpmiddle
      refine ⟨i, by omega, ?_⟩
      simpa [appendPrimeAt, hi] using hip
    · obtain ⟨j, hj, hjp⟩ :=
        hright.cover p hp (Nat.lt_of_not_ge hpmiddle) hpBound
      refine ⟨leftCount + j, by omega, ?_⟩
      simpa [appendPrimeAt] using hjp

end TGComputeContracts.Sqrt218
