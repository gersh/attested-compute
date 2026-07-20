import SparkInterval.Zeta.ZeroCertificate

/-! Focused regression tests for the generic real zero-certificate layer. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaZeroCertificate

open Set
open SparkInterval.Zeta

private def twoRootFunction (x : ℝ) : ℝ :=
  (x + 2) * (x - 2)

private def leftBracket : Bracket := {
  lower := (-3 : ℝ)
  upper := (-1 : ℝ)
  lower_lt_upper := by norm_num
}

private def rightBracket : Bracket := {
  lower := (1 : ℝ)
  upper := (3 : ℝ)
  lower_lt_upper := by norm_num
}

private def twoRootCertificate : ZeroCertificate twoRootFunction 2 where
  brackets := ![leftBracket, rightBracket]
  separated := by
    intro i j hij
    fin_cases i <;> fin_cases j <;>
      simp_all [leftBracket, rightBracket]
  signChange := by
    intro i
    fin_cases i
    · exact Or.inr (by norm_num [twoRootFunction, leftBracket])
    · exact Or.inl (by norm_num [twoRootFunction, rightBracket])

private theorem twoRootFunction_continuous : Continuous twoRootFunction := by
  unfold twoRootFunction
  fun_prop

example : twoRootCertificate.ContinuousOnBrackets := by
  intro i
  exact twoRootFunction_continuous.continuousOn

example : Disjoint
    (twoRootCertificate.brackets 0).carrier
    (twoRootCertificate.brackets 1).carrier := by
  exact twoRootCertificate.toOrderedBrackets.carrier_disjoint (by decide)

example : ∃ x ∈ leftBracket.carrier, twoRootFunction x = 0 := by
  apply Bracket.exists_zero
  · exact twoRootFunction_continuous.continuousOn
  · exact Or.inr (by norm_num [twoRootFunction, leftBracket])

example : Nonempty twoRootCertificate.RootSelection := by
  exact twoRootCertificate.exists_rootSelection (by
    intro i
    exact twoRootFunction_continuous.continuousOn)

private def domain : Set ℝ := Set.Icc (-3 : ℝ) (3 : ℝ)

private theorem zerosOn_twoRootFunction :
    zerosOn twoRootFunction domain = ({-2, 2} : Set ℝ) := by
  ext x
  simp only [zerosOn, Set.mem_setOf_eq, Set.mem_insert_iff,
    Set.mem_singleton_iff]
  constructor
  · rintro ⟨_hdomain, hzero⟩
    change (x + 2) * (x - 2) = 0 at hzero
    rcases mul_eq_zero.mp hzero with hleft | hright
    · exact Or.inl (add_eq_zero_iff_eq_neg.mp hleft)
    · exact Or.inr (sub_eq_zero.mp hright)
  · intro hx
    rcases hx with rfl | rfl
    ·
      norm_num [zerosOn, domain, twoRootFunction]
    ·
      norm_num [zerosOn, domain, twoRootFunction]

private theorem twoRootCountUpperBound :
    ZeroCountUpperBound twoRootFunction domain 2 := by
  refine {
    finite := ?_
    count_le := ?_
  }
  · rw [zerosOn_twoRootFunction]
    simp
  · rw [zerosOn_twoRootFunction]
    exact (Set.ncard_pair (by norm_num : (-2 : ℝ) ≠ 2)).le

example : CompleteZeroCertificate twoRootCertificate domain := by
  apply twoRootCertificate.complete_of_count_upperBound
  · intro i
    exact twoRootFunction_continuous.continuousOn
  · intro i x hx
    fin_cases i
    · change (-3 : ℝ) ≤ x ∧ x ≤ -1 at hx
      change (-3 : ℝ) ≤ x ∧ x ≤ 3
      exact ⟨hx.1, hx.2.trans (by norm_num)⟩
    · change (1 : ℝ) ≤ x ∧ x ≤ 3 at hx
      change (-3 : ℝ) ≤ x ∧ x ≤ 3
      exact ⟨(by linarith [hx.1]), hx.2⟩
  · exact twoRootCountUpperBound

end SparkInterval.Tests.ZetaZeroCertificate
