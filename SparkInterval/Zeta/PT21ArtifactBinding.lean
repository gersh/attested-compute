/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PairedTuringClosureCertificate
import SparkInterval.Zeta.TouchingEndpointCertificate

/-!
# Kernel-checked PT21 compact block handoff

This module is the finite decoder target for one compact Platt--Trudgian
block artifact.  It deliberately derives the physical geometry rather than
accepting arbitrary rational ordinates:

* block `k` is `[10^10 + 1008 k, 10^10 + 1008 (k+1)]`;
* the source sample origin is the midpoint `a + 504`;
* rational sample offset `j` denotes `a + 504 + j * 21/512`;
* the main and Turing-flank ranges are the fixed source ranges.

Exact rational endpoint intervals are converted to
`TouchingRationalBracketFamily`.  The same bracket records are converted to
grid events, while the two exact rational one-sided Turing payloads are
converted to `PairedTuringClosureCertificate`: `turing_min` on `[a-21,a]`
and `turing_max` on `[b,b+21]`.  `check` invokes both existing kernel
checkers and also checks packet identities, the fixed geometry, boundary
signs, touching-endpoint agreement, and stationary-pair/fallback metadata.

Bracket endpoints and Turing events are deliberately separate.  The source's
`resolve_stat_point` returns two strict brackets meeting at a dyadic
interpolation point, while `Nleft_int`/`Nright_int` charge one conservative
integer cell with multiplicity two.  Conflating those coordinates would give
the wrong Turing weights and would be unable to encode a real stationary
resolution.

The handoff does **not** prove that an endpoint interval encloses Hardy Z,
that an event realizes a zero with the recorded multiplicity, or that the
finite Turing intervals realize the analytic quantities.  Those facts remain
explicit premises in `touchingCertificate` and `exactEndpointCounts`; sign
bits alone cannot discharge them.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open SparkInterval.Certificate

namespace PT21ArtifactBinding

def sourceLower : Nat := 10_000_000_000
def sourceBlockStep : Nat := 1_008
def sourceHalfStep : Nat := 504
def sourceBlockCount : Nat := 2_966_443_783
def sourceSpacing : ℚ := 21 / 512
def pinnedUpstreamCommitSha1 : List UInt8 :=
  [0x42, 0xb2, 0x14, 0x26, 0x71, 0x8e, 0x54, 0x2d, 0xaa, 0x2b,
    0x00, 0x6d, 0xc0, 0x5e, 0xa2, 0xd7, 0xf2, 0x64, 0x26, 0xe6]

inductive StreamKind
  | main
  | leftFlank
  | rightFlank
  deriving DecidableEq, Repr

namespace StreamKind

def lowerSample : StreamKind → Int
  | .main => -12_288
  | .leftFlank => -12_800
  | .rightFlank => 12_288

def upperSample : StreamKind → Int
  | .main => 12_288
  | .leftFlank => -12_288
  | .rightFlank => 12_800

def spanSteps (kind : StreamKind) : Nat :=
  (kind.upperSample - kind.lowerSample).toNat

end StreamKind

inductive Resolver
  | direct
  | stationaryLeft
  | stationaryRight
  | pinnedArbFallback
  deriving DecidableEq, Repr

/-- A rational evaluator enclosure with its claimed strict sign.  The sign is
redundant by design: the checker recomputes it from the interval. -/
structure SignedEndpoint where
  enclosure : RatInterval
  positive : Bool
  deriving DecidableEq, Repr

namespace SignedEndpoint

def IsValid (endpoint : SignedEndpoint) : Prop :=
  endpoint.enclosure.IsValid ∧
    if endpoint.positive then 0 < endpoint.enclosure.lo
    else endpoint.enclosure.hi < 0

instance (endpoint : SignedEndpoint) : Decidable endpoint.IsValid := by
  unfold IsValid RatInterval.IsValid
  infer_instance

def check (endpoint : SignedEndpoint) : Bool := decide endpoint.IsValid

