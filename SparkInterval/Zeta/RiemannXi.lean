/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.HardyZ

/-!
# The Riemann `ξ` function and its zeros

The argument principle counts zeros of an entire function inside a rectangle.
`riemannZeta` is not the right function to feed it: it has a pole at `1`, it has
the trivial zeros at `-2, -4, …`, and the completed function `Λ` has poles at
`0` and `1` which sit exactly on the boundary of the critical rectangle
`[0,1] × [-T,T]`.

The classical fix is Riemann's

```text
ξ(s) = s (s - 1) / 2 · Λ(s),
```

which is entire, satisfies `ξ(1 - s) = ξ(s)`, and whose zeros are *exactly* the
nontrivial zeros of `ζ`, with the same multiplicities.  Since Mathlib's `Λ` is
only defined with its poles present, `ξ` is defined here through the entire
`completedRiemannZeta₀`, using

```text
s(s-1)/2 · Λ(s) = s(s-1)/2 · (Λ₀(s) - 1/s - 1/(1-s)) = s(s-1)/2 · Λ₀(s) + 1/2 ,
```

so the definition below is manifestly entire and needs no case split.

The results proved here are exactly the hypotheses that the rectangle argument
principle needs, plus the multiplicity bookkeeping that turns its divisor sum
into `zetaZeroMultiplicityCount`:

* `differentiable_riemannXi`, `analyticAt_riemannXi`;
* `riemannXi_one_sub` — the functional equation, in the clean symmetric form;
* `riemannXi_one`, `riemannXi_zero` — both equal `1/2`, so `ξ` does not vanish
  at the two points where `Λ` has poles;
* `riemannXi_ne_zero_of_one_le_re` and `riemannXi_ne_zero_of_re_le_zero` — `ξ`
  has no zeros outside the open critical strip, so the vertical sides of the
  critical rectangle are automatically free of zeros;
* `riemannXi_eq_zero_iff` — inside the strip, `ξ` and `ζ` have the same zeros;
* `analyticOrderAt_riemannXi` — and the same *multiplicities*, so no zero can be
  miscounted;
* `analyticOrderAt_riemannXi_ne_top`, `meromorphicOrderAt_riemannXi_ne_top` —
  finiteness of the order everywhere, from `ξ(1) = 1/2 ≠ 0` and the identity
  theorem on the connected plane.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Complex

/-- **Riemann's `ξ` function**, `ξ(s) = s(s-1)/2 · Λ(s)`, written through the
entire `completedRiemannZeta₀` so that it is manifestly entire. -/
noncomputable def riemannXi (s : ℂ) : ℂ :=
  s * (s - 1) / 2 * completedRiemannZeta₀ s + 1 / 2

theorem differentiable_riemannXi : Differentiable ℂ riemannXi :=
  (((differentiable_id.mul (differentiable_id.sub (differentiable_const 1))).div_const
      2).mul differentiable_completedZeta₀).add (differentiable_const _)

theorem analyticAt_riemannXi (s : ℂ) : AnalyticAt ℂ riemannXi s :=
  (differentiable_riemannXi).analyticAt s

theorem analyticOnNhd_riemannXi : AnalyticOnNhd ℂ riemannXi Set.univ :=
  fun s _ => analyticAt_riemannXi s

/-! ## The two special values, and the functional equation -/

@[simp] theorem riemannXi_one : riemannXi 1 = 1 / 2 := by
  simp [riemannXi]

@[simp] theorem riemannXi_zero : riemannXi 0 = 1 / 2 := by
  simp [riemannXi]

/-- The functional equation in its symmetric form.  It is a one-line consequence
of `completedRiemannZeta₀_one_sub` because the prefactor `s(s-1)/2` is itself
invariant under `s ↦ 1 - s`. -/
theorem riemannXi_one_sub (s : ℂ) : riemannXi (1 - s) = riemannXi s := by
  unfold riemannXi
  rw [completedRiemannZeta₀_one_sub]
  ring

/-! ## `ξ` in terms of `ζ` -/

