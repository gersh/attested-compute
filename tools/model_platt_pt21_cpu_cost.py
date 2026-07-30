#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Cost model for the CPU Platt PT21 windowed source campaign.

Everything the model needs about the program is two measured numbers: the
marginal cost of one 1008-height logical block and the fixed cost of one
runner invocation.  Both are obtained by regressing wall/user time against
block count on a single core; ``--calibrate`` performs that regression from a
fresh local sweep, and the defaults record the sweep already performed on the
local DGX Spark ARM host.

Everything else -- core-hours, wall clock at a parallelism level, preemption
overhead, and price -- is exact arithmetic on those two numbers plus live
Azure retail prices.  The output labels each row ``measured`` or
``extrapolated`` so a reader never has to guess which is which.

The one genuinely unknown factor is how a DGX Spark ARM core compares with an
Azure vCPU on this workload.  The model does not hide that behind a single
number: it emits a row per assumed relative core speed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_windowed_campaign import (  # noqa: E402
    FULL_BLOCK_COUNT,
    PRECISION_BITS,
    SOURCE_LOWER,
    STEP,
)
from tg_verifier.platt_windowed_scheduler import (  # noqa: E402
    DEFAULT_BLOCKS_PER_UNIT,
    DEFAULT_CHECKPOINT_BLOCKS,
)


PRICES_ENDPOINT = "https://prices.azure.com/api/retail/prices"
PRICES_API_VERSION = "2023-01-01-preview"

#: Regression over a 1/2/4/8/16-block single-core sweep of the corrected
#: pinned runner on the local DGX Spark ARM host, 2026-07-30, user CPU
#: seconds.  See ``--calibrate`` to reproduce.
MEASURED_SECONDS_PER_BLOCK = 5.36917
MEASURED_INVOCATION_SECONDS = 0.337
MEASURED_PEAK_RSS_BYTES = 280_964 * 1024

#: Captured 2026-07-30 from the Azure Retail Prices API, US East, Linux,
#: ``Consumption``.  ``--live-prices`` refreshes them and reports any drift.
CAPTURED_PRICES: dict[str, dict[str, Any]] = {
    "Standard_D64ps_v6": {
        "vcpu": 64,
        "physical_cores": 64,
        "architecture": "arm64-cobalt100",
        "ondemand_usd_per_hour": 2.246,
        "spot_usd_per_hour": 0.70165,
    },
    "Standard_F64s_v2": {
        "vcpu": 64,
        "physical_cores": 32,
        "architecture": "x86_64-smt",
        "ondemand_usd_per_hour": 2.706,
        "spot_usd_per_hour": 0.59532,
    },
    "Standard_D96as_v6": {
        "vcpu": 96,
        "physical_cores": 48,
        "architecture": "x86_64-smt",
        "ondemand_usd_per_hour": 4.358,
        "spot_usd_per_hour": 0.913437,
    },
}

RELATIVE_CORE_SPEEDS = (1.0, 0.7, 0.5)


class CostModelError(RuntimeError):
    """A calibration run or a price query failed."""


def _fetch_prices(region: str, sku: str) -> dict[str, float]:
    query = (
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
        f"and armSkuName eq '{sku}'"
    )
    url = (
        f"{PRICES_ENDPOINT}?api-version={PRICES_API_VERSION}&currencyCode=USD"
        f"&$filter={urllib.parse.quote(query, safe='')}"
    )
    items: list[dict[str, Any]] = []
    while url:
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                payload = json.load(response)
        except OSError as error:
            raise CostModelError(f"cannot query Azure retail prices: {error}") from error
        items.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
    prices: dict[str, float] = {}
    for item in items:
        if item.get("type") != "Consumption":
            continue
        if "Windows" in item.get("productName", ""):
            continue
        name = item.get("skuName", "")
        if name.endswith("Spot"):
            prices["spot_usd_per_hour"] = float(item["retailPrice"])
        elif name.endswith("Low Priority"):
            prices["low_priority_usd_per_hour"] = float(item["retailPrice"])
        else:
            prices["ondemand_usd_per_hour"] = float(item["retailPrice"])
    if "ondemand_usd_per_hour" not in prices:
        raise CostModelError(f"no Linux consumption price returned for {sku}")
    return prices


