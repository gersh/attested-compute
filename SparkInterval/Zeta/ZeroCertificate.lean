import SparkInterval.Basic

/-!
# Generic certificates for ordered real zero brackets

This file provides the axiom-free topological and finite-counting layer needed
by a future Riemann-zeta zero certificate.  It is deliberately generic in a
real-valued function `f`:

* a `Bracket` is a nondegenerate closed real interval;
* an `OrderedBrackets` family is strictly separated, hence pairwise disjoint;
* endpoint sign changes and continuity certify at least one zero per bracket;
* the resulting zero representatives are injective; and
* an external upper bound on the number of zeros turns those representatives
  into an exact count and a completeness statement.

The last input is where a later formal Turing theorem belongs.  Nothing here
asserts such an upper bound, connects a real auxiliary function to
`riemannZeta`, or handles multiplicities.  `zerosOn` counts distinct real
points only.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set

/-- A nondegenerate closed interval used to isolate a real zero. -/
structure Bracket where
  lower : ℝ
  upper : ℝ
  lower_lt_upper : lower < upper

namespace Bracket

/-- The closed set represented by a bracket. -/
def carrier (bracket : Bracket) : Set ℝ :=
  Set.Icc bracket.lower bracket.upper

/-- Either orientation of a weak endpoint sign change.  Weak inequalities
allow a zero at an endpoint. -/
def SignChange (bracket : Bracket) (f : ℝ → ℝ) : Prop :=
  (f bracket.lower ≤ 0 ∧ 0 ≤ f bracket.upper) ∨
    (f bracket.upper ≤ 0 ∧ 0 ≤ f bracket.lower)

/-- Either orientation of a strict endpoint sign change. -/
def StrictSignChange (bracket : Bracket) (f : ℝ → ℝ) : Prop :=
  (f bracket.lower < 0 ∧ 0 < f bracket.upper) ∨
    (f bracket.upper < 0 ∧ 0 < f bracket.lower)

theorem StrictSignChange.signChange {bracket : Bracket} {f : ℝ → ℝ}
    (hchange : bracket.StrictSignChange f) : bracket.SignChange f := by
  rcases hchange with hchange | hchange
  · exact Or.inl ⟨hchange.1.le, hchange.2.le⟩
  · exact Or.inr ⟨hchange.1.le, hchange.2.le⟩

/-- The intermediate value theorem turns a certified endpoint sign change into
the existence of a zero in the closed bracket. -/
theorem exists_zero {bracket : Bracket} {f : ℝ → ℝ}
    (hcontinuous : ContinuousOn f bracket.carrier)
    (hchange : bracket.SignChange f) :
    ∃ x ∈ bracket.carrier, f x = 0 := by
  rcases hchange with hchange | hchange
  · rcases intermediate_value_Icc bracket.lower_lt_upper.le hcontinuous hchange with
      ⟨x, hx, hzero⟩
    exact ⟨x, hx, hzero⟩
  · rcases intermediate_value_Icc' bracket.lower_lt_upper.le hcontinuous hchange with
      ⟨x, hx, hzero⟩
    exact ⟨x, hx, hzero⟩

/-- Strict endpoint signs put the certified zero in the open bracket. -/
theorem exists_zero_interior {bracket : Bracket} {f : ℝ → ℝ}
    (hcontinuous : ContinuousOn f bracket.carrier)
    (hchange : bracket.StrictSignChange f) :
    ∃ x ∈ Set.Ioo bracket.lower bracket.upper, f x = 0 := by
  obtain ⟨x, hx, hzero⟩ := bracket.exists_zero hcontinuous hchange.signChange
  have hlower_ne : bracket.lower ≠ x := by
    intro heq
    subst x
    rcases hchange with hchange | hchange <;> linarith
  have hupper_ne : x ≠ bracket.upper := by
    intro heq
    subst x
    rcases hchange with hchange | hchange <;> linarith
  exact ⟨x, ⟨lt_of_le_of_ne hx.1 hlower_ne, lt_of_le_of_ne hx.2 hupper_ne⟩, hzero⟩

end Bracket

