/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.HardyZ
import SparkInterval.Zeta.TuringMethod

/-!
# The finite-height Riemann hypothesis from a Hardy-`Z` sign scan plus a Turing
window

This file states, as a single theorem, exactly what a compute campaign has to
produce in order to prove

```text
∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = 1/2.
```

Both halves of the argument now exist as Lean theorems:

* the **lower** half -- `count` disjoint sign-change brackets of the genuine
  Hardy `Z` give `count` distinct zeros of `ζ` on the critical line
  (`SparkInterval.Zeta.HardyZ`, unconditional: the evaluator contract is
  discharged, not assumed);
* the **upper** half -- Turing's averaging/staircase/pinning argument bounds the
  total zero count in the same rectangle by `count`
  (`SparkInterval.Zeta.TuringMethod`).

When the two counts meet, every zero is forced onto the line.

The remaining hypotheses are precisely the campaign's obligations; see
`docs/algorithms/ZETA_LEAN_INTERFACE_CONTRACT.md` for the field-by-field
reading of what must be produced and by whom.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set

/-- **Finite-height RH from a certified sign scan and one Turing window.**

Hypotheses, by producer:

* `family`, `hcheck` -- the ordered rational bracket table and its decidable
  check (campaign, kernel-verified);
* `hencloses` -- rigorous enclosures of the Hardy function `hardyZ` at the
  rational bracket endpoints (campaign; this is the only place a numerical
  evaluation enters the lower half);
* `hlower`, `hupper` -- all brackets lie inside `[-height, height]` (campaign);
* `hN`, `input` -- the Riemann-von Mangoldt counting formula on the averaging
  window `[height, height + h]` together with the averaged `S` bound (analytic
  theory: argument principle plus a Turing/Lehman-type citation);
* `gamma`, `mult`, `hmem`, `hstair` -- the zeros already located inside the
  averaging window, with certified ordinates and multiplicity lower bounds
  (campaign);
* `hpin` -- one strict inequality between explicitly computed real numbers
  (campaign, interval arithmetic).

Everything else is proved. -/
theorem zeta_zeros_on_criticalLine_of_scan_and_turing
    {height h : ℝ} {count : ℕ} (hh : 0 < h)
    (family : RationalBracketFamily count)
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints hardyZ)
    (hlower : ∀ i, -height ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ height)
    {N : ℝ → ℝ} (hN : SymmetricCountFunction N)
    (input : TuringAnalyticInput N height h)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc height (height + h))
    (hstair : ∀ t ∈ Icc height (height + h),
      N height + ∑ i, (if gamma i < t then mult i else 0) ≤ N t)
    (hpin :
      ((∫ t in height..(height + h), input.F t) + input.sBound -
        ∑ i, mult i * (height + h - gamma i)) / h < (count : ℝ) + 1) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  hardyZ_verifyEndpointFamily family hcheck hencloses hlower hupper
    (zetaZeroCountUpperBound_of_turing hN hh input gamma mult hmem hstair hpin)

/-- The same capstone for the touching-endpoint bracket family, which permits
consecutive brackets to share a closed endpoint. -/
theorem zeta_zeros_on_criticalLine_of_touching_scan_and_turing
    {height h : ℝ} {count : ℕ} (hh : 0 < h)
    (family : TouchingRationalBracketFamily count)
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints hardyZ)
    (hlower : ∀ i, -height ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ height)
    {N : ℝ → ℝ} (hN : SymmetricCountFunction N)
    (input : TuringAnalyticInput N height h)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc height (height + h))
    (hstair : ∀ t ∈ Icc height (height + h),
      N height + ∑ i, (if gamma i < t then mult i else 0) ≤ N t)
    (hpin :
      ((∫ t in height..(height + h), input.F t) + input.sBound -
        ∑ i, mult i * (height + h - gamma i)) / h < (count : ℝ) + 1) :
    ∀ z ∈ criticalRectangle height, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  hardyZ_verifyTouchingEndpointFamily family hcheck hencloses hlower hupper
    (zetaZeroCountUpperBound_of_turing hN hh input gamma mult hmem hstair hpin)

end SparkInterval.Zeta
