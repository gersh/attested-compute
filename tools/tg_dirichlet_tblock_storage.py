#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inventory or inspect the fail-closed Dirichlet t-block storage boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tblock_storage import (  # noqa: E402
    DirichletTBlockStorageError,
    inventory_campaign,
    project_source_scale,
    storage_boundary,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    inventory = commands.add_parser("inventory")
    inventory.add_argument("campaign_root", type=Path)
    projection = commands.add_parser("project")
    projection.add_argument("campaign_root", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            answer = storage_boundary()
        elif args.command == "inventory":
            answer = inventory_campaign(args.campaign_root)
        elif args.command == "project":
            answer = project_source_scale(
                inventory_campaign(args.campaign_root)
            )
        else:  # pragma: no cover - argparse enforces a command
            raise AssertionError(args.command)
    except (DirichletTBlockStorageError, OSError, ValueError) as error:
        print(f"Dirichlet t-block storage error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(answer, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
