import SparkInterval.Zeta.EvenReflectionCertificate

/-! Kernel-reducible tests for positive-only endpoint reflection. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaEvenReflectionCertificate

open SparkInterval.Certificate
open SparkInterval.Zeta

private def evenFunction (x : ℝ) : ℝ := x * x - 4

private theorem evenFunction_even : Function.Even evenFunction := by
  intro x
  simp [evenFunction]

private def positiveBracket : RationalBracket := {
  lower := 1
  upper := 3
  lowerValue := ⟨-3, -3⟩
  upperValue := ⟨5, 5⟩
}

private def positiveFamily : RationalBracketFamily 1 where
  entries _ := positiveBracket

example : positiveFamily.check = true := by decide

example : positiveFamily.reflectPositive.check = true := by decide

example :
    (positiveFamily.reflectPositive.entries (0 : Fin 2)).lower = -3 ∧
    (positiveFamily.reflectPositive.entries (1 : Fin 2)).upper = 3 := by
  decide

private theorem positiveEncloses (index : Fin 1) :
    (positiveFamily.entries index).EnclosesEndpoints evenFunction := by
  fin_cases index
  constructor <;> constructor <;>
    norm_num [positiveFamily, positiveBracket, evenFunction,
      RatInterval.ContainsReal]

theorem reflectedEncloses (index : Fin 2) :
    (positiveFamily.reflectPositive.entries index).EnclosesEndpoints
      evenFunction := by
  exact RationalBracketFamily.reflectPositive_enclosesEndpoints
    evenFunction_even positiveEncloses index

theorem positiveOnlyGivesTwoValidBrackets :
    positiveFamily.reflectPositive.IsValid := by
  apply RationalBracketFamily.reflectPositive_isValid
  · exact RationalBracketFamily.check_eq_true.mp (by decide)
  · intro index
    fin_cases index
    norm_num [positiveFamily, positiveBracket]

#print axioms positiveOnlyGivesTwoValidBrackets
#print axioms reflectedEncloses

end SparkInterval.Tests.ZetaEvenReflectionCertificate
