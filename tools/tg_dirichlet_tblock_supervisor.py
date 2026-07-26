#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or inspect the fail-closed Dirichlet t-block service supervisor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tblock_supervisor import (  # noqa: E402
    DirichletTBlockSupervisorError,
    capability,
    run_supervisor,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


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

    run = commands.add_parser("run")
    run.add_argument("contract", type=Path)
    run.add_argument("spool_receipt", type=Path)
    run.add_argument("checkpoint_directory", type=Path)
    run.add_argument("output_receipt", type=Path)
    run.add_argument("--expected-spool-receipt-sha256", required=True)
    run.add_argument("--expected-contract-sha256")
    run.add_argument("--expected-worker-handshake-sha256")
    run.add_argument("--expected-worker-implementation-sha256")
    run.add_argument("--expected-checkpoint-chain-sha256")
    run.add_argument("--allow-structural-kat", action="store_true")
    run.add_argument("--stop-after-blocks", type=_positive)
    run.add_argument(
        "--worker-command",
        nargs="+",
        required=True,
        help="long-lived worker argv; place this option last",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "run":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            answer = run_supervisor(
                args.output_receipt,
                args.checkpoint_directory,
                contract_path=args.contract,
                spool_receipt_path=args.spool_receipt,
                expected_spool_receipt_sha256=(
                    args.expected_spool_receipt_sha256
                ),
                worker_command=args.worker_command,
                allow_structural_kat=args.allow_structural_kat,
                expected_contract_sha256=args.expected_contract_sha256,
                expected_worker_handshake_sha256=(
                    args.expected_worker_handshake_sha256
                ),
                expected_worker_implementation_sha256=(
                    args.expected_worker_implementation_sha256
                ),
                expected_checkpoint_chain_sha256=(
                    args.expected_checkpoint_chain_sha256
                ),
                stop_after_blocks=args.stop_after_blocks,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (
        DirichletTBlockSupervisorError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"Dirichlet t-block supervisor error: {error}", file=sys.stderr)
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
