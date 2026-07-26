# A uniform interpolation-truncation bound for Platt's Theorem 7.1 domain

This document addresses item 3 of "Remaining production and analytic work" in
[DIRICHLET_GRH_CAMPAIGN.md](DIRICHLET_GRH_CAMPAIGN.md): *a uniform proof of the
accepted manuscript's interpolation error over every source case, including an
explicit replacement for its printed "large enough" condition.*

It is a paper derivation. It flips no readiness flag. `external_atom_discharged`
and `production_accept` remain `false` everywhere, and nothing here is a
discharged atom, a Lean theorem, or a certificate.

## 1. Source and the exact place the condition appears

All references are to

> D. J. Platt, *Numerical computations concerning the GRH*,
> arXiv:1305.3087v1 [math.NT], 14 May 2013.
> Local copy: `/home/gersh/claude_math/papers/literature/platt-2013-grh.pdf`.

The up-sampling apparatus is Section 6, "Rigorous Up-sampling", pages 11-14.
The statement that the campaign consumes is:

> **Lemma 6.7** (page 14). Define
>
> `E := sum_{|n| >= N} W(n/(2B)) sinc(2 B pi (n/(2B) - t0))`.
>
> *Then for large enough `t0` we have*
>
> `|E| <= sqrt(pi) zeta(9/8) exp(1/6) 2^(5/4) (q/(2 pi))^(5/16) * G(0)/(1 - G(1)/G(0))`.

No proof is printed; the preceding sentence (page 13, immediately after
Lemma 6.6) reads in full: *"We can now combine Lemmas 5.3, 6.3 and 6.6."*
The phrase *"for large enough `t0`"* is the entire hypothesis. No threshold,
no dependence on `q`, `B`, `h` or `N`, and no proof obligation is recorded.

The three inputs it names are:

> **Lemma 5.3** (page 9). For `t` in `R`,
> `|L_chi(1/2 + it)| <= zeta(9/8) (q/(2 pi))^(5/16) (3/2 + |t|)^(5/16)`.
> *Proof.* Rademacher's bound `|L_chi(s)| <= zeta(1+nu) (q|1+s|/(2 pi))^((1+nu-Re s)/2)`
> with `nu = 1/8` and `s = 1/2 + it`.

> **Lemma 6.3** (page 12). For `a_chi` in `{0,1}`,
> `|Gamma((1/2 + it + a_chi)/2)| e^(pi t/4)`
> `<= max( 2^(1/4) sqrt(pi) (3/2 + max(t,0))^(1/4) exp(1/6), sqrt(2 pi) exp(pi/8 + 1/4) )`.
> *Proof.* Stirling, separately for `a_chi = 0` and `a_chi = 1`.

> **Lemma 6.6** (page 13). Let `h, B > 0`, `t0 = n0/(2B)` for some `n0` in `Z_{>0}`,
> and `N` in `Z_{>0}`. Define
> `G(n) := (3/2 + t0 + (N+n)/(2B))^(9/16) exp(-(N+n)^2/(8 B^2 h^2)) / (pi (N+n))`.
> Then
> `sum_{n >= 2 B t0 + N} (3/2 + n/(2B))^(9/16) exp(-(n/(2B) - t0)^2/(2 h^2)) sinc(2 B pi (n/(2B) - t0))`
> `<= G(0)/(1 - G(1)/G(0))`.
> *Proof.* `G(n)` is at least as large as the corresponding term in the sum and
> the ratio `G(n+1)/G(n)` is a decreasing function of `n`, so the result follows
> as the sum of a geometric series.

The completed value being interpolated is, from the proof of Lemma 6.4
(page 12) restricted to the critical line `s = 1/2 + it`,

    |Lambda_chi(t)| = |Gamma((1/2 + it + a_chi)/2)| e^(pi t/4) |L_chi(1/2 + it)|,

the conductor phase `(q/pi)^(it/2)` and the root number `epsilon_chi` having
modulus one there. The windowed function is
`W(t, chi) = Lambda_chi(t) exp(-(t - t0)^2/(2 h^2))` (page 12).

The domain to be covered is Theorem 7.1 (page 14): all primitive characters of
modulus `q <= 400000`, to height

    q even:  T_q = max(10^8/q, 200 + 7.5 *10^7/q)
    q odd:   T_q = max(10^8/q, 200 + 3.75*10^7/q)

