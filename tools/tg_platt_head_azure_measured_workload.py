#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed measured workload for the complete Platt zeta head through 20,000."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "attestation"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
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
from tg_verifier.zeta_zero_campaign import (  # noqa: E402
    PLATT_HEAD_2E4,
    PLATT_HEAD_ALL_Q128_ROWS_SHA256,
    PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256,
    ZetaCampaignError,
    canonical_json_bytes,
    finalize_campaign,
    initialize_campaign,
    load_plan,
    render_head_q128_lean_module,
    replay_chunk,
    replay_plan_count,
    retained_head_q128_cells,
    run_campaign,
    verify_campaign,
)


REGISTERED_ALGORITHM_ID = "sparkinterval.ternary-goldbach.platt-head-2e4.v1"
REGISTERED_INPUT = (
    b'{"all_q128_rows_sha256":"fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca",'
    b'"campaign":"platt-head-2e4",'
    b'"included_q128_rows_sha256":"e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7",'
    b'"source_height":20000,"source_multiplicity_count":22491}'
)
REGISTERED_RESULT = b"true"
TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 3
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.platt-head-2e4.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.platt-head-2e4.step.v1\n"
RETAINED_KIND = "sparkinterval.azure.platt-head-retained.v1"
MAX_RETAINED_FILES = 32
MAX_RETAINED_BYTES = 256 * 1024 * 1024


class PlattHeadMeasuredWorkloadError(RuntimeError):
    pass


