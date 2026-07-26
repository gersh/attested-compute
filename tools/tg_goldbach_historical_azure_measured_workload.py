#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Measured terminal for the historical Helfgott--Platt reconstruction."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "attestation", ROOT / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, extract_archive  # noqa: E402
from tg_verifier.azure_cpu_goldbach_historical_workload_factory import (  # noqa: E402
    REGISTERED_ALGORITHM_ID,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT,
    TRACE_DEFINITION,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    read_bytes_once,
    require_azure_measured_worker,
)
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GoldbachBuildAdmissionError,
    load_build_admission,
)
from tg_verifier.goldbach_historical_terminal import (  # noqa: E402
    HistoricalGoldbachTerminalError,
    load_child_identity_commitment,
    replay_terminal_handoff,
)


TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 3
INITIAL_DOMAIN = (
    b"sparkinterval.measured-work-trace.goldbach-historical.initial.v1\n"
)
STEP_DOMAIN = (
    b"sparkinterval.measured-work-trace.goldbach-historical.step.v1\n"
)
MAX_HANDOFF_FILES = 1_500_000
MAX_HANDOFF_BYTES = 32 * 1024**4


class HistoricalGoldbachMeasuredWorkloadError(RuntimeError):
    """The terminal handoff, child identity, or replay failed closed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_relative(path: Path, what: str) -> Path:
    value = path.as_posix()
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise HistoricalGoldbachMeasuredWorkloadError(
            f"{what} must be a canonical relative path"
        )
    return Path(*relative.parts)


def _hex(value: Any, what: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise HistoricalGoldbachMeasuredWorkloadError(
            f"{what} must be lowercase SHA-256 hex"
        )
    return value


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as error:
        raise HistoricalGoldbachMeasuredWorkloadError(
            f"cannot read {what}: {error}"
        ) from error


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
                raise HistoricalGoldbachMeasuredWorkloadError(
                    f"short write: {path}"
                )
            view = view[count:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _branch_digest(summary: Mapping[str, Any], prefix: str) -> str:
    fields = sorted(
        [key, value]
        for key, value in summary.items()
        if key.startswith(prefix) and key not in {"kind", "schema_version"}
    )
    return _sha(canonical_json_bytes(fields))


def _trace_hash(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    handoff_sha256: str,
    commitment_sha256: str,
    summary: Mapping[str, Any],
    combined_sha256: str,
    result_sha256: str,
) -> str:
    current = _sha(
        INITIAL_DOMAIN
        + f"challenge_nonce={challenge}\n".encode("ascii")
        + f"job_binding_sha256={job_binding}\n".encode("ascii")
        + f"input_sha256={input_sha256}\n".encode("ascii")
        + f"handoff_sha256={handoff_sha256}\n".encode("ascii")
        + f"child_commitment_sha256={commitment_sha256}\n".encode("ascii")
    )
    current = _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"binary_branch_sha256={_branch_digest(summary, 'binary_')}\n".encode(
            "ascii"
        )
    )
    current = _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"ladder_branch_sha256={_branch_digest(summary, 'ladder_')}\n".encode(
            "ascii"
        )
    )
    return _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"combined_sha256={combined_sha256}\n".encode("ascii")
        + f"result_sha256={result_sha256}\n".encode("ascii")
    )


def _trace_value(
    args: argparse.Namespace,
    *,
    summary: Mapping[str, Any],
    combined_sha256: str,
) -> dict[str, Any]:
    input_sha256 = hash_file_once(args.input)[0]
    result_sha256 = hash_file_once(args.output)[0]
    handoff_sha256 = hash_file_once(args.handoff)[0]
    commitment_sha256 = hash_file_once(args.child_commitment)[0]
    return {
        "algorithm_id": args.algorithm_id,
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
            handoff_sha256=handoff_sha256,
            commitment_sha256=commitment_sha256,
            summary=summary,
            combined_sha256=combined_sha256,
            result_sha256=result_sha256,
        ),
    }


def _extract_handoff(archive: Path, destination: Path) -> Path:
    try:
        extract_archive(
            archive,
            destination,
            maximum_files=MAX_HANDOFF_FILES,
            maximum_bytes=MAX_HANDOFF_BYTES,
        )
    except (ArchiveError, OSError, ValueError) as error:
        raise HistoricalGoldbachMeasuredWorkloadError(
            f"cannot extract historical Goldbach handoff: {error}"
        ) from error
    return destination


def _replay(
    args: argparse.Namespace, destination: Path,
) -> tuple[dict[str, Any], str]:
    commitment, _commitment_sha256 = load_child_identity_commitment(
        args.child_commitment
    )
    admission = load_build_admission(args.build_admission)
    combined = destination.parent / "combined.json"
    report = replay_terminal_handoff(
        destination,
        child_commitment=commitment,
        key_manifest=args.key_manifest,
        admission=admission,
        combined_output=combined,
    )
    return report, hash_file_once(combined)[0]


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    if args.work.exists():
        raise HistoricalGoldbachMeasuredWorkloadError(
            "terminal work directory must be fresh"
        )
    args.work.mkdir(mode=0o700, parents=True)
    succeeded = False
    try:
        handoff = _extract_handoff(args.handoff, args.work / "handoff")
        report, combined_sha256 = _replay(args, handoff)
        _write_exclusive(args.output, REGISTERED_OUTPUT)
        _write_exclusive(
            args.trace,
            canonical_json_bytes(
                _trace_value(
                    args,
                    summary=report["branch_summary"],
                    combined_sha256=combined_sha256,
                )
            ),
        )
        succeeded = True
    finally:
        if not succeeded:
            shutil.rmtree(args.work, ignore_errors=True)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    if _read(args.output, 16, "registered result") != REGISTERED_OUTPUT:
        raise HistoricalGoldbachMeasuredWorkloadError(
            "registered result is not literal true"
        )
    temporary = Path(
        tempfile.mkdtemp(prefix=".historical-goldbach-terminal-trace-")
    )
    try:
        handoff = _extract_handoff(args.handoff, temporary / "handoff")
        report, combined_sha256 = _replay(args, handoff)
        expected = _trace_value(
            args,
            summary=report["branch_summary"],
            combined_sha256=combined_sha256,
        )
        try:
            actual = json_load(args.trace)
        except (CampaignIOError, OSError, ValueError) as error:
            raise HistoricalGoldbachMeasuredWorkloadError(
                f"cannot load terminal trace: {error}"
            ) from error
        if actual != expected:
            raise HistoricalGoldbachMeasuredWorkloadError(
                "terminal challenge trace differs from independent replay"
            )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def json_load(path: Path) -> Any:
    from tg_verifier.campaign_io import load_json

    return load_json(path, require_canonical=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--handoff", type=Path, required=True)
    result.add_argument("--child-commitment", type=Path, required=True)
    result.add_argument("--build-admission", type=Path, required=True)
    result.add_argument("--key-manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    return result


def _validate_args(args: argparse.Namespace) -> None:
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        raise HistoricalGoldbachMeasuredWorkloadError(
            "terminal algorithm identity differs"
        )
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    for name in (
        "input",
        "handoff",
        "child_commitment",
        "build_admission",
        "key_manifest",
        "output",
        "trace",
        "work",
    ):
        setattr(args, name, _safe_relative(getattr(args, name), name))
    if _read(args.input, 4096, "registered input") != REGISTERED_INPUT:
        raise HistoricalGoldbachMeasuredWorkloadError(
            "terminal registered input differs"
        )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        require_azure_measured_worker(
            challenge_nonce=args.challenge,
            job_binding=args.job_binding,
        )
        _validate_args(args)
        if args.mode == "run":
            run(args)
        else:
            verify_trace(args)
        return 0
    except (
        ArchiveError,
        CampaignIOError,
        GoldbachBuildAdmissionError,
        HistoricalGoldbachMeasuredWorkloadError,
        HistoricalGoldbachTerminalError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"historical Goldbach measured workload error: {error}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
