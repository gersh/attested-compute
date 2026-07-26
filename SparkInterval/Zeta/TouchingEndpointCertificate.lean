/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.EndpointCertificate

/-!
# Strict zero brackets whose endpoints may touch

The Platt--Trudgian zero scan can return consecutive strict sign-change
brackets with a shared, nonzero endpoint.  Such brackets do not have disjoint
*closed* carriers, so they cannot be inserted into `ZeroCertificate`, whose
ordering deliberately requires a strict gap.  Their open interiors are still
disjoint, however, and strict endpoint signs put the selected roots in those
open interiors.

This file supplies that missing bridge.  It checks non-overlap with `<=`,
retains strict endpoint signs, proves that one root can be selected from every
open bracket, and proves those roots are distinct.  It also reproduces the
finite-counting handoff to `ZeroCountUpperBound`.  No zero-simplicity
assumption is used: a resolved stationary cell may be represented by two
touching strict brackets and therefore contributes two distinct interior
roots.

The executable family checker uses exact rationals and ordinary kernel
reduction.  It does not use `native_decide`, an axiom, or `sorry`.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set

/-- Brackets ordered from left to right without interior overlap.  Consecutive
closed carriers may meet at one endpoint. -/
structure TouchingOrderedBrackets (count : Nat) where
  brackets : Fin count -> Bracket
  nonoverlap : forall {i j : Fin count}, i < j ->
    (brackets i).upper <= (brackets j).lower

/-- A non-overlapping bracket family with strict endpoint signs.  Strictness
is essential: it rules out a root at a shared endpoint. -/
structure TouchingZeroCertificate (f : Real -> Real) (count : Nat)
    extends TouchingOrderedBrackets count where
  strictSignChange : forall i, (brackets i).StrictSignChange f

namespace TouchingZeroCertificate

/-- The function is continuous on every closed bracket. -/
def ContinuousOnBrackets {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count) : Prop :=
  forall i, ContinuousOn f (certificate.brackets i).carrier

/-- Every closed bracket is contained in the application domain. -/
def LiesIn {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count) (domain : Set Real) : Prop :=
  forall i, (certificate.brackets i).carrier <= domain

/-- Every zero in the application domain belongs to one certified bracket. -/
def CompleteIn {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count) (domain : Set Real) : Prop :=
  forall x : Real, x ∈ domain -> f x = 0 ->
    exists i, x ∈ (certificate.brackets i).carrier

/-- Strict endpoint signs and continuity produce a zero in every open
bracket, rather than merely in its closed carrier. -/
theorem exists_zero_in_each {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count)
    (hcontinuous : certificate.ContinuousOnBrackets) :
    forall i, ∃ x ∈ Set.Ioo (certificate.brackets i).lower
        (certificate.brackets i).upper, f x = 0 := by
  intro i
  exact Bracket.exists_zero_interior
    (hcontinuous i) (certificate.strictSignChange i)

/-- One selected interior root from every bracket. -/
structure RootSelection {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count) where
  point : Fin count -> Real
  mem_interior : forall i, point i ∈ Set.Ioo
    (certificate.brackets i).lower (certificate.brackets i).upper
  is_zero : forall i, f (point i) = 0
  injective : Function.Injective point

namespace RootSelection

/-- An interior selected root also lies in its closed bracket. -/
theorem mem_carrier {f : Real -> Real} {count : Nat}
    {certificate : TouchingZeroCertificate f count}
    (selection : certificate.RootSelection) (i : Fin count) :
    selection.point i ∈ (certificate.brackets i).carrier :=
  ⟨(selection.mem_interior i).1.le, (selection.mem_interior i).2.le⟩

end RootSelection

/-- A root selection exists.  Its injectivity follows from disjoint open
interiors, even when the corresponding closed brackets touch. -/
theorem exists_rootSelection {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count)
    (hcontinuous : certificate.ContinuousOnBrackets) :
    Nonempty certificate.RootSelection := by
  classical
  choose point hmem hzero using certificate.exists_zero_in_each hcontinuous
  refine ⟨{
    point := point
    mem_interior := hmem
    is_zero := hzero
    injective := ?_
  }⟩
  intro i j heq
  by_contra hne
  rcases lt_or_gt_of_ne hne with hij | hji
  · have hlt : point i < point j :=
      ((hmem i).2.trans_le
        (certificate.toTouchingOrderedBrackets.nonoverlap hij)).trans (hmem j).1
    exact (ne_of_lt hlt) heq
  · have hlt : point j < point i :=
      ((hmem j).2.trans_le
        (certificate.toTouchingOrderedBrackets.nonoverlap hji)).trans (hmem i).1
    exact (ne_of_lt hlt) heq.symm

