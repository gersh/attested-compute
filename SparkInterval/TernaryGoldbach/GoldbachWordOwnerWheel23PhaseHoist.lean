/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWordOwnerWheel23

/-!
# Machine arithmetic for the through-23 wheel phase hoist

The qualification kernel originally evaluates several unsigned 64-bit
remainder expressions in every owner-word thread.  The host can instead pass

```
qHalfMod = (qLow >> 1) % 111546435
```

and each live thread can form `qHalfMod + 64 * wordIndex`.  For the exact
source segment, that sum is less than three wheel moduli and less than
`2^32`.  Two guarded `UInt32` subtractions therefore compute the same phase
without wraparound or division.

This file proves both the natural-number equation and its realization by
Lean's actual `UInt32` addition, multiplication, comparison, and subtraction.
It does not prove that CUDA source, NVCC, PTX/SASS, or hardware refines these
operations, and it does not select the qualification candidate in production.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachWordOwnerWheel23

/-- Literal number of represented odd inputs in the historical source
segment. -/
def sourceSegmentOddCount : Nat := 200_500_000

/-- The CUDA allocation equation, rounded up to complete 64-bit words. -/
def sourceSegmentWordCount : Nat :=
  (sourceSegmentOddCount + 63) / 64

theorem sourceSegmentWordCount_eq :
    sourceSegmentWordCount = 3_132_813 := by
  norm_num [sourceSegmentWordCount, sourceSegmentOddCount]

/-- Division-free reduction used by the phase-hoisted candidate.  Its
correctness requires the input to be below three wheel moduli. -/
def reduceWheelPhaseTwice (phase : Nat) : Nat :=
  let phase :=
    if wheelModulus ≤ phase then phase - wheelModulus else phase
  if wheelModulus ≤ phase then phase - wheelModulus else phase

theorem reduceWheelPhaseTwice_eq_mod
    {phase : Nat} (phaseBound : phase < 3 * wheelModulus) :
    reduceWheelPhaseTwice phase = phase % wheelModulus := by
  by_cases firstSub : wheelModulus ≤ phase
  · have firstPhaseBound :
        phase - wheelModulus < 2 * wheelModulus := by
      omega
    by_cases secondSub : wheelModulus ≤ phase - wheelModulus
    · have secondPhaseBound :
          phase - wheelModulus - wheelModulus < wheelModulus := by
        omega
      simp only [reduceWheelPhaseTwice, if_pos firstSub, if_pos secondSub]
      rw [Nat.mod_eq_sub_mod firstSub, Nat.mod_eq_sub_mod secondSub]
      exact (Nat.mod_eq_of_lt secondPhaseBound).symm
    · have firstPhaseSmall :
          phase - wheelModulus < wheelModulus :=
        Nat.lt_of_not_ge secondSub
      simp only [reduceWheelPhaseTwice, if_pos firstSub, if_neg secondSub]
      rw [Nat.mod_eq_sub_mod firstSub, Nat.mod_eq_of_lt firstPhaseSmall]
  · have phaseSmall : phase < wheelModulus :=
      Nat.lt_of_not_ge firstSub
    simp [reduceWheelPhaseTwice, firstSub, Nat.mod_eq_of_lt phaseSmall]

theorem sourcePhaseSum_lt_three_moduli
    {qHalfMod wordIndex : Nat}
    (qBound : qHalfMod < wheelModulus)
    (wordBound : wordIndex < sourceSegmentWordCount) :
    qHalfMod + 64 * wordIndex < 3 * wheelModulus := by
  norm_num [wheelModulus, sourceSegmentWordCount, sourceSegmentOddCount]
    at qBound wordBound ⊢
  omega

theorem sourcePhaseSum_lt_uint32Radix
    {qHalfMod wordIndex : Nat}
    (qBound : qHalfMod < wheelModulus)
    (wordBound : wordIndex < sourceSegmentWordCount) :
    qHalfMod + 64 * wordIndex < 2 ^ 32 := by
  norm_num [wheelModulus, sourceSegmentWordCount, sourceSegmentOddCount]
    at qBound wordBound ⊢
  omega

