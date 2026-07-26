#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Back-pressured bounded binary tee for scheduled Dirichlet KAT replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


SCHEMA = "sparkinterval.tg.bounded_stream_tee.receipt.v1"
MAXIMUM_CHUNK_BYTES = 1024 * 1024


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")


def lowercase_sha256(value: str) -> str:
    if (
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("manifest digest is not lowercase SHA-256")
    return value


def positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def atomic_publish(path: Path, temporary: Path) -> None:
    if path.exists() or path.is_symlink():
        raise RuntimeError(f"refusing to replace immutable output: {path}")
    os.link(temporary, path)
    temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("maximum_bytes", type=positive)
    parser.add_argument("stream_role", choices=("TGDAFFI1", "TGDAFFO1"))
    parser.add_argument("schedule_manifest_sha256", type=lowercase_sha256)
    args = parser.parse_args()
    if args.capture.exists() or args.capture.is_symlink():
        raise RuntimeError("capture output already exists")
    if args.receipt.exists() or args.receipt.is_symlink():
        raise RuntimeError("tee receipt already exists")
    args.capture.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{args.capture.name}.", dir=args.capture.parent
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as capture:
            while True:
                block = sys.stdin.buffer.read(MAXIMUM_CHUNK_BYTES)
                if not block:
                    break
                if size > args.maximum_bytes - len(block):
                    raise RuntimeError("bounded stream capture exceeds its limit")
                sys.stdout.buffer.write(block)
                sys.stdout.buffer.flush()
                capture.write(block)
                digest.update(block)
                size += len(block)
            capture.flush()
            os.fsync(capture.fileno())
        atomic_publish(args.capture, temporary)
        receipt = {
            "kind": SCHEMA,
            "classification": (
                "bounded_stream_capture_for_independent_replay_not_evidence"
            ),
            "stream_role": args.stream_role,
            "schedule_manifest_sha256": args.schedule_manifest_sha256,
            "stream_sha256": digest.hexdigest(),
            "stream_size_bytes": size,
            "maximum_stream_bytes": args.maximum_bytes,
            "bounded_memory_bytes": MAXIMUM_CHUNK_BYTES,
            "backpressure_preserved": True,
            "external_atom_discharged": False,
        }
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(receipt)
        ).hexdigest()
        receipt_descriptor, receipt_temporary_name = tempfile.mkstemp(
            prefix=f".{args.receipt.name}.", dir=args.receipt.parent
        )
        receipt_temporary = Path(receipt_temporary_name)
        try:
            with os.fdopen(receipt_descriptor, "wb") as output:
                output.write(canonical_json_bytes(receipt))
                output.flush()
                os.fsync(output.fileno())
            atomic_publish(args.receipt, receipt_temporary)
        except BaseException:
            receipt_temporary.unlink(missing_ok=True)
            raise
        return 0
    except BaseException:
        temporary.unlink(missing_ok=True)
        args.capture.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BrokenPipeError, OSError, RuntimeError, ValueError) as error:
        print(f"tg_bounded_stream_tee: {error}", file=sys.stderr)
        raise SystemExit(2)
