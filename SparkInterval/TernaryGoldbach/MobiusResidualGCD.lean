/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Squarefree
import Mathlib.NumberTheory.ArithmeticFunction.Misc
import Mathlib.Tactic

/-!
# Residual-GCD square-divisibility test

A segmented Möbius sieve may retain the product `P` of the distinct
enumerated prime divisors and write `n = P * R`.  Once both `P` and the
residual `R` are known squarefree, `n` is squarefree exactly when
`gcd(P, R) = 1`.  Thus a final per-row GCD can replace a square-divisibility
test at every prime event.

For the source sieve, the complete prime roster makes `P` squarefree and
leaves `R` equal to one or to one unenumerated prime.  Establishing those two
roster facts for a native execution remains a separate refinement obligation.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusResidualGCD

/-- The exact algebraic condition behind residual-GCD finalization. -/
theorem squarefree_product_residual_iff_gcd_eq_one
    {product residual : Nat}
    (hproduct : Squarefree product)
    (hresidual : Squarefree residual) :
    Squarefree (product * residual) ↔
      Nat.gcd product residual = 1 := by
  rw [Nat.squarefree_mul_iff, Nat.coprime_iff_gcd_eq_one]
  simp [hproduct, hresidual]

/-- For positive factors, failure of squarefreeness is exactly a GCD greater
than one, which is the branch used by the experimental CUDA finalizer. -/
theorem not_squarefree_product_residual_iff_one_lt_gcd
    {product residual : Nat}
    (hproductPositive : 0 < product)
    (hproduct : Squarefree product)
    (hresidual : Squarefree residual) :
    ¬Squarefree (product * residual) ↔
      1 < Nat.gcd product residual := by
  rw [squarefree_product_residual_iff_gcd_eq_one
    hproduct hresidual]
  have hgcdPositive :=
    Nat.gcd_pos_of_pos_left residual hproductPositive
  omega

/-- The source residual case (`1` or one prime) is automatically
squarefree. -/
theorem residual_squarefree_of_one_or_prime
    {residual : Nat}
    (hresidual : residual = 1 ∨ Nat.Prime residual) :
    Squarefree residual := by
  rcases hresidual with rfl | hprime
  · exact squarefree_one
  · exact hprime.squarefree

/-- Source-shaped residual-GCD criterion after substituting `n = P * R`. -/
theorem source_row_not_squarefree_iff_one_lt_gcd
    {number product residual : Nat}
    (hnumber : number = product * residual)
    (hproductPositive : 0 < product)
    (hproduct : Squarefree product)
    (hresidual : residual = 1 ∨ Nat.Prime residual) :
    ¬Squarefree number ↔
      1 < Nat.gcd product residual := by
  subst number
  exact not_squarefree_product_residual_iff_one_lt_gcd
    hproductPositive hproduct
    (residual_squarefree_of_one_or_prime hresidual)

