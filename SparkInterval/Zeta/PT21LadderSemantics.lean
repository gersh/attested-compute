/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.LSeries.ZetaZeros
import SparkInterval.Zeta.PT21Ladder

/-!
# What a checked PT21 ladder proves about `riemannZeta`

`SparkInterval.Zeta.PT21Ladder` is pure finite arithmetic.  This module
states exactly what that arithmetic buys, and exactly what it does not.

Two independent things travel up the ladder.

* **Coverage.**  Consecutive block indices mean consecutive height
  intervals with no gap.  If each block's own certificate proves that
  every zeta zero with ordinate in `(a_k, b_k]` lies on the critical line,
  then the ladder's gap-freeness upgrades that to the whole scanned range.
  This direction needs *no* count at all -- only that the intervals
  tile.  It is proved here as `criticalLine_of_blocks`.

* **Counting.**  If an external count function `N` agrees with each
  window's two advertised endpoint counts, the ladder telescopes it:
  `N(end) = N(start) + (total slots)`.  This is `count_telescopes`.  It is
  the statement that lets a Turing/argument-principle bound at the two
  campaign endpoints be reconciled with a slot total accumulated over
  three billion blocks.

The composition `sourceClaim_of_ladder` produces the exact
Platt--Trudgian source proposition (the same statement as
`SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.SourceClaim`) from
two visible premises: an LMFDB-derived prefix claim below `10^10`, and one
per-block claim for each of the `2966443783` blocks.

## The honest accounting

Nothing here reduces the number of blocks that must be verified.  The
ladder does not make `2966443783` block claims cheaper to *establish*; it
makes them cheap to *combine*.  The per-block premise
`BlockCriticalLine k` is discharged, block by block, by
`PT21ArtifactBinding.BlockArtifact` plus its analytic realizations -- and
at source scale that discharge happens in a compiled checker under
attestation, not in the Lean kernel.  What the ladder removes is the
`1.24e13`-item *aggregation* cost, not the `1.24e13`-item *production*
cost.

This module imports Mathlib's zeta-zero file and the ladder.  It contains
no axiom, `sorry`, or `native_decide`.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.Zeta.PT21Ladder

/-- The exact Platt--Trudgian source height. -/
def sourceHeight : ℝ := 3_000_175_332_800

/-- Per-block conclusion imported from the block-artifact layer: every zeta
zero in the open critical strip whose ordinate lies in the half-open block
`(a_k, b_k]` is on the critical line.

The half-open convention is what makes consecutive blocks tile without
double-counting a shared endpoint. -/
def BlockCriticalLine (block : Nat) : Prop :=
  ∀ s : ℂ, riemannZeta s = 0 → 0 < s.re → s.re < 1 →
    (blockLower block : ℝ) < s.im → s.im ≤ (blockLower (block + 1) : ℝ) →
      s.re = (1 : ℝ) / 2

/-- **Coverage.**  Gap-free consecutive blocks compose.  No count appears:
this is purely the statement that the half-open blocks
`(a_first, a_first+1], ..., (a_{first+n-1}, a_{first+n}]` tile
`(a_first, a_{first+n}]`. -/
theorem criticalLine_of_blocks (first : Nat) :
    ∀ n : Nat,
      (∀ k : Nat, first ≤ k → k < first + n → BlockCriticalLine k) →
        ∀ s : ℂ, riemannZeta s = 0 → 0 < s.re → s.re < 1 →
          (blockLower first : ℝ) < s.im →
          s.im ≤ (blockLower (first + n) : ℝ) →
            s.re = (1 : ℝ) / 2 := by
  intro n
  induction n with
  | zero =>
      intro _hblocks s _hzero _hre0 _hre1 hlow hhigh
      exact absurd hlow (by simpa using not_lt.mpr hhigh)
  | succ m induction =>
      intro hblocks s hzero hre0 hre1 hlow hhigh
      by_cases hcase : s.im ≤ (blockLower (first + m) : ℝ)
      · exact induction
          (fun k hlower hupper => hblocks k hlower (by omega))
          s hzero hre0 hre1 hlow hcase
      · exact hblocks (first + m) (by omega) (by omega)
          s hzero hre0 hre1 (lt_of_not_ge hcase) hhigh

