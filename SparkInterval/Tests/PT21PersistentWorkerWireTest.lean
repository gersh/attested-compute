/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21PersistentWorkerWire

set_option autoImplicit false

namespace SparkInterval.Tests.PT21PersistentWorkerWireTest

open SparkInterval.Zeta.PT21PersistentWorkerWire

def junctionRequestZero : ByteArray :=
  [0x50, 0x54, 0x32, 0x31, 0x4a, 0x52, 0x51, 0x31,
    0x01, 0x00, 0x00, 0x00, 0x18, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00].toByteArray

def turingRequestZero : ByteArray :=
  ([0x50, 0x54, 0x32, 0x31, 0x54, 0x52, 0x51, 0x31,
    0x01, 0x00, 0x00, 0x00, 0x38, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00] ++
    List.replicate 32 (0 : UInt8)).toByteArray

example : parseJunctionRequest junctionRequestZero =
    some { block := 0 } := by
  decide

example : (parseTuringRequest turingRequestZero).map (·.block) = some 0 := by
  decide

example : parseJunctionRequest
    (junctionRequestZero.set! 0 0x51) = none := by
  decide

example : parseTuringResponse ByteArray.empty = none := by
  decide

end SparkInterval.Tests.PT21PersistentWorkerWireTest
