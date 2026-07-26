#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Render the kernel-checkable portion of a production CDEM transcript."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.cdem_recurrence_certificate import (
    CdemRecurrenceCertificateError,
    certificate_from_production_transcript,
    render_lean_source,
)
from tg_verifier.evidence import read_artifact_bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a literal Lean chunk certificate from the exact "
            "production CDEM Abel transcript"
        )
    )
    parser.add_argument("transcript", type=Path)
    parser.add_argument(
        "--namespace",
        default="SparkInterval.Generated.CDEMAbelProduction",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write fresh UTF-8 Lean source here instead of stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        certificate = certificate_from_production_transcript(
            read_artifact_bytes(arguments.transcript)
        )
        source = render_lean_source(
            certificate,
            namespace=arguments.namespace,
        )
        if arguments.output is None:
            sys.stdout.write(source)
        else:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            with arguments.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(source)
    except (CdemRecurrenceCertificateError, OSError) as error:
        print(f"CDEM recurrence certificate generation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
