#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Prepare a source-pinned, locally hardened GoldbachGPU build tree.

The output is a generated build input, not vendored project source.  It keeps
the upstream license and paths, applies the reviewed race and high-range sieve
fixes exactly once, and reports a complete post-patch SHA-256 closure for
measured-build capture.  The production sieve gives one thread exclusive
ownership of each word for the fixed prime prefix through 2039, then retains
atomic composite marking for every larger base prime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import fetch_goldbach_gpu


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "goldbach-gpu" / "b58b2dea-hardening.patch"


class PreparationError(RuntimeError):
    """The deterministic hardened source tree could not be produced."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(checkout: Path, destination: Path) -> dict[str, object]:
    pin = fetch_goldbach_gpu.load_pin()
    upstream = fetch_goldbach_gpu.verify(checkout, pin)
    if destination.exists() and not destination.is_dir():
        raise PreparationError(f"destination is not a directory: {destination}")
    if not PATCH.is_file():
        raise PreparationError("reviewed GoldbachGPU hardening patch is missing")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        for row in pin["files"]:
            relative = Path(row["path"])
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkout.resolve() / relative, target)

        completed = subprocess.run(
            ["git", "apply", "--check", str(PATCH)],
            cwd=temporary,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise PreparationError(
                "hardening patch does not apply to the pinned closure: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        completed = subprocess.run(
            ["git", "apply", str(PATCH)],
            cwd=temporary,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise PreparationError(
                "hardening patch failed: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )

        files = []
        for path in sorted(item for item in temporary.rglob("*") if item.is_file()):
            relative = path.relative_to(temporary).as_posix()
            files.append(
                {
                    "path": relative,
                    "sha256": sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        if {row["path"] for row in files} != {row["path"] for row in pin["files"]}:
            raise PreparationError("hardening changed the reviewed source file set")
        if destination.exists():
            existing = [
                {
                    "path": path.relative_to(destination).as_posix(),
                    "sha256": sha256(path),
                    "size_bytes": path.stat().st_size,
                }
                for path in sorted(
                    item for item in destination.rglob("*") if item.is_file()
                )
            ]
            if existing != files:
                raise PreparationError(
                    "existing hardened GoldbachGPU tree differs from the "
                    "deterministic pinned output"
                )
            shutil.rmtree(temporary)
        else:
            temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        "accepted": True,
        "kind": "sparkinterval.hardened_goldbach_gpu_source.v1",
        "upstream": upstream,
        "patch": {
            "path": PATCH.relative_to(ROOT).as_posix(),
            "sha256": sha256(PATCH),
            "size_bytes": PATCH.stat().st_size,
        },
        "destination": str(destination.resolve()),
        "files": files,
        "production_primality_mode": "mr_first_twelve_prime_bases",
        "production_segment_sieve": (
            "word-owner-prime-prefix-through-2039-then-global-atomic-and"
        ),
        "default_bpsw_mode_accepted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        report = prepare(arguments.checkout, arguments.destination)
    except (
        OSError,
        PreparationError,
        fetch_goldbach_gpu.PinError,
        json.JSONDecodeError,
    ) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2 if arguments.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