@[simp] theorem check_eq_true {endpoint : SignedEndpoint} :
    endpoint.check = true ↔ endpoint.IsValid := by
  simp [check]

/-- Evaluator-specific meaning intentionally kept outside the finite wire
checker. -/
def EnclosesAt (endpoint : SignedEndpoint) (f : ℝ → ℝ) (x : ℚ) : Prop :=
  endpoint.enclosure.ContainsReal (f (x : ℝ))

end SignedEndpoint

/-- One source bracket.  A fallback receipt is required exactly for a pinned
Arb fallback and forbidden for the other resolver classes. -/
structure BracketRecord where
  lowerOffset : ℚ
  upperOffset : ℚ
  lowerValue : SignedEndpoint
  upperValue : SignedEndpoint
  resolver : Resolver
  fallbackReceiptSha256 : Option (List UInt8)
  deriving DecidableEq, Repr

namespace BracketRecord

def fallbackMetadataValid (record : BracketRecord) : Bool :=
  match record.resolver, record.fallbackReceiptSha256 with
  | .pinnedArbFallback, some digest => decide (digest.length = 32)
  | .pinnedArbFallback, none => false
  | _, none => true
  | _, some _ => false

def checkInRange (kind : StreamKind) (record : BracketRecord) : Bool :=
  decide ((kind.lowerSample : ℚ) ≤ record.lowerOffset) &&
    decide (record.lowerOffset < record.upperOffset) &&
    decide (record.upperOffset ≤ (kind.upperSample : ℚ)) &&
    record.lowerValue.check && record.upperValue.check &&
    decide (record.lowerValue.positive ≠ record.upperValue.positive) &&
    record.fallbackMetadataValid

end BracketRecord

/-- The conservative integer cell charged by the source Turing integrals.

A direct sign change has multiplicity one.  A resolved stationary point has
multiplicity two even though it supplies two separate touching strict
brackets at generally dyadic offsets. -/
structure IsolationEvent where
  leftSample : Int
  rightSample : Int
  multiplicity : Nat
  deriving DecidableEq, Repr

namespace IsolationEvent

def checkInRange (kind : StreamKind) (event : IsolationEvent) : Bool :=
  decide (kind.lowerSample ≤ event.leftSample) &&
    decide (event.leftSample < event.rightSample) &&
    decide (event.rightSample ≤ kind.upperSample) &&
    decide (event.multiplicity = 1 ∨ event.multiplicity = 2)

def toGrid (kind : StreamKind) (event : IsolationEvent) : TuringGridEvent := {
  leftStep := (event.leftSample - kind.lowerSample).toNat
  rightStep := (event.rightSample - kind.lowerSample).toNat
  multiplicity := event.multiplicity
}

end IsolationEvent

/-- Boundary signs and the ordered bracket records for one named stream. -/
structure Stream where
  leftBoundary : SignedEndpoint
  rightBoundary : SignedEndpoint
  brackets : List BracketRecord
  events : List IsolationEvent
  deriving DecidableEq, Repr

namespace Stream

private def sequenceCheck (kind : StreamKind)
    (leftPositive rightPositive : Bool) :
    Option (ℚ × Bool) → List BracketRecord → Bool
  | _, [] => true
  | previous, record :: rest =>
      record.checkInRange kind &&
        (match previous with
          | none => true
          | some (previousUpper, previousPositive) =>
              decide (previousUpper ≤ record.lowerOffset) &&
                (if previousUpper = record.lowerOffset then
                  decide (previousPositive = record.lowerValue.positive)
                else true)) &&
        (if record.lowerOffset = (kind.lowerSample : ℚ) then
          decide (record.lowerValue.positive = leftPositive)
        else true) &&
        (if record.upperOffset = (kind.upperSample : ℚ) then
          decide (record.upperValue.positive = rightPositive)
        else true) &&
        sequenceCheck kind leftPositive rightPositive
          (some (record.upperOffset, record.upperValue.positive)) rest

