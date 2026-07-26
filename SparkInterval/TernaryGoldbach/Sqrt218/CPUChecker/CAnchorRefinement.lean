/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CStepRefinement

/-!
# Source-level refinement of the Sqrt218 endpoint anchor

This module closes the source prelude of `tg_sq218_anchor_v2`.  It models:

* the literal `root = 1` search, including both ordered `while` operands,
  the inner `break`, and the `root = next` update;
* the successful call to `tg_reciprocals`; and
* composition with the already-refined checked anchor-arithmetic tail.

The trace is symbolic.  It neither evaluates the production bound nor opens
a production certificate.  Explicit word-fit invariants justify interpreting
the unchecked C multiplication and increment as natural-number operations.
Compiler, ABI, memory, and ISA execution remain separate.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CAnchorRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArithmeticRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPrimitives
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement

/-! ## Literal root-search loop -/

/-- Facts at a successful entry to the body of the root-search `while`.

`divisionGuard` and `squareGuard` are the two operands of the source `&&`,
in evaluation order.  The fit fields expose the invariants needed to read
the unchecked `root * root` and `root + 1` as natural arithmetic. -/
structure CAnchorRootHeadAccepted (bound root : Nat) : Prop where
  rootPositive :
    0 < root
  rootFits :
    root < limbBase
  divisionGuard :
    root ≤ bound / root
  squareFits :
    root * root < limbBase
  squareGuard :
    root * root ≤ bound
  successorFits :
    root + 1 < limbBase

/-- Successful-path trace of the literal loop in `tg_sq218_anchor_v2`.

The `done` constructor is the taken `break` branch.  The `step` constructor
is its negation followed by the exact source assignment `root = root + 1`.
Under the checker's `2 ≤ bound` header guard, every successful anchor call
reaches the reciprocal stage through one of these finite traces; an outer
`while`-guard exit cannot then pass `tg_reciprocals`. -/
inductive CAnchorRootTrace (bound : Nat) : Nat → Nat → Prop where
  | done
      {root : Nat}
      (head : CAnchorRootHeadAccepted bound root)
      (breakGuard : bound / (root + 1) < root + 1) :
      CAnchorRootTrace bound root root
  | step
      {root finalRoot : Nat}
      (head : CAnchorRootHeadAccepted bound root)
      (continueGuard : root + 1 ≤ bound / (root + 1))
      (tail : CAnchorRootTrace bound (root + 1) finalRoot) :
      CAnchorRootTrace bound root finalRoot

theorem CAnchorRootTrace.finalFits
    {bound initial finalRoot : Nat}
    (trace : CAnchorRootTrace bound initial finalRoot) :
    finalRoot < limbBase := by
  induction trace with
  | done head _ => exact head.rootFits
  | step _ _ tail ih => exact ih

/-- The terminal break guard is exactly the successful predicate of
`tg_floor_sqrt_ok`, including the word-maximum exclusion justified by the
unchecked increment's fit invariant. -/
theorem CAnchorRootTrace.finalFloorSqrtOK
    {bound initial finalRoot : Nat}
    (trace : CAnchorRootTrace bound initial finalRoot) :
    cFloorSqrtOK bound finalRoot := by
  induction trace with
  | done head breakGuard =>
      unfold cFloorSqrtOK
      rw [if_neg (Nat.ne_of_gt head.rootPositive)]
      refine ⟨head.divisionGuard, ?_, breakGuard⟩
      intro hmax
      have hsuccessor := head.successorFits
      rw [hmax] at hsuccessor
      have hbase := limbBase_pos
      unfold wordMax at hsuccessor
      omega
  | step _ _ _ ih => exact ih

theorem CAnchorRootTrace.final_eq_sqrt
    {bound initial finalRoot : Nat}
    (trace : CAnchorRootTrace bound initial finalRoot) :
    finalRoot = Nat.sqrt bound :=
  cFloorSqrtOK_eq_sqrt trace.finalFloorSqrtOK

/-! ## Successful reciprocal call and arithmetic tail -/

/-- One successful source path through `tg_sq218_anchor_v2`.

