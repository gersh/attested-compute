#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Report the exact site-pin gap for the two confidential-computing PoC runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.azure_poc_site_pin import (  # noqa: E402
    POC_CAMPAIGNS,
    PocSitePinError,
    build_inventory,
)


def _table(report: dict) -> str:
    lines: list[str] = []
    for campaign in report["campaigns"]:
        lines.append("")
        lines.append(f"campaign: {campaign['campaign_id']}  ({campaign['role']})")
        lines.append(
            f"  pins: {campaign['pin_count']} "
            f"({campaign['pins_obtainable_now']} obtainable now, "
            f"{campaign['pins_blocked_on_subscription']} blocked on subscription)"
        )
        for site in campaign["site_examples"]:
            lines.append(f"  {site['example']}")
            for pin in site["pins"]:
                flag = "now " if pin["obtainable_before_subscription"] else "WAIT"
                lines.append(f"    [{flag}] {pin['location']}")
                lines.append(f"           class={pin['pin_class']}")
                lines.append(f"           value={pin['value_kind']}")
                if pin["depends_on"]:
                    lines.append(f"           after={pin['depends_on']}")
        if campaign["silent_requirements"]:
            lines.append("  requirements the redaction scan cannot see:")
            for row in campaign["silent_requirements"]:
                lines.append(f"    {row['location']}: {row['requirement']}")
    summary = report["summary"]
    lines.append("")
    lines.append(
        f"total {summary['total_pins']} pins; "
        f"{summary['pins_obtainable_now']} obtainable without an Azure account; "
        f"{summary['pins_blocked_on_subscription']} not; "
        f"{summary['silent_requirement_count']} silent requirements"
    )
    for name, count in sorted(summary["pin_class_counts"].items()):
        lines.append(f"  {name}: {count}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign",
        choices=sorted(POC_CAMPAIGNS),
        help="restrict the report to one PoC campaign",
    )
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--table",
        action="store_true",
        help="print a human-readable summary instead of JSON",
    )
    args = parser.parse_args(argv)
    try:
        report = build_inventory()
    except (PocSitePinError, OSError, ValueError, RuntimeError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "azure_poc_site_pin_inventory_failed_closed",
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    if args.campaign is not None:
        report = dict(report)
        report["campaigns"] = [
            row for row in report["campaigns"] if row["campaign_id"] == args.campaign
        ]
    if args.table:
        print(_table(report))
        return 0
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
