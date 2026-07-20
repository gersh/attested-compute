import SparkInterval.Certificate.RatInterval
import SparkInterval.Zeta.ZeroCertificate

/-!
# Executable endpoint-sign certificates

This module is the first executable layer of the zero-isolation path.  A
`RationalBracket` stores rational endpoints together with exact rational
intervals claimed to enclose the real evaluator at those endpoints.  Its
Boolean checker verifies:

* strict endpoint ordering;
* validity of both result intervals; and
* opposite strict signs, with zero excluded by rational comparison.

The checker does not establish that the result intervals enclose a particular
function.  That is the evaluator-specific obligation supplied by a proved
interval algorithm (or by an independently checked full result certificate).
Given those enclosure theorems, `RationalBracketFamily.exists_zeroCertificate`
turns a successful Boolean check into the generic topological certificate from
`ZeroCertificate`.

All comparisons are exact and kernel-reducible; `native_decide` is not used.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open SparkInterval.Certificate

/-- Untrusted wire-level data for one real zero bracket. -/
structure RationalBracket where
  lower : ℚ
  upper : ℚ
  lowerValue : RatInterval
  upperValue : RatInterval
  deriving DecidableEq, Repr

namespace RationalBracket

/-- Exact rational conditions checked for one bracket. -/
def IsValid (bracket : RationalBracket) : Prop :=
  bracket.lower < bracket.upper ∧
    bracket.lowerValue.IsValid ∧
    bracket.upperValue.IsValid ∧
    ((bracket.lowerValue.hi < 0 ∧ 0 < bracket.upperValue.lo) ∨
      (bracket.upperValue.hi < 0 ∧ 0 < bracket.lowerValue.lo))

instance (bracket : RationalBracket) : Decidable bracket.IsValid := by
  unfold IsValid RatInterval.IsValid
  infer_instance

/-- Executable local bracket checker. -/
def check (bracket : RationalBracket) : Bool :=
  decide bracket.IsValid

@[simp] theorem check_eq_true {bracket : RationalBracket} :
    bracket.check = true ↔ bracket.IsValid := by
  simp [check]

@[simp] theorem check_eq_false {bracket : RationalBracket} :
    bracket.check = false ↔ ¬ bracket.IsValid := by
  simp [check]

/-- Evaluator-specific meaning of the two claimed result intervals. -/
def EnclosesEndpoints (bracket : RationalBracket) (f : ℝ → ℝ) : Prop :=
  bracket.lowerValue.ContainsReal (f (bracket.lower : ℝ)) ∧
    bracket.upperValue.ContainsReal (f (bracket.upper : ℝ))

/-- Exact rational sign checks transfer to strict signs of every enclosed real
endpoint value. -/
theorem strictSignChange {bracket : RationalBracket} {f : ℝ → ℝ}
    (hvalid : bracket.IsValid)
    (hencloses : bracket.EnclosesEndpoints f) :
    (f (bracket.lower : ℝ) < 0 ∧ 0 < f (bracket.upper : ℝ)) ∨
      (f (bracket.upper : ℝ) < 0 ∧ 0 < f (bracket.lower : ℝ)) := by
  rcases hvalid.2.2.2 with hsign | hsign
  · left
    constructor
    · have hhi : (bracket.lowerValue.hi : ℝ) < 0 := by
        exact_mod_cast hsign.1
      exact hencloses.1.2.trans_lt hhi
    · have hlo : 0 < (bracket.upperValue.lo : ℝ) := by
        exact_mod_cast hsign.2
      exact hlo.trans_le hencloses.2.1
  · right
    constructor
    · have hhi : (bracket.upperValue.hi : ℝ) < 0 := by
        exact_mod_cast hsign.1
      exact hencloses.2.2.trans_lt hhi
    · have hlo : 0 < (bracket.lowerValue.lo : ℝ) := by
        exact_mod_cast hsign.2
      exact hlo.trans_le hencloses.1.1

end RationalBracket

/-- A fixed-size untrusted family of rational endpoint certificates.  The
family checker uses an all-pairs separation condition matching
`OrderedBrackets`, so its soundness conversion is direct and robust under
parallel/chunked production. -/
structure RationalBracketFamily (count : Nat) where
  entries : Fin count → RationalBracket

namespace RationalBracketFamily

/-- Exact proposition reflected by the family checker. -/
def IsValid {count : Nat} (family : RationalBracketFamily count) : Prop :=
  (∀ i, (family.entries i).IsValid) ∧
    ∀ {i j : Fin count}, i < j →
      (family.entries i).upper < (family.entries j).lower

instance {count : Nat} (family : RationalBracketFamily count) :
    Decidable family.IsValid := by
  unfold IsValid
  infer_instance

/-- Local validity of every bracket. -/
def LocallyValid {count : Nat} (family : RationalBracketFamily count) : Prop :=
  ∀ i, (family.entries i).IsValid

