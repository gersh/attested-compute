import SparkInterval.Certified.LambdaEval

/-!
# Certified evaluation of the Euler-Maclaurin tail

The Euler-Maclaurin correction `hurwitzTail` is a small fixed expression:
two powers of `x = M + α`, a division by the exact rational-complex
constant `s - 1`, and `J` Bernoulli terms whose coefficients
`emCoeff (j+1) * (s)_{2j+1}` are exact rational-complex numbers because
`s = 1/2 + i t` has rational real and imaginary parts.  Every power comes
from the already-certified `rpowNegEval`; everything else is exact
arithmetic.  The soundness theorem is unconditional: `tailEval` encloses
the exact value of `hurwitzTail`.  (The *remainder* of the Euler-Maclaurin
expansion beyond the tail is the named premise
`EulerMaclaurinHurwitzBound`, consumed downstream.)
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate Finset

/-- Exact rational complex numbers for coefficient arithmetic. -/
structure QC where
  re : ℚ
  im : ℚ
  deriving Repr

namespace QC

noncomputable def toC (z : QC) : ℂ := ⟨(z.re : ℝ), (z.im : ℝ)⟩

def mul (z w : QC) : QC :=
  ⟨z.re * w.re - z.im * w.im, z.re * w.im + z.im * w.re⟩

def rect (z : QC) : ComplexRect :=
  ⟨RatInterval.point z.re, RatInterval.point z.im⟩

theorem toC_mul (z w : QC) : (z.mul w).toC = z.toC * w.toC := by
  apply Complex.ext
  · simp only [toC, mul, Complex.mul_re]
    push_cast
    ring
  · simp only [toC, mul, Complex.mul_im]
    push_cast
    ring

theorem rect_containsComplex (z : QC) : z.rect.ContainsComplex z.toC :=
  ⟨RatInterval.point_containsReal _, RatInterval.point_containsReal _⟩

theorem toC_eq (z : QC) :
    z.toC = ((z.re : ℝ) : ℂ) + ((z.im : ℝ) : ℂ) * Complex.I := by
  rw [toC, Complex.mk_eq_add_mul_I]

end QC

/-- The critical-line point `s = 1/2 + i t` shifted by `k`. -/
def sShift (t : ℚ) (k : ℕ) : QC := ⟨1 / 2 + k, t⟩

theorem sShift_toC (t : ℚ) (k : ℕ) :
    (sShift t k).toC =
      ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) + (k : ℂ) := by
  rw [QC.toC_eq]
  simp only [sShift]
  push_cast
  ring

/-- Exact rising factorial `(s)_m` at `s = 1/2 + i t`. -/
def pochQ (t : ℚ) : ℕ → QC
  | 0 => ⟨1, 0⟩
  | m + 1 => (pochQ t m).mul (sShift t m)

theorem pochQ_toC (t : ℚ) (m : ℕ) :
    (pochQ t m).toC =
      pochhammerC ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) m := by
  induction m with
  | zero =>
    simp [pochQ, pochhammerC, QC.toC, Complex.ext_iff]
  | succ m ih =>
    rw [pochQ, QC.toC_mul, ih, sShift_toC, pochhammerC, pochhammerC,
      Finset.prod_range_succ]

/-- Exact inverse of `s - 1 = -1/2 + i t`. -/
def sMinusOneInv (t : ℚ) : QC :=
  let d : ℚ := 1 / 4 + t ^ 2
  ⟨(-1 / 2) / d, -t / d⟩

