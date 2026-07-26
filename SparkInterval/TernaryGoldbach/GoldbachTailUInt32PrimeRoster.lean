/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Tactic

/-!
# Compact machine roster for the Goldbach prime-owner tail

The qualification-only CUDA candidate changes one physical representation:
the tail-prime roster is stored as `uint32_t` instead of `uint64_t`, then each
loaded entry is widened to `uint64_t` before the existing arithmetic.  The
source campaign needs primes only through `floor (sqrt 31250000000000001) =
176776695`, so this conversion is exact.

This file proves the live launch/address bounds, the actual Lean
`UInt32 -> UInt64` widening equation, and equality of every deterministic
machine continuation after the load.  It does not prove CUDA pointer
semantics, NVCC/PTX/SASS refinement, or hardware execution, and it does not
select the candidate in production.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachTailUInt32PrimeRoster

def threadsPerBlock : Nat := 256

def sourceTailPrimeCount : Nat := 9_856_924

def sourceTailPrimeLimit : Nat := 176_776_695

def sourceTailHighestPrime : Nat := 176_776_673

def sourceQHigh : Nat := 31_250_000_000_000_001

def sourceLaunchBlocks : Nat :=
  (sourceTailPrimeCount + threadsPerBlock - 1) / threadsPerBlock

theorem sourceLaunchBlocks_eq :
    sourceLaunchBlocks = 38_504 := by
  norm_num [sourceLaunchBlocks, sourceTailPrimeCount, threadsPerBlock]

theorem sourceLaunchThreadCount_eq :
    sourceLaunchBlocks * threadsPerBlock = 9_857_024 := by
  norm_num [sourceLaunchBlocks_eq, threadsPerBlock]

theorem sourceRoundedInactiveThreadCount_eq :
    sourceLaunchBlocks * threadsPerBlock - sourceTailPrimeCount = 100 := by
  norm_num [sourceLaunchBlocks_eq, threadsPerBlock, sourceTailPrimeCount]

/-- Literal one-dimensional CUDA global-thread index, after the source's
explicit widening of `blockIdx.x`. -/
def sourceGlobalIndex (block thread : Nat) : Nat :=
  block * threadsPerBlock + thread

theorem sourceGlobalIndex_lt_launch
    {block thread : Nat}
    (blockBound : block < sourceLaunchBlocks)
    (threadBound : thread < threadsPerBlock) :
    sourceGlobalIndex block thread <
      sourceLaunchBlocks * threadsPerBlock := by
  simp only [sourceGlobalIndex]
  nlinarith

theorem sourceLiveIndex_lt_uint32Radix
    {block thread : Nat}
    (blockBound : block < sourceLaunchBlocks)
    (threadBound : thread < threadsPerBlock) :
    sourceGlobalIndex block thread < 2 ^ 32 := by
  have launched :=
    sourceGlobalIndex_lt_launch blockBound threadBound
  norm_num [sourceLaunchThreadCount_eq] at launched ⊢
  omega

theorem sourceTailPrimeLimit_is_floorSqrt :
    sourceTailPrimeLimit ^ 2 ≤ sourceQHigh ∧
      sourceQHigh < (sourceTailPrimeLimit + 1) ^ 2 := by
  norm_num [sourceTailPrimeLimit, sourceQHigh]

theorem sourceTailPrimeLimit_lt_uint32Radix :
    sourceTailPrimeLimit < 2 ^ 32 := by
  norm_num [sourceTailPrimeLimit]

theorem sourceTailHighestPrime_le_limit :
    sourceTailHighestPrime ≤ sourceTailPrimeLimit := by
  norm_num [sourceTailHighestPrime, sourceTailPrimeLimit]

/-- Current physical load: one eight-byte roster element. -/
def widePrimeLoad (prime : Nat) : UInt64 :=
  UInt64.ofNat prime

/-- Candidate physical load: one four-byte roster element, widened before any
of the existing 64-bit arithmetic. -/
def compactPrimeLoad (prime : Nat) : UInt64 :=
  (UInt32.ofNat prime).toUInt64

theorem compactPrimeLoad_eq_widePrimeLoad
    {prime : Nat} (primeBound : prime < 2 ^ 32) :
    compactPrimeLoad prime = widePrimeLoad prime := by
  apply UInt64.ext
  simp only [compactPrimeLoad, UInt32.toNat_toUInt64,
    UInt32.toNat_ofNat', widePrimeLoad, UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt primeBound]
  exact (Nat.mod_eq_of_lt (by omega)).symm

theorem qualifiedPrime_compactLoad_eq
    {prime : Nat} (primeBound : prime ≤ sourceTailPrimeLimit) :
    compactPrimeLoad prime = widePrimeLoad prime := by
  apply compactPrimeLoad_eq_widePrimeLoad
  exact lt_of_le_of_lt primeBound sourceTailPrimeLimit_lt_uint32Radix

/-- If the widened load is equal, every deterministic continuation containing
the unchanged division, remainder, square, step, wheel tests, bit indexing,
and atomic clear arguments is equal as well. -/
theorem machineContinuation_eq
    {α : Sort _} (continuation : UInt64 → α)
    {prime : Nat} (primeBound : prime ≤ sourceTailPrimeLimit) :
    continuation (compactPrimeLoad prime) =
      continuation (widePrimeLoad prime) := by
  rw [qualifiedPrime_compactLoad_eq primeBound]

/-- Explicit prefix of the source machine arithmetic.  This is not used as a
semantic shortcut: it records the literal unsigned division, remainder,
multiplication, and doubled-step operations that consume the widened load. -/
structure TailPrimeMachineHead where
  prime : UInt64
  qLowDivPrime : UInt64
  qLowModPrime : UInt64
  qHighDivPrime : UInt64
  square : UInt64
  doubledStep : UInt64
deriving DecidableEq, Repr

def tailPrimeMachineHead
    (qLow qHigh prime : UInt64) : TailPrimeMachineHead where
  prime := prime
  qLowDivPrime := qLow / prime
  qLowModPrime := qLow % prime
  qHighDivPrime := qHigh / prime
  square := prime * prime
  doubledStep := 2 * prime

theorem compactTailPrimeMachineHead_eq
    (qLow qHigh : UInt64) {prime : Nat}
    (primeBound : prime ≤ sourceTailPrimeLimit) :
    tailPrimeMachineHead qLow qHigh (compactPrimeLoad prime) =
      tailPrimeMachineHead qLow qHigh (widePrimeLoad prime) :=
  machineContinuation_eq
    (tailPrimeMachineHead qLow qHigh) primeBound

/-- Abstract roster contents indexed by the same live `Fin count` in both
physical representations. -/
def wideRosterLoad
    {count : Nat} (roster : Fin count → Nat)
    (index : Fin count) : UInt64 :=
  widePrimeLoad (roster index)

def compactRosterLoad
    {count : Nat} (roster : Fin count → Nat)
    (index : Fin count) : UInt64 :=
  compactPrimeLoad (roster index)

theorem compactRosterLoad_eq_wideRosterLoad
    {count : Nat} {roster : Fin count → Nat}
    (rosterBound : ∀ index, roster index ≤ sourceTailPrimeLimit)
    (index : Fin count) :
    compactRosterLoad roster index = wideRosterLoad roster index := by
  exact qualifiedPrime_compactLoad_eq (rosterBound index)

theorem liveSourceIndex_has_same_load
    {roster : Fin sourceTailPrimeCount → Nat}
    (rosterBound : ∀ index, roster index ≤ sourceTailPrimeLimit)
    {block thread : Nat}
    (live : sourceGlobalIndex block thread < sourceTailPrimeCount) :
    compactRosterLoad roster ⟨sourceGlobalIndex block thread, live⟩ =
      wideRosterLoad roster ⟨sourceGlobalIndex block thread, live⟩ :=
  compactRosterLoad_eq_wideRosterLoad rosterBound _

def compactRosterBytes (count : Nat) : Nat := count * 4

def wideRosterBytes (count : Nat) : Nat := count * 8

theorem sourceCompactRosterBytes_eq :
    compactRosterBytes sourceTailPrimeCount = 39_427_696 := by
  norm_num [compactRosterBytes, sourceTailPrimeCount]

theorem sourceWideRosterBytes_eq :
    wideRosterBytes sourceTailPrimeCount = 78_855_392 := by
  norm_num [wideRosterBytes, sourceTailPrimeCount]

theorem sourceCompactRosterBytes_twice_eq_wide :
    2 * compactRosterBytes sourceTailPrimeCount =
      wideRosterBytes sourceTailPrimeCount := by
  norm_num [compactRosterBytes, wideRosterBytes, sourceTailPrimeCount]

def compactByteOffset (index : Nat) : Nat := index * 4

def wideByteOffset (index : Nat) : Nat := index * 8

theorem compactByteOffset_lt
    {index count : Nat} (live : index < count) :
    compactByteOffset index < compactRosterBytes count := by
  simp only [compactByteOffset, compactRosterBytes]
  omega

theorem wideByteOffset_lt
    {index count : Nat} (live : index < count) :
    wideByteOffset index < wideRosterBytes count := by
  simp only [wideByteOffset, wideRosterBytes]
  omega

/-- Actual unsigned-64 address-scale operation used after the source global
index has been widened. -/
def compactByteOffsetUInt64 (index : Nat) : UInt64 :=
  UInt64.ofNat index * 4

theorem compactByteOffsetUInt64_toNat
    {index : Nat} (live : index < sourceTailPrimeCount) :
    (compactByteOffsetUInt64 index).toNat =
      compactByteOffset index := by
  have indexBound : index < 2 ^ 64 := by
    norm_num [sourceTailPrimeCount] at live ⊢
    omega
  have productBound : index * 4 < 2 ^ 64 := by
    norm_num [sourceTailPrimeCount] at live ⊢
    omega
  simp only [compactByteOffsetUInt64, UInt64.toNat_mul,
    UInt64.toNat_ofNat', UInt64.toNat_ofNat, compactByteOffset]
  rw [Nat.mod_eq_of_lt indexBound]
  norm_num
  norm_num at productBound ⊢
  exact productBound

theorem compactMachineByteOffset_lt
    {index : Nat} (live : index < sourceTailPrimeCount) :
    (compactByteOffsetUInt64 index).toNat <
      compactRosterBytes sourceTailPrimeCount := by
  rw [compactByteOffsetUInt64_toNat live]
  exact compactByteOffset_lt live

end SparkInterval.TernaryGoldbach.GoldbachTailUInt32PrimeRoster
