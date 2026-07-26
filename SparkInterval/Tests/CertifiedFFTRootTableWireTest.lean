/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedFFTRootTableWire

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedFFTRootTableWireTest

open SparkInterval.Dirichlet.CertifiedFFTRootTableWire

def encodeU64LE (word : Nat) : List UInt8 :=
  (List.range 8).map fun index =>
    UInt8.ofNat ((word / 256 ^ index) % 256)

def encodeBox (reLo reHi imLo imHi : Nat) : List UInt8 :=
  encodeU64LE reLo ++ encodeU64LE reHi ++
    encodeU64LE imLo ++ encodeU64LE imHi

def positiveOne : Nat := 0x3ff0000000000000
def positiveInfinity : Nat := 0x7ff0000000000000
def positiveZero : Nat := 0x0000000000000000
def positiveI : List UInt8 :=
  encodeBox positiveZero positiveZero positiveOne positiveOne
def one : List UInt8 :=
  encodeBox positiveOne positiveOne positiveZero positiveZero

/- For length four the flattened source order is
`(stage, exponent) = (2,0), (4,0), (4,1)`. -/
def lengthFourFixture : ByteArray :=
  (one ++ one ++ positiveI).toByteArray

#guard sourceConvolution 4
#guard sourceConvolution (2 ^ 20)
#guard !(sourceConvolution 2)
#guard !(sourceConvolution 12)
#guard !(sourceConvolution (2 ^ 21))

#guard specAtFlatIndex 0 = { stage := 2, exponent := 0 }
#guard specAtFlatIndex 1 = { stage := 4, exponent := 0 }
#guard specAtFlatIndex 2 = { stage := 4, exponent := 1 }
#guard specAtFlatIndex 3 = { stage := 8, exponent := 0 }
#guard specAtFlatIndex 6 = { stage := 8, exponent := 3 }
#guard specAtFlatIndex (2 ^ 20 - 2) =
  { stage := 2 ^ 20, exponent := 2 ^ 19 - 1 }

example
    {stageExponent exponent : Nat}
    (hexponent : exponent < 2 ^ stageExponent) :
    specAtFlatIndex
        (2 ^ (stageExponent + 1) / 2 - 1 + exponent) =
      { stage := 2 ^ (stageExponent + 1), exponent } :=
  specAtFlatIndex_source_order hexponent

#guard readU64LE?
  ([0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01] :
    List UInt8).toByteArray 0 = some 0x0102030405060708

#guard checkPositiveDump 192 128 4 lengthFourFixture

/- Exact byte length is mandatory. -/
#guard
  !(checkPositiveDump 192 128 4
    (lengthFourFixture.toList.dropLast.toByteArray))

#guard
  !(checkPositiveDump 192 128 4
    (lengthFourFixture.toList ++ [0]).toByteArray)

/- Unsupported geometry is rejected even if the supplied bytes are empty. -/
#guard !(checkPositiveDump 192 128 2 ByteArray.empty)
#guard !(checkPositiveDump 192 128 12 ByteArray.empty)

/- A finite but mathematically wrong first root is rejected. -/
def wrongFirstRoot : ByteArray :=
  (positiveI ++ (lengthFourFixture.toList.drop recordBytes)).toByteArray

#guard
  firstFailure? 192 128 4 wrongFirstRoot =
    some
      { flatIndex := 0
        stage := 2
        exponent := 0
        kind := .root }

/- A non-finite raw binary64 endpoint fails closed. -/
def nonFiniteFirstRoot : ByteArray :=
  (encodeBox positiveInfinity positiveInfinity positiveZero positiveZero ++
    (lengthFourFixture.toList.drop recordBytes)).toByteArray

#guard
  firstFailure? 192 128 4 nonFiniteFirstRoot =
    some
      { flatIndex := 0
        stage := 2
        exponent := 0
        kind := .root }

example
    {workPrecision outputPrecision : Nat}
    {spec : RootSpec} {root : SparkInterval.Dirichlet.CertifiedRootWire.RawComplexBox}
    (hcheck :
      checkPositiveRoot workPrecision outputPrecision spec root = true) :
    ∃ (outer : SparkInterval.Certified.ComplexRect)
        (hvalid : outer.IsValid),
      root.decodeFinite = some outer ∧
      (SparkInterval.Dirichlet.CertifiedRootWire.toComplexInterval
        outer hvalid).Contains
        (SparkInterval.Dirichlet.FactoredSmallQDFT.unitRoot
          spec.stage spec.exponent) :=
  checkPositiveRoot_sound hcheck

example
    {workPrecision outputPrecision length index : Nat}
    {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    (hindex : index < length - 1) :
    ∃ root : SparkInterval.Dirichlet.CertifiedRootWire.RawComplexBox,
      readRoot? raw index = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (SparkInterval.Dirichlet.CertifiedRootWire.toComplexInterval
          outer hvalid).Contains
          (SparkInterval.Dirichlet.FactoredSmallQDFT.unitRoot
            (specAtFlatIndex index).stage
            (specAtFlatIndex index).exponent) :=
  checkPositiveDump_root_containments hcheck hindex

example
    {workPrecision outputPrecision length : Nat}
    {raw : ByteArray}
    (hcheck :
      checkPositiveDump workPrecision outputPrecision length raw = true)
    {stageExponent exponent : Nat}
    (hstage : 2 ^ (stageExponent + 1) ≤ length)
    (hexponent : exponent < 2 ^ stageExponent) :
    ∃ root : SparkInterval.Dirichlet.CertifiedRootWire.RawComplexBox,
      readRoot? raw (2 ^ stageExponent - 1 + exponent) = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (SparkInterval.Dirichlet.CertifiedRootWire.toComplexInterval
          outer hvalid).Contains
          (SparkInterval.Dirichlet.FactoredSmallQDFT.unitRoot
            (2 ^ (stageExponent + 1)) exponent) :=
  checkPositiveDump_source_stage_root_containment
    hcheck hstage hexponent

#print axioms checkPositiveRoot_sound
#print axioms stageOffset_add_exponent
#print axioms stageOffset_eq_stage_div_two_sub_one
#print axioms specAtFlatIndex_source_order
#print axioms checkPositiveDump_geometry
#print axioms checkPositiveDump_root_containments
#print axioms checkPositiveDump_source_stage_root_containment

end SparkInterval.Tests.CertifiedFFTRootTableWireTest
