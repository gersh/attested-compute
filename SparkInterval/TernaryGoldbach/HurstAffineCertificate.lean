/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Int.Basic

/-!
# Exact arithmetic interface for Hurst affine-shard certificates

This module checks only the small arithmetic certificate assembled from Hurst
shard receipts.  A state has the four coordinates emitted by the C++ adapter:
Mertens `M`, squarefree count `Q`, and the lower and upper Q96 enclosures of
the little-Mertens sum.  Every block carries an exact additive delta and an
incoming-state guard.  The checker verifies range chaining, delta shape,
guard membership at every derived prefix state, and the final state.

The physical edge is deliberately separate.  The original
`ExternalBlockRealization` asks a guard to prove one combined row predicate;
it is retained as a compatibility API.  In particular, it must not be
instantiated with a predicate asserting an exact global prefix for *every*
state in a broad affine guard.

`ReplayBlockRealization` is the production-shaped interface.  It separately
attests primitive row deltas and local arithmetic safety after replaying those
deltas from a guard-admissible incoming state.  `ReplaySourceScaleEvidence`
adds literal coverage of `[1, 10^16 + 1)` and the initial zero state.
Source-specific ordinary Lean theorems can then identify the actual checked
chain with global prefix functions.  None of these propositions is produced
by `check`, and this file declares no axiom asserting one.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstAffineCertificate

/-- Exact four-coordinate prefix state used by the Hurst runner. -/
structure State where
  mertens : Int
  squarefree : Int
  littleLowerQ96 : Int
  littleUpperQ96 : Int
  deriving Repr, DecidableEq

namespace State

def zero : State := ⟨0, 0, 0, 0⟩

def add (left right : State) : State :=
  ⟨left.mertens + right.mertens,
   left.squarefree + right.squarefree,
   left.littleLowerQ96 + right.littleLowerQ96,
   left.littleUpperQ96 + right.littleUpperQ96⟩

instance : Add State := ⟨add⟩

@[simp] theorem add_mertens (left right : State) :
    (left + right).mertens = left.mertens + right.mertens := rfl

@[simp] theorem add_squarefree (left right : State) :
    (left + right).squarefree = left.squarefree + right.squarefree := rfl

@[simp] theorem add_littleLowerQ96 (left right : State) :
    (left + right).littleLowerQ96 =
      left.littleLowerQ96 + right.littleLowerQ96 := rfl

@[simp] theorem add_littleUpperQ96 (left right : State) :
    (left + right).littleUpperQ96 =
      left.littleUpperQ96 + right.littleUpperQ96 := rfl

@[simp] theorem zero_add (state : State) : zero + state = state := by
  rcases state with ⟨mertens, squarefree, littleLower, littleUpper⟩
  change
    State.mk (0 + mertens) (0 + squarefree)
        (0 + littleLower) (0 + littleUpper) =
      State.mk mertens squarefree littleLower littleUpper
  simp

@[simp] theorem add_zero (state : State) : state + zero = state := by
  rcases state with ⟨mertens, squarefree, littleLower, littleUpper⟩
  change
    State.mk (mertens + 0) (squarefree + 0)
        (littleLower + 0) (littleUpper + 0) =
      State.mk mertens squarefree littleLower littleUpper
  simp

theorem add_assoc (first second third : State) :
    first + second + third = first + (second + third) := by
  rcases first with ⟨mertens₁, squarefree₁, lower₁, upper₁⟩
  rcases second with ⟨mertens₂, squarefree₂, lower₂, upper₂⟩
  rcases third with ⟨mertens₃, squarefree₃, lower₃, upper₃⟩
  change
    State.mk ((mertens₁ + mertens₂) + mertens₃)
        ((squarefree₁ + squarefree₂) + squarefree₃)
        ((lower₁ + lower₂) + lower₃)
        ((upper₁ + upper₂) + upper₃) =
      State.mk (mertens₁ + (mertens₂ + mertens₃))
        (squarefree₁ + (squarefree₂ + squarefree₃))
        (lower₁ + (lower₂ + lower₃))
        (upper₁ + (upper₂ + upper₃))
  simp only [Int.add_assoc]

end State

/-- Componentwise closed interval for one block's incoming prefix state. -/
structure Guard where
  lower : State
  upper : State
  deriving Repr, DecidableEq

namespace Guard

