/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.Complex
import SparkInterval.Certified.ComplexDisk

/-!
# Arithmetic bridge for factored small-conductor seeds

The source-scale small-`q` implementation stores one character phase `epsilon`
and one parity-dependent base prefactor instead of repeating their product at
every `(character, frequency)` pair.  This file proves the two algebraic facts
used by that optimization:

* multiplying independently enclosing complex rectangles encloses the full
  character prefactor; and
* the finite-Gaussian recurrence used by the CUDA kernel has state
  `z = w^(n+1)^2`, `ratio = w^(2(n+1)+1)` after `n` updates.

These are ordinary, axiom-free Lean theorems about the arithmetic algorithm.
They do not assert that a binary parser decoded a version-3 frame or that an
H100 implements the modeled directed operations; those are separate
certificate and compiled-artifact refinement edges.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQSeed

open SparkInterval.Certified

/-- The two independently certified factors stored by a version-3 seed. -/
structure PrefactorCertificate where
  parityBase : ComplexRect
  epsilon : ComplexRect

namespace PrefactorCertificate

/-- Exact rectangular multiplication used when expanding a factored seed. -/
def expand (certificate : PrefactorCertificate) : ComplexRect :=
  certificate.parityBase.mul certificate.epsilon

/-- The factored representation contains the same mathematical prefactor as
the former per-character representation. -/
theorem expand_contains {certificate : PrefactorCertificate}
    {parityBase epsilon : ℂ}
    (hbase : certificate.parityBase.ContainsComplex parityBase)
    (hepsilon : certificate.epsilon.ContainsComplex epsilon) :
    certificate.expand.ContainsComplex (parityBase * epsilon) :=
  ComplexRect.mul_containsComplex hbase hepsilon

end PrefactorCertificate

/-! ## Exact disk-wire specialization -/

/-- The actual version-3 CUDA frame stores disks, not rectangles.  This
wrapper requires the proposed parity/epsilon expansion to pass the independent
exact-rational multiplication checker. -/
structure DiskPrefactorCertificate where
  multiplication : ComplexDisk.MulCertificate

namespace DiskPrefactorCertificate

def parityBase (certificate : DiskPrefactorCertificate) : ComplexDisk :=
  certificate.multiplication.left

def epsilon (certificate : DiskPrefactorCertificate) : ComplexDisk :=
  certificate.multiplication.right

def expanded (certificate : DiskPrefactorCertificate) : ComplexDisk :=
  certificate.multiplication.output

def check (certificate : DiskPrefactorCertificate) : Bool :=
  certificate.multiplication.check

/-- Clean arithmetic tie-in for the factored wire format: an accepted rational
witness turns containment of the two independently generated factors into
containment of their product. -/
theorem expanded_contains {certificate : DiskPrefactorCertificate}
    {parityBase epsilon : ℂ}
    (hcheck : certificate.check = true)
    (hbase : certificate.parityBase.ContainsComplex parityBase)
    (hepsilon : certificate.epsilon.ContainsComplex epsilon) :
    certificate.expanded.ContainsComplex (parityBase * epsilon) :=
  ComplexDisk.MulCertificate.output_contains_mul hcheck hbase hepsilon

end DiskPrefactorCertificate

/-- Exact state of the recurrence before evaluating the next Gaussian term. -/
structure ExactGaussianState where
  z : ℂ
  ratio : ℂ

namespace ExactGaussianState

def initial (w : ℂ) : ExactGaussianState :=
  ⟨w, w ^ 3⟩

def step (w : ℂ) (state : ExactGaussianState) : ExactGaussianState :=
  ⟨state.z * state.ratio, state.ratio * w ^ 2⟩

def after (w : ℂ) : ℕ → ExactGaussianState
  | 0 => initial w
  | n + 1 => step w (after w n)

/-- Closed form for both recurrence components.  The `z` component therefore
equals the Gaussian power consumed for term `n + 1`. -/
theorem after_eq_powers (w : ℂ) : ∀ n : ℕ,
    (after w n).z = w ^ ((n + 1) ^ 2) ∧
    (after w n).ratio = w ^ (2 * (n + 1) + 1)
  | 0 => by simp [after, initial]
  | n + 1 => by
      rw [after, step]
      have ih := after_eq_powers w n
      constructor
      · rw [ih.1, ih.2, ← pow_add]
        ring
      · rw [ih.2, ← pow_add]
        congr 1

end ExactGaussianState

/-- Rectangle state computed by the certified arithmetic implementation. -/
structure RectGaussianState where
  z : ComplexRect
  ratio : ComplexRect

namespace RectGaussianState

def initial (W : ComplexRect) : RectGaussianState :=
  ⟨W, (W.mul W).mul W⟩

def step (W : ComplexRect) (state : RectGaussianState) : RectGaussianState :=
  ⟨state.z.mul state.ratio, state.ratio.mul (W.mul W)⟩

def after (W : ComplexRect) : ℕ → RectGaussianState
  | 0 => initial W
  | n + 1 => step W (after W n)

def ContainsState (rectangle : RectGaussianState)
    (exact : ExactGaussianState) : Prop :=
  rectangle.z.ContainsComplex exact.z ∧
  rectangle.ratio.ContainsComplex exact.ratio

theorem initial_contains {W : ComplexRect} {w : ℂ}
    (hw : W.ContainsComplex w) :
    (initial W).ContainsState (ExactGaussianState.initial w) := by
  constructor
  · exact hw
  · simpa [initial, ExactGaussianState.initial, pow_succ] using
      ComplexRect.mul_containsComplex
        (ComplexRect.mul_containsComplex hw hw) hw

theorem step_contains {W : ComplexRect} {w : ℂ}
    {rectangle : RectGaussianState} {exact : ExactGaussianState}
    (hw : W.ContainsComplex w)
    (hstate : rectangle.ContainsState exact) :
    (step W rectangle).ContainsState (ExactGaussianState.step w exact) := by
  constructor
  · exact ComplexRect.mul_containsComplex hstate.1 hstate.2
  · exact ComplexRect.mul_containsComplex hstate.2
      (by simpa [pow_two] using ComplexRect.mul_containsComplex hw hw)

theorem after_contains {W : ComplexRect} {w : ℂ}
    (hw : W.ContainsComplex w) : ∀ n : ℕ,
    (after W n).ContainsState (ExactGaussianState.after w n)
  | 0 => initial_contains hw
  | n + 1 => step_contains hw (after_contains hw n)

/-- Application-facing recurrence theorem: the two interval values produced
after `n` updates contain the precise powers required by the Gaussian sum. -/
theorem after_contains_powers {W : ComplexRect} {w : ℂ}
    (hw : W.ContainsComplex w) (n : ℕ) :
    (after W n).z.ContainsComplex (w ^ ((n + 1) ^ 2)) ∧
    (after W n).ratio.ContainsComplex (w ^ (2 * (n + 1) + 1)) := by
  have hcontains := after_contains hw n
  have hpowers := ExactGaussianState.after_eq_powers w n
  constructor
  · rw [← hpowers.1]
    exact hcontains.1
  · rw [← hpowers.2]
    exact hcontains.2

end RectGaussianState

end SparkInterval.Dirichlet.FactoredSmallQSeed
