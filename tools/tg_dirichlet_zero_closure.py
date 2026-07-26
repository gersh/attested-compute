#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build and run source-shaped Dirichlet zero-closure chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_zero_closure import (  # noqa: E402
    DirichletZeroClosureError,
    capability_report,
    load_canonical_json,
    make_known_answer_request,
    request_from_campaign,
    validate_request,
    validate_result,
    write_canonical_json,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


PRODUCER = ROOT / "tools" / "tg_dirichlet_zero_closure_producer.py"
CHECKER = ROOT / "tools" / "tg_dirichlet_zero_closure_checker.py"


def _emit(value: object, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def _run(argv: list[str]) -> None:
    completed = subprocess.run(argv, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise DirichletZeroClosureError(
            f"role-separated closure command failed with exit {completed.returncode}"
        )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    kat = commands.add_parser("known-answer-request")
    kat.add_argument("output", type=Path)
    adapt = commands.add_parser("from-campaign-request")
    adapt.add_argument("campaign_request", type=Path)
    adapt.add_argument("output", type=Path)
    run = commands.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("result", type=Path)
    run.add_argument("receipt", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("request", type=Path)
    verify.add_argument("result", type=Path)
    verify.add_argument("receipt", type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("request", type=Path)
    inspect.add_argument("result", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        value: object | None = None
        if args.command == "capability":
            value = capability_report()
        elif args.command == "known-answer-request":
            value = make_known_answer_request()
            write_canonical_json(args.output, value)
        elif args.command == "from-campaign-request":
            campaign = load_canonical_json(args.campaign_request)
            value = request_from_campaign(campaign)
            write_canonical_json(args.output, value)
        elif args.command == "run":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            validate_request(load_canonical_json(args.request))
            _run(
                [
                    sys.executable,
                    str(PRODUCER),
                    "produce",
                    "--request",
                    str(args.request),
                    "--output",
                    str(args.result),
                ]
            )
            _run(
                [
                    sys.executable,
                    str(CHECKER),
                    "verify",
                    "--request",
                    str(args.request),
                    "--result",
                    str(args.result),
                    "--receipt",
                    str(args.receipt),
                ]
            )
            value = load_canonical_json(args.receipt)
        elif args.command == "verify":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            _run(
                [
                    sys.executable,
                    str(CHECKER),
                    "verify",
                    "--request",
                    str(args.request),
                    "--result",
                    str(args.result),
                    "--receipt",
                    str(args.receipt),
                ]
            )
            value = load_canonical_json(args.receipt)
        elif args.command == "inspect":
            request = validate_request(load_canonical_json(args.request))
            value = validate_result(request, load_canonical_json(args.result))
        else:  # pragma: no cover
            raise AssertionError("unreachable command")
        if value is not None:
            _emit(value, args.pretty)
        return 0
    except (DirichletZeroClosureError, OSError, ValueError) as error:
        print(f"tg_dirichlet_zero_closure: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