/-- A finite family of brackets ordered from left to right with a strict gap
between every earlier and later bracket.  The stronger all-pairs field makes
pairwise disjointness available without relying on array indexing or an
adjacency invariant. -/
structure OrderedBrackets (count : Nat) where
  brackets : Fin count → Bracket
  separated : ∀ {i j : Fin count}, i < j →
    (brackets i).upper < (brackets j).lower

namespace OrderedBrackets

/-- Distinct brackets in an ordered family have disjoint closed carriers. -/
theorem carrier_disjoint {count : Nat} (family : OrderedBrackets count)
    {i j : Fin count} (hne : i ≠ j) :
    Disjoint (family.brackets i).carrier (family.brackets j).carrier := by
  rw [Set.disjoint_left]
  intro x hxi hxj
  rcases lt_or_gt_of_ne hne with hij | hji
  · have hxlt : x < (family.brackets j).lower :=
      hxi.2.trans_lt (family.separated hij)
    exact (not_lt_of_ge hxj.1) hxlt
  · have hxlt : x < (family.brackets i).lower :=
      hxj.2.trans_lt (family.separated hji)
    exact (not_lt_of_ge hxi.1) hxlt

end OrderedBrackets

/-- Ordered, pairwise separated brackets carrying certified endpoint sign
changes for `f`.  Continuity is a theorem premise rather than certificate data,
so an application can derive it once for its analytic function. -/
structure ZeroCertificate (f : ℝ → ℝ) (count : Nat)
    extends OrderedBrackets count where
  signChange : ∀ i, (brackets i).SignChange f

namespace ZeroCertificate

/-- The function is continuous on every certified bracket. -/
def ContinuousOnBrackets {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count) : Prop :=
  ∀ i, ContinuousOn f (certificate.brackets i).carrier

/-- Every certified bracket is contained in the application domain. -/
def LiesIn {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count) (domain : Set ℝ) : Prop :=
  ∀ i, (certificate.brackets i).carrier ⊆ domain

/-- Every zero in the application domain belongs to one certified bracket. -/
def CompleteIn {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count) (domain : Set ℝ) : Prop :=
  ∀ x : ℝ, x ∈ domain → f x = 0 →
    ∃ i, x ∈ (certificate.brackets i).carrier

/-- Continuity and the recorded sign changes produce a zero in every bracket. -/
theorem exists_zero_in_each {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count)
    (hcontinuous : certificate.ContinuousOnBrackets) :
    ∀ i, ∃ x ∈ (certificate.brackets i).carrier, f x = 0 := by
  intro i
  exact Bracket.exists_zero (hcontinuous i) (certificate.signChange i)

/-- One chosen zero from every bracket, including the proof that separation
makes those representatives distinct. -/
structure RootSelection {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count) where
  point : Fin count → ℝ
  mem_carrier : ∀ i, point i ∈ (certificate.brackets i).carrier
  is_zero : ∀ i, f (point i) = 0
  injective : Function.Injective point

/-- A zero selection exists for every continuous zero certificate. -/
theorem exists_rootSelection {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count)
    (hcontinuous : certificate.ContinuousOnBrackets) :
    Nonempty certificate.RootSelection := by
  classical
  choose point hmem hzero using certificate.exists_zero_in_each hcontinuous
  refine ⟨{
    point := point
    mem_carrier := hmem
    is_zero := hzero
    injective := ?_
  }⟩
  intro i j heq
  by_contra hne
  have hdisjoint := certificate.toOrderedBrackets.carrier_disjoint hne
  apply (Set.disjoint_left.mp hdisjoint) (hmem i)
  rw [heq]
  exact hmem j

end ZeroCertificate

/-- The distinct real zeros of `f` lying in `domain`.  This set does not encode
analytic multiplicity. -/
def zerosOn (f : ℝ → ℝ) (domain : Set ℝ) : Set ℝ :=
  {x | x ∈ domain ∧ f x = 0}

/-- The abstract output expected from a later Turing-style counting theorem:
finiteness and an upper bound on the number of distinct zeros in a domain. -/
structure ZeroCountUpperBound (f : ℝ → ℝ) (domain : Set ℝ)
    (bound : Nat) : Prop where
  finite : (zerosOn f domain).Finite
  count_le : (zerosOn f domain).ncard ≤ bound

