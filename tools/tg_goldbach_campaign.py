#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, run, resume, and replay the Helfgott--Platt ladder campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_campaign import (
    CampaignError,
    CampaignParameters,
    SOURCE_ENDPOINT,
    SOURCE_RANGE_COUNT,
    SOURCE_RANGE_WIDTH,
    advance_replay_state,
    canonical_json_bytes,
    initialize_campaign,
    produce_next_range,
    replay_campaign,
    verify_complete_campaign,
)
from tg_verifier import binary_goldbach_campaign as binary_campaign  # noqa: E402


def _path(value: str | None) -> Path | None:
    return None if value is None else Path(value).resolve()


def _emit(value: object, *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        sys.stdout.buffer.write(canonical_json_bytes(value))


def _status(directory: Path, general_checker: Path | None) -> dict[str, object]:
    state = replay_campaign(directory, external_prime_checker=general_checker)
    complete = state.completed_ranges == state.parameters.range_count
    return {
        "atom_id": "helfgott-platt-theorem-4-1",
        "completed_ranges": state.completed_ranges,
        "covered_through": str(state.covered_through),
        "full_source": state.parameters.mode == "full_source",
        "last_range_sha256": state.previous_sha256,
        "prime_ladder_complete": complete,
        "range_count": state.parameters.range_count,
        "total_unique_ladder_rungs": str(state.total_records),
        "warning": (
            "A complete ladder is still conditional on replaying the separate "
            "binary-Goldbach-through-4e18 prerequisite."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="print the immutable source schedule")
    plan.set_defaults(command_name="plan")

    initialize = subparsers.add_parser("init", help="initialize a full-source directory")
    initialize.add_argument("directory", type=Path)

    status = subparsers.add_parser("status", help="replay the contiguous prefix")
    status.add_argument("directory", type=Path)
    status.add_argument("--general-prime-checker")

    run = subparsers.add_parser("run", help="resume production after replaying the prefix")
    run.add_argument("directory", type=Path)
    run.add_argument("--general-prime-producer")
    run.add_argument("--general-prime-checker")
    run.add_argument(
        "--builtin-pocklington",
        action="store_true",
        help="use the in-repo dense Pocklington grid when no Proth-52 rung exists",
    )
    run.add_argument(
        "--max-new-ranges",
        type=int,
        default=0,
        help="stop after this many new ranges; zero means run to the source endpoint",
    )

    verify = subparsers.add_parser(
        "verify", help="replay the complete ladder and binary-Goldbach prerequisite"
    )
    verify.add_argument("directory", type=Path)
    verify.add_argument("--binary-checker")
    verify.add_argument("--binary-artifact")
    verify.add_argument("--binary-campaign")
    verify.add_argument("--general-prime-checker")

    full = subparsers.add_parser(
        "full",
        help="auto-init/resume and verify both exact full-source computations",
    )
    full.add_argument("workspace", type=Path)
    full.add_argument(
        "--binary-evens-per-chunk",
        type=int,
        default=binary_campaign.DEFAULT_SOURCE_EVENS_PER_CHUNK,
    )
    full.add_argument(
        "--general-prime-producer",
        help=(
            "optional ECPP/general-prime producer used if the bounded built-in "
            "Pocklington search does not find a rung"
        ),
    )
    full.add_argument("--general-prime-checker")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            parameters = CampaignParameters()
            _emit(
                {
                    "binary_goldbach_prerequisite": {
                        "every_even": True,
                        "first_even": "4",
                        "last_even": "4000000000000000000",
                    },
                    "endpoint": str(SOURCE_ENDPOINT),
                    "parameters": parameters.to_json(),
                    "primary_source": "https://arxiv.org/abs/1305.3062v2",
                    "range_count": SOURCE_RANGE_COUNT,
                    "range_width": str(SOURCE_RANGE_WIDTH),
                    "verification_note": (
                        "The ladder and the binary-Goldbach prerequisite are "
                        "independent computations; both must replay."
                    ),
                },
                pretty=args.pretty,
            )
            return 0

        if args.command == "full":
            workspace = args.workspace.resolve()
            binary_directory = workspace / "binary-goldbach-through-4e18"
            directory = workspace / "ternary-prime-ladder"
            binary_campaign.initialize(
                binary_directory,
                binary_campaign.Parameters(evens_per_chunk=args.binary_evens_per_chunk),
            )
            binary_state = binary_campaign.replay(binary_directory)
            while binary_state.completed_chunks < binary_state.parameters.chunk_count:
                binary_state = binary_campaign.produce_next(binary_directory, binary_state)
                print(
                    f"verified binary chunk {binary_state.completed_chunks}/"
                    f"{binary_state.parameters.chunk_count}",
                    file=sys.stderr,
                    flush=True,
                )
            # This call refuses a bounded/sample campaign even if its endpoint
            # happens to equal the source endpoint through malformed metadata.
            binary_campaign.verify_complete(binary_directory)
            initialize_campaign(directory)
            general_checker = _path(args.general_prime_checker)
            general_producer = _path(args.general_prime_producer)
            state = replay_campaign(directory, external_prime_checker=general_checker)
            while state.completed_ranges < state.parameters.range_count:
                produce_next_range(
                    directory,
                    state=state,
                    general_prime_producer=general_producer,
                    external_prime_checker=general_checker,
                    builtin_pocklington=True,
                )
                state = advance_replay_state(
                    directory, state, external_prime_checker=general_checker
                )
                print(
                    f"verified ladder range {state.completed_ranges}/"
                    f"{state.parameters.range_count}",
                    file=sys.stderr,
                    flush=True,
                )
            receipt = verify_complete_campaign(
                directory,
                binary_campaign=binary_directory,
                external_prime_checker=general_checker,
            )
            _emit(receipt, pretty=args.pretty)
            return 0

        directory = args.directory.resolve()
        if args.command == "init":
            initialize_campaign(directory)
            _emit(_status(directory, None), pretty=args.pretty)
            return 0

        general_checker = _path(args.general_prime_checker)
        if args.command == "status":
            _emit(_status(directory, general_checker), pretty=args.pretty)
            return 0

        if args.command == "run":
            if args.max_new_ranges < 0:
                parser.error("--max-new-ranges must be nonnegative")
            state = replay_campaign(directory, external_prime_checker=general_checker)
            stop = state.parameters.range_count
            if args.max_new_ranges:
                stop = min(stop, state.completed_ranges + args.max_new_ranges)
            producer = _path(args.general_prime_producer)
            while state.completed_ranges < stop:
                produce_next_range(
                    directory,
                    state=state,
                    general_prime_producer=producer,
                    external_prime_checker=general_checker,
                    builtin_pocklington=args.builtin_pocklington,
                )
                state = advance_replay_state(
                    directory, state, external_prime_checker=general_checker
                )
                print(
                    f"verified range {state.completed_ranges}/{state.parameters.range_count}",
                    file=sys.stderr,
                    flush=True,
                )
            _emit(_status(directory, general_checker), pretty=args.pretty)
            return 0

        if args.command == "verify":
            receipt = verify_complete_campaign(
                directory,
                binary_checker=_path(args.binary_checker),
                binary_artifact=_path(args.binary_artifact),
                binary_campaign=_path(args.binary_campaign),
                external_prime_checker=general_checker,
            )
            _emit(receipt, pretty=args.pretty)
            return 0
        raise AssertionError(args.command)
    except (
        CampaignError,
        binary_campaign.BinaryGoldbachError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
