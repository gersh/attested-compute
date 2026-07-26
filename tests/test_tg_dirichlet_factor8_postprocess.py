# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier import dirichlet_factor8_postprocess as factor8  # noqa: E402


PINNED_FLINT = (
    factor8.FLINT_IMPORT_ERROR is None
    and factor8.flint.__version__ == "0.9.0"
    and factor8.flint.__FLINT_VERSION__ == "3.6.0"
)
RUNNER = os.environ.get("TG_DIRICHLET_FACTOR8_RUNNER")


def _synthetic_input(coefficient_raw: bytes, *, base_count: int = 512) -> bytes:
    intervals: list[tuple[float, float]] = []
    for index in range(base_count):
        center = math.sin(index * 0.071) + 0.2 * math.cos(index * 0.017)
        intervals.append(
            (
                math.nextafter(center - 1e-12, -math.inf),
                math.nextafter(center + 1e-12, math.inf),
            )
        )
    return factor8.make_input_artifact(
        q=10001,
        conrey_number=3,
        parity=1,
        first_base_index=0,
        intervals=intervals,
        first_fine_index=20 * 8,
        output_count=(base_count - 40) * 8,
        interpolation_error_upper=math.nextafter(8.6e-8, math.inf),
        coefficient_artifact_sha256=hashlib.sha256(coefficient_raw).hexdigest(),
        upstream_sha256="ab" * 32,
    )


class Factor8StructuralTests(unittest.TestCase):
    def test_exact_work_units_distinguish_targets_from_sinc_terms(self) -> None:
        audit = factor8.work_audit()
        self.assertEqual(
            audit["factor8_target_grid_samples"], 1_571_337_544_104_271
        )
        self.assertEqual(
            audit["all_base_grid_completed_value_samples"], 196_430_125_886_102
        )
        self.assertEqual(
            audit["factor8_nonaligned_interpolated_targets"],
            1_374_907_418_218_169,
        )
        self.assertEqual(
            audit["factor8_forty_tap_interval_products"],
            54_996_296_728_726_760,
        )
        self.assertIn("input interval term", audit["old_100985_per_second_unit"])

    def test_cuda_source_uses_explicit_directed_intrinsics_and_no_transcendental(self) -> None:
        header = (
            ROOT
            / "gpu/include/sparkinterval/tg_dirichlet_factor8_postprocess.cuh"
        ).read_text(encoding="utf-8")
        source = (
            ROOT
            / "gpu/platform/h100/h100_tg_dirichlet_factor8_postprocess.cu"
        ).read_text(encoding="utf-8")
        for token in (
            "__dmul_rd",
            "__dmul_ru",
            "__dadd_rd",
            "__dadd_ru",
            "__fma_rd",
            "__fma_ru",
        ):
            self.assertIn(token, header)
        self.assertIn("__dsub_rd", header)
        self.assertNotIn("sin(", header)
        self.assertNotIn("exp(", header)
        self.assertIn("--fmad=false", (ROOT / "CMakeLists.txt").read_text())
        self.assertIn("physical_cuda_refinement_proved\\\":false", source)

    def test_input_parser_rejects_trailing_bytes_and_bad_digest(self) -> None:
        coefficient_raw = bytes(factor8.COEFFICIENT_BYTES)
        # The coefficient digest is only a binding at this layer; coefficient
        # semantics are checked by the dedicated parser/replayer.
        intervals = [(1.0, 1.0)] * 64
        raw = factor8.make_input_artifact(
            q=101,
            conrey_number=2,
            parity=0,
            first_base_index=0,
            intervals=intervals,
            first_fine_index=20 * 8 + 1,
            output_count=8,
            interpolation_error_upper=math.nextafter(8.6e-8, math.inf),
            coefficient_artifact_sha256=hashlib.sha256(coefficient_raw).digest(),
            upstream_sha256=b"\x11" * 32,
        )
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "trailing bytes"
        ):
            factor8.read_input_artifact(raw + b"x")
        corrupted = bytearray(raw)
        corrupted[-1] ^= 1
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "payload digest"
        ):
            factor8.read_input_artifact(bytes(corrupted))

    def test_input_rejects_interpolation_error_understatement(self) -> None:
        coefficient_sha = hashlib.sha256(bytes(factor8.COEFFICIENT_BYTES)).digest()
        intervals = [(1.0, 1.0)] * 64
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "below 8.6e-8"
        ):
            factor8.make_input_artifact(
                q=101,
                conrey_number=2,
                parity=0,
                first_base_index=0,
                intervals=intervals,
                first_fine_index=20 * 8 + 1,
                output_count=8,
                interpolation_error_upper=0.0,
                coefficient_artifact_sha256=coefficient_sha,
                upstream_sha256=b"\x11" * 32,
            )
        valid = factor8.make_input_artifact(
            q=101,
            conrey_number=2,
            parity=0,
            first_base_index=0,
            intervals=intervals,
            first_fine_index=20 * 8 + 1,
            output_count=8,
            interpolation_error_upper=math.nextafter(8.6e-8, math.inf),
            coefficient_artifact_sha256=coefficient_sha,
            upstream_sha256=b"\x11" * 32,
        )
        understated = bytearray(valid)
        fields = list(factor8.INPUT_HEADER.unpack_from(understated))
        fields[9] = 0.0
        understated[: factor8.INPUT_HEADER.size] = factor8.INPUT_HEADER.pack(*fields)
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "below 8.6e-8"
        ):
            factor8.read_input_artifact(bytes(understated))

    def test_input_rejects_fine_index_overflow(self) -> None:
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "overflows int64"
        ):
            factor8.make_input_artifact(
                q=101,
                conrey_number=2,
                parity=0,
                first_base_index=0,
                intervals=[(1.0, 1.0)] * 64,
                first_fine_index=(1 << 63) - 1,
                output_count=2,
                interpolation_error_upper=math.nextafter(8.6e-8, math.inf),
                coefficient_artifact_sha256=b"\x22" * 32,
                upstream_sha256=b"\x11" * 32,
            )

    def test_signed_coefficient_two_corner_hull_equals_four_corners(self) -> None:
        values = (
            (Fraction(-7), Fraction(-2)),
            (Fraction(-5), Fraction(3)),
            (Fraction(2), Fraction(11)),
        )
        coefficients = (
            (Fraction(2), Fraction(5)),
            (Fraction(-5), Fraction(-2)),
        )
        for value in values:
            for coefficient in coefficients:
                four = factor8._product_bounds(value, coefficient)
                if coefficient[0] > 0:
                    if value[0] >= 0:
                        two = (
                            value[0] * coefficient[0],
                            value[1] * coefficient[1],
                        )
                    elif value[1] <= 0:
                        two = (
                            value[0] * coefficient[1],
                            value[1] * coefficient[0],
                        )
                    else:
                        two = (
                            value[0] * coefficient[1],
                            value[1] * coefficient[1],
                        )
                elif value[0] >= 0:
                    two = (
                        value[1] * coefficient[0],
                        value[0] * coefficient[1],
                    )
                elif value[1] <= 0:
                    two = (
                        value[1] * coefficient[1],
                        value[0] * coefficient[0],
                    )
                else:
                    two = (
                        value[1] * coefficient[0],
                        value[0] * coefficient[0],
                    )
                self.assertEqual(two, four)


