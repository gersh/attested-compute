#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Turn a Phala CVM log back into the CH25 A.7 TDX evidence files.

The campaign container prints its evidence to stdout as delimited base64 (see
``proof_build/ch25_a7_phala_tdx/emit_phala_tdx_evidence.py``) and then stays
alive, because that is the only channel out of a dstack CVM: volumes are not
reachable and `phala cvms logs` drops the logs of containers that have exited.

Usage::

    phala cvms logs <cvm> > run.log
    python3 tools/tg_phala_tdx_extract_evidence.py \\
        --log run.log --out-dir ./retained-evidence

What this checks, and what it does not
--------------------------------------

It checks that every block's base64 decodes to bytes whose SHA-256 is the one
the block's own header and trailer state, that the two agree, that the
manifest block is present, and that the manifest and the blocks agree about
which files exist and what their digests are.  A single altered base64
character therefore fails, loudly, and nothing is written.

It does **not** check that the evidence is genuine.  Nothing here parses a
quote or verifies a signature; the digests are self-consistency only.  The
appraisal that matters was performed by ``dcap-qvl`` inside the CVM, and the
signature that matters is checked in Lean.

The extractor refuses outright if the log claims to carry key material.  The
signing key is never emitted; a block that says otherwise means something is
badly wrong and is treated as fatal rather than skipped.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


MARKER = "SPARKINTERVAL-TDX-EVIDENCE-V1"
MANIFEST_NAME = "evidence-manifest.json"
MANIFEST_KIND = "sparkinterval.phala-tdx-evidence-manifest.v1"
FORBIDDEN_NAME_SUBSTRINGS = ("signing-key", "enclave-key", "private", "secret")

MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024


class ExtractError(RuntimeError):
    """The log is not a well-formed, self-consistent evidence transcript."""


def _safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or name != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise ExtractError(f"unsafe evidence file name {name!r}")
    lowered = name.lower()
    for forbidden in FORBIDDEN_NAME_SUBSTRINGS:
        if forbidden in lowered:
            raise ExtractError(
                f"the log carries a block named {name!r}, which looks like key "
                "material. The signing key must never be printed. Treat this "
                "run as compromised and do not promote its receipt."
            )
    return path


def _payload(line: str) -> str | None:
    """The part of a log line after the marker, or None if it carries none.

    `phala cvms logs` prefixes lines with a timestamp and a container name, so
    the marker is located rather than anchored.
    """

    index = line.find(MARKER)
    if index < 0:
        return None
    return line[index + len(MARKER):].lstrip()


def parse(log: str) -> dict[str, bytes]:
    blocks: dict[str, bytes] = {}
    current: dict | None = None
    chunks: list[str] = []
    total = 0
    for raw_line in log.splitlines():
        payload = _payload(raw_line.rstrip("\r"))
        if payload is None:
            continue
        if payload.startswith("BEGIN "):
            if current is not None:
                raise ExtractError(
                    f"a BEGIN for {payload[6:]!r} interrupts the block for "
                    f"{current['name']!r}"
                )
            current = _header(payload[len("BEGIN "):])
            chunks = []
        elif payload.startswith("DATA"):
            if current is None:
                raise ExtractError("a DATA line appears outside any block")
            chunks.append(payload[len("DATA"):].strip())
        elif payload.startswith("END "):
            if current is None:
                raise ExtractError("an END line appears outside any block")
            trailer = json.loads(payload[len("END "):])
            if not isinstance(trailer, dict):
                raise ExtractError("an END trailer is not a JSON object")
            if trailer.get("name") != current["name"]:
                raise ExtractError(
                    f"block {current['name']!r} ends with a trailer for "
                    f"{trailer.get('name')!r}"
                )
            raw = _decode("".join(chunks), current)
            if trailer.get("sha256") != current["sha256"]:
                raise ExtractError(
                    f"block {current['name']!r} states two different digests"
                )
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ExtractError("the transcript exceeds the total size limit")
            name = current["name"]
            if name in blocks and blocks[name] != raw:
                raise ExtractError(
                    f"the log carries two different versions of {name!r}"
                )
            blocks[name] = raw
            current = None
            chunks = []
        # Anything else carrying the marker is a human-readable banner.
    if current is not None:
        raise ExtractError(
            f"the log ends inside the block for {current['name']!r}; it was "
            "truncated before the container finished printing"
        )
    return blocks


