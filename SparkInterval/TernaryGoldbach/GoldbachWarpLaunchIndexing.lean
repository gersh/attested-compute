/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Tactic
import Mathlib.Data.Nat.Bitwise
import Batteries.Data.Nat.Lemmas

/-!
# CUDA launch indexing for the optimized Goldbach warp tail

This file models the exact one-dimensional launch geometry generated for
`sieve_segment_warp_per_prime_kernel`.  In the qualified optimized source
(SHA-256
`2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c`):

* source lines 728--731 compute
  `global = blockIdx.x * 256 + threadIdx.x`,
  `warpIndex = global / 32`, and `lane = threadIdx.x & 31`;
* source line 732 returns when `warpIndex >= primeCount`; and
* source lines 1239--1249 launch
  `ceil(primeCount * 32 / 256)` threads in blocks of 256.

The checked source generator has the same formulas at
`tg_verifier/goldbach_warp_tail_optimizer.py:67-71,105-126`.

Lean proves the source's unsigned `threadIdx.x & 31` expression equals
`thread % 32`, then uses the latter as the convenient arithmetic decode.
Identifying compiled registers and bitwise instructions with these
natural-number expressions remains a machine-refinement obligation.
Everything after that identification is proved here: every
`(primeIndex,lane)` below the launch bound has exactly one active
block/thread owner, including the rounded final block.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing

/-- Literal optimized-source block size. -/
def threadsPerBlock : Nat := 256

/-- Literal NVIDIA warp width used by the source. -/
def warpWidth : Nat := 32

/-- Number of logical warp lanes launched for a retained prime prefix. -/
def launchThreadCount (primeCount : Nat) : Nat :=
  primeCount * warpWidth

/-- Overflow-free ceiling division for the source grid. -/
def launchBlocks (primeCount : Nat) : Nat :=
  let count := launchThreadCount primeCount
  if count = 0 then 0
  else 1 + (count - 1) / threadsPerBlock

/-- Literal host spelling
`(primeCount * 32 + 256 - 1) / 256`, modeled in unbounded arithmetic. -/
def sourceLaunchBlocks (primeCount : Nat) : Nat :=
  (launchThreadCount primeCount + threadsPerBlock - 1) /
    threadsPerBlock

/-- One physical coordinate in the one-dimensional launch. -/
structure ThreadCoordinate where
  block : Nat
  thread : Nat
deriving DecidableEq, Repr

/-- Source global-thread expression after the explicit `uint64_t` cast. -/
def ThreadCoordinate.globalIndex
    (coordinate : ThreadCoordinate) : Nat :=
  coordinate.block * threadsPerBlock + coordinate.thread

/-- Logical prime selected by a source thread. -/
def ThreadCoordinate.warpIndex
    (coordinate : ThreadCoordinate) : Nat :=
  coordinate.globalIndex / warpWidth

/-- Arithmetic model of source `threadIdx.x & 31`. -/
def ThreadCoordinate.lane
    (coordinate : ThreadCoordinate) : Nat :=
  coordinate.thread % warpWidth

/-- Literal natural-number model of source `threadIdx.x & 31`. -/
def ThreadCoordinate.sourceLane
    (coordinate : ThreadCoordinate) : Nat :=
  coordinate.thread &&& 31

/-- Masking by the five low one-bits is exactly remainder modulo 32.  This
discharges the source-level bit arithmetic; compiled-instruction refinement
remains separate. -/
theorem bitmask31_eq_mod32 (value : Nat) :
    value &&& 31 = value % 32 := by
  have maskBits :
      31 = Nat.ofBits (fun _ : Fin 5 => true) := by
    decide
  rw [show 32 = 2 ^ 5 by norm_num, ← Nat.ofBits_testBit value 5]
  apply Nat.eq_of_testBit_eq
  intro index
  rw [Nat.testBit_land]
  simp only [maskBits, Nat.testBit_ofBits]
  split <;> simp_all

@[simp] theorem sourceLane_eq_lane
    (coordinate : ThreadCoordinate) :
    coordinate.sourceLane = coordinate.lane := by
  simpa [ThreadCoordinate.sourceLane, ThreadCoordinate.lane, warpWidth] using
    bitmask31_eq_mod32 coordinate.thread

