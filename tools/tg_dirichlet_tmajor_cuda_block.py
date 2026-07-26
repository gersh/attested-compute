#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tmajor_cuda_block import (  # noqa: E402
    TMajorCudaBlockBuilder,
    benchmark_direct_sidecars,
    capability,
    replay_tmajor_cuda_block,
    source_projection,
    validate_tmajor_cuda_execution_summary,
)
from tg_verifier.dirichlet_tmajor_cuda_arithmetic_replay import (  # noqa: E402
    validate_tmajor_cuda_execution_arithmetic_sample,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build/replay one authenticated row-resident CUDA block"
    )
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build")
    build.add_argument("contract", type=Path)
    build.add_argument("spool_receipt", type=Path)
    build.add_argument("sidecar_manifest", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("receipt", type=Path)
    build.add_argument("--first-t-index", type=int, required=True)
    build.add_argument("--expected-contract-sha256")
    build.add_argument("--expected-spool-receipt-sha256", required=True)
    build.add_argument("--expected-sidecar-manifest-sha256", required=True)
    build.add_argument("--allow-structural-kat", action="store_true")

    direct = commands.add_parser("build-direct")
    direct.add_argument("contract", type=Path)
    direct.add_argument("spool_receipt", type=Path)
    direct.add_argument("output", type=Path)
    direct.add_argument("receipt", type=Path)
    direct.add_argument("--first-t-index", type=int, required=True)
    direct.add_argument("--expected-contract-sha256")
    direct.add_argument(
        "--expected-spool-receipt-sha256", required=True
    )
    direct.add_argument("--allow-structural-kat", action="store_true")

    replay = commands.add_parser("replay")
    replay.add_argument("artifact", type=Path)
    replay.add_argument("receipt", type=Path)
    replay.add_argument("--expected-receipt-sha256", required=True)

    execution = commands.add_parser("validate-execution")
    execution.add_argument("summary", type=Path)
    execution.add_argument("artifact", type=Path)
    execution.add_argument("receipt", type=Path)
    execution.add_argument("--expected-summary-sha256", required=True)
    execution.add_argument("--expected-receipt-sha256", required=True)

    arithmetic = commands.add_parser("validate-arithmetic")
    arithmetic.add_argument("summary", type=Path)
    arithmetic.add_argument("artifact", type=Path)
    arithmetic.add_argument("receipt", type=Path)
    arithmetic.add_argument("seed_artifact", type=Path)
    arithmetic.add_argument("output_stream", type=Path)
    arithmetic.add_argument("--expected-summary-sha256", required=True)
    arithmetic.add_argument("--expected-receipt-sha256", required=True)
    arithmetic.add_argument(
        "--expected-seed-artifact-sha256", required=True
    )
    arithmetic.add_argument("--maximum-targets", type=int, default=8)
    arithmetic.add_argument(
        "--maximum-values-per-target", type=int, default=8
    )
    arithmetic.add_argument(
        "--independent-arb-factor-precision-bits", type=int
    )

    commands.add_parser("capability")
    commands.add_parser("projection")
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--q", type=int, default=10_001)
    benchmark.add_argument("--batch-count", type=int, default=64)
    benchmark.add_argument("--repetitions", type=int, default=64)
    return result


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            value = capability()
        elif args.command == "projection":
            value = source_projection()
        elif args.command == "benchmark":
            value = benchmark_direct_sidecars(
                q=args.q,
                batch_count=args.batch_count,
                repetitions=args.repetitions,
            )
        elif args.command == "replay":
            value = replay_tmajor_cuda_block(
                args.artifact,
                args.receipt,
                expected_receipt_sha256=args.expected_receipt_sha256,
            )
        elif args.command == "validate-execution":
            value = validate_tmajor_cuda_execution_summary(
                args.summary,
                args.artifact,
                args.receipt,
                expected_summary_sha256=args.expected_summary_sha256,
                expected_receipt_sha256=args.expected_receipt_sha256,
            )
        elif args.command == "validate-arithmetic":
            value = validate_tmajor_cuda_execution_arithmetic_sample(
                args.summary,
                args.artifact,
                args.receipt,
                args.seed_artifact,
                args.output_stream,
                expected_summary_sha256=args.expected_summary_sha256,
                expected_receipt_sha256=args.expected_receipt_sha256,
                expected_seed_artifact_sha256=(
                    args.expected_seed_artifact_sha256
                ),
                maximum_targets=args.maximum_targets,
                maximum_values_per_target=(
                    args.maximum_values_per_target
                ),
                independent_arb_factor_precision_bits=(
                    args.independent_arb_factor_precision_bits
                ),
            )
        elif args.command in {"build", "build-direct"}:
            with TMajorCudaBlockBuilder(
                contract_path=args.contract,
                spool_receipt_path=args.spool_receipt,
                expected_spool_receipt_sha256=(
                    args.expected_spool_receipt_sha256
                ),
                expected_contract_sha256=args.expected_contract_sha256,
                allow_structural_kat=args.allow_structural_kat,
            ) as builder:
                if args.command == "build-direct":
                    value = builder.build(
                        args.output,
                        args.receipt,
                        first_t_index=args.first_t_index,
                        direct_sidecars=True,
                    )
                else:
                    value = builder.build(
                        args.output,
                        args.receipt,
                        sidecar_manifest_path=args.sidecar_manifest,
                        expected_sidecar_manifest_sha256=(
                            args.expected_sidecar_manifest_sha256
                        ),
                        first_t_index=args.first_t_index,
                    )
        else:
            raise AssertionError("unreachable command")
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Dirichlet t-major CUDA block error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            value,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