namespace ZeroCertificate.RootSelection

/-- Regard every selected bracket zero as a member of the domain zero set. -/
def asZeroPoint {f : ℝ → ℝ} {count : Nat}
    {certificate : ZeroCertificate f count}
    (selection : certificate.RootSelection) (domain : Set ℝ)
    (hlies : certificate.LiesIn domain) : Fin count → zerosOn f domain :=
  fun i => ⟨selection.point i, hlies i (selection.mem_carrier i), selection.is_zero i⟩

theorem asZeroPoint_injective {f : ℝ → ℝ} {count : Nat}
    {certificate : ZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain) :
    Function.Injective (selection.asZeroPoint domain hlies) := by
  intro i j heq
  apply selection.injective
  exact congrArg Subtype.val heq

/-- Ordered sign-change brackets provide a lower bound on the number of
distinct zeros in any domain containing them. -/
theorem count_le_zerosOn {f : ℝ → ℝ} {count : Nat}
    {certificate : ZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain)
    (hfinite : (zerosOn f domain).Finite) :
    count ≤ (zerosOn f domain).ncard := by
  letI := hfinite.fintype
  have hcard := Fintype.card_le_of_injective
    (selection.asZeroPoint domain hlies)
    (selection.asZeroPoint_injective hlies)
  simpa using hcard

/-- Matching a Turing-style upper bound with the bracket lower bound gives the
exact number of distinct zeros in the domain. -/
theorem exact_count_of_upperBound {f : ℝ → ℝ} {count : Nat}
    {certificate : ZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain count) :
    (zerosOn f domain).ncard = count := by
  exact Nat.le_antisymm hupper.count_le
    (selection.count_le_zerosOn hlies hupper.finite)

/-- If a global zero-count upper bound matches the number of disjoint bracket
zeros, every zero in the domain is covered by one of the brackets. -/
theorem complete_of_upperBound {f : ℝ → ℝ} {count : Nat}
    {certificate : ZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set ℝ}
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain count) :
    certificate.CompleteIn domain := by
  letI := hupper.finite.fintype
  let roots := selection.asZeroPoint domain hlies
  have hcard : Fintype.card (Fin count) = Fintype.card (zerosOn f domain) := by
    rw [Fintype.card_fin, Set.fintypeCard_eq_ncard]
    exact (selection.exact_count_of_upperBound hlies hupper).symm
  have hsurjective : Function.Surjective roots :=
    ((Fintype.bijective_iff_injective_and_card roots).2
      ⟨selection.asZeroPoint_injective hlies, hcard⟩).2
  intro x hdomain hzero
  obtain ⟨i, hi⟩ := hsurjective ⟨x, hdomain, hzero⟩
  refine ⟨i, ?_⟩
  have hpoint : selection.point i = x := congrArg Subtype.val hi
  rw [← hpoint]
  exact selection.mem_carrier i

end ZeroCertificate.RootSelection

/-- Final generic handoff: continuity supplies the bracket lower bound, while
a future Turing theorem supplies the matching global upper bound. -/
structure CompleteZeroCertificate {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count) (domain : Set ℝ) : Prop where
  finiteZeros : (zerosOn f domain).Finite
  exactCount : (zerosOn f domain).ncard = count
  complete : certificate.CompleteIn domain

/-- Compose ordered sign-change brackets with an external zero-count upper
bound.  This theorem is the intended integration point for a future formal
Turing-method result. -/
theorem ZeroCertificate.complete_of_count_upperBound
    {f : ℝ → ℝ} {count : Nat}
    (certificate : ZeroCertificate f count) {domain : Set ℝ}
    (hcontinuous : certificate.ContinuousOnBrackets)
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain count) :
    CompleteZeroCertificate certificate domain := by
  let selection := Classical.choice (certificate.exists_rootSelection hcontinuous)
  exact {
    finiteZeros := hupper.finite
    exactCount := selection.exact_count_of_upperBound hlies hupper
    complete := selection.complete_of_upperBound hlies hupper
  }

end SparkInterval.Zeta