def _header(text: str) -> dict:
    try:
        header = json.loads(text)
    except json.JSONDecodeError as error:
        raise ExtractError(f"a BEGIN header is not JSON: {error}") from error
    if not isinstance(header, dict):
        raise ExtractError("a BEGIN header is not a JSON object")
    name = header.get("name")
    if not isinstance(name, str):
        raise ExtractError("a BEGIN header has no name")
    _safe_name(name)
    digest = header.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ExtractError(f"block {name!r} has no SHA-256 header")
    size = header.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ExtractError(f"block {name!r} has no byte count")
    if size > MAX_FILE_BYTES:
        raise ExtractError(f"block {name!r} claims more than the size limit")
    return {"name": name, "sha256": digest.lower(), "bytes": size}


def _decode(encoded: str, header: dict) -> bytes:
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as error:
        raise ExtractError(
            f"block {header['name']!r} is not valid base64: {error}"
        ) from error
    if len(raw) != header["bytes"]:
        raise ExtractError(
            f"block {header['name']!r} decodes to {len(raw)} bytes, the header "
            f"states {header['bytes']}"
        )
    actual = hashlib.sha256(raw).hexdigest()
    if actual != header["sha256"]:
        raise ExtractError(
            f"block {header['name']!r} has sha256 {actual}, the header states "
            f"{header['sha256']}; the log was altered or corrupted in transit"
        )
    return raw


def check_manifest(blocks: dict[str, bytes]) -> dict:
    if MANIFEST_NAME not in blocks:
        raise ExtractError(
            f"the log carries no {MANIFEST_NAME} block, so it cannot be shown "
            "to be complete; retrieve the whole log and try again"
        )
    try:
        manifest = json.loads(blocks[MANIFEST_NAME].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExtractError(f"the manifest is not JSON: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("kind") != MANIFEST_KIND:
        raise ExtractError("the manifest is not the expected kind")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ExtractError("the manifest carries no file list")
    listed: dict[str, dict] = {}
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ExtractError("a manifest entry is malformed")
        _safe_name(entry["name"])
        listed[entry["name"]] = entry
    for name, entry in listed.items():
        if entry.get("present"):
            if name not in blocks:
                raise ExtractError(
                    f"the manifest lists {name!r} as emitted but the log "
                    "carries no such block"
                )
            actual = hashlib.sha256(blocks[name]).hexdigest()
            if actual != entry.get("sha256"):
                raise ExtractError(
                    f"the manifest states {name!r} has sha256 "
                    f"{entry.get('sha256')}, the block decodes to {actual}"
                )
        elif name in blocks:
            raise ExtractError(
                f"the manifest lists {name!r} as absent but a block for it was "
                "emitted"
            )
    for name in blocks:
        if name != MANIFEST_NAME and name not in listed:
            raise ExtractError(
                f"the log carries an unlisted block {name!r}; the manifest is "
                "supposed to be exhaustive"
            )
    return manifest


def write(blocks: dict[str, bytes], manifest: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    roots = {
        entry["name"]: entry.get("root", "")
        for entry in manifest["files"]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    for name, raw in sorted(blocks.items()):
        root = roots.get(name, "")
        relative = PurePosixPath(root) / name if root else PurePosixPath(name)
        _safe_name(relative.as_posix())
        destination = out_dir / Path(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ExtractError(f"{destination} already exists; refusing to overwrite")
        destination.write_bytes(raw)
        destination.chmod(0o444)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log", type=Path, help="the captured log; stdin when omitted"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="where to write the recovered files.  Omit to verify only.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        log = (
            args.log.read_text(encoding="utf-8", errors="replace")
            if args.log
            else sys.stdin.read()
        )
        blocks = parse(log)
        manifest = check_manifest(blocks)
        if args.out_dir is not None:
            write(blocks, manifest, args.out_dir)
    except ExtractError as error:
        print(f"evidence extraction REFUSED: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"evidence extraction failed: {error}", file=sys.stderr)
        return 5

    missing = manifest.get("missing_required") or []
    for entry in sorted(manifest["files"], key=lambda item: item["name"]):
        state = "ok  " if entry.get("present") else "MISSING"
        print(f"{state} {entry.get('sha256', ''):64} {entry['name']}")
    print(
        f"campaign exit status: {manifest.get('campaign_exit_status')}",
    )
    if args.out_dir is not None:
        print(f"wrote {len(blocks)} files to {args.out_dir}")
    if missing:
        print(
            "these required files were never produced: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 4
    if manifest.get("campaign_exit_status") not in (0, None):
        print("the campaign entry point exited non-zero", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
