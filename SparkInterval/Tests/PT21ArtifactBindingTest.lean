/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21ArtifactBinding

/-! Kernel-reduced tests for the compact PT21 block handoff. -/

set_option autoImplicit false

namespace SparkInterval.Tests.PT21ArtifactBinding

open SparkInterval.Certificate
open SparkInterval.Zeta
open SparkInterval.Zeta.PT21ArtifactBinding

private def negative : SignedEndpoint := {
  enclosure := RatInterval.point (-1)
  positive := false
}

private def positive : SignedEndpoint := {
  enclosure := RatInterval.point 1
  positive := true
}

private def first : BracketRecord := {
  lowerOffset := -1
  upperOffset := 1 / 2
  lowerValue := negative
  upperValue := positive
  resolver := .stationaryLeft
  fallbackReceiptSha256 := none
}

private def second : BracketRecord := {
  lowerOffset := 1 / 2
  upperOffset := 1
  lowerValue := positive
  upperValue := negative
  resolver := .stationaryRight
  fallbackReceiptSha256 := none
}

private def main : Stream := {
  leftBoundary := negative
  rightBoundary := negative
  brackets := [first, second]
  events := [{ leftSample := -1, rightSample := 1, multiplicity := 2 }]
}

private def emptyStream : Stream := {
  leftBoundary := negative
  rightBoundary := negative
  brackets := []
  events := []
}

private def accepted : BlockArtifact := {
  block := 0
  heightLower := 10_000_000_000
  heightUpper := 10_000_001_008
  windowCenter := 10_000_000_504
  upstreamCommitSha1 := pinnedUpstreamCommitSha1
  requiredSignPacketSha256 := List.replicate 32 0xab
  sourceTraceSha256 := List.replicate 32 0xcd
  main := main
  leftFlank := emptyStream
  rightFlank := emptyStream
  turing := {
    lower := {
      sBound := RatInterval.point 21
      logPi := RatInterval.point 0
      imGammaIntegral := RatInterval.point 21
      pi := RatInterval.point 1
      quotient := RatInterval.point 0
      count := 1
    }
    upper := {
      sBound := RatInterval.point 21
      logPi := RatInterval.point 0
      imGammaIntegral := RatInterval.point 21
      pi := RatInterval.point 1
      quotient := RatInterval.point 2
      count := 3
    }
  }
}

#guard accepted.check
#guard accepted.mainBracketFamily.check
#guard accepted.pairedTuring.check

example : accepted.heightLower = sourceLower := by decide

example : (accepted.mainBracketFamily.entries
      ⟨0, by simp [accepted, main]⟩).lower =
    (10_000_000_504 : ℚ) - sourceSpacing := by
  norm_num [BlockArtifact.mainBracketFamily, BlockArtifact.bracketFamily,
    BlockArtifact.rationalBracket, BlockArtifact.sampleOrdinate, accepted,
    main, first, sourceSpacing]

example : (accepted.mainBracketFamily.entries
      ⟨0, by simp [accepted, main]⟩).upper =
    (accepted.mainBracketFamily.entries
      ⟨1, by simp [accepted, main]⟩).lower := by
  norm_num [BlockArtifact.mainBracketFamily, BlockArtifact.bracketFamily,
    BlockArtifact.rationalBracket, BlockArtifact.sampleOrdinate, accepted,
    main, first, second]

example : accepted.main.brackets.length = 2 := by decide

example : accepted.main.events =
    [{ leftSample := -1, rightSample := 1, multiplicity := 2 }] := by decide

example (hcheck : accepted.check = true) :
    accepted.mainBracketFamily.check = true ∧
    accepted.leftFlankBracketFamily.check = true ∧
    accepted.rightFlankBracketFamily.check = true ∧
    accepted.pairedTuring.check = true :=
  accepted.checked_components hcheck

example (hcheck : accepted.check = true) :
    accepted.sampleOrdinate StreamKind.main.lowerSample =
      accepted.heightLower ∧
    accepted.sampleOrdinate StreamKind.main.upperSample =
      accepted.heightUpper := by
  exact ⟨(accepted.source_range_coordinates hcheck).1,
    (accepted.source_range_coordinates hcheck).2.1⟩

private def wrongHeight : BlockArtifact := {
  accepted with heightLower := 10_000_000_001
}

#guard wrongHeight.check = false

private def badSecond : BracketRecord := {
  second with
    lowerValue := negative
    upperValue := positive
}

private def inconsistentTouch : BlockArtifact := {
  accepted with main := { main with brackets := [first, badSecond] }
}

#guard inconsistentTouch.check = false

private def unboundFallback : BracketRecord := {
  first with
    resolver := .pinnedArbFallback
    fallbackReceiptSha256 := none
}

private def badFallback : BlockArtifact := {
  accepted with main := { main with brackets := [unboundFallback] }
}

#guard badFallback.check = false

private def wrongStationaryMultiplicity : BlockArtifact := {
  accepted with main := {
    main with events := [{ leftSample := -1, rightSample := 1, multiplicity := 1 }]
  }
}

#guard wrongStationaryMultiplicity.check = false

end SparkInterval.Tests.PT21ArtifactBinding
