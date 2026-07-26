#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build and replay authenticated t-major shared-row/fixed-q spool inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tmajor_spool import (  # noqa: E402
    AuthenticatedQContiguousSpool,
    DirichletTMajorSpoolError,
    build_lane_spool,
    build_run_manifest,
    capability,
    replay_run_manifest,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _nonnegative(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def _positive(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")

    build = commands.add_parser("build-spool")
    build.add_argument("contract", type=Path)
    build.add_argument("spool", type=Path)
    build.add_argument("receipt", type=Path)
    build.add_argument("--lane-index", type=_nonnegative, required=True)
    build.add_argument("--expected-contract-sha256")
    build.add_argument("--allow-structural-kat", action="store_true")

    audit = commands.add_parser("audit-spool")
    audit.add_argument("contract", type=Path)
    audit.add_argument("receipt", type=Path)
    audit.add_argument("--expected-receipt-sha256", required=True)
    audit.add_argument("--expected-contract-sha256")
    audit.add_argument("--allow-structural-kat", action="store_true")

    run = commands.add_parser("emit-run")
    run.add_argument("contract", type=Path)
    run.add_argument("receipt", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--q", type=_positive, required=True)
    run.add_argument("--first-t-index", type=_nonnegative, required=True)
    run.add_argument("--expected-receipt-sha256", required=True)
    run.add_argument("--expected-contract-sha256")
    run.add_argument("--allow-structural-kat", action="store_true")

    roster = commands.add_parser("build-run-manifest")
    roster.add_argument("contract", type=Path)
    roster.add_argument("spool_receipt", type=Path)
    roster.add_argument("manifest", type=Path)
    roster.add_argument("manifest_receipt", type=Path)
    roster.add_argument("--expected-spool-receipt-sha256", required=True)
    roster.add_argument("--expected-contract-sha256")
    roster.add_argument("--allow-structural-kat", action="store_true")

    replay = commands.add_parser("replay-run-manifest")
    replay.add_argument("contract", type=Path)
    replay.add_argument("spool_receipt", type=Path)
    replay.add_argument("manifest", type=Path)
    replay.add_argument("manifest_receipt", type=Path)
    replay.add_argument("--expected-spool-receipt-sha256", required=True)
    replay.add_argument("--expected-manifest-receipt-sha256", required=True)
    replay.add_argument("--expected-contract-sha256")
    replay.add_argument("--allow-structural-kat", action="store_true")
    return result


def _open_spool(args: argparse.Namespace) -> AuthenticatedQContiguousSpool:
    return AuthenticatedQContiguousSpool(
        args.spool_receipt if hasattr(args, "spool_receipt") else args.receipt,
        contract_path=args.contract,
        expected_receipt_sha256=(
            args.expected_spool_receipt_sha256
            if hasattr(args, "expected_spool_receipt_sha256")
            else args.expected_receipt_sha256
        ),
        allow_structural_kat=args.allow_structural_kat,
        expected_contract_sha256=args.expected_contract_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {
            "build-spool",
            "emit-run",
            "build-run-manifest",
            "replay-run-manifest",
        }:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
        if args.command == "capability":
            answer = capability()
        elif args.command == "build-spool":
            answer = build_lane_spool(
                args.spool,
                args.receipt,
                contract_path=args.contract,
                lane_index=args.lane_index,
                allow_structural_kat=args.allow_structural_kat,
                expected_contract_sha256=args.expected_contract_sha256,
            )
        elif args.command == "audit-spool":
            with _open_spool(args) as spool:
                answer = {
                    "accepted": True,
                    "algorithm_id": spool.receipt["algorithm_id"],
                    "source_contract_sha256": spool.contract[
                        "contract_sha256"
                    ],
                    "spool_receipt_sha256": spool.receipt_sha256,
                    "lane_index": spool.lane_index,
                    "row_schedule_sha256": spool.row_schedule_sha256,
                    "schedule_accounting": spool.receipt[
                        "schedule_accounting"
                    ],
                    "source_scale_spool_run_completed": False,
                    "row_resident_cuda_kernel_executed": False,
                    "external_atom_discharged": False,
                }
        elif args.command == "emit-run":
            with _open_spool(args) as spool:
                answer = spool.write_run_input(
                    args.output,
                    q=args.q,
                    first_t_index=args.first_t_index,
                )
        elif args.command == "build-run-manifest":
            with _open_spool(args) as spool:
                answer = build_run_manifest(
                    args.manifest,
                    args.manifest_receipt,
                    spool=spool,
                )
        elif args.command == "replay-run-manifest":
            with _open_spool(args) as spool:
                answer = replay_run_manifest(
                    args.manifest,
                    args.manifest_receipt,
                    spool=spool,
                    expected_receipt_sha256=(
                        args.expected_manifest_receipt_sha256
                    ),
                )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (DirichletTMajorSpoolError, OSError, RuntimeError, ValueError) as error:
        print(f"Dirichlet t-major spool error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            answer,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