Production sampling parameters (`A = 64/5`, hence `2B = A`, `B = 32/5`;
Gaussian `h = 7/32`; `N = 20` retained samples on each side) come from the
later Bristol accepted manuscript, as recorded in
[DIRICHLET_ZERO_CLOSURE_STAGE.md](DIRICHLET_ZERO_CLOSURE_STAGE.md); they are
absent from arXiv v1. Everything below is stated for general `(B, h, N)` and
then evaluated at those values.

## 2. Three defects in the printed chain, not one

Working through "combine Lemmas 5.3, 6.3 and 6.6" turns up three separate
places where the printed statements do not compose, only one of which is the
advertised "large enough" clause.

**(D1) The `max` in Lemma 6.3 is silently resolved to its first branch.**
Multiplying Lemma 6.3 by Lemma 5.3 gives `(3/2 + |t|)^(1/4 + 5/16) =
(3/2 + |t|)^(9/16)`, which is the exponent appearing in `G`, *only if* the
first branch of the `max` is the larger one. Lemma 6.7's printed constant
`sqrt(pi) exp(1/6) 2^(5/4) = 2 * (2^(1/4) sqrt(pi) exp(1/6))` is exactly twice
the first branch's coefficient. The two branches are equal at

    2^(1/4) sqrt(pi) exp(1/6) (3/2 + t)^(1/4) = sqrt(2 pi) exp(pi/8 + 1/4)

i.e. at `3/2 + t = (D/A)^4` where `A := 2^(1/4) sqrt(pi) exp(1/6)` and
`D := sqrt(2 pi) exp(pi/8 + 1/4)`. Since
`(D/A)^4 = (2^(1/2-1/4))^4 exp(pi/2 + 1 - 2/3) = 2 exp(pi/2 + 1/3)`, the
crossing is at

    t = 2 exp(pi/2 + 1/3) - 3/2 = 11.9271240069416...  .

Below it the *second* branch is larger and the printed constant is not
justified. This is the real content of "for large enough `t0`".

**(D2) Lemma 6.6 assumes the target is a lattice point; up-sampling never is.**
Its hypothesis `t0 = n0/(2B)`, `n0` in `Z_{>0}`, forces `t0` onto the sample
grid, where every `sinc(2 B pi (n/(2B) - t0))` with `n != n0` vanishes
identically. The whole purpose of Section 6 is to evaluate at targets *between*
samples (Section 7 up-samples by factors 8, 32, 128, 512). The lemma as printed
is true but degenerate; the case actually used is not covered.

**(D3) The index sets of Lemma 6.6 and Lemma 6.7 disagree.**
Lemma 6.6 sums over `n >= 2 B t0 + N`, i.e. over samples at distance at least
`N/(2B)` *to the right of the target*. Lemma 6.7 sums over `|n| >= N`, i.e.
over samples at distance at least `N/(2B)` *from the origin*. For `t0 = 10^8/3`
and `N = 20` the set `|n| >= N` contains the target itself and every sample
adjacent to it, where the discarded terms are `O(1)`, so `|n| >= N` cannot be
the intended set. The intended set is plainly `|n - 2 B t0| >= N`, which is
also what the campaign's evaluator enforces
(`tg_verifier/dirichlet_postprocess.py`, the `below < truncation or above <
truncation` guard). We prove the statement for that set.

There is also an unstated hypothesis inside Lemma 6.6's own proof, recorded as
(H3) below: the ratio `G(n+1)/G(n)` is *not* decreasing for all parameter
choices.

## 3. Notation and standing hypotheses

Fix `B > 0`, `h > 0`, an integer `N >= 1`, a modulus `q >= 3`, a primitive
character `chi` mod `q` with parity `a_chi` in `{0,1}`, and a target ordinate
`t0 >= 0`. Samples are `t_n = n/(2B)` for `n` in `Z`. Write

    A := 2^(1/4) sqrt(pi) exp(1/6)          = 2.4900888802805429...
    D := sqrt(2 pi) exp(pi/8 + 1/4)         = 4.7666207462780996...
    Z := zeta(9/8)                          = 8.5862412945105753...
    X(d) := 3/2 + t0 + d/(2B)         (d >= 0 real)
    G(j) := X(N+j)^(9/16) exp(-(N+j)^2/(8 B^2 h^2)) / (pi (N+j))   (j >= 0 integer)

`G` is exactly Platt's `G` of Lemma 6.6. Define the **uniform interpolation
constant**

    C(t0, N, B) := max( A , D * X(N)^(-1/4) )
                 = max( A , D * (3/2 + t0 + N/(2B))^(-1/4) ).

Standing hypotheses, all explicitly checkable:

