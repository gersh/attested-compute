/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.Harmonic.ZetaAsymp
import Mathlib.Analysis.SpecialFunctions.Gamma.Deriv
import SparkInterval.Zeta.HardyZContract

/-!
# The Hardy `Z` function of Mathlib's `riemannZeta`

`SparkInterval.Zeta.HardyZContract` states an abstract *contract*: a real
function differing from `riemannZeta (1/2 + i t)` by a nonvanishing complex
factor.  Nothing there exhibits such a function, so every downstream
sign-change certificate was conditional on an unproved analytic input.

This file removes that gap.  It defines

```text
theta t = arg (Gamma (1/4 + i t/2)) - (t/2) log pi          (Riemann-Siegel theta)
Z t     = Re (completedRiemannZeta (1/2 + i t)) / ‖Gammaℝ (1/2 + i t)‖
```

and proves, unconditionally and with no new axiom:

* `hardyZ_ofReal` : `(Z t : ℂ) = exp (i * θ t) * ζ (1/2 + i t)`, i.e. the real
  function `hardyZ` *is* the classical Hardy `Z`;
* `norm_hardyZ` : `|Z t| = ‖ζ (1/2 + i t)‖`;
* `hardyZ_eq_zero_iff` : `Z t = 0 ↔ ζ (1/2 + i t) = 0`;
* `continuous_hardyZ` : `Z` is continuous on all of `ℝ`;
* `hardyZModel` : the `HardyZModel` contract is *inhabited* at `hardyZ`, for
  every height, so all of `HardyZContract`'s conditional end-to-end theorems
  become unconditional in their analytic input.

The mathematical core is `completedRiemannZeta_im_criticalPoint`: the completed
zeta `Λ(s) = Gammaℝ(s) ζ(s)` is real on the critical line, because

```text
conj (Λ (1/2 + i t)) = Λ (1/2 - i t) = Λ (1 - (1/2 + i t)) = Λ (1/2 + i t),
```

the first step by Schwarz reflection (`riemannZeta_conj`, `Complex.Gamma_conj`)
and the second by the functional equation (`completedRiemannZeta_one_sub`).
Reality of `Λ` on the line is exactly what makes a *sign change* of `Z` a proof
that `ζ` has a zero on the critical line, so this is the theorem that gives
every computed sign-change bracket its meaning.

The definition of `Z` above is definitionally real; `Gammaℝ_criticalPoint_polar`
proves `Gammaℝ (1/2 + i t) = ‖Gammaℝ (1/2 + i t)‖ · exp (i θ t)`, which is what
identifies it with `exp (i θ t) ζ (1/2 + i t)`.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Complex

/-! ## Elementary facts about the critical-line parametrization -/

theorem criticalPoint_eq (t : ℝ) : criticalPoint t = 1 / 2 + (t : ℂ) * I := by
  apply Complex.ext <;> simp [criticalPoint]

theorem criticalPoint_ne_zero (t : ℝ) : criticalPoint t ≠ 0 := by
  intro h
  have hre : (criticalPoint t).re = 0 := by rw [h]; simp
  rw [criticalPoint_re] at hre
  norm_num at hre

theorem criticalPoint_ne_one (t : ℝ) : criticalPoint t ≠ 1 := by
  intro h
  have hre : (criticalPoint t).re = 1 := by rw [h]; simp
  rw [criticalPoint_re] at hre
  norm_num at hre

theorem re_criticalPoint_pos (t : ℝ) : 0 < (criticalPoint t).re := by
  rw [criticalPoint_re]; norm_num

/-- Conjugation on the critical line is exactly the functional-equation
reflection `s ↦ 1 - s`. -/
theorem conj_criticalPoint (t : ℝ) :
    (starRingEnd ℂ) (criticalPoint t) = 1 - criticalPoint t := by
  rw [criticalPoint_eq]
  simp only [map_add, map_mul, map_div₀, map_one, map_ofNat, Complex.conj_I,
    Complex.conj_ofReal]
  ring