/-! ## Packed-table address bounds -/

/-- Logical period plus the 64 duplicated carry bits. -/
def wheelLogicalBitCount : Nat :=
  wheelModulus + 64

/-- Exact allocation equation used by the CUDA table. -/
def wheelPackedWordCount : Nat :=
  (wheelLogicalBitCount + 63) / 64

theorem wheelPackedWordCount_eq :
    wheelPackedWordCount = 1_742_915 := by
  norm_num [wheelPackedWordCount, wheelLogicalBitCount, wheelModulus]

def wheelLoadBase (phase : Nat) : Nat :=
  phase / 64

def wheelLoadShift (phase : Nat) : Nat :=
  phase % 64

def wheelLoadBaseUInt32 (phase : UInt32) : UInt32 :=
  phase >>> (6 : UInt32)

def wheelLoadShiftUInt32 (phase : UInt32) : UInt32 :=
  phase &&& (63 : UInt32)

def wheelLoadNextUInt32 (phase : UInt32) : UInt32 :=
  wheelLoadBaseUInt32 phase + 1

theorem wheelLoadBaseUInt32_toNat
    {phase : UInt32} {phaseNat : Nat}
    (phaseValue : phase.toNat = phaseNat) :
    (wheelLoadBaseUInt32 phase).toNat = wheelLoadBase phaseNat := by
  simp only [wheelLoadBaseUInt32, UInt32.toNat_shiftRight, phaseValue]
  rw [UInt32.toNat_ofNat]
  norm_num [wheelLoadBase, Nat.shiftRight_eq_div_pow]

theorem wheelLoadShiftUInt32_toNat
    (phase : UInt32) :
    (wheelLoadShiftUInt32 phase).toNat =
      wheelLoadShift phase.toNat := by
  simp only [wheelLoadShiftUInt32, UInt32.toNat_and]
  rw [UInt32.toNat_ofNat]
  change phase.toNat &&& 63 = phase.toNat % 64
  rw [show 63 = 2 ^ 6 - 1 by norm_num,
    Nat.and_two_pow_sub_one_eq_mod]

theorem wheelLoadBase_lt
    {phase : Nat} (phaseBound : phase < wheelModulus) :
    wheelLoadBase phase < wheelPackedWordCount := by
  rw [wheelPackedWordCount_eq]
  apply Nat.div_lt_of_lt_mul
  norm_num [wheelLoadBase, wheelModulus] at phaseBound ⊢
  omega

/-- The duplicated carry word makes the source's unconditional `base + 1`
address valid whenever a nonzero shift needs it.  In fact the bound holds for
every legal phase. -/
theorem wheelLoadBase_succ_lt
    {phase : Nat} (phaseBound : phase < wheelModulus) :
    wheelLoadBase phase + 1 < wheelPackedWordCount := by
  have baseBound : wheelLoadBase phase < 1_742_914 := by
    apply Nat.div_lt_of_lt_mul
    norm_num [wheelLoadBase, wheelModulus] at phaseBound ⊢
    omega
  rw [wheelPackedWordCount_eq]
  omega

theorem wheelLoadNextUInt32_toNat
    {phase : UInt32} {phaseNat : Nat}
    (phaseValue : phase.toNat = phaseNat)
    (phaseBound : phaseNat < wheelModulus) :
    (wheelLoadNextUInt32 phase).toNat =
      wheelLoadBase phaseNat + 1 := by
  simp only [wheelLoadNextUInt32, UInt32.toNat_add,
    wheelLoadBaseUInt32_toNat phaseValue]
  change (wheelLoadBase phaseNat + 1) % 2 ^ 32 =
    wheelLoadBase phaseNat + 1
  rw [Nat.mod_eq_of_lt]
  have addressBound := wheelLoadBase_succ_lt phaseBound
  rw [wheelPackedWordCount_eq] at addressBound
  omega

theorem wheelLoadShift_lt (phase : Nat) :
    wheelLoadShift phase < 64 :=
  Nat.mod_lt _ (by norm_num)

