import SparkInterval.IntervalSemantics

/-!
# Soundness of expression evaluation

The main theorem connects the two Phase 1 semantics.  It is conditional on
both evaluators succeeding: interval evaluation may conservatively reject a
division when its denominator interval contains zero even if the selected exact
denominator happens to be nonzero.
-/

set_option autoImplicit false

namespace SparkInterval

noncomputable section

local instance : DecidableEq ℝ := Classical.decEq ℝ

local instance (I : RealInterval) : Decidable I.ExcludesZero :=
  Classical.propDecidable _

private theorem optionMap_eq_some
    {α β : Type} {o : Option α} {f : α → β} {z : β}
    (h : (do let x ← o; pure (f x)) = some z) :
    ∃ x, o = some x ∧ f x = z := by
  cases o with
  | none => simp at h
  | some x =>
      refine ⟨x, rfl, ?_⟩
      simpa using h

private theorem optionMap₂_eq_some
    {α β γ : Type} {oa : Option α} {ob : Option β} {f : α → β → γ} {z : γ}
    (h : (do let x ← oa; let y ← ob; pure (f x y)) = some z) :
    ∃ x y, oa = some x ∧ ob = some y ∧ f x y = z := by
  cases oa with
  | none => simp at h
  | some x =>
      cases ob with
      | none => simp at h
      | some y =>
          refine ⟨x, y, rfl, rfl, ?_⟩
          simpa using h

private theorem optionRealDiv_eq_some
    {oa ob : Option ℝ} {z : ℝ}
    (h : (do
      let x ← oa
      let y ← ob
      if y = 0 then none else some (x / y)) = some z) :
    ∃ x y, oa = some x ∧ ob = some y ∧ y ≠ 0 ∧ x / y = z := by
  cases oa with
  | none => simp at h
  | some x =>
      cases ob with
      | none => simp at h
      | some y =>
          by_cases hy : y = 0
          · simp [hy] at h
          · refine ⟨x, y, rfl, rfl, hy, ?_⟩
            simpa [hy] using h

private theorem optionIntervalDiv_eq_some
    {oa ob : Option RealInterval} {R : RealInterval}
    (h : (do
      let X ← oa
      let Y ← ob
      if hzero : Y.ExcludesZero then some (X.div Y hzero) else none) = some R) :
    ∃ X Y, oa = some X ∧ ob = some Y ∧
      ∃ hzero : Y.ExcludesZero, X.div Y hzero = R := by
  cases oa with
  | none => simp at h
  | some X =>
      cases ob with
      | none => simp at h
      | some Y =>
          by_cases hzero : Y.ExcludesZero
          · refine ⟨X, Y, rfl, rfl, hzero, ?_⟩
            simpa [hzero] using h
          · simp [hzero] at h

/-- Successful interval evaluation encloses successful exact evaluation. -/
theorem evalInterval_sound
    {expr : Expr}
    {realEnv : Array ℝ}
    {intervalEnv : Array RealInterval}
    {value : ℝ}
    {result : RealInterval}
    (henv : EnvironmentsCorrespond realEnv intervalEnv)
    (hreal : evalReal expr realEnv = some value)
    (hint : evalInterval expr intervalEnv = some result) :
    result.Contains value := by
  induction expr generalizing realEnv intervalEnv value result with
  | const c =>
      simp only [evalReal, Option.some.injEq] at hreal
      simp only [evalInterval, Option.some.injEq] at hint
      subst value
      subst result
      exact RealInterval.point_contains c
  | var i =>
      have hi := henv i
      change realEnv[i]? = some value at hreal
      change intervalEnv[i]? = some result at hint
      rw [hreal, hint] at hi
      simpa using hi
  | neg a ih =>
      rcases optionMap_eq_some hreal with ⟨x, hx, hvalue⟩
      rcases optionMap_eq_some hint with ⟨X, hX, hresult⟩
      subst value
      subst result
      exact RealInterval.neg_contains (ih henv hx hX)
  | add a b iha ihb =>
      rcases optionMap₂_eq_some hreal with ⟨x, y, hx, hy, hvalue⟩
      rcases optionMap₂_eq_some hint with ⟨X, Y, hX, hY, hresult⟩
      subst value
      subst result
      exact RealInterval.add_contains (iha henv hx hX) (ihb henv hy hY)
  | sub a b iha ihb =>
      rcases optionMap₂_eq_some hreal with ⟨x, y, hx, hy, hvalue⟩
      rcases optionMap₂_eq_some hint with ⟨X, Y, hX, hY, hresult⟩
      subst value
      subst result
      exact RealInterval.sub_contains (iha henv hx hX) (ihb henv hy hY)
  | mul a b iha ihb =>
      rcases optionMap₂_eq_some hreal with ⟨x, y, hx, hy, hvalue⟩
      rcases optionMap₂_eq_some hint with ⟨X, Y, hX, hY, hresult⟩
      subst value
      subst result
      exact RealInterval.mul_contains (iha henv hx hX) (ihb henv hy hY)
  | div a b iha ihb =>
      rcases optionRealDiv_eq_some hreal with ⟨x, y, hx, hy, _hyzero, hvalue⟩
      rcases optionIntervalDiv_eq_some hint with
        ⟨X, Y, hX, hY, hzero, hresult⟩
      subst value
      subst result
      exact RealInterval.div_contains (iha henv hx hX) (ihb henv hy hY) hzero
  | abs a ih =>
      rcases optionMap_eq_some hreal with ⟨x, hx, hvalue⟩
      rcases optionMap_eq_some hint with ⟨X, hX, hresult⟩
      subst value
      subst result
      exact RealInterval.abs_contains (ih henv hx hX)
  | min a b iha ihb =>
      rcases optionMap₂_eq_some hreal with ⟨x, y, hx, hy, hvalue⟩
      rcases optionMap₂_eq_some hint with ⟨X, Y, hX, hY, hresult⟩
      subst value
      subst result
      exact RealInterval.min_contains (iha henv hx hX) (ihb henv hy hY)
  | max a b iha ihb =>
      rcases optionMap₂_eq_some hreal with ⟨x, y, hx, hy, hvalue⟩
      rcases optionMap₂_eq_some hint with ⟨X, Y, hX, hY, hresult⟩
      subst value
      subst result
      exact RealInterval.max_contains (iha henv hx hX) (ihb henv hy hY)
  | powNat a n ih =>
      rcases optionMap_eq_some hreal with ⟨x, hx, hvalue⟩
      rcases optionMap_eq_some hint with ⟨X, hX, hresult⟩
      subst value
      subst result
      exact RealInterval.powNat_contains (ih henv hx hX) n

end

end SparkInterval