private def resolverCheck : List BracketRecord → Bool
  | [] => true
  | [record] =>
      decide (record.resolver ≠ .stationaryLeft) &&
        decide (record.resolver ≠ .stationaryRight)
  | first :: second :: rest =>
      match first.resolver with
      | .stationaryLeft =>
          decide (second.resolver = .stationaryRight) &&
            decide (first.upperOffset = second.lowerOffset) &&
            resolverCheck rest
      | .stationaryRight => false
      | _ => resolverCheck (second :: rest)

/-- Bind the strict brackets to the conservative source cells without
conflating their coordinates.  Every direct/fallback event consumes one
bracket.  Every stationary event consumes the two touching brackets returned
by `resolve_stat_point`. -/
private def eventRecordCheck : List BracketRecord → List IsolationEvent → Bool
  | [], [] => true
  | first :: brackets, event :: events =>
      decide ((event.leftSample : ℚ) ≤ first.lowerOffset) &&
        (if event.multiplicity = 1 then
          decide (first.upperOffset ≤ (event.rightSample : ℚ)) &&
            decide (first.resolver = .direct ∨
              first.resolver = .pinnedArbFallback) &&
            eventRecordCheck brackets events
        else if event.multiplicity = 2 then
          match brackets with
          | second :: rest =>
              decide (first.resolver = .stationaryLeft) &&
                decide (second.resolver = .stationaryRight) &&
                decide (first.upperOffset = second.lowerOffset) &&
                decide (second.upperOffset ≤ (event.rightSample : ℚ)) &&
                eventRecordCheck rest events
          | [] => false
        else false)
  | _, _ => false

private def eventRangeCheck (kind : StreamKind) :
    Option Int → List IsolationEvent → Bool
  | _, [] => true
  | previous, event :: rest =>
      event.checkInRange kind &&
        (match previous with
          | none => true
          | some previousRight => decide (previousRight ≤ event.leftSample)) &&
        eventRangeCheck kind (some event.rightSample) rest

def checkRecords (kind : StreamKind) (stream : Stream) : Bool :=
  stream.leftBoundary.check && stream.rightBoundary.check &&
    sequenceCheck kind stream.leftBoundary.positive
      stream.rightBoundary.positive none stream.brackets &&
    resolverCheck stream.brackets &&
    eventRangeCheck kind none stream.events &&
    eventRecordCheck stream.brackets stream.events

end Stream

/-- Exact-rational finite inputs for one source one-sided Turing call.  Event
weights and physical geometry are derived rather than trusted. -/
structure TuringSidePayload where
  sBound : RatInterval
  logPi : RatInterval
  imGammaIntegral : RatInterval
  pi : RatInterval
  quotient : RatInterval
  count : Nat
  deriving DecidableEq, Repr

/-- The source calls `turing_min` on `[a-21,a]` and `turing_max` on
`[b,b+21]`; these are not one shared 1008-unit window. -/
structure TuringPayload where
  lower : TuringSidePayload
  upper : TuringSidePayload
  deriving DecidableEq, Repr

/-- Complete compact handoff for one source block. -/
structure BlockArtifact where
  block : Nat
  heightLower : Nat
  heightUpper : Nat
  windowCenter : Nat
  upstreamCommitSha1 : List UInt8
  requiredSignPacketSha256 : List UInt8
  sourceTraceSha256 : List UInt8
  main : Stream
  leftFlank : Stream
  rightFlank : Stream
  turing : TuringPayload
  deriving DecidableEq, Repr

namespace BlockArtifact

def expectedHeightLower (artifact : BlockArtifact) : Nat :=
  sourceLower + artifact.block * sourceBlockStep

def GeometryValid (artifact : BlockArtifact) : Prop :=
  artifact.block < sourceBlockCount ∧
    artifact.heightLower = artifact.expectedHeightLower ∧
    artifact.heightUpper = artifact.heightLower + sourceBlockStep ∧
    artifact.windowCenter = artifact.heightLower + sourceHalfStep ∧
    artifact.upstreamCommitSha1 = pinnedUpstreamCommitSha1 ∧
    artifact.requiredSignPacketSha256.length = 32 ∧
    artifact.sourceTraceSha256.length = 32

