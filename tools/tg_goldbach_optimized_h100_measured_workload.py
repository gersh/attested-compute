#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or replay one bounded optimized-Goldbach H100 calibration workload."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
from math import isqrt
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker,
)
from tg_verifier.goldbach_optimized_calibration_contract import (  # noqa: E402
    ALGORITHM_PREFIX,
    CLASSIFICATION,
    RESULT_KIND,
    TRACE_KIND,
    GoldbachCalibrationContractError,
    algorithm_identity,
    canonical_json_bytes,
    sha256_bytes,
    trace_sha256,
    validate_input,
)


MANIFEST_KIND = "sparkinterval.goldbach-optimized-candidate-package.v1"
MANIFEST_DOMAIN = b"sparkinterval/tg/goldbach-optimized-candidate/v1\x00"
CLOSURE_DOMAIN = b"sparkinterval/tg/goldbach-optimized-closure/v1\x00"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_STDOUT_BYTES = 64 * 1024
SEGMENT_SIZE = 200_000_000
P_SMALL = 1_000_000
BATCH_SIZE = 2_000_000
H100_NAME_RE = re.compile(r"^NVIDIA H100(?: |\Z)")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NUMBER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"
)


class GoldbachCalibrationWorkloadError(RuntimeError):
    """The candidate, input, run transcript, result, or trace differed."""


