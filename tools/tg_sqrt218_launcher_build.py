#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate and index the Sqrt218 cloud launcher build lane."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.sqrt218_launcher_build import (  # noqa: E402
    LauncherBuildError,
    artifact_index,
    load_manifest,
    review_summary,
    source_closure,
    validate_inputs,
)


def _write_new(path: Path, value: object) -> None:
    raw = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o400)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise LauncherBuildError(f"short write to {path}")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate", help="validate metadata and pinned launcher sources"
    )
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--repository-root", type=Path)
    validate.add_argument("--require-build-ready", action="store_true")

    show = commands.add_parser(
        "show-plan", help="show the non-authorizing cloud build plan"
    )
    show.add_argument("manifest", type=Path)

    closure = commands.add_parser(
        "source-closure", help="write the exact cloud source closure"
    )
    closure.add_argument("manifest", type=Path)
    closure.add_argument("--repository-root", type=Path, required=True)
    closure.add_argument("--output", type=Path, required=True)

    index = commands.add_parser(
        "artifact-index", help="index retained outputs after the cloud build"
    )
    index.add_argument("manifest", type=Path)
    index.add_argument("--output-root", type=Path, required=True)
    index.add_argument("--final-image-reference", required=True)
    index.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        manifest = load_manifest(arguments.manifest)
        if arguments.command == "validate":
            if arguments.repository_root is not None:
                validate_inputs(
                    manifest,
                    arguments.repository_root,
                    require_build_ready=arguments.require_build_ready,
                )
            elif arguments.require_build_ready:
                raise LauncherBuildError(
                    "--require-build-ready requires --repository-root"
                )
            output = review_summary(manifest)
        elif arguments.command == "show-plan":
            output = {
                "authority": manifest["authority"],
                "azure": manifest["azure"],
                "build": manifest["build"],
                "container": manifest["container"],
                "review": review_summary(manifest),
                "status": manifest["status"],
                "toolchain": manifest["toolchain"],
            }
        elif arguments.command == "source-closure":
            output = source_closure(manifest, arguments.repository_root)
            _write_new(arguments.output, output)
            output = {
                "authorizes_lean_theorem": False,
                "output": str(arguments.output),
                "source_closure_written": True,
            }
        elif arguments.command == "artifact-index":
            output = artifact_index(
                manifest,
                arguments.output_root,
                arguments.final_image_reference,
            )
            _write_new(arguments.output, output)
            output = {
                "artifact_index_written": True,
                "authorizes_lean_theorem": False,
                "launcher_executed": False,
                "output": str(arguments.output),
            }
        else:  # pragma: no cover
            raise LauncherBuildError("unsupported launcher build command")
        sys.stdout.buffer.write(canonical_json_bytes(output))
        return 0
    except (OSError, LauncherBuildError) as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "error": str(exc),
                    "launcher_build_manifest_valid": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
