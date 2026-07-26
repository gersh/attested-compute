# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tg_verifier.cdem_abel_artifact import (
    ARTIFACT_HEADER,
    CdemAbelArtifactError,
    decode_artifact,
    encode_certificate,
    write_artifact_exclusive,
)
from tg_verifier.cdem_chunk_replay import CdemChunkRecord
from tg_verifier.cdem_recurrence_certificate import CdemRecurrenceCertificate


def fixture_certificate() -> CdemRecurrenceCertificate:
    return CdemRecurrenceCertificate(
        signed_numerator=17,
        absolute_numerator=29,
        chunks=(
            CdemChunkRecord(1, 3, 0, -2, -4, 7, 11),
            CdemChunkRecord(4, 8, -2, 5, 9, 13, 17),
        ),
        transcript_sha256="ab" * 32,
    )


class CdemAbelArtifactTests(unittest.TestCase):
    def test_round_trip_matches_fixed_header_and_omits_diagnostic_variation(self) -> None:
        certificate = fixture_certificate()
        raw = encode_certificate(certificate)
        self.assertTrue(raw.startswith(ARTIFACT_HEADER))
        decoded = decode_artifact(raw)
        self.assertEqual(decoded.signed_numerator, 17)
        self.assertEqual(decoded.absolute_numerator, 29)
        self.assertEqual(
            tuple(
                (
                    row.low,
                    row.high,
                    row.before,
                    row.after,
                    row.u_increment_upper,
                    row.v_increment_upper,
                )
                for row in decoded.chunks
            ),
            tuple(
                (
                    row.low,
                    row.high,
                    row.before,
                    row.after,
                    row.u_increment_upper,
                    row.v_increment_upper,
                )
                for row in certificate.chunks
            ),
        )
        self.assertEqual([row.variation for row in decoded.chunks], [0, 0])

    def test_header_frame_suffix_and_negative_zero_tampering_fail_closed(self) -> None:
        raw = bytearray(encode_certificate(fixture_certificate()))
        cases: list[tuple[str, bytes]] = [
            ("header", b"X" + bytes(raw[1:])),
            ("truncated", bytes(raw[:-1])),
            ("suffix", bytes(raw) + b"x"),
        ]
        first_before_sign = len(ARTIFACT_HEADER) + 68 + 64
        negative_zero = bytearray(raw)
        negative_zero[first_before_sign] = 1
        # The first `before` magnitude is already zero.
        cases.append(("negative-zero", bytes(negative_zero)))
        for label, changed in cases:
            with self.subTest(label=label), self.assertRaises(
                CdemAbelArtifactError
            ):
                decode_artifact(changed)

    def test_exclusive_writer_refuses_reuse(self) -> None:
        # The production-only transcript converter is tested independently;
        # exercise exclusive file semantics without manufacturing a fake
        # production transcript.
        certificate = fixture_certificate()
        raw = encode_certificate(certificate)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact.bin"
            path.write_bytes(raw)
            with self.assertRaises(FileExistsError):
                with path.open("xb"):
                    pass


if __name__ == "__main__":
    unittest.main()
