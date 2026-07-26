#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate and index the fail-closed Sqrt218 cloud proof-build lane."""

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
from tg_verifier.sqrt218_proof_build import (  # noqa: E402
    ProofBuildError,
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
                raise ProofBuildError(f"short write to {path}")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate", help="validate metadata and pinned source identities"
    )
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--repository-root", type=Path)
    validate.add_argument("--proof-root", type=Path)
    validate.add_argument("--require-ready", action="store_true")

    show = subparsers.add_parser(
        "show-plan", help="emit the non-authorizing reviewed cloud plan"
    )
    show.add_argument("manifest", type=Path)

    closure = subparsers.add_parser(
        "source-closure",
        help="write a canonical source/proof pin closure inside the cloud job",
    )
    closure.add_argument("manifest", type=Path)
    closure.add_argument("--repository-root", type=Path, required=True)
    closure.add_argument("--proof-root", type=Path, required=True)
    closure.add_argument("--output", type=Path, required=True)

    index = subparsers.add_parser(
        "artifact-index",
        help="index retained outputs after a successful cloud proof build",
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
                    proof_root=arguments.proof_root,
                    require_ready=arguments.require_ready,
                )
            elif arguments.require_ready or arguments.proof_root is not None:
                raise ProofBuildError(
                    "--require-ready/--proof-root requires --repository-root"
                )
            output = review_summary(manifest)
        elif arguments.command == "show-plan":
            output = {
                "authority": dict(manifest["authority"]),
                "azure": manifest["azure"],
                "container": manifest["container"],
                "pipeline": manifest["pipeline"],
                "proof_project": manifest["proof_project"],
                "review": review_summary(manifest),
                "toolchain": manifest["toolchain"],
            }
        elif arguments.command == "source-closure":
            output = source_closure(
                manifest,
                arguments.repository_root,
                arguments.proof_root,
            )
            _write_new(arguments.output, output)
            output = {
                "authorizes_lean_theorem": False,
                "output": str(arguments.output),
                "production_certificate_opened": False,
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
                "output": str(arguments.output),
                "production_execution_performed": False,
            }
        else:  # pragma: no cover - argparse closes this branch.
            raise ProofBuildError("unsupported proof-build command")
        sys.stdout.buffer.write(canonical_json_bytes(output))
        return 0
    except (OSError, ProofBuildError) as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "error": str(exc),
                    "proof_build_manifest_valid": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
