#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or replay the deterministic binary-Goldbach prerequisite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.binary_goldbach_campaign import (  # noqa: E402
    BinaryGoldbachError,
    DEFAULT_SOURCE_EVENS_PER_CHUNK,
    Parameters,
    ZERO_HASH,
    initialize,
    load,
    produce_next,
    replay,
    verify_complete,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def status(directory: Path) -> dict[str, object]:
    state = replay(directory)
    return {
        "checked_evens": str(state.checked_evens),
        "chunk_count": state.parameters.chunk_count,
        "completed_chunks": state.completed_chunks,
        "full_source": state.parameters.mode == "full_source",
        "last_chunk_sha256": state.previous_sha256,
        "source_complete": state.completed_chunks == state.parameters.chunk_count,
    }


def empty_status(parameters: Parameters) -> dict[str, object]:
    return {
        "checked_evens": "0",
        "chunk_count": parameters.chunk_count,
        "completed_chunks": 0,
        "full_source": parameters.mode == "full_source",
        "last_chunk_sha256": ZERO_HASH,
        "source_complete": False,
    }


def has_retained_chunks(directory: Path) -> bool:
    return any((directory / "chunks").glob("chunk-*.json"))


def guard_finite_work(parameters: Parameters) -> None:
    require_azure_measured_worker_for_workload(
        exact_production=parameters.mode == "full_source",
        work_bounds=(
            parameters.even_count,
            min(parameters.evens_per_chunk, parameters.even_count),
            parameters.chunk_count,
        ),
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument(
        "--evens-per-chunk", type=int, default=DEFAULT_SOURCE_EVENS_PER_CHUNK
    )
    show = commands.add_parser("status")
    show.add_argument("directory", type=Path)
    run = commands.add_parser("run")
    run.add_argument("directory", type=Path)
    run.add_argument("--max-new-chunks", type=int, default=0)
    verify = commands.add_parser("verify")
    verify.add_argument("directory", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        directory = args.directory.resolve()
        if args.command == "init":
            initialize(directory, Parameters(evens_per_chunk=args.evens_per_chunk))
            parameters = load(directory)
            if has_retained_chunks(directory):
                guard_finite_work(parameters)
                emit(status(directory))
            else:
                emit(empty_status(parameters))
        elif args.command == "status":
            parameters = load(directory)
            if has_retained_chunks(directory):
                guard_finite_work(parameters)
                emit(status(directory))
            else:
                emit(empty_status(parameters))
        elif args.command == "run":
            if args.max_new_chunks < 0:
                raise BinaryGoldbachError("--max-new-chunks must be nonnegative")
            parameters = load(directory)
            guard_finite_work(parameters)
            state = replay(directory)
            stop = state.parameters.chunk_count
            if args.max_new_chunks:
                stop = min(stop, state.completed_chunks + args.max_new_chunks)
            while state.completed_chunks < stop:
                state = produce_next(directory, state)
                print(
                    f"verified chunk {state.completed_chunks}/{state.parameters.chunk_count}",
                    file=sys.stderr,
                    flush=True,
                )
            emit(status(directory))
        elif args.command == "verify":
            guard_finite_work(load(directory))
            emit(verify_complete(directory))
        return 0
    except (BinaryGoldbachError, CampaignIOError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
