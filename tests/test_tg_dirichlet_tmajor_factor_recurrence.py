# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tg_verifier.complex_disk_mul_certificate import (
    verify_raw_mul_certificate,
)
from tg_verifier.dirichlet_tmajor_factor_recurrence import (
    FOOTER,
    FOOTER_MAGIC,
    FORMAT_VERSION,
    HEADER,
    MAXIMUM_FACTOR_COUNT,
    _parse_artifact,
    DirichletTMajorFactorRecurrenceError,
    benchmark,
    build_artifact_bytes,
    verify_artifact,
    verify_artifact_bytes,
    verify_artifact_with_arb,
    write_artifact,
)
from tg_verifier.dirichlet_tmajor_cuda_block import FRAME_FACTOR


ROOT = Path(__file__).resolve().parents[1]

try:
    import flint as _flint  # type: ignore[import-not-found]

    PINNED_FLINT_AVAILABLE = (
        str(_flint.__version__) == "0.9.0"
        and str(_flint.__FLINT_VERSION__) == "3.6.0"
        and int(_flint.__FLINT_RELEASE__) == 30_600
    )
except ImportError:
    PINNED_FLINT_AVAILABLE = False


def _repair_transport(raw: bytes) -> bytes:
    changed = bytearray(raw)
    payload_stop = len(changed) - FOOTER.size
    payload = bytes(changed[HEADER.size:payload_stop])
    changed[HEADER.size - 32 : HEADER.size] = hashlib.sha256(
        payload
    ).digest()
    footer = FOOTER.unpack_from(changed, payload_stop)
    changed[payload_stop:] = FOOTER.pack(
        FOOTER_MAGIC,
        FORMAT_VERSION,
        0,
        footer[3],
        hashlib.sha256(bytes(changed[:payload_stop])).digest(),
    )
    return bytes(changed)


class RecurrenceArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = build_artifact_bytes(
            q=10_001, first_t_index=17, count=MAXIMUM_FACTOR_COUNT
        )

    def test_full_exact_and_direct_mpfr_replay(self) -> None:
        report = verify_artifact_bytes(
            self.raw, full_direct_mpfr=True
        )
        self.assertEqual(report["factor_count"], 64)
        self.assertEqual(
            report["exact_rational_multiplication_steps_replayed"], 63
        )
        self.assertEqual(report["transcendental_boxes_per_precision"], 2)
        self.assertTrue(report["full_direct_mpfr_differential_checked"])
        self.assertTrue(report["production_TGDLTMB1_format_unchanged"])
        self.assertFalse(report["external_atom_discharged"])
        self.assertLess(report["maximum_factor_width"], 1e-12)

    def test_artifact_is_deterministic(self) -> None:
        rebuilt = build_artifact_bytes(
            q=10_001, first_t_index=17, count=64
        )
        self.assertEqual(rebuilt, self.raw)

    def test_cached_checker_agrees_with_lean_witness_preflight(self) -> None:
        parsed = _parse_artifact(self.raw)
        for certificate in parsed.certificates:
            # The production replay uses a word-cache optimization, while
            # this independent preflight follows the exact checker mirrored
            # by SparkInterval.Certified.ComplexDisk in Lean.
            verify_raw_mul_certificate(certificate)

    def test_transport_complete_factor_mutation_fails_semantic_replay(
        self,
    ) -> None:
        changed = bytearray(self.raw)
        first_word = struct.unpack_from("<Q", changed, HEADER.size)[0]
        struct.pack_into("<Q", changed, HEADER.size, first_word + 1)
        with self.assertRaisesRegex(
            DirichletTMajorFactorRecurrenceError,
            "payload digest",
        ):
            verify_artifact_bytes(bytes(changed))
        repaired = _repair_transport(bytes(changed))
        with self.assertRaisesRegex(
            DirichletTMajorFactorRecurrenceError,
            "factor rectangle 0",
        ):
            verify_artifact_bytes(repaired)

    def test_transport_complete_certificate_mutation_fails(self) -> None:
        changed = bytearray(self.raw)
        certificate_start = (
            HEADER.size + 64 * FRAME_FACTOR.size
        )
        output_radius_offset = certificate_start + 8 * 8
        word = struct.unpack_from(
            "<Q", changed, output_radius_offset
        )[0]
        struct.pack_into(
            "<Q", changed, output_radius_offset, max(0, word - 1)
        )
        repaired = _repair_transport(bytes(changed))
        with self.assertRaises(
            DirichletTMajorFactorRecurrenceError
        ):
            verify_artifact_bytes(repaired)

    def test_wrong_length_identity_and_range_fail_closed(self) -> None:
        for raw in (self.raw[:-1], self.raw + b"\0"):
            with self.subTest(size=len(raw)), self.assertRaises(
                DirichletTMajorFactorRecurrenceError
            ):
                verify_artifact_bytes(raw)
        changed = bytearray(self.raw)
        changed[0] ^= 1
        repaired = _repair_transport(bytes(changed))
        with self.assertRaisesRegex(
            DirichletTMajorFactorRecurrenceError, "header identity"
        ):
            verify_artifact_bytes(repaired)
        with self.assertRaises(DirichletTMajorFactorRecurrenceError):
            build_artifact_bytes(q=10_000, first_t_index=0, count=1)
        with self.assertRaises(DirichletTMajorFactorRecurrenceError):
            build_artifact_bytes(q=10_001, first_t_index=0, count=65)

    def test_file_path_is_immutable_and_externally_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "factor-recurrence.bin"
            report = write_artifact(
                path, q=10_001, first_t_index=0, count=4
            )
            replay = verify_artifact(
                path, expected_sha256=report["artifact_sha256"]
            )
            self.assertEqual(
                replay["artifact_sha256"], report["artifact_sha256"]
            )
            with self.assertRaisesRegex(
                DirichletTMajorFactorRecurrenceError, "replace immutable"
            ):
                write_artifact(
                    path, q=10_001, first_t_index=0, count=4
                )
            with self.assertRaisesRegex(
                DirichletTMajorFactorRecurrenceError, "external SHA"
            ):
                verify_artifact(path, expected_sha256="0" * 64)

    def test_benchmark_reports_cost_and_no_production_promotion(self) -> None:
        report = benchmark(
            q=10_001,
            first_t_index=0,
            count=8,
            repetitions=1,
        )
        self.assertEqual(
            report["transcendental_box_reduction_factor"], 4.0
        )
        self.assertGreater(
            report["direct_two_precision_mpfr_median_seconds"], 0
        )
        self.assertGreater(
            report[
                "recurrence_build_and_self_replay_median_seconds"
            ],
            0,
        )
        self.assertFalse(report["source_scale_projection_authoritative"])
        self.assertFalse(report["production_format_changed"])
        self.assertFalse(report["external_atom_discharged"])

    def test_cli_build_verify_and_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "factor-recurrence.bin"
            build = subprocess.run(
                [
                    "python3",
                    "tools/tg_dirichlet_tmajor_factor_recurrence.py",
                    "build",
                    str(path),
                    "--q",
                    "10001",
                    "--first-t-index",
                    "0",
                    "--count",
                    "4",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            built = json.loads(build.stdout)
            verified = subprocess.run(
                [
                    "python3",
                    "tools/tg_dirichlet_tmajor_factor_recurrence.py",
                    "verify",
                    str(path),
                    "--expected-sha256",
                    built["artifact_sha256"],
                    "--full-direct-mpfr",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(
                json.loads(verified.stdout)[
                    "full_direct_mpfr_differential_checked"
                ]
            )
            timing = subprocess.run(
                [
                    "python3",
                    "tools/tg_dirichlet_tmajor_factor_recurrence.py",
                    "benchmark",
                    "--count",
                    "4",
                    "--repetitions",
                    "1",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(
                math.isfinite(
                    json.loads(timing.stdout)[
                        "direct_over_recurrence_build_speedup"
                    ]
                )
            )

    @unittest.skipUnless(
        PINNED_FLINT_AVAILABLE,
        "pinned python-flint 0.9.0 / FLINT 3.6.0 is unavailable",
    )
    def test_independent_arb_full_and_spot_checks(self) -> None:
        full = verify_artifact_with_arb(
            self.raw, precision_bits=384
        )
        self.assertTrue(full["independent_arb_checked"])
        self.assertEqual(full["independent_arb_factor_count"], 64)
        spot = verify_artifact_with_arb(
            self.raw,
            precision_bits=384,
            frame_indices=(0, 17, 63),
        )
        self.assertEqual(spot["independent_arb_mode"], "selected_frames")
        self.assertEqual(spot["independent_arb_factor_count"], 3)


if __name__ == "__main__":
    unittest.main()
