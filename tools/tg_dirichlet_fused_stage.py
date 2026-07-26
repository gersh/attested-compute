#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exercise the compact fused selected-character Dirichlet stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_fused_stage import (  # noqa: E402
    DirichletFusedStageError,
    capability_report,
    inspect_compact_input,
    write_synthetic_compact_input,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _nonnegative(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def _emit(value: object, pretty: bool) -> None:
    print(json.dumps(value, sort_keys=True, indent=2 if pretty else None,
                     separators=None if pretty else (",", ":")))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    synthetic = commands.add_parser("synthetic-input")
    synthetic.add_argument("output", type=Path)
    synthetic.add_argument("--q", type=_positive, action="append", required=True)
    synthetic.add_argument("--t-index", type=_nonnegative, default=0)
    mode = synthetic.add_mutually_exclusive_group(required=True)
    mode.add_argument("--characters-per-q", type=_positive)
    mode.add_argument("--all-characters", action="store_true")
    inspect = commands.add_parser("inspect-input")
    inspect.add_argument("input", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "capability":
            value = capability_report()
        elif args.command == "synthetic-input":
            selected = (
                sum(args.q)
                if args.all_characters
                else len(args.q) * args.characters_per_q
            )
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(selected,),
            )
            value = write_synthetic_compact_input(
                args.output,
                q_values=args.q,
                t_index=args.t_index,
                characters_per_q=(
                    None if args.all_characters else args.characters_per_q
                ),
            )
        elif args.command == "inspect-input":
            value = inspect_compact_input(args.input)
        else:  # pragma: no cover
            raise AssertionError("unreachable command")
        _emit(value, args.pretty)
        return 0
    except MeasuredWorkerScopeError as error:
        print(f"tg_dirichlet_fused_stage: {error}", file=sys.stderr)
        return 2
    except (DirichletFusedStageError, OSError, ValueError) as error:
        print(f"tg_dirichlet_fused_stage: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
