/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDiskWire
import SparkInterval.Zeta.PlattDiskPipeline

/-!
# Canonical wire certificate for Platt's exceptional Hermitian endpoint

The CUDA disk runner exports one compact 320-byte certificate for index zero
of the literal upstream `hermidft` preprocessing.  The frame is

```
leftInput (24) || rightInput (24) ||
leftMul (96) || rightMul (96) || outputAdd (80)
```

Every binary64 word is little endian and is decoded to an exact rational by
`ComplexDisk.Wire`.  Successful `checkBytes` proves framing, finite decoding,
all multiplication/addition inequalities, and all linking equalities required
by `HermidftEndpointCertificate`.  It does not prove that a physical CUDA
kernel emitted the bytes, nor does one endpoint certificate cover the FFT.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PlattDiskPipeline.Wire

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk.Wire
open SparkInterval.Zeta.PlattDiskPipeline

/-- Raw binary64 frame before exact-rational decoding. -/
structure RawEndpointCertificate where
  leftInput : ComplexDisk.Raw
  rightInput : ComplexDisk.Raw
  leftMul : ComplexDisk.RawMulCertificate
  rightMul : ComplexDisk.RawMulCertificate
  outputAdd : ComplexDisk.RawAddCertificate
  deriving Repr, DecidableEq, BEq

namespace RawEndpointCertificate

def decode (raw : RawEndpointCertificate) :
    Option HermidftEndpointCertificate := do
  let leftInput ← raw.leftInput.decode
  let rightInput ← raw.rightInput.decode
  let leftMul ← raw.leftMul.decode
  let rightMul ← raw.rightMul.decode
  let outputAdd ← raw.outputAdd.decode
  pure { leftInput, rightInput, leftMul, rightMul, outputAdd }

/-- Exact arithmetic and link check after finite binary64 decoding. -/
def check (raw : RawEndpointCertificate) : Bool :=
  match raw.decode with
  | none => false
  | some certificate => certificate.check

def Validated (raw : RawEndpointCertificate) : Prop :=
  ∃ certificate : HermidftEndpointCertificate,
    raw.decode = some certificate ∧ certificate.IsValid

theorem check_sound {raw : RawEndpointCertificate}
    (hcheck : raw.check = true) : raw.Validated := by
  unfold check at hcheck
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some certificate =>
      exact ⟨certificate, hdecode,
        HermidftEndpointCertificate.check_eq_true.mp (by
          simpa [hdecode] using hcheck)⟩

end RawEndpointCertificate

/-- Consume the canonical 80-byte raw disk-addition witness. -/
def readRawAddCertificate (input : List UInt8) :
    Option (ComplexDisk.RawAddCertificate × List UInt8) := do
  let (left, rest) ← readRaw input
  let (right, rest) ← readRaw rest
  let (output, rest) ← readRaw rest
  let (centerErrorBoundBits, rest) ← readCanonicalBinary64LE rest
  pure ({ left, right, output, centerErrorBoundBits }, rest)

/-- Consume one endpoint certificate, retaining the suffix for exact framing. -/
def readRawEndpointCertificate (input : List UInt8) :
    Option (RawEndpointCertificate × List UInt8) := do
  let (leftInput, rest) ← readRaw input
  let (rightInput, rest) ← readRaw rest
  let (leftMul, rest) ← readRawMulCertificate rest
  let (rightMul, rest) ← readRawMulCertificate rest
  let (outputAdd, rest) ← readRawAddCertificate rest
  pure ({ leftInput, rightInput, leftMul, rightMul, outputAdd }, rest)

def endpointCertificateByteSize : Nat := 320

/-- Parse exactly one complete endpoint frame; truncation and suffixes fail. -/
def parse (input : List UInt8) : Option RawEndpointCertificate :=
  parseExact endpointCertificateByteSize readRawEndpointCertificate input

theorem parse_length {input : List UInt8} {raw : RawEndpointCertificate}
    (hparse : parse input = some raw) :
    input.length = endpointCertificateByteSize :=
  parseExact_length hparse

/-- Single fail-closed byte-level checker used by exported CUDA candidates. -/
def checkBytes (input : List UInt8) : Bool :=
  match parse input with
  | none => false
  | some raw => raw.check

def ValidatedBytes (input : List UInt8) : Prop :=
  ∃ raw : RawEndpointCertificate,
    parse input = some raw ∧ raw.Validated

theorem checkBytes_sound {input : List UInt8}
    (hcheck : checkBytes input = true) : ValidatedBytes input := by
  unfold checkBytes at hcheck
  cases hparse : parse input with
  | none => simp [hparse] at hcheck
  | some raw =>
      exact ⟨raw, hparse, RawEndpointCertificate.check_sound (by
        simpa [hparse] using hcheck)⟩

theorem checkBytes_length {input : List UInt8}
    (hcheck : checkBytes input = true) :
    input.length = endpointCertificateByteSize := by
  rcases checkBytes_sound hcheck with ⟨raw, hparse, _⟩
  exact parse_length hparse

/-- Arithmetic application of one accepted byte frame.  Physical provenance
of `input` remains a separate execution/refinement obligation. -/
theorem checkedBytes_output_contains
    {input : List UInt8} {raw : RawEndpointCertificate}
    {certificate : HermidftEndpointCertificate} {left right : ℂ}
    (hcheck : checkBytes input = true)
    (hparse : parse input = some raw)
    (hdecode : raw.decode = some certificate)
    (hleft : certificate.leftInput.ContainsComplex left)
    (hright : certificate.rightInput.ContainsComplex right) :
    certificate.outputAdd.output.ContainsComplex
      (hermidftEndpoint left right) := by
  have hraw : raw.check = true := by
    unfold checkBytes at hcheck
    simpa [hparse] using hcheck
  have hcertificate : certificate.check = true := by
    unfold RawEndpointCertificate.check at hraw
    simpa [hdecode] using hraw
  exact certificate.output_contains hcertificate hleft hright

end SparkInterval.Zeta.PlattDiskPipeline.Wire
