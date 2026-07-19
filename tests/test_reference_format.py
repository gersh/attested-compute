from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from reference import evaluator  # noqa: E402
from reference import format as wire  # noqa: E402


ZERO = "0000000000000000"
NEGATIVE_ZERO = "8000000000000000"
MIN_SUBNORMAL = "0000000000000001"
ONE = "3ff0000000000000"
NEGATIVE_ONE = "bff0000000000000"
ONE_NEXT = "3ff0000000000001"
TWO = "4000000000000000"
FOUR = "4010000000000000"
MAX_FINITE = "7fefffffffffffff"
POSITIVE_INFINITY = "7ff0000000000000"


def interval(lo: str, hi: str | None = None) -> dict[str, str]:
    return {"lo": lo, "hi": lo if hi is None else hi}


def batch(
    expression: dict,
    rows: list[list[dict[str, str]]],
    variable_count: int,
) -> dict:
    return {
        "schema_version": 1,
        "kind": wire.BATCH_KIND,
        "algorithm": wire.ALGORITHM_ID,
        "variable_count": variable_count,
        "expression": expression,
        "rows": rows,
    }


class ReferenceFormatTests(unittest.TestCase):
    def test_canonical_json_is_utf8_sorted_compact_and_has_no_newline(self) -> None:
        value = {"z": [2, "λ"], "a": {"n": -3}}
        encoded = wire.canonical_json_bytes(value)
        self.assertEqual(encoded, '{"a":{"n":-3},"z":[2,"λ"]}'.encode())
        self.assertFalse(encoded.endswith(b"\n"))
        self.assertEqual(wire.parse_json_bytes(encoded), value)

    def test_ambiguous_or_non_integer_json_is_rejected(self) -> None:
        rejected = (
            b'{"x":1,"x":2}',
            b'{"x":1.0}',
            b'{"x":NaN}',
            b'{"x":Infinity}',
            b'{"x":true}',
            b'{"x":null}',
            b'{ "x":1}',
            b'{"x":1}\n',
            b'\xef\xbb\xbf{"x":1}',
        )
        for encoded in rejected:
            with self.subTest(encoded=encoded):
                with self.assertRaises(wire.FormatError):
                    wire.parse_json_bytes(encoded)
        for value in ({"x": False}, {"x": None}, {"x": 1.25}):
            with self.subTest(value=value):
                with self.assertRaises(wire.FormatError):
                    wire.canonical_json_bytes(value)

    def test_excessive_json_nesting_fails_closed_without_traceback(self) -> None:
        deeply_nested = b"[" * 2000 + b"0" + b"]" * 2000
        with self.assertRaises(wire.FormatError):
            wire.parse_json_bytes(deeply_nested)

    def test_interval_encoding_rejects_noncanonical_nan_and_order_errors(self) -> None:
        invalid = (
            interval("3FF0000000000000"),
            interval("7ff8000000000000"),
            interval(TWO, ONE),
            interval("000"),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(wire.FormatError):
                    wire.validate_interval(value)
        # Signed zero encodings denote the same mathematical endpoint.
        wire.validate_interval(interval(ZERO, NEGATIVE_ZERO))
        wire.validate_interval(interval(NEGATIVE_ZERO, ZERO))

    def test_batch_requires_finite_inputs_exact_arity_and_bounded_variables(self) -> None:
        good = batch({"op": "var", "index": 0}, [[interval(ONE)]], 1)
        wire.validate_batch(good)
        for mutation in (
            lambda b: b["rows"].__setitem__(0, []),
            lambda b: b["rows"][0].__setitem__(0, interval("7ff0000000000000")),
            lambda b: b["expression"].__setitem__("index", 1),
            lambda b: b.__setitem__("unexpected", 1),
        ):
            changed = copy.deepcopy(good)
            mutation(changed)
            with self.assertRaises(wire.FormatError):
                wire.validate_batch(changed)

        too_large_power = batch(
            {"op": "pow_nat", "arg": {"op": "var", "index": 0}, "exponent": 65},
            [[interval(ONE)]],
            1,
        )
        with self.assertRaisesRegex(wire.FormatError, "at most 64"):
            wire.validate_batch(too_large_power)

    def test_exact_evaluator_uses_outward_rounding(self) -> None:
        request = batch(
            {
                "op": "add",
                "left": {"op": "var", "index": 0},
                "right": {"op": "var", "index": 1},
            },
            [[interval(ONE), interval(MIN_SUBNORMAL)]],
            2,
        )
        result = evaluator.evaluate_batch(request)
        # 1 + 2^-1074 lies strictly between 1 and the next binary64 value.
        self.assertEqual(result["rows"], [interval(ONE, ONE_NEXT)])
        self.assertEqual(result["batch_sha256"], wire.canonical_sha256(request))

    def test_overflow_is_serialized_as_an_infinite_result_endpoint(self) -> None:
        request = batch(
            {
                "op": "mul",
                "left": {"op": "var", "index": 0},
                "right": {"op": "var", "index": 1},
            },
            [[interval(MAX_FINITE), interval(TWO)]],
            2,
        )
        result = evaluator.evaluate_batch(request)
        self.assertEqual(
            result["rows"], [interval(MAX_FINITE, POSITIVE_INFINITY)]
        )

    def test_power_uses_the_formal_repeated_interval_multiplication(self) -> None:
        request = batch(
            {
                "op": "pow_nat",
                "arg": {"op": "var", "index": 0},
                "exponent": 2,
            },
            [[interval(NEGATIVE_ONE, ONE)]],
            1,
        )
        # This deliberately follows Lean's interval recurrence rather than a
        # dependency-aware tight square, which would have lower endpoint zero.
        self.assertEqual(
            evaluator.evaluate_batch(request)["rows"],
            [interval(NEGATIVE_ONE, ONE)],
        )

    def test_nested_expression_and_self_contained_certificate(self) -> None:
        request = batch(
            {
                "op": "mul",
                "left": {
                    "op": "add",
                    "left": {"op": "var", "index": 0},
                    "right": {"op": "const", "value": interval(ONE)},
                },
                "right": {"op": "var", "index": 1},
            },
            [[interval(ONE), interval(TWO)]],
            2,
        )
        certificate = evaluator.issue_certificate(request)
        self.assertEqual(certificate["result"]["rows"], [interval(FOUR)])
        receipt = evaluator.check_certificate(certificate)
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["row_count"], 1)

        # Rehashing a fabricated arithmetic result repairs integrity hashes,
        # but cannot make it pass exact recomputation.
        forged = copy.deepcopy(certificate)
        forged["result"]["rows"][0] = interval(TWO)
        forged["result_sha256"] = wire.canonical_sha256(forged["result"])
        wire.validate_certificate(forged)
        with self.assertRaisesRegex(
            evaluator.CertificateError, "exact recomputation"
        ):
            evaluator.check_certificate(forged)

    def test_divisor_containing_signed_zero_fails_closed(self) -> None:
        request = batch(
            {
                "op": "div",
                "left": {"op": "var", "index": 0},
                "right": {"op": "var", "index": 1},
            },
            [[interval(ONE), interval(NEGATIVE_ZERO, ONE)]],
            2,
        )
        with self.assertRaisesRegex(evaluator.EvaluationError, "row 0"):
            evaluator.evaluate_batch(request)

    def test_cli_writes_and_checks_only_canonical_artifacts(self) -> None:
        request = batch({"op": "const", "value": interval(ONE)}, [[]], 0)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch_path = root / "batch.json"
            certificate_path = root / "certificate.json"
            batch_path.write_bytes(wire.canonical_json_bytes(request))
            certify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reference.cli",
                    "certify",
                    str(batch_path),
                    str(certificate_path),
                ],
                cwd=REPOSITORY,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(certify.returncode, 0, certify.stderr.decode())
            certificate = wire.load_canonical_json(certificate_path)
            self.assertEqual(
                certificate_path.read_bytes(), wire.canonical_json_bytes(certificate)
            )
            check = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reference.cli",
                    "check",
                    str(certificate_path),
                ],
                cwd=REPOSITORY,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(check.returncode, 0, check.stderr.decode())
            receipt = wire.parse_json_bytes(check.stdout)
            self.assertEqual(receipt["status"], "accepted")

            # Pretty JSON contains the same value but is not a protocol input.
            pretty_path = root / "pretty.json"
            pretty_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
            rejected = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reference.cli",
                    "certify",
                    str(pretty_path),
                    str(root / "bad-certificate.json"),
                ],
                cwd=REPOSITORY,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn(b"not canonical JSON", rejected.stderr)

    def test_reference_schemas_are_valid_json(self) -> None:
        for path in sorted((REPOSITORY / "schemas").glob("reference-*.schema.json")):
            with self.subTest(path=path.name):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")

        # The self-contained certificate schema must not require an external
        # resolver or network access.
        certificate_schema = json.loads(
            (REPOSITORY / "schemas/reference-certificate.schema.json").read_text(
                encoding="utf-8"
            )
        )
        pending = [certificate_schema]
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                if "$ref" in current:
                    self.assertTrue(current["$ref"].startswith("#/"))
                pending.extend(current.values())
            elif isinstance(current, list):
                pending.extend(current)


if __name__ == "__main__":
    unittest.main()
