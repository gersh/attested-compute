import SparkInterval.Certified.Complex
import Mathlib.NumberTheory.LSeries.ZMod

/-!
# Named analytic premises for the certified Dirichlet evaluator

The certified GRH endpoint evaluator re-computes Platt's completed
function from the Euler-Maclaurin expansion of the Hurwitz zeta function
and the Stirling expansion of `log Gamma`.  Both expansions consist of a
finite, exactly computable main part and an analytic remainder.  This
file defines the main parts and remainder radii as exact mathematical
expressions and names the two remainder facts as explicit `Prop`s:

* `EulerMaclaurinHurwitzBound` — the Euler-Maclaurin tail bound for
  `HurwitzZeta.hurwitzZeta` on the critical line, with the classical
  periodized-Bernoulli remainder estimate; and
* `StirlingGammaBound` — the Stirling remainder for `Complex.Gamma` on
  `re z > 0` after an integer argument shift, stated multiplicatively so
  no logarithm branch choice is needed.

Both statements are true theorems of classical analysis (they are exactly
the bounds Platt's computation and this repository's GPU kernel rely on);
their Lean proofs are deliberately deferred, mirroring how the zeta
verifier isolates its analytic obligations.  Every other ingredient of
the evaluator is proved unconditionally.

The Bernoulli-derived coefficients are given as explicit rationals so
that both the premises and the executable evaluator are self-contained;
a future proof of the premises will identify them with Mathlib's
`bernoulli (2 j)` values.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open Complex Finset

/-- `B_{2j} / (2j)!` for `j = 1..13` as explicit rationals (`0` outside).
These are the Euler-Maclaurin coefficients of the Hurwitz tail. -/
def emCoeff : ℕ → ℚ
  | 1 => 1 / 12
  | 2 => -1 / 720
  | 3 => 1 / 30240
  | 4 => -1 / 1209600
  | 5 => 1 / 47900160
  | 6 => -691 / 1307674368000
  | 7 => 1 / 74724249600
  | 8 => -3617 / 10670622842880000
  | 9 => 43867 / 5109094217170944000
  | 10 => -174611 / 802857662698291200000
  | 11 => 77683 / 14101100039391805440000
  | 12 => -236364091 / 1693824136731743669452800000
  | 13 => 657931 / 186134520519971831808000000
  | _ => 0

/-- `B_{2j} / (2j (2j-1))` for `j = 1..8` as explicit rationals
(`0` outside).  These are the Stirling-series coefficients. -/
def stirlingCoeff : ℕ → ℚ
  | 1 => 1 / 12
  | 2 => -1 / 360
  | 3 => 1 / 1260
  | 4 => -1 / 1680
  | 5 => 1 / 1188
  | 6 => -691 / 360360
  | 7 => 1 / 156
  | 8 => -3617 / 122400
  | _ => 0

/-- Rising factorial `(s)(s+1)...(s+k-1)`. -/
noncomputable def pochhammerC (s : ℂ) (k : ℕ) : ℂ :=
  ∏ i ∈ range k, (s + (i : ℂ))

/-- The truncated Hurwitz Dirichlet sum `∑_{n<M} (n+α)^{-s}`. -/
noncomputable def hurwitzMain (α : ℚ) (M : ℕ) (s : ℂ) : ℂ :=
  ∑ n ∈ range M, ((n : ℂ) + (α : ℂ)) ^ (-s)

/-- The Euler-Maclaurin correction terms through `J` Bernoulli terms,
with `x = M + α`:
`x^{1-s}/(s-1) + x^{-s}/2 + ∑_{j=1..J} emCoeff j (s)_{2j-1} x^{-s-2j+1}`. -/
noncomputable def hurwitzTail (α : ℚ) (M J : ℕ) (s : ℂ) : ℂ :=
  let x : ℂ := (M : ℂ) + (α : ℂ)
  x ^ ((1 : ℂ) - s) / (s - 1) + x ^ (-s) / 2 +
    ∑ j ∈ range J,
      (emCoeff (j + 1) : ℂ) * pochhammerC s (2 * j + 1) *
        x ^ (-s - (2 * (j : ℂ) + 1))

