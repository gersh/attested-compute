#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan or build one lowered-Goldbach H100 measured-job package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.azure_h100_goldbach_10pow27_materializer import (  # noqa: E402
    Goldbach10Pow27H100MaterializerError,
    export_retained_group,
    load_site,
    materialize,
    plan_materialization,
)
from tg_verifier.azure_portfolio import (  # noqa: E402
    PortfolioError,
    load_portfolio_spec,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "materialize"):
        child = commands.add_parser(name)
        child.add_argument("portfolio_spec", type=Path)
        child.add_argument("group_id")
        child.add_argument("shard_index", type=int)
        child.add_argument("site", type=Path)
    export = commands.add_parser(
        "export", help="verify and copy one signed retained H100 group archive"
    )
    export.add_argument("materialization_manifest", type=Path)
    export.add_argument("signed_receipt", type=Path)
    export.add_argument("key_manifest", type=Path)
    export.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result = export_retained_group(
                args.materialization_manifest,
                args.signed_receipt,
                args.key_manifest,
                args.output,
            )
        else:
            context = load_portfolio_spec(args.portfolio_spec)
            site = load_site(args.site)
            operation = (
                plan_materialization if args.command == "plan" else materialize
            )
            result = operation(context, args.group_id, args.shard_index, site)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        Goldbach10Pow27H100MaterializerError,
        PortfolioError,
        OSError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": (
                        "goldbach10pow27_h100_materialization_failed_closed"
                    ),
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
