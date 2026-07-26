#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed measured CPU phases for historical Helfgott--Platt Goldbach.

Every predecessor is a countersigned trusted-compute receipt accompanied by
an archive whose mathematical contents are replayed.  CPU operational phases
emit a deterministic retained archive and a signed-result payload pinning it.
The separately registered CPU terminal consumes the completed branch exports.
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
for directory in (ROOT, ROOT / "attestation", ROOT / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from generate_trusted_compute_lean import load_verified_receipt  # noqa: E402
from tg_verifier.azure_cpu_goldbach_historical_operational_workload_factory import (  # noqa: E402
    CAMPAIGN_ID,
    OPERATIONAL_RESULT_KIND,
    PHASE_COUNTS,
    make_factory,
)
from tg_verifier.azure_h100_goldbach_historical_workload_factory import (  # noqa: E402
    PHASE_ID as H100_PHASE,
    expected_claim_identity as h100_expected_claim_identity,
    expected_execution_projection_sha256 as h100_execution_projection_sha256,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    read_bytes_once,
    require_azure_measured_worker,
)
from tg_verifier.goldbach_campaign import (  # noqa: E402
    CampaignError,
    CampaignParameters,
    independent_group_bounds,
    initialize_campaign,
    load_campaign,
    reduce_independent_campaign,
)
from tg_verifier.goldbach_gpu_campaign import (  # noqa: E402
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
    PRODUCTION_ALGORITHM,
    PRODUCTION_EVEN_LIMIT,
    PRODUCTION_EVEN_START,
    PRODUCTION_GROUPS,
    aggregate_directory,
    load_plan,
    load_receipt as load_binary_receipt,
    make_production_plan,
    production_group_leaf_indices,
    receipt_paths,
    validate_aggregate,
    verify_executable,
    verify_hardened_source_tree,
    write_plan,
)
from tg_verifier.goldbach_native_ladder import (  # noqa: E402
    NATIVE_GROUP_KIND,
    NATIVE_SCHEMA,
    produce_native_group,
)
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GoldbachBuildAdmission,
    GoldbachBuildAdmissionError,
    load_build_admission,
)
from trusted_compute_receipt import ReceiptError  # noqa: E402


PHASES = tuple(PHASE_COUNTS)
EXPORT_KIND = "sparkinterval.azure.goldbach-historical-retained-export.v1"
HANDOFF_KIND = "sparkinterval.azure.goldbach-historical-phase-handoff.v1"
OPERATIONAL_RESULT_FIELDS = {
    "group_index",
    "kind",
    "phase",
    "phase_result",
    "retained_export_sha256",
    "retained_export_size_bytes",
    "retained_tree_sha256",
    "schema_version",
}
TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 2
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.goldbach-historical.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.goldbach-historical.step.v1\n"
TREE_DOMAIN = b"sparkinterval/goldbach-historical-retained-tree/v1\0"
MAX_EXPORT_FILES = 2_000_000
MAX_EXPORT_BYTES = 32 * 1024**4
MAX_HANDOFF_FILES = 20_000
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

