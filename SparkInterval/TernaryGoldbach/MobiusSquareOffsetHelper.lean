/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

/-!
# Exact model of the CUDA square-offset helper

The live CUDA `first_square_offset` helper computes

```
remainder = lower % q
first     = remainder == 0 ? 0 : q - remainder
if (first >= count) return false
*offset = first
return true
```

Here `q` is a positive prime square.  `cudaFirst` models the value computed
before the final range test, and `firstSquareOffset` uses `Option` to model the
Boolean return together with the output pointer.

An earlier experimental version considered an `upper` test and special
quotient-2-through-8 branches.  That experiment is not present in the live
source and is deliberately not modeled or certified here.

The main results prove that:

* the returned value is exactly `MobiusSegmentEventEnumeration.firstOffset`;
* failure is equivalent to the absence of a divisible row in the segment;
* success returns the unique least divisible row; and
* the subsequent `offset += q` loop enumerates every divisible row exactly
  once.

The production guards at the end record the current `10^16` source/divisor
cap and `10^8` segment cap.  They prove that the helper result, `lower +
offset`, and the loop's next `offset + q` are all representable in `uint64`.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

/-- Value assigned to the CUDA helper's local `first` variable. -/
def cudaFirst (lower q : Nat) : Nat :=
  let remainder := lower % q
  if remainder = 0 then 0 else q - remainder

/-- Boolean/output-pointer behavior of the live CUDA helper. -/
def firstSquareOffset (lower count q : Nat) : Option Nat :=
  let first := cudaFirst lower q
  if first ≥ count then none else some first

/-- The helper repeats the exact canonical first-offset formula. -/
@[simp] theorem cudaFirst_eq_firstOffset (lower q : Nat) :
    cudaFirst lower q = firstOffset lower q := rfl

/-- A successful helper call returns the canonical offset, and that offset is
strictly inside the segment. -/
theorem firstSquareOffset_eq_some_iff
    {lower count q offset : Nat} :
    firstSquareOffset lower count q = some offset ↔
      offset = firstOffset lower q ∧ firstOffset lower q < count := by
  simp only [firstSquareOffset, cudaFirst_eq_firstOffset]
  split_ifs with outside
  · constructor
    · intro impossible
      cases impossible
    · rintro ⟨_, inside⟩
      omega
  · simp only [Option.some.injEq]
    constructor
    · intro offsetEq
      exact ⟨offsetEq.symm, Nat.lt_of_not_ge outside⟩
    · rintro ⟨offsetEq, _⟩
      exact offsetEq.symm

/-- The CUDA helper fails exactly when the canonical first offset lies
outside the segment. -/
theorem firstSquareOffset_eq_none_iff
    {lower count q : Nat} :
    firstSquareOffset lower count q = none ↔
      count ≤ firstOffset lower q := by
  simp [firstSquareOffset]

/-- Success returns the first row in the segment divisible by `q`, with no
divisible row before it. -/
theorem firstSquareOffset_eq_some_iff_unique_least
    {lower count q offset : Nat}
    (qPositive : 0 < q) :
    firstSquareOffset lower count q = some offset ↔
      offset < count ∧
        q ∣ lower + offset ∧
        ∀ earlier, earlier < offset → ¬ q ∣ lower + earlier := by
  constructor
  · intro result
    have facts := firstSquareOffset_eq_some_iff.mp result
    have offsetEq : offset = firstOffset lower q := facts.1
    refine ⟨offsetEq ▸ facts.2, offsetEq ▸ firstOffset_dvd lower qPositive, ?_⟩
    intro earlier earlierLt earlierDivides
    have canonicalLeEarlier :
        firstOffset lower q ≤ earlier :=
      firstOffset_le_of_dvd qPositive earlierDivides
    omega
  · rintro ⟨offsetInSegment, offsetDivides, noEarlier⟩
    have canonicalLeOffset :
        firstOffset lower q ≤ offset :=
      firstOffset_le_of_dvd qPositive offsetDivides
    have offsetLeCanonical : offset ≤ firstOffset lower q := by
      by_contra notLe
      have canonicalEarlier : firstOffset lower q < offset :=
        Nat.lt_of_not_ge notLe
      exact noEarlier
        (firstOffset lower q) canonicalEarlier
        (firstOffset_dvd lower qPositive)
    have offsetEq : offset = firstOffset lower q :=
      Nat.le_antisymm offsetLeCanonical canonicalLeOffset
    exact firstSquareOffset_eq_some_iff.mpr
      ⟨offsetEq, offsetEq ▸ offsetInSegment⟩

/-- The helper succeeds iff the segment contains a row divisible by `q`. -/
theorem exists_firstSquareOffset_iff_exists_dvd
    {lower count q : Nat}
    (qPositive : 0 < q) :
    (∃ offset, firstSquareOffset lower count q = some offset) ↔
      ∃ offset, offset < count ∧ q ∣ lower + offset := by
  constructor
  · rintro ⟨offset, result⟩
    have facts :=
      (firstSquareOffset_eq_some_iff_unique_least qPositive).mp result
    exact ⟨offset, facts.1, facts.2.1⟩
  · rintro ⟨offset, offsetInSegment, offsetDivides⟩
    have canonicalInSegment : firstOffset lower q < count := by
      have canonicalLeOffset :
          firstOffset lower q ≤ offset :=
        firstOffset_le_of_dvd qPositive offsetDivides
      omega
    exact ⟨firstOffset lower q,
      firstSquareOffset_eq_some_iff.mpr
        ⟨rfl, canonicalInSegment⟩⟩

/-- Returning `false` is equivalent to there being no `q`-multiple in the
half-open segment `[lower, lower + count)`. -/
theorem firstSquareOffset_eq_none_iff_no_dvd
    {lower count q : Nat}
    (qPositive : 0 < q) :
    firstSquareOffset lower count q = none ↔
      ∀ offset, offset < count → ¬ q ∣ lower + offset := by
  constructor
  · intro result offset offsetInSegment offsetDivides
    have countLeCanonical :
        count ≤ firstOffset lower q :=
      firstSquareOffset_eq_none_iff.mp result
    have canonicalLeOffset :
        firstOffset lower q ≤ offset :=
      firstOffset_le_of_dvd qPositive offsetDivides
    omega
  · intro noDivisible
    apply firstSquareOffset_eq_none_iff.mpr
    by_contra canonicalNotOutside
    have canonicalInSegment :
        firstOffset lower q < count :=
      Nat.lt_of_not_ge canonicalNotOutside
    exact noDivisible
      (firstOffset lower q) canonicalInSegment
      (firstOffset_dvd lower qPositive)

/-- Once the helper returns `first`, the CUDA `offset += q` loop enumerates
every divisible in-segment row exactly once. -/
theorem returned_offset_dvd_iff_existsUnique_loop_event
    {lower count q first offset : Nat}
    (qPositive : 0 < q)
    (result : firstSquareOffset lower count q = some first)
    (offsetInSegment : offset < count) :
    q ∣ lower + offset ↔
      ∃! event,
        event < multipleEventCount count first q ∧
          multipleOffset first q event = offset := by
  have firstEq :
      first = firstOffset lower q :=
    (firstSquareOffset_eq_some_iff.mp result).1
  subst first
  exact dvd_iff_existsUnique_event qPositive offsetInSegment

/-! ## Production-width guards -/

/-- Largest source value used by the Hurst campaign. -/
def productionSourceLimit : Nat := 10_000_000_000_000_000

/-- Largest row count in one production segment. -/
def productionSegmentLimit : Nat := 100_000_000

/-- Largest value representable by the CUDA `std::uint64_t` fields. -/
def uint64Max : Nat := 18_446_744_073_709_551_615

/-- Explicit domain facts required when relating the natural-number helper
and loop arithmetic to the live CUDA machine integers. -/
structure ProductionGuards (lower count q : Nat) : Prop where
  countPositive : 0 < count
  qPositive : 0 < q
  lowerBound : lower ≤ productionSourceLimit
  countBound : count ≤ productionSegmentLimit
  qBound : q ≤ productionSourceLimit

/-- The remainder is strictly below `q`, so the nonzero branch's unsigned
subtraction `q - remainder` cannot underflow. -/
theorem remainder_lt_q
    {lower count q : Nat}
    (guards : ProductionGuards lower count q) :
    lower % q < q :=
  Nat.mod_lt lower guards.qPositive

/-- The helper's local `first` value fits in `uint64`, including on the
failure path. -/
theorem cudaFirst_le_uint64Max
    {lower count q : Nat}
    (guards : ProductionGuards lower count q) :
    cudaFirst lower q ≤ uint64Max := by
  have firstLtQ :
      cudaFirst lower q < q := by
    simpa using firstOffset_lt_prime lower guards.qPositive
  calc
    cudaFirst lower q ≤ q := Nat.le_of_lt firstLtQ
    _ ≤ productionSourceLimit := guards.qBound
    _ ≤ uint64Max := by
      norm_num [productionSourceLimit, uint64Max]

/-- A returned offset is representable in both `size_t` and `uint64`. -/
theorem returned_offset_le_uint64Max
    {lower count q offset : Nat}
    (guards : ProductionGuards lower count q)
    (result : firstSquareOffset lower count q = some offset) :
    offset ≤ uint64Max := by
  have offsetInSegment :
      offset < count :=
    (firstSquareOffset_eq_some_iff.mp result).1 ▸
      (firstSquareOffset_eq_some_iff.mp result).2
  calc
    offset ≤ count := Nat.le_of_lt offsetInSegment
    _ ≤ productionSegmentLimit := guards.countBound
    _ ≤ uint64Max := by
      norm_num [productionSegmentLimit, uint64Max]

/-- Forming the mathematical row `lower + offset` cannot overflow `uint64`
for a returned production offset. -/
theorem returned_number_le_uint64Max
    {lower count q offset : Nat}
    (guards : ProductionGuards lower count q)
    (result : firstSquareOffset lower count q = some offset) :
    lower + offset ≤ uint64Max := by
  have offsetInSegment :
      offset < count :=
    (firstSquareOffset_eq_some_iff.mp result).1 ▸
      (firstSquareOffset_eq_some_iff.mp result).2
  calc
    lower + offset ≤
        productionSourceLimit + productionSegmentLimit :=
      Nat.add_le_add guards.lowerBound
        (le_trans (Nat.le_of_lt offsetInSegment) guards.countBound)
    _ ≤ uint64Max := by
      norm_num [productionSourceLimit, productionSegmentLimit, uint64Max]

/-- After any admitted loop body, the native update `offset += q` is also
representable.  This covers the final update that makes the loop condition
false, not merely the offsets used to index the segment. -/
theorem loop_increment_le_uint64Max
    {lower count q first event : Nat}
    (guards : ProductionGuards lower count q)
    (eventInSegment :
      multipleOffset first q event < count) :
    multipleOffset first q event + q ≤ uint64Max := by
  calc
    multipleOffset first q event + q ≤
        productionSegmentLimit + productionSourceLimit :=
      Nat.add_le_add
        (le_trans (Nat.le_of_lt eventInSegment) guards.countBound)
        guards.qBound
    _ ≤ uint64Max := by
      norm_num [productionSourceLimit, productionSegmentLimit, uint64Max]

#print axioms cudaFirst_eq_firstOffset
#print axioms firstSquareOffset_eq_some_iff
#print axioms firstSquareOffset_eq_some_iff_unique_least
#print axioms exists_firstSquareOffset_iff_exists_dvd
#print axioms firstSquareOffset_eq_none_iff_no_dvd
#print axioms returned_offset_dvd_iff_existsUnique_loop_event
#print axioms loop_increment_le_uint64Max

end SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper
