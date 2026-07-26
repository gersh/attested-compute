#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build canonical PT21BLK1 records from validated finite worker outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_native_record_adapter import (  # noqa: E402
    PT21NativeRecordAdapterError,
    adapt_block,
    adapt_manifest,
    adapt_manifest_to_native_shard,
    block_report,
    write_exclusive,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)

    block = commands.add_parser("block")
    block.add_argument("--required-sign-packet", type=Path, required=True)
    block.add_argument("--stationary-trace", type=Path, required=True)
    block.add_argument("--turing-inputs", type=Path, required=True)
    block.add_argument("--worker", type=Path, required=True)
    block.add_argument("--output", type=Path, required=True)

    shard = commands.add_parser("shard")
    shard.add_argument("--manifest", type=Path, required=True)
    shard.add_argument("--worker", type=Path, required=True)
    shard.add_argument("--output", type=Path, required=True)
    shard.add_argument("--first-block", type=int, required=True)
    shard.add_argument("--block-count", type=int, required=True)

    archive = commands.add_parser(
        "shard-archive",
        help=(
            "stream adapted PT21BLK1 records directly into the pinned native "
            "shard finalizer"
        ),
    )
    archive.add_argument("--manifest", type=Path, required=True)
    archive.add_argument("--expected-manifest-sha256", required=True)
    archive.add_argument("--worker", type=Path, required=True)
    archive.add_argument("--finalizer", type=Path, required=True)
    archive.add_argument("--expected-finalizer-sha256", required=True)
    archive.add_argument("--output", type=Path, required=True)
    archive.add_argument("--first-block", type=int, required=True)
    archive.add_argument("--block-count", type=int, required=True)
    archive.add_argument("--plan-sha256", required=True)
    archive.add_argument("--prefix-evidence-sha256", required=True)
    archive.add_argument("--bounded-test", action="store_true")
    archive.add_argument(
        "--finalizer-exit-timeout-seconds", type=int, default=300
    )
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "block":
            adapted = adapt_block(
                required_sign_packet=arguments.required_sign_packet,
                stationary_trace=arguments.stationary_trace,
                turing_inputs=arguments.turing_inputs,
                worker=arguments.worker,
            )
            write_exclusive(arguments.output, adapted.record)
            report = block_report(adapted)
        elif arguments.command == "shard":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(arguments.block_count,),
            )
            report = adapt_manifest(
                arguments.manifest,
                output=arguments.output,
                worker=arguments.worker,
                first_block=arguments.first_block,
                block_count=arguments.block_count,
            )
        else:
            require_azure_measured_worker_for_workload(
                exact_production=not arguments.bounded_test,
                work_bounds=(arguments.block_count,),
            )
            report = adapt_manifest_to_native_shard(
                arguments.manifest,
                worker=arguments.worker,
                finalizer=arguments.finalizer,
                expected_finalizer_sha256=(
                    arguments.expected_finalizer_sha256
                ),
                expected_manifest_sha256=(
                    arguments.expected_manifest_sha256
                ),
                output=arguments.output,
                first_block=arguments.first_block,
                block_count=arguments.block_count,
                plan_sha256=arguments.plan_sha256,
                prefix_evidence_sha256=(
                    arguments.prefix_evidence_sha256
                ),
                bounded_test=arguments.bounded_test,
                finalizer_exit_timeout_seconds=(
                    arguments.finalizer_exit_timeout_seconds
                ),
            )
    except (
        OSError,
        ValueError,
        PT21NativeRecordAdapterError,
    ) as error:
        print(f"tg_platt_pt21_native_record_adapter: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            report,
            sort_keys=True,
            indent=2 if arguments.pretty else None,
            separators=None if arguments.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
