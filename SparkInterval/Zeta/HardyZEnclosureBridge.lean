/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.HardyZ

/-!
# From what an evaluator computes to `EnclosesEndpoints hardyZ`

`hardyZ_verifyEndpointFamily` consumes
`∀ i, (family.entries i).EnclosesEndpoints hardyZ`: an exact rational interval
containing the *real number* `Z t` at each rational ordinate `t`.  But
`hardyZ` is defined as a quotient,

```text
Z t = Re (completedRiemannZeta (1/2 + i t)) / ‖Gammaℝ (1/2 + i t)‖,
```

and no production evaluator computes it that way.  Riemann-Siegel and
FFT/band-limited evaluators produce the *rotated zeta*
`e^{i θ(t)} ζ(1/2 + i t)` as a complex number; a completed-zeta evaluator
produces `Re Λ(1/2 + i t)`.  This file states, once, what each of those two
outputs buys.

**Rotated zeta (the important case).**  `hardyZ_ofReal` says
`(Z t : ℂ) = e^{i θ(t)} ζ(1/2 + i t)`.  Taking real and imaginary parts gives

```text
Z t = Re (e^{i θ(t)} ζ(1/2 + i t)),     Im (e^{i θ(t)} ζ(1/2 + i t)) = 0.
```

So a certified *rectangular complex* enclosure of the evaluator's output
already contains `Z t` in its real component: no division, no enclosure of
`‖Gammaℝ‖`, no bound on `θ` is needed.  `enclosesEndpoints_of_rotatedZeta_re`
packages that as the `EnclosesEndpoints hardyZ` hypothesis directly.  The
vanishing imaginary part is worth recording separately: it is a free
*consistency check* on the numerics, since any certified enclosure of the
output must contain `0` in its imaginary component.

**Completed zeta.**  Here `Z t = Re Λ(1/2 + i t) / ‖Gammaℝ(1/2 + i t)‖` with a
strictly positive denominator, so only the *sign* transfers for free; the
magnitude does not.  Consequently `EnclosesEndpoints` is the wrong interface
for such an evaluator — an enclosure of `Re Λ` is not an enclosure of `Z`.
The right interface asks for strict sign data only, and
`hardyZ_verifyStrictSignBrackets` provides exactly that: it reproves the
end-to-end finite-height theorem from

```text
Z(lower i) < 0 < Z(upper i)   or   Z(upper i) < 0 < Z(lower i)
```

together with rational ordering and separation of the brackets, bypassing
`RationalBracket` and its interval fields entirely.  Sign changes are all the
intermediate value theorem ever used; the interval fields of
`RationalBracket` exist only to *certify* those signs by exact rational
comparison.  `hardyZ_verifyStrictSignBrackets_of_completedZeta` is the same
theorem with the sign hypothesis phrased on `Re Λ`.

The final section exhibits explicit terms of the wire types, so the interfaces
are visibly not uninhabited shells, and records honestly which single input the
`height = 0` instance still lacks.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Complex

open SparkInterval.Certificate

/-! ## (A) The rotated-zeta evaluator

A Riemann-Siegel or FFT evaluator computes the complex number
`e^{i θ(t)} ζ(1/2 + i t)`.  It is real, and it *is* `Z t`. -/

/-- **The rotated zeta is `Z`.**  `Z t = Re (e^{i θ(t)} ζ(1/2 + i t))`.

Immediate from `hardyZ_ofReal` by taking real parts. -/
theorem hardyZ_eq_re_rotatedZeta (t : ℝ) :
    hardyZ t = (hardyPhase t * riemannZeta (criticalPoint t)).re := by
  rw [← hardyZ_ofReal t, Complex.ofReal_re]

/-- **The rotated zeta is real.**  `Im (e^{i θ(t)} ζ(1/2 + i t)) = 0`.

Also immediate from `hardyZ_ofReal`, by taking imaginary parts.  For a
campaign this is a free consistency check: a correct certified enclosure of
the evaluator's output must contain `0` in its imaginary component. -/
theorem im_rotatedZeta_eq_zero (t : ℝ) :
    (hardyPhase t * riemannZeta (criticalPoint t)).im = 0 := by
  rw [← hardyZ_ofReal t, Complex.ofReal_im]

