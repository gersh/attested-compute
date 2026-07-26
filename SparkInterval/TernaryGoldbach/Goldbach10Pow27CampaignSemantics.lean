/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachShiftedBitset

/-!
# Exact semantic handoff for the optimized finite Goldbach campaign

The external binary campaign does not get to provide
`Goldbach10Pow27SourceSemantics.BinaryGoldbachClaim` directly.  Its semantic
payload is instead the gap-free, word-indexed coverage evidence modeled by
`GoldbachShiftedBitset.CampaignEvidence` at the literal lowered endpoint.
Ordinary Lean derives the binary claim from that evidence and combines it
with the independently checked prime ladder.

This is the narrowest currently proved handoff from the optimized packed-word
algorithm to the finite theorem through `10^27`.  It does not parse a CUDA
receipt, assert that a compiled executable realizes the model, or install a
production artifact.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Goldbach10Pow27CampaignSemantics

namespace Source

abbrev binaryLimit :=
  Goldbach10Pow27SourceSemantics.binaryLimit

abbrev PrimeLadder :=
  Goldbach10Pow27SourceSemantics.PrimeLadder

end Source

/-- Exact semantic evidence that the external binary and ladder branches must
realize.  In particular, the binary field is indexed by
`31_250_000_000_000_000`; evidence for a smaller or historical endpoint has a
different type. -/
structure CheckedCampaignEvidence where
  binary :
    GoldbachShiftedBitset.CampaignEvidence Source.binaryLimit
  ladder : Source.PrimeLadder
  ladderCheck : ladder.check = true

/-- The literal lowered binary campaign contains this many even targets. -/
theorem binaryEvenCount_eq :
    GoldbachShiftedBitset.evenCount Source.binaryLimit =
      15_624_999_999_999_999 := by
  norm_num [GoldbachShiftedBitset.evenCount,
    Source.binaryLimit, Goldbach10Pow27SourceSemantics.binaryLimit]

/-- The packed campaign contains exactly this many 64-even output words. -/
theorem binaryOutputWordCount_eq :
    GoldbachShiftedBitset.outputWordCount Source.binaryLimit =
      244_140_625_000_000 := by
  norm_num [GoldbachShiftedBitset.outputWordCount,
    GoldbachShiftedBitset.evenCount, Source.binaryLimit,
    Goldbach10Pow27SourceSemantics.binaryLimit]

/-- The final packed output word has 63 live lanes. -/
theorem binaryFinalWordLiveCount_eq :
    GoldbachShiftedBitset.evenCount Source.binaryLimit -
        64 *
          (GoldbachShiftedBitset.outputWordCount Source.binaryLimit - 1) =
      63 := by
  norm_num [GoldbachShiftedBitset.outputWordCount,
    GoldbachShiftedBitset.evenCount, Source.binaryLimit,
    Goldbach10Pow27SourceSemantics.binaryLimit]

/-- Ordinary Lean turns exact packed-word campaign coverage into the lowered
binary Goldbach premise. -/
theorem binaryClaim (evidence : CheckedCampaignEvidence) :
    Goldbach10Pow27SourceSemantics.BinaryGoldbachClaim :=
  GoldbachShiftedBitset.binaryGoldbach10Pow27Claim_of_campaign
    evidence.binary

/-- Package the exact algorithm-level evidence into the older source-level
record.  The mathematically strong binary field is derived here, rather than
being accepted directly from an external receipt. -/
def toCheckedSourceEvidence (evidence : CheckedCampaignEvidence) :
    Goldbach10Pow27SourceSemantics.CheckedSourceEvidence where
  ladder := evidence.ladder
  binary := binaryClaim evidence
  ladderCheck := evidence.ladderCheck

/-- Exact end-to-end mathematical reduction after the external execution
boundary has supplied `CheckedCampaignEvidence`. -/
theorem sourceClaim (evidence : CheckedCampaignEvidence) :
    Goldbach10Pow27SourceSemantics.SourceClaim :=
  Goldbach10Pow27SourceSemantics.sourceClaim_of_checked_evidence
    (toCheckedSourceEvidence evidence)

#print axioms binaryEvenCount_eq
#print axioms binaryOutputWordCount_eq
#print axioms binaryFinalWordLiveCount_eq
#print axioms binaryClaim
#print axioms sourceClaim

end SparkInterval.TernaryGoldbach.Goldbach10Pow27CampaignSemantics
