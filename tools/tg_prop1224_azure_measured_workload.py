#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed measured adapter for the Proposition 12.2.4 Azure phase DAG."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from tg_verifier.azure_cpu_prop1224_workload_factory import (  # noqa: E402
    CAMPAIGN_ID,
    LEAF_COUNT,
    PLAN,
    PLAN_SHA256,
    REGISTERED_ALGORITHM_ID,
    REGISTERED_INPUT,
    WORKERS_PER_GROUP,
    WORKER_GROUP_COUNT,
    leaf_indices_for_group,
    make_factory,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    read_bytes_once,
    require_azure_measured_worker,
)
from tg_verifier.prop1224_mpfr_campaign import (  # noqa: E402
    Prop1224MpfrCampaignError,
    run_mpfr_shard,
    validate_receipt,
    verify_receipts,
)
from tg_verifier.prop1224_candidate_artifact import (  # noqa: E402
    arithmetic_check as candidate_arithmetic_check,
    candidate_from_verified_report,
    decode_candidate,
    encode_candidate,
    manifest_bytes as candidate_manifest_bytes,
)


PHASES = ("mpfr-shards", "merge-and-verify")
TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_FIELDS = {
    "algorithm_id",
    "challenge_nonce",
    "input_sha256",
    "iteration_count",
    "job_binding_sha256",
    "kind",
    "result_sha256",
    "schema_version",
    "trace_sha256",
}
TRACE_ITERATIONS = 2
EXPORT_KIND = "sparkinterval.azure.prop1224-leaf-export.v1"
HANDOFF_KIND = "sparkinterval.azure.prop1224-phase-handoff.v1"
REPORT_KIND = "sparkinterval.azure.prop1224-full-merge-report.v1"
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.prop1224.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.prop1224.step.v1\n"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
# One canonical handoff, one exports/ directory entry, and one archive per
# measured worker group.
MAX_HANDOFF_FILES = WORKER_GROUP_COUNT + 2
MAX_HANDOFF_BYTES = 256 * 1024**2
MAX_EXPORT_FILES = 2_000
MAX_EXPORT_BYTES = 32 * 1024**2
MAX_REPORT_BYTES = 256 * 1024
MAX_CANDIDATE_BYTES = 2 * 1024**2
REGISTERED_RESULT = b"true"
RETAINED_ARCHIVE = Path("prop1224-retained.tar")
CANDIDATE_ARTIFACT_NAME = "prop1224-candidate-artifact.bin"
CANDIDATE_MANIFEST_NAME = "prop1224-candidate-artifact-manifest.json"


class Prop1224MeasuredWorkloadError(RuntimeError):
    """The measured input, leaf replay, aggregate, output, or trace differed."""


