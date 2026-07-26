#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate or extract a source-bound PT21 one-sided Turing input artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_turing_inputs import (  # noqa: E402
    PT21TuringInputsError,
    load,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--expected-block", required=True, type=int)
    parser.add_argument("--expected-packet-sha256", required=True)
    parser.add_argument(
        "--extract-trace-payload",
        action="store_true",
        help="print only the lower/upper object accepted as trace.turing_inputs",
    )
    arguments = parser.parse_args()
    try:
        result = load(
            arguments.artifact,
            expected_block=arguments.expected_block,
            expected_packet_sha256=arguments.expected_packet_sha256,
        )
    except (OSError, PT21TuringInputsError) as error:
        print(f"tg_platt_pt21_turing_inputs: {error}", file=sys.stderr)
        return 2
    output = (
        result["turing_inputs"] if arguments.extract_trace_payload else result
    )
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
