/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Exact LMFDB prefix-boundary arithmetic

The public Platt/LMFDB zero file containing height `10^10` stores ordinate
midpoints on the `2^-101` grid and states absolute error `2^-102`.  It is most
convenient to double that grid: a midpoint becomes a natural at scale
`2^102`, and its complete uncertainty interval has integer endpoints
`midpoint - 1` and `midpoint + 1`.

This module checks the finite arithmetic exported by the streamed binary
parser.  It deliberately does not claim that the slots are zeta zeros or that
the LMFDB list is Turing-complete; those are separate Hardy-Z/source
realization obligations.  It also does not assume simplicity: `belowSlots`
counts encoded multiplicity slots, including duplicates if they occur.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.LMFDBPrefixBoundary

/-- Integer scale on which the stated `2^-102` error has radius one. -/
def scale : Nat := 2 ^ 102

/-- Receipt-facing summary of the unique source block crossing a target. -/
structure BoundaryEvidence where
  targetHeight : Nat
  blockFirstHeight : Nat
  blockLastHeight : Nat
  blockFirstMultiplicityCount : Nat
  blockLastMultiplicityCount : Nat
  belowSlots : Nat
  claimedTargetMultiplicityCount : Nat
  predecessorMidpointScaled : Nat
  successorMidpointScaled : Nat
  deriving Repr, DecidableEq, BEq

namespace BoundaryEvidence

/-- Exact, executable obligations.  The final two inequalities say that the
entire predecessor interval is strictly below the target and the entire
successor interval is at or above it. -/
def WellFormed (evidence : BoundaryEvidence) : Prop :=
  evidence.blockFirstHeight < evidence.targetHeight ∧
  evidence.targetHeight < evidence.blockLastHeight ∧
  evidence.blockFirstMultiplicityCount ≤
    evidence.blockLastMultiplicityCount ∧
  evidence.belowSlots ≤
    evidence.blockLastMultiplicityCount -
      evidence.blockFirstMultiplicityCount ∧
  evidence.blockFirstMultiplicityCount + evidence.belowSlots =
    evidence.claimedTargetMultiplicityCount ∧
  evidence.predecessorMidpointScaled + 1 <
    evidence.targetHeight * scale ∧
  evidence.targetHeight * scale + 1 ≤
    evidence.successorMidpointScaled

instance instDecidableWellFormed (evidence : BoundaryEvidence) :
    Decidable evidence.WellFormed := by
  unfold WellFormed
  infer_instance

def check (evidence : BoundaryEvidence) : Bool :=
  decide evidence.WellFormed

theorem check_sound {evidence : BoundaryEvidence}
    (hcheck : evidence.check = true) : evidence.WellFormed :=
  of_decide_eq_true hcheck

/-- A successful check exposes the exact multiplicity-slot count at the cut
and both non-ambiguity inequalities. -/
theorem checked_cut {evidence : BoundaryEvidence}
    (hcheck : evidence.check = true) :
    evidence.claimedTargetMultiplicityCount =
        evidence.blockFirstMultiplicityCount + evidence.belowSlots ∧
      evidence.predecessorMidpointScaled + 1 <
        evidence.targetHeight * scale ∧
      evidence.targetHeight * scale + 1 ≤
        evidence.successorMidpointScaled := by
  rcases check_sound hcheck with ⟨_, _, _, _, hcount, hbelow, habove⟩
  exact ⟨hcount.symm, hbelow, habove⟩

end BoundaryEvidence

/-- Literal summary independently decoded from LMFDB file
`zeros_9998546000.dat`, block 693. -/
def publicEvidence : BoundaryEvidence := {
  targetHeight := 10_000_000_000
  blockFirstHeight := 9_999_999_200
  blockLastHeight := 10_000_001_300
  blockFirstMultiplicityCount := 32_130_155_617
  blockLastMultiplicityCount := 32_130_162_699
  belowSlots := 2_698
  claimedTargetMultiplicityCount := 32_130_158_315
  predecessorMidpointScaled :=
    50_706_024_008_472_293_905_172_656_473_074_529_309_074
  successorMidpointScaled :=
    50_706_024_009_436_628_724_288_681_434_971_016_802_904
}

/-- Kernel-checked public boundary row.  `norm_num` proves the literal natural
inequalities; there is no native evaluator or external arithmetic axiom. -/
theorem publicEvidence_check : publicEvidence.check = true := by
  norm_num [BoundaryEvidence.check, BoundaryEvidence.WellFormed,
    publicEvidence, scale]

theorem public_targetMultiplicityCount :
    publicEvidence.claimedTargetMultiplicityCount = 32_130_158_315 := rfl

/-- Human-readable arithmetic form of the boundary calculation. -/
theorem public_count_equation :
    32_130_155_617 + 2_698 = 32_130_158_315 := by
  norm_num

/-- The two adjacent stated error intervals do not meet the target. -/
theorem public_target_separated :
    publicEvidence.predecessorMidpointScaled + 1 <
        publicEvidence.targetHeight * scale ∧
      publicEvidence.targetHeight * scale + 1 ≤
        publicEvidence.successorMidpointScaled :=
  (BoundaryEvidence.checked_cut publicEvidence_check).2

end SparkInterval.Zeta.LMFDBPrefixBoundary
