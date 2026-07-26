/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDiskContainment
import SparkInterval.Certified.ComplexDiskWire

/-!
# Fixed-width RealDisk106 containment wire

This module checks one pair of PT21 `RealDisk106` records.  Each record is
exactly 24 bytes:

```
center.hi || center.lo || radius
```

and the complete 48-byte frame is:

```
inner || outer
```

Every field is one IEEE-754 binary64 word in little-endian byte order.  Both
centre limbs are decoded exactly and the real centre is `hi + lo`; the
corresponding `ComplexDisk` has imaginary centre zero.  Both spellings of
binary64 zero are accepted and retained in the raw record because a CUDA
double-double result may contain `-0.0`.  Infinity and NaN fail closed during
finite decoding, while truncation and trailing bytes fail closed during
framing.

A successful check proves the generic exact-rational
`ContainmentCertificate.WellFormed` predicate and hence that every complex
value contained by the decoded inner disk is contained by the decoded outer
disk.

This is only a byte-to-exact-arithmetic boundary.  It does not prove that
these bytes came from a CUDA object, instruction trace, compiler, physical
GPU, authenticated receipt, or particular run.
-/

set_option autoImplicit false

namespace SparkInterval.Certified.ComplexDisk.Containment.Wire

open SparkInterval.Certificate

/-! ## Exact RealDisk106 decoding -/

/-- The three raw binary64 words in one 24-byte PT21 `RealDisk106`. -/
structure RawRealDisk106 where
  centerHiBits : Nat
  centerLoBits : Nat
  radiusBits : Nat
  deriving Repr, DecidableEq, BEq

namespace RawRealDisk106

/-- Decode both finite centre limbs as the exact rational `hi + lo`, decode
the finite radius, and embed the real disk with imaginary centre zero. -/
def decode (raw : RawRealDisk106) : Option ComplexDisk := do
  let centerHi ← Binary64.decodeFinite raw.centerHiBits
  let centerLo ← Binary64.decodeFinite raw.centerLoBits
  let radius ← Binary64.decodeFinite raw.radiusBits
  pure ⟨centerHi + centerLo, 0, radius⟩

end RawRealDisk106

/-- Raw words for one `inner || outer` RealDisk106 containment frame. -/
structure RawContainmentPair where
  inner : RawRealDisk106
  outer : RawRealDisk106
  deriving Repr, DecidableEq, BEq

namespace RawContainmentPair

/-- Decode both records to the reusable generic containment certificate. -/
def decode (raw : RawContainmentPair) :
    Option ComplexDisk.ContainmentCertificate := do
  let inner ← raw.inner.decode
  let outer ← raw.outer.decode
  pure ⟨inner, outer⟩

/-- Fail-closed finite decoding and exact-rational containment check. -/
def check (raw : RawContainmentPair) : Bool :=
  match raw.decode with
  | none => false
  | some certificate => certificate.check

/-- Typed evidence recovered from a successful raw check. -/
def Validated (raw : RawContainmentPair) : Prop :=
  ∃ certificate : ComplexDisk.ContainmentCertificate,
    raw.decode = some certificate ∧ certificate.WellFormed

theorem check_sound {raw : RawContainmentPair}
    (hcheck : raw.check = true) : raw.Validated := by
  unfold check at hcheck
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some certificate =>
      exact ⟨certificate, hdecode,
        ComplexDisk.ContainmentCertificate.check_sound (by
          simpa [hdecode] using hcheck)⟩

/-- Arithmetic application at the raw-word boundary. -/
theorem outer_contains_of_inner_contains
    {raw : RawContainmentPair}
    {certificate : ComplexDisk.ContainmentCertificate}
    {value : ℂ}
    (hcheck : raw.check = true)
    (hdecode : raw.decode = some certificate)
    (hvalue : certificate.inner.ContainsComplex value) :
    certificate.outer.ContainsComplex value := by
  have htyped : certificate.check = true := by
    unfold check at hcheck
    simpa [hdecode] using hcheck
  exact
    ComplexDisk.ContainmentCertificate.outer_contains_of_inner_contains
      htyped hvalue

end RawContainmentPair

/-! ## Exact 48-byte little-endian framing -/

/-- Consume one 24-byte `center.hi || center.lo || radius` record.  Raw
`readU64LE` is intentional: signed zero is a valid RealDisk106 limb. -/
def readRawRealDisk106
    (input : List UInt8) :
    Option (RawRealDisk106 × List UInt8) := do
  let (centerHiBits, rest) ←
    ComplexDisk.Wire.readU64LE input
  let (centerLoBits, rest) ←
    ComplexDisk.Wire.readU64LE rest
  let (radiusBits, rest) ←
    ComplexDisk.Wire.readU64LE rest
  pure (⟨centerHiBits, centerLoBits, radiusBits⟩, rest)

