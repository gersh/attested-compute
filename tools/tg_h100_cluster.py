#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, verify, or execute all thirteen TG workflows on a Slurm cluster."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.h100_cluster import (  # noqa: E402
    ATOM_IDS,
    ClusterPlanError,
    capability_report,
    execute_job,
    verify_deployment,
    write_deployment,
)


def emit(value: object, *, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    capability = commands.add_parser(
        "capability", help="classify all thirteen jobs without running them"
    )
    capability.set_defaults(handler="capability")

    plan = commands.add_parser(
        "plan", help="write a deterministic portable manifest and Slurm adapter"
    )
    plan.add_argument("directory", type=Path)
    plan.add_argument(
        "--repository",
        type=Path,
        default=REPOSITORY_ROOT,
        help="clean reviewed Git worktree to bind (default: this checkout)",
    )
    plan.set_defaults(handler="plan")

    verify = commands.add_parser(
        "verify", help="verify manifest and every generated Slurm adapter byte"
    )
    verify.add_argument("directory", type=Path)
    verify.add_argument(
        "--repository",
        type=Path,
        default=REPOSITORY_ROOT,
        help="clean reviewed Git worktree whose complete closure must match",
    )
    verify.set_defaults(handler="verify")

    execute = commands.add_parser(
        "execute",
        help="run one reviewed full-source argument vector (normally from Slurm)",
    )
    execute.add_argument("manifest", type=Path)
    execute.add_argument("--atom", choices=ATOM_IDS, required=True)
    execute.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve and check prerequisites without starting the computation",
    )
    execute.set_defaults(handler="execute")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.handler == "capability":
            result = capability_report()
        elif args.handler == "plan":
            result = write_deployment(
                args.directory.resolve(), args.repository.resolve()
            )
        elif args.handler == "verify":
            result = verify_deployment(
                args.directory.resolve(), args.repository.resolve()
            )
        else:
            result = execute_job(
                args.manifest.resolve(), args.atom, dry_run=args.dry_run
            )
        emit(result, pretty=args.pretty)
        return 0
    except (ClusterPlanError, OSError, ValueError) as error:
        emit(
            {
                "accepted": False,
                "classification": "cluster_adapter_failed_closed",
                "error": str(error),
                "campaigns_completed": 0,
                "lean_atoms_discharged": 0,
            },
            pretty=args.pretty,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
