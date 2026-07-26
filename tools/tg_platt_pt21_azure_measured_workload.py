#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Measured five-stage reference workload for PT21 finite zeta RH.

Each operational stage emits a compact retained export whose digest is placed
in the signed result.  A later materializer accepts that export only after it
verifies the predecessor's production receipt.  The terminal stage restores
the authenticated prefix plus exactly 1,236,316 independently signed shard
receipts, runs the existing fixed Merkle finalizer, and emits literal
``true`` for the registered invocation.
"""

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
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "attestation"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from tg_verifier.azure_cpu_platt_pt21_workload_factory import (  # noqa: E402
    CAMPAIGN_ID,
    CONTRACT_FILE_SHA256,
    PHASE_COUNTS,
    REFERENCE_CONTRACT_ID,
    REGISTERED_ALGORITHM_ID,
    REGISTERED_INPUT,
    REGISTERED_OUTPUT,
    SHARD_COUNT,
    make_factory,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    require_azure_measured_worker,
)
from tg_verifier.platt_zeta_campaign import (  # noqa: E402
    CAPTURED_RUNNER,
    CAPTURED_SOURCE,
    CAPTURED_UPSTREAM,
    COUNT_NAME,
    FINAL_NAME,
    PLAN_NAME,
    PREFIX_NAME,
    SHARD_DIRECTORY,
    PlattZetaCampaignError,
    campaign_status,
    finalize_campaign,
    initialize_campaign,
    run_count,
    run_prefix,
    run_shard,
)


RETAINED_ARCHIVE = "pt21-retained-export.tar"
EXPORT_KIND = "sparkinterval.azure.platt-pt21-retained-export.v1"
HANDOFF_KIND = "sparkinterval.azure.platt-pt21-phase-handoff.v1"
OPERATIONAL_RESULT_KIND = "sparkinterval.azure.platt-pt21-operational-result.v1"
TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 3
INITIAL_DOMAIN = b"sparkinterval.measured-work-trace.platt-pt21.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.measured-work-trace.platt-pt21.step.v1\n"
EXPORT_TREE_DOMAIN = b"sparkinterval/platt-pt21-retained-export-tree/v1\0"
HANDOFF_TREE_DOMAIN = b"sparkinterval/platt-pt21-phase-handoff-tree/v1\0"
MAX_CONTROL_BYTES = 64 * 1024 * 1024
MAX_PREFIX_EXPORT_BYTES = 2 * 1024**3
MAX_SHARD_EXPORT_BYTES = 16 * 1024 * 1024
MAX_FINAL_HANDOFF_BYTES = 64 * 1024**3

CHAIN_FILES: dict[str, tuple[str, ...]] = {
    "initialize": (
        PLAN_NAME,
        CAPTURED_RUNNER,
        CAPTURED_SOURCE,
        CAPTURED_UPSTREAM,
    ),
    "exact-multiplicity-count": (
        PLAN_NAME,
        CAPTURED_RUNNER,
        CAPTURED_SOURCE,
        CAPTURED_UPSTREAM,
        COUNT_NAME,
    ),
    "ordinary-low-index-prefix": (
        PLAN_NAME,
        CAPTURED_RUNNER,
        CAPTURED_SOURCE,
        CAPTURED_UPSTREAM,
        COUNT_NAME,
        PREFIX_NAME,
    ),
}


class PT21MeasuredWorkloadError(RuntimeError):
    """A phase input, retained export, replay, or fixed finalization failed."""


def _safe_relative(value: str, what: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise PT21MeasuredWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _hex(value: str, what: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise PT21MeasuredWorkloadError(f"{what} is not lowercase SHA-256 hex")
    return value


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        with path.open("rb") as source:
            raw = source.read(maximum + 1)
    except OSError as error:
        raise PT21MeasuredWorkloadError(f"cannot read {what}: {error}") from error
    if len(raw) > maximum:
        raise PT21MeasuredWorkloadError(f"{what} exceeds its byte limit")
    return raw


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0),
        0o400,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PT21MeasuredWorkloadError("short exclusive output write")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


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


def _copy_regular(source: Path, destination: Path) -> None:
    metadata = source.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise PT21MeasuredWorkloadError(
            f"retained source is linked or special: {source.name}"
        )
    raw = _read(source, MAX_PREFIX_EXPORT_BYTES, f"retained {source.name}")
    _write_exclusive(destination, raw)


def _load_canonical(path: Path, what: str, maximum: int = MAX_CONTROL_BYTES) -> dict[str, Any]:
    raw = _read(path, maximum, what)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21MeasuredWorkloadError(f"{what} is not JSON") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise PT21MeasuredWorkloadError(f"{what} is not canonical JSON")
    return value


def _tree(
    root: Path, *, domain: bytes, excluded: frozenset[str]
) -> tuple[int, int, str]:
    digest = hashlib.sha256(domain)
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir() or relative in excluded:
            continue
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PT21MeasuredWorkloadError(
                "retained tree contains a linked or special file"
            )
        file_hash, size = hash_file_once(path)
        encoded = relative.encode("utf-8")
        count += 1
        total += size
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(file_hash))
    return count, total, digest.hexdigest()


def _expected_export_paths(phase: str, shard_index: int) -> tuple[str, ...]:
    if phase in CHAIN_FILES:
        return tuple(
            sorted(f"campaign/{name}" for name in CHAIN_FILES[phase])
        )
    if phase == "platt-turing-index-shards":
        return (f"campaign/{SHARD_DIRECTORY}/receipt-{shard_index:07d}.json",)
    if phase == "finalize-merkle-certificate":
        return (f"campaign/{FINAL_NAME}",)
    raise PT21MeasuredWorkloadError("unknown retained-export phase")


def _write_export_manifest(
    root: Path, phase: str, shard_index: int
) -> dict[str, Any]:
    count, total, tree = _tree(
        root,
        domain=EXPORT_TREE_DOMAIN,
        excluded=frozenset({"export-manifest.json"}),
    )
    value = {
        "execution_contract_id": REFERENCE_CONTRACT_ID,
        "execution_contract_sha256": CONTRACT_FILE_SHA256,
        "file_count": count,
        "kind": EXPORT_KIND,
        "phase_id": phase,
        "schema_version": 1,
        "shard_index": shard_index,
        "total_bytes": total,
        "tree_sha256": tree,
    }
    _write_exclusive(root / "export-manifest.json", canonical_json_bytes(value))
    return value


def _extract_export(
    archive: Path, destination: Path, phase: str, shard_index: int
) -> dict[str, Any]:
    maximum = (
        MAX_SHARD_EXPORT_BYTES
        if phase == "platt-turing-index-shards"
        else MAX_PREFIX_EXPORT_BYTES
    )
    extract_archive(
        archive,
        destination,
        maximum_files=16,
        maximum_bytes=maximum,
    )
    manifest = _load_canonical(
        destination / "export-manifest.json", "PT21 retained export manifest"
    )
    fields = {
        "execution_contract_id",
        "execution_contract_sha256",
        "file_count",
        "kind",
        "phase_id",
        "schema_version",
        "shard_index",
        "total_bytes",
        "tree_sha256",
    }
    count, total, tree = _tree(
        destination,
        domain=EXPORT_TREE_DOMAIN,
        excluded=frozenset({"export-manifest.json"}),
    )
    actual_paths = tuple(
        path.relative_to(destination).as_posix()
        for path in sorted(destination.rglob("*"))
        if path.is_file()
        and path.relative_to(destination).as_posix() != "export-manifest.json"
    )
    if (
        set(manifest) != fields
        or manifest["kind"] != EXPORT_KIND
        or manifest["schema_version"] != 1
        or manifest["execution_contract_id"] != REFERENCE_CONTRACT_ID
        or manifest["execution_contract_sha256"] != CONTRACT_FILE_SHA256
        or manifest["phase_id"] != phase
        or manifest["shard_index"] != shard_index
        or manifest["file_count"] != count
        or manifest["total_bytes"] != total
        or manifest["tree_sha256"] != tree
        or actual_paths != _expected_export_paths(phase, shard_index)
    ):
        raise PT21MeasuredWorkloadError(
            "PT21 retained export differs from its fixed phase contract"
        )
    return manifest


def verify_retained_export_archive(
    archive: Path, *, phase: str, shard_index: int, tree_sha256: str
) -> dict[str, Any]:
    """Bounded public checker used by the control-plane materializer."""

    temporary = Path(tempfile.mkdtemp(prefix=".pt21-export-audit-"))
    try:
        manifest = _extract_export(archive, temporary / "export", phase, shard_index)
        if manifest["tree_sha256"] != tree_sha256:
            raise PT21MeasuredWorkloadError(
                "retained export tree differs from the signed operational result"
            )
        return manifest
    finally:
        _remove_tree(temporary)


def _expected_single_predecessor(phase: str) -> tuple[str, str] | None:
    return {
        "initialize": None,
        "exact-multiplicity-count": (
            f"{CAMPAIGN_ID}::initialize",
            "initialize",
        ),
        "ordinary-low-index-prefix": (
            f"{CAMPAIGN_ID}::exact-multiplicity-count",
            "exact-multiplicity-count",
        ),
        "platt-turing-index-shards": (
            f"{CAMPAIGN_ID}::ordinary-low-index-prefix",
            "ordinary-low-index-prefix",
        ),
        "finalize-merkle-certificate": (
            f"{CAMPAIGN_ID}::ordinary-low-index-prefix",
            "ordinary-low-index-prefix",
        ),
    }[phase]


def _extract_handoff(
    archive: Path, destination: Path, phase: str, shard_index: int
) -> tuple[dict[str, Any], Path]:
    maximum_files = SHARD_COUNT + 4 if phase == "finalize-merkle-certificate" else 8
    maximum_bytes = (
        MAX_FINAL_HANDOFF_BYTES
        if phase == "finalize-merkle-certificate"
        else MAX_PREFIX_EXPORT_BYTES
    )
    extract_archive(
        archive,
        destination,
        maximum_files=maximum_files,
        maximum_bytes=maximum_bytes,
    )
    manifest = _load_canonical(
        destination / "handoff.json", "PT21 phase handoff"
    )
    fields = {
        "entry",
        "file_count",
        "kind",
        "mode",
        "schema_version",
        "shard_coverage",
        "target_phase",
        "target_shard_index",
        "total_bytes",
        "tree_sha256",
    }
    count, total, tree = _tree(
        destination,
        domain=HANDOFF_TREE_DOMAIN,
        excluded=frozenset({"handoff.json"}),
    )
    if (
        set(manifest) != fields
        or manifest["kind"] != HANDOFF_KIND
        or manifest["schema_version"] != 1
        or manifest["target_phase"] != phase
        or manifest["target_shard_index"] != shard_index
        or manifest["file_count"] != count
        or manifest["total_bytes"] != total
        or manifest["tree_sha256"] != tree
    ):
        raise PT21MeasuredWorkloadError("PT21 phase handoff identity differs")
    expected = _expected_single_predecessor(phase)
    entry = manifest["entry"]
    if expected is None:
        if (
            manifest["mode"] != "empty"
            or entry is not None
            or manifest["shard_coverage"] is not None
            or count != 0
        ):
            raise PT21MeasuredWorkloadError("initialize handoff must be empty")
        return manifest, destination
    if not isinstance(entry, dict) or set(entry) != {
        "group_id",
        "path",
        "phase_id",
        "portfolio_receipt_sha256",
        "sha256",
        "shard_index",
        "size_bytes",
        "tree_sha256",
    }:
        raise PT21MeasuredWorkloadError("PT21 predecessor handoff entry differs")
    group_id, predecessor_phase = expected
    entry_path = _safe_relative(entry["path"], "predecessor entry path")
    predecessor = destination / entry_path
    if (
        entry["group_id"] != group_id
        or entry["phase_id"] != predecessor_phase
        or entry["shard_index"] != 0
        or hash_file_once(predecessor)
        != (entry["sha256"], entry["size_bytes"])
    ):
        raise PT21MeasuredWorkloadError(
            "PT21 predecessor handoff is not the reviewed phase export"
        )
    _hex(entry["tree_sha256"], "predecessor tree")
    _hex(entry["portfolio_receipt_sha256"], "predecessor receipt")
    if phase != "finalize-merkle-certificate":
        if (
            manifest["mode"] != "single-predecessor"
            or manifest["shard_coverage"] is not None
            or count != 1
        ):
            raise PT21MeasuredWorkloadError(
                "nonterminal PT21 handoff has unexpected coverage"
            )
        return manifest, destination

    coverage = manifest["shard_coverage"]
    coverage_fields = {
        "export_identity_merkle_root_sha256",
        "first_shard_index",
        "portfolio_receipt_merkle_root_sha256",
        "receipt_tree_sha256",
        "shard_count",
        "upper_shard_index_exclusive",
    }
    if (
        manifest["mode"] != "full-finalization"
        or not isinstance(coverage, dict)
        or set(coverage) != coverage_fields
        or coverage["first_shard_index"] != 0
        or coverage["upper_shard_index_exclusive"] != SHARD_COUNT
        or coverage["shard_count"] != SHARD_COUNT
        or count != SHARD_COUNT + 1
    ):
        raise PT21MeasuredWorkloadError(
            "terminal PT21 handoff does not cover exactly 1,236,316 shards"
        )
    for field in (
        "export_identity_merkle_root_sha256",
        "portfolio_receipt_merkle_root_sha256",
        "receipt_tree_sha256",
    ):
        _hex(coverage[field], f"terminal coverage {field}")
    receipt_tree = hashlib.sha256(
        b"sparkinterval/platt-pt21-final-shard-receipt-tree/v1\0"
    )
    for index in range(SHARD_COUNT):
        relative = f"shards/receipt-{index:07d}.json"
        path = destination / relative
        file_hash, size = hash_file_once(path)
        encoded = relative.encode("utf-8")
        receipt_tree.update(len(encoded).to_bytes(8, "big"))
        receipt_tree.update(encoded)
        receipt_tree.update(size.to_bytes(8, "big"))
        receipt_tree.update(bytes.fromhex(file_hash))
    if receipt_tree.hexdigest() != coverage["receipt_tree_sha256"]:
        raise PT21MeasuredWorkloadError(
            "terminal PT21 shard-receipt tree differs"
        )
    return manifest, destination


def _restore_single_predecessor(
    handoff_root: Path,
    manifest: Mapping[str, Any],
    destination: Path,
) -> dict[str, Any]:
    entry = manifest["entry"]
    assert isinstance(entry, dict)
    archive = handoff_root / _safe_relative(
        entry["path"], "predecessor entry path"
    )
    expanded = destination.parent / ".predecessor-expanded"
    export = _extract_export(
        archive,
        expanded,
        entry["phase_id"],
        entry["shard_index"],
    )
    if export["tree_sha256"] != entry["tree_sha256"]:
        raise PT21MeasuredWorkloadError(
            "predecessor export tree differs from handoff"
        )
    campaign = expanded / "campaign"
    destination.mkdir(mode=0o700, parents=True)
    for path in sorted(campaign.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(campaign)
        _copy_regular(path, destination / relative)
    _remove_tree(expanded)
    return export


def _copy_chain(campaign: Path, retained: Path, phase: str) -> None:
    target = retained / "campaign"
    for name in CHAIN_FILES[phase]:
        _copy_regular(campaign / name, target / name)


def _restore_terminal(
    handoff_root: Path,
    manifest: Mapping[str, Any],
    campaign: Path,
) -> None:
    _restore_single_predecessor(handoff_root, manifest, campaign)
    shard_root = campaign / SHARD_DIRECTORY
    shard_root.mkdir(mode=0o700)
    for index in range(SHARD_COUNT):
        _copy_regular(
            handoff_root / f"shards/receipt-{index:07d}.json",
            shard_root / f"receipt-{index:07d}.json",
        )


def _execute_phase(
    args: argparse.Namespace, retained: Path, scratch: Path
) -> dict[str, Any]:
    handoff_manifest, handoff_root = _extract_handoff(
        args.handoff, scratch / "handoff", args.phase, args.shard_index
    )
    campaign = scratch / "campaign"
    if args.phase == "initialize":
        initialize_campaign(
            runner=args.runner,
            runner_source=args.runner_source,
            upstream_manifest=args.upstream_manifest,
            output_directory=campaign,
        )
        _copy_chain(campaign, retained, args.phase)
    elif args.phase == "exact-multiplicity-count":
        _restore_single_predecessor(handoff_root, handoff_manifest, campaign)
        run_count(campaign)
        _copy_chain(campaign, retained, args.phase)
    elif args.phase == "ordinary-low-index-prefix":
        _restore_single_predecessor(handoff_root, handoff_manifest, campaign)
        run_prefix(campaign)
        _copy_chain(campaign, retained, args.phase)
    elif args.phase == "platt-turing-index-shards":
        _restore_single_predecessor(handoff_root, handoff_manifest, campaign)
        run_shard(campaign, args.shard_index)
        receipt = (
            campaign
            / SHARD_DIRECTORY
            / f"receipt-{args.shard_index:07d}.json"
        )
        _copy_regular(
            receipt,
            retained
            / "campaign"
            / SHARD_DIRECTORY
            / receipt.name,
        )
    elif args.phase == "finalize-merkle-certificate":
        _restore_terminal(handoff_root, handoff_manifest, campaign)
        status = finalize_campaign(campaign)
        if (
            status["mode"] != "full_source"
            or status["shard_count"] != SHARD_COUNT
            or status["retained_shards"] != SHARD_COUNT
            or status["count_ready"] is not True
            or status["prefix_ready"] is not True
            or status["complete"] is not True
            or status["final_ready"] is not True
        ):
            raise PT21MeasuredWorkloadError(
                "terminal PT21 finalizer did not close the full campaign"
            )
        _copy_regular(
            campaign / FINAL_NAME, retained / "campaign" / FINAL_NAME
        )
    else:
        raise PT21MeasuredWorkloadError("unknown PT21 measured phase")
    return handoff_manifest


def _semantic_export_identity(
    root: Path, phase: str, shard_index: int
) -> dict[str, Any]:
    campaign = root / "campaign"
    if phase == "initialize":
        plan = _load_canonical(campaign / PLAN_NAME, "campaign plan")
        return {
            "phase": phase,
            "plan_sha256": plan["plan_sha256"],
            "runner_sha256": plan["identities"]["runner_sha256"],
            "upstream_manifest_sha256": plan["identities"][
                "upstream_manifest_sha256"
            ],
        }
    if phase == "exact-multiplicity-count":
        count = _load_canonical(campaign / COUNT_NAME, "count receipt")
        return {
            "phase": phase,
            "plan_sha256": count["plan_sha256"],
            "semantic_sha256": count["semantic_sha256"],
        }
    if phase == "ordinary-low-index-prefix":
        count = _load_canonical(campaign / COUNT_NAME, "count receipt")
        prefix = _load_canonical(campaign / PREFIX_NAME, "prefix receipt")
        return {
            "count_semantic_sha256": count["semantic_sha256"],
            "phase": phase,
            "plan_sha256": prefix["plan_sha256"],
            "prefix_semantic_sha256": prefix["semantic_sha256"],
        }
    if phase == "platt-turing-index-shards":
        shard = _load_canonical(
            campaign
            / SHARD_DIRECTORY
            / f"receipt-{shard_index:07d}.json",
            "shard receipt",
        )
        return {
            "phase": phase,
            "plan_sha256": shard["plan_sha256"],
            "semantic_sha256": shard["semantic_sha256"],
            "shard_index": shard_index,
        }
    final_hash, final_size = hash_file_once(campaign / FINAL_NAME)
    return {
        "final_sha256": final_hash,
        "final_size_bytes": final_size,
        "phase": phase,
    }


def _operational_result(
    *,
    phase: str,
    shard_index: int,
    archive_sha256: str,
    archive_size: int,
    tree_sha256: str,
) -> bytes:
    return canonical_json_bytes(
        {
            "execution_contract_sha256": CONTRACT_FILE_SHA256,
            "kind": OPERATIONAL_RESULT_KIND,
            "phase_id": phase,
            "retained_export_sha256": archive_sha256,
            "retained_export_size_bytes": archive_size,
            "retained_tree_sha256": tree_sha256,
            "schema_version": 1,
            "shard_index": shard_index,
        }
    ).rstrip(b"\n")


def _trace_hash(
    *,
    phase: str,
    shard_index: int,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    handoff_sha256: str,
    handoff_tree_sha256: str,
    retained_sha256: str,
    retained_tree_sha256: str,
    result_sha256: str,
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
        + f"handoff_sha256={handoff_sha256}\n".encode("ascii")
        + f"handoff_tree_sha256={handoff_tree_sha256}\n".encode("ascii")
    ).hexdigest()
    current = hashlib.sha256(
        STEP_DOMAIN
        + f"previous={current}\n".encode("ascii")
        + f"retained_export_sha256={retained_sha256}\n".encode("ascii")
        + f"retained_export_tree_sha256={retained_tree_sha256}\n".encode("ascii")
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
    handoff_sha256: str,
    handoff_tree_sha256: str,
    retained_sha256: str,
    retained_tree_sha256: str,
    result_sha256: str,
) -> dict[str, Any]:
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
            phase=args.phase,
            shard_index=args.shard_index,
            challenge=args.challenge,
            job_binding=args.job_binding,
            input_sha256=input_sha256,
            handoff_sha256=handoff_sha256,
            handoff_tree_sha256=handoff_tree_sha256,
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
    factory = make_factory(args.phase, args.shard_index)
    if _read(args.input, len(factory.input_bytes), "measured input") != factory.input_bytes:
        raise PT21MeasuredWorkloadError(
            "measured PT21 input differs from its closed factory"
        )
    if args.work.exists():
        raise PT21MeasuredWorkloadError("PT21 work path must be fresh")
    retained = args.work / "retained"
    scratch = args.work / "scratch"
    retained.mkdir(mode=0o700, parents=True)
    scratch.mkdir(mode=0o700)
    complete = False
    try:
        handoff = _execute_phase(args, retained, scratch)
        export = _write_export_manifest(
            retained, args.phase, args.shard_index
        )
        archive = args.work / RETAINED_ARCHIVE
        create_archive(retained, archive)
        archive_sha256, archive_size = hash_file_once(archive)
        result = (
            REGISTERED_OUTPUT
            if factory.terminal
            else _operational_result(
                phase=args.phase,
                shard_index=args.shard_index,
                archive_sha256=archive_sha256,
                archive_size=archive_size,
                tree_sha256=export["tree_sha256"],
            )
        )
        _write_exclusive(args.output, result)
        input_sha256, _ = hash_file_once(args.input)
        handoff_sha256, _ = hash_file_once(args.handoff)
        result_sha256, _ = hash_file_once(args.output)
        trace = _trace_value(
            args,
            input_sha256=input_sha256,
            handoff_sha256=handoff_sha256,
            handoff_tree_sha256=handoff["tree_sha256"],
            retained_sha256=archive_sha256,
            retained_tree_sha256=export["tree_sha256"],
            result_sha256=result_sha256,
        )
        _write_exclusive(args.trace, canonical_json_bytes(trace))
        complete = True
    finally:
        _remove_tree(retained)
        _remove_tree(scratch)
        if not complete:
            _remove_tree(args.work)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    factory = make_factory(args.phase, args.shard_index)
    if _read(args.input, len(factory.input_bytes), "measured input") != factory.input_bytes:
        raise PT21MeasuredWorkloadError(
            "measured PT21 input differs from its closed factory"
        )
    archive = args.work / RETAINED_ARCHIVE
    archive_sha256, archive_size = hash_file_once(archive)
    retained = args.work / "trace-retained"
    fresh = args.work / "trace-fresh"
    scratch = args.work / "trace-scratch"
    try:
        export = _extract_export(
            archive, retained, args.phase, args.shard_index
        )
        stored_identity = _semantic_export_identity(
            retained, args.phase, args.shard_index
        )
        fresh.mkdir(mode=0o700)
        scratch.mkdir(mode=0o700)
        handoff = _execute_phase(args, fresh, scratch)
        fresh_identity = _semantic_export_identity(
            fresh, args.phase, args.shard_index
        )
        if fresh_identity != stored_identity:
            raise PT21MeasuredWorkloadError(
                "fresh PT21 phase replay differs from retained semantics"
            )
        expected_result = (
            REGISTERED_OUTPUT
            if factory.terminal
            else _operational_result(
                phase=args.phase,
                shard_index=args.shard_index,
                archive_sha256=archive_sha256,
                archive_size=archive_size,
                tree_sha256=export["tree_sha256"],
            )
        )
        if _read(args.output, factory.output_maximum_bytes, "measured result") != expected_result:
            raise PT21MeasuredWorkloadError("PT21 measured result differs")
        input_sha256, _ = hash_file_once(args.input)
        handoff_sha256, _ = hash_file_once(args.handoff)
        result_sha256, _ = hash_file_once(args.output)
        expected_trace = _trace_value(
            args,
            input_sha256=input_sha256,
            handoff_sha256=handoff_sha256,
            handoff_tree_sha256=handoff["tree_sha256"],
            retained_sha256=archive_sha256,
            retained_tree_sha256=export["tree_sha256"],
            result_sha256=result_sha256,
        )
        if _load_canonical(args.trace, "PT21 work trace") != expected_trace:
            raise PT21MeasuredWorkloadError("PT21 work trace differs")
    finally:
        _remove_tree(retained)
        _remove_tree(fresh)
        _remove_tree(scratch)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--phase", choices=tuple(PHASE_COUNTS), required=True)
    result.add_argument("--shard-index", type=int, required=True)
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--execution-contract", type=Path, required=True)
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
    factory = make_factory(args.phase, args.shard_index)
    if args.algorithm_id != factory.algorithm_id:
        raise PT21MeasuredWorkloadError("algorithm id differs from PT21 factory")
    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    for name in (
        "execution_contract",
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
    if hash_file_once(args.execution_contract)[0] != CONTRACT_FILE_SHA256:
        raise PT21MeasuredWorkloadError(
            "packaged PT21 execution contract differs from its source pin"
        )
    for name in ("runner", "runner_source", "upstream_manifest", "handoff"):
        path = getattr(args, name)
        if path.is_symlink() or not path.is_file():
            raise PT21MeasuredWorkloadError(
                f"{name} is not a regular non-symlink file"
            )
    if factory.terminal and (
        args.algorithm_id != REGISTERED_ALGORITHM_ID
        or factory.input_bytes != REGISTERED_INPUT
    ):
        raise PT21MeasuredWorkloadError(
            "terminal PT21 invocation identity differs"
        )


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
        PT21MeasuredWorkloadError,
        PlattZetaCampaignError,
        ValueError,
    ) as error:
        print(f"PT21 measured workload error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