class HistoricalGoldbachOperationalWorkloadError(RuntimeError):
    """A signed predecessor, retained export, or exact phase failed closed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_relative(value: str, what: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise HistoricalGoldbachOperationalWorkloadError(
            f"{what} is not a safe relative path"
        )
    return Path(*path.parts)


def _hex(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise HistoricalGoldbachOperationalWorkloadError(
            f"{what} must be lowercase SHA-256 hex"
        )
    return value


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as error:
        raise HistoricalGoldbachOperationalWorkloadError(
            f"cannot read {what}: {error}"
        ) from error


def _write_exclusive(path: Path, raw: bytes, *, executable: bool = False) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o500 if executable else 0o400,
    )
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise HistoricalGoldbachOperationalWorkloadError(f"short write: {path}")
            view = view[count:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _copy_file(source: Path, destination: Path, *, executable: bool = False) -> None:
    metadata = source.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise HistoricalGoldbachOperationalWorkloadError(
            f"source is linked or not regular: {source}"
        )
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    source_fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    destination_fd = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o500 if executable else 0o400,
    )
    try:
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                count = os.write(destination_fd, view)
                if count <= 0:
                    raise HistoricalGoldbachOperationalWorkloadError("short copy write")
                view = view[count:]
        os.fsync(destination_fd)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        os.close(source_fd)
        os.close(destination_fd)


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir() or destination.exists():
        raise HistoricalGoldbachOperationalWorkloadError("tree copy boundary is unsafe")
    destination.mkdir(mode=0o700, parents=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
            _copy_file(path, target, executable=bool(metadata.st_mode & 0o111))
        else:
            raise HistoricalGoldbachOperationalWorkloadError(
                "retained tree contains a linked or special file"
            )


def _merge_tree(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise HistoricalGoldbachOperationalWorkloadError("merge source is not a directory")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise HistoricalGoldbachOperationalWorkloadError(
                "merge source contains a linked or special file"
            )
        if target.exists():
            if target.is_symlink() or hash_file_once(target) != hash_file_once(path):
                raise HistoricalGoldbachOperationalWorkloadError(
                    f"predecessor exports disagree at {relative.as_posix()}"
                )
        else:
            _copy_file(path, target, executable=bool(metadata.st_mode & 0o111))


def _tree_rows(
    root: Path, *, exclude_manifest: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise HistoricalGoldbachOperationalWorkloadError(
                f"retained tree contains a linked or special file: {relative}"
            )
        if exclude_manifest and relative == "export-manifest.json":
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


def _write_export_manifest(root: Path, phase: str, group_index: int) -> dict[str, Any]:
    rows, total = _tree_rows(root)
    value = {
        "file_count": len(rows),
        "group_index": group_index,
        "kind": EXPORT_KIND,
        "phase": phase,
        "schema_version": 1,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
    }
    _write_exclusive(root / "export-manifest.json", canonical_json_bytes(value))
    return value


def _validate_export(root: Path, phase: str, group_index: int) -> dict[str, Any]:
    try:
        value = load_json(root / "export-manifest.json", require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachOperationalWorkloadError(
            f"invalid retained export manifest: {error}"
        ) from error
    fields = {
        "file_count", "group_index", "kind", "phase", "schema_version",
        "total_bytes", "tree_sha256",
    }
    rows, total = _tree_rows(root, exclude_manifest=True)
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["kind"] != EXPORT_KIND
        or value["schema_version"] != 1
        or value["phase"] != phase
        or value["group_index"] != group_index
        or value["file_count"] != len(rows)
        or value["total_bytes"] != total
        or value["tree_sha256"] != _tree_digest(rows)
    ):
        raise HistoricalGoldbachOperationalWorkloadError("retained export identity differs")
    return value


def verify_retained_export_archive(
    archive: Path, phase: str, group_index: int,
) -> dict[str, Any]:
    temporary = Path(tempfile.mkdtemp(prefix=".goldbach-historical-export-"))
    try:
        extract_archive(
            archive, temporary / "export", maximum_files=MAX_EXPORT_FILES,
            maximum_bytes=MAX_EXPORT_BYTES,
        )
        return _validate_export(temporary / "export", phase, group_index)
    except (ArchiveError, OSError) as error:
        if isinstance(error, HistoricalGoldbachOperationalWorkloadError):
            raise
        raise HistoricalGoldbachOperationalWorkloadError(
            f"cannot replay retained export: {error}"
        ) from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _claim_result(receipt: Mapping[str, Any]) -> tuple[str, Any]:
    result = receipt["claim"]["result"]
    if not isinstance(result, str) or _sha(result.encode("utf-8")) != receipt["claim"]["output_hash"]:
        raise HistoricalGoldbachOperationalWorkloadError(
            "predecessor result/output hash is inconsistent"
        )
    try:
        return result, json.loads(result)
    except json.JSONDecodeError as error:
        raise HistoricalGoldbachOperationalWorkloadError(
            "predecessor result is not JSON"
        ) from error


def _validate_h100_result(
    receipt: Mapping[str, Any],
    group_index: int,
    admission: GoldbachBuildAdmission,
) -> dict[str, Any]:
    claim = receipt["claim"]
    expected_identity = h100_expected_claim_identity(group_index, admission)
    expected_artifacts = {
        "device_cubin_hash": admission.core["executable"]["sha256"],
        "host_executable_hash": admission.core["python"]["sha256"],
        "kernel_manifest_hash": h100_execution_projection_sha256(
            group_index, admission
        ),
        "source_tree_hash": admission.expected_artifacts["source_tree_hash"],
    }
    if receipt["backend"] != "azure_ncc40ads_h100_v5" or any(
        claim.get(field) != value for field, value in expected_identity.items()
    ) or (
        claim.get("artifacts") != expected_artifacts
        or claim.get("target") != "nvidia_h100_sm90"
        or claim.get("target_profile_hash")
        != admission.deployment["target_profile_sha256"]
        or claim.get("trust") != "nvidia_h100_confidential_compute"
        or claim.get("trust_profile_hash")
        != admission.deployment["trust_profile_sha256"]
    ):
        raise HistoricalGoldbachOperationalWorkloadError(
            "H100 predecessor is not the exact admitted build/job/profile"
        )
    _raw, value = _claim_result(receipt)
    fields = {
        "all_group_receipts_valid", "execution_attested", "group_index",
        "leaf_indices", "lean_atom_discharged", "receipts",
        "scheduler_group_count", "schema",
    }
    indices = list(range(group_index, 65_536, PRODUCTION_GROUPS))
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["schema"] != "sparkinterval.goldbach-gpu-run-group.v1"
        or value["group_index"] != group_index
        or value["scheduler_group_count"] != PRODUCTION_GROUPS
        or value["leaf_indices"] != indices
        or value["all_group_receipts_valid"] is not True
        or value["execution_attested"] is not False
        or value["lean_atom_discharged"] is not False
        or not isinstance(value["receipts"], list)
        or len(value["receipts"]) != 8
    ):
        raise HistoricalGoldbachOperationalWorkloadError("H100 group result differs")
    by_index: dict[int, str] = {}
    for row in value["receipts"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"leaf_index", "receipt_sha256", "status"}
            or row["leaf_index"] not in indices
            or row["leaf_index"] in by_index
            or row["status"] not in {
                "completed-new-receipt", "validated-existing-receipt"
            }
        ):
            raise HistoricalGoldbachOperationalWorkloadError(
                "H100 group result receipt row differs"
            )
        by_index[row["leaf_index"]] = _hex(
            row["receipt_sha256"], "H100 leaf receipt"
        )
    if set(by_index) != set(indices):
        raise HistoricalGoldbachOperationalWorkloadError("H100 group omitted a leaf")
    return {"result": value, "receipt_sha256s": by_index}


def _validate_cpu_result(
    receipt: Mapping[str, Any], phase: str, group_index: int, archive: Path,
) -> dict[str, Any]:
    factory = make_factory(phase, group_index)
    claim = receipt["claim"]
    if (
        factory.terminal
        or receipt["backend"] != "azure_sevsnp_cpu"
        or claim["algorithm_id"] != factory.algorithm_id
        or claim["algorithm_hash"] != _sha(factory.algorithm_definition.encode("utf-8"))
        or claim["parameters_hash"] != _sha(canonical_json_bytes(factory.parameters))
        or claim["domain_hash"] != _sha(canonical_json_bytes(factory.domain))
    ):
        raise HistoricalGoldbachOperationalWorkloadError(
            "CPU predecessor is not the reviewed operational phase"
        )
    raw, value = _claim_result(receipt)
    if (
        not isinstance(value, dict)
        or set(value) != OPERATIONAL_RESULT_FIELDS
        or canonical_json_bytes(value).decode("utf-8") != raw
        or value["kind"] != OPERATIONAL_RESULT_KIND
        or value["schema_version"] != 1
        or value["phase"] != phase
        or value["group_index"] != group_index
        or (
            _validate_native_phase_result(value["phase_result"], group_index)
            if phase == "native-prime-ladder-range-groups"
            else value["phase_result"] is not None
        )
        or hash_file_once(archive) != (
            value["retained_export_sha256"], value["retained_export_size_bytes"]
        )
    ):
        raise HistoricalGoldbachOperationalWorkloadError(
            "CPU predecessor result/export pin differs"
        )
    manifest = verify_retained_export_archive(archive, phase, group_index)
    if manifest["tree_sha256"] != value["retained_tree_sha256"]:
        raise HistoricalGoldbachOperationalWorkloadError(
            "CPU predecessor retained tree differs"
        )
    return value


def _validate_native_phase_result(value: Any, group_index: int) -> bool:
    """Return ``False`` after exact validation, for use in fail-closed guards."""

    fields = {
        "classification", "first_range_index", "group_count", "group_index",
        "kind", "last_range_index", "local_workers",
        "native_receipt_sha256s", "range_count",
        "range_receipt_sha256s", "schema",
    }
    lower, upper = independent_group_bounds(
        CampaignParameters().range_count, group_index, 320
    )
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["classification"] != "full_source"
        or value["first_range_index"] != lower
        or value["group_count"] != 320
        or value["group_index"] != group_index
        or value["kind"] != NATIVE_GROUP_KIND
        or value["last_range_index"] != upper - 1
        or value["local_workers"] != 40
        or value["range_count"] != upper - lower
        or value["schema"] != NATIVE_SCHEMA
        or not isinstance(value["native_receipt_sha256s"], list)
        or not isinstance(value["range_receipt_sha256s"], list)
        or len(value["native_receipt_sha256s"]) != upper - lower
        or len(value["range_receipt_sha256s"]) != upper - lower
    ):
        raise HistoricalGoldbachOperationalWorkloadError(
            "native phase result has wrong historical range geometry"
        )
    for what, rows in (
        ("native receipt", value["native_receipt_sha256s"]),
        ("ordinary receipt", value["range_receipt_sha256s"]),
    ):
        for digest in rows:
            if _hex(digest, what) == "0" * 64:
                raise HistoricalGoldbachOperationalWorkloadError(
                    f"{what} digest cannot be zero"
                )
    return False


def _entry_paths(root: Path, entry: Mapping[str, Any]) -> tuple[Path, Path]:
    receipt = root / _safe_relative(entry["receipt_path"], "receipt path")
    export = root / _safe_relative(entry["export_path"], "export path")
    if hash_file_once(receipt) != (entry["receipt_file_sha256"], entry["receipt_file_size_bytes"]):
        raise HistoricalGoldbachOperationalWorkloadError("handoff receipt file pin differs")
    if hash_file_once(export) != (entry["export_sha256"], entry["export_size_bytes"]):
        raise HistoricalGoldbachOperationalWorkloadError("handoff export file pin differs")
    return receipt, export


def _expected_entries(phase: str, group_index: int) -> set[tuple[str, int]]:
    group = lambda value: f"{CAMPAIGN_ID}::{value}"
    if phase in ("create-production-plan", "initialize-prime-ladder"):
        return set()
    if phase == "native-prime-ladder-range-groups":
        return {(group("initialize-prime-ladder"), 0)}
    if phase == "aggregate":
        return {
            (group("create-production-plan"), 0),
            *((group(H100_PHASE), index) for index in range(PRODUCTION_GROUPS)),
        }
    if phase == "binary-semantic-replay":
        return {(group("aggregate"), 0)}
    if phase == "reduce-prime-ladder-ranges":
        return {
            (group("native-prime-ladder-range-groups"), index)
            for index in range(320)
        }
    raise HistoricalGoldbachOperationalWorkloadError("unknown phase")


def _handoff(
    path: Path,
    phase: str,
    group_index: int,
    key_manifest: Path,
    admission: GoldbachBuildAdmission,
) -> tuple[dict[str, Any], Path, dict[tuple[str, int], dict[str, Any]]]:
    root = path.parent / f".{path.name}.extracted"
    try:
        extract_archive(
            path, root, maximum_files=MAX_HANDOFF_FILES,
            maximum_bytes=MAX_EXPORT_BYTES,
        )
        value = load_json(root / "handoff.json", require_canonical=True)
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachOperationalWorkloadError(
            f"invalid phase handoff: {error}"
        ) from error
    fields = {"entries", "group_index", "kind", "phase", "schema_version"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["kind"] != HANDOFF_KIND
        or value["schema_version"] != 1
        or value["phase"] != phase
        or value["group_index"] != group_index
        or not isinstance(value["entries"], list)
    ):
        raise HistoricalGoldbachOperationalWorkloadError("phase handoff identity differs")
    entry_fields = {
        "export_path", "export_sha256", "export_size_bytes", "group_id",
        "phase", "receipt_file_sha256", "receipt_file_size_bytes",
        "receipt_path", "receipt_sha256", "shard_index",
    }
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    for entry in value["entries"]:
        if not isinstance(entry, dict) or set(entry) != entry_fields:
            raise HistoricalGoldbachOperationalWorkloadError("handoff entry fields changed")
        identity = (entry["group_id"], entry["shard_index"])
        if identity in rows:
            raise HistoricalGoldbachOperationalWorkloadError("duplicate handoff identity")
        receipt_path, export_path = _entry_paths(root, entry)
        try:
            receipt = load_verified_receipt(receipt_path, key_manifest=key_manifest)
        except Exception as error:
            raise HistoricalGoldbachOperationalWorkloadError(
                f"predecessor signature failed: {error}"
            ) from error
        if receipt["receipt_sha256"] != entry["receipt_sha256"]:
            raise HistoricalGoldbachOperationalWorkloadError("predecessor receipt identity differs")
        source_phase = entry["phase"]
        if source_phase == H100_PHASE:
            _validate_h100_result(
                receipt, entry["shard_index"], admission
            )
        else:
            _validate_cpu_result(
                receipt, source_phase, entry["shard_index"], export_path
            )
        rows[identity] = {
            **entry,
            "export": export_path,
            "receipt": receipt,
        }
    if set(rows) != _expected_entries(phase, group_index):
        raise HistoricalGoldbachOperationalWorkloadError(
            "handoff does not exactly cover reviewed predecessors"
        )
    return value, root, rows


def _extract_entry(
    handoff_root: Path, row: Mapping[str, Any], destination: Path,
) -> tuple[Path, dict[str, Any]]:
    extract_archive(
        row["export"], destination, maximum_files=MAX_EXPORT_FILES,
        maximum_bytes=MAX_EXPORT_BYTES,
    )
    return destination, _validate_export(
        destination, row["phase"], row["shard_index"]
    )


def _write_operational_result(
    args: argparse.Namespace,
    archive: Path,
    manifest: Mapping[str, Any],
    phase_result: Mapping[str, Any] | None,
) -> None:
    digest, size = hash_file_once(archive)
    _write_exclusive(
        args.output,
        canonical_json_bytes(
            {
                "group_index": args.group_index,
                "kind": OPERATIONAL_RESULT_KIND,
                "phase": args.phase,
                "phase_result": phase_result,
                "retained_export_sha256": digest,
                "retained_export_size_bytes": size,
                "retained_tree_sha256": manifest["tree_sha256"],
                "schema_version": 1,
            }
        ),
    )


def _binary_payload(root: Path) -> tuple[Path, Path, Path]:
    payload = root / "payload"
    return (
        payload / "binary-plan.json",
        payload / "binary-receipts",
        payload / "binary-aggregate.json",
    )


def _validate_exact_plan(plan_path: Path):
    plan = load_plan(plan_path)
    if (
        not plan.production
        or plan.algorithm != PRODUCTION_ALGORITHM
        or (plan.even_start, plan.even_limit)
        != (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT)
    ):
        raise HistoricalGoldbachOperationalWorkloadError(
            "binary plan is not the exact historical source-height profile"
        )
    return plan


def _replay_binary_payload(root: Path) -> None:
    plan_path, receipts_dir, aggregate_path = _binary_payload(root)
    plan = _validate_exact_plan(plan_path)
    receipts = [load_binary_receipt(path, plan=plan) for path in receipt_paths(receipts_dir)]
    aggregate = load_json(aggregate_path, require_canonical=True)
    validate_aggregate(aggregate, plan=plan, receipts=receipts)


def _run_phase(
    args: argparse.Namespace,
    handoff_root: Path,
    rows: Mapping[tuple[str, int], Mapping[str, Any]],
    export: Path,
) -> dict[str, Any] | None:
    group = lambda value: f"{CAMPAIGN_ID}::{value}"
    payload = export / "payload"
    payload.mkdir(mode=0o700, parents=True)
    if args.phase == "create-production-plan":
        admission = args.build_admission_value
        source_identity = verify_hardened_source_tree(args.goldbach_source)
        if (
            source_identity != EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256
            or source_identity
            != admission.core["source_identity_sha256"]
        ):
            raise HistoricalGoldbachOperationalWorkloadError("hardened source identity changed")
        executable_hash = hash_file_once(args.goldbach_executable)[0]
        if executable_hash != admission.core["executable"]["sha256"]:
            raise HistoricalGoldbachOperationalWorkloadError(
                "plan executable is not the admitted GoldbachGPU binary"
            )
        verify_executable(
            args.goldbach_executable,
            admission.core["executable"]["sha256"],
        )
        plan = make_production_plan(
            executable_sha256=admission.core["executable"]["sha256"]
        )
        write_plan(payload / "binary-plan.json", plan)
    elif args.phase == "initialize-prime-ladder":
        ladder = payload / "prime-ladder"
        initialize_campaign(ladder)
        if load_campaign(ladder) != CampaignParameters():
            raise HistoricalGoldbachOperationalWorkloadError(
                "historical ladder profile changed"
            )
    elif args.phase == "native-prime-ladder-range-groups":
        row = rows[(group("initialize-prime-ladder"), 0)]
        predecessor, _manifest = _extract_entry(
            handoff_root, row, handoff_root / "expanded-initialize"
        )
        ladder = payload / "prime-ladder"
        _copy_tree(predecessor / "payload/prime-ladder", ladder)
        result = produce_native_group(
            ladder,
            runner=args.ladder_runner,
            group_index=args.group_index,
            group_count=320,
            local_workers=40,
        )
        summary = ladder / "groups" / f"group-{args.group_index}.json"
        _write_exclusive(summary, canonical_json_bytes(result))
        _validate_native_phase_result(result, args.group_index)
    elif args.phase == "aggregate":
        plan_row = rows[(group("create-production-plan"), 0)]
        plan_export, _manifest = _extract_entry(
            handoff_root, plan_row, handoff_root / "expanded-plan"
        )
        plan_path = payload / "binary-plan.json"
        _copy_file(plan_export / "payload/binary-plan.json", plan_path)
        plan = _validate_exact_plan(plan_path)
        receipts_dir = payload / "binary-receipts"
        receipts_dir.mkdir(mode=0o700)
        for index in range(PRODUCTION_GROUPS):
            row = rows[(group(H100_PHASE), index)]
            group_export, _manifest = _extract_entry(
                handoff_root, row, handoff_root / f"expanded-h100-{index:04d}"
            )
            signed = _validate_h100_result(
                row["receipt"], index, args.build_admission_value
            )["receipt_sha256s"]
            expected_indices = production_group_leaf_indices(plan, index)
            source_dir = group_export / "payload/binary-receipts"
            actual_names = {path.name for path in source_dir.iterdir() if path.is_file()}
            wanted_names = {f"receipt-{leaf:08d}.json" for leaf in expected_indices}
            if actual_names != wanted_names:
                raise HistoricalGoldbachOperationalWorkloadError(
                    "H100 export does not contain its exact eight receipts"
                )
            for leaf in expected_indices:
                source = source_dir / f"receipt-{leaf:08d}.json"
                receipt = load_binary_receipt(source, plan=plan)
                if receipt["receipt_sha256"] != signed[leaf]:
                    raise HistoricalGoldbachOperationalWorkloadError(
                        "H100 export leaf differs from the signed group result"
                    )
                _copy_file(source, receipts_dir / source.name)
            shutil.rmtree(group_export)
        aggregate_directory(
            plan=plan, output_directory=receipts_dir,
            aggregate_path=payload / "binary-aggregate.json",
        )
    elif args.phase == "binary-semantic-replay":
        row = rows[(group("aggregate"), 0)]
        predecessor, _manifest = _extract_entry(
            handoff_root, row, handoff_root / "expanded-binary-aggregate"
        )
        _copy_tree(predecessor / "payload", payload / ".incoming")
        incoming = payload / ".incoming"
        for child in sorted(incoming.iterdir()):
            os.replace(child, payload / child.name)
        incoming.rmdir()
        _replay_binary_payload(export)
    elif args.phase == "reduce-prime-ladder-ranges":
        ladder = payload / "prime-ladder"
        for index in range(320):
            row = rows[(group("native-prime-ladder-range-groups"), index)]
            predecessor, _manifest = _extract_entry(
                handoff_root, row, handoff_root / f"expanded-ladder-{index:03d}"
            )
            _merge_tree(predecessor / "payload/prime-ladder", ladder)
            shutil.rmtree(predecessor)
        if load_campaign(ladder) != CampaignParameters():
            raise HistoricalGoldbachOperationalWorkloadError(
                "merged historical ladder profile differs"
            )
        reduce_independent_campaign(
            ladder, aggregate_path=ladder / "ladder-aggregate.json"
        )
    else:
        raise HistoricalGoldbachOperationalWorkloadError(
            "unknown historical operational phase"
        )
    return result if args.phase == "native-prime-ladder-range-groups" else None


def _trace_hash(
    *, phase: str, group_index: int, challenge: str, job_binding: str,
    input_sha256: str, handoff_sha256: str, retained_sha256: str,
    retained_tree_sha256: str, result_sha256: str,
) -> str:
    current = _sha(
        INITIAL_DOMAIN
        + f"phase={phase}\n".encode("ascii")
        + f"group_index={group_index}\n".encode("ascii")
        + f"challenge_nonce={challenge}\n".encode("ascii")
        + f"job_binding_sha256={job_binding}\n".encode("ascii")
        + f"input_sha256={input_sha256}\n".encode("ascii")
        + f"handoff_sha256={handoff_sha256}\n".encode("ascii")
    )
    current = _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"retained_archive_sha256={retained_sha256}\n".encode("ascii")
        + f"retained_tree_sha256={retained_tree_sha256}\n".encode("ascii")
    )
    return _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"result_sha256={result_sha256}\n".encode("ascii")
    )


def _trace_value(
    args: argparse.Namespace, *, retained_sha256: str,
    retained_tree_sha256: str,
) -> dict[str, Any]:
    input_sha256 = hash_file_once(args.input)[0]
    handoff_sha256 = hash_file_once(args.handoff)[0]
    result_sha256 = hash_file_once(args.output)[0]
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
            phase=args.phase, group_index=args.group_index,
            challenge=args.challenge, job_binding=args.job_binding,
            input_sha256=input_sha256, handoff_sha256=handoff_sha256,
            retained_sha256=retained_sha256,
            retained_tree_sha256=retained_tree_sha256,
            result_sha256=result_sha256,
        ),
    }


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    _handoff_value, handoff_root, rows = _handoff(
        args.handoff,
        args.phase,
        args.group_index,
        args.key_manifest,
        args.build_admission_value,
    )
    if args.work.exists():
        raise HistoricalGoldbachOperationalWorkloadError("work directory must be fresh")
    args.work.mkdir(mode=0o700, parents=True)
    succeeded = False
    try:
        export = args.work / "retained"
        export.mkdir(mode=0o700)
        phase_result = _run_phase(args, handoff_root, rows, export)
        manifest = _write_export_manifest(export, args.phase, args.group_index)
        archive = args.work / "retained-export.tar"
        create_archive(export, archive)
        _write_operational_result(args, archive, manifest, phase_result)
        retained_sha256 = hash_file_once(archive)[0]
        tree_sha256 = manifest["tree_sha256"]
        _write_exclusive(
            args.trace,
            canonical_json_bytes(
                _trace_value(
                    args,
                    retained_sha256=retained_sha256,
                    retained_tree_sha256=tree_sha256,
                )
            ),
        )
        succeeded = True
    finally:
        shutil.rmtree(handoff_root, ignore_errors=True)
        if not succeeded:
            shutil.rmtree(args.work, ignore_errors=True)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    _handoff_value, handoff_root, rows = _handoff(
        args.handoff,
        args.phase,
        args.group_index,
        args.key_manifest,
        args.build_admission_value,
    )
    temporary = Path(tempfile.mkdtemp(prefix=".goldbach-historical-trace-"))
    try:
        result = load_json(args.output, require_canonical=True)
        archive = args.work / "retained-export.tar"
        manifest = verify_retained_export_archive(
            archive, args.phase, args.group_index
        )
        if (
            not isinstance(result, dict)
            or set(result) != OPERATIONAL_RESULT_FIELDS
            or result.get("kind") != OPERATIONAL_RESULT_KIND
            or result.get("schema_version") != 1
            or result.get("phase") != args.phase
            or result.get("group_index") != args.group_index
            or (
                _validate_native_phase_result(
                    result.get("phase_result"), args.group_index
                )
                if args.phase == "native-prime-ladder-range-groups"
                else result.get("phase_result") is not None
            )
            or hash_file_once(archive) != (
                result.get("retained_export_sha256"),
                result.get("retained_export_size_bytes"),
            )
            or manifest["tree_sha256"] != result.get("retained_tree_sha256")
        ):
            raise HistoricalGoldbachOperationalWorkloadError(
                "operational output differs from retained archive"
            )
        retained_sha256 = result["retained_export_sha256"]
        tree_sha256 = manifest["tree_sha256"]
        expected = _trace_value(
            args,
            retained_sha256=retained_sha256,
            retained_tree_sha256=tree_sha256,
        )
        actual = load_json(args.trace, require_canonical=True)
        if actual != expected:
            raise HistoricalGoldbachOperationalWorkloadError("challenge trace differs")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(handoff_root, ignore_errors=True)


def package_h100_export(
    *, plan_path: Path, receipts_directory: Path, group_index: int,
    signed_receipt_path: Path, key_manifest: Path,
    build_admission_path: Path, output_path: Path,
) -> dict[str, Any]:
    """Package exactly eight H100 leaf receipts after signed-result replay."""

    plan = _validate_exact_plan(plan_path)
    admission = load_build_admission(build_admission_path)
    signed = load_verified_receipt(signed_receipt_path, key_manifest=key_manifest)
    expected = _validate_h100_result(
        signed, group_index, admission
    )["receipt_sha256s"]
    temporary = Path(tempfile.mkdtemp(prefix=".goldbach-historical-h100-export-"))
    try:
        payload = temporary / "payload/binary-receipts"
        payload.mkdir(mode=0o700, parents=True)
        for leaf in production_group_leaf_indices(plan, group_index):
            source = receipts_directory / f"receipt-{leaf:08d}.json"
            receipt = load_binary_receipt(source, plan=plan)
            if receipt["receipt_sha256"] != expected[leaf]:
                raise HistoricalGoldbachOperationalWorkloadError(
                    "leaf receipt differs from signed H100 result"
                )
            _copy_file(source, payload / source.name)
        manifest = _write_export_manifest(temporary, H100_PHASE, group_index)
        create_archive(temporary, output_path)
        digest, size = hash_file_once(output_path)
        return {
            "accepted": False,
            "classification": "signed_h100_group_handoff_not_terminal_evidence",
            "group_index": group_index,
            "kind": "sparkinterval.azure.goldbach-historical-h100-export-package.v1",
            "receipt_sha256": signed["receipt_sha256"],
            "retained_export_sha256": digest,
            "retained_export_size_bytes": size,
            "retained_tree_sha256": manifest["tree_sha256"],
            "schema_version": 1,
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("mode", choices=("run", "verify-trace", "package-h100"))
    result.add_argument("--phase", choices=PHASES)
    result.add_argument("--group-index", type=int)
    result.add_argument("--algorithm-id")
    result.add_argument("--challenge")
    result.add_argument("--job-binding")
    result.add_argument("--input", type=Path)
    result.add_argument("--handoff", type=Path)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path)
    result.add_argument("--work", type=Path)
    result.add_argument("--goldbach-source", type=Path)
    result.add_argument("--goldbach-executable", type=Path)
    result.add_argument("--ladder-runner", type=Path)
    result.add_argument("--key-manifest", type=Path, required=True)
    result.add_argument("--build-admission", type=Path, required=True)
    result.add_argument("--plan", type=Path)
    result.add_argument("--receipts-dir", type=Path)
    result.add_argument("--signed-receipt", type=Path)
    return result


def _validate_measured_args(args: argparse.Namespace) -> None:
    required = (
        "phase", "group_index", "algorithm_id", "challenge", "job_binding",
        "input", "handoff", "trace", "work", "goldbach_source",
        "goldbach_executable", "ladder_runner", "build_admission",
    )
    if any(getattr(args, name) is None for name in required):
        raise HistoricalGoldbachOperationalWorkloadError("measured mode omits a required argument")
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    if args.phase not in PHASE_COUNTS or not 0 <= args.group_index < PHASE_COUNTS[args.phase]:
        raise HistoricalGoldbachOperationalWorkloadError("phase group index is outside the DAG")
    factory = make_factory(args.phase, args.group_index)
    if args.algorithm_id != factory.algorithm_id:
        raise HistoricalGoldbachOperationalWorkloadError("algorithm identity differs from phase")
    for name in (
        "input", "handoff", "output", "trace", "work", "goldbach_source",
        "goldbach_executable", "ladder_runner", "key_manifest",
        "build_admission",
    ):
        value = getattr(args, name)
        setattr(args, name, _safe_relative(value.as_posix(), name))
    try:
        args.build_admission_value = load_build_admission(
            args.build_admission
        )
    except GoldbachBuildAdmissionError as error:
        raise HistoricalGoldbachOperationalWorkloadError(str(error)) from error


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.mode == "package-h100":
            if (
                args.plan is None or args.receipts_dir is None
                or args.signed_receipt is None or args.group_index is None
            ):
                raise HistoricalGoldbachOperationalWorkloadError(
                    "package-h100 requires plan, receipts, signed receipt, and group index"
                )
            value = package_h100_export(
                plan_path=args.plan, receipts_directory=args.receipts_dir,
                group_index=args.group_index, signed_receipt_path=args.signed_receipt,
                key_manifest=args.key_manifest,
                build_admission_path=args.build_admission,
                output_path=args.output,
            )
            sys.stdout.buffer.write(canonical_json_bytes(value))
        else:
            require_azure_measured_worker(
                challenge_nonce=args.challenge,
                job_binding=args.job_binding,
            )
            _validate_measured_args(args)
            if args.mode == "run":
                run(args)
            else:
                verify_trace(args)
    except (
        ArchiveError, CampaignError, CampaignIOError,
        HistoricalGoldbachOperationalWorkloadError, OSError, ReceiptError, ValueError,
    ) as error:
        print(f"historical Goldbach measured workload error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
