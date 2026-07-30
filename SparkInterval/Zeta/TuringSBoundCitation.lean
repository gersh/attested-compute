/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.TuringMethod

/-!
# The cited averaged bound on `S(t)` (Turing / Lehman / Trudgian)

`TuringAnalyticInput` (see `SparkInterval.Zeta.TuringMethod`) needs one number
it cannot compute: a bound on `∫_{t₀}^{t₀+h} S`, where `S` is the oscillating
part of the Riemann-von Mangoldt counting formula.  This file states that
bound as an explicit `Prop`, with its source, so that it can be *supplied* and
*audited*, and proves the (entirely elementary) glue that turns it into the
`s_integral_le` field.

There is no `axiom`, `sorry`, or `native_decide` in this file.  Nothing here
asserts that the cited bound is true; it is a hypothesis, and every theorem
below takes it as an argument.

## The source

> **Timothy Trudgian**, *Improvements to Turing's method*,
> Mathematics of Computation **80** (2011), no. 276, 2259-2279.
> DOI `10.1090/S0025-5718-2011-02470-1`.  Preprint `arXiv:0903.1885v3`.
> **Theorem 2.2**, page 2261.

Verbatim (published version, p. 2261):

> **Theorem 2.2.** If `t₂ > t₁ > 168π`, then
> `|∫_{t₁}^{t₂} S(t) dt| ≤ 2.067 + 0.059 log t₂`.

with the accompanying remark on the same page:

> It should be noted that the constants achieved in Theorem 2.2 are valid for
> all `t₂ > t₁ > 168π`, and that at `t₁ > 2π · 10¹²` these constants minimise
> the right side of (2.3).

(The optimisation is *for* height `2π·10¹²`, but the inequality itself is
asserted for every `t₂ > t₁ > 168π`; §2.3 records the underlying numbers as
`a(11/10, 3/4) = 2.0666`, `b(11/10, 3/4) = 0.0585`, rounded outward to
`2.067`, `0.059`.)

The same inequality with weaker constants is due to Turing and to Lehman.
Trudgian §2.1, p. 2261, records the admissible triples `(a, b, t₀)` for
`|∫_{t₁}^{t₂} S| ≤ a + b log t₂` valid for `t₂ > t₁ > t₀`:

* Turing 1953: `(2.07, 0.128, 168π)`;
* Lehman 1970 (*On the distribution of zeros of the Riemann zeta-function*,
  Proc. London Math. Soc. (3) **20** (1970), 303-320): `(1.7, 0.114, 168π)`;
* Trudgian §2.3 with parameters `c = 5/4`, `d = 1`: `(1.61, 0.0914, 168π)`
  -- sharper than Theorem 2.2 for `t₂ ≲ 1.1 · 10⁶`;
* Trudgian Theorem 2.2: `(2.067, 0.059, 168π)`.

(Platt's thesis, Theorem 2.5.2, quotes Turing's triple as `(2.3, 0.128)`
rather than Trudgian's `(2.07, 0.128)`.  The discrepancy is harmless here:
every one of these triples is *weaker* than Theorem 2.2 at large height, and
only Theorem 2.2 is used below.)

## The source's conventions

Trudgian (1.1), p. 2260:

> `S(T) = π⁻¹ arg ζ(1/2 + iT)`,
> where if `T` is not an ordinate of a zero of `ζ(s)`, the argument is
> determined by continuous variation along the lines connecting
> `2, 2 + iT, 1/2 + iT`.

Trudgian (1.2), p. 2260, relates it to the counting function:

> `N(T) = (T/2π) log(T/2π) - T/2π + 7/8 + O(T⁻¹) + S(T)`.