/-- The classical periodized-Bernoulli remainder radius
`4 |(s)_{2J+1}| (2π)^{-(2J+1)} x^{-(σ+2J)} / (σ+2J)` at `σ = re s`. -/
noncomputable def hurwitzTailError (α : ℚ) (M J : ℕ) (s : ℂ) : ℝ :=
  let x : ℝ := (M : ℝ) + (α : ℝ)
  4 * ‖pochhammerC s (2 * J + 1)‖ / (2 * Real.pi) ^ (2 * J + 1) *
    x ^ (-(s.re + 2 * J)) / (s.re + 2 * J)

/-- **Premise P1.**  Euler-Maclaurin expansion of the Hurwitz zeta
function with the classical remainder bound, for shift parameters in
`(0, 1]` and any point on the critical line.  This is the bound the GPU
kernel and Platt's computation use; its formal proof is deferred. -/
def EulerMaclaurinHurwitzBound : Prop :=
  ∀ (α : ℚ), 0 < α → α ≤ 1 → ∀ (M J : ℕ), 0 < M → 0 < J → J ≤ 13 →
    ∀ (t : ℝ),
      ‖HurwitzZeta.hurwitzZeta (((α : ℝ) : UnitAddCircle)) (1 / 2 + t * I) -
          hurwitzMain α M (1 / 2 + t * I) -
          hurwitzTail α M J (1 / 2 + t * I)‖ ≤
        hurwitzTailError α M J (1 / 2 + t * I)

/-- The Stirling main term for `log Gamma` after shifting the argument by
`shift`: with `w = z + shift`,
`(w - 1/2) log w - w + log(2π)/2 + ∑_{j=1..JG} stirlingCoeff j w^{1-2j}
 - ∑_{k<shift} log (z+k)`. -/
noncomputable def stirlingMain (z : ℂ) (shift JG : ℕ) : ℂ :=
  let w : ℂ := z + (shift : ℂ)
  (w - 1 / 2) * Complex.log w - w +
      (Real.log (2 * Real.pi) / 2 : ℝ) +
      ∑ j ∈ range JG,
        (stirlingCoeff (j + 1) : ℂ) * w ^ (1 - (2 * ((j : ℂ) + 1))) -
    ∑ k ∈ range shift, Complex.log (z + (k : ℂ))

/-- The Stirling remainder radius after the shift, with the
`sec(arg w / 2) ≤ √2` estimate for `re w > 0` folded into `2^{JG+1}`:
`|B_{2JG+2}| / ((2JG+2)(2JG+1)) 2^{JG+1} |w|^{-(2JG+1)}`.
The leading rational is supplied by the caller so the statement stays
self-contained; `stirlingErrorConst 8 = 3617/272 · 2^9 / ...` etc. -/
noncomputable def stirlingError (z : ℂ) (shift JG : ℕ) (errConst : ℚ) : ℝ :=
  (errConst : ℝ) * ‖z + (shift : ℂ)‖ ^ (-(2 * (JG : ℝ) + 1))

/-- **Premise P2.**  Stirling expansion of `Complex.Gamma` with explicit
remainder, stated multiplicatively: for `re z > 0` and shift making the
expansion admissible, `Gamma z` differs from `exp (stirlingMain z)` by a
factor `exp δ` with `|δ|` at most the remainder radius.  The instance
used by the evaluator takes `JG = 8`, `errConst = (3617/122400)·2^9`
(that is, `|B_18|/(18·17) · 2^9`).  Formal proof deferred. -/
def StirlingGammaBound : Prop :=
  ∀ (z : ℂ), 0 < z.re → ∀ (shift : ℕ), 12 ≤ (z + (shift : ℂ)).re →
    ∃ δ : ℂ,
      Complex.Gamma z = Complex.exp (stirlingMain z shift 8 + δ) ∧
        ‖δ‖ ≤ stirlingError z shift 8 (3617 / 122400 * 2 ^ 9)

end SparkInterval.Certified