* **(H1)** `t0 >= 0`.
* **(H2)** the discarded index set is contained in `{ n in Z : |n - 2 B t0| >= N }`.
* **(H3)** `N (N + 1) >= 4 B^2 h^2`.
* **(H4)** `G(1)/G(0) < 1`.

(H3) and (H4) are what Lemma 6.6's proof actually needs; see Step 4. At the
production parameters `B = 32/5`, `h = 7/32`, `N = 20`: `N(N+1) = 420` and
`4 B^2 h^2 = 7.84`, so (H3) holds with room to spare, and `G(1)/G(0)` lies
between `0.0696978` and `0.0706925` for every `t0` in `[0, 10^8/3]`, so (H4)
holds.

## 4. The theorem

> **Theorem U.** Assume (H1)-(H4) and let
>
>     E := sum over the discarded indices n of  W(n/(2B), chi) * sinc(2 B pi (n/(2B) - t0)).
>
> Then
>
>     |E| <= 2 * C(t0, N, B) * zeta(9/8) * (q/(2 pi))^(5/16) * G(0) / (1 - G(1)/G(0)).
>
> Moreover, if in addition
>
>     **(H5)**   t0 + N/(2B) >= 2 exp(pi/2 + 1/3) - 3/2 = 11.9271240069417 ,
>
> then `C(t0, N, B) = A` and the bound is *exactly* Platt's printed Lemma 6.7
> bound `sqrt(pi) zeta(9/8) exp(1/6) 2^(5/4) (q/(2 pi))^(5/16) G(0)/(1-G(1)/G(0))`.
> If (H5) fails, the bound is Platt's multiplied by `C(t0,N,B)/A`, which never
> exceeds `(3/2)^(-1/4) D / A = 1.7297085621698320`.

(H5) is the explicit replacement for "for large enough `t0`". It is a
*sufficient* condition for the printed constant; Theorem U itself holds
unconditionally on `t0 >= 0`.

The only unproved inputs are Platt's Lemma 5.3 (Rademacher's convexity bound)
and Lemma 6.3 (Stirling), which are accepted as cited. Everything else below is
proved.

### Step 1: a majorant for the windowed samples

By the displayed definition of `Lambda_chi` and `W`, for every real `t`,

    |W(t, chi)| = |Gamma((1/2 + it + a_chi)/2)| e^(pi t/4) |L_chi(1/2 + it)|
                  * exp(-(t - t0)^2/(2 h^2)).

Apply Lemma 6.3 to the first two factors and Lemma 5.3 to the third:

    |W(t, chi)| <= Z (q/(2 pi))^(5/16) * mu(t) * exp(-(t - t0)^2/(2 h^2)),      (1)

    mu(t) := max( A (3/2 + max(t,0))^(1/4) , D ) * (3/2 + |t|)^(5/16).

Both lemmas hold for every real `t` with no side condition, so (1) is valid on
all of `R`, including `t < 0`.

### Step 2: pairing the two tails

Let `n` be a discarded index and put `d := |n - 2 B t0| >= N` by (H2), so that
`|t_n - t0| = d/(2B)` and

    (t_n - t0)^2/(2 h^2) = d^2/(8 B^2 h^2),
    |sinc(2 B pi (t_n - t0))| = |sin(pi d)|/(pi d) <= 1/(pi d).                 (2)

The second inequality is the only property of `sinc` used; it needs no
assumption on `d` beyond `d > 0`, and in particular does not require `2 B t0`
to be an integer. This is what removes defect (D2).

Define, for real `d >= N`,

    mu+(d) := max( A X(d)^(1/4) , D ) * X(d)^(5/16),
    phi(d) := mu+(d) * exp(-d^2/(8 B^2 h^2)) / (pi d).

**Claim.** For every discarded index `n`, with `d = |n - 2 B t0|`,

    |W(t_n, chi) sinc(2 B pi (t_n - t0))| <= Z (q/(2 pi))^(5/16) phi(d).        (3)

*Proof.* Combine (1) and (2); it remains to show `mu(t_n) <= mu+(d)`, i.e. that
the *left* samples are dominated by their mirror images on the right. Note
`X(d) = 3/2 + t0 + d/(2B)`.

*Right samples* (`t_n = t0 + d/(2B) >= 0`): then `3/2 + max(t_n,0) = 3/2 + |t_n|
= X(d)`, so `mu(t_n) = mu+(d)` exactly.