theorem continuous_criticalPoint : Continuous criticalPoint := by
  have hfun : criticalPoint = fun t : ℝ => 1 / 2 + (t : ℂ) * I := by
    funext t; exact criticalPoint_eq t
  rw [hfun]
  exact continuous_const.add (Complex.continuous_ofReal.mul continuous_const)

/-! ## The archimedean factor `Gammaℝ` on the critical line -/

theorem differentiableAt_Gammaℝ_of_re_pos {s : ℂ} (hs : 0 < s.re) :
    DifferentiableAt ℂ Complex.Gammaℝ s := by
  have hpow : DifferentiableAt ℂ (fun z : ℂ => (Real.pi : ℂ) ^ (-z / 2)) s :=
    (differentiableAt_id.neg.div_const 2).const_cpow
      (Or.inl (Complex.ofReal_ne_zero.mpr Real.pi_ne_zero))
  have hgam : DifferentiableAt ℂ (fun z : ℂ => Complex.Gamma (z / 2)) s := by
    refine DifferentiableAt.comp s (Complex.differentiableAt_Gamma _ ?_)
      (differentiableAt_id.div_const 2)
    intro m hm
    have hre : (s / 2).re = (-(m : ℂ)).re := by rw [hm]
    rw [Complex.div_ofNat_re, Complex.neg_re, Complex.natCast_re] at hre
    have hpos : 0 < s.re / 2 := by positivity
    have hnonneg : (0 : ℝ) ≤ (m : ℝ) := Nat.cast_nonneg m
    linarith
  have hdef : Complex.Gammaℝ =
      fun z : ℂ => (Real.pi : ℂ) ^ (-z / 2) * Complex.Gamma (z / 2) := by
    funext z; rw [Complex.Gammaℝ_def]
  rw [hdef]
  exact hpow.mul hgam

theorem Gammaℝ_criticalPoint_ne_zero (t : ℝ) :
    Complex.Gammaℝ (criticalPoint t) ≠ 0 :=
  Complex.Gammaℝ_ne_zero_of_re_pos (re_criticalPoint_pos t)

theorem norm_Gammaℝ_criticalPoint_pos (t : ℝ) :
    0 < ‖Complex.Gammaℝ (criticalPoint t)‖ :=
  norm_pos_iff.mpr (Gammaℝ_criticalPoint_ne_zero t)

/-- `Λ(s) = Gammaℝ(s) · ζ(s)`; Mathlib states the quotient form. -/
theorem completedRiemannZeta_eq_Gammaℝ_mul {s : ℂ} (hs : s ≠ 0)
    (hG : Complex.Gammaℝ s ≠ 0) :
    completedRiemannZeta s = Complex.Gammaℝ s * riemannZeta s := by
  rw [riemannZeta_def_of_ne_zero hs]
  field_simp

/-! ## Schwarz reflection for the completed zeta -/

/-- `Gammaℝ(conj s) = conj (Gammaℝ s)`. -/
theorem Gammaℝ_conj (s : ℂ) :
    Complex.Gammaℝ ((starRingEnd ℂ) s) = (starRingEnd ℂ) (Complex.Gammaℝ s) := by
  rw [Complex.Gammaℝ_def, Complex.Gammaℝ_def, map_mul]
  have harg : ((Real.pi : ℝ) : ℂ).arg ≠ Real.pi := by
    rw [Complex.arg_ofReal_of_nonneg Real.pi_pos.le]
    exact Real.pi_pos.ne
  congr 1
  · have hconj : -(starRingEnd ℂ) s / 2 = (starRingEnd ℂ) (-s / 2) := by
      rw [map_div₀, map_neg, map_ofNat]
    rw [hconj, Complex.cpow_conj _ _ harg, Complex.conj_ofReal]
  · have hconj2 : (starRingEnd ℂ) s / 2 = (starRingEnd ℂ) (s / 2) := by
      rw [map_div₀, map_ofNat]
    rw [hconj2, Complex.Gamma_conj]

