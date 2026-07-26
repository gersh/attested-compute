#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect the metadata-only Sqrt218 pure-entry launcher boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.sqrt218_launcher_boundary import (  # noqa: E402
    LauncherBoundaryError,
    load_manifest,
    require_execution_ready,
    review_summary,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="fail closed unless a future reviewed manifest kind is ready",
    )
    parser.add_argument(
        "--show-contract",
        action="store_true",
        help="include the complete static contract in the JSON output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        manifest = load_manifest(arguments.manifest)
        if arguments.require_ready:
            require_execution_ready(manifest)
        output: dict[str, object] = {
            "manifest_sha256": manifest["manifest_sha256"],
            "review": review_summary(manifest),
        }
        if arguments.show_contract:
            output["contract"] = manifest
        sys.stdout.buffer.write(canonical_json_bytes(output))
        return 0
    except (LauncherBoundaryError, OSError) as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "error": str(exc),
                    "launcher_boundary_valid": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
