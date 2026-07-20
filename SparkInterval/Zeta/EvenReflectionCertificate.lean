import SparkInterval.Zeta.EndpointCertificate

/-!
# Reflecting positive endpoint certificates

A conventional Hardy-Z computation only evaluates positive ordinates.  This
module proves the exact finite-family optimization needed by that layout: if
the checked real evaluator is even, `n` ordered positive sign-change brackets
can be reflected into `n` negative brackets without evaluating another `2*n`
endpoints.  The reflected brackets are placed in reverse order, followed by
the original positive family, giving `2*n` globally ordered brackets.

The theorem is purely structural.  It does not assert that a concrete Hardy-Z
implementation is even; that evaluator theorem remains an explicit premise.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

namespace RationalBracket

/-- Reflect a bracket through zero.  Endpoint result intervals are swapped,
which is sound for an even evaluator. -/
def reflect (bracket : RationalBracket) : RationalBracket where
  lower := -bracket.upper
  upper := -bracket.lower
  lowerValue := bracket.upperValue
  upperValue := bracket.lowerValue

@[simp] theorem reflect_lower (bracket : RationalBracket) :
    bracket.reflect.lower = -bracket.upper := rfl

@[simp] theorem reflect_upper (bracket : RationalBracket) :
    bracket.reflect.upper = -bracket.lower := rfl

@[simp] theorem reflect_lowerValue (bracket : RationalBracket) :
    bracket.reflect.lowerValue = bracket.upperValue := rfl

@[simp] theorem reflect_upperValue (bracket : RationalBracket) :
    bracket.reflect.upperValue = bracket.lowerValue := rfl

@[simp] theorem reflect_reflect (bracket : RationalBracket) :
    bracket.reflect.reflect = bracket := by
  cases bracket
  simp [reflect]

/-- Reflection preserves every exact-rational local checker condition. -/
@[simp] theorem reflect_isValid_iff (bracket : RationalBracket) :
    bracket.reflect.IsValid ↔ bracket.IsValid := by
  constructor
  · intro hvalid
    have hreflected : bracket.reflect.reflect.IsValid := by
      rcases hvalid with ⟨horder, hlower, hupper, hsign⟩
      refine ⟨neg_lt_neg horder, hupper, hlower, ?_⟩
      exact hsign.elim (fun h => Or.inr h) (fun h => Or.inl h)
    simpa using hreflected
  · intro hvalid
    rcases hvalid with ⟨horder, hlower, hupper, hsign⟩
    refine ⟨neg_lt_neg horder, hupper, hlower, ?_⟩
    exact hsign.elim (fun h => Or.inr h) (fun h => Or.inl h)

/-- Endpoint enclosures transfer to the reflected bracket for an even real
evaluator. -/
theorem reflect_enclosesEndpoints {bracket : RationalBracket} {f : ℝ → ℝ}
    (heven : Function.Even f)
    (hencloses : bracket.EnclosesEndpoints f) :
    bracket.reflect.EnclosesEndpoints f := by
  constructor
  · change bracket.upperValue.ContainsReal
      (f (((-bracket.upper : ℚ) : ℝ)))
    simpa using (show bracket.upperValue.ContainsReal
      (f (-(bracket.upper : ℝ))) by
        rw [heven]
        exact hencloses.2)
  · change bracket.lowerValue.ContainsReal
      (f (((-bracket.lower : ℚ) : ℝ)))
    simpa using (show bracket.lowerValue.ContainsReal
      (f (-(bracket.lower : ℝ))) by
        rw [heven]
        exact hencloses.1)

end RationalBracket

namespace RationalBracketFamily

/-- Negative reflected brackets in reverse order, followed by the original
positive brackets. -/
def reflectPositive {count : Nat}
    (family : RationalBracketFamily count) :
    RationalBracketFamily (count + count) where
  entries := Fin.append
    (fun index => (family.entries index.rev).reflect)
    family.entries

@[simp] theorem reflectPositive_negative {count : Nat}
    (family : RationalBracketFamily count) (index : Fin count) :
    (family.reflectPositive.entries (Fin.castAdd count index)) =
      (family.entries index.rev).reflect := by
  simp [reflectPositive]

@[simp] theorem reflectPositive_positive {count : Nat}
    (family : RationalBracketFamily count) (index : Fin count) :
    (family.reflectPositive.entries (Fin.natAdd count index)) =
      family.entries index := by
  simpa [reflectPositive] using
    (Fin.append_right
      (fun index => (family.entries index.rev).reflect)
      family.entries index)

