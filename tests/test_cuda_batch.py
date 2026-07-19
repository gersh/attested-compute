from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest

from reference import exact_binary64 as exact
from tools import run_primitive_conformance as conformance


class CudaBatchFormatTests(unittest.TestCase):
    def test_generated_rows_are_finite_except_explicit_invalid_tail(self) -> None:
        for operation in conformance.OPERATIONS:
            rows = list(conformance.rows_for_operation(operation, 128, 12345))
            expected_count = conformance.row_count(operation, 128)
            self.assertEqual(len(rows), expected_count)
            random_end = len(conformance.CURATED_FINITE_PAIRS) + 128
            for lhs, rhs in rows[:random_end]:
                self.assertTrue(exact.is_finite(lhs))
                self.assertTrue(exact.is_finite(rhs))
                if operation == "div":
                    self.assertFalse(exact.is_zero(rhs))

    def test_input_header_and_exact_length(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "add.input.bin"
            conformance.write_input(path, "add", 7, 99)
            expected_rows = conformance.row_count("add", 7)
            self.assertEqual(
                path.stat().st_size,
                conformance.HEADER.size + expected_rows * conformance.INPUT_ROW.size,
            )
            with path.open("rb") as stream:
                self.assertEqual(
                    conformance._read_header(stream, conformance.INPUT_MAGIC, "add"),
                    expected_rows,
                )

    def test_expected_status_priority(self) -> None:
        one = 0x3FF0000000000000
        self.assertEqual(conformance.expected_status("add", one, one), 0)
        self.assertEqual(
            conformance.expected_status("add", exact.POSITIVE_INFINITY, one), 1
        )
        self.assertEqual(
            conformance.expected_status("div", one, exact.NEGATIVE_ZERO), 2
        )
        self.assertEqual(
            conformance.expected_status(
                "div", exact.POSITIVE_INFINITY, exact.POSITIVE_ZERO
            ),
            1,
        )

    def test_output_header_rejects_wrong_operation(self) -> None:
        encoded = conformance.HEADER.pack(
            conformance.OUTPUT_MAGIC,
            conformance.FORMAT_VERSION,
            conformance.OPERATIONS["mul"],
            1,
        )
        with self.assertRaisesRegex(ValueError, "operation code"):
            conformance._read_header(io.BytesIO(encoded), conformance.OUTPUT_MAGIC, "div")


if __name__ == "__main__":
    unittest.main()
