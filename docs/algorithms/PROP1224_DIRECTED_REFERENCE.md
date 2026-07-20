# Proposition 12.2.4 directed reference

`tg_verifier/prop1224_directed.py` closes the arithmetic-semantic gap in the
*bounded* Proposition 12.2.4 reference.  Unlike
`create_prop1224_window`, its public producer accepts only `q`, precision, and
a resource guard.  It computes all of these values itself:

- the distinct prime factors and `phi(q)`;
- directed enclosures of `log(q)` and `sum_(p|q) log(p)/p`;
- `tau`, `c(c_+)`, `c2`, `kappa(q)`, and `f1(q)`;
- the complete conservative integer window enclosing `[varpi(q),lambda(q))`;
- exact rational `G_q(k)` for every retained integer `k`; and
- a directed lower bound for the final `RHS - LHS` margin.

No Python `float`, platform `libm`, decimal endpoint supplied by a caller, or
GPU result controls an inequality decision.  Logarithms use an exact rational
atanh series with a geometric tail.  Exponentials use a rational Taylor series
with a geometric tail after exact range reduction.  Positive real powers use
`exp(y*log(x))`.  The many one-third powers use integer cube-root enclosures
instead, avoiding unnecessary transcendental evaluation.

The two non-rational constants enter through explicit theorem-backed rational
intervals:

```text
577215657/10^9 <= EulerGamma <= 5772162/10^7
1.3325822       <= c_E       <= 1.3339
```

Their Lean bridges are, respectively,
`Real.eulerMascheroniConstant_ge_d577215657`,
`AnalyticNT.LargeSieve.eulerMascheroni_le_d5772162`,
`RamareCE_lower_bound_holds`, and `ramareCE_le_1_3339`.  Thus they are explicit
proof inputs, not unauthenticated numerical literals.  The relatively broad
`c_E` enclosure can enlarge a conservative `k` window; the producer checks the
extra rows rather than silently rounding the window inward.

Run the focused tests with:

```bash
python3 -m unittest tests.test_tg_prop1224_directed -v
```

The retained representative test is the complete directed row for
`q = 6469693230 = 2*3*5*7*11*13*17*19*23*29`.  At 96 bits and 32 series terms
it conservatively checks all 136 integers `586 <= k <= 721`; every rational
margin lower bound is greater than one.  The final `k=721` is deliberately an
extra row caused by outward endpoint uncertainty.

`create_directed_prop1224_chunk` stores one or more such rows in the existing
`Prop1224Chunk` format, so the ordinary scheduler, canonical body, predecessor
hash, and record hash are reused.  `verify_directed_prop1224_chunk` first runs
that structural verifier and then reconstructs every endpoint, `G_q(k)`, and
margin from `q`; a structurally valid chunk with a replaced nonnegative margin
is rejected by the directed replay.  This overlay is bounded to at most 10,000
`q` rows per call and does not change the generic chunk format's intentionally
structural `semantics_status` field.

## What this does not establish

This is not a completed replay of Helfgott's two-week computation.  The source
range contains exactly 3,389,047,618 admissible `q` rows, and no complete run
or full directed chunk chain has been produced.  The current `G_q` reference
also materializes arithmetic prefixes and is intended for bounded rows, not
that production campaign.  Finally, no Lean theorem yet realizes this Python
rational evaluator as the definitions in
`RamareProp1224FiniteCite.lean`.  Accordingly every result reports
`full_source_campaign = false` and `lean_realization_proved = false`; it must
not be used to retire the Lean source atom by itself.