*Left samples with `t_n >= 0`* (`t_n = t0 - d/(2B)`): here `3/2 + max(t_n,0) =
3/2 + |t_n| = 3/2 + t0 - d/(2B) <= X(d)`. The function
`x -> max(A x^(1/4), D) x^(5/16)` is nondecreasing in `x > 0`, so
`mu(t_n) <= mu+(d)`.

*Left samples with `t_n < 0`*: here `max(t_n, 0) = 0` and
`|t_n| = d/(2B) - t0 <= d/(2B) <= t0 + d/(2B)` because `t0 >= 0` by (H1). Hence
`3/2 + |t_n| <= X(d)` and, since `max(A (3/2)^(1/4), D) = D` (numerically
`A (3/2)^(1/4) = 2.7557 < 4.7666 = D`),

    mu(t_n) = D (3/2 + |t_n|)^(5/16) <= D X(d)^(5/16) <= mu+(d).

That exhausts the cases. []

This is where the factor `2` in Platt's constant comes from, and it is the
correct accounting for the two-sided index set of (H2), replacing the
inconsistent `|n| >= N` of defect (D3).

### Step 3: `phi` is decreasing, so any unit-spaced tail is dominated

The discarded indices to the right of `t0` produce offsets
`d = d_R, d_R + 1, d_R + 2, ...` for some real `d_R >= N`; those to the left
produce `d = d_L, d_L + 1, ...` for some real `d_L >= N`. (Both progressions
have spacing exactly `1` because the indices are consecutive integers; `d_R`
and `d_L` are in general *not* integers, which is precisely the off-lattice
case Lemma 6.6 excluded.)

**Claim.** `phi` is strictly decreasing on `(0, infinity)`.

*Proof.* On each branch of the `max`, with `e` in `{9/16, 5/16}`,

    d/dd log( X(d)^e exp(-d^2/(8 B^2 h^2)) / (pi d) )
      = e/(2 B X(d)) - d/(4 B^2 h^2) - 1/d
      = e/(2 B (3/2 + t0) + d) - d/(4 B^2 h^2) - 1/d .

Since `t0 >= 0` and `B > 0` we have `2 B (3/2 + t0) + d > d`, hence
`e/(2 B (3/2 + t0) + d) < e/d <= (9/16)/d < 1/d`, and the whole expression is
negative. Each branch is therefore strictly decreasing, and the pointwise
maximum of two positive decreasing functions is decreasing. []

Consequently, for any real `d_0 >= N`,

    sum_{k >= 0} phi(d_0 + k) <= sum_{k >= 0} phi(N + k),                       (4)

term by term. Applying (3) and (4) to each of the two tails and adding,

    |E| <= 2 Z (q/(2 pi))^(5/16) sum_{k >= 0} phi(N + k).                        (5)

### Step 4: the geometric sum, with the missing hypothesis made explicit

For integer `k >= 0`, `X(N+k) >= X(N)`, so
`max(A X(N+k)^(1/4), D) <= max(A, D X(N)^(-1/4)) X(N+k)^(1/4) = C(t0,N,B) X(N+k)^(1/4)`,
whence

    phi(N + k) <= C(t0, N, B) * X(N+k)^(9/16) exp(-(N+k)^2/(8 B^2 h^2))/(pi (N+k))
               = C(t0, N, B) * G(k).                                            (6)

This inequality is the entire content of the repair: it is where the `max` of
Lemma 6.3 is discharged honestly instead of being assumed to sit on its first
branch, and it is where `C` replaces `A`.

It remains to sum `G`. Platt's Lemma 6.6 asserts that `G(n+1)/G(n)` is
decreasing in `n`; that is *not* true for all parameters. With
`u := N + n` treated as a real variable and `rho(u) := G(u+1)/G(u)`,

    d/du log rho(u)
      = (9/16) [ 1/(2 B X(u+1)) - 1/(2 B X(u)) ] - 1/(4 B^2 h^2) + 1/(u(u+1)).

The bracket is negative, so `d/du log rho(u) <= 1/(u(u+1)) - 1/(4 B^2 h^2)`,
which is `<= 0` for all `u >= N` as soon as `N(N+1) >= 4 B^2 h^2`. That is
hypothesis (H3). (Informally: the retained half-window must be at least about
`2 B h`, i.e. must reach past the Gaussian's own width; otherwise the `1/(pi d)`
sinc decay, not the Gaussian, controls the ratio and the ratio can increase.)

