#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan or build one closed shared-Hurst Azure CPU phase package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.azure_cpu_hurst_materializer import (  # noqa: E402
    HurstMaterializerError,
    load_site,
    materialize,
    plan_materialization,
)
from tg_verifier.azure_cpu_portfolio_materializer import (  # noqa: E402
    MaterializerError as CommonMaterializerError,
)
from tg_verifier.azure_portfolio import PortfolioError, load_portfolio_spec  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "materialize"))
    parser.add_argument("portfolio_spec", type=Path)
    parser.add_argument("group_id")
    parser.add_argument("shard_index", type=int)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    try:
        context = load_portfolio_spec(args.portfolio_spec)
        site = load_site(args.site)
        operation = plan_materialization if args.command == "plan" else materialize
        result = operation(context, args.group_id, args.shard_index, site)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        CommonMaterializerError,
        HurstMaterializerError,
        PortfolioError,
        OSError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "hurst_cpu_materialization_failed_closed",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