def _safe_relative(value: Path, what: str) -> Path:
    text = value.as_posix()
    parsed = PurePosixPath(text)
    if (
        not text
        or parsed.is_absolute()
        or text != parsed.as_posix()
        or any(part in ("", ".", "..") for part in parsed.parts)
    ):
        raise GoldbachCalibrationWorkloadError(
            f"{what} must be a safe relative POSIX path"
        )
    return Path(*parsed.parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _pin(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise GoldbachCalibrationWorkloadError(
            f"candidate file is linked or nonregular: {path}"
        )
    return {"sha256": _sha256(path), "size_bytes": metadata.st_size}


def _read_canonical_json(path: Path, maximum: int, what: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > maximum:
        raise GoldbachCalibrationWorkloadError(f"{what} exceeds size limit")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise GoldbachCalibrationWorkloadError(
            f"{what} is not JSON"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise GoldbachCalibrationWorkloadError(
            f"{what} is not one canonical JSON object"
        )
    return value


def _closure_rows(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise GoldbachCalibrationWorkloadError(
                "candidate closure contains a symbolic link"
            )
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise GoldbachCalibrationWorkloadError(
                "candidate closure contains a linked or special file"
            )
        relative = path.relative_to(root).as_posix()
        if relative == "candidate-manifest.json":
            continue
        rows.append({"path": relative, **_pin(path)})
    return rows


def _candidate_manifest(candidate_root: Path) -> dict[str, Any]:
    value = _read_canonical_json(
        candidate_root / "candidate-manifest.json",
        MAX_MANIFEST_BYTES,
        "candidate manifest",
    )
    if value.get("kind") != MANIFEST_KIND or value.get("schema_version") != 1:
        raise GoldbachCalibrationWorkloadError(
            "candidate manifest kind/version differs"
        )
    manifest_sha256 = value.get("manifest_sha256")
    if (
        not isinstance(manifest_sha256, str)
        or SHA256_RE.fullmatch(manifest_sha256) is None
    ):
        raise GoldbachCalibrationWorkloadError(
            "candidate manifest digest is malformed"
        )
    body = dict(value)
    del body["manifest_sha256"]
    if hashlib.sha256(
        MANIFEST_DOMAIN + canonical_json_bytes(body)
    ).hexdigest() != manifest_sha256:
        raise GoldbachCalibrationWorkloadError(
            "candidate manifest self-hash differs"
        )
    rows = _closure_rows(candidate_root)
    if rows != value.get("closure_files"):
        raise GoldbachCalibrationWorkloadError(
            "candidate retained file closure differs"
        )
    closure_sha256 = hashlib.sha256(
        CLOSURE_DOMAIN + canonical_json_bytes(rows)
    ).hexdigest()
    if closure_sha256 != value.get("closure_sha256"):
        raise GoldbachCalibrationWorkloadError(
            "candidate closure digest differs"
        )
    trust = value.get("trust_status")
    if not isinstance(trust, dict) or any(item is not False for item in trust.values()):
        raise GoldbachCalibrationWorkloadError(
            "candidate manifest overstates a trust gate"
        )
    build = value.get("build")
    if (
        not isinstance(build, dict)
        or build.get("arch") != "sm_90"
        or build.get("host_architecture") != "x86_64"
        or value.get("bounded_component_kats_completed") is not True
        or value.get("bounded_full_differential_completed") is not True
    ):
        raise GoldbachCalibrationWorkloadError(
            "candidate was not fully qualified on an x86_64 sm_90 build host"
        )
    return value


def _input(
    input_path: Path, candidate_root: Path, executable: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = _read_canonical_json(
        input_path, 64 * 1024, "calibration input"
    )
    try:
        checked = validate_input(value)
    except GoldbachCalibrationContractError as error:
        raise GoldbachCalibrationWorkloadError(str(error)) from error
    manifest = _candidate_manifest(candidate_root)
    candidate = checked["candidate"]
    artifacts = manifest["artifacts"]
    expected = {
        "candidate_closure_sha256": manifest["closure_sha256"],
        "candidate_manifest_sha256": manifest["manifest_sha256"],
        "cubin_sha256": artifacts["cubin"]["sha256"],
        "executable_sha256": artifacts["executable"]["sha256"],
        "executable_size_bytes": artifacts["executable"]["size_bytes"],
        "ptx_sha256": artifacts["ptx"]["sha256"],
        "sass_sha256": artifacts["sass"]["sha256"],
        "source_identity_sha256": manifest["optimized_source"][
            "source_identity_sha256"
        ],
    }
    if candidate != expected or _pin(executable) != {
        "sha256": candidate["executable_sha256"],
        "size_bytes": candidate["executable_size_bytes"],
    }:
        raise GoldbachCalibrationWorkloadError(
            "calibration input/candidate executable identity differs"
        )
    if executable.stat().st_mode & 0o111 == 0:
        raise GoldbachCalibrationWorkloadError(
            "candidate executable lacks execute permission"
        )
    return checked, manifest


def _expected_small_high(limit: int) -> int:
    result = max(isqrt(limit) + 1, min(P_SMALL, limit))
    return result if result % 2 else result + 1


def _parse_stdout(
    raw: bytes, *, start: int, limit: int, count: int
) -> dict[str, object]:
    if len(raw) > MAX_STDOUT_BYTES:
        raise GoldbachCalibrationWorkloadError(
            "candidate stdout exceeds limit"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise GoldbachCalibrationWorkloadError(
            "candidate stdout is not UTF-8"
        ) from error
    number = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
    pattern = re.compile(
        r"\A\[Hardware\] GPU 0: (?P<gpu>[^\r\n\[\]]+) "
        r"\((?P<vram>[1-9][0-9]*) MB VRAM\)\n"
        r"Building small primes bitset up to (?P<small>[1-9][0-9]*)\.\.\.\n"
        r"Pre-generating CPU primes up to 100000000\.\.\.\n"
        rf"Initialization completed in (?P<init>{number}) ms\.\n\n"
        r"--- Launching Multi-GPU Verifier ---\n"
        r"Checking range : \[(?P<start>[0-9]+), (?P<limit>[0-9]+)\]\n"
        r"Total numbers  : (?P<count>[0-9]+)\n\n\n"
        r"--- Verification Complete ---\n"
        r"All even numbers from (?P<success_start>[0-9]+) up to "
        r"(?P<success_limit>[0-9]+) satisfy Goldbach\. ✓\n"
        rf"Total computation time : (?P<seconds>{number}) seconds\n"
        r"Phase 2 fallbacks      : (?P<fallbacks>[0-9]+)\n\Z"
    )
    match = pattern.fullmatch(text)
    if match is None:
        raise GoldbachCalibrationWorkloadError(
            "candidate stdout grammar differs"
        )
    values = match.groupdict()
    expected = {
        "count": count,
        "limit": limit,
        "small": _expected_small_high(limit),
        "start": start,
        "success_limit": limit,
        "success_start": start,
    }
    if any(int(values[name]) != wanted for name, wanted in expected.items()):
        raise GoldbachCalibrationWorkloadError(
            "candidate stdout domain differs"
        )
    if (
        H100_NAME_RE.match(values["gpu"]) is None
        or int(values["vram"]) < 75_000
        or int(values["fallbacks"]) != 0
        or NUMBER_RE.fullmatch(values["init"]) is None
        or NUMBER_RE.fullmatch(values["seconds"]) is None
    ):
        raise GoldbachCalibrationWorkloadError(
            "candidate H100/fallback/timing transcript differs"
        )
    return {
        "gpu_name": values["gpu"],
        "gpu_vram_mb": int(values["vram"]),
        "initialization_milliseconds": values["init"],
        "phase2_fallbacks": 0,
        "reported_computation_seconds": values["seconds"],
        "small_prime_bitset_limit": int(values["small"]),
    }


def _seconds_to_nanoseconds(value: str) -> int:
    try:
        scaled = Decimal(value) * Decimal(1_000_000_000)
    except InvalidOperation as error:
        raise GoldbachCalibrationWorkloadError(
            "reported seconds are not decimal"
        ) from error
    integral = scaled.to_integral_exact()
    if scaled != integral or not 0 < integral <= (1 << 63) - 1:
        raise GoldbachCalibrationWorkloadError(
            "reported seconds do not encode positive whole nanoseconds"
        )
    return int(integral)


def _runner_argv(executable: Path, input_value: dict[str, Any]) -> list[str]:
    domain = input_value["domain"]
    return [
        str(executable),
        str(domain["even_limit_inclusive"]),
        f"--start={domain['even_start_inclusive']}",
        f"--seg-size={SEGMENT_SIZE}",
        f"--p-small={P_SMALL}",
        f"--batch-size={BATCH_SIZE}",
        "--gpus=1",
        "--primetest=mr",
    ]


def _run_once(
    executable: Path, input_value: dict[str, Any], timeout: int
) -> dict[str, Any]:
    domain = input_value["domain"]
    started = time.monotonic_ns()
    try:
        completed = subprocess.run(
            _runner_argv(executable, input_value),
            cwd=executable.parent,
            env={
                "CUDA_VISIBLE_DEVICES": "0",
                "HOME": "/nonexistent",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/local/cuda/bin:/usr/bin:/bin",
                "TZ": "UTC",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.SubprocessError as error:
        raise GoldbachCalibrationWorkloadError(
            "candidate process did not complete"
        ) from error
    wall = time.monotonic_ns() - started
    if completed.returncode != 0 or completed.stderr:
        raise GoldbachCalibrationWorkloadError(
            "candidate process failed or wrote stderr"
        )
    parsed = _parse_stdout(
        completed.stdout,
        start=domain["even_start_inclusive"],
        limit=domain["even_limit_inclusive"],
        count=domain["even_count"],
    )
    reported = _seconds_to_nanoseconds(
        str(parsed["reported_computation_seconds"])
    )
    if wall < reported:
        raise GoldbachCalibrationWorkloadError(
            "candidate wall time is below its reported compute time"
        )
    return {
        "parsed": parsed,
        "reported_computation_nanoseconds": reported,
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "stdout_utf8": completed.stdout.decode("utf-8"),
        "wall_nanoseconds": wall,
    }


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o400,
    )
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise GoldbachCalibrationWorkloadError(
                    f"short write: {path}"
                )
            view = view[count:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _validate_result(
    value: object, input_value: dict[str, Any]
) -> dict[str, Any]:
    fields = {
        "authority",
        "candidate",
        "classification",
        "domain",
        "kind",
        "measured_runs",
        "median_reported_computation_nanoseconds",
        "schema_version",
        "warmup_runs",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise GoldbachCalibrationWorkloadError(
            "calibration result has wrong fields"
        )
    if (
        value["kind"] != RESULT_KIND
        or value["schema_version"] != 1
        or value["classification"] != CLASSIFICATION
        or value["candidate"] != input_value["candidate"]
        or value["domain"] != input_value["domain"]
        or value["authority"]
        != {
            "confidential_attestation_completed": False,
            "lean_atom_discharged": False,
            "production_identity_promoted": False,
            "source_scale_completion": False,
            "target_h100_measurement_completed": False,
        }
    ):
        raise GoldbachCalibrationWorkloadError(
            "calibration result identity/authority differs"
        )
    warmups = value["warmup_runs"]
    measured = value["measured_runs"]
    if (
        not isinstance(warmups, list)
        or len(warmups) != input_value["warmups"]
        or not isinstance(measured, list)
        or len(measured) != input_value["repetitions"]
    ):
        raise GoldbachCalibrationWorkloadError(
            "calibration result repetition geometry differs"
        )
    for index, row in enumerate([*warmups, *measured]):
        if not isinstance(row, dict) or set(row) != {
            "parsed",
            "reported_computation_nanoseconds",
            "stdout_sha256",
            "stdout_utf8",
            "wall_nanoseconds",
        }:
            raise GoldbachCalibrationWorkloadError(
                f"calibration run {index} has wrong fields"
            )
        stdout = row["stdout_utf8"]
        if not isinstance(stdout, str):
            raise GoldbachCalibrationWorkloadError(
                f"calibration run {index} stdout is not text"
            )
        raw = stdout.encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != row["stdout_sha256"]:
            raise GoldbachCalibrationWorkloadError(
                f"calibration run {index} stdout hash differs"
            )
        domain = input_value["domain"]
        parsed = _parse_stdout(
            raw,
            start=domain["even_start_inclusive"],
            limit=domain["even_limit_inclusive"],
            count=domain["even_count"],
        )
        reported = _seconds_to_nanoseconds(
            str(parsed["reported_computation_seconds"])
        )
        wall = row["wall_nanoseconds"]
        if (
            parsed != row["parsed"]
            or reported != row["reported_computation_nanoseconds"]
            or isinstance(wall, bool)
            or not isinstance(wall, int)
            or wall < reported
        ):
            raise GoldbachCalibrationWorkloadError(
                f"calibration run {index} replay differs"
            )
    ordered = sorted(
        row["reported_computation_nanoseconds"] for row in measured
    )
    if value["median_reported_computation_nanoseconds"] != ordered[len(ordered) // 2]:
        raise GoldbachCalibrationWorkloadError(
            "calibration median differs from exact repetitions"
        )
    return value


def _trace_value(
    args: argparse.Namespace,
    *,
    input_value: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    input_sha256 = _sha256(args.input)
    result_sha256 = _sha256(args.output)
    stdout_sha256s = [
        row["stdout_sha256"]
        for row in [*result["warmup_runs"], *result["measured_runs"]]
    ]
    return {
        "algorithm_id": args.algorithm_id,
        "challenge_nonce": args.challenge,
        "input_sha256": input_sha256,
        "iteration_count": 1,
        "job_binding_sha256": args.job_binding,
        "kind": TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
        "trace_sha256": trace_sha256(
            challenge_nonce=args.challenge,
            job_binding_sha256=args.job_binding,
            input_sha256=input_sha256,
            executable_sha256=input_value["candidate"][
                "executable_sha256"
            ],
            result_sha256=result_sha256,
            stdout_sha256s=stdout_sha256s,
        ),
    }


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge, job_binding=args.job_binding
    )
    input_value, _manifest = _input(
        args.input, args.candidate_root, args.executable
    )
    expected_identity = algorithm_identity(input_value)
    if args.algorithm_id != expected_identity["algorithm_id"]:
        raise GoldbachCalibrationWorkloadError(
            "calibration algorithm identity differs"
        )
    warmups = [
        _run_once(args.executable, input_value, args.timeout)
        for _ in range(input_value["warmups"])
    ]
    measured = [
        _run_once(args.executable, input_value, args.timeout)
        for _ in range(input_value["repetitions"])
    ]
    ordered = sorted(
        row["reported_computation_nanoseconds"] for row in measured
    )
    result = {
        "authority": {
            "confidential_attestation_completed": False,
            "lean_atom_discharged": False,
            "production_identity_promoted": False,
            "source_scale_completion": False,
            "target_h100_measurement_completed": False,
        },
        "candidate": input_value["candidate"],
        "classification": CLASSIFICATION,
        "domain": input_value["domain"],
        "kind": RESULT_KIND,
        "measured_runs": measured,
        "median_reported_computation_nanoseconds": ordered[len(ordered) // 2],
        "schema_version": 1,
        "warmup_runs": warmups,
    }
    encoded = canonical_json_bytes(result)
    _write_exclusive(args.output, encoded)
    _write_exclusive(
        args.trace,
        canonical_json_bytes(
            _trace_value(args, input_value=input_value, result=result)
        ),
    )


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge, job_binding=args.job_binding
    )
    input_value, _manifest = _input(
        args.input, args.candidate_root, args.executable
    )
    if args.algorithm_id != algorithm_identity(input_value)["algorithm_id"]:
        raise GoldbachCalibrationWorkloadError(
            "calibration algorithm identity differs"
        )
    result = _validate_result(
        _read_canonical_json(
            args.output, 1024 * 1024, "calibration result"
        ),
        input_value,
    )
    expected = _trace_value(
        args, input_value=input_value, result=result
    )
    actual = _read_canonical_json(
        args.trace, 64 * 1024, "calibration trace"
    )
    if actual != expected:
        raise GoldbachCalibrationWorkloadError(
            "calibration challenge trace differs"
        )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--candidate-root", type=Path, required=True)
    result.add_argument("--executable", type=Path, required=True)
    result.add_argument("--timeout", type=int, default=3600)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if (
            SHA256_RE.fullmatch(args.challenge) is None
            or SHA256_RE.fullmatch(args.job_binding) is None
            or not 60 <= args.timeout <= 86_400
            or not args.algorithm_id.startswith(ALGORITHM_PREFIX)
        ):
            raise GoldbachCalibrationWorkloadError(
                "calibration invocation identity/timeout differs"
            )
        for name in ("input", "output", "trace", "candidate_root", "executable"):
            setattr(args, name, _safe_relative(getattr(args, name), name))
        if args.mode == "run":
            run(args)
        else:
            verify_trace(args)
        return 0
    except (
        CampaignIOError,
        GoldbachCalibrationContractError,
        GoldbachCalibrationWorkloadError,
        OSError,
        ValueError,
    ) as error:
        print(f"optimized Goldbach H100 calibration failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
