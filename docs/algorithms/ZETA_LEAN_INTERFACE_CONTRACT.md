# The Lean interface contract for the zeta (Platt PT21) campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This note says exactly what the compute campaign must produce so that the
finite-height Riemann hypothesis follows as a Lean theorem, and exactly which
pieces are already proved. It is the contract between the numerical campaign,
the certificate-checker work, and the analytic (Lean) work.

The single target theorem is

```lean
SparkInterval.Zeta.zeta_zeros_on_criticalLine_of_scan_and_turing :
  ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = 1/2
```

in `SparkInterval/Zeta/HardyZTuringCapstone.lean`. `riemannZeta` is Mathlib's,
`criticalRectangle height = [0,1] × [-height, height]`, and the theorem depends
only on `propext, Classical.choice, Quot.sound` — no `native_decide`, no
execution axiom, no citation axiom.

## 0. What changed

Before this work the repository had `HardyZModel`, an *abstract contract* for a
Hardy-`Z`-like evaluator, and nothing satisfying it. Every sign-change
certificate was therefore conditional on an unproved analytic statement about
whatever function the campaign actually computed.

Now `SparkInterval/Zeta/HardyZ.lean` defines the genuine Hardy `Z` in terms of
Mathlib's `riemannZeta` and proves the contract, so `hardyZModel height` is a
term, not a hypothesis. The load-bearing theorem is

```lean
completedRiemannZeta_im_criticalPoint (t : ℝ) :
  (completedRiemannZeta (1/2 + i t)).im = 0
```

— the completed zeta is *real* on the critical line, because conjugation on the
line is the functional-equation reflection `s ↦ 1 - s`. That is what makes a
sign change of a real function a proof that `ζ` has a zero.

## 1. Definitions the campaign must match

```text
theta t   = arg (Gamma (1/4 + i t/2)) - (t/2) log pi          -- riemannSiegelTheta
Z t       = Re (completedRiemannZeta (1/2 + i t)) / ‖Gammaℝ (1/2 + i t)‖   -- hardyZ
```

and the proved identities (all in `SparkInterval/Zeta/HardyZ.lean`):

| Lean name | statement |
|---|---|
| `hardyZ_ofReal` | `(Z t : ℂ) = exp (i * theta t) * riemannZeta (1/2 + i t)` |
| `norm_hardyZ` | `|Z t| = ‖riemannZeta (1/2 + i t)‖` |
| `hardyZ_eq_zero_iff` | `Z t = 0 ↔ riemannZeta (1/2 + i t) = 0` |
| `continuous_hardyZ` | `Continuous Z` |
| `Gammaℝ_criticalPoint_polar` | `Gammaℝ(1/2+it) = pi^(-1/4)‖Gamma(1/4+it/2)‖ · e^{i theta t}` |
| `hardyZ_mul_norm_Gammaℝ` | `Z t · ‖Gammaℝ(1/2+it)‖ = Re completedRiemannZeta (1/2+it)` |
| `hardyZ_pos_iff`, `hardyZ_neg_iff` | sign of `Z t` = sign of `Re completedRiemannZeta (1/2+it)` |

**Consequence for the campaign.** An evaluator may certify enclosures of any of
the three equivalent objects, whichever its arithmetic produces:

1. `e^{i theta t} zeta(1/2+it)` (Riemann-Siegel / FFT evaluators compute this);
2. `Re completedRiemannZeta (1/2+it)` (the completed function, real on the line);
3. `Z t` itself.

For (2), only the *sign* transfers for free (`hardyZ_pos_iff`); a full enclosure
of `Z` additionally needs an enclosure of `‖Gammaℝ(1/2+it)‖`, which is
`pi^(-1/4)‖Gamma(1/4+it/2)‖` by `Gammaℝ_criticalPoint_polar` and is a smooth
positive quantity with no cancellation.

## 2. The lower half: sign-change brackets (campaign obligation)

Target: `hardyZ_verifyEndpointFamily`. Required objects:

| Obligation | Lean type | Producer |
|---|---|---|
| ordered bracket table | `family : RationalBracketFamily count` | campaign |
| table check | `family.check = true` | kernel (`decide`) |
| endpoint enclosures | `∀ i, (family.entries i).EnclosesEndpoints hardyZ` | campaign |
| brackets inside the box | `∀ i, -height ≤ lower i`, `upper i ≤ height` | campaign |

`EnclosesEndpoints` unfolds to: for each bracket, a rational interval
containing `Z` at the rational left endpoint, and one containing `Z` at the
rational right endpoint. `RationalBracket.IsValid` (checked by `family.check`)
additionally requires those two intervals to have strictly opposite signs and
the brackets to be ordered and disjoint. So the numerical obligation is exactly:

> for each of the `count` brackets, two rational intervals with rational
> endpoints, proved to enclose `Z` at two rational ordinates, with opposite
> strict signs.