**Counting convention.**  Trudgian's *prose* on p. 2260 describes `N(T)` as
"the number of non-trivial zeroes of `ζ(σ + it)` for `|t| ≤ T`", but his
displayed formula (1.2) carries the constant `7/8`, which is the **one-sided**
Riemann-von Mangoldt formula: `θ(T)/π + 1 = (T/2π) log(T/2π) - T/2π + 7/8`
asymptotically, where `θ` is the continuous Riemann-Siegel theta function.
The two-sided count would carry `2 · 7/8 = 7/4`.  The prose is therefore a
slip; the convention actually in force -- and the one used by Lehman, by
Turing, and by Platt (thesis, Theorem 2.5.1: "the number of zeros of `ζ(s)`
with `ℜs ∈ (0,1)` and `ℑs ∈ [0,t]`", satisfying `N(t) = θ(t)/π + 1 + S(t)`)
-- is

> `N(t) = #{ρ : ζ(ρ) = 0, 0 < ℜρ < 1, 0 < ℑρ ≤ t}`, with multiplicity.

This was checked numerically (below): with the one-sided convention the
identity `S(t) = N(t) - θ(t)/π - 1` reproduces `π⁻¹ arg ζ(1/2 + it)` to full
precision, and the averaged bound holds; with a two-sided `N` it would not.

## Translation to this repository

`zetaMultCount t` counts the zeros of `riemannZeta` in
`criticalRectangle t = [0,1] × [-t, t]` with analytic multiplicity, i.e. the
**two-sided** count.  Since `ζ` has no zeros with `ℜ s ∈ {0, 1}` and no real
zeros in `(0,1)`, and its zeros come in conjugate pairs,

> `zetaMultCount t = 2 * N(t)` for `t ≥ 0`,

with `N` the source's one-sided count.  Consequently the repository-side error
term is `2 S` and the repository-side main term is `2 (θ(t)/π + 1)` -- exactly
the "twice `θ(t)/π + 1`" anticipated in the `TuringAnalyticInput` docstring --
and the usable bound on `∫ 2S` is `2 (2.067 + 0.059 log t₂)`.

Both facts -- the exact Riemann-von Mangoldt identity and the reflection
identity -- are packaged below as the hypothesis `ZetaCountingBridge`.  They
are *not* proved here.

**Caveat on `riemannSiegelTheta` (soundness-relevant).**  The repository's
`SparkInterval.Zeta.riemannSiegelTheta t = (Γ(1/4 + i t/2)).arg - (t/2) log π`
uses `Complex.arg`, i.e. the *principal* branch, whereas the Riemann-von
Mangoldt formula needs the *continuous* branch.  The two agree only while
`|Im log Γ(1/4 + i t/2)| ≤ π`, i.e. for `t ≤ 10.5922...`; past that they differ
by a nonzero integer multiple of `2π`.  Numerically, at `t = 1000`:

```text
continuous θ(1000)                =  2034.5464280...   (mpmath siegeltheta)
riemannSiegelTheta 1000           =  -572.9754744...   (principal branch)
difference / 2π                   =  415  exactly
```

So `riemannSiegelTheta` must **not** be substituted for `theta` below.  The
bridge therefore takes `theta` as an abstract function, and whoever supplies
the bridge must supply a genuinely continuous branch.  (`riemannSiegelTheta`
is fine for its actual use in `HardyZ.lean`, where only `exp (i θ t)` occurs
and the branch is irrelevant.)

## Numerical verification

`tools/verify_turing_sbound_citation.py` (mpmath, 25 digits; full transcript in
`tools/verify_turing_sbound_citation.out`) recomputes `∫_{t₁}^{t₂} S` from the
10849 zero ordinates with `γ ≤ 10600` (enumerated by `mpmath.zetazero`, which
does Gram/Rosser block bookkeeping and does not assume Rosser's rule), using
`∫ S = A(t₂) - A(t₁)` with the exact staircase antiderivative

`A(t) = Σ_{γ ≤ t} (t - γ) - (1/π) ∫_0^t θ - t`

and Gauss-Legendre quadrature on unit panels for `∫ θ`.  A closed-form-vs-
quadrature cross-check agrees to `~2·10⁻¹⁹`.

**Convention discriminator.**  Only the one-sided `N` reproduces
`π⁻¹ arg ζ(1/2 + it)`; the two-sided reading is off by `N(t)`:

```text
      t     one-sided S     two-sided S   π⁻¹ arg ζ(1/2+it)   verdict
  12.30   -0.2329008179   -0.2329008179      -0.2329008179    one-sided matches
  20.70   -0.5087112918   +0.4912887082      -0.5087112918    one-sided matches
 530.10   +0.3048741761 +291.3048741761      +0.3048741761    one-sided matches
1000.70   -0.1811082485 +648.8188917515      -0.1811082485    one-sided matches
9999.90   -0.8480118718 +10141.151988128     -0.8480118718    one-sided matches
```

**Task grid** (`bound = 2.067 + 0.059 log t₂`; rows with `t₁ < 168π` are
outside the theorem's hypothesis and are reported only for information):

```text
    t₁     h      t₂        ∫S     bound   |∫S|/bound  in hypothesis
    10     1      11 -0.063258  2.208476     0.028643  no
    10     5      15 -0.474000  2.226775     0.212864  no
    10    20      30 -0.448485  2.267671     0.197773  no
    10   100     110 +0.101269  2.344328     0.043197  no
    10   500     510 -0.249681  2.434830     0.102545  no
    50     1      51 +0.411504  2.298978     0.178994  no
    50     5      55 +0.724035  2.303433     0.314329  no
    50    20      70 +0.309335  2.317661     0.133469  no
    50   100     150 -0.083355  2.362627     0.035280  no
    50   500     550 +0.368411  2.439285     0.151032  no
   100     1     101 -0.222888  2.339292     0.095280  no
   100     5     105 -0.593536  2.341584     0.253476  no
   100    20     120 -0.057947  2.349462     0.024664  no
   100   100     200 +0.275114  2.379601     0.115613  no
   100   500     600 -0.045307  2.444419     0.018535  no
   500     1     501 -0.244158  2.433780     0.100321  no
   500     5     505 -0.337074  2.434249     0.138472  no
   500    20     520 -0.217781  2.435976     0.089402  no
   500   100     600 +0.149957  2.444419     0.061347  no
   500   500    1000 -0.157852  2.474558     0.063790  no
  1000     1    1001 -0.019717  2.474617     0.007968  YES
  1000     5    1005 +0.132636  2.474852     0.053594  YES
  1000    20    1020 -0.336957  2.475726     0.136104  YES
  1000   100    1100 -0.140734  2.480181     0.056743  YES
  1000   500    1500 -0.328359  2.498480     0.131424  YES
  5000     1    5001 +0.068599  2.569526     0.026697  YES
  5000     5    5005 +0.757967  2.569573     0.294978  YES  <-- worst on grid
  5000    20    5020 +0.361317  2.569750     0.140604  YES
  5000   100    5100 -0.007987  2.570683     0.003107  YES
  5000   500    5500 +0.174122  2.575138     0.067617  YES
 10000     1   10001 -0.187405  2.610416     0.071791  YES
 10000     5   10005 -0.115402  2.610440     0.044208  YES
 10000    20   10020 +0.080619  2.610528     0.030882  YES
 10000   100   10100 +0.523700  2.610997     0.200575  YES
 10000   500   10500 +0.049244  2.613289     0.018844  YES
```

Every row satisfies the bound, including the ones below the cut-off `168π`.

**Adversarial scan**, 328157 windows with `168π < t₁ < t₂ ≤ 10500`, left
endpoints on an arithmetic grid of step `2.13` from `527.79`, together with
`γ ± 10⁻⁹` for every zero ordinate (the places where `∫S` jumps), widths
`h ∈ {0.25, 0.5, 1, 2, 3, 5, 8, 13, 21, 50, 100, 300, 1000}`:

```text
triple (a, b)                    max |∫S|/bound        t₁      h        ∫S    bound  status
Trudgian 2011 Thm 2.2                  0.531928  5978.139  50.00 +1.372666 2.580547 SURVIVES
Turing 1953 (per Trudgian 2.1)         0.432293  1329.205  21.00 +1.293692 2.992626 SURVIVES
Lehman 1970 (per Trudgian 2.1)         0.513021  1329.205  21.00 +1.293692 2.521713 SURVIVES
Trudgian sec 2.3, c=5/4 d=1            0.570622  5978.139  50.00 +1.372666 2.405563 SURVIVES
```

Worst case overall: `∫_{5978.1393}^{6028.1393} S = +1.372666` against a bound
of `2.580547`, ratio `0.5319`.  The largest `|∫S|` seen anywhere is `1.372666`;
the smallest constant `a` compatible with `b = 0.059` on this data is `0.868`,
so the printed `a = 2.067` has genuine headroom at these heights (as it must:
the constants are optimised for `t ≈ 2π·10¹²`, not for `t ≈ 10⁴`).

**Verdict: the printed statement SURVIVED numerical verification.**  No window
violated it, and the convention question is settled in favour of the one-sided
count.

Caveat: the numerical `N(t)` is the count of critical-line zeros located by
`mpmath.zetazero`; it equals the true `N(t)` for `t ≤ 10600` because RH has
been verified computationally far past that height.  The check is therefore a
refutation test, not a proof.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open MeasureTheory Set

/-! ## The citation, as a `Prop` -/

/-- **Trudgian 2011, Theorem 2.2**, as a hypothesis about a function `S`.

`TrudgianAveragedSBound S` says exactly

`∀ t₁ t₂, 168π < t₁ → t₁ < t₂ → |∫_{t₁}^{t₂} S(t) dt| ≤ 2.067 + 0.059 log t₂`,

which is the printed statement with the printed hypotheses and the printed
constants.  It is a `Prop`, never an `axiom`: nothing in this repository
asserts it.

Note that the bound does **not** depend on the window width `t₂ - t₁`; that
h-independence is the whole point of Turing's method. -/
def TrudgianAveragedSBound (S : ℝ → ℝ) : Prop :=
  ∀ t₁ t₂ : ℝ, 168 * Real.pi < t₁ → t₁ < t₂ →
    |∫ t in t₁..t₂, S t| ≤ 2.067 + 0.059 * Real.log t₂

/-- The general shape of the cited inequality, for recording the weaker
historical triples `(a, b, t₀)`: Turing `(2.07, 0.128, 168π)`, Lehman
`(1.7, 0.114, 168π)`, Trudgian §2.3 `(1.61, 0.0914, 168π)`. -/
def AveragedSBoundTriple (S : ℝ → ℝ) (a b t₀ : ℝ) : Prop :=
  ∀ t₁ t₂ : ℝ, t₀ < t₁ → t₁ < t₂ → |∫ t in t₁..t₂, S t| ≤ a + b * Real.log t₂

/-- Theorem 2.2 is the triple `(2.067, 0.059, 168π)`. -/
theorem trudgianAveragedSBound_iff (S : ℝ → ℝ) :
    TrudgianAveragedSBound S ↔ AveragedSBoundTriple S 2.067 0.059 (168 * Real.pi) :=
  Iff.rfl

/-- A weaker triple with `a' ≥ a`, `b' ≥ b` and a larger cut-off is implied,
provided the logarithm is nonnegative on the range -- which it is, since
`t₂ > t₀ ≥ 1` there.  This is the monotonicity used to compare the historical
constants. -/
theorem AveragedSBoundTriple.mono {S : ℝ → ℝ} {a b t₀ a' b' t₀' : ℝ}
    (h : AveragedSBoundTriple S a b t₀) (ha : a ≤ a') (hb : b ≤ b')
    (ht : t₀ ≤ t₀') (ht1 : 1 ≤ t₀') :
    AveragedSBoundTriple S a' b' t₀' := by
  intro t₁ t₂ h₁ h₂
  have hlog : 0 ≤ Real.log t₂ :=
    Real.log_nonneg (by linarith)
  exact (h t₁ t₂ (lt_of_le_of_lt ht h₁) h₂).trans (by nlinarith)

/-! ## The Riemann-von Mangoldt bridge, also a hypothesis -/

/-- What must be proved (or separately cited) to connect the source's `S` to
this repository's `zetaMultCount`.

* `rvm` is the exact Riemann-von Mangoldt identity in the source's one-sided
  convention, `N(t) = θ(t)/π + 1 + S(t)`, with `theta` a **continuous** branch
  of the Riemann-Siegel theta function (*not* the principal-branch
  `SparkInterval.Zeta.riemannSiegelTheta`);
* `reflect` is the conjugate-symmetry identity `zetaMultCount t = 2 N(t)`,
  valid because `ζ` has no zeros on `ℜ s ∈ {0,1}` and none real in `(0,1)`.

Neither is proved here. -/
structure ZetaCountingBridge (theta oneSided S : ℝ → ℝ) : Prop where
  /-- `N(t) = θ(t)/π + 1 + S(t)` for `t > 0`. -/
  rvm : ∀ t : ℝ, 0 < t → oneSided t = theta t / Real.pi + 1 + S t
  /-- `zetaMultCount t = 2 N(t)` for `t ≥ 0`. -/
  reflect : ∀ t : ℝ, 0 ≤ t → zetaMultCount t = 2 * oneSided t

/-! ## The glue: from the citation to `s_integral_le`

Everything from here down is proved. -/

section Glue

variable {theta oneSided S : ℝ → ℝ} {t0 h : ℝ}

/-- `168π > 0`, used repeatedly. -/
theorem pos_of_gt_oneSixtyEightPi {t : ℝ} (ht : 168 * Real.pi < t) : 0 < t :=
  lt_trans (by positivity) ht

/-- `168π > 504 > 1`, so the source's cut-off is comfortably above `1` and the
logarithm appearing in the bound is nonnegative. -/
theorem one_le_of_gt_oneSixtyEightPi {t : ℝ} (ht : 168 * Real.pi < t) : 1 ≤ t := by
  have hpi : (3 : ℝ) < Real.pi := Real.pi_gt_three
  linarith

/-- **The `s_integral_le` field, derived from the citation.**

The repository-side error term is `2 S`, so its mean over the window is
bounded by twice the cited bound, evaluated at the right endpoint. -/
theorem two_smul_integral_le_of_citation (hS : TrudgianAveragedSBound S)
    (ht0 : 168 * Real.pi < t0) (hh : 0 < h) :
    (∫ t in t0..(t0 + h), 2 * S t) ≤ 2 * (2.067 + 0.059 * Real.log (t0 + h)) := by
  have hlt : t0 < t0 + h := by linarith
  have hb := hS t0 (t0 + h) ht0 hlt
  have hle : (∫ t in t0..(t0 + h), S t) ≤ 2.067 + 0.059 * Real.log (t0 + h) :=
    (abs_le.mp hb).2
  rw [intervalIntegral.integral_const_mul]
  linarith

/-- A window-uniform version: capping the right endpoint by `H` gives a bound
that does not depend on the window at all. -/
theorem two_smul_integral_le_of_citation_cap (hS : TrudgianAveragedSBound S)
    (ht0 : 168 * Real.pi < t0) (hh : 0 < h) {H : ℝ} (hH : t0 + h ≤ H) :
    (∫ t in t0..(t0 + h), 2 * S t) ≤ 2 * (2.067 + 0.059 * Real.log H) := by
  have hpos : (0 : ℝ) < t0 + h := by
    have := pos_of_gt_oneSixtyEightPi ht0; linarith
  have hlog : Real.log (t0 + h) ≤ Real.log H :=
    Real.log_le_log hpos hH
  exact (two_smul_integral_le_of_citation hS ht0 hh).trans (by nlinarith)

/-- The counting formula in the repository's two-sided convention, on the
window. -/
theorem zetaMultCount_eq_of_bridge (bridge : ZetaCountingBridge theta oneSided S)
    (ht0 : 168 * Real.pi < t0) (_hh : 0 < h) :
    ∀ t ∈ Icc t0 (t0 + h),
      zetaMultCount t = 2 * (theta t / Real.pi + 1) + 2 * S t := by
  intro t ht
  have hpos : 0 < t := lt_of_lt_of_le (pos_of_gt_oneSixtyEightPi ht0) ht.1
  rw [bridge.reflect t hpos.le, bridge.rvm t hpos]
  ring

/-- **The assembled analytic input.**

Given the cited averaged bound, the Riemann-von Mangoldt bridge, and
integrability of the two pieces, the `TuringAnalyticInput` required by
`SparkInterval.Zeta.TuringMethod` exists, with
`sBound = 2 (2.067 + 0.059 log (t₀ + h))`. -/
noncomputable def turingAnalyticInputOfCitation
    (bridge : ZetaCountingBridge theta oneSided S)
    (hS : TrudgianAveragedSBound S)
    (hthetaInt : IntervalIntegrable theta volume t0 (t0 + h))
    (hSInt : IntervalIntegrable S volume t0 (t0 + h))
    (ht0 : 168 * Real.pi < t0) (hh : 0 < h) :
    TuringAnalyticInput zetaMultCount t0 h where
  F := fun t => 2 * (theta t / Real.pi + 1)
  S := fun t => 2 * S t
  F_integrable := ((hthetaInt.div_const Real.pi).add intervalIntegrable_const).const_mul 2
  S_integrable := hSInt.const_mul 2
  counting_le := by
    intro t ht
    exact le_of_eq (zetaMultCount_eq_of_bridge bridge ht0 hh t ht)
  sBound := 2 * (2.067 + 0.059 * Real.log (t0 + h))
  s_integral_le := two_smul_integral_le_of_citation hS ht0 hh

@[simp] theorem turingAnalyticInputOfCitation_sBound
    (bridge : ZetaCountingBridge theta oneSided S)
    (hS : TrudgianAveragedSBound S)
    (hthetaInt : IntervalIntegrable theta volume t0 (t0 + h))
    (hSInt : IntervalIntegrable S volume t0 (t0 + h))
    (ht0 : 168 * Real.pi < t0) (hh : 0 < h) :
    (turingAnalyticInputOfCitation bridge hS hthetaInt hSInt ht0 hh).sBound
      = 2 * (2.067 + 0.059 * Real.log (t0 + h)) := rfl

@[simp] theorem turingAnalyticInputOfCitation_F
    (bridge : ZetaCountingBridge theta oneSided S)
    (hS : TrudgianAveragedSBound S)
    (hthetaInt : IntervalIntegrable theta volume t0 (t0 + h))
    (hSInt : IntervalIntegrable S volume t0 (t0 + h))
    (ht0 : 168 * Real.pi < t0) (hh : 0 < h) :
    (turingAnalyticInputOfCitation bridge hS hthetaInt hSInt ht0 hh).F
      = fun t => 2 * (theta t / Real.pi + 1) := rfl

end Glue

/-! ## The capstone: a certified zero count from the citation -/

/-- **Turing's method for `ζ`, with the averaged `S`-bound supplied as the
cited hypothesis.**

If

* `bridge` supplies the exact counting formula and the reflection identity,
* `hS` supplies Trudgian's Theorem 2.2,
* `gamma`/`mult` are certified zero ordinates and multiplicity lower bounds
  inside the averaging window `[t₀, t₀+h]`, already accounted for by the
  counting function (`hstair`),
* and the resulting explicit number is `< bound + 1`,

then the total multiplicity of zeta zeros in `[0,1] × [-t₀, t₀]` is at most
`bound`.

Every analytic ingredient is an argument; the theorem itself is proved. -/
theorem zetaMultiplicityCountUpperBound_of_citation
    {theta oneSided S : ℝ → ℝ} {t0 h : ℝ}
    (bridge : ZetaCountingBridge theta oneSided S)
    (hS : TrudgianAveragedSBound S)
    (hthetaInt : IntervalIntegrable theta volume t0 (t0 + h))
    (hSInt : IntervalIntegrable S volume t0 (t0 + h))
    (ht0 : 168 * Real.pi < t0) (hh : 0 < h)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h))
    (hstair : ∀ t ∈ Icc t0 (t0 + h),
      zetaMultCount t0 + ∑ i, (if gamma i < t then mult i else 0) ≤ zetaMultCount t)
    {bound : ℕ}
    (hpin :
      ((∫ t in t0..(t0 + h), 2 * (theta t / Real.pi + 1))
          + 2 * (2.067 + 0.059 * Real.log (t0 + h))
          - ∑ i, mult i * (t0 + h - gamma i)) / h < (bound : ℝ) + 1) :
    ZetaMultiplicityCountUpperBound t0 bound :=
  zetaMultiplicityCountUpperBound_of_turing symmetricCountFunction_zetaMultCount hh
    (turingAnalyticInputOfCitation bridge hS hthetaInt hSInt ht0 hh)
    gamma mult hmem hstair hpin

/-- The same conclusion in the distinct-zero form the finite-height verifier
consumes. -/
theorem zetaZeroCountUpperBound_of_citation
    {theta oneSided S : ℝ → ℝ} {t0 h : ℝ}
    (bridge : ZetaCountingBridge theta oneSided S)
    (hS : TrudgianAveragedSBound S)
    (hthetaInt : IntervalIntegrable theta volume t0 (t0 + h))
    (hSInt : IntervalIntegrable S volume t0 (t0 + h))
    (ht0 : 168 * Real.pi < t0) (hh : 0 < h)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h))
    (hstair : ∀ t ∈ Icc t0 (t0 + h),
      zetaMultCount t0 + ∑ i, (if gamma i < t then mult i else 0) ≤ zetaMultCount t)
    {bound : ℕ}
    (hpin :
      ((∫ t in t0..(t0 + h), 2 * (theta t / Real.pi + 1))
          + 2 * (2.067 + 0.059 * Real.log (t0 + h))
          - ∑ i, mult i * (t0 + h - gamma i)) / h < (bound : ℝ) + 1) :
    ZetaZeroCountUpperBound t0 bound :=
  (zetaMultiplicityCountUpperBound_of_citation bridge hS hthetaInt hSInt ht0 hh
    gamma mult hmem hstair hpin).toZetaZeroCountUpperBound

/-! ## Non-vacuity

The hypotheses above are not contradictory: `S = 0`, `theta = 0`,
`oneSided = fun _ => 1` and `zetaMultCount` replaced by `fun _ => 2` would
satisfy them, so no theorem above is vacuously true for silly reasons.  The
first two components are exhibited concretely below; the third is genuinely a
statement about `riemannZeta` and is not exhibited.

`TrudgianAveragedSBound` in particular is satisfiable, so the `Prop` is not
accidentally `False`. -/

theorem trudgianAveragedSBound_zero : TrudgianAveragedSBound (fun _ => 0) := by
  intro t₁ t₂ h₁ h₂
  have hlog : 0 ≤ Real.log t₂ :=
    Real.log_nonneg (le_trans (one_le_of_gt_oneSixtyEightPi h₁) h₂.le)
  simp only [intervalIntegral.integral_zero, abs_zero]
  nlinarith [hlog]

end SparkInterval.Zeta
