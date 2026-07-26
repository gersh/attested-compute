/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedChirpStateWire

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedChirpStateWireTest

open SparkInterval.Dirichlet.CertifiedChirpStateWire

def encodeU64LE (word : Nat) : List UInt8 :=
  (List.range 8).map fun index =>
    UInt8.ofNat ((word / 256 ^ index) % 256)

def encodeBox (reLo reHi imLo imHi : Nat) : List UInt8 :=
  encodeU64LE reLo ++ encodeU64LE reHi ++
    encodeU64LE imLo ++ encodeU64LE imHi

def positiveOne : Nat := 0x3ff0000000000000
def negativeOne : Nat := 0xbff0000000000000
def positiveZero : Nat := 0x0000000000000000

def axisBox (re im : Nat) : List UInt8 :=
  encodeBox re re im im

/- Length two has exact states
`c₀ = 1`, `d₀ = i`, `c₁ = i`, and `d₁ = -i`. -/
def lengthTwoFixture : ByteArray :=
  (axisBox positiveOne positiveZero ++
    axisBox positiveZero positiveOne ++
    axisBox positiveZero positiveOne ++
    axisBox positiveZero negativeOne).toByteArray

#guard readU64LE?
  ([0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01] :
    List UInt8).toByteArray 0 = some 0x0102030405060708

#guard checkPositiveDump 160 80 2 lengthTwoFixture

/- Exact byte length is mandatory. -/
#guard
  !(checkPositiveDump 160 80 2
    (lengthTwoFixture.toList.dropLast.toByteArray))

#guard
  !(checkPositiveDump 160 80 2
    (lengthTwoFixture.toList ++ [0]).toByteArray)

#guard !(checkPositiveDump 160 80 0 ByteArray.empty)

/- A valid but wrong singleton is rejected at the first chirp. -/
def wrongFirstChirp : ByteArray :=
  (axisBox positiveZero positiveZero ++
    (lengthTwoFixture.toList.drop (2 * complexBoxBytes))).toByteArray

#guard
  firstFailure? 160 80 2 wrongFirstChirp =
    some { index := 0, kind := .chirp }

example
    {workPrecision outputPrecision length index : Nat}
    {row : RawChirpStateRow}
    (hcheck :
      checkPositiveRow workPrecision outputPrecision length index row = true) :
    ∃ (outer : SparkInterval.Certified.ComplexRect)
        (hvalid : outer.IsValid),
      row.chirp.decodeFinite = some outer ∧
      (SparkInterval.Dirichlet.CertifiedRootWire.toComplexInterval
        outer hvalid).Contains
        (SparkInterval.Dirichlet.FactoredSmallQDFT.unitRoot
          (2 * length) (index ^ 2)) :=
  checkPositiveRow_chirp_sound hcheck

example
    {workPrecision outputPrecision length index : Nat}
    {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    (hindex : index < length) :
    ∃ row : RawChirpStateRow,
      readRow? raw index = some row ∧
      (∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        row.chirp.decodeFinite = some outer ∧
        (SparkInterval.Dirichlet.CertifiedRootWire.toComplexInterval
          outer hvalid).Contains
          (SparkInterval.Dirichlet.FactoredSmallQDFT.unitRoot
            (2 * length) (index ^ 2))) ∧
      (∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        row.oddStep.decodeFinite = some outer ∧
        (SparkInterval.Dirichlet.CertifiedRootWire.toComplexInterval
          outer hvalid).Contains
          (SparkInterval.Dirichlet.FactoredSmallQDFT.unitRoot
            (2 * length) (2 * index + 1))) :=
  checkPositiveDump_root_containments hcheck hindex

#print axioms checkPositiveRow_chirp_sound
#print axioms checkPositiveRow_oddStep_sound
#print axioms checkPositiveDump_root_containments

end SparkInterval.Tests.CertifiedChirpStateWireTest
