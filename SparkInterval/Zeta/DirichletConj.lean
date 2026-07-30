/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.LSeries.DirichletContinuation
import SparkInterval.Zeta.HardyZ

/-!
# Conjugation symmetry of Dirichlet `L`-functions

Mathlib proves `riemannZeta_conj : ζ (conj s) = conj (ζ s)` but has no analogue
for Dirichlet `L`-functions.  This file supplies it.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Complex Set Filter Topology HurwitzZeta
open scoped ComplexConjugate

/-! ## Conjugation symmetry of the Hurwitz zeta function -/

/-- Conjugation symmetry of the Hurwitz zeta function, for a parameter given by an explicit
real representative in `[0, 1]`. -/
theorem hurwitzZeta_conj_of_mem_Icc {b : ℝ} (hb : b ∈ Icc (0 : ℝ) 1) (s : ℂ) :
    hurwitzZeta (b : UnitAddCircle) ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (hurwitzZeta (b : UnitAddCircle) s) := by
  set a : UnitAddCircle := (b : UnitAddCircle) with ha
  -- Termwise conjugation symmetry in the convergence range.
  have hgz : EqOn (fun z ↦ conj (hurwitzZeta a (conj z))) (hurwitzZeta a) {z : ℂ | 1 < z.re} := by
    intro z hz
    have hz' : 1 < z.re := hz
    have h1 : HasSum (fun n : ℕ ↦ 1 / ((n : ℂ) + (b : ℂ)) ^ (conj z))
        (hurwitzZeta a (conj z)) :=
      hasSum_hurwitzZeta_of_one_lt_re hb (by rwa [conj_re])
    have h2 : HasSum (fun n : ℕ ↦ 1 / ((n : ℂ) + (b : ℂ)) ^ z) (hurwitzZeta a z) :=
      hasSum_hurwitzZeta_of_one_lt_re hb hz'
    simp only []
    rw [← h1.tsum_eq, ← h2.tsum_eq, conj_tsum]
    refine tsum_congr fun n ↦ ?_
    have hre : ((n : ℂ) + (b : ℂ)) = (((n : ℝ) + b : ℝ) : ℂ) := by push_cast; ring
    have hnn : (0 : ℝ) ≤ (n : ℝ) + b := by
      have := hb.1
      positivity
    have harg : ((n : ℂ) + (b : ℂ)).arg ≠ Real.pi := by
      rw [hre, Complex.arg_ofReal_of_nonneg hnn]
      exact fun h ↦ Real.pi_ne_zero h.symm
    rw [map_div₀, map_one, ← Complex.conj_cpow _ _ harg, hre, Complex.conj_ofReal]
  -- Analyticity of both sides off `s = 1`.
  have hf_an : AnalyticOnNhd ℂ (hurwitzZeta a) {1}ᶜ :=
    DifferentiableOn.analyticOnNhd
      (fun z hz ↦ (differentiableAt_hurwitzZeta a hz).differentiableWithinAt)
      isOpen_compl_singleton
  have hg_an : AnalyticOnNhd ℂ (fun z ↦ conj (hurwitzZeta a (conj z))) {1}ᶜ :=
    DifferentiableOn.analyticOnNhd
      (fun z hz ↦ (differentiableAt_conj_conj_iff.mpr <| differentiableAt_hurwitzZeta a
        ((map_ne_one_iff _ (starRingEnd ℂ).injective).mpr hz)).differentiableWithinAt)
      isOpen_compl_singleton
  have heq : EqOn (fun z ↦ conj (hurwitzZeta a (conj z))) (hurwitzZeta a) {1}ᶜ :=
    hg_an.eqOn_of_preconnected_of_eventuallyEq hf_an
      (isConnected_compl_singleton_of_one_lt_rank (by simp) 1).isPreconnected
      (by norm_num : (2 : ℂ) ∈ _)
      (eventuallyEq_of_mem
        ((isOpen_lt continuous_const continuous_re).mem_nhds (by norm_num)) hgz)
  rcases eq_or_ne s 1 with rfl | hs
  · -- At the pole we compare the two (continuous) regularisations `ζ_H - 1/((s-1)Γ_ℝ(s))`.
    set G : ℂ → ℂ := fun z ↦ hurwitzZeta a z - 1 / (z - 1) / Gammaℝ z with hG
    have hGc : ContinuousAt G 1 := (differentiableAt_hurwitzZeta_sub_one_div a).continuousAt
    have hHc : ContinuousAt (fun z ↦ conj (G (conj z))) 1 := by
      have h0 : ContinuousAt (fun z : ℂ ↦ conj z) 1 := Complex.continuous_conj.continuousAt
      have h1 : ContinuousAt G ((starRingEnd ℂ) 1) := by simpa using hGc
      exact Complex.continuous_conj.continuousAt.comp (h1.comp h0)
    have hEq : (fun z ↦ conj (G (conj z))) =ᶠ[𝓝[≠] (1 : ℂ)] G := by
      filter_upwards [self_mem_nhdsWithin] with z hz
      have hz1 : z ≠ 1 := hz
      have hzc : conj (hurwitzZeta a (conj z)) = hurwitzZeta a z := heq hz1
      have hGam : conj (Gammaℝ (conj z)) = Gammaℝ z := by
        rw [← Gammaℝ_conj, Complex.conj_conj]
      simp only [hG, map_sub, map_div₀, map_one, map_sub, Complex.conj_conj, hzc, hGam]
    have h1 : Tendsto (fun z ↦ conj (G (conj z))) (𝓝[≠] (1 : ℂ)) (𝓝 (conj (G 1))) := by
      have := hHc.continuousWithinAt (s := {(1 : ℂ)}ᶜ)
      simpa using this.tendsto
    have h2 : Tendsto (fun z ↦ conj (G (conj z))) (𝓝[≠] (1 : ℂ)) (𝓝 (G 1)) := by
      refine Tendsto.congr' hEq.symm ?_
      have := hGc.continuousWithinAt (s := {(1 : ℂ)}ᶜ)
      exact this.tendsto
    have hfin : conj (G 1) = G 1 := tendsto_nhds_unique h1 h2
    have hG1 : G 1 = hurwitzZeta a 1 := by simp [hG]
    rw [hG1] at hfin
    simpa using hfin.symm
  · have := heq hs
    simpa using congrArg (starRingEnd ℂ) this