Nothing about the interior of a bracket is required, and no simplicity or
spacing assumption on zeros is used. `count` brackets give `count` *distinct*
zeros of `ζ` on the critical line inside the box.

## 3. The upper half: the Turing window

Target: `zetaZeroCountUpperBound_of_turing` in
`SparkInterval/Zeta/TuringMethod.lean`. The averaging window is
`[height, height + h]` with `h > 0`.

### 3.1 Analytic obligations (still to be proved in Lean — not axioms)

`SymmetricCountFunction N`:

* `mono` : `N` is nondecreasing;
* `dominates` : `∀ t m, (m : ℕ∞) ≤ zetaZeroMultiplicityCount t → (m : ℝ) ≤ N t`.

`zetaZeroMultiplicityCount t` is the sum of `analyticOrderAt riemannZeta` over
the zeros in the box of half height `t`, valued in `ℕ∞`, so an infinite order
cannot be silently truncated to zero.

**This obligation is now discharged for the canonical counting function.**
`symmetricCountFunction_zetaMultCount` proves `SymmetricCountFunction
zetaMultCount`, where `zetaMultCount t = (zetaZeroMultiplicityCount t).toNat`,
using `analyticOrderAt_riemannZeta_ne_top` (`ζ` vanishes on no open set, by the
identity theorem on the connected `{1}ᶜ` and `ζ(2) ≠ 0`) and
`zetaZeroMultiplicityCount_monotone`.  Use
`zeta_zeros_on_criticalLine_of_scan_and_canonical_turing`, which has no
unspecified counting function at all.

`TuringAnalyticInput N height h` bundles the Riemann-von Mangoldt formula and
the averaged error bound:

* `F`, `S : ℝ → ℝ` with `F_integrable`, `S_integrable` on the window;
* `counting_le : ∀ t ∈ [height, height+h], N t ≤ F t + S t` — the argument
  principle, in the one direction actually used;
* `sBound : ℝ` with `s_integral_le : ∫_{height}^{height+h} S ≤ sBound` — note
  this is the **one-sided** form, which is exactly what Rumely's Theorem 2 and
  Turing/Lehman-type results state.

These are the honest analytic gap. They are hypotheses of a theorem, not
axioms; nothing downstream is proved until someone constructs them.

### 3.2 Campaign obligations for the window

| Obligation | Lean type | Meaning |
|---|---|---|
| located ordinates | `gamma : Fin n → ℝ` | zeros found inside `[height, height+h]` |
| certified multiplicities | `mult : Fin n → ℝ` | multiplicity *lower* bounds |
| in-window | `hmem : ∀ i, gamma i ∈ Icc height (height+h)` | |
| staircase | `hstair : ∀ t ∈ Icc height (height+h), N height + ∑ i, (if gamma i < t then mult i else 0) ≤ N t` | the counting function really gained them |
| final comparison | `hpin : ((∫ F) + sBound - ∑ i, mult i * (height + h - gamma i)) / h < count + 1` | one strict real inequality |

Direction of safety, proved rather than asserted: the staircase enters `hpin`
with a minus sign, so an **incomplete** list of located zeros, or ordinate
enclosures taken at their left ends, or multiplicity *lower* bounds, all weaken
the conclusion rather than strengthen it. `sBound` is added, not subtracted.

`hpin` is the only place where a numerical decision is made, and it is a single
strict inequality between real numbers each of which is an outward-rounded
interval-arithmetic quantity.

## 4. What is proved versus what is owed

Proved, base trio only:

* Hardy `Z` exists, is real, has `|Z| = |zeta|`, is continuous, and satisfies
  the evaluator contract (`SparkInterval/Zeta/HardyZ.lean`);
* Turing averaging, exact staircase integration, and integer pinning
  (`SparkInterval/Zeta/TuringMethod.lean`);
* the composition of the two halves into finite-height RH
  (`SparkInterval/Zeta/HardyZTuringCapstone.lean`);
* finiteness and monotonicity of the zeta multiplicity count, hence
  `SymmetricCountFunction zetaMultCount` (`SparkInterval/Zeta/TuringMethod.lean`);
* the finite-set argument turning matched counts into "all zeros on the line"
  (`SparkInterval/Zeta/CriticalLine.lean`, pre-existing);
* distinct-count ≤ multiplicity-count (`SparkInterval/Zeta/MultiplicityCount.lean`,
  pre-existing).

Owed, in dependency order:

1. **Argument principle for the completed zeta on a rectangle**, giving
   `TuringAnalyticInput.counting_le` with the explicit `F`. Mathlib has the
   entire `completedRiemannZeta₀`, the functional equation, `Gammaℝ`, and
   `MeromorphicOn.divisor`; what is missing is the winding-number evaluation of
   the Gamma factor on the box boundary (Stirling).
