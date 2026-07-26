/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundaryWire
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.ResultWire

/-!
# Cross-language checks for the compact CH25 A.7 finite wire

`tools/tg_a7_boundary_wire.py` produced the literal 496-byte fixture
below from the canonical four-leaf JSON fixture used by the independent
Python artifact tests.  Lean therefore checks the Python layout, signed
dyadic fields, SHA-256 payload binding, exact-length parser, and the existing
four-edge certificate checker without sharing a binary decoder with Python.

This tiny fixture is intentionally not the retained production identity and
does not carry a FLINT-to-Mathlib analytic realization.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.A7BoundaryWireTest

open SparkInterval.TernaryGoldbach
open SparkInterval.TernaryGoldbach.A7BoundaryWire
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

private def pythonFixtureHex : String :=
  "5447413757495231010000009000000058000000000000000000000004000000130a000000000000d4a066147594471c46ab69c1c65d85f7ef84ed0902240e4aaae1b3c6cac481fbe4096d8b76c78699d7c0fb00fa47d11e73867270a131730a865d57b7bfd30a16995884ac40341288cb70bbec6a34c2f987025f8fe708ded3b0d0438c3bdc76ae000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000100000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000001000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000010000000003000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000100000000"

private def pythonFixture : ByteArray :=
  (decodeLowerHex pythonFixtureHex).getD ByteArray.empty

#guard pythonFixture.size = headerBytes + 4 * recordBytes
#guard SparkInterval.Certificate.SHA256.digestByteArray pythonFixture =
  "eb4098cd36c1bf73acae9c335545b447fec2b060f4efe92f071467c5ebbe4679"
#guard checkBytes pythonFixture
#guard checkRetainedBytes pythonFixture = false

private def parsedFixture : Option Artifact :=
  parse pythonFixture

#guard parsedFixture.map (fun artifact => artifact.header.maxDepth) = some 0
#guard parsedFixture.map (fun artifact => artifact.header.leafCount) = some 4
#guard
  parsedFixture.map (fun artifact => artifact.certificate.leaves.length) =
    some 4
private def firstLeaf :=
  parsedFixture.bind (fun artifact => artifact.certificate.leaves.head?)

#guard firstLeaf.map (fun leaf => leaf.edgeId) = some 0
#guard firstLeaf.map (fun leaf => leaf.depth) = some 0
#guard firstLeaf.map (fun leaf => leaf.index) = some 0
#guard firstLeaf.map (fun leaf => leaf.normSqUpperMantissa) = some 1
#guard firstLeaf.map (fun leaf => leaf.normSqUpperExponent) = some 0
#guard firstLeaf.map (fun leaf => leaf.zetaAbsLowerMantissa) = some 1
#guard firstLeaf.map (fun leaf => leaf.zetaAbsLowerExponent) = some 0

/- Magic, count/length, payload, truncation, and suffix mutations all fail
closed.  Semantic mutations with a recomputed payload hash are covered by the
independent Python tests. -/
#guard checkBytes (pythonFixture.set! 0 0) = false
#guard checkBytes (pythonFixture.set! 28 5) = false
#guard checkBytes (pythonFixture.set! 104 0) = false
#guard checkBytes (pythonFixture.set! headerBytes 3) = false
#guard checkBytes (pythonFixture.extract 0 (pythonFixture.size - 1)) = false
#guard
  checkBytes ((pythonFixture.toList ++ [(0 : UInt8)]).toByteArray) = false

example (hcheck : checkBytes pythonFixture = true) :
    ValidatedBytes pythonFixture :=
  checkBytes_sound hcheck

example (hcheck : checkBytes pythonFixture = true) :
    ∃ artifact : Artifact,
      parse pythonFixture = some artifact ∧
        artifact.certificate.Accepted :=
  acceptedCertificate_of_checkBytes hcheck

#print axioms checkBytes_sound
#print axioms acceptedCertificate_of_checkBytes
#print axioms exactLength_of_checkBytes
#print axioms checkRetainedBytes_sound
#print axioms sourceClaim_of_checked_retained_wire

end SparkInterval.Tests.A7BoundaryWireTest
