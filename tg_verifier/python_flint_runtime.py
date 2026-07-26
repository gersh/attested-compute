# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Pinned python-flint source and native-wheel closure utilities."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from typing import Any
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = REPOSITORY_ROOT / "specifications/PYTHON_FLINT_0_9_UPSTREAM.json"
GIT_TREE_DOMAIN = b"sparkinterval/git-tracked-source-tree/v1\0"
WHEEL_TREE_DOMAIN = b"sparkinterval/python-flint-wheel-tree/v1\0"
MAX_WHEEL_FILES = 2_000
MAX_WHEEL_BYTES = 256 * 1024 * 1024


class PythonFlintRuntimeError(RuntimeError):
    """A source checkout, wheel, or extracted runtime differs from its pin."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PythonFlintRuntimeError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_pin(path: Path = PIN_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=_unique)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PythonFlintRuntimeError(f"cannot load python-flint pin: {error}") from error
    required = {
        "commit",
        "files",
        "kind",
        "license",
        "name",
        "repository",
        "runtime_wheel",
        "tag",
        "tracked_bytes",
        "tracked_file_count",
        "tracked_tree_hash_domain",
        "tracked_tree_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise PythonFlintRuntimeError("python-flint pin fields changed")
    if value["kind"] != "sparkinterval.pinned_python_flint_upstream.v1":
        raise PythonFlintRuntimeError("unsupported python-flint pin kind")
    return value


def _git(checkout: Path, *argv: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(checkout), *argv],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin", "TZ": "UTC"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PythonFlintRuntimeError(f"git source check failed: {error}") from error
    if completed.returncode != 0:
        raise PythonFlintRuntimeError(
            "git source check failed: "
            + completed.stderr[-2000:].decode("utf-8", "replace")
        )
    return completed.stdout


def tracked_tree_identity(checkout: Path) -> dict[str, Any]:
    raw = _git(checkout, "ls-files", "-z")
    try:
        names = [part.decode("utf-8") for part in raw.split(b"\0") if part]
    except UnicodeDecodeError as error:
        raise PythonFlintRuntimeError("tracked source path is not UTF-8") from error
    if names != sorted(names) or len(names) != len(set(names)):
        raise PythonFlintRuntimeError("tracked source paths are not sorted and unique")
    digest = hashlib.sha256(GIT_TREE_DOMAIN)
    total = 0
    for name in names:
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            raise PythonFlintRuntimeError("tracked source path is unsafe")
        path = checkout.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise PythonFlintRuntimeError(f"tracked source is not regular: {name}")
        content = path.read_bytes()
        encoded = name.encode("utf-8")
        total += len(content)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return {
        "file_count": len(names),
        "size_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }


def verify_checkout(checkout: Path, pin: dict[str, Any] | None = None) -> dict[str, Any]:
    pin = load_pin() if pin is None else pin
    if not checkout.is_dir() or checkout.is_symlink():
        raise PythonFlintRuntimeError("python-flint checkout is not a directory")
    commit = _git(checkout, "rev-parse", "HEAD^{commit}").decode("ascii").strip()
    if commit != pin["commit"]:
        raise PythonFlintRuntimeError("python-flint checkout commit differs")
    tag = _git(checkout, "rev-list", "-n", "1", pin["tag"]).decode("ascii").strip()
    if tag != commit:
        raise PythonFlintRuntimeError("python-flint tag does not resolve to its pin")
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PythonFlintRuntimeError("python-flint checkout is dirty")
    for row in pin["files"]:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size_bytes"}:
            raise PythonFlintRuntimeError("python-flint reviewed source row is malformed")
        path = checkout / row["path"]
        if path.is_symlink() or not path.is_file():
            raise PythonFlintRuntimeError("python-flint reviewed source is absent")
        content = path.read_bytes()
        if (hashlib.sha256(content).hexdigest(), len(content)) != (
            row["sha256"],
            row["size_bytes"],
        ):
            raise PythonFlintRuntimeError("python-flint reviewed source differs")
    identity = tracked_tree_identity(checkout)
    if identity != {
        "file_count": pin["tracked_file_count"],
        "size_bytes": pin["tracked_bytes"],
        "tree_sha256": pin["tracked_tree_sha256"],
    } or pin["tracked_tree_hash_domain"] != GIT_TREE_DOMAIN[:-1].decode("ascii"):
        raise PythonFlintRuntimeError("python-flint tracked source tree differs")
    return {"commit": commit, "tag": pin["tag"], **identity}


def verify_wheel(wheel: Path, pin: dict[str, Any] | None = None) -> dict[str, Any]:
    pin = load_pin() if pin is None else pin
    expected = pin["runtime_wheel"]
    if wheel.is_symlink() or not wheel.is_file() or wheel.name != expected["filename"]:
        raise PythonFlintRuntimeError("python-flint runtime wheel path/name differs")
    content = wheel.read_bytes()
    if (hashlib.sha256(content).hexdigest(), len(content)) != (
        expected["sha256"],
        expected["size_bytes"],
    ):
        raise PythonFlintRuntimeError("python-flint runtime wheel differs")
    return {
        "filename": wheel.name,
        "sha256": expected["sha256"],
        "size_bytes": expected["size_bytes"],
    }


def _safe_member(name: str) -> Path:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or name != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise PythonFlintRuntimeError(f"unsafe wheel member {name!r}")
    return Path(*path.parts)


def _tree_identity(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256(WHEEL_TREE_DOMAIN)
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise PythonFlintRuntimeError("extracted wheel contains a special file")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        count += 1
        total += len(content)
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return {"file_count": count, "size_bytes": total, "tree_sha256": digest.hexdigest()}


def extract_verified_wheel(
    wheel: Path, destination: Path, pin: dict[str, Any] | None = None
) -> dict[str, Any]:
    pin = load_pin() if pin is None else pin
    verify_wheel(wheel, pin)
    if destination.exists():
        raise PythonFlintRuntimeError("python-flint extraction destination must be fresh")
    destination.mkdir(mode=0o700, parents=True)
    seen: set[str] = set()
    count = 0
    total = 0
    try:
        with zipfile.ZipFile(wheel) as archive:
            for info in archive.infolist():
                member_name = (
                    info.filename[:-1]
                    if info.is_dir() and info.filename.endswith("/")
                    else info.filename
                )
                relative = _safe_member(member_name)
                if info.filename in seen:
                    raise PythonFlintRuntimeError("wheel contains a duplicate member")
                seen.add(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise PythonFlintRuntimeError("wheel contains a linked or special member")
                target = destination / relative
                if info.is_dir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                count += 1
                total += info.file_size
                if count > MAX_WHEEL_FILES or total > MAX_WHEEL_BYTES:
                    raise PythonFlintRuntimeError("wheel exceeds its extraction limit")
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("xb") as output:
                    remaining = info.file_size
                    while remaining:
                        chunk = source.read(min(1 << 20, remaining))
                        if not chunk:
                            raise PythonFlintRuntimeError("wheel member was truncated")
                        output.write(chunk)
                        remaining -= len(chunk)
                    if source.read(1):
                        raise PythonFlintRuntimeError("wheel member exceeds declared size")
                target.chmod(0o400)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, PythonFlintRuntimeError):
            raise
        raise PythonFlintRuntimeError(f"cannot extract python-flint wheel: {error}") from error
    identity = _tree_identity(destination)
    expected = pin["runtime_wheel"]
    if identity != {
        "file_count": expected["extracted_file_count"],
        "size_bytes": expected["extracted_bytes"],
        "tree_sha256": expected["extracted_tree_sha256"],
    } or expected["extracted_tree_hash_domain"] != WHEEL_TREE_DOMAIN[:-1].decode("ascii"):
        raise PythonFlintRuntimeError("extracted python-flint runtime tree differs")
    required = (
        destination / "flint/__init__.py",
        destination / "flint/types/acb.abi3.so",
        destination / "python_flint-0.9.0.dist-info/METADATA",
        destination / "python_flint-0.9.0.dist-info/WHEEL",
    )
    if any(not path.is_file() for path in required):
        raise PythonFlintRuntimeError("python-flint wheel lacks its reviewed runtime files")
    for directory in sorted(
        (path for path in destination.rglob("*") if path.is_dir()), reverse=True
    ):
        directory.chmod(0o500)
    destination.chmod(0o500)
    return identity


__all__ = [
    "PIN_PATH",
    "PythonFlintRuntimeError",
    "extract_verified_wheel",
    "load_pin",
    "tracked_tree_identity",
    "verify_checkout",
    "verify_wheel",
]
