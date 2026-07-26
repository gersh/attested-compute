/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiAffineGuards

/-!
# Arithmetic checker for ordered CH25 psi affine children

This module mirrors the small deterministic boundary of
`psi_affine_guard_campaign.py`.  It checks exact source-range chaining,
ordered child indices, additive Q64 state transitions, incoming affine
rectangles, u128 safety, event counters, and the final state.

The checker does not parse JSON or SHA-256, enumerate prime powers, interpret
CRlibm, identify native rows with Lean rows, or authenticate execution.
`RadiusSemantics` makes the missing row/source realization an explicit
parameter.  Conditional on that evidence, `all_radius_safe_of_folds` proves
all endpoint predicates represented by each child's extrema.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.TernaryGoldbach.PsiAffineChildCertificate

open PsiSourceSemantics
open PsiAffineGuards

def sourceLower : Nat := 2
def sourceUpperExclusive : Nat := 10_000_000_000_001
def sourceEventCount : Nat := 346_065_767_406
def sourceShardSpan : Nat := 100_000_000
def sourceShardCount : Nat := 100_000
def u128Limit : Nat := 2 ^ 128
def u128Maximum : Nat := u128Limit - 1

/-- The two directed Q64 endpoints scanned between independent shards. -/
structure State where
  lower : Nat
  upper : Nat
  deriving Repr, DecidableEq

namespace State

def zero : State := ⟨0, 0⟩

def add (left right : State) : State :=
  ⟨left.lower + right.lower, left.upper + right.upper⟩

def Ordered (state : State) : Prop :=
  state.lower ≤ state.upper

def InU128 (state : State) : Prop :=
  state.lower < u128Limit ∧ state.upper < u128Limit

instance (state : State) : Decidable state.Ordered := by
  unfold Ordered
  infer_instance

instance (state : State) : Decidable state.InU128 := by
  unfold InU128
  infer_instance

end State

/-- The independent worker's inclusive rectangle for an incoming state. -/
structure Bounds where
  minimumLowerQ64 : Nat
  maximumUpperQ64 : Nat
  deriving Repr, DecidableEq

namespace Bounds

def WellFormed (bounds : Bounds) : Prop :=
  bounds.minimumLowerQ64 ≤ bounds.maximumUpperQ64

def Contains (bounds : Bounds) (state : State) : Prop :=
  bounds.minimumLowerQ64 ≤ state.lower ∧
    state.lower ≤ state.upper ∧
    state.upper ≤ bounds.maximumUpperQ64

instance (bounds : Bounds) : Decidable bounds.WellFormed := by
  unfold WellFormed
  infer_instance

instance (bounds : Bounds) (state : State) :
    Decidable (bounds.Contains state) := by
  unfold Contains
  infer_instance

end Bounds

/-- One plan-bound child after raw-receipt validation.  Hash commitments stay
in the external wire; this type contains only the arithmetic they bind. -/
structure Child where
  index : Nat
  lower : Nat
  upperExclusive : Nat
  primePowerEvents : Nat
  primeEvents : Nat
  higherPowerEvents : Nat
  delta : State
  bounds : Bounds
  deriving Repr, DecidableEq

namespace Child

def workCount (child : Child) : Nat :=
  child.upperExclusive - child.lower

def WellFormed (child : Child) : Prop :=
  child.lower < child.upperExclusive ∧
    0 < child.primePowerEvents ∧
    child.primePowerEvents ≤ child.workCount ∧
    child.primePowerEvents =
      child.primeEvents + child.higherPowerEvents ∧
    child.delta.Ordered ∧
    child.delta.upper ≤ child.primePowerEvents * 31 * scale ∧
    child.bounds.WellFormed ∧
    child.bounds.maximumUpperQ64 + child.delta.lower < u128Limit ∧
    child.bounds.maximumUpperQ64 + child.delta.upper < u128Limit

instance (child : Child) : Decidable child.WellFormed := by
  unfold WellFormed
  infer_instance

