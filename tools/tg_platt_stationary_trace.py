#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Check a PT21 stationary trace or extract its source-trace payload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.platt_stationary_trace import (  # noqa: E402
    PT21StationaryTraceError,
    load,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument(
        "--extract-resolutions",
        action="store_true",
        help="emit only the canonical stationary_resolutions array",
    )
    arguments = parser.parse_args()
    try:
        # This CLI is the retained production-trace replay.  Unit tests use
        # the pure validator directly; the command-line route is cloud-only
        # and fails before opening the trace.
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
        value = load(arguments.trace)
    except (MeasuredWorkerScopeError, OSError, PT21StationaryTraceError) as error:
        print(f"tg_platt_stationary_trace: {error}", file=sys.stderr)
        return 2
    if arguments.extract_resolutions:
        print(
            json.dumps(
                value["stationary_resolutions"],
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        print(
            json.dumps(
                {
                    "accepted": value["accepted"],
                    "ambiguous_input_disks": value["ambiguous_input_disks"],
                    "candidate_count": value["candidate_count"],
                    "input_sha256": value["input_sha256"],
                    "interpolation_evaluations": value[
                        "interpolation_evaluations"
                    ],
                    "refinements_applied": value["refinements_applied"],
                    "replay_accepted": value["replay_accepted"],
                    "resolution_sha256": value["resolution_sha256"],
                    "semantic_status": value["semantic_status"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return 0 if value["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