instance (artifact : BlockArtifact) : Decidable artifact.GeometryValid := by
  unfold GeometryValid
  infer_instance

/-- Exact ordinate of a source lattice offset. -/
def sampleOrdinate (artifact : BlockArtifact) (offset : ℚ) : ℚ :=
  (artifact.windowCenter : ℚ) + offset * sourceSpacing

end BlockArtifact

namespace Stream

/-- Full evaluator-specific interpretation of the endpoint intervals in one
stream.  This is a premise, not a consequence of the wire checker. -/
def EnclosesEndpointRecords (artifact : BlockArtifact)
    (kind : StreamKind) (stream : Stream) (f : ℝ → ℝ) : Prop :=
  stream.leftBoundary.EnclosesAt f
      (artifact.sampleOrdinate kind.lowerSample) ∧
    stream.rightBoundary.EnclosesAt f
      (artifact.sampleOrdinate kind.upperSample) ∧
    ∀ record ∈ stream.brackets,
      record.lowerValue.EnclosesAt f
          (artifact.sampleOrdinate record.lowerOffset) ∧
        record.upperValue.EnclosesAt f
            (artifact.sampleOrdinate record.upperOffset)

end Stream

namespace BlockArtifact

def rationalBracket (artifact : BlockArtifact)
    (record : BracketRecord) : RationalBracket := {
  lower := artifact.sampleOrdinate record.lowerOffset
  upper := artifact.sampleOrdinate record.upperOffset
  lowerValue := record.lowerValue.enclosure
  upperValue := record.upperValue.enclosure
}

def bracketFamily (artifact : BlockArtifact) (stream : Stream) :
    TouchingRationalBracketFamily stream.brackets.length := {
  entries := fun i => artifact.rationalBracket (stream.brackets.get i)
}

def mainBracketFamily (artifact : BlockArtifact) :=
  artifact.bracketFamily artifact.main

def leftFlankBracketFamily (artifact : BlockArtifact) :=
  artifact.bracketFamily artifact.leftFlank

def rightFlankBracketFamily (artifact : BlockArtifact) :=
  artifact.bracketFamily artifact.rightFlank

def streamCertificate (kind : StreamKind) (stream : Stream) :
    TuringGridEventCertificate :=
  let events := stream.events.map (IsolationEvent.toGrid kind)
  {
    spanSteps := kind.spanSteps
    events := events
    isolatedCount := turingGridTotalMultiplicity events
    leftWeight := turingGridLeftWeight events
    rightWeight := turingGridRightWeight kind.spanSteps events
    leftPositive := stream.leftBoundary.positive
    rightPositive := stream.rightBoundary.positive
  }

def mainStreamCertificate (artifact : BlockArtifact) :=
  streamCertificate .main artifact.main

def leftFlankStreamCertificate (artifact : BlockArtifact) :=
  streamCertificate .leftFlank artifact.leftFlank

def rightFlankStreamCertificate (artifact : BlockArtifact) :=
  streamCertificate .rightFlank artifact.rightFlank

def lowerTuringWindow (artifact : BlockArtifact) : LowerTuringCertificate := {
  input := {
    a := (artifact.heightLower : ℚ) - 21
    b := artifact.heightLower
    delta := sourceSpacing
    sBound := artifact.turing.lower.sBound
    logPi := artifact.turing.lower.logPi
    imGammaIntegral := artifact.turing.lower.imGammaIntegral
    pi := artifact.turing.lower.pi
    leftWeight := artifact.leftFlankStreamCertificate.leftWeight
    rightWeight := 0
  }
  quotient := artifact.turing.lower.quotient
  count := artifact.turing.lower.count
}

