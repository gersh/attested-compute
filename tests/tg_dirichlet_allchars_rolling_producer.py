#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Test-only producer for the rolling all-character input protocol."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_allchars_stage import write_synthetic_input  # noqa: E402


def main() -> int:
    if len(sys.argv) != 7:
        raise RuntimeError(
            "usage: producer Q FIRST_NUM DEN STEP_NUM BATCH_COUNT OUTPUT"
        )
    q, first, denominator, step, count = map(int, sys.argv[1:6])
    if denominator != 64 or step != 5 or first % 5:
        raise RuntimeError("test producer only supports Platt's 5/64 grid")
    write_synthetic_input(
        Path(sys.argv[6]),
        q=q,
        t_index=first // 5,
        batch_count=count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
