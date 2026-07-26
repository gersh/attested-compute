#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operator CLI for independent replay of native PT21 retained exports."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_native_finalizer import (  # noqa: E402
    CampaignReplay,
    LOCAL_KAT_MAX_BLOCK_RECORDS,
    PT21NativeFinalizerError,
    ShardReplay,
    replay_campaign,
    replay_shard,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


MAXIMUM_SHARD_LIST_BYTES = 16 * 1024 * 1024


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value: bytes) -> str:
    return value.hex()


def shard_json(value: ShardReplay) -> dict[str, object]:
    return {
        "archive_sha256": digest(value.archive_sha256),
        "archive_size_bytes": value.archive_size_bytes,
        "block_artifact_merkle_root_sha256": digest(
            value.block_merkle_root_sha256
        ),
        "block_count": value.block_count,
        "first_block": value.first_block,
        "first_count": value.first_count,
        "last_count": value.last_count,
        "mode": "production" if value.mode == 1 else "bounded_test",
        "record_stream_sha256": digest(value.record_stream_sha256),
        "replayed_every_retained_record": True,
        "schema": "sparkinterval.tg.platt-pt21-native-shard-replay.v1",
        "source_claim_ready": False,
        "source_height_count": value.source_height_count,
        "total_main_slots": value.total_main_slots,
        "total_sparse_refinements": value.total_sparse_refinements,
        "total_stationary_resolutions": value.total_stationary_resolutions,
        "upper_block_exclusive": value.upper_block_exclusive,
    }


def campaign_json(value: CampaignReplay) -> dict[str, object]:
    return {
        "archive_sha256": digest(value.archive_sha256),
        "archive_size_bytes": value.archive_size_bytes,
        "block_count": value.block_count,
        "first_block": value.first_block,
        "first_count": value.first_count,
        "last_count": value.last_count,
        "mode": "production" if value.mode == 1 else "bounded_test",
        "replayed_every_retained_record": True,
        "replayed_every_shard_archive": True,
        "schema": "sparkinterval.tg.platt-pt21-native-campaign-replay.v1",
        "shard_count": value.shard_count,
        "shard_receipt_merkle_root_sha256": digest(
            value.shard_merkle_root_sha256
        ),
        "source_claim_ready": False,
        "source_height_count": value.source_height_count,
        "summary_stream_sha256": digest(value.summary_stream_sha256),
        "total_main_slots": value.total_main_slots,
        "total_sparse_refinements": value.total_sparse_refinements,
        "total_stationary_resolutions": value.total_stationary_resolutions,
        "upper_block_exclusive": value.upper_block_exclusive,
    }


def shard_roster(path: Path) -> list[Path]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 1
            or metadata.st_size > MAXIMUM_SHARD_LIST_BYTES
        ):
            raise PT21NativeFinalizerError(
                "shard list has an invalid byte length or file type"
            )
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise PT21NativeFinalizerError("shard list is truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except OSError as error:
        raise PT21NativeFinalizerError(
            f"cannot open shard list without following links: {error}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not raw.endswith(b"\n") or b"\0" in raw or b"\r" in raw:
        raise PT21NativeFinalizerError("shard list framing differs")
    rows = raw[:-1].split(b"\n")
    if not rows or any(not row for row in rows):
        raise PT21NativeFinalizerError("shard list contains an empty row")
    try:
        result = [Path(row.decode("utf-8")) for row in rows]
    except UnicodeDecodeError as error:
        raise PT21NativeFinalizerError("shard list is not UTF-8") from error
    if len({str(item) for item in result}) != len(result):
        raise PT21NativeFinalizerError("shard list repeats a path")
    return result


def add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-worker-sha256")
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--expected-prefix-evidence-sha256")
    parser.add_argument("--allow-bounded-test", action="store_true")
    parser.add_argument(
        "--max-kat-records",
        type=int,
        default=LOCAL_KAT_MAX_BLOCK_RECORDS,
        help=(
            "maximum total retained records for an explicitly bounded local "
            "KAT; values above 64 require the measured Azure worker"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    shard = commands.add_parser("replay-shard")
    shard.add_argument("archive", type=Path)
    add_identity_arguments(shard)
    campaign = commands.add_parser("replay-campaign")
    campaign.add_argument("archive", type=Path)
    campaign.add_argument("--shard-list", type=Path, required=True)
    add_identity_arguments(campaign)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    require_azure_measured_worker_for_workload(
        exact_production=not arguments.allow_bounded_test,
        work_bounds=(arguments.max_kat_records,),
    )
    common = {
        "expected_plan_sha256": arguments.expected_plan_sha256,
        "expected_worker_sha256": arguments.expected_worker_sha256,
        "expected_prefix_sha256": arguments.expected_prefix_evidence_sha256,
        "allow_bounded_test": arguments.allow_bounded_test,
        "maximum_bounded_records": arguments.max_kat_records,
        "require_bounded_test_mode": arguments.allow_bounded_test,
    }
    if arguments.command == "replay-shard":
        result = shard_json(replay_shard(arguments.archive, **common))
    else:
        result = campaign_json(
            replay_campaign(
                arguments.archive,
                shard_roster(arguments.shard_list),
                **common,
            )
        )
    sys.stdout.write(canonical(result) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, PT21NativeFinalizerError, ValueError) as error:
        sys.stderr.write(f"tg_platt_pt21_native_finalizer: {error}\n")
        raise SystemExit(2)
