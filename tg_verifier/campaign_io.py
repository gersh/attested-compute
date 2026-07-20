# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Canonical, crash-safe I/O for ternary-Goldbach campaign metadata.

Campaign JSON is control-plane input.  It is therefore parsed without binary
floating point, duplicate keys, or non-finite constants.  Immutable plans are
content addressed; mutable status files are replaced atomically while holding
an advisory lock in the same directory.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Iterator


MAX_CONTROL_BYTES = 64 * 1024 * 1024


class CampaignIOError(ValueError):
    """Campaign control data is malformed or cannot be updated safely."""


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CampaignIOError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_number(token: str) -> None:
    raise CampaignIOError(f"floating-point JSON is forbidden: {token}")


def _validate_json_value(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise CampaignIOError(f"floating-point value is forbidden at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CampaignIOError(f"non-string object key at {path}")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise CampaignIOError(f"unsupported JSON value at {path}: {type(value).__name__}")


def parse_json_bytes(raw: bytes, *, label: str = "JSON") -> Any:
    """Parse captured bytes once, rejecting duplicate keys and all floats."""

    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise CampaignIOError(f"cannot parse {label}: {exc}") from exc
    _validate_json_value(value)
    return value


def read_bytes_once(path: Path, *, limit: int = MAX_CONTROL_BYTES) -> bytes:
    """Read at most ``limit`` bytes from one opened regular file."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise CampaignIOError("byte limit must be a positive integer")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CampaignIOError(f"control path is not a regular file: {path}")
            chunks: list[bytes] = []
            total = 0
            while total <= limit:
                chunk = os.read(descriptor, min(1 << 20, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CampaignIOError(f"cannot read {path}: {exc}") from exc
    if len(raw) > limit:
        raise CampaignIOError(f"control file exceeds {limit} bytes: {path}")
    return raw


def load_json(path: Path, *, require_canonical: bool = False) -> Any:
    """Read and parse one JSON file, optionally requiring canonical bytes."""

    raw = read_bytes_once(path)
    value = parse_json_bytes(raw, label=str(path))
    if require_canonical and raw != canonical_json_bytes(value):
        raise CampaignIOError(f"JSON is not in canonical form: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return the unique UTF-8 encoding used for immutable campaign records."""

    _validate_json_value(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def hash_file_once(path: Path, *, limit: int | None = None) -> tuple[str, int]:
    """Hash one opened regular file, optionally enforcing a size ceiling."""

    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CampaignIOError(f"path is not a regular file: {path}")
            while True:
                chunk = os.read(descriptor, 1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if limit is not None and total > limit:
                    raise CampaignIOError(f"file exceeds {limit} bytes: {path}")
                digest.update(chunk)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CampaignIOError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest(), total


@contextmanager
def advisory_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on ``path`` until the context exits."""

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise CampaignIOError(f"cannot open lock {path}: {exc}") from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _replace_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
        ) as output:
            temporary_name = output.name
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise CampaignIOError(f"cannot atomically write {path}: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def atomic_write_json(path: Path, value: Any) -> str:
    """Atomically replace mutable canonical JSON under a sibling lock."""

    raw = canonical_json_bytes(value)
    lock_path = path.with_name(f".{path.name}.lock")
    with advisory_lock(lock_path):
        _replace_bytes(path, raw)
    return sha256_bytes(raw)


def atomic_write_bytes(path: Path, raw: bytes) -> str:
    """Atomically replace a byte artifact under a sibling advisory lock."""

    if not isinstance(raw, bytes):
        raise CampaignIOError("atomic byte output must be bytes")
    lock_path = path.with_name(f".{path.name}.lock")
    with advisory_lock(lock_path):
        _replace_bytes(path, raw)
    return sha256_bytes(raw)


def write_immutable_json(path: Path, value: Any) -> str:
    """Create a content-addressed canonical record, refusing changed bytes."""

    raw = canonical_json_bytes(value)
    digest = sha256_bytes(raw)
    lock_path = path.with_name(f".{path.name}.lock")
    with advisory_lock(lock_path):
        if path.exists():
            existing = read_bytes_once(path)
            if existing != raw:
                raise CampaignIOError(
                    f"immutable record already exists with different bytes: {path}"
                )
            return digest
        _replace_bytes(path, raw)
    return digest
