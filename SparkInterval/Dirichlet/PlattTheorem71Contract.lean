/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.GRHVerification

/-!
# Source-shaped target for Platt's Theorem 7.1

This file is the narrow mathematical handoff from the per-modulus verifier to
the proposition used by the ternary-Goldbach development.  It reproduces the
two parity-dependent conductor/height branches of Platt, *Numerical
computations concerning the GRH*, Theorem 7.1.

No computation is asserted here.  `plattTheorem71_of_modulus_verification`
only proves that symmetric `GRHVerifiedForModulus` results at the displayed
heights imply the expanded source proposition.  Thus an accelerated checker
has a single human-readable target, while primitive-character realization,
critical-line endpoint brackets, the Hardy-model theorem, and the total-zero
count remain visible obligations upstream.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.Dirichlet

open DirichletCharacter

/-- The even-conductor height printed in Platt Theorem 7.1. -/
def plattTheorem71EvenHeight (q : Nat) : Real :=
  max ((10 : Real) ^ (8 : Nat) / (q : Real))
    (200 + 7.5 * (10 : Real) ^ (7 : Nat) / (q : Real))

/-- The odd-conductor height printed in Platt Theorem 7.1. -/
def plattTheorem71OddHeight (q : Nat) : Real :=
  max ((10 : Real) ^ (8 : Nat) / (q : Real))
    (200 + 3.75 * (10 : Real) ^ (7 : Nat) / (q : Real))

/-- Nontrivial critical-strip zeros, expanded exactly as in the downstream
ternary-Goldbach source atom. -/
def plattNontrivialZeros {q : Nat} [NeZero q]
    (chi : DirichletCharacter Complex q) : Set Complex :=
  {rho : Complex |
    chi.LFunction rho = 0 ∧ 0 < rho.re ∧ rho.re < 1}

/-- Every nontrivial zero through an absolute ordinate height is on the
critical line. -/
def plattZerosOnCriticalLineUpTo {q : Nat} [NeZero q]
    (chi : DirichletCharacter Complex q) (height : Real) : Prop :=
  ∀ rho ∈ plattNontrivialZeros chi,
    |rho.im| ≤ height → rho.re = (1 : Real) / 2

/-- Exact two-branch source proposition of Platt Theorem 7.1. -/
def PlattTheorem71DirichletVerification : Prop :=
  (∀ (q : Nat) [NeZero q], q ≤ 400000 → q % 2 = 0 →
    ∀ chi : DirichletCharacter Complex q,
      chi.IsPrimitive →
      plattZerosOnCriticalLineUpTo chi
        (plattTheorem71EvenHeight q)) ∧
  (∀ (q : Nat) [NeZero q], q ≤ 400000 → q % 2 = 1 →
    ∀ chi : DirichletCharacter Complex q,
      chi.IsPrimitive →
      plattZerosOnCriticalLineUpTo chi
        (plattTheorem71OddHeight q))

private theorem zerosUpTo_of_modulusVerification
    {q : Nat} [NeZero q] {height : Real}
    (verified : GRHVerifiedForModulus q (-height) height)
    (chi : DirichletCharacter Complex q) (primitive : chi.IsPrimitive) :
    plattZerosOnCriticalLineUpTo chi height := by
  intro rho hrho habs
  rcases hrho with ⟨hzero, hreLower, hreUpper⟩
  have him := abs_le.mp habs
  apply verified chi primitive rho
  · rw [mem_nontrivialCriticalStrip]
    exact ⟨hreLower, hreUpper, him.1, him.2⟩
  · exact hzero

/-- Clean application boundary: source-wide symmetric per-modulus verifier
results imply the exact Platt Theorem 7.1 proposition used downstream.

The hypotheses deliberately quantify over the source modulus and every
primitive character. A finite roster theorem and the arithmetic/Turing
certificates must construct these hypotheses; neither a digest nor a sampled
run can do so. -/
theorem plattTheorem71_of_modulus_verification
    (evenVerified :
      ∀ (q : Nat) [NeZero q], q ≤ 400000 → q % 2 = 0 →
        GRHVerifiedForModulus q
          (-plattTheorem71EvenHeight q) (plattTheorem71EvenHeight q))
    (oddVerified :
      ∀ (q : Nat) [NeZero q], q ≤ 400000 → q % 2 = 1 →
        GRHVerifiedForModulus q
          (-plattTheorem71OddHeight q) (plattTheorem71OddHeight q)) :
    PlattTheorem71DirichletVerification := by
  constructor
  · intro q _ hq hparity chi hprimitive
    exact zerosUpTo_of_modulusVerification
      (evenVerified q hq hparity) chi hprimitive
  · intro q _ hq hparity chi hprimitive
    exact zerosUpTo_of_modulusVerification
      (oddVerified q hq hparity) chi hprimitive

/-- Source-scale semantic evidence with the two parity branches kept
separate.  A physical campaign must construct these universal per-modulus
results from its complete primitive-character roster; a sample or aggregate
digest cannot inhabit this structure. -/
structure PlattTheorem71SourceEvidence where
  evenVerified :
    ∀ (q : Nat) [NeZero q], q ≤ 400000 → q % 2 = 0 →
      GRHVerifiedForModulus q
        (-plattTheorem71EvenHeight q) (plattTheorem71EvenHeight q)
  oddVerified :
    ∀ (q : Nat) [NeZero q], q ≤ 400000 → q % 2 = 1 →
      GRHVerifiedForModulus q
        (-plattTheorem71OddHeight q) (plattTheorem71OddHeight q)

/-- The packaged complete campaign implies the exact source proposition. -/
theorem plattTheorem71_of_source_evidence
    (evidence : PlattTheorem71SourceEvidence) :
    PlattTheorem71DirichletVerification :=
  plattTheorem71_of_modulus_verification evidence.evenVerified
    evidence.oddVerified

end SparkInterval.Dirichlet