/-- **Schwarz reflection for `Λ`** on the open right half plane:
`Λ(conj s) = conj (Λ s)` whenever `0 < re s`. -/
theorem completedRiemannZeta_conj_of_re_pos {s : ℂ} (hs : 0 < s.re) :
    completedRiemannZeta ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (completedRiemannZeta s) := by
  have hs0 : s ≠ 0 := by
    intro h; rw [h] at hs; simp at hs
  have hcs0 : (starRingEnd ℂ) s ≠ 0 := by
    rw [ne_eq, map_eq_zero]; exact hs0
  have hG : Complex.Gammaℝ s ≠ 0 := Complex.Gammaℝ_ne_zero_of_re_pos hs
  have hcG : Complex.Gammaℝ ((starRingEnd ℂ) s) ≠ 0 :=
    Complex.Gammaℝ_ne_zero_of_re_pos (by rwa [Complex.conj_re])
  rw [completedRiemannZeta_eq_Gammaℝ_mul hcs0 hcG,
    completedRiemannZeta_eq_Gammaℝ_mul hs0 hG, map_mul, Gammaℝ_conj, riemannZeta_conj]

/-- **The completed zeta is real on the critical line.**

This is the analytic fact that turns a sign change of the Hardy function into a
proof of a zeta zero: `Λ(1/2 + i t)` is fixed by conjugation, because
conjugation on the line is the functional-equation reflection `s ↦ 1 - s`. -/
theorem completedRiemannZeta_im_criticalPoint (t : ℝ) :
    (completedRiemannZeta (criticalPoint t)).im = 0 := by
  have hconj :
      (starRingEnd ℂ) (completedRiemannZeta (criticalPoint t)) =
        completedRiemannZeta (criticalPoint t) := by
    rw [← completedRiemannZeta_conj_of_re_pos (re_criticalPoint_pos t),
      conj_criticalPoint, completedRiemannZeta_one_sub]
  exact Complex.conj_eq_iff_im.mp hconj

theorem ofReal_re_completedRiemannZeta_criticalPoint (t : ℝ) :
    (((completedRiemannZeta (criticalPoint t)).re : ℝ) : ℂ) =
      completedRiemannZeta (criticalPoint t) := by
  apply Complex.ext <;> simp [completedRiemannZeta_im_criticalPoint t]

/-! ## The Riemann-Siegel theta function and the Hardy phase -/

/-- The Riemann-Siegel theta function
`θ(t) = arg Γ(1/4 + i t/2) - (t/2) log π`.

Using `arg` rather than a continuous branch of `log Γ` is harmless: only
`exp (i θ t)` is used below, and that is branch independent. -/
noncomputable def riemannSiegelTheta (t : ℝ) : ℝ :=
  (Complex.Gamma (1 / 4 + ((t / 2 : ℝ) : ℂ) * I)).arg - t / 2 * Real.log Real.pi

/-- The Hardy phase `e^{i θ(t)}`. -/
noncomputable def hardyPhase (t : ℝ) : ℂ :=
  Complex.exp (((riemannSiegelTheta t : ℝ) : ℂ) * I)

@[simp] theorem norm_hardyPhase (t : ℝ) : ‖hardyPhase t‖ = 1 := by
  simp [hardyPhase]

theorem hardyPhase_ne_zero (t : ℝ) : hardyPhase t ≠ 0 :=
  Complex.exp_ne_zero _