def WellFormed (guard : Guard) : Prop :=
  guard.lower.mertens ≤ guard.upper.mertens ∧
  guard.lower.squarefree ≤ guard.upper.squarefree ∧
  guard.lower.littleLowerQ96 ≤ guard.upper.littleLowerQ96 ∧
  guard.lower.littleUpperQ96 ≤ guard.upper.littleUpperQ96

def Contains (guard : Guard) (state : State) : Prop :=
  guard.lower.mertens ≤ state.mertens ∧
  state.mertens ≤ guard.upper.mertens ∧
  guard.lower.squarefree ≤ state.squarefree ∧
  state.squarefree ≤ guard.upper.squarefree ∧
  guard.lower.littleLowerQ96 ≤ state.littleLowerQ96 ∧
  state.littleLowerQ96 ≤ guard.upper.littleLowerQ96 ∧
  guard.lower.littleUpperQ96 ≤ state.littleUpperQ96 ∧
  state.littleUpperQ96 ≤ guard.upper.littleUpperQ96

instance instDecidableWellFormed (guard : Guard) :
    Decidable guard.WellFormed := by
  unfold WellFormed
  infer_instance

instance instDecidableContains (guard : Guard) (state : State) :
    Decidable (guard.Contains state) := by
  unfold Contains
  infer_instance

end Guard

/-- One half-open source block with its exact additive transition. -/
structure Block where
  lower : Nat
  upper : Nat
  delta : State
  guard : Guard
  deriving Repr, DecidableEq

namespace Block

def rowCount (block : Block) : Nat := block.upper - block.lower

/-- Cheap source-independent consistency conditions also enforced by the
Python campaign supervisor. -/
def WellFormed (block : Block) : Prop :=
  block.lower < block.upper ∧
  -(block.rowCount : Int) ≤ block.delta.mertens ∧
  block.delta.mertens ≤ (block.rowCount : Int) ∧
  0 ≤ block.delta.squarefree ∧
  block.delta.squarefree ≤ (block.rowCount : Int) ∧
  block.delta.littleLowerQ96 ≤ block.delta.littleUpperQ96 ∧
  block.guard.WellFormed

instance instDecidableWellFormed (block : Block) :
    Decidable block.WellFormed := by
  unfold WellFormed
  infer_instance

/-- Exact affine transition at a block boundary. -/
def advance (block : Block) (incoming : State) : State :=
  incoming + block.delta

end Block

/-- Fold exact block deltas from one boundary state. -/
def foldState : State → List Block → State
  | state, [] => state
  | state, block :: rest => foldState (block.advance state) rest

/-- Folding adjacent shard batches in two stages is exactly the same as
folding their concatenation.  This is the arithmetic merge law used by a
distributed supervisor; it does not permit reordering guards or blocks. -/
@[simp] theorem foldState_append (state : State) (left right : List Block) :
    foldState state (left ++ right) =
      foldState (foldState state left) right := by
  induction left generalizing state with
  | nil => rfl
  | cons block rest inductionHypothesis =>
      simp only [List.cons_append, foldState]
      exact inductionHypothesis (block.advance state)

/-- Two routes with the same ordered delta vector have the same terminal
state.  Range coverage and guard acceptance remain separate `ChainValid`
obligations, so this theorem cannot justify an omitted or reordered shard. -/
theorem foldState_eq_of_map_delta_eq
    (state : State) {left right : List Block}
    (hdeltas : left.map Block.delta = right.map Block.delta) :
    foldState state left = foldState state right := by
  induction left generalizing state right with
  | nil =>
      cases right with
      | nil => rfl
      | cons block rest => simp at hdeltas
  | cons leftBlock leftRest inductionHypothesis =>
      cases right with
      | nil => simp at hdeltas
      | cons rightBlock rightRest =>
          simp only [List.map_cons, List.cons.injEq] at hdeltas
          rcases hdeltas with ⟨hdelta, hrest⟩
          simp only [foldState, Block.advance]
          rw [hdelta]
          exact inductionHypothesis (state + rightBlock.delta) hrest

/-- Range, guard, and prefix-state semantics for an ordered block list. -/
def ChainValid (sourceUpper : Nat) : Nat → State → List Block → Prop
  | nextLower, _, [] => nextLower = sourceUpper
  | nextLower, incoming, block :: rest =>
      block.lower = nextLower ∧
      block.WellFormed ∧
      block.guard.Contains incoming ∧
      ChainValid sourceUpper block.upper (block.advance incoming) rest