/-- Flat global thread required by one logical prime/lane pair. -/
def primeLaneGlobalIndex (primeIndex : Nat) (lane : Fin 32) : Nat :=
  primeIndex * warpWidth + (lane : Nat)

/-- Canonical physical owner of a logical prime/lane pair. -/
def ownerCoordinate
    (primeIndex : Nat) (lane : Fin 32) : ThreadCoordinate :=
  let index := primeLaneGlobalIndex primeIndex lane
  { block := index / threadsPerBlock
    thread := index % threadsPerBlock }

/-- Source-shaped active ownership.  The block and thread are physically
launched, and the kernel decodes the requested prime and lane. -/
def OwnsPrimeLane
    (primeCount primeIndex : Nat) (lane : Fin 32)
    (coordinate : ThreadCoordinate) : Prop :=
  coordinate.block < launchBlocks primeCount ∧
    coordinate.thread < threadsPerBlock ∧
    coordinate.warpIndex = primeIndex ∧
    coordinate.lane = (lane : Nat)

/-- Ownership with the literal source bit-mask lane expression. -/
def SourceOwnsPrimeLane
    (primeCount primeIndex : Nat) (lane : Fin 32)
    (coordinate : ThreadCoordinate) : Prop :=
  coordinate.block < launchBlocks primeCount ∧
    coordinate.thread < threadsPerBlock ∧
    coordinate.warpIndex = primeIndex ∧
    coordinate.sourceLane = (lane : Nat)

theorem sourceOwnsPrimeLane_iff
    {primeCount primeIndex : Nat} {lane : Fin 32}
    {coordinate : ThreadCoordinate} :
    SourceOwnsPrimeLane primeCount primeIndex lane coordinate ↔
      OwnsPrimeLane primeCount primeIndex lane coordinate := by
  simp only [SourceOwnsPrimeLane, OwnsPrimeLane, sourceLane_eq_lane]

theorem launchBlocks_eq_positiveFormula
    {primeCount : Nat} (positive : 0 < primeCount) :
    launchBlocks primeCount =
      1 + (launchThreadCount primeCount - 1) / threadsPerBlock := by
  have hthreads : launchThreadCount primeCount ≠ 0 := by
    simp only [launchThreadCount, warpWidth]
    omega
  simp [launchBlocks, hthreads]

/-- The overflow-free model equals the literal source ceiling expression. -/
theorem sourceLaunchBlocks_eq_launchBlocks (primeCount : Nat) :
    sourceLaunchBlocks primeCount = launchBlocks primeCount := by
  by_cases hzero : primeCount = 0
  · subst primeCount
    norm_num [sourceLaunchBlocks, launchBlocks, launchThreadCount,
      threadsPerBlock, warpWidth]
  · have hpositive : 0 < primeCount := Nat.pos_of_ne_zero hzero
    have hthreads : 0 < launchThreadCount primeCount := by
      simp only [launchThreadCount, warpWidth]
      omega
    rw [launchBlocks_eq_positiveFormula hpositive]
    have hreassociate :
        launchThreadCount primeCount + threadsPerBlock - 1 =
          threadsPerBlock + (launchThreadCount primeCount - 1) := by
      omega
    rw [sourceLaunchBlocks, hreassociate]
    have hdivides : threadsPerBlock ∣ threadsPerBlock :=
      dvd_refl threadsPerBlock
    rw [Nat.add_div_of_dvd_right hdivides]
    norm_num [threadsPerBlock]

@[simp] theorem ownerCoordinate_globalIndex
    (primeIndex : Nat) (lane : Fin 32) :
    (ownerCoordinate primeIndex lane).globalIndex =
      primeLaneGlobalIndex primeIndex lane := by
  simpa [ownerCoordinate, ThreadCoordinate.globalIndex, Nat.mul_comm] using
    Nat.div_add_mod (primeLaneGlobalIndex primeIndex lane) threadsPerBlock

