#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed tests for the full-source Goldbach campaign machinery."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from tg_verifier import goldbach_campaign as tg


class SourceConstantsTests(unittest.TestCase):
    def test_paper_constants_and_exact_endpoint(self) -> None:
        self.assertEqual(tg.PROTH_EXPONENT, 52)
        self.assertEqual(tg.SOURCE_RANGE_WIDTH, (1 << 54) * 10**9)
        self.assertEqual(tg.SOURCE_RANGE_COUNT, 492_700)
        self.assertEqual(
            tg.SOURCE_ENDPOINT,
            8_875_694_145_621_773_516_800_000_000_000,
        )
        self.assertEqual(tg.SOURCE_MAXIMUM_GAP, 4 * 10**18)
        self.assertEqual(tg.SOURCE_ENDPOINT_TOLERANCE, 2 * 10**18)

    def test_full_source_profile_cannot_be_weakened(self) -> None:
        with self.assertRaises(tg.CampaignError):
            replace(tg.CampaignParameters(), range_count=1).validate()

    def test_plan_cli_prints_source_profile(self) -> None:
        completed = subprocess.run(
            ["python3", "tools/tg_goldbach_campaign.py", "plan"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        root = json.loads(completed.stdout)
        self.assertEqual(root["endpoint"], str(tg.SOURCE_ENDPOINT))
        self.assertEqual(root["range_count"], tg.SOURCE_RANGE_COUNT)
        self.assertEqual(
            root["binary_goldbach_prerequisite"]["last_even"],
            "4000000000000000000",
        )


class PrimeCertificateTests(unittest.TestCase):
    def test_fixed_n_52_proth_witness(self) -> None:
        number = 7 * (1 << 52) + 1
        self.assertTrue(tg.check_source_proth(number, 3))
        self.assertFalse(tg.check_source_proth(number, 2))
        self.assertEqual(
            tg.find_source_proth(6 * (1 << 52), 8 * (1 << 52)),
            tg.Rung(number, "proth52", witness=3),
        )

    def test_pocklington_certificate_above_direct_64_bit_domain(self) -> None:
        number = 18_446_744_073_709_551_629
        certificate = {
            "cofactor": "1",
            "factors": [
                {"exponent": 2, "prime": "2", "witness": "2"},
                {"exponent": 1, "prime": "7", "witness": "2"},
                {
                    "exponent": 1,
                    "prime": "658812288346769701",
                    "witness": "2",
                },
            ],
            "kind": tg.POCKLINGTON_KIND,
            "number": str(number),
        }
        self.assertTrue(tg.check_pocklington_object(certificate, expected=number))
        bad = dict(certificate)
        bad["cofactor"] = "2"
        self.assertFalse(tg.check_pocklington_object(bad, expected=number))

    def test_builtin_dense_pocklington_grid_produces_a_checked_prime(self) -> None:
        lower = 1 << 64
        rung, certificate = tg.find_general_pocklington(
            lower, lower + 10**12, factor_prime_attempts=100
        )
        self.assertEqual(rung.certificate_kind, "pocklington")
        self.assertTrue(lower < rung.number < lower + 10**12)
        self.assertTrue(
            tg.check_pocklington_object(certificate, expected=rung.number)
        )

    def test_external_pocklington_fallback_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = {
                "kind": tg.GENERAL_REQUEST_KIND,
                "lower_exclusive": str(1 << 64),
                "upper_exclusive": str((1 << 64) + 10**12),
            }
            request_path = root / "request.json"
            output_path = root / "output.json"
            request_path.write_bytes(tg.canonical_json_bytes(request))
            subprocess.run(
                [
                    sys.executable,
                    "tools/tg_pocklington_producer.py",
                    "--request",
                    str(request_path),
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
            )
            result = json.loads(output_path.read_bytes())
            certificate = json.loads(Path(result["certificate_path"]).read_bytes())
            self.assertTrue(
                tg.check_pocklington_object(
                    certificate, expected=int(result["number"])
                )
            )


class CompactRangeCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.parameters = tg.CampaignParameters(
            range_width=20,
            range_count=2,
            maximum_gap=10,
            endpoint_tolerance=5,
            binary_first_even=4,
            binary_last_even=10,
            proth_exponent=52,
            seed_prime=3,
            mode="bounded_test",
        )
        tg.initialize_campaign(self.directory, self.parameters)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _direct(*numbers: int) -> tuple[tg.Rung, ...]:
        return tuple(tg.Rung(number, "direct64") for number in numbers)

    def _write_both(self) -> None:
        first = self.directory / "ranges" / tg.range_filename(0)
        first_hash = tg.write_range_file(
            first,
            parameters=self.parameters,
            index=0,
            previous_range_sha256=tg.ZERO_HASH,
            rungs=self._direct(3, 7, 13, 17),
        )
        tg.write_range_file(
            self.directory / "ranges" / tg.range_filename(1),
            parameters=self.parameters,
            index=1,
            previous_range_sha256=first_hash,
            rungs=self._direct(17, 23, 29, 37),
        )

    def test_gap_free_hash_chained_replay(self) -> None:
        self._write_both()
        state = tg.replay_campaign(self.directory)
        self.assertEqual(state.completed_ranges, 2)
        self.assertEqual(state.last_rung.number, 37)
        self.assertEqual(state.total_records, 7)
        self.assertGreaterEqual(state.covered_through, 39)

    def test_resume_rechecks_root_and_rejects_tampering(self) -> None:
        self._write_both()
        first = self.directory / "ranges" / tg.range_filename(0)
        raw = bytearray(first.read_bytes())
        raw[-1] ^= 1
        first.write_bytes(raw)
        with self.assertRaises(tg.CampaignError):
            tg.replay_campaign(self.directory)

    def test_resume_rejects_changed_implementation_identity(self) -> None:
        manifest = self.directory / "manifest.json"
        value = json.loads(manifest.read_bytes())
        value["implementation_sha256"] = "0" * 64
        manifest.write_bytes(tg.canonical_json_bytes(value))
        with self.assertRaisesRegex(tg.CampaignError, "source identity"):
            tg.replay_campaign(self.directory)

    def test_boundary_rung_and_endpoint_tolerance_are_mandatory(self) -> None:
        first = self.directory / "ranges" / tg.range_filename(0)
        first_hash = tg.write_range_file(
            first,
            parameters=self.parameters,
            index=0,
            previous_range_sha256=tg.ZERO_HASH,
            rungs=self._direct(3, 7, 13, 17),
        )
        tg.write_range_file(
            self.directory / "ranges" / tg.range_filename(1),
            parameters=self.parameters,
            index=1,
            previous_range_sha256=first_hash,
            rungs=self._direct(19, 23, 29, 37),
        )
        with self.assertRaisesRegex(tg.CampaignError, "boundary rung"):
            tg.replay_campaign(self.directory)

    def test_a_ladder_alone_cannot_emit_source_receipt(self) -> None:
        self._write_both()
        with self.assertRaisesRegex(tg.CampaignError, "bounded-test"):
            tg.verify_complete_campaign(
                self.directory,
                binary_checker=Path("missing-checker"),
                binary_artifact=Path("missing-artifact"),
            )


class BinaryGoldbachBoundaryTests(unittest.TestCase):
    def test_external_result_is_bound_to_checker_artifact_and_exact_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "binary.cert"
            artifact.write_bytes(b"test artifact\n")
            checker = root / "checker.py"
            checker.write_text(
                """#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--request'); p.add_argument('--artifact'); a=p.parse_args()
r=json.loads(Path(a.request).read_text())
out={'artifact_sha256':hashlib.sha256(Path(a.artifact).read_bytes()).hexdigest(),
     'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
     'every_even':True,'first_even':'4','kind':'tg_binary_goldbach_result_v1',
     'last_even':'4000000000000000000','verified':True}
print(json.dumps(out,sort_keys=True,separators=(',',':')))
""",
                encoding="utf-8",
            )
            checker.chmod(checker.stat().st_mode | stat.S_IXUSR)
            result = tg.check_binary_prerequisite(checker, artifact)
            self.assertTrue(result["verified"])
            self.assertEqual(
                result["artifact_sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest()
            )

            # A checker that reports a narrower endpoint fails closed.
            checker.write_text(checker.read_text().replace(
                "4000000000000000000", "3999999999999999998"
            ))
            with self.assertRaises(tg.CampaignError):
                tg.check_binary_prerequisite(checker, artifact)


if __name__ == "__main__":
    unittest.main()
