#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the bounded TGDCSB03 q=10001 vertical slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_compact_state_streaming_v3 import (  # noqa: E402
    replay_compact_state_v3,
    write_flat_sign_codes_v3,
)
from tg_verifier.dirichlet_root_number_stage import (  # noqa: E402
    primitive_frequency_records_bulk,
)


def _chunks(
    character_count: int,
    sample_count: int,
    *,
    chunk_codes: int,
    ambiguity_period: int,
):
    chunk = bytearray()
    for ordinal in range(character_count):
        for sample in range(sample_count):
            code = 1 if (sample // 17 + ordinal) % 2 == 0 else 2
            if (
                ambiguity_period
                and ordinal % ambiguity_period == 0
                and sample in {sample_count // 2, sample_count // 2 + 1}
            ):
                code = 0
            chunk.append(code)
            if len(chunk) == chunk_codes:
                yield bytes(chunk)
                chunk.clear()
    if chunk:
        yield bytes(chunk)


def benchmark(
    *,
    sample_count: int = 64,
    chunk_codes: int = 1 << 18,
    ambiguity_period: int = 997,
) -> dict[str, object]:
    q = 10_001
    character_count = len(primitive_frequency_records_bulk(q))
    total_codes = character_count * sample_count
    with tempfile.TemporaryDirectory(
        prefix="tg-dirichlet-v3-q10001-"
    ) as temporary:
        path = Path(temporary) / "state-v3.bin"
        started = time.perf_counter()
        record = write_flat_sign_codes_v3(
            path,
            q=q,
            frame_count=1,
            first_t_numerator=0,
            stop_t_numerator=5 * sample_count,
            code_chunks=_chunks(
                character_count,
                sample_count,
                chunk_codes=chunk_codes,
                ambiguity_period=ambiguity_period,
            ),
            source_binding_sha256="b" * 64,
        )
        write_seconds = time.perf_counter() - started
        started = time.perf_counter()
        replay = replay_compact_state_v3(path, expected_record=record)
        replay_seconds = time.perf_counter() - started
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_compact_state_v3.benchmark.v1"
        ),
        "classification": (
            "q10001_synthetic_codec_benchmark_not_source_or_analytic_evidence"
        ),
        "q": q,
        "primitive_character_count": character_count,
        "sample_count_per_character": sample_count,
        "sign_code_count": total_codes,
        "ambiguity_period_characters": ambiguity_period,
        "artifact_bytes": record["size_bytes"],
        "transition_count": record["transition_count"],
        "ambiguity_sample_count": record["ambiguity_sample_count"],
        "ambiguity_range_count": record["ambiguity_range_count"],
        "write_seconds": write_seconds,
        "replay_seconds": replay_seconds,
        "write_sign_codes_per_second": total_codes / write_seconds,
        "replay_sign_codes_per_second": total_codes / replay_seconds,
        "maximum_rss_kib": resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss,
        "fresh_replay_matched": replay == record,
        "source_scale_projection_permitted": False,
        "ambiguity_density_measured": False,
        "producer_fused_with_arithmetic": False,
        "turing_completeness": False,
        "external_atom_discharged": False,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--sample-count", type=int, default=64)
    result.add_argument("--chunk-codes", type=int, default=1 << 18)
    result.add_argument("--ambiguity-period", type=int, default=997)
    result.add_argument("--pretty", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.sample_count <= 0 or args.chunk_codes <= 0:
        parser().error("sample-count and chunk-codes must be positive")
    result = benchmark(
        sample_count=args.sample_count,
        chunk_codes=args.chunk_codes,
        ambiguity_period=args.ambiguity_period,
    )
    print(
        json.dumps(
            result,
            indent=2 if args.pretty else None,
            sort_keys=True,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
