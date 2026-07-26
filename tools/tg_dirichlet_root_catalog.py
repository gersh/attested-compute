#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build or audit the source-wide TGDRNRO1 root-artifact catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_root_catalog import (  # noqa: E402
    DirichletRootCatalogError,
    audit_root_catalog,
    build_root_catalog,
    capability,
    split_root_stream,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")

    split = commands.add_parser("split-stream")
    split.add_argument("root_stream", type=Path)
    split.add_argument("receipt_stream", type=Path)
    split.add_argument("output_root", type=Path)
    split.add_argument("--q-start", type=int, default=10_001)
    split.add_argument("--q-stop", type=int, default=400_000)
    split.add_argument("--expected-root-stream-sha256")
    split.add_argument("--expected-receipt-stream-sha256")

    build = commands.add_parser("build")
    build.add_argument("root", type=Path)
    build.add_argument("catalog", type=Path)
    build.add_argument("--q-start", type=int, default=10_001)
    build.add_argument("--q-stop", type=int, default=400_000)

    audit = commands.add_parser("audit")
    audit.add_argument("catalog", type=Path)
    audit.add_argument("--root", type=Path)
    audit.add_argument("--expected-sha256")
    audit.add_argument("--require-full-source", action="store_true")
    audit.add_argument("--revalidate-artifacts", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "split-stream":
            answer = split_root_stream(
                args.root_stream,
                args.receipt_stream,
                args.output_root,
                q_start=args.q_start,
                q_stop=args.q_stop,
                expected_root_stream_sha256=args.expected_root_stream_sha256,
                expected_receipt_stream_sha256=(
                    args.expected_receipt_stream_sha256
                ),
            )
        elif args.command == "build":
            answer = build_root_catalog(
                args.catalog,
                args.root,
                q_start=args.q_start,
                q_stop=args.q_stop,
            )
        elif args.command == "audit":
            answer = audit_root_catalog(
                args.catalog,
                root=args.root,
                expected_sha256=args.expected_sha256,
                require_full_source=args.require_full_source,
                revalidate_artifacts=args.revalidate_artifacts,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (DirichletRootCatalogError, OSError, RuntimeError, ValueError) as error:
        print(f"Dirichlet root catalog error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(answer, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