theorem primeLaneGlobalIndex_lt
    {primeCount primeIndex : Nat} {lane : Fin 32}
    (inRange : primeIndex < primeCount) :
    primeLaneGlobalIndex primeIndex lane <
      launchThreadCount primeCount := by
  have hlane : (lane : Nat) < warpWidth := by
    change (lane : Nat) < 32
    exact lane.isLt
  norm_num [primeLaneGlobalIndex, launchThreadCount, warpWidth] at hlane ⊢
  omega

theorem ownerCoordinate_thread_lt
    (primeIndex : Nat) (lane : Fin 32) :
    (ownerCoordinate primeIndex lane).thread < threadsPerBlock := by
  exact Nat.mod_lt _ (by norm_num [threadsPerBlock])

theorem ownerCoordinate_block_lt
    {primeCount primeIndex : Nat} {lane : Fin 32}
    (inRange : primeIndex < primeCount) :
    (ownerCoordinate primeIndex lane).block <
      launchBlocks primeCount := by
  have hpositive : 0 < primeCount := by omega
  have hglobal :=
    primeLaneGlobalIndex_lt (lane := lane) inRange
  have hle :
      primeLaneGlobalIndex primeIndex lane ≤
        launchThreadCount primeCount - 1 := by
    omega
  rw [launchBlocks_eq_positiveFormula hpositive]
  exact lt_of_le_of_lt
    (Nat.div_le_div_right hle)
    (by omega)

/-- A bounded physical coordinate can be reconstructed from its global
thread index. -/
theorem globalIndex_injective
    {first second : ThreadCoordinate}
    (firstThread : first.thread < threadsPerBlock)
    (secondThread : second.thread < threadsPerBlock)
    (sameGlobal : first.globalIndex = second.globalIndex) :
    first = second := by
  have threadEq : first.thread = second.thread := by
    have reduced :=
      congrArg (fun value => value % threadsPerBlock) sameGlobal
    simpa [ThreadCoordinate.globalIndex, Nat.add_mod, Nat.mul_mod,
      Nat.mod_eq_of_lt firstThread, Nat.mod_eq_of_lt secondThread] using
      reduced
  have blockProducts :
      first.block * threadsPerBlock =
        second.block * threadsPerBlock := by
    rw [ThreadCoordinate.globalIndex, threadEq] at sameGlobal
    exact Nat.add_right_cancel sameGlobal
  have blockEq : first.block = second.block :=
    Nat.mul_right_cancel
      (by norm_num [threadsPerBlock]) blockProducts
  cases first
  cases second
  simp_all

/-- Because 256 is divisible by 32, the source's local lane remainder is also
the remainder of the complete global thread index. -/
theorem globalIndex_mod_warpWidth
    (coordinate : ThreadCoordinate) :
    coordinate.globalIndex % warpWidth = coordinate.lane := by
  norm_num [ThreadCoordinate.globalIndex, ThreadCoordinate.lane,
    threadsPerBlock, warpWidth, Nat.add_mod, Nat.mul_mod]

/-- Exact decode equation for any bounded source thread. -/
theorem warp_lane_decode
    (coordinate : ThreadCoordinate) :
    coordinate.warpIndex * warpWidth + coordinate.lane =
      coordinate.globalIndex := by
  have hdivision :=
    Nat.div_add_mod coordinate.globalIndex warpWidth
  rw [globalIndex_mod_warpWidth] at hdivision
  simpa [ThreadCoordinate.warpIndex, Nat.mul_comm] using hdivision

@[simp] theorem ownerCoordinate_warpIndex
    (primeIndex : Nat) (lane : Fin 32) :
    (ownerCoordinate primeIndex lane).warpIndex = primeIndex := by
  simp only [ThreadCoordinate.warpIndex, ownerCoordinate_globalIndex,
    primeLaneGlobalIndex]
  rw [Nat.add_div_of_dvd_right]
  · simp [warpWidth]
  · exact dvd_mul_left warpWidth primeIndex

@[simp] theorem ownerCoordinate_lane
    (primeIndex : Nat) (lane : Fin 32) :
    (ownerCoordinate primeIndex lane).lane = (lane : Nat) := by
  have hlane : (lane : Nat) < warpWidth := by
    change (lane : Nat) < 32
    exact lane.isLt
  have hglobal :=
    globalIndex_mod_warpWidth (ownerCoordinate primeIndex lane)
  rw [ownerCoordinate_globalIndex] at hglobal
  simpa [primeLaneGlobalIndex, Nat.add_mod, Nat.mul_mod,
    Nat.mod_eq_of_lt hlane] using hglobal.symm

