#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate, replay, and benchmark compact Dirichlet recovery seeds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_recovery_seeds import (  # noqa: E402
    DEFAULT_CHUNK_RECORDS,
    DEFAULT_PRECISION_BITS,
    DEFAULT_REPLAY_PRECISION_BITS,
    DirichletRecoverySeedError,
    benchmark_seed_recurrence,
    capability,
    convert_largeq_v1_to_seeded_v2,
    generate_seed_artifact,
    verify_cuda_output,
    verify_seed_artifact,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be nonnegative")
    return parsed


def _emit(value: object, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")

    generate = commands.add_parser("generate")
    generate.add_argument("artifact", type=Path)
    generate.add_argument("manifest", type=Path)
    generate.add_argument(
        "--precision-bits", type=_positive, default=DEFAULT_PRECISION_BITS
    )
    generate.add_argument(
        "--chunk-records", type=_positive, default=DEFAULT_CHUNK_RECORDS
    )
    generate.add_argument(
        "--sample-x-stop",
        type=_positive,
        help="explicitly create a bounded-prefix KAT instead of the full table",
    )

    replay = commands.add_parser("replay")
    replay.add_argument("artifact", type=Path)
    replay.add_argument("manifest", type=Path)
    replay.add_argument(
        "--precision-bits", type=_positive, default=DEFAULT_REPLAY_PRECISION_BITS
    )
    replay.add_argument("--report", type=Path)

    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("artifact", type=Path)
    benchmark.add_argument("--q", type=_positive, default=10_001)
    benchmark.add_argument("--t-index", type=_nonnegative, default=127_987)
    benchmark.add_argument("--residues", type=_positive, default=1_024)

    audit = commands.add_parser("audit-cuda-output")
    audit.add_argument("artifact", type=Path)
    audit.add_argument("artifact_sha256")
    audit.add_argument("output", type=Path)
    audit.add_argument(
        "--maximum-values",
        type=_positive,
        help="explicit deterministic KAT sample; omit to replay the complete frame",
    )
    audit.add_argument("--precision-bits", type=_positive, default=384)

    convert = commands.add_parser("convert-largeq-v1")
    convert.add_argument("source", type=Path)
    convert.add_argument("source_sha256")
    convert.add_argument("seed_artifact_sha256")
    convert.add_argument("seed_replay_sha256")
    convert.add_argument("output", type=Path)
    convert.add_argument("--receipt", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "capability":
            result = capability()
        elif args.command == "generate":
            require_azure_measured_worker_for_workload(
                exact_production=args.sample_x_stop is None,
                work_bounds=(
                    ()
                    if args.sample_x_stop is None
                    else (args.sample_x_stop,)
                ),
            )
            result = generate_seed_artifact(
                args.artifact,
                args.manifest,
                precision_bits=args.precision_bits,
                chunk_records=args.chunk_records,
                sample_x_stop=args.sample_x_stop,
            )
        elif args.command == "replay":
            # The record count is authenticated inside the artifact and this
            # command has no truncation option.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            result = verify_seed_artifact(
                args.artifact,
                args.manifest,
                replay_precision_bits=args.precision_bits,
            )
            if args.report is not None:
                if args.report.exists():
                    raise DirichletRecoverySeedError(
                        f"refusing to replace immutable report: {args.report}"
                    )
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(
                    json.dumps(
                        result["replay"], sort_keys=True, separators=(",", ":")
                    )
                    + "\n",
                    encoding="ascii",
                )
        elif args.command == "benchmark":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(args.residues,),
            )
            result = benchmark_seed_recurrence(
                args.artifact,
                q=args.q,
                t_index=args.t_index,
                residues=args.residues,
            )
        elif args.command == "audit-cuda-output":
            require_azure_measured_worker_for_workload(
                exact_production=args.maximum_values is None,
                work_bounds=(
                    ()
                    if args.maximum_values is None
                    else (args.maximum_values,)
                ),
            )
            result = verify_cuda_output(
                args.artifact,
                args.artifact_sha256,
                args.output,
                maximum_values=args.maximum_values,
                arb_precision_bits=args.precision_bits,
            )
        else:
            result = convert_largeq_v1_to_seeded_v2(
                args.source,
                args.output,
                expected_source_sha256=args.source_sha256,
                seed_artifact_sha256=args.seed_artifact_sha256,
                seed_replay_sha256=args.seed_replay_sha256,
                receipt_path=args.receipt,
            )
        _emit(result, args.pretty)
        return 0
    except (DirichletRecoverySeedError, OSError, ValueError) as error:
        print(f"tg_dirichlet_recovery_seeds: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
