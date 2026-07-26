#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit the static ternary-Goldbach compact receipt closure matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.compact_receipt_closure import (  # noqa: E402
    DEFAULT_MANIFEST,
    CompactReceiptClosureError,
    load_and_validate_closure,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check all thirteen TG external atoms plus the lowered "
            "10^27 endpoint without replaying production data"
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="closure inventory to audit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the small summary as canonical JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        document = load_and_validate_closure(
            arguments.manifest,
            repository_root=REPOSITORY_ROOT,
        )
    except CompactReceiptClosureError as error:
        print(f"compact receipt closure audit failed: {error}", file=sys.stderr)
        return 1

    summary = {
        "campaigns": len(document["campaigns"]),
        "claims": len(document["claims"]),
        "exact_executable_refinements": document["summary"][
            "campaigns_with_exact_executable_refinement"
        ],
        "kind": document["kind"],
        "one_receipt_claim_authorities": document["summary"][
            "campaigns_with_one_receipt_claim_authority_now"
        ],
        "status": "static_audit_passed",
    }
    if arguments.json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "compact receipt closure audit passed: "
            f"{summary['claims']} claims / {summary['campaigns']} campaigns; "
            "0 exact executable refinements and 0 current receipt authorities"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
