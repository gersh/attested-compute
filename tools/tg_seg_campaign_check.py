#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
"""Check a chained leancompcert campaign directory before anything runs it.

The campaign's `canonicalDefinition` names the manifest by digest, and nothing
else.  Everything the manifest asserts about the run therefore has to be
checked against the manifest *text*, by the same routine, in three places: on
the reviewed build host, inside the TD before the chain starts, and by a
reviewer.  This is that routine.

What it checks:

* the manifest header is the expected kind and carries every field the
  campaign relies on;
* the windows form a **gap-free cover**: window 0 starts at `cover-lo`, each
  window abuts the previous one, and the last ends exactly at `range-hi`;
* the windows form a **correct chain**: each window's `seed` is the previous
  window's `carry`, and window 0's seed is `initial-seed`;
* `segLen * segCount` reaches exactly `hi` for every window, so no window
  tests past the end of the range its threshold was computed for;
* every window inside the claimed range `[range-lo, range-hi]` expects **zero**
  threshold violations, and every window that expects a nonzero count is
  marked `primer=1` and lies entirely below `range-lo`;
* every artifact exists, is a regular file, is executable, and hashes to the
  digest the manifest records.

Exit status is 0 only when all of that holds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

KIND = "sparkinterval.leancompcert-seg-campaign-manifest.v1"

REQUIRED_HEADER = (
    "name", "producer", "program", "emitter", "reduced-family", "claim",
    "cover-lo", "range-lo", "range-hi", "windows", "initial-seed",
    "compcert-version", "compcert-target", "link", "start-stub-sha256",
    "success", "output",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse(manifest: Path):
    text = manifest.read_text().splitlines()
    if not text or text[0] != KIND:
        raise SystemExit(f"manifest is not a {KIND} document")
    header: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    inside = False
    for line in text[1:]:
        if line == "windows-begin":
            inside = True
            continue
        if line == "windows-end":
            inside = False
            continue
        if inside:
            fields = line.split()
            if not fields or fields[0] != "w":
                raise SystemExit(f"malformed window row: {line!r}")
            row = {"index": fields[1]}
            for field in fields[2:]:
                key, _, value = field.partition("=")
                row[key] = value
            rows.append(row)
        elif "=" in line:
            key, _, value = line.partition("=")
            header[key] = value
    return header, rows


def check(campaign_root: Path):
    manifest = campaign_root / "campaign-manifest.txt"
    header, rows = parse(manifest)
    problems: list[str] = []

    for key in REQUIRED_HEADER:
        if key not in header:
            problems.append(f"header is missing {key}")
    if problems:
        return header, rows, problems

    if header["compcert-target"] != "x86_64-linux":
        problems.append(
            f"compcert-target is {header['compcert-target']}, but Intel TDX "
            f"is x86_64 only")
    if int(header["windows"]) != len(rows):
        problems.append(
            f"header says {header['windows']} windows, {len(rows)} listed")
    if not rows:
        problems.append("manifest lists no windows")
        return header, rows, problems

    cover_lo = int(header["cover-lo"])
    claim_lo = int(header["range-lo"])
    hi = int(header["range-hi"])
    if claim_lo < cover_lo:
        problems.append("range-lo is below cover-lo")

    expect_lo = cover_lo
    expect_seed = int(header["initial-seed"])
    for i, row in enumerate(rows):
        tag = f"window {i}"
        if int(row["index"]) != i:
            problems.append(f"{tag}: index out of order")
        if int(row["lo"]) != expect_lo:
            problems.append(
                f"{tag}: gap or overlap -- starts at {row['lo']}, the cover "
                f"needs it to start at {expect_lo}")
        if int(row["seed"]) != expect_seed:
            problems.append(
                f"{tag}: chain break -- seed {row['seed']} is not the "
                f"previous window's carry {expect_seed}")
        span = int(row["segLen"]) * int(row["segCount"])
        if int(row["lo"]) + span - 1 != int(row["hi"]):
            problems.append(
                f"{tag}: segLen*segCount covers {span} integers, which does "
                f"not land on hi={row['hi']}; the window would test past the "
                f"point its threshold was computed for")
        if int(row["primer"]):
            if int(row["hi"]) >= claim_lo:
                problems.append(
                    f"{tag}: marked primer but reaches {row['hi']}, inside "
                    f"the claimed range starting at {claim_lo}")
        elif int(row["expectViol"]) != 0:
            problems.append(
                f"{tag}: inside the claimed range but expects "
                f"{row['expectViol']} threshold violations")
        expect_seed = int(row["carry"])
        expect_lo = int(row["hi"]) + 1

    if expect_lo != hi + 1:
        problems.append(f"the cover stops at {expect_lo - 1}, not at {hi}")

    for i, row in enumerate(rows):
        binary = campaign_root / "bin" / f"w{i:05d}"
        if not binary.is_file() or binary.is_symlink():
            problems.append(f"window {i}: missing artifact {binary.name}")
            continue
        actual = sha256_file(binary)
        if actual != row["binSha256"]:
            problems.append(
                f"window {i}: artifact digest {actual} is not the manifest's "
                f"{row['binSha256']}")
        if binary.stat().st_size != int(row["binBytes"]):
            problems.append(f"window {i}: artifact size disagrees")
    return header, rows, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true",
                       help="print '<index> bin/w<index>' for each window, in "
                            "run order, only if every check passes")
    group.add_argument("--count", action="store_true")
    args = parser.parse_args()

    header, rows, problems = check(args.campaign_root)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"header": header, "windows": len(rows), "problems": problems},
            indent=1, sort_keys=True))
    if problems:
        for problem in problems:
            print(f"CAMPAIGN PRECHECK FAILED: {problem}", file=sys.stderr)
        return 1
    if args.list:
        for i in range(len(rows)):
            print(f"{i} bin/w{i:05d}")
    elif args.count:
        print(len(rows))
    else:
        print(f"campaign precheck OK: {len(rows)} windows, cover "
              f"[{header['cover-lo']}, {header['range-hi']}], claimed from "
              f"{header['range-lo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
