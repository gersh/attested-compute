/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusDenseSchedule

/-!
# Exact segment-event enumeration for the Möbius sieve

The CUDA dense and sparse kernels compute

```
remainder    = lower % prime
firstOffset  = remainder == 0 ? 0 : prime - remainder
offset(event) = firstOffset + event * prime
```

This module proves that, for a positive prime, those events enumerate each
row in the segment divisible by the prime exactly once.  Combined with
`MobiusDenseSchedule`, the theorem covers both the arithmetic event roster
and the dense block/thread partition.

This remains architecture independent: identifying CUDA registers, loops,
and memory operations with these natural-number definitions is a separate
compiled-program refinement.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule

/-- First in-segment row offset divisible by `prime`, exactly as computed by
the CUDA dense and sparse kernels. -/
def firstOffset (lower prime : Nat) : Nat :=
  let remainder := lower % prime
  if remainder = 0 then 0 else prime - remainder

theorem firstOffset_lt_prime
    (lower : Nat) {prime : Nat} (primePositive : 0 < prime) :
    firstOffset lower prime < prime := by
  rw [firstOffset]
  split_ifs with remainderZero
  · exact primePositive
  · have remainderLt := Nat.mod_lt lower primePositive
    have remainderPositive :
        0 < lower % prime := Nat.pos_of_ne_zero remainderZero
    omega

/-- The row at the first generated offset is divisible by the prime. -/
theorem firstOffset_dvd
    (lower : Nat) {prime : Nat} (primePositive : 0 < prime) :
    prime ∣ lower + firstOffset lower prime := by
  apply Nat.dvd_of_mod_eq_zero
  rw [firstOffset]
  split_ifs with remainderZero
  · simpa using remainderZero
  · have remainderLt := Nat.mod_lt lower primePositive
    have remainderPositive :
        0 < lower % prime := Nat.pos_of_ne_zero remainderZero
    have complementLt :
        prime - lower % prime < prime := by
      omega
    rw [Nat.add_mod,
      Nat.mod_eq_of_lt complementLt]
    have sumEq :
        lower % prime + (prime - lower % prime) = prime := by
      omega
    simp [sumEq]

/-- No divisible row can occur before the native first-offset formula. -/
theorem firstOffset_le_of_dvd
    {lower offset prime : Nat}
    (primePositive : 0 < prime)
    (divides : prime ∣ lower + offset) :
    firstOffset lower prime ≤ offset := by
  rw [firstOffset]
  split_ifs with remainderZero
  · exact Nat.zero_le _
  · by_contra before
    have remainderLt := Nat.mod_lt lower primePositive
    have remainderPositive :
        0 < lower % prime := Nat.pos_of_ne_zero remainderZero
    have offsetLtComplement :
        offset < prime - lower % prime := Nat.lt_of_not_ge before
    have offsetLtPrime : offset < prime := by omega
    have sumLt :
        lower % prime + offset < prime := by omega
    have generatedMod :
        (lower + offset) % prime =
          lower % prime + offset := by
      rw [Nat.add_mod, Nat.mod_eq_of_lt offsetLtPrime,
        Nat.mod_eq_of_lt sumLt]
    have zeroMod := Nat.mod_eq_zero_of_dvd divides
    rw [generatedMod] at zeroMod
    omega

/-- Every divisible row offset has an event ordinal in the native arithmetic
progression. -/
theorem exists_event_of_dvd
    {lower offset prime : Nat}
    (primePositive : 0 < prime)
    (divides : prime ∣ lower + offset) :
    ∃ event,
      multipleOffset (firstOffset lower prime) prime event =
        offset := by
  have firstLe :
      firstOffset lower prime ≤ offset :=
    firstOffset_le_of_dvd primePositive divides
  have firstDivides :
      prime ∣ lower + firstOffset lower prime :=
    firstOffset_dvd lower primePositive
  have differenceDivides :
      prime ∣ offset - firstOffset lower prime := by
    have rawDifference :
        prime ∣
          (lower + offset) -
            (lower + firstOffset lower prime) :=
      Nat.dvd_sub divides firstDivides
    have differenceEq :
        (lower + offset) -
            (lower + firstOffset lower prime) =
          offset - firstOffset lower prime := by
      omega
    rwa [differenceEq] at rawDifference
  rcases differenceDivides with ⟨event, differenceEq⟩
  refine ⟨event, ?_⟩
  calc
    multipleOffset (firstOffset lower prime) prime event =
        firstOffset lower prime + event * prime := rfl
    _ = firstOffset lower prime + prime * event := by
      rw [Nat.mul_comm]
    _ = firstOffset lower prime +
          (offset - firstOffset lower prime) := by
      rw [← differenceEq]
    _ = offset := Nat.add_sub_of_le firstLe

/-- Conversely every generated event is a row divisible by the prime. -/
theorem dvd_multipleOffset
    (lower first prime event : Nat)
    (firstDivides : prime ∣ lower + first) :
    prime ∣ lower + multipleOffset first prime event := by
  have eventDivides : prime ∣ event * prime := by
    exact dvd_mul_left prime event
  have sumDivides :
      prime ∣ (lower + first) + event * prime :=
    Nat.dvd_add firstDivides eventDivides
  simpa [multipleOffset, Nat.add_assoc] using sumDivides

/-- Exact in-segment event-roster theorem: a row is divisible by the supplied
prime iff exactly one admitted event generates its offset. -/
theorem dvd_iff_existsUnique_event
    {lower count offset prime : Nat}
    (primePositive : 0 < prime)
    (offsetInSegment : offset < count) :
    prime ∣ lower + offset ↔
      ∃! event,
        event <
            multipleEventCount count
              (firstOffset lower prime) prime ∧
          multipleOffset (firstOffset lower prime) prime event =
            offset := by
  constructor
  · intro divides
    rcases exists_event_of_dvd primePositive divides with
      ⟨event, eventEq⟩
    have firstLe :
        firstOffset lower prime ≤ offset :=
      firstOffset_le_of_dvd primePositive divides
    have firstInSegment :
        firstOffset lower prime < count := by
      omega
    have eventInRoster :
        event <
          multipleEventCount count
            (firstOffset lower prime) prime :=
      event_lt_multipleEventCount
        firstInSegment primePositive (eventEq.trans_lt offsetInSegment)
    refine ⟨event, ⟨eventInRoster, eventEq⟩, ?_⟩
    intro other otherFacts
    exact multipleOffset_injective primePositive
      (otherFacts.2.trans eventEq.symm)
  · rintro ⟨event, ⟨_, eventEq⟩, _⟩
    rw [← eventEq]
    exact dvd_multipleOffset lower
      (firstOffset lower prime) prime event
      (firstOffset_dvd lower primePositive)

#print axioms firstOffset_lt_prime
#print axioms firstOffset_dvd
#print axioms firstOffset_le_of_dvd
#print axioms exists_event_of_dvd
#print axioms dvd_multipleOffset
#print axioms dvd_iff_existsUnique_event

end SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration
