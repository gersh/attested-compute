#!/usr/bin/env python3
"""Run and independently verify a rigorous real-integer Riemann-zeta POC.

For an integer ``s`` with ``2 <= s <= 64``, the GPU evaluates one interval
term ``1 / n^s`` per row.  The host folds those intervals in ascending ``n``
order and applies the integral-test remainder bound

    1 / ((s - 1) (N + 1)^(s - 1))
      <= sum_{n=N+1}^infinity 1/n^s
      <= 1 / ((s - 1) N^(s - 1)).

The ``verify`` command does not trust summary booleans in the report.  It
reparses the exact input and both GPU outputs, recomputes every row with the
integer/rational binary64 oracle, repeats the fold and tail calculation, and
verifies every artifact in the inner local-unattested run bundle.

This is a tutorial calculation of zeta at a real integer greater than one.  It
is not a zero-isolation or high-height Riemann-zeta verifier.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from reference import exact_binary64 as exact  # noqa: E402
import create_run_bundle as bundle_format  # noqa: E402
import inspect_expression_ptx  # noqa: E402
import run_expression_conformance as expression  # noqa: E402
import verify_run_bundle as bundle_verify  # noqa: E402


SCHEMA_VERSION = 1
REPORT_KIND = "sparkinterval_real_zeta_poc_report"
ALGORITHM_ID = "sparkinterval.real_zeta_integer_dirichlet_integral_tail.v1"
H100_ALGORITHM_ID = (
    "sparkinterval.real_zeta_integer_dirichlet_integral_tail.h100.v1"
)
MIN_S = 2
MAX_S = expression.MAX_POW_EXPONENT
MAX_TERMS = expression.MAX_ROWS
DEFAULT_TERMS = 4096
ONE_BITS = 0x3FF0000000000000
ZERO_INTERVAL = exact.Binary64Interval(exact.POSITIVE_ZERO, exact.POSITIVE_ZERO)
ALGORITHM_DEFINITION = REPOSITORY_ROOT / "specifications/REAL_ZETA_POC.md"
H100_ALGORITHM_DEFINITION = (
    REPOSITORY_ROOT / "specifications/REAL_ZETA_POC_H100.md"
)
TARGET_PROFILE = REPOSITORY_ROOT / "profiles/targets/dgx_spark_sm121.json"
H100_TARGET_PROFILE = REPOSITORY_ROOT / "profiles/targets/h100_sm90.json"
TRUST_PROFILE = REPOSITORY_ROOT / "profiles/trust/local_unattested.json"
REPORT_NAME = "zeta-report.json"
BUNDLE_NAME = "run-bundle.json"
INPUT_NAME = "zeta.input.bin"
OUTPUT_NAME = "zeta.gpu.output.bin"
REPLAY_OUTPUT_NAME = "zeta.gpu.replay.output.bin"


STAGED_SOURCES: dict[str, Path] = {
    "algorithm_definition": ALGORITHM_DEFINITION,
    "source_zeta_tool": REPOSITORY_ROOT / "tools/run_zeta_poc.py",
    "source_expression_codec": REPOSITORY_ROOT / "tools/run_expression_conformance.py",
    "source_ptx_audit": REPOSITORY_ROOT / "tools/inspect_expression_ptx.py",
    "source_sass_audit": REPOSITORY_ROOT / "tools/inspect_sass.py",
    "source_exact_binary64": REPOSITORY_ROOT / "reference/exact_binary64.py",
    "source_expression_header": REPOSITORY_ROOT / "gpu/include/expression_batch.h",
    "source_expression_kernel": REPOSITORY_ROOT / "gpu/src/expression_batch_kernel.cu",
    "source_expression_runner": REPOSITORY_ROOT / "gpu/src/expression_batch_runner.cpp",
    "source_h100_expression_kernel": (
        REPOSITORY_ROOT / "gpu/platform/h100/h100_expression_batch_kernel.cu"
    ),
    "source_h100_expression_runner": (
        REPOSITORY_ROOT / "gpu/platform/h100/h100_expression_batch_runner.cpp"
    ),
    "source_h100_runtime_policy": (
        REPOSITORY_ROOT / "gpu/platform/h100/h100_runtime_policy.h"
    ),
}


STAGED_PATHS: dict[str, str] = {
    "host_executable": "artifacts/sparkinterval-expression-batch",
    "gpu_executable": "artifacts/sparkinterval-expression-batch",
    "tool_cuobjdump": "artifacts/cuobjdump",
    "gpu_ptx": "artifacts/expression.ptx",
    "ptx_audit": "artifacts/expression-ptx-audit.json",
    "gpu_sass": "artifacts/expression.sass",
    "sass_audit": "artifacts/expression-sass-audit.json",
    "runner_report": "artifacts/runner.json",
    "replay_runner_report": "artifacts/replay-runner.json",
    "gpu_output": OUTPUT_NAME,
    "gpu_replay_output": REPLAY_OUTPUT_NAME,
    "source_target_profile": "sources/target-profile.json",
    **{
        role: f"sources/{source.name}"
        for role, source in STAGED_SOURCES.items()
    },
}


class ZetaPocError(ValueError):
    """A zeta POC artifact or calculation is invalid."""


@dataclass(frozen=True)
class DerivedResult:
    partial_sum: exact.Binary64Interval
    tail: exact.Binary64Interval
    result: exact.Binary64Interval
    tail_lower: Fraction
    tail_upper: Fraction


@dataclass(frozen=True)
class TargetConfig:
    profile_id: str
    profile_path: Path
    algorithm_id: str
    algorithm_definition: Path
    host_architecture: str
    ptx_target: str
    compute_capability: str
    device_name_exact: str | None
    device_name_contains: str | None
    default_executable: Path
    run_label: str
    limitation: str

    def accepts_device_name(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        if self.device_name_exact is not None:
            return name == self.device_name_exact
        assert self.device_name_contains is not None
        return self.device_name_contains in name


DGX_TARGET = TargetConfig(
    profile_id="dgx_spark_sm121",
    profile_path=TARGET_PROFILE,
    algorithm_id=ALGORITHM_ID,
    algorithm_definition=ALGORITHM_DEFINITION,
    host_architecture="aarch64",
    ptx_target="sm_121",
    compute_capability="12.1",
    device_name_exact="NVIDIA GB10",
    device_name_contains=None,
    default_executable=(
        REPOSITORY_ROOT / "build/dgx-spark/sparkinterval-expression-batch"
    ),
    run_label="DGX Spark",
    limitation=(
        "DGX Spark supplies no hardware-backed execution attestation; a user "
        "signature authenticates only an endorsement of these bytes."
    ),
)

H100_TARGET = TargetConfig(
    profile_id="h100_sm90",
    profile_path=H100_TARGET_PROFILE,
    algorithm_id=H100_ALGORITHM_ID,
    algorithm_definition=H100_ALGORITHM_DEFINITION,
    host_architecture="x86_64",
    ptx_target="sm_90",
    compute_capability="9.0",
    device_name_exact=None,
    device_name_contains="H100",
    default_executable=(
        REPOSITORY_ROOT / "build/h100-native/sparkinterval-h100-expression-batch"
    ),
    run_label="H100",
    limitation=(
        "This H100 record is local_unattested; it contains no verified NVIDIA "
        "confidential-computing evidence."
    ),
)

TARGETS: dict[str, TargetConfig] = {
    target.profile_id: target for target in (DGX_TARGET, H100_TARGET)
}


def _target_config(profile_id: str) -> TargetConfig:
    try:
        return TARGETS[profile_id]
    except KeyError as exc:
        _fail(f"unsupported target profile {profile_id!r}")
        raise AssertionError("unreachable") from exc


def _fail(message: str) -> None:
    raise ZetaPocError(message)


def _sha256(path: Path) -> str:
    try:
        return bundle_format.hash_file(path)[0]
    except bundle_format.BundleError as exc:
        raise ZetaPocError(str(exc)) from exc


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise ZetaPocError(f"cannot bind artifact {path}: {exc}") from exc
    digest, size = bundle_format.hash_file(resolved)
    return {"path": relative, "sha256": digest, "size_bytes": size}


def _write_canonical(path: Path, value: Any) -> None:
    try:
        data = bundle_format.canonical_json_bytes(value)
    except bundle_format.BundleError as exc:
        raise ZetaPocError(str(exc)) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ZetaPocError(f"cannot write {path}: {exc}") from exc


def _load_canonical(path: Path) -> Any:
    try:
        return bundle_format.load_canonical_json(path)
    except bundle_format.BundleError as exc:
        raise ZetaPocError(str(exc)) from exc


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    _fail(f"non-finite JSON token is forbidden: {token}")


def _check_finite_numbers(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _fail(f"non-finite number at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_finite_numbers(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_finite_numbers(item, f"{path}.{key}")


def _load_runner_report(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > 1024 * 1024:
            _fail(f"runner report is too large: {path}")
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except ZetaPocError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ZetaPocError(f"cannot parse runner report {path}: {exc}") from exc
    _check_finite_numbers(value)
    if not isinstance(value, dict):
        _fail(f"runner report must be an object: {path}")
    return value


def _exact_object(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{what} must be an object")
    if set(value) != fields:
        _fail(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - set(value))}, unexpected={sorted(set(value) - fields)})"
        )
    return value


def _integer(
    value: Any, what: str, *, minimum: int, maximum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{what} must be an integer at least {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{what} must be at most {maximum}")
    return value


def validate_parameters(s: int, terms: int) -> None:
    _integer(s, "s", minimum=MIN_S, maximum=MAX_S)
    _integer(terms, "terms", minimum=1, maximum=MAX_TERMS)
    # The row ABI permits one million rows, so every row index is exactly
    # representable as binary64.  Refuse a power that the reviewed evaluator
    # cannot keep finite; a whole-interval result is not a useful zeta term.
    program = zeta_program(s)
    last_bits = exact.round_nearest_even(terms)
    _, _, status = expression.evaluate_program(
        program, (exact.Binary64Interval(last_bits, last_bits),)
    )
    if status != expression.STATUS_VALID:
        _fail(
            f"n^s becomes nonfinite under the reviewed binary64 program at n={terms}; "
            "choose smaller parameters"
        )


def zeta_program(s: int) -> expression.Program:
    if isinstance(s, bool) or not isinstance(s, int) or not MIN_S <= s <= MAX_S:
        raise ZetaPocError(f"s must be in [{MIN_S}, {MAX_S}]")
    return expression.Program(
        "real_zeta_terms",
        1,
        (
            expression.const(ONE_BITS),
            expression.var(0),
            expression.op("pow_nat", s),
            expression.op("div"),
        ),
    )


def zeta_rows(terms: int) -> list[expression.Row]:
    _integer(terms, "terms", minimum=1, maximum=MAX_TERMS)
    rows: list[expression.Row] = []
    for n in range(1, terms + 1):
        bits = exact.round_nearest_even(n)
        if exact.decode_finite(bits) != n:
            raise AssertionError("wire row integer is not exact in binary64")
        rows.append((exact.Binary64Interval(bits, bits),))
    return rows


def write_input(path: Path, s: int, terms: int) -> None:
    validate_parameters(s, terms)
    expression.write_input(path, zeta_program(s), zeta_rows(terms))


def validate_input(path: Path, s: int, terms: int) -> None:
    validate_parameters(s, terms)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ZetaPocError(f"cannot read zeta input {path}: {exc}") from exc
    program = zeta_program(s)
    expected_size = (
        expression.HEADER.size
        + len(program.instructions) * expression.INSTRUCTION.size
        + terms * expression.INTERVAL.size
    )
    if len(raw) != expected_size:
        _fail("zeta input length does not match its exact program and row count")
    header = expression.HEADER.unpack_from(raw)
    expected_header = (
        expression.INPUT_MAGIC,
        expression.FORMAT_VERSION,
        len(program.instructions),
        1,
        expression.validated_max_stack(program),
        terms,
    )
    if header != expected_header:
        _fail("zeta input header does not name the required program")
    program_start = expression.HEADER.size
    program_end = program_start + len(program.instructions) * expression.INSTRUCTION.size
    if raw[program_start:program_end] != expression.encoded_program(program):
        _fail("zeta input postfix program is not exactly 1 / n^s")
    for index in range(terms):
        lo, hi = expression.INTERVAL.unpack_from(
            raw, program_end + index * expression.INTERVAL.size
        )
        expected_bits = exact.round_nearest_even(index + 1)
        if (lo, hi) != (expected_bits, expected_bits):
            _fail(f"zeta input row {index} is not the exact point n={index + 1}")


def _interval_json(value: exact.Binary64Interval) -> dict[str, str]:
    return {"lo": f"{value.lo:016x}", "hi": f"{value.hi:016x}"}


def _tail_bounds(s: int, terms: int) -> tuple[Fraction, Fraction]:
    lower = Fraction(1, (s - 1) * (terms + 1) ** (s - 1))
    upper = Fraction(1, (s - 1) * terms ** (s - 1))
    return lower, upper


def derive_output(path: Path, s: int, terms: int) -> DerivedResult:
    """Reparse and exactly recompute every retained GPU row."""

    validate_parameters(s, terms)
    program = zeta_program(s)
    partial = ZERO_INTERVAL
    try:
        with path.open("rb") as stream:
            encoded_header = stream.read(expression.HEADER.size)
            if len(encoded_header) != expression.HEADER.size:
                _fail("GPU output is shorter than its header")
            header = expression.HEADER.unpack(encoded_header)
            expected_header = (
                expression.OUTPUT_MAGIC,
                expression.FORMAT_VERSION,
                len(program.instructions),
                1,
                expression.validated_max_stack(program),
                terms,
            )
            if header != expected_header:
                _fail("GPU output header does not match the zeta program")
            for row_index, row in enumerate(zeta_rows(terms)):
                encoded = stream.read(expression.OUTPUT.size)
                if len(encoded) != expression.OUTPUT.size:
                    _fail(f"GPU output is truncated at row {row_index}")
                lo, hi, status, reserved = expression.OUTPUT.unpack(encoded)
                expected_lo, expected_hi, expected_status = expression.evaluate_program(
                    program, row
                )
                if reserved != bytes(7):
                    _fail(f"GPU output row {row_index} has nonzero reserved bytes")
                if status != expression.STATUS_VALID:
                    _fail(f"GPU output row {row_index} has non-valid status {status}")
                if (lo, hi, status) != (expected_lo, expected_hi, expected_status):
                    _fail(f"GPU output row {row_index} differs from exact recomputation")
                if not exact.is_finite(lo) or not exact.is_finite(hi):
                    _fail(f"GPU output row {row_index} is nonfinite")
                true_term = Fraction(1, (row_index + 1) ** s)
                if not (
                    exact.decode_finite(lo)
                    <= true_term
                    <= exact.decode_finite(hi)
                ):
                    raise AssertionError("exactly recomputed interval missed its rational term")
                partial = exact.interval_add(
                    partial, exact.Binary64Interval(lo, hi)
                )
            if stream.read(1):
                _fail("GPU output has trailing bytes")
    except OSError as exc:
        raise ZetaPocError(f"cannot read GPU output {path}: {exc}") from exc

    tail_lower, tail_upper = _tail_bounds(s, terms)
    tail = exact.Binary64Interval(
        exact.round_down(tail_lower), exact.round_up(tail_upper)
    )
    result = exact.interval_add(partial, tail)
    return DerivedResult(partial, tail, result, tail_lower, tail_upper)


def _runner_fields(
    value: dict[str, Any],
    *,
    target: TargetConfig,
    s: int,
    terms: int,
    what: str,
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "kind",
        "instruction_count",
        "variable_count",
        "max_stack_depth",
        "row_count",
        "valid_row_count",
        "zero_divisor_row_count",
        "nonfinite_widening_row_count",
        "all_rows_valid",
        "device_name",
        "compute_capability",
        "cuda_driver_api_version",
        "cuda_runtime_version",
        "kernel_milliseconds",
        "kernel_rows_per_second",
    }
    report = _exact_object(value, fields, what)
    expected_values = {
        "schema_version": 1,
        "kind": "sparkinterval_cuda_expression_batch",
        "instruction_count": 4,
        "variable_count": 1,
        "max_stack_depth": 2,
        "row_count": terms,
        "valid_row_count": terms,
        "zero_divisor_row_count": 0,
        "nonfinite_widening_row_count": 0,
        "all_rows_valid": True,
        "compute_capability": target.compute_capability,
    }
    for key, expected in expected_values.items():
        if report[key] != expected:
            _fail(
                f"{what}.{key} does not match the strict "
                f"{target.run_label} zeta run"
            )
    if not target.accepts_device_name(report["device_name"]):
        _fail(
            f"{what}.device_name does not match the strict "
            f"{target.run_label} zeta run"
        )
    for key in ("cuda_driver_api_version", "cuda_runtime_version"):
        _integer(report[key], f"{what}.{key}", minimum=1)
    for key in ("kernel_milliseconds", "kernel_rows_per_second"):
        number = report[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or number < 0:
            _fail(f"{what}.{key} must be a finite nonnegative number")
    return {
        "device_name": report["device_name"],
        "compute_capability": report["compute_capability"],
        "cuda_driver_api_version": report["cuda_driver_api_version"],
        "cuda_runtime_version": report["cuda_runtime_version"],
    }


def _validate_audits(root: Path, target: TargetConfig) -> None:
    ptx = root / STAGED_PATHS["gpu_ptx"]
    sass = root / STAGED_PATHS["gpu_sass"]
    ptx_audit = _load_canonical(root / STAGED_PATHS["ptx_audit"])
    sass_audit = _load_canonical(root / STAGED_PATHS["sass_audit"])
    try:
        expected_ptx_audit = inspect_expression_ptx.audit_ptx(
            ptx.read_bytes(), expected_target=target.ptx_target
        )
    except OSError as exc:
        raise ZetaPocError(f"cannot independently audit staged PTX: {exc}") from exc
    if ptx_audit != expected_ptx_audit or expected_ptx_audit.get("passed") is not True:
        _fail(
            "PTX audit does not accept the exact staged "
            f"{target.ptx_target} PTX"
        )

    with tempfile.TemporaryDirectory(prefix="sparkinterval-zeta-sass-audit-") as raw:
        independent_path = Path(raw) / "sass-audit.json"
        _run_command(
            [
                sys.executable,
                str(STAGED_SOURCES["source_sass_audit"]),
                str(sass),
                str(independent_path),
                "--allow-division-lowering",
            ],
            "independent SASS inspection",
        )
        expected_sass_audit = _load_runner_report(independent_path)
    if sass_audit != expected_sass_audit or expected_sass_audit.get("passed") is not True:
        _fail("SASS audit does not accept the exact staged SASS")


def _report_artifacts(root: Path) -> dict[str, dict[str, Any]]:
    result = {
        role: _artifact(root / relative, root)
        for role, relative in STAGED_PATHS.items()
    }
    result["input"] = _artifact(root / INPUT_NAME, root)
    return result


def make_report(
    root: Path,
    s: int,
    terms: int,
    derived: DerivedResult,
    target: TargetConfig = DGX_TARGET,
) -> dict[str, Any]:
    primary = _load_runner_report(root / STAGED_PATHS["runner_report"])
    replay = _load_runner_report(root / STAGED_PATHS["replay_runner_report"])
    device = _runner_fields(
        primary, target=target, s=s, terms=terms, what="runner report"
    )
    replay_device = _runner_fields(
        replay, target=target, s=s, terms=terms, what="replay runner report"
    )
    if replay_device != device:
        _fail("deterministic replay used different reported hardware or CUDA versions")
    _validate_audits(root, target)
    output_hash = _sha256(root / OUTPUT_NAME)
    replay_hash = _sha256(root / REPLAY_OUTPUT_NAME)
    if output_hash != replay_hash:
        _fail("deterministic replay output is not byte-identical")
    definition_hash = _sha256(root / STAGED_PATHS["algorithm_definition"])
    if definition_hash != _sha256(target.algorithm_definition):
        _fail("staged algorithm definition is not the checked-in version for this algorithm id")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "algorithm": {
            "algorithm_id": target.algorithm_id,
            "definition_sha256": definition_hash,
        },
        "parameters": {
            "integer_s": s,
            "term_count": terms,
            "gpu_expression": "1/(n^s)",
            "row_order": "ascending_n_from_1",
            "reduction": "sequential_outward_binary64_interval_add",
        },
        "program": {
            "wire_magic": expression.INPUT_MAGIC.decode("ascii"),
            "instruction_count": 4,
            "variable_count": 1,
            "max_stack_depth": 2,
            "postfix": ["const_one", "var_0", f"pow_nat_{s}", "div"],
        },
        "device": device,
        "exact_row_check": {
            "row_count": terms,
            "valid_row_count": terms,
            "mismatch_count": 0,
            "reserved_bytes_zero": True,
            "every_term_contains_exact_rational": True,
        },
        "partial_sum": _interval_json(derived.partial_sum),
        "tail": {
            "method": "decreasing_positive_integral_test",
            "lower_rational": {
                "numerator": str(derived.tail_lower.numerator),
                "denominator": str(derived.tail_lower.denominator),
            },
            "upper_rational": {
                "numerator": str(derived.tail_upper.numerator),
                "denominator": str(derived.tail_upper.denominator),
            },
            "binary64_interval": _interval_json(derived.tail),
        },
        "zeta_enclosure": {
            "real": _interval_json(derived.result),
            "imaginary": {"lo": "0000000000000000", "hi": "0000000000000000"},
        },
        "deterministic_replay": {
            "passed": True,
            "first_output_sha256": output_hash,
            "replay_output_sha256": replay_hash,
        },
        "artifacts": _report_artifacts(root),
        "accepted": True,
        "assurance": "exact_recomputation_and_local_unattested_execution_record",
        "limitations": [
            "The interval encloses zeta(s) for the recorded real integer s; it does not verify zeta zeros.",
            "The PTX and SASS inspections are lexical audits, not formal compiler or hardware semantics.",
            target.limitation,
        ],
    }


def _parameters(s: int, terms: int) -> dict[str, Any]:
    return {
        "integer_s": s,
        "term_count": terms,
        "gpu_expression": "1/(n^s)",
        "reduction": "ascending_n_sequential_outward_binary64_interval_add",
        "tail_bound": "decreasing_positive_integral_test",
    }


def _coverage(terms: int) -> dict[str, Any]:
    return {
        "first_gpu_term": 1,
        "last_gpu_term": terms,
        "first_tail_term": terms + 1,
        "covers_infinite_positive_integer_series": True,
    }


def _build_artifacts(root: Path) -> list[tuple[str, Path]]:
    return [(role, root / relative) for role, relative in STAGED_PATHS.items()]


def create_local_bundle(
    root: Path,
    *,
    target: TargetConfig = DGX_TARGET,
    s: int,
    terms: int,
    nonce: str,
    start_time_utc: str,
    end_time_utc: str,
) -> dict[str, Any]:
    primary = _load_runner_report(root / STAGED_PATHS["runner_report"])
    device = _runner_fields(
        primary, target=target, s=s, terms=terms, what="runner report"
    )
    try:
        bundle = bundle_format.create_bundle(
            root=root,
            target_profile=bundle_format.load_profile(target.profile_path, "target"),
            trust_profile=bundle_format.load_profile(TRUST_PROFILE, "trust"),
            algorithm_id=target.algorithm_id,
            algorithm_definition_sha256=_sha256(
                root / STAGED_PATHS["algorithm_definition"]
            ),
            input_path=root / INPUT_NAME,
            parameters=_parameters(s, terms),
            domain_coverage=_coverage(terms),
            output_path=root / REPORT_NAME,
            nonce=nonce,
            build_artifacts=_build_artifacts(root),
            execution_environment={
                "host_architecture": platform.machine(),
                "python_version": platform.python_version(),
                "target_profile": target.profile_id,
                **device,
            },
            completion={
                "status": "success",
                "exit_code": 0,
                "expected_output_count": terms,
                "written_output_count": terms,
                "cuda_errors": [],
                "start_time_utc": start_time_utc,
                "end_time_utc": end_time_utc,
            },
        )
        bundle_format.write_bundle(bundle, root / BUNDLE_NAME)
    except bundle_format.BundleError as exc:
        raise ZetaPocError(str(exc)) from exc
    return bundle


def _verify_bundle_semantics(
    root: Path,
    report: dict[str, Any],
    s: int,
    terms: int,
    target: TargetConfig,
) -> dict[str, Any]:
    try:
        receipt = bundle_verify.verify_bundle_file(
            root / BUNDLE_NAME,
            artifact_root=root,
            policy=bundle_verify.INTEGRITY_POLICY,
        )
    except (bundle_format.BundleError, bundle_verify.VerificationError) as exc:
        raise ZetaPocError(str(exc)) from exc
    if (
        receipt.get("accepted") is not True
        or receipt.get("artifacts_verified") is not True
        or receipt.get("target_profile") != target.profile_id
        or receipt.get("trust_profile") != "local_unattested"
        or receipt.get("hardware_evidence") is not False
    ):
        _fail(
            "inner run bundle did not verify as a local-unattested "
            f"{target.run_label} record"
        )
    bundle = _load_canonical(root / BUNDLE_NAME)
    if not isinstance(bundle, dict):
        _fail("run bundle must be an object")
    statement = bundle["statement"]
    if statement["algorithm"] != report["algorithm"]:
        _fail("run bundle algorithm does not match the zeta report")
    if statement["parameters"]["value"] != _parameters(s, terms):
        _fail("run bundle parameters do not match the zeta calculation")
    if statement["domain_coverage"]["value"] != _coverage(terms):
        _fail("run bundle coverage does not include the exact series and tail")
    if statement["input_artifact"] != _artifact(root / INPUT_NAME, root):
        _fail("run bundle input is not the exact zeta input")
    if statement["output_artifact"] != _artifact(root / REPORT_NAME, root):
        _fail("run bundle output is not the exact zeta report")
    actual_build = {(item["role"], item["path"]) for item in statement["build_artifacts"]}
    expected_build = {
        (role, Path(relative).as_posix()) for role, relative in STAGED_PATHS.items()
    }
    if actual_build != expected_build:
        _fail("run bundle does not bind the complete zeta artifact set")
    environment = statement["execution_environment"]["value"]
    if (
        environment.get("target_profile") != target.profile_id
        or environment.get("host_architecture") != target.host_architecture
        or not target.accepts_device_name(environment.get("device_name"))
        or environment.get("compute_capability") != target.compute_capability
    ):
        _fail(
            "run bundle execution environment is not the strict "
            f"{target.run_label} profile"
        )
    return receipt


def verify_work_dir(work_dir: Path) -> dict[str, Any]:
    try:
        root = work_dir.resolve(strict=True)
    except OSError as exc:
        raise ZetaPocError(f"cannot resolve work directory {work_dir}: {exc}") from exc
    if not root.is_dir():
        _fail(f"work directory is not a directory: {root}")
    bundle = _load_canonical(root / BUNDLE_NAME)
    if not isinstance(bundle, dict):
        _fail("run bundle must be an object")
    try:
        profile_id = bundle["statement"]["target_profile"]["profile_id"]
    except (KeyError, TypeError) as exc:
        raise ZetaPocError("run bundle has no target profile id") from exc
    if not isinstance(profile_id, str):
        _fail("run bundle target profile id must be a string")
    target = _target_config(profile_id)
    report = _load_canonical(root / REPORT_NAME)
    if not isinstance(report, dict):
        _fail("zeta report must be an object")
    parameters = report.get("parameters")
    if not isinstance(parameters, dict):
        _fail("zeta report parameters must be an object")
    s = _integer(parameters.get("integer_s"), "report integer_s", minimum=MIN_S, maximum=MAX_S)
    terms = _integer(parameters.get("term_count"), "report term_count", minimum=1, maximum=MAX_TERMS)
    validate_input(root / INPUT_NAME, s, terms)
    derived = derive_output(root / OUTPUT_NAME, s, terms)
    replay_derived = derive_output(root / REPLAY_OUTPUT_NAME, s, terms)
    if replay_derived != derived:
        _fail("replayed GPU result has different exact interval semantics")
    expected_report = make_report(root, s, terms, derived, target)
    if report != expected_report:
        _fail("zeta report differs from independent artifact recomputation")
    bundle_receipt = _verify_bundle_semantics(root, report, s, terms, target)
    return {
        "schema_version": 1,
        "kind": "sparkinterval_real_zeta_poc_verification",
        "accepted": True,
        "integer_s": s,
        "term_count": terms,
        "target_profile": target.profile_id,
        "zeta_enclosure": report["zeta_enclosure"],
        "report_sha256": _sha256(root / REPORT_NAME),
        "bundle_sha256": bundle_receipt["bundle_sha256"],
        "evidence_class": "local_unattested",
        "hardware_evidence": False,
    }


def _copy(source: Path, destination: Path, *, executable: bool = False) -> None:
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise ZetaPocError(f"cannot resolve required artifact {source}: {exc}") from exc
    if not resolved.is_file():
        _fail(f"required artifact is not a regular file: {resolved}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(resolved, destination)
        if executable:
            destination.chmod(destination.stat().st_mode | 0o111)
    except OSError as exc:
        raise ZetaPocError(f"cannot stage {resolved}: {exc}") from exc


def _stage_sources(root: Path, target: TargetConfig) -> None:
    for role, source in STAGED_SOURCES.items():
        if role == "algorithm_definition":
            source = target.algorithm_definition
        _copy(source, root / STAGED_PATHS[role])
    _copy(target.profile_path, root / STAGED_PATHS["source_target_profile"])


def _run_command(command: Sequence[str], what: str, *, timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ZetaPocError(f"cannot run {what}: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        _fail(f"{what} failed with exit {completed.returncode}: {message}")
    return completed


def _audit_device(
    root: Path, executable: Path, target: TargetConfig = DGX_TARGET
) -> None:
    located = shutil.which("cuobjdump")
    if located is None:
        _fail("cuobjdump is required to bind and audit the expression device code")
    cuobjdump = root / STAGED_PATHS["tool_cuobjdump"]
    _copy(Path(located), cuobjdump, executable=True)
    try:
        ptx = inspect_expression_ptx.extract_ptx(executable, cuobjdump=str(cuobjdump))
    except (OSError, RuntimeError) as exc:
        raise ZetaPocError(str(exc)) from exc
    ptx_path = root / STAGED_PATHS["gpu_ptx"]
    ptx_path.write_bytes(ptx)
    ptx_audit = inspect_expression_ptx.audit_ptx(
        ptx, expected_target=target.ptx_target
    )
    if ptx_audit.get("passed") is not True:
        _fail("strict expression PTX audit failed")
    _write_canonical(root / STAGED_PATHS["ptx_audit"], ptx_audit)

    sass_completed = _run_command(
        [str(cuobjdump), "--dump-sass", str(executable)],
        "cuobjdump SASS extraction",
    )
    if not sass_completed.stdout:
        _fail("cuobjdump SASS extraction produced no output")
    sass_path = root / STAGED_PATHS["gpu_sass"]
    sass_path.write_bytes(sass_completed.stdout)
    sass_audit_path = root / STAGED_PATHS["sass_audit"]
    _run_command(
        [
            sys.executable,
            str(root / STAGED_PATHS["source_sass_audit"]),
            str(sass_path),
            str(sass_audit_path),
            "--allow-division-lowering",
        ],
        "strict SASS inspection",
    )
    sass_audit = _load_runner_report(sass_audit_path)
    if sass_audit.get("passed") is not True:
        _fail("strict SASS inspection did not pass")
    _write_canonical(sass_audit_path, sass_audit)


def _run_gpu(
    executable: Path,
    input_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    device: int,
    what: str,
) -> dict[str, Any]:
    completed = _run_command(
        [
            str(executable),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--device",
            str(device),
        ],
        what,
    )
    report_path.write_bytes(completed.stdout)
    return _load_runner_report(report_path)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_poc(
    work_dir: Path,
    *,
    executable: Path,
    target_profile: str = DGX_TARGET.profile_id,
    s: int,
    terms: int,
    device: int,
    nonce: str | None,
) -> dict[str, Any]:
    target = _target_config(target_profile)
    validate_parameters(s, terms)
    if platform.machine() != target.host_architecture:
        _fail(
            f"the recorded {target.run_label} profile requires a "
            f"{target.host_architecture} host"
        )
    if device != 0:
        _fail(f"the recorded {target.run_label} profile requires device 0")
    if nonce is None:
        nonce = secrets.token_hex(32)
    try:
        bundle_format.validate_nonce(nonce)
    except bundle_format.BundleError as exc:
        raise ZetaPocError(str(exc)) from exc
    destination = work_dir.resolve(strict=False)
    if destination.exists():
        _fail(f"work directory already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=destination.name + ".tmp-", dir=destination.parent)
    )
    completed = False
    try:
        _stage_sources(staging, target)
        staged_executable = staging / STAGED_PATHS["host_executable"]
        _copy(executable, staged_executable, executable=True)
        _audit_device(staging, staged_executable, target)
        write_input(staging / INPUT_NAME, s, terms)
        start_time = _utc_now()
        primary = _run_gpu(
            staged_executable,
            staging / INPUT_NAME,
            staging / OUTPUT_NAME,
            staging / STAGED_PATHS["runner_report"],
            device=device,
            what=f"{target.run_label} zeta term run",
        )
        _runner_fields(
            primary, target=target, s=s, terms=terms, what="runner report"
        )
        replay = _run_gpu(
            staged_executable,
            staging / INPUT_NAME,
            staging / REPLAY_OUTPUT_NAME,
            staging / STAGED_PATHS["replay_runner_report"],
            device=device,
            what=f"{target.run_label} zeta deterministic replay",
        )
        _runner_fields(
            replay,
            target=target,
            s=s,
            terms=terms,
            what="replay runner report",
        )
        end_time = _utc_now()
        derived = derive_output(staging / OUTPUT_NAME, s, terms)
        replay_derived = derive_output(staging / REPLAY_OUTPUT_NAME, s, terms)
        if replay_derived != derived or _sha256(staging / OUTPUT_NAME) != _sha256(
            staging / REPLAY_OUTPUT_NAME
        ):
            _fail(
                f"{target.run_label} zeta replay was not byte-identical and "
                "semantically identical"
            )
        report = make_report(staging, s, terms, derived, target)
        _write_canonical(staging / REPORT_NAME, report)
        create_local_bundle(
            staging,
            target=target,
            s=s,
            terms=terms,
            nonce=nonce,
            start_time_utc=start_time,
            end_time_utc=end_time,
        )
        receipt = verify_work_dir(staging)
        if destination.exists():
            _fail(f"work directory appeared during the run: {destination}")
        staging.rename(destination)
        completed = True
        return receipt
    finally:
        if not completed:
            shutil.rmtree(staging, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="run, replay, check, and package a target-bound POC"
    )
    run.add_argument("--work-dir", type=Path, required=True)
    run.add_argument(
        "--target-profile",
        choices=tuple(TARGETS),
        default=DGX_TARGET.profile_id,
        help="strict execution target (default: dgx_spark_sm121)",
    )
    run.add_argument(
        "--executable",
        type=Path,
        help="target-specific expression runner (default selected by --target-profile)",
    )
    run.add_argument("--s", type=int, default=2)
    run.add_argument("--terms", type=int, default=DEFAULT_TERMS)
    run.add_argument("--device", type=int, default=0)
    run.add_argument("--nonce", help="optional 32-byte challenger nonce in lowercase hex")
    verify = commands.add_parser("verify", help="independently verify a retained POC")
    verify.add_argument("work_dir", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            target = _target_config(args.target_profile)
            receipt = run_poc(
                args.work_dir,
                executable=args.executable or target.default_executable,
                target_profile=target.profile_id,
                s=args.s,
                terms=args.terms,
                device=args.device,
                nonce=args.nonce,
            )
        else:
            receipt = verify_work_dir(args.work_dir)
    except (
        ZetaPocError,
        bundle_format.BundleError,
        bundle_verify.VerificationError,
        OSError,
        ValueError,
    ) as exc:
        print(f"run_zeta_poc: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(bundle_format.canonical_json_bytes(receipt))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