def _safe_relative(value: str, what: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise Prop1224MeasuredWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _hex(value: str, what: str) -> str:
    if SHA256_RE.fullmatch(value) is None:
        raise Prop1224MeasuredWorkloadError(f"{what} is not lowercase SHA-256 hex")
    return value


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as error:
        raise Prop1224MeasuredWorkloadError(f"cannot read {what}: {error}") from error


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
                raise Prop1224MeasuredWorkloadError("short exclusive output write")
            view = view[count:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _tree_rows(root: Path, *, exclude_manifest: bool) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise Prop1224MeasuredWorkloadError(
                f"retained tree contains a linked or special file: {relative}"
            )
        if exclude_manifest and relative == "export-manifest.json":
            continue
        digest, size = hash_file_once(path)
        rows.append({"path": relative, "sha256": digest, "size_bytes": size})
        total += size
    return rows, total


def _tree_digest(rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256(b"sparkinterval/prop1224-retained-tree/v1\0")
    for row in rows:
        encoded = row["path"].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(row["size_bytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(row["sha256"]))
    return digest.hexdigest()


def _write_export_manifest(root: Path, phase: str, shard_index: int) -> dict[str, Any]:
    rows, total = _tree_rows(root, exclude_manifest=False)
    manifest = {
        "file_count": len(rows),
        "kind": EXPORT_KIND,
        "phase": phase,
        "schema_version": 1,
        "shard_index": shard_index,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
    }
    _write_exclusive(root / "export-manifest.json", canonical_json_bytes(manifest))
    return manifest


def _validate_export(root: Path, phase: str, shard_index: int) -> dict[str, Any]:
    try:
        manifest = load_json(root / "export-manifest.json", require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise Prop1224MeasuredWorkloadError(
            f"invalid retained export manifest: {error}"
        ) from error
    fields = {
        "file_count", "kind", "phase", "schema_version", "shard_index",
        "total_bytes", "tree_sha256",
    }
    rows, total = _tree_rows(root, exclude_manifest=True)
    if (
        not isinstance(manifest, dict)
        or set(manifest) != fields
        or manifest["kind"] != EXPORT_KIND
        or manifest["phase"] != phase
        or manifest["schema_version"] != 1
        or manifest["shard_index"] != shard_index
        or manifest["file_count"] != len(rows)
        or manifest["total_bytes"] != total
        or manifest["tree_sha256"] != _tree_digest(rows)
    ):
        raise Prop1224MeasuredWorkloadError("retained export identity differs")
    return manifest


def _extract_export(
    archive: Path, destination: Path, phase: str, shard_index: int,
) -> dict[str, Any]:
    try:
        extract_archive(
            archive,
            destination,
            maximum_files=MAX_EXPORT_FILES,
            maximum_bytes=MAX_EXPORT_BYTES,
        )
    except ArchiveError as error:
        raise Prop1224MeasuredWorkloadError(
            f"cannot extract retained {phase} export: {error}"
        ) from error
    return _validate_export(destination, phase, shard_index)


def verify_retained_export_archive(
    archive: Path, *, phase: str, shard_index: int, tree_sha256: str,
) -> dict[str, Any]:
    """Replay one retained export before admitting it to a later phase."""

    _hex(tree_sha256, "retained tree")
    temporary = Path(tempfile.mkdtemp(prefix=".prop1224-export-audit-"))
    try:
        manifest = _extract_export(
            archive, temporary / "export", phase, shard_index
        )
        if manifest["tree_sha256"] != tree_sha256:
            raise Prop1224MeasuredWorkloadError(
                "retained export tree differs from its signed operational result"
            )
        return manifest
    finally:
        _remove_tree(temporary)


def _stable_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: receipt[key]
        for key in sorted(receipt)
        if key not in {"elapsed_milliseconds", "receipt_hash"}
    }


def _map_stable(receipts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_stable_receipt(receipt) for receipt in receipts]


def _load_leaf_receipt(root: Path, shard_index: int) -> dict[str, Any]:
    try:
        receipt = load_json(
            root / f"receipts/mpfr-shard-{shard_index:05d}.json",
            require_canonical=True,
        )
    except (CampaignIOError, OSError, ValueError) as error:
        raise Prop1224MeasuredWorkloadError(f"invalid retained leaf: {error}") from error
    if not isinstance(receipt, dict):
        raise Prop1224MeasuredWorkloadError("retained leaf receipt is not an object")
    validate_receipt(
        receipt,
        plan=PLAN,
        precision_bits=192,
        mpfr_version="4.2.1",
    )
    if receipt.get("shard_index") != shard_index:
        raise Prop1224MeasuredWorkloadError("retained leaf index differs")
    return receipt


def _run_leaf(runner: Path, shard_index: int) -> dict[str, Any]:
    receipt = run_mpfr_shard(
        runner=runner,
        plan=PLAN,
        shard_index=shard_index,
        precision_bits=192,
        mpfr_version="4.2.1",
        segment_size=250_000,
    )
    validate_receipt(
        receipt,
        plan=PLAN,
        precision_bits=192,
        mpfr_version="4.2.1",
    )
    return receipt


def _run_group(runner: Path, group_index: int) -> list[dict[str, Any]]:
    indices = leaf_indices_for_group(group_index)
    completed: list[tuple[int, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=min(WORKERS_PER_GROUP, len(indices))) as pool:
        futures = {pool.submit(_run_leaf, runner, index): index for index in indices}
        for future in as_completed(futures):
            completed.append((futures[future], future.result()))
    completed.sort(key=lambda item: item[0])
    if [index for index, _receipt in completed] != list(indices):
        raise Prop1224MeasuredWorkloadError(
            "worker group did not return every reviewed logical leaf"
        )
    return [receipt for _index, receipt in completed]


def _handoff(path: Path, extracted: Path) -> tuple[dict[str, Any], Path]:
    if extracted.exists():
        raise Prop1224MeasuredWorkloadError("handoff extraction path already exists")
    try:
        extract_archive(
            path,
            extracted,
            maximum_files=MAX_HANDOFF_FILES,
            maximum_bytes=MAX_HANDOFF_BYTES,
        )
        value = load_json(extracted / "handoff.json", require_canonical=True)
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        _remove_tree(extracted)
        raise Prop1224MeasuredWorkloadError(f"invalid phase handoff: {error}") from error
    fields = {"entries", "kind", "phase", "schema_version", "shard_index"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["kind"] != HANDOFF_KIND
        or value["phase"] != "merge-and-verify"
        or value["schema_version"] != 1
        or value["shard_index"] != 0
        or not isinstance(value["entries"], list)
        or len(value["entries"]) != WORKER_GROUP_COUNT
    ):
        _remove_tree(extracted)
        raise Prop1224MeasuredWorkloadError("phase handoff identity differs")
    expected_fields = {"group_id", "path", "sha256", "shard_index", "size_bytes"}
    for index, entry in enumerate(value["entries"]):
        if (
            not isinstance(entry, dict)
            or set(entry) != expected_fields
            or entry["group_id"] != f"{CAMPAIGN_ID}::mpfr-shards"
            or entry["shard_index"] != index
        ):
            _remove_tree(extracted)
            raise Prop1224MeasuredWorkloadError("handoff entry order/identity differs")
        relative = _safe_relative(str(entry["path"]), "handoff entry path")
        candidate = extracted / relative
        if hash_file_once(candidate) != (entry["sha256"], entry["size_bytes"]):
            _remove_tree(extracted)
            raise Prop1224MeasuredWorkloadError("handoff leaf archive differs")
    return value, extracted


def _merge_handoff(path: Path, runner: Path, scratch: Path) -> dict[str, Any]:
    handoff, root = _handoff(path, scratch / "handoff")
    receipts: list[dict[str, Any]] = []
    try:
        runner_sha256, _ = hash_file_once(runner)
        for group_index, entry in enumerate(handoff["entries"]):
            expanded = scratch / "groups" / f"group-{group_index:02d}"
            archive = root / _safe_relative(str(entry["path"]), "handoff entry path")
            _extract_export(archive, expanded, "mpfr-shards", group_index)
            for leaf_index in leaf_indices_for_group(group_index):
                receipt = _load_leaf_receipt(expanded, leaf_index)
                if receipt["runner_executable_sha256"] != runner_sha256:
                    raise Prop1224MeasuredWorkloadError(
                        "leaf executable differs from the packaged terminal runner"
                    )
                receipts.append(receipt)
            _remove_tree(expanded)
        receipts.sort(key=lambda receipt: receipt["shard_index"])
        if [receipt["shard_index"] for receipt in receipts] != list(range(LEAF_COUNT)):
            raise Prop1224MeasuredWorkloadError(
                "worker-group exports do not exactly partition the logical leaves"
            )
        verification = verify_receipts(
            receipts,
            plan=PLAN,
            precision_bits=192,
            mpfr_version="4.2.1",
        )
        if (
            verification.plan_sha256 != PLAN_SHA256
            or verification.root_state != (0,)
            or verification.final_state != (3_389_047_618,)
            or len(verification.incoming_states) != LEAF_COUNT
        ):
            raise Prop1224MeasuredWorkloadError("full fixed-plan merge differs")
        return {
            **verification.to_dict(),
            "all_fixed_plan_receipts_present": True,
            "kind": REPORT_KIND,
            "runner_executable_sha256": runner_sha256,
            "schema_version": 1,
        }
    finally:
        _remove_tree(root)


def _operational_result(
    *, shard_index: int, archive_sha256: str, archive_size: int,
    manifest: Mapping[str, Any],
) -> bytes:
    return canonical_json_bytes(
        {
            "kind": "sparkinterval.azure.prop1224-operational-result.v1",
            "phase": "mpfr-shards",
            "retained_export_sha256": archive_sha256,
            "retained_export_size_bytes": archive_size,
            "retained_tree_sha256": manifest["tree_sha256"],
            "schema_version": 1,
            "shard_index": shard_index,
        }
    ).rstrip(b"\n")


def _candidate_identity(root: Path) -> dict[str, Any]:
    artifact_path = root / CANDIDATE_ARTIFACT_NAME
    manifest_path = root / CANDIDATE_MANIFEST_NAME
    raw = _read(artifact_path, MAX_CANDIDATE_BYTES, "candidate artifact")
    certificate = decode_candidate(raw)
    if not candidate_arithmetic_check(certificate):
        raise Prop1224MeasuredWorkloadError(
            "retained candidate artifact fails its Lean arithmetic boundary"
        )
    expected_manifest = candidate_manifest_bytes(CANDIDATE_ARTIFACT_NAME, raw)
    if _read(
        manifest_path, MAX_REPORT_BYTES, "candidate artifact manifest"
    ) != expected_manifest:
        raise Prop1224MeasuredWorkloadError(
            "candidate artifact manifest differs from its exact bytes"
        )
    return {
        "manifest_path": CANDIDATE_MANIFEST_NAME,
        "manifest_sha256": hashlib.sha256(expected_manifest).hexdigest(),
        "path": CANDIDATE_ARTIFACT_NAME,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "status": "arithmetic-chain-only-not-semantic-closure",
    }


def _write_candidate_after_replay(
    root: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    certificate = candidate_from_verified_report(report, plan=PLAN)
    raw = encode_candidate(certificate)
    _write_exclusive(root / CANDIDATE_ARTIFACT_NAME, raw)
    _write_exclusive(
        root / CANDIDATE_MANIFEST_NAME,
        candidate_manifest_bytes(CANDIDATE_ARTIFACT_NAME, raw),
    )
    return _candidate_identity(root)


def _candidate_hash_bytes(candidate: Mapping[str, Any] | None) -> bytes:
    if candidate is None:
        return b"candidate_artifact=none\n"
    return (
        f"candidate_artifact_path={candidate['path']}\n"
        f"candidate_artifact_sha256={candidate['sha256']}\n"
        f"candidate_artifact_size_bytes={candidate['size_bytes']}\n"
        f"candidate_manifest_path={candidate['manifest_path']}\n"
        f"candidate_manifest_sha256={candidate['manifest_sha256']}\n"
    ).encode("ascii")


def _trace_hash(
    *, phase: str, shard_index: int, challenge: str, job_binding: str,
    input_sha256: str, archive_sha256: str, tree_sha256: str, result_sha256: str,
    candidate: Mapping[str, Any] | None,
) -> str:
    current = hashlib.sha256(
        INITIAL_DOMAIN
        + f"phase={phase}\n".encode("ascii")
        + f"shard_index={shard_index}\n".encode("ascii")
        + f"challenge_nonce={challenge}\n".encode("ascii")
        + f"job_binding_sha256={job_binding}\n".encode("ascii")
        + f"input_sha256={input_sha256}\n".encode("ascii")
    ).hexdigest()
    current = hashlib.sha256(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"retained_archive_sha256={archive_sha256}\n".encode("ascii")
        + f"retained_tree_sha256={tree_sha256}\n".encode("ascii")
        + _candidate_hash_bytes(candidate)
    ).hexdigest()
    return hashlib.sha256(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"result_sha256={result_sha256}\n".encode("ascii")
    ).hexdigest()


def _trace_value(
    args: argparse.Namespace, *, input_sha256: str, archive_sha256: str,
    tree_sha256: str, result_sha256: str,
    candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    value = {
        "algorithm_id": args.algorithm_id,
        "challenge_nonce": args.challenge,
        "input_sha256": input_sha256,
        "iteration_count": TRACE_ITERATIONS,
        "job_binding_sha256": args.job_binding,
        "kind": TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
        "trace_sha256": _trace_hash(
            phase=args.phase,
            shard_index=args.shard_index,
            challenge=args.challenge,
            job_binding=args.job_binding,
            input_sha256=input_sha256,
            archive_sha256=archive_sha256,
            tree_sha256=tree_sha256,
            result_sha256=result_sha256,
            candidate=candidate,
        ),
    }
    return value


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    factory = make_factory(args.phase, args.shard_index)
    if _read(args.input, len(factory.input_bytes), "registered input") != factory.input_bytes:
        raise Prop1224MeasuredWorkloadError("measured input differs from its factory")
    if args.work.exists():
        raise Prop1224MeasuredWorkloadError("work path must be fresh")
    retained = args.work / "retained"
    retained.mkdir(mode=0o700, parents=True)
    complete = False
    try:
        if args.phase == "mpfr-shards":
            receipts = _run_group(args.runner, args.shard_index)
            for receipt in receipts:
                _write_exclusive(
                    retained
                    / f"receipts/mpfr-shard-{receipt['shard_index']:05d}.json",
                    canonical_json_bytes(receipt),
                )
        else:
            report = _merge_handoff(args.handoff, args.runner, args.work / "merge")
            _write_exclusive(retained / "aggregate.json", canonical_json_bytes(report))
            _write_candidate_after_replay(retained, report)
        manifest = _write_export_manifest(retained, args.phase, args.shard_index)
        archive = args.work / RETAINED_ARCHIVE
        create_archive(retained, archive)
        archive_sha256, archive_size = hash_file_once(archive)
        result = (
            REGISTERED_RESULT
            if args.phase == "merge-and-verify"
            else _operational_result(
                shard_index=args.shard_index,
                archive_sha256=archive_sha256,
                archive_size=archive_size,
                manifest=manifest,
            )
        )
        _write_exclusive(args.output, result)
        input_sha256, _ = hash_file_once(args.input)
        result_sha256, _ = hash_file_once(args.output)
        candidate = (
            _candidate_identity(retained)
            if args.phase == "merge-and-verify"
            else None
        )
        trace = _trace_value(
            args,
            input_sha256=input_sha256,
            archive_sha256=archive_sha256,
            tree_sha256=manifest["tree_sha256"],
            result_sha256=result_sha256,
            candidate=candidate,
        )
        _write_exclusive(args.trace, canonical_json_bytes(trace))
        complete = True
    finally:
        _remove_tree(retained)
        _remove_tree(args.work / "merge")
        if not complete:
            _remove_tree(args.work)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    factory = make_factory(args.phase, args.shard_index)
    if _read(args.input, len(factory.input_bytes), "registered input") != factory.input_bytes:
        raise Prop1224MeasuredWorkloadError("measured input differs from its factory")
    archive = args.work / RETAINED_ARCHIVE
    archive_sha256, _ = hash_file_once(archive)
    retained = args.work / "trace-retained"
    try:
        manifest = _extract_export(
            archive, retained, args.phase, args.shard_index
        )
        if args.phase == "mpfr-shards":
            stored = [
                _load_leaf_receipt(retained, leaf_index)
                for leaf_index in leaf_indices_for_group(args.shard_index)
            ]
            fresh = _run_group(args.runner, args.shard_index)
            if _map_stable(stored) != _map_stable(fresh):
                raise Prop1224MeasuredWorkloadError(
                    "fresh directed worker-group replay differs from retained arithmetic"
                )
            result = _read(args.output, factory.output_maximum_bytes, "operational result")
            expected_result = _operational_result(
                shard_index=args.shard_index,
                archive_sha256=archive_sha256,
                archive_size=archive.stat().st_size,
                manifest=manifest,
            )
            if result != expected_result:
                raise Prop1224MeasuredWorkloadError("operational result differs")
        else:
            if _read(args.output, len(REGISTERED_RESULT), "registered result") != REGISTERED_RESULT:
                raise Prop1224MeasuredWorkloadError("registered result is not literal true")
            retained_report = _read(
                retained / "aggregate.json", MAX_REPORT_BYTES, "aggregate report"
            )
            fresh_report_value = _merge_handoff(
                args.handoff, args.runner, args.work / "trace-merge"
            )
            fresh_report = canonical_json_bytes(fresh_report_value)
            if retained_report != fresh_report:
                raise Prop1224MeasuredWorkloadError("fresh full merge differs")
            expected_candidate = encode_candidate(
                candidate_from_verified_report(fresh_report_value, plan=PLAN)
            )
            retained_candidate = _read(
                retained / CANDIDATE_ARTIFACT_NAME,
                MAX_CANDIDATE_BYTES,
                "candidate artifact",
            )
            if retained_candidate != expected_candidate:
                raise Prop1224MeasuredWorkloadError(
                    "candidate artifact differs from the freshly replayed fixed plan"
                )
        input_sha256, _ = hash_file_once(args.input)
        result_sha256, _ = hash_file_once(args.output)
        candidate = (
            _candidate_identity(retained)
            if args.phase == "merge-and-verify"
            else None
        )
        expected = _trace_value(
            args,
            input_sha256=input_sha256,
            archive_sha256=archive_sha256,
            tree_sha256=manifest["tree_sha256"],
            result_sha256=result_sha256,
            candidate=candidate,
        )
        trace_raw = _read(args.trace, MAX_REPORT_BYTES, "work trace")
        try:
            trace = json.loads(trace_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise Prop1224MeasuredWorkloadError("work trace is not JSON") from error
        if canonical_json_bytes(trace) != trace_raw or trace != expected:
            raise Prop1224MeasuredWorkloadError("work trace differs")
    finally:
        _remove_tree(retained)
        _remove_tree(args.work / "trace-merge")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--phase", choices=PHASES, required=True)
    result.add_argument("--shard-index", type=int, required=True)
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--handoff", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    result.add_argument("--runner", type=Path, required=True)
    return result


def _validate_args(args: argparse.Namespace) -> None:
    factory = make_factory(args.phase, args.shard_index)
    if args.algorithm_id != factory.algorithm_id:
        raise Prop1224MeasuredWorkloadError("algorithm id differs from factory")
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    for name in ("input", "handoff", "output", "trace", "work", "runner"):
        value = getattr(args, name)
        setattr(args, name, _safe_relative(value.as_posix(), name))
    if args.runner.is_symlink() or not args.runner.is_file():
        raise Prop1224MeasuredWorkloadError("runner is not a regular file")
    if args.phase == "merge-and-verify" and args.algorithm_id != REGISTERED_ALGORITHM_ID:
        raise Prop1224MeasuredWorkloadError("terminal algorithm id differs")
    if args.phase == "merge-and-verify" and factory.input_bytes != REGISTERED_INPUT:
        raise Prop1224MeasuredWorkloadError("terminal registered input differs")


def main() -> int:
    args = parser().parse_args()
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
        OSError,
        Prop1224MeasuredWorkloadError,
        Prop1224MpfrCampaignError,
        ValueError,
    ) as error:
        print(f"Proposition 12.2.4 measured workload error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
