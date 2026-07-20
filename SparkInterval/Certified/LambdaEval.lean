import SparkInterval.Certified.PowGlue
import SparkInterval.Certified.Exp
import SparkInterval.Certified.SinCos
import SparkInterval.Certified.LambdaPremises

/-!
# Certified evaluation of Dirichlet main sums

The executable core of the certified GRH endpoint evaluator.  For a
positive rational base `r` and rational `c, t`,

`rpowNegEval` encloses `r ^ (-(c + i t))`

from the proved elementary layer (`logInterval`, `expInterval`,
`sinCosInterval`) through the decomposition lemma
`contains_cpow_of_contains`, and

`mainSumEval` encloses the truncated Hurwitz sum
`hurwitzMain α M s = ∑_{n<M} (n+α)^{-s}` at `s = 1/2 + i t`

by accumulation with outward rounding.  Both soundness theorems are
unconditional: this is the computationally heavy part of the pipeline
(the Euler-Maclaurin tail and Gamma factor are O(1) per endpoint), and
its enclosures carry no analytic premise at all.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate Finset

/-- Evaluation parameters: exponential Taylor length, exponential
argument envelope `2^envExp`, sin/cos halving depth, and outward-rounding
precision. -/
structure EvalParams where
  terms : ℕ
  envExp : ℕ
  depth : ℕ
  prec : ℕ
  deriving Repr

/-- Certified enclosure of `r ^ (-(c + i t))` for rational `r > 0`.
Returns `none` when an internal witness search or envelope guard fails;
any `some` answer is sound. -/
def rpowNegEval (p : EvalParams) (r c t : ℚ) : Option ComplexRect :=
  if 0 < r ∧ 0 < p.terms then
    match logInterval p.terms p.envExp p.prec r with
    | none => none
    | some L =>
      let nc := (RatInterval.point (-c)).mul L
      let tL := (RatInterval.point t).mul L
      if |nc.lo| ≤ 2 ^ p.envExp ∧ |nc.hi| ≤ 2 ^ p.envExp then
        match sinCosInterval p.depth p.prec tL with
        | none => none
        | some (S, C) =>
            some (ComplexRect.roundOutRect p.prec
              (ComplexRect.scale (expInterval p.terms p.envExp p.prec nc)
                ⟨C, S.neg⟩))
      else none
  else none

theorem rpowNegEval_containsComplex {p : EvalParams} {r c t : ℚ}
    {R : ComplexRect} (h : rpowNegEval p r c t = some R) :
    R.ContainsComplex
      (((r : ℚ) : ℂ) ^ (-(((c : ℚ) : ℂ) + ((t : ℚ) : ℂ) * Complex.I))) := by
  unfold rpowNegEval at h
  split at h
  case isFalse => exact absurd h (by simp)
  case isTrue hcond =>
    obtain ⟨hr, hterms⟩ := hcond
    rcases hL : logInterval p.terms p.envExp p.prec r with _ | L
    · rw [hL] at h
      exact absurd h (by simp)
    rw [hL] at h
    simp only at h
    split at h
    case isFalse => exact absurd h (by simp)
    case isTrue hg =>
      rcases hSC : sinCosInterval p.depth p.prec
          ((RatInterval.point t).mul L) with _ | ⟨S, C⟩
      · rw [hSC] at h
        exact absurd h (by simp)
      rw [hSC] at h
      simp only [Option.some.injEq] at h
      subst h
      have hLog : L.ContainsReal (Real.log (r : ℝ)) :=
        logInterval_containsReal hterms hr hL
      have hnc : ((RatInterval.point (-c)).mul L).ContainsReal
          (-(c : ℝ) * Real.log (r : ℝ)) := by
        have hpt : (RatInterval.point (-c)).ContainsReal ((-c : ℚ) : ℝ) :=
          RatInterval.point_containsReal (-c)
        have hcast : ((-c : ℚ) : ℝ) = -(c : ℝ) := by push_cast; ring
        rw [hcast] at hpt
        exact RatInterval.mul_containsReal hpt hLog
      have hA := expInterval_containsReal (prec := p.prec) hterms hnc hg.1 hg.2
      have htL : ((RatInterval.point t).mul L).ContainsReal
          ((t : ℝ) * Real.log (r : ℝ)) :=
        RatInterval.mul_containsReal (RatInterval.point_containsReal t) hLog
      have hSCr := sinCosInterval_containsReal hSC htL
      exact ComplexRect.roundOutRect_containsComplex
        (contains_cpow_of_contains hr hA hSCr.1 hSCr.2)

/-- Certified enclosure of the truncated Hurwitz sum
`∑_{n<M} (n+α)^{-(1/2 + i t)}` by term accumulation with outward
rounding. -/
def mainSumEval (p : EvalParams) (α t : ℚ) : ℕ → Option ComplexRect
  | 0 => some ⟨RatInterval.point 0, RatInterval.point 0⟩
  | M + 1 =>
    match mainSumEval p α t M, rpowNegEval p ((M : ℚ) + α) (1 / 2) t with
    | some A, some T => some (ComplexRect.roundOutRect p.prec (A.add T))
    | _, _ => none

theorem zero_rect_containsComplex :
    (ComplexRect.mk (RatInterval.point 0) (RatInterval.point 0)
      ).ContainsComplex 0 := by
  constructor
  · simpa using RatInterval.point_containsReal 0
  · simpa using RatInterval.point_containsReal 0

/-- Unconditional soundness of the certified main sum: any `some` result
encloses the exact truncated Hurwitz Dirichlet sum on the critical
line. -/
theorem mainSumEval_containsComplex {p : EvalParams} {α t : ℚ}
    {M : ℕ} {R : ComplexRect}
    (h : mainSumEval p α t M = some R) :
    R.ContainsComplex
      (hurwitzMain α M ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I)) := by
  induction M generalizing R with
  | zero =>
    simp only [mainSumEval, Option.some.injEq] at h
    subst h
    simpa [hurwitzMain] using zero_rect_containsComplex
  | succ M ih =>
    rcases hA : mainSumEval p α t M with _ | A
    · rw [mainSumEval, hA] at h
      exact absurd h (by simp)
    rcases hT : rpowNegEval p ((M : ℚ) + α) (1 / 2) t with _ | T
    · rw [mainSumEval, hA, hT] at h
      exact absurd h (by simp)
    rw [mainSumEval, hA, hT] at h
    simp only [Option.some.injEq] at h
    subst h
    have hsum := ih hA
    have hterm := rpowNegEval_containsComplex hT
    have hbase : (((M : ℚ) + α : ℚ) : ℂ) = (M : ℂ) + (α : ℂ) := by
      push_cast
      ring
    have hexp : (-((((1 : ℚ) / 2 : ℚ) : ℂ) + ((t : ℚ) : ℂ) * Complex.I)) =
        (-((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I)) := by
      norm_num
    rw [hbase, hexp] at hterm
    have hstep :
        hurwitzMain α (M + 1) ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) =
          hurwitzMain α M ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) +
            ((M : ℂ) + (α : ℂ)) ^
              (-((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I)) :=
      Finset.sum_range_succ _ M
    rw [hstep]
    exact ComplexRect.roundOutRect_containsComplex
      (ComplexRect.add_containsComplex hsum hterm)

end SparkInterval.Certified
