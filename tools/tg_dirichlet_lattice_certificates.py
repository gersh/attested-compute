#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate and independently replay certified Dirichlet lattice inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_certificates import (  # noqa: E402
    DEFAULT_PRECISION_BITS,
    DirichletLatticeCertificateError,
    benchmark_generation,
    capability,
    generate_certificate,
    replay_certificate,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _nonnegative(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def _emit(value: object, *, pretty: bool) -> None:
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

    commands.add_parser("capability", help="report the pinned Arb/FLINT runtime")

    generate = commands.add_parser(
        "generate",
        help="publish one immutable zeta_M lattice and finite-recovery bundle",
    )
    generate.add_argument("root", type=Path)
    generate.add_argument("--q-start", type=_positive, required=True)
    generate.add_argument("--q-stop", type=_positive, required=True)
    generate.add_argument("--t-index", type=_nonnegative, required=True)
    generate.add_argument("--m", type=_positive, required=True)
    generate.add_argument(
        "--precision-bits", type=_positive, default=DEFAULT_PRECISION_BITS
    )
    generate.add_argument(
        "--max-items",
        type=_positive,
        help="explicitly label and truncate a conformance sample",
    )

    replay = commands.add_parser(
        "replay", help="recompute every semantic rectangle at higher precision"
    )
    replay.add_argument("root", type=Path)
    replay.add_argument("--precision-bits", type=_positive)
    replay.add_argument("--report", type=Path)

    benchmark = commands.add_parser(
        "benchmark", help="measure a local producer sample without publishing it"
    )
    benchmark.add_argument("--t-index", type=_nonnegative, default=127)
    benchmark.add_argument("--m", type=_positive, required=True)
    benchmark.add_argument(
        "--precision-bits", type=_positive, default=DEFAULT_PRECISION_BITS
    )
    benchmark.add_argument("--lattice-rows", type=_positive, default=32)
    benchmark.add_argument("--recovery-items", type=_positive, default=128)
    benchmark.add_argument("--tail-repetitions", type=_positive, default=1_000)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "capability":
            result = capability()
        elif args.command == "generate":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            result = generate_certificate(
                args.root,
                q_start=args.q_start,
                q_stop=args.q_stop,
                t_index=args.t_index,
                m=args.m,
                precision_bits=args.precision_bits,
                max_items=args.max_items,
            )
        elif args.command == "replay":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            result = replay_certificate(
                args.root, replay_precision_bits=args.precision_bits
            )
            if args.report is not None:
                if args.report.exists():
                    raise DirichletLatticeCertificateError(
                        f"refusing to replace replay report: {args.report}"
                    )
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(
                    json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="ascii",
                )
        elif args.command == "benchmark":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            result = benchmark_generation(
                t_index=args.t_index,
                m=args.m,
                precision_bits=args.precision_bits,
                lattice_rows=args.lattice_rows,
                recovery_items=args.recovery_items,
                tail_repetitions=args.tail_repetitions,
            )
        else:  # pragma: no cover
            parser.error("unknown command")
        _emit(result, pretty=args.pretty)
        return 0
    except (DirichletLatticeCertificateError, OSError, ValueError) as error:
        print(f"tg_dirichlet_lattice_certificates: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