/-- Small arithmetic certificate.  Hash parsing and physical execution are
intentionally not fields of this type. -/
structure Certificate where
  sourceLower : Nat
  sourceUpper : Nat
  rootState : State
  finalState : State
  blocks : List Block
  deriving Repr, DecidableEq

namespace Certificate

def ArithmeticValid (certificate : Certificate) : Prop :=
  certificate.sourceLower < certificate.sourceUpper ∧
  ChainValid certificate.sourceUpper certificate.sourceLower
    certificate.rootState certificate.blocks ∧
  foldState certificate.rootState certificate.blocks = certificate.finalState

private def chainCheck (sourceUpper : Nat) : Nat → State → List Block → Bool
  | nextLower, _, [] => decide (nextLower = sourceUpper)
  | nextLower, incoming, block :: rest =>
      decide (block.lower = nextLower ∧ block.WellFormed ∧
        block.guard.Contains incoming) &&
      chainCheck sourceUpper block.upper (block.advance incoming) rest

private theorem chainCheck_sound
    {sourceUpper nextLower : Nat} {incoming : State} {blocks : List Block}
    (hcheck : chainCheck sourceUpper nextLower incoming blocks = true) :
    ChainValid sourceUpper nextLower incoming blocks := by
  induction blocks generalizing nextLower incoming with
  | nil => simpa [chainCheck, ChainValid] using hcheck
  | cons block rest inductionHypothesis =>
      simp only [chainCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
      rcases hcheck with ⟨⟨hlower, hwellFormed, hguard⟩, hrest⟩
      rw [ChainValid]
      exact ⟨hlower, hwellFormed, hguard, inductionHypothesis hrest⟩

/-- Kernel-reducible checker for the complete arithmetic certificate. -/
def check (certificate : Certificate) : Bool :=
  decide (certificate.sourceLower < certificate.sourceUpper) &&
    (chainCheck certificate.sourceUpper certificate.sourceLower
      certificate.rootState certificate.blocks &&
    decide (foldState certificate.rootState certificate.blocks =
      certificate.finalState))

/-- The executable checker proves exactly the range, prefix, guard, and final
state proposition above.  It says nothing about who produced the deltas. -/
theorem checker_sound {certificate : Certificate}
    (hcheck : certificate.check = true) : certificate.ArithmeticValid := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, chainCheck_sound hcheck.2.1, hcheck.2.2⟩

end Certificate

/-! ## Explicit physical/source-scale boundary -/

/-- External meaning of one block.  `prefixBefore n` is the exact local state
before row `n`; the recurrence and `totalDelta` bind those rows to the compact
block transition.  `rowSafe` is the source-specific analytic check.  The Lean
arithmetic checker does not construct this structure. -/
structure ExternalBlockRealization
    (rowPredicate : Nat → State → Prop) (block : Block) where
  rowDelta : Nat → State
  prefixBefore : Nat → State
  prefixAtLower : prefixBefore block.lower = State.zero
  prefixStep : ∀ n, block.lower ≤ n → n < block.upper →
    prefixBefore (n + 1) = prefixBefore n + rowDelta n
  totalDelta : prefixBefore block.upper = block.delta
  rowSafe : ∀ incoming, block.guard.Contains incoming →
    ∀ n, block.lower ≤ n → n < block.upper →
      rowPredicate n (incoming + prefixBefore (n + 1))

/-- Replay-shaped meaning of one block.

`rowDeltaValid` describes one primitive source row independently of any
incoming prefix.  `rowSafe` records only the local finite guard decision at
the replayed state.  Neither field may assert that an arbitrary
guard-admissible incoming state is the unique global source prefix. -/
structure ReplayBlockRealization
    (rowDeltaPredicate rowSafePredicate : Nat → State → Prop)
    (block : Block) where
  rowDelta : Nat → State
  prefixBefore : Nat → State
  prefixAtLower : prefixBefore block.lower = State.zero
  prefixStep : ∀ n, block.lower ≤ n → n < block.upper →
    prefixBefore (n + 1) = prefixBefore n + rowDelta n
  totalDelta : prefixBefore block.upper = block.delta
  rowDeltaValid : ∀ n, block.lower ≤ n → n < block.upper →
    rowDeltaPredicate n (rowDelta n)
  rowSafe : ∀ incoming, block.guard.Contains incoming →
    ∀ n, block.lower ≤ n → n < block.upper →
      rowSafePredicate n (incoming + prefixBefore (n + 1))

/-- Recursive conclusion obtained when every checked arithmetic block is also
supplied with its separate physical realization. -/
def PhysicalRunSafeFrom (rowPredicate : Nat → State → Prop) :
    State → List Block → Prop
  | _, [] => True
  | incoming, block :: rest =>
      ∃ evidence : ExternalBlockRealization rowPredicate block,
        block.guard.Contains incoming ∧
        (∀ n, block.lower ≤ n → n < block.upper →
          rowPredicate n (incoming + evidence.prefixBefore (n + 1))) ∧
        PhysicalRunSafeFrom rowPredicate (block.advance incoming) rest

/-- A source row is covered by one block of the ordered chain, with the exact
incoming prefix state for that block and a physical realization witnessing the
local recurrence.  This proposition is intentionally existential in the
physical evidence: the small arithmetic checker orders and composes block
states, while the closed registered execution supplies each block's row-level
realization. -/
def RowSafeWitnessFrom (rowPredicate : Nat → State → Prop) :
    State → List Block → Nat → Prop
  | _, [], _ => False
  | incoming, block :: rest, n =>
      (∃ evidence : ExternalBlockRealization rowPredicate block,
        block.lower ≤ n ∧ n < block.upper ∧
          rowPredicate n (incoming + evidence.prefixBefore (n + 1))) ∨
      RowSafeWitnessFrom rowPredicate (block.advance incoming) rest n

private theorem chainValid_physicalRunSafeFrom
    {rowPredicate : Nat → State → Prop}
    {sourceUpper nextLower : Nat} {incoming : State} {blocks : List Block}
    (hchain : ChainValid sourceUpper nextLower incoming blocks)
    (hphysical : ∀ block, block ∈ blocks →
      ExternalBlockRealization rowPredicate block) :
    PhysicalRunSafeFrom rowPredicate incoming blocks := by
  induction blocks generalizing nextLower incoming with
  | nil => simp [PhysicalRunSafeFrom]
  | cons block rest inductionHypothesis =>
      rw [ChainValid] at hchain
      rcases hchain with ⟨_, _, hguard, hrest⟩
      have evidence := hphysical block (by simp)
      simp only [PhysicalRunSafeFrom]
      refine ⟨evidence, hguard, evidence.rowSafe incoming hguard, ?_⟩
      apply inductionHypothesis hrest
      intro tailBlock hmem
      exact hphysical tailBlock (by simp [hmem])

private theorem chainValid_rowSafeWitnessFrom
    {rowPredicate : Nat → State → Prop}
    {sourceUpper nextLower : Nat} {incoming : State} {blocks : List Block}
    (hchain : ChainValid sourceUpper nextLower incoming blocks)
    (hphysical : ∀ block, block ∈ blocks →
      ExternalBlockRealization rowPredicate block) :
    ∀ n, nextLower ≤ n → n < sourceUpper →
      RowSafeWitnessFrom rowPredicate incoming blocks n := by
  induction blocks generalizing nextLower incoming with
  | nil =>
      intro n hnLower hnUpper
      simp only [ChainValid] at hchain
      omega
  | cons block rest inductionHypothesis =>
      rw [ChainValid] at hchain
      rcases hchain with ⟨hlower, _, hguard, hrest⟩
      intro n hnLower hnUpper
      rw [RowSafeWitnessFrom]
      by_cases hnBlock : n < block.upper
      · left
        let evidence := hphysical block (by simp)
        refine ⟨evidence, ?_, hnBlock, ?_⟩
        · simpa [hlower] using hnLower
        · exact evidence.rowSafe incoming hguard n
            (by simpa [hlower] using hnLower) hnBlock
      · right
        refine inductionHypothesis hrest ?_ n ?_ hnUpper
        · intro tailBlock hmem
          exact hphysical tailBlock (by simp [hmem])
        · omega

/-- Arithmetic checking plus an explicit physical premise yields the recursive
row-safety conclusion.  The physical premise remains visible to callers. -/
theorem checked_physical_run_sound
    {certificate : Certificate} {rowPredicate : Nat → State → Prop}
    (hcheck : certificate.check = true)
    (hphysical : ∀ block, block ∈ certificate.blocks →
      ExternalBlockRealization rowPredicate block) :
    PhysicalRunSafeFrom rowPredicate certificate.rootState
      certificate.blocks := by
  have hvalid := Certificate.checker_sound hcheck
  exact chainValid_physicalRunSafeFrom hvalid.2.1 hphysical

def sourceUpperExclusive : Nat := 10_000_000_000_000_001

/-- Literal source geometry is deliberately outside `Certificate.check`. -/
def Certificate.FullSourceRange (certificate : Certificate) : Prop :=
  certificate.sourceLower = 1 ∧
  certificate.sourceUpper = sourceUpperExclusive

instance Certificate.instDecidableFullSourceRange
    (certificate : Certificate) : Decidable certificate.FullSourceRange := by
  unfold Certificate.FullSourceRange
  infer_instance

/-- Older global-predicate physical interface retained for compatibility.

New registered campaigns should use `ReplaySourceScaleEvidence`.  In
particular, instantiating `rowPredicate` with a unique global-prefix assertion
would force that assertion for every state in an incoming affine guard. -/
structure SourceScaleEvidence
    (rowPredicate : Nat → State → Prop) (certificate : Certificate) where
  fullRange : certificate.FullSourceRange
  physical : ∀ block, block ∈ certificate.blocks →
    ExternalBlockRealization rowPredicate block

/-- Narrow production evidence for a complete replay-shaped campaign.

The root state is fixed to zero rather than being identified with a global
source function.  Global prefix semantics must be derived from
`rowDeltaPredicate` along the one actual checked chain. -/
structure ReplaySourceScaleEvidence
    (rowDeltaPredicate rowSafePredicate : Nat → State → Prop)
    (certificate : Certificate) where
  fullRange : certificate.FullSourceRange
  rootZero : certificate.rootState = State.zero
  physical : ∀ block, block ∈ certificate.blocks →
    ReplayBlockRealization rowDeltaPredicate rowSafePredicate block

/-- Compatibility wrapper for the older global-predicate evidence.  The
registered Hurst route uses the replay-shaped interface instead. -/
theorem checked_source_scale_sound
    {certificate : Certificate} {rowPredicate : Nat → State → Prop}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence rowPredicate certificate) :
    certificate.FullSourceRange ∧
      PhysicalRunSafeFrom rowPredicate certificate.rootState
        certificate.blocks := by
  exact ⟨evidence.fullRange,
    checked_physical_run_sound hcheck evidence.physical⟩

