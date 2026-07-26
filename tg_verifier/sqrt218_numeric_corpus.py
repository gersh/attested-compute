# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resolve one reviewed numeric-corpus pin to the exact Sqrt218 archive."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from .campaign_io import CampaignIOError, read_bytes_once
from .numeric_corpus import (
    MAX_CONTROL_BYTES,
    NumericCorpusError,
    parse_manifest_bytes,
    parse_pin_bytes,
    verify_snapshot,
)
from .sqrt218_contract import (
    CORPUS_CLAIM_ID,
    CORPUS_COMMITMENTS,
    CORPUS_COVERAGE_ID,
    CORPUS_ENCODING,
    CORPUS_ID,
    CORPUS_PARAMETERS,
    CORPUS_ROLE,
    LEAN_CLAIM,
    SOURCE_STATEMENT,
)


class Sqrt218CorpusError(ValueError):
    """The pin/snapshot is valid generically but not the Sqrt218 corpus."""


def _normalize_runner_snapshot_modes(
    root: Path,
    pin: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    """Restore numeric-corpus read-only modes after runner snapshotting.

    The measured runner intentionally recreates closure members as 0400/0500
    files beneath 0700 directories.  The generic corpus verifier additionally
    audits its published 0444/0555 snapshot convention, so this deterministic
    metadata-only step restores that convention inside the private run stage.
    Bytes remain bound by the measured artifact-closure manifest.
    """

    modes: dict[str, int] = {
        pin["repository"]["manifest_path"]: 0o444,
    }
    for record in manifest["payloads"]:
        modes[record["path"]] = 0o444
    for record in manifest["source_files"]:
        modes[record["path"]] = 0o555 if record["executable"] else 0o444
    directories: set[Path] = {root}
    for relative, mode in modes.items():
        path = root / PurePosixPath(relative)
        try:
            metadata = path.lstat()
        except OSError as error:
            raise Sqrt218CorpusError(
                f"cannot inspect measured corpus member {relative}: {error}"
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise Sqrt218CorpusError(
                f"measured corpus member is not a regular non-symlink file: {relative}"
            )
        os.chmod(path, mode)
        parent = path.parent
        while parent != root:
            directories.add(parent)
            parent = parent.parent
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            metadata = directory.lstat()
        except OSError as error:
            raise Sqrt218CorpusError(
                f"cannot inspect measured corpus directory {directory}: {error}"
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise Sqrt218CorpusError(
                f"measured corpus path is not a non-symlink directory: {directory}"
            )
        os.chmod(directory, 0o555)


def require_sqrt218_manifest(
    pin: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    claim = manifest["claim"]
    if (
        pin["expected"]["claim_id"] != CORPUS_CLAIM_ID
        or pin["expected"]["claim_version"] != 1
        or pin["expected"]["corpus_id"] != CORPUS_ID
        or pin["expected"]["corpus_version"] != 1
        or claim["claim_id"] != CORPUS_CLAIM_ID
        or claim["claim_version"] != 1
        or claim["lean_theorem"] != LEAN_CLAIM
        or claim["lean_type"] != LEAN_CLAIM
        or claim["statement"] != SOURCE_STATEMENT
        or manifest["corpus_id"] != CORPUS_ID
        or manifest["corpus_version"] != 1
        or manifest["parameters"] != CORPUS_PARAMETERS
        or manifest["payload_prefix"] != "corpus/payloads"
    ):
        raise Sqrt218CorpusError(
            "numeric-corpus identity, claim, statement, or parameters differ "
            "from the closed Sqrt218 protocol"
        )
    expected_coverage = [
        {
            "axis": "certificate_archive",
            "coverage_id": CORPUS_COVERAGE_ID,
            "index_start": 0,
            "index_stop": 1,
            "role": CORPUS_ROLE,
        }
    ]
    if manifest["coverage"] != expected_coverage or len(manifest["payloads"]) != 1:
        raise Sqrt218CorpusError(
            "Sqrt218 corpus must contain exactly one complete archive payload"
        )
    payload = manifest["payloads"][0]
    if (
        payload["coverage_id"] != CORPUS_COVERAGE_ID
        or payload["encoding"] != CORPUS_ENCODING
        or payload["index_start"] != 0
        or payload["index_stop"] != 1
        or payload["role"] != CORPUS_ROLE
        or payload["row_count"] != 1
    ):
        raise Sqrt218CorpusError(
            "Sqrt218 corpus payload does not have the closed archive semantics"
        )
    expected_commitments = [
        {"hash_domain": domain, "name": name, "sha256": digest}
        for name, domain, digest in CORPUS_COMMITMENTS
    ]
    if manifest["semantic_commitments"] != expected_commitments:
        raise Sqrt218CorpusError(
            "Sqrt218 corpus semantic commitments differ from the registered pins"
        )
    return payload


def resolve_verified_archive(
    pin_raw: bytes,
    snapshot_root: Path,
) -> tuple[Path, dict[str, Any]]:
    """Verify the exact pin/snapshot and return its sole certificate archive."""

    try:
        pin = parse_pin_bytes(pin_raw, label="measured Sqrt218 corpus pin")
        manifest_path = snapshot_root / PurePosixPath(
            pin["repository"]["manifest_path"]
        )
        manifest_raw = read_bytes_once(manifest_path, limit=MAX_CONTROL_BYTES)
        manifest = parse_manifest_bytes(
            manifest_raw,
            pin=pin,
            label="measured Sqrt218 corpus manifest",
        )
        payload = require_sqrt218_manifest(pin, manifest)
        _normalize_runner_snapshot_modes(snapshot_root, pin, manifest)
        verification = verify_snapshot(snapshot_root, pin, manifest)
    except (CampaignIOError, NumericCorpusError, OSError) as error:
        raise Sqrt218CorpusError(str(error)) from error
    archive_path = snapshot_root / PurePosixPath(payload["path"])
    return archive_path, {
        "claim_id": pin["expected"]["claim_id"],
        "corpus_id": pin["expected"]["corpus_id"],
        "manifest_sha256": verification["manifest_sha256"],
        "payload_root_sha256": verification["payload_root_sha256"],
        "pin_id": pin["pin_id"],
        "pin_sha256": hashlib.sha256(pin_raw).hexdigest(),
        "repository_commit": pin["repository"]["commit"],
        "source_root_sha256": verification["source_root_sha256"],
    }
