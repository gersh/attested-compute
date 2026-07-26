# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import math
import os
from pathlib import Path
import tempfile
import unittest

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    INPUT_MAGIC,
)
from tg_verifier.dirichlet_tmajor_recurrence_downstream import (
    DirichletTMajorRecurrenceDownstreamError,
    _zero_hull_transform_frame,
    compare_factor_rosters,
    compare_interval_streams,
    run_qualification,
)


ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = (
    ROOT
    / "build/tg-production-kat/sparkinterval-tg-dirichlet-largeq-seeded"
)
ALLCHARS = (
    ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars"
)
CHECKER = (
    ROOT
    / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr"
)
RUN_FULL = os.environ.get(
    "TG_RUN_DIRICHLET_RECURRENCE_DOWNSTREAM_KAT"
) == "1"


def _stream(boxes: tuple[tuple[float, float, float, float], ...]) -> bytes:
    return INPUT_HEADER.pack(
        INPUT_MAGIC,
        1,
        5,
        1,
        1,
        len(boxes),
        0,
        64,
        5,
        len(boxes),
        0,
    ) + b"".join(COMPLEX_INTERVAL.pack(*box) for box in boxes)


class DirichletTMajorRecurrenceDownstreamStructuralTest(unittest.TestCase):
    def test_factor_comparison_requires_complete_containment(self) -> None:
        direct = {10_001: ((1.0, 2.0, -1.0, 1.0),)}
        recurrence = {10_001: ((0.5, 2.5, -2.0, 2.0),)}
        report = compare_factor_rosters(direct, recurrence)
        self.assertTrue(
            report["all_recurrence_factors_contain_direct_MPFR"]
        )
        attacked = {10_001: ((1.5, 2.5, -2.0, 2.0),)}
        with self.assertRaisesRegex(
            DirichletTMajorRecurrenceDownstreamError,
            "does not contain",
        ):
            compare_factor_rosters(direct, attacked)

    def test_stream_attack_cannot_hide_inward_endpoint(self) -> None:
        direct = _stream(((1.0, 2.0, -1.0, 1.0),))
        recurrence = _stream(((0.5, 2.5, -2.0, 2.0),))
        report = compare_interval_streams(
            direct, recurrence, output=False
        )
        self.assertTrue(
            report["all_recurrence_intervals_contain_direct"]
        )
        attacked = bytearray(recurrence)
        offset = INPUT_HEADER.size
        box = list(COMPLEX_INTERVAL.unpack_from(attacked, offset))
        box[0] = math.nextafter(1.0, math.inf)
        COMPLEX_INTERVAL.pack_into(attacked, offset, *box)
        with self.assertRaisesRegex(
            DirichletTMajorRecurrenceDownstreamError,
            "does not contain",
        ):
            compare_interval_streams(
                direct, bytes(attacked), output=False
            )

    def test_transform_elapsed_field_is_not_treated_as_value_identity(
        self,
    ) -> None:
        # The output parser intentionally excludes elapsed nanoseconds from
        # frame identity; the interval payload remains the compared object.
        from tg_verifier.dirichlet_allchars_stage import (
            OUTPUT_HEADER,
            OUTPUT_MAGIC,
        )

        left = OUTPUT_HEADER.pack(
            OUTPUT_MAGIC, 1, 5, 1, 1, 1, 1, 10, 11
        ) + COMPLEX_INTERVAL.pack(1.0, 2.0, 3.0, 4.0)
        right = OUTPUT_HEADER.pack(
            OUTPUT_MAGIC, 1, 5, 1, 1, 1, 1, 10, 99
        ) + COMPLEX_INTERVAL.pack(0.0, 3.0, 2.0, 5.0)
        report = compare_interval_streams(left, right, output=True)
        self.assertFalse(report["byte_identical_streams"])
        self.assertEqual(report["recurrence_contains_direct_count"], 1)

    def test_consumer_zero_hull_is_outward_only(self) -> None:
        from tg_verifier.dirichlet_allchars_stage import (
            OUTPUT_HEADER,
            OUTPUT_MAGIC,
        )

        raw = OUTPUT_HEADER.pack(
            OUTPUT_MAGIC, 1, 5, 1, 1, 1, 1, 10, 11
        ) + COMPLEX_INTERVAL.pack(1.0, 2.0, -4.0, -3.0)
        hulled = _zero_hull_transform_frame(raw)
        self.assertEqual(hulled[: OUTPUT_HEADER.size], raw[: OUTPUT_HEADER.size])
        self.assertEqual(
            COMPLEX_INTERVAL.unpack_from(hulled, OUTPUT_HEADER.size),
            (0.0, 2.0, -4.0, 0.0),
        )


@unittest.skipUnless(
    RUN_FULL
    and COMPOSITION.is_file()
    and ALLCHARS.is_file()
    and CHECKER.is_file(),
    "set TG_RUN_DIRICHLET_RECURRENCE_DOWNSTREAM_KAT=1 for the bounded "
    "real CUDA/MPFR/Arb qualification",
)
class DirichletTMajorRecurrenceDownstreamProcessTest(unittest.TestCase):
    def test_real_cuda_mpfr_and_arb_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_qualification(
                Path(temporary),
                composition_runner=COMPOSITION,
                allchars_runner=ALLCHARS,
                allchars_checker=CHECKER,
                timeout_seconds=900.0,
            )
            self.assertTrue(
                report["factor_comparison"][
                    "all_recurrence_factors_contain_direct_MPFR"
                ]
            )
            self.assertTrue(
                report["composition_comparison"][
                    "all_recurrence_intervals_contain_direct"
                ]
            )
            self.assertTrue(
                report["transform_comparison"][
                    "all_recurrence_intervals_contain_direct"
                ]
            )
            self.assertGreater(
                report["transform_comparison"][
                    "median_recurrence_over_direct_width"
                ],
                1.0,
            )
            self.assertTrue(
                report["Arb_FLINT_consumer"]["direct"][
                    "Arb_FLINT_consumer_executed"
                ]
            )
            self.assertTrue(
                report["Arb_FLINT_consumer"]["recurrence"][
                    "Arb_FLINT_consumer_executed"
                ]
            )
            self.assertFalse(
                report["assessment"][
                    "recurrence_beneficial_for_current_pipeline"
                ]
            )
            self.assertFalse(report["source_scale_run"])
            self.assertFalse(report["trusted_execution_attested"])
            self.assertFalse(report["external_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
