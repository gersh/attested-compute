#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, populate, authenticate, and benchmark the t-major Hurwitz cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_cache import (  # noqa: E402
    DEFAULT_BROADCAST_LANES,
    DEFAULT_T_INDICES_PER_SHARD,
    SOURCE_T_INDEX_STOP,
    DirichletLatticeCacheError,
    benchmark_cache_io,
    broadcast_plan,
    build_cache_catalog,
    cache_shard_filename,
    capability,
    inspect_cache_shard,
    iter_catalog_rows,
    pack_replayed_lattice_certificates,
    projection,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _positive(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _nonnegative(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
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


def _add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--t-index-stop",
        type=_positive,
        default=SOURCE_T_INDEX_STOP,
        help="exclusive stop; changing it labels a bounded-prefix KAT",
    )
    parser.add_argument(
        "--t-indices-per-shard",
        type=_positive,
        default=DEFAULT_T_INDICES_PER_SHARD,
    )


def _plan(args: argparse.Namespace) -> dict[str, object]:
    return source_cache_plan(
        t_index_stop_exclusive=args.t_index_stop,
        t_indices_per_shard=args.t_indices_per_shard,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("capability")

    plan = commands.add_parser("plan")
    _add_plan_arguments(plan)

    broadcast = commands.add_parser("broadcast-plan")
    _add_plan_arguments(broadcast)
    broadcast.add_argument(
        "--lanes", type=_positive, default=DEFAULT_BROADCAST_LANES
    )

    synthetic = commands.add_parser("synthetic-shard")
    _add_plan_arguments(synthetic)
    synthetic.add_argument("root", type=Path)
    synthetic.add_argument("shard_index", type=_nonnegative)

    inspect = commands.add_parser("inspect-shard")
    _add_plan_arguments(inspect)
    inspect.add_argument("artifact", type=Path)
    inspect.add_argument("shard_index", type=_nonnegative)
    inspect.add_argument("--sha256")
    inspect.add_argument("--validate-cells", action="store_true")

    pack = commands.add_parser("pack-replayed-shard")
    _add_plan_arguments(pack)
    pack.add_argument("artifact", type=Path)
    pack.add_argument("receipt", type=Path)
    pack.add_argument("shard_index", type=_nonnegative)
    pack.add_argument("certificate_roots", nargs="+", type=Path)
    pack.add_argument("--replay-precision-bits", type=_positive)

    catalog = commands.add_parser("build-catalog")
    _add_plan_arguments(catalog)
    catalog.add_argument("root", type=Path)
    catalog.add_argument("catalog", type=Path)
    catalog.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="permit a structural/KAT catalog with no analytic replay claim",
    )

    audit = commands.add_parser("audit-catalog")
    audit.add_argument("root", type=Path)
    audit.add_argument("catalog", type=Path)
    audit.add_argument("--require-replayed", action="store_true")

    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--t-indices", type=_positive, default=4)
    benchmark.add_argument("--repetitions", type=_positive, default=3)

    project = commands.add_parser("project")
    project.add_argument(
        "--authenticated-file-bytes-per-second",
        type=_positive_float,
        required=True,
    )
    project.add_argument(
        "--analytic-cells-per-second",
        type=_positive_float,
    )
    project.add_argument(
        "--lanes", type=_positive, default=DEFAULT_BROADCAST_LANES
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if (
            args.command
            in {"synthetic-shard", "pack-replayed-shard", "benchmark"}
            or (
                args.command == "inspect-shard"
                and args.validate_cells
            )
        ):
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
        if args.command == "capability":
            result = capability()
        elif args.command == "plan":
            result = _plan(args)
        elif args.command == "broadcast-plan":
            result = broadcast_plan(_plan(args), lane_count=args.lanes)
        elif args.command == "synthetic-shard":
            plan = _plan(args)
            args.root.mkdir(parents=True, exist_ok=True)
            result = write_synthetic_cache_shard(
                args.root / cache_shard_filename(args.shard_index),
                plan=plan,
                shard_index=args.shard_index,
            )
        elif args.command == "inspect-shard":
            result = inspect_cache_shard(
                args.artifact,
                plan=_plan(args),
                shard_index=args.shard_index,
                expected_sha256=args.sha256,
                validate_cells=args.validate_cells,
            )
        elif args.command == "pack-replayed-shard":
            result = pack_replayed_lattice_certificates(
                args.artifact,
                args.receipt,
                plan=_plan(args),
                shard_index=args.shard_index,
                certificate_roots=args.certificate_roots,
                replay_precision_bits=args.replay_precision_bits,
            )
        elif args.command == "build-catalog":
            result = build_cache_catalog(
                args.catalog,
                args.root,
                plan=_plan(args),
                require_replayed_receipts=not args.allow_synthetic,
            )
        elif args.command == "audit-catalog":
            started = time.perf_counter()
            count = sum(
                1
                for _row in iter_catalog_rows(
                    args.root,
                    args.catalog,
                    require_replayed=args.require_replayed,
                )
            )
            result = {
                "classification": (
                    "complete_catalog_transport_audit_not_hurwitz_semantic_replay"
                ),
                "t_rows_authenticated": count,
                "elapsed_seconds": time.perf_counter() - started,
                "external_atom_discharged": False,
            }
        elif args.command == "benchmark":
            result = benchmark_cache_io(
                t_indices=args.t_indices,
                repetitions=args.repetitions,
            )
        else:
            result = projection(
                authenticated_file_bytes_per_second=(
                    args.authenticated_file_bytes_per_second
                ),
                lane_count=args.lanes,
                analytic_cells_per_second=args.analytic_cells_per_second,
            )
        _emit(result, args.pretty)
        return 0
    except (DirichletLatticeCacheError, OSError, ValueError) as error:
        print(f"tg_dirichlet_lattice_cache: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
