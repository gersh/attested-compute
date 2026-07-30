# The corrected reflected Turing bound for Dirichlet L-functions

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This note supplies the analytic half of item 5 of
[DIRICHLET_GRH_CAMPAIGN.md](DIRICHLET_GRH_CAMPAIGN.md): a derivation of the
paired Turing window formula that `tg_verifier/dirichlet_postprocess.py`
executes, a statement of exactly where it differs from the printed display in
[Platt, arXiv:1305.3087v1](https://arxiv.org/abs/1305.3087v1), and the list of
obligations that a Lean realization must still discharge.

It does **not** discharge the external atom. `production_accept`,
`literal_paper_theorem_3_2_accepted`, and `external_atom_discharged` all remain
false. Producing the analytic half is not authority to flip them.

## 1. Notation

Let `chi` be a primitive character modulo `q >= 3`, `a = a_chi` in `{0,1}` with
`chi(-1) = (-1)^a`, and

```text
Lambda(s,chi) = (q/pi)^((s+a)/2) Gamma((s+a)/2) L(s,chi).
```

`Lambda(.,chi)` is entire of order one, has no pole, and satisfies
`Lambda(s,chi) = epsilon_chi Lambda(1-s, bar-chi)` with
`epsilon_chi = tau(chi) / (i^a sqrt(q))` and `|epsilon_chi| = 1`.

Following Platt's Theorem 3.1, quoted from Booker (§4 of *Artin's conjecture,
Turing's method and the Riemann hypothesis*, Experiment. Math. 15 (2006)), set

```text
Phi_chi(t) = (1/pi) [ arg epsilon_chi
                      + (t/2) log(q/pi)
                      + Im log Gamma((1/2 + a + i t)/2) ],

S_chi(t)   = (1/pi) Im int_{+infinity}^{1/2} (L'/L)(sigma + i t, chi) d sigma,

N_chi(t)   = Phi_chi(t) + S_chi(t),
```

with `S_chi` made upper semicontinuous at zero ordinates. Booker's theorem says
that for `t1 < t2` the net number of zeros of `Lambda(.,chi)` with imaginary
part in `[t1,t2)`, counted with multiplicity, equals `N_chi(t2) - N_chi(t1)`.

Write `N_chi(t0)` (Platt's notation, and the quantity the campaign wants) for
the number of zeros of `L(s,chi)` with `Re s` in `(0,1)` and `|Im s| <= t0`,
counted with multiplicity, and let

```text
Ntilde_{t0,chi}(t) = #{ zeros of L(.,chi) with Im s in [t0,t) }.
```

Throughout, `t0 > 50` and `h > 0`, and neither `t0` nor `t0+h` is the ordinate
of a zero.

## 2. Reflection of the negative window

Because `chi` has real-analytic Dirichlet coefficients after conjugation,

```text
L(bar-s, bar-chi) = conj( L(s,chi) ),
```

so `(L'/L)(sigma - i t, bar-chi) = conj( (L'/L)(sigma + i t, chi) )`, and
taking imaginary parts of the defining integral gives the reflection identity

```text
S_chi(-t) = - S_bar-chi(t).                                            (2.1)
```

The same conjugation gives `Im log Gamma(conj z) = - Im log Gamma(z)` for the
gamma factor, whose argument is `(1/2 + a + i t)/2` with `a` real, so

```text
Phi_chi(t0) - Phi_chi(-t0)
  = (1/pi) [ t0 log(q/pi) + 2 Im log Gamma((1/2 + a + i t0)/2) ].       (2.2)
```

The term `arg epsilon_chi` cancels identically in (2.2). This is the whole
point of the reflection: `epsilon_chi` is fixed only up to the numerical
convention used to compute the Gauss sum, and no branch choice for it survives
into the formula. No caller-supplied phase anchor is consumed anywhere in the
executable path.

Since neither `t0` nor `-t0` is a zero ordinate, Booker's theorem applied with
`t1 = -t0`, `t2 = t0` counts precisely the zeros with `|Im s| <= t0`:

```text
N_chi(t0) = N_chi(t0) - N_chi(-t0)                       (Booker, net count)
          = (1/pi) [ t0 log(q/pi) + 2 Im log Gamma((1/2 + a + i t0)/2) ]
            + S_chi(t0) + S_bar-chi(t0).                                (2.3)
```

Equation (2.3) is an exact identity. **It has no additive constant.**

### Independent confirmation

(2.3) is not a rearrangement peculiar to this note. Trudgian, *An improved
upper bound for the error in the zero-counting formulae for Dirichlet
L-functions and Dedekind zeta-functions*, Math. Comp. 84 (2015), no. 293,
1439-1450 ([arXiv:1206.1844v4](https://arxiv.org/abs/1206.1844), §2),
derives the same identity from Cauchy's theorem and the functional equation.
His display (2.3), in his notation with `k = q` and `N(T,chi)` the count of
zeros with `0 < beta < 1` and `|gamma| <= T`, reads

```text
N(T,chi) = (T/pi) log(k/pi)
           + (2/pi) Im log Gamma(1/4 + a/2 + i T/2)
           + (1/pi) Delta_C arg L(s,chi),
```

and `(1/pi) Delta_C arg L(s,chi) = S_chi(T) + S_bar-chi(T)` because the contour
`C` runs from `1/2 - iT` out to `sigma_1 - iT`, up to `sigma_1 + iT`, and back
to `1/2 + iT`, with the vertical contribution vanishing as `sigma_1 -> infinity`.
Trudgian's identity carries no additive constant either.

## 3. Turing averaging and the normalization asymmetry

`N_chi(.)` is nondecreasing, and for `t` in `[t0, t0+h]` the zeros gained
between `t0` and `t` are those of `chi` with ordinate in `(t0,t]` together with
those of `chi` with ordinate in `[-t,-t0)`; the latter are, by conjugation,
exactly the zeros of `bar-chi` with ordinate in `(t0,t]`. Hence, off a finite
set,

```text
N_chi(t) = N_chi(t0) + Ntilde_{t0,chi}(t) + Ntilde_{t0,bar-chi}(t).
```

Integrating over `[t0, t0+h]` and using (2.3) on the left:

```text
h N_chi(t0) + int Ntilde_{t0,chi} + int Ntilde_{t0,bar-chi}
   = (1/pi) [ ((2 h t0 + h^2)/2) log(q/pi)
              + 2 int_{t0}^{t0+h} Im log Gamma((1/2 + a + i t)/2) dt ]
     + int S_chi + int S_bar-chi,
```

all integrals over `[t0, t0+h]`; the elementary integral used is
`int_{t0}^{t0+h} t dt = (2 h t0 + h^2)/2`. Dividing by `h`:

> **Theorem (corrected reflected Turing identity).** For `chi` primitive
> modulo `q >= 3`, `h > 0`, and `t0 > 0` such that neither `t0` nor `t0+h` is
> the ordinate of a zero of `L(.,chi)`,
>
> ```text
> N_chi(t0) = (1/(h pi)) [ ((2 h t0 + h^2)/2) log(q/pi)
>                          + 2 int_{t0}^{t0+h} Im log Gamma((1/2+a+i t)/2) dt ]
>             - (1/h) [ int Ntilde_{t0,chi} + int Ntilde_{t0,bar-chi} ]
>             + (1/h) [ int S_chi + int S_bar-chi ].                    (3.1)
> ```

The scaling asymmetry in (3.1) is forced and is **not** the bug:

- `Phi_chi` was *defined* with a `1/pi` in front, so the elementary and
  log-gamma terms that come out of it carry `1/pi`, and the `1/h` from the
  average makes `1/(h pi)`;
- `Ntilde` is a plain integer zero count carrying no `pi`, so it can only take
  the `1/h` from the average;
- `S_chi` already carries its own `1/pi` inside its definition, so it too can
  only take `1/h`.

Putting all four groups behind a single `1/(h pi)` divides two of them by `pi`
a second time. That is a dimensional inconsistency, not a normalization
convention, and it is what the arXiv v1 display does.

## 4. The upper bound actually used

Rumely's Theorem 2 (quoted as Platt Theorem 3.3) gives, for `t0 > 50` and
`h > 0`,

```text
| int_{t0}^{t0+h} S_chi(t) dt | <= 1.8397 + 0.1242 log( q (t0+h) / (2 pi) )
                                =: R(q,t0,h),
```

and the same bound holds for `bar-chi` with the same `q`, `t0`, `h`. Let
`B` be any subfamily of the true window zeros, each with a certified ordinate
enclosure and a certified multiplicity lower bound, and let

```text
Sigma_B = sum_{rho in B} m(rho) ( (t0+h) - gamma(rho) )
```

be the corresponding partial staircase integral, computed with outward
enclosures. Then `Sigma_B <= int Ntilde`, so from (3.1)

```text
N_chi(t0) <= (1/(h pi)) [ ((2 h t0 + h^2)/2) log(q/pi) + 2 int Im log Gamma ]
             - (1/h) [ Sigma_{B,chi} + Sigma_{B,bar-chi} ]
             + 2 R(q,t0,h) / h.                                        (4.1)
```

The inequality direction matters and is checked twice in code: the staircase
enters with a minus sign, so an *under*-estimate of the staircase (from an
incomplete bracket list, or from taking the low end of an ordinate enclosure)
weakens (4.1) in the safe direction, and the `+2R/h` slack is added, not
subtracted. `dirichlet_postprocess.paired_turing` computes (4.1) as an Arb
ball and then requires the ball's **upper** endpoint to be strictly below
`isolated_count_below_t0 + 1`, which is the only place the decision is made.
Combined with the certified lower bound `N_chi(t0) >= isolated_count_below_t0`
this pins the integer, which is the standard non-circular Turing argument.

## 5. The two defects in the printed display

Platt's Theorem 3.2 (arXiv:1305.3087v1, page 5) prints

```text
N_chi(t0) = (1/(h pi)) [ 2h + ((2 h t0 + h^2)/2) log(q/pi)
                         + 2 int Im log Gamma((1/2 + a_chi + i t)/2) dt
                         - int Ntilde_{t0,chi} - int Ntilde_{t0,bar-chi}
                         + int S_chi + int S_bar-chi ].
```

Comparing with (3.1) there are exactly two discrepancies.

### 5.1 The common denominator (a typesetting erratum)

The `Ntilde` and `S` integrals must carry `1/h`, not `1/(h pi)`. Numerically,
for the real primitive character modulo 3 with `t0 = 60`, `h = 100`, the
literal bracket-over-`h pi` evaluates to `[86.3 +/- 0.065]`, whereas two
independent argument-principle winding counts give `N_chi(60) = 44` exactly.
The literal display is wrong by a factor of roughly two on a quantity that has
to land inside a unit interval.

Three independent sources agree on the corrected placement:

1. the derivation of §3 above;
2. Trudgian's (2.3), which contains no `1/pi` on the `arg L` term relative to
   the gamma terms;
3. Platt's own released program, commit
   [`42b2142`](https://github.com/djplatt/code/blob/42b21426718e542daa2b006dc05ea2d7f26426e6/l-func-hi/find_zeros.cpp).
   In `turing_max` the sequence is
   `res = St_int(...); res -= Nright_int(...); tmp = ln_term(...) + im_int(...);
   tmp /= pi; res += tmp; res /= h`.
   Only the elementary/log-gamma group is divided by `pi`; the Rumely bound and
   the staircase are not. Everything is divided by `h`.

So the *computation* Platt performed used the correct scaling, and the printed
common-denominator display is a typesetting erratum. The accepted Bristol
manuscript repeats the same display; no published erratum was found.

### 5.2 The `+2h` term (a genuine spurious constant, conservative)

Under the corrected scaling the printed `2h` contributes `2h/(h pi) = 2/pi
= 0.63662...`, independent of `q`, `t0`, and `h`. The identity (3.1) has no
such term, and neither does Trudgian's (2.3). Platt's released code has it too:
`ln_term` ends with `mpfi_add(res,res,h1)`, adding one `h` per character inside
the group that is later divided by `pi`, and `find_zeros_cmplx` sums two
`turing_max` calls, giving `+2/pi` for the pair.

This repository previously retained the term "conservatively" because its sign
makes (4.1) weaker rather than stronger. That reasoning is sound as far as it
goes — a bound with `+2/pi` added is still a bound — but the term is not part
of the theorem, and it costs `0.6366` out of a decision budget whose total
width is `1`.

The term is now **refuted numerically**, not merely unproved. Under (3.1), if
the window bracket list is complete with exact multiplicities and
`N_chi(t0)` is known exactly, then the residual

```text
r := N_chi(t0)
     - (1/(h pi)) [ ((2 h t0 + h^2)/2) log(q/pi) + 2 int Im log Gamma ]
     + (1/h) [ int Ntilde_{t0,chi} + int Ntilde_{t0,bar-chi} ]
```

*is* `(int S_chi + int S_bar-chi)/h`, and Rumely's theorem forces
`|r| <= 2 R(q,t0,h)/h`. The `+2h` variant would instead require
`|r - 2/pi| <= 2 R(q,t0,h)/h`.

`tests/test_tg_dirichlet_postprocess.py`,
`test_turing_identity_holds_and_refutes_the_source_2h_constant`, certifies
`N_chi(t0)` and `N_chi(t0+h)` by two independent argument-principle winding
counts, certifies bracket-list completeness by matching the total bracket count
against the winding difference, bisects every ordinate to width `2^-20`, and
then evaluates both variants:

| q | Conrey | parity | t0 | h | N(t0) | N(t0+h) | brackets | residual `r` | `r - 2/pi` | envelope `2R/h` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 2 | odd | 3841/64 | 100 | 44 | 170 | 126 | -0.001256 | -0.637876 | 0.0475646 |
| 3 | 2 | odd | 7681/64 | 40 | 116 | 170 | 54 | +0.003084 | -0.633536 | 0.118912 |
| 4 | 3 | odd | 3841/64 | 40 | 50 | 100 | 50 | -0.006235 | -0.642855 | 0.117780 |
| 5 | 4 | even | 3841/64 | 40 | 54 | 108 | 54 | -0.034762 | -0.671381 | 0.119165 |
| 7 | 2 | even | 3841/64 | 40 | 61 | 118 | 57 | -0.009783 | -0.646403 | 0.121255 |
| 7 | 3 | odd | 3841/64 | 40 | 61 | 118 | 57 | -0.020294 | -0.656913 | 0.121255 |

Every row satisfies `|r| <= 2R/h` with margin, and every row violates
`|r - 2/pi| <= 2R/h` by a factor between `5` and `13`. The rows cover both
parities, real characters (`bar-chi = chi`) and genuinely complex conjugate
pairs (`q = 7`), and two different `(t0,h)` window shapes, so no single additive
or multiplicative constant fitted at one point can reproduce them.

`t0` and `t0+h` are shifted by `1/64` so that the argument-principle rectangle
never runs through a zero, which is the same convention the direct FLINT
backend uses.

Conclusion, stated plainly: **the manuscript's printed display is wrong in two
independent ways.** One is a typesetting erratum in the placement of `1/pi`
that Platt's own program does not share; the other is a spurious constant
`+2h` that Platt's program does share, which is harmless to the soundness of
his published bounds because it only weakens an upper bound, but which is not a
theorem and should not be carried by this repository. The repository's earlier
transcription of the corrected candidate was right about the scaling and wrong
to keep the constant. Both audit quantities are still emitted
(`literal_arxiv_v1_typeset_interval` and `platt_released_code_upper_bound`) so
a reviewer can see the discrepancy rather than have it silently erased.

### 5.3 Incidental: a defect in the released code's odd-parity gamma integral

While cross-checking `turing_max` against (3.1) a separate defect appeared in
the released `im_int2`, which is the antiderivative used for
`int Im log Gamma((1/2 + a + i t)/2) dt` when `a = 1`. From Stirling, with
`s > 0` real and `L(t) = log(s^2+t^2)`, `theta(t) = atan(t/s)`,

```text
int Im log Gamma(s + i t) dt
  = (s - 1/2) [ t theta(t) - (s/2) log(1 + t^2/s^2) ]
    + (1/4)(s^2+t^2) L(t) - (3/4) t^2 + O(log(...)),
```

so the coefficient of `log(1 + t^2/s^2)` is `-s(s-1/2)/2`. The even branch
`im_int1` (`s = 1/4`) uses `+1/32`, which is correct. The odd branch `im_int2`
(`s = 3/4`) should use `-3/32` but uses `-15/32`, and it computes `atan(t/3)`
where `atan(4t/3)` is intended (`mpfi_mul_ui(im_t,t,4)` is immediately
discarded by `mpfi_div_ui(im_t,t,3)`, which reads `t` rather than `im_t`).

At Platt's production window `t0 = 200`, `h = 10` the combined effect is about
`-0.075` inside the bracket, i.e. about `-0.0024` in the final count, which is
comfortably absorbed by the spurious `+2/pi` slack; at `t0 = 60`, `h = 100` it
is `-1.31`, which exceeds the routine's own declared error ball
`(t1-t0)/(4 t0)`. This repository does not use `im_int2`; it evaluates the
log-gamma integral directly with Arb's rigorous `acb.integral`. The point is
recorded only so that a future reviewer comparing against the released program
is not misled by an apparent agreement.

## 6. What the executable path now computes

`tg_verifier/dirichlet_postprocess.paired_turing` emits, per conjugate pair:

| Field | Meaning |
|---|---|
| `phi_over_h_pi_interval` | first line of (3.1) |
| `paired_staircase_over_h_interval` | `(Sigma_{B,chi} + Sigma_{B,bar-chi})/h` |
| `rumely_bound_per_character` | `R(q,t0,h)` |
| `paired_rumely_bound_over_h` | `2 R(q,t0,h)/h` |
| `source_normalized_model_interval` | (3.1) with the `S` pair replaced by the symmetric Rumely ball |
| `completion_upper_bound` | (4.1), the only quantity used for the decision |
| `identity_residual_interval` | `r` of §5.2 |
| `platt_released_code_upper_bound` | (4.1) `+ 2/pi`, audit only |
| `literal_arxiv_v1_typeset_interval` | the printed display, audit only |
| `source_two_over_pi_contribution` | `2/pi`, audit only |

An optional request flag `window_complete_and_count_exact_certified` asserts
that the bracket list is complete with exact multiplicities and that
`isolated_count_below_t0` equals `N_chi(t0)` exactly. When set, the module
additionally requires `|r| <= 2 R(q,t0,h)/h` and fails closed otherwise. That
check is what the multi-conductor KAT drives; production requests, which only
have a staircase lower bound, leave it unset and rely on (4.1) alone.

## 7. What remains for a Lean realization

The analytic statement above is not yet a Lean theorem. A realization needs,
in dependency order:

1. **Completed L-function and functional equation.** `Lambda(s,chi)` as above,
   entire, order one, with `Lambda(s,chi) = epsilon_chi Lambda(1-s,bar-chi)`
   and `|epsilon_chi| = 1`, connected to `DirichletCharacter.LFunction`. Mathlib
   has the Dirichlet L-function and the completed form; what is missing is the
   packaging that Booker's argument consumes.
2. **Booker's Theorem 3.1 for the degree-one case.** The statement that
   `N_chi(t) = Phi_chi(t) + S_chi(t)` counts net zeros in `[t1,t2)`. This is an
   argument-principle statement for `Lambda`; the honest formal route is a
   direct Cauchy-theorem proof for this single case rather than a formalization
   of Booker's general degree-`r` framework. Trudgian's §2 is the shorter
   published path and gives (2.3) directly, skipping `Phi`/`S` bookkeeping.
3. **The reflection identity (2.1)** and `Im log Gamma(conj z) = -Im log Gamma(z)`
   on the relevant half-plane, including the branch bookkeeping that makes
   `arg epsilon_chi` cancel in (2.2). This is where an informal treatment can
   silently pick a branch; the Lean statement must quantify over the branch
   choice or fix it once and reuse it at both endpoints.
4. **The staircase averaging step of §3**, i.e.
   `int_{t0}^{t0+h} N_chi = h N_chi(t0) + int Ntilde_chi + int Ntilde_bar-chi`,
   with the measure-zero endpoint conventions handled. This is elementary but
   is the step where the `1/h` versus `1/(h pi)` distinction becomes visible,
   so it should be stated separately rather than folded into (3.1).
5. **Rumely's Theorem 2 as a cited atom**, `|int_{t0}^{t0+h} S_chi| <=
   1.8397 + 0.1242 log(q(t0+h)/(2 pi))` for `t0 > 50`, `h > 0`, primitive
   `chi`. This is a genuine external citation (Rumely, *Numerical computations
   concerning the ERH*, Math. Comp. 61 (1993), no. 203, Theorem 2) and should
   be recorded as a named axiom with the paper reference, not proved. Care is
   needed here: Rumely has a similarly titled joint paper with Ramare, *Primes
   in arithmetic progressions*, Math. Comp. 65 (1996), 397-425, which is a
   different paper and does not contain this bound. The constants must be read
   off the 1993 ERH paper before the citation atom is registered. Platt also
   records revised constants `2.17618` and `0.0679955` attributed to Trudgian
   by personal communication; those are **not** a published citation and must
   not be used in a Lean atom.
6. **The monotone-staircase inequality of §4**, that a certified subfamily of
   window zeros with multiplicity lower bounds gives `Sigma_B <= int Ntilde`,
   and therefore that (4.1) is an upper bound.
7. **The integer-pinning step**, that `isolated <= N_chi(t0) <= upper` with
   `upper < isolated + 1` forces `N_chi(t0) = isolated`.
8. **The interval-arithmetic bridge**, connecting the Arb ball emitted by
   `paired_turing` to the real quantity in (4.1), including the outward
   rounding of `log(q/pi)`, `acb.integral` on the log-gamma path, and the
   rational ordinate enclosures. This is the same bridge the other Dirichlet
   stages need and is not specific to Turing's method.

Items 1-4 are the mathematical content. Items 5-8 are bookkeeping that the
repository already performs elsewhere. Until at least items 1-4 and 6-7 exist
as Lean theorems over the recorded certificate format, this stage stays
`production_accept=false` and the atom stays undischarged.

## 8. Commands

```bash
.venv-tg-flint/bin/python -m unittest -v \
  tests.test_tg_dirichlet_postprocess
```

The multi-conductor identity KAT performs twelve argument-principle winding
counts and takes roughly 280 seconds on a DGX Spark GB10; the remaining tests
in that module run in well under a second.
