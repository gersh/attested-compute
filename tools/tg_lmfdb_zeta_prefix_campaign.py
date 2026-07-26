#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the fixed 4,766-file LMFDB zeta-prefix audit campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)
from tg_verifier.lmfdb_zeta_prefix_campaign import (  # noqa: E402
    LMFDBZetaPrefixCampaignError,
    campaign_status,
    finalize_campaign,
    initialize_campaign,
    load_campaign,
    materialize_shard,
    replay_shard,
    run_shard,
    shard_file_range,
)


def nonnegative(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def positive(text: str) -> int:
    value = nonnegative(text)
    if value == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def emit(value: object, *, pretty: bool) -> None:
    print(json.dumps(value, sort_keys=True, indent=2 if pretty else None))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="snapshot the reviewed inventory and make the plan")
    init.add_argument("directory", type=Path)
    init.add_argument("--filelist", type=Path, required=True)
    init.add_argument("--md5-manifest", type=Path, required=True)
    init.add_argument(
        "--source-specification",
        type=Path,
        default=ROOT / "specifications" / "LMFDB_ZETA_PREFIX_UPSTREAM.json",
    )

    for name in ("materialize-shard", "audit-shard", "replay-shard"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        command.add_argument("index", type=nonnegative)
        command.add_argument("--data-directory", type=Path, required=True)
        if name == "materialize-shard":
            command.add_argument("--timeout-seconds", type=positive, default=120)

    for name in ("status", "finalize", "plan"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)

    shard_range = commands.add_parser("range", help="show one deterministic file shard")
    shard_range.add_argument("directory", type=Path)
    shard_range.add_argument("index", type=nonnegative)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "init":
            value = initialize_campaign(
                output_directory=arguments.directory,
                filelist=arguments.filelist,
                md5_manifest=arguments.md5_manifest,
                source_specification=arguments.source_specification,
            )
        elif arguments.command == "materialize-shard":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            value = materialize_shard(
                arguments.directory,
                arguments.data_directory,
                arguments.index,
                timeout_seconds=arguments.timeout_seconds,
            )
        elif arguments.command == "audit-shard":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            value = run_shard(
                arguments.directory, arguments.data_directory, arguments.index
            )
        elif arguments.command == "replay-shard":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            value = replay_shard(
                arguments.directory, arguments.data_directory, arguments.index
            )
        elif arguments.command == "status":
            value = campaign_status(arguments.directory)
        elif arguments.command == "finalize":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            value = finalize_campaign(arguments.directory)
        elif arguments.command == "plan":
            value, _inventory = load_campaign(arguments.directory)
        elif arguments.command == "range":
            plan, inventory = load_campaign(arguments.directory)
            lower, upper = shard_file_range(plan, arguments.index)
            value = {
                "accepted": True,
                "classification": "deterministic_lmfdb_prefix_file_shard",
                "plan_sha256": plan["plan_sha256"],
                "shard_index": arguments.index,
                "first_file_index": lower,
                "upper_file_index_exclusive": upper,
                "file_count": upper - lower,
                "filenames": list(inventory.prefix_filenames[lower:upper]),
                "source_claim_ready": False,
                "receipt_eligible_without_realization": False,
            }
        else:
            raise AssertionError("unreachable command")
    except (LMFDBZetaPrefixCampaignError, OSError, ValueError, KeyError, TypeError) as error:
        emit(
            {
                "accepted": False,
                "classification": "lmfdb_zeta_prefix_campaign_failed_closed",
                "error": str(error),
                "source_claim_ready": False,
                "receipt_eligible_without_realization": False,
                "lean_atom_discharged": False,
            },
            pretty=arguments.pretty,
        )
        return 2
    emit(value, pretty=arguments.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
