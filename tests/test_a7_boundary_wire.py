# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import unittest

from tests.test_tg_analytic import a7_fixture, canonical
from tg_verifier.a7_boundary_wire import (
    A7BoundaryWireError,
    RETAINED_LEAF_COUNT,
    RETAINED_LEAVES_SHA256,
    RETAINED_MAX_DEPTH,
    RETAINED_PAYLOAD_SHA256,
    RETAINED_TRANSCRIPT_SHA256,
    RETAINED_TRANSCRIPT_SIZE_BYTES,
    RETAINED_WIRE_SHA256,
    WIRE_HEADER_BYTES,
    WIRE_RECORD_BYTES,
    decode_a7_boundary_wire,
    encode_a7_boundary_wire,
    wire_from_transcript_bytes,
)
from tg_verifier.a7_lean_certificate import (
    A7LeanCertificateError,
    certificate_from_transcript_bytes,
)


def tiny_wire() -> bytes:
    return wire_from_transcript_bytes(
        canonical(a7_fixture()), require_retained_identity=False
    )


def with_recomputed_payload_digest(raw: bytes | bytearray) -> bytes:
    changed = bytearray(raw)
    changed[104:136] = hashlib.sha256(changed[WIRE_HEADER_BYTES:]).digest()
    return bytes(changed)


