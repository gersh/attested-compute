#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed tests for the distinct finite campaign below 10^27."""

from __future__ import annotations

import tempfile
from pathlib import Path
import subprocess
import sys
import unittest

from tg_verifier.goldbach_10pow27_campaign import (
    Goldbach10Pow27CampaignError,
    combine_branches,
    combine_optimized_branches,
    initialize_ladder,
    make_binary_plan,
    make_optimized_binary_plan,
    schedule_summary,
)
from tg_verifier.goldbach_campaign import (
    ANALYTIC_10POW27_ATOM_ID,
    ANALYTIC_10POW27_ENDPOINT,
    analytic_10pow27_parameters,
    load_campaign,
)
from tg_verifier.goldbach_gpu_campaign import (
    ANALYTIC_10POW27_ALGORITHM,
    ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
    GoldbachPlan,
    make_production_plan,
    write_plan,
)
from tools.tg_goldbach_10pow27_finalizer import write_registered_result


class Goldbach10Pow27CampaignTests(unittest.TestCase):
    def test_schedule_is_exact_and_explicitly_unrun(self) -> None:
        schedule = schedule_summary()
        self.assertEqual(schedule["status"], "UNRUN")
        self.assertFalse(schedule["execution_attested"])
        self.assertFalse(schedule["lean_atom_discharged"])
        self.assertEqual(schedule["semantic_target_inclusive"], str(10**27))
        self.assertEqual(
            schedule["prime_ladder"]["scheduled_endpoint"],
            str(ANALYTIC_10POW27_ENDPOINT),
        )
        self.assertEqual(schedule["prime_ladder"]["proth_exponent"], 45)

    def test_binary_plan_is_exact_and_round_trips(self) -> None:
        plan = make_binary_plan(executable_sha256="a" * 64)
        self.assertEqual(plan.algorithm, ANALYTIC_10POW27_ALGORITHM)
        self.assertEqual(plan.even_limit, 31_250_000_000_000_000)
        self.assertEqual(GoldbachPlan.from_dict(plan.to_dict()), plan)
        optimized = make_optimized_binary_plan(executable_sha256="b" * 64)
        self.assertEqual(
            optimized.algorithm, ANALYTIC_10POW27_OPTIMIZED_ALGORITHM
        )
        self.assertEqual(optimized.even_limit, plan.even_limit)
        self.assertNotEqual(optimized.plan_sha256, plan.plan_sha256)
        self.assertEqual(
            GoldbachPlan.from_dict(optimized.to_dict()), optimized
        )

    def test_ladder_initializer_uses_only_the_reviewed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            initialize_ladder(directory)
            self.assertEqual(load_campaign(directory), analytic_10pow27_parameters())
            self.assertIn(
                f'"atom_id":"{ANALYTIC_10POW27_ATOM_ID}"',
                (directory / "manifest.json").read_text(encoding="ascii"),
            )

    def test_historical_binary_plan_cannot_enter_lowered_combiner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "historical-plan.json"
            write_plan(plan_path, make_production_plan(executable_sha256="a" * 64))
            with self.assertRaisesRegex(
                Goldbach10Pow27CampaignError, "not the exact analytic-10pow27"
            ):
                combine_branches(
                    root / "ladder",
                    ladder_aggregate_path=root / "ladder.json",
                    binary_plan_path=plan_path,
                    binary_receipts_directory=root / "receipts",
                    binary_aggregate_path=root / "binary.json",
                )

    def test_lowered_combiners_are_algorithm_domain_separated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base_path = root / "base-plan.json"
            optimized_path = root / "optimized-plan.json"
            write_plan(
                base_path, make_binary_plan(executable_sha256="a" * 64)
            )
            write_plan(
                optimized_path,
                make_optimized_binary_plan(executable_sha256="b" * 64),
            )
            with self.assertRaisesRegex(
                Goldbach10Pow27CampaignError,
                "not the exact analytic-10pow27",
            ):
                combine_branches(
                    root / "ladder",
                    ladder_aggregate_path=root / "ladder.json",
                    binary_plan_path=optimized_path,
                    binary_receipts_directory=root / "receipts",
                    binary_aggregate_path=root / "binary.json",
                )
            with self.assertRaisesRegex(
                Goldbach10Pow27CampaignError,
                "not the exact analytic-10pow27",
            ):
                combine_optimized_branches(
                    root / "ladder",
                    ladder_aggregate_path=root / "ladder.json",
                    binary_plan_path=base_path,
                    binary_receipts_directory=root / "receipts",
                    binary_aggregate_path=root / "binary.json",
                )

    def test_measured_finalizer_fails_closed_before_printing_true(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/tg_goldbach_10pow27_finalizer.py",
                    str(root / "ladder"),
                    "--ladder-aggregate",
                    str(root / "ladder.json"),
                    "--binary-plan",
                    str(root / "binary-plan.json"),
                    "--binary-receipts-dir",
                    str(root / "receipts"),
                    "--binary-aggregate",
                    str(root / "binary.json"),
                    "--combined-out",
                    str(root / "combined.json"),
                    "--registered-result-output",
                    str(root / "registered-result.txt"),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertFalse((root / "combined.json").exists())
            self.assertFalse((root / "registered-result.txt").exists())

    def test_registered_result_is_exact_immutable_true(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result" / "registered-result.txt"
            write_registered_result(path)
            self.assertEqual(path.read_bytes(), b"true")
            self.assertEqual(path.stat().st_mode & 0o777, 0o400)
            write_registered_result(path)
            path.chmod(0o600)
            with self.assertRaisesRegex(
                Goldbach10Pow27CampaignError,
                "existing registered-result output differs",
            ):
                write_registered_result(path)
            path.write_bytes(b"false")
            with self.assertRaisesRegex(
                Goldbach10Pow27CampaignError,
                "existing registered-result output differs",
            ):
                write_registered_result(path)


if __name__ == "__main__":
    unittest.main()
