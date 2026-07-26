#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, produce, or replay the split v3 small-q certificate service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_booker_smallq import transform_parameters  # noqa: E402
from tg_verifier.dirichlet_booker_smallq_factored import (  # noqa: E402
    FactoredSmallQError,
    factored_service_batch_plan,
    source_work,
    verify_factored_service_campaign,
    write_factored_service_campaign,
)
from tg_verifier.dirichlet_campaign import (  # noqa: E402
    primitive_character_count,
    primitive_character_descriptor,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _roster(q: int) -> tuple[int, ...]:
    return tuple(
        int(primitive_character_descriptor(q, ordinal)["conrey_number"])
        for ordinal in range(primitive_character_count(q))
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)

    work = commands.add_parser("source-work", help="exact source payload and memory plan")
    work.add_argument("--usable-device-bytes", type=_positive, default=80 * 1024**3)

    plan = commands.add_parser("plan-q", help="write one full source q campaign")
    plan.add_argument("q", type=_positive)
    plan.add_argument("plan", type=Path)
    plan.add_argument("batch_directory", type=Path)
    plan.add_argument("--usable-device-bytes", type=_positive, default=80 * 1024**3)
    plan.add_argument("--maximum-batch-characters", type=_positive)

    verify = commands.add_parser("verify-q", help="independently replay one q campaign")
    verify.add_argument("q", type=_positive)
    verify.add_argument("plan", type=Path)
    verify.add_argument("batch_directory", type=Path)
    verify.add_argument("--guard-bits", type=_positive, default=64)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "source-work":
            value = source_work(usable_device_bytes=args.usable_device_bytes)
        elif args.command == "plan-q":
            numbers = _roster(args.q)
            parameters = transform_parameters(args.q)
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            memory_plan = factored_service_batch_plan(
                q=args.q,
                transform_length=parameters.transform_length,
                character_count=len(numbers),
                usable_device_bytes=args.usable_device_bytes,
            )
            maximum_batch = (
                args.maximum_batch_characters
                if args.maximum_batch_characters is not None
                else int(memory_plan["maximum_batch_characters"])
            )
            value = write_factored_service_campaign(
                args.plan,
                args.batch_directory,
                q=args.q,
                conrey_numbers=numbers,
                parameters=parameters,
                maximum_batch_characters=maximum_batch,
            )
            value["device_memory_plan"] = memory_plan
        else:
            numbers = _roster(args.q)
            parameters = transform_parameters(args.q)
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            paths = sorted(args.batch_directory.glob("batch-*.bin"))
            value = verify_factored_service_campaign(
                args.plan,
                paths,
                parameters=parameters,
                expected_conrey_numbers=numbers,
                guard_bits=args.guard_bits,
            )
    except (FactoredSmallQError, MeasuredWorkerScopeError) as error:
        print(f"tg_dirichlet_booker_smallq_factored: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(value, indent=2 if args.pretty else None, sort_keys=True,
                   separators=None if args.pretty else (",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
