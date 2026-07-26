# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tg_verifier.dirichlet_allchars_q_scheduler import (
    BOUNDED_CLASSIFICATION,
    DirichletAllCharsQSchedulerError,
    FULL_SOURCE_CLASSIFICATION,
    MANIFEST_HEADER,
    PINNED_SOURCE_EXECUTION_SHA256,
    PINNED_SOURCE_ROSTER_SHA256,
    ScheduleRecord,
    build_schedule_manifest_bytes,
    component_signature,
    parse_schedule_manifest,
    phase_schedule_projection,
    source_schedule_inventory,
    source_schedule_records,
    validate_scheduled_multiq_framed_summary,
    write_bounded_schedule_manifest,
)


class DirichletAllCharsQSchedulerTest(unittest.TestCase):
    def test_full_source_manifest_and_optimal_cache_inventory_are_exact(self) -> None:
        records = source_schedule_records()
        raw = build_schedule_manifest_bytes(records, full_source=True)
        parsed = parse_schedule_manifest(raw)
        self.assertEqual(parsed.classification, FULL_SOURCE_CLASSIFICATION)
        self.assertEqual(parsed.q_count, 292_500)
        self.assertEqual(parsed.t_row_count, 3_637_613_167)
        self.assertEqual(
            parsed.source_roster_sha256, PINNED_SOURCE_ROSTER_SHA256
        )
        self.assertEqual(
            parsed.execution_order_sha256,
            PINNED_SOURCE_EXECUTION_SHA256,
        )
        self.assertEqual(parsed.execution_records[0].q, 10_080)
        self.assertEqual(parsed.execution_records[-1].q, 399_989)
        self.assertEqual(len(raw), 2_340_112)

        inventory = source_schedule_inventory()
        self.assertTrue(
            inventory["attains_cold_cache_preparation_lower_bound"]
        )
        self.assertEqual(
            inventory["order_cache_prepared_enclosures"], 12_948_488_448
        )
        self.assertEqual(
            inventory["root_pool_prepared_enclosures"], 4_194_258
        )
        self.assertEqual(
            inventory["total_prepared_enclosures"], 12_952_682_706
        )
        self.assertEqual(
            inventory["saved_prepared_enclosures"], 5_153_638_792
        )
        self.assertEqual(inventory["order_cache_misses"], 34_000)
        self.assertEqual(inventory["order_cache_hits"], 782_177)
        self.assertEqual(inventory["order_cache_uncached_misses"], 0)
        self.assertLessEqual(
            inventory["cache_peak_total_retained_bytes"], 512 * 1024 * 1024
        )

    def test_bounded_manifest_is_nonmonotone_but_canonical_and_bound(self) -> None:
        records = (
            ScheduleRecord(10_001, 2),
            ScheduleRecord(10_080, 1),
            ScheduleRecord(11_088, 3),
            ScheduleRecord(18_480, 2),
        )
        raw = build_schedule_manifest_bytes(records)
        parsed = parse_schedule_manifest(raw)
        self.assertEqual(parsed.classification, BOUNDED_CLASSIFICATION)
        self.assertEqual(
            [record.q for record in parsed.execution_records],
            [10_080, 18_480, 11_088, 10_001],
        )
        self.assertEqual(
            [
                component_signature(record.q)
                for record in parsed.execution_records
            ],
            sorted(component_signature(record.q) for record in records),
        )
        with self.assertRaisesRegex(
            DirichletAllCharsQSchedulerError, "full-source"
        ):
            validate_scheduled_multiq_framed_summary(
                {},
                manifest=raw,
                input_stream=b"",
                output_stream=b"",
                require_full_source=True,
            )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "schedule.bin"
            report = write_bounded_schedule_manifest(path, records)
            self.assertEqual(report["manifest_sha256"], parsed.manifest_sha256)
            self.assertEqual(path.read_bytes(), raw)
            with self.assertRaisesRegex(
                DirichletAllCharsQSchedulerError, "refusing to replace"
            ):
                write_bounded_schedule_manifest(path, records)

    def test_manifest_tampering_and_invalid_rosters_fail_closed(self) -> None:
        records = (
            ScheduleRecord(10_001, 2),
            ScheduleRecord(10_080, 1),
        )
        raw = bytearray(build_schedule_manifest_bytes(records))
        raw[MANIFEST_HEADER.size] ^= 1
        with self.assertRaises(DirichletAllCharsQSchedulerError):
            parse_schedule_manifest(raw)
        with self.assertRaisesRegex(
            DirichletAllCharsQSchedulerError, "duplicate"
        ):
            build_schedule_manifest_bytes(
                (ScheduleRecord(10_001, 1), ScheduleRecord(10_001, 2))
            )
        with self.assertRaisesRegex(
            DirichletAllCharsQSchedulerError, "primitive V2"
        ):
            build_schedule_manifest_bytes((ScheduleRecord(10_002, 1),))
        with self.assertRaisesRegex(
            DirichletAllCharsQSchedulerError, "primitive V2"
        ):
            build_schedule_manifest_bytes((ScheduleRecord(10_001, 999_999),))

    def test_phase_projection_skips_inactive_q_and_binds_parent_indices(
        self,
    ) -> None:
        raw = build_schedule_manifest_bytes(
            (
                ScheduleRecord(10_001, 3),
                ScheduleRecord(10_080, 5),
                ScheduleRecord(11_088, 4),
                ScheduleRecord(18_480, 2),
            )
        )
        projection = phase_schedule_projection(
            raw,
            phase_plan_sha256="12" * 32,
            first_t_index=2,
            t_index_stop_exclusive=5,
        )
        self.assertEqual(
            [
                (
                    record.execution_q_index,
                    record.q,
                    record.first_t_index,
                    record.t_index_stop_exclusive,
                )
                for record in projection.active_records
            ],
            [
                (0, 10_080, 2, 5),
                (2, 11_088, 2, 4),
                (3, 10_001, 2, 3),
            ],
        )
        self.assertEqual(projection.active_modulus_count, 3)
        self.assertEqual(projection.t_index_row_count, 6)
        narrowed = phase_schedule_projection(
            raw,
            phase_plan_sha256="12" * 32,
            first_t_index=2,
            t_index_stop_exclusive=4,
            start_execution_q_index=1,
            stop_execution_q_index=4,
        )
        self.assertNotEqual(
            projection.phase_schedule_sha256,
            narrowed.phase_schedule_sha256,
        )
        with self.assertRaisesRegex(
            DirichletAllCharsQSchedulerError, "unused"
        ):
            phase_schedule_projection(
                raw,
                phase_plan_sha256="12" * 32,
                first_t_index=5,
                t_index_stop_exclusive=6,
            )
        with self.assertRaisesRegex(
            DirichletAllCharsQSchedulerError, "digest"
        ):
            phase_schedule_projection(
                raw,
                phase_plan_sha256="A" * 64,
                first_t_index=0,
                t_index_stop_exclusive=1,
            )


if __name__ == "__main__":
    unittest.main()
