# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier.sqrt218_certificate import (
    Sqrt218ProducerError,
    produce_certificate_bytes,
)
import tg_verifier.sqrt218_certificate as producer_implementation
from tg_verifier.sqrt218_certificate_verifier import (
    Sqrt218VerificationError,
    verify_certificate,
    verify_certificate_bytes,
)
import tg_verifier.sqrt218_certificate_verifier as verifier_implementation
from tg_verifier.sqrt218_contract import (
    BOUND,
    BOUND_64_KAT,
    LEAN_CLAIM,
    canonical_json_bytes,
    production_run_input,
    production_run_input_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/sqrt218/sample-certificate.bound64.json.txt"


class Sqrt218CertificateTests(unittest.TestCase):
    def test_bound_64_known_answer_and_independent_replay(self) -> None:
        raw = produce_certificate_bytes(64)
        report = verify_certificate_bytes(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), BOUND_64_KAT["certificate_sha256"])
        self.assertEqual(report["summary"], BOUND_64_KAT["summary"])
        self.assertTrue(report["accepted"])
        self.assertFalse(report["proves_lean_claim"])

    def test_display_fixture_is_the_exact_known_answer_before_final_newline(self) -> None:
        display = SAMPLE.read_bytes()
        self.assertTrue(display.endswith(b"\n"))
        self.assertEqual(display[:-1], produce_certificate_bytes(64))
        verify_certificate_bytes(display[:-1])

    def test_wire_encoding_and_archive_tampering_fail_closed(self) -> None:
        raw = produce_certificate_bytes(64)
        with self.assertRaisesRegex(Sqrt218VerificationError, "canonical"):
            verify_certificate_bytes(raw + b"\n")
        with self.assertRaises(Sqrt218VerificationError):
            verify_certificate_bytes(
                b'{"bound":64,"bound":64}',
            )
        value = json.loads(raw)
        value["primes"][1][1] = 1
        with self.assertRaisesRegex(Sqrt218VerificationError, "Lucas"):
            verify_certificate_bytes(canonical_json_bytes(value))
        value = json.loads(raw)
        value["events"][3][0] = 6
        with self.assertRaisesRegex(Sqrt218VerificationError, "complete prime-power"):
            verify_certificate_bytes(canonical_json_bytes(value))
        value = json.loads(raw)
        value["summary"]["fixed_scan_sha256"] = "0" * 64
        with self.assertRaisesRegex(Sqrt218VerificationError, "summary differs"):
            verify_certificate_bytes(canonical_json_bytes(value))

    def test_sample_cannot_be_selected_as_production(self) -> None:
        with self.assertRaisesRegex(Sqrt218VerificationError, "selected profile"):
            verify_certificate_bytes(
                produce_certificate_bytes(64),
                require_production=True,
            )

    def test_registered_recomputation_input_is_exact_and_source_shaped(self) -> None:
        raw = production_run_input_bytes()
        self.assertFalse(raw.endswith(b"\n"))
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "17d1c5328bd05b4883670f33823cd218dd1f32e53bad51c9a5c96bec5e06d178",
        )
        self.assertEqual(production_run_input()["lean_claim"], LEAN_CLAIM)

    def test_production_sized_cli_requires_an_explicit_cloud_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must-not-exist.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/tg_sqrt218_certificate.py"),
                    "produce",
                    str(output),
                    "--bound",
                    "2000000",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(b"standalone CLI is KAT-only", completed.stdout)
            self.assertFalse(output.exists())

    def test_library_rejects_every_non_kat_bound_without_measured_context(self) -> None:
        with mock.patch.object(
            producer_implementation,
            "_smallest_prime_factors",
            side_effect=AssertionError("production sieve must not start locally"),
        ) as sieve:
            for bound in (65, BOUND):
                with self.subTest(bound=bound):
                    with self.assertRaisesRegex(
                        Sqrt218ProducerError,
                        "Azure measured-production context",
                    ):
                        produce_certificate_bytes(bound)
            sieve.assert_not_called()

    def test_cloud_flag_is_rejected_by_standalone_cli_before_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must-not-exist.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/tg_sqrt218_certificate.py"),
                    "produce",
                    str(output),
                    "--bound",
                    "2000000",
                    "--cloud-production",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(
                b"standalone CLI is KAT-only",
                completed.stdout,
            )
            self.assertFalse(output.exists())

    def test_production_shaped_archive_is_rejected_before_full_replay(self) -> None:
        value = json.loads(produce_certificate_bytes(64))
        value["bound"] = BOUND
        with mock.patch.object(
            verifier_implementation,
            "_verify_prime_rows",
            side_effect=AssertionError("production replay must not start locally"),
        ) as prime_replay:
            with self.assertRaisesRegex(
                Sqrt218VerificationError,
                "Azure measured-production context",
            ):
                verify_certificate_bytes(canonical_json_bytes(value))
            prime_replay.assert_not_called()

    def test_file_verifier_rejects_production_prefix_before_reading_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "production-shaped.json"
            archive.write_bytes(b'{"bound":2000000,"events":')
            with self.assertRaisesRegex(
                Sqrt218VerificationError,
                "Azure measured-production context",
            ):
                verify_certificate(archive)

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_json_schemas_accept_the_exact_input_and_sample_archive(self) -> None:
        for name in (
            "sqrt218-finite-run-input.schema.json",
            "sqrt218-finite-certificate.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text())
            jsonschema.Draft202012Validator.check_schema(schema)
        input_schema = json.loads(
            (ROOT / "schemas/sqrt218-finite-run-input.schema.json").read_text()
        )
        certificate_schema = json.loads(
            (ROOT / "schemas/sqrt218-finite-certificate.schema.json").read_text()
        )
        jsonschema.Draft202012Validator(input_schema).validate(production_run_input())
        jsonschema.Draft202012Validator(certificate_schema).validate(
            json.loads(produce_certificate_bytes(64))
        )


if __name__ == "__main__":
    unittest.main()
