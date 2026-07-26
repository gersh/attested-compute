#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch and verify the reviewed GoldbachGPU source closure.

Verification of this pin is intentionally not approval to execute upstream's
default BPSW mode.  The production adapter must enforce every item in the
pin's ``review_policy`` and must retain the upstream MIT notice.
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
PIN = ROOT / "specifications" / "GOLDBACH_GPU_UPSTREAM.json"


class PinError(RuntimeError):
    """The checkout is missing or differs from the reviewed closure."""


def run(arguments: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        arguments, cwd=cwd, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PinError(f"{' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def load_pin() -> dict[str, Any]:
    value = json.loads(PIN.read_text(encoding="utf-8"))
    if value.get("kind") != "sparkinterval.pinned_upstream_source.v1":
        raise PinError("unsupported GoldbachGPU pin schema")
    if not isinstance(value.get("review_policy"), dict):
        raise PinError("GoldbachGPU pin omits its mandatory review policy")
    if not isinstance(value.get("files"), list) or not value["files"]:
        raise PinError("GoldbachGPU pin has no source closure")
    return value


def fetch(checkout: Path, pin: dict[str, Any]) -> None:
    if checkout.exists():
        return
    checkout.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--no-checkout", pin["repository"], str(checkout)])
    run(["git", "checkout", "--detach", pin["commit"]], cwd=checkout)


def verify(checkout: Path, pin: dict[str, Any]) -> dict[str, Any]:
    checkout = checkout.resolve()
    if not checkout.is_dir():
        raise PinError(f"GoldbachGPU checkout does not exist: {checkout}")
    commit = run(["git", "rev-parse", "HEAD^{commit}"], cwd=checkout)
    if commit != pin["commit"]:
        raise PinError(f"expected commit {pin['commit']}, got {commit}")
    if run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=checkout):
        raise PinError("GoldbachGPU checkout is dirty")

    actual: list[dict[str, Any]] = []
    for expected in pin["files"]:
        if set(expected) != {"path", "sha256", "size_bytes"}:
            raise PinError("malformed GoldbachGPU file entry")
        relative = Path(expected["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise PinError(f"unsafe GoldbachGPU path: {relative}")
        path = checkout / relative
        if path.is_symlink() or not path.is_file():
            raise PinError(f"source closure entry is not a regular file: {relative}")
        raw = path.read_bytes()
        row = {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
        if row != expected:
            raise PinError(f"source closure entry differs: {relative}")
        actual.append(row)
    return {
        "accepted": True,
        "kind": "sparkinterval.verified_upstream_checkout.v1",
        "name": pin["name"],
        "repository": pin["repository"],
        "commit": commit,
        "license": pin["license"],
        "checkout": str(checkout),
        "review_policy": pin["review_policy"],
        "files": actual,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        pin = load_pin()
        if not arguments.verify_only:
            fetch(arguments.checkout, pin)
        report = verify(arguments.checkout, pin)
    except (OSError, PinError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2 if arguments.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
