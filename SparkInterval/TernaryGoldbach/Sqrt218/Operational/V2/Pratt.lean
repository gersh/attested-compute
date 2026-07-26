/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.List.Dedup
import Mathlib.Data.List.Prime
import Mathlib.Data.Nat.Prime.Basic
import Mathlib.NumberTheory.LucasPrimality

/-!
# Data-independent Lucas/Pratt kernel for Sqrt218 V2

This file contains the small mathematical kernel used by the V2 prime-roster
checker.  It has no production rows and performs no closed large computation.
A concrete row supplies the complete factorization of `p - 1`, with
multiplicity, and a Lucas witness.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

/-- Repeated-squaring exponentiation in `ZMod p`. -/
def fastPow (p a exponent : Nat) : ZMod p :=
  npowBinRec exponent (a : ZMod p)

/-- The executable repeated-squaring operation agrees with ordinary power. -/
theorem fastPow_eq_pow (p a exponent : Nat) :
    fastPow p a exponent = (a : ZMod p) ^ exponent := by
  unfold fastPow
  rw [← npowBinRecAuto, ← npowRec_eq_npowBinRec]
  induction exponent with
  | zero =>
      simp only [npowRecAuto, npowRec, pow_zero]
  | succ exponent inductionHypothesis =>
      simp only [npowRecAuto, npowRec, pow_succ, inductionHypothesis]

/-- Executable modular-residue part of a Lucas certificate. -/
def lucasResidueCheck (p witness : Nat) (primeFactors : List Nat) : Bool :=
  decide (fastPow p witness (p - 1) = 1) &&
    primeFactors.all fun factor =>
      decide (fastPow p witness ((p - 1) / factor) ≠ 1)

theorem lucasResidueCheck_sound
    {p witness : Nat} {primeFactors : List Nat}
    (hcheck : lucasResidueCheck p witness primeFactors = true) :
    fastPow p witness (p - 1) = 1 ∧
      ∀ factor, factor ∈ primeFactors →
        fastPow p witness ((p - 1) / factor) ≠ 1 := by
  simpa only [lucasResidueCheck, Bool.and_eq_true, decide_eq_true_eq,
    List.all_eq_true] using hcheck

/-- Lucas primality from a complete prime factor list for `p - 1`.

`factors` contains multiplicities.  Residues are checked only for the
deduplicated list. -/
theorem prime_of_lucas_factor_list
    (p witness : Nat) (factors : List Nat)
    (hproduct : factors.prod = p - 1)
    (hprime : ∀ factor, factor ∈ factors → factor.Prime)
    (hresidue :
      lucasResidueCheck p witness factors.dedup = true) :
    p.Prime := by
  have hresidueFacts := lucasResidueCheck_sound hresidue
  apply lucas_primality p (witness : ZMod p)
  · rw [← fastPow_eq_pow]
    exact hresidueFacts.1
  · intro factor hfactorPrime hfactorDvd
    have hfactorProduct : factor ∣ factors.prod := by
      rw [hproduct]
      exact hfactorDvd
    have hfactorMember : factor ∈ factors := by
      exact mem_list_primes_of_dvd_prod
        (Nat.prime_iff.mp hfactorPrime)
        (fun candidate hcandidate =>
          Nat.prime_iff.mp (hprime candidate hcandidate))
        hfactorProduct
    have hfactorDedup : factor ∈ factors.dedup :=
      List.mem_dedup.mpr hfactorMember
    rw [← fastPow_eq_pow]
    exact hresidueFacts.2 factor hfactorDedup

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
