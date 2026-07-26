/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire
import SparkInterval.Zeta.PT21EventWire

/-!
# Cross-language tests for the compact PT21 event-stage wire

`reference/tg_platt_event_record_kat.cpp` produced the literal record below.
The independent Lean checker therefore fixes magic, widths, little-endian
signed weights, finite-stage invariants, and domain-separated SHA-256 without
sharing an encoder with C++.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.PT21EventWire

open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire
open SparkInterval.Zeta.PT21EventWire

private def cppFixtureHex : String :=
  "505432314556543101000000c00000000700000000000000000000008d640000010000000000000002000000030000000100000000000000010000000000000002000000030000000100000001000000fbffffffffffffffe2ffffffffffffffffffffffffffffff0400000000000000280000000000000000000000000000003333333333333333333333333333333333333333333333333333333333333333d4a997e4b8644bab07c97035f57ecce362c297ec378b26871fb31461e6276ba1"

private def cppFixture : ByteArray :=
  (decodeLowerHex cppFixtureHex).getD ByteArray.empty

#guard cppFixture.size = eventRecordBytes
#guard checkBytes cppFixture

private def parsedFixture : Option EventRecord :=
  parse cppFixture

#guard parsedFixture.map EventRecord.block = some 7
#guard parsedFixture.map EventRecord.certifiedSampleCount = some 25_741
#guard parsedFixture.map EventRecord.mainDirectCount = some 3
#guard parsedFixture.map EventRecord.mainStationaryCount = some 1
#guard parsedFixture.map EventRecord.unresolvedStationaryCount = some 1
#guard parsedFixture.map EventRecord.leftNleftUnits = some (-5)
#guard parsedFixture.map EventRecord.mainNrightUnits = some 40

#guard
  SparkInterval.Zeta.PT21EventWire.byteArrayLowerHex
      (cppFixture.extract recordDigestOffset eventRecordBytes) ==
    "d4a997e4b8644bab07c97035f57ecce362c297ec378b26871fb31461e6276ba1"

/- Framing, finite counts, pending-stationary accounting, and the digest all
fail closed under one-byte mutation. -/
#guard checkBytes (cppFixture.set! 0 0) = false
#guard checkBytes (cppFixture.set! 24 1) = false
#guard checkBytes (cppFixture.set! 76 0) = false
#guard checkBytes (cppFixture.set! 191 0) = false
#guard checkBytes ((cppFixture.toList ++ [0]).toByteArray) = false

example (hcheck : checkBytes cppFixture = true) :
    cppFixture.size = eventRecordBytes :=
  checkBytes_size hcheck

end SparkInterval.Tests.PT21EventWire
