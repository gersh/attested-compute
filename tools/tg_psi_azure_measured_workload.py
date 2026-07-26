#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed measured-workload adapter for the distributed CH25 psi DAG.

The adapter accepts only the six reviewed portfolio phases.  Operational
phases emit deterministic archives containing every retained campaign file;
the terminal phase replays the complete final archive and exclusively emits
the registered literal ``true``.  A challenge-dependent trace binds the exact
handoff, retained archive, job, input, and result without invoking a shell.
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
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "attestation"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    read_bytes_once,
    require_azure_measured_worker,
)
from tg_verifier.psi_residual_campaign import (  # noqa: E402
    FINAL_NAME,
    REGISTERED_RESULT,
    SOURCE_UPPER_EXCLUSIVE,
    finalize_campaign,
    grouped_shard_indices,
    initialize_campaign,
    reduce_summaries,
    run_phase,
    verify_campaign,
    write_registered_result,
)


PHASES = (
    "initialize",
    "summary-shards",
    "reduce-summaries",
    "verify-shards",
    "finalize",
    "semantic-replay",
)
GROUP_COUNT = 320
MAX_EXPORT_FILES = 400_500
MAX_EXPORT_BYTES = 256 * 1024**3
TRACE_ITERATIONS = 2
TRACE_KIND = "sparkinterval_challenge_work_trace"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.ch25-psi-lemma-9-2.v1"
)
HANDOFF_KIND = "sparkinterval.azure.psi-phase-handoff.v1"
EXPORT_KIND = "sparkinterval.azure.psi-retained-export.v1"
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.ch25-psi.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.ch25-psi.step.v1\n"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class PsiMeasuredWorkloadError(RuntimeError):
    pass


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
        raise PsiMeasuredWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _hex(value: str, what: str) -> str:
    if SHA256_RE.fullmatch(value) is None:
        raise PsiMeasuredWorkloadError(f"{what} must be lowercase SHA-256 hex")
    return value


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as error:
        raise PsiMeasuredWorkloadError(f"cannot read {what}: {error}") from error


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
                raise PsiMeasuredWorkloadError(f"short write: {path}")
            view = view[count:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _tree_rows(root: Path, *, exclude_manifest: bool = False) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PsiMeasuredWorkloadError(
                f"retained tree contains a linked or special file: {relative}"
            )
        if exclude_manifest and relative == "export-manifest.json":
            continue
        digest, size = hash_file_once(path)
        rows.append({"path": relative, "sha256": digest, "size_bytes": size})
        total += size
    return rows, total


def _tree_digest(rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256(b"sparkinterval/psi-retained-tree/v1\0")
    for row in rows:
        encoded = row["path"].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(row["size_bytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(row["sha256"]))
    return digest.hexdigest()


def _write_export_manifest(root: Path, phase: str, group_index: int) -> dict[str, Any]:
    rows, total = _tree_rows(root)
    manifest = {
        "file_count": len(rows),
        "group_index": group_index,
        "kind": EXPORT_KIND,
        "phase": phase,
        "schema_version": 1,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
    }
    _write_exclusive(root / "export-manifest.json", canonical_json_bytes(manifest))
    return manifest


def _validate_export(root: Path, phase: str, group_index: int) -> dict[str, Any]:
    try:
        manifest = load_json(root / "export-manifest.json", require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise PsiMeasuredWorkloadError(f"invalid retained export manifest: {error}") from error
    expected_fields = {
        "file_count",
        "group_index",
        "kind",
        "phase",
        "schema_version",
        "total_bytes",
        "tree_sha256",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        raise PsiMeasuredWorkloadError("retained export manifest fields changed")
    if (
        manifest["kind"] != EXPORT_KIND
        or manifest["schema_version"] != 1
        or manifest["phase"] != phase
        or manifest["group_index"] != group_index
    ):
        raise PsiMeasuredWorkloadError("retained export identity differs")
    rows, total = _tree_rows(root, exclude_manifest=True)
    if (
        manifest["file_count"] != len(rows)
        or manifest["total_bytes"] != total
        or manifest["tree_sha256"] != _tree_digest(rows)
    ):
        raise PsiMeasuredWorkloadError("retained export tree differs from its manifest")
    return manifest


def _extract_export(archive: Path, destination: Path, phase: str, index: int) -> dict[str, Any]:
    try:
        extract_archive(
            archive,
            destination,
            maximum_files=MAX_EXPORT_FILES,
            maximum_bytes=MAX_EXPORT_BYTES,
        )
    except ArchiveError as error:
        raise PsiMeasuredWorkloadError(f"cannot extract retained export: {error}") from error
    return _validate_export(destination, phase, index)


def _handoff(path: Path, phase: str, group_index: int) -> tuple[dict[str, Any], Path]:
    root = path.parent / f".{path.name}.extracted"
    _safe_relative(root.as_posix(), "handoff extraction path")
    try:
        extract_archive(path, root, maximum_files=650, maximum_bytes=MAX_EXPORT_BYTES)
        value = load_json(root / "handoff.json", require_canonical=True)
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        raise PsiMeasuredWorkloadError(f"invalid phase handoff: {error}") from error
    fields = {"entries", "group_index", "kind", "phase", "schema_version"}
    if not isinstance(value, dict) or set(value) != fields:
        raise PsiMeasuredWorkloadError("phase handoff fields changed")
    if (
        value["kind"] != HANDOFF_KIND
        or value["schema_version"] != 1
        or value["phase"] != phase
        or value["group_index"] != group_index
        or not isinstance(value["entries"], list)
    ):
        raise PsiMeasuredWorkloadError("phase handoff identity differs")
    expected_entry_fields = {
        "group_id",
        "path",
        "sha256",
        "shard_index",
        "size_bytes",
    }
    for entry in value["entries"]:
        if not isinstance(entry, dict) or set(entry) != expected_entry_fields:
            raise PsiMeasuredWorkloadError("phase handoff entry fields changed")
        relative = _safe_relative(entry["path"], "predecessor export path")
        candidate = root / relative
        if hash_file_once(candidate) != (entry["sha256"], entry["size_bytes"]):
            raise PsiMeasuredWorkloadError("predecessor export differs from its handoff pin")
    return value, root


def _copy_file(source: Path, destination: Path) -> None:
    raw = _read(source, 4 << 20, "retained leaf")
    _write_exclusive(destination, raw)


def _initialize(args: argparse.Namespace, campaign: Path) -> None:
    result = initialize_campaign(
        runner=args.runner,
        runner_source=args.runner_source,
        upstream_manifest=args.upstream_manifest,
        output_directory=campaign,
    )
    if result.mode != "full_source" or result.shard_count != 100_000:
        raise PsiMeasuredWorkloadError("psi initialization did not create the source plan")


def _restore_campaign(export_root: Path, campaign: Path) -> None:
    source = export_root / "campaign"
    if campaign.exists() or not source.is_dir():
        raise PsiMeasuredWorkloadError("predecessor lacks one fresh campaign snapshot")
    shutil.copytree(source, campaign)


def _entry_archive(handoff_root: Path, entry: dict[str, Any]) -> Path:
    return handoff_root / _safe_relative(entry["path"], "predecessor export path")


def _import_leaf_exports(
    handoff: dict[str, Any], handoff_root: Path, campaign: Path,
    *, source_phase: str, destination_phase: str,
) -> None:
    expected = set(range(GROUP_COUNT))
    actual = {entry["shard_index"] for entry in handoff["entries"]}
    if actual != expected or len(handoff["entries"]) != GROUP_COUNT:
        raise PsiMeasuredWorkloadError("leaf predecessor set does not cover 320 groups")
    destination = campaign / destination_phase
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for entry in sorted(handoff["entries"], key=lambda row: row["shard_index"]):
        index = entry["shard_index"]
        extracted = handoff_root / f"expanded-{source_phase}-{index:03d}"
        _extract_export(
            _entry_archive(handoff_root, entry), extracted, source_phase, index
        )
        leaf_root = extracted / "payload" / destination_phase
        if not leaf_root.is_dir():
            raise PsiMeasuredWorkloadError("leaf export payload is absent")
        wanted = {
            f"receipt-{leaf:08d}.json"
            for leaf in range(index, 100_000, GROUP_COUNT)
        }
        files = {path.name for path in leaf_root.iterdir() if path.is_file()}
        if files != wanted:
            raise PsiMeasuredWorkloadError("leaf export does not match its strided group")
        for name in sorted(files):
            _copy_file(leaf_root / name, destination / name)
        shutil.rmtree(extracted)


def _single_predecessor(
    handoff: dict[str, Any], handoff_root: Path, phase: str, group_index: int
) -> Path:
    if len(handoff["entries"]) != 1:
        raise PsiMeasuredWorkloadError("phase requires exactly one predecessor export")
    entry = handoff["entries"][0]
    extracted = handoff_root / f"expanded-{phase}"
    _extract_export(_entry_archive(handoff_root, entry), extracted, phase, group_index)
    return extracted


def _export_subset(campaign: Path, export: Path, phase: str, group_index: int) -> None:
    destination_name = "summary" if phase == "summary-shards" else "verify"
    destination = export / "payload" / destination_name
    destination.mkdir(mode=0o700, parents=True)
    for leaf in grouped_shard_indices(
        campaign, group_index=group_index, group_count=GROUP_COUNT
    ):
        source = campaign / destination_name / f"receipt-{leaf:08d}.json"
        _copy_file(source, destination / source.name)


def _trace_hash(
    *, phase: str, group_index: int, challenge: str, job_binding: str,
    input_sha256: str, retained_sha256: str, retained_tree_sha256: str,
    result_sha256: str,
) -> str:
    current = _sha(
        INITIAL_DOMAIN
        + f"phase={phase}\n".encode("ascii")
        + f"group_index={group_index}\n".encode("ascii")
        + f"challenge_nonce={challenge}\n".encode("ascii")
        + f"job_binding_sha256={job_binding}\n".encode("ascii")
        + f"input_sha256={input_sha256}\n".encode("ascii")
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


def _write_trace(
    args: argparse.Namespace, *, input_sha256: str, retained_sha256: str,
    retained_tree_sha256: str, result_sha256: str,
) -> None:
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
            group_index=args.group_index,
            challenge=args.challenge,
            job_binding=args.job_binding,
            input_sha256=input_sha256,
            retained_sha256=retained_sha256,
            retained_tree_sha256=retained_tree_sha256,
            result_sha256=result_sha256,
        ),
    }
    _write_exclusive(args.trace, canonical_json_bytes(value))


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    input_sha256, _input_size = hash_file_once(args.input)
    handoff, handoff_root = _handoff(args.handoff, args.phase, args.group_index)
    if args.work.exists():
        raise PsiMeasuredWorkloadError("psi work directory must be fresh")
    args.work.mkdir(mode=0o700, parents=True)
    campaign = args.work / "campaign"
    export = args.work / "export"
    export.mkdir(mode=0o700)
    retained_archive: Path
    retained_manifest: dict[str, Any]
    succeeded = False
    try:
        if args.phase in ("initialize", "summary-shards", "reduce-summaries"):
            _initialize(args, campaign)
        if args.phase == "summary-shards":
            if handoff["entries"]:
                raise PsiMeasuredWorkloadError("summary groups take no predecessor export")
            run_phase(
                campaign,
                phase="summary",
                shard_indices=grouped_shard_indices(
                    campaign,
                    group_index=args.group_index,
                    group_count=GROUP_COUNT,
                ),
                workers=40,
            )
            _export_subset(campaign, export, args.phase, args.group_index)
        elif args.phase == "reduce-summaries":
            _import_leaf_exports(
                handoff, handoff_root, campaign,
                source_phase="summary-shards", destination_phase="summary",
            )
            reduce_summaries(campaign)
            shutil.copytree(campaign, export / "campaign")
        elif args.phase == "verify-shards":
            predecessor = _single_predecessor(
                handoff, handoff_root, "reduce-summaries", 0
            )
            _restore_campaign(predecessor, campaign)
            run_phase(
                campaign,
                phase="verify",
                shard_indices=grouped_shard_indices(
                    campaign,
                    group_index=args.group_index,
                    group_count=GROUP_COUNT,
                ),
                workers=40,
            )
            _export_subset(campaign, export, args.phase, args.group_index)
        elif args.phase == "finalize":
            reduce_entries = [
                entry for entry in handoff["entries"]
                if entry["group_id"].endswith("::reduce-summaries")
            ]
            verify_entries = [
                entry for entry in handoff["entries"]
                if entry["group_id"].endswith("::verify-shards")
            ]
            reduce_handoff = {**handoff, "entries": reduce_entries}
            predecessor = _single_predecessor(
                reduce_handoff, handoff_root, "reduce-summaries", 0
            )
            _restore_campaign(predecessor, campaign)
            verify_handoff = {**handoff, "entries": verify_entries}
            _import_leaf_exports(
                verify_handoff, handoff_root, campaign,
                source_phase="verify-shards", destination_phase="verify",
            )
            result = finalize_campaign(campaign)
            if not result.complete or not (campaign / FINAL_NAME).is_file():
                raise PsiMeasuredWorkloadError("psi finalization did not complete")
            shutil.copytree(campaign, export / "campaign")
        elif args.phase == "semantic-replay":
            predecessor = _single_predecessor(handoff, handoff_root, "finalize", 0)
            _restore_campaign(predecessor, campaign)
            checked, artifact = write_registered_result(campaign, args.output)
            if (
                artifact["sha256"] != _sha(REGISTERED_RESULT)
                or not checked.complete
                or not checked.full_source_range
                or not checked.source_atom_replayed
            ):
                raise PsiMeasuredWorkloadError("registered psi terminal replay differed")
            retained_archive = _entry_archive(handoff_root, handoff["entries"][0])
            retained_manifest = _validate_export(predecessor, "finalize", 0)
        elif args.phase == "initialize":
            if handoff["entries"]:
                raise PsiMeasuredWorkloadError("initialization takes no predecessor export")
            shutil.copytree(campaign, export / "campaign")
        else:  # pragma: no cover - argparse and PHASES make this unreachable
            raise PsiMeasuredWorkloadError("unsupported phase")

        if args.phase != "semantic-replay":
            retained_manifest = _write_export_manifest(
                export, args.phase, args.group_index
            )
            retained_archive = args.work / "retained-export.tar"
            create_archive(export, retained_archive)
            retained_sha256, retained_size = hash_file_once(retained_archive)
            _write_exclusive(
                args.output,
                canonical_json_bytes(
                    {
                        "group_index": args.group_index,
                        "kind": "sparkinterval.azure.psi-operational-result.v1",
                        "phase": args.phase,
                        "retained_export_sha256": retained_sha256,
                        "retained_export_size_bytes": retained_size,
                        "retained_tree_sha256": retained_manifest["tree_sha256"],
                        "schema_version": 1,
                    }
                ),
            )
        retained_sha256, _retained_size = hash_file_once(retained_archive)
        result_sha256, _result_size = hash_file_once(args.output)
        _write_trace(
            args,
            input_sha256=input_sha256,
            retained_sha256=retained_sha256,
            retained_tree_sha256=retained_manifest["tree_sha256"],
            result_sha256=result_sha256,
        )
        succeeded = True
    finally:
        shutil.rmtree(handoff_root, ignore_errors=True)
        shutil.rmtree(campaign, ignore_errors=True)
        shutil.rmtree(export, ignore_errors=True)
        if not succeeded:
            shutil.rmtree(args.work, ignore_errors=True)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    input_sha256, _input_size = hash_file_once(args.input)
    result_sha256, _result_size = hash_file_once(args.output)
    temporary = Path(tempfile.mkdtemp(prefix=".psi-trace-", dir=args.trace.parent))
    try:
        if args.phase == "semantic-replay":
            if _read(args.output, 16, "registered psi result") != REGISTERED_RESULT:
                raise PsiMeasuredWorkloadError("registered psi result is not literal true")
            handoff, handoff_root = _handoff(args.handoff, args.phase, args.group_index)
            predecessor = _single_predecessor(handoff, handoff_root, "finalize", 0)
            manifest = _validate_export(predecessor, "finalize", 0)
            checked = verify_campaign(predecessor / "campaign")
            if not checked.complete or not checked.full_source_range or not checked.source_atom_replayed:
                raise PsiMeasuredWorkloadError("terminal retained campaign failed replay")
            retained_archive = _entry_archive(handoff_root, handoff["entries"][0])
        else:
            result = load_json(args.output, require_canonical=True)
            expected_fields = {
                "group_index",
                "kind",
                "phase",
                "retained_export_sha256",
                "retained_export_size_bytes",
                "retained_tree_sha256",
                "schema_version",
            }
            if (
                not isinstance(result, dict)
                or set(result) != expected_fields
                or result["kind"]
                != "sparkinterval.azure.psi-operational-result.v1"
                or result["schema_version"] != 1
                or result["phase"] != args.phase
                or result["group_index"] != args.group_index
            ):
                raise PsiMeasuredWorkloadError("psi operational result identity differs")
            retained_archive = args.work / "retained-export.tar"
            if hash_file_once(retained_archive) != (
                result["retained_export_sha256"],
                result["retained_export_size_bytes"],
            ):
                raise PsiMeasuredWorkloadError("retained export differs from result pin")
            manifest = _extract_export(
                retained_archive,
                temporary / "export",
                args.phase,
                args.group_index,
            )
            if manifest["tree_sha256"] != result["retained_tree_sha256"]:
                raise PsiMeasuredWorkloadError("retained tree differs from result pin")
            handoff_root = None
        retained_sha256, _retained_size = hash_file_once(retained_archive)
        expected = {
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
                group_index=args.group_index,
                challenge=args.challenge,
                job_binding=args.job_binding,
                input_sha256=input_sha256,
                retained_sha256=retained_sha256,
                retained_tree_sha256=manifest["tree_sha256"],
                result_sha256=result_sha256,
            ),
        }
        actual = load_json(args.trace, require_canonical=True)
        if actual != expected:
            raise PsiMeasuredWorkloadError("psi challenge work trace differs")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        if "handoff_root" in locals() and handoff_root is not None:
            shutil.rmtree(handoff_root, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--phase", choices=PHASES, required=True)
    result.add_argument("--group-index", type=int, required=True)
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--handoff", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    result.add_argument("--runner", type=Path)
    result.add_argument("--runner-source", type=Path)
    result.add_argument("--upstream-manifest", type=Path)
    return result


def _validate_args(args: argparse.Namespace) -> None:
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        _hex(args.algorithm_id.split(".")[-1], "algorithm instance suffix")
    for name in ("input", "handoff", "output", "trace", "work"):
        value = getattr(args, name)
        setattr(args, name, _safe_relative(value.as_posix(), name))
    if args.phase in ("summary-shards", "verify-shards"):
        if not 0 <= args.group_index < GROUP_COUNT:
            raise PsiMeasuredWorkloadError("worker group index must be in [0,320)")
    elif args.group_index != 0:
        raise PsiMeasuredWorkloadError("single-job phase requires group index zero")
    if args.mode == "run":
        if args.runner is None or args.runner_source is None or args.upstream_manifest is None:
            raise PsiMeasuredWorkloadError("run mode requires the closed runner/source/upstream paths")
        for name in ("runner", "runner_source", "upstream_manifest"):
            value = getattr(args, name)
            setattr(args, name, _safe_relative(value.as_posix(), name))
    elif any(
        value is not None
        for value in (args.runner, args.runner_source, args.upstream_manifest)
    ):
        raise PsiMeasuredWorkloadError("trace verification takes no executable/source override")


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
    except (PsiMeasuredWorkloadError, ArchiveError, CampaignIOError, OSError, ValueError) as error:
        print(f"psi measured workload error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
