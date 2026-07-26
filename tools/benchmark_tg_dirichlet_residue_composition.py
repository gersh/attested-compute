#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark full synthetic residue-composition batches, including I/O/hash checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.tg_dirichlet_residue_composition_fixture import write_job  # type: ignore  # noqa: E402
from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    CompositionEngine,
    DirichletResidueCompositionError,
)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--q", type=_positive, default=10_001)
    parser.add_argument("--batch-count", type=_positive, default=8)
    parser.add_argument("--first-t-index", type=_positive, default=127)
    parser.add_argument("--precision-bits", type=_positive, default=192)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            indices = tuple(
                range(args.first_t_index, args.first_t_index + args.batch_count)
            )
            job, frames = write_job(root, q=args.q, t_indices=indices)
            upstream_bytes = sum(
                path.stat().st_size for frame in frames for path in frame.values()
            )
            output = root / "composed.bin"
            engine = CompositionEngine(
                factor_precision_bits=args.precision_bits,
                max_batch_count=args.batch_count,
            )
            receipt = engine.compose(job, output, allow_synthetic_kat=True)
            report = {
                "kind": (
                    "sparkinterval.tg.dirichlet_residue_composition."
                    "representative_batch_benchmark.v1"
                ),
                "classification": (
                    "synthetic_full_adapter_batch_not_analytic_or_atom_runtime"
                ),
                "q": args.q,
                "batch_count": args.batch_count,
                "group_order": receipt["group_order"],
                "value_count": receipt["value_count"],
                "upstream_bytes_hashed_and_parsed": upstream_bytes,
                "TGDAFFI1_bytes_written": receipt["output"]["size_bytes"],
                "elapsed_seconds": receipt["elapsed_seconds"],
                "values_per_second": receipt["values_per_second"],
                "factor_precision_bits": args.precision_bits,
                "maximum_live_binary_interval_payload_bytes": receipt[
                    "bounded_working_set"
                ]["binary_interval_payload_bytes"],
                "includes": [
                    "SHA-256 prevalidation and post-parse revalidation of every synthetic upstream artifact",
                    "TGDLATI1/TGDLATO1/TGDLREC1 lockstep parsing",
                    "MPFR q^(-s) factor generation",
                    "outward interval composition and canonical CRT reordering",
                    "TGDAFFI1 write, hash, flush, fsync, and atomic rename",
                ],
                "excludes": [
                    "synthetic fixture generation",
                    "real lattice/recovery generation and Taylor GPU work",
                    "independent 384-bit replay",
                    "all-character FFT and every zero-closure stage",
                ],
            }
        print(
            json.dumps(
                report,
                sort_keys=True,
                indent=2 if args.pretty else None,
                separators=None if args.pretty else (",", ":"),
            )
        )
        return 0
    except (DirichletResidueCompositionError, OSError, ValueError) as error:
        print(
            f"benchmark_tg_dirichlet_residue_composition: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
