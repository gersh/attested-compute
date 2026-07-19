#!/usr/bin/env python3
"""Package an accepted Phase 5 generated-cubin run as local DGX evidence.

The resulting object uses the existing ``sparkinterval_run_bundle`` format and
the canonical ``local_unattested`` trust profile.  This tool verifies the
retained Phase 5 report and its critical byte/hash relationships before it
copies anything.  It is an integrity and reproducibility packager, not an
attestation provider.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import sys
import tempfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from reference import format as wire  # noqa: E402
import create_run_bundle as bundle_format  # noqa: E402
import verify_run_bundle as bundle_verify  # noqa: E402


REPORT_LIMIT = 16 * 1024 * 1024
AUDIT_LIMIT = 16 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(r"^[0-9a-f]{32}$")
GENERATED_HEADER = struct.Struct("<8sIIQ")
PHASE4_HEADER = struct.Struct("<8sIIIIQ")
INTERVAL = struct.Struct("<QQ")
OUTPUT = struct.Struct("<QQB7s")
INPUT_MAGIC = b"SIG64I01"
OUTPUT_MAGIC = b"SIG64O01"
PHASE4_OUTPUT_MAGIC = b"SIE64O01"
NEGATIVE_INFINITY = 0xFFF0000000000000
POSITIVE_INFINITY = 0x7FF0000000000000
EXPONENT_MASK = 0x7FF0000000000000
FRACTION_MASK = 0x000FFFFFFFFFFFFF
SIGN_MASK = 0x8000000000000000
EXPECTED_SASS_COUNT_KEYS = {
    "DADD.RM",
    "DADD.RP",
    "DMUL.RM",
    "DMUL.RP",
    "DSETP.MIN.AND",
    "DSETP.MAX.AND",
    "FSEL",
    "SEL",
    "LDG.E.64",
    "LDG.E",
    "STG.E.64",
    "STG.E.U8",
}


BASE_FILES: dict[str, str] = {
    "batch": "batch.json",
    "rows": "rows.bin",
    "results": "results.bin",
    "ptx": "kernel.ptx",
    "cubin": "kernel.sm_121.cubin",
    "driver_report": "driver-run.json",
    "ptx_audit": "ptx-audit.json",
    "sass": "kernel.sm_121.sass.txt",
    "sass_audit": "sass-audit.json",
    "signed_zero_batch": "signed-zero-batch.json",
    "signed_zero_rows": "signed-zero-rows.bin",
    "signed_zero_results": "signed-zero-results.bin",
    "signed_zero_ptx": "signed-zero-kernel.ptx",
    "signed_zero_cubin": "signed-zero-kernel.sm_121.cubin",
    "signed_zero_driver_report": "signed-zero-driver-run.json",
    "signed_zero_ptx_audit": "signed-zero-ptx-audit.json",
    "signed_zero_sass": "signed-zero-kernel.sm_121.sass.txt",
    "signed_zero_sass_audit": "signed-zero-sass-audit.json",
}

STRONG_FILES: dict[str, str] = {
    "replayed_ptx": "kernel.replay.ptx",
    "reassembled_cubin": "kernel.reassembled.sm_121.cubin",
    "replayed_results": "results.replay.bin",
    "signed_zero_replayed_ptx": "signed-zero-kernel.replay.ptx",
    "signed_zero_reassembled_cubin": "signed-zero-kernel.reassembled.sm_121.cubin",
    "signed_zero_replayed_results": "signed-zero-results.replay.bin",
    "phase4_input": "phase4-expression-input.bin",
    "phase4_results": "phase4-expression-results.bin",
    "ptx_audit": "ptx-audit.closure.json",
    "sass": "kernel.closure.sm_121.sass.txt",
    "sass_audit": "sass-audit.closure.json",
    "signed_zero_ptx_audit": "signed-zero-ptx-audit.closure.json",
    "signed_zero_sass": "signed-zero-kernel.closure.sm_121.sass.txt",
    "signed_zero_sass_audit": "signed-zero-sass-audit.closure.json",
}

SOURCE_HASHES: dict[str, Path] = {
    "conformance_harness": ROOT / "tools/run_generated_ptx_conformance.py",
    "acceptance_closure_tool": ROOT / "tools/close_generated_ptx_acceptance.py",
    "ptx_audit_tool": ROOT / "tools/inspect_generated_ptx.py",
    "sass_audit_tool": ROOT / "tools/inspect_generated_sass.py",
    "reference_evaluator": ROOT / "reference/evaluator.py",
    "reference_binary64": ROOT / "reference/exact_binary64.py",
    "reference_format": ROOT / "reference/format.py",
}


@dataclass(frozen=True)
class ValidatedRun:
    work: Path
    report: dict[str, Any]
    batch: dict[str, Any]
    files: dict[str, Path]
    external_files: dict[str, Path]
    digests: dict[Path, str]
    row_count: int
    variable_count: int
    status_counts: dict[str, int]
    hardware: dict[str, Any]


def _error(message: str) -> bundle_format.BundleError:
    return bundle_format.BundleError(message)


def _sha256(path: Path) -> str:
    return bundle_format.hash_file(path)[0]


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise _error(f"non-finite JSON token is forbidden: {token}")


def _check_finite_json(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise _error(f"non-finite JSON number at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_finite_json(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_finite_json(item, f"{path}.{key}")


def _load_json(path: Path, *, limit: int, what: str) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _error(f"cannot read {what} {path}: {exc}") from exc
    if len(raw) > limit:
        raise _error(f"{what} exceeds {limit} bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except bundle_format.BundleError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _error(f"cannot parse {what} {path}: {exc}") from exc
    _check_finite_json(value)
    return value


def _dict(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(f"{what} must be a JSON object")
    return value


def _integer(value: Any, what: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _error(f"{what} must be an integer at least {minimum}")
    return value


def _digest(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise _error(f"{what} must be a lowercase SHA-256")
    return value


def _work_file(work: Path, name: str) -> Path:
    candidate = work / name
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise _error(f"required retained artifact is missing: {candidate}") from exc
    try:
        resolved.relative_to(work)
    except ValueError as exc:
        raise _error(f"retained artifact escapes the work directory: {candidate}") from exc
    if not resolved.is_file():
        raise _error(f"retained artifact is not a regular file: {candidate}")
    return resolved


def _external_executable(path: Path, what: str) -> Path:
    try:
        result = path.resolve(strict=True)
    except OSError as exc:
        raise _error(f"cannot resolve {what}: {path}") from exc
    if not result.is_file() or not os.access(result, os.X_OK):
        raise _error(f"{what} is not an executable regular file: {result}")
    return result


def _numeric_le(left: int, right: int) -> bool:
    if (left & ~SIGN_MASK) == 0 and (right & ~SIGN_MASK) == 0:
        return True
    left_negative = (left & SIGN_MASK) != 0
    right_negative = (right & SIGN_MASK) != 0
    if left_negative != right_negative:
        return left_negative
    return left >= right if left_negative else left <= right


def _valid_endpoint(bits: int) -> bool:
    return not (
        (bits & EXPONENT_MASK) == EXPONENT_MASK
        and (bits & FRACTION_MASK) != 0
    )


def _validate_encoded_rows(batch: dict[str, Any], path: Path, what: str) -> None:
    raw = path.read_bytes()
    row_count = len(batch["rows"])
    variable_count = batch["variable_count"]
    expected_size = GENERATED_HEADER.size + row_count * variable_count * INTERVAL.size
    if len(raw) != expected_size:
        raise _error(f"{what} length does not match the canonical batch")
    header = GENERATED_HEADER.unpack_from(raw)
    if header != (INPUT_MAGIC, 1, variable_count, row_count):
        raise _error(f"{what} header does not match the canonical batch")
    offset = GENERATED_HEADER.size
    for row_index, row in enumerate(batch["rows"]):
        for column, interval in enumerate(row):
            lo, hi = INTERVAL.unpack_from(raw, offset)
            offset += INTERVAL.size
            expected = (int(interval["lo"], 16), int(interval["hi"], 16))
            if (lo, hi) != expected:
                raise _error(
                    f"{what} differs from batch row {row_index}, column {column}"
                )


def _expected_signed_zero_batch() -> dict[str, Any]:
    """Construct the exact multiplication corner suite without trusting Phase 5."""

    positive_zero = {"lo": "0000000000000000", "hi": "0000000000000000"}
    negative_zero = {"lo": "8000000000000000", "hi": "8000000000000000"}
    both_zeros = {"lo": "8000000000000000", "hi": "0000000000000000"}
    probes = (positive_zero, negative_zero, both_zeros)
    return wire.validate_batch(
        {
            "schema_version": wire.SCHEMA_VERSION,
            "kind": wire.BATCH_KIND,
            "algorithm": wire.ALGORITHM_ID,
            "variable_count": 2,
            "expression": {
                "op": "mul",
                "left": {"op": "var", "index": 0},
                "right": {"op": "var", "index": 1},
            },
            "rows": [
                [dict(left), dict(right)] for left in probes for right in probes
            ],
        }
    )


def _validate_results(
    path: Path, *, variable_count: int, row_count: int, what: str
) -> dict[str, int]:
    raw = path.read_bytes()
    expected_size = GENERATED_HEADER.size + row_count * OUTPUT.size
    if len(raw) != expected_size:
        raise _error(f"{what} length does not match its row count")
    header = GENERATED_HEADER.unpack_from(raw)
    if header != (OUTPUT_MAGIC, 1, variable_count, row_count):
        raise _error(f"{what} header is invalid")
    counts: dict[str, int] = {}
    for row in range(row_count):
        lo, hi, status, reserved = OUTPUT.unpack_from(
            raw, GENERATED_HEADER.size + row * OUTPUT.size
        )
        if reserved != b"\0" * 7:
            raise _error(f"{what} row {row} has nonzero reserved bytes")
        if status not in (0, 2):
            raise _error(f"{what} row {row} has unsupported status {status}")
        if not _valid_endpoint(lo) or not _valid_endpoint(hi) or not _numeric_le(lo, hi):
            raise _error(f"{what} row {row} is not a valid non-NaN interval")
        if status == 2 and (lo, hi) != (NEGATIVE_INFINITY, POSITIVE_INFINITY):
            raise _error(f"{what} row {row} status 2 is not the whole interval")
        key = str(status)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _validate_status_counts(
    value: Any, *, expected: dict[str, int], what: str
) -> None:
    counts = _dict(value, what)
    if set(counts) != set(expected):
        raise _error(f"{what} has unexpected or missing status values")
    for status, expected_count in expected.items():
        count = _integer(counts[status], f"{what}.{status}")
        if count != expected_count:
            raise _error(f"{what}.{status} differs from the retained output")


def _phase4_result_payload(
    path: Path,
    *,
    instruction_count: int,
    variable_count: int,
    maximum_stack_depth: int,
    row_count: int,
) -> bytes:
    raw = path.read_bytes()
    if len(raw) < PHASE4_HEADER.size:
        raise _error("retained Phase 4 result is truncated")
    expected_header = (
        PHASE4_OUTPUT_MAGIC,
        1,
        instruction_count,
        variable_count,
        maximum_stack_depth,
        row_count,
    )
    if PHASE4_HEADER.unpack_from(raw) != expected_header:
        raise _error("retained Phase 4 result header does not match the closure")
    payload = raw[PHASE4_HEADER.size :]
    if len(payload) != row_count * OUTPUT.size:
        raise _error("retained Phase 4 result payload length is invalid")
    return payload


def _validate_hardware(value: Any, *, row_count: int, what: str) -> dict[str, Any]:
    hardware = _dict(value, what)
    expected_keys = {
        "schema_version",
        "kind",
        "module_kind",
        "device_count",
        "device_index",
        "device_name",
        "device_uuid",
        "compute_capability",
        "cuda_driver_version",
        "allow_other_device",
        "row_count",
    }
    if set(hardware) != expected_keys:
        raise _error(f"{what} has unexpected or missing fields")
    if hardware["schema_version"] != 1 or hardware["kind"] != "sparkinterval_generated_driver_run":
        raise _error(f"{what} has an unsupported schema or kind")
    if hardware["module_kind"] != "offline_cubin":
        raise _error(f"{what} did not execute the offline cubin")
    if hardware["allow_other_device"] is not False:
        raise _error(f"{what} used the development device override")
    if (
        hardware["device_count"] != 1
        or hardware["device_index"] != 0
        or hardware["device_name"] != "NVIDIA GB10"
        or hardware["compute_capability"] != "12.1"
        or hardware["row_count"] != row_count
    ):
        raise _error(f"{what} is not the exact one-device GB10/sm_121 profile")
    if not isinstance(hardware["device_uuid"], str) or UUID_RE.fullmatch(hardware["device_uuid"]) is None:
        raise _error(f"{what}.device_uuid is not 16 bytes of lowercase hex")
    _integer(hardware["cuda_driver_version"], f"{what}.cuda_driver_version", minimum=1)
    return hardware


def _same_device(left: dict[str, Any], right: dict[str, Any]) -> bool:
    ignored = {"row_count"}
    return {k: v for k, v in left.items() if k not in ignored} == {
        k: v for k, v in right.items() if k not in ignored
    }


def _validate_ptx_audit(audit: Any, *, ptx: Path, what: str) -> None:
    value = _dict(audit, what)
    if (
        value.get("passed") is not True
        or value.get("schema_version") != 1
        or value.get("target") != "sm_121"
        or value.get("input_sha256") != _sha256(ptx)
    ):
        raise _error(f"{what} does not accept the exact sm_121 PTX")
    lowering = _dict(value.get("lowering_model"), f"{what}.lowering_model")
    if (
        lowering.get("schema_version") != 1
        or lowering.get("analysis_kind")
        != "generated_ptx_demand_and_value_numbering_v1"
        or lowering.get("passed") is not True
        or lowering.get("errors") != []
    ):
        raise _error(f"{what} does not contain a successful lowering model")
    counts = _dict(
        lowering.get("expected_sass_counts"),
        f"{what}.lowering_model.expected_sass_counts",
    )
    if set(counts) != EXPECTED_SASS_COUNT_KEYS:
        raise _error(f"{what} lowering model has the wrong SASS count vocabulary")
    for mnemonic, count in counts.items():
        _integer(
            count,
            f"{what}.lowering_model.expected_sass_counts.{mnemonic}",
        )


def _validate_sass_audit(
    audit: Any, *, ptx: Path, cubin: Path, sass: Path, ptx_audit: Path, what: str
) -> None:
    value = _dict(audit, what)
    ptx_audit_value = _dict(
        _load_json(ptx_audit, limit=AUDIT_LIMIT, what=f"{what} PTX audit"),
        f"{what} PTX audit",
    )
    lowering = _dict(
        ptx_audit_value.get("lowering_model"), f"{what} PTX lowering model"
    )
    lowering_sha256 = hashlib.sha256(
        bundle_format.canonical_json_bytes(lowering)
    ).hexdigest()
    if (
        value.get("passed") is not True
        or value.get("schema_version") != 1
        or value.get("targets") != ["sm_121"]
        or value.get("ptx_sha256") != _sha256(ptx)
        or value.get("cubin_sha256") != _sha256(cubin)
        or value.get("sass_sha256") != _sha256(sass)
        or value.get("ptx_audit_sha256") != _sha256(ptx_audit)
        or value.get("lowering_model_valid") is not True
        or value.get("lowering_model_sha256") != lowering_sha256
    ):
        raise _error(f"{what} does not bind the exact PTX/cubin/SASS chain")


def _require_recorded_hashes(
    recorded: Any, paths: dict[str, Path], *, what: str
) -> dict[str, str]:
    values = _dict(recorded, what)
    result: dict[str, str] = {}
    for name, path in paths.items():
        expected = _digest(values.get(name), f"{what}.{name}")
        actual = _sha256(path)
        if expected != actual:
            raise _error(f"{what}.{name} does not match {path.name}")
        result[name] = actual
    return result


def validate_retained_run(
    *, work_dir: Path, generator: Path, driver: Path, phase4: Path
) -> ValidatedRun:
    try:
        work = work_dir.resolve(strict=True)
    except OSError as exc:
        raise _error(f"cannot resolve retained work directory: {work_dir}") from exc
    if not work.is_dir():
        raise _error(f"retained work path is not a directory: {work}")
    generator = _external_executable(generator, "generator executable")
    driver = _external_executable(driver, "generated-cubin driver")
    phase4 = _external_executable(phase4, "Phase 4 expression runner")

    files = {key: _work_file(work, name) for key, name in BASE_FILES.items()}
    files.update(
        {f"strong_{key}": _work_file(work, name) for key, name in STRONG_FILES.items()}
    )
    report_path = _work_file(work, "report.json")
    report = _dict(
        _load_json(report_path, limit=REPORT_LIMIT, what="Phase 5 acceptance report"),
        "Phase 5 acceptance report",
    )
    if (
        report.get("schema_version") != 1
        or report.get("kind") != "sparkinterval_generated_ptx_conformance"
        or report.get("accepted") is not True
        or report.get("mismatches") != []
        or report.get("target") != "sm_121"
    ):
        raise _error("Phase 5 base acceptance did not pass exactly")
    if _integer(
        report.get("mismatch_count_capped"), "report.mismatch_count_capped"
    ) != 0:
        raise _error("Phase 5 base acceptance has recorded mismatches")
    strong = _dict(report.get("strong_acceptance"), "strong_acceptance")
    if strong.get("passed") is not True:
        raise _error("strong_acceptance.passed must be true")

    try:
        batch = wire.load_batch(files["batch"])
        zero_batch = wire.load_batch(files["signed_zero_batch"])
    except wire.FormatError as exc:
        raise _error(str(exc)) from exc
    row_count = len(batch["rows"])
    variable_count = batch["variable_count"]
    if (
        _integer(report.get("row_count"), "report.row_count") != row_count
        or _integer(strong.get("row_count"), "strong_acceptance.row_count")
        != row_count
    ):
        raise _error("acceptance report row count differs from the canonical batch")
    if zero_batch != _expected_signed_zero_batch():
        raise _error("signed-zero batch is not the exact 3x3 multiplication probe")
    _validate_encoded_rows(batch, files["rows"], "encoded main rows")
    _validate_encoded_rows(zero_batch, files["signed_zero_rows"], "encoded signed-zero rows")
    status_counts = _validate_results(
        files["results"], variable_count=variable_count, row_count=row_count,
        what="main results",
    )
    zero_status_counts = _validate_results(
        files["signed_zero_results"], variable_count=zero_batch["variable_count"],
        row_count=9, what="signed-zero results",
    )
    _validate_status_counts(
        report.get("status_counts"),
        expected=status_counts,
        what="report.status_counts",
    )
    if zero_status_counts != {"0": 9}:
        raise _error("signed-zero validation results are not all successful")
    zero_probe = _dict(report.get("signed_zero_mul_probe"), "signed_zero_mul_probe")
    if zero_probe.get("covers_pairwise") != ["+0", "-0", "[-0,+0]"]:
        raise _error("signed-zero validation summary is not accepted")
    if (
        _integer(zero_probe.get("row_count"), "signed_zero_mul_probe.row_count")
        != 9
        or _integer(
            zero_probe.get("mismatch_count"),
            "signed_zero_mul_probe.mismatch_count",
        )
        != 0
    ):
        raise _error("signed-zero validation summary is not accepted")

    for name in ("ptx", "signed_zero_ptx"):
        text = files[name].read_text(encoding="utf-8", errors="strict")
        if text.count(".target sm_121") != 1 or text.count(".version 9.0") != 1:
            raise _error(f"{files[name].name} is not exact PTX 9.0 for sm_121")
    for name in ("cubin", "signed_zero_cubin", "strong_reassembled_cubin", "strong_signed_zero_reassembled_cubin"):
        if not files[name].read_bytes().startswith(b"\x7fELF"):
            raise _error(f"{files[name].name} is not an ELF cubin")

    _validate_ptx_audit(
        _load_json(files["ptx_audit"], limit=AUDIT_LIMIT, what="PTX audit"),
        ptx=files["ptx"], what="retained PTX audit",
    )
    _validate_sass_audit(
        _load_json(files["sass_audit"], limit=AUDIT_LIMIT, what="SASS audit"),
        ptx=files["ptx"], cubin=files["cubin"], sass=files["sass"],
        ptx_audit=files["ptx_audit"], what="retained SASS audit",
    )
    _validate_ptx_audit(
        _load_json(files["signed_zero_ptx_audit"], limit=AUDIT_LIMIT, what="signed-zero PTX audit"),
        ptx=files["signed_zero_ptx"], what="retained signed-zero PTX audit",
    )
    _validate_sass_audit(
        _load_json(files["signed_zero_sass_audit"], limit=AUDIT_LIMIT, what="signed-zero SASS audit"),
        ptx=files["signed_zero_ptx"], cubin=files["signed_zero_cubin"],
        sass=files["signed_zero_sass"], ptx_audit=files["signed_zero_ptx_audit"],
        what="retained signed-zero SASS audit",
    )
    _validate_ptx_audit(
        _load_json(files["strong_ptx_audit"], limit=AUDIT_LIMIT, what="closure PTX audit"),
        ptx=files["strong_replayed_ptx"], what="closure PTX audit",
    )
    _validate_sass_audit(
        _load_json(files["strong_sass_audit"], limit=AUDIT_LIMIT, what="closure SASS audit"),
        ptx=files["strong_replayed_ptx"], cubin=files["cubin"],
        sass=files["strong_sass"], ptx_audit=files["strong_ptx_audit"],
        what="closure SASS audit",
    )
    _validate_ptx_audit(
        _load_json(files["strong_signed_zero_ptx_audit"], limit=AUDIT_LIMIT, what="closure signed-zero PTX audit"),
        ptx=files["strong_signed_zero_replayed_ptx"], what="closure signed-zero PTX audit",
    )
    _validate_sass_audit(
        _load_json(files["strong_signed_zero_sass_audit"], limit=AUDIT_LIMIT, what="closure signed-zero SASS audit"),
        ptx=files["strong_signed_zero_replayed_ptx"], cubin=files["signed_zero_cubin"],
        sass=files["strong_signed_zero_sass"],
        ptx_audit=files["strong_signed_zero_ptx_audit"],
        what="closure signed-zero SASS audit",
    )

    execution_module = _dict(report.get("execution_module"), "execution_module")
    if (
        execution_module.get("kind") != "offline_ptxas_cubin"
        or execution_module.get("development_ptx_jit_used") is not False
        or execution_module.get("sass_audit_passed_before_execution") is not True
        or execution_module.get("cubin_sha256") != _sha256(files["cubin"])
    ):
        raise _error("execution_module does not bind the audited offline cubin")
    hardware = _validate_hardware(
        report.get("hardware_execution"), row_count=row_count, what="hardware_execution"
    )
    zero_hardware = _validate_hardware(
        report.get("signed_zero_hardware_execution"), row_count=9,
        what="signed_zero_hardware_execution",
    )
    if not _same_device(hardware, zero_hardware):
        raise _error("main and signed-zero suites ran on different hardware")
    if _load_json(files["driver_report"], limit=AUDIT_LIMIT, what="driver report") != hardware:
        raise _error("driver-run.json differs from hardware_execution")
    if _load_json(files["signed_zero_driver_report"], limit=AUDIT_LIMIT, what="signed-zero driver report") != zero_hardware:
        raise _error("signed-zero-driver-run.json differs from report metadata")
    if strong.get("replay_hardware_execution") != hardware:
        raise _error("strong replay hardware differs from the original execution")
    if strong.get("signed_zero_replay_hardware_execution") != zero_hardware:
        raise _error("strong signed-zero replay hardware differs from the original execution")

    required_true = (
        "deterministic_generation",
        "deterministic_cubin_reassembly",
        "deterministic_execution_replay",
        "signed_zero_deterministic_generation",
        "signed_zero_deterministic_cubin_reassembly",
        "signed_zero_deterministic_execution_replay",
        "phase4_generated_payload_equal",
        "sass_audit_passed",
        "signed_zero_sass_audit_passed",
    )
    if any(strong.get(name) is not True for name in required_true):
        raise _error("strong acceptance is missing a required successful closure check")
    for name, expected_rows in (
        ("exact_reference_recomputed", row_count),
        ("signed_zero_exact_reference_recomputed", 9),
    ):
        exact = _dict(strong.get(name), f"strong_acceptance.{name}")
        if (
            exact.get("passed") is not True
            or exact.get("mismatches_capped") != []
        ):
            raise _error(f"strong_acceptance.{name} did not pass exactly")
        if (
            _integer(exact.get("row_count"), f"strong_acceptance.{name}.row_count")
            != expected_rows
            or _integer(
                exact.get("mismatch_count"),
                f"strong_acceptance.{name}.mismatch_count",
            )
            != 0
        ):
            raise _error(f"strong_acceptance.{name} did not pass exactly")
    _validate_status_counts(
        strong["exact_reference_recomputed"].get("status_counts"),
        expected=status_counts,
        what="strong_acceptance.exact_reference_recomputed.status_counts",
    )
    _validate_status_counts(
        strong["signed_zero_exact_reference_recomputed"].get("status_counts"),
        expected={"0": 9},
        what=(
            "strong_acceptance.signed_zero_exact_reference_recomputed."
            "status_counts"
        ),
    )

    instruction_count = _integer(
        strong.get("phase4_instruction_count"),
        "strong_acceptance.phase4_instruction_count",
        minimum=1,
    )
    maximum_stack_depth = _integer(
        strong.get("phase4_max_stack_depth"),
        "strong_acceptance.phase4_max_stack_depth",
        minimum=1,
    )
    generated_payload = files["results"].read_bytes()[GENERATED_HEADER.size :]
    phase4_payload = _phase4_result_payload(
        files["strong_phase4_results"],
        instruction_count=instruction_count,
        variable_count=variable_count,
        maximum_stack_depth=maximum_stack_depth,
        row_count=row_count,
    )
    if generated_payload != phase4_payload:
        raise _error("retained Phase 4 and generated-cubin result payloads differ")

    toolchain = _dict(report.get("toolchain"), "toolchain")
    toolchain_files: dict[str, Path] = {}
    for tool in ("ptxas", "nvdisasm"):
        metadata = _dict(toolchain.get(tool), f"toolchain.{tool}")
        path_value = metadata.get("path")
        if not isinstance(path_value, str) or not path_value:
            raise _error(f"toolchain.{tool}.path must be nonempty")
        executable = _external_executable(Path(path_value), f"recorded {tool}")
        if _digest(metadata.get("sha256"), f"toolchain.{tool}.sha256") != _sha256(executable):
            raise _error(f"recorded {tool} hash differs from the installed executable")
        if not isinstance(metadata.get("version"), str) or not metadata["version"]:
            raise _error(f"toolchain.{tool}.version must be nonempty")
        toolchain_files[f"{tool}_executable"] = executable

    external_files = {
        "generator_executable": generator,
        "generated_driver_executable": driver,
        "phase4_expression_runner": phase4,
        **toolchain_files,
        **SOURCE_HASHES,
    }
    top_paths = {key: files[key] for key in BASE_FILES}
    top_paths.update({
        "generator_executable": generator,
        "generated_driver_executable": driver,
        **{key: path for key, path in SOURCE_HASHES.items() if key != "acceptance_closure_tool"},
    })
    _require_recorded_hashes(report.get("sha256"), top_paths, what="report.sha256")
    strong_paths = {key: files[f"strong_{key}"] for key in STRONG_FILES}
    strong_paths.update({
        "cubin": files["cubin"],
        "signed_zero_cubin": files["signed_zero_cubin"],
    })
    strong_paths.update(external_files)
    _require_recorded_hashes(
        strong.get("sha256"), strong_paths, what="strong_acceptance.sha256"
    )
    strong_hashes = _dict(strong.get("sha256"), "strong_acceptance.sha256")
    if _digest(
        strong_hashes.get("generated_result_payload"),
        "strong_acceptance.sha256.generated_result_payload",
    ) != hashlib.sha256(generated_payload).hexdigest():
        raise _error("strong generated-result payload hash does not match")
    if _digest(
        strong_hashes.get("phase4_result_payload"),
        "strong_acceptance.sha256.phase4_result_payload",
    ) != hashlib.sha256(phase4_payload).hexdigest():
        raise _error("strong Phase 4 result payload hash does not match")
    if _sha256(files["strong_replayed_ptx"]) != _sha256(files["ptx"]):
        raise _error("replayed PTX is not byte-identical")
    if _sha256(files["strong_reassembled_cubin"]) != _sha256(files["cubin"]):
        raise _error("reassembled cubin is not byte-identical")
    if _sha256(files["strong_replayed_results"]) != _sha256(files["results"]):
        raise _error("replayed result is not byte-identical")
    if _sha256(files["strong_signed_zero_replayed_ptx"]) != _sha256(files["signed_zero_ptx"]):
        raise _error("signed-zero replayed PTX is not byte-identical")
    if _sha256(files["strong_signed_zero_reassembled_cubin"]) != _sha256(files["signed_zero_cubin"]):
        raise _error("signed-zero reassembled cubin is not byte-identical")
    if _sha256(files["strong_signed_zero_replayed_results"]) != _sha256(files["signed_zero_results"]):
        raise _error("signed-zero replayed result is not byte-identical")

    all_paths = {**files, **external_files, "report": report_path}
    digests = {path: _sha256(path) for path in set(all_paths.values())}
    return ValidatedRun(
        work=work,
        report=report,
        batch=batch,
        files={**files, "report": report_path},
        external_files=external_files,
        digests=digests,
        row_count=row_count,
        variable_count=variable_count,
        status_counts=status_counts,
        hardware=hardware,
    )


def _copy_checked(source: Path, destination: Path, expected_sha256: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if _sha256(destination) != expected_sha256:
        raise _error(f"artifact changed while being copied: {source}")
    return destination


def _build_copy_plan(run: ValidatedRun, root: Path) -> tuple[Path, Path, list[tuple[str, Path]]]:
    batch = _copy_checked(
        run.files["batch"], root / "input/batch.json", run.digests[run.files["batch"]]
    )
    results = _copy_checked(
        run.files["results"], root / "output/results.bin", run.digests[run.files["results"]]
    )
    roles: list[tuple[str, str, Path]] = [
        ("encoded_input_rows", "rows.bin", run.files["rows"]),
        ("gpu_ptx", "kernel.ptx", run.files["ptx"]),
        ("gpu_cubin", "kernel.sm_121.cubin", run.files["cubin"]),
        ("execution_metadata", "driver-run.json", run.files["driver_report"]),
        ("ptx_audit", "ptx-audit.json", run.files["ptx_audit"]),
        ("gpu_sass_dump", "kernel.sm_121.sass.txt", run.files["sass"]),
        ("sass_audit", "sass-audit.json", run.files["sass_audit"]),
        ("acceptance_report", "report.json", run.files["report"]),
        ("signed_zero_batch", "signed-zero-batch.json", run.files["signed_zero_batch"]),
        ("signed_zero_rows", "signed-zero-rows.bin", run.files["signed_zero_rows"]),
        ("signed_zero_results", "signed-zero-results.bin", run.files["signed_zero_results"]),
        ("signed_zero_ptx", "signed-zero-kernel.ptx", run.files["signed_zero_ptx"]),
        ("signed_zero_cubin", "signed-zero-kernel.sm_121.cubin", run.files["signed_zero_cubin"]),
        ("signed_zero_execution_metadata", "signed-zero-driver-run.json", run.files["signed_zero_driver_report"]),
        ("signed_zero_ptx_audit", "signed-zero-ptx-audit.json", run.files["signed_zero_ptx_audit"]),
        ("signed_zero_sass_dump", "signed-zero-kernel.sm_121.sass.txt", run.files["signed_zero_sass"]),
        ("signed_zero_sass_audit", "signed-zero-sass-audit.json", run.files["signed_zero_sass_audit"]),
    ]
    for key, filename in STRONG_FILES.items():
        roles.append((f"closure_{key}", filename, run.files[f"strong_{key}"]))
    roles.extend(
        [
            ("host_executable", "sparkinterval-generated-driver", run.external_files["generated_driver_executable"]),
            ("generator_executable", "sparkinterval-gen", run.external_files["generator_executable"]),
            ("phase4_expression_runner", "sparkinterval-expression-batch", run.external_files["phase4_expression_runner"]),
            ("ptxas_executable", "toolchain/ptxas", run.external_files["ptxas_executable"]),
            ("nvdisasm_executable", "toolchain/nvdisasm", run.external_files["nvdisasm_executable"]),
        ]
    )
    for key in SOURCE_HASHES:
        roles.append((key, f"source/{run.external_files[key].name}", run.external_files[key]))
    copied: list[tuple[str, Path]] = []
    for role, name, source in roles:
        destination = _copy_checked(
            source, root / "artifacts" / name, run.digests[source]
        )
        copied.append((role, destination))
    return batch, results, copied


def package_retained_run(
    *,
    work_dir: Path,
    generator: Path,
    driver: Path,
    phase4: Path,
    output_root: Path,
    start_time_utc: str,
    end_time_utc: str,
    nonce: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    run = validate_retained_run(
        work_dir=work_dir, generator=generator, driver=driver, phase4=phase4
    )
    destination = output_root.resolve(strict=False)
    if destination.exists():
        raise _error(f"output root already exists; refusing to mix evidence: {destination}")
    if destination == run.work or run.work in destination.parents:
        raise _error("output root must not overlap the retained work directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    try:
        batch_path, results_path, build_artifacts = _build_copy_plan(run, staging)
        report_sha256 = run.digests[run.files["report"]]
        status_counts = [
            {"status": int(status), "count": count}
            for status, count in sorted(run.status_counts.items(), key=lambda item: int(item[0]))
        ]
        parameters = {
            "phase": 5,
            "schema_version": 1,
            "execution_module": "offline_ptxas_cubin",
            "development_ptx_jit_used": False,
            "ptx_target": "sm_121",
            "acceptance_report_sha256": report_sha256,
            "seed": _integer(run.report.get("seed"), "report.seed"),
            "result_status_semantics": "0_interval_2_whole",
            "downstream_domain_policy_required": True,
            "strong_acceptance_required": True,
        }
        coverage = {
            "scope": "accepted_phase5_generated_polynomial_batch",
            "row_count": run.row_count,
            "variable_count": run.variable_count,
            "status_counts": status_counts,
            "signed_zero_validation_rows": 9,
        }
        toolchain = run.report["toolchain"]
        execution_environment = {
            "device_name": run.hardware["device_name"],
            "device_uuid": run.hardware["device_uuid"],
            "device_count": run.hardware["device_count"],
            "device_index": run.hardware["device_index"],
            "compute_capability": run.hardware["compute_capability"],
            "cuda_driver_version": run.hardware["cuda_driver_version"],
            "module_kind": run.hardware["module_kind"],
            "allow_other_device": False,
            "executed_cubin_sha256": run.digests[run.files["cubin"]],
            "source_ptx_sha256": run.digests[run.files["ptx"]],
            "ptxas_sha256": toolchain["ptxas"]["sha256"],
            "ptxas_version": toolchain["ptxas"]["version"],
            "nvdisasm_sha256": toolchain["nvdisasm"]["sha256"],
            "nvdisasm_version": toolchain["nvdisasm"]["version"],
            "hardware_attestation": None,
        }
        completion = {
            "status": "success",
            "exit_code": 0,
            "expected_output_count": run.row_count,
            "written_output_count": run.row_count,
            "cuda_errors": [],
            "start_time_utc": start_time_utc,
            "end_time_utc": end_time_utc,
        }
        target = bundle_format.load_profile(
            ROOT / "profiles/targets/dgx_spark_sm121.json", "target"
        )
        trust = bundle_format.load_profile(
            ROOT / "profiles/trust/local_unattested.json", "trust"
        )
        bundle = bundle_format.create_bundle(
            root=staging,
            target_profile=target,
            trust_profile=trust,
            algorithm_id="SparkInterval.GeneratedPolynomialCubin.v1",
            algorithm_definition_sha256=run.digests[run.files["cubin"]],
            input_path=batch_path,
            parameters=parameters,
            domain_coverage=coverage,
            output_path=results_path,
            nonce=nonce or secrets.token_hex(32),
            build_artifacts=build_artifacts,
            execution_environment=execution_environment,
            completion=completion,
        )
        bundle_path = staging / "run-bundle.json"
        bundle_format.write_bundle(bundle, bundle_path)
        verification = bundle_verify.verify_bundle_file(
            bundle_path, artifact_root=staging
        )
        (staging / "verification.json").write_bytes(
            bundle_format.canonical_json_bytes(verification)
        )
        os.replace(staging, destination)
        return bundle, verification, destination / "run-bundle.json"
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--generator", required=True, type=Path)
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--phase4", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--start-time-utc", required=True)
    parser.add_argument("--end-time-utc", required=True)
    parser.add_argument(
        "--nonce",
        help="64 lowercase hex characters; default is locally random and does not prove freshness",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        bundle, verification, bundle_path = package_retained_run(
            work_dir=args.work_dir,
            generator=args.generator,
            driver=args.driver,
            phase4=args.phase4,
            output_root=args.output_root,
            start_time_utc=args.start_time_utc,
            end_time_utc=args.end_time_utc,
            nonce=args.nonce,
        )
    except (OSError, bundle_format.BundleError, bundle_verify.VerificationError) as exc:
        print(f"create_dgx_generated_cubin_bundle: {exc}", file=sys.stderr)
        return 2
    summary = {
        "assurance": verification["assurance"],
        "bundle": str(bundle_path),
        "bundle_sha256": bundle["bundle_sha256"],
        "evidence_class": bundle["evidence"]["evidence_class"],
        "hardware_evidence": verification["hardware_evidence"],
        "statement_sha256": bundle["statement_sha256"],
    }
    print(bundle_format.canonical_json_bytes(summary).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
