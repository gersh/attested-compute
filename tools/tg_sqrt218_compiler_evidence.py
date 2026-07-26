#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate one compact Sqrt218 compiler-evidence manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.sqrt218_compiler_evidence import (  # noqa: E402
    CompilerEvidenceError,
    execution_closure_projection,
    load_manifest,
    validation_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execution-closure-projection",
        "--projection",
        dest="execution_closure_projection",
        action="store_true",
        help=(
            "emit the review-only exact Lean execution-closure projection "
            "instead of the validation summary"
        ),
    )
    parser.add_argument("manifest", type=Path)
    arguments = parser.parse_args(argv)
    try:
        manifest = load_manifest(arguments.manifest)
        output = (
            execution_closure_projection(manifest)
            if arguments.execution_closure_projection
            else validation_summary(manifest)
        )
        sys.stdout.buffer.write(canonical_json_bytes(output))
        return 0
    except (CompilerEvidenceError, OSError) as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "compiler_evidence_manifest_valid": False,
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
