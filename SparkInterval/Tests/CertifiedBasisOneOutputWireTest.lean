/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedBasisOneOutputWire

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedBasisOneOutputWireTest

open SparkInterval.Dirichlet.CertifiedBasisOneOutputWire

def encodeLE (width word : Nat) : List UInt8 :=
  (List.range width).map fun index =>
    UInt8.ofNat ((word / 256 ^ index) % 256)

def encodeU32LE (word : Nat) : List UInt8 :=
  encodeLE 4 word

def encodeU64LE (word : Nat) : List UInt8 :=
  encodeLE 8 word

def encodeBox (reLo reHi imLo imHi : Nat) : List UInt8 :=
  encodeU64LE reLo ++ encodeU64LE reHi ++
    encodeU64LE imLo ++ encodeU64LE imHi

def positiveOne : Nat := 0x3ff0000000000000
def negativeOne : Nat := 0xbff0000000000000
def positiveZero : Nat := 0x0000000000000000
def positiveInfinity : Nat := 0x7ff0000000000000

def axisBox (re im : Nat) : List UInt8 :=
  encodeBox re re im im

/- The positive DFT of basis one at order two is `[1, -1]`. -/
def orderTwoPayload : ByteArray :=
  (axisBox positiveOne positiveZero ++
    axisBox negativeOne positiveZero).toByteArray

def encodeHeader
    (magic : ByteArray) (version q componentCount batchCount
      groupOrder valueCount butterflies elapsed : Nat) : List UInt8 :=
  magic.toList ++
    encodeU32LE version ++
    encodeU32LE q ++
    encodeU32LE componentCount ++
    encodeU32LE batchCount ++
    encodeU64LE groupOrder ++
    encodeU64LE valueCount ++
    encodeU64LE butterflies ++
    encodeU64LE elapsed

def sampleArtifact (elapsed : Nat := 123) : ByteArray :=
  (encodeHeader outputMagic 1 3 1 1 2 2 7 elapsed ++
    orderTwoPayload.toList).toByteArray

def headerOffsetProbe : ByteArray :=
  (encodeHeader outputMagic 2 3 4 5 6 7 8 9).toByteArray

#guard outputMagic.size = 8
#guard headerBytes = 56
#guard recordBytes = 32
#guard productionArtifactBytes = 12799672
#guard readHeader? headerOffsetProbe =
  some
    { version := 2
      q := 3
      componentCount := 4
      batchCount := 5
      groupOrder := 6
      valueCount := 7
      radix2Butterflies := 8
      elapsedNanoseconds := 9 }

#guard readU64LE?
  ([0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01] :
    List UInt8).toByteArray 0 = some 0x0102030405060708

#guard checkPositivePayload 160 80 2 orderTwoPayload
#guard checkArtifact 160 80 3 2 7 (sampleArtifact 123)
/- Elapsed nanoseconds is parsed but deliberately not pinned. -/
#guard checkArtifact 160 80 3 2 7 (sampleArtifact 987654321)

/- Exact size is mandatory for both layers. -/
#guard
  !(checkPositivePayload 160 80 2
    orderTwoPayload.toList.dropLast.toByteArray)
#guard
  !(checkPositivePayload 160 80 2
    (orderTwoPayload.toList ++ [0]).toByteArray)
#guard
  !(checkArtifact 160 80 3 2 7
    (sampleArtifact 123).toList.dropLast.toByteArray)
#guard
  !(checkArtifact 160 80 3 2 7
    ((sampleArtifact 123).toList ++ [0]).toByteArray)

/- Basis one is unavailable at orders zero and one. -/
#guard !(checkPositivePayload 160 80 0 ByteArray.empty)
#guard
  !(checkPositivePayload 160 80 1
    (axisBox positiveOne positiveZero).toByteArray)

/- A wrong but finite row, non-finite endpoint, and reversed interval fail. -/
def wrongFinitePayload : ByteArray :=
  (axisBox positiveZero positiveZero ++
    axisBox negativeOne positiveZero).toByteArray

def nonfinitePayload : ByteArray :=
  (encodeBox positiveOne positiveInfinity positiveZero positiveZero ++
    axisBox negativeOne positiveZero).toByteArray

def reversedPayload : ByteArray :=
  (encodeBox positiveOne positiveZero positiveZero positiveZero ++
    axisBox negativeOne positiveZero).toByteArray