def upperTuringWindow (artifact : BlockArtifact) : UpperTuringCertificate := {
  input := {
    a := artifact.heightUpper
    b := (artifact.heightUpper : ℚ) + 21
    delta := sourceSpacing
    sBound := artifact.turing.upper.sBound
    logPi := artifact.turing.upper.logPi
    imGammaIntegral := artifact.turing.upper.imGammaIntegral
    pi := artifact.turing.upper.pi
    leftWeight := 0
    rightWeight := artifact.rightFlankStreamCertificate.rightWeight
  }
  quotient := artifact.turing.upper.quotient
  count := artifact.turing.upper.count
}

def pairedTuring (artifact : BlockArtifact) :
    PairedTuringClosureCertificate := {
  mainStream := artifact.mainStreamCertificate
  leftFlankStream := artifact.leftFlankStreamCertificate
  rightFlankStream := artifact.rightFlankStreamCertificate
  lowerWindow := artifact.lowerTuringWindow
  upperWindow := artifact.upperTuringWindow
  lowerCount := artifact.turing.lower.count
  mainIsolatedSlots := artifact.main.brackets.length
  upperCount := artifact.turing.upper.count
}

/-- One fail-closed acceptance bit for the whole finite handoff. -/
def check (artifact : BlockArtifact) : Bool :=
  decide artifact.GeometryValid &&
    artifact.main.checkRecords .main &&
    artifact.leftFlank.checkRecords .leftFlank &&
    artifact.rightFlank.checkRecords .rightFlank &&
    artifact.mainBracketFamily.check &&
    artifact.leftFlankBracketFamily.check &&
    artifact.rightFlankBracketFamily.check &&
    artifact.pairedTuring.check

/-- All physical endpoint enclosures still required from a proved Hardy-Z
evaluator or independently checked interval trace. -/
structure EndpointRealization (artifact : BlockArtifact) (f : ℝ → ℝ) : Prop where
  main : artifact.main.EnclosesEndpointRecords artifact .main f
  leftFlank : artifact.leftFlank.EnclosesEndpointRecords artifact .leftFlank f
  rightFlank : artifact.rightFlank.EnclosesEndpointRecords artifact .rightFlank f

/-- A successful handoff has entered both proved finite contracts. -/
theorem checked_components (artifact : BlockArtifact)
    (hcheck : artifact.check = true) :
    artifact.mainBracketFamily.check = true ∧
      artifact.leftFlankBracketFamily.check = true ∧
      artifact.rightFlankBracketFamily.check = true ∧
      artifact.pairedTuring.check = true := by
  simp only [check, Bool.and_eq_true] at hcheck
  tauto

theorem geometry_of_check (artifact : BlockArtifact)
    (hcheck : artifact.check = true) : artifact.GeometryValid := by
  have hgeometry : decide artifact.GeometryValid = true := by
    simp only [check, Bool.and_eq_true] at hcheck
    tauto
  exact of_decide_eq_true hgeometry

/-- The fixed offsets really are `[a,b]`, `[a-21,a]`, and `[b,b+21]` in
physical ordinates. -/
theorem source_range_coordinates (artifact : BlockArtifact)
    (hcheck : artifact.check = true) :
    artifact.sampleOrdinate StreamKind.main.lowerSample = artifact.heightLower ∧
      artifact.sampleOrdinate StreamKind.main.upperSample = artifact.heightUpper ∧
      artifact.sampleOrdinate StreamKind.leftFlank.lowerSample =
        (artifact.heightLower : ℚ) - 21 ∧
      artifact.sampleOrdinate StreamKind.leftFlank.upperSample =
        artifact.heightLower ∧
      artifact.sampleOrdinate StreamKind.rightFlank.lowerSample =
        artifact.heightUpper ∧
      artifact.sampleOrdinate StreamKind.rightFlank.upperSample =
        (artifact.heightUpper : ℚ) + 21 := by
  rcases artifact.geometry_of_check hcheck with
    ⟨_block, _heightLower, hheightUpper, hcenter, _upstream,
      _packetDigest, _traceDigest⟩
  simp only [sampleOrdinate, StreamKind.lowerSample, StreamKind.upperSample,
    sourceSpacing]
  rw [hcenter, hheightUpper]
  norm_num [sourceHalfStep, sourceBlockStep]
  constructor
  · ring
  constructor
  · ring
  constructor
  · ring
  · ring