def advance (child : Child) (incoming : State) : State :=
  incoming.add child.delta

end Child

/-- Exact exclusive scan from a fixed root.  The child-supplied state, if any,
is never an input to this relation. -/
def ChainValid (sourceUpper : Nat) :
    Nat → Nat → State → List Child → Prop
  | _, nextLower, _, [] => nextLower = sourceUpper
  | expectedIndex, nextLower, incoming, child :: rest =>
      child.index = expectedIndex ∧
        child.lower = nextLower ∧
        child.WellFormed ∧
        child.bounds.Contains incoming ∧
        (child.advance incoming).InU128 ∧
        ChainValid sourceUpper (expectedIndex + 1)
          child.upperExclusive (child.advance incoming) rest

def foldState : State → List Child → State
  | state, [] => state
  | state, child :: rest => foldState (child.advance state) rest

/-- Compact arithmetic projection of the Python campaign certificate. -/
structure Certificate where
  sourceLower : Nat
  sourceUpperExclusive : Nat
  rootState : State
  finalState : State
  children : List Child
  deriving Repr, DecidableEq

namespace Certificate

def ArithmeticValid (certificate : Certificate) : Prop :=
  certificate.sourceLower < certificate.sourceUpperExclusive ∧
    certificate.rootState = State.zero ∧
    ChainValid certificate.sourceUpperExclusive 0
      certificate.sourceLower certificate.rootState certificate.children ∧
    foldState certificate.rootState certificate.children =
      certificate.finalState

private def chainCheck (sourceUpper : Nat) :
    Nat → Nat → State → List Child → Bool
  | _, nextLower, _, [] => decide (nextLower = sourceUpper)
  | expectedIndex, nextLower, incoming, child :: rest =>
      decide
        (child.index = expectedIndex ∧
          child.lower = nextLower ∧
          child.WellFormed ∧
          child.bounds.Contains incoming ∧
          (child.advance incoming).InU128) &&
        chainCheck sourceUpper (expectedIndex + 1)
          child.upperExclusive (child.advance incoming) rest

