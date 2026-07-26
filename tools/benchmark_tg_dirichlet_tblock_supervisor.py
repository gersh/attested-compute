#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark constant-size source accounting and optional 64-MiB protocol I/O."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_cache import (  # noqa: E402
    ROW_PAYLOAD_BYTES,
    build_cache_catalog,
    cache_shard_filename,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    SOURCE_Q_START,
    SOURCE_Q_STOP,
)
from tg_verifier.dirichlet_source_supervisor import (  # noqa: E402
    PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED,
    PINNED_SOURCE_LANE_TOTALS,
    build_structural_kat_contract,
)
from tg_verifier.dirichlet_tblock_supervisor import (  # noqa: E402
    _RosterIndex,
    run_supervisor,
)
from tg_verifier.dirichlet_tmajor_spool import (  # noqa: E402
    PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES,
    build_lane_spool,
)


def _io_rows(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 64:
        raise argparse.ArgumentTypeError("must be in 0..64")
    return value


def _formula_benchmark(repetitions: int) -> dict[str, object]:
    samples = []
    last_lanes: list[tuple[int, int]] = []
    for _ in range(repetitions):
        start = time.perf_counter()
        index = _RosterIndex.build(SOURCE_Q_START, SOURCE_Q_STOP)
        indexed = time.perf_counter()
        last_lanes = [
            index.lane_counts(lane[1], lane[2])
            for lane in PINNED_SOURCE_LANE_TOTALS
        ]
        finished = time.perf_counter()
        samples.append(
            {
                "q_index_seconds": indexed - start,
                "eight_lane_accounting_seconds": finished - indexed,
            }
        )
    target_counts = tuple(value[0] for value in last_lanes)
    row_counts = tuple(value[1] for value in last_lanes)
    if (
        target_counts
        != PINNED_SOURCE_LANE_Q_CONTIGUOUS_FFT_BATCHES_IF_TRANSPOSED
        or row_counts != PINNED_SOURCE_LANE_Q_T_ROW_REFERENCES
    ):
        raise RuntimeError("formula accounting differs from pinned source totals")
    return {
        "q_range": [SOURCE_Q_START, SOURCE_Q_STOP],
        "repetitions": repetitions,
        "samples": samples,
        "minimum_q_index_seconds": min(
            item["q_index_seconds"] for item in samples
        ),
        "minimum_eight_lane_accounting_seconds": min(
            item["eight_lane_accounting_seconds"] for item in samples
        ),
        "fixed_q_target_count": sum(target_counts),
        "target_row_reference_count": sum(row_counts),
        "q_major_manifest_lines_materialized": 0,
    }


def _io_benchmark(rows: int) -> dict[str, object] | None:
    if rows == 0:
        return None
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        cache = root / "cache"
        cache.mkdir()
        plan = source_cache_plan(
            t_index_stop_exclusive=rows,
            t_indices_per_shard=rows,
        )
        setup_start = time.perf_counter()
        write_synthetic_cache_shard(
            cache / cache_shard_filename(0),
            plan=plan,
            shard_index=0,
        )
        catalog = cache / "catalog.json"
        build_cache_catalog(
            catalog,
            cache,
            plan=plan,
            require_replayed_receipts=False,
        )
        contract = root / "contract.json"
        build_structural_kat_contract(
            contract,
            cache_root=cache,
            cache_catalog=catalog,
            lane_count=1,
            recovery_artifact_sha256="a" * 64,
            recovery_replay_sha256="b" * 64,
            q_tile_size=1,
            q_start=10_001,
            q_stop=10_001,
        )
        spool_receipt = root / "spool.receipt.json"
        spool = build_lane_spool(
            root / "spool.bin",
            spool_receipt,
            contract_path=contract,
            lane_index=0,
            allow_structural_kat=True,
        )
        setup_seconds = time.perf_counter() - setup_start
        run_start = time.perf_counter()
        receipt = run_supervisor(
            root / "supervisor.receipt.json",
            root / "checkpoints",
            contract_path=contract,
            spool_receipt_path=spool_receipt,
            expected_spool_receipt_sha256=spool["receipt_sha256"],
            worker_command=[
                sys.executable,
                str(ROOT / "tools/tg_dirichlet_tblock_worker.py"),
            ],
            allow_structural_kat=True,
        )
        run_seconds = time.perf_counter() - run_start
        payload_bytes = rows * ROW_PAYLOAD_BYTES
        return {
            "classification": (
                "bounded_structural_protocol_io_not_pipeline_compute"
            ),
            "rows": rows,
            "payload_bytes": payload_bytes,
            "setup_seconds": setup_seconds,
            "supervisor_seconds": run_seconds,
            "effective_payload_mib_per_second": (
                payload_bytes / (1024 * 1024) / run_seconds
            ),
            "completed_blocks": receipt["completed_block_count"],
            "external_atom_discharged": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--io-rows", type=_io_rows, default=0)
    args = parser.parse_args(argv)
    if args.repetitions <= 0:
        parser.error("--repetitions must be positive")
    result = {
        "formula_accounting": _formula_benchmark(args.repetitions),
        "protocol_io": _io_benchmark(args.io_rows),
        "cuda_or_analytic_compute_benchmarked": False,
        "external_atom_discharged": False,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
