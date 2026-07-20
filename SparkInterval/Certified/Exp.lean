import SparkInterval.Certified.Rounding

/-!
# Certified rational-interval enclosures of `Real.exp` and `Real.log`

This file provides executable, fully proved enclosures of the real
exponential and logarithm by rational intervals.

* `expSmall` encloses `Real.exp x` for `|x| ≤ 1` by a truncated Taylor sum
  widened by the Lagrange-style remainder bound `Real.exp_bound`.
* `expQ` extends the enclosure to `|x| ≤ 2 ^ k` by argument scaling and
  interval squaring: `exp x = (exp (x / 2 ^ k)) ^ (2 ^ k)`.
* `expInterval` evaluates `exp` on a rational interval by monotone endpoint
  evaluation.
* `logCheck`/`logInterval` enclose `Real.log x` by exp-witness checking: an
  unverified rational guess for the logarithm is certified a posteriori by
  evaluating `expQ` at the candidate endpoints and comparing with `x`.

Every enclosure theorem is proved without `sorry`, `native_decide`, or new
axioms, so the computations may be replayed inside the kernel.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-! ## Taylor enclosure of `exp` on `|x| ≤ 1` -/

/-- The truncated exponential Taylor sum `∑ m < terms, x ^ m / m!`,
evaluated in exact rational arithmetic. -/
def expTaylorSum (terms : ℕ) (x : ℚ) : ℚ :=
  ∑ m ∈ Finset.range terms, x ^ m / (m.factorial : ℚ)

/-- Rational remainder slack for the truncated exponential series.  For
`|x| ≤ 1` and `0 < terms` the tail of the series is bounded by
`(terms + 1) / (terms! * terms)`; see `Real.exp_bound`. -/
def expSlack (terms : ℕ) : ℚ :=
  ((terms : ℚ) + 1) / ((terms.factorial : ℚ) * (terms : ℚ))

/-- Taylor enclosure of `Real.exp x`, sound for `|x| ≤ 1` and `0 < terms`. -/
def expSmall (terms : ℕ) (x : ℚ) : RatInterval :=
  ⟨expTaylorSum terms x - expSlack terms, expTaylorSum terms x + expSlack terms⟩

theorem expTaylorSum_cast (terms : ℕ) (x : ℚ) :
    ((expTaylorSum terms x : ℚ) : ℝ) =
      ∑ m ∈ Finset.range terms, (x : ℝ) ^ m / (m.factorial : ℝ) := by
  unfold expTaylorSum
  push_cast
  rfl

theorem expSlack_cast (terms : ℕ) :
    ((expSlack terms : ℚ) : ℝ) =
      (terms.succ : ℝ) / ((terms.factorial : ℝ) * (terms : ℝ)) := by
  unfold expSlack
  push_cast
  ring

theorem expSmall_containsReal {terms : ℕ} (ht : 0 < terms) {x : ℚ}
    (hx : |x| ≤ 1) : (expSmall terms x).ContainsReal (Real.exp (x : ℝ)) := by
  have hxR : |(x : ℝ)| ≤ 1 := by exact_mod_cast hx
  have hb := Real.exp_bound hxR ht
  have hpow : |(x : ℝ)| ^ terms ≤ 1 := pow_le_one₀ (abs_nonneg _) hxR
  have hslack_nonneg :
      (0 : ℝ) ≤ (terms.succ : ℝ) / ((terms.factorial : ℝ) * (terms : ℝ)) := by
    positivity
  have hb' : |Real.exp (x : ℝ) -
        ∑ m ∈ Finset.range terms, (x : ℝ) ^ m / (m.factorial : ℝ)|
      ≤ (terms.succ : ℝ) / ((terms.factorial : ℝ) * (terms : ℝ)) :=
    hb.trans (mul_le_of_le_one_left hslack_nonneg hpow)
  rw [← expTaylorSum_cast, ← expSlack_cast] at hb'
  obtain ⟨h1, h2⟩ := abs_le.mp hb'
  constructor
  · show ((expTaylorSum terms x - expSlack terms : ℚ) : ℝ) ≤ Real.exp (x : ℝ)
    rw [Rat.cast_sub]
    linarith
  · show Real.exp (x : ℝ) ≤ ((expTaylorSum terms x + expSlack terms : ℚ) : ℝ)
    rw [Rat.cast_add]
    linarith