Under (H3), `G(k+1)/G(k) <= G(1)/G(0) =: r0` for all `k >= 0`, hence
`G(k) <= G(0) r0^k`, and under (H4) (`r0 < 1`)

    sum_{k >= 0} G(k) <= G(0)/(1 - r0).                                          (7)

Combining (5), (6), (7) gives Theorem U. []

### Step 5: the threshold (H5)

`C(t0,N,B) = A` exactly when `D X(N)^(-1/4) <= A`, i.e. when
`X(N) = 3/2 + t0 + N/(2B) >= (D/A)^4 = 2 exp(pi/2 + 1/3) = 13.4271240069417`,
i.e. when

    t0 + N/(2B) >= 2 exp(pi/2 + 1/3) - 3/2 = 11.9271240069417 .

When it fails, `C/A = (D/A) X(N)^(-1/4) < 1` is replaced by
`C/A = (D/A) X(N)^(-1/4)`, which is largest when `X(N)` is smallest. Since
`X(N) >= 3/2` always, `C/A <= (D/A)(3/2)^(-1/4) = 1.7297085621698320`; this
worst case is only approached as `t0 -> 0` *and* `N/(2B) -> 0`. At the
production parameters `N/(2B) = 20/(64/5) = 1.5625`, so `X(N) >= 3.0625` and

    C/A <= D (3.0625)^(-1/4) / A = 3.6032265968037027/2.4900888802805430
         = 1.4470273030566481 ,

attained at `t0 = 0`, and `C = A` for every `t0 >= 10.3646240069417`.

**Loss relative to Platt.** Theorem U is weaker than the printed Lemma 6.7 by
the factor `C/A`, which is `1` for `t0 >= 10.36463` and at most `1.44703` below
that (at production parameters), or at most `1.72971` for arbitrary `(N, B)`.
That is the entire price of uniformity.

## 5. Behaviour over the source domain

### 5.1 The height function and its branches

    even q:  T_q = max(10^8/q, 200 + 7.5 *10^7/q);  branches cross at q = 125000, T = 800
    odd  q:  T_q = max(10^8/q, 200 + 3.75*10^7/q);  branches cross at q = 312500, T = 440

For `q` below the crossover the `10^8/q` branch binds and `T_q` falls like
`1/q`; above it the `200 + c/q` branch binds and `T_q` falls towards `200`.
Extremes over `3 <= q <= 400000`:

| case | `q` | `T_q` |
|---|---|---|
| smallest modulus | 3 (odd) | `33333333.333...` |
| even crossover | 125000 | `800` |
| odd crossover | 312500 | `440` |
| largest modulus | 400000 (even) | `387.5` |
| **global minimum of `T_q`** | 399999 (odd) | `293.7502343755859...` |

So `T_q >= 293.75` throughout the domain.

### 5.2 Where (H5) binds

`T_q >= 293.75 >> 11.93`, so **at the top of every ordinate range the printed
constant is valid and Theorem U reproduces Platt's Lemma 6.7 verbatim.** The
condition fails only near the bottom of the range: at production parameters,
for `0 <= t0 < 10.3646240069417`. That band is not vacuous — the campaign must
decide the sign of `Lambda_chi(1/2)` (`t0 = 0`) and works on the closed
symmetric interval `[-T_q, T_q]` — so the gap is live, but it lies exactly
where the truncation budget is smallest.