/-- The rotated zeta never vanishes off the zeta zeros, and its modulus is
`‖ζ(1/2 + i t)‖`; recorded so a campaign can sanity-check its enclosure
widths against the size of zeta. -/
theorem norm_rotatedZeta (t : ℝ) :
    ‖hardyPhase t * riemannZeta (criticalPoint t)‖ =
      ‖riemannZeta (criticalPoint t)‖ := by
  rw [norm_mul, norm_hardyPhase, one_mul]

/-- **The enclosure bridge for a rotated-zeta evaluator.**

If the two rational intervals stored in a bracket contain the *real parts* of
the evaluator's certified complex outputs at the two rational ordinates, then
the bracket encloses the endpoints of the genuine Hardy `Z`.  This is the
hypothesis `hardyZ_verifyEndpointFamily` asks for, obtained with no further
numerical work: no division by `‖Gammaℝ‖`, no enclosure of `θ`. -/
theorem enclosesEndpoints_of_rotatedZeta_re (bracket : RationalBracket)
    (hlo : bracket.lowerValue.ContainsReal
      ((hardyPhase (bracket.lower : ℝ) *
        riemannZeta (criticalPoint (bracket.lower : ℝ))).re))
    (hhi : bracket.upperValue.ContainsReal
      ((hardyPhase (bracket.upper : ℝ) *
        riemannZeta (criticalPoint (bracket.upper : ℝ))).re)) :
    bracket.EnclosesEndpoints hardyZ := by
  refine ⟨?_, ?_⟩
  · rwa [hardyZ_eq_re_rotatedZeta]
  · rwa [hardyZ_eq_re_rotatedZeta]

/-- The whole-family form of the previous lemma: this is literally the
`hencloses` argument of `hardyZ_verifyEndpointFamily`. -/
theorem enclosesEndpointsFamily_of_rotatedZeta_re {count : Nat}
    (family : RationalBracketFamily count)
    (hlo : ∀ i, (family.entries i).lowerValue.ContainsReal
      ((hardyPhase ((family.entries i).lower : ℝ) *
        riemannZeta (criticalPoint ((family.entries i).lower : ℝ))).re))
    (hhi : ∀ i, (family.entries i).upperValue.ContainsReal
      ((hardyPhase ((family.entries i).upper : ℝ) *
        riemannZeta (criticalPoint ((family.entries i).upper : ℝ))).re)) :
    ∀ i, (family.entries i).EnclosesEndpoints hardyZ := fun i =>
  enclosesEndpoints_of_rotatedZeta_re (family.entries i) (hlo i) (hhi i)

