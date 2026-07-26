#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fresh, source-scale measured worker for Ramaré--Zúñiga Lemma 6.2.

The worker has no resume/import argument.  Its fixed work directory must not
exist when the measured command starts, so a caller cannot smuggle a merely
structural historical prefix into a successful run.  Every bounded CUDA
receipt is produced after the challenge-dependent job begins, then the full
chain and its registered result are replayed before a canonical retained
archive and work trace are emitted.

The independent trace verifier rechecks the complete retained chain, exact
runner/source identities, and every factor-support and directed-arithmetic row
with a separately built CPU executable.  It does not prove that the resulting
integer recurrence refines the Lean definitions; that remains an explicit
proof-boundary obligation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "attestation"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from tg_verifier.azure_h100_r2star_workload_factory import (  # noqa: E402
    REGISTERED_ALGORITHM_ID,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT,
    registered_identity,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    require_azure_measured_worker,
)
from tg_verifier.r2star import R2STAR_SOURCE_LIMIT  # noqa: E402
from tg_verifier.r2star_campaign import (  # noqa: E402
    DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS,
    R2StarCampaignError,
    run_campaign,
    verify_campaign_arithmetic,
    write_registered_result,
)


TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 2
EXPORT_KIND = "sparkinterval.azure.r2star-retained-export.v1"
SOURCE_CLOSURE_KIND = "sparkinterval.r2star-h100-source-closure.v1"
ARITHMETIC_REPLAY_EVIDENCE_KIND = (
    "sparkinterval.r2star-independent-arithmetic-replay.v1"
)
ARITHMETIC_REPLAY_EVIDENCE_NAME = "independent-arithmetic-replay.json"
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.r2star.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.r2star.step.v1\n"
TREE_DOMAIN = b"sparkinterval/r2star-retained-tree/v1\0"
FIXED_WORK = Path("work/r2star-source-scale")
FIXED_PYTHON = Path("artifacts/python3")
FIXED_RUNNER = Path("artifacts/r2star-h100")
FIXED_ARITHMETIC_REPLAYER = Path("artifacts/r2star-arithmetic-replay")
FIXED_SOURCE_CLOSURE = Path("source/source-closure.json")
ARITHMETIC_REPLAY_THREADS = 32
ARITHMETIC_REPLAY_SEGMENT_ROWS = (
    DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS
)
ARCHIVE_NAME = "r2star-full-source.tar"
EXPECTED_RECEIPTS = 21_000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 22_100
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class R2StarAzureMeasuredWorkloadError(RuntimeError):
    """The fresh execution, retained export, or replay failed closed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hex(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise R2StarAzureMeasuredWorkloadError(
            f"{what} must be lowercase SHA-256 hex"
        )
    return value


def _safe_relative(value: Path, what: str) -> Path:
    text = value.as_posix()
    path = PurePosixPath(text)
    if (
        not text
        or path.is_absolute()
        or text != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise R2StarAzureMeasuredWorkloadError(
            f"{what} must be a safe relative path"
        )
    return Path(*path.parts)


def _require_fixed_executable(path: Path, what: str) -> None:
    try:
        metadata = path.stat()
    except OSError as error:
        raise R2StarAzureMeasuredWorkloadError(
            f"cannot inspect fixed {what}: {error}"
        ) from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not os.access(path, os.X_OK)
    ):
        raise R2StarAzureMeasuredWorkloadError(
            f"fixed {what} must be one executable, non-linked regular file"
        )


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
                raise R2StarAzureMeasuredWorkloadError(f"short write: {path}")
            view = view[count:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _tree_rows(root: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise R2StarAzureMeasuredWorkloadError(
                f"retained export contains a linked or special file: {relative}"
            )
        if relative == "export-manifest.json":
            continue
        digest, size = hash_file_once(path)
        rows.append({"path": relative, "sha256": digest, "size_bytes": size})
        total += size
    return rows, total


def _tree_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(TREE_DOMAIN)
    for row in rows:
        encoded = row["path"].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(row["size_bytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(row["sha256"]))
    return digest.hexdigest()


def _source_identity() -> dict[str, Any]:
    value = load_json(FIXED_SOURCE_CLOSURE, require_canonical=True)
    if (
        not isinstance(value, dict)
        or value.get("kind") != SOURCE_CLOSURE_KIND
        or value.get("schema_version") != 1
        or set(value)
        != {
            "build",
            "files",
            "kind",
            "runtime",
            "schema_version",
        }
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star source closure has the wrong exact shape"
        )
    runtime = value.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {
        "arithmetic_replayer",
        "dynamic_runtime_boundary",
        "python",
        "runner",
    }:
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star runtime closure has the wrong exact shape"
        )
    python = runtime.get("python")
    if (
        not isinstance(python, dict)
        or set(python) != {"path", "sha256", "size_bytes"}
        or python.get("path") != FIXED_PYTHON.as_posix()
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star source closure does not name the fixed Python runtime"
        )
    runner = runtime.get("runner")
    if (
        not isinstance(runner, dict)
        or set(runner) != {"path", "sha256", "size_bytes"}
        or runner.get("path") != FIXED_RUNNER.as_posix()
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star source closure does not name the fixed runner"
        )
    arithmetic_replayer = runtime.get("arithmetic_replayer")
    if (
        not isinstance(arithmetic_replayer, dict)
        or set(arithmetic_replayer) != {"path", "sha256", "size_bytes"}
        or arithmetic_replayer.get("path")
        != FIXED_ARITHMETIC_REPLAYER.as_posix()
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star source closure does not name the fixed arithmetic replayer"
        )
    actual_sha, actual_size = hash_file_once(FIXED_RUNNER)
    if (runner.get("sha256"), runner.get("size_bytes")) != (
        actual_sha,
        actual_size,
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star runner differs from the source-closure manifest"
        )
    replay_sha, replay_size = hash_file_once(FIXED_ARITHMETIC_REPLAYER)
    if (
        arithmetic_replayer.get("sha256"),
        arithmetic_replayer.get("size_bytes"),
    ) != (replay_sha, replay_size):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star arithmetic replayer differs from the source-closure manifest"
        )
    _require_fixed_executable(FIXED_RUNNER, "R2Star runner")
    _require_fixed_executable(
        FIXED_ARITHMETIC_REPLAYER, "R2Star arithmetic replayer"
    )
    python_sha, python_size = hash_file_once(FIXED_PYTHON)
    if (python.get("sha256"), python.get("size_bytes")) != (
        python_sha,
        python_size,
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star Python runtime differs from the source-closure manifest"
        )
    _require_fixed_executable(FIXED_PYTHON, "Python runtime")
    running_python_sha, running_python_size = hash_file_once(
        Path(sys.executable).resolve()
    )
    if (running_python_sha, running_python_size) != (
        python_sha,
        python_size,
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "measured worker is not running under the fixed Python runtime"
        )
    source_sha, source_size = hash_file_once(FIXED_SOURCE_CLOSURE)
    return {
        "arithmetic_replayer_sha256": replay_sha,
        "arithmetic_replayer_size_bytes": replay_size,
        "python_sha256": python_sha,
        "python_size_bytes": python_size,
        "runner_sha256": actual_sha,
        "runner_size_bytes": actual_size,
        "source_closure_sha256": source_sha,
        "source_closure_size_bytes": source_size,
    }


def _validate_input(args: argparse.Namespace) -> dict[str, Any]:
    identity = registered_identity()
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        raise R2StarAzureMeasuredWorkloadError("algorithm identity differs")
    if args.input.read_bytes() != REGISTERED_INPUT:
        raise R2StarAzureMeasuredWorkloadError(
            "measured input is not the exact registered source range"
        )
    if hash_file_once(args.input)[0] != identity["input_hash"]:
        raise R2StarAzureMeasuredWorkloadError("registered input hash differs")
    return _source_identity()


def _check_complete(
    result: Any,
    *,
    require_independent_rows: bool = True,
    expected_arithmetic_replayer_sha256: str | None = None,
) -> None:
    if (
        result.endpoint != R2STAR_SOURCE_LIMIT
        or result.completed_upper != R2STAR_SOURCE_LIMIT
        or result.complete is not True
        or result.receipts != EXPECTED_RECEIPTS
        or result.final_record_hash == "0" * 64
        or result.minimum_squared_slack is None
        or result.minimum_slack_index is None
        or (
            require_independent_rows
            and getattr(result, "independent_rows_replayed", False) is not True
        )
        or (
            expected_arithmetic_replayer_sha256 is not None
            and getattr(result, "arithmetic_replayer_sha256", None)
            != expected_arithmetic_replayer_sha256
        )
    ):
        raise R2StarAzureMeasuredWorkloadError(
            "R2Star campaign is not the exact complete 21-billion-row chain"
        )


def _arithmetic_replay_evidence(
    result: Any, source_identity: Mapping[str, Any]
) -> dict[str, Any]:
    _check_complete(
        result,
        expected_arithmetic_replayer_sha256=source_identity[
            "arithmetic_replayer_sha256"
        ],
    )
    return {
        "arithmetic_replayer_sha256": result.arithmetic_replayer_sha256,
        "arithmetic_replay_segment_rows": (
            ARITHMETIC_REPLAY_SEGMENT_ROWS
        ),
        "arithmetic_replay_threads": ARITHMETIC_REPLAY_THREADS,
        "checked_rows": result.completed_upper,
        "final_record_hash": result.final_record_hash,
        "kind": ARITHMETIC_REPLAY_EVIDENCE_KIND,
        "minimum_slack_index": result.minimum_slack_index,
        "minimum_squared_slack": result.minimum_squared_slack,
        "receipt_count": result.receipts,
        "schema_version": 1,
        "status": "PASS",
    }


def _write_export_manifest(
    root: Path, source_identity: Mapping[str, Any]
) -> dict[str, Any]:
    rows, total = _tree_rows(root)
    manifest = {
        "file_count": len(rows),
        "kind": EXPORT_KIND,
        "receipt_count": EXPECTED_RECEIPTS,
        "arithmetic_replayer_sha256": source_identity[
            "arithmetic_replayer_sha256"
        ],
        "runner_sha256": source_identity["runner_sha256"],
        "schema_version": 1,
        "source_closure_sha256": source_identity["source_closure_sha256"],
        "source_upper_inclusive": R2STAR_SOURCE_LIMIT,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
        "workspace_origin": "fresh_inside_challenge_bound_measured_job",
    }
    _write_exclusive(root / "export-manifest.json", canonical_json_bytes(manifest))
    return manifest


def _validate_export(
    root: Path, source_identity: Mapping[str, Any]
) -> dict[str, Any]:
    value = load_json(root / "export-manifest.json", require_canonical=True)
    rows, total = _tree_rows(root)
    expected = {
        "file_count": len(rows),
        "kind": EXPORT_KIND,
        "receipt_count": EXPECTED_RECEIPTS,
        "arithmetic_replayer_sha256": source_identity[
            "arithmetic_replayer_sha256"
        ],
        "runner_sha256": source_identity["runner_sha256"],
        "schema_version": 1,
        "source_closure_sha256": source_identity["source_closure_sha256"],
        "source_upper_inclusive": R2STAR_SOURCE_LIMIT,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
        "workspace_origin": "fresh_inside_challenge_bound_measured_job",
    }
    if value != expected:
        raise R2StarAzureMeasuredWorkloadError(
            "retained R2Star export manifest/tree identity differs"
        )
    return expected


def _archive_path() -> Path:
    return FIXED_WORK / ARCHIVE_NAME


def _trace_hash(
    args: argparse.Namespace,
    *,
    source_identity: Mapping[str, Any],
    retained_sha256: str,
    tree_sha256: str,
    result_sha256: str,
) -> str:
    current = _sha(
        INITIAL_DOMAIN
        + f"algorithm_id={args.algorithm_id}\n".encode("ascii")
        + f"challenge_nonce={args.challenge}\n".encode("ascii")
        + f"job_binding_sha256={args.job_binding}\n".encode("ascii")
        + f"input_sha256={hash_file_once(args.input)[0]}\n".encode("ascii")
        + (
            "arithmetic_replayer_sha256="
            f"{source_identity['arithmetic_replayer_sha256']}\n"
        ).encode("ascii")
        + f"python_sha256={source_identity['python_sha256']}\n".encode("ascii")
        + f"runner_sha256={source_identity['runner_sha256']}\n".encode("ascii")
        + (
            "source_closure_sha256="
            f"{source_identity['source_closure_sha256']}\n"
        ).encode("ascii")
    )
    current = _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"retained_archive_sha256={retained_sha256}\n".encode("ascii")
        + f"retained_tree_sha256={tree_sha256}\n".encode("ascii")
    )
    return _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"registered_result_sha256={result_sha256}\n".encode("ascii")
    )


def _trace_value(
    args: argparse.Namespace,
    *,
    source_identity: Mapping[str, Any],
    retained_sha256: str,
    tree_sha256: str,
) -> dict[str, Any]:
    result_sha256 = hash_file_once(args.output)[0]
    return {
        "algorithm_id": args.algorithm_id,
        "challenge_nonce": args.challenge,
        "input_sha256": hash_file_once(args.input)[0],
        "iteration_count": TRACE_ITERATIONS,
        "job_binding_sha256": args.job_binding,
        "kind": TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
        "trace_sha256": _trace_hash(
            args,
            source_identity=source_identity,
            retained_sha256=retained_sha256,
            tree_sha256=tree_sha256,
            result_sha256=result_sha256,
        ),
    }


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    _validate_path_separation(args)
    source_identity = _validate_input(args)
    if FIXED_WORK.exists() or FIXED_WORK.is_symlink():
        raise R2StarAzureMeasuredWorkloadError(
            "fresh R2Star work directory already exists; resume/import is forbidden"
        )
    retained = FIXED_WORK / "retained"
    campaign = retained / "payload/campaign"
    succeeded = False
    try:
        result = run_campaign(
            runner=FIXED_RUNNER,
            output_directory=campaign,
            segment_count=1_000_000,
            device=0,
            allow_other_device=False,
            cross_check_serial=False,
            max_chunks=None,
            chunk_timeout_seconds=900,
        )
        _check_complete(result, require_independent_rows=False)
        checked, _artifact = write_registered_result(
            campaign,
            args.output,
            arithmetic_replayer=FIXED_ARITHMETIC_REPLAYER,
            expected_arithmetic_replayer_sha256=source_identity[
                "arithmetic_replayer_sha256"
            ],
            replay_threads=ARITHMETIC_REPLAY_THREADS,
            replay_segment_rows=ARITHMETIC_REPLAY_SEGMENT_ROWS,
        )
        _check_complete(
            checked,
            expected_arithmetic_replayer_sha256=source_identity[
                "arithmetic_replayer_sha256"
            ],
        )
        _write_exclusive(
            campaign / ARITHMETIC_REPLAY_EVIDENCE_NAME,
            canonical_json_bytes(
                _arithmetic_replay_evidence(checked, source_identity)
            ),
        )
        if args.output.read_bytes() != REGISTERED_OUTPUT:
            raise R2StarAzureMeasuredWorkloadError(
                "terminal emitted a non-registered result"
            )
        # The advisory lock is process-local scaffolding, not campaign data.
        # Removing it before archiving lets an independent read-only extraction
        # create its own lock without changing the committed tree.
        (campaign / ".r2star-campaign.lock").unlink(missing_ok=True)
        manifest = _write_export_manifest(retained, source_identity)
        archive = _archive_path()
        create_archive(retained, archive)
        retained_sha256, retained_size = hash_file_once(archive)
        if retained_size > MAX_ARCHIVE_BYTES:
            raise R2StarAzureMeasuredWorkloadError(
                "retained R2Star export is too large"
            )
        _write_exclusive(
            args.trace,
            canonical_json_bytes(
                _trace_value(
                    args,
                    source_identity=source_identity,
                    retained_sha256=retained_sha256,
                    tree_sha256=manifest["tree_sha256"],
                )
            ),
        )
        shutil.rmtree(retained)
        succeeded = True
    finally:
        if not succeeded:
            shutil.rmtree(FIXED_WORK, ignore_errors=True)
            args.output.unlink(missing_ok=True)
            args.trace.unlink(missing_ok=True)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    _validate_path_separation(args)
    source_identity = _validate_input(args)
    if args.output.read_bytes() != REGISTERED_OUTPUT:
        raise R2StarAzureMeasuredWorkloadError(
            "signed result is not the registered success bytes"
        )
    archive = _archive_path()
    retained_sha256, retained_size = hash_file_once(archive)
    if retained_size > MAX_ARCHIVE_BYTES:
        raise R2StarAzureMeasuredWorkloadError(
            "retained R2Star export is too large"
        )
    temporary = Path(tempfile.mkdtemp(prefix=".r2star-azure-replay-"))
    try:
        retained = temporary / "retained"
        extract_archive(
            archive,
            retained,
            maximum_files=MAX_ARCHIVE_MEMBERS,
            maximum_bytes=MAX_EXTRACTED_BYTES,
        )
        manifest = _validate_export(retained, source_identity)
        campaign = retained / "payload/campaign"
        checked = verify_campaign_arithmetic(
            campaign,
            arithmetic_replayer=FIXED_ARITHMETIC_REPLAYER,
            expected_arithmetic_replayer_sha256=source_identity[
                "arithmetic_replayer_sha256"
            ],
            replay_threads=ARITHMETIC_REPLAY_THREADS,
            replay_segment_rows=ARITHMETIC_REPLAY_SEGMENT_ROWS,
        )
        _check_complete(
            checked,
            expected_arithmetic_replayer_sha256=source_identity[
                "arithmetic_replayer_sha256"
            ],
        )
        replay_evidence = load_json(
            campaign / ARITHMETIC_REPLAY_EVIDENCE_NAME,
            require_canonical=True,
        )
        if replay_evidence != _arithmetic_replay_evidence(
            checked, source_identity
        ):
            raise R2StarAzureMeasuredWorkloadError(
                "retained R2Star arithmetic-replay evidence differs"
            )
        expected_trace = _trace_value(
            args,
            source_identity=source_identity,
            retained_sha256=retained_sha256,
            tree_sha256=manifest["tree_sha256"],
        )
        actual_trace = load_json(args.trace, require_canonical=True)
        if actual_trace != expected_trace:
            raise R2StarAzureMeasuredWorkloadError(
                "challenge-dependent R2Star trace differs"
            )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    return result


def _validate_path_separation(args: argparse.Namespace) -> None:
    paths = {
        "input": args.input,
        "output": args.output,
        "trace": args.trace,
    }
    if len(set(paths.values())) != len(paths):
        raise R2StarAzureMeasuredWorkloadError(
            "input, output, and trace paths must be distinct"
        )
    fixed = {
        FIXED_ARITHMETIC_REPLAYER,
        FIXED_PYTHON,
        FIXED_RUNNER,
        FIXED_SOURCE_CLOSURE,
    }
    for name, path in paths.items():
        if _safe_relative(path, name) != path:
            raise R2StarAzureMeasuredWorkloadError(
                f"{name} path is not in canonical relative form"
            )
        if path in fixed or path == FIXED_WORK or FIXED_WORK in path.parents:
            raise R2StarAzureMeasuredWorkloadError(
                f"{name} path overlaps a fixed runtime or retained-work path"
            )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        require_azure_measured_worker(
            challenge_nonce=args.challenge,
            job_binding=args.job_binding,
        )
        _hex(args.challenge, "challenge")
        _hex(args.job_binding, "job binding")
        for name in ("input", "output", "trace"):
            setattr(args, name, _safe_relative(getattr(args, name), name))
        if args.mode == "run":
            run(args)
        else:
            verify_trace(args)
        return 0
    except (
        ArchiveError,
        CampaignIOError,
        OSError,
        R2StarAzureMeasuredWorkloadError,
        R2StarCampaignError,
        ValueError,
    ) as error:
        print(f"R2Star Azure measured workload error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
