#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Measured H100 worker for eight lowered finite-Goldbach checkpoint leaves."""

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
from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (  # noqa: E402
    PHASE_ID,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    require_azure_measured_worker,
)
from tg_verifier.goldbach_gpu_campaign import (  # noqa: E402
    ANALYTIC_10POW27_ALGORITHM,
    ANALYTIC_10POW27_EVEN_LIMIT,
    ANALYTIC_10POW27_EVEN_START,
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
    GoldbachGPUCampaignError,
    PRODUCTION_GROUPS,
    load_plan,
    load_receipt,
    production_group_leaf_indices,
    run_group,
    verify_executable,
    verify_hardened_source_tree,
)
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GOLDBACH_H100_ALGORITHM_PREFIX,
    GoldbachBuildAdmissionError,
    verify_runtime_identity,
    verify_runtime_image_closure,
)


TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 2
EXPORT_KIND = "sparkinterval.azure.goldbach10pow27-retained-export.v1"
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.goldbach10pow27.h100.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.goldbach10pow27.h100.step.v1\n"
TREE_DOMAIN = b"sparkinterval/goldbach10pow27-retained-tree/v1\0"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


class H100GoldbachMeasuredWorkloadError(RuntimeError):
    """The exact group, result, trace, or retained export failed closed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hex(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise H100GoldbachMeasuredWorkloadError(
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
        raise H100GoldbachMeasuredWorkloadError(
            f"{what} must be a safe relative path"
        )
    return Path(*path.parts)


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
                raise H100GoldbachMeasuredWorkloadError(f"short write: {path}")
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
            raise H100GoldbachMeasuredWorkloadError(
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


def _write_export_manifest(
    root: Path, group_index: int,
) -> dict[str, Any]:
    rows, total = _tree_rows(root)
    manifest = {
        "file_count": len(rows),
        "group_index": group_index,
        "kind": EXPORT_KIND,
        "phase": PHASE_ID,
        "schema_version": 1,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
    }
    _write_exclusive(root / "export-manifest.json", canonical_json_bytes(manifest))
    return manifest


def _validate_export(root: Path, group_index: int) -> dict[str, Any]:
    value = load_json(root / "export-manifest.json", require_canonical=True)
    rows, total = _tree_rows(root)
    expected = {
        "file_count": len(rows),
        "group_index": group_index,
        "kind": EXPORT_KIND,
        "phase": PHASE_ID,
        "schema_version": 1,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
    }
    if value != expected:
        raise H100GoldbachMeasuredWorkloadError(
            "retained export manifest/tree identity differs"
        )
    return expected


def _runtime_identity(args: argparse.Namespace) -> dict[str, Any]:
    value = load_json(args.build_identity, require_canonical=True)
    identity = verify_runtime_identity(value)
    core = identity["core"]
    if hash_file_once(args.executable) != (
        core["executable"]["sha256"],
        core["executable"]["size_bytes"],
    ):
        raise H100GoldbachMeasuredWorkloadError(
            "runtime executable differs from the admitted build identity"
        )
    if (
        verify_hardened_source_tree(args.source_root)
        != core["source_identity_sha256"]
    ):
        raise H100GoldbachMeasuredWorkloadError(
            "runtime source differs from the admitted build identity"
        )
    return identity


def _runtime_image_closure(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    value = load_json(args.runtime_image_closure, require_canonical=True)
    checked = verify_runtime_image_closure(value)
    digest, _size = hash_file_once(args.runtime_image_closure)
    return checked, digest


def _exact_plan(
    path: Path, executable: Path, source_root: Path, identity: Mapping[str, Any],
):
    plan = load_plan(path)
    core = identity["core"]
    if (
        not plan.production
        or plan.algorithm != ANALYTIC_10POW27_ALGORITHM
        or (plan.even_start, plan.even_limit)
        != (ANALYTIC_10POW27_EVEN_START, ANALYTIC_10POW27_EVEN_LIMIT)
        or verify_hardened_source_tree(source_root)
        != core["source_identity_sha256"]
        or core["source_identity_sha256"]
        != EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256
        or plan.executable_sha256 != core["executable"]["sha256"]
    ):
        raise H100GoldbachMeasuredWorkloadError(
            "plan/source is not the exact lowered production profile"
        )
    verify_executable(executable, plan.executable_sha256)
    return plan


def _validate_input(args: argparse.Namespace) -> None:
    identity = _runtime_identity(args)
    runtime_image, runtime_image_sha256 = _runtime_image_closure(args)
    value = load_json(args.input, require_canonical=True)
    fields = {
        "artifact_closure_manifest_sha256",
        "build_admission_sha256",
        "build_identity_sha256",
        "campaign_id",
        "executable_sha256",
        "group_index",
        "immutable_image_reference_sha256",
        "phase",
        "runtime_image_closure_sha256",
        "source_identity_sha256",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["campaign_id"]
        != "ternary-goldbach-finite-below-10pow27-v1"
        or value["group_index"] != args.group_index
        or value["phase"] != PHASE_ID
        or value["build_identity_sha256"]
        != identity["build_identity_sha256"]
        or value["executable_sha256"]
        != identity["core"]["executable"]["sha256"]
        or value["source_identity_sha256"]
        != identity["core"]["source_identity_sha256"]
        or value["immutable_image_reference_sha256"]
        != runtime_image["immutable_image_reference_sha256"]
        or value["runtime_image_closure_sha256"] != runtime_image_sha256
        or not isinstance(value["build_admission_sha256"], str)
        or SHA256_RE.fullmatch(value["build_admission_sha256"]) is None
        or not isinstance(value["artifact_closure_manifest_sha256"], str)
        or SHA256_RE.fullmatch(
            value["artifact_closure_manifest_sha256"]
        ) is None
    ):
        raise H100GoldbachMeasuredWorkloadError(
            "measured input is not the exact group descriptor"
        )
    if not args.algorithm_id.startswith(GOLDBACH_H100_ALGORITHM_PREFIX):
        raise H100GoldbachMeasuredWorkloadError("algorithm identity differs")


def _expected_group_result(
    plan: Any, receipts: Path, group_index: int,
) -> dict[str, Any]:
    indices = production_group_leaf_indices(plan, group_index)
    actual_names = {
        path.name for path in receipts.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    expected_names = {f"receipt-{index:08d}.json" for index in indices}
    if actual_names != expected_names:
        raise H100GoldbachMeasuredWorkloadError(
            "retained group does not contain exactly its eight receipts"
        )
    rows = []
    for index in indices:
        receipt = load_receipt(
            receipts / f"receipt-{index:08d}.json", plan=plan
        )
        rows.append(
            {
                "leaf_index": index,
                "receipt_sha256": receipt["receipt_sha256"],
                "status": "completed-new-receipt",
            }
        )
    return {
        "all_group_receipts_valid": True,
        "execution_attested": False,
        "group_index": group_index,
        "leaf_indices": list(indices),
        "lean_atom_discharged": False,
        "receipts": rows,
        "scheduler_group_count": PRODUCTION_GROUPS,
        "schema": "sparkinterval.goldbach-gpu-run-group.v1",
    }


def _trace_hash(
    args: argparse.Namespace, *, plan_sha256: str, executable_sha256: str,
    source_sha256: str, retained_sha256: str, tree_sha256: str,
    result_sha256: str,
) -> str:
    current = _sha(
        INITIAL_DOMAIN
        + f"group_index={args.group_index}\n".encode("ascii")
        + f"challenge_nonce={args.challenge}\n".encode("ascii")
        + f"job_binding_sha256={args.job_binding}\n".encode("ascii")
        + f"input_sha256={hash_file_once(args.input)[0]}\n".encode("ascii")
        + f"plan_sha256={plan_sha256}\n".encode("ascii")
        + f"executable_sha256={executable_sha256}\n".encode("ascii")
        + f"source_identity_sha256={source_sha256}\n".encode("ascii")
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
        + f"result_sha256={result_sha256}\n".encode("ascii")
    )


def _trace_value(
    args: argparse.Namespace, *, plan: Any, retained_sha256: str,
    tree_sha256: str,
) -> dict[str, Any]:
    result_sha256 = hash_file_once(args.output)[0]
    source_sha256 = verify_hardened_source_tree(args.source_root)
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
            plan_sha256=plan.plan_sha256,
            executable_sha256=plan.executable_sha256,
            source_sha256=source_sha256,
            retained_sha256=retained_sha256,
            tree_sha256=tree_sha256,
            result_sha256=result_sha256,
        ),
    }


def _archive_path(args: argparse.Namespace) -> Path:
    return args.work / f"goldbach10pow27-h100-group-{args.group_index:08d}.tar"


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    _validate_input(args)
    identity = _runtime_identity(args)
    plan = _exact_plan(
        args.plan, args.executable, args.source_root, identity
    )
    if args.work.exists():
        raise H100GoldbachMeasuredWorkloadError("work directory must be fresh")
    retained = args.work / "retained"
    receipts = retained / "payload/binary-receipts"
    receipts.mkdir(mode=0o700, parents=True)
    succeeded = False
    try:
        result = run_group(
            plan=plan,
            group_index=args.group_index,
            executable=args.executable,
            source_root=args.source_root,
            output_directory=receipts,
            cuda_visible_device=args.cuda_visible_device,
            timeout_seconds=9_000,
        )
        expected = _expected_group_result(plan, receipts, args.group_index)
        if result != expected:
            raise H100GoldbachMeasuredWorkloadError(
                "producer group result differs from independent receipt replay"
            )
        _write_exclusive(args.output, canonical_json_bytes(expected))
        manifest = _write_export_manifest(retained, args.group_index)
        archive = _archive_path(args)
        create_archive(retained, archive)
        retained_sha256, retained_size = hash_file_once(archive)
        if retained_size > MAX_ARCHIVE_BYTES:
            raise H100GoldbachMeasuredWorkloadError("retained export is too large")
        _write_exclusive(
            args.trace,
            canonical_json_bytes(
                _trace_value(
                    args,
                    plan=plan,
                    retained_sha256=retained_sha256,
                    tree_sha256=manifest["tree_sha256"],
                )
            ),
        )
        shutil.rmtree(retained)
        succeeded = True
    finally:
        if not succeeded:
            shutil.rmtree(args.work, ignore_errors=True)
            args.output.unlink(missing_ok=True)
            args.trace.unlink(missing_ok=True)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    _validate_input(args)
    identity = _runtime_identity(args)
    plan = _exact_plan(
        args.plan, args.executable, args.source_root, identity
    )
    archive = _archive_path(args)
    retained_sha256, retained_size = hash_file_once(archive)
    if retained_size > MAX_ARCHIVE_BYTES:
        raise H100GoldbachMeasuredWorkloadError("retained export is too large")
    temporary = Path(tempfile.mkdtemp(prefix=".goldbach10pow27-h100-replay-"))
    try:
        root = temporary / "retained"
        extract_archive(
            archive, root, maximum_files=16, maximum_bytes=MAX_ARCHIVE_BYTES
        )
        manifest = _validate_export(root, args.group_index)
        expected_result = _expected_group_result(
            plan, root / "payload/binary-receipts", args.group_index
        )
        result = load_json(args.output, require_canonical=True)
        if result != expected_result:
            raise H100GoldbachMeasuredWorkloadError(
                "signed group result differs from retained receipts"
            )
        expected_trace = _trace_value(
            args,
            plan=plan,
            retained_sha256=retained_sha256,
            tree_sha256=manifest["tree_sha256"],
        )
        actual_trace = load_json(args.trace, require_canonical=True)
        if actual_trace != expected_trace:
            raise H100GoldbachMeasuredWorkloadError(
                "challenge-dependent group trace differs"
            )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--group-index", type=int, required=True)
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    result.add_argument("--plan", type=Path, required=True)
    result.add_argument("--build-identity", type=Path, required=True)
    result.add_argument("--runtime-image-closure", type=Path, required=True)
    result.add_argument("--source-root", type=Path, required=True)
    result.add_argument("--executable", type=Path, required=True)
    result.add_argument("--cuda-visible-device", type=int, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        require_azure_measured_worker(
            challenge_nonce=args.challenge,
            job_binding=args.job_binding,
        )
        _hex(args.challenge, "challenge")
        _hex(args.job_binding, "job binding")
        if not 0 <= args.group_index < PRODUCTION_GROUPS:
            raise H100GoldbachMeasuredWorkloadError("group index is outside the plan")
        if args.cuda_visible_device != 0:
            raise H100GoldbachMeasuredWorkloadError("only CUDA device zero is reviewed")
        for name in (
            "input", "output", "trace", "work", "plan", "build_identity",
            "runtime_image_closure", "source_root", "executable"
        ):
            setattr(args, name, _safe_relative(getattr(args, name), name))
        if args.mode == "run":
            run(args)
        else:
            verify_trace(args)
        return 0
    except (
        ArchiveError,
        CampaignIOError,
        GoldbachGPUCampaignError,
        GoldbachBuildAdmissionError,
        H100GoldbachMeasuredWorkloadError,
        OSError,
        ValueError,
    ) as error:
        print(f"Goldbach 10^27 H100 measured workload error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