/-! ## Scaling and squaring for moderate arguments -/

/-- Enclosure of `Real.exp x` for `|x| ≤ 2 ^ k` by scaling and squaring:
`exp x = (exp (x / 2 ^ k)) ^ (2 ^ k)`.  Intermediate results are
outward-rounded to dyadics with denominator `2 ^ prec`. -/
def expQ (terms k prec : ℕ) (x : ℚ) : RatInterval :=
  roundOut prec ((roundOut prec (expSmall terms (x / 2 ^ k))).powNat (2 ^ k))

theorem expQ_containsReal {terms k prec : ℕ} (ht : 0 < terms) {x : ℚ}
    (hx : |x| ≤ 2 ^ k) : (expQ terms k prec x).ContainsReal (Real.exp (x : ℝ)) := by
  have h2k : (0 : ℚ) < 2 ^ k := by positivity
  have hy : |x / 2 ^ k| ≤ 1 := by
    rw [abs_div, abs_of_pos h2k, div_le_one h2k]
    exact hx
  have hsmall :
      (roundOut prec (expSmall terms (x / 2 ^ k))).ContainsReal
        (Real.exp (((x / 2 ^ k : ℚ) : ℝ))) :=
    roundOut_containsReal (expSmall_containsReal ht hy)
  have hpow := RatInterval.powNat_containsReal hsmall (2 ^ k)
  have hexp : Real.exp (((x / 2 ^ k : ℚ) : ℝ)) ^ (2 ^ k : ℕ)
      = Real.exp (x : ℝ) := by
    rw [← Real.exp_nat_mul]
    congr 1
    have hne : ((2 : ℝ)) ^ k ≠ 0 := by positivity
    push_cast
    field_simp
  rw [hexp] at hpow
  exact roundOut_containsReal hpow

/-! ## Monotone interval evaluation of `exp` -/

/-- Enclosure of `Real.exp` over an interval by monotone endpoint
evaluation. -/
def expInterval (terms k prec : ℕ) (I : RatInterval) : RatInterval :=
  ⟨(expQ terms k prec I.lo).lo, (expQ terms k prec I.hi).hi⟩

theorem expInterval_containsReal {terms k prec : ℕ} (ht : 0 < terms)
    {I : RatInterval} {x : ℝ} (hI : I.ContainsReal x)
    (hlo : |I.lo| ≤ 2 ^ k) (hhi : |I.hi| ≤ 2 ^ k) :
    (expInterval terms k prec I).ContainsReal (Real.exp x) := by
  have h1 := expQ_containsReal (prec := prec) ht hlo
  have h2 := expQ_containsReal (prec := prec) ht hhi
  constructor
  · show ((expQ terms k prec I.lo).lo : ℝ) ≤ Real.exp x
    exact h1.1.trans (Real.exp_le_exp.mpr hI.1)
  · show Real.exp x ≤ ((expQ terms k prec I.hi).hi : ℝ)
    exact (Real.exp_le_exp.mpr hI.2).trans h2.2

/-! ## Logarithm via exp-witness checking -/

/-- Executable certificate check that `[lo, hi]` encloses `log x`: the
guards keep both endpoints inside the `expQ` design envelope, and the two
comparisons certify `exp lo ≤ x ≤ exp hi` through sound `expQ` enclosures. -/
def logCheck (terms k prec : ℕ) (x lo hi : ℚ) : Bool :=
  decide (|lo| ≤ 2 ^ k ∧ |hi| ≤ 2 ^ k ∧
    (expQ terms k prec lo).hi ≤ x ∧ x ≤ (expQ terms k prec hi).lo)

