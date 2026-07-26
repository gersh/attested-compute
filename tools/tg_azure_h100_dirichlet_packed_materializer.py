#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan or materialize one nonterminal Dirichlet TGDBSPK1 H100 job."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.azure_h100_dirichlet_packed_materializer import (  # noqa: E402
    DirichletPackedMaterializerError,
    load_site,
    materialize,
    plan_materialization,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "materialize"))
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    try:
        site = load_site(args.site)
        operation = (
            plan_materialization
            if args.command == "plan"
            else materialize
        )
        result = operation(site)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        DirichletPackedMaterializerError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": (
                        "dirichlet_h100_packed_materialization_failed_closed"
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
