#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed measured workload for the retained CH25 Lemma A.7 boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.a7_flint import A7FlintReplayError, replay_a7_flint  # noqa: E402
from tg_verifier.analytic import canonical_json_bytes  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    hash_file_once,
    require_azure_measured_worker,
)
from tg_verifier.python_flint_runtime import (  # noqa: E402
    PythonFlintRuntimeError,
    extract_verified_wheel,
    load_pin as load_python_flint_pin,
    verify_wheel,
)


REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1"
)
REGISTERED_INPUT = (
    b'{"campaign":"ch25-a7-boundary-v1","retained_artifact_sha256":'
    b'"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"}'
)
REGISTERED_RESULT = b"true"
RETAINED_ARTIFACT_SHA256 = (
    "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"
)
TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 3
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.ch25-a7-boundary.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.ch25-a7-boundary.step.v1\n"
REPORT_PATH = Path("a7-replay.json")
MAX_REPORT_BYTES = 64 * 1024


class A7MeasuredWorkloadError(RuntimeError):
    """The exact input, runtime, artifact replay, report, or trace differed."""


def _safe_relative(value: str, what: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise A7MeasuredWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _hex(value: str, what: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise A7MeasuredWorkloadError(f"{what} is not lowercase SHA-256 hex")
    return value


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
            written = os.write(descriptor, view)
            if written <= 0:
                raise A7MeasuredWorkloadError("short exclusive output write")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        with path.open("rb") as source:
            raw = source.read(maximum + 1)
    except OSError as error:
        raise A7MeasuredWorkloadError(f"cannot read {what}: {error}") from error
    if len(raw) > maximum:
        raise A7MeasuredWorkloadError(f"{what} exceeds its byte limit")
    return raw


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for directory, names, _files in os.walk(path):
        try:
            Path(directory).chmod(0o700)
        except OSError:
            pass
        for name in names:
            candidate = Path(directory) / name
            if candidate.is_dir():
                try:
                    candidate.chmod(0o700)
                except OSError:
                    pass
    shutil.rmtree(path, ignore_errors=True)


def _activate_runtime(wheel: Path, destination: Path) -> dict[str, Any]:
    pin = load_python_flint_pin(ROOT / "specifications/PYTHON_FLINT_0_9_UPSTREAM.json")
    identity = extract_verified_wheel(wheel, destination, pin)
    sys.path.insert(0, str(destination))
    try:
        import flint  # type: ignore

        if (
            str(flint.__version__) != "0.9.0"
            or str(flint.__FLINT_VERSION__) != "3.6.0"
            or int(flint.__FLINT_RELEASE__) != 30_600
        ):
            raise A7MeasuredWorkloadError("loaded python-flint/FLINT version differs")
    except (ImportError, AttributeError, OSError, ValueError) as error:
        raise A7MeasuredWorkloadError(
            f"cannot load pinned python-flint runtime: {error}"
        ) from error
    return identity


def _normalized_report(report: dict[str, Any]) -> dict[str, Any]:
    value = dict(report)
    elapsed = value.pop("elapsed_milliseconds", None)
    if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0:
        raise A7MeasuredWorkloadError("A.7 replay elapsed time is malformed")
    required_true = (
        "artifact_bytes_match_pinned_sha256",
        "four_edge_dyadic_cover_verified",
        "every_leaf_flint_box_recomputed",
        "every_exact_leaf_endpoint_matched",
        "all_denominator_and_zeta_nonvanishing_guards_checked",
        "strict_norm_square_bound_verified_under_flint_semantics",
        "external_analytic_verification_complete",
    )
    if (
        value.get("accepted") is not True
        or value.get("artifact_kind") != "ch25_a7_boundary"
        or value.get("verification_class")
        != "complete_external_flint_arb_leaf_replay"
        or value.get("artifact_sha256") != RETAINED_ARTIFACT_SHA256
        or value.get("python_flint_version") != "0.9.0"
        or value.get("flint_version") != "3.6.0"
        or value.get("flint_release") != 30_600
        or value.get("leaf_count") != 16_191
        or any(value.get(field) is not True for field in required_true)
        or value.get("ordinary_kernel_lean_proof") is not False
        or value.get("mathlib_zeta_realization_theorem_present") is not False
        or value.get("lean_atom_discharged") is not False
    ):
        raise A7MeasuredWorkloadError("A.7 replay report differs from the closed contract")
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_REPORT_BYTES:
        raise A7MeasuredWorkloadError("normalized A.7 replay report is too large")
    return value


def _trace_hash(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    wheel_sha256: str,
    artifact_sha256: str,
    report_sha256: str,
    result_sha256: str,
) -> str:
    current = hashlib.sha256(
        INITIAL_DOMAIN
        + f"challenge_nonce={challenge}\n".encode("ascii")
        + f"job_binding_sha256={job_binding}\n".encode("ascii")
        + f"input_sha256={input_sha256}\n".encode("ascii")
    ).hexdigest()
    current = hashlib.sha256(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"python_flint_wheel_sha256={wheel_sha256}\n".encode("ascii")
    ).hexdigest()
    current = hashlib.sha256(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"retained_artifact_sha256={artifact_sha256}\n".encode("ascii")
        + f"normalized_report_sha256={report_sha256}\n".encode("ascii")
    ).hexdigest()
    return hashlib.sha256(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"result_sha256={result_sha256}\n".encode("ascii")
    ).hexdigest()


def _trace_value(
    args: argparse.Namespace,
    *,
    input_sha256: str,
    wheel_sha256: str,
    artifact_sha256: str,
    report_sha256: str,
    result_sha256: str,
) -> dict[str, Any]:
    return {
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "challenge_nonce": args.challenge,
        "input_sha256": input_sha256,
        "iteration_count": TRACE_ITERATIONS,
        "job_binding_sha256": args.job_binding,
        "kind": TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
        "trace_sha256": _trace_hash(
            challenge=args.challenge,
            job_binding=args.job_binding,
            input_sha256=input_sha256,
            wheel_sha256=wheel_sha256,
            artifact_sha256=artifact_sha256,
            report_sha256=report_sha256,
            result_sha256=result_sha256,
        ),
    }


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    if _read(args.input, len(REGISTERED_INPUT), "registered input") != REGISTERED_INPUT:
        raise A7MeasuredWorkloadError("registered A.7 input differs")
    artifact_sha256, _artifact_size = hash_file_once(args.artifact)
    if artifact_sha256 != RETAINED_ARTIFACT_SHA256:
        raise A7MeasuredWorkloadError("retained A.7 artifact differs")
    wheel = verify_wheel(args.wheel)
    if args.work.exists():
        raise A7MeasuredWorkloadError("A.7 work path must be fresh")
    args.work.mkdir(mode=0o700, parents=True)
    runtime = args.work / "python-flint-runtime"
    succeeded = False
    try:
        _activate_runtime(args.wheel, runtime)
        report = _normalized_report(
            replay_a7_flint(args.artifact, require_retained_identity=True)
        )
        report_path = args.work / REPORT_PATH
        _write_exclusive(report_path, canonical_json_bytes(report))
        _write_exclusive(args.output, REGISTERED_RESULT)
        input_sha256, _ = hash_file_once(args.input)
        report_sha256, _ = hash_file_once(report_path)
        result_sha256, _ = hash_file_once(args.output)
        trace = _trace_value(
            args,
            input_sha256=input_sha256,
            wheel_sha256=wheel["sha256"],
            artifact_sha256=artifact_sha256,
            report_sha256=report_sha256,
            result_sha256=result_sha256,
        )
        _write_exclusive(args.trace, canonical_json_bytes(trace))
        succeeded = True
    finally:
        _remove_tree(runtime)
        if not succeeded:
            _remove_tree(args.work)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    if _read(args.input, len(REGISTERED_INPUT), "registered input") != REGISTERED_INPUT:
        raise A7MeasuredWorkloadError("registered A.7 input differs")
    if _read(args.output, len(REGISTERED_RESULT), "registered result") != REGISTERED_RESULT:
        raise A7MeasuredWorkloadError("registered A.7 result is not literal true")
    artifact_sha256, _artifact_size = hash_file_once(args.artifact)
    if artifact_sha256 != RETAINED_ARTIFACT_SHA256:
        raise A7MeasuredWorkloadError("retained A.7 artifact differs")
    wheel = verify_wheel(args.wheel)
    report_path = args.work / REPORT_PATH
    retained_report = _read(report_path, MAX_REPORT_BYTES, "retained A.7 report")
    runtime = args.work / "python-flint-trace-runtime"
    try:
        _activate_runtime(args.wheel, runtime)
        fresh_report = canonical_json_bytes(
            _normalized_report(
                replay_a7_flint(args.artifact, require_retained_identity=True)
            )
        )
        if fresh_report != retained_report:
            raise A7MeasuredWorkloadError(
                "fresh A.7 trace replay differs from the retained report"
            )
        input_sha256, _ = hash_file_once(args.input)
        report_sha256 = hashlib.sha256(retained_report).hexdigest()
        result_sha256, _ = hash_file_once(args.output)
        expected = _trace_value(
            args,
            input_sha256=input_sha256,
            wheel_sha256=wheel["sha256"],
            artifact_sha256=artifact_sha256,
            report_sha256=report_sha256,
            result_sha256=result_sha256,
        )
        trace_raw = _read(args.trace, MAX_REPORT_BYTES, "A.7 work trace")
        try:
            trace = json.loads(trace_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise A7MeasuredWorkloadError("A.7 work trace is not JSON") from error
        if canonical_json_bytes(trace) != trace_raw or trace != expected:
            raise A7MeasuredWorkloadError("A.7 work trace differs")
    finally:
        _remove_tree(runtime)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--artifact", type=Path, required=True)
    result.add_argument("--wheel", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    return result


def _validate_args(args: argparse.Namespace) -> None:
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        raise A7MeasuredWorkloadError("algorithm id differs from registered A.7")
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    for name in ("input", "output", "trace", "artifact", "wheel", "work"):
        value = getattr(args, name)
        setattr(args, name, _safe_relative(value.as_posix(), name))


def main() -> int:
    args = parser().parse_args()
    try:
        _validate_args(args)
        if args.mode == "run":
            run(args)
        else:
            verify_trace(args)
        return 0
    except (
        A7FlintReplayError,
        A7MeasuredWorkloadError,
        OSError,
        PythonFlintRuntimeError,
        ValueError,
    ) as error:
        print(f"A.7 measured workload error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
