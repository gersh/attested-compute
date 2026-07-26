/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire
import SparkInterval.Zeta.PT21StationaryJunctionWire

/-!
# Cross-language checks for `PT21STJ1`

The fixture is the terminal-block record emitted by
`tg_platt_stationary_junction_benchmark.cu` after an actual CUDA scanner
replay and FLINT 3.6.0 resolution of two bounded synthetic candidates.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.PT21StationaryJunctionWire

open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire
open SparkInterval.Zeta.PT21StationaryJunctionWire

private def cppFixtureHex : String :=
  "5054323153544a3101000000900100000657d0b00000000000000000000000000200000002000000000000000000000004000000800000004000000040000000887700000000000001000000010000005f38f41feb45e8d4cb9ff031a5a8f7b5be3a729a2929cf2a0331b73330550be37c5f8e2911ac4cc35b2600cc18e21b1fb4d5d19cb9fe720eecaf9126cce4831e09c1d4a305c3f981bdc61b022614684b11187a0af28ac8233f438c6af4e810e181a331f7f29f17de65d41e95ed9a988ead3f561fa32117917139be441227b1b573c724c1b5a02c77da7a1fcb5bfa3e1361c3e50678fff5988c9766b1dbddb66db982a4c4aa0b34a0c902c09086f8ec88e0dfebaf91c844b7d29cd412a2cb1139a65c2326941852bb130e19b349e47f6302faa1c0f37eb4debf1e0cbb9d60e688a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a55a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a4ec4e772a9019a1b44237f464cd85cf6b04b1f05e76be43316f62a18d41e2678"

private def cppFixture : ByteArray :=
  (decodeLowerHex cppFixtureHex).getD ByteArray.empty

#guard cppFixture.size = recordBytes
#guard checkBytes cppFixture

private def parsedFixture : Option JunctionRecord :=
  parse cppFixture

#guard parsedFixture.map JunctionRecord.block = some 2_966_443_782
#guard parsedFixture.map JunctionRecord.candidateCount = some 2
#guard parsedFixture.map JunctionRecord.resolutionCount = some 2
#guard parsedFixture.map JunctionRecord.resolvedMultiplicitySlots = some 4
#guard parsedFixture.map JunctionRecord.semanticRealizationFlags = some 0
#guard parsedFixture.map JunctionRecord.resolverReplayAccepted = some 1
#guard
  parsedFixture.map JunctionRecord.higherPrecisionContainmentComplete = some 1
#guard parsedFixture.map JunctionRecord.flintReleaseRaw = some 30_600

/- Every finite relationship, all semantic flags, and the terminal digest fail
closed under direct mutation. -/
#guard checkBytes (cppFixture.set! 0 0) = false
#guard checkBytes (cppFixture.set! 36 1) = false
#guard checkBytes (cppFixture.set! 48 2) = false
#guard checkBytes (cppFixture.set! 68 1) = false
#guard checkBytes (cppFixture.set! 112 0) = false
#guard checkBytes (cppFixture.set! 399 0) = false
#guard checkBytes ((cppFixture.toList ++ [0]).toByteArray) = false

example (hcheck : checkBytes cppFixture = true) :
    cppFixture.size = recordBytes :=
  checkBytes_size hcheck

end SparkInterval.Tests.PT21StationaryJunctionWire