theorem sMinusOneInv_toC (t : ℚ) :
    (sMinusOneInv t).toC =
      (((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) - 1)⁻¹ := by
  have hd : (1 / 4 + t ^ 2 : ℚ) ≠ 0 := by positivity
  have hsm : ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) - 1 =
      (QC.mk (-1 / 2) t).toC := by
    rw [QC.toC_eq]
    push_cast
    ring
  have hmulq : (QC.mk (-1 / 2) t).mul (sMinusOneInv t) = QC.mk 1 0 := by
    simp only [QC.mul, sMinusOneInv, QC.mk.injEq]
    constructor
    · field_simp
      ring
    · field_simp
      ring
  have honeC : (QC.mk 1 0).toC = 1 := by
    rw [QC.toC_eq]
    push_cast
    ring
  refine (inv_eq_of_mul_eq_one_right ?_).symm
  rw [hsm, ← QC.toC_mul, hmulq, honeC]

/-- The zero rectangle used to seed accumulations. -/
def zeroRect : ComplexRect :=
  ⟨RatInterval.point 0, RatInterval.point 0⟩

/-- Accumulated Bernoulli terms
`∑_{j<J} emCoeff (j+1) (s)_{2j+1} x^{-s-(2j+1)}`. -/
def tailBernoulli (p : EvalParams) (x t : ℚ) : ℕ → Option ComplexRect
  | 0 => some zeroRect
  | j + 1 =>
    match tailBernoulli p x t j,
        rpowNegEval p x (1 / 2 + (2 * j + 1 : ℕ)) t with
    | some A, some X =>
        some (ComplexRect.roundOutRect p.prec
          (A.add (((QC.mk (emCoeff (j + 1)) 0).mul
            (pochQ t (2 * j + 1))).rect.mul X)))
    | _, _ => none

