#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark canonical vector TGDBSZR1 event encoding on a local file."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
except ImportError:  # pragma: no cover - the CLI reports the missing dependency
    np = None

from tg_verifier import dirichlet_booker_smallq_semantic_reducer as semantic  # noqa: E402
from tg_verifier.dirichlet_booker_smallq_sign_scan import (  # noqa: E402
    EVENT_RECORD,
    _BufferedEventWriter,
    _CharacterScan,
    _emit_ambiguity,
    _scan_numpy_chunk,
)


SOURCE_SMALL_Q_CODES = 4_729_082_453_090


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _probability(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(
            "expected a finite probability in [0,1]"
        )
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "output",
        type=Path,
        help="local/NVMe event-payload file to create",
    )
    result.add_argument("--codes", type=_positive, default=50_000_000)
    result.add_argument("--chunk-codes", type=_positive, default=1 << 20)
    result.add_argument(
        "--transition-probability",
        type=_probability,
        default=0.1937562681649638,
        help="Markov flip probability before sparse ambiguities",
    )
    result.add_argument(
        "--ambiguity-probability",
        type=_probability,
        default=0.0,
    )
    result.add_argument("--seed", type=int, default=0x54474442535A5231)
    result.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output file",
    )
    result.add_argument(
        "--remove-output",
        action="store_true",
        help="remove the measured file after hashing it",
    )
    result.add_argument("--pretty", action="store_true")
    return result


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while raw := source.read(8 * 1024 * 1024):
            digest.update(raw)
            size += len(raw)
    return digest.hexdigest(), size


def benchmark(
    output: Path,
    *,
    codes: int,
    chunk_codes: int,
    transition_probability: float,
    ambiguity_probability: float,
    seed: int,
    overwrite: bool,
    remove_output: bool,
) -> dict[str, object]:
    if np is None:
        raise RuntimeError("NumPy is required for the vector benchmark")
    if (
        isinstance(codes, bool)
        or not isinstance(codes, int)
        or not 0 < codes <= (1 << 64) - 1
        or isinstance(chunk_codes, bool)
        or not isinstance(chunk_codes, int)
        or chunk_codes <= 0
    ):
        raise RuntimeError("codes/chunk-codes are outside the supported range")
    if (
        not math.isfinite(transition_probability)
        or not 0.0 <= transition_probability <= 1.0
        or not math.isfinite(ambiguity_probability)
        or not 0.0 <= ambiguity_probability <= 1.0
        or isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
    ):
        raise RuntimeError("benchmark probabilities or seed are invalid")
    if output.exists() and not overwrite:
        raise RuntimeError("output exists; pass --overwrite to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)

    template_count = min(codes, chunk_codes)
    template_started = time.perf_counter_ns()
    generator = np.random.default_rng(seed)
    flips = generator.random(template_count) < transition_probability
    flips[0] = False
    template = (
        semantic.NEGATIVE_CODE
        + np.bitwise_xor.accumulate(flips.astype(np.uint8))
    ).astype(np.uint8, copy=False)
    if ambiguity_probability:
        ambiguous = generator.random(template_count) < ambiguity_probability
        template[ambiguous] = semantic.AMBIGUOUS_CODE
    template_elapsed = time.perf_counter_ns() - template_started

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=output.parent
    )
    state = _CharacterScan()
    encode_started = time.perf_counter_ns()
    try:
        with os.fdopen(descriptor, "wb") as sink:
            writer = _BufferedEventWriter(sink)
            sample_start = 0
            while sample_start < codes:
                count = min(template_count, codes - sample_start)
                _scan_numpy_chunk(
                    state,
                    template[:count],
                    sample_start=sample_start,
                    emit=writer.emit,
                    emit_packed=writer.emit_packed,
                )
                sample_start += count
            if state.ambiguous_start is not None:
                _emit_ambiguity(
                    state,
                    writer.emit,
                    state.ambiguous_start,
                    codes - 1,
                )
                state.ambiguous_start = None
            writer.flush()
            sink.flush()
            os.fsync(sink.fileno())
        os.replace(temporary_name, output)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    encode_elapsed = time.perf_counter_ns() - encode_started

    hash_started = time.perf_counter_ns()
    digest, size = _sha256_file(output)
    hash_elapsed = time.perf_counter_ns() - hash_started
    expected_size = state.event_count * EVENT_RECORD.size
    if (
        state.ambiguous_samples
        + state.negative_samples
        + state.positive_samples
        != codes
        or size != expected_size
    ):
        raise RuntimeError("benchmark event coverage or byte count differs")

    encode_seconds = encode_elapsed / 1_000_000_000
    hash_seconds = hash_elapsed / 1_000_000_000
    event_density = state.event_count / codes
    projected_events = SOURCE_SMALL_Q_CODES * event_density
    result: dict[str, object] = {
        "kind": (
            "sparkinterval.tg.dirichlet_booker_smallq."
            "vector_event_encoder_benchmark.v1"
        ),
        "classification": (
            "synthetic_local_file_sensitivity_not_source_run_or_azure_eta"
        ),
        "backend": "numpy-structured-vector",
        "machine": platform.machine(),
        "platform": platform.platform(),
        "codes": codes,
        "chunk_codes": chunk_codes,
        "template_codes": template_count,
        "transition_probability": transition_probability,
        "ambiguity_probability": ambiguity_probability,
        "seed": seed,
        "template_generation_seconds": (
            template_elapsed / 1_000_000_000
        ),
        "ambiguous_samples": state.ambiguous_samples,
        "negative_samples": state.negative_samples,
        "positive_samples": state.positive_samples,
        "ambiguity_ranges": state.ambiguity_ranges,
        "opposite_sign_intervals": state.opposite_intervals,
        "event_count": state.event_count,
        "event_density": event_density,
        "event_record_bytes": EVENT_RECORD.size,
        "output_path": str(output.resolve()),
        "output_size_bytes": size,
        "output_sha256": digest,
        "encode_write_fsync_seconds": encode_seconds,
        "hash_read_seconds": hash_seconds,
        "encode_codes_per_second": codes / encode_seconds,
        "encode_events_per_second": state.event_count / encode_seconds,
        "encode_output_bytes_per_second": size / encode_seconds,
        "hash_read_bytes_per_second": size / hash_seconds,
        "source_small_q_codes": SOURCE_SMALL_Q_CODES,
        "linear_source_projected_events": projected_events,
        "linear_source_projected_event_bytes": (
            projected_events * EVENT_RECORD.size
        ),
        "linear_source_single_encode_hours": (
            SOURCE_SMALL_Q_CODES / (codes / encode_seconds) / 3600
        ),
        "linear_source_encode_plus_replay_cpu_hours": (
            2 * SOURCE_SMALL_Q_CODES / (codes / encode_seconds) / 3600
        ),
        "projection_is_not_parallel_io_or_cloud_calibration": True,
        "output_removed_after_measurement": remove_output,
    }
    if remove_output:
        output.unlink()
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        value = benchmark(
            args.output,
            codes=args.codes,
            chunk_codes=args.chunk_codes,
            transition_probability=args.transition_probability,
            ambiguity_probability=args.ambiguity_probability,
            seed=args.seed,
            overwrite=args.overwrite,
            remove_output=args.remove_output,
        )
    except (OSError, RuntimeError) as error:
        print(
            f"benchmark_tg_dirichlet_booker_smallq_sign_scan: {error}",
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            value,
            indent=2 if args.pretty else None,
            sort_keys=True,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
