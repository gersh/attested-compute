# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import unittest

from tg_verifier.dirichlet_allchars_q_scheduler import (
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
    source_schedule_records,
)
from tg_verifier.dirichlet_formulaic_qmajor_cursor import (
    DirichletFormulaicQMajorError,
    FormulaicQMajorCursor,
    FormulaicTarget,
    LaneRange,
    PINNED_SOURCE_LANE_ROWS,
    PINNED_SOURCE_LANE_TARGETS,
    PINNED_SOURCE_ROWS,
    PINNED_SOURCE_TARGETS,
    capability,
    formulaic_accounting,
    source_lanes,
)


def _bounded_schedule(rows: tuple[tuple[int, int], ...]):
    return parse_schedule_manifest(
        build_schedule_manifest_bytes(
            tuple(ScheduleRecord(q, count) for q, count in rows)
        )
    )


class DirichletFormulaicQMajorCursorTest(unittest.TestCase):
    def test_bounded_cursor_equals_explicit_q_t_roster(self) -> None:
        schedule = _bounded_schedule(
            ((10_001, 5), (10_003, 19), (10_004, 16), (10_005, 31))
        )
        # The scheduler deliberately changes the input order.
        self.assertNotEqual(
            tuple(record.q for record in schedule.execution_records),
            (10_001, 10_003, 10_004, 10_005),
        )
        lanes = (
            LaneRange(0, 0, 8),
            LaneRange(1, 8, 16),
            LaneRange(2, 16, 31),
        )
        cursor = FormulaicQMajorCursor(
            schedule, lanes, maximum_batch_count=8
        )
        observed: list[tuple[int, int]] = []
        targets: list[FormulaicTarget] = []
        while (target := cursor.expected_target()) is not None:
            targets.append(target)
            observed.extend(
                (target.q, t)
                for t in range(
                    target.first_t_index,
                    target.t_index_stop_exclusive,
                )
            )
            cursor.accept(target)
        receipt = cursor.finish()
        self.assertEqual(
            cursor.accounting["plan_sha256"],
            (
                "03b5f39b9dec5e9518c1283d9d46208f"
                "3a7464b16db084d96ae4e8c9c72854b1"
            ),
        )
        self.assertEqual(
            receipt["target_chain_sha256"],
            (
                "a53afecd88edf8d5502427d53945d411"
                "92de64a7d55c07cbdbf70311b7431e2b"
            ),
        )
        expected = [
            (record.q, t)
            for record in schedule.execution_records
            for t in range(record.t_index_count)
        ]
        self.assertEqual(observed, expected)
        self.assertEqual(receipt["row_reference_count"], len(expected))
        self.assertEqual(receipt["target_count"], len(targets))
        self.assertTrue(
            receipt["decisions"]["exact_formulaic_q_t_coverage_consumed"]
        )
        self.assertFalse(receipt["decisions"]["cuda_executed"])
        self.assertFalse(receipt["decisions"]["external_atom_discharged"])

    def test_compressed_accounting_matches_expansion_and_q_shards(self) -> None:
        schedule = _bounded_schedule(
            ((10_001, 7), (10_003, 23), (10_004, 16), (10_005, 31))
        )
        lanes = (
            LaneRange(0, 0, 8),
            LaneRange(1, 8, 16),
            LaneRange(2, 16, 31),
        )
        whole = formulaic_accounting(
            schedule, lanes, maximum_batch_count=8
        )
        shards = [
            formulaic_accounting(
                schedule,
                lanes,
                start_execution_q_index=index,
                stop_execution_q_index=index + 1,
                maximum_batch_count=8,
            )
            for index in range(len(schedule.execution_records))
        ]
        self.assertEqual(
            whole["target_count"], sum(item["target_count"] for item in shards)
        )
        self.assertEqual(
            whole["row_reference_count"],
            sum(item["row_reference_count"] for item in shards),
        )
        self.assertEqual(whole["serialized_control_records_required"], 0)

    def test_full_source_pins_without_target_materialization(self) -> None:
        schedule = parse_schedule_manifest(
            build_schedule_manifest_bytes(
                source_schedule_records(), full_source=True
            )
        )
        accounting = formulaic_accounting(schedule, source_lanes())
        self.assertTrue(accounting["source_scale_pins_matched"])
        self.assertEqual(accounting["target_count"], PINNED_SOURCE_TARGETS)
        self.assertEqual(accounting["row_reference_count"], PINNED_SOURCE_ROWS)
        self.assertEqual(
            tuple(accounting["per_lane_target_counts"]),
            PINNED_SOURCE_LANE_TARGETS,
        )
        self.assertEqual(
            tuple(accounting["per_lane_row_reference_counts"]),
            PINNED_SOURCE_LANE_ROWS,
        )
        self.assertEqual(accounting["q_count"], 292_500)
        self.assertFalse(accounting["cuda_executed"])

    def test_target_substitution_and_reordering_fail_closed(self) -> None:
        schedule = _bounded_schedule(((10_001, 9), (10_003, 13)))
        lanes = (LaneRange(0, 0, 8), LaneRange(1, 8, 13))
        cursor = FormulaicQMajorCursor(
            schedule, lanes, maximum_batch_count=8
        )
        target = cursor.expected_target()
        assert target is not None
        with self.assertRaisesRegex(
            DirichletFormulaicQMajorError, "skipped, substituted, or reordered"
        ):
            cursor.accept(
                FormulaicTarget(
                    target.execution_q_index,
                    target.q,
                    target.lane_index,
                    target.first_t_index,
                    target.t_index_stop_exclusive - 1,
                )
            )
        cursor.accept(target)
        next_target = cursor.expected_target()
        assert next_target is not None
        with self.assertRaisesRegex(
            DirichletFormulaicQMajorError, "skipped, substituted, or reordered"
        ):
            cursor.accept(target)
        cursor.accept(next_target)

    def test_lane_gap_overlap_reorder_and_split_batch_rejected(self) -> None:
        schedule = _bounded_schedule(((10_001, 17),))
        bad = (
            (LaneRange(0, 0, 8), LaneRange(1, 9, 17)),
            (LaneRange(0, 0, 9), LaneRange(1, 8, 17)),
            (LaneRange(1, 0, 8), LaneRange(0, 8, 17)),
            (LaneRange(0, 0, 7), LaneRange(1, 7, 17)),
        )
        for lanes in bad:
            with self.subTest(lanes=lanes):
                with self.assertRaises(DirichletFormulaicQMajorError):
                    formulaic_accounting(
                        schedule, lanes, maximum_batch_count=8
                    )

    def test_bool_and_truncated_session_rejected(self) -> None:
        schedule = _bounded_schedule(((10_001, 9),))
        lanes = (LaneRange(0, 0, 8), LaneRange(1, 8, 9))
        with self.assertRaises(DirichletFormulaicQMajorError):
            formulaic_accounting(
                schedule,
                lanes,
                start_execution_q_index=True,  # type: ignore[arg-type]
                maximum_batch_count=8,
            )
        cursor = FormulaicQMajorCursor(
            schedule, lanes, maximum_batch_count=8
        )
        with self.assertRaisesRegex(
            DirichletFormulaicQMajorError, "truncated"
        ):
            cursor.finish()

    def test_target_digest_and_session_are_deterministic(self) -> None:
        schedule = _bounded_schedule(((10_001, 9),))
        lanes = (LaneRange(0, 0, 8), LaneRange(1, 8, 9))

        def run() -> tuple[list[str], dict[str, object]]:
            cursor = FormulaicQMajorCursor(
                schedule, lanes, maximum_batch_count=8
            )
            digests: list[str] = []
            while (target := cursor.expected_target()) is not None:
                digests.append(target.digest())
                self.assertEqual(
                    target.digest(),
                    hashlib.sha256(
                        b"TG_DIRICHLET_FORMULAIC_QMAJOR_TARGET_V1"
                        + target.packed()
                    ).hexdigest(),
                )
                cursor.accept(target.report())
            return digests, cursor.finish()

        first = run()
        second = run()
        self.assertEqual(first, second)

    def test_capability_does_not_overclaim(self) -> None:
        report = capability()
        self.assertTrue(report["constant_memory_target_cursor_implemented"])
        self.assertEqual(report["serialized_source_control_records_required"], 0)
        self.assertTrue(report["cuda_executor_consumes_cursor_directly"])
        self.assertTrue(
            report["descriptor_free_bounded_binary_service_implemented"]
        )
        self.assertTrue(report["bounded_real_cuda_kat_implemented"])
        self.assertEqual(
            report[
                "source_formulaic_raw_lattice_transfer_bytes_if_executed"
            ],
            3_814_313_864_200_192,
        )
        self.assertFalse(
            report["preserves_tmajor_one_upload_per_physical_row"]
        )
        self.assertFalse(report["economical_production_storage_solution"])
        self.assertEqual(
            report["candidate_resident_t_shard_cuts"],
            [
                0,
                768,
                1_600,
                2_368,
                3_200,
                4_032,
                5_568,
                9_600,
                49_088,
                88_512,
                127_988,
            ],
        )
        self.assertEqual(
            report["candidate_resident_t_shard_phase_count"], 10
        )
        self.assertEqual(
            report["candidate_resident_t_shard_maximum_rows"], 39_488
        )
        self.assertEqual(
            report["candidate_resident_t_shard_report_sha256"],
            "eae086771356cc3e2cc26780012686f"
            "dbc3a8097aa76a3417056fe74f5a32eb6",
        )
        self.assertFalse(
            report["candidate_resident_t_shard_executor_implemented"]
        )
        self.assertFalse(report["production_run_completed"])
        self.assertFalse(report["cuda_executor_accepts_full_source_schedule"])
        self.assertFalse(report["trusted_execution_attested"])
        self.assertFalse(report["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
