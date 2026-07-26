#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run and independently replay the native Helfgott--Platt ladder producer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_campaign import (  # noqa: E402
    CampaignError,
    SOURCE_MAXIMUM_GAP,
    canonical_json_bytes,
)
from tg_verifier.goldbach_native_ladder import (  # noqa: E402
    invoke_native_segment,
    produce_native_group,
    produce_native_independent_range,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


def _path(value: str | None) -> Path | None:
    return None if value is None else Path(value).resolve()


def _emit(value: object, pretty: bool) -> None:
    if pretty:
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        sys.stdout.buffer.write(canonical_json_bytes(value))


def _add_general_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--general-prime-producer")
    parser.add_argument("--general-prime-checker")
    parser.add_argument(
        "--no-builtin-pocklington",
        action="store_false",
        dest="builtin_pocklington",
        help="fail unless an external certified general-prime producer is configured",
    )
    parser.add_argument("--sieve-block-candidates", type=int, default=1 << 24)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    segment = subparsers.add_parser(
        "segment", help="run and independently replay one bounded native segment"
    )
    segment.add_argument("--runner", type=Path, required=True)
    segment.add_argument("--anchor-number", type=int, required=True)
    segment.add_argument("--target-number", type=int, required=True)
    segment.add_argument(
        "--coverage-step", type=int, default=SOURCE_MAXIMUM_GAP - 2
    )
    segment.add_argument("--proth-exponent", type=int, default=52)
    segment.add_argument("--sieve-block-candidates", type=int, default=1 << 24)

    produce_range = subparsers.add_parser(
        "produce-range",
        help="produce one exact full-source range into the parallel campaign",
    )
    produce_range.add_argument("directory", type=Path)
    produce_range.add_argument("index", type=int)
    produce_range.add_argument("--runner", type=Path, required=True)
    _add_general_options(produce_range)

    produce_group = subparsers.add_parser(
        "produce-group", help="run a bounded native CPU pool over one array group"
    )
    produce_group.add_argument("directory", type=Path)
    produce_group.add_argument("--runner", type=Path, required=True)
    produce_group.add_argument("--group-index", type=int, required=True)
    produce_group.add_argument("--group-count", type=int, required=True)
    produce_group.add_argument("--local-workers", type=int, default=1)
    produce_group.add_argument("--summary", type=Path)
    _add_general_options(produce_group)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "segment":
            if args.target_number <= args.anchor_number:
                raise CampaignError(
                    "target number must be greater than anchor number"
                )
            span = args.target_number - args.anchor_number
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(
                    span,
                    min(args.coverage_step, span),
                    min(args.sieve_block_candidates, span),
                ),
            )
            with invoke_native_segment(
                args.runner,
                anchor_number=args.anchor_number,
                target_number=args.target_number,
                coverage_step=args.coverage_step,
                proth_exponent=args.proth_exponent,
                sieve_block_candidates=args.sieve_block_candidates,
            ) as run:
                rungs = 0
                last = args.anchor_number
                for rung in run.checked_rungs():
                    rungs += 1
                    last = rung.number
                _emit(
                    {
                        "benchmark_only_not_a_certificate": True,
                        "complete_without_general_prime": run.header.complete,
                        "independently_replayed_rungs": rungs,
                        "kind": "tg_goldbach_native_segment_replay_v1",
                        "last_replayed_number": str(last),
                        "native_protocol_sha256": run.protocol_sha256,
                        "native_report": dict(run.report),
                        "runner_sha256": run.runner_sha256,
                    },
                    args.pretty,
                )
            return 0

        # Both range commands deliberately accept only the historical or
        # analytic-10^27 reviewed production profiles.  Refuse them before
        # opening the campaign manifest or native runner.
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
        common = {
            "runner": args.runner,
            "general_prime_producer": _path(args.general_prime_producer),
            "external_prime_checker": _path(args.general_prime_checker),
            "builtin_pocklington": args.builtin_pocklington,
            "sieve_block_candidates": args.sieve_block_candidates,
        }
        if args.command == "produce-range":
            ordinary, native = produce_native_independent_range(
                args.directory, args.index, **common
            )
            _emit(
                {"native_producer_receipt": native, "range_receipt": ordinary},
                args.pretty,
            )
            return 0
        if args.command == "produce-group":
            result = produce_native_group(
                args.directory,
                group_index=args.group_index,
                group_count=args.group_count,
                local_workers=args.local_workers,
                **common,
            )
            if args.summary is not None:
                if args.summary.exists():
                    existing = args.summary.read_bytes()
                    if existing != canonical_json_bytes(result):
                        raise CampaignError("existing group summary differs")
                else:
                    args.summary.parent.mkdir(parents=True, exist_ok=True)
                    args.summary.write_bytes(canonical_json_bytes(result))
            _emit(result, args.pretty)
            return 0
        raise CampaignError("unknown native ladder command")
    except (
        CampaignIOError,
        CampaignError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"tg_goldbach_ladder_native: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