/-- **Conjugation symmetry of the Hurwitz zeta function**. -/
theorem hurwitzZeta_conj (a : UnitAddCircle) (s : ℂ) :
    hurwitzZeta a ((starRingEnd ℂ) s) = (starRingEnd ℂ) (hurwitzZeta a s) := by
  obtain ⟨x, rfl⟩ := (QuotientAddGroup.mk_surjective (s := AddSubgroup.zmultiples (1 : ℝ))) a
  have hx : ((Int.fract x : ℝ) : UnitAddCircle) = (x : UnitAddCircle) := AddCircle.coe_fract x
  have hmem : Int.fract x ∈ Icc (0 : ℝ) 1 :=
    ⟨Int.fract_nonneg x, (Int.fract_lt_one x).le⟩
  have := hurwitzZeta_conj_of_mem_Icc hmem s
  rwa [hx] at this

/-- Conjugation symmetry of the even part of the Hurwitz zeta function. -/
theorem hurwitzZetaEven_conj (a : UnitAddCircle) (s : ℂ) :
    hurwitzZetaEven a ((starRingEnd ℂ) s) = (starRingEnd ℂ) (hurwitzZetaEven a s) := by
  rw [hurwitzZetaEven_eq a ((starRingEnd ℂ) s), hurwitzZetaEven_eq a s, map_div₀, map_add,
    hurwitzZeta_conj, hurwitzZeta_conj]
  rw [map_ofNat]

