#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Produce or independently replay the canonical finite Sqrt218 archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.sqrt218_certificate import (  # noqa: E402
    Sqrt218ProducerError,
    write_certificate,
)
from tg_verifier.sqrt218_certificate_verifier import (  # noqa: E402
    Sqrt218VerificationError,
    verify_certificate,
)
from tg_verifier.sqrt218_contract import (  # noqa: E402
    LOCAL_KAT_MAX_BOUND,
    canonical_json_bytes,
    recomputation_run_input_bytes,
)


def _write_fresh(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)
        output.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    produce = subparsers.add_parser("produce")
    produce.add_argument("output", type=Path)
    produce.add_argument("--bound", type=int, required=True)
    produce.add_argument(
        "--cloud-production",
        action="store_true",
        help=(
            "Deprecated and rejected: production execution is available only "
            "through tg_sqrt218_azure_measured_workload.py under the measured "
            "Azure runner."
        ),
    )
    verify = subparsers.add_parser("verify")
    verify.add_argument("certificate", type=Path)
    verify.add_argument("--input", type=Path)
    verify.add_argument("--production", action="store_true")
    verify.add_argument(
        "--cloud-production",
        action="store_true",
        help=(
            "Deprecated and rejected: production replay is available only "
            "through the measured Azure workload."
        ),
    )
    emit_input = subparsers.add_parser("emit-recomputation-input")
    emit_input.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "produce":
            if args.cloud_production or args.bound > LOCAL_KAT_MAX_BOUND:
                raise ValueError(
                    "this standalone CLI is KAT-only (bound <= 64); production "
                    "generation must run through "
                    "tools/tg_sqrt218_azure_measured_workload.py under the "
                    "challenge-bound Azure measured runner"
                )
            result = {
                "accepted": False,
                "classification": "untrusted_certificate_produced_pending_independent_replay",
                **write_certificate(
                    args.output,
                    args.bound,
                ),
            }
        elif args.command == "verify":
            if args.production or args.cloud_production:
                raise ValueError(
                    "this standalone CLI is KAT-only; production replay must "
                    "run through tools/tg_sqrt218_azure_measured_workload.py "
                    "under the challenge-bound Azure measured runner"
                )
            result = verify_certificate(
                args.certificate,
                run_input_path=args.input,
                require_production=False,
            )
        else:
            _write_fresh(args.output, recomputation_run_input_bytes())
            result = {
                "accepted": False,
                "classification": "recomputation_input_emitted_not_execution_evidence",
                "path": str(args.output),
                "size_bytes": args.output.stat().st_size,
            }
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
        return 0
    except (
        OSError,
        Sqrt218ProducerError,
        Sqrt218VerificationError,
        ValueError,
    ) as error:
        sys.stdout.write(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "sqrt218_certificate_operation_failed_closed",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