/-- Consume one fixed-order `inner || outer` pair. -/
def readRawContainmentPair
    (input : List UInt8) :
    Option (RawContainmentPair × List UInt8) := do
  let (inner, rest) ← readRawRealDisk106 input
  let (outer, rest) ← readRawRealDisk106 rest
  pure (⟨inner, outer⟩, rest)

def rawRealDisk106ByteSize : Nat := 24
def rawContainmentPairByteSize : Nat := 48

/-- Parse exactly one complete 48-byte RealDisk106 containment frame. -/
def parseRawContainmentPair
    (input : List UInt8) : Option RawContainmentPair :=
  ComplexDisk.Wire.parseExact rawContainmentPairByteSize
    readRawContainmentPair input

theorem parseRawContainmentPair_length
    {input : List UInt8} {raw : RawContainmentPair}
    (hparse : parseRawContainmentPair input = some raw) :
    input.length = rawContainmentPairByteSize :=
  ComplexDisk.Wire.parseExact_length hparse

/-! ## Byte-to-arithmetic composition -/

/-- Strict framing, finite exact `hi + lo` decoding, radius checks, and the
exact squared-distance containment inequality in one Boolean. -/
def checkRawContainmentBytes (input : List UInt8) : Bool :=
  match parseRawContainmentPair input with
  | none => false
  | some raw => raw.check

/-- The named raw words and generic rational certificate recovered from
accepted bytes. -/
def ValidatedRawContainmentBytes (input : List UInt8) : Prop :=
  ∃ raw : RawContainmentPair,
    ∃ certificate : ComplexDisk.ContainmentCertificate,
      parseRawContainmentPair input = some raw ∧
      raw.decode = some certificate ∧
      certificate.WellFormed

theorem checkRawContainmentBytes_sound {input : List UInt8}
    (hcheck : checkRawContainmentBytes input = true) :
    ValidatedRawContainmentBytes input := by
  unfold checkRawContainmentBytes at hcheck
  cases hparse : parseRawContainmentPair input with
  | none => simp [hparse] at hcheck
  | some raw =>
      rcases RawContainmentPair.check_sound (by
          simpa [hparse] using hcheck) with
        ⟨certificate, hdecode, hwellFormed⟩
      exact ⟨raw, certificate, hparse, hdecode, hwellFormed⟩

theorem checkRawContainmentBytes_length {input : List UInt8}
    (hcheck : checkRawContainmentBytes input = true) :
    input.length = rawContainmentPairByteSize := by
  rcases checkRawContainmentBytes_sound hcheck with
    ⟨raw, _, hparse, _, _⟩
  exact parseRawContainmentPair_length hparse

/-- End-to-end semantic theorem for a named parse and decode.  Every value in
the decoded inner disk is in the decoded outer disk. -/
theorem checkedBytes_outer_contains
    {input : List UInt8}
    {raw : RawContainmentPair}
    {certificate : ComplexDisk.ContainmentCertificate}
    {value : ℂ}
    (hcheck : checkRawContainmentBytes input = true)
    (hparse : parseRawContainmentPair input = some raw)
    (hdecode : raw.decode = some certificate)
    (hvalue : certificate.inner.ContainsComplex value) :
    certificate.outer.ContainsComplex value := by
  have hraw : raw.check = true := by
    unfold checkRawContainmentBytes at hcheck
    simpa [hparse] using hcheck
  exact
    RawContainmentPair.outer_contains_of_inner_contains
      hraw hdecode hvalue

/-- An accepted frame existentially exposes both the generic well-formedness
proof and its semantic containment consequence for every complex value. -/
theorem checkRawContainmentBytes_semantic {input : List UInt8}
    (hcheck : checkRawContainmentBytes input = true) :
    ∃ raw : RawContainmentPair,
      ∃ certificate : ComplexDisk.ContainmentCertificate,
        parseRawContainmentPair input = some raw ∧
        raw.decode = some certificate ∧
        certificate.WellFormed ∧
        ∀ value : ℂ,
          certificate.inner.ContainsComplex value →
          certificate.outer.ContainsComplex value := by
  rcases checkRawContainmentBytes_sound hcheck with
    ⟨raw, certificate, hparse, hdecode, hwellFormed⟩
  refine ⟨raw, certificate, hparse, hdecode, hwellFormed, ?_⟩
  intro value hvalue
  exact checkedBytes_outer_contains hcheck hparse hdecode hvalue

/-! ## Fixed-cardinality streams of independent containment frames -/