/-- Conjugation symmetry of the odd part of the Hurwitz zeta function. -/
theorem hurwitzZetaOdd_conj (a : UnitAddCircle) (s : ℂ) :
    hurwitzZetaOdd a ((starRingEnd ℂ) s) = (starRingEnd ℂ) (hurwitzZetaOdd a s) := by
  rw [hurwitzZetaOdd_eq a ((starRingEnd ℂ) s), hurwitzZetaOdd_eq a s, map_div₀, map_sub,
    hurwitzZeta_conj, hurwitzZeta_conj]
  rw [map_ofNat]

/-- `conj (Γ_ℝ (conj s)) = Γ_ℝ s`, a restatement of `Gammaℝ_conj`. -/
private theorem conj_Gammaℝ_conj (s : ℂ) :
    (starRingEnd ℂ) (Gammaℝ ((starRingEnd ℂ) s)) = Gammaℝ s := by
  rw [← Gammaℝ_conj, Complex.conj_conj]

/-- Conjugation symmetry of the completed odd Hurwitz zeta function. -/
theorem completedHurwitzZetaOdd_conj (a : UnitAddCircle) (s : ℂ) :
    completedHurwitzZetaOdd a ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (completedHurwitzZetaOdd a s) := by
  have key : EqOn (fun z ↦ conj (completedHurwitzZetaOdd a (conj z)))
      (completedHurwitzZetaOdd a) {z : ℂ | 0 < z.re} := by
    intro z hz
    have hz' : 0 < z.re := hz
    have hG : Gammaℝ (z + 1) ≠ 0 :=
      Complex.Gammaℝ_ne_zero_of_re_pos (by simp only [Complex.add_re, Complex.one_re]; linarith)
    have hcG : Gammaℝ ((starRingEnd ℂ) z + 1) ≠ 0 :=
      Complex.Gammaℝ_ne_zero_of_re_pos (by
        simp only [Complex.add_re, Complex.one_re, Complex.conj_re]; linarith)
    have e1 : completedHurwitzZetaOdd a z = hurwitzZetaOdd a z * Gammaℝ (z + 1) := by
      have : hurwitzZetaOdd a z = completedHurwitzZetaOdd a z / Gammaℝ (z + 1) := rfl
      rw [this]; field_simp
    have e2 : completedHurwitzZetaOdd a ((starRingEnd ℂ) z) =
        hurwitzZetaOdd a ((starRingEnd ℂ) z) * Gammaℝ ((starRingEnd ℂ) z + 1) := by
      have : hurwitzZetaOdd a ((starRingEnd ℂ) z) =
          completedHurwitzZetaOdd a ((starRingEnd ℂ) z) / Gammaℝ ((starRingEnd ℂ) z + 1) := rfl
      rw [this]; field_simp
    have hGam : (starRingEnd ℂ) (Gammaℝ ((starRingEnd ℂ) z + 1)) = Gammaℝ (z + 1) := by
      have : (starRingEnd ℂ) z + 1 = (starRingEnd ℂ) (z + 1) := by simp
      rw [this, conj_Gammaℝ_conj]
    show conj (completedHurwitzZetaOdd a (conj z)) = completedHurwitzZetaOdd a z
    rw [e1, e2, map_mul, hurwitzZetaOdd_conj, Complex.conj_conj, hGam]
  have han1 : AnalyticOnNhd ℂ (completedHurwitzZetaOdd a) univ :=
    DifferentiableOn.analyticOnNhd
      (fun z _ ↦ (differentiable_completedHurwitzZetaOdd a z).differentiableWithinAt) isOpen_univ
  have han2 : AnalyticOnNhd ℂ (fun z ↦ conj (completedHurwitzZetaOdd a (conj z))) univ :=
    DifferentiableOn.analyticOnNhd
      (fun z _ ↦ (differentiableAt_conj_conj_iff.mpr
        (differentiable_completedHurwitzZetaOdd a _)).differentiableWithinAt) isOpen_univ
  have heq : EqOn (fun z ↦ conj (completedHurwitzZetaOdd a (conj z)))
      (completedHurwitzZetaOdd a) univ :=
    han2.eqOn_of_preconnected_of_eventuallyEq han1 isPreconnected_univ (mem_univ 1)
      (eventuallyEq_of_mem ((isOpen_lt continuous_const continuous_re).mem_nhds
        (by norm_num : (0 : ℝ) < (1 : ℂ).re)) key)
  simpa using congrArg (starRingEnd ℂ) (heq (mem_univ s))

