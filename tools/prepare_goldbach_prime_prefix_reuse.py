#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the unpromoted Goldbach v2 prime-prefix source candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_prime_prefix_reuse_candidate import (
    prepare_prime_prefix_reuse_source,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v1_source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = prepare_prime_prefix_reuse_source(
        args.v1_source, args.destination
    )
    print(
        json.dumps(
            result,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