2. **A Turing/Lehman-type averaged bound** `∫ S ≤ sBound`. This is a legitimate
   citation atom; record it with its paper reference rather than proving it.
3. **The enclosure bridge**: from the campaign's rational interval outputs to
   `EnclosesEndpoints hardyZ` and to the reals appearing in `hpin`. This is the
   same bridge the other stages need.

## 5. Dirichlet L-functions

The same programme for `DirichletCharacter.LFunction` needs one extra Mathlib
ingredient that does not yet exist: the conjugation symmetry
`L(conj s, conj chi) = conj L(s, chi)`. Mathlib has `completedLFunction`,
`gammaFactor`, `rootNumber`, and `IsPrimitive.completedLFunction_one_sub`, so
once the conjugation symmetry is proved (the same identity-theorem argument
Mathlib uses for `riemannZeta_conj`), the real-character case gives a Hardy
model exactly as here, and the reflected/paired Turing identity applies.

**Do not transcribe Platt arXiv:1305.3087v1 Theorem 3.2 as printed**: see
`DIRICHLET_TURING_REFLECTED_BOUND.md` and section 6 below.

## 6. Independent verification of the Platt Theorem 3.2 defects

The corrected reflected identity used by this repository, and the two defects
in the printed display, were re-verified independently for this note (argument
principle by winding number, mpmath, `dps = 25`, rectangle
`[-1/2, 3/2] × [-T, T]`, boundary step `0.01`):

* the printed display was read directly out of `platt-2013-grh.pdf`: all four
  groups sit inside a single bracket divided by `h*pi`, and the bracket opens
  with `2h`;
* pointwise identity check (no additive constant), residual
  `r(T) = N_chi(T) - (1/pi)[T log(q/pi) + 2 Im log Gamma((1/2+a+iT)/2)]`:

  All 19 residuals lie in `[-0.88, +1.44]` with mean `+0.03`; under the printed
  `+2h` they would have to centre on `+0.637`.

  | q | parity | T | winding `N(T)` | `r(T)` |
  |---:|---|---:|---:|---:|
  | 3 | odd | 20.03 / 30.07 / 40.11 / 50.05 / 60.13 | 8 / 16 / 26 / 34 / 46 | -0.271 / -0.180 / +0.823 / -0.881 / +0.632 |
  | 4 | odd | same | 10 / 20 / 28 / 40 / 50 | -0.105 / +1.066 / -0.850 / +0.536 / -0.874 |
  | 5 | even | same | 12 / 22 / 32 / 42 / 54 | +0.972 / +1.431 / +0.801 / -0.519 / -0.645 |
  | 7 | odd | 20.03 / 30.07 / 40.11 / 50.05 | 14 / 24 / 36 / 48 | +0.327 / -0.290 / +0.005 / -0.380 |

* Turing-averaged residual `(1/H) ∫_{20}^{60} [N(t) - main(t)] dt`, with the
  ordinate list proved complete by matching `2 × (#sign changes) = winding`:

  | q | complete? | averaged residual | value required by the printed `+2h` |
  |---:|---|---:|---:|
  | 3 | 46 = 2×23 | **+0.0107** | +0.6366 |
  | 5 | 54 = 2×27 | **+0.0252** | +0.6366 |

  The averaged residual is `(1/H)∫(S_chi + S_conj)`, which Rumely bounds; it
  sits at `0.01`-`0.03`, not at `2/pi = 0.6366`. The `+2h` term is **refuted**,
  confirming the branch finding.

* the incidental `im_int2` defect was confirmed by comparing the claimed
  Stirling antiderivative against numerical `∫ Im log Gamma(s+it) dt`. With the
  coefficient `-s(s-1/2)/2` of `log(1+t^2/s^2)` the numeric-minus-formula
  residual is `-0.0041` on `[200,210]` and `-0.0817` on `[60,160]`, *identical*
  for `s = 1/4` and `s = 3/4` (as it must be, since the omitted term does not
  depend on that coefficient). The even branch's `+1/32` equals
  `-s(s-1/2)/2` at `s = 1/4`, so `im_int1` is correct; the odd branch needs
  `-3/32` at `s = 3/4`, and `-15/32` leaves residuals `+0.033` and `+0.654`.
  The Stirling term is `(s-1/2) t atan(t/s)`, so at `s = 3/4` the intended
  argument is `atan(4t/3)`, not `atan(t/3)`.

As a by-product, the reality of the completed function on the critical line —
the Dirichlet analogue of `completedRiemannZeta_im_criticalPoint` — showed up
numerically as `max |Im Lambda| / |Lambda| ≈ 1e-22` at `dps = 25`.

Reproduce with the scripts recorded in the session scratchpad
(`turing_check.py`, `turing_avg.py`, `imint.py`); they need only `mpmath`.
