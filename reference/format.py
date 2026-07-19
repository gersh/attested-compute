#!/usr/bin/env python3
"""Strict, canonical serialization for the executable interval reference.

The wire format deliberately uses a small JSON subset: objects, arrays,
strings, and exact integers.  Booleans, null, floating-point tokens,
duplicate keys, insignificant whitespace, and trailing newlines are rejected.
Binary64 values are always their raw 64-bit words written as sixteen lowercase
hexadecimal digits.  NaN encodings are never valid interval endpoints.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = 1
BATCH_KIND = "sparkinterval_reference_batch"
RESULT_KIND = "sparkinterval_reference_result"
CERTIFICATE_KIND = "sparkinterval_reference_certificate"
ALGORITHM_ID = "sparkinterval.binary64_interval_expr.v1"

HEX64_RE = re.compile(r"^[0-9a-f]{16}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SIGN_MASK = 1 << 63
EXPONENT_MASK = 0x7FF0000000000000
FRACTION_MASK = 0x000FFFFFFFFFFFFF
MAX_EXPRESSION_DEPTH = 256
MAX_EXPRESSION_NODES = 100_000
MAX_VARIABLE_COUNT = 65_536
MAX_BATCH_ROWS = 1_000_000
MAX_CANONICAL_JSON_BYTES = 512 * 1024 * 1024
# The exact implementation raises rational endpoints to this power.  A wire
# limit keeps an untrusted certificate from requesting billion-bit work in a
# single expression node; application expressions need only small powers.
MAX_POW_EXPONENT = 64


class FormatError(ValueError):
    """The serialized reference request or certificate is invalid."""


def _fail(message: str) -> None:
    raise FormatError(message)


def _reject_float(token: str) -> None:
    _fail(f"JSON floating-point values are forbidden: {token}")


def _reject_constant(token: str) -> None:
    _fail(f"non-finite JSON value is forbidden: {token}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def validate_json_value(value: Any, path: str = "$") -> None:
    """Validate the integer/string-only canonical JSON value domain."""

    # bool is an int subclass, so it must be rejected first.
    if isinstance(value, bool) or value is None:
        _fail(f"boolean and null JSON values are forbidden at {path}")
    if isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        _fail(f"JSON floating-point value is forbidden at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(f"JSON object key is not a string at {path}")
            validate_json_value(item, f"{path}.{key}")
        return
    _fail(f"value at {path} is outside the canonical JSON subset")


def canonical_json_bytes(value: Any) -> bytes:
    """Encode canonical UTF-8 JSON, with no whitespace or final newline."""

    validate_json_value(value)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        encoded = text.encode("utf-8", errors="strict")
        if len(encoded) > MAX_CANONICAL_JSON_BYTES:
            _fail(
                f"canonical JSON exceeds {MAX_CANONICAL_JSON_BYTES} bytes; "
                "use a future streaming batch format"
            )
        return encoded
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise FormatError(f"cannot encode canonical JSON: {exc}") from exc


def parse_json_bytes(data: bytes, *, source: str = "JSON input") -> Any:
    """Parse strict UTF-8 JSON and require its unique canonical encoding."""

    if len(data) > MAX_CANONICAL_JSON_BYTES:
        _fail(
            f"{source} exceeds the {MAX_CANONICAL_JSON_BYTES}-byte "
            "non-streaming format limit"
        )

    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FormatError(f"{source} is not valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except FormatError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise FormatError(f"cannot parse {source}: {exc}") from exc
    try:
        validate_json_value(value)
        if data != canonical_json_bytes(value):
            _fail(f"{source} is not canonical JSON")
    except RecursionError as exc:
        raise FormatError(f"{source} exceeds the supported nesting depth") from exc
    return value


def load_canonical_json(path: str | os.PathLike[str]) -> Any:
    json_path = Path(path)
    try:
        data = json_path.read_bytes()
    except OSError as exc:
        raise FormatError(f"cannot read {json_path}: {exc}") from exc
    return parse_json_bytes(data, source=str(json_path))


def write_canonical_json(path: str | os.PathLike[str], value: Any) -> None:
    """Write a complete canonical value.  Existing files are replaced."""

    json_path = Path(path)
    try:
        json_path.write_bytes(canonical_json_bytes(value))
    except OSError as exc:
        raise FormatError(f"cannot write {json_path}: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _exact_object(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{what} must be an object")
    keys = set(value)
    if keys != fields:
        _fail(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - keys)}, unexpected={sorted(keys - fields)})"
        )
    return value


def _array(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{what} must be an array")
    return value


def _integer(
    value: Any, what: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{what} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        upper = "" if maximum is None else f" and at most {maximum}"
        _fail(f"{what} must be at least {minimum}{upper}")
    return value


def _fixed_string(value: Any, expected: str, what: str) -> None:
    if value != expected or not isinstance(value, str):
        _fail(f"{what} must be {expected!r}")


def _sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(f"{what} must be 64 lowercase hexadecimal digits")
    return value


def parse_binary64_hex(value: Any, what: str = "binary64 endpoint") -> int:
    if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
        _fail(f"{what} must be exactly 16 lowercase hexadecimal digits")
    bits = int(value, 16)
    if (bits & EXPONENT_MASK) == EXPONENT_MASK and (bits & FRACTION_MASK) != 0:
        _fail(f"{what} must not encode NaN")
    return bits


def binary64_hex(bits: int) -> str:
    if isinstance(bits, bool) or not isinstance(bits, int) or not 0 <= bits < 1 << 64:
        _fail("binary64 word must be an integer in [0, 2^64)")
    if (bits & EXPONENT_MASK) == EXPONENT_MASK and (bits & FRACTION_MASK) != 0:
        _fail("binary64 word must not encode NaN")
    return f"{bits:016x}"


def _binary64_numeric_le(left: int, right: int) -> bool:
    """IEEE numeric <= for non-NaN encodings, identifying the signed zeros."""

    left_zero = (left & ~SIGN_MASK) == 0
    right_zero = (right & ~SIGN_MASK) == 0
    if left_zero and right_zero:
        return True
    left_negative = (left & SIGN_MASK) != 0
    right_negative = (right & SIGN_MASK) != 0
    if left_negative != right_negative:
        return left_negative
    if left_negative:
        return left >= right
    return left <= right


def validate_interval(
    value: Any, what: str = "interval", *, require_finite: bool = False
) -> dict[str, str]:
    interval = _exact_object(value, {"lo", "hi"}, what)
    lo = parse_binary64_hex(interval["lo"], f"{what}.lo")
    hi = parse_binary64_hex(interval["hi"], f"{what}.hi")
    if require_finite and (
        (lo & EXPONENT_MASK) == EXPONENT_MASK
        or (hi & EXPONENT_MASK) == EXPONENT_MASK
    ):
        _fail(f"{what} must have finite endpoints")
    if not _binary64_numeric_le(lo, hi):
        _fail(f"{what} has decreasing endpoints")
    return interval  # type: ignore[return-value]


def validate_expression(
    value: Any,
    *,
    variable_count: int,
    _depth: int = 0,
    _counter: list[int] | None = None,
    _path: str = "$.expression",
) -> dict[str, Any]:
    if _counter is None:
        _counter = [0]
    if _depth > MAX_EXPRESSION_DEPTH:
        _fail(f"expression exceeds maximum depth {MAX_EXPRESSION_DEPTH}")
    _counter[0] += 1
    if _counter[0] > MAX_EXPRESSION_NODES:
        _fail(f"expression exceeds maximum node count {MAX_EXPRESSION_NODES}")
    if not isinstance(value, dict):
        _fail(f"{_path} must be an object")
    op = value.get("op")
    if not isinstance(op, str):
        _fail(f"{_path}.op must be a string")

    if op == "const":
        node = _exact_object(value, {"op", "value"}, _path)
        validate_interval(node["value"], f"{_path}.value", require_finite=True)
        return node
    if op == "var":
        node = _exact_object(value, {"op", "index"}, _path)
        index = _integer(node["index"], f"{_path}.index")
        if index >= variable_count:
            _fail(f"{_path}.index is outside variable_count {variable_count}")
        return node
    if op in {"neg", "abs"}:
        node = _exact_object(value, {"op", "arg"}, _path)
        validate_expression(
            node["arg"], variable_count=variable_count, _depth=_depth + 1,
            _counter=_counter, _path=f"{_path}.arg"
        )
        return node
    if op == "pow_nat":
        node = _exact_object(value, {"op", "arg", "exponent"}, _path)
        _integer(
            node["exponent"], f"{_path}.exponent", maximum=MAX_POW_EXPONENT
        )
        validate_expression(
            node["arg"], variable_count=variable_count, _depth=_depth + 1,
            _counter=_counter, _path=f"{_path}.arg"
        )
        return node
    if op in {"add", "sub", "mul", "div", "min", "max"}:
        node = _exact_object(value, {"op", "left", "right"}, _path)
        validate_expression(
            node["left"], variable_count=variable_count, _depth=_depth + 1,
            _counter=_counter, _path=f"{_path}.left"
        )
        validate_expression(
            node["right"], variable_count=variable_count, _depth=_depth + 1,
            _counter=_counter, _path=f"{_path}.right"
        )
        return node
    _fail(f"{_path}.op is unsupported: {op!r}")


def validate_batch(value: Any) -> dict[str, Any]:
    batch = _exact_object(
        value,
        {"schema_version", "kind", "algorithm", "variable_count", "expression", "rows"},
        "reference batch",
    )
    _integer(batch["schema_version"], "reference batch.schema_version", minimum=1, maximum=1)
    _fixed_string(batch["kind"], BATCH_KIND, "reference batch.kind")
    _fixed_string(batch["algorithm"], ALGORITHM_ID, "reference batch.algorithm")
    variable_count = _integer(
        batch["variable_count"], "reference batch.variable_count",
        maximum=MAX_VARIABLE_COUNT,
    )
    validate_expression(batch["expression"], variable_count=variable_count)
    rows = _array(batch["rows"], "reference batch.rows")
    if not rows:
        _fail("reference batch.rows must not be empty")
    if len(rows) > MAX_BATCH_ROWS:
        _fail(f"reference batch.rows must contain at most {MAX_BATCH_ROWS} rows")
    for row_index, raw_row in enumerate(rows):
        row = _array(raw_row, f"reference batch.rows[{row_index}]")
        if len(row) != variable_count:
            _fail(
                f"reference batch.rows[{row_index}] has {len(row)} variables; "
                f"expected {variable_count}"
            )
        for column, interval in enumerate(row):
            validate_interval(
                interval,
                f"reference batch.rows[{row_index}][{column}]",
                require_finite=True,
            )
    return batch


def validate_result(
    value: Any, *, batch: dict[str, Any] | None = None
) -> dict[str, Any]:
    result = _exact_object(
        value,
        {"schema_version", "kind", "algorithm", "batch_sha256", "rows"},
        "reference result",
    )
    _integer(result["schema_version"], "reference result.schema_version", minimum=1, maximum=1)
    _fixed_string(result["kind"], RESULT_KIND, "reference result.kind")
    _fixed_string(result["algorithm"], ALGORITHM_ID, "reference result.algorithm")
    _sha256(result["batch_sha256"], "reference result.batch_sha256")
    rows = _array(result["rows"], "reference result.rows")
    if len(rows) > MAX_BATCH_ROWS:
        _fail(f"reference result.rows must contain at most {MAX_BATCH_ROWS} rows")
    for index, interval in enumerate(rows):
        validate_interval(interval, f"reference result.rows[{index}]")
    if batch is not None:
        validate_batch(batch)
        expected_digest = canonical_sha256(batch)
        if result["batch_sha256"] != expected_digest:
            _fail("reference result does not bind the supplied batch")
        if len(rows) != len(batch["rows"]):
            _fail("reference result row count does not match the supplied batch")
    return result


def make_certificate(
    batch: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    validate_batch(batch)
    validate_result(result, batch=batch)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CERTIFICATE_KIND,
        "batch": batch,
        "batch_sha256": canonical_sha256(batch),
        "result": result,
        "result_sha256": canonical_sha256(result),
    }


def validate_certificate(value: Any) -> dict[str, Any]:
    certificate = _exact_object(
        value,
        {"schema_version", "kind", "batch", "batch_sha256", "result", "result_sha256"},
        "reference certificate",
    )
    _integer(certificate["schema_version"], "reference certificate.schema_version", minimum=1, maximum=1)
    _fixed_string(certificate["kind"], CERTIFICATE_KIND, "reference certificate.kind")
    batch = validate_batch(certificate["batch"])
    result = validate_result(certificate["result"], batch=batch)
    _sha256(certificate["batch_sha256"], "reference certificate.batch_sha256")
    _sha256(certificate["result_sha256"], "reference certificate.result_sha256")
    if certificate["batch_sha256"] != canonical_sha256(batch):
        _fail("reference certificate batch SHA-256 mismatch")
    if certificate["result_sha256"] != canonical_sha256(result):
        _fail("reference certificate result SHA-256 mismatch")
    return certificate


def parse_batch_bytes(data: bytes, *, source: str = "reference batch") -> dict[str, Any]:
    return validate_batch(
        parse_json_bytes(data, source=source)
    )


def parse_result_bytes(
    data: bytes,
    *,
    batch: dict[str, Any] | None = None,
    source: str = "reference result",
) -> dict[str, Any]:
    return validate_result(
        parse_json_bytes(data, source=source), batch=batch
    )


def parse_certificate_bytes(
    data: bytes, *, source: str = "reference certificate"
) -> dict[str, Any]:
    return validate_certificate(
        parse_json_bytes(data, source=source)
    )


def load_batch(path: str | os.PathLike[str]) -> dict[str, Any]:
    batch_path = Path(path)
    try:
        data = batch_path.read_bytes()
    except OSError as exc:
        raise FormatError(f"cannot read {batch_path}: {exc}") from exc
    return parse_batch_bytes(data, source=str(batch_path))


def load_result(
    path: str | os.PathLike[str], *, batch: dict[str, Any] | None = None
) -> dict[str, Any]:
    result_path = Path(path)
    try:
        data = result_path.read_bytes()
    except OSError as exc:
        raise FormatError(f"cannot read {result_path}: {exc}") from exc
    return parse_result_bytes(data, batch=batch, source=str(result_path))


def load_certificate(path: str | os.PathLike[str]) -> dict[str, Any]:
    certificate_path = Path(path)
    try:
        data = certificate_path.read_bytes()
    except OSError as exc:
        raise FormatError(f"cannot read {certificate_path}: {exc}") from exc
    return parse_certificate_bytes(data, source=str(certificate_path))