end TouchingZeroCertificate

namespace TouchingZeroCertificate.RootSelection

/-- Regard every selected bracket root as a zero in the containing domain. -/
def asZeroPoint {f : Real -> Real} {count : Nat}
    {certificate : TouchingZeroCertificate f count}
    (selection : certificate.RootSelection) (domain : Set Real)
    (hlies : certificate.LiesIn domain) : Fin count -> zerosOn f domain :=
  fun i =>
    ⟨selection.point i, hlies i (selection.mem_carrier i), selection.is_zero i⟩

theorem asZeroPoint_injective {f : Real -> Real} {count : Nat}
    {certificate : TouchingZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set Real}
    (hlies : certificate.LiesIn domain) :
    Function.Injective (selection.asZeroPoint domain hlies) := by
  intro i j heq
  apply selection.injective
  exact congrArg Subtype.val heq

/-- Non-overlapping strict brackets give a lower bound on distinct zeros. -/
theorem count_le_zerosOn {f : Real -> Real} {count : Nat}
    {certificate : TouchingZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set Real}
    (hlies : certificate.LiesIn domain)
    (hfinite : (zerosOn f domain).Finite) :
    count <= (zerosOn f domain).ncard := by
  letI := hfinite.fintype
  have hcard := Fintype.card_le_of_injective
    (selection.asZeroPoint domain hlies)
    (selection.asZeroPoint_injective hlies)
  simpa using hcard

/-- A matching Turing-style upper bound gives the exact distinct-root count. -/
theorem exact_count_of_upperBound {f : Real -> Real} {count : Nat}
    {certificate : TouchingZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set Real}
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain count) :
    (zerosOn f domain).ncard = count := by
  exact Nat.le_antisymm hupper.count_le
    (selection.count_le_zerosOn hlies hupper.finite)

/-- A matching upper bound also proves that every domain zero is covered. -/
theorem complete_of_upperBound {f : Real -> Real} {count : Nat}
    {certificate : TouchingZeroCertificate f count}
    (selection : certificate.RootSelection) {domain : Set Real}
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

end TouchingZeroCertificate.RootSelection

/-- The complete result of composing strict touching brackets with a global
distinct-zero upper bound. -/
structure CompleteTouchingZeroCertificate {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count)
    (domain : Set Real) : Prop where
  finiteZeros : (zerosOn f domain).Finite
  exactCount : (zerosOn f domain).ncard = count
  complete : certificate.CompleteIn domain

theorem TouchingZeroCertificate.complete_of_count_upperBound
    {f : Real -> Real} {count : Nat}
    (certificate : TouchingZeroCertificate f count) {domain : Set Real}
    (hcontinuous : certificate.ContinuousOnBrackets)
    (hlies : certificate.LiesIn domain)
    (hupper : ZeroCountUpperBound f domain count) :
    CompleteTouchingZeroCertificate certificate domain := by
  let selection := Classical.choice (certificate.exists_rootSelection hcontinuous)
  exact {
    finiteZeros := hupper.finite
    exactCount := selection.exact_count_of_upperBound hlies hupper
    complete := selection.complete_of_upperBound hlies hupper
  }

/-- Exact-rational endpoint data using the source-permitted `<=` ordering. -/
structure TouchingRationalBracketFamily (count : Nat) where
  entries : Fin count -> RationalBracket

namespace TouchingRationalBracketFamily

def LocallyValid {count : Nat}
    (family : TouchingRationalBracketFamily count) : Prop :=
  forall i, (family.entries i).IsValid

def IsValid {count : Nat}
    (family : TouchingRationalBracketFamily count) : Prop :=
  family.LocallyValid ∧
    forall {i j : Fin count}, i < j ->
      (family.entries i).upper <= (family.entries j).lower

instance {count : Nat} (family : TouchingRationalBracketFamily count) :
    Decidable family.IsValid := by
  unfold IsValid LocallyValid
  infer_instance

/-- The linear-time adjacency condition reflected by `check`. -/
def AdjacentOrdered {count : Nat}
    (family : TouchingRationalBracketFamily count) : Prop :=
  match count with
  | 0 => True
  | n + 1 => forall i : Fin n,
      (family.entries i.castSucc).upper <=
        (family.entries i.succ).lower

