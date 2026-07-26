#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch and verify the pinned Greg Hurst segmented-Mobius implementation.

The upstream files remain MIT-licensed Greg Hurst code; this helper does not
rewrite their notices or make them part of SparkInterval's project-owned
source.  A production build records the pinned commit and verifies every file
used by the adapter against the repository manifest before compiling it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / "specifications" / "HURST_MERTENS_UPSTREAM.json"


class FetchError(RuntimeError):
    """The upstream checkout does not match the reviewed source closure."""


def _run(arguments: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise FetchError(f"{' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def load_pin() -> dict[str, Any]:
    value = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    if value.get("kind") != "sparkinterval.pinned_upstream_source.v1":
        raise FetchError("unsupported upstream pin schema")
    if not isinstance(value.get("files"), list) or not value["files"]:
        raise FetchError("upstream pin has no file closure")
    return value


def verify_checkout(checkout: Path, pin: dict[str, Any]) -> dict[str, Any]:
    checkout = checkout.resolve()
    if not checkout.is_dir():
        raise FetchError(f"upstream checkout does not exist: {checkout}")
    commit = _run(["git", "rev-parse", "HEAD^{commit}"], cwd=checkout)
    if commit != pin["commit"]:
        raise FetchError(f"upstream commit differs: expected {pin['commit']}, got {commit}")
    dirty = _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=checkout
    )
    if dirty:
        raise FetchError("upstream checkout is dirty")

    files: list[dict[str, Any]] = []
    for row in pin["files"]:
        if set(row) != {"path", "sha256", "size_bytes"}:
            raise FetchError("upstream file pin is malformed")
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise FetchError(f"unsafe upstream path: {relative}")
        path = checkout / relative
        if path.is_symlink() or not path.is_file():
            raise FetchError(f"upstream closure entry is not a regular file: {relative}")
        raw = path.read_bytes()
        actual = {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
        if actual != row:
            raise FetchError(f"upstream file differs from pin: {relative}")
        files.append(actual)
    return {
        "kind": "sparkinterval.verified_upstream_checkout.v1",
        "name": pin["name"],
        "repository": pin["repository"],
        "commit": commit,
        "license": pin["license"],
        "checkout": str(checkout),
        "files": files,
        "accepted": True,
    }


def fetch(checkout: Path, pin: dict[str, Any]) -> None:
    checkout = checkout.resolve()
    if checkout.exists():
        return
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--no-checkout", pin["repository"], str(checkout)])
    _run(["git", "checkout", "--detach", pin["commit"]], cwd=checkout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="reject a missing checkout instead of fetching it",
    )
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        pin = load_pin()
        if not arguments.verify_only:
            fetch(arguments.checkout, pin)
        report = verify_checkout(arguments.checkout, pin)
    except (FetchError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2 if arguments.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
