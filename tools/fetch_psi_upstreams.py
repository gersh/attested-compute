#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch and verify the two upstreams used by the CH25 psi runner.

The commit identifier is checked first.  A second SHA-256 commitment covers
the path and contents of *every* tracked file, including build scripts and
licenses.  This avoids treating a SHA-1 Git object name as the sole source
identity and makes the exact source closure independently reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / "specifications" / "PSI_UPSTREAMS.json"
TREE_DOMAIN = b"sparkinterval/pinned-git-tree/v1\0"


class FetchError(RuntimeError):
    """A checkout differs from the reviewed upstream source closure."""


def _run(arguments: list[str], *, cwd: Path | None = None, binary: bool = False):
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    if completed.returncode != 0:
        stderr = completed.stderr
        stdout = completed.stdout
        if binary:
            stderr = stderr.decode("utf-8", "replace")
            stdout = stdout.decode("utf-8", "replace")
        detail = stderr.strip() or stdout.strip()
        raise FetchError(f"{' '.join(arguments)} failed: {detail}")
    return completed.stdout


def load_pin(component: str) -> dict[str, Any]:
    value = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    if value.get("kind") != "sparkinterval.pinned_upstream_bundle.v1":
        raise FetchError("unsupported psi upstream pin schema")
    components = value.get("components")
    if not isinstance(components, dict) or component not in components:
        raise FetchError(f"unknown psi upstream component: {component}")
    row = components[component]
    required = {
        "name",
        "repository",
        "commit",
        "license",
        "tracked_file_count",
        "tracked_bytes",
        "tree_sha256",
    }
    if not isinstance(row, dict) or set(row) != required:
        raise FetchError(f"malformed pin for psi upstream component: {component}")
    return row


def _tracked_tree(checkout: Path) -> tuple[int, int, str]:
    raw = _run(["git", "ls-files", "-z"], cwd=checkout, binary=True)
    paths = [item for item in raw.split(b"\0") if item]
    digest = hashlib.sha256(TREE_DOMAIN)
    total_bytes = 0
    for encoded in paths:
        try:
            relative_text = encoded.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise FetchError("upstream contains a non-UTF-8 tracked path") from exc
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise FetchError(f"unsafe tracked path: {relative_text}")
        path = checkout / relative
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise FetchError(f"cannot stat tracked path {relative_text}: {exc}") from exc
        if not stat.S_ISREG(mode):
            raise FetchError(f"tracked path is not a regular file: {relative_text}")
        data = path.read_bytes()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
        total_bytes += len(data)
    return len(paths), total_bytes, digest.hexdigest()


def verify_checkout(checkout: Path, component: str, pin: dict[str, Any]) -> dict[str, Any]:
    checkout = checkout.resolve()
    if not checkout.is_dir():
        raise FetchError(f"upstream checkout does not exist: {checkout}")
    commit = _run(["git", "rev-parse", "HEAD^{commit}"], cwd=checkout).strip()
    if commit != pin["commit"]:
        raise FetchError(
            f"{component} commit differs: expected {pin['commit']}, got {commit}"
        )
    dirty = _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=checkout
    ).strip()
    if dirty:
        raise FetchError(f"{component} checkout is dirty")
    count, byte_count, tree_sha256 = _tracked_tree(checkout)
    actual = {
        "tracked_file_count": count,
        "tracked_bytes": byte_count,
        "tree_sha256": tree_sha256,
    }
    expected = {key: pin[key] for key in actual}
    if actual != expected:
        raise FetchError(
            f"{component} tracked tree differs: expected {expected}, got {actual}"
        )
    return {
        "kind": "sparkinterval.verified_upstream_checkout.v1",
        "component": component,
        "name": pin["name"],
        "repository": pin["repository"],
        "commit": commit,
        "license": pin["license"],
        "checkout": os.fspath(checkout),
        **actual,
        "accepted": True,
    }


def fetch(checkout: Path, pin: dict[str, Any]) -> None:
    checkout = checkout.resolve()
    if checkout.exists():
        return
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--no-checkout", pin["repository"], os.fspath(checkout)])
    _run(["git", "checkout", "--detach", pin["commit"]], cwd=checkout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=("crlibm", "primesieve"))
    parser.add_argument("checkout", type=Path)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="reject a missing checkout instead of fetching it",
    )
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        pin = load_pin(arguments.component)
        if not arguments.verify_only:
            fetch(arguments.checkout, pin)
        report = verify_checkout(arguments.checkout, arguments.component, pin)
    except (FetchError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2 if arguments.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
