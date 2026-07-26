/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire
import SparkInterval.Zeta.PT21TuringBlockJunction

/-!
# Cross-language test for the PT21 stationary/Turing/native junction

The three records below were emitted by the Python/C++ encoders.  Small
retained payload strings keep the kernel test fast while still exercising
all parsers, all SHA-256 recomputations, the ten-input predecessor
commitment, and the multiplicity-two linkage.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.PT21TuringBlockJunction

open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire
open SparkInterval.Zeta.PT21TuringBlockJunction

private def hex (value : String) : ByteArray :=
  (decodeLowerHex value).getD ByteArray.empty

private def eventRecord : ByteArray :=
  hex "505432314556543101000000c00000000000000000000000000000008d64000001000000000000000000000002000000000000000000000002000000000000000000000002000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000031313131313131313131313131313131313131313131313131313131313131313cc97dbe5dd0a8fb7e3bd1f31461ae669fd2c63f7a3396c029b97c22a4cf9102"

private def junctionRecord : ByteArray :=
  hex "5054323153544a310100000090010000000000000000000000000000000000000200000002000000000000000000000004000000800000004000000040000000887700000000000001000000010000003cc97dbe5dd0a8fb7e3bd1f31461ae669fd2c63f7a3396c029b97c22a4cf910231313131313131313131313131313131313131313131313131313131313131311111111111111111111111111111111111111111111111111111111111111111121212121212121212121212121212121212121212121212121212121212121213131313131313131313131313131313131313131313131313131313131313131414141414141414141414141414141414141414141414141414141414141414e3f7fc136777eff3882e0580370e7f4f21479f2126a8853c29542889e3b891bba5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a55a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a571ff6d84d5d986968c5b49ea7fa2f807de21e929d16121598c2c7059ad1ddc6"

private def blockRecord : ByteArray :=
  hex "50543231424c4b31010000004001000000000000000000000a000000000000000e0000000000000004000000000000000200000000000000000000000000000000000000000000000000000000000000ffffffffffffffff7426afc489d0eef99a0b438def226ad139f752350c25cf2c04900281afbb79e041cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947dc7c5c1d70c5dec4416ab6158afd0b223ef40c29b1dc1f97ed9428b94d4cadb1ce3f7fc136777eff3882e0580370e7f4f21479f2126a8853c29542889e3b891bb0000000000000000000000000000000000000000000000000000000000000000fb9ef68aee3944227d17adf3274c96153404da2c89110996992a1cd690c369690000000000000000f7aa3e34e28f2472e197a24c78baced46694c5d6a2093b901e512c61560cbc02"

private def payloads : RetainedPayloads := {
  eventRecord
  junctionRecord
  requiredPacket := hex "7061636b6574"
  stationaryTrace := hex "73746174696f6e617279"
  turingInputs := hex "747572696e67"
  sourceTrace := hex "736f75726365"
  blockArtifact := hex "6172746966616374"
}

private def digests : RawDigests := {
  eventRecord :=
    hex "3eac32df8b0d11f5edf6bfd22244d25a156dc441e96bc2ae1713afe93dfa86ae"
  junctionRecord :=
    hex "80ca799dd3ccf967087adbaaccce873de551dd4d1b683e5f26475f0c3b4dacf3"
  requiredPacket :=
    hex "7426afc489d0eef99a0b438def226ad139f752350c25cf2c04900281afbb79e0"
  stationaryTrace :=
    hex "e3f7fc136777eff3882e0580370e7f4f21479f2126a8853c29542889e3b891bb"
  turingInputs :=
    hex "c84e9bbecb4337cc165699ab194ac5daf827a186a9677eaa4d1915ef55c15861"
}

private def identities : ExecutionIdentities := {
  junctionExecutable :=
    hex "a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5"
  turingExecutable :=
    hex "b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6"
  flintLibrary :=
    hex "5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a"
  adapterSources :=
    hex "c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7"
  finalizerExecutable :=
    hex "d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8"
}

#guard check payloads digests identities blockRecord

#guard
  (SparkInterval.Zeta.PT21NativeBlockWire.parse blockRecord).map
      SparkInterval.Zeta.PT21NativeBlockWire.BlockRecord.mainSlots = some 4
#guard
  (SparkInterval.Zeta.PT21StationaryJunctionWire.parse junctionRecord).map
      (fun record => record.resolvedMultiplicitySlots) = some 4

/- Payload, identity, cross-record, count, and final-record mutations all fail
closed. -/
#guard
  check { payloads with turingInputs := hex "747572696e68" }
    digests identities blockRecord = false
#guard
  check payloads digests
    { identities with finalizerExecutable := hex "0101010101010101010101010101010101010101010101010101010101010101" }
    blockRecord = false
#guard
  check { payloads with junctionRecord := junctionRecord.set! 48 2 }
    digests identities blockRecord = false
#guard check payloads digests identities (blockRecord.set! 48 1) = false
#guard check payloads digests identities (blockRecord.set! 319 0) = false

example (hcheck : check payloads digests identities blockRecord = true) :
    ValidatedBytes payloads digests identities blockRecord :=
  check_sound hcheck

end SparkInterval.Tests.PT21TuringBlockJunction
