/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21NativeBlockWire
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Cross-language PT21 native block wire tests

`python -m tg_verifier.platt_pt21_native_finalizer` uses
`encode_block_record` to produce the 320-byte fixture below.  Keeping the
fixture as literal lowercase hexadecimal makes this test independent of a
second Lean encoder and catches field-order, endianness, width, and digest
disagreements between the Python producer and the Lean checker.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.PT21NativeBlockWire

open SparkInterval.Zeta.PT21NativeBlockWire
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

private def pythonFixtureHex : String :=
  "50543231424c4b3101000000400100000000000000000000eb4e1b7b07000000ee4e1b7b0700000003000000000000000000000000000000000000000000000000000000000000000000000000000000ffffffffffffffff1111111111111111111111111111111111111111111111111111111111111111222222222222222222222222222222222222222222222222222222222222222233333333333333333333333333333333333333333333333333333333333333330000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000044444444444444444444444444444444444444444444444444444444444444440000000000000000a8d2f4218b1f8871363dca585fb5583bce843b0b41465d1e229316837952edd8"

private def pythonFixture : ByteArray :=
  (decodeLowerHex pythonFixtureHex).getD ByteArray.empty

#guard pythonFixture.size = 320
#guard checkBytes pythonFixture

private def parsedFixture : Option BlockRecord :=
  parse pythonFixture

#guard parsedFixture.map BlockRecord.block = some 0
#guard parsedFixture.map BlockRecord.lowerCount = some 32_130_158_315
#guard parsedFixture.map BlockRecord.upperCount = some 32_130_158_318
#guard parsedFixture.map BlockRecord.mainSlots = some 3
#guard parsedFixture.map BlockRecord.sourceHeightCountRaw = some noCount

/- A second Python fixture exercises the unique source-height block and both
optional fallback digests. -/
private def pythonSourceHeightFixtureHex : String :=
  "50543231424c4b3101000000400100000657d0b000000000cb715e853e0b0000d7715e853e0b00000c000000000000000200000001000000010000000000000000000000000000000000000000000000d2715e853e0b000011111111111111111111111111111111111111111111111111111111111111112222222222222222222222222222222222222222222222222222222222222222333333333333333333333333333333333333333333333333333333333333333355555555555555555555555555555555555555555555555555555555555555556666666666666666666666666666666666666666666666666666666666666666444444444444444444444444444444444444444444444444444444444444444407000000000000001920d6b61a1df206e6eee2daae0eb553968a9cba935ba6f0fafe80bdb04d4d31"

private def pythonSourceHeightFixture : ByteArray :=
  (decodeLowerHex pythonSourceHeightFixtureHex).getD ByteArray.empty

#guard checkBytes pythonSourceHeightFixture
#guard
  (parse pythonSourceHeightFixture).map BlockRecord.block =
    some sourceHeightBlock
#guard
  (parse pythonSourceHeightFixture).map BlockRecord.sourceHeightCountRaw =
    some 12_363_153_437_138
#guard
  (parse pythonSourceHeightFixture).map
      BlockRecord.sourceHeightSlotsFromLower = some 7

#guard
  SparkInterval.Zeta.PT21NativeBlockWire.byteArrayLowerHex
      (pythonFixture.extract blockDigestOffset blockRecordBytes) ==
    "a8d2f4218b1f8871363dca585fb5583bce843b0b41465d1e229316837952edd8"

/- Every class of bytes checked by the parser or validator fails closed after
tampering: framing, arithmetic payload, and record digest. -/
#guard checkBytes (pythonFixture.set! 0 0) = false
#guard checkBytes (pythonFixture.set! 40 4) = false
#guard checkBytes (pythonFixture.set! 319 0) = false
#guard checkBytes ((pythonFixture.toList ++ [0]).toByteArray) = false

example (hcheck : checkBytes pythonFixture = true) :
    pythonFixture.size = blockRecordBytes :=
  checkBytes_size hcheck

end SparkInterval.Tests.PT21NativeBlockWire