/-- **Counting.**  A checked window run telescopes any count function that
agrees with the windows' advertised endpoint counts. -/
theorem count_telescopes (N : Nat → Nat) :
    ∀ (block count : Nat) (windows : List WindowSummary),
      WindowChainValid block count windows →
      (∀ window ∈ windows,
        N window.block = window.lowerCount ∧
          N (window.block + 1) = window.upperCount) →
      N block = count →
        N (block + windows.length) = count + slotSum windows := by
  intro block count windows
  induction windows generalizing block count with
  | nil => intro _ _ hstart; simpa using hstart
  | cons window rest induction =>
      rintro ⟨hblock, hcount, hclosed, htail⟩ hmatch _hstart
      obtain ⟨_hleft, hright⟩ := hmatch window List.mem_cons_self
      have hnext : N (block + 1) = window.upperCount := by
        rw [← hblock]; exact hright
      have := induction (block + 1) window.upperCount htail
        (fun w hw => hmatch w (List.mem_cons_of_mem _ hw)) hnext
      unfold WindowSummary.Closed at hclosed
      simp only [List.length_cons, slotSum_cons]
      have hindex : block + (rest.length + 1) = block + 1 + rest.length := by
        omega
      rw [hindex, this]
      omega

/-- The exact Platt--Trudgian source proposition. -/
def SourceClaim : Prop :=
  ∀ s : ℂ, riemannZeta s = 0 →
    0 < s.re → s.re < 1 →
    0 < s.im → s.im ≤ sourceHeight →
    s.re = (1 : ℝ) / 2

theorem sourceLower_lt_sourceHeight :
    ((sourceLower : Nat) : ℝ) < sourceHeight := by
  unfold sourceLower sourceHeight
  norm_num

theorem sourceHeight_le_endpoint :
    sourceHeight ≤ ((blockLower sourceBlockCount : Nat) : ℝ) := by
  rw [source_endpoint_height]
  unfold sourceHeight
  norm_num

/-- **The composition.**  An LMFDB-derived prefix claim below `10^10` plus
one per-block claim for every source block gives the exact source
proposition.

Both premises are deliberately visible.  The prefix premise is discharged
by the public zero file (see
`SparkInterval.Zeta.LMFDBPrefixBoundary`); the block premises are
discharged, one block at a time, by `PT21ArtifactBinding.BlockArtifact`
together with its Hardy-Z and Turing realizations. -/
theorem sourceClaim_of_ladder
    (prefixClaim : ∀ s : ℂ, riemannZeta s = 0 → 0 < s.re → s.re < 1 →
      0 < s.im → s.im ≤ ((sourceLower : Nat) : ℝ) → s.re = (1 : ℝ) / 2)
    (blockClaims : ∀ k : Nat, k < sourceBlockCount → BlockCriticalLine k) :
    SourceClaim := by
  intro s hzero hre0 hre1 him0 himUpper
  by_cases hprefix : s.im ≤ ((sourceLower : Nat) : ℝ)
  · exact prefixClaim s hzero hre0 hre1 him0 hprefix
  · have hlow : ((blockLower 0 : Nat) : ℝ) < s.im := by
      have hzeroBlock : blockLower 0 = sourceLower := by
        unfold blockLower; omega
      rw [hzeroBlock]
      exact lt_of_not_ge hprefix
    have hhigh : s.im ≤ ((blockLower (0 + sourceBlockCount) : Nat) : ℝ) := by
      have : (0 : Nat) + sourceBlockCount = sourceBlockCount := by omega
      rw [this]
      exact himUpper.trans sourceHeight_le_endpoint
    exact criticalLine_of_blocks 0 sourceBlockCount
      (fun k _hlower hupper => blockClaims k (by omega))
      s hzero hre0 hre1 hlow hhigh

end SparkInterval.Zeta.PT21Ladder

end