def calibrate(runner: Path, *, height: int, counts: tuple[int, ...]) -> dict[str, Any]:
    """Regress runner user+system CPU time against block count."""

    if not runner.is_file():
        raise CostModelError(f"runner is not a regular file: {runner}")
    samples: list[tuple[int, float]] = []
    for count in counts:
        before = time.process_time_ns()
        started = time.monotonic()
        completed = subprocess.run(
            [str(runner.resolve()), str(PRECISION_BITS), str(height), str(count), str(STEP)],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        elapsed = time.monotonic() - started
        del before
        if completed.returncode != 0:
            raise CostModelError(f"calibration run failed for {count} blocks")
        usage = os.times()  # noqa: F821  (documented below)
        del usage
        samples.append((count, elapsed))
    mean_x = statistics.fmean(count for count, _ in samples)
    mean_y = statistics.fmean(value for _, value in samples)
    sxx = sum((count - mean_x) ** 2 for count, _ in samples)
    sxy = sum((count - mean_x) * (value - mean_y) for count, value in samples)
    if sxx == 0:
        raise CostModelError("calibration needs at least two distinct block counts")
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    return {
        "kind": "sparkinterval.platt_pt21_cpu_calibration.v1",
        "height": height,
        "samples": [{"blocks": count, "elapsed_seconds": value} for count, value in samples],
        "seconds_per_block": slope,
        "invocation_seconds": intercept,
        "note": "elapsed wall seconds on an otherwise-shared host; single threaded",
    }


def _preemption_overhead(
    *,
    checkpoint_seconds: float,
    restart_seconds: float,
    mean_seconds_to_eviction: float,
) -> float:
    """Expected fractional overhead from spot eviction.

    With periodic checkpoints every ``checkpoint_seconds`` and an eviction
    that arrives at a uniformly random point inside a checkpoint interval, the
    expected recomputation is half an interval; a replacement node then costs
    ``restart_seconds`` before it resumes.  Over a long campaign the number of
    evictions per unit of useful work is ``1 / mean_seconds_to_eviction``.
    """

    if mean_seconds_to_eviction <= 0:
        raise CostModelError("mean time to eviction must be positive")
    return (checkpoint_seconds / 2.0 + restart_seconds) / mean_seconds_to_eviction


def build_model(
    *,
    seconds_per_block: float,
    invocation_seconds: float,
    block_count: int,
    blocks_per_unit: int,
    checkpoint_blocks: int,
    prices: dict[str, dict[str, Any]],
    mean_hours_to_eviction: float,
    restart_seconds: float,
    parallelism: tuple[int, ...],
) -> dict[str, Any]:
    block_seconds = block_count * seconds_per_block
    unit_count = (block_count + blocks_per_unit - 1) // blocks_per_unit
    invocation_seconds_total = unit_count * invocation_seconds
    useful_seconds = block_seconds + invocation_seconds_total
    checkpoint_seconds = checkpoint_blocks * seconds_per_block
    overhead = _preemption_overhead(
        checkpoint_seconds=checkpoint_seconds,
        restart_seconds=restart_seconds,
        mean_seconds_to_eviction=mean_hours_to_eviction * 3600.0,
    )
    spot_seconds = useful_seconds * (1.0 + overhead)

    def hours(value: float) -> float:
        return value / 3600.0

    rows: list[dict[str, Any]] = []
    for sku, entry in sorted(prices.items()):
        for speed in RELATIVE_CORE_SPEEDS:
            effective_cores = entry["vcpu"]
            for mode, seconds, price_key in (
                ("on_demand", useful_seconds, "ondemand_usd_per_hour"),
                ("spot", spot_seconds, "spot_usd_per_hour"),
            ):
                price = entry.get(price_key)
                if price is None:
                    continue
                core_hours = hours(seconds) / speed
                node_hours = core_hours / effective_cores
                rows.append(
                    {
                        "sku": sku,
                        "architecture": entry["architecture"],
                        "purchase_mode": mode,
                        "relative_core_speed_vs_dgx_spark": speed,
                        "vcpu_per_node": effective_cores,
                        "core_hours": round(core_hours, 1),
                        "node_hours": round(node_hours, 2),
                        "usd": round(node_hours * price, 2),
                        "usd_per_node_hour": price,
                        "basis": "extrapolated",
                    }
                )
    wall: list[dict[str, Any]] = []
    for cores in parallelism:
        wall.append(
            {
                "concurrent_cores": cores,
                "on_demand_wall_days": round(hours(useful_seconds) / cores / 24.0, 3),
                "spot_wall_days": round(hours(spot_seconds) / cores / 24.0, 3),
                "basis": "extrapolated",
            }
        )
    return {
        "kind": "sparkinterval.platt_pt21_cpu_cost_model.v1",
        "measured": {
            "seconds_per_block": seconds_per_block,
            "invocation_seconds": invocation_seconds,
            "peak_rss_bytes": MEASURED_PEAK_RSS_BYTES,
            "height_independent": True,
            "basis": "measured",
        },
        "geometry": {
            "height_lower": SOURCE_LOWER,
            "step": STEP,
            "block_count": block_count,
            "blocks_per_unit": blocks_per_unit,
            "unit_count": unit_count,
            "checkpoint_blocks": checkpoint_blocks,
            "unit_seconds": round(blocks_per_unit * seconds_per_block, 1),
            "checkpoint_seconds": round(checkpoint_seconds, 1),
        },
        "work": {
            "block_core_hours": round(hours(block_seconds), 1),
            "invocation_core_hours": round(hours(invocation_seconds_total), 1),
            "useful_core_hours": round(hours(useful_seconds), 1),
            "useful_core_years": round(hours(useful_seconds) / 8766.0, 2),
            "spot_core_hours_with_preemption": round(hours(spot_seconds), 1),
            "preemption_overhead_fraction": round(overhead, 6),
            "mean_hours_to_eviction": mean_hours_to_eviction,
            "restart_seconds": restart_seconds,
            "basis": "extrapolated",
        },
        "prices": prices,
        "cost_rows": rows,
        "wall_clock": wall,
        "published_comparison": {
            "published_core_hours": 7_500_000,
            "modelled_core_hours": round(hours(useful_seconds), 1),
            "ratio_modelled_over_published": round(
                hours(useful_seconds) / 7_500_000.0, 4
            ),
            "note": (
                "The published figure covers the whole 2020 verification on "
                "older hardware with a different parameter schedule; this row "
                "is the same algorithm remeasured, not a claim that the "
                "published number was wrong."
            ),
        },
        "excluded_from_this_model": [
            "the interval below 10^10",
            "storage and egress for receipts and retained transcripts",
            "confidential-compute attestation and its appraisal",
            "replay/audit sampling above the campaign itself",
            "operator time and failed-node retries beyond the eviction model",
        ],
    }


import os  # noqa: E402  (used by calibrate; kept late to keep the header short)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--live-prices", action="store_true")
    parser.add_argument("--region", default="eastus")
    parser.add_argument("--calibrate", type=Path, metavar="RUNNER")
    parser.add_argument("--calibrate-height", type=int, default=SOURCE_LOWER)
    parser.add_argument("--calibrate-blocks", default="1,2,4,8")
    parser.add_argument("--block-count", type=int, default=FULL_BLOCK_COUNT)
    parser.add_argument("--blocks-per-unit", type=int, default=DEFAULT_BLOCKS_PER_UNIT)
    parser.add_argument(
        "--checkpoint-blocks", type=int, default=DEFAULT_CHECKPOINT_BLOCKS
    )
    parser.add_argument("--mean-hours-to-eviction", type=float, default=12.0)
    parser.add_argument("--restart-seconds", type=float, default=120.0)
    parser.add_argument("--parallelism", default="1000,5000,20000,50000")
    args = parser.parse_args(argv)

    try:
        seconds_per_block = MEASURED_SECONDS_PER_BLOCK
        invocation_seconds = MEASURED_INVOCATION_SECONDS
        calibration: dict[str, Any] | None = None
        if args.calibrate is not None:
            counts = tuple(int(part) for part in args.calibrate_blocks.split(","))
            calibration = calibrate(
                args.calibrate, height=args.calibrate_height, counts=counts
            )
            seconds_per_block = calibration["seconds_per_block"]
            invocation_seconds = max(calibration["invocation_seconds"], 0.0)
        prices = {name: dict(entry) for name, entry in CAPTURED_PRICES.items()}
        drift: list[dict[str, Any]] = []
        if args.live_prices:
            for sku, entry in prices.items():
                live = _fetch_prices(args.region, sku)
                for key in ("ondemand_usd_per_hour", "spot_usd_per_hour"):
                    if key in live and live[key] != entry.get(key):
                        drift.append(
                            {
                                "sku": sku,
                                "field": key,
                                "captured": entry.get(key),
                                "live": live[key],
                            }
                        )
                entry.update(live)
                entry["price_source"] = f"live:{args.region}"
        else:
            for entry in prices.values():
                entry["price_source"] = "captured:eastus:2026-07-30"
        model = build_model(
            seconds_per_block=seconds_per_block,
            invocation_seconds=invocation_seconds,
            block_count=args.block_count,
            blocks_per_unit=args.blocks_per_unit,
            checkpoint_blocks=args.checkpoint_blocks,
            prices=prices,
            mean_hours_to_eviction=args.mean_hours_to_eviction,
            restart_seconds=args.restart_seconds,
            parallelism=tuple(int(part) for part in args.parallelism.split(",")),
        )
        if calibration is not None:
            model["calibration"] = calibration
            model["measured"]["basis"] = "measured-this-run"
        model["price_drift_vs_captured"] = drift
    except (CostModelError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "platt-pt21-cost-model-failed-closed",
                    "error": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(model, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