Negative ordinates need no separate treatment: `conj(L_chi(conj(s))) =
L_conj(chi)(s)`, so the zeros of `L_chi` on `[-T_q, 0]` are the mirror images
of the zeros of `L_conj(chi)` on `[0, T_q]`, and the set of primitive
characters mod `q` is closed under conjugation. Hypothesis (H1) `t0 >= 0` is
therefore not a restriction on the domain, only on the bookkeeping. (This is
the same reflection the campaign's Turing arithmetic already performs.)

### 5.3 The bound is monotone in `t0`, so the maximum is unaffected

`C(t0,N,B) G(0) = max(A X(N)^(9/16), D X(N)^(5/16)) exp(-N^2/(8B^2h^2))/(pi N)`
is nondecreasing in `X(N)` and hence in `t0`. The correction therefore inflates
only small-`t0` values and leaves the domain maximum, attained at `t0 = T_q`,
exactly equal to Platt's. At production parameters and `q = 3`,
`t0 = 10^8/3`, the truncation budget is `8.2526166e-8` with either constant.

### 5.4 Numbers at the corners (production parameters `B=32/5`, `h=7/32`, `N=20`)

Truncation budget `2 C Z (q/(2 pi))^(5/16) G(0)/(1-G(1)/G(0))`, evaluated at
`t0 = T_q`:

| `q` | parity | `T_q` | `C/A` | budget (corrected) | budget (Platt printed) |
|---|---|---|---|---|---|
| 3 | odd | 3.3333e7 | 1 | 8.25262e-8 | 8.25262e-8 |
| 4 | even | 2.5e7 | 1 | 7.67993e-8 | 7.67993e-8 |
| 124999 / 125000 / 125001 | - | ~800 | 1 | 5.7887e-9 | same |
| 312499 / 312500 / 312501 | - | 320 / 440 / 320 | 1 | 4.618e-9 / 5.516e-9 / 4.618e-9 | same |
| 399999 | odd | 293.7502 | 1 | 4.75654e-9 | same |
| 400000 | even | 387.5 | 1 | 5.55067e-9 | same |

At `t0 = 0` (worst case for the correction), `q = 400000`: corrected
`5.258656e-10` against printed `3.634110e-10`, an absolute increase of
`1.62e-10`. Scanning `q` over the whole domain, the largest absolute amount by
which the printed constant understates the corrected budget anywhere in
`[0, T_q]` is `1.6245e-10`, at `q = 400000`, `t0 = 0`. The manuscript's
`8.6e-8` headline is nowhere threatened by the correction.

## 6. Attempts to refute the result

Numerics can only refute. Everything below was run as an attempt to break
Theorem U, not to confirm it.

1. **Lemma 6.3 itself.** Direct evaluation of
   `|Gamma((1/2+it+a)/2)| e^(pi t/4)` against its printed majorant, for
   `a` in `{0,1}`, on a `0.02` grid over `t` in `[-40, 40]` and at
   `t = +-10^k` for `k <= 8`: maximum ratio `0.8465`, no violation. The lemma
   is true and not tight; the crossing of the two branches at
   `t = 11.9271` is confirmed.
2. **Step 2's termwise domination and Step 3's monotonicity.** Checked on grids
   in `d` for `t0` in `{0, 1, 10, 11.9271, 293.75, 387.5, 800, 3.3333e7}`;
   no violation of `mu(t_n) <= mu+(d)` and no non-decreasing step of `phi`.
3. **Step 4's geometric bound.** `sum_{k<=400} G(k)` compared with
   `G(0)/(1-G(1)/G(0))`: the geometric bound holds at every tested `t0`, with
   about `0.07%` slack, and the ratio `G(k+1)/G(k)` was decreasing throughout,
   consistent with (H3).
4. **Theorem U end to end.** For 109,564 triples `(q, t0, theta)` — `q` at both
   crossovers, both parities, both extremes, plus 300 random moduli; `t0`
   including `0`, `10^-9`, the (H5) threshold from both sides, `T_q`, and 20
   random interior values per modulus; and `theta = 2 B t0 - floor(2 B t0)` in
   `{0, 10^-12, 1/4, 1/2, 3/4, 1-10^-6, random}` — the exact sum of the
   rigorous termwise majorant of `|E|` was compared with the right-hand side of
   Theorem U. **Worst observed ratio `0.99936 < 1`; no counterexample.** The
   bound is nearly attained when `theta = 0` (both tails start at distance
   exactly `N`), which is the correct worst case.
5. **Platt's printed constant, same harness.** Worst ratio `1.44539 > 1`, at
   `q = 3`, `t0 = 0`, `theta = 0`. That is a genuine refutation *of the printed
   derivation*: the majorant that Lemmas 5.3, 6.3 and 6.6 actually produce
   exceeds the bound printed in Lemma 6.7, at small `t0`, by up to `44.5%`.
   It is **not** a refutation of `|E| <= (printed bound)` — the true `E` is far
   smaller than its majorant — but it does show the printed statement cannot be
   obtained from its stated inputs without (H5), and therefore that "for large
   enough `t0`" is load-bearing rather than cosmetic.
6. **(H3), and a counterexample to Lemma 6.6 as printed.** Lemma 6.6 carries no
   hypothesis relating `N`, `B` and `h`, and its proof asserts flatly that
   `G(n+1)/G(n)` is decreasing. It is not. Taking `N = 2`, `B = 32/5`, `h = 2`,
   `t0 = 0`, the ratios run `0.6816, 0.7647, 0.8136, 0.8454, ...` — increasing —
   and

       sum_{k >= 0} G(k) = 1.45566   >   0.661823 = G(0)/(1 - G(1)/G(0)) ,

   so the printed conclusion of Lemma 6.6 is **false** at those parameters, by
   a factor of `2.2`. Further failing parameter sets: `(N,B,h) = (3, 32/5, 1)`
   giving `0.82026 > 0.56868`; `(2, 10, 1)` giving `1.21297 > 0.63293`;
   `(4, 32/5, 3)` giving `1.39955 > 0.60340`. Every failure observed has
   `N(N+1) < 4 B^2 h^2`; no failure was found when (H3) holds. At production
   parameters `420 >= 7.84`, so the source domain is safe and Theorem U applies
   there unchanged.

## 7. Discrepancy with the repository's implementation

`tg_verifier/dirichlet_postprocess.py`, in `whittaker_shannon`, computes the
truncation budget as

```
tail = pi.sqrt() * zeta(9/8) * exp(1/6) * 2**(5/4) * (q/(2*pi))**(5/16) * g0/(1 - ratio)
```

i.e. with Platt's printed constant `2A` and no `t0`-dependence. This is
**inconsistent with the uniform bound derived here whenever
`t0 + N/(2B) < 11.9271240069417`**, i.e. for `t0 < 10.3646240069417` at the
production parameters. In that band the emitted budget is smaller than the one
Theorem U establishes, by the factor `C(t0,N,B)/A`, which reaches `1.4470273`
at `t0 = 0`.

Assessment:

* It is a live soundness defect in the sense that the stage emits a budget
  narrower than the argument supports, for ordinates that the campaign really
  visits (`t0` near `0` in particular).
* Its magnitude is bounded: the missing amount never exceeds `1.63e-10`
  anywhere in the source domain, against a total error claim of `8.6e-8`.
* The file already refuses to promote the stage (`production_accept: False`,
  and the request Boolean
  `lemma_6_7_large_enough_t0_obligation_discharged` is recorded but explicitly
  cannot promote anything), so no accepted decision currently rests on it.

**Second discrepancy: (H3) is neither checked nor satisfied by the module's own
unit test.** `whittaker_shannon` validates only `truncation >= 2`, `bandwidth >
0`, `gaussian_h > 0`, and `ratio < 1`. It never checks `N(N+1) >= 4 B^2 h^2`.
The existing test
`tests/test_tg_dirichlet_postprocess.py::test_finite_sinc_has_separate_alias_and_tail_budgets`
calls it with `N = 4`, `B = 32/5`, `h = 2`, `t0 = 1/100`, for which

    N(N+1) = 20   <   655.36 = 4 B^2 h^2 ,
    sum_{k >= 0} G(k) = 1.103762   >   0.590817 = G(0)/(1 - G(1)/G(0)) ,

so at those parameters the emitted `truncation_budget` is smaller than the sum
it is supposed to dominate, by a factor of `1.87`. The `ratio < 1` guard does
not catch it (`ratio = 0.8135`). The production parameter set is unaffected
(`420 >= 7.84`), and no production decision is taken from this path, but a
request with a short window or a wide Gaussian would receive an unsound budget
with no diagnostic.

**No constant and no code has been changed.** Per instruction, the
discrepancies are reported, not silently patched. If they are repaired later,
the correct changes are: replace the fixed `2^(5/4) sqrt(pi) exp(1/6)` by
`2 * C(t0, N, B)` with `C(t0,N,B) = max(A, D (3/2 + t0 + N/(2B))^(-1/4))`
evaluated in outward interval arithmetic; and add an explicit
`N*(N+1) >= 4*B^2*h^2` gate for (H3) alongside the existing (H4) check.

## 8. A separate inconsistency found while checking the domain (not this gap)

While scanning the domain, the *Weiss aliasing* budget of Lemmas 6.4-6.5 — a
different term, not the interpolation truncation — was evaluated at the
production parameters as the code implements it:

    I_chi <= 2 (q/pi)^(M/2) zeta(M+1/2) exp(M^2/(2h^2) - 2 pi B M) P(t0,h)/(pi M),
    M = 5/2 - a_chi,   P(t0,h) <= h pi (t0 + h/sqrt(2 pi) + 1 + 1/(2 sqrt 2)).

For **even** characters (`a_chi = 0`, `M = 5/2`) this grows like `q^(5/4)` and,
at `t0 = T_q`, exceeds the accepted manuscript's total claim of `8.6e-8` on its
own for every even modulus `q >= 301134` — that is `49434` moduli — reaching
`9.909e-8` at `q = 400000`, for a printed total of `1.0464e-7`. Odd characters
are far from the boundary (largest total `8.41228e-8`, at `q = 3`, matching the
repo's existing `q = 3` KAT of about `8.4123e-8`).

This is consistent with, and makes precise, the remark already in
[DIRICHLET_ZERO_CLOSURE_STAGE.md](DIRICHLET_ZERO_CLOSURE_STAGE.md) that "the
simple printed bounds for some other endpoint combinations require a tighter or
case-specific argument". It is recorded here only because it was found by the
same scan; it is **not** addressed by Theorem U and remains open. Likely
resolutions (none verified here): the accepted manuscript may use a larger `B`,
a different `h`, or a case split for large even `q`; or the printed `P(t0,h)`
bound, which is linear in `t0`, may be replaced by a sharper one. Until one of
those is confirmed against the accepted manuscript, the `8.6e-8` figure should
be treated as established only for the cases the repo's KAT actually covers.

## 9. What is proved, what is assumed, what is open

**Proved here** (ordinary mathematics, on paper, not formalized):

* Theorem U of Section 4, under the explicit hypotheses (H1)-(H4), for every
  `q >= 3`, either parity, every `t0 >= 0`, and every `B, h > 0`, `N >= 1`.
* The explicit threshold (H5), `t0 + N/(2B) >= 2 exp(pi/2 + 1/3) - 3/2`, under
  which Theorem U coincides with Platt's printed Lemma 6.7 — an explicit
  replacement for "for large enough `t0`".
* The uniform fallback constant `C(t0,N,B) <= (3/2)^(-1/4) sqrt(2 pi)
  exp(pi/8+1/4) = 4.3071281`, i.e. a loss of at most `1.7297086` relative to
  the printed constant in general, and at most `1.4470274` at production
  parameters.
* Repairs of the two structural defects (D2) (off-lattice targets) and (D3)
  (index set `|n - 2 B t0| >= N`), and the identification of the unstated
  hypothesis (H3) inside Lemma 6.6's proof, together with an explicit
  counterexample showing Lemma 6.6 is false without it.

**Assumed** (accepted citations, not reproved here):

* Platt Lemma 5.3 (page 9), i.e. Rademacher's convexity bound with `nu = 1/8`.
* Platt Lemma 6.3 (page 12), i.e. the Stirling majorant for
  `|Gamma((1/2+it+a)/2)| e^(pi t/4)`. Numerically probed in Section 6.1 and not
  refuted, but not proved here.
* Theorem 6.1 (Whittaker-Shannon) and Theorem 6.2 (Weiss), which supply the
  interpolation identity and the aliasing term; Theorem U bounds only the
  *truncation* term `E`.
* The identification `|Lambda_chi(t)| = |Gamma((1/2+it+a_chi)/2)| e^(pi t/4)
  |L_chi(1/2+it)|`, read off the displayed definition and the proof of
  Lemma 6.4.

**Open / not done:**

* No Lean statement, no certificate, no flag change. `external_atom_discharged`
  and `production_accept` stay `false`.
* The aliasing budget of Section 8 is unresolved and, at the printed
  parameters, breaks the `8.6e-8` claim for large even moduli. Theorem U does
  not touch it.
* Theorem U bounds the truncation term of the *first-level* Whittaker-Shannon
  reconstruction. The campaign up-samples repeatedly (factors 8, 32, 128, 512);
  the composition of the per-level budgets over an escalation chain is not
  analysed here.
* The production parameters `A = 64/5`, `h = 7/32`, `N = 20` are taken from the
  repo's reading of the Bristol accepted manuscript, which was not available
  locally. Theorem U is stated for general `(B, h, N)`, so this does not affect
  the mathematics, only the numerical tables.
* Whether Platt's Theorem 6.2 (Weiss) as printed, with its one-sided integral
  `4 * int_{2 pi B}^{infinity} |F(x)| dx`, is the correct form of Brown's
  theorem was not checked against [5] of the source.

## 10. Citation

D. J. Platt, *Numerical computations concerning the GRH*, arXiv:1305.3087v1
[math.NT], 14 May 2013. Section 5.2, Lemma 5.3 (page 9); Section 6, Theorem 6.1
and Theorem 6.2 (page 11), Lemma 6.3 and Lemma 6.4 (page 12), Lemma 6.5 and
Lemma 6.6 (page 13), Lemma 6.7 (page 14, the "for large enough `t0`"
statement); Section 7, Theorem 7.1 (page 14, the `q <= 400000` GRH statement
and the even/odd height formulas). Rademacher's bound is [15] of that paper;
the Weiss/Brown aliasing theorem is [5].
