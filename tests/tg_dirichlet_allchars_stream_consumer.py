#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Test-only compact sink for the all-character persistent stream protocol.

The production slot is reserved for the completed-L/zero-scan consumer.  This
KAT sink only validates the binary envelope and commits the streamed values;
it must not be represented as analytic closure.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys


OUTPUT_HEADER = struct.Struct("<8sIIIIQQQQ")
ITEM = struct.Struct("<dddd")


def main() -> int:
    if len(sys.argv) != 2:
        raise RuntimeError("usage: consumer RECEIPT")
    raw_header = sys.stdin.buffer.read(OUTPUT_HEADER.size)
    if len(raw_header) != OUTPUT_HEADER.size:
        raise RuntimeError("truncated stream header")
    fields = OUTPUT_HEADER.unpack(raw_header)
    magic, version, q, components, batches, order, count, butterflies, elapsed = fields
    if magic != b"TGDAFFO1" or version != 1 or batches <= 0 or count != batches * order:
        raise RuntimeError("invalid stream identity")
    digest = hashlib.sha256(raw_header)
    for _ in range(count):
        raw = sys.stdin.buffer.read(ITEM.size)
        if len(raw) != ITEM.size:
            raise RuntimeError("truncated stream value")
        re_lo, re_hi, im_lo, im_hi = ITEM.unpack(raw)
        if not (
            all(math.isfinite(value) for value in (re_lo, re_hi, im_lo, im_hi))
            and re_lo <= re_hi
            and im_lo <= im_hi
        ):
            raise RuntimeError("malformed stream interval")
        digest.update(raw)
    if sys.stdin.buffer.read(1):
        raise RuntimeError("trailing stream bytes")
    receipt = {
        "kind": "sparkinterval.tg.dirichlet_allchars.test_sink_receipt.v1",
        "classification": "format_kat_not_completed_l_or_zero_scan",
        "q": q,
        "component_count": components,
        "batch_count": batches,
        "group_order": order,
        "value_count": count,
        "radix2_butterflies": butterflies,
        "elapsed_nanoseconds": elapsed,
        "stream_sha256": digest.hexdigest(),
    }
    path = Path(sys.argv[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    temporary.replace(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