/-- The exact `UInt32` representation of the wheel modulus. -/
def wheelModulusUInt32 : UInt32 :=
  UInt32.ofNat wheelModulus

@[simp] theorem wheelModulusUInt32_toNat :
    wheelModulusUInt32.toNat = wheelModulus := by
  norm_num [wheelModulusUInt32, wheelModulus]

/-- Literal machine reduction proposed for the CUDA owner-word thread. -/
def reduceWheelPhaseTwiceUInt32 (phase : UInt32) : UInt32 :=
  let phase :=
    if wheelModulusUInt32 ≤ phase then
      phase - wheelModulusUInt32
    else
      phase
  if wheelModulusUInt32 ≤ phase then
    phase - wheelModulusUInt32
  else
    phase

/-- Machine comparisons and subtractions realize the natural reducer for
every `UInt32` input. -/
theorem reduceWheelPhaseTwiceUInt32_toNat
    {phase : UInt32} {phaseNat : Nat}
    (phaseValue : phase.toNat = phaseNat) :
    (reduceWheelPhaseTwiceUInt32 phase).toNat =
      reduceWheelPhaseTwice phaseNat := by
  by_cases firstSub : wheelModulus ≤ phaseNat
  · have firstSubUInt :
        wheelModulusUInt32 ≤ phase := by
      rw [UInt32.le_iff_toNat_le, wheelModulusUInt32_toNat, phaseValue]
      exact firstSub
    have firstValue :
        (phase - wheelModulusUInt32).toNat =
          phaseNat - wheelModulus := by
      rw [UInt32.toNat_sub_of_le phase wheelModulusUInt32 firstSubUInt,
        phaseValue, wheelModulusUInt32_toNat]
    by_cases secondSub :
        wheelModulus ≤ phaseNat - wheelModulus
    · have secondSubUInt :
          wheelModulusUInt32 ≤
            phase - wheelModulusUInt32 := by
        rw [UInt32.le_iff_toNat_le, wheelModulusUInt32_toNat, firstValue]
        exact secondSub
      simp only [reduceWheelPhaseTwiceUInt32, if_pos firstSubUInt,
        if_pos secondSubUInt, reduceWheelPhaseTwice, if_pos firstSub,
        if_pos secondSub]
      rw [UInt32.toNat_sub_of_le
        (phase - wheelModulusUInt32) wheelModulusUInt32 secondSubUInt,
        firstValue, wheelModulusUInt32_toNat]
    · have secondSubUInt :
          ¬wheelModulusUInt32 ≤
            phase - wheelModulusUInt32 := by
        rw [UInt32.le_iff_toNat_le, wheelModulusUInt32_toNat, firstValue]
        exact secondSub
      simp [reduceWheelPhaseTwiceUInt32, firstSubUInt, secondSubUInt,
        reduceWheelPhaseTwice, firstSub, secondSub, firstValue]
  · have firstSubUInt :
        ¬wheelModulusUInt32 ≤ phase := by
      rw [UInt32.le_iff_toNat_le, wheelModulusUInt32_toNat, phaseValue]
      exact firstSub
    simp [reduceWheelPhaseTwiceUInt32, firstSubUInt,
      reduceWheelPhaseTwice, firstSub, phaseValue]

/-- Machine phase from the host-supplied residue and the guarded owner-word
index.  Conversion to `UInt32` is part of the definition being proved. -/
def fastSourceWordPhaseUInt32
    (qHalfMod wordIndex : Nat) : UInt32 :=
  reduceWheelPhaseTwiceUInt32
    (UInt32.ofNat qHalfMod + UInt32.ofNat wordIndex * 64)

/-- Actual unsigned-64 host computation of `(qLow >> 1) % M`. -/
def hostQHalfModUInt64 (qLow : Nat) : UInt64 :=
  (UInt64.ofNat qLow >>> (1 : UInt64)) %
    UInt64.ofNat wheelModulus