/-- Physical endpoints of every decoded main bracket are forced by the
source lattice, rather than trusted from the producer. -/
@[simp] theorem mainBracket_lower (artifact : BlockArtifact)
    (i : Fin artifact.main.brackets.length) :
    (artifact.mainBracketFamily.entries i).lower =
      artifact.sampleOrdinate (artifact.main.brackets.get i).lowerOffset := rfl

@[simp] theorem mainBracket_upper (artifact : BlockArtifact)
    (i : Fin artifact.main.brackets.length) :
    (artifact.mainBracketFamily.entries i).upper =
      artifact.sampleOrdinate (artifact.main.brackets.get i).upperOffset := rfl

/-- The finite decoder reaches the existing touching-bracket theorem only
after the caller proves that every emitted interval encloses the chosen real
evaluator. -/
theorem touchingCertificate (artifact : BlockArtifact)
    (hcheck : artifact.check = true) {f : ℝ → ℝ}
    (hencloses : ∀ i,
      (artifact.mainBracketFamily.entries i).EnclosesEndpoints f) :
    ∃ certificate : TouchingZeroCertificate f artifact.main.brackets.length,
      ∀ i,
        (certificate.brackets i).lower =
            (artifact.mainBracketFamily.entries i).lower ∧
          (certificate.brackets i).upper =
            (artifact.mainBracketFamily.entries i).upper := by
  exact artifact.mainBracketFamily.exists_touchingZeroCertificate
    (artifact.checked_components hcheck).1 hencloses

theorem EndpointRealization.mainFamilyEncloses
    {artifact : BlockArtifact} {f : ℝ → ℝ}
    (realization : artifact.EndpointRealization f) :
    ∀ i, (artifact.mainBracketFamily.entries i).EnclosesEndpoints f := by
  intro i
  have hrecord := realization.main.2.2
    (artifact.main.brackets.get i) (List.get_mem artifact.main.brackets i)
  exact hrecord

/-- Convenience composition retaining the full physical-endpoint realization
as the visible upstream obligation. -/
theorem touchingCertificateFromRealization (artifact : BlockArtifact)
    (hcheck : artifact.check = true) {f : ℝ → ℝ}
    (realization : artifact.EndpointRealization f) :
    ∃ certificate : TouchingZeroCertificate f artifact.main.brackets.length,
      ∀ i,
        (certificate.brackets i).lower =
            (artifact.mainBracketFamily.entries i).lower ∧
          (certificate.brackets i).upper =
            (artifact.mainBracketFamily.entries i).upper := by
  exact artifact.touchingCertificate hcheck realization.mainFamilyEncloses

/-- The finite decoder reaches exact endpoint counts only with the analytic
Turing realization and the multiplicity-count lower bound still visible. -/
theorem exactEndpointCounts (artifact : BlockArtifact)
    (hcheck : artifact.check = true)
    (lowerValues : artifact.pairedTuring.lowerWindow.input.Realization)
    (upperValues : artifact.pairedTuring.upperWindow.input.Realization)
    {countAtLeft countAtRight : Nat}
    (analytic : artifact.pairedTuring.AnalyticTuringBounds
      lowerValues upperValues countAtLeft countAtRight)
    (mainLower : artifact.pairedTuring.MainMultiplicitySlotLowerBound
      countAtLeft countAtRight) :
    countAtLeft = artifact.turing.lower.count ∧
      countAtRight = artifact.turing.upper.count ∧
      countAtLeft + artifact.main.brackets.length = countAtRight := by
  exact artifact.pairedTuring.exact_endpoint_counts
    (artifact.checked_components hcheck).2.2.2 lowerValues upperValues
      analytic mainLower

end BlockArtifact

end PT21ArtifactBinding

end SparkInterval.Zeta