def CheckCondition {count : Nat}
    (family : TouchingRationalBracketFamily count) : Prop :=
  family.LocallyValid ∧ family.AdjacentOrdered

instance {count : Nat} (family : TouchingRationalBracketFamily count) :
    Decidable family.CheckCondition := by
  unfold CheckCondition LocallyValid AdjacentOrdered
  split <;> infer_instance

theorem isValid_iff_checkCondition {count : Nat}
    {family : TouchingRationalBracketFamily count} :
    family.IsValid <-> family.CheckCondition := by
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
        have hadjacent : forall i : Fin n,
            (family.entries i.castSucc).upper <=
              (family.entries i.succ).lower := hcheck.2
        have hlower : StrictMono
            (fun i : Fin (n + 1) => (family.entries i).lower) :=
          Fin.strictMono_iff_lt_succ.mpr fun i =>
            ((hcheck.1 i.castSucc).1).trans_le (hadjacent i)
        intro i j hij
        let previous : Fin n := ⟨i.val, by omega⟩
        have hprevious : previous.castSucc = i := by
          apply Fin.ext
          rfl
        have hnext := hadjacent previous
        rw [hprevious] at hnext
        have hnext_le : previous.succ <= j := by
          change previous.val + 1 <= j.val
          dsimp [previous]
          omega
        exact hnext.trans (hlower.monotone hnext_le)

def check {count : Nat}
    (family : TouchingRationalBracketFamily count) : Bool :=
  decide family.CheckCondition

@[simp] theorem check_eq_true {count : Nat}
    {family : TouchingRationalBracketFamily count} :
    family.check = true <-> family.IsValid := by
  rw [isValid_iff_checkCondition]
  simp [check]

@[simp] theorem check_eq_false {count : Nat}
    {family : TouchingRationalBracketFamily count} :
    family.check = false <-> ¬ family.IsValid := by
  constructor
  · intro hfalse hvalid
    have htrue : family.check = true := family.check_eq_true.mpr hvalid
    simp [htrue] at hfalse
  · intro hnot
    cases hcheck : family.check with
    | false => rfl
    | true =>
        exact False.elim (hnot (family.check_eq_true.mp hcheck))

/-- Turn an accepted exact-rational family and evaluator enclosures into the
strict touching zero certificate. -/
theorem exists_touchingZeroCertificate {count : Nat}
    (family : TouchingRationalBracketFamily count)
    {f : Real -> Real}
    (hcheck : family.check = true)
    (hencloses : forall i, (family.entries i).EnclosesEndpoints f) :
    exists certificate : TouchingZeroCertificate f count,
      forall i,
        (certificate.brackets i).lower = (family.entries i).lower ∧
        (certificate.brackets i).upper = (family.entries i).upper := by
  have hvalid : family.IsValid := family.check_eq_true.mp hcheck
  let bracketAt : Fin count -> Bracket := fun i => {
    lower := (family.entries i).lower
    upper := (family.entries i).upper
    lower_lt_upper := by
      exact_mod_cast (hvalid.1 i).1
  }
  let certificate : TouchingZeroCertificate f count := {
    brackets := bracketAt
    nonoverlap := by
      intro i j hij
      change ((family.entries i).upper : Real) <=
        ((family.entries j).lower : Real)
      exact_mod_cast hvalid.2 hij
    strictSignChange := by
      intro i
      simpa [bracketAt, Bracket.StrictSignChange] using
        (family.entries i).strictSignChange (hvalid.1 i) (hencloses i)
  }
  refine ⟨certificate, ?_⟩
  intro i
  exact ⟨rfl, rfl⟩

/-- Continuity supplies one distinct interior root per accepted entry. -/
theorem exists_rootSelection {count : Nat}
    (family : TouchingRationalBracketFamily count)
    {f : Real -> Real}
    (hcheck : family.check = true)
    (hencloses : forall i, (family.entries i).EnclosesEndpoints f)
    (hcontinuous : Continuous f) :
    exists certificate : TouchingZeroCertificate f count,
      Nonempty certificate.RootSelection := by
  obtain ⟨certificate, _hendpoints⟩ :=
    family.exists_touchingZeroCertificate hcheck hencloses
  refine ⟨certificate, certificate.exists_rootSelection ?_⟩
  intro i
  exact hcontinuous.continuousOn

end TouchingRationalBracketFamily

end SparkInterval.Zeta
