#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Report the auditable 8xH100 TG runtime and Azure-cost model."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.azure_production_sizing import (  # noqa: E402
    ProductionSizingError,
    CPU_SKU,
    NCC_SKU,
    build_sizing_report,
    fetch_retail_prices,
)
from tg_verifier.azure_backend_optimizer import (  # noqa: E402
    PRODUCTION_MAX_COST_USD,
    PRODUCTION_MAX_WALL_HOURS,
)
from tg_verifier.azure_target_sku_calibration import (  # noqa: E402
    TargetSKUCalibrationError,
    load_manifest as load_target_sku_calibration,
)


def _positive_decimal(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("expected a decimal number") from error
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite decimal")
    return value


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected an integer") from error
    if value < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-prices",
        action="store_true",
        help="query Microsoft's Retail Prices API instead of using the dated snapshot",
    )
    parser.add_argument(
        "--deadline-hours",
        type=_positive_decimal,
        help=(
            "optional ideal wall deadline for the fail-closed backend optimizer; "
            "uncalibrated routes remain ineligible"
        ),
    )
    parser.add_argument(
        "--max-cpu-nodes",
        type=_positive_int,
        default=64,
        help="maximum DC96as_v6 nodes available to one campaign (default: 64)",
    )
    parser.add_argument(
        "--max-h100-nodes",
        type=_positive_int,
        default=8,
        help="maximum NCC40ads_H100_v5 nodes available to one campaign (default: 8)",
    )
    parser.add_argument(
        "--production-max-wall-hours",
        type=_positive_decimal,
        default=PRODUCTION_MAX_WALL_HOURS,
        help="hard production-readiness wall cap; may tighten but not exceed 168",
    )
    parser.add_argument(
        "--production-max-cost-usd",
        type=_positive_decimal,
        default=PRODUCTION_MAX_COST_USD,
        help="hard production-readiness cost cap; may tighten but not exceed 10000",
    )
    parser.add_argument(
        "--target-sku-calibration",
        action="append",
        type=Path,
        default=[],
        help=(
            "explicit canonical target-SKU calibration manifest; repeat for "
            "multiple exact route-resource branches"
        ),
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        prices = (
            fetch_retail_prices(sku=NCC_SKU) if args.refresh_prices else None
        )
        cpu_prices = (
            fetch_retail_prices(sku=CPU_SKU) if args.refresh_prices else None
        )
        report = build_sizing_report(
            prices=prices,
            cpu_prices=cpu_prices,
            deadline_hours=args.deadline_hours,
            max_cpu_nodes=args.max_cpu_nodes,
            max_h100_nodes=args.max_h100_nodes,
            production_max_wall_hours=args.production_max_wall_hours,
            production_max_cost_usd=args.production_max_cost_usd,
            target_sku_calibrations=tuple(
                load_target_sku_calibration(path)
                for path in args.target_sku_calibration
            ),
        )
    except (
        OSError,
        ValueError,
        ProductionSizingError,
        TargetSKUCalibrationError,
    ) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            report,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
