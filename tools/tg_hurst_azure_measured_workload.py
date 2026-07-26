#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed measured-workload adapter for the shared Hurst Azure CPU DAG.

Operational phases return canonical JSON which pins a deterministic retained
archive and the exact runner, adapter source, and upstream manifest bytes.
Every consumer checks those identities again before accepting a handoff.  The
terminal independently replays the complete full-source campaign and is the
only phase permitted to emit the registered literal ``true``.
"""

from __future__ import annotations

import argparse
import hashlib
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
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    read_bytes_once,
    require_azure_measured_worker,
)
from tg_verifier.hurst_residual_campaign import (  # noqa: E402
    FINAL_NAME,
    REGISTERED_RESULT,
    UPSTREAM_COMMIT,
    finalize_campaign,
    grouped_shard_indices,
    initialize_campaign,
    reduce_summaries,
    run_phase,
    verify_campaign,
    write_registered_result,
)
from tg_verifier.hurst_candidate_artifact import (  # noqa: E402
    arithmetic_check as candidate_arithmetic_check,
    candidate_from_replayed_campaign,
    decode_candidate,
    encode_candidate,
    manifest_bytes as candidate_manifest_bytes,
)


PHASES = (
    "initialize",
    "summary-shards",
    "reduce-summaries",
    "verify-shards",
    "finalize-four-residual-certificate",
    "semantic-replay",
)
CAMPAIGN_ID = "hurst-four-residuals-v1"
GROUP_COUNT = 320
LEAF_COUNT = 10_000
GROUP_LOCAL_WORKERS = 2
GROUP_RUNNER_THREADS = 20
MAX_EXPORT_FILES = 100_100
MAX_EXPORT_BYTES = 128 * 1024**3
TRACE_ITERATIONS = 2
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
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.hurst-shared-four-residual.v2"
)
HANDOFF_KIND = "sparkinterval.azure.hurst-phase-handoff.v1"
EXPORT_KIND = "sparkinterval.azure.hurst-retained-export.v1"
OPERATIONAL_RESULT_KIND = "sparkinterval.azure.hurst-operational-result.v1"
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.hurst.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.hurst.step.v1\n"
TREE_DOMAIN = b"sparkinterval/hurst-retained-tree/v1\0"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTITY_FIELDS = {
    "runner_sha256",
    "runner_size_bytes",
    "source_sha256",
    "source_size_bytes",
    "upstream_manifest_sha256",
    "upstream_manifest_size_bytes",
}
CANDIDATE_ARTIFACT_PATH = Path("candidate/hurst-candidate-artifact.bin")
CANDIDATE_MANIFEST_PATH = Path(
    "candidate/hurst-candidate-artifact-manifest.json"
)
MAX_CANDIDATE_BYTES = 8 * 1024**2


class HurstMeasuredWorkloadError(RuntimeError):
    """The closed Hurst phase or its independent replay failed."""


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
        raise HurstMeasuredWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _hex(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise HurstMeasuredWorkloadError(f"{what} must be lowercase SHA-256 hex")
    return value


def _plain_int(value: Any, what: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HurstMeasuredWorkloadError(f"{what} must be an integer >= {minimum}")
    return value


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as error:
        raise HurstMeasuredWorkloadError(f"cannot read {what}: {error}") from error


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o400)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise HurstMeasuredWorkloadError(f"short write: {path}")
            view = view[count:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _file_identity(args: argparse.Namespace) -> dict[str, Any]:
    runner_sha, runner_size = hash_file_once(args.runner, limit=1 << 30)
    source_sha, source_size = hash_file_once(args.runner_source, limit=32 << 20)
    upstream_sha, upstream_size = hash_file_once(
        args.upstream_manifest, limit=32 << 20
    )
    upstream = load_json(args.upstream_manifest, require_canonical=False)
    if (
        not isinstance(upstream, dict)
        or upstream.get("kind") != "sparkinterval.pinned_upstream_source.v1"
        or upstream.get("commit") != UPSTREAM_COMMIT
        or not isinstance(upstream.get("files"), list)
        or not upstream["files"]
    ):
        raise HurstMeasuredWorkloadError("Hurst upstream manifest differs from the pin")
    return {
        "runner_sha256": runner_sha,
        "runner_size_bytes": runner_size,
        "source_sha256": source_sha,
        "source_size_bytes": source_size,
        "upstream_manifest_sha256": upstream_sha,
        "upstream_manifest_size_bytes": upstream_size,
    }


def _validate_identity(value: Mapping[str, Any], what: str) -> dict[str, Any]:
    if set(value) != IDENTITY_FIELDS:
        raise HurstMeasuredWorkloadError(f"{what} identity fields changed")
    for name in ("runner_sha256", "source_sha256", "upstream_manifest_sha256"):
        _hex(value[name], f"{what} {name}")
    for name in (
        "runner_size_bytes",
        "source_size_bytes",
        "upstream_manifest_size_bytes",
    ):
        _plain_int(value[name], f"{what} {name}", minimum=1)
    return dict(value)


def _campaign_identity(campaign: Path, identity: Mapping[str, Any]) -> None:
    checked = verify_campaign(campaign)
    config = load_json(campaign / "campaign-config.json", require_canonical=True)
    if (
        checked.runner_sha256 != identity["runner_sha256"]
        or checked.source_sha256 != identity["source_sha256"]
        or not isinstance(config, dict)
        or config.get("upstream_manifest_sha256")
        != identity["upstream_manifest_sha256"]
        or config.get("captured_runner_size") != identity["runner_size_bytes"]
        or config.get("captured_source_size") != identity["source_size_bytes"]
    ):
        raise HurstMeasuredWorkloadError(
            "retained campaign does not use the measured runner/source identities"
        )


def _tree_rows(
    root: Path, *, exclude_manifest: bool = False
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise HurstMeasuredWorkloadError(
                f"retained tree contains a linked or special file: {relative}"
            )
        if exclude_manifest and relative == "export-manifest.json":
            continue
        digest, size = hash_file_once(path)
        rows.append({"path": relative, "sha256": digest, "size_bytes": size})
        total += size
    return rows, total


def _tree_digest(rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256(TREE_DOMAIN)
    for row in rows:
        encoded = row["path"].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(row["size_bytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(row["sha256"]))
    return digest.hexdigest()


def _write_export_manifest(
    root: Path,
    phase: str,
    group_index: int,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    rows, total = _tree_rows(root)
    manifest = {
        "file_count": len(rows),
        "group_index": group_index,
        **identity,
        "kind": EXPORT_KIND,
        "phase": phase,
        "schema_version": 1,
        "total_bytes": total,
        "tree_sha256": _tree_digest(rows),
    }
    _write_exclusive(root / "export-manifest.json", canonical_json_bytes(manifest))
    return manifest


def _validate_export(
    root: Path,
    phase: str,
    group_index: int,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        manifest = load_json(root / "export-manifest.json", require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HurstMeasuredWorkloadError(
            f"invalid retained export manifest: {error}"
        ) from error
    fields = {
        "file_count",
        "group_index",
        "kind",
        "phase",
        "schema_version",
        "total_bytes",
        "tree_sha256",
        *IDENTITY_FIELDS,
    }
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise HurstMeasuredWorkloadError("retained export manifest fields changed")
    if (
        manifest["kind"] != EXPORT_KIND
        or manifest["schema_version"] != 1
        or manifest["phase"] != phase
        or manifest["group_index"] != group_index
        or {name: manifest[name] for name in IDENTITY_FIELDS} != dict(identity)
    ):
        raise HurstMeasuredWorkloadError("retained export identity differs")
    rows, total = _tree_rows(root, exclude_manifest=True)
    if (
        manifest["file_count"] != len(rows)
        or manifest["total_bytes"] != total
        or manifest["tree_sha256"] != _tree_digest(rows)
    ):
        raise HurstMeasuredWorkloadError(
            "retained export tree differs from its manifest"
        )
    return manifest


def _extract_export(
    archive: Path,
    destination: Path,
    phase: str,
    index: int,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        extract_archive(
            archive,
            destination,
            maximum_files=MAX_EXPORT_FILES,
            maximum_bytes=MAX_EXPORT_BYTES,
        )
    except ArchiveError as error:
        raise HurstMeasuredWorkloadError(
            f"cannot extract retained export: {error}"
        ) from error
    return _validate_export(destination, phase, index, identity)


def _handoff(
    path: Path,
    phase: str,
    group_index: int,
    identity: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    root = path.parent / f".{path.name}.extracted"
    _safe_relative(root.as_posix(), "handoff extraction path")
    try:
        extract_archive(path, root, maximum_files=400, maximum_bytes=MAX_EXPORT_BYTES)
        value = load_json(root / "handoff.json", require_canonical=True)
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        raise HurstMeasuredWorkloadError(f"invalid phase handoff: {error}") from error
    fields = {"entries", "group_index", "kind", "phase", "schema_version"}
    if not isinstance(value, dict) or set(value) != fields:
        raise HurstMeasuredWorkloadError("phase handoff fields changed")
    if (
        value["kind"] != HANDOFF_KIND
        or value["schema_version"] != 1
        or value["phase"] != phase
        or value["group_index"] != group_index
        or not isinstance(value["entries"], list)
    ):
        raise HurstMeasuredWorkloadError("phase handoff identity differs")
    entry_fields = {
        "group_id",
        "path",
        "sha256",
        "shard_index",
        "size_bytes",
        *IDENTITY_FIELDS,
    }
    seen: set[tuple[str, int]] = set()
    for entry in value["entries"]:
        if not isinstance(entry, dict) or set(entry) != entry_fields:
            raise HurstMeasuredWorkloadError("phase handoff entry fields changed")
        key = (entry["group_id"], entry["shard_index"])
        if (
            not isinstance(key[0], str)
            or not key[0]
            or isinstance(key[1], bool)
            or not isinstance(key[1], int)
            or key[1] < 0
            or key in seen
        ):
            raise HurstMeasuredWorkloadError("phase handoff identity is malformed")
        seen.add(key)
        relative = _safe_relative(entry["path"], "predecessor export path")
        candidate = root / relative
        if hash_file_once(candidate) != (entry["sha256"], entry["size_bytes"]):
            raise HurstMeasuredWorkloadError(
                "predecessor export differs from its handoff pin"
            )
        predecessor_identity = {
            name: entry[name] for name in IDENTITY_FIELDS
        }
        _validate_identity(predecessor_identity, "predecessor")
        if predecessor_identity != dict(identity):
            raise HurstMeasuredWorkloadError(
                "predecessor was built from different runner/source bytes"
            )
    return value, root


def _copy_file(source: Path, destination: Path) -> None:
    _write_exclusive(destination, _read(source, 4 << 20, "retained leaf"))


def _initialize(args: argparse.Namespace, campaign: Path) -> None:
    result = initialize_campaign(
        runner=args.runner,
        runner_source=args.runner_source,
        upstream_manifest=args.upstream_manifest,
        output_directory=campaign,
    )
    if result.mode != "full_source" or result.shard_count != LEAF_COUNT:
        raise HurstMeasuredWorkloadError(
            "Hurst initialization did not create the literal source plan"
        )


def _restore_campaign(export_root: Path, campaign: Path) -> None:
    source = export_root / "campaign"
    if campaign.exists() or not source.is_dir():
        raise HurstMeasuredWorkloadError(
            "predecessor lacks one fresh campaign snapshot"
        )
    shutil.copytree(source, campaign)


def _entry_archive(handoff_root: Path, entry: Mapping[str, Any]) -> Path:
    return handoff_root / _safe_relative(entry["path"], "predecessor export path")


def _expected_group(phase: str) -> str:
    return f"{CAMPAIGN_ID}::{phase}"


def _expected_handoff_keys(phase: str) -> set[tuple[str, int]]:
    if phase == "initialize":
        return set()
    if phase == "summary-shards":
        return {(_expected_group("initialize"), 0)}
    if phase == "reduce-summaries":
        return {
            (_expected_group("summary-shards"), index)
            for index in range(GROUP_COUNT)
        }
    if phase == "verify-shards":
        return {(_expected_group("reduce-summaries"), 0)}
    if phase == "finalize-four-residual-certificate":
        return {
            (_expected_group("reduce-summaries"), 0),
            *((_expected_group("verify-shards"), index) for index in range(GROUP_COUNT)),
        }
    return {(_expected_group("finalize-four-residual-certificate"), 0)}


def _validate_handoff_shape(handoff: Mapping[str, Any], phase: str) -> None:
    actual = {
        (entry["group_id"], entry["shard_index"])
        for entry in handoff["entries"]
    }
    expected = _expected_handoff_keys(phase)
    if actual != expected or len(handoff["entries"]) != len(expected):
        raise HurstMeasuredWorkloadError(
            "phase handoff does not exactly cover its reviewed predecessors"
        )


def _single_predecessor(
    handoff: Mapping[str, Any],
    handoff_root: Path,
    *,
    source_phase: str,
    identity: Mapping[str, Any],
) -> Path:
    entries = handoff["entries"]
    if len(entries) != 1:
        raise HurstMeasuredWorkloadError("phase requires exactly one predecessor")
    entry = entries[0]
    if (
        entry["group_id"] != _expected_group(source_phase)
        or entry["shard_index"] != 0
    ):
        raise HurstMeasuredWorkloadError("single predecessor has the wrong phase")
    extracted = handoff_root / f"expanded-{source_phase}"
    _extract_export(
        _entry_archive(handoff_root, entry),
        extracted,
        source_phase,
        0,
        identity,
    )
    return extracted


def _import_leaf_exports(
    handoff: Mapping[str, Any],
    handoff_root: Path,
    campaign: Path,
    *,
    source_phase: str,
    destination_phase: str,
    identity: Mapping[str, Any],
) -> None:
    expected = {(_expected_group(source_phase), index) for index in range(GROUP_COUNT)}
    actual = {(entry["group_id"], entry["shard_index"]) for entry in handoff["entries"]}
    if actual != expected or len(handoff["entries"]) != GROUP_COUNT:
        raise HurstMeasuredWorkloadError(
            f"{source_phase} predecessor set does not cover 320 groups"
        )
    destination = campaign / destination_phase
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for entry in sorted(handoff["entries"], key=lambda row: row["shard_index"]):
        index = entry["shard_index"]
        extracted = handoff_root / f"expanded-{source_phase}-{index:03d}"
        _extract_export(
            _entry_archive(handoff_root, entry),
            extracted,
            source_phase,
            index,
            identity,
        )
        leaf_root = extracted / "payload" / destination_phase
        if not leaf_root.is_dir():
            raise HurstMeasuredWorkloadError("leaf export payload is absent")
        wanted = {
            f"receipt-{leaf:08d}.json"
            for leaf in range(index, LEAF_COUNT, GROUP_COUNT)
        }
        files = {path.name for path in leaf_root.iterdir() if path.is_file()}
        if files != wanted:
            raise HurstMeasuredWorkloadError(
                "leaf export does not match its exact strided group"
            )
        for name in sorted(files):
            _copy_file(leaf_root / name, destination / name)
        shutil.rmtree(extracted)


def _export_subset(campaign: Path, export: Path, phase: str, group_index: int) -> None:
    destination_name = "summary" if phase == "summary-shards" else "verify"
    destination = export / "payload" / destination_name
    destination.mkdir(mode=0o700, parents=True)
    for leaf in grouped_shard_indices(
        campaign, group_index=group_index, group_count=GROUP_COUNT
    ):
        source = campaign / destination_name / f"receipt-{leaf:08d}.json"
        _copy_file(source, destination / source.name)


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
    *,
    phase: str,
    group_index: int,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    identity: Mapping[str, Any],
    retained_sha256: str,
    retained_tree_sha256: str,
    result_sha256: str,
    candidate: Mapping[str, Any] | None,
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
        + f"runner_sha256={identity['runner_sha256']}\n".encode("ascii")
        + f"source_sha256={identity['source_sha256']}\n".encode("ascii")
        + (
            f"upstream_manifest_sha256={identity['upstream_manifest_sha256']}\n"
        ).encode("ascii")
        + f"retained_archive_sha256={retained_sha256}\n".encode("ascii")
        + f"retained_tree_sha256={retained_tree_sha256}\n".encode("ascii")
        + _candidate_hash_bytes(candidate)
    )
    return _sha(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"result_sha256={result_sha256}\n".encode("ascii")
    )


def _write_trace(
    args: argparse.Namespace,
    *,
    input_sha256: str,
    identity: Mapping[str, Any],
    retained_sha256: str,
    retained_tree_sha256: str,
    result_sha256: str,
    candidate: Mapping[str, Any] | None,
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
            identity=identity,
            retained_sha256=retained_sha256,
            retained_tree_sha256=retained_tree_sha256,
            result_sha256=result_sha256,
            candidate=candidate,
        ),
    }
    _write_exclusive(args.trace, canonical_json_bytes(value))


def _operational_result(
    args: argparse.Namespace,
    identity: Mapping[str, Any],
    retained_sha256: str,
    retained_size: int,
    retained_tree_sha256: str,
) -> dict[str, Any]:
    return {
        "group_index": args.group_index,
        **identity,
        "kind": OPERATIONAL_RESULT_KIND,
        "phase": args.phase,
        "retained_export_sha256": retained_sha256,
        "retained_export_size_bytes": retained_size,
        "retained_tree_sha256": retained_tree_sha256,
        "schema_version": 1,
    }


def _candidate_identity(root: Path) -> dict[str, Any]:
    artifact = root / CANDIDATE_ARTIFACT_PATH
    manifest = root / CANDIDATE_MANIFEST_PATH
    raw = _read(artifact, MAX_CANDIDATE_BYTES, "Hurst candidate artifact")
    certificate = decode_candidate(raw)
    if not candidate_arithmetic_check(certificate):
        raise HurstMeasuredWorkloadError(
            "Hurst candidate fails its Lean arithmetic boundary"
        )
    expected_manifest = candidate_manifest_bytes(
        CANDIDATE_ARTIFACT_PATH.as_posix(), raw
    )
    if _read(
        manifest, 256 * 1024, "Hurst candidate manifest"
    ) != expected_manifest:
        raise HurstMeasuredWorkloadError(
            "Hurst candidate manifest differs from its exact bytes"
        )
    return {
        "manifest_path": CANDIDATE_MANIFEST_PATH.as_posix(),
        "manifest_sha256": hashlib.sha256(expected_manifest).hexdigest(),
        "path": CANDIDATE_ARTIFACT_PATH.as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "status": "arithmetic-chain-only-not-semantic-closure",
    }


def _write_candidate_after_replay(root: Path, raw: bytes) -> dict[str, Any]:
    certificate = decode_candidate(raw)
    if not candidate_arithmetic_check(certificate):
        raise HurstMeasuredWorkloadError(
            "refusing to retain an invalid Hurst arithmetic candidate"
        )
    _write_exclusive(root / CANDIDATE_ARTIFACT_PATH, raw)
    _write_exclusive(
        root / CANDIDATE_MANIFEST_PATH,
        candidate_manifest_bytes(CANDIDATE_ARTIFACT_PATH.as_posix(), raw),
    )
    return _candidate_identity(root)


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    input_sha256, _input_size = hash_file_once(args.input)
    identity = _file_identity(args)
    handoff, handoff_root = _handoff(
        args.handoff, args.phase, args.group_index, identity
    )
    _validate_handoff_shape(handoff, args.phase)
    if args.work.exists():
        raise HurstMeasuredWorkloadError("Hurst work directory must be fresh")
    args.work.mkdir(mode=0o700, parents=True)
    campaign = args.work / "campaign"
    export = args.work / "export"
    export.mkdir(mode=0o700)
    candidate: Mapping[str, Any] | None = None
    succeeded = False
    try:
        if args.phase in ("initialize", "reduce-summaries"):
            _initialize(args, campaign)

        if args.phase == "initialize":
            if handoff["entries"]:
                raise HurstMeasuredWorkloadError(
                    "initialization takes no predecessor export"
                )
            _campaign_identity(campaign, identity)
            shutil.copytree(campaign, export / "campaign")
        elif args.phase == "summary-shards":
            predecessor = _single_predecessor(
                handoff,
                handoff_root,
                source_phase="initialize",
                identity=identity,
            )
            _restore_campaign(predecessor, campaign)
            _campaign_identity(campaign, identity)
            run_phase(
                campaign,
                phase="summary",
                shard_indices=grouped_shard_indices(
                    campaign,
                    group_index=args.group_index,
                    group_count=GROUP_COUNT,
                ),
                workers=GROUP_LOCAL_WORKERS,
                runner_threads=GROUP_RUNNER_THREADS,
            )
            _campaign_identity(campaign, identity)
            _export_subset(campaign, export, args.phase, args.group_index)
        elif args.phase == "reduce-summaries":
            _import_leaf_exports(
                handoff,
                handoff_root,
                campaign,
                source_phase="summary-shards",
                destination_phase="summary",
                identity=identity,
            )
            reduce_summaries(campaign)
            _campaign_identity(campaign, identity)
            shutil.copytree(campaign, export / "campaign")
        elif args.phase == "verify-shards":
            predecessor = _single_predecessor(
                handoff,
                handoff_root,
                source_phase="reduce-summaries",
                identity=identity,
            )
            _restore_campaign(predecessor, campaign)
            _campaign_identity(campaign, identity)
            run_phase(
                campaign,
                phase="verify",
                shard_indices=grouped_shard_indices(
                    campaign,
                    group_index=args.group_index,
                    group_count=GROUP_COUNT,
                ),
                workers=GROUP_LOCAL_WORKERS,
                runner_threads=GROUP_RUNNER_THREADS,
            )
            _campaign_identity(campaign, identity)
            _export_subset(campaign, export, args.phase, args.group_index)
        elif args.phase == "finalize-four-residual-certificate":
            reduce_entries = [
                entry
                for entry in handoff["entries"]
                if entry["group_id"] == _expected_group("reduce-summaries")
            ]
            verify_entries = [
                entry
                for entry in handoff["entries"]
                if entry["group_id"] == _expected_group("verify-shards")
            ]
            if len(reduce_entries) != 1 or len(verify_entries) != GROUP_COUNT:
                raise HurstMeasuredWorkloadError(
                    "finalizer needs one reducer and all 320 verify groups"
                )
            predecessor = _single_predecessor(
                {**handoff, "entries": reduce_entries},
                handoff_root,
                source_phase="reduce-summaries",
                identity=identity,
            )
            _restore_campaign(predecessor, campaign)
            _import_leaf_exports(
                {**handoff, "entries": verify_entries},
                handoff_root,
                campaign,
                source_phase="verify-shards",
                destination_phase="verify",
                identity=identity,
            )
            result = finalize_campaign(campaign)
            if not result.complete or not (campaign / FINAL_NAME).is_file():
                raise HurstMeasuredWorkloadError(
                    "Hurst four-residual finalization did not complete"
                )
            _campaign_identity(campaign, identity)
            shutil.copytree(campaign, export / "campaign")
        elif args.phase == "semantic-replay":
            predecessor = _single_predecessor(
                handoff,
                handoff_root,
                source_phase="finalize-four-residual-certificate",
                identity=identity,
            )
            _restore_campaign(predecessor, campaign)
            _campaign_identity(campaign, identity)
            candidate_raw = encode_candidate(
                candidate_from_replayed_campaign(campaign)
            )
            checked, artifact = write_registered_result(campaign, args.output)
            if (
                artifact["sha256"] != _sha(REGISTERED_RESULT)
                or not checked.complete
                or not checked.full_source_range
                or not checked.source_residuals_replayed
            ):
                raise HurstMeasuredWorkloadError(
                    "registered Hurst terminal replay differed"
                )
            candidate = _write_candidate_after_replay(args.work, candidate_raw)
            retained_archive = _entry_archive(handoff_root, handoff["entries"][0])
            retained_manifest = _validate_export(
                predecessor,
                "finalize-four-residual-certificate",
                0,
                identity,
            )
        else:  # pragma: no cover
            raise HurstMeasuredWorkloadError("unsupported phase")

        if args.phase != "semantic-replay":
            retained_manifest = _write_export_manifest(
                export, args.phase, args.group_index, identity
            )
            retained_archive = args.work / "retained-export.tar"
            create_archive(export, retained_archive)
            retained_sha256, retained_size = hash_file_once(retained_archive)
            _write_exclusive(
                args.output,
                canonical_json_bytes(
                    _operational_result(
                        args,
                        identity,
                        retained_sha256,
                        retained_size,
                        retained_manifest["tree_sha256"],
                    )
                ),
            )
        retained_sha256, _retained_size = hash_file_once(retained_archive)
        result_sha256, _result_size = hash_file_once(args.output)
        _write_trace(
            args,
            input_sha256=input_sha256,
            identity=identity,
            retained_sha256=retained_sha256,
            retained_tree_sha256=retained_manifest["tree_sha256"],
            result_sha256=result_sha256,
            candidate=candidate,
        )
        succeeded = True
    finally:
        shutil.rmtree(handoff_root, ignore_errors=True)
        shutil.rmtree(campaign, ignore_errors=True)
        shutil.rmtree(export, ignore_errors=True)
        if not succeeded:
            shutil.rmtree(args.work, ignore_errors=True)


def _validate_operational_result(
    value: Any,
    args: argparse.Namespace,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "group_index",
        "kind",
        "phase",
        "retained_export_sha256",
        "retained_export_size_bytes",
        "retained_tree_sha256",
        "schema_version",
        *IDENTITY_FIELDS,
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["kind"] != OPERATIONAL_RESULT_KIND
        or value["schema_version"] != 1
        or value["phase"] != args.phase
        or value["group_index"] != args.group_index
        or {name: value[name] for name in IDENTITY_FIELDS} != dict(identity)
    ):
        raise HurstMeasuredWorkloadError("Hurst operational result differs")
    _hex(value["retained_export_sha256"], "retained export digest")
    _hex(value["retained_tree_sha256"], "retained tree digest")
    _plain_int(value["retained_export_size_bytes"], "retained export size", minimum=1)
    return value


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    input_sha256, _input_size = hash_file_once(args.input)
    result_sha256, _result_size = hash_file_once(args.output)
    identity = _file_identity(args)
    temporary = Path(tempfile.mkdtemp(prefix=".hurst-trace-", dir=args.trace.parent))
    handoff_root: Path | None = None
    try:
        handoff, handoff_root = _handoff(
            args.handoff, args.phase, args.group_index, identity
        )
        _validate_handoff_shape(handoff, args.phase)
        if args.phase == "semantic-replay":
            if _read(args.output, 16, "registered Hurst result") != REGISTERED_RESULT:
                raise HurstMeasuredWorkloadError(
                    "registered Hurst result is not literal true"
                )
            predecessor = _single_predecessor(
                handoff,
                handoff_root,
                source_phase="finalize-four-residual-certificate",
                identity=identity,
            )
            manifest = _validate_export(
                predecessor,
                "finalize-four-residual-certificate",
                0,
                identity,
            )
            checked = verify_campaign(predecessor / "campaign")
            if (
                not checked.complete
                or not checked.full_source_range
                or not checked.source_residuals_replayed
            ):
                raise HurstMeasuredWorkloadError(
                    "terminal retained Hurst campaign failed independent replay"
                )
            _campaign_identity(predecessor / "campaign", identity)
            expected_candidate = encode_candidate(
                candidate_from_replayed_campaign(predecessor / "campaign")
            )
            actual_candidate = _read(
                args.work / CANDIDATE_ARTIFACT_PATH,
                MAX_CANDIDATE_BYTES,
                "Hurst candidate artifact",
            )
            if actual_candidate != expected_candidate:
                raise HurstMeasuredWorkloadError(
                    "Hurst candidate differs from the independently replayed chain"
                )
            candidate: Mapping[str, Any] | None = _candidate_identity(args.work)
            retained_archive = _entry_archive(handoff_root, handoff["entries"][0])
        else:
            result = _validate_operational_result(
                load_json(args.output, require_canonical=True), args, identity
            )
            retained_archive = args.work / "retained-export.tar"
            if hash_file_once(retained_archive) != (
                result["retained_export_sha256"],
                result["retained_export_size_bytes"],
            ):
                raise HurstMeasuredWorkloadError(
                    "retained export differs from the signed result pin"
                )
            manifest = _extract_export(
                retained_archive,
                temporary / "export",
                args.phase,
                args.group_index,
                identity,
            )
            if manifest["tree_sha256"] != result["retained_tree_sha256"]:
                raise HurstMeasuredWorkloadError(
                    "retained tree differs from the result pin"
                )
            candidate = None
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
                identity=identity,
                retained_sha256=retained_sha256,
                retained_tree_sha256=manifest["tree_sha256"],
                result_sha256=result_sha256,
                candidate=candidate,
            ),
        }
        actual = load_json(args.trace, require_canonical=True)
        if actual != expected:
            raise HurstMeasuredWorkloadError("Hurst challenge work trace differs")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        if handoff_root is not None:
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
    result.add_argument("--runner", type=Path, required=True)
    result.add_argument("--runner-source", type=Path, required=True)
    result.add_argument("--upstream-manifest", type=Path, required=True)
    return result


def _validate_args(args: argparse.Namespace) -> None:
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        _hex(args.algorithm_id.rsplit(".", 1)[-1], "algorithm instance suffix")
    for name in (
        "input",
        "handoff",
        "output",
        "trace",
        "work",
        "runner",
        "runner_source",
        "upstream_manifest",
    ):
        value = getattr(args, name)
        setattr(args, name, _safe_relative(value.as_posix(), name))
    if args.phase in ("summary-shards", "verify-shards"):
        if not 0 <= args.group_index < GROUP_COUNT:
            raise HurstMeasuredWorkloadError(
                "worker group index must be in [0,320)"
            )
    elif args.group_index != 0:
        raise HurstMeasuredWorkloadError("single-job phase requires group index zero")


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
    except (
        HurstMeasuredWorkloadError,
        ArchiveError,
        CampaignIOError,
        OSError,
        ValueError,
    ) as error:
        print(f"Hurst measured workload error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