theorem tailBernoulli_containsComplex {p : EvalParams} {x t : ℚ}
    {J : ℕ} {R : ComplexRect}
    (h : tailBernoulli p x t J = some R) :
    R.ContainsComplex
      (∑ j ∈ range J,
        (emCoeff (j + 1) : ℂ) *
          pochhammerC ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I)
            (2 * j + 1) *
          ((x : ℚ) : ℂ) ^
            (-((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) -
              (2 * (j : ℂ) + 1))) := by
  induction J generalizing R with
  | zero =>
    simp only [tailBernoulli, Option.some.injEq] at h
    subst h
    simpa [zeroRect] using zero_rect_containsComplex
  | succ J ih =>
    rcases hA : tailBernoulli p x t J with _ | A
    · rw [tailBernoulli, hA] at h
      exact absurd h (by simp)
    rcases hX : rpowNegEval p x (1 / 2 + (2 * J + 1 : ℕ)) t with _ | X
    · rw [tailBernoulli, hA, hX] at h
      exact absurd h (by simp)
    rw [tailBernoulli, hA, hX] at h
    simp only [Option.some.injEq] at h
    subst h
    rw [Finset.sum_range_succ]
    have hsum := ih hA
    have hpow := rpowNegEval_containsComplex hX
    have hexp :
        (-(((1 / 2 + (2 * J + 1 : ℕ) : ℚ) : ℂ) +
            ((t : ℚ) : ℂ) * Complex.I)) =
          (-((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I) -
            (2 * (J : ℂ) + 1)) := by
      push_cast
      ring
    rw [hexp] at hpow
    have hcoef := ComplexRect.mul_containsComplex
      (QC.rect_containsComplex
        ((QC.mk (emCoeff (J + 1)) 0).mul (pochQ t (2 * J + 1)))) hpow
    rw [QC.toC_mul, pochQ_toC] at hcoef
    have hqc : (QC.mk (emCoeff (J + 1)) 0).toC = (emCoeff (J + 1) : ℂ) := by
      apply Complex.ext <;> simp [QC.toC]
    rw [hqc] at hcoef
    exact ComplexRect.roundOutRect_containsComplex
      (ComplexRect.add_containsComplex hsum hcoef)

/-- Certified enclosure of the full Euler-Maclaurin correction
`hurwitzTail α M J (1/2 + i t)`. -/
def tailEval (p : EvalParams) (α t : ℚ) (M J : ℕ) : Option ComplexRect :=
  let x : ℚ := (M : ℚ) + α
  match rpowNegEval p x (-1 / 2) t, rpowNegEval p x (1 / 2) t,
      tailBernoulli p x t J with
  | some xOneMinusS, some xMinusS, some bern =>
      some (ComplexRect.roundOutRect p.prec
        (((xOneMinusS.mul (sMinusOneInv t).rect).add
            (ComplexRect.scale (RatInterval.point (1 / 2)) xMinusS)).add
          bern))
  | _, _, _ => none

theorem tailEval_containsComplex {p : EvalParams} {α t : ℚ}
    {M J : ℕ} {R : ComplexRect}
    (h : tailEval p α t M J = some R) :
    R.ContainsComplex
      (hurwitzTail α M J ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I)) := by
  set s : ℂ := (1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I with hs
  rcases h1 : rpowNegEval p ((M : ℚ) + α) (-1 / 2) t with _ | xOneMinusS
  · rw [tailEval, h1] at h
    exact absurd h (by simp)
  rcases h2 : rpowNegEval p ((M : ℚ) + α) (1 / 2) t with _ | xMinusS
  · rw [tailEval, h1, h2] at h
    exact absurd h (by simp)
  rcases h3 : tailBernoulli p ((M : ℚ) + α) t J with _ | bern
  · rw [tailEval, h1, h2, h3] at h
    exact absurd h (by simp)
  rw [tailEval, h1, h2, h3] at h
  simp only [Option.some.injEq] at h
  subst h
  have hbase : (((M : ℚ) + α : ℚ) : ℂ) = (M : ℂ) + (α : ℂ) := by
    push_cast
    ring
  have hp1 := rpowNegEval_containsComplex h1
  have hp2 := rpowNegEval_containsComplex h2
  have he1' : (-((((-1 : ℚ) / 2 : ℚ) : ℂ) + ((t : ℚ) : ℂ) * Complex.I)) =
      ((1 : ℂ) - s) := by
    rw [hs]
    push_cast
    ring
  have he2' : (-((((1 : ℚ) / 2 : ℚ) : ℂ) + ((t : ℚ) : ℂ) * Complex.I)) =
      (-s) := by
    rw [hs]
    push_cast
    ring
  rw [hbase, he1'] at hp1
  rw [hbase, he2'] at hp2
  have hbern := tailBernoulli_containsComplex h3
  rw [hbase] at hbern
  have hterm1 := ComplexRect.mul_containsComplex hp1
    (QC.rect_containsComplex (sMinusOneInv t))
  rw [sMinusOneInv_toC] at hterm1
  have hterm2 := ComplexRect.scale_containsComplex
    (RatInterval.point_containsReal (1 / 2)) hp2
  rw [hurwitzTail]
  have hgoal :
      ((M : ℂ) + (α : ℂ)) ^ ((1 : ℂ) - s) / (s - 1) +
          ((M : ℂ) + (α : ℂ)) ^ (-s) / 2 +
          ∑ j ∈ range J,
            (emCoeff (j + 1) : ℂ) * pochhammerC s (2 * j + 1) *
              ((M : ℂ) + (α : ℂ)) ^ (-s - (2 * (j : ℂ) + 1)) =
        (((M : ℂ) + (α : ℂ)) ^ ((1 : ℂ) - s) * (s - 1)⁻¹ +
            (((1 / 2 : ℚ) : ℝ) : ℂ) * ((M : ℂ) + (α : ℂ)) ^ (-s)) +
          ∑ j ∈ range J,
            (emCoeff (j + 1) : ℂ) * pochhammerC s (2 * j + 1) *
              ((M : ℂ) + (α : ℂ)) ^ (-s - (2 * (j : ℂ) + 1)) := by
    push_cast
    ring
  rw [hgoal]
  exact ComplexRect.roundOutRect_containsComplex
    (ComplexRect.add_containsComplex
      (ComplexRect.add_containsComplex hterm1 hterm2) hbern)

end SparkInterval.Certified
