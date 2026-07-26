#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or verify resumable exact Möbius-family CUDA campaigns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.mobius_campaign import (  # noqa: E402
    TARGET_ENDPOINTS,
    MobiusCampaignError,
    run_campaign,
    verify_campaign,
)


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Run hash-linked, resumable exact Möbius segments for the two "
            "little-Mertens, Hurst-Mertens, or CDEM squarefree targets. "
            "Retained output is local external evidence, not GPU attestation "
            "or a Lean proof."
        )
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="start or resume a campaign")
    run.add_argument("--runner", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--target", choices=sorted(TARGET_ENDPOINTS), default="both")
    run.add_argument("--segment-count", type=positive, default=10_000_000)
    run.add_argument("--device", type=nonnegative, default=0)
    run.add_argument("--allow-other-device", action="store_true")
    run.add_argument(
        "--max-chunks",
        type=positive,
        help="stop cleanly after this many new chunks; omit for the full range",
    )
    run.add_argument(
        "--chunk-timeout-seconds",
        type=positive,
        help="fail if one runner invocation exceeds this wall-clock limit",
    )
    run.add_argument(
        "--allow-bounded-test",
        action="store_true",
        help=(
            "permit a fresh local KAT only when segment-count times "
            "max-chunks is at most 64"
        ),
    )
    verify = subcommands.add_parser(
        "verify", help="structurally verify a retained campaign"
    )
    verify.add_argument("output_dir", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "run":
            endpoint = TARGET_ENDPOINTS[args.target]
            requested_work = (
                endpoint
                if args.max_chunks is None
                else min(endpoint, args.segment_count * args.max_chunks)
            )
            require_azure_measured_worker_for_workload(
                exact_production=not args.allow_bounded_test,
                work_bounds=(requested_work,),
            )
            if (
                args.allow_bounded_test
                and args.output_dir.exists()
                and (
                    not args.output_dir.is_dir()
                    or any(args.output_dir.iterdir())
                )
            ):
                raise MobiusCampaignError(
                    "a local bounded KAT requires a fresh empty output directory"
                )
            outcome = run_campaign(
                runner=args.runner,
                output_directory=args.output_dir,
                target=args.target,
                segment_count=args.segment_count,
                device=args.device,
                allow_other_device=args.allow_other_device,
                max_chunks=args.max_chunks,
                chunk_timeout_seconds=args.chunk_timeout_seconds,
            )
        else:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            outcome = verify_campaign(args.output_dir)
    except (MeasuredWorkerScopeError, MobiusCampaignError) as exc:
        print(f"Möbius campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(outcome.as_json(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
