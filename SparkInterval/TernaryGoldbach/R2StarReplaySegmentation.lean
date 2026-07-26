/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.R2StarSourceSemantics

/-!
# Ordered segmentation of the R2Star arithmetic replay

The native replay may compute bounded row segments concurrently, but its
directed prefix must still consume every row in source order.  This file proves
the arithmetic part of that optimization: folding an ordered list of segments
is exactly the same operation as folding the flattened serial row list.

This theorem does not identify C++ bytes with Lean values and does not supply
`R2StarSourceSemantics.SourceScaleEvidence`.  It isolates the small,
architecture-independent fact needed after a physical replay has established
the ordered segment contents.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.R2StarReplaySegmentation

open R2StarSourceSemantics

/-- Serial directed-state replay of exact row deltas. -/
def foldRows : State → List State → State
  | state, [] => state
  | state, delta :: rest => foldRows (state + delta) rest

/-- Replay already-computed segments in their authenticated source order. -/
def foldSegments : State → List (List State) → State
  | state, [] => state
  | state, rows :: rest => foldSegments (foldRows state rows) rest

@[simp] theorem foldRows_nil (state : State) :
    foldRows state [] = state := rfl

@[simp] theorem foldRows_cons
    (state delta : State) (rest : List State) :
    foldRows state (delta :: rest) =
      foldRows (state + delta) rest := rfl

/-- Splitting a serial replay at any row boundary preserves its state. -/
theorem foldRows_append
    (state : State) (left right : List State) :
    foldRows state (left ++ right) =
      foldRows (foldRows state left) right := by
  induction left generalizing state with
  | nil => rfl
  | cons delta rest inductionHypothesis =>
      simpa only [List.cons_append, foldRows_cons] using
        inductionHypothesis (state + delta)

/-- Ordered segment replay is definitionally independent of the grouping. -/
theorem foldSegments_eq_foldRows_flatten
    (state : State) (segments : List (List State)) :
    foldSegments state segments =
      foldRows state segments.flatten := by
  induction segments generalizing state with
  | nil => rfl
  | cons rows rest inductionHypothesis =>
      simp only [foldSegments, List.flatten_cons, foldRows_append]
      exact inductionHypothesis (foldRows state rows)

/-- Two exact ordered partitions of the same row list have the same terminal
directed state. -/
theorem foldSegments_eq_of_flatten_eq
    (state : State) {left right : List (List State)}
    (hrows : left.flatten = right.flatten) :
    foldSegments state left = foldSegments state right := by
  rw [foldSegments_eq_foldRows_flatten,
    foldSegments_eq_foldRows_flatten, hrows]

end SparkInterval.TernaryGoldbach.R2StarReplaySegmentation
