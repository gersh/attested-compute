from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from reference import exact_binary64 as exact
from tools import run_expression_conformance as conformance


class ExpressionBatchFormatTests(unittest.TestCase):
    def test_curated_suite_covers_every_opcode(self) -> None:
        operations = {
            instruction.op
            for program in conformance.curated_programs()
            for instruction in program.instructions
        }
        self.assertEqual(operations, set(conformance.OPCODES))
        for program in conformance.curated_programs():
            self.assertGreaterEqual(conformance.validated_max_stack(program), 1)
        stack_boundary = next(
            program
            for program in conformance.curated_programs()
            if program.name == "stack_32_boundary"
        )
        self.assertEqual(
            conformance.validated_max_stack(stack_boundary),
            conformance.MAX_STACK_DEPTH,
        )
        pow_boundary = next(
            program
            for program in conformance.curated_programs()
            if program.name == "pow_64_boundary"
        )
        self.assertEqual(pow_boundary.instructions[-1].argument, 64)

    def test_postfix_validation_rejects_underflow_and_bad_payload(self) -> None:
        underflow = conformance.Program(
            "underflow", 0, (conformance.op("add"),)
        )
        with self.assertRaisesRegex(ValueError, "underflows"):
            conformance.validated_max_stack(underflow)

        payload = conformance.Program(
            "payload",
            1,
            (conformance.Instruction("var", argument=0, lo_bits=1),),
        )
        with self.assertRaisesRegex(ValueError, "endpoint payload"):
            conformance.validated_max_stack(payload)

    def test_input_has_fixed_width_header_program_and_rows(self) -> None:
        program = conformance.Program(
            "add", 2, (conformance.var(0), conformance.var(1), conformance.op("add"))
        )
        rows = conformance.rows_for_program(program, 7, 1234)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            conformance.write_input(path, program, rows)
            expected = (
                conformance.HEADER.size
                + len(program.instructions) * conformance.INSTRUCTION.size
                + len(rows) * program.variable_count * conformance.INTERVAL.size
            )
            self.assertEqual(path.stat().st_size, expected)
            with path.open("rb") as stream:
                self.assertEqual(
                    conformance._read_header(stream, conformance.INPUT_MAGIC),
                    (
                        len(program.instructions),
                        program.variable_count,
                        conformance.validated_max_stack(program),
                        len(rows),
                    ),
                )

    def test_exact_evaluator_reports_dynamic_zero_divisor(self) -> None:
        program = conformance.Program(
            "div", 2, (conformance.var(0), conformance.var(1), conformance.op("div"))
        )
        one = exact.Binary64Interval(0x3FF0000000000000, 0x3FF0000000000000)
        crosses_zero = exact.Binary64Interval(
            0xBFF0000000000000, 0x3FF0000000000000
        )
        self.assertEqual(
            conformance.evaluate_program(program, (one, crosses_zero)),
            (0, 0, conformance.STATUS_DIVISOR_CONTAINS_ZERO),
        )

    def test_exact_evaluator_uses_four_corner_interval_multiplication(self) -> None:
        program = conformance.Program(
            "mul", 2, (conformance.var(0), conformance.var(1), conformance.op("mul"))
        )
        left = exact.Binary64Interval(0xC000000000000000, 0x3FF0000000000000)
        right = exact.Binary64Interval(0xC008000000000000, 0x4010000000000000)
        expected = exact.interval_mul(left, right)
        self.assertEqual(
            conformance.evaluate_program(program, (left, right)),
            (expected.lo, expected.hi, conformance.STATUS_VALID),
        )

    def test_final_overflow_is_valid_but_later_arithmetic_records_widening(self) -> None:
        final_overflow = conformance.Program(
            "final_overflow",
            0,
            (
                conformance.const(exact.MAX_FINITE),
                conformance.const(exact.MAX_FINITE),
                conformance.op("add"),
            ),
        )
        lo, hi, status = conformance.evaluate_program(final_overflow, ())
        self.assertEqual(status, conformance.STATUS_VALID)
        self.assertTrue(exact.is_finite(lo))
        self.assertEqual(hi, exact.POSITIVE_INFINITY)

        widened = conformance.Program(
            "widened",
            0,
            final_overflow.instructions
            + (conformance.const(0x3FF0000000000000), conformance.op("add")),
        )
        self.assertEqual(
            conformance.evaluate_program(widened, ()),
            (
                exact.NEGATIVE_INFINITY,
                exact.POSITIVE_INFINITY,
                conformance.STATUS_NONFINITE_INTERMEDIATE_WIDENING,
            ),
        )

    def test_repeated_power_records_nonfinite_intermediate_widening(self) -> None:
        power_one = conformance.Program(
            "power_one",
            0,
            (conformance.const(exact.MAX_FINITE), conformance.op("pow_nat", 1)),
        )
        self.assertEqual(
            conformance.evaluate_program(power_one, ())[2], conformance.STATUS_VALID
        )
        power_two = conformance.Program(
            "power_two",
            0,
            (conformance.const(exact.MAX_FINITE), conformance.op("pow_nat", 2)),
        )
        self.assertEqual(
            conformance.evaluate_program(power_two, ())[2], conformance.STATUS_VALID
        )
        power_three = conformance.Program(
            "power_three",
            0,
            (conformance.const(exact.MAX_FINITE), conformance.op("pow_nat", 3)),
        )
        self.assertEqual(
            conformance.evaluate_program(power_three, ()),
            (
                exact.NEGATIVE_INFINITY,
                exact.POSITIVE_INFINITY,
                conformance.STATUS_NONFINITE_INTERMEDIATE_WIDENING,
            ),
        )

    def test_random_programs_and_rows_are_deterministic(self) -> None:
        first_programs = conformance.randomized_programs(5, 987654)
        second_programs = conformance.randomized_programs(5, 987654)
        self.assertEqual(first_programs, second_programs)
        first_rows = conformance.rows_for_program(first_programs[0], 20, 987654)
        second_rows = conformance.rows_for_program(second_programs[0], 20, 987654)
        self.assertEqual(first_rows, second_rows)
        for row in first_rows:
            self.assertTrue(all(value.has_finite_endpoints for value in row))

    def test_basic_binary_programs_include_cartesian_bit_boundaries(self) -> None:
        multiplication = next(
            program
            for program in conformance.curated_programs()
            if program.name == "mul"
        )
        rows = conformance.rows_for_program(multiplication, 0, 1)
        expected = len(conformance.SPECIAL_INTERVALS) + len(
            conformance.CARTESIAN_POINT_INTERVALS
        ) ** 2
        self.assertEqual(len(rows), expected)
        cartesian = rows[len(conformance.SPECIAL_INTERVALS) :]
        self.assertIn(
            (
                conformance.CARTESIAN_POINT_INTERVALS[1],
                conformance.CARTESIAN_POINT_INTERVALS[2],
            ),
            cartesian,
        )

    def test_synthetic_output_is_compared_bit_for_bit(self) -> None:
        program = conformance.Program(
            "neg", 1, (conformance.var(0), conformance.op("neg"))
        )
        rows = conformance.rows_for_program(program, 3, 44)
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "output.bin"
            payload = bytearray(
                conformance.HEADER.pack(
                    conformance.OUTPUT_MAGIC,
                    conformance.FORMAT_VERSION,
                    len(program.instructions),
                    program.variable_count,
                    conformance.validated_max_stack(program),
                    len(rows),
                )
            )
            for row in rows:
                lo, hi, status = conformance.evaluate_program(program, row)
                payload += conformance.OUTPUT.pack(lo, hi, status, bytes(7))
            output_path.write_bytes(payload)
            report = conformance.compare_output(output_path, program, rows)
            self.assertTrue(report["passed"])
            self.assertEqual(report["mismatch_count"], 0)


if __name__ == "__main__":
    unittest.main()
