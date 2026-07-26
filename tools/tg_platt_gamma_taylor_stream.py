#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Authenticate and inspect a PT21 all-window Gamma/Taylor stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_gamma_taylor_stream import (  # noqa: E402
    PlattGammaTaylorStreamError,
    inspect_gamma_taylor_stream,
    inspection_report,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stream", type=Path)
    parser.add_argument("--expected-first-block", type=int)
    parser.add_argument("--expected-block-count", type=int)
    parser.add_argument("--expected-stream-sha256")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        # This command streams and rechecks the all-window production trace.
        # Keep the guard ahead of the first file access.
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
        inspection = inspect_gamma_taylor_stream(
            args.stream,
            expected_first_block=args.expected_first_block,
            expected_block_count=args.expected_block_count,
            expected_stream_sha256=args.expected_stream_sha256,
        )
        result = inspection_report(inspection)
    except (OSError, ValueError, PlattGammaTaylorStreamError) as error:
        result = {
            "schema": "sparkinterval.tg.platt-gamma-taylor-stream-inspection.v1",
            "accepted": False,
            "classification": "gamma-taylor-stream-failed-closed",
            "error": str(error),
            "flint_to_mathlib_realization_proved": False,
            "pt21_source_claim_discharged": False,
        }
        print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
