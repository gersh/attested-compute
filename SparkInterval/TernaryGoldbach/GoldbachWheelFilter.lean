/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWordOwnerSieve

/-!
# Redundant-clear theorem for the Goldbach tail wheel

The word-owner initializer clears multiples of every prime through `2039`.
For a later tail prime `p`, a progression term is `p * k`.  If `k` is
divisible by one of the selected word-owner primes through `47`, the
corresponding output bit was therefore already cleared by the initializer.
The optimized CUDA kernel may skip precisely those global atomic operations
without changing the sieve set.

This file proves that finite arithmetic reduction and the cofactor updates
used by the one-thread and 32-lane kernels.  It does not prove that CUDA,
PTX, or SASS implements the model.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachWheelFilter

open GoldbachWordOwnerSieve

/-- Cofactor primes used by the best measured diagnostic sieve-tail
optimization.  All are contained in the word-owner prefix through `2039`. -/
def filterPrimes : List Nat :=
  [3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]

/-- Mathematical meaning of the complete CUDA cofactor predicate. -/
def FilterSurvives (cofactor : Nat) : Prop :=
  ∀ prime ∈ filterPrimes, ¬ prime ∣ cofactor

/-- The implementation reduces modulo `15015` for its five factors, then
tests the remaining primes directly. -/
def KernelFilterSurvives (cofactor : Nat) : Prop :=
  ∀ prime ∈ filterPrimes,
    if prime ≤ 13 then (cofactor % 15015) % prime ≠ 0
    else cofactor % prime ≠ 0

theorem smallFilterPrime_dvd_modulus {prime : Nat}
    (hprime : prime ∈ filterPrimes) (hsmall : prime ≤ 13) :
    prime ∣ 15015 := by
  simp only [filterPrimes, List.mem_cons, List.not_mem_nil, or_false] at hprime
  have hsmallPrime :
      prime = 3 ∨ prime = 5 ∨ prime = 7 ∨ prime = 11 ∨ prime = 13 := by
    omega
  rcases hsmallPrime with rfl | rfl | rfl | rfl | rfl <;> norm_num

theorem filterPrime_le_47 {prime : Nat}
    (hprime : prime ∈ filterPrimes) :
    prime ≤ 47 := by
  simp only [filterPrimes, List.mem_cons, List.not_mem_nil, or_false] at hprime
  omega

/-- The concrete remainder tests are exactly the abstract coprimality tests;
there is no probabilistic or truncated divisibility test here. -/
theorem kernelFilterSurvives_iff (cofactor : Nat) :
    KernelFilterSurvives cofactor ↔ FilterSurvives cofactor := by
  constructor
  · intro hkernel prime hprime hdiv
    specialize hkernel prime hprime
    have hzero : cofactor % prime = 0 :=
      Nat.mod_eq_zero_of_dvd hdiv
    by_cases hsmall : prime ≤ 13
    · rw [if_pos hsmall] at hkernel
      have hmod := Nat.mod_mod_of_dvd cofactor
        (smallFilterPrime_dvd_modulus hprime hsmall)
      exact hkernel (by simpa [hmod] using hzero)
    · rw [if_neg hsmall] at hkernel
      exact hkernel hzero
  · intro hwheel prime hprime
    by_cases hsmall : prime ≤ 13
    · rw [if_pos hsmall]
      intro hzero
      apply hwheel prime hprime
      apply Nat.dvd_of_mod_eq_zero
      rw [← Nat.mod_mod_of_dvd cofactor
          (smallFilterPrime_dvd_modulus hprime hsmall)]
      exact hzero
    · rw [if_neg hsmall]
      intro hzero
      exact hwheel prime hprime (Nat.dvd_of_mod_eq_zero hzero)

/-- One-thread-per-prime cofactor update: advancing the odd multiple by
`2*p` advances the cofactor by exactly two. -/
theorem tail_cofactor_step (prime cofactor : Nat) :
    prime * cofactor + 2 * prime = prime * (cofactor + 2) := by
  ring

/-- Warp lane/round equation.  Lane `l` starts at cofactor `k + 2*l`, and
each subsequent round advances that cofactor by `64`. -/
theorem warp_cofactor_equation
    (prime firstCofactor : Nat) (lane : Fin 32) (round : Nat) :
    prime * firstCofactor +
        (2 * prime) * ((lane : Nat) + 32 * round) =
      prime *
        (firstCofactor + 2 * (lane : Nat) + 64 * round) := by
  ring

/-- Every atomic omitted by the wheel filter targets a bit already cleared by
the word-owner prefix.  The `2039 < tailPrime` and positive-cofactor
hypotheses also derive the small prime's square guard, so the result is
non-vacuous in the live sieve regime. -/
theorem rejected_tail_event_already_cleared
    (basePrimes : List Nat) (tailPrime cofactor : Nat)
    (htail : 2039 < tailPrime)
    (hcofactor : 0 < cofactor)
    (hbase : ∀ prime ∈ filterPrimes, prime ∈ basePrimes)
    (hrejected : ¬ FilterSurvives cofactor) :
    ClearedBy basePrimes (tailPrime * cofactor) := by
  simp only [FilterSurvives] at hrejected
  push Not at hrejected
  rcases hrejected with ⟨prime, hprime, hdiv⟩
  have hprime_le_47 := filterPrime_le_47 hprime
  have hprime_le_tail : prime ≤ tailPrime := by omega
  have hprime_le_cofactor : prime ≤ cofactor :=
    Nat.le_of_dvd hcofactor hdiv
  refine ⟨prime, hbase prime hprime,
    dvd_mul_of_dvd_right hdiv tailPrime, ?_⟩
  exact Nat.mul_le_mul hprime_le_tail hprime_le_cofactor

#print axioms kernelFilterSurvives_iff
#print axioms tail_cofactor_step
#print axioms warp_cofactor_equation
#print axioms rejected_tail_event_already_cleared

end SparkInterval.TernaryGoldbach.GoldbachWheelFilter