/-- Polar decomposition of the archimedean factor on the critical line:
`Gammaℝ(1/2 + i t) = π^(-1/4) ‖Γ(1/4 + i t/2)‖ · e^{i θ(t)}`. -/
theorem Gammaℝ_criticalPoint_polar (t : ℝ) :
    Complex.Gammaℝ (criticalPoint t) =
      ((Real.pi ^ (-(1 / 4) : ℝ) *
        ‖Complex.Gamma (1 / 4 + ((t / 2 : ℝ) : ℂ) * I)‖ : ℝ) : ℂ) * hardyPhase t := by
  have hpi : ((Real.pi : ℝ) : ℂ) ≠ 0 := Complex.ofReal_ne_zero.mpr Real.pi_ne_zero
  have hhalf : criticalPoint t / 2 = 1 / 4 + ((t / 2 : ℝ) : ℂ) * I := by
    rw [criticalPoint_eq]; push_cast; ring
  have hsplit : -(criticalPoint t) / 2 =
      ((-(1 / 4) : ℝ) : ℂ) + ((-(t / 2) : ℝ) : ℂ) * I := by
    rw [criticalPoint_eq]; push_cast; ring
  -- the power factor
  have hpow :
      ((Real.pi : ℝ) : ℂ) ^ (-(criticalPoint t) / 2) =
        ((Real.pi ^ (-(1 / 4) : ℝ) : ℝ) : ℂ) *
          Complex.exp (((-(t / 2) * Real.log Real.pi : ℝ) : ℂ) * I) := by
    rw [hsplit, Complex.cpow_add _ _ hpi]
    congr 1
    · rw [← Complex.ofReal_cpow Real.pi_pos.le]
    · rw [Complex.cpow_def_of_ne_zero hpi, ← Complex.ofReal_log Real.pi_pos.le]
      congr 1
      push_cast
      all_goals ring
  -- the Gamma factor
  have hgam :
      Complex.Gamma (1 / 4 + ((t / 2 : ℝ) : ℂ) * I) =
        ((‖Complex.Gamma (1 / 4 + ((t / 2 : ℝ) : ℂ) * I)‖ : ℝ) : ℂ) *
          Complex.exp (((Complex.Gamma (1 / 4 + ((t / 2 : ℝ) : ℂ) * I)).arg : ℝ) * I) :=
    (Complex.norm_mul_exp_arg_mul_I _).symm
  have hexp :
      Complex.exp (((-(t / 2) * Real.log Real.pi : ℝ) : ℂ) * I) *
          Complex.exp (((Complex.Gamma (1 / 4 + ((t / 2 : ℝ) : ℂ) * I)).arg : ℝ) * I) =
        hardyPhase t := by
    rw [hardyPhase, ← Complex.exp_add, riemannSiegelTheta]
    congr 1
    push_cast
    all_goals ring
  rw [Complex.Gammaℝ_def, hhalf, hpow]
  conv_lhs => rw [hgam]
  rw [← hexp]
  push_cast
  ring

/-- Norm of the archimedean factor on the critical line. -/
theorem norm_Gammaℝ_criticalPoint (t : ℝ) :
    ‖Complex.Gammaℝ (criticalPoint t)‖ =
      Real.pi ^ (-(1 / 4) : ℝ) *
        ‖Complex.Gamma (1 / 4 + ((t / 2 : ℝ) : ℂ) * I)‖ := by
  rw [Gammaℝ_criticalPoint_polar t, norm_mul, norm_hardyPhase, mul_one,
    Complex.norm_real, Real.norm_eq_abs, abs_of_nonneg]
  positivity

/-- The archimedean factor equals its own modulus times the Hardy phase. -/
theorem Gammaℝ_criticalPoint_eq_norm_mul_phase (t : ℝ) :
    Complex.Gammaℝ (criticalPoint t) =
      ((‖Complex.Gammaℝ (criticalPoint t)‖ : ℝ) : ℂ) * hardyPhase t := by
  rw [norm_Gammaℝ_criticalPoint t]
  exact Gammaℝ_criticalPoint_polar t

/-! ## The Hardy `Z` function -/

/-- **Hardy's `Z` function** for Mathlib's `riemannZeta`.