/-- Away from `0` and `1`, `ξ` is the classical `s(s-1)/2 · Λ(s)`. -/
theorem riemannXi_eq_mul_completedRiemannZeta {s : ℂ} (hs0 : s ≠ 0) (hs1 : s ≠ 1) :
    riemannXi s = s * (s - 1) / 2 * completedRiemannZeta s := by
  have hs1' : s - 1 ≠ 0 := sub_ne_zero.mpr hs1
  have h1s : (1 : ℂ) - s ≠ 0 := by
    intro h
    exact hs1' (by linear_combination -h)
  rw [completedRiemannZeta_eq, riemannXi]
  field_simp
  ring

/-- On the open right half plane, `ξ = s(s-1)/2 · Gammaℝ(s) · ζ(s)`.  All three
factors of the prefactor are nonvanishing there except at `s = 0, 1`, which is
what makes `ξ` and `ζ` share their zeros and multiplicities inside the strip. -/
theorem riemannXi_eq_mul_riemannZeta {s : ℂ} (hs : 0 < s.re) (hs1 : s ≠ 1) :
    riemannXi s = (s * (s - 1) / 2 * Complex.Gammaℝ s) * riemannZeta s := by
  have hs0 : s ≠ 0 := by
    intro h; rw [h] at hs; simp at hs
  have hG : Complex.Gammaℝ s ≠ 0 := Complex.Gammaℝ_ne_zero_of_re_pos hs
  rw [riemannXi_eq_mul_completedRiemannZeta hs0 hs1,
    completedRiemannZeta_eq_Gammaℝ_mul hs0 hG]
  ring

/-- The prefactor relating `ξ` to `ζ`. -/
noncomputable def xiPrefactor (s : ℂ) : ℂ := s * (s - 1) / 2 * Complex.Gammaℝ s

