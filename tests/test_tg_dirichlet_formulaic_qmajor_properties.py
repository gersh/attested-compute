# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic property checks for the formulaic q-major cursor.

The fixed-answer tests pin one cross-language instance.  This suite varies
the batch width, execution order, row counts, and aligned lane partition and
then compares the cursor against the explicit Cartesian q/t roster.
"""

from __future__ import annotations

import random
import unittest

from tg_verifier.dirichlet_allchars_q_scheduler import (
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
)
from tg_verifier.dirichlet_formulaic_qmajor_cursor import (
    FormulaicQMajorCursor,
    LaneRange,
    formulaic_accounting,
)


class DirichletFormulaicQMajorPropertyTests(unittest.TestCase):
    def test_random_aligned_partitions_equal_explicit_roster(self) -> None:
        rng = random.Random(0x7A11C)
        valid_moduli = (10_001, 10_003, 10_004, 10_005)

        for case_index in range(256):
            with self.subTest(case_index=case_index):
                maximum_batch_count = rng.choice((1, 2, 4, 8, 16, 32, 64))
                q_count = rng.randint(1, len(valid_moduli))
                q_values = rng.sample(valid_moduli, q_count)
                source_records = tuple(
                    ScheduleRecord(q, rng.randint(1, 300))
                    for q in q_values
                )
                schedule = parse_schedule_manifest(
                    build_schedule_manifest_bytes(source_records)
                )
                required_t_stop = max(
                    record.t_index_count
                    for record in schedule.execution_records
                )

                cuts = [0]
                next_cut = maximum_batch_count * rng.randint(
                    1,
                    max(
                        1,
                        (
                            required_t_stop
                            + maximum_batch_count
                            - 1
                        )
                        // maximum_batch_count,
                    ),
                )
                while next_cut < required_t_stop:
                    cuts.append(next_cut)
                    next_cut += maximum_batch_count * rng.randint(1, 4)
                cuts.append(max(required_t_stop, next_cut))
                lanes = tuple(
                    LaneRange(index, cuts[index], cuts[index + 1])
                    for index in range(len(cuts) - 1)
                )

                cursor = FormulaicQMajorCursor(
                    schedule,
                    lanes,
                    maximum_batch_count=maximum_batch_count,
                )
                observed: list[tuple[int, int]] = []
                target_count = 0
                while (target := cursor.expected_target()) is not None:
                    self.assertLessEqual(
                        target.batch_count, maximum_batch_count
                    )
                    self.assertGreaterEqual(target.batch_count, 1)
                    observed.extend(
                        (target.q, t_index)
                        for t_index in range(
                            target.first_t_index,
                            target.t_index_stop_exclusive,
                        )
                    )
                    cursor.accept(target)
                    target_count += 1
                receipt = cursor.finish()

                expected = [
                    (record.q, t_index)
                    for record in schedule.execution_records
                    for t_index in range(record.t_index_count)
                ]
                accounting = formulaic_accounting(
                    schedule,
                    lanes,
                    maximum_batch_count=maximum_batch_count,
                )
                self.assertEqual(observed, expected)
                self.assertEqual(accounting["target_count"], target_count)
                self.assertEqual(
                    accounting["row_reference_count"], len(expected)
                )
                self.assertEqual(receipt["target_count"], target_count)
                self.assertEqual(
                    receipt["row_reference_count"], len(expected)
                )


if __name__ == "__main__":
    unittest.main()
