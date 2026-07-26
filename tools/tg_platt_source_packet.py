#!/usr/bin/env python3
"""Inspect the fixed first-window PT21 Gamma/bucket source packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


MAGIC_V1 = b"PT21SRC1"
MAGIC_V2 = b"PT21SRC2"
VERSION_V1 = 1
VERSION_V2 = 2
ENDIAN_TAG = 0x01020304
INTERVAL_ENCODING_V1 = 1
INTERVAL_ENCODING_V2 = 2
BUCKETS = 32768
STAGES = 23
SOURCE_TERMS = 768000
WINDOW_CENTER = 10_000_000_000 + 1008 // 2
UPSTREAM_COMMIT = b"42b21426718e542daa2b006dc05ea2d7f26426e6"
HEADER = struct.Struct("<8s8I6Q40s")
INTERVAL_BYTES_V1 = 32
INTERVAL_BYTES_V2 = 40


class PacketError(ValueError):
    """The packet is not the fixed source-core handoff."""


def fnv1a64(raw: memoryview) -> int:
    result = 1469598103934665603
    for byte in raw:
        result ^= byte
        result = (result * 1099511628211) & ((1 << 64) - 1)
    return result


def inspect(path: Path, *, check_all_intervals: bool = True) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) < HEADER.size:
        raise PacketError("source packet is truncated before its header")
    (
        magic,
        version,
        header_bytes,
        endian_tag,
        interval_encoding,
        buckets,
        stages,
        source_terms,
        reserved,
        window_center,
        gamma_count,
        skn_count,
        payload_bytes,
        gamma_fnv,
        skn_fnv,
        upstream_commit,
    ) = HEADER.unpack_from(raw)
    if (magic, version, interval_encoding) == (
        MAGIC_V1,
        VERSION_V1,
        INTERVAL_ENCODING_V1,
    ):
        interval_bytes = INTERVAL_BYTES_V1
        kind = "sparkinterval.tg.platt-pt21-first-window-source-packet.v1"
    elif (magic, version, interval_encoding) == (
        MAGIC_V2,
        VERSION_V2,
        INTERVAL_ENCODING_V2,
    ):
        interval_bytes = INTERVAL_BYTES_V2
        kind = "sparkinterval.tg.platt-pt21-first-window-source-packet.v2"
    else:
        raise PacketError("source packet version/encoding is not v1 or v2")
    expected_skn = STAGES * BUCKETS
    expected_payload = (BUCKETS + expected_skn) * interval_bytes
    fixed = (
        header_bytes == HEADER.size
        and endian_tag == ENDIAN_TAG
        and buckets == BUCKETS
        and stages == STAGES
        and 0 < source_terms <= SOURCE_TERMS
        and reserved == 0
        and window_center == WINDOW_CENTER
        and gamma_count == BUCKETS
        and skn_count == expected_skn
        and payload_bytes == expected_payload
        and upstream_commit == UPSTREAM_COMMIT
        and len(raw) == HEADER.size + expected_payload
    )
    if not fixed:
        raise PacketError("source packet header or exact payload length differs")
    view = memoryview(raw)
    gamma_start = HEADER.size
    gamma_end = gamma_start + BUCKETS * interval_bytes
    gamma = view[gamma_start:gamma_end]
    skn = view[gamma_end:]
    if fnv1a64(gamma) != gamma_fnv or fnv1a64(skn) != skn_fnv:
        raise PacketError("source packet FNV payload commitment differs")
    if check_all_intervals:
        for offset in range(HEADER.size, len(raw), interval_bytes):
            if version == VERSION_V1:
                re_lo, re_hi, im_lo, im_hi = struct.unpack_from(
                    "<dddd", raw, offset
                )
                valid = (
                    math.isfinite(re_lo)
                    and math.isfinite(re_hi)
                    and math.isfinite(im_lo)
                    and math.isfinite(im_hi)
                    and re_lo <= re_hi
                    and im_lo <= im_hi
                )
            else:
                re_hi, re_lo, im_hi, im_lo, radius = struct.unpack_from(
                    "<ddddd", raw, offset
                )
                valid = (
                    math.isfinite(re_hi)
                    and math.isfinite(re_lo)
                    and math.isfinite(im_hi)
                    and math.isfinite(im_lo)
                    and math.isfinite(radius)
                    and radius >= 0.0
                )
            if not valid:
                index = (offset - HEADER.size) // interval_bytes
                raise PacketError(f"invalid complex cell at payload index {index}")
    return {
        "accepted": True,
        "bucket_count": buckets,
        "byte_size": len(raw),
        "complete_source_terms": source_terms == SOURCE_TERMS,
        "gamma_count": gamma_count,
        "gamma_fnv1a64": f"{gamma_fnv:016x}",
        "intervals_checked": gamma_count + skn_count if check_all_intervals else 0,
        "interval_encoding": interval_encoding,
        "kind": kind,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "skn_count": skn_count,
        "skn_fnv1a64": f"{skn_fnv:016x}",
        "source_terms": source_terms,
        "taylor_stages": stages,
        "upstream_commit": upstream_commit.decode("ascii"),
        "window_center": window_center,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--skip-interval-scan", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(args.path, check_all_intervals=not args.skip_interval_scan)
    except (OSError, PacketError) as error:
        print(json.dumps({"accepted": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
