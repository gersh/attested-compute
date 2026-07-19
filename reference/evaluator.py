#!/usr/bin/env python3
"""Deterministic interval-expression evaluator and certificate checker.

All arithmetic is delegated to :mod:`exact_binary64`, whose implementation
uses exact integers and rational values.  This module never converts an
endpoint to a Python ``float``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

try:  # Package import (tests and ``python -m reference.cli``).
    from . import exact_binary64 as exact
    from . import format as wire
except ImportError:  # Direct execution with ``reference`` on sys.path.
    import exact_binary64 as exact  # type: ignore[no-redef]
    import format as wire  # type: ignore[no-redef]


class EvaluationError(ValueError):
    """A well-formed request cannot be evaluated under the fixed semantics."""


class CertificateError(ValueError):
    """A certificate is malformed, unbound, or arithmetically incorrect."""


@dataclass(frozen=True)
class Instruction:
    op: str
    argument: Any = None


def _decode_interval(value: dict[str, str]) -> exact.Binary64Interval:
    return exact.Binary64Interval(int(value["lo"], 16), int(value["hi"], 16))


def _encode_interval(value: exact.Binary64Interval) -> dict[str, str]:
    encoded = {
        "lo": wire.binary64_hex(value.lo),
        "hi": wire.binary64_hex(value.hi),
    }
    wire.validate_interval(encoded)
    return encoded


def _compile_expression(expression: dict[str, Any]) -> list[Instruction]:
    """Compile the bounded tree to postfix instructions once per batch."""

    program: list[Instruction] = []

    def visit(node: dict[str, Any]) -> None:
        op = node["op"]
        if op == "const":
            program.append(Instruction(op, _decode_interval(node["value"])))
        elif op == "var":
            program.append(Instruction(op, node["index"]))
        elif op in {"neg", "abs"}:
            visit(node["arg"])
            program.append(Instruction(op))
        elif op == "pow_nat":
            visit(node["arg"])
            program.append(Instruction(op, node["exponent"]))
        else:
            visit(node["left"])
            visit(node["right"])
            program.append(Instruction(op))

    visit(expression)
    return program


_UNARY_OPERATIONS = {
    "neg": exact.interval_neg,
    "abs": exact.interval_abs,
}

_BINARY_OPERATIONS = {
    "add": exact.interval_add,
    "sub": exact.interval_sub,
    "mul": exact.interval_mul,
    "div": exact.interval_div,
    "min": exact.interval_min,
    "max": exact.interval_max,
}


def _run_program(
    program: Sequence[Instruction], row: Sequence[exact.Binary64Interval]
) -> exact.Binary64Interval:
    stack: list[exact.Binary64Interval] = []
    try:
        for instruction in program:
            op = instruction.op
            if op == "const":
                stack.append(instruction.argument)
            elif op == "var":
                stack.append(row[instruction.argument])
            elif op in _UNARY_OPERATIONS:
                if not stack:
                    raise EvaluationError("invalid unary evaluation stack")
                stack.append(_UNARY_OPERATIONS[op](stack.pop()))
            elif op == "pow_nat":
                if not stack:
                    raise EvaluationError("invalid power evaluation stack")
                stack.append(exact.interval_pow_nat(stack.pop(), instruction.argument))
            elif op in _BINARY_OPERATIONS:
                if len(stack) < 2:
                    raise EvaluationError("invalid binary evaluation stack")
                right = stack.pop()
                left = stack.pop()
                stack.append(_BINARY_OPERATIONS[op](left, right))
            else:  # The format validator makes this unreachable.
                raise EvaluationError(f"unsupported operation {op!r}")
    except EvaluationError:
        raise
    except (ArithmeticError, ValueError, IndexError) as exc:
        raise EvaluationError(str(exc) or type(exc).__name__) from exc
    if len(stack) != 1:
        raise EvaluationError("expression did not produce exactly one result")
    return stack[0]


def evaluate_batch(batch: dict[str, Any]) -> dict[str, Any]:
    """Recompute every row with exact outward-rounded binary64 arithmetic."""

    validated = wire.validate_batch(batch)
    program = _compile_expression(validated["expression"])
    output_rows: list[dict[str, str]] = []
    for row_index, encoded_row in enumerate(validated["rows"]):
        try:
            row = [_decode_interval(value) for value in encoded_row]
            output_rows.append(_encode_interval(_run_program(program, row)))
        except (EvaluationError, ValueError, ArithmeticError) as exc:
            raise EvaluationError(f"row {row_index}: {exc}") from exc
    result: dict[str, Any] = {
        "schema_version": wire.SCHEMA_VERSION,
        "kind": wire.RESULT_KIND,
        "algorithm": wire.ALGORITHM_ID,
        "batch_sha256": wire.canonical_sha256(validated),
        "rows": output_rows,
    }
    wire.validate_result(result, batch=validated)
    return result


def issue_certificate(batch: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a batch and return a self-contained reference certificate."""

    validated = wire.validate_batch(batch)
    return wire.make_certificate(validated, evaluate_batch(validated))


def check_result(batch: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Validate bindings and require bit-for-bit equality with recomputation."""

    try:
        validated_batch = wire.validate_batch(batch)
        validated_result = wire.validate_result(result, batch=validated_batch)
        expected = evaluate_batch(validated_batch)
    except (wire.FormatError, EvaluationError, ValueError, ArithmeticError) as exc:
        raise CertificateError(str(exc)) from exc
    if validated_result != expected:
        raise CertificateError("reference result differs from exact recomputation")
    return {
        "status": "accepted",
        "algorithm": wire.ALGORITHM_ID,
        "batch_sha256": wire.canonical_sha256(validated_batch),
        "result_sha256": wire.canonical_sha256(validated_result),
        "row_count": len(validated_result["rows"]),
    }


def check_certificate(certificate: dict[str, Any]) -> dict[str, Any]:
    """Check structure, both hashes, division preconditions, and every result."""

    try:
        validated = wire.validate_certificate(certificate)
    except wire.FormatError as exc:
        raise CertificateError(str(exc)) from exc
    return check_result(validated["batch"], validated["result"])