class A7BoundaryWireTests(unittest.TestCase):
    def test_python_and_lean_retained_pins_are_synchronized(self) -> None:
        lean = (
            Path(__file__).resolve().parents[1]
            / "SparkInterval/TernaryGoldbach/A7BoundaryWire.lean"
        ).read_text(encoding="utf-8")
        for pin in (
            RETAINED_TRANSCRIPT_SHA256,
            RETAINED_LEAVES_SHA256,
            RETAINED_PAYLOAD_SHA256,
            RETAINED_WIRE_SHA256,
        ):
            self.assertIn(pin, lean)
        self.assertIn(f"def retainedLeafCount : Nat := 16_191", lean)
        self.assertEqual(RETAINED_LEAF_COUNT, 16_191)
        self.assertIn(f"def retainedMaxDepth : Nat := {RETAINED_MAX_DEPTH}", lean)
        self.assertIn(
            "def retainedTranscriptSizeBytes : Nat := 1_494_999", lean
        )
        self.assertEqual(RETAINED_TRANSCRIPT_SIZE_BYTES, 1_494_999)

    def test_python_to_lean_fixture_is_stable_and_fully_decoded(self) -> None:
        raw = tiny_wire()
        self.assertEqual(len(raw), WIRE_HEADER_BYTES + 4 * WIRE_RECORD_BYTES)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "eb4098cd36c1bf73acae9c335545b447fec2b060f4efe92f071467c5ebbe4679",
        )
        artifact = decode_a7_boundary_wire(raw)
        self.assertEqual(artifact.max_depth, 0)
        self.assertEqual(len(artifact.leaves), 4)
        self.assertEqual(
            (
                artifact.leaves[0].edge_id,
                artifact.leaves[0].depth,
                artifact.leaves[0].index,
                artifact.leaves[0].norm_sq_upper_mantissa,
                artifact.leaves[0].norm_sq_upper_exponent,
                artifact.leaves[0].zeta_abs_lower_mantissa,
                artifact.leaves[0].zeta_abs_lower_exponent,
            ),
            (0, 0, 0, 1, 0, 1, 0),
        )
        self.assertEqual(
            artifact.payload_sha256,
            "995884ac40341288cb70bbec6a34c2f987025f8fe708ded3b0d0438c3bdc76ae",
        )

    def test_truncation_suffix_layout_and_payload_mutations_fail_closed(self) -> None:
        raw = tiny_wire()
        mutations = [
            raw[:-1],
            raw + b"\0",
            bytes([0]) + raw[1:],
            raw[:28] + (5).to_bytes(4, "little") + raw[32:],
            raw[:104] + bytes([raw[104] ^ 1]) + raw[105:],
            raw[:WIRE_HEADER_BYTES]
            + bytes([raw[WIRE_HEADER_BYTES] ^ 1])
            + raw[WIRE_HEADER_BYTES + 1 :],
        ]
        for mutation in mutations:
            with self.subTest(sha256=hashlib.sha256(mutation).hexdigest()):
                with self.assertRaises(A7BoundaryWireError):
                    decode_a7_boundary_wire(mutation)

    def test_semantic_mutations_fail_after_attacker_rehashes_payload(self) -> None:
        raw = tiny_wire()

        # Make the first edge ID 3.  The payload hash is repaired, but
        # canonical four-edge ordering/coverage is no longer true.
        changed = bytearray(raw)
        changed[WIRE_HEADER_BYTES : WIRE_HEADER_BYTES + 4] = (3).to_bytes(
            4, "little"
        )
        with self.assertRaisesRegex(A7BoundaryWireError, "canonical|covered"):
            decode_a7_boundary_wire(with_recomputed_payload_digest(changed))

        # Increase the first norm-square bound from 1 to 2, beyond
        # (349/250)^2, and repair the payload digest.
        changed = bytearray(raw)
        changed[WIRE_HEADER_BYTES + 16 + 31] = 2
        with self.assertRaisesRegex(A7BoundaryWireError, "strict source"):
            decode_a7_boundary_wire(with_recomputed_payload_digest(changed))

        # Erase the first positive zeta mantissa and repair the payload digest.
        changed = bytearray(raw)
        zeta_start = WIRE_HEADER_BYTES + 52
        changed[zeta_start : zeta_start + 32] = bytes(32)
        with self.assertRaisesRegex(A7BoundaryWireError, "not positive"):
            decode_a7_boundary_wire(with_recomputed_payload_digest(changed))

        # Depth zero cannot carry index one.
        changed = bytearray(raw)
        changed[WIRE_HEADER_BYTES + 8 : WIRE_HEADER_BYTES + 16] = (1).to_bytes(
            8, "little"
        )
        with self.assertRaisesRegex(A7BoundaryWireError, "dyadic depth"):
            decode_a7_boundary_wire(with_recomputed_payload_digest(changed))

        # Bounded signed exponents prevent a tiny malicious wire from forcing
        # enormous integer shifts in either checker.
        changed = bytearray(raw)
        changed[
            WIRE_HEADER_BYTES + 48 : WIRE_HEADER_BYTES + 52
        ] = (16_385).to_bytes(4, "little", signed=True)
        with self.assertRaisesRegex(A7BoundaryWireError, "bounded range"):
            decode_a7_boundary_wire(with_recomputed_payload_digest(changed))

    def test_tiny_wire_does_not_impersonate_retained_identity(self) -> None:
        with self.assertRaisesRegex(A7BoundaryWireError, "retained"):
            decode_a7_boundary_wire(
                tiny_wire(), require_retained_identity=True
            )

    def test_encoder_revalidates_manually_replaced_literal_records(self) -> None:
        certificate = certificate_from_transcript_bytes(
            canonical(a7_fixture()), require_retained_identity=False
        )
        leaf = certificate.leaves[0]
        changed = replace(
            certificate,
            leaves=(replace(leaf, edge_id=3),) + certificate.leaves[1:],
        )
        with self.assertRaisesRegex(A7LeanCertificateError, "canonical"):
            encode_a7_boundary_wire(changed)

    def test_retained_binary_pins_are_concrete_sha256_values(self) -> None:
        self.assertRegex(RETAINED_PAYLOAD_SHA256, r"^[0-9a-f]{64}$")
        self.assertRegex(RETAINED_WIRE_SHA256, r"^[0-9a-f]{64}$")
        self.assertNotEqual(RETAINED_PAYLOAD_SHA256, RETAINED_WIRE_SHA256)


if __name__ == "__main__":
    unittest.main()