theorem hostQHalfModUInt64_toNat
    {qLow : Nat} (qLowBound : qLow < 2 ^ 64) :
    (hostQHalfModUInt64 qLow).toNat =
      cudaHalf qLow % wheelModulus := by
  simp only [hostQHalfModUInt64, UInt64.toNat_mod,
    UInt64.toNat_shiftRight, UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt qLowBound]
  rw [UInt64.toNat_ofNat]
  norm_num [wheelModulus, cudaHalf]

theorem fastSourceWordPhaseUInt32_toNat
    {qHalfMod wordIndex : Nat}
    (qBound : qHalfMod < wheelModulus)
    (wordBound : wordIndex < sourceSegmentWordCount) :
    (fastSourceWordPhaseUInt32 qHalfMod wordIndex).toNat =
      (qHalfMod + 64 * wordIndex) % wheelModulus := by
  have qUint32 : qHalfMod < 2 ^ 32 := by
    norm_num [wheelModulus] at qBound ⊢
    omega
  have wordUint32 : wordIndex < 2 ^ 32 := by
    norm_num [sourceSegmentWordCount, sourceSegmentOddCount]
      at wordBound ⊢
    omega
  have productUint32 : wordIndex * 64 < 2 ^ 32 := by
    norm_num [sourceSegmentWordCount, sourceSegmentOddCount]
      at wordBound ⊢
    omega
  have sumUint32 :
      qHalfMod + wordIndex * 64 < 2 ^ 32 := by
    simpa [Nat.mul_comm] using
      sourcePhaseSum_lt_uint32Radix qBound wordBound
  have phaseValue :
      (UInt32.ofNat qHalfMod +
        UInt32.ofNat wordIndex * 64).toNat =
        qHalfMod + 64 * wordIndex := by
    simp only [UInt32.toNat_add, UInt32.toNat_mul,
      UInt32.toNat_ofNat']
    rw [Nat.mod_eq_of_lt qUint32, Nat.mod_eq_of_lt wordUint32]
    change
      (qHalfMod + (wordIndex * 64) % 2 ^ 32) % 2 ^ 32 =
        qHalfMod + 64 * wordIndex
    rw [Nat.mod_eq_of_lt productUint32]
    rw [Nat.mod_eq_of_lt (by simpa [Nat.mul_comm] using sumUint32)]
    ring
  rw [fastSourceWordPhaseUInt32,
    reduceWheelPhaseTwiceUInt32_toNat phaseValue]
  exact reduceWheelPhaseTwice_eq_mod
    (sourcePhaseSum_lt_three_moduli qBound wordBound)

/-- The division-free natural phase is exactly the generic phase already
proved to address the wheel table. -/
theorem fastSourceWordPhase_eq_cudaWordPhase
    {qLow wordIndex : Nat}
    (wordBound : wordIndex < sourceSegmentWordCount) :
    reduceWheelPhaseTwice
        (cudaHalf qLow % wheelModulus + 64 * wordIndex) =
      cudaWordPhase qLow wordIndex := by
  rw [reduceWheelPhaseTwice_eq_mod
    (sourcePhaseSum_lt_three_moduli
      (Nat.mod_lt _ wheelModulus_pos) wordBound)]
  simp [cudaWordPhase, Nat.add_mod, Nat.mul_mod, Nat.mul_comm]

/-- End-to-end machine arithmetic theorem for the phase-hoisted source
segment. -/
theorem fastSourceWordPhaseUInt32_eq_cudaWordPhase
    {qLow wordIndex : Nat}
    (wordBound : wordIndex < sourceSegmentWordCount) :
    (fastSourceWordPhaseUInt32
        (cudaHalf qLow % wheelModulus) wordIndex).toNat =
      cudaWordPhase qLow wordIndex := by
  rw [fastSourceWordPhaseUInt32_toNat
    (Nat.mod_lt _ wheelModulus_pos) wordBound]
  simp [cudaWordPhase, Nat.add_mod, Nat.mul_mod, Nat.mul_comm]

/-- Host unsigned-64 residue computation followed by the device unsigned-32
reducer equals the generic phase, assuming the source `uint64_t` input and
word-count guards. -/
theorem hostAndDeviceFastPhase_eq_cudaWordPhase
    {qLow wordIndex : Nat}
    (qLowBound : qLow < 2 ^ 64)
    (wordBound : wordIndex < sourceSegmentWordCount) :
    (fastSourceWordPhaseUInt32
        (hostQHalfModUInt64 qLow).toNat wordIndex).toNat =
      cudaWordPhase qLow wordIndex := by
  rw [hostQHalfModUInt64_toNat qLowBound]
  exact fastSourceWordPhaseUInt32_eq_cudaWordPhase wordBound

/-- Both packed-word reads selected by the optimized source phase are within
the exact `M + 64`-bit allocation. -/
theorem sourceFastPhase_load_addresses_lt
    {qLow wordIndex : Nat}
    (wordBound : wordIndex < sourceSegmentWordCount) :
    let phase :=
      (fastSourceWordPhaseUInt32
        (cudaHalf qLow % wheelModulus) wordIndex).toNat
    wheelLoadBase phase < wheelPackedWordCount ∧
      wheelLoadBase phase + 1 < wheelPackedWordCount := by
  have phaseValue :=
    fastSourceWordPhaseUInt32_eq_cudaWordPhase
      (qLow := qLow) wordBound
  have phaseBound : cudaWordPhase qLow wordIndex < wheelModulus :=
    cudaWordPhase_lt qLow wordIndex
  simp only
  rw [phaseValue]
  exact ⟨wheelLoadBase_lt phaseBound,
    wheelLoadBase_succ_lt phaseBound⟩

/-- The same address result for the literal `UInt32` shift, mask-free base,
and `base + 1` operations used by the device load. -/
theorem sourceFastPhase_machine_load_addresses_lt
    {qLow wordIndex : Nat}
    (wordBound : wordIndex < sourceSegmentWordCount) :
    let phase :=
      fastSourceWordPhaseUInt32
        (cudaHalf qLow % wheelModulus) wordIndex
    (wheelLoadBaseUInt32 phase).toNat < wheelPackedWordCount ∧
      (wheelLoadNextUInt32 phase).toNat < wheelPackedWordCount := by
  let phase :=
    fastSourceWordPhaseUInt32
      (cudaHalf qLow % wheelModulus) wordIndex
  have phaseValue :
      phase.toNat = cudaWordPhase qLow wordIndex :=
    fastSourceWordPhaseUInt32_eq_cudaWordPhase wordBound
  have phaseBound : cudaWordPhase qLow wordIndex < wheelModulus :=
    cudaWordPhase_lt qLow wordIndex
  change
    (wheelLoadBaseUInt32 phase).toNat < wheelPackedWordCount ∧
      (wheelLoadNextUInt32 phase).toNat < wheelPackedWordCount
  rw [wheelLoadBaseUInt32_toNat phaseValue,
    wheelLoadNextUInt32_toNat phaseValue phaseBound]
  exact ⟨wheelLoadBase_lt phaseBound,
    wheelLoadBase_succ_lt phaseBound⟩

#print axioms reduceWheelPhaseTwice_eq_mod
#print axioms sourceSegmentWordCount_eq
#print axioms sourcePhaseSum_lt_uint32Radix
#print axioms wheelPackedWordCount_eq
#print axioms wheelLoadBaseUInt32_toNat
#print axioms wheelLoadShiftUInt32_toNat
#print axioms wheelLoadBase_succ_lt
#print axioms wheelLoadNextUInt32_toNat
#print axioms reduceWheelPhaseTwiceUInt32_toNat
#print axioms hostQHalfModUInt64_toNat
#print axioms fastSourceWordPhaseUInt32_toNat
#print axioms fastSourceWordPhaseUInt32_eq_cudaWordPhase
#print axioms hostAndDeviceFastPhase_eq_cudaWordPhase
#print axioms sourceFastPhase_load_addresses_lt
#print axioms sourceFastPhase_machine_load_addresses_lt

end SparkInterval.TernaryGoldbach.GoldbachWordOwnerWheel23