/-- End-to-end finite-height theorem stated directly on a rotated-zeta
evaluator: the certified data are rectangular complex enclosures of
`e^{i θ(t)} ζ(1/2 + i t)`, and only their real parts are used. -/
theorem hardyZ_verifyEndpointFamily_of_rotatedZeta {height : ℝ} {count : Nat}
    (family : RationalBracketFamily count)
    (hcheck : family.check = true)
    (hlo : ∀ i, (family.entries i).lowerValue.ContainsReal
      ((hardyPhase ((family.entries i).lower : ℝ) *
        riemannZeta (criticalPoint ((family.entries i).lower : ℝ))).re))
    (hhi : ∀ i, (family.entries i).upperValue.ContainsReal
      ((hardyPhase ((family.entries i).upper : ℝ) *
        riemannZeta (criticalPoint ((family.entries i).upper : ℝ))).re))
    (hlower : ∀ i, -height ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  hardyZ_verifyEndpointFamily family hcheck
    (enclosesEndpointsFamily_of_rotatedZeta_re family hlo hhi) hlower hupper
    totalUpper

/-! ## (B) The completed-zeta evaluator: signs only

`Z t = Re Λ(1/2 + i t) / ‖Gammaℝ(1/2 + i t)‖` and the denominator is strictly
positive, so the sign transfers but the magnitude does not. -/

/-- A positive real part of the completed zeta forces `Z t > 0`. -/
theorem hardyZ_sign_of_completedZeta_pos {t : ℝ}
    (h : 0 < (completedRiemannZeta (criticalPoint t)).re) : 0 < hardyZ t :=
  (hardyZ_pos_iff t).mpr h

/-- A negative real part of the completed zeta forces `Z t < 0`. -/
theorem hardyZ_sign_of_completedZeta_neg {t : ℝ}
    (h : (completedRiemannZeta (criticalPoint t)).re < 0) : hardyZ t < 0 :=
  (hardyZ_neg_iff t).mpr h

/-- The strict sign change of `Z` across a pair of ordinates, obtained from
strict sign data for `Re Λ` alone. -/
theorem hardyZ_strictSignChange_of_completedZeta {a b : ℝ}
    (h : ((completedRiemannZeta (criticalPoint a)).re < 0 ∧
            0 < (completedRiemannZeta (criticalPoint b)).re) ∨
          ((completedRiemannZeta (criticalPoint b)).re < 0 ∧
            0 < (completedRiemannZeta (criticalPoint a)).re)) :
    (hardyZ a < 0 ∧ 0 < hardyZ b) ∨ (hardyZ b < 0 ∧ 0 < hardyZ a) := by
  rcases h with ⟨hneg, hpos⟩ | ⟨hneg, hpos⟩
  · exact Or.inl ⟨hardyZ_sign_of_completedZeta_neg hneg,
      hardyZ_sign_of_completedZeta_pos hpos⟩
  · exact Or.inr ⟨hardyZ_sign_of_completedZeta_neg hneg,
      hardyZ_sign_of_completedZeta_pos hpos⟩

/-! ## (C) The sign-only end-to-end theorem

Because (B) yields signs and nothing else, `EnclosesEndpoints` is not the
interface a completed-zeta campaign can meet.  This section reproves the
end-to-end theorem from strict sign data, with no interval fields anywhere in
the hypotheses. -/

/-- **Finite-height theorem from strict sign data alone.**

The hypotheses are: rational bracket endpoints `lower i < upper i`, strictly
separated in index order, at which the genuine Hardy `Z` takes strictly
opposite signs, all lying inside `[-height, height]`, together with a zero
count upper bound equal to the number of brackets.  The conclusion is the
exact finite-height statement about Mathlib's `riemannZeta`.

This is the analogue of `hardyZ_verifyEndpointFamily` for evaluators whose
certified output determines the sign of `Z` but not its magnitude — in
particular, any evaluator of `Re completedRiemannZeta` on the critical line
(see `hardyZ_verifyStrictSignBrackets_of_completedZeta`).

The proof constructs the generic `ZeroCertificate` directly: strict signs give
`Bracket.SignChange`, rational separation gives `OrderedBrackets.separated`,
`continuous_hardyZ` discharges every bracket continuity premise, and
`(hardyZModel height).criticalLineZeroBridge` supplies the analytic bridge. -/
theorem hardyZ_verifyStrictSignBrackets {height : ℝ} {count : Nat}
    (lower upper : Fin count → ℚ)
    (hlt : ∀ i, lower i < upper i)
    (hsep : ∀ {i j : Fin count}, i < j → upper i < lower j)
    (hsign : ∀ i,
      (hardyZ (lower i : ℝ) < 0 ∧ 0 < hardyZ (upper i : ℝ)) ∨
      (hardyZ (upper i : ℝ) < 0 ∧ 0 < hardyZ (lower i : ℝ)))
    (hlow : ∀ i, -height ≤ (lower i : ℝ))
    (hupp : ∀ i, (upper i : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 := by
  let bracketAt : Fin count → Bracket := fun i =>
    { lower := (lower i : ℝ)
      upper := (upper i : ℝ)
      lower_lt_upper := by exact_mod_cast hlt i }
  let certificate : ZeroCertificate hardyZ count :=
    { brackets := bracketAt
      separated := by
        intro i j hij
        change ((upper i : ℚ) : ℝ) < ((lower j : ℚ) : ℝ)
        exact_mod_cast hsep hij
      signChange := by
        intro i
        rcases hsign i with ⟨hneg, hpos⟩ | ⟨hneg, hpos⟩
        · exact Or.inl ⟨hneg.le, hpos.le⟩
        · exact Or.inr ⟨hneg.le, hpos.le⟩ }
  let evidence : ZetaVerifierEvidence hardyZ height count :=
    { brackets := certificate
      continuous := fun _i => continuous_hardyZ.continuousOn
      liesIn := by
        intro i x hx
        have hx' : (lower i : ℝ) ≤ x ∧ x ≤ (upper i : ℝ) := hx
        exact ⟨(hlow i).trans hx'.1, hx'.2.trans (hupp i)⟩
      bridge := (hardyZModel height).criticalLineZeroBridge
      totalUpper := totalUpper }
  exact evidence.all_zeros_on_criticalLine

/-- **The completed-zeta corollary.**

Same conclusion, with the sign hypothesis stated on
`Re completedRiemannZeta (1/2 + i t)` — the quantity a completed-zeta
evaluator actually produces.  Nothing about the magnitude of `Re Λ`, and no
enclosure of `‖Gammaℝ‖`, is required. -/
theorem hardyZ_verifyStrictSignBrackets_of_completedZeta
    {height : ℝ} {count : Nat}
    (lower upper : Fin count → ℚ)
    (hlt : ∀ i, lower i < upper i)
    (hsep : ∀ {i j : Fin count}, i < j → upper i < lower j)
    (hsign : ∀ i,
      ((completedRiemannZeta (criticalPoint (lower i : ℝ))).re < 0 ∧
        0 < (completedRiemannZeta (criticalPoint (upper i : ℝ))).re) ∨
      ((completedRiemannZeta (criticalPoint (upper i : ℝ))).re < 0 ∧
        0 < (completedRiemannZeta (criticalPoint (lower i : ℝ))).re))
    (hlow : ∀ i, -height ≤ (lower i : ℝ))
    (hupp : ∀ i, (upper i : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  hardyZ_verifyStrictSignBrackets lower upper hlt hsep
    (fun i => hardyZ_strictSignChange_of_completedZeta (hsign i))
    hlow hupp totalUpper

/-- The rotated-zeta corollary of the same sign-only theorem: the campaign only
has to pin down the sign of the real part of `e^{i θ(t)} ζ(1/2 + i t)`. -/
theorem hardyZ_verifyStrictSignBrackets_of_rotatedZeta
    {height : ℝ} {count : Nat}
    (lower upper : Fin count → ℚ)
    (hlt : ∀ i, lower i < upper i)
    (hsep : ∀ {i j : Fin count}, i < j → upper i < lower j)
    (hsign : ∀ i,
      ((hardyPhase (lower i : ℝ) *
          riemannZeta (criticalPoint (lower i : ℝ))).re < 0 ∧
        0 < (hardyPhase (upper i : ℝ) *
          riemannZeta (criticalPoint (upper i : ℝ))).re) ∨
      ((hardyPhase (upper i : ℝ) *
          riemannZeta (criticalPoint (upper i : ℝ))).re < 0 ∧
        0 < (hardyPhase (lower i : ℝ) *
          riemannZeta (criticalPoint (lower i : ℝ))).re))
    (hlow : ∀ i, -height ≤ (lower i : ℝ))
    (hupp : ∀ i, (upper i : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 := by
  refine hardyZ_verifyStrictSignBrackets lower upper hlt hsep ?_ hlow hupp
    totalUpper
  intro i
  simpa only [hardyZ_eq_re_rotatedZeta] using hsign i

/-! ## (D) The interfaces are inhabited

Explicit terms of every wire type used above, so nothing here is an
uninhabited shell. -/

/-- An explicit `RationalBracket`.  The numbers are illustrative wire data
only: this term asserts *nothing* about `hardyZ`, it merely shows the checked
structure is inhabited and that its Boolean checker accepts. -/
def exampleBracket : RationalBracket where
  lower := 14
  upper := 15
  lowerValue := ⟨-1, -1 / 2⟩
  upperValue := ⟨1 / 2, 1⟩

/-- The exact rational checker accepts `exampleBracket`. -/
theorem exampleBracket_check : exampleBracket.check = true := by
  refine RationalBracket.check_eq_true.mpr ?_
  simp only [exampleBracket, RationalBracket.IsValid, RatInterval.IsValid]
  norm_num

/-- The empty bracket family, an explicit `RationalBracketFamily 0`. -/
def emptyBracketFamily : RationalBracketFamily 0 where
  entries := fun i => i.elim0

theorem emptyBracketFamily_check : emptyBracketFamily.check = true := by
  refine RationalBracketFamily.check_eq_true.mpr ⟨fun i => i.elim0, ?_⟩
  intro i _ _
  exact i.elim0

/-- The count-zero zero-count bound is available at any *negative* height,
because `criticalRectangle height` is then empty. -/
theorem zetaZeroCountUpperBound_of_neg {height : ℝ} (h : height < 0) :
    ZetaZeroCountUpperBound height 0 := by
  refine ⟨?_⟩
  have hempty : zetaZerosIn (criticalRectangle height) = ∅ := by
    ext z
    simp only [Set.mem_empty_iff_false, iff_false]
    rintro ⟨hz, -⟩
    rw [mem_criticalRectangle] at hz
    linarith [hz.2.2.1, hz.2.2.2]
  rw [hempty, Set.ncard_empty]

/-- **Unconditional instance of the sign-only pipeline.**

Every hypothesis of `hardyZ_verifyStrictSignBrackets` is discharged here with
no unproved input, at `count = 0` and `height = -1`.  Stated loudly: the
conclusion is *vacuous*, because `criticalRectangle (-1) = ∅`.  What this
exhibit demonstrates is only that the interface accepts real arguments and
produces the intended conclusion type — it is a type-level, not a
mathematical, non-vacuity witness. -/
theorem zeta_zeros_on_criticalLine_neg_height :
    ∀ z ∈ criticalRectangle (-1 : ℝ), riemannZeta z = 0 →
      z.re = (1 : ℝ) / 2 :=
  hardyZ_verifyStrictSignBrackets (count := 0) (fun i => i.elim0)
    (fun i => i.elim0) (fun i => i.elim0) (fun {i _} _ => i.elim0)
    (fun i => i.elim0) (fun i => i.elim0) (fun i => i.elim0)
    (zetaZeroCountUpperBound_of_neg (by norm_num))

/-- **The `height = 0` instance, with its one missing input named.**

At `height = 0` the rectangle is the real segment `[0,1] × {0}`, and
`count = 0` discharges every bracket hypothesis of
`hardyZ_verifyStrictSignBrackets`.  The single remaining input is
`ZetaZeroCountUpperBound 0 0`, i.e.

```text
riemannZeta σ ≠ 0   for every real σ with 0 ≤ σ ≤ 1.
```

That statement is **not** trivial and is **not** proved here.  Mathlib
supplies zeta nonvanishing only on `1 ≤ re s`
(`riemannZeta_ne_zero_of_one_le_re`); the classical argument for the rest of
the real segment goes through the Dirichlet eta function,
`(1 - 2^{1-s}) ζ(s) = Σ (-1)^{n-1} n^{-s}`, whose alternating series is
strictly positive for real `s ∈ (0,1)`, and that is not in Mathlib.  So this
theorem is stated *conditionally* on that one hypothesis rather than faked.
Everything else in the pipeline is discharged. -/
theorem zeta_real_segment_of_countUpperBound
    (totalUpper : ZetaZeroCountUpperBound (0 : ℝ) 0) :
    ∀ z ∈ criticalRectangle (0 : ℝ), riemannZeta z = 0 →
      z.re = (1 : ℝ) / 2 :=
  hardyZ_verifyStrictSignBrackets (count := 0) (fun i => i.elim0)
    (fun i => i.elim0) (fun i => i.elim0) (fun {i _} _ => i.elim0)
    (fun i => i.elim0) (fun i => i.elim0) (fun i => i.elim0) totalUpper

end SparkInterval.Zeta
