#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch, safely extract, and verify pinned GMP/MPFR release sources."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.prop1224_upstreams import (  # noqa: E402
    Prop1224UpstreamError,
    load_pin,
    verify_archive,
    verify_source,
)


MAX_FILES = 5_000
MAX_BYTES = 64 * 1024 * 1024


def _safe_member(name: str, expected_root: str) -> Path:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or name != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
        or not path.parts
        or path.parts[0] != expected_root
    ):
        raise Prop1224UpstreamError(f"unsafe archive member {name!r}")
    return Path(*path.parts)


def safe_extract(archive: Path, destination: Path, pin: dict[str, object]) -> Path:
    if destination.exists():
        raise Prop1224UpstreamError("source extraction destination already exists")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".prop1224-upstream-", dir=destination.parent))
    complete = False
    try:
        count = 0
        total = 0
        with tarfile.open(archive, mode="r:xz") as source:
            for member in source:
                relative = _safe_member(member.name, str(pin["archive_root"]))
                target = stage / relative
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise Prop1224UpstreamError(
                        f"archive contains a non-regular member: {member.name!r}"
                    )
                count += 1
                total += member.size
                if count > MAX_FILES or total > MAX_BYTES:
                    raise Prop1224UpstreamError("upstream archive exceeds extraction limits")
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                extracted = source.extractfile(member)
                if extracted is None:
                    raise Prop1224UpstreamError("cannot read regular archive member")
                descriptor = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o500 if member.mode & 0o111 else 0o400,
                )
                try:
                    remaining = member.size
                    while remaining:
                        block = extracted.read(min(1 << 20, remaining))
                        if not block:
                            raise Prop1224UpstreamError("short archive member")
                        view = memoryview(block)
                        while view:
                            written = os.write(descriptor, view)
                            if written <= 0:
                                raise Prop1224UpstreamError("short extracted write")
                            view = view[written:]
                        remaining -= len(block)
                    if extracted.read(1):
                        raise Prop1224UpstreamError("archive member exceeds declared size")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        root = stage / str(pin["archive_root"])
        verify_source(root, str(pin["component"]))
        os.replace(root, destination)
        complete = True
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if not complete and destination.exists():
            shutil.rmtree(destination, ignore_errors=True)


def fetch(component: str, archive: Path, source: Path) -> dict[str, object]:
    pin = load_pin(component)
    pin = {**pin, "component": component}
    if archive.name != pin["archive_filename"]:
        raise Prop1224UpstreamError("archive destination filename differs from pin")
    if not archive.exists():
        archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with urllib.request.urlopen(str(pin["source_url"]), timeout=300) as response:
            raw = response.read(int(pin["archive_size_bytes"]) + 1)
        temporary = archive.with_name(f".{archive.name}.download")
        if temporary.exists():
            raise Prop1224UpstreamError("temporary archive path already exists")
        with temporary.open("xb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        try:
            verify_archive(temporary, {**pin, "archive_filename": temporary.name})
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    archive_identity = verify_archive(archive, pin)
    if not source.exists():
        safe_extract(archive, source, pin)
    source_identity = verify_source(source, component)
    return {
        "accepted": True,
        "archive": archive_identity,
        "source": source_identity,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=("gmp", "mpfr"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    try:
        if args.fetch:
            result = fetch(args.component, args.archive, args.source)
        else:
            result = {
                "accepted": True,
                "archive": verify_archive(args.archive, load_pin(args.component)),
                "source": verify_source(args.source, args.component),
            }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, Prop1224UpstreamError, tarfile.TarError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
