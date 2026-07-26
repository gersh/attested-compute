#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independently validate one retained PT21EVT1 event-stage stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_event_record import (  # noqa: E402
    PT21EventRecordError,
    validate_stream,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stream", type=Path)
    parser.add_argument("--expected-gamma-stream-sha256", required=True)
    parser.add_argument("--expected-producer-sha256", required=True)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        report = validate_stream(
            arguments.stream,
            expected_gamma_stream_sha256=(
                arguments.expected_gamma_stream_sha256
            ),
            expected_producer_sha256=arguments.expected_producer_sha256,
        )
    except (OSError, PT21EventRecordError) as error:
        print(f"tg_platt_pt21_event_record: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            report,
            sort_keys=True,
            indent=2 if arguments.pretty else None,
            separators=None if arguments.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
