#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Print the exact resident q-major source partition."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_resident_qmajor_plan import source_projection


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute the exact ten-phase resident q-major Dirichlet plan."
        )
    )
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    if arguments.pretty:
        print(json.dumps(source_projection(), indent=2, sort_keys=True))
    else:
        print(json.dumps(source_projection(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
