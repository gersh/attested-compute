#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tg_verifier.platt_pt21_lean_artifact import (
    PT21LeanArtifactError,
    inspect,
    render_lean_source,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check or emit Lean for one compact PT21 block artifact"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("artifact", type=Path)
    check.add_argument("--required-sign-packet", type=Path)
    check.add_argument("--source-packet", type=Path)
    emit = commands.add_parser("emit-lean")
    emit.add_argument("artifact", type=Path)
    emit.add_argument("--declaration", default="pt21BlockArtifact")
    emit.add_argument("--required-sign-packet", type=Path)
    emit.add_argument("--source-packet", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "check":
            print(json.dumps(inspect(
                args.artifact,
                required_sign_packet=args.required_sign_packet,
                source_packet=args.source_packet,
            ), sort_keys=True, separators=(",", ":")))
        else:
            print(render_lean_source(
                args.artifact,
                args.declaration,
                required_sign_packet=args.required_sign_packet,
                source_packet=args.source_packet,
            ), end="")
    except (OSError, PT21LeanArtifactError) as error:
        print(json.dumps({"accepted": False, "error": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