/-- A valid family strictly above zero becomes a valid symmetric family with
twice as many brackets. -/
theorem reflectPositive_isValid {count : Nat}
    {family : RationalBracketFamily count}
    (hvalid : family.IsValid)
    (hpositive : ∀ index, 0 < (family.entries index).lower) :
    family.reflectPositive.IsValid := by
  constructor
  · intro index
    refine Fin.addCases (motive := fun index =>
      (family.reflectPositive.entries index).IsValid) ?_ ?_ index
    · intro negative
      simp [hvalid.1 negative.rev]
    · intro positive
      rw [reflectPositive_positive]
      exact hvalid.1 positive
  · intro left right hlt
    refine (Fin.addCases (motive := fun left => ∀ {right}, left < right →
      (family.reflectPositive.entries left).upper <
        (family.reflectPositive.entries right).lower) ?_ ?_ left) hlt
    · intro leftNegative right hleftRight
      refine Fin.addCases (motive := fun right =>
        Fin.castAdd count leftNegative < right →
          (family.reflectPositive.entries
              (Fin.castAdd count leftNegative)).upper <
            (family.reflectPositive.entries right).lower) ?_ ?_ right hleftRight
      · intro rightNegative hnegative
        simp only [reflectPositive_negative, RationalBracket.reflect_upper,
          RationalBracket.reflect_lower]
        have hreverse : rightNegative.rev < leftNegative.rev := by
          rw [Fin.rev_lt_rev]
          exact hnegative
        exact neg_lt_neg (hvalid.2 hreverse)
      · intro rightPositive _hcross
        simp only [reflectPositive_negative, reflectPositive_positive,
          RationalBracket.reflect_upper]
        exact (neg_neg_of_pos (hpositive leftNegative.rev)).trans
          (hpositive rightPositive)
    · intro leftPositive right hleftRight
      refine Fin.addCases (motive := fun right =>
        Fin.natAdd count leftPositive < right →
          (family.reflectPositive.entries
              (Fin.natAdd count leftPositive)).upper <
            (family.reflectPositive.entries right).lower) ?_ ?_ right hleftRight
      · intro rightNegative himpossible
        change count + leftPositive.val < rightNegative.val at himpossible
        have hright : rightNegative.val < count := rightNegative.isLt
        omega
      · intro rightPositive hpositiveOrder
        simp only [reflectPositive_positive]
        apply hvalid.2
        change count + leftPositive.val < count + rightPositive.val at hpositiveOrder
        omega

/-- The reflected family has evaluator enclosures without any negative-side
arithmetic rows when the evaluator is even. -/
theorem reflectPositive_enclosesEndpoints {count : Nat}
    {family : RationalBracketFamily count} {f : ℝ → ℝ}
    (heven : Function.Even f)
    (hencloses : ∀ index, (family.entries index).EnclosesEndpoints f) :
    ∀ index, (family.reflectPositive.entries index).EnclosesEndpoints f := by
  intro index
  refine Fin.addCases (motive := fun index =>
    (family.reflectPositive.entries index).EnclosesEndpoints f) ?_ ?_ index
  · intro negative
    simp only [reflectPositive_negative]
    exact RationalBracket.reflect_enclosesEndpoints heven
      (hencloses negative.rev)
  · intro positive
    rw [reflectPositive_positive]
    exact hencloses positive

/-- Positive-side bounds imply that every reflected/original bracket lies in
the symmetric height interval. -/
theorem reflectPositive_lower_bound {count : Nat}
    {family : RationalBracketFamily count} {height : ℝ}
    (hheight : 0 ≤ height)
    (hpositive : ∀ index, 0 < ((family.entries index).lower : ℝ))
    (hupper : ∀ index, ((family.entries index).upper : ℝ) ≤ height) :
    ∀ index, -height ≤
      ((family.reflectPositive.entries index).lower : ℝ) := by
  intro index
  refine Fin.addCases (motive := fun index => -height ≤
    ((family.reflectPositive.entries index).lower : ℝ)) ?_ ?_ index
  · intro negative
    simp only [reflectPositive_negative, RationalBracket.reflect_lower,
      Rat.cast_neg]
    exact neg_le_neg (hupper negative.rev)
  · intro positive
    simp only [reflectPositive_positive]
    exact (neg_nonpos.mpr hheight).trans (le_of_lt (hpositive positive))

/-- Positive-side bounds imply the symmetric upper endpoint bound. -/
theorem reflectPositive_upper_bound {count : Nat}
    {family : RationalBracketFamily count} {height : ℝ}
    (hheight : 0 ≤ height)
    (hpositive : ∀ index, 0 < ((family.entries index).lower : ℝ))
    (hupper : ∀ index, ((family.entries index).upper : ℝ) ≤ height) :
    ∀ index,
      ((family.reflectPositive.entries index).upper : ℝ) ≤ height := by
  intro index
  refine Fin.addCases (motive := fun index =>
    ((family.reflectPositive.entries index).upper : ℝ) ≤ height) ?_ ?_ index
  · intro negative
    simp only [reflectPositive_negative, RationalBracket.reflect_upper,
      Rat.cast_neg]
    exact (neg_nonpos.mpr (le_of_lt (hpositive negative.rev))).trans hheight
  · intro positive
    simp only [reflectPositive_positive]
    exact hupper positive

end RationalBracketFamily

end SparkInterval.Zeta
