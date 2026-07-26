#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate, or finalize, one authenticated PT21 worker block-input stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_block_input_stream import (  # noqa: E402
    PT21BlockInputStreamError,
    stream_shard_archive,
    validate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    checker = commands.add_parser(
        "validate",
        help="independently replay every frame, digest, and nested payload",
    )
    checker.add_argument("stream", type=Path)
    checker.add_argument("--expected-stream-sha256")
    checker.add_argument("--expected-first-block", type=int)
    checker.add_argument("--expected-block-count", type=int)
    checker.add_argument("--expected-gamma-stream-sha256")
    checker.add_argument("--expected-producer-sha256")
    checker.add_argument("--expected-resolver-sha256")
    checker.add_argument("--expected-flint-sha256")
    checker.add_argument("--pretty", action="store_true")

    shard = commands.add_parser(
        "shard-archive",
        help=(
            "stream frames through the exact record adapter into the pinned "
            "native shard finalizer without a manifest or retained inputs"
        ),
    )
    shard.add_argument("stream", type=Path)
    shard.add_argument("--expected-stream-sha256", required=True)
    shard.add_argument("--worker", type=Path, required=True)
    shard.add_argument("--finalizer", type=Path, required=True)
    shard.add_argument("--expected-finalizer-sha256", required=True)
    shard.add_argument("--output", type=Path, required=True)
    shard.add_argument("--first-block", type=int, required=True)
    shard.add_argument("--block-count", type=int, required=True)
    shard.add_argument("--plan-sha256", required=True)
    shard.add_argument("--prefix-evidence-sha256", required=True)
    shard.add_argument("--bounded-test", action="store_true")
    shard.add_argument("--pretty", action="store_true")

    arguments = parser.parse_args()
    try:
        if arguments.command == "validate":
            result = validate(
                arguments.stream,
                expected_stream_sha256=arguments.expected_stream_sha256,
                expected_first_block=arguments.expected_first_block,
                expected_block_count=arguments.expected_block_count,
                expected_gamma_stream_sha256=(
                    arguments.expected_gamma_stream_sha256
                ),
                expected_producer_sha256=arguments.expected_producer_sha256,
                expected_resolver_sha256=arguments.expected_resolver_sha256,
                expected_flint_sha256=arguments.expected_flint_sha256,
            )
        else:
            result = stream_shard_archive(
                arguments.stream,
                expected_stream_sha256=arguments.expected_stream_sha256,
                worker=arguments.worker,
                finalizer=arguments.finalizer,
                expected_finalizer_sha256=(
                    arguments.expected_finalizer_sha256
                ),
                output=arguments.output,
                first_block=arguments.first_block,
                block_count=arguments.block_count,
                plan_sha256=arguments.plan_sha256,
                prefix_evidence_sha256=arguments.prefix_evidence_sha256,
                bounded_test=arguments.bounded_test,
            )
    except (OSError, ValueError, PT21BlockInputStreamError) as error:
        print(f"tg_platt_pt21_block_input_stream: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            sort_keys=True,
            indent=2 if arguments.pretty else None,
            separators=None if arguments.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
