#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch, verify, and optionally build the pinned FLINT 3.6 Platt backend."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "specifications" / "FLINT_3_6_PLATT_UPSTREAM.json"


class FetchFlintError(RuntimeError):
    """The source checkout or build does not match the reviewed pin."""


def _run(argv: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FetchFlintError(f"{' '.join(argv)} failed: {detail}")
    return result.stdout.strip()


def load_pin() -> dict[str, Any]:
    value = json.loads(PIN.read_text(encoding="utf-8"))
    if value.get("kind") != "sparkinterval.pinned_upstream_source.v1":
        raise FetchFlintError("unsupported pin schema")
    if not isinstance(value.get("files"), list) or not value["files"]:
        raise FetchFlintError("pin has no reviewed source files")
    return value


def fetch(checkout: Path, pin: dict[str, Any]) -> None:
    if checkout.exists():
        return
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--no-checkout", pin["repository"], str(checkout)])
    _run(["git", "checkout", "--detach", pin["commit"]], cwd=checkout)


def verify(checkout: Path, pin: dict[str, Any]) -> dict[str, Any]:
    if not checkout.is_dir():
        raise FetchFlintError(f"checkout does not exist: {checkout}")
    commit = _run(["git", "rev-parse", "HEAD^{commit}"], cwd=checkout)
    if commit != pin["commit"]:
        raise FetchFlintError(f"expected commit {pin['commit']}, got {commit}")
    tag_commit = _run(["git", "rev-list", "-n", "1", pin["tag"]], cwd=checkout)
    if tag_commit != commit:
        raise FetchFlintError(f"tag {pin['tag']} does not resolve to the pinned commit")
    if _run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=checkout):
        raise FetchFlintError("checkout is dirty")
    for row in pin["files"]:
        if set(row) != {"path", "sha256", "size_bytes"}:
            raise FetchFlintError("malformed reviewed source row")
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise FetchFlintError(f"unsafe reviewed path: {relative}")
        path = checkout / relative
        if path.is_symlink() or not path.is_file():
            raise FetchFlintError(f"reviewed path is not a regular file: {relative}")
        raw = path.read_bytes()
        actual = (hashlib.sha256(raw).hexdigest(), len(raw))
        expected = (row["sha256"], row["size_bytes"])
        if actual != expected:
            raise FetchFlintError(f"reviewed source differs: {relative}")
    return {
        "accepted": True,
        "name": pin["name"],
        "tag": pin["tag"],
        "commit": commit,
        "license": pin["license"],
        "checkout": str(checkout.resolve()),
        "reviewed_files": len(pin["files"]),
    }


def build(checkout: Path, prefix: Path, jobs: int) -> None:
    prefix.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "./configure",
            f"--prefix={prefix.resolve()}",
            "--enable-shared",
            "--disable-static",
        ],
        cwd=checkout,
    )
    _run(["make", f"-j{jobs}"], cwd=checkout)
    _run(["make", "install"], cwd=checkout)
    header = prefix / "include" / "flint" / "acb_dirichlet.h"
    library = prefix / "lib" / "libflint.so"
    if not header.is_file() or not library.exists():
        raise FetchFlintError("FLINT install is missing its header or shared library")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--prefix", type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        pin = load_pin()
        if not args.verify_only:
            fetch(args.checkout, pin)
        report = verify(args.checkout, pin)
        if args.build:
            if args.prefix is None:
                raise FetchFlintError("--build requires --prefix")
            if args.jobs < 1:
                raise FetchFlintError("--jobs must be positive")
            build(args.checkout, args.prefix, args.jobs)
            report["install_prefix"] = str(args.prefix.resolve())
    except (FetchFlintError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