/-- Conjugation symmetry of the entire regularisation `Λ₀` of the completed even Hurwitz zeta
function. -/
theorem completedHurwitzZetaEven₀_conj (a : UnitAddCircle) (s : ℂ) :
    completedHurwitzZetaEven₀ a ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (completedHurwitzZetaEven₀ a s) := by
  have hz0 : ∀ z : ℂ, completedHurwitzZetaEven₀ a z =
      completedHurwitzZetaEven a z + (if a = 0 then (1 : ℂ) else 0) / z + 1 / (1 - z) := by
    intro z; rw [completedHurwitzZetaEven_eq]; ring
  have key : EqOn (fun z ↦ conj (completedHurwitzZetaEven₀ a (conj z)))
      (completedHurwitzZetaEven₀ a) {z : ℂ | 0 < z.re} := by
    intro z hz
    have hz' : 0 < z.re := hz
    have hzne : z ≠ 0 := by
      intro h; rw [h] at hz'; simp at hz'
    have hcne : (starRingEnd ℂ) z ≠ 0 := by simpa using hzne
    have hG : Gammaℝ z ≠ 0 := Complex.Gammaℝ_ne_zero_of_re_pos hz'
    have hcG : Gammaℝ ((starRingEnd ℂ) z) ≠ 0 :=
      Complex.Gammaℝ_ne_zero_of_re_pos (by rwa [Complex.conj_re])
    have e1 : completedHurwitzZetaEven a z = hurwitzZetaEven a z * Gammaℝ z := by
      rw [hurwitzZetaEven_def_of_ne_or_ne (Or.inr hzne)]; field_simp
    have e2 : completedHurwitzZetaEven a ((starRingEnd ℂ) z) =
        hurwitzZetaEven a ((starRingEnd ℂ) z) * Gammaℝ ((starRingEnd ℂ) z) := by
      rw [hurwitzZetaEven_def_of_ne_or_ne (Or.inr hcne)]; field_simp
    have ecomp : (starRingEnd ℂ) (completedHurwitzZetaEven a ((starRingEnd ℂ) z)) =
        completedHurwitzZetaEven a z := by
      rw [e1, e2, map_mul, hurwitzZetaEven_conj, Complex.conj_conj, conj_Gammaℝ_conj]
    show conj (completedHurwitzZetaEven₀ a (conj z)) = completedHurwitzZetaEven₀ a z
    rw [hz0 ((starRingEnd ℂ) z), hz0 z]
    simp only [map_add, map_div₀, map_one, map_sub, Complex.conj_conj, ecomp,
      apply_ite (starRingEnd ℂ), map_zero]
  have han1 : AnalyticOnNhd ℂ (completedHurwitzZetaEven₀ a) univ :=
    DifferentiableOn.analyticOnNhd
      (fun z _ ↦ (differentiable_completedHurwitzZetaEven₀ a z).differentiableWithinAt) isOpen_univ
  have han2 : AnalyticOnNhd ℂ (fun z ↦ conj (completedHurwitzZetaEven₀ a (conj z))) univ :=
    DifferentiableOn.analyticOnNhd
      (fun z _ ↦ (differentiableAt_conj_conj_iff.mpr
        (differentiable_completedHurwitzZetaEven₀ a _)).differentiableWithinAt) isOpen_univ
  have heq : EqOn (fun z ↦ conj (completedHurwitzZetaEven₀ a (conj z)))
      (completedHurwitzZetaEven₀ a) univ :=
    han2.eqOn_of_preconnected_of_eventuallyEq han1 isPreconnected_univ (mem_univ 1)
      (eventuallyEq_of_mem ((isOpen_lt continuous_const continuous_re).mem_nhds
        (by norm_num : (0 : ℝ) < (1 : ℂ).re)) key)
  simpa using congrArg (starRingEnd ℂ) (heq (mem_univ s))

