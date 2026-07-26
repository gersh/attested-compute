/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Tiny KATs for the 120-byte Sqrt218 V2 result envelope

These checks construct 120 bytes in memory.  They do not import, open, hash,
decode, or replay a production certificate.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.Sqrt218V2ResultWire

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

private def be (width value : Nat) : List UInt8 :=
  (List.range width).map fun index =>
    UInt8.ofNat ((value / 256 ^ (width - (index + 1))) % 256)

private def digestBytes : List UInt8 :=
  (List.range 32).map UInt8.ofNat

private def acceptedBytes : ByteArray :=
  (nativeResultMagic ++
    be 2 nativeResultVersion ++
    be 2 nativeResultByteWidth ++
    be 4 0 ++
    be 8 160 ++
    be 8 1 ++
    be 8 2 ++
    be 8 3 ++
    be 8 4 ++
    be 8 5 ++
    be 8 6 ++
    be 8 7 ++
    be 8 8 ++
    digestBytes).toByteArray

private def expected : NativeResultRecord := {
  status := 0
  inputByteLength := 160
  nextEventIndex := 1
  lastEventValue := 2
  weightedUpper := ⟨3, 4⟩
  psiLower := ⟨5, 6⟩
  anchorSlack := ⟨7, 8⟩
  inputSHA256 := byteArrayLowerHex digestBytes.toByteArray
}

private def rejected {α : Type} (value : Except String α) : Bool :=
  match value with
  | .error _ => true
  | .ok _ => false

#guard acceptedBytes.size = 120
#guard decodeNativeResultBytes acceptedBytes = .ok expected
#guard acceptedResultCheck expected
#guard
  decodeResultEnvelope (encodeResultEnvelope acceptedBytes) =
    .ok (acceptedBytes, expected)
#guard
  rejected (decodeResultEnvelope
      ("sparkinterval.sqrt218-fixed-v2-result.v1:" ++
        "00"))
#guard
  rejected (decodeResultEnvelope
      ("sparkinterval.sqrt218-fixed-v2-result.v1:" ++
        String.ofList
          (List.replicate 239 '0' ++ ['A'])))

end SparkInterval.Tests.Sqrt218V2ResultWire
