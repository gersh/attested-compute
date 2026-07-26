# Platt Appendix C interpolation source map

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

This note maps the interpolation used by the pinned `zeta_arb` program to
Appendix C of D. J. Platt, *Isolating some non-trivial zeros of zeta*, Math.
Comp. 86 (2017), 2449--2467, DOI
[`10.1090/mcom/3198`](https://doi.org/10.1090/mcom/3198).  The
[public author manuscript](https://research-information.bris.ac.uk/ws/portalfiles/portal/78836669/platt_zeta_submitted.pdf)
contains the full Appendix C.  Platt and Trudgian's later
[3-trillion verification](https://arxiv.org/abs/2004.09765) says explicitly
that it uses that algorithm with Arb and parameters optimized for the higher
range.

The conclusion is narrower than “interpolation is proved.”  The finite
140-term interval arithmetic is certificate-friendly, but three analytic
facts remain to be formalized or retained as clearly named source premises:

1. the scaled completed-zeta growth bound in Lemma C.2;
2. the corrected omitted-tail estimate in Lemma C.3; and
3. the non-bandlimited Fourier-tail estimate in Lemma C.1, used through
   Weiss's theorem.

[`PlattLemmaC3.lean`](../../SparkInterval/Zeta/PlattLemmaC3.lean) gives these
facts an exact Lean boundary and proves the sinc, majorant, and error-composition
steps available from Mathlib.  It introduces no axiom.
[`PlattAppendixCBridge.lean`](../../SparkInterval/Zeta/PlattAppendixCBridge.lean)
then constructs the 140-term checker's `Realization` only after separate C.1
and corrected-C.3 evidence has been supplied.

## The source proposition and two typographical corrections

The paper defines

\[
 W(t)=\Lambda(t)\exp\!\left(\frac{\pi t}{4}
                   -\frac{(t-t_0)^2}{2H^2}\right),
 \qquad
 \operatorname{sinc}(x)=\frac{\sin(\pi x)}{\pi x},
\]

with the continuous value `sinc(0)=1`.  Lemma C.3 takes

\[
 t_0>\exp(e),\qquad
 \beta=\frac16+\frac{\log\log t_0}{\log t_0},\qquad
 N_s\in\mathbb Z_{>0},\qquad N_s\leq t_0A,
\]

and, after correcting two evident typesetting errors, states

\[
 \left|
 \sum_{|n-A t_0|>N_s}
 W\!\left(\frac nA\right)
 \operatorname{sinc}\!\left(A\left(\frac nA-t_0\right)\right)
 \right|
 \leq \frac{6A}{\pi N_s}(X+Y+Z),
\]

where

\[
\begin{aligned}
X={}&\left(t_0+\frac{N_s}{A}\right)^\beta
 \exp\!\left(-\frac{N_s^2}{2A^2H^2}\right),\\
Y={}&2^{(2\beta-1)/2}t_0^\beta AH\,
 \Gamma\!\left(\frac12,\frac{N_s^2}{2A^2H^2}\right),\\
Z={}&2^{(3\beta-1)/2}A H^{\beta+1}
 \Gamma\!\left(\frac{\beta+1}{2},\frac{t_0^2}{2H^2}\right).
\end{aligned}
\]

Here `Gamma(s,x)` is the upper incomplete Gamma integral
`integral_x^infinity u^(s-1) exp(-u) du`.

The public author manuscript actually prints the summation condition as
`|n-t0/A| > Ns`.  That cannot be the intended condition:

- the sample is at `n/A`, so its lattice-index distance from `t0` is
  `|n-A*t0|`;
- the very next line of the proof identifies the first omitted sample as
  `W(t0+Ns/A) sinc(Ns/A)`; and
- `inter.c` computes the index displacement and hence uses `n-A*t0`.

The manuscript also prints a lowercase `h` in the denominator of `X`, while
Lemma C.2, `Y`, `Z`, and every line of the proof use the interpolation width
`H`.  The Lean file exposes the printed tail term separately for comparison,
but every soundness theorem uses the proof-consistent corrections
`|n-A*t0|` and `H`.  These are corrections to the statement, not weakenings.

There is one further notational mismatch in the proof: substituting the first
omitted sample into the displayed kernel gives `sinc(Ns)`, whereas the proof
prints `sinc(Ns/A)`.  The subsequent estimate uses the conservative factor
`A/(pi*Ns)`.  For the source specialization `A=512/21 > 1`, the standard bound
on the *actual* kernel is the stronger `1/(pi*Ns)`, so retaining the paper's
larger right-hand side is sound once the tail comparison is formalized.  A
generic formalization should not silently use this step for arbitrary
`0 < A < 1`.

## Exact `zeta_arb` symbol map

The upstream reviewed source is
[`djplatt/code@42b2142`](https://github.com/djplatt/code/tree/42b21426718e542daa2b006dc05ea2d7f26426e6/zeta_arb).
Its reviewed hashes remain in
[`PLATT_PT21_WINDOWED_UPSTREAM.json`](../../specifications/PLATT_PT21_WINDOWED_UPSTREAM.json).

| paper | pinned source | exact value or operation |
|---|---|---|
| sample spacing `1/A` | `one_over_A` and `INTER_A` | `21/512` |
| `A` | `1/INTER_A` in `inter_sinc_cos` | `512/21` |
| Gaussian width `H` | `H` | `13/64` |
| one-sided cutoff `Ns` | `Ns` | `70` |
| retained samples | two loops of length `Ns` | `140` |
| displacement `(n/A-t0)` | `inter_tmp` | `(i-t_ptr) * (21/512)` |
| normalized sinc | `sin(sinc_tmp)/sinc_tmp` | `sinc_tmp = pi * A * displacement` |
| Gaussian | `inter_gaussian` | `exp(-displacement^2/(2H^2))` |
| claimed total radius | `intererr_d` | source decimal `2.45e-40`; corrected runner rounds upward from exact `245/10^42` |

At an exactly integral target, one boundary sample at distance exactly `Ns`
is omitted by the two 70-element loops.  Its normalized sinc is exactly zero,
so the strict `> Ns` source theorem still matches the computed sum.  At a
nonintegral target, the first omitted index on either side has distance
strictly greater than `Ns`.

The original 2017 run described in Section 5 used `H=2089/16384` and every
fifth lattice point.  The generic Appendix C lemma is not restricted to those
choices.  The pinned 3-trillion source instead uses the exact values in the
table.

## C.3 is not the whole interpolation error

Theorem 4.4 (Weiss) bounds the discrepancy between the true value and the
*infinite* sinc series because `W` is not exactly band-limited.  Lemma C.1
bounds that Fourier tail.  Lemma C.3 then bounds the difference between the
infinite series and the finite 140-term series.  Consequently the radius that
must be added to the finite interval is

```text
Weiss/non-bandlimited error (C.1) + omitted sampling tail (C.3).
```

The upstream PARI/GP parameter generator follows this structure as
`inter_err2 + inter_err1`; `parameters.h` labels the rounded joint result only
as “lemma C.3”.  The Lean theorem `interpolation_error_le` deliberately keeps
the two summands separate before weakening them to one rational radius.

As a non-proof audit, 80-decimal `mpmath` evaluation of the published C.3
right-hand side with `A=512/21`, `H=13/64`, and `Ns=70` gives approximately

| target `t0` | C.3 tail bound |
|---:|---:|
| `10^10` | `4.20657e-41` |
| `3.0001753328e12` | `1.35257e-40` |
| `3.01e12` | `1.35345e-40` |

These values are below `2.45e-40`, but they are only a diagnostic.  A
production proof still needs a directed interval certificate for the uniform
range and the separate C.1 contribution.

They can be reproduced, including the exact binary64 direction check, with

```bash
python3 tools/audit_platt_lemma_c3_bound.py --pretty
```

The JSON output labels itself `diagnostic_only` and cannot be admitted as a
certificate.

## Corrected build gate

The pinned split-file source contains a soundness omission.  `arb_zeta.c`
initializes the symmetric ball `intererr` from `intererr_d`, but the compiled
[`inter.c`](https://github.com/djplatt/code/blob/42b21426718e542daa2b006dc05ea2d7f26426e6/zeta_arb/inter.c)
returns the 140-term sum without adding that ball.  The older monolithic
`zeta_arb/arb_zeta_orig.cpp` and several other interpolation implementations
in the same upstream repository do add the error to `f_res`, supporting the
interpretation that this was a split-file omission.

The project build now applies
[`0001-apply-interpolation-error.patch`](../../patches/platt-pt21/0001-apply-interpolation-error.patch)
only in a temporary local build tree.  The upstream checkout remains pristine.
There is a second machine-level correction in the same patch.  The C decimal
literal `2.45e-40` rounds *down* to
`0x1.557aebd2564ecp-132`, approximately
`2.44999999999999986755e-40`.  The patch uses the next binary64 value upward,
`0x1.557aebd2564edp-132`, so the actual Arb radius is at least the exact Lean
rational `245/10^42`.  `PlattLemmaC3.lean` proves both exact rational
comparisons from the two binary64 significands and powers of two; this is not
left to a floating-point test.

The build fails closed unless all reviewed and corrected identities match:

```text
patch SHA256       2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3
upstream inter.c   71568e572b571ee08394acec4cb03f9feb351407187f70fa569d7d2f1ab86d39
corrected inter.c  4dba515103aa3c03a4c8385b9093296ecb86652d33ee916aac905e42ed0457cf
upstream params    b2fe59cfc850297aa9e75f997b84f838707a6b388dd8a514f4f1d703dcbe4a93
corrected params   fa0232a59098784fd474ff4de8df493908116f96e370416da94861e3a1093b20
```

The corrected FLINT 3.6 binary passes both retained known answers: 3,399
zeros on `[10000000000,10000001008]` and 4,314 zeros on
`[3000000000000,3000000001008]`.  Build evidence records the correction
digests and states that no derivative-error claim is made.  The current
Turing consumer requests only function values (`fd_res == NULL`); any future
derivative consumer needs a separately derived derivative interpolation
radius.

## Remaining formal obligations

The following work is still required before Appendix C is removed from the
analytic trust boundary:

- define the actual scaled completed zeta/Hardy function used by the source
  and prove its equality with the theorem consumer's zeta function;
- formalize the Lemma C.2 growth estimate, including the zeta and Gamma bounds;
- complete the integral comparison in C.3 and its upper-incomplete-Gamma
  evaluations (Mathlib currently has complete Gamma but no named incomplete
  Gamma API);
- formalize Weiss's theorem in the Fourier-transform convention used by this
  source and prove the Lemma C.1 bound;
- produce a checked interval certificate showing the sum of C.1 and corrected
  C.3 is at most `245/10^42` throughout every interpolation target actually
  used by the campaign; and
- bind the corrected radius addition, along with the 140 finite terms, to the
  measured GPU/CPU transcript.

Until those obligations are discharged, the appropriate trust boundary is a
source-shaped Appendix C premise plus independently checked finite arithmetic,
not a claim that the decimal in `parameters.h` proves itself.
