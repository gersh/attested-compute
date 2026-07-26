#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize or replay compact small-q ambiguity/sign-transition events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_booker_smallq import (  # noqa: E402
    DirichletBookerSmallQError,
)
from tg_verifier.dirichlet_booker_smallq_factored import (  # noqa: E402
    FactoredSmallQError,
)
from tg_verifier.dirichlet_booker_smallq_sign_scan import (  # noqa: E402
    DEFAULT_CHUNK_CODES,
    SmallQSignScanError,
    inspect_sign_scan,
    materialize_sign_scan,
    verify_sign_scan,
)
from tg_verifier.dirichlet_booker_smallq_semantic_reducer import (  # noqa: E402
    SmallQSemanticReducerError,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _batches(directory: Path) -> list[Path]:
    return sorted(directory.glob("batch-*.bin"))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    materialize = commands.add_parser(
        "materialize",
        help="stream TGDBSSG1 into a deterministic TGDBSZR1 artifact",
    )
    materialize.add_argument("plan", type=Path)
    materialize.add_argument("batch_directory", type=Path)
    materialize.add_argument("sign_artifact", type=Path)
    materialize.add_argument("semantic_reducer_receipt", type=Path)
    materialize.add_argument("scan_artifact", type=Path)
    materialize.add_argument("materializer_receipt", type=Path)
    materialize.add_argument(
        "--chunk-codes", type=_positive, default=DEFAULT_CHUNK_CODES
    )
    materialize.add_argument(
        "--backend", choices=("auto", "numpy", "scalar"), default="auto"
    )

    verify = commands.add_parser(
        "verify",
        help="replay every retained TGDBSZR1 character block and event",
    )
    verify.add_argument("plan", type=Path)
    verify.add_argument("batch_directory", type=Path)
    verify.add_argument("sign_artifact", type=Path)
    verify.add_argument("semantic_reducer_receipt", type=Path)
    verify.add_argument("scan_artifact", type=Path)
    verify.add_argument("materializer_receipt", type=Path)
    verify.add_argument("checker_receipt", type=Path)
    verify.add_argument(
        "--chunk-codes", type=_positive, default=DEFAULT_CHUNK_CODES
    )
    verify.add_argument(
        "--backend", choices=("auto", "numpy", "scalar"), default="auto"
    )

    inspect = commands.add_parser(
        "inspect",
        help="perform structural checks without replaying the source signs",
    )
    inspect.add_argument("scan_artifact", type=Path)

    result.add_argument("--pretty", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command != "inspect":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
        if args.command == "materialize":
            value = materialize_sign_scan(
                args.plan,
                _batches(args.batch_directory),
                args.sign_artifact,
                args.semantic_reducer_receipt,
                args.scan_artifact,
                receipt_path=args.materializer_receipt,
                chunk_codes=args.chunk_codes,
                backend=args.backend,
            )
        elif args.command == "verify":
            value = verify_sign_scan(
                args.plan,
                _batches(args.batch_directory),
                args.sign_artifact,
                args.semantic_reducer_receipt,
                args.scan_artifact,
                args.materializer_receipt,
                receipt_path=args.checker_receipt,
                chunk_codes=args.chunk_codes,
                backend=args.backend,
            )
        else:
            value = inspect_sign_scan(args.scan_artifact)
    except (
        OSError,
        DirichletBookerSmallQError,
        FactoredSmallQError,
        SmallQSemanticReducerError,
        SmallQSignScanError,
        MeasuredWorkerScopeError,
    ) as error:
        print(f"tg_dirichlet_booker_smallq_sign_scan: {error}", file=sys.stderr)
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
