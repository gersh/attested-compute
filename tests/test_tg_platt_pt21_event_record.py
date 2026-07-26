# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tg_verifier import platt_pt21_event_record as event_wire


ROOT = Path(__file__).resolve().parents[1]
KAT_SOURCE = ROOT / "reference/tg_platt_event_record_kat.cpp"
FUSED_SOURCE = (
    ROOT / "gpu/platform/h100/h100_tg_platt_fused_source_worker_v2.cu"
)
CMAKE = ROOT / "CMakeLists.txt"
TOOL = ROOT / "tools/tg_platt_pt21_event_record.py"


class PT21EventRecordTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("g++ is required for the event-wire KAT")
        cls.class_temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.class_temporary.cleanup)
        cls.runner = Path(cls.class_temporary.name) / "event-record-kat"
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                "-I",
                str(ROOT / "gpu/include"),
                str(KAT_SOURCE),
                "-o",
                str(cls.runner),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stream = Path(self.temporary.name) / "events.bin"
        completed = subprocess.run(
            [str(self.runner), str(self.stream)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.producer_report = json.loads(completed.stdout)

    def validate(self, path: Path | None = None) -> dict[str, object]:
        return event_wire.validate_stream(
            self.stream if path is None else path,
            expected_gamma_stream_sha256="11" * 32,
            expected_producer_sha256="22" * 32,
        )

    def test_cpp_stream_roundtrips_in_independent_python(self) -> None:
        report = self.validate()
        self.assertTrue(report["accepted"])
        self.assertEqual(report["first_block"], 7)
        self.assertEqual(report["upper_block_exclusive"], 9)
        self.assertEqual(report["block_count"], 2)
        self.assertEqual(report["event_record_bytes"], 192)
        self.assertEqual(report["stream_size_bytes"], 768)
        self.assertEqual(report["total_direct_events"], 12)
        self.assertEqual(report["total_stationary_candidates"], 3)
        self.assertEqual(
            report["event_contract_sha256"],
            "7c3a3e984b71315a2fdd9407b4cfc5746ce9d25e1f633cd9f897f2a92d8de1f8",
        )
        self.assertEqual(
            report["stream_sha256"],
            self.producer_report["event_stream_sha256"],
        )
        self.assertTrue(report["three_stream_event_scan_complete"])
        self.assertFalse(
            report["gaussian_sinc_stationary_resolution_complete"]
        )
        self.assertFalse(report["turing_closure_complete"])
        self.assertFalse(report["source_claim_ready"])

    def test_header_record_footer_prefix_and_suffix_mutations_fail(self) -> None:
        original = self.stream.read_bytes()
        mutations = {
            "header": original[:20]
            + bytes([original[20] ^ 1])
            + original[21:],
            "record": original[: event_wire.HEADER.size + 40]
            + bytes([original[event_wire.HEADER.size + 40] ^ 1])
            + original[event_wire.HEADER.size + 41 :],
            "footer": original[:-32]
            + bytes([original[-32] ^ 1])
            + original[-31:],
            "prefix": original[:-1],
            "suffix": original + b"\0",
        }
        for label, raw in mutations.items():
            with self.subTest(label=label):
                path = Path(self.temporary.name) / f"{label}.bin"
                path.write_bytes(raw)
                with self.assertRaises(event_wire.PT21EventRecordError):
                    self.validate(path)

    def test_semantic_count_mutations_fail_even_with_fresh_record_digest(
        self,
    ) -> None:
        raw = bytearray(
            self.stream.read_bytes()[
                event_wire.HEADER.size :
                event_wire.HEADER.size + event_wire.RECORD.size
            ]
        )
        mutations = {
            "failure": (24, 1),
            "slot_mismatch": (64, 9),
            "unresolved_mismatch": (76, 7),
        }
        for label, (offset, value) in mutations.items():
            with self.subTest(label=label):
                changed = bytearray(raw)
                struct.pack_into("<I", changed, offset, value)
                changed[event_wire.RECORD_DIGEST_OFFSET :] = hashlib.sha256(
                    event_wire.RECORD_DOMAIN
                    + changed[: event_wire.RECORD_DIGEST_OFFSET]
                ).digest()
                with self.assertRaises(event_wire.PT21EventRecordError):
                    event_wire.parse_record(bytes(changed), expected_block=7)

    def test_kat_output_is_create_only(self) -> None:
        before = self.stream.read_bytes()
        completed = subprocess.run(
            [str(self.runner), str(self.stream)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(self.stream.read_bytes(), before)

    def test_pins_are_required_to_match_when_supplied(self) -> None:
        with self.assertRaisesRegex(
            event_wire.PT21EventRecordError, "Gamma identity"
        ):
            event_wire.validate_stream(
                self.stream,
                expected_gamma_stream_sha256="33" * 32,
                expected_producer_sha256="22" * 32,
            )
        with self.assertRaisesRegex(
            event_wire.PT21EventRecordError, "producer identity"
        ):
            event_wire.validate_stream(
                self.stream,
                expected_gamma_stream_sha256="11" * 32,
                expected_producer_sha256="44" * 32,
            )

    def test_cli_requires_both_external_identity_pins(self) -> None:
        completed = subprocess.run(
            [
                "python3",
                str(TOOL),
                str(self.stream),
                "--expected-gamma-stream-sha256",
                "11" * 32,
                "--expected-producer-sha256",
                "22" * 32,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["accepted"])
        self.assertFalse(report["source_claim_ready"])
        missing = subprocess.run(
            ["python3", str(TOOL), str(self.stream)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(missing.returncode, 0)

    def test_fused_worker_source_uses_device_scan_and_nonterminal_wire(
        self,
    ) -> None:
        source = FUSED_SOURCE.read_text(encoding="utf-8")
        cmake = CMAKE.read_text(encoding="utf-8")
        for token in (
            '#include "sparkinterval/tg_platt_event_record.hpp"',
            '#include "sparkinterval/tg_platt_event_scan.hpp"',
            "pes::scan_source_required_samples",
            "pes::device_scan_status",
            "pes::device_stream_summaries",
            "per::encode_record",
            "--event-stream-output",
            "--producer-sha256",
            "source_packet_retained",
            "pt21_native_block_records_emitted",
            "gaussian_sinc_interpolation_complete",
            "turing_closure_complete",
        ):
            self.assertIn(token, source)
        link_marker = (
            "target_link_libraries(\n"
            "    sparkinterval-tg-platt-fused-source-worker-v2 PRIVATE"
        )
        link_start = cmake.index(link_marker)
        self.assertIn(
            "sparkinterval-tg-platt-event-scan",
            cmake[link_start : link_start + 500],
        )
        self.assertIn("PT21EVT1 is explicitly nonterminal", source)
        self.assertNotIn('"PT21BLK1"', source)


if __name__ == "__main__":
    unittest.main()
