#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Author and inspect fused large-q certified-box CUDA batches."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_largeq_batch import (  # noqa: E402
    capability,
    pack_input,
    pretty_json,
    source_work,
    write_job_from_composition_job,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("capability")
    work = subparsers.add_parser("work")
    work.add_argument("--batch-size", type=_positive, default=64)

    convert = subparsers.add_parser("convert-composition-job")
    convert.add_argument("composition_job", type=Path)
    convert.add_argument("output", type=Path)
    convert.add_argument("--certified", action="store_true")

    pack = subparsers.add_parser("pack")
    pack.add_argument("job", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--receipt", type=Path)
    pack.add_argument("--allow-synthetic-kat", action="store_true")
    pack.add_argument("--factor-precision-bits", type=_positive, default=192)
    args = parser.parse_args()
    if args.command == "capability":
        report = capability()
    elif args.command == "work":
        report = source_work(batch_size=args.batch_size)
    elif args.command == "convert-composition-job":
        report = write_job_from_composition_job(
            args.composition_job, args.output, certified=args.certified
        )
    else:
        report = pack_input(
            args.job,
            args.output,
            receipt_path=args.receipt,
            allow_synthetic_kat=args.allow_synthetic_kat,
            factor_precision_bits=args.factor_precision_bits,
        )
    sys.stdout.write(pretty_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