Defined so as to be manifestly real; `hardyZ_ofReal` proves it agrees with the
classical `e^{i θ(t)} ζ(1/2 + i t)`. -/
noncomputable def hardyZ (t : ℝ) : ℝ :=
  (completedRiemannZeta (criticalPoint t)).re / ‖Complex.Gammaℝ (criticalPoint t)‖

/-- **`Z` is the Hardy function**: `(Z t : ℂ) = e^{i θ(t)} · ζ(1/2 + i t)`.

Read the other way round: `e^{i θ(t)} ζ(1/2 + i t)` is real, and `hardyZ` is
that real number. -/
theorem hardyZ_ofReal (t : ℝ) :
    ((hardyZ t : ℝ) : ℂ) = hardyPhase t * riemannZeta (criticalPoint t) := by
  have hGne : ((‖Complex.Gammaℝ (criticalPoint t)‖ : ℝ) : ℂ) ≠ 0 :=
    Complex.ofReal_ne_zero.mpr (norm_Gammaℝ_criticalPoint_pos t).ne'
  have hlam : completedRiemannZeta (criticalPoint t) =
      ((‖Complex.Gammaℝ (criticalPoint t)‖ : ℝ) : ℂ) * hardyPhase t *
        riemannZeta (criticalPoint t) := by
    rw [completedRiemannZeta_eq_Gammaℝ_mul (criticalPoint_ne_zero t)
      (Gammaℝ_criticalPoint_ne_zero t)]
    conv_lhs => rw [Gammaℝ_criticalPoint_eq_norm_mul_phase t]
  rw [hardyZ, Complex.ofReal_div, ofReal_re_completedRiemannZeta_criticalPoint t, hlam]
  field_simp

/-- `|Z t| = ‖ζ(1/2 + i t)‖`: the Hardy function has the modulus of zeta on the
critical line. -/
theorem norm_hardyZ (t : ℝ) : |hardyZ t| = ‖riemannZeta (criticalPoint t)‖ := by
  have h : ‖((hardyZ t : ℝ) : ℂ)‖ = ‖hardyPhase t * riemannZeta (criticalPoint t)‖ := by
    rw [hardyZ_ofReal t]
  rwa [Complex.norm_real, Real.norm_eq_abs, norm_mul, norm_hardyPhase, one_mul] at h

/-- A zero of the real function `Z` is exactly a zero of `ζ` on the critical
line.  This is the statement a sign-change bracket consumes. -/
theorem hardyZ_eq_zero_iff (t : ℝ) :
    hardyZ t = 0 ↔ riemannZeta (criticalPoint t) = 0 := by
  constructor
  · intro h
    have h0 : ((hardyZ t : ℝ) : ℂ) = 0 := by rw [h]; simp
    rw [hardyZ_ofReal t] at h0
    exact (mul_eq_zero.mp h0).resolve_left (hardyPhase_ne_zero t)
  · intro h
    have h0 : ((hardyZ t : ℝ) : ℂ) = 0 := by rw [hardyZ_ofReal t, h, mul_zero]
    exact_mod_cast h0

/-- `Z` and the real part of the completed zeta differ by a positive factor, so
a campaign may certify enclosures of either one. -/
theorem hardyZ_mul_norm_Gammaℝ (t : ℝ) :
    hardyZ t * ‖Complex.Gammaℝ (criticalPoint t)‖ =
      (completedRiemannZeta (criticalPoint t)).re := by
  rw [hardyZ, div_mul_cancel₀]
  exact (norm_Gammaℝ_criticalPoint_pos t).ne'

theorem hardyZ_pos_iff (t : ℝ) :
    0 < hardyZ t ↔ 0 < (completedRiemannZeta (criticalPoint t)).re := by
  rw [hardyZ, lt_div_iff₀ (norm_Gammaℝ_criticalPoint_pos t), zero_mul]