/-- Only consecutive brackets need to be compared by the executable checker.
Together with local nondegeneracy, transitivity implies the all-pairs ordering
used by `IsValid`. -/
def AdjacentOrdered {count : Nat}
    (family : RationalBracketFamily count) : Prop :=
  match count with
  | 0 => True
  | n + 1 => ∀ i : Fin n,
      (family.entries i.castSucc).upper <
        (family.entries i.succ).lower

/-- Linear-comparison condition implemented by `check`. -/
def CheckCondition {count : Nat}
    (family : RationalBracketFamily count) : Prop :=
  family.LocallyValid ∧ family.AdjacentOrdered

instance {count : Nat} (family : RationalBracketFamily count) :
    Decidable family.CheckCondition := by
  unfold CheckCondition LocallyValid AdjacentOrdered
  split <;> infer_instance

/-- Consecutive ordering is logically equivalent to the stronger all-pairs
ordering exported to the generic zero-certificate layer. -/
theorem isValid_iff_checkCondition {count : Nat}
    {family : RationalBracketFamily count} :
    family.IsValid ↔ family.CheckCondition := by
  constructor
  · intro hvalid
    refine ⟨hvalid.1, ?_⟩
    cases count with
    | zero => trivial
    | succ n =>
        intro i
        exact hvalid.2 i.castSucc_lt_succ
  · intro hcheck
    refine ⟨hcheck.1, ?_⟩
    cases count with
    | zero =>
        intro i
        exact Fin.elim0 i
    | succ n =>
        have hadjacent : ∀ i : Fin n,
            (family.entries i.castSucc).upper <
              (family.entries i.succ).lower := hcheck.2
        have hlower : StrictMono
            (fun i : Fin (n + 1) => (family.entries i).lower) :=
          Fin.strictMono_iff_lt_succ.mpr fun i =>
            ((hcheck.1 i.castSucc).1).trans (hadjacent i)
        intro i j hij
        let previous : Fin n := ⟨i.val, by omega⟩
        have hprevious : previous.castSucc = i := by
          apply Fin.ext
          rfl
        have hnext := hadjacent previous
        rw [hprevious] at hnext
        have hnext_le : previous.succ ≤ j := by
          change previous.val + 1 ≤ j.val
          dsimp [previous]
          omega
        exact hnext.trans_le (hlower.monotone hnext_le)

/-- Executable exact-rational check for all local brackets and their global
ordering. -/
def check {count : Nat} (family : RationalBracketFamily count) : Bool :=
  decide family.CheckCondition

@[simp] theorem check_eq_true {count : Nat}
    {family : RationalBracketFamily count} :
    family.check = true ↔ family.IsValid := by
  rw [isValid_iff_checkCondition]
  simp [check]

@[simp] theorem check_eq_false {count : Nat}
    {family : RationalBracketFamily count} :
    family.check = false ↔ ¬ family.IsValid := by
  rw [isValid_iff_checkCondition]
  simp [check]

/-- A successful executable family check plus evaluator-specific endpoint
enclosures constructs the generic ordered sign-change certificate. -/
theorem exists_zeroCertificate {count : Nat}
    (family : RationalBracketFamily count)
    {f : ℝ → ℝ}
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints f) :
    ∃ certificate : ZeroCertificate f count,
      ∀ i,
        (certificate.brackets i).lower = (family.entries i).lower ∧
        (certificate.brackets i).upper = (family.entries i).upper := by
  have hvalid : family.IsValid := family.check_eq_true.mp hcheck
  let bracketAt : Fin count → Bracket := fun i => {
    lower := (family.entries i).lower
    upper := (family.entries i).upper
    lower_lt_upper := by
      exact_mod_cast (hvalid.1 i).1
  }
  let certificate : ZeroCertificate f count := {
    brackets := bracketAt
    separated := by
      intro i j hij
      change ((family.entries i).upper : ℝ) <
        ((family.entries j).lower : ℝ)
      exact_mod_cast hvalid.2 hij
    signChange := by
      intro i
      apply Bracket.StrictSignChange.signChange
      simpa [bracketAt, Bracket.StrictSignChange] using
        (family.entries i).strictSignChange (hvalid.1 i) (hencloses i)
  }
  refine ⟨certificate, ?_⟩
  intro i
  exact ⟨rfl, rfl⟩

/-- Continuity turns an accepted family and sound endpoint enclosures into one
distinct selected root per bracket. -/
theorem exists_rootSelection {count : Nat}
    (family : RationalBracketFamily count)
    {f : ℝ → ℝ}
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints f)
    (hcontinuous : Continuous f) :
    ∃ certificate : ZeroCertificate f count,
      Nonempty certificate.RootSelection := by
  obtain ⟨certificate, _hendpoints⟩ :=
    family.exists_zeroCertificate hcheck hencloses
  refine ⟨certificate, certificate.exists_rootSelection ?_⟩
  intro i
  exact hcontinuous.continuousOn

end RationalBracketFamily

end SparkInterval.Zeta