/-- Conjugation symmetry of the completed even Hurwitz zeta function. -/
theorem completedHurwitzZetaEven_conj (a : UnitAddCircle) (s : ℂ) :
    completedHurwitzZetaEven a ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (completedHurwitzZetaEven a s) := by
  rw [completedHurwitzZetaEven_eq a ((starRingEnd ℂ) s), completedHurwitzZetaEven_eq a s,
    completedHurwitzZetaEven₀_conj]
  simp only [map_sub, map_div₀, map_one, apply_ite (starRingEnd ℂ), map_zero]

/-! ## Conjugation symmetry of `ZMod.LFunction` -/

/-- `conj (N ^ (-s)) = N ^ (-conj s)` for a natural number `N`. -/
private theorem natCast_cpow_neg_conj (N : ℕ) (s : ℂ) :
    ((N : ℂ)) ^ (-(starRingEnd ℂ) s) = (starRingEnd ℂ) (((N : ℂ)) ^ (-s)) := by
  have hNr : ((N : ℂ)) = (((N : ℝ)) : ℂ) := by push_cast; ring
  have harg : ((N : ℂ)).arg ≠ Real.pi := by
    rw [hNr, Complex.arg_ofReal_of_nonneg (by positivity)]
    exact fun h ↦ Real.pi_ne_zero h.symm
  have h := Complex.conj_cpow ((N : ℂ)) (-(starRingEnd ℂ) s) harg
  rw [Complex.conj_natCast] at h
  simpa using h

/-- **Conjugation symmetry of `ZMod.LFunction`.** -/
theorem ZMod_LFunction_conj {N : ℕ} [NeZero N] (Φ : ZMod N → ℂ) (s : ℂ) :
    ZMod.LFunction (fun j ↦ (starRingEnd ℂ) (Φ j)) ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (ZMod.LFunction Φ s) := by
  simp only [ZMod.LFunction, map_mul, map_sum, hurwitzZeta_conj, natCast_cpow_neg_conj]

/-- **Conjugation symmetry of `ZMod.completedLFunction`.** -/
theorem ZMod_completedLFunction_conj {N : ℕ} [NeZero N] (Φ : ZMod N → ℂ) (s : ℂ) :
    ZMod.completedLFunction (fun j ↦ (starRingEnd ℂ) (Φ j)) ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (ZMod.completedLFunction Φ s) := by
  simp only [ZMod.completedLFunction, map_add, map_mul, map_sum,
    completedHurwitzZetaEven_conj, completedHurwitzZetaOdd_conj, natCast_cpow_neg_conj]

end SparkInterval.Zeta

/-! ## Conjugation symmetry of Dirichlet `L`-functions -/

namespace DirichletCharacter

open Complex SparkInterval.Zeta
open scoped ComplexConjugate

variable {N : ℕ} [NeZero N]

/-- **Conjugation symmetry of Dirichlet `L`-functions**:
`L(conj χ, conj s) = conj (L(χ, s))`, where `conj χ = χ.ringHomComp (starRingEnd ℂ)` is the
complex-conjugate character. -/
theorem LFunction_conj (χ : DirichletCharacter ℂ N) (s : ℂ) :
    LFunction (χ.ringHomComp (starRingEnd ℂ)) ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (LFunction χ s) := by
  have h : (fun j ↦ (χ.ringHomComp (starRingEnd ℂ)) j) =
      fun j ↦ (starRingEnd ℂ) (χ j) := rfl
  show ZMod.LFunction (fun j ↦ (χ.ringHomComp (starRingEnd ℂ)) j) ((starRingEnd ℂ) s) =
    (starRingEnd ℂ) (ZMod.LFunction (fun j ↦ χ j) s)
  rw [h]
  exact ZMod_LFunction_conj _ _