theorem hardyZ_neg_iff (t : ℝ) :
    hardyZ t < 0 ↔ (completedRiemannZeta (criticalPoint t)).re < 0 := by
  rw [hardyZ, div_lt_iff₀ (norm_Gammaℝ_criticalPoint_pos t), zero_mul]

/-! ## Continuity -/

theorem continuousAt_completedRiemannZeta_criticalPoint (t : ℝ) :
    ContinuousAt (fun u : ℝ => completedRiemannZeta (criticalPoint u)) t :=
  ((differentiableAt_completedZeta (criticalPoint_ne_zero t)
    (criticalPoint_ne_one t)).continuousAt).comp
      continuous_criticalPoint.continuousAt

theorem continuousAt_Gammaℝ_criticalPoint (t : ℝ) :
    ContinuousAt (fun u : ℝ => Complex.Gammaℝ (criticalPoint u)) t :=
  ((differentiableAt_Gammaℝ_of_re_pos (re_criticalPoint_pos t)).continuousAt).comp
    continuous_criticalPoint.continuousAt

theorem continuous_hardyZ : Continuous hardyZ := by
  rw [continuous_iff_continuousAt]
  intro t
  have hnum : ContinuousAt
      (fun u : ℝ => (completedRiemannZeta (criticalPoint u)).re) t :=
    Complex.continuous_re.continuousAt.comp
      (continuousAt_completedRiemannZeta_criticalPoint t)
  have hden : ContinuousAt
      (fun u : ℝ => ‖Complex.Gammaℝ (criticalPoint u)‖) t :=
    continuous_norm.continuousAt.comp (continuousAt_Gammaℝ_criticalPoint t)
  exact hnum.div hden (norm_Gammaℝ_criticalPoint_pos t).ne'

/-! ## The contract is inhabited -/

/-- **The `HardyZModel` contract is satisfied by the genuine Hardy `Z`.**

Every conditional theorem in `SparkInterval.Zeta.HardyZContract` may now be
applied with `f := hardyZ` and this model, discharging its analytic premise. -/
noncomputable def hardyZModel (height : ℝ) : HardyZModel hardyZ height where
  phase := hardyPhase
  phase_ne_zero := fun {t} _ => hardyPhase_ne_zero t
  representation := fun {t} _ => hardyZ_ofReal t
  continuous := continuous_hardyZ

/-- The critical-line zero bridge, unconditionally, for the real Hardy `Z`. -/
theorem hardyZ_criticalLineZeroBridge (height : ℝ) :
    CriticalLineZeroBridge hardyZ height :=
  (hardyZModel height).criticalLineZeroBridge

/-- **End-to-end finite-height theorem with no analytic side condition on the
evaluator.**

If a campaign supplies rational sign-change brackets for the genuine Hardy `Z`
whose endpoint enclosures are certified, all lying inside `[-height, height]`,
and a zero-count upper bound matching the number of brackets, then every zeta
zero in the closed critical rectangle lies on the critical line.

The only remaining inputs are `hencloses` (the certified evaluator enclosures,
i.e. the compute campaign) and `totalUpper` (the Turing/argument-principle
count). -/
theorem hardyZ_verifyEndpointFamily {height : ℝ} {count : Nat}
    (family : RationalBracketFamily count)
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints hardyZ)
    (hlower : ∀ i, -height ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  HardyZModel.verifyEndpointFamily (hardyZModel height) family hcheck hencloses
    hlower hupper totalUpper

/-- The same end-to-end theorem for the touching-endpoint bracket family. -/
theorem hardyZ_verifyTouchingEndpointFamily {height : ℝ} {count : Nat}
    (family : TouchingRationalBracketFamily count)
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints hardyZ)
    (hlower : ∀ i, -height ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  HardyZModel.verifyTouchingEndpointFamily (hardyZModel height) family hcheck
    hencloses hlower hupper totalUpper

end SparkInterval.Zeta
