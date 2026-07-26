#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate and inspect a PT21 required-region DD/sign packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_required_sign_packet import (  # noqa: E402
    PlattRequiredSignPacketError,
    inspect_required_sign_packet,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--source-packet", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = inspect_required_sign_packet(
            args.packet, source_packet=args.source_packet
        )
    except (OSError, ValueError, PlattRequiredSignPacketError) as error:
        result = {
            "schema": "sparkinterval.tg.platt-required-sign-packet-inspection.v1",
            "accepted": False,
            "classification": "required-sign-packet-failed-closed",
            "error": str(error),
            "zero_isolation_events_constructed": False,
            "turing_event_stream_constructed": False,
            "global_zero_count_constructed": False,
            "lean_source_claim_ready": False,
        }
        print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
