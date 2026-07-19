#!/usr/bin/env python3
"""Command-line interface for the exact binary64 interval reference."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Sequence

try:
    from . import evaluator
    from . import format as wire
except ImportError:
    import evaluator  # type: ignore[no-redef]
    import format as wire  # type: ignore[no-redef]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate or verify canonical SparkInterval reference data."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    evaluate = commands.add_parser(
        "evaluate", help="evaluate a canonical batch and write its exact result"
    )
    evaluate.add_argument("batch", type=Path)
    evaluate.add_argument("result", type=Path)

    certify = commands.add_parser(
        "certify", help="evaluate a batch and write a self-contained certificate"
    )
    certify.add_argument("batch", type=Path)
    certify.add_argument("certificate", type=Path)
    certify.add_argument(
        "--result", type=Path,
        help="also write the standalone reference result",
    )

    check = commands.add_parser(
        "check", help="recompute and verify every row in a certificate"
    )
    check.add_argument("certificate", type=Path)

    check_result = commands.add_parser(
        "check-result", help="recompute and verify a separate batch/result pair"
    )
    check_result.add_argument("batch", type=Path)
    check_result.add_argument("result", type=Path)
    return parser


def _load(path: Path) -> Any:
    return wire.load_canonical_json(path)


def _emit_receipt(receipt: dict[str, Any]) -> None:
    # The receipt follows the same no-newline canonical encoding as artifacts.
    sys.stdout.buffer.write(wire.canonical_json_bytes(receipt))
    sys.stdout.buffer.flush()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "evaluate":
            batch = _load(args.batch)
            result = evaluator.evaluate_batch(batch)
            wire.write_canonical_json(args.result, result)
            _emit_receipt({
                "status": "written",
                "artifact": "reference_result",
                "row_count": len(result["rows"]),
                "sha256": wire.canonical_sha256(result),
            })
        elif args.command == "certify":
            batch = _load(args.batch)
            certificate = evaluator.issue_certificate(batch)
            wire.write_canonical_json(args.certificate, certificate)
            if args.result is not None:
                wire.write_canonical_json(args.result, certificate["result"])
            _emit_receipt({
                "status": "written",
                "artifact": "reference_certificate",
                "row_count": len(certificate["result"]["rows"]),
                "sha256": wire.canonical_sha256(certificate),
            })
        elif args.command == "check":
            _emit_receipt(evaluator.check_certificate(_load(args.certificate)))
        elif args.command == "check-result":
            _emit_receipt(
                evaluator.check_result(_load(args.batch), _load(args.result))
            )
        else:  # argparse enforces this.
            raise AssertionError(f"unknown command {args.command!r}")
    except (wire.FormatError, evaluator.EvaluationError, evaluator.CertificateError) as exc:
        print(f"reference error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
