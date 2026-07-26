/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Goldbach10Pow27CampaignSemantics

set_option autoImplicit false

namespace SparkInterval.Tests.Goldbach10Pow27CampaignSemanticsTest

open SparkInterval.TernaryGoldbach

example
    (evidence :
      Goldbach10Pow27CampaignSemantics.CheckedCampaignEvidence) :
    Goldbach10Pow27SourceSemantics.BinaryGoldbachClaim :=
  Goldbach10Pow27CampaignSemantics.binaryClaim evidence

example
    (evidence :
      Goldbach10Pow27CampaignSemantics.CheckedCampaignEvidence) :
    Goldbach10Pow27SourceSemantics.SourceClaim :=
  Goldbach10Pow27CampaignSemantics.sourceClaim evidence

example :
    GoldbachShiftedBitset.evenCount
        Goldbach10Pow27SourceSemantics.binaryLimit =
      15_624_999_999_999_999 :=
  Goldbach10Pow27CampaignSemantics.binaryEvenCount_eq

example :
    GoldbachShiftedBitset.outputWordCount
        Goldbach10Pow27SourceSemantics.binaryLimit =
      244_140_625_000_000 :=
  Goldbach10Pow27CampaignSemantics.binaryOutputWordCount_eq

example :
    GoldbachShiftedBitset.evenCount
          Goldbach10Pow27SourceSemantics.binaryLimit -
        64 *
          (GoldbachShiftedBitset.outputWordCount
              Goldbach10Pow27SourceSemantics.binaryLimit - 1) =
      63 :=
  Goldbach10Pow27CampaignSemantics.binaryFinalWordLiveCount_eq

#print axioms
  Goldbach10Pow27CampaignSemantics.binaryEvenCount_eq
#print axioms
  Goldbach10Pow27CampaignSemantics.binaryOutputWordCount_eq
#print axioms
  Goldbach10Pow27CampaignSemantics.binaryFinalWordLiveCount_eq
#print axioms Goldbach10Pow27CampaignSemantics.binaryClaim
#print axioms Goldbach10Pow27CampaignSemantics.sourceClaim

end SparkInterval.Tests.Goldbach10Pow27CampaignSemanticsTest