/-- Check an explicitly framed transform output.  The caller supplies one
48-byte `inner || outer` frame per transform sample; the cardinality check
prevents a valid prefix or suffix from being mistaken for a complete
transform. -/
def checkRawContainmentByteFrames
    (expectedCount : Nat) (frames : List (List UInt8)) : Bool :=
  decide (frames.length = expectedCount) &&
    frames.all checkRawContainmentBytes

/-- Acceptance fixes the exact frame count and validates every named frame.
This theorem is intentionally independent of hashes and run provenance: those
belong to the authenticated artifact layer that supplies `frames`. -/
theorem checkRawContainmentByteFrames_sound
    {expectedCount : Nat} {frames : List (List UInt8)}
    (hcheck : checkRawContainmentByteFrames expectedCount frames = true) :
    frames.length = expectedCount ∧
      ∀ frame ∈ frames, ValidatedRawContainmentBytes frame := by
  simp only [checkRawContainmentByteFrames, Bool.and_eq_true,
    decide_eq_true_eq] at hcheck
  refine ⟨hcheck.1, ?_⟩
  intro frame hframe
  exact checkRawContainmentBytes_sound
    ((List.all_eq_true.mp hcheck.2) frame hframe)

/-- Every accepted frame has the generic exact-rational containment
consequence.  This is the list-level theorem needed by a transform candidate:
the physical producer may widen every output disk independently, without
requiring byte identity with the reference transform. -/
theorem checkRawContainmentByteFrames_semantic
    {expectedCount : Nat} {frames : List (List UInt8)}
    (hcheck : checkRawContainmentByteFrames expectedCount frames = true) :
    frames.length = expectedCount ∧
      ∀ frame ∈ frames,
        ∃ raw : RawContainmentPair,
          ∃ certificate : ComplexDisk.ContainmentCertificate,
            parseRawContainmentPair frame = some raw ∧
            raw.decode = some certificate ∧
            certificate.WellFormed ∧
            ∀ value : ℂ,
              certificate.inner.ContainsComplex value →
              certificate.outer.ContainsComplex value := by
  refine ⟨(checkRawContainmentByteFrames_sound hcheck).1, ?_⟩
  intro frame hframe
  have hpairs :
      frames.length = expectedCount ∧
        frames.all checkRawContainmentBytes = true := by
    simpa only [checkRawContainmentByteFrames, Bool.and_eq_true,
      decide_eq_true_eq] using hcheck
  have hframes :
      frames.all checkRawContainmentBytes = true := by
    exact hpairs.2
  exact checkRawContainmentBytes_semantic
    ((List.all_eq_true.mp hframes) frame hframe)

/-! ## Flat raw artifacts -/

/-- Split a headerless containment artifact into its canonical 48-byte
frames.  The frame checker rejects a short terminal chunk because parsing is
exact, and `expectedCount` rejects both prefixes and appended complete
frames. -/
def rawContainmentArtifactFrames
    (input : List UInt8) : List (List UInt8) :=
  input.toChunks rawContainmentPairByteSize

/-- Check the exact flat byte stream emitted by the PT21 live qualifier. -/
def checkRawContainmentArtifactBytes
    (expectedCount : Nat) (input : List UInt8) : Bool :=
  checkRawContainmentByteFrames expectedCount
    (rawContainmentArtifactFrames input)

/-- Soundness of the flat artifact checker.  The resulting named frames are
definitionally the consecutive chunks of the supplied byte stream. -/
theorem checkRawContainmentArtifactBytes_sound
    {expectedCount : Nat} {input : List UInt8}
    (hcheck :
      checkRawContainmentArtifactBytes expectedCount input = true) :
    (rawContainmentArtifactFrames input).length = expectedCount ∧
      ∀ frame ∈ rawContainmentArtifactFrames input,
        ValidatedRawContainmentBytes frame :=
  checkRawContainmentByteFrames_sound hcheck

/-- Every frame in an accepted flat artifact has the exact-rational
containment consequence. -/
theorem checkRawContainmentArtifactBytes_semantic
    {expectedCount : Nat} {input : List UInt8}
    (hcheck :
      checkRawContainmentArtifactBytes expectedCount input = true) :
    (rawContainmentArtifactFrames input).length = expectedCount ∧
      ∀ frame ∈ rawContainmentArtifactFrames input,
        ∃ raw : RawContainmentPair,
          ∃ certificate : ComplexDisk.ContainmentCertificate,
            parseRawContainmentPair frame = some raw ∧
            raw.decode = some certificate ∧
            certificate.WellFormed ∧
            ∀ value : ℂ,
              certificate.inner.ContainsComplex value →
              certificate.outer.ContainsComplex value :=
  checkRawContainmentByteFrames_semantic hcheck

end SparkInterval.Certified.ComplexDisk.Containment.Wire
