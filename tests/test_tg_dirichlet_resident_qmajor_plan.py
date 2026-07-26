# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tg_verifier.dirichlet_allchars_q_scheduler import source_schedule_records
from tg_verifier.dirichlet_allchars_stage import (
    group_order,
    modulus_butterflies,
)
from tg_verifier.dirichlet_resident_qmajor_plan import (
    DirichletResidentQMajorPlanError,
    MAXIMUM_RESIDENT_ROWS,
    PINNED_PHASES,
    ResidentPhase,
    _phase_accounting,
    _precompute_modulus_work,
    capability,
    source_projection,
    validate_phases,
)


def _legacy_phase_accounting(records, phase):
    """Independent reference retained from the original planning loop."""

    active_q_count = 0
    target_count = 0
    row_count = 0
    value_count = 0
    batched_butterflies = 0
    for record in records:
        active_rows = max(
            0,
            min(record.t_index_count, phase.t_index_stop_exclusive)
            - phase.first_t_index,
        )
        if active_rows == 0:
            continue
        active_q_count += 1
        full_batches, remainder = divmod(active_rows, 64)
        target_count += full_batches + int(remainder != 0)
        row_count += active_rows
        value_count += active_rows * group_order(record.q)
        batched_butterflies += full_batches * modulus_butterflies(
            record.q, batch_count=64
        )
        if remainder:
            batched_butterflies += modulus_butterflies(
                record.q, batch_count=remainder
            )
    return {
        "active_q_count": active_q_count,
        "target_count": target_count,
        "row_reference_count": row_count,
        "group_value_count": value_count,
        "batched_radix2_butterflies": batched_butterflies,
    }


class DirichletResidentQMajorPlanTests(unittest.TestCase):
    def test_direct_cli_help_smoke(self) -> None:
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "tools/tg_dirichlet_resident_qmajor_plan.py"),
                "--help",
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertIn(
            "Recompute the exact ten-phase resident q-major Dirichlet plan.",
            completed.stdout.decode(),
        )

    def test_pretty_cli_report_is_exactly_pinned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "tools/tg_dirichlet_resident_qmajor_plan.py"),
                "--pretty",
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(
            json.loads(completed.stdout),
            source_projection(),
        )
        self.assertEqual(
            hashlib.sha256(completed.stdout).hexdigest(),
            "eae086771356cc3e2cc26780012686f"
            "dbc3a8097aa76a3417056fe74f5a32eb6",
        )

    def test_exact_source_projection_and_eight_slot_balance(self) -> None:
        report = source_projection()
        self.assertEqual(report["phase_count"], 10)
        self.assertEqual(report["gpu_slot_count"], 8)
        self.assertEqual(report["totals"]["target_count"], 56_981_100)
        self.assertEqual(
            report["totals"]["row_reference_count"], 3_637_613_167
        )
        self.assertEqual(
            report["totals"]["group_value_count"], 266_697_737_764_848
        )
        self.assertEqual(
            report["totals"]["batched_radix2_butterflies"],
            15_334_965_882_246_056,
        )
        self.assertEqual(report["unique_lattice_row_count"], 127_988)
        self.assertEqual(
            report["unique_lattice_payload_bytes"], 134_205_145_088
        )
        self.assertEqual(
            report["maximum_resident_row_count"], MAXIMUM_RESIDENT_ROWS
        )
        self.assertEqual(
            report["maximum_resident_lattice_payload_bytes"],
            41_406_169_088,
        )
        slot_work = report["slot_batched_radix2_butterflies"]
        self.assertEqual(len(slot_work), 8)
        self.assertEqual(sum(slot_work), 15_334_965_882_246_056)
        self.assertEqual(max(slot_work), 1_998_670_835_119_088)
        self.assertEqual(min(slot_work), 1_844_926_924_725_312)
        self.assertLess(max(slot_work) * 1000, min(slot_work) * 1084)

    def test_phases_cover_each_t_once(self) -> None:
        phases = validate_phases(PINNED_PHASES)
        for t_index in (
            0,
            767,
            768,
            9_599,
            9_600,
            49_087,
            49_088,
            88_511,
            88_512,
            127_987,
        ):
            containing = [
                phase
                for phase in phases
                if phase.first_t_index
                <= t_index
                < phase.t_index_stop_exclusive
            ]
            self.assertEqual(len(containing), 1)

    def test_precomputed_affine_cost_matches_legacy_reference(self) -> None:
        records = source_schedule_records()
        modulus_work = _precompute_modulus_work(records)
        for phase in PINNED_PHASES:
            with self.subTest(phase=phase.phase_index):
                self.assertEqual(
                    _phase_accounting(modulus_work, phase),
                    _legacy_phase_accounting(records, phase),
                )

    def test_gap_overlap_alignment_memory_and_assignment_fail_closed(
        self,
    ) -> None:
        attacks = []
        for index, replacement in (
            (
                1,
                ResidentPhase(1, 1, 769, 1_600),
            ),
            (
                1,
                ResidentPhase(1, 1, 767, 1_600),
            ),
            (
                7,
                ResidentPhase(7, 7, 9_600, 49_087),
            ),
            (
                7,
                ResidentPhase(7, 7, 9_600, 49_152),
            ),
            (
                9,
                ResidentPhase(9, 6, 88_512, 127_988),
            ),
        ):
            changed = list(PINNED_PHASES)
            changed[index] = replacement
            attacks.append(tuple(changed))
        for phases in attacks:
            with self.subTest(phases=phases):
                with self.assertRaises(DirichletResidentQMajorPlanError):
                    validate_phases(phases)

    def test_capability_promotes_only_the_bounded_candidate(self) -> None:
        report = capability()
        self.assertTrue(report["exact_source_partition_planned"])
        self.assertTrue(report["resident_shard_wire_implemented"])
        self.assertTrue(report["resident_cuda_executor_implemented"])
        self.assertTrue(report["bounded_cuda_kat_completed"])
        self.assertFalse(
            report["persistent_downstream_transform_integrated"]
        )
        self.assertFalse(report["source_phase_execution_completed"])
        self.assertFalse(report["source_h100_fit_claimed"])
        self.assertFalse(report["source_scale_run_completed"])
        self.assertFalse(report["target_h100_measured"])
        self.assertFalse(report["trusted_execution_attested"])
        self.assertFalse(
            report["completed_l_zero_state_validated"]
        )
        self.assertFalse(report["zero_completeness_claimed"])
        self.assertFalse(report["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