/-- A checked literal source-scale campaign covers every row in its half-open
source range.  Unlike `checked_source_scale_sound`, whose recursive conclusion
is convenient for induction over blocks, this theorem exposes the pointwise
form needed by source-facing residual theorems.  The physical premise remains
explicit in `evidence`; no fabricated arithmetic certificate can create it. -/
theorem checked_source_rows_sound
    {certificate : Certificate} {rowPredicate : Nat → State → Prop}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence rowPredicate certificate) :
    ∀ n, certificate.sourceLower ≤ n → n < certificate.sourceUpper →
      RowSafeWitnessFrom rowPredicate certificate.rootState
        certificate.blocks n := by
  have hvalid := Certificate.checker_sound hcheck
  exact chainValid_rowSafeWitnessFrom hvalid.2.1 evidence.physical

/-- Literal specialization used by the four shared ternary-Goldbach atoms.
The source-scale evidence fixes the checked half-open range to
`[1, 10^16 + 1)`, so every natural endpoint through `10^16` receives an exact
row-safety witness. -/
theorem checked_full_source_rows_sound
    {certificate : Certificate} {rowPredicate : Nat → State → Prop}
    (hcheck : certificate.check = true)
    (evidence : SourceScaleEvidence rowPredicate certificate) :
    ∀ n, 1 ≤ n → n ≤ 10_000_000_000_000_000 →
      RowSafeWitnessFrom rowPredicate certificate.rootState
        certificate.blocks n := by
  intro n hnLower hnUpper
  apply checked_source_rows_sound hcheck evidence n
  · simpa [evidence.fullRange.1] using hnLower
  · rw [evidence.fullRange.2]
    simp only [sourceUpperExclusive]
    omega

end SparkInterval.TernaryGoldbach.HurstAffineCertificate