#guard
  firstPayloadFailure? 160 80 2 wrongFinitePayload =
    some { index := 0, kind := .root }
#guard !(checkPositivePayload 160 80 2 nonfinitePayload)
#guard !(checkPositivePayload 160 80 2 reversedPayload)

/- Every stable header field is checked, including magic. -/
def badMagic : ByteArray :=
  (encodeHeader "TGDAFFX1".toUTF8 1 3 1 1 2 2 7 123 ++
    orderTwoPayload.toList).toByteArray

def badVersion : ByteArray :=
  (encodeHeader outputMagic 2 3 1 1 2 2 7 123 ++
    orderTwoPayload.toList).toByteArray

def badQ : ByteArray :=
  (encodeHeader outputMagic 1 5 1 1 2 2 7 123 ++
    orderTwoPayload.toList).toByteArray

def badComponentCount : ByteArray :=
  (encodeHeader outputMagic 1 3 2 1 2 2 7 123 ++
    orderTwoPayload.toList).toByteArray

def badBatchCount : ByteArray :=
  (encodeHeader outputMagic 1 3 1 2 2 2 7 123 ++
    orderTwoPayload.toList).toByteArray

def badGroupOrder : ByteArray :=
  (encodeHeader outputMagic 1 3 1 1 4 2 7 123 ++
    orderTwoPayload.toList).toByteArray

def badValueCount : ByteArray :=
  (encodeHeader outputMagic 1 3 1 1 2 4 7 123 ++
    orderTwoPayload.toList).toByteArray

def badButterflies : ByteArray :=
  (encodeHeader outputMagic 1 3 1 1 2 2 8 123 ++
    orderTwoPayload.toList).toByteArray

#guard !(checkArtifact 160 80 3 2 7 badMagic)
#guard !(checkArtifact 160 80 3 2 7 badVersion)
#guard !(checkArtifact 160 80 3 2 7 badQ)
#guard !(checkArtifact 160 80 3 2 7 badComponentCount)
#guard !(checkArtifact 160 80 3 2 7 badBatchCount)
#guard !(checkArtifact 160 80 3 2 7 badGroupOrder)
#guard !(checkArtifact 160 80 3 2 7 badValueCount)
#guard !(checkArtifact 160 80 3 2 7 badButterflies)

example
    {workPrecision outputPrecision order : Nat} {raw : ByteArray}
    (hcheck :
      checkPositivePayload
        workPrecision outputPrecision order raw = true)
    (frequency : Fin order) :
    ∃ root : SparkInterval.Dirichlet.CertifiedRootWire.RawComplexBox,
      readPayloadRoot? raw frequency.val = some root ∧
      ∃ (outer : SparkInterval.Certified.ComplexRect)
          (hvalid : outer.IsValid),
        root.decodeFinite = some outer ∧
        (SparkInterval.Dirichlet.CertifiedRootWire.toComplexInterval
          outer hvalid).Contains
          (SparkInterval.Dirichlet.BluesteinDFT.positiveDFT order
            (SparkInterval.Dirichlet.BluesteinDFT.basisVector
              ⟨1, (checkPositivePayload_geometry hcheck).1⟩)
            frequency) :=
  checkPositivePayload_basisOne_dft_containments hcheck frequency

example
    {workPrecision outputPrecision : Nat} {raw : ByteArray}
    (hcheck :
      checkMaximumOrderDeltaOneArtifact
        workPrecision outputPrecision raw = true) :
    magicMatches raw = true ∧
      raw.size = 12799672 ∧
      ∃ header : OutputHeader,
        readHeader? raw = some header ∧
        header.version = 1 ∧
        header.q = 399989 ∧
        header.componentCount = 1 ∧
        header.batchCount = 1 ∧
        header.groupOrder = 399988 ∧
        header.valueCount = 399988 ∧
        header.radix2Butterflies = 31457280 :=
  checkMaximumOrderDeltaOneArtifact_header hcheck

#print axioms checkPositiveRow_sound
#print axioms checkPositivePayload_root_containments
#print axioms checkPositivePayload_basisOne_dft_containments
#print axioms readHeader?_magic
#print axioms checkArtifact_basisOne_dft_containments
#print axioms checkMaximumOrderDeltaOneArtifact_header
#print axioms checkMaximumOrderDeltaOneArtifact_basisOne_dft_containments

end SparkInterval.Tests.CertifiedBasisOneOutputWireTest