theorem logCheck_sound {terms k prec : ℕ} {x lo hi : ℚ} (ht : 0 < terms)
    (hx : 0 < x) (h : logCheck terms k prec x lo hi = true) :
    (RatInterval.mk lo hi).ContainsReal (Real.log (x : ℝ)) := by
  rw [logCheck, decide_eq_true_eq] at h
  obtain ⟨hlo, hhi, h1, h2⟩ := h
  have hxR : (0 : ℝ) < (x : ℝ) := by exact_mod_cast hx
  have hcl := expQ_containsReal (prec := prec) ht hlo
  have hch := expQ_containsReal (prec := prec) ht hhi
  constructor
  · rw [Real.le_log_iff_exp_le hxR]
    calc Real.exp ((lo : ℚ) : ℝ) ≤ ((expQ terms k prec lo).hi : ℝ) := hcl.2
      _ ≤ (x : ℝ) := by exact_mod_cast h1
  · rw [Real.log_le_iff_le_exp hxR]
    calc (x : ℝ) ≤ ((expQ terms k prec hi).lo : ℝ) := by exact_mod_cast h2
      _ ≤ Real.exp ((hi : ℚ) : ℝ) := hch.1

/-- Fixed rational approximation of `log 2`.  It only seeds the witness
search in `logInterval`; no correctness property is needed or proved. -/
def ln2Approx : ℚ := 693147180559945309417232121458 / 10 ^ 30

/-- Unverified rational guess for `log x` via range reduction to roughly
`[1, 2)` and ten terms of the atanh series
`log m = 2 ∑ u^(2i+1)/(2i+1)` with `u = (m-1)/(m+1)`.  Accuracy is
irrelevant for soundness: `logCheck` certifies the final interval a
posteriori; a sharper guess only tightens the certified interval the
witness search converges to. -/
def logGuess (x : ℚ) : ℚ :=
  if x ≤ 0 then 0
  else
    let e : ℤ := (Nat.log 2 x.num.toNat : ℤ) - (Nat.log 2 x.den : ℤ)
    let m : ℚ := x / (2 : ℚ) ^ e
    let u : ℚ := (m - 1) / (m + 1)
    let u2 : ℚ := u * u
    let series : ℚ :=
      u * (1 + u2 * (1 / 3 + u2 * (1 / 5 + u2 * (1 / 7 + u2 * (1 / 9 +
        u2 * (1 / 11 + u2 * (1 / 13 + u2 * (1 / 15 + u2 * (1 / 17 +
          u2 / 19)))))))))
    (e : ℚ) * ln2Approx + 2 * series

/-- Bounded witness search: try symmetric intervals around the guess `g`
with geometrically growing slack until `logCheck` certifies one. -/
def logSearch (terms k prec : ℕ) (x g : ℚ) : ℕ → ℚ → Option RatInterval
  | 0, _ => none
  | fuel + 1, slack =>
    if logCheck terms k prec x (g - slack) (g + slack) then
      some ⟨g - slack, g + slack⟩
    else
      logSearch terms k prec x g fuel (2 * slack)

theorem logSearch_sound {terms k prec : ℕ} {x g : ℚ} (ht : 0 < terms)
    (hx : 0 < x) :
    ∀ (fuel : ℕ) (slack : ℚ) {I : RatInterval},
      logSearch terms k prec x g fuel slack = some I →
      I.ContainsReal (Real.log (x : ℝ)) := by
  intro fuel
  induction fuel with
  | zero =>
    intro slack I h
    simp [logSearch] at h
  | succ n ih =>
    intro slack I h
    rw [logSearch] at h
    split at h
    · rename_i hcheck
      injection h with h
      subst h
      exact logCheck_sound ht hx hcheck
    · exact ih _ h

/-- Total executable enclosure of `Real.log x`.  A rational guess is
refined by the certified witness search; `none` is returned when no
candidate interval passes `logCheck` within the fuel budget. -/
def logInterval (terms k prec : ℕ) (x : ℚ) : Option RatInterval :=
  if 0 < x then
    logSearch terms k prec x (logGuess x) 64 (1 / 2 ^ (prec / 2))
  else
    none

theorem logInterval_containsReal {terms k prec : ℕ} {x : ℚ}
    {I : RatInterval} (ht : 0 < terms) (hx : 0 < x)
    (h : logInterval terms k prec x = some I) :
    I.ContainsReal (Real.log (x : ℝ)) := by
  rw [logInterval, if_pos hx] at h
  exact logSearch_sound ht hx _ _ h

end SparkInterval.Certified
