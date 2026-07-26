#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed tests for the full-source Goldbach campaign machinery."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tg_verifier import goldbach_campaign as tg
from tg_verifier.campaign_io import AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS


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

    def test_analytic_10pow27_profile_is_exact_and_distinct(self) -> None:
        parameters = tg.analytic_10pow27_parameters()
        self.assertEqual(parameters.mode, "analytic_10pow27")
        self.assertEqual(parameters.proth_exponent, 45)
        self.assertEqual(parameters.range_count, 7_106)
        self.assertEqual(parameters.range_width, (1 << 47) * 10**9)
        self.assertEqual(
            parameters.endpoint, 1_000_080_592_252_960_768_000_000_000
        )
        self.assertGreaterEqual(parameters.endpoint, 10**27)
        with self.assertRaises(tg.CampaignError):
            replace(parameters, range_count=7_105).validate()

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

    def test_source_height_benchmark_is_explicitly_not_a_certificate(self) -> None:
        completed = subprocess.run(
            [
                "python3",
                "tools/tg_goldbach_campaign.py",
                "benchmark-source-height",
                "--steps",
                "10",
            ],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        root = json.loads(completed.stdout)
        self.assertTrue(root["benchmark_only_not_a_certificate"])
        self.assertEqual(root["sample_steps"], 10)


class PrimeCertificateTests(unittest.TestCase):
    def test_fixed_n_52_proth_witness(self) -> None:
        number = 7 * (1 << 52) + 1
        self.assertTrue(tg.check_source_proth(number, 3))
        self.assertFalse(tg.check_source_proth(number, 2))
        self.assertEqual(
            tg.find_source_proth(6 * (1 << 52), 8 * (1 << 52)),
            tg.Rung(number, "proth52", witness=3),
        )

    def test_parameterized_n45_proth_is_not_labeled_proth52(self) -> None:
        result = tg.find_proth(0, 10**18, 45)
        self.assertIsNotNone(result)
        assert result is not None and result.witness is not None
        self.assertEqual(result.certificate_kind, "proth")
        self.assertTrue(tg.check_proth(result.number, result.witness, 45))
        self.assertFalse(tg.check_source_proth(result.number, result.witness))

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
            environment = dict(os.environ)
            for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
                environment.pop(key, None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/tg_pocklington_producer.py",
                    "--request",
                    str(request_path),
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=False,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(completed.returncode, 2, completed)
            self.assertIn(
                b"production arithmetic/replay is cloud-only",
                completed.stderr,
            )
            self.assertFalse(output_path.exists())


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
    def test_optimized_combined_result_binds_its_distinct_source(self) -> None:
        from tg_verifier import campaign_io
        from tg_verifier import goldbach_gpu_campaign as gpu

        plan = gpu.make_optimized_production_plan(
            executable_sha256="b" * 64
        )
        binary = {
            "aggregate_sha256": "c" * 64,
            "coverage_structurally_complete": True,
            "domain": {
                "even_start_inclusive": 4,
                "even_limit_inclusive": 4_000_000_000_000_000_000,
                "even_count": 1_999_999_999_999_999_999,
            },
            "production_campaign_complete": True,
            "receipt_merkle_root_sha256": "d" * 64,
        }
        ladder = {
            "aggregate_sha256": "e" * 64,
            "range_count": tg.SOURCE_RANGE_COUNT,
            "range_receipt_merkle_root_sha256": "f" * 64,
        }
        with (
            mock.patch.object(gpu, "load_plan", return_value=plan),
            mock.patch.object(gpu, "receipt_paths", return_value=[]),
            mock.patch.object(
                gpu, "validate_aggregate", return_value=binary
            ),
            mock.patch.object(campaign_io, "load_json", return_value={}),
            mock.patch.object(
                tg, "_read_canonical_json", return_value={}
            ),
            mock.patch.object(
                tg, "validate_independent_aggregate", return_value=ladder
            ),
            mock.patch.object(
                tg, "load_campaign", return_value=tg.CampaignParameters()
            ),
        ):
            result = tg.combine_with_optimized_binary_goldbach(
                Path("ladder"),
                ladder_aggregate_path=Path("ladder.json"),
                binary_plan_path=Path("plan.json"),
                binary_receipts_directory=Path("receipts"),
                binary_aggregate_path=Path("aggregate.json"),
            )
        self.assertEqual(
            result["kind"], tg.OPTIMIZED_COMBINED_GPU_RESULT_KIND
        )
        self.assertEqual(
            result["binary_goldbach"]["algorithm"], plan.algorithm
        )
        self.assertEqual(
            result["binary_goldbach"]["plan_sha256"], plan.plan_sha256
        )
        self.assertEqual(
            result["binary_goldbach"]["source_identity_sha256"],
            gpu.EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256,
        )
        self.assertIn("not_registered", result["classification"])
        self.assertFalse(result["execution_attested"])
        self.assertFalse(result["lean_atom_discharged"])

    def test_historical_combiners_are_algorithm_domain_separated(self) -> None:
        from tg_verifier.goldbach_gpu_campaign import (
            make_optimized_production_plan,
            make_production_plan,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipts = root / "receipts"
            receipts.mkdir()
            aggregate = root / "aggregate.json"
            ladder = root / "ladder.json"
            output = root / "combined.json"
            plans = {
                "base": make_production_plan(executable_sha256="a" * 64),
                "optimized": make_optimized_production_plan(
                    executable_sha256="b" * 64
                ),
            }
            paths: dict[str, Path] = {}
            for name, plan in plans.items():
                path = root / f"{name}-plan.json"
                path.write_bytes(tg.canonical_json_bytes(plan.to_dict()))
                paths[name] = path

            with self.assertRaisesRegex(
                tg.CampaignError, "exact hardened historical profile"
            ):
                tg.combine_with_hardened_binary_goldbach(
                    root,
                    ladder_aggregate_path=ladder,
                    binary_plan_path=paths["optimized"],
                    binary_receipts_directory=receipts,
                    binary_aggregate_path=aggregate,
                    output_path=output,
                )
            with self.assertRaisesRegex(
                tg.CampaignError, "exact optimized historical profile"
            ):
                tg.combine_with_optimized_binary_goldbach(
                    root,
                    ladder_aggregate_path=ladder,
                    binary_plan_path=paths["base"],
                    binary_receipts_directory=receipts,
                    binary_aggregate_path=aggregate,
                    output_path=output,
                )
            self.assertFalse(output.exists())

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


class IndependentParallelRangeTests(unittest.TestCase):
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

    def test_ranges_produce_out_of_order_and_reduce_in_fixed_order(self) -> None:
        second = tg.produce_independent_range(self.directory, 1)
        self.assertFalse(
            (self.directory / "independent-ranges" / "range-000000.tggl").exists()
        )
        self.assertEqual(second["index"], 1)
        self.assertEqual(
            sum(
                second["evidence"][field]
                for field in (
                    "direct64_count",
                    "external_count",
                    "pocklington_count",
                    "proth52_count",
                )
            ),
            second["record_count"],
        )
        tg.produce_independent_range(self.directory, 0)
        aggregate = tg.reduce_independent_campaign(self.directory)
        self.assertEqual(aggregate["range_count"], 2)
        self.assertEqual(
            aggregate["coverage"], {"first_odd": "7", "last_odd": "39"}
        )
        self.assertEqual(len(aggregate["range_receipt_sha256s"]), 2)
        self.assertRegex(
            aggregate["range_receipt_merkle_root_sha256"], r"^[0-9a-f]{64}$"
        )
        self.assertFalse(aggregate["binary_goldbach_prerequisite_satisfied"])
        self.assertIn("separate binary-Goldbach", aggregate["verification_note"])

    def test_missing_or_swapped_receipt_fails_closed(self) -> None:
        tg.produce_independent_range(self.directory, 0)
        with self.assertRaisesRegex(tg.CampaignError, "incomplete"):
            tg.reduce_independent_campaign(self.directory)
        tg.produce_independent_range(self.directory, 1)
        receipts = self.directory / "independent-receipts"
        first = receipts / tg.independent_receipt_filename(0)
        second = receipts / tg.independent_receipt_filename(1)
        first_raw, second_raw = first.read_bytes(), second.read_bytes()
        first.write_bytes(second_raw)
        second.write_bytes(first_raw)
        with self.assertRaisesRegex(tg.CampaignError, "differs from exact replay"):
            tg.reduce_independent_campaign(self.directory)

    def test_receipt_is_immutable_and_range_replay_detects_tampering(self) -> None:
        receipt = tg.produce_independent_range(self.directory, 0)
        self.assertEqual(receipt, tg.emit_independent_receipt(self.directory, 0))
        range_path = (
            self.directory
            / "independent-ranges"
            / tg.independent_range_filename(0)
        )
        raw = bytearray(range_path.read_bytes())
        raw[-1] ^= 1
        range_path.write_bytes(raw)
        with self.assertRaises(tg.CampaignError):
            tg.emit_independent_receipt(self.directory, 0)

    def test_cli_parallel_worker_and_reducer(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        group = subprocess.run(
            [
                sys.executable,
                "tools/tg_goldbach_campaign.py",
                "produce-group",
                str(self.directory),
                "--group-index",
                "0",
                "--group-count",
                "1",
                "--local-workers",
                "2",
            ],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(group.stdout)["range_count"], 2)
        output = self.directory / "ladder-aggregate.json"
        completed = subprocess.run(
            [
                sys.executable,
                "tools/tg_goldbach_campaign.py",
                "reduce-ranges",
                str(self.directory),
                "--out",
                str(output),
            ],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), json.loads(output.read_bytes()))

    def test_formulaic_worker_groups_are_balanced_and_gap_free(self) -> None:
        bounds = [tg.independent_group_bounds(10, index, 3) for index in range(3)]
        self.assertEqual(bounds, [(0, 4), (4, 7), (7, 10)])
        with self.assertRaises(tg.CampaignError):
            tg.independent_group_bounds(2, 0, 3)


if __name__ == "__main__":
    unittest.main()