theorem xiPrefactor_ne_zero {s : ℂ} (hs : 0 < s.re) (hs1 : s ≠ 1) :
    xiPrefactor s ≠ 0 := by
  have hs0 : s ≠ 0 := by
    intro h; rw [h] at hs; simp at hs
  have hs1' : s - 1 ≠ 0 := sub_ne_zero.mpr hs1
  have hG : Complex.Gammaℝ s ≠ 0 := Complex.Gammaℝ_ne_zero_of_re_pos hs
  unfold xiPrefactor
  exact mul_ne_zero (div_ne_zero (mul_ne_zero hs0 hs1') two_ne_zero) hG

/-- The open right half plane. -/
theorem isOpen_rePos : IsOpen {z : ℂ | 0 < z.re} :=
  isOpen_lt continuous_const Complex.continuous_re

theorem analyticAt_xiPrefactor {s : ℂ} (hs : 0 < s.re) : AnalyticAt ℂ xiPrefactor s := by
  have hdiff : DifferentiableOn ℂ xiPrefactor {z : ℂ | 0 < z.re} := by
    intro z hz
    have hG : DifferentiableAt ℂ Complex.Gammaℝ z := differentiableAt_Gammaℝ_of_re_pos hz
    exact ((((differentiableAt_id.mul
      (differentiableAt_id.sub (differentiableAt_const 1))).div_const 2)).mul
        hG).differentiableWithinAt
  exact hdiff.analyticOnNhd isOpen_rePos s hs

/-! ## `ξ` has no zeros outside the open critical strip -/

theorem riemannXi_ne_zero_of_one_le_re {s : ℂ} (hs : 1 ≤ s.re) : riemannXi s ≠ 0 := by
  rcases eq_or_ne s 1 with rfl | hs1
  · simp
  · have hspos : 0 < s.re := lt_of_lt_of_le one_pos hs
    rw [riemannXi_eq_mul_riemannZeta hspos hs1]
    exact mul_ne_zero (xiPrefactor_ne_zero hspos hs1)
      (riemannZeta_ne_zero_of_one_le_re hs)

theorem riemannXi_ne_zero_of_re_le_zero {s : ℂ} (hs : s.re ≤ 0) : riemannXi s ≠ 0 := by
  have hre : 1 ≤ (1 - s).re := by
    rw [Complex.sub_re, Complex.one_re]; linarith
  have := riemannXi_ne_zero_of_one_le_re hre
  rwa [riemannXi_one_sub] at this

/-- Every zero of `ξ` lies in the open critical strip. -/
theorem re_mem_Ioo_of_riemannXi_eq_zero {s : ℂ} (hs : riemannXi s = 0) :
    0 < s.re ∧ s.re < 1 := by
  constructor
  · by_contra h
    exact riemannXi_ne_zero_of_re_le_zero (not_lt.mp h) hs
  · by_contra h
    exact riemannXi_ne_zero_of_one_le_re (not_lt.mp h) hs

/-! ## Inside the strip, `ξ` and `ζ` have the same zeros and multiplicities -/

theorem riemannXi_eq_zero_iff {s : ℂ} (hs : 0 < s.re) (hs1 : s ≠ 1) :
    riemannXi s = 0 ↔ riemannZeta s = 0 := by
  rw [riemannXi_eq_mul_riemannZeta hs hs1]
  constructor
  · intro h
    exact (mul_eq_zero.mp h).resolve_left (xiPrefactor_ne_zero hs hs1)
  · intro h; rw [h, mul_zero]

/-- `ξ` and `ζ` agree up to a nonvanishing analytic factor on a neighbourhood of
any point of the open right half plane other than `1`. -/
theorem riemannXi_eventuallyEq {s : ℂ} (hs : 0 < s.re) (hs1 : s ≠ 1) :
    riemannXi =ᶠ[nhds s] fun z => xiPrefactor z * riemannZeta z := by
  have hopen : IsOpen {z : ℂ | 0 < z.re ∧ z ≠ 1} := by
    have h1 : IsOpen {z : ℂ | 0 < z.re} := isOpen_lt continuous_const Complex.continuous_re
    have h2 : IsOpen ({(1 : ℂ)}ᶜ : Set ℂ) := isOpen_compl_singleton
    have : {z : ℂ | 0 < z.re ∧ z ≠ 1} = {z : ℂ | 0 < z.re} ∩ ({(1 : ℂ)}ᶜ : Set ℂ) := by
      ext z; simp [Set.mem_inter_iff, and_comm]
    rw [this]; exact h1.inter h2
  filter_upwards [hopen.mem_nhds ⟨hs, hs1⟩] with z hz
  exact riemannXi_eq_mul_riemannZeta hz.1 hz.2

/-- **Multiplicities agree.**  Inside the open right half plane and away from
`1`, the analytic order of `ξ` equals that of `ζ`.  This is what stops a double
zero of `ζ` from being counted once by the argument principle. -/
theorem analyticOrderAt_riemannXi {s : ℂ} (hs : 0 < s.re) (hs1 : s ≠ 1) :
    analyticOrderAt riemannXi s = analyticOrderAt riemannZeta s := by
  have hpre : AnalyticAt ℂ xiPrefactor s := analyticAt_xiPrefactor hs
  have hzeta : AnalyticAt ℂ riemannZeta s := analyticOn_riemannZeta s (by simpa using hs1)
  have hprod : analyticOrderAt (fun z => xiPrefactor z * riemannZeta z) s
      = analyticOrderAt xiPrefactor s + analyticOrderAt riemannZeta s :=
    analyticOrderAt_mul hpre hzeta
  have hpre0 : analyticOrderAt xiPrefactor s = 0 :=
    hpre.analyticOrderAt_eq_zero.mpr (xiPrefactor_ne_zero hs hs1)
  rw [analyticOrderAt_congr (riemannXi_eventuallyEq hs hs1), hprod, hpre0, zero_add]

/-! ## `ζ` has no zeros on the imaginary axis

This is what makes the *left* vertical side of the critical rectangle free of
zeros, and hence lets the closed rectangle `[0,1] × [-T,T]` be used without
worrying about `ζ` zeros on its boundary. -/

theorem riemannZeta_ne_zero_of_re_eq_zero {s : ℂ} (hs : s.re = 0) : riemannZeta s ≠ 0 := by
  rcases eq_or_ne s 0 with rfl | hs0
  · rw [riemannZeta_zero]; norm_num
  intro hzero
  -- `Gammaℝ s ≠ 0` : the zeros of `Gammaℝ` are the nonpositive even integers,
  -- which meet the imaginary axis only at the origin.
  have hG : Complex.Gammaℝ s ≠ 0 := by
    rw [Ne, Complex.Gammaℝ_eq_zero_iff]
    rintro ⟨n, rfl⟩
    apply hs0
    have hre : (-(2 * (n : ℂ))).re = -(2 * (n : ℝ)) := by simp
    rw [hre] at hs
    have hn : (n : ℝ) = 0 := by linarith
    have hn' : (n : ℂ) = 0 := by exact_mod_cast hn
    rw [hn']; ring
  have hLam : completedRiemannZeta s = 0 := by
    rw [completedRiemannZeta_eq_Gammaℝ_mul hs0 hG, hzero, mul_zero]
  have hLam' : completedRiemannZeta (1 - s) = 0 := by
    rw [completedRiemannZeta_one_sub]; exact hLam
  have hre : (1 - s).re = 1 := by rw [Complex.sub_re, Complex.one_re, hs]; ring
  have hne0 : (1 : ℂ) - s ≠ 0 := by
    intro h
    rw [h] at hre; simp at hre
  have hG' : Complex.Gammaℝ (1 - s) ≠ 0 :=
    Complex.Gammaℝ_ne_zero_of_re_pos (by rw [hre]; norm_num)
  rw [completedRiemannZeta_eq_Gammaℝ_mul hne0 hG'] at hLam'
  exact riemannZeta_ne_zero_of_one_le_re (by rw [hre])
    ((mul_eq_zero.mp hLam').resolve_left hG')

/-- **`ξ` and `ζ` have exactly the same zeros in the closed critical strip.**
Both vertical sides `re = 0` and `re = 1` are free of zeros of both functions. -/
theorem riemannXi_eq_zero_iff_riemannZeta {s : ℂ} (h0 : 0 ≤ s.re) (h1 : s.re ≤ 1) :
    riemannXi s = 0 ↔ riemannZeta s = 0 := by
  rcases eq_or_lt_of_le h0 with hz | hpos
  · constructor
    · intro h; exact absurd h (riemannXi_ne_zero_of_re_le_zero (by rw [← hz]))
    · intro h; exact absurd h (riemannZeta_ne_zero_of_re_eq_zero hz.symm)
  rcases eq_or_ne s 1 with rfl | hs1
  · constructor
    · intro h; rw [riemannXi_one] at h; norm_num at h
    · intro h; exact absurd h riemannZeta_one_ne_zero
  exact riemannXi_eq_zero_iff hpos hs1

/-- Multiplicities agree at every zero of `ξ`, with no side condition: a zero of
`ξ` is automatically interior to the strip. -/
theorem analyticOrderAt_riemannXi_of_eq_zero {s : ℂ} (hs : riemannXi s = 0) :
    analyticOrderAt riemannXi s = analyticOrderAt riemannZeta s := by
  obtain ⟨hlo, hhi⟩ := re_mem_Ioo_of_riemannXi_eq_zero hs
  refine analyticOrderAt_riemannXi hlo ?_
  intro h
  rw [h, Complex.one_re] at hhi
  exact absurd hhi (lt_irrefl 1)

/-! ## Finiteness of the order everywhere -/

/-- `ξ` does not vanish on any open set: it is entire and `ξ(1) = 1/2 ≠ 0`. -/
theorem analyticOrderAt_riemannXi_ne_top (s : ℂ) : analyticOrderAt riemannXi s ≠ ⊤ := by
  have hone : analyticOrderAt riemannXi 1 ≠ ⊤ := by
    rw [Ne, analyticOrderAt_eq_top]
    intro hev
    have h1 : riemannXi 1 = 0 := hev.self_of_nhds
    rw [riemannXi_one] at h1
    norm_num at h1
  exact analyticOnNhd_riemannXi.analyticOrderAt_ne_top_of_isPreconnected
    (isPreconnected_univ) (Set.mem_univ 1) (Set.mem_univ s) hone

theorem meromorphicAt_riemannXi (s : ℂ) : MeromorphicAt riemannXi s :=
  (analyticAt_riemannXi s).meromorphicAt

theorem meromorphicOn_riemannXi (S : Set ℂ) : MeromorphicOn riemannXi S :=
  fun s _ => meromorphicAt_riemannXi s

theorem meromorphicOn_logDeriv_riemannXi (S : Set ℂ) :
    MeromorphicOn (logDeriv riemannXi) S :=
  (meromorphicOn_riemannXi S).logDeriv

theorem meromorphicOrderAt_riemannXi_ne_top (s : ℂ) :
    meromorphicOrderAt riemannXi s ≠ ⊤ := by
  rw [(analyticAt_riemannXi s).meromorphicOrderAt_eq]
  simpa using analyticOrderAt_riemannXi_ne_top s

end SparkInterval.Zeta
