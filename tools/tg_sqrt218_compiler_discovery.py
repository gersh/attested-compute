#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect the non-authorizing Sqrt218 compiler-discovery metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.sqrt218_compiler_discovery import (  # noqa: E402
    CompilerDiscoveryError,
    load_manifest,
    review_summary,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "show-plan"),
        help="both commands read only the bounded manifest file",
    )
    parser.add_argument("manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        manifest = load_manifest(arguments.manifest)
        if arguments.command == "validate":
            output: object = review_summary(manifest)
        else:
            output = {
                "authority": manifest["authority"],
                "cloud_policy": manifest["cloud_policy"],
                "elf_gate": manifest["elf_gate"],
                "inventory_contract": manifest["inventory_contract"],
                "pipeline": manifest["pipeline"],
                "retained_artifacts": manifest["retained_artifacts"],
                "review": review_summary(manifest),
                "scope": manifest["scope"],
                "toolchain": manifest["toolchain"],
            }
        sys.stdout.buffer.write(canonical_json_bytes(output))
        return 0
    except (OSError, CompilerDiscoveryError) as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "compiler_discovery_manifest_valid": False,
                    "error": str(exc),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