/-- Every retained prime and lane has one active owner, including lanes in
the rounded final block, and no second bounded block/thread can decode to the
same pair. -/
theorem existsUnique_ownerCoordinate
    {primeCount primeIndex : Nat} {lane : Fin 32}
    (inRange : primeIndex < primeCount) :
    ∃! coordinate,
      OwnsPrimeLane primeCount primeIndex lane coordinate := by
  refine ⟨ownerCoordinate primeIndex lane, ?_, ?_⟩
  · exact ⟨ownerCoordinate_block_lt inRange,
      ownerCoordinate_thread_lt primeIndex lane,
      ownerCoordinate_warpIndex primeIndex lane,
      ownerCoordinate_lane primeIndex lane⟩
  · intro coordinate owns
    have coordinateGlobal :
        coordinate.globalIndex =
          primeLaneGlobalIndex primeIndex lane := by
      have decoded := warp_lane_decode coordinate
      rw [owns.2.2.1, owns.2.2.2] at decoded
      exact decoded.symm
    exact globalIndex_injective owns.2.1
      (ownerCoordinate_thread_lt primeIndex lane)
      (coordinateGlobal.trans
        (ownerCoordinate_globalIndex primeIndex lane).symm)

/-- The same exact completeness/duplicate-freedom result stated with the
literal source `threadIdx.x & 31` lane expression. -/
theorem existsUnique_sourceOwnerCoordinate
    {primeCount primeIndex : Nat} {lane : Fin 32}
    (inRange : primeIndex < primeCount) :
    ∃! coordinate,
      SourceOwnsPrimeLane primeCount primeIndex lane coordinate := by
  simpa only [sourceOwnsPrimeLane_iff] using
    existsUnique_ownerCoordinate (lane := lane) inRange

/-! ## Fixed-width launch bounds -/

/-- Conservative count bound derived from the production source cutoff
`WARP_PARALLEL_SIEVE_LIMIT = 32749`: a strictly increasing positive roster
can contain no more than 32749 entries below that value.  Roster validation
supplies this premise to the launch proof. -/
def maximumWarpPrimeCount : Nat := 32_749

/-- The live count bound gives at most 4,094 physical blocks. -/
theorem launchBlocks_le_productionMaximum
    {primeCount : Nat}
    (countBound : primeCount ≤ maximumWarpPrimeCount) :
    launchBlocks primeCount ≤ 4_094 := by
  by_cases hzero : primeCount = 0
  · subst primeCount
    norm_num [launchBlocks, launchThreadCount, threadsPerBlock, warpWidth]
  · have hpositive : 0 < primeCount := Nat.pos_of_ne_zero hzero
    have hthreads :
        launchThreadCount primeCount ≤
          maximumWarpPrimeCount * warpWidth := by
      exact Nat.mul_le_mul_right warpWidth countBound
    have hsub :
        launchThreadCount primeCount - 1 ≤
          maximumWarpPrimeCount * warpWidth - 1 :=
      Nat.sub_le_sub_right hthreads 1
    have hquotient :=
      Nat.div_le_div_right (c := threadsPerBlock) hsub
    rw [launchBlocks_eq_positiveFormula hpositive]
    norm_num [maximumWarpPrimeCount, warpWidth, threadsPerBlock] at hquotient ⊢
    omega