/-- Under an exact quotient decomposition, the residual GCD is greater than
one exactly when some prime already present in the distinct-prime product
occurs at least twice in the source row. -/
theorem one_lt_gcd_iff_exists_product_prime_square_dvd
    {number product : Nat}
    (hproductDvd : product ∣ number)
    (hproductPositive : 0 < product)
    (hproduct : Squarefree product)
    (hresidual : Squarefree (number / product)) :
    1 < Nat.gcd product (number / product) ↔
      ∃ prime, Nat.Prime prime ∧
        prime ∣ product ∧ prime * prime ∣ number := by
  constructor
  · intro hgcd
    have hgcdNeOne :
        Nat.gcd product (number / product) ≠ 1 := by
      omega
    obtain ⟨prime, hprime, hprimeGcd⟩ :=
      Nat.exists_prime_and_dvd hgcdNeOne
    have hcommon :=
      Nat.dvd_gcd_iff.mp hprimeGcd
    refine ⟨prime, hprime, hcommon.1, ?_⟩
    have hsquare :
        prime * prime ∣ product * (number / product) :=
      Nat.mul_dvd_mul hcommon.1 hcommon.2
    simpa [Nat.mul_div_cancel' hproductDvd] using hsquare
  · rintro ⟨prime, hprime, hprimeProduct, hprimeSquare⟩
    have hnumberNotSquarefree : ¬Squarefree number := by
      intro hsquarefree
      exact
        (Nat.squarefree_iff_prime_squarefree.mp
          hsquarefree prime hprime) hprimeSquare
    have hproductNotSquarefree :
        ¬Squarefree (product * (number / product)) := by
      simpa [Nat.mul_div_cancel' hproductDvd] using
        hnumberNotSquarefree
    exact
      (not_squarefree_product_residual_iff_one_lt_gcd
        hproductPositive hproduct hresidual).mp
        hproductNotSquarefree

/-- A complete roster turns the product-local witness above into the usual
existential definition of a squareful source row. -/
theorem one_lt_gcd_iff_exists_prime_square_dvd
    {number product : Nat}
    (hproductDvd : product ∣ number)
    (hproductPositive : 0 < product)
    (hproduct : Squarefree product)
    (hresidual : Squarefree (number / product))
    (hcomplete :
      ∀ prime, Nat.Prime prime →
        prime ∣ number → prime ∣ product) :
    1 < Nat.gcd product (number / product) ↔
      ∃ prime, Nat.Prime prime ∧ prime * prime ∣ number := by
  rw [one_lt_gcd_iff_exists_product_prime_square_dvd
    hproductDvd hproductPositive hproduct hresidual]
  constructor
  · rintro ⟨prime, hprime, _, hsquare⟩
    exact ⟨prime, hprime, hsquare⟩
  · rintro ⟨prime, hprime, hsquare⟩
    have hprimeNumber : prime ∣ number :=
      (dvd_mul_right prime prime).trans hsquare
    exact
      ⟨prime, hprime,
        hcomplete prime hprime hprimeNumber, hsquare⟩

/-- When the residual is one or prime and coprime to the enumerated product,
the native `residual > 1` bit contributes exactly zero or one additional
distinct prime factor. -/
theorem cardDistinctFactors_product_residual
    {product residual : Nat}
    (hcoprime : Nat.Coprime product residual)
    (hresidual : residual = 1 ∨ Nat.Prime residual) :
    ArithmeticFunction.cardDistinctFactors
        (product * residual) =
      ArithmeticFunction.cardDistinctFactors product +
        if 1 < residual then 1 else 0 := by
  rw [ArithmeticFunction.cardDistinctFactors_mul hcoprime]
  rcases hresidual with rfl | hprime
  · simp
  · rw [
      ArithmeticFunction.cardDistinctFactors_apply_prime hprime]
    simp [hprime.one_lt]

/-- The same equality modulo two is the exact parity update used by Möbius
finalization after the residual-GCD branch has accepted squarefreeness. -/
theorem cardDistinctFactors_parity_product_residual
    {product residual : Nat}
    (hcoprime : Nat.Coprime product residual)
    (hresidual : residual = 1 ∨ Nat.Prime residual) :
    ArithmeticFunction.cardDistinctFactors
          (product * residual) % 2 =
      (ArithmeticFunction.cardDistinctFactors product +
          if 1 < residual then 1 else 0) % 2 := by
  rw [cardDistinctFactors_product_residual
    hcoprime hresidual]

#print axioms squarefree_product_residual_iff_gcd_eq_one
#print axioms not_squarefree_product_residual_iff_one_lt_gcd
#print axioms residual_squarefree_of_one_or_prime
#print axioms source_row_not_squarefree_iff_one_lt_gcd
#print axioms one_lt_gcd_iff_exists_product_prime_square_dvd
#print axioms one_lt_gcd_iff_exists_prime_square_dvd
#print axioms cardDistinctFactors_product_residual
#print axioms cardDistinctFactors_parity_product_residual

end SparkInterval.TernaryGoldbach.MobiusResidualGCD