@unittest.skipUnless(PINNED_FLINT, "requires pinned python-flint")
class Factor8CoefficientAndReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.coefficient_raw = factor8.generate_coefficient_artifact()

    def test_all_280_coefficients_have_fresh_arb_containment(self) -> None:
        report = factor8.verify_coefficient_artifact(
            self.coefficient_raw, precision=320
        )
        self.assertEqual(report["coefficient_count"], 280)
        self.assertTrue(report["complete_fresh_arb_replay"])
        self.assertFalse(report["physical_cuda_refinement_proved"])

    def test_exact_reference_artifact_round_trip(self) -> None:
        input_raw = _synthetic_input(self.coefficient_raw, base_count=96)
        shard = factor8.read_input_artifact(input_raw)
        coefficients = factor8.read_coefficient_artifact(self.coefficient_raw)
        codes = factor8.exact_codes(shard, coefficients)
        output_raw = factor8.make_output_artifact(
            shard,
            coefficient_artifact_raw=self.coefficient_raw,
            codes=codes,
        )
        receipt = factor8.verify_output_artifact(
            self.coefficient_raw, input_raw, output_raw
        )
        self.assertEqual(receipt["target_samples_replayed"], shard.output_count)
        self.assertEqual(
            receipt["strict_samples_replayed"]
            + receipt["ambiguous_samples"],
            shard.output_count,
        )
        self.assertTrue(receipt["complete_exact_rational_endpoint_replay"])
        self.assertFalse(receipt["production_ready"])
        self.assertFalse(receipt["external_atom_discharged"])

    def test_checker_rejects_forged_strict_sign(self) -> None:
        input_raw = _synthetic_input(self.coefficient_raw, base_count=96)
        shard = factor8.read_input_artifact(input_raw)
        coefficients = factor8.read_coefficient_artifact(self.coefficient_raw)
        codes = bytearray(factor8.exact_codes(shard, coefficients))
        offset = next(
            index
            for index in range(shard.output_count)
            if factor8.exact_output_interval(shard, coefficients, index)[0] > 0
        )
        codes[offset] = factor8.NEGATIVE_CODE
        forged = factor8.make_output_artifact(
            shard,
            coefficient_artifact_raw=self.coefficient_raw,
            codes=bytes(codes),
        )
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "negative code"
        ):
            factor8.verify_output_artifact(
                self.coefficient_raw, input_raw, forged
            )

    def test_coefficient_parser_rejects_payload_corruption(self) -> None:
        corrupted = bytearray(self.coefficient_raw)
        corrupted[-1] ^= 1
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "payload digest"
        ):
            factor8.read_coefficient_artifact(bytes(corrupted))

    def test_coefficient_parser_rejects_rehashed_zero_crossing_interval(self) -> None:
        corrupted = bytearray(self.coefficient_raw)
        start = factor8.COEFFICIENT_HEADER.size
        corrupted[start : start + factor8.INTERVAL.size] = factor8.INTERVAL.pack(
            -1.0, 1.0
        )
        fields = list(factor8.COEFFICIENT_HEADER.unpack_from(corrupted))
        fields[-1] = hashlib.sha256(
            corrupted[factor8.COEFFICIENT_HEADER.size :]
        ).digest()
        corrupted[: factor8.COEFFICIENT_HEADER.size] = (
            factor8.COEFFICIENT_HEADER.pack(*fields)
        )
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "crosses zero"
        ):
            factor8.read_coefficient_artifact(bytes(corrupted))

    def test_output_parser_rejects_rehashed_reserved_code(self) -> None:
        input_raw = _synthetic_input(self.coefficient_raw, base_count=96)
        shard = factor8.read_input_artifact(input_raw)
        coefficients = factor8.read_coefficient_artifact(self.coefficient_raw)
        output = bytearray(
            factor8.make_output_artifact(
                shard,
                coefficient_artifact_raw=self.coefficient_raw,
                codes=factor8.exact_codes(shard, coefficients),
            )
        )
        payload = bytearray(output[factor8.OUTPUT_HEADER.size :])
        payload[0] = (payload[0] & 0xFC) | factor8.RESERVED_CODE
        fields = list(factor8.OUTPUT_HEADER.unpack_from(output))
        fields[-1] = hashlib.sha256(payload).digest()
        output[: factor8.OUTPUT_HEADER.size] = factor8.OUTPUT_HEADER.pack(*fields)
        output[factor8.OUTPUT_HEADER.size :] = payload
        with self.assertRaisesRegex(
            factor8.Factor8PostprocessError, "reserved code"
        ):
            factor8.verify_output_artifact(
                self.coefficient_raw, input_raw, bytes(output)
            )

    @unittest.skipUnless(RUNNER, "TG_DIRICHLET_FACTOR8_RUNNER is not set")
    def test_cuda_artifact_has_complete_exact_rational_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            coefficient_path = root / "coefficients.bin"
            input_path = root / "input.bin"
            output_path = root / "output.bin"
            four_corner_path = root / "four-corner.bin"
            input_raw = _synthetic_input(self.coefficient_raw, base_count=4096)
            coefficient_path.write_bytes(self.coefficient_raw)
            input_path.write_bytes(input_raw)
            completed = subprocess.run(
                [RUNNER, coefficient_path, input_path, output_path, "5"],
                check=True,
                capture_output=True,
                text=True,
            )
            benchmark = json.loads(completed.stdout)
            self.assertGreater(benchmark["target_samples_per_second"], 0)
            self.assertGreater(
                benchmark["forty_tap_interval_products_per_second"], 0
            )
            receipt = factor8.verify_output_artifact(
                coefficient_path, input_path, output_path
            )
            self.assertTrue(receipt["complete_exact_rational_endpoint_replay"])
            self.assertEqual(benchmark["device_error_or"], 0)
            subprocess.run(
                [
                    RUNNER,
                    coefficient_path,
                    input_path,
                    four_corner_path,
                    "1",
                    "--four-corner",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(output_path.read_bytes(), four_corner_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