/-- All host launch arithmetic and all launched global indices fit in 32
bits, hence also in the source's explicit 64-bit temporaries.  This covers
`primeCount * 32`, its `+255` ceiling numerator, the `uint32_t` grid cast,
`blockIdx.x * 256`, and the final global-thread addition. -/
theorem productionLaunch_widthSafe
    {primeCount : Nat}
    (countBound : primeCount ≤ maximumWarpPrimeCount) :
    launchThreadCount primeCount < 2 ^ 32 ∧
      launchThreadCount primeCount + (threadsPerBlock - 1) < 2 ^ 32 ∧
      launchBlocks primeCount < 2 ^ 32 ∧
      ∀ coordinate : ThreadCoordinate,
        coordinate.block < launchBlocks primeCount →
        coordinate.thread < threadsPerBlock →
          coordinate.block * threadsPerBlock < 2 ^ 32 ∧
          coordinate.globalIndex < 2 ^ 32 ∧
          coordinate.globalIndex < 2 ^ 64 := by
  have hthreads :
      launchThreadCount primeCount ≤
        maximumWarpPrimeCount * warpWidth :=
    Nat.mul_le_mul_right warpWidth countBound
  have hblocks :
      launchBlocks primeCount ≤ 4_094 :=
    launchBlocks_le_productionMaximum countBound
  have hthreadCountWidth :
      launchThreadCount primeCount < 2 ^ 32 := by
    norm_num [maximumWarpPrimeCount, warpWidth] at hthreads ⊢
    omega
  have hnumeratorWidth :
      launchThreadCount primeCount + (threadsPerBlock - 1) < 2 ^ 32 := by
    norm_num [maximumWarpPrimeCount, warpWidth, threadsPerBlock] at hthreads ⊢
    omega
  have hblockCountWidth : launchBlocks primeCount < 2 ^ 32 := by
    norm_num at hblocks ⊢
    omega
  refine ⟨hthreadCountWidth, hnumeratorWidth, hblockCountWidth, ?_⟩
  intro coordinate hblock hthread
  have hblockValue : coordinate.block < 4_094 := by omega
  have hproduct :
      coordinate.block * threadsPerBlock < 4_094 * 256 := by
    simpa [threadsPerBlock] using
      (Nat.mul_lt_mul_right (by norm_num : 0 < 256)).2 hblockValue
  have hglobal :
      coordinate.globalIndex < 4_094 * 256 := by
    simp only [ThreadCoordinate.globalIndex]
    norm_num [threadsPerBlock] at hthread hblockValue ⊢
    omega
  refine ⟨?_, ?_, ?_⟩
  · norm_num [threadsPerBlock] at hproduct ⊢
    omega
  · norm_num at hglobal ⊢
    omega
  · norm_num at hglobal ⊢
    omega

/-- The unique canonical owner of every production-bounded prime/lane pair
inherits the launch-wide width bounds.  In particular, the flat
`primeIndex * 32 + lane` index and its block/thread reconstruction fit both
the CUDA 32-bit launch coordinates and the source's 64-bit global temporary. -/
theorem productionOwner_widthSafe
    {primeCount primeIndex : Nat} {lane : Fin 32}
    (countBound : primeCount ≤ maximumWarpPrimeCount)
    (inRange : primeIndex < primeCount) :
    primeLaneGlobalIndex primeIndex lane < 2 ^ 32 ∧
      (ownerCoordinate primeIndex lane).block * threadsPerBlock < 2 ^ 32 ∧
      (ownerCoordinate primeIndex lane).globalIndex < 2 ^ 32 ∧
      (ownerCoordinate primeIndex lane).globalIndex < 2 ^ 64 := by
  have hlaunch := productionLaunch_widthSafe countBound
  have howner := hlaunch.2.2.2 (ownerCoordinate primeIndex lane)
    (ownerCoordinate_block_lt inRange)
    (ownerCoordinate_thread_lt primeIndex lane)
  exact ⟨by
      simpa only [ownerCoordinate_globalIndex] using howner.2.1,
    howner⟩

#print axioms sourceLaunchBlocks_eq_launchBlocks
#print axioms bitmask31_eq_mod32
#print axioms sourceLane_eq_lane
#print axioms ownerCoordinate_globalIndex
#print axioms globalIndex_injective
#print axioms globalIndex_mod_warpWidth
#print axioms warp_lane_decode
#print axioms ownerCoordinate_warpIndex
#print axioms ownerCoordinate_lane
#print axioms existsUnique_ownerCoordinate
#print axioms existsUnique_sourceOwnerCoordinate
#print axioms launchBlocks_le_productionMaximum
#print axioms productionLaunch_widthSafe
#print axioms productionOwner_widthSafe

end SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing
