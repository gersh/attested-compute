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
    benchmark_source_height,
    canonical_json_bytes,
    combine_with_hardened_binary_goldbach,
    combine_with_optimized_binary_goldbach,
    emit_independent_receipt,
    initialize_campaign,
    load_campaign,
    produce_independent_group,
    produce_independent_range,
    produce_next_range,
    reduce_independent_campaign,
    replay_campaign,
    verify_complete_campaign,
)
from tg_verifier import binary_goldbach_campaign as binary_campaign  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


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


def _guard_parameters(parameters: CampaignParameters) -> None:
    require_azure_measured_worker_for_workload(
        exact_production=parameters.mode != "bounded_test",
        work_bounds=(
            parameters.range_width,
            parameters.range_count,
            parameters.endpoint,
            parameters.binary_last_even // 2,
        ),
    )


def _guard_status_replay(
    directory: Path, parameters: CampaignParameters
) -> None:
    """An empty production status is metadata; a retained range is replay."""

    if any((directory / "ranges").glob("range-*")):
        _guard_parameters(parameters)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="print the immutable source schedule")
    plan.set_defaults(command_name="plan")

    benchmark = subparsers.add_parser(
        "benchmark-source-height",
        help="time a bounded noncertificate producer/replay sample near T",
    )
    benchmark.add_argument("--steps", type=int, default=5_000)

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

    produce_range = subparsers.add_parser(
        "produce-range",
        help="produce one formulaically fixed range without reading any predecessor",
    )
    produce_range.add_argument("directory", type=Path)
    produce_range.add_argument("index", type=int)
    produce_range.add_argument("--general-prime-producer")
    produce_range.add_argument("--general-prime-checker")
    produce_range.add_argument(
        "--no-builtin-pocklington",
        action="store_false",
        dest="builtin_pocklington",
        help="disable the exact built-in fallback and require the external producer",
    )

    produce_group = subparsers.add_parser(
        "produce-group",
        help="run one deterministic scheduler group with bounded local workers",
    )
    produce_group.add_argument("directory", type=Path)
    produce_group.add_argument("--group-index", type=int, required=True)
    produce_group.add_argument("--group-count", type=int, required=True)
    produce_group.add_argument("--local-workers", type=int, default=1)
    produce_group.add_argument("--general-prime-producer")
    produce_group.add_argument("--general-prime-checker")
    produce_group.add_argument("--summary", type=Path)
    produce_group.add_argument(
        "--no-builtin-pocklington",
        action="store_false",
        dest="builtin_pocklington",
    )

    check_range = subparsers.add_parser(
        "check-range", help="independently replay one range and retain its receipt"
    )
    check_range.add_argument("directory", type=Path)
    check_range.add_argument("index", type=int)
    check_range.add_argument("--general-prime-checker")

    reduce_ranges = subparsers.add_parser(
        "reduce-ranges",
        help="replay all fixed ranges, check ordered coverage, and commit a Merkle root",
    )
    reduce_ranges.add_argument("directory", type=Path)
    reduce_ranges.add_argument("--out", type=Path, required=True)
    reduce_ranges.add_argument("--general-prime-checker")

    combine_gpu = subparsers.add_parser(
        "combine-gpu",
        help="replay hardened binary Goldbach, then the independent ladder aggregate",
    )
    combine_gpu.add_argument("directory", type=Path)
    combine_gpu.add_argument("--ladder-aggregate", type=Path, required=True)
    combine_gpu.add_argument("--binary-plan", type=Path, required=True)
    combine_gpu.add_argument("--binary-receipts-dir", type=Path, required=True)
    combine_gpu.add_argument("--binary-aggregate", type=Path, required=True)
    combine_gpu.add_argument("--general-prime-checker")
    combine_gpu.add_argument("--out", type=Path, required=True)

    combine_optimized_gpu = subparsers.add_parser(
        "combine-optimized-gpu",
        help=(
            "replay the exact optimized binary Goldbach route and independent "
            "ladder into an unregistered, domain-separated result"
        ),
    )
    combine_optimized_gpu.add_argument("directory", type=Path)
    combine_optimized_gpu.add_argument(
        "--ladder-aggregate", type=Path, required=True
    )
    combine_optimized_gpu.add_argument(
        "--binary-plan", type=Path, required=True
    )
    combine_optimized_gpu.add_argument(
        "--binary-receipts-dir", type=Path, required=True
    )
    combine_optimized_gpu.add_argument(
        "--binary-aggregate", type=Path, required=True
    )
    combine_optimized_gpu.add_argument("--general-prime-checker")
    combine_optimized_gpu.add_argument("--out", type=Path, required=True)
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
                    "parallel_worker": (
                        "produce-range DIRECTORY RANGE_INDEX; every index from "
                        "0 through 492699 is independent"
                    ),
                    "scheduler_group_worker": (
                        "produce-group DIRECTORY --group-index G --group-count N "
                        "--local-workers W; use N=320..3200 when MaxArraySize is small"
                    ),
                    "parallel_reducer": "reduce-ranges DIRECTORY --out AGGREGATE.json",
                    "verification_note": (
                        "The ladder and the binary-Goldbach prerequisite are "
                        "independent computations; both must replay."
                    ),
                },
                pretty=args.pretty,
            )
            return 0

        if args.command == "benchmark-source-height":
            if args.steps < 1:
                raise CampaignError("--steps must be positive")
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(args.steps,),
            )
            _emit(benchmark_source_height(args.steps), pretty=args.pretty)
            return 0

        if args.command == "full":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
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
            _guard_status_replay(directory, load_campaign(directory))
            _emit(_status(directory, None), pretty=args.pretty)
            return 0

        parameters = load_campaign(directory)

        if args.command == "produce-range":
            _guard_parameters(parameters)
            receipt = produce_independent_range(
                directory,
                args.index,
                general_prime_producer=_path(args.general_prime_producer),
                external_prime_checker=_path(args.general_prime_checker),
                builtin_pocklington=args.builtin_pocklington,
            )
            _emit(receipt, pretty=args.pretty)
            return 0

        if args.command == "produce-group":
            _guard_parameters(parameters)
            summary = produce_independent_group(
                directory,
                group_index=args.group_index,
                group_count=args.group_count,
                local_workers=args.local_workers,
                general_prime_producer=_path(args.general_prime_producer),
                external_prime_checker=_path(args.general_prime_checker),
                builtin_pocklington=args.builtin_pocklington,
                summary_path=(
                    None if args.summary is None else args.summary.resolve()
                ),
            )
            _emit(summary, pretty=args.pretty)
            return 0

        if args.command == "check-range":
            _guard_parameters(parameters)
            receipt = emit_independent_receipt(
                directory,
                args.index,
                external_prime_checker=_path(args.general_prime_checker),
            )
            _emit(receipt, pretty=args.pretty)
            return 0

        if args.command == "reduce-ranges":
            _guard_parameters(parameters)
            aggregate = reduce_independent_campaign(
                directory,
                aggregate_path=args.out.resolve(),
                external_prime_checker=_path(args.general_prime_checker),
            )
            _emit(aggregate, pretty=args.pretty)
            return 0

        if args.command == "combine-gpu":
            _guard_parameters(parameters)
            combined = combine_with_hardened_binary_goldbach(
                directory,
                ladder_aggregate_path=args.ladder_aggregate.resolve(),
                binary_plan_path=args.binary_plan.resolve(),
                binary_receipts_directory=args.binary_receipts_dir.resolve(),
                binary_aggregate_path=args.binary_aggregate.resolve(),
                output_path=args.out.resolve(),
                external_prime_checker=_path(args.general_prime_checker),
            )
            _emit(combined, pretty=args.pretty)
            return 0

        if args.command == "combine-optimized-gpu":
            _guard_parameters(parameters)
            combined = combine_with_optimized_binary_goldbach(
                directory,
                ladder_aggregate_path=args.ladder_aggregate.resolve(),
                binary_plan_path=args.binary_plan.resolve(),
                binary_receipts_directory=args.binary_receipts_dir.resolve(),
                binary_aggregate_path=args.binary_aggregate.resolve(),
                output_path=args.out.resolve(),
                external_prime_checker=_path(args.general_prime_checker),
            )
            _emit(combined, pretty=args.pretty)
            return 0

        general_checker = _path(args.general_prime_checker)
        if args.command == "status":
            _guard_status_replay(directory, parameters)
            _emit(_status(directory, general_checker), pretty=args.pretty)
            return 0

        if args.command == "run":
            _guard_parameters(parameters)
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
            _guard_parameters(parameters)
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
        CampaignIOError,
        binary_campaign.BinaryGoldbachError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
