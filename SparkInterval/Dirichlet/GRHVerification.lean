import SparkInterval.Dirichlet.HardyContract

/-!
# Finite GRH verification statements per modulus

Platt's Theorem 7.1 (arXiv:1305.3087) has the shape "GRH holds for all
Dirichlet L-functions of primitive character modulus `q ≤ 400000` up to a
`q`-dependent height".  This file states the per-modulus building block:
every primitive character of the modulus has all its L-function zeros in
the checked rectangle on the critical line.

Primitive characters of modulus at least 2 are nontrivial, so the
per-character verifier applies to each of them.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open DirichletCharacter

variable {N : ℕ} [NeZero N]

/-- For modulus at least 2, a primitive character is nontrivial: the
trivial character has conductor 1. -/
theorem ne_one_of_isPrimitive (hN : 2 ≤ N)
    {χ : DirichletCharacter ℂ N} (hχ : χ.IsPrimitive) : χ ≠ 1 := by
  intro h1
  have hcond : χ.conductor = N := hχ
  rw [h1, conductor_one] at hcond
  omega

/-- Finite GRH verification statement for one modulus and one rectangle:
every zero of every primitive-character L-function in the closed rectangle
`[0,1] x [lo,hi]` lies on the critical line. -/
def GRHVerifiedForModulus (N : ℕ) [NeZero N] (lo hi : ℝ) : Prop :=
  ∀ χ : DirichletCharacter ℂ N, χ.IsPrimitive →
    ∀ z ∈ criticalStrip lo hi, χ.LFunction z = 0 → z.re = (1 : ℝ) / 2

/-- Per-modulus assembly: individual per-character conclusions aggregate to
the modulus-level statement. -/
theorem grhVerifiedForModulus_of_characters {lo hi : ℝ}
    (h : ∀ χ : DirichletCharacter ℂ N, χ.IsPrimitive →
      ∀ z ∈ criticalStrip lo hi, χ.LFunction z = 0 → z.re = (1 : ℝ) / 2) :
    GRHVerifiedForModulus N lo hi :=
  h

end SparkInterval.Dirichlet
