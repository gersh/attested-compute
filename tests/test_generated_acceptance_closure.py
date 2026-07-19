#!/usr/bin/env python3

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

from reference import format as wire


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generated_acceptance_closure",
    ROOT / "tools/close_generated_ptx_acceptance.py",
)
assert SPEC is not None and SPEC.loader is not None
CLOSURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOSURE)


def batch() -> dict:
    return wire.validate_batch(
        {
            "schema_version": 1,
            "kind": wire.BATCH_KIND,
            "algorithm": wire.ALGORITHM_ID,
            "variable_count": 1,
            "expression": {"op": "var", "index": 0},
            "rows": [
                [{"lo": "3ff0000000000000", "hi": "4000000000000000"}]
            ],
        }
    )


class GeneratedAcceptanceClosureTest(unittest.TestCase):
    def write_rows(self, path: Path, lo: int, hi: int) -> None:
        path.write_bytes(
            CLOSURE.GENERATED_HEADER.pack(
                CLOSURE.GENERATED_INPUT_MAGIC, 1, 1, 1
            )
            + struct.pack("<QQ", lo, hi)
        )

    def test_phase4_conversion_binds_every_binary_endpoint_to_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = root / "rows.bin"
            output = root / "phase4.bin"
            self.write_rows(rows, 0x3FF0000000000000, 0x4000000000000000)
            instruction_count, stack, row_count = CLOSURE.make_phase4_input(
                batch(), rows, output
            )
            self.assertEqual((instruction_count, stack, row_count), (1, 1, 1))
            self.assertTrue(output.is_file())

            # Shape and header remain valid, but one retained endpoint differs
            # from the canonical JSON. Closure must reject before GPU execution.
            self.write_rows(rows, 0x3FF0000000000001, 0x4000000000000000)
            with self.assertRaisesRegex(ValueError, "differs from batch"):
                CLOSURE.make_phase4_input(batch(), rows, output)

    def test_exact_recomputation_does_not_trust_base_acceptance_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results.bin"

            def write_result(lo: int, hi: int, status: int) -> None:
                results.write_bytes(
                    CLOSURE.GENERATED_HEADER.pack(
                        CLOSURE.GENERATED_OUTPUT_MAGIC, 1, 1, 1
                    )
                    + CLOSURE.OUTPUT.pack(lo, hi, status, b"\0" * 7)
                )

            write_result(0x3FF0000000000000, 0x4000000000000000, 0)
            verification, _ = CLOSURE.verify_exact_reference(batch(), results)
            self.assertTrue(verification["passed"])
            self.assertEqual(verification["status_counts"], {"0": 1})

            write_result(0x3FF0000000000001, 0x4000000000000000, 0)
            verification, _ = CLOSURE.verify_exact_reference(batch(), results)
            self.assertFalse(verification["passed"])
            self.assertEqual(verification["mismatch_count"], 1)

    def test_signed_zero_probe_identity_is_literal_and_complete(self) -> None:
        probe = CLOSURE.expected_signed_zero_batch()
        self.assertEqual(probe["variable_count"], 2)
        self.assertEqual(len(probe["rows"]), 9)
        self.assertEqual(probe["expression"]["op"], "mul")
        pairs = {
            tuple((interval["lo"], interval["hi"]) for interval in row)
            for row in probe["rows"]
        }
        self.assertEqual(len(pairs), 9)


if __name__ == "__main__":
    unittest.main()