def _safe_relative(value: str, what: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise PlattHeadMeasuredWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _hex(value: str, what: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise PlattHeadMeasuredWorkloadError(f"{what} is not lowercase SHA-256 hex")
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
                raise PlattHeadMeasuredWorkloadError("short exclusive output write")
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
        raise PlattHeadMeasuredWorkloadError(f"cannot read {what}: {error}") from error
    if len(raw) > maximum:
        raise PlattHeadMeasuredWorkloadError(f"{what} exceeds its byte limit")
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


def _tree(root: Path, *, exclude_manifest: bool) -> tuple[int, int, str]:
    digest = hashlib.sha256(b"sparkinterval/platt-head-retained-tree/v1\0")
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir() or (exclude_manifest and relative == "retained-manifest.json"):
            continue
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PlattHeadMeasuredWorkloadError("retained tree contains a linked/special file")
        file_hash, size = hash_file_once(path)
        encoded = relative.encode("utf-8")
        count += 1
        total += size
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(file_hash))
    return count, total, digest.hexdigest()


def _load_canonical(path: Path, what: str) -> dict[str, Any]:
    raw = _read(path, 8 * 1024 * 1024, what)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlattHeadMeasuredWorkloadError(f"{what} is not JSON") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise PlattHeadMeasuredWorkloadError(f"{what} is not canonical JSON")
    return value


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
            raise PlattHeadMeasuredWorkloadError("loaded python-flint/FLINT version differs")
    except (ImportError, AttributeError, OSError, ValueError) as error:
        raise PlattHeadMeasuredWorkloadError(f"cannot load pinned python-flint runtime: {error}") from error
    return identity


def _write_retained_manifest(
    retained: Path,
    *, table_sha256: str,
    table_size: int,
    final_sha256: str,
    replay_rows: list[dict[str, Any]],
    wheel_sha256: str,
) -> dict[str, Any]:
    count, total, tree = _tree(retained, exclude_manifest=True)
    value = {
        "all_q128_row_count": 22_492,
        "all_q128_rows_sha256": PLATT_HEAD_ALL_Q128_ROWS_SHA256,
        "campaign_final_sha256": final_sha256,
        "file_count": count,
        "included_q128_row_count": 22_491,
        "included_q128_rows_sha256": PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256,
        "kind": RETAINED_KIND,
        "python_flint_wheel_sha256": wheel_sha256,
        "replay_chunks": replay_rows,
        "schema_version": 1,
        "table_sha256": table_sha256,
        "table_size_bytes": table_size,
        "total_bytes": total,
        "tree_sha256": tree,
    }
    _write_exclusive(retained / "retained-manifest.json", canonical_json_bytes(value))
    return value


def _validate_retained(retained: Path, wheel_sha256: str) -> dict[str, Any]:
    value = _load_canonical(retained / "retained-manifest.json", "retained manifest")
    fields = {
        "all_q128_row_count",
        "all_q128_rows_sha256",
        "campaign_final_sha256",
        "file_count",
        "included_q128_row_count",
        "included_q128_rows_sha256",
        "kind",
        "python_flint_wheel_sha256",
        "replay_chunks",
        "schema_version",
        "table_sha256",
        "table_size_bytes",
        "total_bytes",
        "tree_sha256",
    }
    count, total, tree = _tree(retained, exclude_manifest=True)
    if (
        set(value) != fields
        or value["kind"] != RETAINED_KIND
        or value["schema_version"] != 1
        or value["all_q128_row_count"] != 22_492
        or value["included_q128_row_count"] != 22_491
        or value["all_q128_rows_sha256"] != PLATT_HEAD_ALL_Q128_ROWS_SHA256
        or value["included_q128_rows_sha256"] != PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256
        or value["python_flint_wheel_sha256"] != wheel_sha256
        or value["file_count"] != count
        or value["total_bytes"] != total
        or value["tree_sha256"] != tree
    ):
        raise PlattHeadMeasuredWorkloadError("retained Platt-head manifest differs")
    table = retained / "PlattHeadQ128.lean"
    if hash_file_once(table) != (value["table_sha256"], value["table_size_bytes"]):
        raise PlattHeadMeasuredWorkloadError("literal Lean table differs from retained pin")
    final = retained / "campaign/final.json"
    if hash_file_once(final)[0] != value["campaign_final_sha256"]:
        raise PlattHeadMeasuredWorkloadError("campaign final differs from retained pin")
    if not isinstance(value["replay_chunks"], list) or len(value["replay_chunks"]) != 6:
        raise PlattHeadMeasuredWorkloadError("retained replay list is incomplete")
    return value


def _trace_hash(
    *, challenge: str, job_binding: str, input_sha256: str, wheel_sha256: str,
    retained_sha256: str, retained_tree_sha256: str, table_sha256: str,
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
        + f"retained_archive_sha256={retained_sha256}\n".encode("ascii")
        + f"retained_tree_sha256={retained_tree_sha256}\n".encode("ascii")
        + f"literal_table_sha256={table_sha256}\n".encode("ascii")
    ).hexdigest()
    return hashlib.sha256(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"result_sha256={result_sha256}\n".encode("ascii")
    ).hexdigest()


def _write_trace(
    args: argparse.Namespace,
    *, input_sha256: str, wheel_sha256: str, retained_sha256: str,
    retained_tree_sha256: str, table_sha256: str, result_sha256: str,
) -> None:
    value = {
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
            retained_sha256=retained_sha256,
            retained_tree_sha256=retained_tree_sha256,
            table_sha256=table_sha256,
            result_sha256=result_sha256,
        ),
    }
    _write_exclusive(args.trace, canonical_json_bytes(value))


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    if _read(args.input, len(REGISTERED_INPUT), "registered input") != REGISTERED_INPUT:
        raise PlattHeadMeasuredWorkloadError("registered Platt-head input differs")
    input_sha256, _ = hash_file_once(args.input)
    wheel_identity = verify_wheel(args.wheel)
    if args.work.exists():
        raise PlattHeadMeasuredWorkloadError("Platt-head work path must be fresh")
    args.work.mkdir(mode=0o700, parents=True)
    runtime = args.work / "python-flint-runtime"
    retained = args.work / "retained"
    campaign = retained / "campaign"
    retained.mkdir(mode=0o700)
    succeeded = False
    try:
        _activate_runtime(args.wheel, runtime)
        initialize_campaign(
            campaign,
            PLATT_HEAD_2E4,
            batch_size=4_096,
            precision_bits=96,
        )
        run_result = run_campaign(campaign, max_chunks=None, replay_count=True)
        if not run_result["complete"] or run_result["chunks_total"] != 6:
            raise PlattHeadMeasuredWorkloadError("Platt-head isolation did not complete")
        replay_rows = [replay_chunk(campaign, index) for index in range(6)]
        final = finalize_campaign(campaign)
        checked = verify_campaign(campaign, require_complete=True)
        if not checked["complete_chain"] or not checked["final_present"]:
            raise PlattHeadMeasuredWorkloadError("Platt-head final replay is incomplete")
        cells = retained_head_q128_cells(campaign)
        table_raw = render_head_q128_lean_module(cells).encode("utf-8")
        table = retained / "PlattHeadQ128.lean"
        _write_exclusive(table, table_raw)
        final_hash, _ = hash_file_once(campaign / "final.json")
        table_hash, table_size = hash_file_once(table)
        manifest = _write_retained_manifest(
            retained,
            table_sha256=table_hash,
            table_size=table_size,
            final_sha256=final_hash,
            replay_rows=replay_rows,
            wheel_sha256=wheel_identity["sha256"],
        )
        archive = args.work / "platt-head-retained.tar"
        create_archive(retained, archive)
        _write_exclusive(args.output, REGISTERED_RESULT)
        retained_hash, _ = hash_file_once(archive)
        result_hash, _ = hash_file_once(args.output)
        _write_trace(
            args,
            input_sha256=input_sha256,
            wheel_sha256=wheel_identity["sha256"],
            retained_sha256=retained_hash,
            retained_tree_sha256=manifest["tree_sha256"],
            table_sha256=table_hash,
            result_sha256=result_hash,
        )
        succeeded = True
    finally:
        # The deterministic archive is the retained artifact. Expanded native
        # libraries and campaign files would only duplicate it in the package.
        _remove_tree(runtime)
        _remove_tree(retained)
        if not succeeded:
            _remove_tree(args.work)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    if _read(args.input, len(REGISTERED_INPUT), "registered input") != REGISTERED_INPUT:
        raise PlattHeadMeasuredWorkloadError("registered Platt-head input differs")
    if _read(args.output, len(REGISTERED_RESULT), "registered result") != REGISTERED_RESULT:
        raise PlattHeadMeasuredWorkloadError("registered result is not literal true")
    input_hash, _ = hash_file_once(args.input)
    result_hash, _ = hash_file_once(args.output)
    wheel_identity = verify_wheel(args.wheel)
    archive = args.work / "platt-head-retained.tar"
    retained_hash, _ = hash_file_once(archive)
    temporary = Path(tempfile.mkdtemp(prefix=".platt-head-trace-", dir=args.trace.parent))
    try:
        runtime = temporary / "python-flint-runtime"
        _activate_runtime(args.wheel, runtime)
        retained = temporary / "retained"
        extract_archive(
            archive,
            retained,
            maximum_files=MAX_RETAINED_FILES,
            maximum_bytes=MAX_RETAINED_BYTES,
        )
        manifest = _validate_retained(retained, wheel_identity["sha256"])
        campaign = retained / "campaign"
        plan, _plan_raw, _campaign_sha256 = load_plan(campaign)
        replay_plan_count(plan)
        fresh = [replay_chunk(campaign, index) for index in range(6)]
        if fresh != manifest["replay_chunks"]:
            raise PlattHeadMeasuredWorkloadError("fresh trace replay differs from retained replay")
        checked = verify_campaign(campaign, require_complete=True)
        if not checked["complete_chain"] or not checked["final_present"]:
            raise PlattHeadMeasuredWorkloadError("trace campaign replay is incomplete")
        cells = retained_head_q128_cells(campaign)
        table_raw = render_head_q128_lean_module(cells).encode("utf-8")
        if table_raw != _read(
            retained / "PlattHeadQ128.lean",
            64 * 1024 * 1024,
            "literal Lean table",
        ):
            raise PlattHeadMeasuredWorkloadError("freshly emitted Lean table differs")
        expected = {
            "algorithm_id": REGISTERED_ALGORITHM_ID,
            "challenge_nonce": args.challenge,
            "input_sha256": input_hash,
            "iteration_count": TRACE_ITERATIONS,
            "job_binding_sha256": args.job_binding,
            "kind": TRACE_KIND,
            "result_sha256": result_hash,
            "schema_version": 1,
            "trace_sha256": _trace_hash(
                challenge=args.challenge,
                job_binding=args.job_binding,
                input_sha256=input_hash,
                wheel_sha256=wheel_identity["sha256"],
                retained_sha256=retained_hash,
                retained_tree_sha256=manifest["tree_sha256"],
                table_sha256=manifest["table_sha256"],
                result_sha256=result_hash,
            ),
        }
        if _load_canonical(args.trace, "work trace") != expected:
            raise PlattHeadMeasuredWorkloadError("Platt-head work trace differs")
    finally:
        _remove_tree(temporary)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--wheel", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    return result


def _validate_args(args: argparse.Namespace) -> None:
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        raise PlattHeadMeasuredWorkloadError("algorithm id differs from registered Platt head")
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    for name in ("input", "output", "trace", "wheel", "work"):
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
        ArchiveError,
        OSError,
        PlattHeadMeasuredWorkloadError,
        PythonFlintRuntimeError,
        ValueError,
        ZetaCampaignError,
    ) as error:
        print(f"Platt-head measured workload error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