private theorem chainCheck_sound
    {sourceUpper expectedIndex nextLower : Nat}
    {incoming : State} {children : List Child}
    (hcheck :
      chainCheck sourceUpper expectedIndex nextLower incoming children =
        true) :
    ChainValid sourceUpper expectedIndex nextLower incoming children := by
  induction children generalizing expectedIndex nextLower incoming with
  | nil =>
      simpa [chainCheck, ChainValid] using hcheck
  | cons child rest inductionHypothesis =>
      simp only [chainCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
      rcases hcheck with
        ⟨⟨hindex, hlower, hwellFormed, hcontains, hu128⟩, hrest⟩
      rw [ChainValid]
      exact
        ⟨hindex, hlower, hwellFormed, hcontains, hu128,
          inductionHypothesis hrest⟩

/-- Kernel-reducible checker for the root, range, rectangle, transition, and
final-state arithmetic. -/
def check (certificate : Certificate) : Bool :=
  decide
      (certificate.sourceLower <
        certificate.sourceUpperExclusive) &&
    decide (certificate.rootState = State.zero) &&
    chainCheck certificate.sourceUpperExclusive 0
      certificate.sourceLower certificate.rootState certificate.children &&
    decide
      (foldState certificate.rootState certificate.children =
        certificate.finalState)

theorem checker_sound {certificate : Certificate}
    (hcheck : certificate.check = true) :
    certificate.ArithmeticValid := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact
    ⟨hcheck.1.1.1, hcheck.1.1.2,
      chainCheck_sound hcheck.1.2, hcheck.2⟩

end Certificate

def sourceShardLower (index : Nat) : Nat :=
  sourceLower + index * sourceShardSpan

def sourceShardUpperExclusive (index : Nat) : Nat :=
  min sourceUpperExclusive
    (sourceLower + (index + 1) * sourceShardSpan)

def SourceGeometryFrom : Nat → List Child → Prop
  | _, [] => True
  | index, child :: rest =>
      child.index = index ∧
        child.lower = sourceShardLower index ∧
        child.upperExclusive = sourceShardUpperExclusive index ∧
        SourceGeometryFrom (index + 1) rest

private def sourceGeometryCheck : Nat → List Child → Bool
  | _, [] => true
  | index, child :: rest =>
      decide
        (child.index = index ∧
          child.lower = sourceShardLower index ∧
          child.upperExclusive = sourceShardUpperExclusive index) &&
        sourceGeometryCheck (index + 1) rest

private theorem sourceGeometryCheck_sound
    {index : Nat} {children : List Child}
    (hcheck : sourceGeometryCheck index children = true) :
    SourceGeometryFrom index children := by
  induction children generalizing index with
  | nil => simp [SourceGeometryFrom]
  | cons child rest inductionHypothesis =>
      simp only [sourceGeometryCheck, Bool.and_eq_true,
        decide_eq_true_eq] at hcheck
      rw [SourceGeometryFrom]
      exact
        ⟨hcheck.1.1, hcheck.1.2.1, hcheck.1.2.2,
          inductionHypothesis hcheck.2⟩

def totalEvents (children : List Child) : Nat :=
  (children.map Child.primePowerEvents).sum

/-- Exact source-specific meaning of the small child-list checker. -/
def SourceValid (certificate : Certificate) : Prop :=
  certificate.ArithmeticValid ∧
    certificate.sourceLower = sourceLower ∧
    certificate.sourceUpperExclusive = sourceUpperExclusive ∧
    certificate.children.length = sourceShardCount ∧
    SourceGeometryFrom 0 certificate.children ∧
    totalEvents certificate.children = sourceEventCount

/-- This total source checker is defined but not evaluated in the repository.
It checks only the compact arithmetic projection, never native rows. -/
def checkSource (certificate : Certificate) : Bool :=
  certificate.check &&
    decide
      (certificate.sourceLower = sourceLower ∧
        certificate.sourceUpperExclusive = sourceUpperExclusive) &&
    decide (certificate.children.length = sourceShardCount) &&
    sourceGeometryCheck 0 certificate.children &&
    decide (totalEvents certificate.children = sourceEventCount)

theorem checkSource_sound {certificate : Certificate}
    (hcheck : checkSource certificate = true) :
    SourceValid certificate := by
  simp only [checkSource, Bool.and_eq_true,
    decide_eq_true_eq] at hcheck
  rcases hcheck with
    ⟨⟨⟨⟨harithmetic, hsource⟩, hlength⟩, hgeometry⟩, hevents⟩
  exact
    ⟨Certificate.checker_sound harithmetic,
      hsource.1, hsource.2, hlength,
      sourceGeometryCheck_sound hgeometry, hevents⟩

/-! ## Explicit row/source realization boundary -/

/-- Full row lists whose max/min folds are claimed by one child.

`rowsRealize` is intentionally supplied by the caller.  A future native
refinement may instantiate it with prime-power roster, directed-log, prefix,
and commitment semantics.  The arithmetic checker above does not construct
this structure. -/
structure RadiusSemantics
    (rowsRealize :
      Child → List LowerRadiusGuard → List UpperRadiusGuard → Prop)
    (child : Child) where
  lowerGuards : List LowerRadiusGuard
  upperGuards : List UpperRadiusGuard
  lowerFold :
    minimumIncoming lowerGuards = child.bounds.minimumLowerQ64
  upperFold :
    maximumIncoming u128Maximum upperGuards =
      child.bounds.maximumUpperQ64
  lowerRadius :
    ∀ guard ∈ lowerGuards, guard.RadiusSafe
  upperBoundary :
    ∀ guard ∈ upperGuards, guard.BoundaryDefined
  upperRadius :
    ∀ guard ∈ upperGuards, guard.RadiusSafe
  rowsRealized : rowsRealize child lowerGuards upperGuards

namespace RadiusSemantics

/-- Once the root-derived input is in the checked rectangle, exact fold and
radius evidence proves every represented lower and upper endpoint guard. -/
theorem all_safe
    {rowsRealize :
      Child → List LowerRadiusGuard → List UpperRadiusGuard → Prop}
    {child : Child} (semantics : RadiusSemantics rowsRealize child)
    {incoming : State} (hcontains : child.bounds.Contains incoming) :
    (∀ guard ∈ semantics.lowerGuards, guard.SafeAt incoming.lower) ∧
      ∀ guard ∈ semantics.upperGuards, guard.SafeAt incoming.upper := by
  apply all_radius_safe_of_folds u128Maximum
  · rw [semantics.lowerFold]
    exact hcontains.1
  · rw [semantics.upperFold]
    exact hcontains.2.2
  · exact semantics.lowerRadius
  · exact semantics.upperBoundary
  · exact semantics.upperRadius

end RadiusSemantics

def RadiusRealized
    (rowsRealize :
      Child → List LowerRadiusGuard → List UpperRadiusGuard → Prop) :
    List Child → Prop
  | [] => True
  | child :: rest =>
      Nonempty (RadiusSemantics rowsRealize child) ∧
        RadiusRealized rowsRealize rest

def SemanticRunSafeFrom
    (rowsRealize :
      Child → List LowerRadiusGuard → List UpperRadiusGuard → Prop) :
    State → List Child → Prop
  | _, [] => True
  | incoming, child :: rest =>
      ∃ semantics : RadiusSemantics rowsRealize child,
        (∀ guard ∈ semantics.lowerGuards,
          guard.SafeAt incoming.lower) ∧
        (∀ guard ∈ semantics.upperGuards,
          guard.SafeAt incoming.upper) ∧
        SemanticRunSafeFrom rowsRealize (child.advance incoming) rest

theorem semanticRunSafe_of_chain
    {rowsRealize :
      Child → List LowerRadiusGuard → List UpperRadiusGuard → Prop}
    {sourceUpper expectedIndex nextLower : Nat}
    {incoming : State} {children : List Child}
    (hchain :
      ChainValid sourceUpper expectedIndex nextLower incoming children)
    (hrealized : RadiusRealized rowsRealize children) :
    SemanticRunSafeFrom rowsRealize incoming children := by
  induction children generalizing expectedIndex nextLower incoming with
  | nil =>
      simp [SemanticRunSafeFrom]
  | cons child rest inductionHypothesis =>
      rw [ChainValid] at hchain
      rw [RadiusRealized] at hrealized
      rcases hchain with
        ⟨_, _, _, hcontains, _, hrest⟩
      rcases hrealized with ⟨⟨semantics⟩, hrestRealized⟩
      have hsafe := semantics.all_safe hcontains
      rw [SemanticRunSafeFrom]
      exact
        ⟨semantics, hsafe.1, hsafe.2,
          inductionHypothesis hrest hrestRealized⟩

/-- The checked child scan composes the conditional row semantics in plan
order.  Its explicit `RadiusRealized` premise is the native-row/source
refinement obligation; the Boolean checker cannot synthesize that premise. -/
theorem Certificate.checked_semantic_run_safe
    {rowsRealize :
      Child → List LowerRadiusGuard → List UpperRadiusGuard → Prop}
    {certificate : Certificate}
    (hcheck : certificate.check = true)
    (hrealized : RadiusRealized rowsRealize certificate.children) :
    SemanticRunSafeFrom rowsRealize certificate.rootState
      certificate.children := by
  rcases Certificate.checker_sound hcheck with
    ⟨_, _, hchain, _⟩
  exact semanticRunSafe_of_chain hchain hrealized

end SparkInterval.TernaryGoldbach.PsiAffineChildCertificate
