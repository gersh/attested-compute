/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPureEntryComposition

/-!
Known-answer and trust-boundary tests for the pure Sqrt218 C SHA-256 model.
These executable guards create no theorem and introduce no native-evaluation
axiom.  The symbolic declarations printed below remain the proof authority.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CSHA256Refinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

private def nonUTF8 : ByteArray :=
  ([0x00, 0x80, 0xff, 0xfe, 0x41] : List UInt8).toByteArray

#guard
  byteArrayLowerHex (cDigestByteArray ByteArray.empty) =
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#guard
  byteArrayLowerHex (cDigestByteArray "abc".toUTF8) =
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

#guard
  byteArrayLowerHex
      (cDigestByteArray
        (String.ofList (List.replicate 56 'a')).toUTF8) =
    "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a"

#guard
  byteArrayLowerHex
      (cDigestByteArray
        (String.ofList (List.replicate 64 'a')).toUTF8) =
    "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"

#guard
  byteArrayLowerHex (cDigestByteArray nonUTF8) =
    "9c1331e828ee11c2078baec74b31e32713cda32649a2de28a1b8324f05900f55"

#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement.cReadWord_toNat
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement.cDigestByteArray_refines
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPureEntryComposition.CSuccessfulPureEntryTrace.sha256Correct

end SparkInterval.Tests.CSHA256Refinement