Typed arguments represent the successful non-null branch.  The ignored
`upper_reciprocal` output remains present in `reciprocals`, exactly as in the
C call.  The enclosing validation-control-flow relation records status zero.
-/
structure CAnchorAccepted
    (image : ArchiveImage)
    (state : ScanState)
    (slack : U128)
    (root : Nat)
    (reciprocals : CReciprocals) : Prop where
  rootTrace :
    CAnchorRootTrace image.header.bound 1 root
  reciprocalsRun :
    cReciprocals
        image.header.reciprocalScale
        image.header.bound
        root =
      some reciprocals
  arithmeticRun :
    cAnchorArithmetic
        state.weightedUpper
        state.psiLower
        reciprocals.lower
        root
        image.header.logScale
        image.header.reciprocalScale =
      some slack

theorem CAnchorAccepted.root_eq_sqrt
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    {root : Nat} {reciprocals : CReciprocals}
    (accepted : CAnchorAccepted image state slack root reciprocals) :
    root = Nat.sqrt image.header.bound :=
  accepted.rootTrace.final_eq_sqrt

/-- The lower word written by the successful `tg_reciprocals` call is the
kernel's directed lower reciprocal at the source-computed root. -/
theorem CAnchorAccepted.lower_eq_reciprocalLower
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    {root : Nat} {reciprocals : CReciprocals}
    (accepted : CAnchorAccepted image state slack root reciprocals)
    (hboundFits : image.header.bound < limbBase)
    (hscale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale) :
    reciprocals.lower =
      TGComputeContracts.Sqrt218.reciprocalLower
        image.header.bound root := by
  have hscaleFits :
      image.header.reciprocalScale < limbBase := by
    rw [hscale]
    norm_num [TGComputeContracts.Sqrt218.reciprocalScale, limbBase]
  have hfacts :=
    cReciprocals_facts hscaleFits hboundFits
      accepted.rootTrace.finalFits accepted.reciprocalsRun
  rw [hfacts.lower, hscale]
  rfl

/-- Whole-source composition: root search plus reciprocal computation supply
the exact arguments expected by the already-proved anchor arithmetic tail. -/
theorem CAnchorAccepted.refines_cAnchorArithmetic
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    {root : Nat} {reciprocals : CReciprocals}
    (accepted : CAnchorAccepted image state slack root reciprocals)
    (hboundFits : image.header.bound < limbBase)
    (hscale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale) :
    cAnchorArithmetic
        state.weightedUpper
        state.psiLower
        (TGComputeContracts.Sqrt218.reciprocalLower
          image.header.bound (Nat.sqrt image.header.bound))
        (Nat.sqrt image.header.bound)
        image.header.logScale
        image.header.reciprocalScale =
      some slack := by
  have hroot := accepted.root_eq_sqrt
  have hlower :=
    accepted.lower_eq_reciprocalLower hboundFits hscale
  rw [← hroot, ← hlower]
  exact accepted.arithmeticRun

theorem CAnchorAccepted.implies_IR_anchorSlack
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    {root : Nat} {reciprocals : CReciprocals}
    (accepted : CAnchorAccepted image state slack root reciprocals)
    (hboundFits : image.header.bound < limbBase)
    (hscale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale)
    (hweighted : state.weightedUpper.Valid)
    (hpsi : state.psiLower.Valid) :
    anchorSlack image state = .ok slack :=
  cAnchorArithmetic_implies_IR_anchorSlack hweighted hpsi
    (accepted.refines_cAnchorArithmetic hboundFits hscale)

theorem CAnchorAccepted.implies_anchorOK
    {image : ArchiveImage} {state : ScanState} {slack : U128}
    {root : Nat} {reciprocals : CReciprocals}
    (accepted : CAnchorAccepted image state slack root reciprocals)
    (hheader : headerCheck image = true)
    (hboundFits : image.header.bound < limbBase)
    (hscale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale)
    (hweighted : state.weightedUpper.Valid)
    (hpsi : state.psiLower.Valid) :
    TGComputeContracts.Sqrt218.anchorOK
        image.header.bound
        state.weightedUpper.toNat
        state.psiLower.toNat = true :=
  cAnchorArithmetic_implies_anchorOK hheader hweighted hpsi
    (accepted.refines_cAnchorArithmetic hboundFits hscale)

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CAnchorRefinement
