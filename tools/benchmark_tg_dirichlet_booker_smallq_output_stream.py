#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark vectorized structural reduction of a synthetic TGDBSQO3 stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import struct
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier import dirichlet_booker_smallq_certified as v2  # noqa: E402
from tg_verifier.dirichlet_booker_smallq_factored import (  # noqa: E402
    BATCH_BINDING,
    BATCH_MAGIC,
    CHARACTER_HEADER,
    FORMAT_VERSION,
    INPUT_HEADER,
    PARAMETER_HEADER,
    PLAN_COMMITMENT,
    PLAN_MAGIC,
    SERVICE_OUTPUT_BINDING,
    SERVICE_OUTPUT_MAGIC,
    SHARED_FREQUENCY_SIZE,
    _character_roster_digest,
)
from tg_verifier.dirichlet_booker_smallq_output_stream import (  # noqa: E402
    reduce_factored_service_output_path,
    reduce_factored_service_output_stream,
)
from tg_verifier.dirichlet_booker_smallq_factored import source_work  # noqa: E402


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _power_of_two(value: str) -> int:
    parsed = _positive(value)
    if parsed & (parsed - 1):
        raise argparse.ArgumentTypeError("expected a power of two")
    return parsed


def _write_fixture(root: Path, *, length: int, character_count: int) -> tuple[Path, Path, Path]:
    q = max(5, character_count + 2)
    characters = tuple(range(1, character_count + 1))
    plan_path = root / "plan.bin"
    plan_header = b"".join(
        (
            INPUT_HEADER.pack(
                PLAN_MAGIC,
                FORMAT_VERSION,
                q,
                2,
                character_count,
                length,
                0,
                length,
                1,
                96,
                0,
            ),
            PLAN_COMMITMENT.pack(_character_roster_digest(characters)),
            PARAMETER_HEADER.pack(0, 1, 1, 1, length, 1),
        )
    )
    with plan_path.open("wb") as output:
        output.write(plan_header)
        zero = bytes(min(8 * 1024 * 1024, length * SHARED_FREQUENCY_SIZE))
        remaining = length * SHARED_FREQUENCY_SIZE
        while remaining:
            piece = zero[:remaining]
            output.write(piece)
            remaining -= len(piece)
    plan_sha = hashlib.sha256(plan_path.read_bytes()).digest()

    batch_path = root / "batch-00000000.bin"
    batch_chunks = [
        INPUT_HEADER.pack(
            BATCH_MAGIC,
            FORMAT_VERSION,
            q,
            2,
            character_count,
            length,
            0,
            length,
            1,
            96,
            0,
        ),
        BATCH_BINDING.pack(plan_sha, 0, character_count, 0, 1),
    ]
    for character_id in characters:
        batch_chunks.append(
            CHARACTER_HEADER.pack(character_id, character_id & 1, 0, 0, 1.0, 0.0, 0.0)
        )
        batch_chunks.append(struct.pack(f"<{q}I", *(0 for _ in range(q))))
    batch_raw = b"".join(batch_chunks)
    batch_path.write_bytes(batch_raw)
    batch_sha = hashlib.sha256(batch_raw).digest()

    stream_path = root / "stream.bin"
    butterflies = character_count * (length // 2) * (length.bit_length() - 1)
    with stream_path.open("wb") as output:
        output.write(
            v2.OUTPUT_HEADER.pack(
                SERVICE_OUTPUT_MAGIC,
                FORMAT_VERSION,
                q,
                character_count,
                1,
                0,
                length,
                0,
                butterflies,
                0,
                0,
                0,
            )
        )
        output.write(
            SERVICE_OUTPUT_BINDING.pack(
                plan_sha, batch_sha, 0, character_count, 0, 1
            )
        )
        buffer = bytearray()
        for character_id in characters:
            for index in range(length):
                buffer.extend(
                    v2.OUTPUT_ITEM.pack(
                        character_id, index, 1.0, -0.5, 0.125, 0, 0
                    )
                )
                if len(buffer) >= 8 * 1024 * 1024:
                    output.write(buffer)
                    buffer.clear()
        if buffer:
            output.write(buffer)
    return plan_path, batch_path, stream_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transform-length", type=_power_of_two, default=1 << 16)
    parser.add_argument("--characters", type=_positive, default=64)
    parser.add_argument("--repetitions", type=_positive, default=3)
    parser.add_argument("--chunk-items", type=_positive, default=1 << 16)
    parser.add_argument("--transport", choices=("file", "pipe"), default="pipe")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="tg-smallq-output-benchmark-") as temporary:
        root = Path(temporary)
        plan, batch, stream = _write_fixture(
            root,
            length=args.transform_length,
            character_count=args.characters,
        )
        reports = []
        for _ in range(args.repetitions):
            if args.transport == "file":
                reports.append(
                    reduce_factored_service_output_path(
                        plan,
                        [batch],
                        stream,
                        chunk_items=args.chunk_items,
                        backend="numpy",
                    )
                )
            else:
                read_fd, write_fd = os.pipe()
                producer_errors: list[BaseException] = []

                def produce() -> None:
                    try:
                        with stream.open("rb", buffering=0) as source, os.fdopen(
                            write_fd, "wb", buffering=0
                        ) as destination:
                            while block := source.read(8 * 1024 * 1024):
                                destination.write(block)
                    except BaseException as error:
                        producer_errors.append(error)

                producer = threading.Thread(target=produce, daemon=True)
                producer.start()
                with os.fdopen(read_fd, "rb", buffering=0) as source:
                    reports.append(
                        reduce_factored_service_output_stream(
                            plan,
                            [batch],
                            source,
                            chunk_items=args.chunk_items,
                            backend="numpy",
                        )
                    )
                producer.join()
                if producer_errors:
                    raise producer_errors[0]
    rates = [float(report["stream_megabytes_per_second"]) for report in reports]
    median_rate = statistics.median(rates)
    work = source_work()
    full_source_bytes = int(work["factored_v3_literal_service_output_bytes"])
    reduced_source_bytes = int(
        work["factored_v3_source_sample_only_service_output_bytes"]
    )
    result = {
        "algorithm_id": "platt-booker-smallq-output-stream-mmr-v1",
        "backend": "numpy",
        "classification": (
            "local-synthetic-anonymous-pipe-not-concurrent-cuda-h100-or-source-run"
            if args.transport == "pipe"
            else "cached-local-synthetic-file-not-h100-or-source-run"
        ),
        "fixture_bytes": int(reports[0]["raw_stream_bytes_consumed"]),
        "fixture_characters": args.characters,
        "fixture_transform_length": args.transform_length,
        "median_megabytes_per_second": median_rate,
        "projected_full_source_stream_hours_at_median_rate": (
            full_source_bytes / (median_rate * 1_000_000 * 3600)
        ),
        "projected_source_sample_only_stream_hours_at_median_rate": (
            reduced_source_bytes / (median_rate * 1_000_000 * 3600)
        ),
        "rates_megabytes_per_second": rates,
        "repetitions": args.repetitions,
        "transport": args.transport,
        "full_source_stream_bytes": full_source_bytes,
        "source_sample_only_stream_bytes": reduced_source_bytes,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
