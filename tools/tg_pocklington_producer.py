#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""General-prime certificate producer for the Goldbach ladder protocol.

This is a liveness fallback for the bounded in-process grid search.  It may
search indefinitely, but it can never add a rung without emitting a recursive
Pocklington object that the separate campaign checker accepts exactly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_campaign import (  # noqa: E402
    GENERAL_REQUEST_KIND,
    GENERAL_RESULT_KIND,
    POCKLINGTON_KIND,
    CampaignError,
    canonical_json_bytes,
    check_pocklington_object,
    find_general_pocklington,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _load(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise CampaignError("general-prime request is not canonical JSON")
    if set(value) != {"kind", "lower_exclusive", "upper_exclusive"}:
        raise CampaignError("general-prime request fields differ")
    if value["kind"] != GENERAL_REQUEST_KIND:
        raise CampaignError("general-prime request kind differs")
    return value


def _decimal(value: object, name: str) -> int:
    if not isinstance(value, str) or not value.isdigit() or (
        len(value) > 1 and value.startswith("0")
    ):
        raise CampaignError(f"{name} must be a canonical decimal integer")
    return int(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    request = _load(args.request)
    lower = _decimal(request["lower_exclusive"], "lower_exclusive")
    upper = _decimal(request["upper_exclusive"], "upper_exclusive")
    if upper <= lower + 1:
        raise CampaignError("general-prime request interval is empty")
    require_azure_measured_worker_for_workload(
        exact_production=False,
        work_bounds=(upper - lower - 1,),
    )
    rung, certificate = find_general_pocklington(
        lower, upper, factor_prime_attempts=0
    )
    if rung.certificate_kind != "pocklington" or not check_pocklington_object(
        certificate, expected=rung.number
    ):
        raise CampaignError("fallback did not construct a checked Pocklington object")
    if certificate.get("kind") != POCKLINGTON_KIND:
        raise CampaignError("fallback certificate kind differs")
    certificate_path = (args.output.parent / "pocklington-certificate.json").resolve()
    certificate_path.write_bytes(canonical_json_bytes(certificate))
    result = {
        "certificate_kind": "pocklington",
        "certificate_path": str(certificate_path),
        "kind": GENERAL_RESULT_KIND,
        "number": str(rung.number),
    }
    args.output.write_bytes(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CampaignError, OSError, ValueError) as error:
        print(f"tg_pocklington_producer: {error}", file=sys.stderr)
        raise SystemExit(2)