/-- **Conjugation symmetry of completed Dirichlet `L`-functions**:
`Λ(conj χ, conj s) = conj (Λ(χ, s))`. -/
theorem completedLFunction_conj (χ : DirichletCharacter ℂ N) (s : ℂ) :
    completedLFunction (χ.ringHomComp (starRingEnd ℂ)) ((starRingEnd ℂ) s) =
      (starRingEnd ℂ) (completedLFunction χ s) := by
  have h : (fun j ↦ (χ.ringHomComp (starRingEnd ℂ)) j) =
      fun j ↦ (starRingEnd ℂ) (χ j) := rfl
  show ZMod.completedLFunction (fun j ↦ (χ.ringHomComp (starRingEnd ℂ)) j) ((starRingEnd ℂ) s) =
    (starRingEnd ℂ) (ZMod.completedLFunction (fun j ↦ χ j) s)
  rw [h]
  exact ZMod_completedLFunction_conj _ _

/-- **Schwarz reflection for a real Dirichlet character**: if `χ` is fixed by complex conjugation
then `L(χ, conj s) = conj (L(χ, s))`. -/
theorem LFunction_conj_of_isReal {χ : DirichletCharacter ℂ N}
    (hχ : χ.ringHomComp (starRingEnd ℂ) = χ) (s : ℂ) :
    LFunction χ ((starRingEnd ℂ) s) = (starRingEnd ℂ) (LFunction χ s) := by
  conv_lhs => rw [← hχ]
  exact LFunction_conj χ s

/-- **Schwarz reflection for the completed `L`-function of a real Dirichlet character.** -/
theorem completedLFunction_conj_of_isReal {χ : DirichletCharacter ℂ N}
    (hχ : χ.ringHomComp (starRingEnd ℂ) = χ) (s : ℂ) :
    completedLFunction χ ((starRingEnd ℂ) s) = (starRingEnd ℂ) (completedLFunction χ s) := by
  conv_lhs => rw [← hχ]
  exact completedLFunction_conj χ s

omit [NeZero N] in
/-- A Dirichlet character all of whose values are real is fixed by complex conjugation. -/
theorem ringHomComp_starRingEnd_eq_self_of_forall {χ : DirichletCharacter ℂ N}
    (hχ : ∀ j : ZMod N, (starRingEnd ℂ) (χ j) = χ j) :
    χ.ringHomComp (starRingEnd ℂ) = χ :=
  MulChar.ext fun j ↦ hχ j

end DirichletCharacter

section SanityCheck
-- Non-vacuity: the new theorem specialises to Mathlib's `riemannZeta_conj`
-- (mod-1 character), with no appeal to Mathlib's own `riemannZeta_conj`.
example (s : ℂ) : riemannZeta ((starRingEnd ℂ) s) = (starRingEnd ℂ) (riemannZeta s) := by
  have h := DirichletCharacter.LFunction_conj (1 : DirichletCharacter ℂ 1) s
  rwa [DirichletCharacter.LFunction_modOne_eq, DirichletCharacter.LFunction_modOne_eq] at h

example (s : ℂ) :
    completedRiemannZeta ((starRingEnd ℂ) s) = (starRingEnd ℂ) (completedRiemannZeta s) := by
  have h := DirichletCharacter.completedLFunction_conj (1 : DirichletCharacter ℂ 1) s
  rwa [DirichletCharacter.completedLFunction_modOne_eq,
    DirichletCharacter.completedLFunction_modOne_eq] at h
end SanityCheck
