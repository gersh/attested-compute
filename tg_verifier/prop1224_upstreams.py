# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact release-archive identities for the Proposition 12.2.4 runtime."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIN_PATHS = {
    "gmp": ROOT / "specifications/GMP_6_3_PROP1224_UPSTREAM.json",
    "mpfr": ROOT / "specifications/MPFR_4_2_1_PROP1224_UPSTREAM.json",
}
TREE_DOMAIN = b"sparkinterval/upstream-source-tree/v1\0"
PIN_FIELDS = {
    "archive_filename",
    "archive_root",
    "archive_sha256",
    "archive_size_bytes",
    "kind",
    "license",
    "name",
    "required_paths",
    "source_bytes",
    "source_file_count",
    "source_tree_hash_domain",
    "source_tree_sha256",
    "source_url",
    "version",
}


class Prop1224UpstreamError(RuntimeError):
    """A release archive or extracted source tree differed from its pin."""


def load_pin(component: str) -> dict[str, Any]:
    path = PIN_PATHS.get(component)
    if path is None:
        raise Prop1224UpstreamError(f"unknown upstream component {component!r}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Prop1224UpstreamError(f"cannot load {component} pin: {error}") from error
    fields = set(value) if isinstance(value, dict) else set()
    allowed = PIN_FIELDS | {"signature_url", "signing_key_fingerprint"}
    if (
        not isinstance(value, dict)
        or not PIN_FIELDS <= fields <= allowed
        or value.get("kind") != "sparkinterval.pinned_release_archive_source.v1"
        or value.get("source_tree_hash_domain") != TREE_DOMAIN[:-1].decode("ascii")
        or not isinstance(value.get("required_paths"), list)
        or not value["required_paths"]
    ):
        raise Prop1224UpstreamError(f"malformed {component} upstream pin")
    return value


def verify_archive(path: Path, pin: dict[str, Any]) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.name != pin["archive_filename"]:
        raise Prop1224UpstreamError("upstream archive path/name differs")
    raw = path.read_bytes()
    identity = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }
    if identity != {
        "sha256": pin["archive_sha256"],
        "size_bytes": pin["archive_size_bytes"],
    }:
        raise Prop1224UpstreamError("upstream release archive differs")
    return {**identity, "filename": path.name}


def source_tree_identity(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise Prop1224UpstreamError("upstream source root is not a directory")
    digest = hashlib.sha256(TREE_DOMAIN)
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise Prop1224UpstreamError(
                f"upstream source tree contains a symlink: {relative}"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise Prop1224UpstreamError(
                f"upstream source tree contains a special file: {relative}"
            )
        raw = path.read_bytes()
        encoded = relative.encode("utf-8")
        count += 1
        total += len(raw)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return {
        "file_count": count,
        "size_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }


def verify_source(root: Path, component: str) -> dict[str, Any]:
    pin = load_pin(component)
    identity = source_tree_identity(root)
    expected = {
        "file_count": pin["source_file_count"],
        "size_bytes": pin["source_bytes"],
        "tree_sha256": pin["source_tree_sha256"],
    }
    if identity != expected:
        raise Prop1224UpstreamError(f"{component} source tree differs from its pin")
    for value in pin["required_paths"]:
        path = root / value
        if path.is_symlink() or not path.is_file():
            raise Prop1224UpstreamError(
                f"{component} source lacks required path {value!r}"
            )
    return {
        "component": component,
        "license": pin["license"],
        "name": pin["name"],
        "version": pin["version"],
        **identity,
    }


__all__ = [
    "Prop1224UpstreamError",
    "load_pin",
    "source_tree_identity",
    "verify_archive",
    "verify_source",
]
